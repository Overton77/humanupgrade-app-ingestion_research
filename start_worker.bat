@echo off
REM Start Taskiq Worker with Windows Event Loop Fix
REM This script ensures sitecustomize.py is loaded for psycopg compatibility

cd /d "%~dp0"

echo [start_worker] Setting PYTHONPATH to include sitecustomize.py...
set PYTHONPATH=%CD%;%PYTHONPATH%

echo [start_worker] Starting Taskiq worker with 2 workers...
echo [start_worker] Event loop policy will be set via sitecustomize.py
echo.

uv run taskiq worker research_agent.infrastructure.queue.taskiq_broker:broker --workers 2

pause
