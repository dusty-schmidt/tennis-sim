
# --- Advanced Market Simulation (Min Uniques) ---
import numpy as np
import pandas as pd
import random

def simulate_uniques_ownership(projections_df, n_lineups=300, min_uniques=3):
	"""
	Simulates how many builders operate using a 'Min Uniques' constraint.
	- n_lineups: Total lineups in the simulated contest pool.
	- min_uniques: Minimum players that must be different between any two lineups.
	"""
	if projections_df.empty: return projections_df
	
	pool = projections_df[projections_df['salary'] > 0].copy()
	# Create a probability distribution based on proj_mean to act as the 'meta' bias
	pool['meta_bias'] = np.exp(pool['proj_mean'] / pool['proj_mean'].max() * 5)
	pool['meta_bias'] /= pool['meta_bias'].sum()
	
	lineups = []
	player_counts = {name: 0 for name in pool['player_name']}
	
	k = 0
	max_attempts = n_lineups * 20
	attempt = 0
	
	while len(lineups) < n_lineups and attempt < max_attempts:
		attempt += 1
		# Sample a candidate lineup based on meta bias
		candidate_indices = np.random.choice(pool.index, size=10, p=pool['meta_bias'], replace=False)
		candidate_df = pool.loc[candidate_indices]
		
		current_lu = []
		current_sal = 0
		for _, p in candidate_df.iterrows():
			if len(current_lu) < 6 and current_sal + p['salary'] <= 50000:
				current_lu.append(p['player_name'])
				current_sal += p['salary']
		
		if len(current_lu) == 6:
			# Enforce Uniques Constraint
			is_unique_enough = True
			for existing in lineups:
				common_players = len(set(current_lu) & set(existing))
				if (6 - common_players) < min_uniques:
					is_unique_enough = False
					break
			
			if is_unique_enough:
				lineups.append(current_lu)
				for p_name in current_lu:
					player_counts[p_name] += 1
	
	actual_pool_size = len(lineups) if len(lineups) > 0 else 1
	projections_df['proj_ownership'] = projections_df['player_name'].map(
		lambda x: round((player_counts.get(x, 0) / actual_pool_size) * 100, 1)
	)
	return projections_df
