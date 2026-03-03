import logging

logger = logging.getLogger(__name__)

class StubScheduler:
	def __init__(self):
		self.is_running = False

	def start(self):
		self.is_running = True
		logger.info('Stub scheduler started')

	def run_now(self):
		logger.info('Manual ingestion triggered (stub - no action taken)')

pool_scheduler = StubScheduler()
