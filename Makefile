dev-setup:
	pip install -r requirements.txt

run-pipeline:
	python pipeline/pipeline_runner.py --year 2024

run-api:
	python api/server.py

test:
	python3 -m unittest discover tests

test-sim:
	python3 -c "import sys; sys.path.insert(0, '.'); from pipeline.processors.sim.match import simulate_match; from pipeline.db.manager import DatabaseManager; from pipeline.processors.sim.profiles import PlayerProfile; db=DatabaseManager('data/tennis_dfs.db'); p1=PlayerProfile('Grigor Dimitrov', db.get_player_profile('Grigor Dimitrov', 'hard')); p2=PlayerProfile('Novak Djokovic', db.get_player_profile('Novak Djokovic', 'hard')); print(simulate_match(p1, p2))"

docker-build:
	docker-compose build

docker-up:
	docker-compose up -d

run-ui:
	streamlit run ui/app.py
