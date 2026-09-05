@echo off
setlocal
cd /d "%~dp0"
set "OUT=%~dp0new-user-3070.txt"
net session >nul 2>&1
if errorlevel 1 echo EJECUTE COMO ADMINISTRADOR (clic derecho) & pause & exit /b 1
echo Creando usuario local expertia (sin admin, solo entreno) ...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$o=@();" ^
  "$pw=-join ((48..57)+(65..90)+(97..122) | Get-Random -Count 24 | ForEach-Object {[char]$_});" ^
  "try{net user expertia /delete | Out-Null}catch{};" ^
  "net user expertia $pw /add /expires:never /passwordchg:no | Out-Null;" ^
  "Set-LocalUser -Name expertia -PasswordNeverExpires $true -UserMayChangePassword $false;" ^
  "$o+='usuario expertia creado';" ^
  "New-Item -ItemType Directory -Path C:\training -Force | Out-Null;" ^
  "icacls C:\training /grant 'expertia:(OI)(CI)F' | Out-Null;" ^
  "$o+='C:\training accesible';" ^
  "$prof=(Get-CimInstance Win32_UserProfile | Where-Object {$_.LocalPath -like '*expertia'} | Select-Object -First 1).LocalPath;" ^
  "if(-not $prof){$prof='C:\Users\expertia'};" ^
  "New-Item -ItemType Directory -Path \"$prof\.ssh\" -Force | Out-Null;" ^
  "$k='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGogcxnaZ3xhz8B3KP9offEsipuuUCzS0KsTMhzaDztY expertia-sobremesa';" ^
  "[IO.File]::WriteAllText(\"$prof\.ssh\authorized_keys\", $k+\"`r`n\");" ^
  "icacls \"$prof\.ssh\authorized_keys\" /inheritance:r /grant 'SYSTEM:F' /grant '*S-1-5-32-544:F' /grant 'expertia:F' | Out-Null;" ^
  "icacls \"$prof\.ssh\" /inheritance:r /grant 'SYSTEM:(OI)(CI)F' /grant '*S-1-5-32-544:(OI)(CI)F' /grant 'expertia:(OI)(CI)F' | Out-Null;" ^
  "try{$o+='fingerprint: '+(& 'C:\Program Files\OpenSSH\ssh-keygen.exe' -l -f \"$prof\.ssh\authorized_keys\" 2>&1 | Out-String).Trim()}catch{};" ^
  "$o+='listo: expertia@'+((Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.AddressState -eq 'Preferred' -and $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*'} | Select-Object -First 1).IPAddress);" ^
  "$o|Set-Content '%OUT%' -Encoding utf8;"
echo.
type "%OUT%"
echo.
echo Guardado en %OUT% - devuelve el USB.
echo.
pause
endlocal
