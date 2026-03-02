"""
Elo-based calibration of player profiles — analytical edition (v2).

Replaces the empirical 6%-capped serve adjustment with:
  1. theory_game(p)            — closed-form game win probability
  2. prob_set_analytical()     — Markov-chain set win probability
  3. prob_match_analytical()   — full match win probability chain
  4. calibrate_profiles()      — binary-search calibration, no cap

The binary search finds the adjusted serve-point probability for player A
such that the analytical match win prob matches the Elo-implied win prob.
This correctly handles large Elo gaps (e.g. Alcaraz/Zverev ~72/28).
"""
import logging
from functools import lru_cache
from typing import Tuple

from .profiles import PlayerProfile
from .point import derive_serve_probs

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Analytical building blocks
# ─────────────────────────────────────────────────────────────────────────────

def theory_game(p: float) -> float:
    """
    Closed-form probability that the server wins a service game,
    given per-point serve win probability p.

    Derived from the standard tennis game formula (Barnett & Clarke):
      P(win 4-0) + P(win 4-1) + P(win 4-2) + P(win from deuce)
    """
    p4_0 = p ** 4
    p4_1 = 4.0 * p ** 4 * (1.0 - p)
    p4_2 = 10.0 * p ** 4 * (1.0 - p) ** 2
    # Deuce: reach 3-3 then win the advantage game
    # P(reach deuce) = C(6,3)*p^3*(1-p)^3
    # P(win from deuce) = p^2 / (1 - 2p(1-p))
    denom = 1.0 - 2.0 * p * (1.0 - p)
    denom = max(denom, 1e-12)  # guard against p=0.5 edge
    deuce = 20.0 * (p ** 3) * ((1.0 - p) ** 3) * (p ** 2 / denom)
    return p4_0 + p4_1 + p4_2 + deuce


def prob_tiebreak_analytical(p_a: float, p_b: float) -> float:
    """
    Probability that player A wins a tiebreak given:
      p_a = P(A wins point on A's serve)
      p_b = P(B wins point on B's serve)

    Uses the standard formula for a repeated-advantage game:
      p_win = p_A_wins_2pts / (p_A_wins_2pts + p_B_wins_2pts)
    where "2 pts" = win serve point + return point (or vice versa).

    In a tiebreak with equal serve opportunities (long tiebreak):
      avg point win prob for A = (p_a + (1-p_b)) / 2
      Then apply the deuce-style infinite series.
    """
    # A's prob winning a point in tiebreak (average of serving and returning)
    p_a_pt = (p_a + (1.0 - p_b)) / 2.0
    p_b_pt = 1.0 - p_a_pt
    # Infinite series for winning consecutive 2-point sequences
    p_a2 = p_a_pt ** 2
    p_b2 = p_b_pt ** 2
    denom = p_a2 + p_b2
    if denom < 1e-12:
        return 0.5
    return p_a2 / denom


def prob_set_analytical(p_a: float, p_b: float) -> float:
    """
    Probability that player A wins a set given:
      p_a = P(A wins a point on A's serve)
      p_b = P(B wins a point on B's serve)

    Uses a Markov-chain DP over game states (g_a, g_b) with server
    alternating each game (A serves first game of the set).

    States: 0..6 x 0..6, plus tiebreak at 6-6.
    """
    g_a_wins = theory_game(p_a)      # P(A wins a game when A serves)
    g_b_wins = theory_game(p_b)      # P(B wins a game when B serves)
    g_a_return = 1.0 - g_b_wins     # P(A wins a game when B serves)
    g_b_return = 1.0 - g_a_wins     # P(B wins a game when A serves)

    tb_prob = prob_tiebreak_analytical(p_a, p_b)

    # DP: state = (g_a, g_b, server_flag) where server_flag=True means A serves
    # Memoize with a dict
    memo = {}

    def dp(ga: int, gb: int, a_serves: bool) -> float:
        """Return P(A wins set from state (ga, gb) with a_serves indicator)."""
        # Terminal states
        if ga == 7:  # A won tiebreak
            return 1.0
        if gb == 7:  # B won tiebreak
            return 0.0
        if ga >= 6 and ga - gb >= 2:
            return 1.0
        if gb >= 6 and gb - ga >= 2:
            return 0.0

        key = (ga, gb, a_serves)
        if key in memo:
            return memo[key]

        # Tiebreak state
        if ga == 6 and gb == 6:
            result = tb_prob
            memo[key] = result
            return result

        # Play next game
        if a_serves:
            # A serves: A wins game with prob g_a_wins
            p_a_wins_game = g_a_wins
        else:
            # B serves: A wins game with prob g_a_return
            p_a_wins_game = g_a_return

        # After game, server alternates
        # If A wins game:
        result = (p_a_wins_game       * dp(ga + 1, gb, not a_serves) +
                  (1.0 - p_a_wins_game) * dp(ga, gb + 1, not a_serves))
        memo[key] = result
        return result

    return dp(0, 0, True)  # A serves first game


