import sys
import time
import requests
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from pipeline.db.manager import DatabaseManager
from pipeline.core.logger import get_logger, setup_logging
from config.settings import config

setup_logging()
logger = get_logger(__name__)


def _get_db() -> DatabaseManager:
    return DatabaseManager(db_path=config.DATABASE_PATH)


def _safe_get(url: str, params: dict = None, timeout: int = None) -> dict:
    """GET with retry logic. Returns parsed JSON or empty dict on failure."""
    timeout = timeout or config.REQUEST_TIMEOUT
    for attempt in range(config.REQUEST_RETRY_COUNT):
        try:
            resp = requests.get(url, params=params, timeout=timeout,
                                headers={'User-Agent': 'Mozilla/5.0'})
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            logger.warning(f"HTTP {e.response.status_code} on attempt {attempt+1}: {url}")
        except Exception as e:
            logger.warning(f"Request failed attempt {attempt+1}: {e}")
        if attempt < config.REQUEST_RETRY_COUNT - 1:
            time.sleep(config.REQUEST_DELAY * (attempt + 1))
    return {}


def fetch_sports() -> list:
    """Fetch all sports from DK API."""
    logger.info("Fetching sports list from DK API")
    data = _safe_get(config.DRAFTKINGS_SPORTS_ENDPOINT)
    if not data:
        logger.error("Failed to fetch sports")
        return []
    sports = data.get('sports', [])
    logger.info(f"Found {len(sports)} sports")
    return sports


def fetch_contests(sport: str) -> dict:
    """Fetch contest data for a given sport abbreviation."""
    url = config.DRAFTKINGS_CONTESTS_ENDPOINT.format(sport=sport)
    logger.info(f"Fetching contests for sport: {sport}")
    data = _safe_get(url)
    return data


def fetch_draftables(dg_id: int) -> list:
    """Fetch draftable players for a draft group."""
    url = config.DRAFTKINGS_DRAFTABLES_ENDPOINT.format(draftgroup_id=dg_id)
    logger.info(f"Fetching draftables for dg_id={dg_id}")
    data = _safe_get(url)
    return data.get('draftables', [])


def fetch_and_store_draftgroup_metadata(sport: str, contest_data: dict, db: DatabaseManager) -> int:
    """Parse contests response and upsert draftgroups. Returns count of new groups."""
    new_count = 0
    draft_groups = contest_data.get('DraftGroups', [])
    if not draft_groups:
        draft_groups = contest_data.get('draftGroups', [])
    logger.info(f"Processing {len(draft_groups)} draft groups for {sport}")

    for dg in draft_groups:
        # Support both camelCase and PascalCase field names
        dg_id = dg.get('DraftGroupId') or dg.get('draftGroupId')
        if not dg_id:
            continue

        game_type = dg.get('GameTypeId') or dg.get('gameTypeId', '')  
        game_type_name = dg.get('ContestTypeAbbreviation') or dg.get('gameType') or str(game_type)

        # Filter by valid game types (skip filter for TEN - tennis has varied contest type names)
        if sport != 'TEN':
            if game_type_name and not any(vt in game_type_name.lower() for vt in ['classic', 'showdown', 'single']):
                logger.debug(f"Skipping game type: {game_type_name}")
                continue

        start_time = dg.get('StartDate') or dg.get('startDate') or dg.get('startTime')
        prize_pool = 0.0
        min_fee = 0.0
        contest_count = dg.get('ContestCount') or dg.get('contestCount', 0)
        draft_count = dg.get('DraftCount') or dg.get('draftCount', 0)

        dg_data = {
            'dg_id': dg_id,
            'sport': sport,
            'game_type': game_type_name,
            'start_time': start_time,
            'contest_count': contest_count,
            'draft_count': draft_count,
            'entries_remaining': dg.get('EntriesRemaining') or dg.get('entriesRemaining', 0),
            'prize_pool': prize_pool,
            'min_entry_fee': min_fee,
            'description': dg.get('Description') or dg.get('name', ''),
        }
        is_new = db.upsert_draftgroup(dg_data)
        if is_new:
            new_count += 1
    return new_count


