@echo off
setlocal EnableDelayedExpansion
title Trade Log — First-Time Setup
color 0A
cd /d "%~dp0"

:: ── Relocate to a per-user, no-admin, non-synced home ────────────────────────
:: Trade Log is a portable app: it builds a .venv, writes its database, and
:: self-updates by rewriting its own files — all *inside* this folder. Program
:: Files needs admin for every one of those writes, and OneDrive / Downloads /
:: Documents (cloud-synced) break the Python install. So before doing anything
:: else we copy ourselves to %LOCALAPPDATA%\TradeLog — which is per-user, never
:: needs admin, and is never cloud-synced — and continue setup from there, no
:: matter where the user extracted the zip. Existing trade data is migrated.
set "TARGET=%LOCALAPPDATA%\TradeLog"
if /i "%~dp0"=="%TARGET%\" goto :in_home

echo.
echo   Setting up Trade Log in your user folder:
echo     %TARGET%
echo.

if not exist "%TARGET%" mkdir "%TARGET%"

:: Copy the program files. Exclude the venv (rebuilt fresh in the new home) and
:: the data folders + database (migrated separately below so we never clobber
:: trades that already live in the target).
robocopy "%~dp0." "%TARGET%" /E /XD ".venv" ".git" "__pycache__" "backups" "attachments" "plan_attachments" "imports" /XF "_write_test.tmp" "tradelog.db" >nul
if %ERRORLEVEL% GEQ 8 (
    echo   [!] Could not copy Trade Log to your user folder — possibly blocked
    echo       by antivirus. Falling back to installing in this folder instead.
    echo.
    goto :in_home
)

:: Migrate existing user data, but only when the target has none yet (never
:: overwrite trades already living in the user folder).
if not exist "%TARGET%\tradelog.db" if exist "%~dp0tradelog.db" copy /y "%~dp0tradelog.db" "%TARGET%\tradelog.db" >nul
for %%D in (backups attachments plan_attachments imports) do (
    if not exist "%TARGET%\%%D" if exist "%~dp0%%D" robocopy "%~dp0%%D" "%TARGET%\%%D" /E >nul
)

echo   [OK] Continuing setup from your user folder...
echo.
start "" "%TARGET%\INSTALL - Double-Click This First.bat"
exit /b 0

:in_home

:: ── Force uv to copy, never hardlink ─────────────────────────────────────────
:: OneDrive / Dropbox / Google Drive sync turns folders into cloud placeholders,
:: and hardlinking into (or out of) those fails with "os error 396". Copy mode
:: sidesteps it entirely. We also park uv's cache in a local temp dir so neither
:: side of the install touches a synced location.
set "UV_LINK_MODE=copy"
set "UV_CACHE_DIR=%TEMP%\uv_cache_tradelog"

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

:: ── Guard: cloud-synced path? ────────────────────────────────────────────────
:: Catches OneDrive in the path, and also the common case where the whole user
:: profile (or its Downloads/Documents) is backed up by OneDrive — those paths
:: don't contain "OneDrive" but still sit under the cloud filter. With copy mode
:: forced above this is usually harmless now, but warn anyway.
echo "%~dp0" | findstr /i "OneDrive \\Downloads\\ \\Documents\\" >nul
if not errorlevel 1 (
    echo  [WARNING] This folder appears to be inside a cloud-synced
    echo            location ^(OneDrive / Downloads / Documents^).
    echo.
    echo  Cloud syncing can interfere with the Python installation.
    echo  This installer now forces copy mode to work around it, but for
    echo  best results move the "Trade Log" folder somewhere NOT synced:
    echo.
    echo    C:\TradeLog\
    echo.
    echo  Press any key to try installing here anyway, or close this
    echo  window and move the folder first.
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

:: --only-binary=cryptography forces uv to use cryptography's prebuilt wheel
:: instead of compiling from source (which needs Rust + OpenSSL that end-user
:: machines don't have). Prevents a confusing build failure on install.
"%UV%" pip install -r "%~dp0requirements.txt" --only-binary=cryptography --python "%~dp0.venv\Scripts\python.exe"
if errorlevel 1 (
    echo.
    echo  [!] Package installation failed.
    echo      Screenshot this window and send it for support.
    echo.
    pause & exit /b 1
)
echo  [OK] Trade Log installed.
echo.

:: ── Desktop shortcut ─────────────────────────────────────────────────────────
echo  [..] Creating a Desktop shortcut...
powershell -NoProfile -Command "$d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'Trade Log.lnk')); $s.TargetPath='%~dp0launch.bat'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%SystemRoot%\System32\shell32.dll,220'; $s.Save()" >nul 2>&1
if not errorlevel 1 (
    echo  [OK] Desktop shortcut "Trade Log" created.
) else (
    echo  [--] Could not create a Desktop shortcut ^(not essential^).
)
echo.

echo  ============================================================
echo.
echo   All done!
echo.
echo   Trade Log now lives in your user folder:
echo.
echo        %~dp0
echo.
echo   To open it, double-click the "Trade Log" shortcut on your
echo   Desktop. (You can also double-click launch.bat in the folder
echo   above.) Your browser will open automatically. Leave the black
echo   window open while you use the app - closing it stops Trade Log.
echo.
echo   You do NOT need to run this installer again, and you can delete
echo   the folder you originally unzipped.
echo.
echo  ============================================================
echo.
pause
endlocal
