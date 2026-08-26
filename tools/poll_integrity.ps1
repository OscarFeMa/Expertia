param([int]$IntervalSec=7200,[int]$MaxHours=24)
$log="C:\Users\usuario\AppData\Local\Temp\opencode\fase2c_integrity.log"
$flag="C:\Users\usuario\AppData\Local\Temp\opencode\integrity_done.flag"
$start=Get-Date
while(((Get-Date)-$start).TotalHours -lt $MaxHours){
  Start-Sleep -Seconds $IntervalSec
  $alive=[bool](Get-CimInstance Win32_Process -Filter "ProcessId=25440" -ErrorAction SilentlyContinue)
  $tail=Get-Content $log -ErrorAction SilentlyContinue | Select-Object -Last 5
  $ok=$tail -match '^\s*ok\s*$'
  $ts=Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Add-Content -Path "C:\Users\usuario\AppData\Local\Temp\opencode\poll_integrity.log" -Value "[$ts] alive=$alive ok=$([bool]$ok) tail=$($tail -join '|')" -ErrorAction SilentlyContinue
  if($ok){
    Add-Content $flag "ok $ts" -ErrorAction SilentlyContinue
    $py="C:\Users\usuario\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
    $repo="D:\proyectos\expertia\incubator-root"
    Start-Process -FilePath $py -ArgumentList "orchestrator.py --phase web" -WorkingDirectory $repo -WindowStyle Hidden
    Start-Sleep -Seconds 5
    Start-Process -FilePath $py -ArgumentList "query_api.py" -WorkingDirectory $repo -WindowStyle Hidden
    Start-Process -FilePath $py -ArgumentList "tools/watchdog.py" -WorkingDirectory $repo -WindowStyle Hidden
    Add-Content "C:\Users\usuario\AppData\Local\Temp\opencode\poll_integrity.log" "[$ts] PIPELINE RELANZADO tras integrity ok" -ErrorAction SilentlyContinue
    break
  }
  if(-not $alive -and -not $ok){
    Add-Content "C:\Users\usuario\AppData\Local\Temp\opencode\poll_integrity.log" "[$ts] PID 25440 muerto sin ok -> fallback quick_check pendiente" -ErrorAction SilentlyContinue
    break
  }
}
