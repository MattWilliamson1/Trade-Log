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

:: ── Guard: make sure we are NOT running from inside a zip ────────────────────
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

:: ── Step 1: Download uv (tiny Python/package manager from Astral) ────────────
echo  [1 of 4]  Downloading setup tools...
echo            (this is a small, one-time download)
echo.

set "UV_DIR=%~dp0_uv"
set "UV=%UV_DIR%\uv.exe"
set "UV_URL=https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip"
set "UV_ZIP=%TEMP%\uv_setup.zip"

if exist "%UV%" goto :uv_ready

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
echo  [2 of 4]  Installing Python...
echo            (also a one-time download, may take a minute)
echo.
"%UV%" python install 3.12
if errorlevel 1 (
    echo.
    echo  [!] Python installation failed.
    echo.
    echo      Common causes:
    echo        - No internet connection or the download was blocked
    echo        - Antivirus software blocked the download
    echo        - Not enough disk space (needs ~200 MB)
    echo        - Company/school IT policy blocking installs
    echo.
    echo      Screenshot this window and send it for support.
    echo.
    pause & exit /b 1
)
echo  [OK] Python ready.
echo.

:: ── Step 3: Install Trade Log packages ───────────────────────────────────────
echo  [3 of 4]  Installing Trade Log (this is the slow step — 2 to 5 minutes)
echo            Please wait...
echo.
"%UV%" venv --python 3.12 "%~dp0.venv"
"%UV%" pip install -r "%~dp0requirements.txt" --python "%~dp0.venv\Scripts\python.exe"
if errorlevel 1 (
    echo.
    echo  [!] Package installation failed.
    echo.
    echo      Screenshot this window and send it for support.
    echo.
    pause & exit /b 1
)
echo  [OK] Trade Log installed.
echo.

:: ── Step 4: Create Desktop shortcut ──────────────────────────────────────────
echo  [4 of 4]  Creating your Desktop shortcut...

set "VBS_PATH=%~dp0launch.vbs"
set "SHORTCUT=%USERPROFILE%\Desktop\Trade Log.lnk"

powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; " ^
  "$s = $ws.CreateShortcut('%SHORTCUT%'); " ^
  "$s.TargetPath = 'wscript.exe'; " ^
  "$s.Arguments = '\"%VBS_PATH%\"'; " ^
  "$s.WorkingDirectory = '%~dp0'; " ^
  "$s.IconLocation = '%SystemRoot%\System32\SHELL32.dll,14'; " ^
  "$s.Description = 'Open Trade Log'; " ^
  "$s.Save()"

echo  [OK] Shortcut created on your Desktop.
echo.

echo  ============================================================
echo.
echo   All done!
echo.
echo   You will find a "Trade Log" icon on your Desktop.
echo   Double-click it any time to open Trade Log.
echo.
echo   You do NOT need to run this installer again.
echo.
echo  ============================================================
echo.
pause
endlocal
