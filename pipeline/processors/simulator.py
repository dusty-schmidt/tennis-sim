"""
Facade module — re-exports sim package for backwards compatibility.
Existing code using `from pipeline.processors.simulator import X` continues to work.
"""
from pipeline.processors.sim import (
    PlayerProfile,
    ProfileLoader,
    TOUR_AVG,
    MonteCarloEngine,
    SimResult,
    simulate_match,
    MatchResult,
    SetResult,
    dk_score,
    extract_player_stats,
    PlayerStats,
    calibrate_profiles,
    elo_match_win_prob,
)

__all__ = [
    'PlayerProfile', 'ProfileLoader', 'TOUR_AVG',
    'MonteCarloEngine', 'SimResult',
    'simulate_match', 'MatchResult', 'SetResult',
    'dk_score', 'extract_player_stats', 'PlayerStats',
    'calibrate_profiles', 'elo_match_win_prob',
]
