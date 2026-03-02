"""
Aggregates per-player, per-surface statistics from ATP match data.
Weights recent matches more heavily using exponential decay (half-life=52 weeks).

Public API:
  build_surface_stats(atp_df, min_matches=10, recency_weight=True) -> dict
  get_player_stats(player, surface, stats_dict) -> dict
  save_surface_stats(stats_dict, path=None) -> None
  load_surface_stats(path=None) -> dict
"""
import sys
import json
import logging
import math
from pathlib import Path
from collections import defaultdict
from typing import Optional

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.settings import PROCESSED_DIR, MIN_MATCHES

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_STATS_PATH = PROCESSED_DIR / 'player_surface_stats.json'

# Surface normalization map
SURFACE_NORM = {
    'hard': 'hard',
    'clay': 'clay',
    'grass': 'grass',
    'carpet': 'indoor',
    'indoor': 'indoor',
}

# Tour average fallbacks (reasonable ATP baselines)
TOUR_AVERAGES = {
    '1stServe_pct': 0.615,
    '1stServeWon_pct': 0.735,
    '2ndServeWon_pct': 0.530,
    'ace_per_game': 0.65,
    'df_per_game': 0.35,
    'bp_saved_pct': 0.625,
    'return_pts_won_pct': 0.385,
    'sv_games_per_match': 10.0,
    'matches_played': 0,
}


def _norm_surface(surface: str) -> Optional[str]:
    """Normalize surface string to lowercase canonical form."""
    if not isinstance(surface, str):
        return None
    return SURFACE_NORM.get(surface.lower().strip())


def _weighted_mean(values: list, weights: list) -> Optional[float]:
    """Compute weighted mean, skipping NaN values. Returns None if no valid data."""
    valid = [(v, w) for v, w in zip(values, weights)
             if v is not None and not math.isnan(v) and w > 0]
    if not valid:
        return None
    total_w = sum(w for _, w in valid)
    if total_w == 0:
        return None
    return sum(v * w for v, w in valid) / total_w


def _safe_div(num, den):
    """Safe division returning None on zero/NaN denominator."""
    if den is None or num is None:
        return None
    try:
        if math.isnan(float(den)) or float(den) == 0:
            return None
        if math.isnan(float(num)):
            return None
        return float(num) / float(den)
    except (TypeError, ValueError):
        return None


