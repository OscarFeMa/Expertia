@echo off
title Expertia Control Center
cd /d "D:\proyectos\expertia\incubator-root"

echo [Expertia] Limpiando procesos anteriores...
taskkill /F /IM pythonw.exe >nul 2>&1
taskkill /F /IM python.exe >nul 2>&1
timeout /t 2 /nobreak >nul

echo [Expertia] Limpiando puerto 8011...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8011') do (
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 2 /nobreak >nul

echo [Expertia] Iniciando API...
start "Expertia API" /MIN python.exe query_api.py

echo        Esperando a que la API responda...
set /a "attempts=0"
:wait_loop
timeout /t 1 /nobreak >nul
set /a "attempts+=1"
curl -s http://127.0.0.1:8011/api/health >nul 2>&1
if %errorlevel% neq 0 (
    if %attempts% lss 20 goto wait_loop
    echo        [ERROR] API no responde tras 20 segundos.
    pause
    exit /b 1
)
echo        API lista (%attempts%s). Abriendo Expertia...
start "" "http://localhost:8011/admin"
