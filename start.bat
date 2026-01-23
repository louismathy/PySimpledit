@echo off
REM ==============================
REM Simpledit Starter (Windows)
REM ==============================

REM Ensure we run from the BAT file folder
cd /d "%~dp0"

if not exist venv (
    echo [Simpledit] Missing virtual environment. Run install_dependencies.bat first.
    pause
    exit /b 1
)

REM Activate venv
call venv\Scripts\activate

REM Start the app
echo [Simpledit] Starting editor ...
python src/main.py

pause
