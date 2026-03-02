"""
Monte Carlo simulation engine.
Runs N match simulations and aggregates DK fantasy point distributions.
"""
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from config.settings import DK_SCORING

from .profiles import PlayerProfile
from .match import simulate_match
from .scoring import dk_score
from .calibration import calibrate_profiles

logger = logging.getLogger(__name__)


@dataclass
class SimResult:
    player_name: str
    n_sims: int
    mean: float
    std: float
    floor: float          # p10
    p25: float
    p75: float
    ceil: float           # p90
    p_win: float
    p_straight_sets: float  # P(win in straight sets)
    p_clean_set: float      # P(win at least one 6-0 set)
    raw: np.ndarray         # shape (n_sims,) — DK pts per sim


class MonteCarloEngine:
    """
    Runs Monte Carlo tennis match simulations and returns DK point distributions.
    """

    def __init__(
        self,
        n_sims: int = 10000,
        dk_format: str = '3set',
        seed: int = None,
    ):
        """
        Args:
            n_sims:    Number of simulations per matchup
            dk_format: '3set' or '5set'
            seed:      RNG seed for reproducibility (None = random)
        """
        self.n_sims  = n_sims
        self.best_of = 3 if dk_format == '3set' else 5
        key = 'best_of_3' if dk_format == '3set' else 'best_of_5'
        self.scoring = DK_SCORING[key]
        self.rng     = np.random.default_rng(seed)
        logger.debug('MonteCarloEngine: n_sims=%d best_of=%d', n_sims, self.best_of)

    def _build_result(
        self,
        player_name: str,
        scores: np.ndarray,
        wins: np.ndarray,
        straight_set_wins: np.ndarray,
        clean_set_wins: np.ndarray,
    ) -> SimResult:
        n = len(scores)
        return SimResult(
            player_name=player_name,
            n_sims=n,
            mean=float(np.mean(scores)),
            std=float(np.std(scores)),
            floor=float(np.percentile(scores, 10)),
            p25=float(np.percentile(scores, 25)),
            p75=float(np.percentile(scores, 75)),
            ceil=float(np.percentile(scores, 90)),
            p_win=float(np.mean(wins)),
            p_straight_sets=float(np.mean(straight_set_wins)),
            p_clean_set=float(np.mean(clean_set_wins)),
            raw=scores,
        )

    def run(
        self,
        p0: PlayerProfile,
        p1: PlayerProfile,
    ) -> Tuple[SimResult, SimResult]:
        """
        Run n_sims match simulations. Returns (p0_result, p1_result).
        """
        scores0 = np.empty(self.n_sims, dtype=np.float64)
        scores1 = np.empty(self.n_sims, dtype=np.float64)
        wins0   = np.empty(self.n_sims, dtype=np.float64)
        wins1   = np.empty(self.n_sims, dtype=np.float64)
        ss0     = np.empty(self.n_sims, dtype=np.float64)
        ss1     = np.empty(self.n_sims, dtype=np.float64)
        cs0     = np.empty(self.n_sims, dtype=np.float64)
        cs1     = np.empty(self.n_sims, dtype=np.float64)

        scoring = self.scoring
        best_of = self.best_of
        rng     = self.rng

        for i in range(self.n_sims):
            match = simulate_match(p0, p1, best_of=best_of, rng=rng)

            s0 = dk_score(match, 0, scoring)
            s1 = dk_score(match, 1, scoring)

            scores0[i] = s0
            scores1[i] = s1

            w0 = 1.0 if match.winner == 0 else 0.0
            wins0[i] = w0
            wins1[i] = 1.0 - w0

            if match.winner == 0:
                ss0[i] = 1.0 if match.straight_sets else 0.0
                ss1[i] = 0.0
            else:
                ss0[i] = 0.0
                ss1[i] = 1.0 if match.straight_sets else 0.0

            cs0[i] = 1.0 if match.clean_sets[0] > 0 else 0.0
            cs1[i] = 1.0 if match.clean_sets[1] > 0 else 0.0

        r0 = self._build_result(p0.name, scores0, wins0, ss0, cs0)
        r1 = self._build_result(p1.name, scores1, wins1, ss1, cs1)

        logger.info(
            'Sim complete: %s mean=%.1f p_win=%.3f | %s mean=%.1f p_win=%.3f',
            p0.name, r0.mean, r0.p_win,
            p1.name, r1.mean, r1.p_win,
        )
        return r0, r1

    def run_with_calibration(
        self,
        p0: PlayerProfile,
        p1: PlayerProfile,
        elo_blend: float = 0.3,
    ) -> Tuple[SimResult, SimResult]:
        """
        Run simulations with Elo calibration.
        """
        adj_p0, adj_p1 = calibrate_profiles(p0, p1, blend=elo_blend)
        return self.run(adj_p0, adj_p1)
