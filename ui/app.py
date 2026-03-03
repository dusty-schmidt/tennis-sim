import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.db.manager import DatabaseManager
from pipeline.processors.sim.match import simulate_match
from pipeline.processors.sim.profiles import PlayerProfile
from config.settings import config

st.set_page_config(page_title='Tennis Sim Dashboard', layout='wide')
st.title('🎾 Tennis Simulation Dashboard')

db = DatabaseManager(config.DATABASE_PATH)

st.sidebar.header('Controls')
action = st.sidebar.selectbox('App Mode', ['Player Analytics', 'Match Simulator', 'Slate Optimizer', 'Pipeline Status'])

players = [p[0] for p in db.conn.cursor().execute('SELECT DISTINCT player_name FROM player_profiles').fetchall()]

if action == 'Player Analytics':
	st.subheader('Player Stats Explorer')
	selected_player = st.selectbox('Select a Player', players if players else ['No players in DB'])
	if selected_player != 'No players in DB':
		stats = db.get_player_profile(selected_player, 'overall')
		st.json(stats)

elif action == 'Match Simulator':
	st.subheader('Monte Carlo Match Simulation')
	col1, col2 = st.columns(2)
	with col1: p1_name = st.selectbox('Player 1', players, index=0 if len(players)>0 else None)
	with col2: p2_name = st.selectbox('Player 2', players, index=1 if len(players)>1 else 0)
	surface = st.selectbox('Surface', ['hard', 'clay', 'grass', 'indoor'])
	if st.button('Run Simulation'):
		p1_stats = db.get_player_profile(p1_name, surface)
		p2_stats = db.get_player_profile(p2_name, surface)
		p1 = PlayerProfile(p1_name, p1_stats or {})
		p2 = PlayerProfile(p2_name, p2_stats or {})
		res = simulate_match(p1, p2)
		st.success(f'Winner: {p1_name if res.winner == 0 else p2_name}')
		st.write(res)

else:
	st.subheader('Data Pipeline Monitor')
	st.write('Database Location:', config.DATABASE_PATH)
		from pipeline.processors.ownership import project_ownership_simulated; df = project_ownership(df); st.table(df[['player_name', 'salary', 'proj_mean', 'proj_ceil', 'p_win', 'proj_ownership']])