def build_surface_stats(
    atp_df: pd.DataFrame,
    min_matches: int = 10,
    recency_weight: bool = True,
) -> dict:
    """
    Build per-player per-surface stats dict from ATP match DataFrame.

    Returns:
        {player_name: {'hard': {stat: value}, 'clay': {...}, 'overall': {...}}}
    """
    if atp_df.empty:
        logger.warning('Empty DataFrame passed to build_surface_stats')
        return {}

    df = atp_df.copy()

    # Parse tourney_date (YYYYMMDD int) -> datetime
    df['match_date'] = pd.to_datetime(
        df['tourney_date'].astype(str), format='%Y%m%d', errors='coerce'
    )
    reference_date = df['match_date'].max()
    logger.info('Reference date for decay: %s', reference_date)

    # Compute recency weight per row
    if recency_weight:
        weeks_ago = (reference_date - df['match_date']).dt.days / 7.0
        df['weight'] = np.power(2.0, -weeks_ago / 52.0)
    else:
        df['weight'] = 1.0

    # Normalize surface
    df['surface_norm'] = df['surface'].apply(_norm_surface)

    # Numeric cast for all stat columns
    stat_cols = [
        'w_ace', 'w_df', 'w_svpt', 'w_1stIn', 'w_1stWon', 'w_2ndWon',
        'w_SvGms', 'w_bpSaved', 'w_bpFaced',
        'l_ace', 'l_df', 'l_svpt', 'l_1stIn', 'l_1stWon', 'l_2ndWon',
        'l_SvGms', 'l_bpSaved', 'l_bpFaced',
    ]
    for col in stat_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # ── Per-match stat computation ──────────────────────────────────────────────
    # We'll accumulate per (player, surface) lists of (stat_value, weight)
    # Structure: {player: {surface: {stat: [(value, weight), ...]}}}
    accum = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    def _acc(player, surface, stat, value, weight):
        if surface and value is not None and not math.isnan(value):
            accum[player][surface][stat].append((value, weight))
            accum[player]['overall'][stat].append((value, weight))

    for _, row in df.iterrows():
        surface = row['surface_norm']
        if not surface:
            continue

        w = float(row['weight']) if not math.isnan(float(row['weight'])) else 1.0

        winner = row['winner_name']
        loser = row['loser_name']

        # ── WINNER (serving stats) ──────────────────────────────────────────────
        if pd.notna(winner):
            w_svpt  = row.get('w_svpt')
            w_1stIn = row.get('w_1stIn')
            w_1stWon= row.get('w_1stWon')
            w_2ndWon= row.get('w_2ndWon')
            w_SvGms = row.get('w_SvGms')
            w_ace   = row.get('w_ace')
            w_df    = row.get('w_df')
            w_bpS   = row.get('w_bpSaved')
            w_bpF   = row.get('w_bpFaced')

            w_2nd_att = _safe_div(
                (w_svpt - w_1stIn) if (w_svpt is not None and w_1stIn is not None and
                    not math.isnan(w_svpt) and not math.isnan(w_1stIn)) else None,
                1
            )
            if w_svpt and not math.isnan(w_svpt) and w_1stIn and not math.isnan(w_1stIn):
                w_2nd_att = w_svpt - w_1stIn
            else:
                w_2nd_att = None

            _acc(winner, surface, '1stServe_pct',    _safe_div(w_1stIn, w_svpt),    w)
            _acc(winner, surface, '1stServeWon_pct', _safe_div(w_1stWon, w_1stIn),  w)
            _acc(winner, surface, '2ndServeWon_pct', _safe_div(w_2ndWon, w_2nd_att), w)
            _acc(winner, surface, 'ace_per_game',    _safe_div(w_ace, w_SvGms),      w)
            _acc(winner, surface, 'df_per_game',     _safe_div(w_df, w_SvGms),       w)
            _acc(winner, surface, 'sv_games_per_match', float(w_SvGms) if w_SvGms and not math.isnan(float(w_SvGms)) else None, w)

            # BP saved: only when faced >= threshold
            if (w_bpF is not None and not math.isnan(w_bpF) and
                    w_bpF >= MIN_MATCHES['bp_saved']):
                _acc(winner, surface, 'bp_saved_pct', _safe_div(w_bpS, w_bpF), w)

            # WINNER as returner: use LOSER's serve stats
            l_svpt  = row.get('l_svpt')
            l_1stWon= row.get('l_1stWon')
            l_2ndWon= row.get('l_2ndWon')
            # return pts won = points loser did NOT win on serve
            if (l_svpt is not None and l_1stWon is not None and l_2ndWon is not None
                    and not math.isnan(l_svpt) and not math.isnan(l_1stWon)
                    and not math.isnan(l_2ndWon) and l_svpt > 0):
                ret_won = (l_svpt - l_1stWon - l_2ndWon) / l_svpt
                _acc(winner, surface, 'return_pts_won_pct', ret_won, w)

        # ── LOSER (serving stats) ───────────────────────────────────────────────
        if pd.notna(loser):
            l_svpt  = row.get('l_svpt')
            l_1stIn = row.get('l_1stIn')
            l_1stWon= row.get('l_1stWon')
            l_2ndWon= row.get('l_2ndWon')
            l_SvGms = row.get('l_SvGms')
            l_ace   = row.get('l_ace')
            l_df    = row.get('l_df')
            l_bpS   = row.get('l_bpSaved')
            l_bpF   = row.get('l_bpFaced')

            if (l_svpt is not None and l_1stIn is not None and
                    not math.isnan(l_svpt) and not math.isnan(l_1stIn)):
                l_2nd_att = l_svpt - l_1stIn
            else:
                l_2nd_att = None

            _acc(loser, surface, '1stServe_pct',    _safe_div(l_1stIn, l_svpt),    w)
            _acc(loser, surface, '1stServeWon_pct', _safe_div(l_1stWon, l_1stIn),  w)
            _acc(loser, surface, '2ndServeWon_pct', _safe_div(l_2ndWon, l_2nd_att), w)
            _acc(loser, surface, 'ace_per_game',    _safe_div(l_ace, l_SvGms),      w)
            _acc(loser, surface, 'df_per_game',     _safe_div(l_df, l_SvGms),       w)
            _acc(loser, surface, 'sv_games_per_match', float(l_SvGms) if l_SvGms and not math.isnan(float(l_SvGms)) else None, w)

            if (l_bpF is not None and not math.isnan(l_bpF) and
                    l_bpF >= MIN_MATCHES['bp_saved']):
                _acc(loser, surface, 'bp_saved_pct', _safe_div(l_bpS, l_bpF), w)

            # LOSER as returner: use WINNER's serve stats
            w_svpt  = row.get('w_svpt')
            w_1stWon= row.get('w_1stWon')
            w_2ndWon= row.get('w_2ndWon')
            if (w_svpt is not None and w_1stWon is not None and w_2ndWon is not None
                    and not math.isnan(w_svpt) and not math.isnan(w_1stWon)
                    and not math.isnan(w_2ndWon) and w_svpt > 0):
                ret_won = (w_svpt - w_1stWon - w_2ndWon) / w_svpt
                _acc(loser, surface, 'return_pts_won_pct', ret_won, w)

    # ── Aggregate into stats dict ───────────────────────────────────────────────
    stats = {}
    STAT_KEYS = [
        '1stServe_pct', '1stServeWon_pct', '2ndServeWon_pct',
        'ace_per_game', 'df_per_game', 'bp_saved_pct',
        'return_pts_won_pct', 'sv_games_per_match', 'matches_played',
    ]

    for player, surfaces in accum.items():
        stats[player] = {}
        for surf, stat_data in surfaces.items():
            # Count matches = number of '1stServe_pct' observations (each match adds one)
            n_matches = len(stat_data.get('1stServe_pct', []))
            if surf != 'overall' and n_matches < min_matches:
                continue  # skip surfaces with insufficient data

            surface_stats = {}
            for stat in STAT_KEYS:
                if stat == 'matches_played':
                    surface_stats[stat] = n_matches
                    continue
                observations = stat_data.get(stat, [])
                if not observations:
                    continue
                vals = [v for v, _ in observations]
                wts  = [wt for _, wt in observations]
                result = _weighted_mean(vals, wts)
                if result is not None:
                    surface_stats[stat] = round(result, 6)

            if surface_stats:
                stats[player][surf] = surface_stats

    logger.info('Surface stats built for %d players', len(stats))
    return stats


