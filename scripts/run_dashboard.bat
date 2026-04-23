@echo off
REM Launch the Rubin Anomaly Hunter dashboard on Windows.
REM Run from the project root: scripts\run_dashboard.bat
REM See docs/ux/brief.md for dashboard context.

pushd "%~dp0.."
if not exist "data\demo.sqlite" (
  echo No demo.sqlite found. Generating synthetic dataset...
  python scripts\make_demo_db.py
)
streamlit run dashboard\app.py
popd
