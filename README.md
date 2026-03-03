# 🎾 Tennis Sim & DFS Optimizer

Professional-grade tennis match simulation and DraftKings lineup optimization engine.

## 🌟 Core Features
- **Monte Carlo Engine**: Simulates tennis matches at the point-by-point level using historical surface stats and Elo calibration.
- **SaberSim Workflow**: Generates range-of-outcome projections (Mean, Floor, Ceiling) via 10k+ simulations per matchup.
- **Market Ownership Simulation**: Projects player ownership by simulating a field of builders using 'Min Uniques' constraints (2-3 players difference).
- **Docker Ready**: Fully containerized API and Streamlit UI for consistent deployment.

## 🚀 Quick Start
- **Setup**: make dev-setup
- **Docker**: make docker-up
- **UI**: Access at http://localhost:8501
- **Tests**: make test

## 🏗️ Architecture
- pipeline/: Data fetchers, processors, and simulation logic.
- ui/: Streamlit frontend dashboard.
- api/: Flask REST endpoints for projection data.
- data/: SQLite storage and raw ATP/Elo CSVs.
