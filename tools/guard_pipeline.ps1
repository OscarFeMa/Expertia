$ErrorActionPreference = "Continue"
$repo = Split-Path -Parent $PSScriptRoot
$log = Join-Path $repo "logs\guard.log"
function GLog($m) { Add-Content $log "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m" }
$py = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -like "*orchestrator.py*" -and $_.CommandLine -like "*--phase*" }
$lastLog = Get-ChildItem (Join-Path $repo "logs\pipeline_*.log") -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
$ageMin = if ($lastLog) { ((Get-Date) - $lastLog.LastWriteTime).TotalMinutes } else { 9999 }
if (-not $py -and $ageMin -gt 20) {
  GLog "MUERTO (sin proceso, log hace $([int]$ageMin)min). Relanzando completo..."
  $proc = Start-Process -FilePath "C:\Users\usuario\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe" `
    -ArgumentList "orchestrator.py", "--phase", "web", "--parallel", "2" `
    -WorkingDirectory $repo -WindowStyle Hidden -PassThru
  Start-Sleep -Seconds 5
  try {
    $stPath = Join-Path $repo "pipeline_state.json"
    $st = @{}
    if (Test-Path $stPath) { $st = Get-Content $stPath -Raw -Encoding utf8 | ConvertFrom-Json }
    $st | Add-Member -NotePropertyName "pid" -NotePropertyValue $proc.Id -Force
    $st | Add-Member -NotePropertyName "mode" -NotePropertyValue "web" -Force
    $st | Add-Member -NotePropertyName "start_time" -NotePropertyValue ([DateTimeOffset]::UtcNow.ToUnixTimeSeconds()) -Force
    $st | ConvertTo-Json -Compress | Set-Content $stPath -Encoding utf8
    GLog "relanzado pid=$($proc.Id) (pipeline_state.json actualizado)"
  } catch { GLog "relanzado pid=$($proc.Id) (WARN state: $($_.Exception.Message))" }
} else {
  $n = @($py).Count
  GLog "ok (procesos=$n, log hace $([int]$ageMin)min)"
}
# Early warning: Ollama sin GPU (v0.34.x rompio discovery en GTX 1660 el 2026-09-14).
# Si todo corre en CPU, la destilacion pasa de ~50 a ~9 tok/s y aparecen timeouts.
try {
  $psOut = & "C:\Users\usuario\AppData\Local\Programs\Ollama\ollama.exe" ps 2>$null | Out-String
  if ($psOut -match "100% CPU") { GLog "ALERTA GPU: modelo en CPU (revisar Ollama/discovery)" }
} catch {}
