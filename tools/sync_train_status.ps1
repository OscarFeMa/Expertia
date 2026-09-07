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
    $txt = Invoke-Command -Session $S -ScriptBlock { Get-Content C:\training\logs\train_status.json -Raw -Encoding utf8 } -ErrorAction Stop
    if ($txt -match '"step"\s*:\s*\d+') {
      [IO.File]::WriteAllText((Join-Path $inc "train_status.json"), [string]$txt)
      $copied = $true
    } else {
      Start-Sleep -Seconds 5
    }
  } catch {
    Start-Sleep -Seconds 5
  }
}
if (-not $copied) { throw "Copy train_status.json failed x3" }
try {
  $repTs = Get-Content (Join-Path $inc "train_status.json") -Raw -Encoding utf8 | ConvertFrom-Json | Select-Object -ExpandProperty ts
  $origin = [datetime]'1970-01-01Z'
  $staleMin = ((Get-Date).ToUniversalTime() - $origin.AddSeconds($repTs)).TotalMinutes
  if (-not ($staleMin -ge 0) -or $staleMin -gt 10080) {
    $fileAge = ((Get-Date) - (Get-ChildItem (Join-Path $inc "train_status.json")).LastWriteTime).TotalMinutes
    if ($fileAge -ge 0 -and $fileAge -lt 10080) {
      Add-Content (Join-Path $inc "relaunch.log") "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ts futuro/ileible ($([int]$staleMin)min), usando file age $([int]$fileAge)min"
      $staleMin = $fileAge
    } else {
      $staleMin = 9999
    }
  }
  $bigPy = Invoke-Command -Session $S -ScriptBlock {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*train_expertia*" } | Select-Object -First 1 ProcessId
  }
  if ($staleMin -eq 9999) {
    Add-Content (Join-Path $inc "relaunch.log") "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ts ilegible, se reintenta en el proximo ciclo (sin relanzar)"
  }
  $coolFile = Join-Path $inc "last_relaunch.txt"
  $coolOk = $true
  try {
    if (Test-Path $coolFile) {
      $age = ((Get-Date) - (Get-ChildItem $coolFile).LastWriteTime).TotalMinutes
      if ($age -lt 20) {
        $coolOk = $false
        Add-Content (Join-Path $inc "relaunch.log") "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') cooldown activo ($([int]$age)min), se omite"
      }
    }
  } catch {}
  if ($staleMin -gt 15 -and $staleMin -lt 9999 -and -not $bigPy -and $coolOk) {
    Start-Sleep -Seconds 20
    $bigPy2 = Invoke-Command -Session $S -ScriptBlock {
      Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*train_expertia*" } | Select-Object -First 1 ProcessId
    }
    if ($bigPy2) {
      Add-Content (Join-Path $inc "relaunch.log") "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') carrera evitada (aparecio $($bigPy2.ProcessId))"
    } else {
      Set-Content $coolFile (Get-Date -Format o)
      Invoke-Command -Session $S -ScriptBlock {
        Set-Content C:\training\logs\last_relaunch.txt (Get-Date -Format o)
        Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*train_expertia*" } | ForEach-Object {
          try { Stop-Process -Id $_.ProcessId -Force } catch {}
        }
        $wait = 0
        while ($wait -lt 90) {
          $used = try { [int]((nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>$null) -replace "[^0-9]","") } catch { 9999 }
          if ($used -lt 500) { break }
          Start-Sleep -Seconds 5
          $wait += 5
        }
        $env:TRAIN_STATUS_FILE = "C:\training\logs\train_status.json"
        $env:PYTHONUNBUFFERED = "1"
        Start-Process -FilePath "C:\training\python311\python.exe" -ArgumentList "-u C:\training\train_expertia_math.py --model C:\training\base\phi-4-mini-reasoning --train C:\training\datasets\expertia-math-puro.jsonl --out C:\training\adapters\expertia-math-r16 --offload C:\training\offload --epochs 3 --seq-len 2048 --batch 1 --accum 16 --bf16 --no-offload --save-steps 200" -RedirectStandardOutput "C:\training\logs\train_auto.log" -RedirectStandardError "C:\training\logs\train_auto.err.log" -WindowStyle Hidden
        Start-Process -FilePath "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File C:\training\Watch-Train.ps1" -WindowStyle Hidden
      }
      Add-Content (Join-Path $inc "relaunch.log") "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') auto-relaunch (stale $([int]$staleMin)min)"
    }
  }
} catch { }
$trend = Invoke-Command -Session $S -ScriptBlock {
  $pys = Get-Process python* -ErrorAction SilentlyContinue | ForEach-Object { [math]::Round($_.WorkingSet64/1GB,2) }
  $g = try { nvidia-smi --query-gpu=utilization.gpu,temperature.gpu,memory.used --format=csv,noheader,nounits 2>$null } catch { $null }
  "$(Get-Date -Format 'HH:mm:ss') pyGB=$($pys -join '+') gpu=$g"
}
if ($trend) { Add-Content (Join-Path $inc "trend.log") $trend }
Invoke-Command -Session $S -ScriptBlock {
  $l = Get-ChildItem C:\training\logs\train_*.log | Sort-Object LastWriteTime | Select-Object -Last 1
  $e = Get-ChildItem C:\training\logs\train_*.err.log -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
  $ad = "C:\training\adapters\expertia-math-r16"
  $g = try { nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.free,power.draw,power.limit,clocks.sm --format=csv,noheader,nounits 2>$null } catch { $null }
  $cks = @($(if (Test-Path $ad) { Get-ChildItem $ad -Directory -Filter "checkpoint-*" -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -ExpandProperty Name }))
  $tail = @()
  if ($e) { $tail += Get-Content $e.FullName -Tail 18 | ForEach-Object { ([string]$_ -replace "`0", "") } }
  if ($l) { $tail += Get-Content $l.FullName -Tail 8 | ForEach-Object { ([string]$_ -replace "`0", "") } }
  [pscustomobject]@{
    log_tail = @($tail | Where-Object { $_ -and $_.Trim() })
    log_file = $(if ($e) { $e.Name } elseif ($l) { $l.Name } else { $null })
    checkpoints = $cks
    gpu_raw = $g
  }
} | ConvertTo-Json -Depth 3 | Set-Content (Join-Path $inc "remote_extra.json") -Encoding utf8
Remove-PSSession $S
