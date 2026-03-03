
# --- Builder Simulation Module (Uniques) ---
import numpy as np
import pandas as pd
import random

def simulate_market_ownership(projections_df, n_lineups=250, min_uniques=3, randomness=0.3):
	"""
	Simulates a market by building N lineups with a uniqueness constraint.
	- randomness: adds noise to projections to simulate different builder perspectives.
	- min_uniques: ensures lineups aren't too similar.
	"""
	if projections_df.empty: return projections_df
	
	pool = projections_df[projections_df['salary'] > 0].copy()
	lineups = []
	player_counts = {name: 0 for name in pool['player_name']}
	
	for _ in range(n_lineups):
		# Create a 'skewed' projection set for this specific builder
		# (proj * random factor between 1-randomness and 1+randomness)
		temp_df = pool.copy()
		temp_df['sim_score'] = temp_df['proj_mean'] * (1 + np.random.uniform(-randomness, randomness, len(temp_df)))
		temp_df = temp_df.sort_values('sim_score', ascending=False)
		
		# Build a lineup with basic greedy logic but checking uniqueness
		for _retry in range(10): # retry sample variations
			current_lu = []
			current_salary = 0
			# Sample from top 12 instead of just pure greedy
			for _, p in temp_df.head(12).sample(frac=1).iterrows():
				if len(current_lu) < 6 and current_salary + p['salary'] <= 50000:
					current_lu.append(p['player_name'])
					current_salary += p['salary']
			
			if len(current_lu) == 6:
				# Check uniqueness against all previous lineups
				is_valid = True
				for existing in lineups:
					matches = len(set(current_lu) & set(existing))
					if (6 - matches) < min_uniques:
						is_valid = False
						break
				
				if is_valid:
					lineups.append(current_lu)
					for p_name in current_lu:
						player_counts[p_name] += 1
					break
	
	# Ownership is frequency in result pool
	actual_n = len(lineups) if len(lineups) > 0 else 1
	projections_df['proj_ownership'] = projections_df['player_name'].map(lambda x: round((player_counts[x] / actual_n) * 100, 1))
	return projections_df
