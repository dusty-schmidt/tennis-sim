"""
Player name normalization across ATP, TennisAbstract, MCP, and DraftKings data sources.

Public API:
  normalize_name(name) -> str
  build_name_index(atp_df, ta_df) -> dict
  get_canonical(name, index, threshold=85) -> Optional[str]
"""
import re
import sys
import logging
from pathlib import Path
from typing import Optional

from rapidfuzz import process as rf_process, fuzz as rf_fuzz

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# ── Known aliases / nicknames ──────────────────────────────────────────────────
ALIASES: dict[str, str] = {
    'Nole': 'Novak Djokovic',
    'Carlitos': 'Carlos Alcaraz',
    'Rafa': 'Rafael Nadal',
    'Federer': 'Roger Federer',
    'Djokovic': 'Novak Djokovic',
    'Nadal': 'Rafael Nadal',
    'Murray': 'Andy Murray',
    'Wawrinka': 'Stan Wawrinka',
    'Sinner': 'Jannik Sinner',
    'Alcaraz': 'Carlos Alcaraz',
    'Medvedev': 'Daniil Medvedev',
    'Zverev': 'Alexander Zverev',
    'Tsitsipas': 'Stefanos Tsitsipas',
    'Ruud': 'Casper Ruud',
    'Rune': 'Holger Rune',
    'Fritz': 'Taylor Fritz',
    'Hurkacz': 'Hubert Hurkacz',
    'Dimitrov': 'Grigor Dimitrov',
    'Tiafoe': 'Frances Tiafoe',
    'Auger-Aliassime': 'Felix Auger-Aliassime',
    'FAA': 'Felix Auger-Aliassime',
    'Berrettini': 'Matteo Berrettini',
    'Cilic': 'Marin Cilic',
    'Shapovalov': 'Denis Shapovalov',
    'Khachanov': 'Karen Khachanov',
    'Bublik': 'Alexander Bublik',
    'Korda': 'Sebastian Korda',
    'Shelton': 'Ben Shelton',
    'Lehecka': 'Jiri Lehecka',
    'Musetti': 'Lorenzo Musetti',
    'Jarry': 'Nicolas Jarry',
    'Cerundolo': 'Francisco Cerundolo',
    'Arnaldi': 'Mattia Arnaldi',
    'Draper': 'Jack Draper',
    'Paul': 'Tommy Paul',
    'Struff': 'Jan-Lennard Struff',
    'Grigor': 'Grigor Dimitrov',
    'Jannik': 'Jannik Sinner',
    'Carlos': 'Carlos Alcaraz',
    'Novak': 'Novak Djokovic',
    'Holger': 'Holger Rune',
}

# ── Name cleaning helpers ──────────────────────────────────────────────────────
# Matches patterns like "SINNER, J." or "ALCARAZ, C."
_LAST_FIRST_INITIAL_RE = re.compile(r'^([A-Z][A-Z\-]*),\s*([A-Z])\.?$')

# Matches abbreviated forms like "J. Sinner" or "C. Alcaraz"
_INITIAL_LAST_RE = re.compile(r'^([A-Z])\.?\s+(.+)$')


def normalize_name(name: str) -> str:
    """
    Normalize a player name to canonical 'Firstname Lastname' form.
    Handles:
      - ALL CAPS
      - SINNER J. -> J. Sinner
      - whitespace stripping
      - known alias substitution
      - Title-case enforcement
    """
    if not name or not isinstance(name, str):
        return ''

    name = name.strip()

    # Check alias table first (case-insensitive)
    alias_hit = ALIASES.get(name)
    if alias_hit:
        return alias_hit

    name_lower = name.lower()
    for alias, canonical in ALIASES.items():
        if alias.lower() == name_lower:
            return canonical

    # Handle "SINNER, J." format -> "J. Sinner"
    m = _LAST_FIRST_INITIAL_RE.match(name.upper())
    if m:
        last, initial = m.group(1), m.group(2)
        last_title = '-'.join(p.capitalize() for p in last.split('-'))
        return f'{initial}. {last_title}'

    # Handle "J. Sinner" -> leave initial, capitalize last
    m = _INITIAL_LAST_RE.match(name)
    if m:
        initial, last = m.group(1), m.group(2)
        last_title = ' '.join(
            '-'.join(p.capitalize() for p in word.split('-'))
            for word in last.split()
        )
        return f'{initial}. {last_title}'

    # General case: title-case each word, preserve hyphens
    parts = name.split()
    titled = []
    for part in parts:
        if '-' in part:
            titled.append('-'.join(p.capitalize() for p in part.split('-')))
        elif part.upper() == part and len(part) > 2:  # ALL CAPS word
            titled.append(part.capitalize())
        else:
            titled.append(part)
    result = ' '.join(titled)

    return ALIASES.get(result, result)


