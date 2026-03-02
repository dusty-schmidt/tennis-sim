import logging
import logging.handlers
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.settings import PROJECT_ROOT

BASE_DIR = PROJECT_ROOT


class ApplicationLogger:
    _instance = None
    _loggers = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ApplicationLogger, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._setup_logging()

    def _setup_logging(self):
        log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
        log_dir = os.getenv('LOG_DIR', str(BASE_DIR / 'logs'))

        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        log_format = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(log_format)

        log_file = os.path.join(
            log_dir,
            f"tennis_dfs_{datetime.now().strftime('%Y%m%d')}.log"
        )
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=10485760, backupCount=5
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(log_format)

        if not root_logger.handlers:
            root_logger.addHandler(console_handler)
            root_logger.addHandler(file_handler)

    @staticmethod
    def get_logger(name):
        logger = logging.getLogger(name)
        if name not in ApplicationLogger._loggers:
            ApplicationLogger._loggers[name] = logger
        return logger


def setup_logging():
    ApplicationLogger()


def get_logger(name):
    return ApplicationLogger.get_logger(name)
