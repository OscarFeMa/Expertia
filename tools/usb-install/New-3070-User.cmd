@echo off
setlocal EnableDelayedExpansion
set "OUT=%TEMP%\new-user-3070.txt"
set "OK=1"
net session >nul 2>&1
if errorlevel 1 echo EJECUTE COMO ADMINISTRADOR (clic derecho) & pause & exit /b 1
echo Acceso Expertia 3070 (solo EXE nativos) ...
echo [%date% %time%] inicio > "%OUT%"
echo [1/6] WinRM >> "%OUT%"
winrm quickconfig -q >> "%OUT%" 2>&1
sc config WinRM start= auto >> "%OUT%" 2>&1
echo [2/6] usuario >> "%OUT%"
net user expertia >nul 2>&1
if not errorlevel 1 echo Y | net user expertia /delete >> "%OUT%" 2>&1
net user expertia "Rk4YU3gL219FmauxjJ8i" /add /expires:never /passwordchg:no >> "%OUT%" 2>&1
if errorlevel 1 echo FALLO crear usuario >> "%OUT%" & set "OK=0" & goto fin
wmic useraccount where "name='expertia'" set PasswordExpires=FALSE >> "%OUT%" 2>&1
echo [3/6] carpeta >> "%OUT%"
mkdir "C:\training" 2>nul
icacls "C:\training" /grant "expertia:(OI)(CI)F" >> "%OUT%" 2>&1
echo [4/6] clave SSH >> "%OUT%"
mkdir "C:\Users\expertia\.ssh" 2>nul
echo ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGogcxnaZ3xhz8B3KP9offEsipuuUCzS0KsTMhzaDztY expertia-sobremesa>"C:\Users\expertia\.ssh\authorized_keys"
icacls "C:\Users\expertia\.ssh\authorized_keys" /inheritance:r /grant "SYSTEM:F" /grant "*S-1-5-32-544:F" /grant "expertia:F" >> "%OUT%" 2>&1
icacls "C:\Users\expertia\.ssh" /inheritance:r /grant "SYSTEM:(OI)(CI)F" /grant "*S-1-5-32-544:(OI)(CI)F" /grant "expertia:(OI)(CI)F" >> "%OUT%" 2>&1
"C:\Program Files\OpenSSH\ssh-keygen.exe" -l -f "C:\Users\expertia\.ssh\authorized_keys" >> "%OUT%" 2>&1
echo [5/6] autotest SSH local >> "%OUT%"
ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10 expertia@localhost "echo SELFTEST_OK" >> "%OUT%" 2>&1
if errorlevel 1 echo AVISO autotest SSH (WinRM sigue valiendo) >> "%OUT%"
echo [6/6] autotest WinRM local >> "%OUT%"
winrm identify -r:http://localhost:5985/wsman -u:localhost\expertia -p:Rk4YU3gL219FmauxjJ8i -auth:negotiate >> "%OUT%" 2>&1
if errorlevel 1 echo FALLO autotest WinRM >> "%OUT%" & set "OK=0" & goto fin
for /f "tokens=2 delims=, " %%A in ('"wmic nicconfig where IPEnabled=TRUE get IPAddress /value 2>nul | findstr 192.168.1."') do set "IP=%%~A"
echo listo: expertia@%IP% via WinRM 5985 --- password conocido por PC principal >> "%OUT%"
:fin
echo. >> "%OUT%"
if "%OK%"=="1" (echo RESULTADO: TODO OK >> "%OUT%") else (echo RESULTADO: REVISAR FALLOS ARRIBA >> "%OUT%")
echo.
type "%OUT%"
echo.
echo Copiando resultado al USB ...
copy /Y "%OUT%" "%~dp0new-user-3070.txt" >nul 2>&1
if errorlevel 1 echo AVISO: no se pudo copiar al USB, haga foto a lo de arriba
echo.
pause
endlocal
