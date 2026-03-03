"""
Slate projection engine.
Loads player profiles, runs Monte Carlo simulations per matchup,
and returns a DraftKings projection DataFrame.
"""
import logging
import sys
from pathlib import Path
from typing import List, Tuple, Optional

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.settings import RAW_DIR, DK_SCORING_3SET, DK_SCORING_5SET
from pipeline.processors.surface_stats import load_surface_stats
from pipeline.processors.sim import (
    PlayerProfile, ProfileLoader, MonteCarloEngine, SimResult
)

logger = logging.getLogger(__name__)

_ELO_CSV = RAW_DIR / 'tennis_abstract' / 'latest.csv'


def _load_profile_loader(surface: str) -> ProfileLoader:
    """Instantiate ProfileLoader with surface_stats JSON and Elo CSV."""
    stats_dict = load_surface_stats()

    elo_df = None
    if _ELO_CSV.exists():
        try:
            elo_df = pd.read_csv(_ELO_CSV)
            logger.info('Loaded Elo CSV: %d players from %s', len(elo_df), _ELO_CSV)
        except Exception as exc:
            logger.warning('Failed to load Elo CSV %s: %s', _ELO_CSV, exc)
    else:
        logger.warning('Elo CSV not found: %s', _ELO_CSV)

    return ProfileLoader(stats_dict=stats_dict, elo_df=elo_df)


def _sim_result_to_dict(
    result: SimResult,
    salary: Optional[int],
    surface: str,
    best_of: int,
) -> dict:
    """Convert SimResult to projection dict for DataFrame and DB storage."""
    value = None
    if salary and salary > 0:
        value = round(result.mean / (salary / 1000.0), 4)

    return {
        'player_name':      result.player_name,
        'salary':           salary,
        'proj_mean':        round(result.mean, 3),
        'proj_floor':       round(result.floor, 3),
        'proj_ceil':        round(result.ceil, 3),
        'proj_std':         round(result.std, 3),
        'p10':              round(result.floor, 3),
        'p25':              round(result.p25, 3),
        'p75':              round(result.p75, 3),
        'p85':              round(np.percentile(result.scores, 85), 3) if hasattr(result, 'scores') else 0.0,
        'p95':              round(np.percentile(result.scores, 95), 3) if hasattr(result, 'scores') else 0.0,
        'p99':              round(np.percentile(result.scores, 99), 3) if hasattr(result, 'scores') else 0.0,
        'p90':              round(result.ceil, 3),
        'p_win':            round(result.p_win, 4),
        'p_straight_sets':  round(result.p_straight_sets, 4),
        'p_clean_set':      round(result.p_clean_set, 4),
        'value':            value,
        'surface':          surface,
        'best_of':          best_of,
        'sim_count':        result.n_sims,
    }


def _pair_draftables_by_game(draftables: List[dict]) -> List[Tuple[dict, dict]]:
    """
    Group draftables into matchup pairs using the 'game_info' field.
    game_info format: 'PlayerA @ PlayerB HH:MMpm ET' or similar.
    Returns list of (player_a_dict, player_b_dict) pairs.
    Falls back to positional pairing if grouping fails.
    """
    from collections import defaultdict
    groups = defaultdict(list)

    for d in draftables:
        game_info = d.get('game_info', '') or ''
        groups[game_info].append(d)

    pairs = []
    for game_info, players in groups.items():
        if len(players) == 2:
            pairs.append((players[0], players[1]))
        elif len(players) > 2:
            # Multiple players in same 'game' (shouldn't happen in tennis)
            # Pair sequentially
            for i in range(0, len(players) - 1, 2):
                pairs.append((players[i], players[i + 1]))
        else:
            logger.warning('Only 1 player found for game_info=%r, skipping', game_info)

    if not pairs:
        logger.warning('game_info grouping failed; falling back to positional pairing')
        for i in range(0, len(draftables) - 1, 2):
            pairs.append((draftables[i], draftables[i + 1]))

    return pairs


