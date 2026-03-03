import streamlit as st
import sys
import os
import pandas as pd
import plotly.express as px
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.db.manager import DatabaseManager
from pipeline.processors.sim.match import simulate_match
from pipeline.processors.sim.profiles import PlayerProfile
from pipeline.processors.projector import project_dummy_slate
from pipeline.processors.ownership import simulate_uniques_ownership
from config.settings import config

st.set_page_config(page_title='Tennis Sim Dashboard', layout='wide')

def get_last_logs(n=30):
    log_dir = Path(config.LOG_DIR)
    log_files = sorted(log_dir.glob('*.log'))
    if not log_files: return "No logs found."
    with open(log_files[-1], 'r') as f:
        return "".join(f.readlines()[-n:])

db = DatabaseManager(config.DATABASE_PATH)

st.sidebar.header('Navigation')
action = st.sidebar.selectbox('App Mode', ['Slate Optimizer', 'Match Simulator', 'Player Analytics', 'System Insights'])

if action == 'System Insights':
    st.subheader('🖥️ System Health & Pipeline Insights')
    col1, col2, col3 = st.columns(3)
    with col1: st.metric('Database Info', f"{os.path.getsize(config.DATABASE_PATH)/1024/1024:.2f} MB")
    with col2: st.metric('Total Players', db.conn.cursor().execute('SELECT COUNT(*) FROM player_profiles').fetchone()[0])
    with col3: st.metric('DK Slates Tracked', len(db.get_tennis_slates()))
    
    st.divider()
    st.subheader('📋 Background Pipeline Logs (Live)')
    st.code(get_last_logs())

elif action == 'Slate Optimizer':
    st.subheader('🎯 SaberSim-Style Slate Optimizer')
    if st.button('Generate / Refresh Projections'):
        matchups = [('Jannik Sinner', 'Daniil Medvedev'), ('Carlos Alcaraz', 'Alexander Zverev')]
        salaries = {'Jannik Sinner': 10000, 'Daniil Medvedev': 7600, 'Carlos Alcaraz': 9800, 'Alexander Zverev': 7800}
        df = project_dummy_slate(matchups, surface='hard', salaries=salaries, n_sims=1000)
        df = simulate_uniques_ownership(df, n_lineups=300, min_uniques=3)
        st.table(df[['player_name', 'salary', 'proj_mean', 'proj_ceil', 'p_win', 'proj_ownership']])

elif action == 'Match Simulator':
    st.subheader('📊 Bi-Modal Outcome Simulator')
    players = [p[0] for p in db.conn.cursor().execute('SELECT DISTINCT player_name FROM player_profiles').fetchall()]
    p1_name = st.selectbox('Player 1', players)
    p2_name = st.selectbox('Player 2', players, index=1 if len(players)>1 else 0)
    if st.button('Run 1000 Sims'):
        p1_stats = db.get_player_profile(p1_name, 'hard')
        p2_stats = db.get_player_profile(p2_name, 'hard')
        scores = []
        for _ in range(1000):
            res = simulate_match(PlayerProfile(p1_name, p1_stats or {}), PlayerProfile(p2_name, p2_stats or {}))
            scores.append((res.games_won[0]*2.5) + (30 if res.winner==0 else 0))
        fig = px.histogram(pd.DataFrame({'Points': scores}), x='Points', nbins=30, title=f'{p1_name} Distribution')
        st.plotly_chart(fig, use_container_width=True)

elif action == 'Player Analytics':
    st.subheader('🎾 Player Profile Explorer')
    players = [p[0] for p in db.conn.cursor().execute('SELECT DISTINCT player_name FROM player_profiles').fetchall()]
    sel = st.selectbox('Select Player', players)
    st.json(db.get_player_profile(sel, 'overall'))