def prob_match_analytical(
    p_a: float,
    p_b: float,
    best_of: int = 3,
    sets_a: int = 0,
    sets_b: int = 0,
) -> float:
    """
    Probability that player A wins the match from a given sets_won state.

    Args:
        p_a:    P(A wins a point on A's serve)
        p_b:    P(B wins a point on B's serve)
        best_of: 3 or 5
        sets_a:  Sets already won by A
        sets_b:  Sets already won by B

    Returns:
        float: P(A wins match)
    """
    sets_to_win = (best_of + 1) // 2
    if sets_a >= sets_to_win:
        return 1.0
    if sets_b >= sets_to_win:
        return 0.0

    p_set_a = prob_set_analytical(p_a, p_b)  # P(A wins a set)
    p_set_b = 1.0 - p_set_a

    # Memoized DP over remaining sets needed
    memo = {}

    def dp(sa: int, sb: int) -> float:
        if sa >= sets_to_win:
            return 1.0
        if sb >= sets_to_win:
            return 0.0
        if (sa, sb) in memo:
            return memo[(sa, sb)]
        result = p_set_a * dp(sa + 1, sb) + p_set_b * dp(sa, sb + 1)
        memo[(sa, sb)] = result
        return result

    return dp(sets_a, sets_b)


# ─────────────────────────────────────────────────────────────────────────────
# Profile -> effective serve-point probability
# ─────────────────────────────────────────────────────────────────────────────

def effective_p_serve(profile: PlayerProfile, opponent: PlayerProfile) -> float:
    """
    Compute the effective per-point serve win probability for `profile`
    serving against `opponent`, using the same blending logic as
    derive_serve_probs() in point.py.

    p_eff = p_1st_in * p_win_1st + (1 - p_1st_in) * (1 - p_df) * p_win_2nd
    """
    probs = derive_serve_probs(profile, opponent)
    p_1st_in  = probs['p_1st_in']
    p_win_1st = probs['p_win_1st']
    p_win_2nd = probs['p_win_2nd']
    p_df      = probs['p_df']

    p_eff = (p_1st_in * p_win_1st +
             (1.0 - p_1st_in) * (1.0 - p_df) * p_win_2nd)
    return float(p_eff)


# ─────────────────────────────────────────────────────────────────────────────
# Elo utilities
# ─────────────────────────────────────────────────────────────────────────────

def elo_match_win_prob(elo_a: float, elo_b: float) -> float:
    """Standard Elo formula: P(A beats B)."""
    return 1.0 / (1.0 + 10.0 ** ((elo_b - elo_a) / 400.0))


# ─────────────────────────────────────────────────────────────────────────────
# Calibration via binary search
# ─────────────────────────────────────────────────────────────────────────────

def _analytical_win_prob_from_profiles(
    p0: PlayerProfile,
    p1: PlayerProfile,
    best_of: int = 3,
) -> float:
    """
    Compute the analytical match win probability for p0 vs p1
    from their current PlayerProfile stats.
    """
    p_a = effective_p_serve(p0, p1)
    p_b = effective_p_serve(p1, p0)
    return prob_match_analytical(p_a, p_b, best_of=best_of)


