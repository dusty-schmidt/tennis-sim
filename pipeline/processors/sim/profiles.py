"""
PlayerProfile dataclass and ProfileLoader.
Loads player stats from surface_stats JSON or DB, merges Elo, falls back to tour averages.
"""
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

logger = logging.getLogger(__name__)

# Tour average defaults (ATP baseline)
TOUR_AVG = {
    'first_serve_pct': 0.615,
    'first_serve_won_pct': 0.737,
    'second_serve_won_pct': 0.527,
    'ace_per_game': 0.52,
    'df_per_game': 0.22,
    'return_pts_won_pct': 0.374,
    'sv_games_per_match': 11.2,
}

# Mapping from surface_stats JSON keys -> PlayerProfile field names
_STAT_KEY_MAP = {
    '1stServe_pct':       'first_serve_pct',
    '1stServeWon_pct':    'first_serve_won_pct',
    '2ndServeWon_pct':    'second_serve_won_pct',
    'ace_per_game':       'ace_per_game',
    'df_per_game':        'df_per_game',
    'return_pts_won_pct': 'return_pts_won_pct',
    'sv_games_per_match': 'sv_games_per_match',
}

# Mapping from DB player_profiles column names -> PlayerProfile field names
_DB_KEY_MAP = {
    'first_serve_pct':       'first_serve_pct',
    'first_serve_won_pct':   'first_serve_won_pct',
    'second_serve_won_pct':  'second_serve_won_pct',
    'ace_per_game':          'ace_per_game',
    'df_per_game':           'df_per_game',
    'return_pts_won_pct':    'return_pts_won_pct',
    'sv_games_per_match':    'sv_games_per_match',
}

_ELO_SURFACE_COL = {
    'hard':    'hard_elo',
    'clay':    'clay_elo',
    'grass':   'grass_elo',
    'indoor':  'hard_elo',   # fall back to hard for indoor
    'overall': 'overall_elo',
}


@dataclass
class PlayerProfile:
    name: str
    elo: float = 1500.0
    first_serve_pct: float = 0.615
    first_serve_won_pct: float = 0.737
    second_serve_won_pct: float = 0.527
    ace_per_game: float = 0.52
    df_per_game: float = 0.22
    return_pts_won_pct: float = 0.374
    sv_games_per_match: float = 11.2
    surface: str = 'hard'

    def copy(self) -> 'PlayerProfile':
        """Return a shallow copy."""
        return PlayerProfile(
            name=self.name,
            elo=self.elo,
            first_serve_pct=self.first_serve_pct,
            first_serve_won_pct=self.first_serve_won_pct,
            second_serve_won_pct=self.second_serve_won_pct,
            ace_per_game=self.ace_per_game,
            df_per_game=self.df_per_game,
            return_pts_won_pct=self.return_pts_won_pct,
            sv_games_per_match=self.sv_games_per_match,
            surface=self.surface,
        )


