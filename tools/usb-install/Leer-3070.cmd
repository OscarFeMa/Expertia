@echo off
setlocal
cd /d "%~dp0"
set "OUT=%~dp03070-id.txt"
set "JSON=%~dp03070-id.json"
echo Recogiendo datos del equipo para acceso Expertia (no cambia nada) ...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$u=$env:USERNAME; $h=$env:COMPUTERNAME;" ^
  "$isAdmin=[bool]([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator);" ^
  "$ad=Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | Select-Object Name,MacAddress,LinkSpeed;" ^
  "$ips=Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.AddressState -eq 'Preferred' -and $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*'} | Select-Object IPAddress,InterfaceAlias;" ^
  "$os=(Get-CimInstance Win32_OperatingSystem).Caption;" ^
  "$gpu=''; try{$gpu=(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>$null) -join '; '}catch{};" ^
  "$py=''; try{$py=[string](py -3.11 --version 2>$null)}catch{}; if(-not $py){try{$py=[string](python --version 2>$null)}catch{}};" ^
  "$diskC=''; try{$diskC=[math]::Round((Get-Volume -DriveLetter C).SizeRemaining/1GB,1)}catch{};" ^
  "$obj=[ordered]@{user=$u;host=$h;is_admin=$isAdmin;os=$os;adapters=$ad;ips=$ips;gpu=$gpu;python=$py;diskC_freeGB=$diskC;date=(Get-Date -Format o)};" ^
  "$obj|ConvertTo-Json -Depth 4|Set-Content '%JSON%' -Encoding utf8;" ^
  "'usuario='+$u;'host='+$h;'admin='+$isAdmin | Set-Content '%OUT%' -Encoding utf8;" ^
  "'Lee este fichero y devuelve el USB' | Out-Null;"
if errorlevel 1 echo FALLO al recoger datos & pause & exit /b 1
echo.
echo Datos guardados en:
echo   %OUT%
echo   %JSON%
echo.
type "%OUT%"
echo.
echo Devuelve el USB al PC principal. No se ha cambiado nada en este equipo.
echo.
pause
endlocal
