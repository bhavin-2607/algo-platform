@echo off
rem ==============================================================================
rem Algo Platform — Universal Standalone Launcher (Windows)
rem ==============================================================================
setlocal
cd /d "%~dp0"

if exist "backend\.venv\Scripts\python.exe" (
    "backend\.venv\Scripts\python.exe" run.py %*
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run.py %*
) else (
    python run.py %*
)
