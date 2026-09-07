param([int]$StaleMin = 10, [int]$IntervalS = 120)
$TrainRoot = "C:\training"
$Log = Join-Path $TrainRoot "logs\watch-train.log"
function WLog($m) { Add-Content $Log "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m" }
WLog "watchdog entreno iniciado (stale ${StaleMin}min)"
while ($true) {
  try {
    $sf = Join-Path $TrainRoot "logs\train_status.json"
    $stale = $true
    if (Test-Path $sf) {
      $age = ((Get-Date) - (Get-ChildItem $sf).LastWriteTime).TotalMinutes
      $stale = $age -gt $StaleMin
    }
    $py = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*train_expertia*" }
    $done = $false
    try {
      $st = Get-Content (Join-Path $TrainRoot "logs\train_status.json") -Raw -Encoding utf8 | ConvertFrom-Json
      $done = $st.phase -eq "done"
    } catch {}
    if ($done) {
      WLog "ENTRENO COMPLETADO. Evaluando base vs adapter..."
      try {
        & (Join-Path $TrainRoot "python311\python.exe") (Join-Path $TrainRoot "eval_expertia_math.py") --model (Join-Path $TrainRoot "base\phi-4-mini-reasoning") --val (Join-Path $TrainRoot "datasets\expertia-math-puro_val.jsonl") --max-samples 500 --out (Join-Path $TrainRoot "logs\eval_base.json")
        WLog "eval base OK"
      } catch { WLog ("eval base FALLO: " + $_.Exception.Message) }
      try {
        & (Join-Path $TrainRoot "python311\python.exe") (Join-Path $TrainRoot "eval_expertia_math.py") --model (Join-Path $TrainRoot "base\phi-4-mini-reasoning") --adapter (Join-Path $TrainRoot "adapters\expertia-math-r16") --val (Join-Path $TrainRoot "datasets\expertia-math-puro_val.jsonl") --max-samples 500 --out (Join-Path $TrainRoot "logs\eval_adapter.json")
        WLog "eval adapter OK"
      } catch { WLog ("eval adapter FALLO: " + $_.Exception.Message) }
      WLog "Evaluaciones listas. Esperando promocion manual."
      Start-Sleep -Seconds 3600
      continue
    }
    $justLaunched = $false
    try {
      $sl = Get-ChildItem (Join-Path $TrainRoot "logs\train_status.json") -ErrorAction Stop
      $justLaunched = ((Get-Date) - $sl.LastWriteTime).TotalMinutes -lt 8
    } catch {}
    try {
      $el = Get-ChildItem (Join-Path $TrainRoot "logs\train_*.err.log") | Sort-Object LastWriteTime -Descending | Select-Object -First 1
      if ($el) {
        $tail = Get-Content $el.FullName -Tail 3 | Out-String
        if ($tail -match '(\d+\.\d+)s/it') {
          $sit = [double]$Matches[1]
          if ($sit -gt 30) {
            WLog "DEGRADADO (${sit}s/it). Relanzamiento preventivo..."
            Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*train_expertia*" } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force } catch {} }
          $wait = 0
          while ($wait -lt 90) {
            $used = try { [int]((nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>$null) -replace "[^0-9]","") } catch { 9999 }
            if ($used -lt 500) { break }
            Start-Sleep -Seconds 5
            $wait += 5
          }
          }
        }
      }
    } catch {}
    $coolOk = $true
    try {
      $lf = Join-Path $TrainRoot "logs\last_relaunch.txt"
      if ((Test-Path $lf) -and (((Get-Date) - (Get-ChildItem $lf).LastWriteTime).TotalMinutes -lt 20)) { $coolOk = $false }
    } catch {}
    if ($stale -and -not $py -and -not $justLaunched -and $coolOk) {
      Start-Sleep -Seconds 20
      $py2 = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*train_expertia*" }
      if ($py2) { WLog "carrera evitada: worker aparecio durante la espera"; Start-Sleep -Seconds $IntervalS; continue }
      try {
        $t = nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,memory.used --format=csv,noheader 2>$null
        WLog "forense muerte: GPU $t"
      } catch {}
      try {
        $e = Get-ChildItem (Join-Path $TrainRoot "logs\train_*.err.log") | Sort-Object LastWriteTime | Select-Object -Last 1
        if ($e) { WLog ("ultima linea: " + (Get-Content $e.FullName -Tail 1 | Out-String).Trim()) }
      } catch {}
      WLog "MUERTO (stale, sin proceso). Relanzando con resume..."
      Set-Content (Join-Path $TrainRoot "logs\last_relaunch.txt") (Get-Date -Format o)
      $env:TRAIN_STATUS_FILE = Join-Path $TrainRoot "logs\train_status.json"
      $env:PYTHONUNBUFFERED = "1"
      $ts = Get-Date -Format "yyyyMMdd_HHmmss"
      Start-Process -FilePath (Join-Path $TrainRoot "python311\python.exe") -ArgumentList "-u C:\training\train_expertia_math.py --model C:\training\base\phi-4-mini-reasoning --train C:\training\datasets\expertia-math-puro.jsonl --out C:\training\adapters\expertia-math-r16 --offload C:\training\offload --epochs 3 --seq-len 2048 --batch 1 --accum 16 --bf16 --no-offload --save-steps 200" -RedirectStandardOutput (Join-Path $TrainRoot ("logs\train_wd_${ts}.log")) -RedirectStandardError (Join-Path $TrainRoot ("logs\train_wd_${ts}.err.log")) -WindowStyle Hidden
      WLog "relanzado"
    }
  } catch {
    WLog ("ERROR vigilancia: " + $_.Exception.Message)
  }
  Start-Sleep -Seconds $IntervalS
}
