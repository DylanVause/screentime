@echo off
setlocal EnableDelayedExpansion

set GITHUB_URL=https://github.com/DylanVause/screentime
set SERVER_URL=https://screentime.dylanvause.com
set INSTALL_DIR=%USERPROFILE%\ScreenTime

echo.
echo  ScreenTime Installer
echo  ====================
echo.

REM ── Check Python ────────────────────────────────────────────────────────────

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found.
    echo Install from https://python.org/downloads and re-run.
    pause & exit /b 1
)
echo [OK] Python found.

REM ── Download repo ────────────────────────────────────────────────────────────

if exist "%INSTALL_DIR%" (
    echo [OK] Existing install found at %INSTALL_DIR% -- skipping download.
) else (
    echo Downloading ScreenTime...
    powershell -NoProfile -Command "Invoke-WebRequest '%GITHUB_URL%/archive/refs/heads/main.zip' -OutFile '%TEMP%\screentime.zip'"
    if errorlevel 1 (
        echo ERROR: Download failed. Check your internet connection.
        pause & exit /b 1
    )
    powershell -NoProfile -Command "Expand-Archive '%TEMP%\screentime.zip' -DestinationPath '%TEMP%\screentime-extract' -Force"
    xcopy /E /I /Q "%TEMP%\screentime-extract\screentime-main\client" "%INSTALL_DIR%" >nul
    del "%TEMP%\screentime.zip"
    rd /s /q "%TEMP%\screentime-extract"
    echo [OK] Installed to %INSTALL_DIR%
)

REM ── Install Python dependencies ──────────────────────────────────────────────

echo Installing dependencies...
python -m pip install -q -r "%INSTALL_DIR%\requirements.txt"
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause & exit /b 1
)
echo [OK] Dependencies installed.

REM ── Prompt for config ────────────────────────────────────────────────────────

echo.
set /p DEVICE_NAME=Device name (shown in dashboard, e.g. Home Desktop):
if "!DEVICE_NAME!"=="" set DEVICE_NAME=%COMPUTERNAME%

set /p API_KEY=API key (from %SERVER_URL%/api-keys):
if "!API_KEY!"=="" (
    echo ERROR: API key is required.
    pause & exit /b 1
)

REM ── Write config.toml ────────────────────────────────────────────────────────

(
echo [server]
echo url = "%SERVER_URL%"
echo api_key = "!API_KEY!"
echo verify_ssl = true
echo timeout_seconds = 30
echo.
echo [device]
echo name = "!DEVICE_NAME!"
echo.
echo [tracking]
echo poll_interval = 1
echo upload_interval = 900
echo min_session_seconds = 2
echo.
echo [storage]
echo db_path = "sessions.db"
) > "%INSTALL_DIR%\config.toml"

echo [OK] Config written.

REM ── Startup shortcut ─────────────────────────────────────────────────────────

echo.
set /p ADD_STARTUP=Start tracker automatically when you log in? (y/n):
if /i "!ADD_STARTUP!"=="y" (
    set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
    set SHORTCUT=!STARTUP!\ScreenTimeTracker.lnk
    powershell -NoProfile -Command ^
        "$ws = New-Object -ComObject WScript.Shell; ^
         $s = $ws.CreateShortcut('!SHORTCUT!'); ^
         $s.TargetPath = 'wscript.exe'; ^
         $s.Arguments = '\"%INSTALL_DIR%\run_silent.vbs\"'; ^
         $s.WorkingDirectory = '%INSTALL_DIR%'; ^
         $s.Description = 'ScreenTime Tracker'; ^
         $s.Save()"
    echo [OK] Shortcut created -- tracker will start on next login.
) else (
    echo Skipped. Run manually with: %INSTALL_DIR%\run.bat
)

REM ── Done ─────────────────────────────────────────────────────────────────────

echo.
echo  Install complete!
echo  To start now, run: %INSTALL_DIR%\run.bat
echo.
pause
