@echo off
REM Installs a shortcut to run_silent.vbs in the Windows Startup folder
REM so the tracker launches automatically when you log in.

setlocal
set SCRIPT_DIR=%~dp0
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set SHORTCUT=%STARTUP%\ScreenTimeTracker.lnk

echo Installing ScreenTime Tracker to startup...

REM Use PowerShell to create a proper shortcut.
powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath = 'wscript.exe'; $s.Arguments = '\"%SCRIPT_DIR%run_silent.vbs\"'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.Description = 'ScreenTime Tracker'; $s.Save()"

if exist "%SHORTCUT%" (
    echo Done!  The tracker will start automatically on next login.
    echo Shortcut: %SHORTCUT%
) else (
    echo Failed to create shortcut.  You can manually place a shortcut to
    echo run_silent.vbs in:  %STARTUP%
)
pause
