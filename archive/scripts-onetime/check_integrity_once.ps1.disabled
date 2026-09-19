$log="C:\Users\usuario\AppData\Local\Temp\opencode\fase2c_integrity.log"
$tail=Get-Content $log -ErrorAction SilentlyContinue | Select-Object -Last 5
if($tail -match '^\s*ok\s*$'){
  $py="C:\Users\usuario\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
  $repo="D:\proyectos\expertia\incubator-root"
  $running=Get-CimInstance Win32_Process -Filter "Name like '%python%'" | Where-Object { $_.CommandLine -like "*orchestrator*" }
  if(-not $running){
    Start-Process -FilePath $py -ArgumentList "orchestrator.py --phase web" -WorkingDirectory $repo -WindowStyle Hidden
    Start-Sleep -Seconds 5
    Start-Process -FilePath $py -ArgumentList "query_api.py" -WorkingDirectory $repo -WindowStyle Hidden
    Start-Process -FilePath $py -ArgumentList "tools/watchdog.py" -WorkingDirectory $repo -WindowStyle Hidden
  }
}
