"""
Tennis Monte Carlo simulation engine.
"""
from .profiles import PlayerProfile, ProfileLoader, TOUR_AVG
from .engine import MonteCarloEngine, SimResult
from .match import simulate_match, MatchResult, SetResult
from .scoring import dk_score, extract_player_stats, PlayerStats
from .calibration import (
    calibrate_profiles,
    elo_match_win_prob,
    theory_game,
    effective_p_serve,
    prob_set_analytical,
    prob_match_analytical,
    prob_set_from_state,
    prob_match_from_state,
)

__all__ = [
    # Profiles
    'PlayerProfile', 'ProfileLoader', 'TOUR_AVG',
    # Engine
    'MonteCarloEngine', 'SimResult',
    # Match simulation
    'simulate_match', 'MatchResult', 'SetResult',
    # Scoring
    'dk_score', 'extract_player_stats', 'PlayerStats',
    # Calibration & analytical
    'calibrate_profiles', 'elo_match_win_prob',
    'theory_game', 'effective_p_serve',
    'prob_set_analytical', 'prob_match_analytical',
    'prob_set_from_state', 'prob_match_from_state',
]
