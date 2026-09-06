param([int]$StaleMin = 15, [int]$IntervalS = 120)
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
    $py = Get-Process python* -ErrorAction SilentlyContinue | Where-Object { $_.WorkingSet64 -gt 500MB }
    if ($stale -and -not $py) {
      try {
        $t = nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,memory.used --format=csv,noheader 2>$null
        WLog "forense muerte: GPU $t"
      } catch {}
      try {
        $e = Get-ChildItem (Join-Path $TrainRoot "logs\train_*.err.log") | Sort-Object LastWriteTime | Select-Object -Last 1
        if ($e) { WLog ("ultima linea: " + (Get-Content $e.FullName -Tail 1 | Out-String).Trim()) }
      } catch {}
      WLog "MUERTO (stale, sin proceso). Relanzando con resume..."
      $env:TRAIN_STATUS_FILE = Join-Path $TrainRoot "logs\train_status.json"
      Start-Process -FilePath (Join-Path $TrainRoot "python311\python.exe") -ArgumentList "C:\training\train_expertia_math.py --model C:\training\base\phi-4-mini-reasoning --train C:\training\datasets\expertia-math-puro.jsonl --out C:\training\adapters\expertia-math-r16 --offload C:\training\offload --epochs 3 --seq-len 2048 --batch 1 --accum 16 --bf16 --no-offload --save-steps 200" -RedirectStandardOutput (Join-Path $TrainRoot ("logs\train_wd_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))) -WindowStyle Hidden
      WLog "relanzado"
    }
  } catch {
    WLog ("ERROR vigilancia: " + $_.Exception.Message)
  }
  Start-Sleep -Seconds $IntervalS
}
