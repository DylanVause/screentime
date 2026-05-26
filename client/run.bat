@echo off
REM Run the tracker in a visible console window.
REM For silent background operation, use run_silent.vbs instead.
cd /d "%~dp0"
pythonw tracker.py
