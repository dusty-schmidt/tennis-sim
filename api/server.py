import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, jsonify, request
from pipeline.db.manager import DatabaseManager
from pipeline.scheduler import pool_scheduler
from pipeline.core.logger import get_logger, setup_logging
from config.settings import config

setup_logging()
logger = get_logger(__name__)

app = Flask(__name__)
db = DatabaseManager(db_path=config.DATABASE_PATH)


# ── Health & Status ──────────────────────────────────────────────────────────
@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()}), 200


@app.route('/api/status', methods=['GET'])
def status():
    try:
        slates = db.get_tennis_slates()
        profiles = db.get_all_player_profiles()
        sports = db.get_sports_inventory()
        return jsonify({
            'status': 'ok',
            'tennis_slates': len(slates),
            'player_profiles': len(profiles),
            'sports_tracked': len(sports),
            'scheduler_running': pool_scheduler.is_running,
            'scheduler_interval_hours': config.SCHEDULER_INTERVAL_HOURS,
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── DraftGroups ──────────────────────────────────────────────────────────────
@app.route('/api/draftgroups', methods=['GET'])
def get_draftgroups():
    try:
        sport = request.args.get('sport')
        dgs = db.get_all_draftgroups(sport=sport)
        return jsonify({'count': len(dgs), 'draftgroups': dgs}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/draftgroups/<int:dg_id>', methods=['GET'])
def get_draftgroup(dg_id):
    try:
        dg = db.get_draftgroup(dg_id)
        if not dg:
            return jsonify({'error': f'draftgroup {dg_id} not found'}), 404
        return jsonify(dg), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/draftgroups/<int:dg_id>/draftables', methods=['GET'])
def get_draftables(dg_id):
    try:
        players = db.get_draftables(dg_id)
        return jsonify({'dg_id': dg_id, 'count': len(players), 'draftables': players}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Sports Inventory ─────────────────────────────────────────────────────────
@app.route('/api/sports', methods=['GET'])
def get_sports():
    try:
        sports = db.get_sports_inventory()
        return jsonify({'count': len(sports), 'sports': sports}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Scheduler Control ────────────────────────────────────────────────────────
@app.route('/api/scheduler/status', methods=['GET'])
def scheduler_status():
    return jsonify({
        'enabled': config.SCHEDULER_ENABLED,
        'running': pool_scheduler.is_running,
        'interval_hours': config.SCHEDULER_INTERVAL_HOURS,
    }), 200


@app.route('/api/scheduler/trigger', methods=['POST'])
def trigger_ingestion():
    try:
        import threading
        t = threading.Thread(target=pool_scheduler.run_now, daemon=True)
        t.start()
        return jsonify({'status': 'triggered', 'message': 'Ingestion started in background'}), 202
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── Tennis Endpoints ─────────────────────────────────────────────────────────
@app.route('/api/tennis/slates', methods=['GET'])
def get_tennis_slates():
    try:
        slates = db.get_tennis_slates()
        return jsonify({'count': len(slates), 'slates': slates}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tennis/slates/<int:dg_id>/projections', methods=['GET'])
def get_tennis_projections(dg_id):
    try:
        projections = db.get_projections(dg_id)
        return jsonify({'dg_id': dg_id, 'count': len(projections), 'projections': projections}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tennis/slates/<int:dg_id>/simulate', methods=['POST'])
def simulate_tennis_slate(dg_id):
    return jsonify({
        'status': 'not_implemented',
        'message': 'Simulation engine not yet built',
        'dg_id': dg_id,
    }), 501


@app.route('/api/tennis/slates/<int:dg_id>/lineups', methods=['GET'])
def get_tennis_lineups(dg_id):
    try:
        lineups = db.get_lineups(dg_id)
        return jsonify({'dg_id': dg_id, 'count': len(lineups), 'lineups': lineups}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tennis/players/<path:name>/profile', methods=['GET'])
def get_tennis_player_profile(name):
    try:
        surface = request.args.get('surface', 'overall')
        profile = db.get_player_profile(name, surface)
        if not profile:
            return jsonify({'error': f'No profile found for {name} on {surface}'}), 404
        return jsonify(profile), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def create_app():
    if config.SCHEDULER_ENABLED:
        pool_scheduler.start()
    return app


if __name__ == '__main__':
    application = create_app()
    logger.info(f"Starting API on {config.API_HOST}:{config.API_PORT}")
    application.run(
        host=config.API_HOST,
        port=config.API_PORT,
        debug=config.API_DEBUG,
    )
