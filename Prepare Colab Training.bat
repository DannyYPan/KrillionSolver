@echo off
setlocal
cd /d "%~dp0"
title Prepare KrillionSolver Colab training

set "BUNDLE_PYTHON="
if exist ".venv\Scripts\python.exe" set "BUNDLE_PYTHON=.venv\Scripts\python.exe"
if not defined BUNDLE_PYTHON if exist ".training-venv\Scripts\python.exe" set "BUNDLE_PYTHON=.training-venv\Scripts\python.exe"
if not defined BUNDLE_PYTHON goto :no_python

"%BUNDLE_PYTHON%" training\prepare_colab_bundle.py
if errorlevel 1 goto :failed
echo.
echo Next, open training\KrillionSolver_Colab_Training.ipynb in Google Colab.
echo Select a GPU runtime, run each cell, and upload KrillionSolver-Colab-Training.zip.
pause
exit /b 0

:no_python
echo The project Python environment was not found. Run Run KrillionSolver.bat once first.
pause
exit /b 1

:failed
echo Could not prepare the Colab upload bundle. Review the error above.
pause
exit /b 1
