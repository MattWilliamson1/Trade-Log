@echo off
setlocal
title Trade Log
color 0E
cd /d "%~dp0"

set "PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    cls
    echo.
    echo  [!] Trade Log is not set up yet.
    echo.
    echo  Please run "INSTALL - Double-Click This First.bat" first.
    echo.
    pause & exit /b 1
)

:: ── Find the first free port, starting at 8502 ───────────────────────────────
:: Each line below is its own statement (no parenthesised block) so that %PORT%
:: re-expands fresh on every loop. ATTEMPTS is a safety cap against looping.
set "PORT=8501"
set /a ATTEMPTS=0
:find_port
set /a PORT+=1
set /a ATTEMPTS+=1
if %ATTEMPTS% GTR 50 goto port_ready
netstat -an | find ":%PORT% " >nul 2>&1
if not errorlevel 1 goto find_port
:port_ready

cls
echo.
echo  ============================================================
echo.
echo   ###   ####      #  #  ####  #####
echo   #  #  #  #      ## #  #  #    #
echo   #  #  #  #      # ##  #  #    #
echo   #  #  #  #      #  #  #  #    #
echo   ###   ####      #  #  ####    #
echo.
echo    ###  #     ####   ###  ####
echo   #     #     #  #  #     #
echo   #     #     #  #   ##   ###
echo   #     #     #  #     #  #
echo    ###  ####  ####  ###   ####
echo.
echo                THIS WINDOW
echo.
echo  ============================================================
echo.
echo   Closing this window will CLOSE Trade Log.
echo.
echo   Leave it open while you are using the app. Your browser
echo   will open automatically in a few seconds.
echo.
echo   If it does NOT open on its own, click or type this address
echo   into your web browser:
echo.
echo        http://localhost:%PORT%
echo.
echo   When you are finished, you can just close this window.
echo.
echo  ============================================================
echo.

:: ── Open the browser once Streamlit has had a moment to start ────────────────
start /min "" cmd /c "timeout /t 5 /nobreak >nul & start http://localhost:%PORT%"

:: ── Run Trade Log (keeps this window open until it stops) ────────────────────
"%PYTHON%" -m streamlit run "%~dp0app.py" --server.port %PORT% --server.headless true --browser.gatherUsageStats false

echo.
echo  Trade Log has stopped. You can close this window.
echo.
pause
endlocal
