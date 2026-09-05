@echo off
setlocal EnableDelayedExpansion
set "OUT=%TEMP%\new-user-3070.txt"
set "OK=1"
set "PW=Rk4YU3gL219FmauxjJ8i"
net session >nul 2>&1
if errorlevel 1 echo EJECUTE COMO ADMINISTRADOR (clic derecho) & pause & exit /b 1
echo Habilitando acceso Expertia (WinRM + usuario expertia) ...
echo [%date% %time%] inicio > "%OUT%"
echo [1/7] WinRM >> "%OUT%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Enable-PSRemoting -Force -SkipNetworkProfileCheck" >> "%OUT%" 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "Set-NetFirewallRule -Name 'WINRM-HTTP-In-TCP' -RemoteAddress 192.168.1.0/24 -ErrorAction SilentlyContinue; Set-Service WinRM -StartupType Automatic" >> "%OUT%" 2>&1
echo [2/7] usuario >> "%OUT%"
net user expertia >nul 2>&1
if not errorlevel 1 echo Y | net user expertia /delete >> "%OUT%" 2>&1
net user expertia "%PW%" /add /expires:never /passwordchg:no >> "%OUT%" 2>&1
if errorlevel 1 echo FALLO crear usuario >> "%OUT%" & set "OK=0" & goto fin
powershell -NoProfile -ExecutionPolicy Bypass -Command "Set-LocalUser -Name expertia -PasswordNeverExpires $true -UserMayChangePassword $false" >> "%OUT%" 2>&1
echo [3/7] carpeta >> "%OUT%"
mkdir "C:\training" 2>nul
icacls "C:\training" /grant "expertia:(OI)(CI)F" >> "%OUT%" 2>&1
echo [4/6] clave SSH (se mantiene por si acaso) >> "%OUT%"
mkdir "C:\Users\expertia\.ssh" 2>nul
echo ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGogcxnaZ3xhz8B3KP9offEsipuuUCzS0KsTMhzaDztY expertia-sobremesa>"C:\Users\expertia\.ssh\authorized_keys"
icacls "C:\Users\expertia\.ssh\authorized_keys" /inheritance:r /grant "SYSTEM:F" /grant "*S-1-5-32-544:F" /grant "expertia:F" >> "%OUT%" 2>&1
icacls "C:\Users\expertia\.ssh" /inheritance:r /grant "SYSTEM:(OI)(CI)F" /grant "*S-1-5-32-544:(OI)(CI)F" /grant "expertia:(OI)(CI)F" >> "%OUT%" 2>&1
echo [5/7] autotest WinRM local >> "%OUT%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=ConvertTo-SecureString '%PW%' -AsPlainText -Force; $c=New-Object PSCredential('localhost\expertia',$s); Invoke-Command -ComputerName localhost -Credential $c -ScriptBlock { hostname } -ErrorAction Stop" >> "%OUT%" 2>&1
if errorlevel 1 echo FALLO autotest WinRM >> "%OUT%" & set "OK=0" & goto fin
echo [6/7] red >> "%OUT%"
for /f "tokens=2 delims=, " %%A in ('"wmic nicconfig where IPEnabled=TRUE get IPAddress /value 2>nul | findstr 192.168.1."') do set "IP=%%~A"
echo listo: expertia@%IP% via WinRM 5985 >> "%OUT%"
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
