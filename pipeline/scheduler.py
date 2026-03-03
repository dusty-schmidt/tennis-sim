
import time
import threading
import logging
from pipeline.fetchers.dk_live import fetch_tennis_only
from pipeline.processors.projector import project_slate
from pipeline.db.manager import DatabaseManager
from config.settings import config

logger = logging.getLogger(__name__)

class PipelineScheduler:
	def __init__(self):
		self.running = False
		self.db = DatabaseManager(config.DATABASE_PATH)

	def start(self):
		if not self.running:
			self.running = True
			threading.Thread(target=self._main_loop, daemon=True).start()
			logger.info('Background Pipeline Scheduler Started')

	def _main_loop(self):
		while self.running:
			try:
				# Step 1: Check for new slates
				logger.info('Polling DraftKings for new pools...')
				dk_res = fetch_tennis_only()
				
				# Step 2: Identify un-simulated slates
				dgs = self.db.get_tennis_slates()
				for dg in dgs:
					dg_id = dg.get('dg_id')
					projs = self.db.get_projections(dg_id)
					
					if not projs:
						logger.info(f'New slate detected (dg_id={dg_id}). Starting auto-simulation...')
						project_slate(dg_id, n_sims=5000, db=self.db)
						logger.info(f'Auto-simulation complete for dg_id={dg_id}')
				
			except Exception as e:
				logger.error(f'Pipeline loop error: {e}')
			
			time.sleep(600) # Poll every 10 minutes

	def run_now(self):
		# Manual trigger via API
		threading.Thread(target=self._main_loop_once, daemon=True).start()

	def _main_loop_once(self):
		# logic to run exactly once for 'Run Now' button
		pass

pool_scheduler = PipelineScheduler()
