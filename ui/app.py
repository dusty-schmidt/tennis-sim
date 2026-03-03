import streamlit as st
import sys
import plotly.express as px
import pandas as pd
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

if action == 'Match Simulator':
	st.subheader('Monte Carlo Outcome Distribution')
	col1, col2 = st.columns(2)
	with col1: p1_name = st.selectbox('Player 1', players, index=0 if len(players)>0 else None)
	with col2: p2_name = st.selectbox('Player 2', players, index=1 if len(players)>1 else 0)
	n_sims = st.slider('Number of Simulations', 100, 10000, 1000)
	
	if st.button('Run High-Fidelity Simulation'):
		p1_stats = db.get_player_profile(p1_name, 'hard')
		p2_stats = db.get_player_profile(p2_name, 'hard')
		p1 = PlayerProfile(p1_name, p1_stats or {})
		p2 = PlayerProfile(p2_name, p2_stats or {})
		
		scores_p1 = []
		for _ in range(n_sims):
			res = simulate_match(p1, p2)
			# We calculate a mock DK score based on games won/lost and winner bonus
			# In a real run we use the scoring.py but for bench we simulate simple version
			p1_score = res.games_won[0] * 2.5 - res.games_lost[0] * 2.0 + (30 if res.winner == 0 else 0) + (6 if res.winner == 0 else 0)
			scores_p1.append(p1_score)
		
		df_scores = pd.DataFrame({'DK Points': scores_p1})
		fig = px.histogram(df_scores, x='DK Points', nbins=50, title=f'{p1_name} Outcome Range vs {p2_name}', color_discrete_sequence=['#00CC96'])
		fig.add_vline(x=df_scores['DK Points'].mean(), line_dash='dash', line_color='red', annotation_text='Average')
		st.plotly_chart(fig, use_container_width=True)
		st.info('Observe the bi-modal distribution: The "Average" is actually one of the least likely outcomes.')

else:
	st.write('Select Match Simulator to see distribution charts.')
