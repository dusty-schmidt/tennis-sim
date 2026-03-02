"""
Set and match-level simulation.

Upgrades (v2):
  - wp_timeline: optional per-game Win Probability tracking for player A
  - track_wp param (default False) enables it when needed
  - WP computed analytically via prob_match_from_state() after each game

Upgrades (v3 — DK scoring fix):
  - Track games_won / games_lost per player (ALL games, not just service)
  - Track breaks per player (return games won = opponent's service game won by you)
  - MatchResult carries games_won, games_lost, breaks fields
  - no_double_fault computed at match level
  - Removed rt_games_won/rt_games_lost (superseded by breaks + games_won/lost)
"""
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from .game import simulate_game, simulate_tiebreak


@dataclass
class SetResult:
    games: Tuple[int, int]        # (p0_games, p1_games)
    winner: int                   # absolute player index 0 or 1
    went_to_tiebreak: bool
    aces: List[int]               # [p0_aces, p1_aces]
    double_faults: List[int]      # [p0_dfs, p1_dfs]
    sv_games_won: List[int]       # service games won while serving [p0, p1]
    sv_games_lost: List[int]      # service games lost (broken) while serving [p0, p1]
    games_won: List[int]          # total games won (serve + return) [p0, p1]
    games_lost: List[int]         # total games lost [p0, p1]
    breaks: List[int]             # return games won (breaks) [p0, p1]


@dataclass
class MatchResult:
    sets: List[SetResult]
    winner: int
    sets_won: List[int]           # [p0_sets, p1_sets]
    total_aces: List[int]         # [p0_aces, p1_aces]
    total_dfs: List[int]          # [p0_dfs, p1_dfs]
    sv_games_won: List[int]       # service games won [p0, p1]  (kept for compat)
    sv_games_lost: List[int]      # service games lost [p0, p1] (kept for compat)
    rt_games_won: List[int]       # return games won [p0, p1]   (kept for compat)
    rt_games_lost: List[int]      # return games lost [p0, p1]  (kept for compat)
    games_won: List[int]          # ALL games won [p0, p1]
    games_lost: List[int]         # ALL games lost [p0, p1]
    breaks: List[int]             # return games won (breaks) [p0, p1]
    no_double_fault: List[int]    # 1 if player had 0 DFs in entire match [p0, p1]
    straight_sets: bool
    clean_sets: List[int]         # 6-0 sets won per player
    wp_timeline: Optional[List[float]] = None  # per-game WP for player 0


def _is_clean_set(games: Tuple[int, int], winner: int) -> bool:
    return (games[0] == 6 and games[1] == 0) if winner == 0 else (games[1] == 6 and games[0] == 0)


def simulate_set(
    p0, p1,
    first_server: int,
    is_final_set: bool = False,
    best_of: int = 3,
    rng=None,
    wp_list: Optional[List[float]] = None,
    wp_context: Optional[Tuple] = None,
) -> Tuple[SetResult, int]:
    """
    Simulate one set. Returns (SetResult, next_server_idx).
    - First to 6 games, win by 2
    - Standard tiebreak at 6-6 (except final set of best-of-5: match tiebreak at 12-12)
    - Server alternates each game
    """
    import numpy as np
    if rng is None:
        rng = np.random.default_rng()

    players = [p0, p1]
    scores = [0, 0]
    aces = [0, 0]
    dfs = [0, 0]
    sv_won   = [0, 0]   # won when serving
    sv_lost  = [0, 0]   # lost (broken) when serving
    gm_won   = [0, 0]   # all games won
    gm_lost  = [0, 0]   # all games lost
    brks     = [0, 0]   # return games won (breaks)
    current_server = first_server
    went_to_tiebreak = False

    # Unpack WP context if provided
    if wp_list is not None and wp_context is not None:
        p_a_eff, p_b_eff, sets_a, sets_b = wp_context
        try:
            from .calibration import prob_match_from_state
            _wp_enabled = True
        except ImportError:
            _wp_enabled = False
    else:
        _wp_enabled = False

    def _record_wp(ga: int, gb: int, a_serves_next: bool):
        if not _wp_enabled:
            return
        try:
            wp = prob_match_from_state(
                p_a_eff, p_b_eff,
                best_of=best_of,
                sets_a=sets_a, sets_b=sets_b,
                ga=ga, gb=gb,
                a_serves_set=a_serves_next,
            )
            wp_list.append(float(wp))
        except Exception:
            pass

    while True:
        g0, g1 = scores[0], scores[1]

        need_std_tb   = (g0 == 6 and g1 == 6) and not (is_final_set and best_of == 5)
        need_match_tb = (g0 == 12 and g1 == 12) and is_final_set and best_of == 5

        if need_std_tb or need_match_tb:
            went_to_tiebreak = True
            tb = simulate_tiebreak(p0, p1, first_server=current_server, rng=rng)
            tb_winner = tb.winner

            aces[0] += tb.aces
            dfs[0]  += tb.double_faults

            # Tiebreak: tb_winner held serve (effectively)
            sv_won[tb_winner]      += 1
            sv_lost[1 - tb_winner] += 1
            scores[tb_winner]      += 1

            # games_won/lost and breaks for tiebreak
            tb_server = current_server
            gm_won[tb_winner]      += 1
            gm_lost[1 - tb_winner] += 1
            if tb_winner != tb_server:  # returner won = break
                brks[tb_winner] += 1

            next_server = 1 - current_server
            return SetResult(
                games=(scores[0], scores[1]),
                winner=tb_winner,
                went_to_tiebreak=True,
                aces=aces[:],
                double_faults=dfs[:],
                sv_games_won=sv_won[:],
                sv_games_lost=sv_lost[:],
                games_won=gm_won[:],
                games_lost=gm_lost[:],
                breaks=brks[:],
            ), next_server

        # Normal set win condition
        if g0 >= 6 and g0 - g1 >= 2:
            return SetResult(
                games=(scores[0], scores[1]),
                winner=0,
                went_to_tiebreak=went_to_tiebreak,
                aces=aces[:],
                double_faults=dfs[:],
                sv_games_won=sv_won[:],
                sv_games_lost=sv_lost[:],
                games_won=gm_won[:],
                games_lost=gm_lost[:],
                breaks=brks[:],
            ), current_server

        if g1 >= 6 and g1 - g0 >= 2:
            return SetResult(
                games=(scores[0], scores[1]),
                winner=1,
                went_to_tiebreak=went_to_tiebreak,
                aces=aces[:],
                double_faults=dfs[:],
                sv_games_won=sv_won[:],
                sv_games_lost=sv_lost[:],
                games_won=gm_won[:],
                games_lost=gm_lost[:],
                breaks=brks[:],
            ), current_server

        # Play a game
        server   = players[current_server]
        returner = players[1 - current_server]
        game = simulate_game(server, returner, rng=rng)

        # Aces/DFs accrue to server
        aces[current_server] += game.aces
        dfs[current_server]  += game.double_faults

        # Determine absolute winner
        if game.winner == 0:   # server won
            absolute_winner = current_server
            sv_won[current_server] += 1
        else:                  # returner won = BREAK
            absolute_winner = 1 - current_server
            sv_lost[current_server] += 1
            brks[absolute_winner] += 1   # break credited to winner

        # All-games tracking
        gm_won[absolute_winner]        += 1
        gm_lost[1 - absolute_winner]   += 1

        scores[absolute_winner] += 1
        current_server = 1 - current_server

        if _wp_enabled:
            _record_wp(scores[0], scores[1], current_server == 0)


