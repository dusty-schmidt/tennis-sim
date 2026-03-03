
# --- Ownership Projection Module ---
import numpy as np

def project_ownership(projections_df):
	"""
	Calculates baseline ownership based on salary-adjusted value and win probability.
	Higher probability and better value = higher ownership.
	"""
	if projections_df.empty or 'value' not in projections_df.columns:
		return projections_df
	
	# Scale values to create a distribution
	vals = projections_df['value'].fillna(0).values
	p_win = projections_df['p_win'].fillna(0.5).values
	
	# Heuristic: Score = (Value scaled) * (Win Prob scaled)
	score = (vals / np.max(vals)) * (p_win / np.max(p_win))
	ownership = (score / np.sum(score)) * 600 # 6 players * 1000tal per lineup
	
	projections_df['proj_ownership'] = np.round(ownership, 2)
	return projections_df
