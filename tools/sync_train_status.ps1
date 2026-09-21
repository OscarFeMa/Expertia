$ErrorActionPreference = "Continue"
function json2obj($p) { Get-Content $p -Raw -Encoding utf8 | ConvertFrom-Json }
$here = Split-Path -Parent $PSCommandPath
$inc = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "training\incoming_3070"
New-Item -ItemType Directory -Path $inc -Force | Out-Null
$cred = Import-Clixml (Join-Path $inc "cred.xml")
$ip3070 = @(arp -a 2>$null | Select-String "E0-0A-F6-9E-CB-01" | ForEach-Object { if ($_ -match "(192\.168\.1\.\d+)") { $Matches[1] } }) | Select-Object -First 1
if (-not $ip3070) { $ip3070 = "192.168.1.41" }
try {
  $S = New-PSSession -ComputerName $ip3070 -Credential $cred -ErrorAction Stop
} catch {
  $pw = $cred.GetNetworkCredential().Password
  net use "\\$ip3070\C$" /user:expertia $pw 2>$null | Out-Null
  Copy-Item "\\$ip3070\C$\training\logs\train_status.json" (Join-Path $inc "train_status.json") -Force -ErrorAction Stop
  Remove-Item (Join-Path $inc "remote_extra.json") -Force -ErrorAction SilentlyContinue
  net use "\\$ip3070\C$" /delete 2>$null | Out-Null
  exit 0
}
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
  if ((-not ($staleMin -ge 0) -or $staleMin -gt 10080 -or $staleMin -lt -2)) {
    $fileAge = ((Get-Date) - (Get-ChildItem (Join-Path $inc "train_status.json")).LastWriteTime).TotalMinutes
    if ($fileAge -ge 0 -and $fileAge -lt 10080) {
      if ($staleMin -ne 9999) {
        Add-Content (Join-Path $inc "relaunch.log") "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ts desvio ($([int]$staleMin)min), usando file age $([int]$fileAge)min"
      }
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
  $phaseDone = $false
  try { $phaseDone = ((Get-Content (Join-Path $inc "train_status.json") -Raw -Encoding utf8 | ConvertFrom-Json).phase -eq "done") } catch {}
  if ($phaseDone) { Add-Content (Join-Path $inc "relaunch.log") "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') fase done, no se relanza" }
  $tempNow = -1
  try {
    $tq = Invoke-Command -Session $S -ScriptBlock {
      $qq = ((nvidia-smi -q -d TEMPERATURE 2>$null) -join "`n")
      if ($qq -match "GPU Current Temp\s*:\s*([\d\.]+)") { $Matches[1] } else { "-1" }
    } -ErrorAction Stop
    $tempNow = [double]$tq
  } catch {}
  if ($tempNow -ge 80) { Add-Content (Join-Path $inc "relaunch.log") "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') pausa termica ($([int]$tempNow)C), se omite relaunch" }
  if ($staleMin -gt 15 -and $staleMin -lt 9999 -and -not $bigPy -and $coolOk -and -not $phaseDone -and ($tempNow -lt 0 -or $tempNow -lt 80)) {
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
          $used = try { $ln = ((nvidia-smi --query-gpu=memory.used --format=csv 2>$null) | Where-Object { $_ -match "\d" } | Select-Object -Last 1); [int](($ln -replace "[^0-9]", "")) } catch { 9999 }
          if ($used -lt 500) { break }
          Start-Sleep -Seconds 5
          $wait += 5
        }
        # Lanzamiento blindado: tarea SYSTEM (los hijos de sesion WinRM mueren al cerrarla)
        try { Invoke-WebRequest "http://192.168.1.42:8000/Run-Electronics.cmd" -OutFile C:\training\Run-Electronics.cmd -UseBasicParsing } catch {}
        # One-shot sin cita-trampa: programa a +2min con /Z y borra tras verificar arranque.
        # (/SC ONCE /ST 23:59 + /Run dejaba la cita viva: el /Run no la consume y re-dispara a las 23:59.)
        $stNow = (Get-Date).AddMinutes(2).ToString('HH:mm')
        schtasks /Create /TN "ExpertiaTrainElectronics" /TR "C:\training\Run-Electronics.cmd" /SC ONCE /ST $stNow /RU SYSTEM /Z /F
        schtasks /Run /TN "ExpertiaTrainElectronics"
        Start-Sleep -Seconds 60
        $upNow = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*train_expertia*" }
        if ($upNow) { schtasks /Delete /TN "ExpertiaTrainElectronics" /F }
      }
      Add-Content (Join-Path $inc "relaunch.log") "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') auto-relaunch por tarea (stale $([int]$staleMin)min)"
    }
  }
} catch { }
$trend = Invoke-Command -Session $S -ScriptBlock {
  $pys = Get-Process python* -ErrorAction SilentlyContinue | ForEach-Object { [math]::Round($_.WorkingSet64/1GB,2) }
  $g = try { ((nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv 2>$null) | Where-Object { $_ -match "\d" } | Select-Object -Last 1) } catch { $null }
  "$(Get-Date -Format 'HH:mm:ss') pyGB=$($pys -join '+') gpu=$g"
}
if ($trend) { Add-Content (Join-Path $inc "trend.log") $trend }
Invoke-Command -Session $S -ScriptBlock {
  $l = Get-ChildItem C:\training\logs\train_*.log | Sort-Object LastWriteTime | Select-Object -Last 1
  $e = Get-ChildItem C:\training\logs\train_*.err.log -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
  $ad = "C:\training\adapters\expertia-electronics-r16"
  $g = $null
  try {
    $q = ((nvidia-smi -q -d TEMPERATURE,POWER,CLOCK 2>$null) -join "`n")
    $t = if ($q -match "GPU Current Temp\s*:\s*([\d\.]+)") { $Matches[1] } else { "-1" }
    $pw = if ($q -match "Average Power Draw\s*:\s*([\d\.]+)") { $Matches[1] } else { "-1" }
    $pl = if ($q -match "Current Power Limit\s*:\s*([\d\.]+)") { $Matches[1] } else { "-1" }
    $ck = if ($q -match "(?m)^\s*SM\s*:\s*([\d\.]+)") { $Matches[1] } else { "-1" }
    $ln = ((nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.free --format=csv 2>$null) | Where-Object { $_ -match "\d" } | Select-Object -Last 1)
    $p = @($ln -split "," | ForEach-Object { ($_ -replace "[^0-9.]", "") })
    if ($p.Count -ge 3 -and $p[0] -ne "") { $g = "$t, $($p[0]), $($p[1]), $($p[2]), $pw, $pl, $ck" }
  } catch {}
  $cks = @($(if (Test-Path $ad) { Get-ChildItem $ad -Directory -Filter "checkpoint-*" -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -ExpandProperty Name }))
  $tail = @()
  if ($e) { $tail += Get-Content $e.FullName -Tail 18 | ForEach-Object { ([string]$_ -replace "`0", "") } }
  if ($l) { $tail += Get-Content $l.FullName -Tail 8 | ForEach-Object { ([string]$_ -replace "`0", "") } }
  $talert = ""
  $tnum = -1
  try { $tnum = [double]$t } catch {}
  if ($tnum -ge 90) {
    $trainers = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*train_expertia*" })
    if ($trainers.Count -gt 0) {
      $trainers | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force } catch {} }
      $talert = "PAUSA-TERMICA $([int]$tnum)C, reanuda <80C"
      Add-Content "C:\training\logs\thermal.log" "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') PAUSA termica ${tnum}C, entreno detenido"
    } else {
      $talert = "TEMP-ALTA $([int]$tnum)C (sin proceso)"
    }
  } elseif ($tnum -ge 80) {
    $talert = "AVISO-TEMP $([int]$tnum)C"
  }
  [pscustomobject]@{
    log_tail = @($tail | Where-Object { $_ -and $_.Trim() })
    log_file = $(if ($e) { $e.Name } elseif ($l) { $l.Name } else { $null })
    checkpoints = $cks
    gpu_raw = $g
    thermal_alert = $talert
    thermal_temp = $t
  }
} | ConvertTo-Json -Depth 3 | Set-Content (Join-Path $inc "remote_extra.json") -Encoding utf8
Remove-PSSession $S
