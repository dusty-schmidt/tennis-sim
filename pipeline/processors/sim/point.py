"""
Point-level simulation: probability derivation and single-point outcome.
"""
from dataclasses import dataclass, field
from typing import Optional

AVG_PTS_PER_SV_GAME = 6.5  # empirical ATP average


@dataclass
class PointResult:
    winner: int          # 0 = server wins, 1 = returner wins
    is_ace: bool = False
    is_double_fault: bool = False


def derive_serve_probs(server, returner) -> dict:
    """
    Derive per-point serving probabilities from PlayerProfile stats.

    Returns dict with keys:
      p_df          - P(double fault) per service point (on 2nd serve attempt)
      p_ace_1st     - P(ace | 1st serve in)
      p_1st_in      - P(1st serve in)
      p_win_1st     - P(server wins point | 1st serve in)
      p_win_2nd     - P(server wins point | 2nd serve in play)
    """
    p_1st_in = float(server.first_serve_pct)

    # Per-point rates scaled from per-game rates
    p_ace_raw = server.ace_per_game / AVG_PTS_PER_SV_GAME
    p_df_raw  = server.df_per_game  / AVG_PTS_PER_SV_GAME

    # Clamp to valid probability range
    p_1st_in = max(0.30, min(0.85, p_1st_in))
    p_ace_raw = max(0.0, min(0.20, p_ace_raw))
    p_df_raw  = max(0.0, min(0.15, p_df_raw))

    # Opponent-adjusted win probabilities (blend server strength vs returner strength)
    p_win_1st_raw = float(server.first_serve_won_pct)
    p_win_1st_adj = (p_win_1st_raw + (1.0 - float(returner.return_pts_won_pct))) / 2.0
    p_win_1st_adj = max(0.40, min(0.90, p_win_1st_adj))

    p_win_2nd_raw = float(server.second_serve_won_pct)
    p_win_2nd_adj = (p_win_2nd_raw + (1.0 - float(returner.return_pts_won_pct))) / 2.0
    p_win_2nd_adj = max(0.25, min(0.75, p_win_2nd_adj))

    # ace probability is conditional on 1st serve in
    # p_ace_1st = P(ace | 1st serve in) — ensure it doesn't exceed p_win_1st
    p_ace_1st = min(p_ace_raw / max(p_1st_in, 0.01), p_win_1st_adj * 0.30)
    p_ace_1st = max(0.0, p_ace_1st)

    return {
        'p_df':       p_df_raw,
        'p_ace_1st':  p_ace_1st,
        'p_1st_in':   p_1st_in,
        'p_win_1st':  p_win_1st_adj,
        'p_win_2nd':  p_win_2nd_adj,
    }


def simulate_point(server, returner, probs: dict = None, rng=None) -> PointResult:
    """
    Simulate a single service point.

    Args:
        server:   PlayerProfile of serving player
        returner: PlayerProfile of returning player
        probs:    Pre-computed dict from derive_serve_probs() (pass for speed)
        rng:      numpy Generator (default_rng); if None uses module-level fallback

    Returns:
        PointResult with winner (0=server, 1=returner), ace/df flags
    """
    import numpy as np

    if rng is None:
        rng = np.random.default_rng()

    if probs is None:
        probs = derive_serve_probs(server, returner)

    r = rng.random()

    p_1st_in  = probs['p_1st_in']
    p_win_1st = probs['p_win_1st']
    p_ace_1st = probs['p_ace_1st']
    p_win_2nd = probs['p_win_2nd']
    p_df      = probs['p_df']

    if r < p_1st_in:
        # First serve in
        r2 = rng.random()
        if r2 < p_ace_1st:
            return PointResult(winner=0, is_ace=True)
        elif r2 < p_win_1st:
            return PointResult(winner=0)
        else:
            return PointResult(winner=1)
    else:
        # First serve fault -> second serve
        r2 = rng.random()
        if r2 < p_df:
            return PointResult(winner=1, is_double_fault=True)
        elif r2 < p_df + p_win_2nd:
            return PointResult(winner=0)
        else:
            return PointResult(winner=1)
