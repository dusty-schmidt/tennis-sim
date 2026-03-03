
# --- Optimizer Module ---
import pandas as pd

def build_optimal_lineup(projections_df, salary_cap=50000, roster_size=6):
	"""
	Simple knapsack-style optimizer for DraftKings Tennis.
	Filters out players without salaries and picks the top 6 by proj_mean within cap.
	"""
	df = projections_df[projections_df['salary'] > 0].sort_values('proj_mean', ascending=False)
	lineup = []
	total_salary = 0
	for _, player in df.iterrows():
		if total_salary + player['salary'] <= salary_cap and len(lineup) < roster_size:
			lineup.append(player)
			total_salary += player['salary']
	return pd.DataFrame(lineup), total_salary
