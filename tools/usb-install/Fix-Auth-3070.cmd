@echo off
setlocal
cd /d "%~dp0"
set "OUT=%~dp0fix-auth-3070.txt"
net session >nul 2>&1
if errorlevel 1 echo EJECUTE COMO ADMINISTRADOR (clic derecho) & pause & exit /b 1
echo Reparando autorizacion SSH (idempotente) ...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$o=@();" ^
  "$k='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGogcxnaZ3xhz8B3KP9offEsipuuUCzS0KsTMhzaDztY expertia-sobremesa';" ^
  "$f=\"$env:ProgramData\ssh\administrators_authorized_keys\";" ^
  "[IO.File]::WriteAllText($f, $k+\"`r`n\");" ^
  "$o+='escrita 1 linea ASCII sin BOM';" ^
  "takeown.exe /F $f /A | Out-Null;" ^
  "icacls.exe $f /inheritance:r /grant '*S-1-5-32-544:F' /grant 'SYSTEM:F' | Out-Null;" ^
  "$o+='owner='+(Get-Acl $f).Owner;" ^
  "$o+=(icacls.exe $f);" ^
  "try{$o+='fingerprint: '+(& 'C:\Program Files\OpenSSH\ssh-keygen.exe' -l -f $f 2>&1 | Out-String).Trim()}catch{};" ^
  "Restart-Service sshd; Start-Sleep 3;" ^
  "$o+='sshd='+(Get-Service sshd).Status;" ^
  "try{$ev=Get-WinEvent -LogName 'OpenSSH/Operational' -MaxEvents 30 -ErrorAction Stop; $o+='--- eventos (todos los niveles, ultimos 30) ---'; $o+=$ev.Message}catch{$o+='sin log operacional'};" ^
  "$o|Set-Content '%OUT%' -Encoding utf8;"
echo.
type "%OUT%"
echo.
echo Guardado en %OUT% - devuelve el USB.
echo.
pause
endlocal
