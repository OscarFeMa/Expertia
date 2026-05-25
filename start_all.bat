@echo off
start /min pythonw.exe web_dashboard.py
timeout /t 3 >nul
start /min pythonw.exe watchdog.py