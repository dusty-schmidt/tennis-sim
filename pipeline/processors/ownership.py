
# --- Advanced Ownership Simulation Module ---
import numpy as np
import pandas as pd
import random

def build_lineup_with_uniques(players_df, existing_lineups, min_uniques=3, salary_cap=50000, roster_size=6):
	"""
	Attempts to build a single lineup that has at least min_uniques difference from existing ones.
	Uses a weighted random selection based on proj_mean to introduce variance.
	"""
	# Filter players with salary
	players_df = players_df[players_df['salary'] > 0].copy()
	
	for _ in range(50): # Try 50 times to find a unique lineup
		selected = []
		curr_salary = 0
		
		# Weighted random sampling
		weights = players_df['proj_mean'] ** 2 # Prefer higher point totals
		candidates = players_df.sample(n=roster_size*2, weights=weights, replace=False)
		
		for _, p in candidates.iterrows():
			if len(selected) < roster_size and curr_salary + p['salary'] <= salary_cap:
				selected.append(p['player_name'])
				curr_salary += p['salary']
		
		if len(selected) == roster_size:
			is_unique = True
			for old in existing_lineups:
				intersection = set(selected) & set(old)
				if len(selected) - len(intersection) < min_uniques:
					is_unique = False
					break
			if is_unique:
				return selected
	return None

def project_ownership_simulated(projections_df, n_lineups=100, min_uniques=3):
	"""
	Simulates a builder creating n_lineups to see actual player frequency (ownership).
	"""
	lineups = []
	counts = {name: 0 for name in projections_df['player_name']}
	
	for _ in range(n_lineups):
		lu = build_lineup_with_uniques(projections_df, lineups, min_uniques=min_uniques)
		if lu:
			lineups.append(lu)
			for p in lu: counts[p] += 1
	
	# Ownership = 0f lineups player appears in
	projections_df['proj_ownership'] = projections_df['player_name'].map(lambda x: round((counts[x]/max(1, len(lineups))) * 100, 2))
	return projections_df