def project_slate(
    dg_id: int,
    surface: str = 'hard',
    best_of: int = 3,
    n_sims: int = 10000,
    use_calibration: bool = True,
    db=None,
) -> pd.DataFrame:
    """
    Project a full DraftKings slate.

    1. Load draftables from DB
    2. Load profiles via ProfileLoader
    3. Pair players by matchup (game_info)
    4. Run MonteCarloEngine per matchup
    5. Build and return projection DataFrame
    6. Optionally persist projections to DB

    Args:
        dg_id:           DraftKings draftgroup ID
        surface:         Court surface ('hard', 'clay', 'grass')
        best_of:         3 or 5
        n_sims:          Simulations per matchup
        use_calibration: Apply Elo calibration
        db:              DatabaseManager instance (created if None)

    Returns:
        DataFrame sorted by proj_mean descending
    """
    if db is None:
        from pipeline.db.manager import DatabaseManager
        db = DatabaseManager()

    dk_format = '3set' if best_of == 3 else '5set'
    logger.info('project_slate: dg_id=%d surface=%s best_of=%d n_sims=%d', dg_id, surface, best_of, n_sims)

    draftables = db.get_draftables(dg_id)
    if not draftables:
        logger.error('No draftables found for dg_id=%d', dg_id)
        return pd.DataFrame()

    loader = _load_profile_loader(surface)
    engine = MonteCarloEngine(n_sims=n_sims, dk_format=dk_format)

    # Build salary lookup
    salary_map = {d.get('display_name') or d.get('player_name', ''): d.get('salary') for d in draftables}

    pairs = _pair_draftables_by_game(draftables)
    rows = []

    for d0, d1 in pairs:
        name0 = d0.get('display_name') or d0.get('player_name', 'Unknown')
        name1 = d1.get('display_name') or d1.get('player_name', 'Unknown')

        p0 = loader.get(name0, surface)
        p1 = loader.get(name1, surface)

        try:
            if use_calibration:
                r0, r1 = engine.run_with_calibration(p0, p1)
            else:
                r0, r1 = engine.run(p0, p1)
        except Exception as exc:
            logger.error('Simulation failed for %s vs %s: %s', name0, name1, exc)
            continue

        for r, name in [(r0, name0), (r1, name1)]:
            row = _sim_result_to_dict(r, salary_map.get(name), surface, best_of)
            rows.append(row)

            try:
                db.upsert_projection(dg_id, name, row)
            except Exception as exc:
                logger.warning('DB upsert failed for %s: %s', name, exc)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).sort_values('proj_mean', ascending=False).reset_index(drop=True)
    logger.info('project_slate complete: %d players projected', len(df))
    return df


def project_dummy_slate(
    matchups: List[Tuple[str, str]],
    surface: str = 'hard',
    salaries: dict = None,
    best_of: int = 3,
    n_sims: int = 10000,
    dg_id: int = 99001,
    use_calibration: bool = True,
) -> pd.DataFrame:
    """
    Project a manually-specified list of matchups. For testing/dev.

    Args:
        matchups:        List of (player1_name, player2_name) tuples
        surface:         Court surface
        salaries:        {player_name: salary} dict (optional)
        best_of:         3 or 5
        n_sims:          Simulations per matchup
        dg_id:           Dummy draftgroup ID for output labeling
        use_calibration: Apply Elo calibration

    Returns:
        DataFrame sorted by proj_mean descending
    """
    salaries = salaries or {}
    dk_format = '3set' if best_of == 3 else '5set'

    logger.info(
        'project_dummy_slate: dg_id=%d surface=%s best_of=%d n_sims=%d matchups=%d',
        dg_id, surface, best_of, n_sims, len(matchups),
    )

    loader = _load_profile_loader(surface)
    engine = MonteCarloEngine(n_sims=n_sims, dk_format=dk_format)

    rows = []
    for name0, name1 in matchups:
        p0 = loader.get(name0, surface)
        p1 = loader.get(name1, surface)

        try:
            if use_calibration:
                r0, r1 = engine.run_with_calibration(p0, p1)
            else:
                r0, r1 = engine.run(p0, p1)
        except Exception as exc:
            logger.error('Simulation failed for %s vs %s: %s', name0, name1, exc)
            continue

        for r, name in [(r0, name0), (r1, name1)]:
            row = _sim_result_to_dict(r, salaries.get(name), surface, best_of)
            rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).sort_values('proj_mean', ascending=False).reset_index(drop=True)
    return df


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.WARNING,
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )

    matchups = [
        ('Jannik Sinner',   'Daniil Medvedev'),
        ('Carlos Alcaraz',  'Alexander Zverev'),
        ('Novak Djokovic',  'Andrey Rublev'),
        ('Taylor Fritz',    'Tommy Paul'),
    ]
    salaries = {
        'Jannik Sinner':    10000,
        'Daniil Medvedev':   7600,
        'Carlos Alcaraz':    9800,
        'Alexander Zverev':  7800,
        'Novak Djokovic':    9200,
        'Andrey Rublev':     7400,
        'Taylor Fritz':      8200,
        'Tommy Paul':        7200,
    }

    print(f'\n=== Projections dg_id=99001 (hard, 3-set, N=10,000) ===')
    df = project_dummy_slate(
        matchups, surface='hard', salaries=salaries, n_sims=10000
    )
    cols = ['player_name', 'salary', 'proj_mean', 'proj_floor', 'proj_ceil', 'value', 'p_win', 'p_straight_sets']
    print(df[cols].to_string(index=False, float_format=lambda x: f'{x:.2f}' if x else 'N/A'))
