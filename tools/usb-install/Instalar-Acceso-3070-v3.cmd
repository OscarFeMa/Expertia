@echo off
setlocal
cd /d "%~dp0"
set "LOG=%TEMP%\expertia-acceso-3070-v3.log"
echo [%date% %time%] Acceso Expertia 3070 v3 offline > "%LOG%"
net session >nul 2>&1
if errorlevel 1 echo EJECUTE COMO ADMINISTRADOR (clic derecho) & pause & exit /b 1
set "ZIP=%~dp0payload\redist\OpenSSH-Win64.zip"
if not exist "%ZIP%" set "ZIP=%~dp0OpenSSH-Win64.zip"
if not exist "%ZIP%" echo FALTA OpenSSH-Win64.zip junto a este .cmd & pause & exit /b 1

echo [1/6] Extrayendo OpenSSH portable ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "if(Test-Path 'C:\Program Files\OpenSSH\sshd.exe'){Write-Output 'ya instalado'}else{if(Test-Path 'C:\Program Files\OpenSSH-Win64\sshd.exe'){Rename-Item 'C:\Program Files\OpenSSH-Win64' 'C:\Program Files\OpenSSH'}else{Expand-Archive -Path '%ZIP%' -DestinationPath 'C:\Program Files\OpenSSH-TMP' -Force; Move-Item 'C:\Program Files\OpenSSH-TMP\OpenSSH-Win64' 'C:\Program Files\OpenSSH'}; powershell -NoProfile -ExecutionPolicy Bypass -File 'C:\Program Files\OpenSSH\install-sshd.ps1'; Remove-Item 'C:\Program Files\OpenSSH-TMP' -Recurse -Force -ErrorAction SilentlyContinue}" >> "%LOG%" 2>&1
if not exist "C:\Program Files\OpenSSH\sshd.exe" echo FALLO extraccion, revise "%LOG%" & pause & exit /b 1
echo      OK

echo [2/6] Servicio sshd ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Service sshd; Set-Service -Name sshd -StartupType 'Automatic'; Start-Service ssh-agent -ErrorAction SilentlyContinue; Set-Service -Name ssh-agent -StartupType 'Automatic' -ErrorAction SilentlyContinue; (Get-Service sshd).Status" >> "%LOG%" 2>&1

echo [3/6] Firewall 22 solo LAN ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$r=Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue; if(-not $r){New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 -RemoteAddress 192.168.1.0/24 | Out-Null}else{Set-NetFirewallAddressFilter -Name 'OpenSSH-Server-In-TCP' -RemoteAddress 192.168.1.0/24}" >> "%LOG%" 2>&1

echo [4/6] Shell + clave (SID, vale en cualquier idioma) ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "New-ItemProperty -Path 'HKLM:\SOFTWARE\OpenSSH' -Name DefaultShell -Value 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -PropertyType String -Force | Out-Null; New-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System' -Name LocalAccountTokenFilterPolicy -Value 1 -PropertyType DWord -Force | Out-Null; Restart-Service sshd; Start-Sleep 2" >> "%LOG%" 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$k='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGogcxnaZ3xhz8B3KP9offEsipuuUCzS0KsTMhzaDztY expertia-sobremesa'; $f=\"$env:ProgramData\ssh\administrators_authorized_keys\"; $c=if(Test-Path $f){Get-Content $f -Raw}else{''}; if($c -notmatch 'expertia-sobremesa'){Add-Content -Force -Path $f -Value $k}; icacls.exe $f /inheritance:r /grant '*S-1-5-32-544:F' /grant 'SYSTEM:F' | Out-Null; 'authkeys lineas='+((Get-Content $f|Measure-Object -Line).Lines)" >> "%LOG%" 2>&1

echo [5/6] Verificando puerto 22 ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ok=$false; for($i=0;$i -lt 6;$i++){if(Get-NetTCPConnection -LocalPort 22 -State Listen -ErrorAction SilentlyContinue){$ok=$true;break}; Start-Sleep 5}; if(-not $ok){exit 1}" >nul 2>&1
if errorlevel 1 echo FALLO: 22 no escucha, revise "%LOG%" & pause & exit /b 1
echo      OK puerto 22 escuchando

echo [6/6] Share de estado (opcional, 2 min max) ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$j=Start-Job -ScriptBlock { New-Item -ItemType Directory -Path C:\training\out-share -Force | Out-Null }; if(Wait-Job $j -Timeout 120){'share-dir OK'}else{'share TIMEOUT, omitido'}; Remove-Job $j -Force -ErrorAction SilentlyContinue" >> "%LOG%" 2>&1

echo.
echo ACCESO SSH LISTO:
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ips=(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.AddressState -eq 'Preferred' -and $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*'} | ForEach-Object {$_.IPAddress}); Write-Host ('  SSH: '+$env:USERNAME+'@'+($ips|Select-Object -First 1))"
echo Log: %LOG%
echo.
pause
endlocal
