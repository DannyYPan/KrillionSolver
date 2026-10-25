@echo off
setlocal
cd /d "%~dp0"
title Edit KrillionSolver training data

set "USER_DATA=%LOCALAPPDATA%\KrillionSolver"
if not exist "%USER_DATA%" mkdir "%USER_DATA%"
if not exist "%USER_DATA%\training_examples.jsonl" type nul > "%USER_DATA%\training_examples.jsonl"
if not exist "%USER_DATA%\rejected_answers.jsonl" type nul > "%USER_DATA%\rejected_answers.jsonl"

echo Opening the training files.
echo Each line is one JSON record. Delete the entire line to remove a bad example.
echo Confirmed answers: %USER_DATA%\training_examples.jsonl
echo Rejected answers:  %USER_DATA%\rejected_answers.jsonl
echo Curated examples:  %CD%\training\trivia_data.jsonl
echo.

where code.cmd >nul 2>nul
if not errorlevel 1 (
    start "" code.cmd "%USER_DATA%\training_examples.jsonl" "%USER_DATA%\rejected_answers.jsonl" "%CD%\training\trivia_data.jsonl"
) else (
    start "" notepad.exe "%USER_DATA%\training_examples.jsonl"
    start "" notepad.exe "%USER_DATA%\rejected_answers.jsonl"
    start "" notepad.exe "%CD%\training\trivia_data.jsonl"
)
exit /b 0