def calibrate_profiles(
    p0: PlayerProfile,
    p1: PlayerProfile,
    blend: float = 1.0,
    best_of: int = 3,
    tolerance: float = 0.005,
) -> Tuple[PlayerProfile, PlayerProfile]:
    """
    Adjust player profiles so the analytical match win probability
    matches the Elo-implied win probability.

    Strategy: binary-search for adjusted serve-point probability p_a_adj
    such that prob_match_analytical(p_a_adj, p_b) = elo_win_prob.
    Then back-calculate the required scaling on first/second serve won %.

    No 6% cap — full adjustment is applied via analytical root-finding.

    Args:
        p0:        PlayerProfile for player 0
        p1:        PlayerProfile for player 1
        blend:     Fraction of the gap to close (0.3 = close 30%)
                   Use 1.0 to fully align to Elo.
        best_of:   3 or 5
        tolerance: Binary search convergence tolerance

    Returns:
        (adjusted_p0, adjusted_p1) — copies, originals not mutated
    """
    elo_prob    = elo_match_win_prob(p0.elo, p1.elo)
    stats_prob  = _analytical_win_prob_from_profiles(p0, p1, best_of)
    gap         = elo_prob - stats_prob

    logger.debug(
        'Calibration: elo_prob=%.3f stats_prob=%.3f gap=%.3f (%s vs %s)',
        elo_prob, stats_prob, gap, p0.name, p1.name
    )

    # If within tolerance, no adjustment needed
    if abs(gap) <= tolerance:
        return p0.copy(), p1.copy()

    # Target: close `blend` fraction of the gap
    target_prob = stats_prob + blend * gap
    target_prob = max(0.05, min(0.95, target_prob))

    logger.debug(
        'Calibration target: stats_prob=%.3f -> target=%.3f (blend=%.1f)',
        stats_prob, target_prob, blend
    )

    # Current effective serve probs
    p_a_current = effective_p_serve(p0, p1)
    p_b_current = effective_p_serve(p1, p0)

    # --- Binary search for p_a_adj ---
    # We want: prob_match_analytical(p_a_adj, p_b_current) = target_prob
    # p_a_adj is bounded in [0.35, 0.85] (realistic serve win range)

    def f(p_a_adj: float) -> float:
        return prob_match_analytical(p_a_adj, p_b_current, best_of=best_of) - target_prob

    lo, hi = 0.35, 0.85
    # Check if root is in range
    f_lo, f_hi = f(lo), f(hi)
    if f_lo * f_hi > 0:
        # Root not in range — use boundary closest to target
        logger.warning(
            'Calibration: binary search out of range for %s vs %s '
            '(target=%.3f, f_lo=%.3f, f_hi=%.3f); using boundary',
            p0.name, p1.name, target_prob, f_lo, f_hi
        )
        p_a_adj = lo if abs(f_lo) < abs(f_hi) else hi
    else:
        # Bisection method
        for _ in range(60):  # 60 iterations gives < 1e-12 precision
            mid = (lo + hi) / 2.0
            if abs(hi - lo) < tolerance:
                break
            if f(mid) * f_lo < 0:
                hi = mid
            else:
                lo = mid
                f_lo = f(mid)
        p_a_adj = (lo + hi) / 2.0

    # Translate p_a_adj back to profile serve stats using analytical inversion
    # of the Barnett-Clarke blend formula:
    #   p_eff = p_1st_in*(x+R)/2 + (1-p_1st_in)*(1-p_df)*(k*x+R)/2
    # where x = first_serve_won_pct, k = 2nd/1st ratio, R = 1-returner.return_pts_won
    # Solving for x:
    #   A = p_1st_in + (1-p_1st_in)*(1-p_df)*k
    #   B = p_1st_in + (1-p_1st_in)*(1-p_df)
    #   x = (2*p_a_adj - R*B) / A
    import numpy as np

    probs0     = derive_serve_probs(p0, p1)
    p_1st_in   = probs0['p_1st_in']
    p_df       = probs0['p_df']
    R          = 1.0 - float(p1.return_pts_won_pct)  # opponent return complement

    orig_1st = float(p0.first_serve_won_pct)
    orig_2nd = float(p0.second_serve_won_pct)
    k = orig_2nd / orig_1st if orig_1st > 1e-6 else 1.0  # preserve 2nd/1st ratio

    A = p_1st_in + (1.0 - p_1st_in) * (1.0 - p_df) * k
    B = p_1st_in + (1.0 - p_1st_in) * (1.0 - p_df)

    if A > 1e-9:
        x_new = (2.0 * p_a_adj - R * B) / A
    else:
        x_new = orig_1st  # fallback: no adjustment

    new_1st = float(np.clip(x_new,           0.35, 0.95))
    new_2nd = float(np.clip(x_new * k,       0.20, 0.80))

    adj_p0 = p0.copy()
    adj_p1 = p1.copy()
    adj_p0.first_serve_won_pct  = new_1st
    adj_p0.second_serve_won_pct = new_2nd

    # Verify final analytical prob
    final_prob = _analytical_win_prob_from_profiles(adj_p0, adj_p1, best_of)
    logger.info(
        'Calibrated: %s vs %s | elo=%.3f stats=%.3f target=%.3f final=%.3f '
        '(p_a: %.4f -> %.4f, 1st: %.4f->%.4f 2nd: %.4f->%.4f)',
        p0.name, p1.name, elo_prob, stats_prob, target_prob, final_prob,
        p_a_current, p_a_adj,
        orig_1st, new_1st, orig_2nd, new_2nd,
    )

    return adj_p0, adj_p1


