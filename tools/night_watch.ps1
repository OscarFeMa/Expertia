$ErrorActionPreference = "Continue"
$Log = "D:\proyectos\expertia\training\incoming_3070\night_watch.log"
$Repo = "D:\proyectos\expertia\incubator-root"
$Hive = "C:\Users\usuario\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
function WLog($m) { Add-Content $Log "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m" }
function CooldownOk() {
  $f = "D:\proyectos\expertia\training\incoming_3070\last_relaunch.txt"
  try {
    if (Test-Path $f) {
      $age = ((Get-Date) - (Get-ChildItem $f).LastWriteTime).TotalMinutes
      if ($age -lt 20) { WLog "cooldown: ultimo relaunch hace $([int]$age)min, se omite"; return $false }
    }
    Set-Content $f (Get-Date -Format o)
    return $true
  } catch { return $true }
}
function Cred3070() {
  $inc = "D:\proyectos\expertia\training\incoming_3070"
  $pw = ConvertTo-SecureString "Experto3070!" -AsPlainText -Force
  return New-Object PSCredential("192.168.1.41\expertia", $pw)
}
function Remote($sb) {
  $s = $null
  try {
    $s = New-PSSession -ComputerName 192.168.1.41 -Credential (Cred3070) -ErrorAction Stop
    return Invoke-Command -Session $s -ScriptBlock $sb
  } catch {
    WLog ("3070 INALCANZABLE: " + $_.Exception.Message)
    return $null
  } finally {
    if ($s) { Remove-PSSession $S -ErrorAction SilentlyContinue }
  }
}
WLog "=== vigilante nocturno iniciado ==="
$lastStep = -1
$lastAdvance = Get-Date
while ($true) {
  try {
    $st = Remote({ Get-Content C:\training\logs\train_status.json -Raw -Encoding utf8 | ConvertFrom-Json | Select-Object phase, step, loss })
    if (-not $st) { Start-Sleep -Seconds 300; continue }
    $step = [int]$st.step
    if ($step -gt $lastStep) { $lastStep = $step; $lastAdvance = Get-Date; $Script:lastLoss = $st.loss }
    $idleMin = ((Get-Date) - $lastAdvance).TotalMinutes
    $procs = Remote({ Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*train_expertia*" } | Select-Object ProcessId })
    $npy = @($procs).Count
    if ($idleMin -gt 40 -and $st.phase -eq "training") {
      if (-not (CooldownOk)) { Start-Sleep -Seconds 300; continue }
      WLog "SIN AVANCE ${idleMin}m (paso $step). Reiniciando worker..."
      try {
        $rs = New-PSSession -ComputerName 192.168.1.41 -Credential (Cred3070) -ErrorAction Stop -Name NightRelaunch
        Invoke-Command -Session $rs -ScriptBlock {
          Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*train_expertia*" } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force } catch {} }
          $wait = 0
          while ($wait -lt 90) {
            $used = try { [int]((nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>$null) -replace "[^0-9]","") } catch { 9999 }
            if ($used -lt 500) { break }
            Start-Sleep -Seconds 5
            $wait += 5
          }
          $env:TRAIN_STATUS_FILE = "C:\training\logs\train_status.json"
          $env:PYTHONUNBUFFERED = "1"
          Start-Process -FilePath "C:\training\python311\python.exe" -ArgumentList "-u C:\training\train_expertia_math.py --model C:\training\base\phi-4-mini-reasoning --train C:\training\datasets\expertia-math-puro.jsonl --out C:\training\adapters\expertia-math-r16 --offload C:\training\offload --epochs 3 --seq-len 2048 --batch 1 --accum 16 --bf16 --no-offload --save-steps 200" -RedirectStandardOutput "C:\training\logs\train_night.log" -RedirectStandardError "C:\training\logs\train_night.err.log" -WindowStyle Hidden
        } | Out-Null
        Disconnect-PSSession -Session $rs | Out-Null
        WLog "relaunch emitido (sesion desconectada, proceso huerfano)"
      } catch {
        WLog ("FALLO relaunch: " + $_.Exception.Message)
      }
      $lastAdvance = Get-Date
    }
    if ($npy -gt 1) { WLog "AVISO: $npy pythons en 3070 (posible duplicado)" }
    try {
      $r = Invoke-RestMethod -Uri "http://localhost:8011/api/health" -TimeoutSec 60
      $Script:apiFails = 0
    } catch {
      $Script:apiFails = ([int]$Script:apiFails) + 1
      WLog ("API health fallo ${Script:apiFails}/2: " + $_.Exception.Message)
      if ([int]$Script:apiFails -ge 2) {
        $alive = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*query_api*" }
        if ($alive) {
          WLog "API procesa viva pese al health: NO se mata (falso positivo)"
        } else {
          WLog "API caida confirmada, relanzando..."
          $np = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine = "$Hive D:\proyectos\expertia\incubator-root\query_api.py" }
          WLog ("API relanzada PID=" + $np.ProcessId)
        }
        $Script:apiFails = 0
      }
    }
    $pipe = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*orchestrator*" }
    if (-not $pipe) {
      WLog "PIPELINE local caido (el watchdog deberia resucitarlo)"
    }
  } catch {
    WLog ("ERROR ciclo: " + $_.Exception.Message)
  }
  Start-Sleep -Seconds 300
}
