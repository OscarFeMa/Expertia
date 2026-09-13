@echo off
REM ============================================================
REM  EXPERTIA LAUNCHER — menú interactivo + CLI
REM  Double-click: menú interactivo
REM  CLI: launcher.cmd --mode web --duration 24 --specialist Physics
REM ============================================================
setlocal
cd /d "%~dp0"

set "PY=%~dp0..\..\..\..\venv\Scripts\python.exe"
if exist "C:\Users\usuario\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe" (
  set "PY=C:\Users\usuario\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
)

"%PY%" "%~dp0tools\launcher.py" %*
if errorlevel 1 pause
endlocal