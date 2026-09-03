$ErrorActionPreference = "Continue"
$repo = "D:\proyectos\expertia\incubator-root"
$py = "C:\Users\usuario\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
& $py (Join-Path $repo "tools\gen_cycle_report.py") --kind training 2>&1 | Out-Null
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like "*train_expertia_math.py*" } | ForEach-Object {
  taskkill /F /T /PID $_.ProcessId 2>&1 | Out-Null
}
Start-Sleep -Seconds 3
$apiUp = $false
try {
  $r = Invoke-RestMethod -Uri "http://localhost:8011/api/health" -TimeoutSec 8
  if ($r) { $apiUp = $true }
} catch { $apiUp = $false }
if ($apiUp) {
  & $py (Join-Path $repo "tools\launcher.py") --mode web --parallel 2 --with-watchdog
} else {
  & $py (Join-Path $repo "tools\launcher.py") --mode web --parallel 2 --with-watchdog --api
}