class ProfileLoader:
    """
    Load PlayerProfile from surface_stats JSON or DB.
    Falls back to tour averages for missing fields.
    Merges Elo from elo_df (tennis_abstract latest.csv).
    """

    def __init__(self, stats_dict: dict = None, elo_df: pd.DataFrame = None):
        """
        Args:
            stats_dict: from load_surface_stats() — {player: {surface: {stat: val}}}
            elo_df: pd.read_csv('data/raw/tennis_abstract/latest.csv')
                    columns: player, overall_elo, hard_elo, clay_elo, grass_elo
        """
        self._stats = stats_dict or {}
        self._elo_df = elo_df
        self._elo_index: dict = {}   # lowercase name -> row
        self._elo_names: list = []   # list of lowercase names for fuzzy match

        if elo_df is not None and not elo_df.empty:
            for _, row in elo_df.iterrows():
                name_lower = str(row['player']).lower().strip()
                self._elo_index[name_lower] = row
            self._elo_names = list(self._elo_index.keys())
            logger.debug('EloIndex loaded: %d players', len(self._elo_names))

    def _lookup_elo(self, player_name: str, surface: str) -> Optional[float]:
        """Fuzzy-match player name in Elo index, return surface Elo."""
        if not self._elo_names:
            return None

        col = _ELO_SURFACE_COL.get(surface.lower(), 'hard_elo')
        name_lower = player_name.lower().strip()

        # Exact match first
        if name_lower in self._elo_index:
            val = self._elo_index[name_lower].get(col)
            return float(val) if val is not None and not pd.isna(val) else None

        # Fuzzy match with rapidfuzz
        try:
            from rapidfuzz import process as rf_process, fuzz
            match = rf_process.extractOne(
                name_lower, self._elo_names,
                scorer=fuzz.WRatio, score_cutoff=80
            )
            if match:
                matched_name, score, _ = match
                row = self._elo_index[matched_name]
                val = row.get(col)
                logger.debug('Elo fuzzy match: "%s" -> "%s" (score=%d)', player_name, matched_name, score)
                return float(val) if val is not None and not pd.isna(val) else None
        except ImportError:
            logger.warning('rapidfuzz not available; skipping fuzzy Elo lookup')

        return None

    def _stats_for_player(self, player_name: str, surface: str) -> dict:
        """
        Return raw stats dict from surface_stats for player.
        Fallback: surface-specific -> overall -> {}.
        """
        player_data = self._stats.get(player_name, {})
        surf_lower = surface.lower()

        if surf_lower in player_data:
            return player_data[surf_lower]
        if 'overall' in player_data:
            logger.debug('%s: no %s stats, using overall', player_name, surface)
            return player_data['overall']

        # Try fuzzy match on player name in stats dict
        if self._stats:
            try:
                from rapidfuzz import process as rf_process, fuzz
                match = rf_process.extractOne(
                    player_name.lower(),
                    [k.lower() for k in self._stats.keys()],
                    scorer=fuzz.WRatio, score_cutoff=85
                )
                if match:
                    matched_lower, score, idx = match
                    matched_key = list(self._stats.keys())[idx]
                    player_data2 = self._stats[matched_key]
                    logger.debug('Stats fuzzy match: "%s" -> "%s" (score=%d)', player_name, matched_key, score)
                    if surf_lower in player_data2:
                        return player_data2[surf_lower]
                    if 'overall' in player_data2:
                        return player_data2['overall']
            except ImportError:
                pass

        return {}

    def get(self, player_name: str, surface: str) -> PlayerProfile:
        """
        Build PlayerProfile for player on surface.
        Priority: surface_stats -> tour averages, then merge Elo.
        Logs warning when using full tour averages.
        """
        raw = self._stats_for_player(player_name, surface)

        if not raw:
            logger.warning('No stats found for "%s" on %s — using tour averages', player_name, surface)

        # Start from tour averages, overlay with actual stats
        merged = dict(TOUR_AVG)
        for src_key, dst_key in _STAT_KEY_MAP.items():
            if src_key in raw and raw[src_key] is not None:
                merged[dst_key] = float(raw[src_key])

        # Elo lookup
        elo = self._lookup_elo(player_name, surface)
        if elo is None:
            elo = 1500.0
            logger.debug('No Elo for "%s", using default 1500', player_name)

        return PlayerProfile(
            name=player_name,
            elo=elo,
            surface=surface.lower(),
            **{k: merged[k] for k in TOUR_AVG},
        )

    def from_slate_draftables(self, draftables: list, surface: str) -> list:
        """
        Build PlayerProfile list from DK draftables.
        Each draftable dict has 'display_name' (and optionally 'player_name').
        """
        profiles = []
        for d in draftables:
            name = d.get('display_name') or d.get('player_name', 'Unknown')
            profiles.append(self.get(name, surface))
        return profiles
