@echo off
setlocal
cd /d "%~dp0"
title KrillionSolver setup and launcher

if not exist ".venv\Scripts\python.exe" (
    echo First run: creating the app's private Python environment...
    where py >nul 2>nul
    if errorlevel 1 (
        echo Python Launcher was not found. Install Python for Windows, then run this file again.
        pause
        exit /b 1
    )
    py -m venv .venv
    if errorlevel 1 goto :failed
)

if not exist ".venv\.krill_ready" (
    echo Installing KrillionSolver requirements...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto :failed
    echo Installing the Chromium browser used by the app...
    ".venv\Scripts\python.exe" -m playwright install chromium
    if errorlevel 1 goto :failed
    type nul > ".venv\.krill_ready"
)

echo Starting KrillionSolver...
".venv\Scripts\python.exe" prompt_assistant.py
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo Setup or startup failed. Check the message above, then run this file again.
pause
exit /b 1
