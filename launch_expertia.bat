@echo off
title Expertia Control Center
cd /d "D:\proyectos\expertia\incubator-root"

echo [Expertia] Limpiando puerto 8011...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8011') do (
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 2 /nobreak >nul

echo [Expertia] Iniciando API + Frontend...
start "Expertia API" /min python query_api.py

echo        Esperando a que arranque...
timeout /t 5 /nobreak >nul

echo        Abriendo navegador...
start "" "http://localhost:8011/admin"
echo.
echo        Admin:   http://localhost:8011/admin
echo        API:     http://localhost:8011/api/health
echo        Movil:   http://192.168.1.43:8011/admin
echo.
echo        Streamlit (fallback): http://localhost:8501
echo        (si existe, iniciar manual: streamlit run expertia_console.py)
echo.
echo        Pulsa cualquier tecla para cerrar esta ventana
echo        (la API sigue corriendo)
pause >nul
