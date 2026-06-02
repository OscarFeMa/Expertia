@echo off
cd /d "%~dp0"
start /min pythonw.exe query_api.py
timeout /t 5 >nul
start /min pythonw.exe orchestrator.py --phase nurture
