dev-setup:
	pip install -r requirements.txt

run-pipeline:
	docker-compose exec ui python pipeline/pipeline_runner.py --year 2024

run-api:
	python api/server.py

test:
	python3 -m unittest discover tests

test-sim:
	python3 -m unittest tests/test_simulation.py

docker-build:
	docker-compose build

docker-up:
	docker-compose up -d
