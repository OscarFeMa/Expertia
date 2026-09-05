@echo off
setlocal
cd /d "%~dp0"
set "LOG=%TEMP%\expertia-acceso-3070.log"
echo [%date% %time%] Acceso Expertia 3070 > "%LOG%"
net session >nul 2>&1
if errorlevel 1 echo EJECUTE COMO ADMINISTRADOR (clic derecho) & pause & exit /b 1

echo [1/7] Instalando OpenSSH Server ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0" >> "%LOG%" 2>&1
echo [2/7] Servicio sshd automatico ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Service sshd; Set-Service -Name sshd -StartupType 'Automatic'" >> "%LOG%" 2>&1

echo [3/7] Firewall puerto 22 solo LAN ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$r=Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue; if(-not $r){New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 -RemoteAddress 192.168.1.0/24 | Out-Null}else{Set-NetFirewallAddressFilter -Name 'OpenSSH-Server-In-TCP' -RemoteAddress 192.168.1.0/24}" >> "%LOG%" 2>&1

echo [4/7] Shell PowerShell + token admin completo ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "New-ItemProperty -Path 'HKLM:\SOFTWARE\OpenSSH' -Name DefaultShell -Value 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -PropertyType String -Force | Out-Null; New-ItemProperty -Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System' -Name LocalAccountTokenFilterPolicy -Value 1 -PropertyType DWord -Force | Out-Null; Restart-Service sshd" >> "%LOG%" 2>&1

echo [5/7] Desplegando clave autorizada ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$k='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGogcxnaZ3xhz8B3KP9offEsipuuUCzS0KsTMhzaDztY expertia-sobremesa'; $f=\"$env:ProgramData\ssh\administrators_authorized_keys\"; Add-Content -Force -Path $f -Value $k; icacls.exe $f /inheritance:r /grant 'Administrators:F' /grant 'SYSTEM:F' | Out-Null" >> "%LOG%" 2>&1

echo [6/7] Share de estado solo-lectura ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "New-Item -ItemType Directory -Path C:\training\out-share -Force | Out-Null; icacls C:\training\out-share /inheritance:r | Out-Null; icacls C:\training\out-share /grant:r 'SYSTEM:(OI)(CI)F' 'Administradores:(OI)(CI)F' | Out-Null; try{net user trainro /delete | Out-Null}catch{}; net user trainro \"ExpertiaRO-3070-cambiar\" /add /expires:never /passwordchg:no | Out-Null; New-SmbShare -Name ExpertiaTrain -Path C:\training\out-share -ReadAccess trainro -FolderEnumerationMode AccessBased -EncryptData $true -Description 'Estado entreno ExpertiaMath RO' -Force | Out-Null; New-NetFirewallRule -DisplayName 'SMB ExpertiaTrain RO' -Direction Inbound -Protocol TCP -LocalPort 445 -RemoteAddress 192.168.1.0/24 -Action Allow -Profile Private -ErrorAction SilentlyContinue | Out-Null" >> "%LOG%" 2>&1

echo [7/7] Tarea publicacion cada 15 min ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Copy-Item '%~dp0payload\scripts\Publish-TrainStatus.ps1' 'C:\training\Publish-TrainStatus.ps1' -Force -ErrorAction SilentlyContinue; schtasks /Create /TN 'ExpertiaPublishTrain' /TR 'powershell -NoProfile -ExecutionPolicy Bypass -File C:\training\Publish-TrainStatus.ps1' /SC MINUTE /MO 15 /RU SYSTEM /F | Out-Null; schtasks /Run /TN 'ExpertiaPublishTrain' | Out-Null" >> "%LOG%" 2>&1

echo.
echo ACCESO LISTO. Datos para el PC principal:
powershell -NoProfile -ExecutionPolicy Bypass -Command "$macs=(Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | ForEach-Object {$_.MacAddress}); $ips=(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.AddressState -eq 'Preferred' -and $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*'} | ForEach-Object {$_.IPAddress}); Write-Host \"  MAC: $($macs -join ' / ')\"; Write-Host \"  IP: $($ips -join ' / ')\"; Write-Host ('  SSH: '+$env:USERNAME+'@'+($ips|Select-Object -First 1))"
echo Log: %LOG%
echo.
pause
endlocal
