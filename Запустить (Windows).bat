@echo off
rem Runs the bridge in a visible window: for checking what it says when something is off.
rem Keep this file ASCII-only: cmd reads it in the OEM codepage.
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
chcp 65001 >nul
if not exist ".venv\Scripts\python.exe" (
    echo Run "Ustanovit (Windows).bat" first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m bridge.main %*
pause
