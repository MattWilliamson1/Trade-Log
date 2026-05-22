@echo off
setlocal
title Trade Log — Diagnostics
color 0E
cd /d "%~dp0"

echo.
echo  ============================================================
echo   Trade Log — Diagnostics
echo   This window will show you exactly why Trade Log won't start.
echo  ============================================================
echo.

:: ── Check .venv exists ────────────────────────────────────────────────────────
set "PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo  [PROBLEM] The Trade Log setup is incomplete.
    echo.
    echo  The Python environment was not found at:
    echo  %PYTHON%
    echo.
    echo  SOLUTION: Please run "INSTALL - Double-Click This First.bat" again.
    echo.
    pause & exit /b 1
)
echo  [OK] Python found at: %PYTHON%
echo.

:: ── Check port 8502 is free ───────────────────────────────────────────────────
netstat -an | find ":8502" >nul 2>&1
if not errorlevel 1 (
    echo  [WARNING] Something is already using port 8502.
    echo  This may mean Trade Log is already running in the background.
    echo.
    echo  Try opening your browser and going to:  http://localhost:8502
    echo.
    echo  If that doesn't work, restart your computer and try again.
    echo.
    pause & exit /b 1
)
echo  [OK] Port 8502 is free.
echo.

:: ── Try to launch Streamlit — errors will be visible here ────────────────────
echo  [STARTING] Launching Trade Log now...
echo  Watch this window for any error messages.
echo  (Press Ctrl+C to stop when you are done.)
echo.
echo  ============================================================
echo.

"%PYTHON%" -m streamlit run "%~dp0app.py" --server.port 8502 --server.headless true --browser.gatherUsageStats false

echo.
echo  ============================================================
echo  Trade Log has stopped. If you saw an error above, please
echo  take a screenshot and send it for support.
echo  ============================================================
echo.
pause
endlocal
