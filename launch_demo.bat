@echo off
cd /d "%~dp0"

:: Re-seed demo data on every launch so it stays fresh
python seed_demo.py
:: errorlevel 2 = the app is already running; seed_demo printed the details
if errorlevel 2 (
    pause
    exit /b 2
)
if errorlevel 1 (
    echo Failed to seed demo database. Check that Python and requirements are installed.
    pause
    exit /b 1
)

set TRADELOG_DB=%~dp0demo\tradelog_demo.db
python launch.py --port 8502
pause
