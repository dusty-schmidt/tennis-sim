"""
Loads and parses DraftKings tennis contest export CSV files.

DK tennis slate CSV format:
  Name, ID, Roster Position, Salary, Game Info, TeamAbbrev, AvgPointsPerGame

Public API:
  load_slate(path) -> pd.DataFrame
  list_slates() -> list[str]
"""
import re
import sys
import logging
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.settings import RAW_DIR

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

DK_DIR = RAW_DIR / 'dk_slates'
DK_DIR.mkdir(parents=True, exist_ok=True)

# Regex: "Player A vs Player B (Surface) MM/DD/YYYY HH:MMAM ET"
# Surface part is optional
GAME_INFO_RE = re.compile(
    r'([^(]+?)\s+vs\s+([^(]+?)\s*(?:\(([^)]+)\)\s*)?\d{2}/\d{2}/\d{4}',
    re.IGNORECASE
)

# Strip team abbreviation suffix like "Sinner (SIN)" -> "Sinner"
NAME_SUFFIX_RE = re.compile(r'\s*\([A-Z]{2,4}\)\s*$')

# Surfaces mentioned in game info
SURFACE_WORDS = {'hard', 'clay', 'grass', 'indoor', 'carpet'}


def _strip_name(name: str) -> str:
    """Remove DK team suffix like (SIN) from player name."""
    return NAME_SUFFIX_RE.sub('', str(name).strip())


def _parse_game_info(game_info: str, player_name: str):
    """
    Parse Game Info field to extract matchup, opponent, and optional surface.
    Returns (matchup, opponent, surface_guess).
    """
    if not isinstance(game_info, str):
        return None, None, None

    m = GAME_INFO_RE.search(game_info)
    if not m:
        return game_info.strip(), None, None

    left = m.group(1).strip()
    right = m.group(2).strip()
    extra = m.group(3).strip() if m.group(3) else ''

    matchup = f'{left} vs {right}'

    # Determine opponent by checking which side player_name is on
    pname_lower = player_name.lower()
    left_lower = left.lower()
    right_lower = right.lower()

    if pname_lower in left_lower or any(
        part in left_lower for part in pname_lower.split() if len(part) > 3
    ):
        opponent = right
    elif pname_lower in right_lower or any(
        part in right_lower for part in pname_lower.split() if len(part) > 3
    ):
        opponent = left
    else:
        # fallback: pick side that doesn't contain player name fragments
        opponent = right  # default

    # Try to extract surface from extra field
    surface_guess = None
    if extra:
        extra_lower = extra.lower()
        for s in SURFACE_WORDS:
            if s in extra_lower:
                surface_guess = s
                break

    return matchup, opponent, surface_guess


def load_slate(path: str) -> pd.DataFrame:
    """
    Load a DraftKings tennis slate CSV.

    Returns DataFrame with columns:
      player_name, dk_id, salary, position, matchup, opponent,
      game_info, avg_ppg, surface_guess
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f'Slate file not found: {path}')

    logger.info('Loading DK slate: %s', path)
    df = pd.read_csv(path)

    # Normalize column names
    df.columns = [c.strip() for c in df.columns]

    # Flexible column mapping
    col_map = {
        'Name': 'player_name',
        'ID': 'dk_id',
        'Roster Position': 'position',
        'Salary': 'salary',
        'Game Info': 'game_info',
        'TeamAbbrev': 'team_abbrev',
        'AvgPointsPerGame': 'avg_ppg',
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    # Ensure required columns exist
    for col in ['player_name', 'dk_id', 'salary', 'game_info']:
        if col not in df.columns:
            logger.warning('Missing expected column: %s', col)
            df[col] = None

    # Strip player name suffixes
    df['player_name'] = df['player_name'].apply(
        lambda x: _strip_name(x) if pd.notna(x) else x
    )

    # Parse game info
    parsed = df.apply(
        lambda row: _parse_game_info(
            row.get('game_info', ''),
            row.get('player_name', '') or ''
        ),
        axis=1,
        result_type='expand'
    )
    df['matchup'] = parsed[0]
    df['opponent'] = parsed[1]
    df['surface_guess'] = parsed[2]

    # Clean salary
    if 'salary' in df.columns:
        df['salary'] = (
            df['salary']
            .astype(str)
            .str.replace(r'[\$,]', '', regex=True)
            .pipe(pd.to_numeric, errors='coerce')
        )

    if 'avg_ppg' in df.columns:
        df['avg_ppg'] = pd.to_numeric(df['avg_ppg'], errors='coerce')

    output_cols = [
        'player_name', 'dk_id', 'salary', 'position',
        'matchup', 'opponent', 'game_info', 'avg_ppg', 'surface_guess'
    ]
    return df[[c for c in output_cols if c in df.columns]]


def list_slates() -> list:
    """Return sorted list of all .csv files in data/raw/dk_slates/."""
    slates = sorted(DK_DIR.glob('*.csv'))
    return [str(s) for s in slates]


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    slates = list_slates()
    print(f'Found {len(slates)} slate(s) in {DK_DIR}')
    for s in slates:
        print(f'  {s}')

    if slates:
        df = load_slate(slates[0])
        print(f'\nFirst slate shape: {df.shape}')
        print(df.head(10).to_string())
    else:
        print('\nNo slates found. Place DK export CSVs in:', DK_DIR)
