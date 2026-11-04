@echo off
setlocal
cd /d "%~dp0"
title KrillionSolver Answer History

if not exist ".venv\Scripts\python.exe" (
    echo Run "Run KrillionSolver.bat" once before opening answer history.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m app.history_window
if errorlevel 1 (
    echo.
    echo The answer history editor could not be opened.
    pause
)