def build_name_index(
    atp_df,
    ta_df=None
) -> dict:
    """
    Build mapping from all name variants to canonical names.
    ATP winner_name / loser_name are canonical ground truth.
    TA last-name-only forms mapped via exact last-name + fuzzy matching.

    Returns {variant: canonical}
    """
    index = {}

    # ── Step 1: ATP canonical names ──────────────────────────────────────
    atp_names = set()
    if atp_df is not None and not atp_df.empty:
        for col in ['winner_name', 'loser_name']:
            if col in atp_df.columns:
                atp_names.update(atp_df[col].dropna().unique())

    for name in atp_names:
        normalized = normalize_name(name)
        index[name] = normalized
        index[normalized] = normalized

    # Add aliases
    for alias, canonical in ALIASES.items():
        norm_canonical = normalize_name(canonical)
        if norm_canonical in index.values() or canonical in index:
            index[alias] = index.get(canonical, norm_canonical)
            index[alias.lower()] = index.get(canonical, norm_canonical)

    # Build last-name -> canonical for TA matching
    last_name_to_canonical = {}
    for canonical in set(index.values()):
        parts = canonical.split()
        if len(parts) >= 2:
            last = parts[-1].lower()
            if last not in last_name_to_canonical:
                last_name_to_canonical[last] = canonical

    # ── Step 2: TennisAbstract names ─────────────────────────────────────
    if ta_df is not None and not ta_df.empty and 'player' in ta_df.columns:
        ta_names = ta_df['player'].dropna().unique()
        canonical_list = list(set(index.values()))

        for ta_name in ta_names:
            ta_name = str(ta_name).strip()
            if ta_name in index:
                continue

            ta_lower = ta_name.lower()
            if ta_lower in last_name_to_canonical:
                index[ta_name] = last_name_to_canonical[ta_lower]
                continue

            alias_hit = ALIASES.get(ta_name)
            if alias_hit:
                index[ta_name] = normalize_name(alias_hit)
                continue

            if canonical_list:
                result = rf_process.extractOne(
                    ta_name,
                    canonical_list,
                    scorer=rf_fuzz.token_sort_ratio,
                    score_cutoff=80
                )
                if result:
                    index[ta_name] = result[0]

    logger.info('Name index built: %d entries', len(index))
    return index


def get_canonical(
    name: str,
    index: dict,
    threshold: int = 85
) -> Optional[str]:
    """
    Look up name in index. Exact first, then fuzzy via rapidfuzz.
    Returns canonical name or None if below threshold.
    """
    if not name:
        return None

    if name in index:
        return index[name]

    norm = normalize_name(name)
    if norm in index:
        return index[norm]

    keys = list(index.keys())
    if not keys:
        return None

    result = rf_process.extractOne(
        norm,
        keys,
        scorer=rf_fuzz.token_sort_ratio,
        score_cutoff=threshold
    )
    if result:
        matched_key = result[0]
        return index[matched_key]

    return None


if __name__ == '__main__':
    test_names = [
        'SINNER, J.',
        'ALCARAZ, C.',
        'Nole',
        'Carlitos',
        'Rafa',
        'FAA',
        'Auger-Aliassime',
        'medvedev',
        'J. Sinner',
        'Felix Auger-Aliassime',
        'Jannik Sinner',
    ]

    print('Name normalization demo:')
    print('-' * 45)
    for n in test_names:
        print(f'  {n!r:30} -> {normalize_name(n)!r}')

    import pandas as pd
    mock_atp = pd.DataFrame({
        'winner_name': ['Jannik Sinner', 'Carlos Alcaraz', 'Novak Djokovic', 'Daniil Medvedev'],
        'loser_name':  ['Holger Rune', 'Taylor Fritz', 'Alexander Zverev', 'Casper Ruud'],
    })
    mock_ta = pd.DataFrame({'player': ['Sinner', 'Alcaraz', 'Djokovic', 'Medvedev', 'Zverev']})

    idx = build_name_index(mock_atp, mock_ta)
    print(f'\nName index: {len(idx)} entries')

    print('\nCanonical lookup tests:')
    for variant in ['Sinner', 'Carlitos', 'Nole', 'Zverev', 'Medvedv']:
        result = get_canonical(variant, idx, threshold=75)
        print(f'  {variant!r:20} -> {result!r}')
