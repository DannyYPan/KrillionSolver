@echo off
setlocal EnableDelayedExpansion
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

".venv\Scripts\python.exe" -c "import cmudict" >nul 2>nul
if errorlevel 1 (
    echo Installing the local word dictionary...
    ".venv\Scripts\python.exe" -m pip install "cmudict>=1.0.32"
    if errorlevel 1 goto :failed
)

if defined LOCALAPPDATA if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "PATH=%LOCALAPPDATA%\Programs\Ollama;%PATH%"
rem Use the fine-tuned 8B tag when available, otherwise use base Llama 3.1 8B.
set "KRILLION_OLLAMA_MODEL=llama3.1:latest"
where ollama.exe >nul 2>nul
if errorlevel 1 (
    echo Ollama was not found in PATH. Install Ollama to enable local model answers.
) else (
    echo Checking the Ollama service...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$url='http://127.0.0.1:11434/api/tags'; try { Invoke-RestMethod -Uri $url -TimeoutSec 2 | Out-Null; exit 0 } catch {}; $exe=(Get-Command ollama.exe -ErrorAction SilentlyContinue).Source; if (-not $exe) { exit 2 }; try { Start-Process -FilePath $exe -ArgumentList 'serve' -WindowStyle Hidden } catch { exit 3 }; for ($i=0; $i -lt 20; $i++) { Start-Sleep -Seconds 1; try { Invoke-RestMethod -Uri $url -TimeoutSec 2 | Out-Null; exit 0 } catch {} }; exit 1"
    if errorlevel 1 echo Could not start Ollama. KrillionSolver will open, but local model answers may be unavailable.
    if errorlevel 1 goto :ollama_done
    for /f "tokens=1" %%M in ('ollama list 2^>nul ^| findstr /b /c:"krillionsolver:8b"') do set "KRILLION_OLLAMA_MODEL=%%M"
    if "!KRILLION_OLLAMA_MODEL!"=="krillionsolver:8b" echo Using the fine-tuned Llama 3.1 8B model.
    echo Loading the configured Ollama model. The first load can take a while...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$model=$env:KRILLION_OLLAMA_MODEL; $url='http://127.0.0.1:11434/api/generate'; $body=@{ model=$model; prompt=''; stream=$false; keep_alive='10m' } | ConvertTo-Json -Compress; try { Invoke-RestMethod -Uri $url -Method Post -Body $body -ContentType 'application/json' -TimeoutSec 600 | Out-Null; Write-Host ('Model ' + $model + ' (Llama 3.1 8B) is running and ready.'); exit 0 } catch { Write-Host ('Could not load model ' + $model + '. Install it with: ollama pull ' + $model); exit 1 }"
    if errorlevel 1 echo KrillionSolver will still open, but Ollama answers may be unavailable.
)
:ollama_done

echo Starting KrillionSolver...
".venv\Scripts\python.exe" prompt_assistant.py
if errorlevel 1 goto :failed
exit /b 0

:failed
echo.
echo Setup or startup failed. Check the message above, then run this file again.
pause
exit /b 1