def fetch_and_store_draftables(dg_id: int, db: DatabaseManager) -> int:
    """Fetch and store draftables for a draft group. Returns count stored."""
    if db.draftgroup_has_draftables(dg_id):
        logger.info(f"dg_id={dg_id} already has draftables, skipping")
        return 0

    players = fetch_draftables(dg_id)
    if not players:
        logger.warning(f"No draftables returned for dg_id={dg_id}")
        return 0

    count = 0
    for p in players:
        player_id = p.get('playerId') or p.get('draftableId')
        player_name = (p.get('displayName') or p.get('name', 'Unknown')).strip()
        draftable = {
            'dg_id': dg_id,
            'player_id': player_id,
            'player_name': player_name,
            'display_name': p.get('displayName'),
            'team_abbrev': p.get('teamAbbreviation') or p.get('teamCode'),
            'position': p.get('rosterSlotId') or p.get('position'),
            'salary': p.get('salary'),
            'avg_ppg': p.get('avgPointsPerGame', 0),
            'game_info': p.get('gameDescription') or p.get('competition', {}).get('name'),
            'status': p.get('status', 'Active'),
        }
        db.upsert_draftable(draftable)
        count += 1

    time.sleep(config.REQUEST_DELAY)
    logger.info(f"Stored {count} draftables for dg_id={dg_id}")
    return count


def fetch_tennis_only() -> dict:
    """
    Fetch only TEN (tennis) sport draftgroups and draftables.
    Main entry point for the tennis pipeline.
    Returns dict with keys: draftgroups_added, draftables_fetched
    """
    db = _get_db()
    stats = {'draftgroups_added': 0, 'draftables_fetched': 0, 'draftgroups_total': 0}

    try:
        # Step 1: Fetch TEN contests
        contest_data = fetch_contests('TEN')
        if not contest_data:
            logger.warning("No TEN contest data returned from DK — no live tennis slates today")
            return stats

        # Step 2: Store draftgroup metadata
        new_dgs = fetch_and_store_draftgroup_metadata('TEN', contest_data, db)
        stats['draftgroups_added'] = new_dgs

        # Step 3: Get all TEN draftgroups and fetch draftables for any without
        all_ten = db.get_tennis_slates()
        stats['draftgroups_total'] = len(all_ten)
        total_draftables = 0

        for dg in all_ten:
            fetched = fetch_and_store_draftables(dg['dg_id'], db)
            total_draftables += fetched

        stats['draftables_fetched'] = total_draftables

        # Step 4: Update sports inventory
        db.update_sports_inventory([{'sportName': 'TEN', 'sportId': None}])

        logger.info(f"TEN fetch complete: {stats}")
    except Exception as e:
        logger.error(f"fetch_tennis_only failed: {e}", exc_info=True)
    finally:
        db.close()

    return stats


def main():
    """Fetch all sports, then all draftgroups and draftables."""
    db = _get_db()
    try:
        sports = fetch_sports()
        db.update_sports_inventory(sports)
        total_new = 0
        total_draftables = 0
        sport_names = [s.get('sportAbbreviation', s.get('abbreviation', '')) for s in sports]
        for sport_abbr in sport_names:
            if not sport_abbr:
                continue
            contest_data = fetch_contests(sport_abbr)
            if contest_data:
                new_dgs = fetch_and_store_draftgroup_metadata(sport_abbr, contest_data, db)
                total_new += new_dgs
                for dg in db.get_all_draftgroups(sport=sport_abbr):
                    total_draftables += fetch_and_store_draftables(dg['dg_id'], db)
        logger.info(f"Full fetch complete: {total_new} new draftgroups, {total_draftables} draftables")
    finally:
        db.close()


if __name__ == '__main__':
    result = fetch_tennis_only()
    print(f"Tennis fetch result: {result}")
