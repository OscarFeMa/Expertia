@echo off
setlocal
cd /d "%~dp0"
set "PY=%~dp0.venv-train\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
echo Monitor ExpertiaMath en http://localhost:8077/
start "" "http://localhost:8077/"
"%PY%" "%~dp0monitor\monitor_train.py"
if errorlevel 1 pause
endlocal
