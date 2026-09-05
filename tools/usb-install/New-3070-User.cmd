@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set "OUT=%~dp0new-user-3070.txt"
set "OK=1"
net session >nul 2>&1
if errorlevel 1 echo EJECUTE COMO ADMINISTRADOR (clic derecho) & pause & exit /b 1
echo Creando usuario local expertia (sin admin, solo entreno) ...
echo [%date% %time%] inicio > "%OUT%"
echo [1/6] dependencias >> "%OUT%"
if not exist "C:\Program Files\OpenSSH\sshd.exe" echo FALTA OpenSSH, ejecute antes Instalar-Acceso-3070-v5.cmd >> "%OUT%" & set "OK=0" & goto fin
sc query sshd | findstr /i RUNNING >nul
if errorlevel 1 echo AVISO sshd parado, intentando arrancar >> "%OUT%" & net start sshd >> "%OUT%" 2>&1
echo [2/6] usuario >> "%OUT%"
net user expertia >nul 2>&1
if not errorlevel 1 echo Y | net user expertia /delete >> "%OUT%" 2>&1
set "PW=Ex%RANDOM%%RANDOM%%RANDOM%%TIME:~6,2%"
set "PW=!PW: =0!"
set "PW=!PW::=0!"
set "PW=!PW:.=0!"
set "PW=!PW:,=0!"
net user expertia "!PW!" /add /expires:never /passwordchg:no >> "%OUT%" 2>&1
if errorlevel 1 echo FALLO crear usuario >> "%OUT%" & set "OK=0" & goto fin
net user expertia | findstr /i "Activo.*S" >nul
if errorlevel 1 echo FALLO usuario inactivo >> "%OUT%" & set "OK=0" & goto fin
echo [3/6] carpeta >> "%OUT%"
mkdir "C:\training" 2>nul
icacls "C:\training" /grant "expertia:(OI)(CI)F" >> "%OUT%" 2>&1
echo [4/6] clave >> "%OUT%"
mkdir "C:\Users\expertia\.ssh" 2>nul
echo ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGogcxnaZ3xhz8B3KP9offEsipuuUCzS0KsTMhzaDztY expertia-sobremesa>"C:\Users\expertia\.ssh\authorized_keys"
icacls "C:\Users\expertia\.ssh\authorized_keys" /inheritance:r /grant "SYSTEM:F" /grant "*S-1-5-32-544:F" /grant "expertia:F" >> "%OUT%" 2>&1
icacls "C:\Users\expertia\.ssh" /inheritance:r /grant "SYSTEM:(OI)(CI)F" /grant "*S-1-5-32-544:(OI)(CI)F" /grant "expertia:(OI)(CI)F" >> "%OUT%" 2>&1
"C:\Program Files\OpenSSH\ssh-keygen.exe" -l -f "C:\Users\expertia\.ssh\authorized_keys" >> "%OUT%" 2>&1
echo [5/6] autotest SSH local >> "%OUT%"
ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10 expertia@localhost "echo SELFTEST_OK" >> "%OUT%" 2>&1
if errorlevel 1 echo FALLO autotest local >> "%OUT%" & set "OK=0" & goto fin
echo [6/6] red >> "%OUT%"
for /f "tokens=2 delims=, " %%A in ('"wmic nicconfig where IPEnabled=TRUE get IPAddress /value 2>nul | findstr 192.168.1."') do set "IP=%%~A"
echo listo: expertia@%IP% >> "%OUT%"
:fin
echo. >> "%OUT%"
if "%OK%"=="1" (echo RESULTADO: TODO OK >> "%OUT%") else (echo RESULTADO: REVISAR FALLOS ARRIBA >> "%OUT%")
echo.
type "%OUT%"
echo.
echo Devuelve el USB con new-user-3070.txt.
echo.
pause
endlocal
