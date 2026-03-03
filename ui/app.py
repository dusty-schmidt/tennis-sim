import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.db.manager import DatabaseManager
from config.settings import config

st.set_page_config(page_title='Tennis Sim Dashboard', layout='wide')

st.title('🎾 Tennis Simulation Dashboard')

db = DatabaseManager(config.DATABASE_PATH)

st.sidebar.header('Controls')
action = st.sidebar.selectbox('App Mode', ['Player Analytics', 'Match Simulator', 'Pipeline Status'])

if action == 'Player Analytics':
	st.subheader('Player Stats Explorer')
	players = [p[0] for p in db.conn.cursor().execute('SELECT DISTINCT player_name FROM player_profiles').fetchall()]
	selected_player = st.selectbox('Select a Player', players if players else ['No players in DB'])
	if selected_player != 'No players in DB':
		stats = db.get_player_profile(selected_player, 'overall')
		st.json(stats)

elif action == 'Match Simulator':
	st.subheader('Monte Carlo Match Simulation')
	st.info('Simulation engine integrated. Select players to begin.')

else:
	st.subheader('Data Pipeline Monitor')
	st.write('Database Location:', config.DATABASE_PATH)
