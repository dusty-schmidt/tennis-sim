import sqlite3
import json
import sys
from pathlib import Path
from typing import Optional, List
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config.settings import BASE_DIR

DEFAULT_DB_PATH = str(BASE_DIR / 'data' / 'tennis_dfs.db')


class DatabaseManager:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.init_db()

    def init_db(self):
        c = self.conn.cursor()

        c.execute("""CREATE TABLE IF NOT EXISTS draftgroups (
            id INTEGER PRIMARY KEY,
            dg_id INTEGER UNIQUE NOT NULL,
            sport TEXT,
            game_type TEXT,
            start_time TEXT,
            contest_count INTEGER DEFAULT 0,
            draft_count INTEGER DEFAULT 0,
            entries_remaining INTEGER DEFAULT 0,
            prize_pool REAL DEFAULT 0,
            min_entry_fee REAL DEFAULT 0,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS draftables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dg_id INTEGER NOT NULL,
            player_id INTEGER,
            player_name TEXT NOT NULL,
            display_name TEXT,
            team_abbrev TEXT,
            position TEXT,
            salary INTEGER,
            avg_ppg REAL DEFAULT 0,
            game_info TEXT,
            status TEXT DEFAULT 'Active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (dg_id) REFERENCES draftgroups (dg_id),
            UNIQUE(dg_id, player_id)
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS sports_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sport_name TEXT NOT NULL,
            sport_id INTEGER,
            region_abbreviation TEXT,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(sport_name)
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS player_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_name TEXT NOT NULL,
            canonical_name TEXT NOT NULL,
            surface TEXT NOT NULL DEFAULT 'overall',
            elo_overall REAL,
            elo_hard REAL,
            elo_clay REAL,
            elo_grass REAL,
            first_serve_pct REAL,
            first_serve_won_pct REAL,
            second_serve_won_pct REAL,
            ace_per_game REAL,
            df_per_game REAL,
            bp_saved_pct REAL,
            return_pts_won_pct REAL,
            sv_games_per_match REAL,
            matches_played INTEGER,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(canonical_name, surface)
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS projections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dg_id INTEGER NOT NULL,
            player_name TEXT NOT NULL,
            canonical_name TEXT,
            salary INTEGER,
            surface TEXT,
            best_of INTEGER DEFAULT 3,
            proj_mean REAL,
            proj_floor REAL,
            proj_ceil REAL,
            proj_std REAL,
            p10 REAL, p25 REAL, p75 REAL, p90 REAL,
            p_win REAL,
            p_straight_sets REAL,
            p_clean_set REAL,
            value REAL,
            sim_count INTEGER DEFAULT 10000,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(dg_id, player_name)
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS lineups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dg_id INTEGER NOT NULL,
            lineup_num INTEGER NOT NULL,
            players TEXT NOT NULL,
            total_salary INTEGER,
            proj_total REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        c.execute("CREATE INDEX IF NOT EXISTS idx_draftables_dg_id ON draftables(dg_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_draftgroups_sport ON draftgroups(sport)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_profiles_canonical ON player_profiles(canonical_name)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_profiles_surface ON player_profiles(surface)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_projections_dg_id ON projections(dg_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_lineups_dg_id ON lineups(dg_id)")
        self.conn.commit()

    # ── DraftGroups ──────────────────────────────────────────────────────────
    def upsert_draftgroup(self, dg_data: dict) -> bool:
        c = self.conn.cursor()
        c.execute("SELECT dg_id FROM draftgroups WHERE dg_id = ?", (dg_data['dg_id'],))
        existing = c.fetchone()
        if existing:
            c.execute("""UPDATE draftgroups SET
                sport=?, game_type=?, start_time=?, contest_count=?,
                draft_count=?, entries_remaining=?, prize_pool=?,
                min_entry_fee=?, description=?, last_updated=?
                WHERE dg_id=?""",
                (dg_data.get('sport'), dg_data.get('game_type'),
                 dg_data.get('start_time'), dg_data.get('contest_count', 0),
                 dg_data.get('draft_count', 0), dg_data.get('entries_remaining', 0),
                 dg_data.get('prize_pool', 0), dg_data.get('min_entry_fee', 0),
                 dg_data.get('description'), datetime.now().isoformat(),
                 dg_data['dg_id']))
            self.conn.commit()
            return False
        else:
            c.execute("""INSERT INTO draftgroups
                (dg_id, sport, game_type, start_time, contest_count,
                 draft_count, entries_remaining, prize_pool, min_entry_fee, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (dg_data['dg_id'], dg_data.get('sport'), dg_data.get('game_type'),
                 dg_data.get('start_time'), dg_data.get('contest_count', 0),
                 dg_data.get('draft_count', 0), dg_data.get('entries_remaining', 0),
                 dg_data.get('prize_pool', 0), dg_data.get('min_entry_fee', 0),
                 dg_data.get('description')))
            self.conn.commit()
            return True

    def get_draftgroup(self, dg_id: int) -> Optional[dict]:
        c = self.conn.cursor()
        c.execute("SELECT * FROM draftgroups WHERE dg_id = ?", (dg_id,))
        row = c.fetchone()
        return dict(row) if row else None

    def get_all_draftgroups(self, sport: str = None) -> List[dict]:
        c = self.conn.cursor()
        if sport:
            c.execute("SELECT * FROM draftgroups WHERE sport = ? ORDER BY start_time DESC", (sport,))
        else:
            c.execute("SELECT * FROM draftgroups ORDER BY start_time DESC")
        return [dict(r) for r in c.fetchall()]

    def get_tennis_slates(self) -> List[dict]:
        c = self.conn.cursor()
        c.execute("SELECT * FROM draftgroups WHERE sport = 'TEN' ORDER BY start_time ASC")
        return [dict(r) for r in c.fetchall()]

    # ── Draftables ───────────────────────────────────────────────────────────
    def upsert_draftable(self, draftable: dict) -> None:
        c = self.conn.cursor()
        c.execute("""INSERT OR REPLACE INTO draftables
            (dg_id, player_id, player_name, display_name, team_abbrev,
             position, salary, avg_ppg, game_info, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (draftable['dg_id'], draftable.get('player_id'),
             draftable['player_name'], draftable.get('display_name'),
             draftable.get('team_abbrev'), draftable.get('position'),
             draftable.get('salary'), draftable.get('avg_ppg', 0),
             draftable.get('game_info'), draftable.get('status', 'Active')))
        self.conn.commit()

    def get_draftables(self, dg_id: int) -> List[dict]:
        c = self.conn.cursor()
        c.execute("SELECT * FROM draftables WHERE dg_id = ? ORDER BY salary DESC", (dg_id,))
        return [dict(r) for r in c.fetchall()]

    def draftgroup_has_draftables(self, dg_id: int) -> bool:
        c = self.conn.cursor()
        c.execute("SELECT COUNT(*) FROM draftables WHERE dg_id = ?", (dg_id,))
        return c.fetchone()[0] > 0

    # ── Sports Inventory ─────────────────────────────────────────────────────
    def update_sports_inventory(self, sports_list: list = None) -> None:
        if not sports_list:
            return
        c = self.conn.cursor()
        for sport in sports_list:
            c.execute("""INSERT OR REPLACE INTO sports_inventory
                (sport_name, sport_id, region_abbreviation, last_seen)
                VALUES (?, ?, ?, ?)""",
                (sport.get('sportName', sport.get('name', str(sport))),
                 sport.get('sportId'), sport.get('regionAbbreviation'),
                 datetime.now().isoformat()))
        self.conn.commit()

    def get_sports_inventory(self) -> List[dict]:
        c = self.conn.cursor()
        c.execute("SELECT * FROM sports_inventory ORDER BY sport_name")
        return [dict(r) for r in c.fetchall()]

    # ── Player Profiles ──────────────────────────────────────────────────────
    def upsert_player_profile(self, canonical_name: str, surface: str, stats_dict: dict) -> None:
        c = self.conn.cursor()
        c.execute("""INSERT INTO player_profiles
            (player_name, canonical_name, surface,
             first_serve_pct, first_serve_won_pct, second_serve_won_pct,
             ace_per_game, df_per_game, bp_saved_pct, return_pts_won_pct,
             sv_games_per_match, matches_played, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(canonical_name, surface) DO UPDATE SET
             first_serve_pct=excluded.first_serve_pct,
             first_serve_won_pct=excluded.first_serve_won_pct,
             second_serve_won_pct=excluded.second_serve_won_pct,
             ace_per_game=excluded.ace_per_game,
             df_per_game=excluded.df_per_game,
             bp_saved_pct=excluded.bp_saved_pct,
             return_pts_won_pct=excluded.return_pts_won_pct,
             sv_games_per_match=excluded.sv_games_per_match,
             matches_played=excluded.matches_played,
             last_updated=excluded.last_updated""",
            (canonical_name, canonical_name, surface,
             stats_dict.get('1stServe_pct'), stats_dict.get('1stServeWon_pct'),
             stats_dict.get('2ndServeWon_pct'), stats_dict.get('ace_per_game'),
             stats_dict.get('df_per_game'), stats_dict.get('bp_saved_pct'),
             stats_dict.get('return_pts_won_pct'), stats_dict.get('sv_games_per_match'),
             stats_dict.get('matches_played'), datetime.now().isoformat()))
        self.conn.commit()

    def get_player_profile(self, canonical_name: str, surface: str = 'overall') -> Optional[dict]:
        c = self.conn.cursor()
        c.execute("SELECT * FROM player_profiles WHERE canonical_name = ? AND surface = ?",
                  (canonical_name, surface))
        row = c.fetchone()
        return dict(row) if row else None

    def get_all_player_profiles(self) -> List[dict]:
        c = self.conn.cursor()
        c.execute("SELECT * FROM player_profiles ORDER BY canonical_name, surface")
        return [dict(r) for r in c.fetchall()]

    # ── Projections ──────────────────────────────────────────────────────────
    def upsert_projection(self, dg_id: int, player_name: str, proj_dict: dict) -> None:
        c = self.conn.cursor()
        c.execute("""INSERT INTO projections
            (dg_id, player_name, canonical_name, salary, surface, best_of,
             proj_mean, proj_floor, proj_ceil, proj_std,
             p10, p25, p75, p90, p_win, p_straight_sets, p_clean_set,
             value, sim_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(dg_id, player_name) DO UPDATE SET
             canonical_name=excluded.canonical_name,
             salary=excluded.salary, surface=excluded.surface,
             best_of=excluded.best_of, proj_mean=excluded.proj_mean,
             proj_floor=excluded.proj_floor, proj_ceil=excluded.proj_ceil,
             proj_std=excluded.proj_std, p10=excluded.p10, p25=excluded.p25,
             p75=excluded.p75, p90=excluded.p90, p_win=excluded.p_win,
             p_straight_sets=excluded.p_straight_sets,
             p_clean_set=excluded.p_clean_set, value=excluded.value,
             sim_count=excluded.sim_count""",
            (dg_id, player_name,
             proj_dict.get('canonical_name'), proj_dict.get('salary'),
             proj_dict.get('surface'), proj_dict.get('best_of', 3),
             proj_dict.get('proj_mean'), proj_dict.get('proj_floor'),
             proj_dict.get('proj_ceil'), proj_dict.get('proj_std'),
             proj_dict.get('p10'), proj_dict.get('p25'),
             proj_dict.get('p75'), proj_dict.get('p90'),
             proj_dict.get('p_win'), proj_dict.get('p_straight_sets'),
             proj_dict.get('p_clean_set'), proj_dict.get('value'),
             proj_dict.get('sim_count', 10000)))
        self.conn.commit()

    def get_projections(self, dg_id: int) -> List[dict]:
        c = self.conn.cursor()
        c.execute("SELECT * FROM projections WHERE dg_id = ? ORDER BY proj_mean DESC", (dg_id,))
        return [dict(r) for r in c.fetchall()]

    def clear_projections(self, dg_id: int) -> None:
        c = self.conn.cursor()
        c.execute("DELETE FROM projections WHERE dg_id = ?", (dg_id,))
        self.conn.commit()

    # ── Lineups ──────────────────────────────────────────────────────────────
    def save_lineup(self, dg_id: int, lineup_num: int, players: list,
                    total_salary: int, proj_total: float) -> None:
        c = self.conn.cursor()
        c.execute("""INSERT INTO lineups
            (dg_id, lineup_num, players, total_salary, proj_total)
            VALUES (?, ?, ?, ?, ?)""",
            (dg_id, lineup_num, json.dumps(players), total_salary, proj_total))
        self.conn.commit()

    def get_lineups(self, dg_id: int) -> List[dict]:
        c = self.conn.cursor()
        c.execute("SELECT * FROM lineups WHERE dg_id = ? ORDER BY lineup_num ASC", (dg_id,))
        rows = [dict(r) for r in c.fetchall()]
        for row in rows:
            try:
                row['players'] = json.loads(row['players'])
            except Exception:
                pass
        return rows

    def close(self):
        if self.conn:
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
