import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import DK_SCORING

class TestScoring(unittest.TestCase):
	def test_scoring_structure(self):
		self.assertIn('best_of_3', DK_SCORING)
		self.assertIn('best_of_5', DK_SCORING)
		
	def test_specific_values(self):
		# Verify match_played flat bonus matches DraftKings rules
		self.assertEqual(DK_SCORING['best_of_3']['match_played'], 30.0)

if __name__ == '__main__':
	unittest.main()
