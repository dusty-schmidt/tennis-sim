"""
Game-level simulation: standard service game and tiebreak.

Upgrades (v2):
  - Deuce reset trick: when both players reach 4 points (4-4), reset to 3-3.
    This prevents any edge-case infinite loops and matches the tennisim pattern.
  - Tiebreak serve rotation: explicit state-machine (1-2-2-2...) from tennisim,
    replacing the block-formula which could drift on long tiebreaks.
"""
from dataclasses import dataclass
from .point import derive_serve_probs, simulate_point


@dataclass
class GameResult:
    winner: int          # 0 = server wins, 1 = returner wins
    server_points: int
    returner_points: int
    aces: int
    double_faults: int
    is_tiebreak: bool = False


def simulate_game(server, returner, rng=None) -> GameResult:
    """
    Simulate a standard service game.
    Win condition: first to 4 points with a lead of 2 (deuce/advantage handled).

    Uses the deuce-reset trick: when both players reach 4 points, reset to 3-3.
    This keeps the loop finite and matches the tennisim reference implementation.
    """
    import numpy as np
    if rng is None:
        rng = np.random.default_rng()

    probs = derive_serve_probs(server, returner)
    ppg = 4  # points per game (minimum to win)

    sv_pts = 0
    rt_pts = 0
    aces = 0
    dfs = 0

    # Pre-deuce phase: play until one player reaches ppg or both reach ppg-1 (deuce)
    while sv_pts < ppg and rt_pts < ppg:
        result = simulate_point(server, returner, probs=probs, rng=rng)
        if result.is_ace:
            aces += 1
        if result.is_double_fault:
            dfs += 1

        if result.winner == 0:
            sv_pts += 1
        else:
            rt_pts += 1

    # If one player won cleanly (no deuce)
    if sv_pts == ppg and rt_pts < ppg - 1:
        return GameResult(winner=0, server_points=sv_pts, returner_points=rt_pts,
                          aces=aces, double_faults=dfs)
    if rt_pts == ppg and sv_pts < ppg - 1:
        return GameResult(winner=1, server_points=sv_pts, returner_points=rt_pts,
                          aces=aces, double_faults=dfs)

    # If we reached here, one player has ppg and the other has ppg-1 (e.g. 4-3)
    # OR both reached ppg (deuce - 4-4 -> reset to 3-3)
    # Handle 4-3 / 3-4 (advantage) — one more point decides
    if sv_pts == ppg and rt_pts == ppg - 1:
        # Server at advantage: one point wins
        result = simulate_point(server, returner, probs=probs, rng=rng)
        if result.is_ace: aces += 1
        if result.is_double_fault: dfs += 1
        if result.winner == 0:
            sv_pts += 1
            return GameResult(winner=0, server_points=sv_pts, returner_points=rt_pts,
                              aces=aces, double_faults=dfs)
        else:
            rt_pts += 1
            # Now at deuce (4-4): fall through to deuce loop below

    elif rt_pts == ppg and sv_pts == ppg - 1:
        # Returner at advantage
        result = simulate_point(server, returner, probs=probs, rng=rng)
        if result.is_ace: aces += 1
        if result.is_double_fault: dfs += 1
        if result.winner == 1:
            rt_pts += 1
            return GameResult(winner=1, server_points=sv_pts, returner_points=rt_pts,
                              aces=aces, double_faults=dfs)
        else:
            sv_pts += 1
            # Now at deuce (4-4): fall through to deuce loop below

    # Deuce loop with reset trick
    # At this point both are at ppg (4-4). Reset to deuce (3-3) and play advantage-game.
    s = ppg - 1
    r = ppg - 1

    while True:
        # Play from deuce: need to win 2 consecutive points (advantage then game)
        # But we use the reset trick: give a bit of space (play to ppg+1)
        # and if both reach ppg again, reset back to ppg-1
        while s < ppg + 1 and r < ppg + 1:
            result = simulate_point(server, returner, probs=probs, rng=rng)
            if result.is_ace: aces += 1
            if result.is_double_fault: dfs += 1
            if result.winner == 0:
                s += 1
            else:
                r += 1
            # Deuce reset: if both at ppg, bring back to ppg-1
            if s == ppg and r == ppg:
                s = ppg - 1
                r = ppg - 1

        # Someone won the deuce phase
        if s == ppg + 1:
            return GameResult(winner=0, server_points=s, returner_points=r,
                              aces=aces, double_faults=dfs)
        else:
            return GameResult(winner=1, server_points=s, returner_points=r,
                              aces=aces, double_faults=dfs)


def simulate_tiebreak(p0, p1, first_server: int, rng=None) -> GameResult:
    """
    Simulate a tiebreak game.
    First to 7 points, win by 2.

    Service pattern (1-2-2-2...): tennisim explicit state machine.
      - Point 1:  first_server serves
      - Points 2-3: other player serves (2 consecutive)
      - Points 4-5: first_server serves (2 consecutive)
      - ... alternates every 2 after the first point

    Aces/DFs tracked relative to p0 (player index 0).

    Args:
        p0: PlayerProfile for player 0
        p1: PlayerProfile for player 1
        first_server: index (0 or 1) of player serving first point
        rng: numpy Generator

    Returns:
        GameResult where winner is 0 or 1 (absolute player index)
    """
    import numpy as np
    if rng is None:
        rng = np.random.default_rng()

    pts = [0, 0]   # points for [p0, p1]
    aces_p0 = 0
    dfs_p0 = 0
    players = [p0, p1]

    # Explicit 1-2-2-2 state machine (tennisim pattern)
    server_idx = first_server     # current server (absolute index)
    points_served = 0             # points served by current server in current stint
    total_points = 0              # total points played so far

    while True:
        returner_idx = 1 - server_idx
        server   = players[server_idx]
        returner = players[returner_idx]

        probs = derive_serve_probs(server, returner)
        result = simulate_point(server, returner, probs=probs, rng=rng)

        # Track aces/DFs for p0
        if server_idx == 0:
            if result.is_ace:
                aces_p0 += 1
            if result.is_double_fault:
                dfs_p0 += 1

        # Assign point to absolute player
        if result.winner == 0:   # server wins
            pts[server_idx] += 1
        else:
            pts[returner_idx] += 1

        total_points += 1
        points_served += 1

        # Win condition: 7+ points, lead by 2
        if pts[0] >= 7 and pts[0] - pts[1] >= 2:
            return GameResult(
                winner=0,
                server_points=pts[first_server],
                returner_points=pts[1 - first_server],
                aces=aces_p0,
                double_faults=dfs_p0,
                is_tiebreak=True,
            )
        if pts[1] >= 7 and pts[1] - pts[0] >= 2:
            return GameResult(
                winner=1,
                server_points=pts[first_server],
                returner_points=pts[1 - first_server],
                aces=aces_p0,
                double_faults=dfs_p0,
                is_tiebreak=True,
            )

        # Service rotation: 1-2-2-2...
        # After the very first point: always swap
        if total_points == 1:
            server_idx = 1 - server_idx
            points_served = 0
        elif points_served == 2:
            # After every 2 subsequent points: swap
            server_idx = 1 - server_idx
            points_served = 0
