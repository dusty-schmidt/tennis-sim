"""
Fetches ATP match data from Jeff Sackmann's tennis_atp GitHub repository.

Public API:
  fetch_atp_season(year, force=False) -> pd.DataFrame
  update_atp_data(years=None, force=False) -> pd.DataFrame
"""
import sys
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.settings import RAW_DIR, SACKMANN_BASE_URL

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

ATP_DIR = RAW_DIR / 'atp'
ATP_DIR.mkdir(parents=True, exist_ok=True)


def fetch_atp_season(year: int, force: bool = False) -> pd.DataFrame:
    """
    Download atp_matches_{year}.csv from Sackmann GitHub.
    Saves to data/raw/atp/atp_{year}.csv.
    Returns loaded DataFrame.
    """
    dest = ATP_DIR / f'atp_{year}.csv'

    if dest.exists() and not force:
        logger.info('Using cached ATP data: %s', dest)
        return pd.read_csv(dest, low_memory=False)

    url = f'{SACKMANN_BASE_URL}/atp_matches_{year}.csv'
    logger.info('Downloading ATP %d data from %s', year, url)

    try:
        resp = requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning('Failed to fetch ATP %d data: %s', year, e)
        if dest.exists():
            logger.info('Using existing (possibly stale) file: %s', dest)
            return pd.read_csv(dest, low_memory=False)
        return pd.DataFrame()

    total = int(resp.headers.get('content-length', 0))
    downloaded = 0
    chunks = []

    for chunk in resp.iter_content(chunk_size=65536):
        if chunk:
            chunks.append(chunk)
            downloaded += len(chunk)

    data = b''.join(chunks)
    dest.write_bytes(data)

    size_kb = downloaded / 1024
    logger.info('Downloaded %.1f KB -> %s', size_kb, dest)

    df = pd.read_csv(dest, low_memory=False)
    logger.info('ATP %d: %d matches loaded', year, len(df))
    return df


def update_atp_data(years: list = None, force: bool = False) -> pd.DataFrame:
    """
    Fetch multiple years of ATP data and concatenate.
    Default: current year (2026) + last year.
    """
    current_year = datetime.now().year
    if years is None:
        years = [current_year - 1, current_year]

    dfs = []
    for year in years:
        df = fetch_atp_season(year, force=force)
        if not df.empty:
            df['_source_year'] = year
            dfs.append(df)

    if not dfs:
        logger.warning('No ATP data loaded for years: %s', years)
        return pd.DataFrame()

    combined = pd.concat(dfs, ignore_index=True)
    logger.info('Combined ATP data: %d rows from years %s', len(combined), years)
    return combined


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    df = update_atp_data()
    if df.empty:
        print('WARNING: No data loaded.')
    else:
        print(f'Shape: {df.shape}')
        if 'tourney_date' in df.columns:
            dates = pd.to_datetime(df['tourney_date'].astype(str), format='%Y%m%d', errors='coerce')
            print(f'Date range: {dates.min().date()} -> {dates.max().date()}')
        print(df.dtypes)