def prob_set_from_state(
    p_a: float,
    p_b: float,
    ga: int,
    gb: int,
    a_serves: bool = True,
) -> float:
    """
    Probability that player A wins the set from mid-set state (ga, gb)
    with a_serves indicating who serves the next game.

    Args:
        p_a:      P(A wins a point on A's serve)
        p_b:      P(B wins a point on B's serve)
        ga:       Games already won by A in this set
        gb:       Games already won by B in this set
        a_serves: True if A serves the next game

    Returns:
        float: P(A wins set from this state)
    """
    g_a_wins    = theory_game(p_a)
    g_b_wins    = theory_game(p_b)
    g_a_return  = 1.0 - g_b_wins
    tb_prob     = prob_tiebreak_analytical(p_a, p_b)

    memo = {}

    def dp(gga: int, ggb: int, a_sv: bool) -> float:
        if gga == 7:
            return 1.0
        if ggb == 7:
            return 0.0
        if gga >= 6 and gga - ggb >= 2:
            return 1.0
        if ggb >= 6 and ggb - gga >= 2:
            return 0.0
        key = (gga, ggb, a_sv)
        if key in memo:
            return memo[key]
        if gga == 6 and ggb == 6:
            memo[key] = tb_prob
            return tb_prob
        p_a_game = g_a_wins if a_sv else g_a_return
        result = (p_a_game * dp(gga + 1, ggb, not a_sv) +
                  (1.0 - p_a_game) * dp(gga, ggb + 1, not a_sv))
        memo[key] = result
        return result

    return dp(ga, gb, a_serves)


def prob_match_from_state(
    p_a: float,
    p_b: float,
    best_of: int = 3,
    sets_a: int = 0,
    sets_b: int = 0,
    ga: int = 0,
    gb: int = 0,
    a_serves_set: bool = True,
) -> float:
    """
    Full match win probability for A from mid-match state:
    sets_a/sets_b sets won, current set at ga:gb games.

    Args:
        p_a, p_b:    Per-point serve win probs
        best_of:     3 or 5
        sets_a/b:    Sets already completed
        ga/gb:       Games in current set
        a_serves_set: Whether A serves the next game in current set

    Returns:
        float: P(A wins match)
    """
    sets_to_win = (best_of + 1) // 2
    if sets_a >= sets_to_win:
        return 1.0
    if sets_b >= sets_to_win:
        return 0.0

    p_set_a = prob_set_analytical(p_a, p_b)  # P(A wins a fresh set)
    p_set_b = 1.0 - p_set_a

    # P(A wins current set from (ga, gb))
    p_curr_set_a = prob_set_from_state(p_a, p_b, ga, gb, a_serves_set)
    p_curr_set_b = 1.0 - p_curr_set_a

    # Memoized DP for remaining sets (after current set)
    memo = {}
    def dp_match(sa: int, sb: int) -> float:
        if sa >= sets_to_win:
            return 1.0
        if sb >= sets_to_win:
            return 0.0
        if (sa, sb) in memo:
            return memo[(sa, sb)]
        result = p_set_a * dp_match(sa + 1, sb) + p_set_b * dp_match(sa, sb + 1)
        memo[(sa, sb)] = result
        return result

    # Combine: A wins current set + remaining, or loses current set + remaining
    return (p_curr_set_a * dp_match(sets_a + 1, sets_b) +
            p_curr_set_b * dp_match(sets_a, sets_b + 1))
