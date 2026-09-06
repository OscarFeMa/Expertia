@echo off
setlocal
set "OUT=%TEMP%\tdrdelay-3070.txt"
net session >nul 2>&1
if errorlevel 1 echo EJECUTE COMO ADMINISTRADOR (clic derecho) & pause & exit /b 1
echo Anti-cuelgue GPU (TdrDelay 60s) ...
echo [%date% %time%] inicio > "%OUT%"
echo [1/3] TdrDelay+TdrDdiDelay a 60s >> "%OUT%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "New-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers' -Name TdrDelay -Value 60 -PropertyType DWord -Force | Out-Null; New-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers' -Name TdrDdiDelay -Value 60 -PropertyType DWord -Force | Out-Null; Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers' | Select-Object TdrDelay, TdrDdiDelay" >> "%OUT%" 2>&1
echo [2/3] verificar >> "%OUT%"
reg query "HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers" /v TdrDelay >> "%OUT%" 2>&1
reg query "HKLM\SYSTEM\CurrentControlSet\Control\GraphicsDrivers" /v TdrDdiDelay >> "%OUT%" 2>&1
echo [3/3] NOTA: aplica al reiniciar el driver (reinicio del equipo) >> "%OUT%"
echo. >> "%OUT%"
echo RESULTADO: TODO OK, REINICIE EL EQUIPO para aplicar >> "%OUT%"
type "%OUT%"
echo.
pause
endlocal
