#!/usr/bin/env bash
# Launch the Rubin Anomaly Hunter dashboard on macOS/Linux/WSL.
set -e
cd "$(dirname "$0")/.."
if [ ! -f "data/demo.sqlite" ]; then
  echo "No demo.sqlite found. Generating synthetic dataset..."
  python scripts/make_demo_db.py
fi
exec streamlit run dashboard/app.py
