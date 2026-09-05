@echo off
setlocal
cd /d "%~dp0"
set "OUT=%~dp03070-diag.txt"
echo Diagnostico acceso 3070 (solo lee, no cambia nada) ...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$o=@();" ^
  "$o+='== windows =='; try{$o+=((Get-CimInstance Win32_OperatingSystem).Caption+' '+(Get-CimInstance Win32_OperatingSystem).BuildNumber)}catch{$o+='ERR os: '+$_};" ^
  "$o+='== capability =='; try{$o+=((Get-WindowsCapability -Online | Where-Object Name -like 'OpenSSH.Server*') | ForEach-Object {$_.Name+' = '+$_.State}) -join '; '}catch{$o+='ERR capability: '+$_};" ^
  "$o+='== servicio sshd =='; try{$s=Get-Service sshd -ErrorAction Stop; $o+='status='+$s.Status+'; startup='+$s.StartType}catch{$o+='NO existe servicio sshd'};" ^
  "$o+='== firewall =='; try{$r=Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction Stop; $o+='rule enabled='+$r.Enabled; $o+='remote='+(($r|Get-NetFirewallAddressFilter).RemoteAddress -join ',')}catch{$o+='SIN regla firewall'};" ^
  "$o+='== puerto 22 =='; try{$l=Get-NetTCPConnection -LocalPort 22 -State Listen -ErrorAction Stop; $o+='ESCUCHANDO pid='+($l.OwningProcess -join ',')}catch{$o+='22 cerrado'};" ^
  "$o+='== clave =='; $f=\"$env:ProgramData\ssh\administrators_authorized_keys\"; if(Test-Path $f){$o+='authkeys existe, lineas='+((Get-Content $f|Measure-Object -Line).Lines)}else{$o+='authkeys NO existe'};" ^
  "$o+='== log instalador (ultimas 15) =='; $lg=\"$env:TEMP\expertia-acceso-3070.log\"; if(Test-Path $lg){$o+=Get-Content $lg -Tail 15}else{$o+='sin log'};" ^
  "$o|Set-Content '%OUT%' -Encoding utf8;"
if errorlevel 1 echo FALLO diagnostico & pause & exit /b 1
echo.
type "%OUT%"
echo.
echo Guardado en %OUT% - devuelve el USB.
echo.
pause
endlocal
