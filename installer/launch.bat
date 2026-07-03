@echo off
setlocal
title Trade Log
color 0E
cd /d "%~dp0"

:: Locate the installed app. Normally the venv sits next to this launcher, but
:: the installer relocates a fresh install to %LOCALAPPDATA%\TradeLog. If this
:: copy has no venv — e.g. this is the launch.bat still sitting in the folder you
:: unzipped — fall back to that per-user install so double-clicking here works.
set "APP_DIR=%~dp0"
set "PYTHON=%APP_DIR%.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    if exist "%LOCALAPPDATA%\TradeLog\.venv\Scripts\python.exe" (
        set "APP_DIR=%LOCALAPPDATA%\TradeLog\"
        set "PYTHON=%LOCALAPPDATA%\TradeLog\.venv\Scripts\python.exe"
    )
)

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
:: launch.py supervises Streamlit: it picks a light/dark theme base matching the
:: saved theme, and relaunches automatically when the app requests a restart.
:: Run the installed copy's launch.py (APP_DIR) so its data/venv paths resolve
:: to the real install, not this possibly-empty extract folder.
cd /d "%APP_DIR%"
"%PYTHON%" "%APP_DIR%launch.py" --port %PORT% --no-browser

echo.
echo  Trade Log has stopped. You can close this window.
echo.
pause
endlocal
