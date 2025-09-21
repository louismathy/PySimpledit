@echo off
REM ==============================
REM Simpledit Starter (Windows)
REM ==============================

REM Stelle sicher, dass wir im Ordner der BAT-Datei sind
cd /d "%~dp0"

echo [Simpledit] Starte Setup ...

REM Virtuelle Umgebung prüfen/erstellen
if not exist venv (
    echo [Simpledit] Erstelle virtuelle Umgebung ...
    python -m venv venv
)

REM Aktivieren der venv
call venv\Scripts\activate

REM Pakete installieren/aktualisieren
echo [Simpledit] Installiere Abhängigkeiten ...
pip install --upgrade pip
pip install --upgrade PySide6 moviepy python-vlc

REM Hinweis zu ffmpeg
echo.
echo [Hinweis] Stelle sicher, dass ffmpeg installiert und im PATH ist.
echo           (Download: https://ffmpeg.org/download.html)
echo.

REM Start der App
echo [Simpledit] Starte Editor ...
python main.py

pause
