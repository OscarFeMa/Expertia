$ErrorActionPreference = "Continue"
$repo = "D:\proyectos\expertia\incubator-root"
$trainRoot = "D:\proyectos\expertia\training"
$stateFile = Join-Path $repo "pipeline_state.json"
$py = "C:\Users\usuario\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
$trainPy = Join-Path $trainRoot ".venv-train\Scripts\python.exe"
if (-not (Test-Path $trainPy)) { $trainPy = $py }
try {
  $st = Get-Content $stateFile -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json
  $pidPipe = $st.pid
} catch { $pidPipe = $null }
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like "*tools/watchdog.py*" } | ForEach-Object {
  taskkill /F /T /PID $_.ProcessId 2>&1 | Out-Null
}
Start-Sleep -Seconds 2
if ($pidPipe) { taskkill /F /T /PID $pidPipe 2>&1 | Out-Null }
Start-Sleep -Seconds 3
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like "*orchestrator.py*" -or $_.CommandLine -like "*query_api.py*" } | ForEach-Object {
  taskkill /F /T /PID $_.ProcessId 2>&1 | Out-Null
}
Start-Sleep -Seconds 3
& ollama stop phi4-mini:latest 2>&1 | Out-Null
& ollama stop gemma3:4b 2>&1 | Out-Null
& ollama stop qwen2.5-coder:3b 2>&1 | Out-Null
& ollama stop "hf.co/liodon-ai/Qwen2.5-Math-1.5B-Instruct-imatrix-GGUF:Q4_K_M" 2>&1 | Out-Null
Start-Sleep -Seconds 5
$dataset = Join-Path $trainRoot "datasets\expertia-math-puro.jsonl"
if (-not (Test-Path $dataset)) {
  & $py (Join-Path $repo "tools\build_expertia_math_dataset.py") --limit 50000 --out $dataset
}
$logDir = Join-Path $trainRoot "logs"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logDir "train_$stamp.log"
& $trainPy (Join-Path $trainRoot "train_expertia_math.py") --train $dataset --out (Join-Path $trainRoot "adapters\expertia-math-r16") --offload (Join-Path $trainRoot "offload") --epochs 3 --seq-len 1024 --batch 1 --accum 16 > $logFile 2>&1
