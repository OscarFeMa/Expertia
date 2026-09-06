$ErrorActionPreference = "Continue"
function json2obj($p) { Get-Content $p -Raw -Encoding utf8 | ConvertFrom-Json }
$here = Split-Path -Parent $PSCommandPath
$inc = "D:\proyectos\expertia\training\incoming_3070"
New-Item -ItemType Directory -Path $inc -Force | Out-Null
$cred = Import-Clixml (Join-Path $inc "cred.xml")
$S = New-PSSession -ComputerName 192.168.1.41 -Credential $cred -ErrorAction Stop
$copied = $false
for ($i = 0; $i -lt 3 -and -not $copied; $i++) {
  try {
    Copy-Item -FromSession $S -Path "C:\training\logs\train_status.json" -Destination (Join-Path $inc "train_status.json") -Force -ErrorAction Stop
    $copied = $true
  } catch {
    Start-Sleep -Seconds 5
  }
}
if (-not $copied) { throw "Copy train_status.json failed x3" }
try {
  $localTs = (Get-ChildItem (Join-Path $inc "train_status.json")).LastWriteTime
  $staleMin = ((Get-Date) - $localTs).TotalMinutes
  $bigPy = Invoke-Command -Session $S -ScriptBlock {
    Get-Process python* -ErrorAction SilentlyContinue | Where-Object { $_.WorkingSet64 -gt 500MB } | Select-Object -First 1 Id
  }
  if ($staleMin -gt 25 -and -not $bigPy) {
    Invoke-Command -Session $S -ScriptBlock {
      $env:TRAIN_STATUS_FILE = "C:\training\logs\train_status.json"
      Start-Process -FilePath "C:\training\python311\python.exe" -ArgumentList "C:\training\train_expertia_math.py --model C:\training\base\phi-4-mini-reasoning --train C:\training\datasets\expertia-math-puro.jsonl --out C:\training\adapters\expertia-math-r16 --offload C:\training\offload --epochs 3 --seq-len 2048 --batch 1 --accum 16 --bf16 --no-offload --save-steps 200" -RedirectStandardOutput "C:\training\logs\train_auto.log" -WindowStyle Hidden
      Start-Process -FilePath "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File C:\training\Watch-Train.ps1" -WindowStyle Hidden
    }
    Add-Content (Join-Path $inc "relaunch.log") "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') auto-relaunch (stale $([int]$staleMin)min)"
  }
} catch { }
Invoke-Command -Session $S -ScriptBlock {
  $l = Get-ChildItem C:\training\logs\train_*.log | Sort-Object LastWriteTime | Select-Object -Last 1
  $ad = "C:\training\adapters\expertia-math-r16"
  $g = try { nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.free,power.draw,power.limit,clocks.sm --format=csv,noheader,nounits 2>$null } catch { $null }
  [pscustomobject]@{
    log_tail = @($(if ($l) { Get-Content $l.FullName -Tail 25 | ForEach-Object { ([string]$_ -replace "`0", "") } }))
    log_file = $(if ($l) { $l.Name } else { $null })
    checkpoints = @()
    gpu_raw = $g
  }
} | ConvertTo-Json -Depth 3 | Set-Content (Join-Path $inc "remote_extra.json") -Encoding utf8
Remove-PSSession $S
