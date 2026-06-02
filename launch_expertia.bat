@echo off
title Expertia Control Center
cd /d "D:\proyectos\expertia\incubator-root"

echo [Expertia] Limpiando puerto 8011...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8011') do (
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 2 /nobreak >nul

echo [Expertia] Iniciando API en segundo plano...
start /min pythonw.exe query_api.py

echo        Esperando a que arranque...
timeout /t 5 /nobreak >nul

echo        Abriendo Expertia...
start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge_proxy.exe" --profile-directory=Default --app-id=ggfbkolakpabfgbfpdgdblkodmgihlmp --app-url=http://localhost:8011/admin/ --app-launch-source=4
