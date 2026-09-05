@echo off
setlocal
cd /d "%~dp0"
net session >nul 2>&1
if errorlevel 1 echo EJECUTE COMO ADMINISTRADOR (clic derecho) & pause & exit /b 1
echo Creando usuario local expertia (sin admin, solo entreno) ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0New-3070-User.ps1" -OutDir "%~dp0"
echo.
echo Devuelve el USB con new-user-3070.txt.
echo.
pause
endlocal
