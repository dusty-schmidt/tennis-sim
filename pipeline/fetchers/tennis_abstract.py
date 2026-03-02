"""
Fetches current ATP Elo ratings from TennisAbstract.
URL: http://www.tennisabstract.com/reports/atp_elo_ratings.html

Parses the HTML table and extracts:
  player, overall_elo, hard_elo, clay_elo, grass_elo

Cache: saves to data/raw/tennis_abstract/elo_ratings_{YYYYMMDD}.csv
Also writes data/raw/tennis_abstract/latest.csv

Public API:
  fetch_elo_ratings(force=False) -> pd.DataFrame
"""
import re
import sys
import logging
from pathlib import Path
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.settings import RAW_DIR, TENNIS_ABSTRACT_ELO_URL

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

TA_DIR = RAW_DIR / 'tennis_abstract'
TA_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    )
}

# Header text -> canonical field name
COL_HEADERS = {
    'EloRank':   'elo_rank',
    'Player':    'player',
    'Age':       'age',
    'Elo':       'overall_elo',
    'hElo':      'hard_elo',
    'cElo':      'clay_elo',
    'gElo':      'grass_elo',
    'PeakElo':   'peak_elo',
    'ATPRank':   'atp_rank',
}

# Split CamelCase player names like "CarlosAlcaraz" -> "Carlos Alcaraz"
_CAMEL_RE = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

def _split_camel(name: str) -> str:
    """Split CamelCase name into space-separated words."""
    if not name:
        return name
    return _CAMEL_RE.sub(' ', name).strip()


def _safe_float(val):
    """Convert cell text to float, return None for dashes/empty."""
    if val is None:
        return None
    s = str(val).strip().replace(',', '.')
    if s in ('', '-', 'N/A', 'n/a'):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_table(soup: BeautifulSoup) -> pd.DataFrame:
    """Parse the TennisAbstract Elo ratings table.

    Table structure:
      Row 0: artifact row (skip)
      Row 1: header row (th cells: EloRank, Player, Age, Elo, hElo, cElo, gElo...)
      Row 2+: data rows
    """
    tables = soup.find_all('table')
    if not tables:
        raise ValueError('No tables found on TennisAbstract Elo page')

    for table in tables:
        rows = table.find_all('tr')
        if len(rows) < 5:
            continue

        # Row 1 (index 1) has the real headers; row 0 is an artifact
        header_cells = rows[1].find_all(['th', 'td'])
        headers = [c.get_text(strip=True) for c in header_cells]

        if 'Player' not in headers or 'Elo' not in headers:
            continue  # not the right table

        # Build column index map
        col_map = {}  # index -> field name
        for i, h in enumerate(headers):
            if h in COL_HEADERS:
                col_map[i] = COL_HEADERS[h]

        if not col_map:
            continue

        records = []
        # Data rows start at index 2
        for row in rows[2:]:
            cells = row.find_all(['td', 'th'])
            if len(cells) < 4:
                continue
            texts = [c.get_text(strip=True) for c in cells]

            record = {}
            for idx, field in col_map.items():
                if idx >= len(texts):
                    continue
                val = texts[idx]
                if field == 'player':
                    record[field] = _split_camel(val)
                elif field in ('elo_rank', 'atp_rank'):
                    record[field] = _safe_float(val)
                else:
                    record[field] = _safe_float(val)

            if record.get('player'):
                records.append(record)

        if records:
            logger.info('Parsed %d player records from TennisAbstract', len(records))
            return pd.DataFrame(records)

    raise ValueError('Could not find Elo data table on TennisAbstract page')

def fetch_elo_ratings(force: bool = False) -> pd.DataFrame:
    """
    Fetch ATP Elo ratings from TennisAbstract.

    Returns cached today's file if it exists and force=False.
    Falls back to latest.csv if fetch fails.
    Returns empty DataFrame with correct columns on total failure.
    """
    today = datetime.now().strftime(' %Y%m%d').strip()
    dated_path = TA_DIR / f'elo_ratings_{today}.csv'
    latest_path = TA_DIR / 'latest.csv'

    if dated_path.exists() and not force:
        logger.info('Using cached Elo ratings: %s', dated_path)
        return pd.read_csv(dated_path)

    logger.info('Fetching Elo ratings from TennisAbstract...')
    try:
        resp = requests.get(TENNIS_ABSTRACT_ELO_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning('Failed to fetch TennisAbstract Elo ratings: %s', e)
        if latest_path.exists():
            logger.info('Falling back to latest cached file')
            return pd.read_csv(latest_path)
        return pd.DataFrame(columns=['player', 'overall_elo', 'hard_elo', 'clay_elo', 'grass_elo'])

    try:
        soup = BeautifulSoup(resp.text, 'lxml')
        df = _parse_table(soup)
    except (ValueError, Exception) as e:
        logger.warning('Failed to parse TennisAbstract page: %s', e)
        if latest_path.exists():
            logger.info('Falling back to latest cached file')
            return pd.read_csv(latest_path)
        return pd.DataFrame(columns=['player', 'overall_elo', 'hard_elo', 'clay_elo', 'grass_elo'])

    # Ensure all elo columns exist
    for col in ['overall_elo', 'hard_elo', 'clay_elo', 'grass_elo']:
        if col not in df.columns:
            df[col] = None

    # Fill surface elos with overall fallback
    for col in ['hard_elo', 'clay_elo', 'grass_elo']:
        df[col] = df[col].fillna(df['overall_elo'])

    # Cast elo columns to float
    for col in ['overall_elo', 'hard_elo', 'clay_elo', 'grass_elo']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # Drop rows with no player or no elo at all
    df = df.dropna(subset=['player', 'overall_elo'])
    df = df[[c for c in ['player', 'overall_elo', 'hard_elo', 'clay_elo', 'grass_elo'] if c in df.columns]]

    df.to_csv(dated_path, index=False)
    df.to_csv(latest_path, index=False)
    logger.info('Saved %d players to %s', len(df), dated_path)

    return df


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    df = fetch_elo_ratings(force=True)
    if df.empty:
        print('WARNING: Returned empty DataFrame (fetch may have failed).')
    else:
        print(f'Shape: {df.shape}')
        print(df.head(10).to_string())
