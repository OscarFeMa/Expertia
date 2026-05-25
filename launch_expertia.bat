@echo off
title Expertia Control Center
cd /d "D:\proyectos\expertia\incubator-root"

echo [Expertia] Limpiando puerto 8501...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8501') do (
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 2 /nobreak >nul

echo [Expertia] Iniciando Consola...
start /min "Expertia Console" streamlit run expertia_console.py --server.address 0.0.0.0 --server.port 8501 --server.fileWatcherType none --server.headless true

echo        Esperando a que arranque...
timeout /t 8 /nobreak >nul

echo        Abriendo navegador...
start "" "http://localhost:8501"
echo.
echo        Consola: http://localhost:8501
echo        Movil:   http://192.168.1.43:8501
echo.
echo        Pulsa cualquier tecla para cerrar esta ventana
echo        (la consola sigue corriendo)
pause >nul
