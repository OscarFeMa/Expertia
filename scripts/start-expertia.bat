@echo off
cd /d "%~dp0.."
start /B pythonw.exe query_api.py >nul 2>&1
ping -n 5 127.0.0.1 >nul
start http://localhost:8011/admin
