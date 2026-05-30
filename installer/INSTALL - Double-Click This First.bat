@echo off
setlocal EnableDelayedExpansion
title Trade Log — First-Time Setup
color 0A
cd /d "%~dp0"

echo.
echo  ============================================================
echo   Trade Log — First-Time Setup
echo   Please keep this window open. It will close when done.
echo  ============================================================
echo.

:: ── Guard: running from inside a zip? ────────────────────────────────────────
echo. > "%~dp0_write_test.tmp" 2>nul
if errorlevel 1 (
    echo  [!] It looks like you are running this from inside a zip file.
    echo.
    echo      Please close this, then RIGHT-CLICK the zip file and choose
    echo      "Extract All" before trying again.
    echo.
    pause & exit /b 1
)
del "%~dp0_write_test.tmp" >nul 2>&1

:: ── Guard: already installed? ─────────────────────────────────────────────────
if exist "%~dp0.venv\Scripts\python.exe" (
    echo  [OK] Trade Log is already installed.
    echo.
    echo       If something is broken, delete the ".venv" folder
    echo       in this directory and run this installer again.
    echo.
    pause & exit /b 0
)

:: ── Guard: OneDrive path? ────────────────────────────────────────────────────
echo "%~dp0" | findstr /i "OneDrive" >nul
if not errorlevel 1 (
    echo  [WARNING] This folder appears to be inside OneDrive.
    echo.
    echo  OneDrive syncing can interfere with the Python installation
    echo  and cause it to fail or behave unpredictably.
    echo.
    echo  RECOMMENDED: Move the "Trade Log" folder somewhere outside
    echo  OneDrive first, such as:
    echo.
    echo    C:\Users\%USERNAME%\Trade Log\
    echo.
    echo  Press any key to try installing here anyway (may not work),
    echo  or close this window and move the folder first.
    echo.
    pause
)

:: ── Guard: Program Files path? ───────────────────────────────────────────────
echo "%~dp0" | findstr /i "Program Files" >nul
if not errorlevel 1 (
    echo  [!] This folder is inside "Program Files" which requires
    echo      administrator access for every file operation.
    echo.
    echo  Please move the "Trade Log" folder to your Desktop or
    echo  Documents folder and run this installer again.
    echo.
    pause & exit /b 1
)

:: ── Clean up any partial previous install ────────────────────────────────────
if exist "%~dp0.venv" (
    echo  [..] Cleaning up incomplete previous install...
    rmdir /s /q "%~dp0.venv" 2>nul
    echo  [OK] Cleaned up.
    echo.
)

:: ── Step 1: uv setup tools ────────────────────────────────────────────────────
echo  [1 of 3]  Checking setup tools...
echo.

set "UV_DIR=%~dp0_uv"
set "UV=%UV_DIR%\uv.exe"
set "UV_URL=https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip"
set "UV_ZIP=%TEMP%\uv_setup.zip"

if exist "%UV%" goto :uv_ready

echo  [..] Downloading setup tools (one-time)...
powershell -NoProfile -Command "Invoke-WebRequest -Uri '%UV_URL%' -OutFile '%UV_ZIP%' -UseBasicParsing"
if errorlevel 1 (
    echo.
    echo  [!] Could not download setup tools.
    echo      Please check your internet connection and try again.
    echo.
    pause & exit /b 1
)
if not exist "%UV_DIR%" mkdir "%UV_DIR%"
powershell -NoProfile -Command "Expand-Archive -Path '%UV_ZIP%' -DestinationPath '%UV_DIR%' -Force"
del "%UV_ZIP%" 2>nul

:uv_ready
echo  [OK] Setup tools ready.
echo.

:: ── Step 2: Install Python ────────────────────────────────────────────────────
echo  [2 of 3]  Installing Python 3.12...
echo            (one-time download — may take a minute)
echo.
"%UV%" python install 3.12
if errorlevel 1 (
    echo.
    echo  [!] Python installation failed.
    echo.
    echo      Common causes:
    echo        - No internet connection or download was blocked by firewall
    echo        - Antivirus quarantined the download
    echo        - Not enough disk space ^(needs ~200 MB^)
    echo        - Company/school IT policy blocking software installs
    echo.
    echo      Screenshot this window and send it for support.
    echo.
    pause & exit /b 1
)
echo  [OK] Python ready.
echo.

:: ── Step 3: Create virtual environment ───────────────────────────────────────
echo  [3 of 3]  Installing Trade Log...
echo            ^(this is the slow step — 2 to 5 minutes^)
echo            Please wait...
echo.

"%UV%" venv --python 3.12 "%~dp0.venv"
if errorlevel 1 (
    echo.
    echo  [!] Could not create the Python environment.
    echo.
    echo      This can happen if:
    echo        - The folder path contains special characters
    echo        - Python 3.12 did not install correctly in step 2
    echo        - Antivirus blocked the operation
    echo.
    echo      Screenshot this window and send it for support.
    echo.
    pause & exit /b 1
)

:: Verify python.exe was actually created
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo.
    echo  [!] Python environment was created but python.exe is missing.
    echo      This is usually caused by antivirus software removing files.
    echo.
    echo      Try temporarily disabling antivirus and running this again.
    echo.
    pause & exit /b 1
)

"%UV%" pip install -r "%~dp0requirements.txt" --python "%~dp0.venv\Scripts\python.exe"
if errorlevel 1 (
    echo.
    echo  [!] Package installation failed.
    echo      Screenshot this window and send it for support.
    echo.
    pause & exit /b 1
)
echo  [OK] Trade Log installed.
echo.

echo  ============================================================
echo.
echo   All done!
echo.
echo   To open Trade Log from now on:
echo.
echo     In THIS SAME FOLDER, double-click the file named
echo.
echo        launch.bat
echo.
echo   (It sits right next to this installer.) Your browser will
echo   open automatically. Leave the black window open while you
echo   use the app - closing it stops Trade Log.
echo.
echo   You do NOT need to run this installer again.
echo.
echo  ============================================================
echo.
pause
endlocal
