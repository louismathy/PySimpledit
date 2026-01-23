@echo off
REM ======================================
REM Simpledit Dependency Installer (Windows)
REM ======================================

REM Ensure we run from the BAT file folder
cd /d "%~dp0"

echo [Simpledit] Starting setup ...

REM Check/create virtual environment
if not exist venv (
    echo [Simpledit] Creating virtual environment ...
    python -m venv venv
)

REM Activate venv
call venv\Scripts\activate

REM Install/update packages
echo [Simpledit] Installing dependencies ...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

REM ffmpeg note (needed for moviepy/pydub)
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo.
    echo [Note] ffmpeg not found. Please install and add to PATH.
    echo        Download: https://ffmpeg.org/download.html
    echo.
)

echo [Simpledit] Dependencies installed.
pause
