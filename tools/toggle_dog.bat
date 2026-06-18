@echo off
title DogController
cd /d "%~dp0.."
set PWSH="C:\Program Files\PowerShell\7\pwsh.exe"

%PWSH% -NoProfile -ExecutionPolicy Bypass -File "%~dp0toggle_dog.ps1"

echo.
echo  Pulsa cualquier tecla para cerrar...
pause >nul
