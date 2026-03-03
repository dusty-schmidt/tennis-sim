import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.processors.sim.match import simulate_match
from pipeline.processors.sim.profiles import PlayerProfile
from pipeline.db.manager import DatabaseManager
from config.settings import config

class TestSimulationCore(unittest.TestCase):
	def setUp(self):
		self.db = DatabaseManager(config.DATABASE_PATH)

	def test_real_player_sim(self):
		# Load real stats from DB to ensure schema alignment
		p1_stats = self.db.get_player_profile('Grigor Dimitrov', 'hard') or {}
		p2_stats = self.db.get_player_profile('Novak Djokovic', 'hard') or {}
		p1 = PlayerProfile('Grigor Dimitrov', p1_stats)
		p2 = PlayerProfile('Novak Djokovic', p2_stats)
		
		# simulate_match is positional only or keyword based without 'surface'
		result = simulate_match(p1, p2)
		self.assertIsNotNone(result)
		self.assertTrue(hasattr(result, 'winner'))

	def test_dk_points_present(self):
		p1 = PlayerProfile('A', {'sv_win_pct': 0.7})
		p2 = PlayerProfile('B', {'sv_win_pct': 0.7})
		res = simulate_match(p1, p2)
		# Verify result object has necessary fields for DK processing
		self.assertTrue(hasattr(res, 'total_aces'))
		self.assertTrue(hasattr(res, 'straight_sets'))

if __name__ == '__main__':
	unittest.main()
