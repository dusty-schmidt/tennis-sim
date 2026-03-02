from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR     = PROJECT_ROOT / 'data'
RAW_DIR      = DATA_DIR / 'raw'
PROCESSED_DIR = DATA_DIR / 'processed'
CACHE_DIR    = DATA_DIR / 'cache'

# Ensure dirs exist
for _d in [RAW_DIR, PROCESSED_DIR, CACHE_DIR,
           RAW_DIR / 'atp', RAW_DIR / 'tennis_abstract', RAW_DIR / 'dk_slates']:
    _d.mkdir(parents=True, exist_ok=True)

# ── Official DraftKings Tennis Scoring ──────────────────────────────────────
# Source: DraftKings scoring rules (verified 2024)
#
# best_of_3: standard ATP/WTA non-Grand-Slam
# best_of_5: Grand Slams
DK_SCORING = {
    'best_of_3': {
        'match_played':    30.0,   # flat bonus every player who plays
        'game_won':         2.5,   # every game won (serve or return)
        'game_lost':       -2.0,   # every game lost
        'set_won':          6.0,
        'set_lost':        -3.0,
        'match_won':        6.0,
        'ace':              0.4,
        'double_fault':    -1.0,
        'break':            0.75,  # win opponent's service game
        'clean_set':        4.0,   # win a set 6-0
        'straight_sets':    6.0,   # win without losing a set
        'no_double_fault':  2.5,   # 0 DFs in entire match
        'ace_bonus':        2.0,   # 10+ aces in match (3-set)
    },
    'best_of_5': {
        'match_played':    30.0,
        'game_won':         2.0,
        'game_lost':       -1.6,
        'set_won':          5.0,
        'set_lost':        -2.5,
        'match_won':        5.0,
        'ace':              0.25,
        'double_fault':    -1.0,
        'break':            0.5,
        'clean_set':        2.5,
        'straight_sets':    5.0,
        'no_double_fault':  5.0,
        'ace_bonus':        2.0,   # 15+ aces in match (5-set)
    },
}

# Legacy aliases — kept for any external code that still imports these names
DK_SCORING_3SET = DK_SCORING['best_of_3']
DK_SCORING_5SET = DK_SCORING['best_of_5']

SURFACES = ['hard', 'clay', 'grass', 'indoor']

GRAND_SLAMS = [
    'Australian Open', 'Roland Garros', 'Wimbledon', 'US Open'
]

MIN_MATCHES = {
    'surface_stats': 10,
    'bp_saved': 10,
    'elo': 20,
    'serve': 5,
}

SACKMANN_BASE_URL = 'https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master'
TENNIS_ABSTRACT_ELO_URL = 'http://www.tennisabstract.com/reports/atp_elo_ratings.html'

# ── DK Pipeline Configuration ─────────────────────────────────────────────────
import os
from dotenv import load_dotenv
load_dotenv()

BASE_DIR = PROJECT_ROOT

class Config:
    """Base configuration"""
    DEBUG_MODE = os.getenv("DEBUG_MODE", "False") == "True"
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_DIR = os.getenv("LOG_DIR", str(BASE_DIR / "logs"))

    SCHEDULER_ENABLED = os.getenv("SCHEDULER_ENABLED", "True") == "True"
    SCHEDULER_INTERVAL_HOURS = int(os.getenv("SCHEDULER_INTERVAL_HOURS", "2"))

    DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "tennis_dfs.db"))

    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", "5000"))
    API_DEBUG = os.getenv("API_DEBUG", "False") == "True"

    DRAFTKINGS_SPORTS_ENDPOINT = "https://api.draftkings.com/sites/US-DK/sports/v1/sports?format=json"
    DRAFTKINGS_CONTESTS_ENDPOINT = "https://www.draftkings.com/lobby/getcontests?sport={sport}"
    DRAFTKINGS_DRAFTABLES_ENDPOINT = "https://api.draftkings.com/draftgroups/v1/draftgroups/{draftgroup_id}/draftables"

    VALID_GAME_TYPES = ["Classic", "Showdown Captain Mode"]
    TENNIS_VALID_GAME_TYPES = ["Classic", "Showdown Captain Mode", "Single Game"]

    REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "10"))
    REQUEST_RETRY_COUNT = int(os.getenv("REQUEST_RETRY_COUNT", "3"))
    REQUEST_DELAY = float(os.getenv("REQUEST_DELAY", "0.5"))

    SAVE_JSON_BACKUPS = os.getenv("SAVE_JSON_BACKUPS", "False") == "True"
    JSON_BACKUP_DIR = os.getenv("JSON_BACKUP_DIR", str(BASE_DIR / "data" / "draftables"))

    @classmethod
    def validate(cls):
        errors = []
        if cls.SCHEDULER_INTERVAL_HOURS <= 0:
            errors.append("SCHEDULER_INTERVAL_HOURS must be > 0")
        if cls.API_PORT < 1 or cls.API_PORT > 65535:
            errors.append("API_PORT must be 1-65535")
        if cls.REQUEST_TIMEOUT <= 0:
            errors.append("REQUEST_TIMEOUT must be > 0")
        return errors


class DevelopmentConfig(Config):
    DEBUG_MODE = True
    LOG_LEVEL = "DEBUG"
    API_DEBUG = True


class ProductionConfig(Config):
    DEBUG_MODE = False
    LOG_LEVEL = "WARNING"
    API_DEBUG = False
    SCHEDULER_ENABLED = True


class TestingConfig(Config):
    DEBUG_MODE = True
    LOG_LEVEL = "DEBUG"
    DATABASE_PATH = ":memory:"
    SCHEDULER_ENABLED = False


def get_config(env=None):
    if env is None:
        env = os.getenv("ENVIRONMENT", "development").lower()
    return {
        "development": DevelopmentConfig,
        "production": ProductionConfig,
        "testing": TestingConfig,
    }.get(env, DevelopmentConfig)


config = get_config()


if __name__ == '__main__':
    print("PROJECT_ROOT:", PROJECT_ROOT)
    print("\nDK_SCORING[best_of_3]:")
    for k, v in DK_SCORING['best_of_3'].items():
        print(f"  {k}: {v}")
    print("\nDK_SCORING[best_of_5]:")
    for k, v in DK_SCORING['best_of_5'].items():
        print(f"  {k}: {v}")
