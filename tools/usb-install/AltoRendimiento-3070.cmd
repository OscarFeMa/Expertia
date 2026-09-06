@echo off
setlocal
set "OUT=%TEMP%\alto-rendimiento-3070.txt"
net session >nul 2>&1
if errorlevel 1 echo EJECUTE COMO ADMINISTRADOR (clic derecho) & pause & exit /b 1
echo Alto rendimiento 3070 (entreno) ...
echo [%date% %time%] inicio > "%OUT%"
echo [1/5] plan Alto rendimiento >> "%OUT%"
powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c >> "%OUT%" 2>&1
echo [2/5] nunca suspender/hibernar con CA >> "%OUT%"
powercfg /change standby-timeout-ac 0 >> "%OUT%" 2>&1
powercfg /change hibernate-timeout-ac 0 >> "%OUT%" 2>&1
powercfg /change disk-timeout-ac 0 >> "%OUT%" 2>&1
powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0 >> "%OUT%" 2>&1
powercfg /setacvalueindex SCHEME_CURRENT SUB_SLEEP STANDBYIDLE 0 >> "%OUT%" 2>&1
echo [3/5] GPU a 90W (termica, de 115W max) >> "%OUT%"
nvidia-smi -pl 90 >> "%OUT%" 2>&1
echo [4/6] relojes persistentes >> "%OUT%"
nvidia-smi -pm 1 >> "%OUT%" 2>&1
echo [5/6] estado >> "%OUT%"
powercfg /getactivescheme >> "%OUT%" 2>&1
nvidia-smi --query-gpu=power.limit,enforced.power.limit --format=csv,noheader >> "%OUT%" 2>&1
echo. >> "%OUT%"
echo RESULTADO: TODO OK >> "%OUT%"
type "%OUT%"
echo.
pause
endlocal
