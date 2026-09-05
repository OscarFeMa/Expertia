@echo off
setlocal
cd /d "%~dp0"
set "LOG=%TEMP%\expertia-acceso-3070-v2.log"
echo [%date% %time%] Acceso Expertia 3070 v2 > "%LOG%"
net session >nul 2>&1
if errorlevel 1 echo EJECUTE COMO ADMINISTRADOR (clic derecho) & pause & exit /b 1

echo [1/6] OpenSSH Server ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$c=Get-WindowsCapability -Online | Where-Object Name -like 'OpenSSH.Server*'; if($c.State -ne 'Installed'){Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 | Out-Null}; (Get-WindowsCapability -Online | Where-Object Name -like 'OpenSSH.Server*').State" >> "%LOG%" 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "if((Get-WindowsCapability -Online | Where-Object Name -like 'OpenSSH.Server*').State -ne 'Installed'){exit 1}" >nul 2>&1
if errorlevel 1 echo FALLO: no se pudo instalar OpenSSH (revise "%LOG%") & pause & exit /b 1
echo      OK instalado

echo [2/6] Servicio sshd ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Service sshd; Set-Service -Name sshd -StartupType 'Automatic'; (Get-Service sshd).Status" >> "%LOG%" 2>&1
echo [3/6] Firewall 22 solo LAN ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$r=Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue; if(-not $r){New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 -RemoteAddress 192.168.1.0/24 | Out-Null}else{Set-NetFirewallAddressFilter -Name 'OpenSSH-Server-In-TCP' -RemoteAddress 192.168.1.0/24}" >> "%LOG%" 2>&1

echo [4/6] Shell PowerShell + clave ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "New-ItemProperty -Path 'HKLM:\SOFTWARE\OpenSSH' -Name DefaultShell -Value 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -PropertyType String -Force | Out-Null; New-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System' -Name LocalAccountTokenFilterPolicy -Value 1 -PropertyType DWord -Force | Out-Null; Restart-Service sshd; Start-Sleep 2; (Get-Service sshd).Status" >> "%LOG%" 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$k='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGogcxnaZ3xhz8B3KP9offEsipuuUCzS0KsTMhzaDztY expertia-sobremesa'; $f=\"$env:ProgramData\ssh\administrators_authorized_keys\"; $c=if(Test-Path $f){Get-Content $f -Raw}else{''}; if($c -notmatch 'expertia-sobremesa'){Add-Content -Force -Path $f -Value $k}; icacls.exe $f /inheritance:r /grant 'Administrators:F' /grant 'SYSTEM:F' | Out-Null; 'authkeys lineas='+((Get-Content $f|Measure-Object -Line).Lines)" >> "%LOG%" 2>&1

echo [5/6] Verificando puerto 22 ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ok=$false; for($i=0;$i -lt 6;$i++){if(Get-NetTCPConnection -LocalPort 22 -State Listen -ErrorAction SilentlyContinue){$ok=$true;break}; Start-Sleep 5}; if(-not $ok){exit 1}" >nul 2>&1
if errorlevel 1 echo AVISO: puerto 22 no escucha, revise "%LOG%" & pause & exit /b 1
echo      OK puerto 22 escuchando

echo [6/6] Share de estado (opcional, con limite 2 min) ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$j=Start-Job -ScriptBlock { New-Item -ItemType Directory -Path C:\training\out-share -Force | Out-Null; icacls C:\training\out-share /inheritance:r | Out-Null; icacls C:\training\out-share /grant:r 'SYSTEM:(OI)(CI)F' 'Administradores:(OI)(CI)F' | Out-Null; try{net user trainro /delete | Out-Null}catch{}; net user trainro 'ExpertiaRO-3070-cambiar' /add /expires:never /passwordchg:no | Out-Null; New-SmbShare -Name ExpertiaTrain -Path C:\training\out-share -ReadAccess trainro -FolderEnumerationMode AccessBased -EncryptData $true -Description 'Estado entreno ExpertiaMath RO' -Force | Out-Null }; if(Wait-Job $j -Timeout 120){Receive-Job $j | Out-Null; 'share OK'}else{Stop-Job $j -ErrorAction SilentlyContinue; 'share TIMEOUT, omitido'}; Remove-Job $j -Force -ErrorAction SilentlyContinue" >> "%LOG%" 2>&1
echo      paso 6/6 terminado (ver log si el share quedo pendiente)

echo.
echo ACCESO SSH LISTO. Datos para el PC principal:
powershell -NoProfile -ExecutionPolicy Bypass -Command "$macs=(Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | ForEach-Object {$_.MacAddress}); $ips=(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.AddressState -eq 'Preferred' -and $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*'} | ForEach-Object {$_.IPAddress}); Write-Host \"  MAC: $($macs -join ' / ')\"; Write-Host \"  IP: $($ips -join ' / ')\"; Write-Host ('  SSH: '+$env:USERNAME+'@'+($ips|Select-Object -First 1))"
echo Log: %LOG%
echo.
pause
endlocal
