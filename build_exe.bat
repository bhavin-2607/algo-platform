@echo off
setlocal enabledelayedexpansion
title Algo Platform - Standalone Executable Builder

echo ==============================================================================
echo          ALGO PLATFORM - STANDALONE SINGLE-FILE EXECUTABLE BUILDER
echo ==============================================================================
echo.

cd /d "%~dp0"

REM 1. Detect Python or Virtual Environment
set "PYTHON_EXE="

if exist "backend\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=backend\.venv\Scripts\python.exe"
    echo [OK] Using virtual environment Python: !PYTHON_EXE!
) else if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    echo [OK] Using virtual environment Python: !PYTHON_EXE!
) else (
    python --version >nul 2>&1
    if not errorlevel 1 set "PYTHON_EXE=python"
)

if not defined PYTHON_EXE (
    echo [ERROR] Python not found. Please setup virtual environment first!
    pause
    exit /b 1
)

REM 2. Verify compilation dependencies
echo [*] Checking build dependencies...
!PYTHON_EXE! -m pip install pyinstaller customtkinter pystray Pillow psutil --quiet

REM 3. Close running instances to release Windows file lock
echo [*] Closing any active instances of AlgoPlatformLauncher to release file lock...
taskkill /F /IM AlgoPlatformLauncher.exe >nul 2>&1
timeout /t 1 /nobreak >nul 2>&1

REM 4. Build Frontend Bundle if needed
if not exist "frontend\dist\index.html" (
    echo [*] Building production React frontend bundle...
    cd frontend && call npm run build && cd ..
)

REM 5. Compile Standalone Single-File Executable
echo.
echo [*] Compiling Standalone Windows Single-File Executable via PyInstaller...
echo     (Embedding Python runtime, CustomTkinter, Uvicorn, Celery, and assets into one file)
echo.

set "PYINSTALLER_CONFIG_DIR=%~dp0.pyinstaller_cache"
if not exist "%PYINSTALLER_CONFIG_DIR%" mkdir "%PYINSTALLER_CONFIG_DIR%"

!PYTHON_EXE! -m PyInstaller algo_platform.spec --clean --noconfirm

if errorlevel 1 (
    echo.
    echo ==============================================================================
    echo [ERROR] Build failed! Review the PyInstaller log output above.
    echo ==============================================================================
    pause
    exit /b 1
)

REM 6. Clean intermediate build cache
if exist "build" (
    echo [*] Removing intermediate build cache folder...
    rmdir /s /q "build"
)
if exist ".pyinstaller_cache" (
    rmdir /s /q ".pyinstaller_cache"
)

REM 7. Copy auxiliary files alongside dist\AlgoPlatformLauncher.exe
echo.
echo [*] Copying configuration and assets to dist folder...
if not exist "dist" mkdir "dist"

if exist ".env" (
    copy /Y ".env" "dist\.env" >nul
) else if exist ".env.example" (
    copy /Y ".env.example" "dist\.env" >nul
)

if exist "launcher\assets" xcopy /E /I /Y "launcher\assets" "dist\assets" >nul

echo.
echo ==============================================================================
echo [SUCCESS] Standalone Single-File Executable Built Successfully!
echo ==============================================================================
echo  Executable location:
echo    dist\AlgoPlatformLauncher.exe
echo.
echo  This is a 100%% self-contained single executable. All Python DLLs,
echo  libraries, backend services, and GUI are embedded inside.
echo  You can copy 'dist\AlgoPlatformLauncher.exe' and 'dist\.env' to any Windows PC
echo  and double-click to launch!
echo ==============================================================================
echo.
pause
