@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set "OUT=%~dp0new-user-3070.txt"
net session >nul 2>&1
if errorlevel 1 echo EJECUTE COMO ADMINISTRADOR (clic derecho) & pause & exit /b 1
echo Creando usuario local expertia (sin admin, solo entreno) ...
echo [%time%] inicio > "%OUT%"
set "PW=Ex%RANDOM%%RANDOM%%RANDOM%%TIME:~6,2%"
set "PW=!PW: =0!"
set "PW=!PW::=0!"
set "PW=!PW:.=0!"
set "PW=!PW:,=0!"
echo [%time%] creando usuario >> "%OUT%"
echo Y | net user expertia "!PW!" /add /expires:never /passwordchg:no >> "%OUT%" 2>&1
echo [%time%] carpeta training >> "%OUT%"
mkdir "C:\training" 2>nul
icacls "C:\training" /grant "expertia:(OI)(CI)F" >> "%OUT%" 2>&1
echo [%time%] clave ssh >> "%OUT%"
mkdir "C:\Users\expertia\.ssh" 2>nul
echo ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGogcxnaZ3xhz8B3KP9offEsipuuUCzS0KsTMhzaDztY expertia-sobremesa>"C:\Users\expertia\.ssh\authorized_keys"
icacls "C:\Users\expertia\.ssh\authorized_keys" /inheritance:r /grant "SYSTEM:F" /grant "*S-1-5-32-544:F" /grant "expertia:F" >> "%OUT%" 2>&1
icacls "C:\Users\expertia\.ssh" /inheritance:r /grant "SYSTEM:(OI)(CI)F" /grant "*S-1-5-32-544:(OI)(CI)F" /grant "expertia:(OI)(CI)F" >> "%OUT%" 2>&1
echo [%time%] fingerprint >> "%OUT%"
"C:\Program Files\OpenSSH\ssh-keygen.exe" -l -f "C:\Users\expertia\.ssh\authorized_keys" >> "%OUT%" 2>&1
echo [%time%] fin >> "%OUT%"
for /f "tokens=2 delims=, " %%A in ('"wmic nicconfig where IPEnabled=TRUE get IPAddress /value 2>nul | findstr 192.168.1."') do set "IP=%%~A"
echo listo: expertia@%IP% >> "%OUT%"
echo.
type "%OUT%"
echo.
echo Devuelve el USB con new-user-3070.txt.
echo.
pause
endlocal
