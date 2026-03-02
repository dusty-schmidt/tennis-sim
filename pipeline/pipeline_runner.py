"""
Orchestrates the full tennis DFS data pipeline refresh.

Usage:
  python pipeline/pipeline_runner.py
  python pipeline/pipeline_runner.py --force
  python pipeline/pipeline_runner.py --year 2024
"""
import sys
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger('pipeline_runner')


def _step(name: str):
    class _Timer:
        def __enter__(self):
            self.start = time.time()
            logger.info('▶ START: %s', name)
            return self
        def __exit__(self, *args):
            elapsed = time.time() - self.start
            logger.info('✓ DONE:  %s (%.1fs)', name, elapsed)
    return _Timer()


def run_pipeline(force: bool = False, years: list = None):
    summary = {}
    pipeline_start = time.time()
    logger.info('=' * 60)
    logger.info('Tennis DFS Pipeline — %s', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    logger.info('=' * 60)

    # ── Step 0: Fetch live DK tennis slates ─────────────────────────────────
    with _step('Fetch live DK tennis slates'):
        try:
            from pipeline.fetchers.dk_live import fetch_tennis_only
            dk_result = fetch_tennis_only()
            summary['dk_draftgroups_added'] = dk_result.get('draftgroups_added', 0)
            summary['dk_draftables_fetched'] = dk_result.get('draftables_fetched', 0)
            summary['dk_slates_total'] = dk_result.get('draftgroups_total', 0)
            logger.info('  DK: %d new draftgroups, %d draftables, %d total TEN slates',
                        dk_result.get('draftgroups_added', 0),
                        dk_result.get('draftables_fetched', 0),
                        dk_result.get('draftgroups_total', 0))
        except Exception as e:
            logger.warning('  DK fetch failed (non-fatal): %s', e)
            summary['dk_draftgroups_added'] = 0
            summary['dk_draftables_fetched'] = 0

    # ── Step 1: Fetch ATP data ───────────────────────────────────────────────
    with _step('Fetch ATP match data'):
        try:
            from pipeline.fetchers.atp_data import update_atp_data
            current_year = datetime.now().year
            fetch_years = years if years else [current_year - 1, current_year]
            atp_df = update_atp_data(years=fetch_years, force=force)
            summary['atp_rows'] = len(atp_df)
            summary['atp_years'] = fetch_years
            logger.info('  ATP data: %d rows, years %s', len(atp_df), fetch_years)
        except Exception as e:
            logger.error('  ATP fetch failed: %s', e)
            atp_df = None
            summary['atp_rows'] = 0

    # ── Step 2: Fetch Elo ratings ────────────────────────────────────────────
    with _step('Fetch TennisAbstract Elo ratings'):
        try:
            from pipeline.fetchers.tennis_abstract import fetch_elo_ratings
            elo_df = fetch_elo_ratings(force=force)
            summary['elo_players'] = len(elo_df)
            logger.info('  Elo ratings: %d players', len(elo_df))
        except Exception as e:
            logger.error('  Elo fetch failed: %s', e)
            elo_df = None
            summary['elo_players'] = 0

    # ── Step 3: Build surface stats ──────────────────────────────────────────
    stats = {}
    with _step('Build surface statistics'):
        try:
            if atp_df is not None and not atp_df.empty:
                from pipeline.processors.surface_stats import build_surface_stats, save_surface_stats
                stats = build_surface_stats(atp_df, min_matches=10, recency_weight=True)
                save_surface_stats(stats)
                summary['stats_players'] = len(stats)
                logger.info('  Surface stats: %d players', len(stats))
            else:
                logger.warning('  Skipped surface stats — no ATP data available')
                summary['stats_players'] = 0
        except Exception as e:
            logger.error('  Surface stats failed: %s', e)
            summary['stats_players'] = 0

    # ── Step 3b: Sync surface stats to DB ────────────────────────────────────
    with _step('Sync player profiles to DB'):
        try:
            if stats:
                from pipeline.db.manager import DatabaseManager
                from config.settings import config
                db = DatabaseManager(db_path=config.DATABASE_PATH)
                synced = 0
                for player_name, surfaces in stats.items():
                    for surface, stat_dict in surfaces.items():
                        db.upsert_player_profile(player_name, surface, stat_dict)
                        synced += 1
                db.close()
                summary['db_profiles_synced'] = synced
                logger.info('  Synced %d player×surface profiles to DB', synced)
            else:
                logger.warning('  Skipped DB sync — no stats built')
                summary['db_profiles_synced'] = 0
        except Exception as e:
            logger.warning('  DB sync failed (non-fatal): %s', e)
            summary['db_profiles_synced'] = 0

    # ── Step 4: Build player profiles (stub) ─────────────────────────────────
    with _step('Build player profiles (stub)'):
        try:
            from pipeline.processors.normalizer import build_name_index
            if atp_df is not None and not atp_df.empty:
                name_index = build_name_index(atp_df, elo_df)
                player_count = len(set(name_index.values()))
                summary['player_profiles'] = player_count
                logger.info('  Player profiles (stub): %d unique players', player_count)
            else:
                summary['player_profiles'] = 0
        except Exception as e:
            logger.error('  Profile build failed: %s', e)
            summary['player_profiles'] = 0

    # ── Summary ──────────────────────────────────────────────────────────────
    total_time = time.time() - pipeline_start
    logger.info('=' * 60)
    logger.info('Pipeline complete in %.1fs', total_time)
    logger.info('Summary:')
    for k, v in summary.items():
        logger.info('  %-30s %s', k + ':', v)
    logger.info('=' * 60)
    return summary


def main():
    parser = argparse.ArgumentParser(description='Tennis DFS Data Pipeline')
    parser.add_argument('--force', action='store_true', help='Force re-fetch all data')
    parser.add_argument('--year', type=int, default=None, help='Specific year to fetch')
    args = parser.parse_args()
    years = [args.year] if args.year else None
    run_pipeline(force=args.force, years=years)


if __name__ == '__main__':
    main()
