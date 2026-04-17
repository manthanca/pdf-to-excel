@echo off
title MRACA Smart Contract Note Converter
echo =====================================================
echo   MRACA Smart Contract Note Converter
echo   Starting...
echo =====================================================

REM Try to use the venv python first, then system python
IF EXIST "%~dp0.venv\Scripts\python.exe" (
    SET PYTHON="%~dp0.venv\Scripts\python.exe"
) ELSE (
    SET PYTHON=python
)

REM Install dependencies if needed
%PYTHON% -m pip install -r "%~dp0requirements.txt" --quiet

REM Launch the app
%PYTHON% "%~dp0launcher.py"

pause
