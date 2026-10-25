@echo off
setlocal
cd /d "%~dp0"
title KrillionSolver training

set "PREVIEW_PYTHON="
if exist ".venv\Scripts\python.exe" set "PREVIEW_PYTHON=.venv\Scripts\python.exe"
if not defined PREVIEW_PYTHON if exist ".training-venv\Scripts\python.exe" set "PREVIEW_PYTHON=.training-venv\Scripts\python.exe"
if not defined PREVIEW_PYTHON (
    where py.exe >nul 2>nul
    if not errorlevel 1 set "PREVIEW_PYTHON=py.exe"
)
if not defined PREVIEW_PYTHON goto :no_python

"%PREVIEW_PYTHON%" training\preview_training.py
if errorlevel 1 goto :failed

echo.
echo Review every item above before training.
echo Type TRAIN to begin, EDIT to open the data files, or anything else to cancel.
set /p "TRAIN_CONFIRM=Confirmation: "
if /i "%TRAIN_CONFIRM%"=="EDIT" (
    call "Edit Training Data.bat"
    echo Run this training launcher again after saving your edits.
    pause
    exit /b 0
)
if /i not "%TRAIN_CONFIRM%"=="TRAIN" (
    echo Training cancelled. No model files were changed.
    pause
    exit /b 0
)

set "TRAINING_PYTHON="
if defined KRILLION_TRAINING_PYTHON if exist "%KRILLION_TRAINING_PYTHON%" set "TRAINING_PYTHON=%KRILLION_TRAINING_PYTHON%"
if not defined TRAINING_PYTHON if exist ".training-venv\Scripts\python.exe" set "TRAINING_PYTHON=.training-venv\Scripts\python.exe"
if not defined TRAINING_PYTHON goto :no_training_environment

"%TRAINING_PYTHON%" -c "import unsloth, datasets, trl" >nul 2>nul
if errorlevel 1 goto :missing_packages

echo.
echo Starting Llama 3.1 8B fine-tuning...
"%TRAINING_PYTHON%" training\finetune_krillion.py
if errorlevel 1 goto :failed

echo.
echo Training and GGUF export finished.
echo Run the ollama create command printed above, then restart KrillionSolver.
pause
exit /b 0

:no_training_environment
echo.
echo A separate training environment was not found at .training-venv.
echo.
echo 1. Install 64-bit Python 3.12 if it is not already installed.
echo 2. Open PowerShell in this project folder and run:
echo    py -3.12 -m venv .training-venv
echo    .\.training-venv\Scripts\python.exe -m pip install -r training\requirements.txt
echo 3. Run Train KrillionSolver.bat again.
echo.
echo Unsloth is GPU/CUDA-specific. If installation fails, follow its Windows/WSL guide.
echo See training\README.md for the commands and Unsloth Windows/WSL guidance.
pause
exit /b 1

:missing_packages
echo.
echo The training environment exists, but Unsloth, datasets, or TRL is missing.
echo Follow training\README.md to install the GPU-compatible packages, then run this file again.
pause
exit /b 1

:no_python
echo Python was not found. Install Python 3.10 through 3.12 for training.
pause
exit /b 1

:failed
echo.
echo Training did not finish. Review the error above; the existing Ollama model was not replaced.
pause
exit /b 1