def simulate_match(
    p0, p1,
    best_of: int = 3,
    rng=None,
    track_wp: bool = False,
) -> MatchResult:
    """
    Simulate a full match. p0 serves first.
    """
    import numpy as np
    if rng is None:
        rng = np.random.default_rng()

    sets_to_win  = (best_of + 1) // 2
    sets_won     = [0, 0]
    total_aces   = [0, 0]
    total_dfs    = [0, 0]
    sv_won       = [0, 0]
    sv_lost      = [0, 0]
    tot_gm_won   = [0, 0]
    tot_gm_lost  = [0, 0]
    tot_brks     = [0, 0]
    set_results  = []
    clean_sets   = [0, 0]
    current_server = 0
    wp_timeline: Optional[List[float]] = None

    if track_wp:
        try:
            from .calibration import effective_p_serve, prob_match_from_state, prob_match_analytical
            p_a_eff = effective_p_serve(p0, p1)
            p_b_eff = effective_p_serve(p1, p0)
            wp_timeline = [float(prob_match_analytical(p_a_eff, p_b_eff, best_of=best_of))]
            _track_wp = True
        except Exception:
            _track_wp = False
    else:
        _track_wp = False
        p_a_eff = p_b_eff = None

    while sets_won[0] < sets_to_win and sets_won[1] < sets_to_win:
        set_idx  = len(set_results)
        is_final = (set_idx == best_of - 1)

        wp_context = (p_a_eff, p_b_eff, sets_won[0], sets_won[1]) if _track_wp else None
        wp_list    = wp_timeline if _track_wp else None

        set_result, next_server = simulate_set(
            p0, p1,
            first_server=current_server,
            is_final_set=is_final,
            best_of=best_of,
            rng=rng,
            wp_list=wp_list,
            wp_context=wp_context,
        )

        set_results.append(set_result)
        sets_won[set_result.winner] += 1

        total_aces[0] += set_result.aces[0]
        total_aces[1] += set_result.aces[1]
        total_dfs[0]  += set_result.double_faults[0]
        total_dfs[1]  += set_result.double_faults[1]
        sv_won[0]     += set_result.sv_games_won[0]
        sv_won[1]     += set_result.sv_games_won[1]
        sv_lost[0]    += set_result.sv_games_lost[0]
        sv_lost[1]    += set_result.sv_games_lost[1]
        tot_gm_won[0]  += set_result.games_won[0]
        tot_gm_won[1]  += set_result.games_won[1]
        tot_gm_lost[0] += set_result.games_lost[0]
        tot_gm_lost[1] += set_result.games_lost[1]
        tot_brks[0]    += set_result.breaks[0]
        tot_brks[1]    += set_result.breaks[1]

        if _is_clean_set(set_result.games, set_result.winner):
            clean_sets[set_result.winner] += 1

        current_server = next_server

    match_winner = 0 if sets_won[0] > sets_won[1] else 1
    straight     = (sets_won[1 - match_winner] == 0)

    # Legacy compat fields
    rt_won  = [sv_lost[1], sv_lost[0]]
    rt_lost = [sv_won[1],  sv_won[0]]

    # no_double_fault: 1 if player had 0 DFs in entire match
    no_df = [1 if total_dfs[i] == 0 else 0 for i in range(2)]

    return MatchResult(
        sets=set_results,
        winner=match_winner,
        sets_won=sets_won,
        total_aces=total_aces,
        total_dfs=total_dfs,
        sv_games_won=sv_won,
        sv_games_lost=sv_lost,
        rt_games_won=rt_won,
        rt_games_lost=rt_lost,
        games_won=tot_gm_won,
        games_lost=tot_gm_lost,
        breaks=tot_brks,
        no_double_fault=no_df,
        straight_sets=straight,
        clean_sets=clean_sets,
        wp_timeline=wp_timeline,
    )
