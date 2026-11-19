@echo off
setlocal
cd /d "%~dp0"
title Algo Platform - Desktop Launcher

if exist "backend\.venv\Scripts\python.exe" (
    start "" "backend\.venv\Scripts\pythonw.exe" desktop_launcher.py %* 2>nul || "backend\.venv\Scripts\python.exe" desktop_launcher.py %*
) else if exist ".venv\Scripts\python.exe" (
    start "" ".venv\Scripts\pythonw.exe" desktop_launcher.py %* 2>nul || ".venv\Scripts\python.exe" desktop_launcher.py %*
) else (
    start "" pythonw desktop_launcher.py %* 2>nul || python desktop_launcher.py %*
)