def get_player_stats(player: str, surface: str, stats_dict: dict) -> dict:
    """
    Get stats for player on given surface.
    Fallback chain: surface-specific -> overall -> TOUR_AVERAGES.
    """
    surface = surface.lower().strip() if surface else 'hard'
    player_data = stats_dict.get(player, {})

    if surface in player_data:
        return {**TOUR_AVERAGES, **player_data[surface]}

    if 'overall' in player_data:
        return {**TOUR_AVERAGES, **player_data['overall']}

    return dict(TOUR_AVERAGES)


def save_surface_stats(stats_dict: dict, path: str = None) -> None:
    """Save stats dict to JSON."""
    out_path = Path(path) if path else DEFAULT_STATS_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(stats_dict, f, indent=2)
    logger.info('Saved surface stats to %s (%d players)', out_path, len(stats_dict))


def load_surface_stats(path: str = None) -> dict:
    """Load stats dict from JSON."""
    in_path = Path(path) if path else DEFAULT_STATS_PATH
    if not in_path.exists():
        logger.warning('Surface stats file not found: %s', in_path)
        return {}
    with open(in_path) as f:
        data = json.load(f)
    logger.info('Loaded surface stats from %s (%d players)', in_path, len(data))
    return data


if __name__ == '__main__':
    import os
    from pathlib import Path as _Path

    # Find atp_2024.csv
    proj_root = _Path(__file__).parent.parent.parent
    atp_path = proj_root / 'data' / 'raw' / 'atp' / 'atp_2024.csv'

    if not atp_path.exists():
        print(f'atp_2024.csv not found at {atp_path}')
        sys.exit(1)

    print(f'Loading {atp_path}...')
    df = pd.read_csv(atp_path, low_memory=False)
    print(f'  {len(df)} matches loaded')

    stats = build_surface_stats(df, min_matches=5)
    print(f'  Stats built for {len(stats)} players')

    # Top 10 players on hard by ace_per_game
    hard_aces = []
    for player, surfs in stats.items():
        hard = surfs.get('hard', {})
        if 'ace_per_game' in hard and hard.get('matches_played', 0) >= 5:
            hard_aces.append((player, hard['ace_per_game'], hard['matches_played']))

    hard_aces.sort(key=lambda x: x[1], reverse=True)
    print(f'\nTop 10 players on Hard by ace_per_game:')
    print(f'{"Player":<30} {"Ace/Gm":>8} {"Matches":>8}')
    print('-' * 50)
    for player, ace_pg, matches in hard_aces[:10]:
        print(f'{player:<30} {ace_pg:>8.3f} {matches:>8}')

    save_surface_stats(stats)
    print('\nStats saved.')
