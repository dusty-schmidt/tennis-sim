"""
DraftKings scoring calculation from MatchResult.

v3 — corrected official DK scoring:
  - Match Played: flat +30 for every player
  - Game Won/Lost: ALL games (not just service games)
  - Break: return game won (+0.75 bo3, +0.5 bo5)
  - No Double Fault bonus
  - 10+ Aces bonus (bo3) / 15+ Aces bonus (bo5)
  - Correct set/match/straight-sets values
"""
from dataclasses import dataclass
from .match import MatchResult


@dataclass
class PlayerStats:
    """Accumulated DK-scoring stats for one player across one simulated match."""
    match_played: int = 1      # always 1 — flat +30 bonus
    games_won: int = 0         # ALL games won (serve + return)
    games_lost: int = 0        # ALL games lost
    sets_won: int = 0
    sets_lost: int = 0
    match_won: int = 0         # 1 if winner, else 0
    aces: int = 0
    double_faults: int = 0
    breaks: int = 0            # return games won (opponent's service game)
    clean_sets: int = 0        # sets won 6-0
    straight_sets: int = 0     # 1 if won match without losing a set
    no_double_fault: int = 0   # 1 if 0 DFs in entire match


def extract_player_stats(match_result: MatchResult, player_idx: int) -> PlayerStats:
    """Extract PlayerStats for a given player index from a MatchResult."""
    i   = player_idx
    opp = 1 - i
    won_match = (match_result.winner == i)

    return PlayerStats(
        match_played=1,
        games_won=match_result.games_won[i],
        games_lost=match_result.games_lost[i],
        sets_won=match_result.sets_won[i],
        sets_lost=match_result.sets_won[opp],
        match_won=1 if won_match else 0,
        aces=match_result.total_aces[i],
        double_faults=match_result.total_dfs[i],
        breaks=match_result.breaks[i],
        clean_sets=match_result.clean_sets[i],
        straight_sets=1 if (won_match and match_result.straight_sets) else 0,
        no_double_fault=match_result.no_double_fault[i],
    )


def dk_score(match_result: MatchResult, player_idx: int, scoring: dict) -> float:
    """
    Calculate DraftKings fantasy score for a player from a simulated match.

    Args:
        match_result: MatchResult from simulate_match()
        player_idx:   0 or 1 — which player to score
        scoring:      DK_SCORING['best_of_3'] or DK_SCORING['best_of_5']

    Returns:
        float DK fantasy points
    """
    ps = extract_player_stats(match_result, player_idx)

    pts  = scoring['match_played']
    pts += ps.games_won     * scoring['game_won']
    pts += ps.games_lost    * scoring['game_lost']
    pts += ps.sets_won      * scoring['set_won']
    pts += ps.sets_lost     * scoring['set_lost']
    pts += ps.match_won     * scoring['match_won']
    pts += ps.aces          * scoring['ace']
    pts += ps.double_faults * scoring['double_fault']
    pts += ps.breaks        * scoring['break']
    pts += ps.clean_sets    * scoring['clean_set']
    pts += ps.straight_sets * scoring['straight_sets']

    if ps.no_double_fault:
        pts += scoring['no_double_fault']

    # Ace bonus threshold: 10 for bo3 (ace=0.4), 15 for bo5 (ace=0.25)
    ace_threshold = 10 if abs(scoring['ace'] - 0.4) < 0.01 else 15
    if ps.aces >= ace_threshold:
        pts += scoring['ace_bonus']

    return round(pts, 2)


def calc_dk_points(stats: dict, best_of: int = 3) -> float:
    """
    Standalone DK points calculator from a stats dict.
    Useful for testing and external callers.

    Args:
        stats:   dict with keys matching PlayerStats fields
        best_of: 3 or 5

    Returns:
        float DK fantasy points
    """
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../..'))
    from config.settings import DK_SCORING
    sc = DK_SCORING[f'best_of_{best_of}']

    pts  = sc['match_played']
    pts += stats.get('games_won', 0)     * sc['game_won']
    pts += stats.get('games_lost', 0)    * sc['game_lost']
    pts += stats.get('sets_won', 0)      * sc['set_won']
    pts += stats.get('sets_lost', 0)     * sc['set_lost']
    pts += stats.get('match_won', 0)     * sc['match_won']
    pts += stats.get('aces', 0)          * sc['ace']
    pts += stats.get('double_faults', 0) * sc['double_fault']
    pts += stats.get('breaks', 0)        * sc['break']
    pts += stats.get('clean_sets', 0)    * sc['clean_set']
    pts += stats.get('straight_sets', 0) * sc['straight_sets']

    if stats.get('no_double_fault', 0):
        pts += sc['no_double_fault']

    ace_threshold = 10 if best_of == 3 else 15
    if stats.get('aces', 0) >= ace_threshold:
        pts += sc['ace_bonus']

    return round(pts, 2)
