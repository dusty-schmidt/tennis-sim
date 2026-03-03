import unittest
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.db.manager import DatabaseManager
from config.settings import config

class TestDatabase(unittest.TestCase):
	def setUp(self):
		self.db = DatabaseManager(config.DATABASE_PATH)

	def test_db_connection(self):
		self.assertTrue(os.path.exists(config.DATABASE_PATH))

	def test_tables_exist(self):
		cursor = self.db.conn.cursor()
		cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
		tables = [r[0] for r in cursor.fetchall()]
		self.assertIn('player_profiles', tables)

if __name__ == '__main__':
	unittest.main()
