$ErrorActionPreference = "Continue"
$Log = "D:\proyectos\expertia\training\incoming_3070\night_watch.log"
$Repo = "D:\proyectos\expertia\incubator-root"
$Hive = "C:\Users\usuario\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
function WLog($m) { Add-Content $Log "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m" }
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
    $procs = Remote({ Get-Process python* -ErrorAction SilentlyContinue | Select-Object Id }) 
    $npy = @($procs).Count
    if ($idleMin -gt 40 -and $st.phase -eq "training") {
      WLog "SIN AVANCE ${idleMin}m (paso $step). Reiniciando worker..."
      try {
        $rs = New-PSSession -ComputerName 192.168.1.41 -Credential (Cred3070) -ErrorAction Stop -Name NightRelaunch
        Invoke-Command -Session $rs -ScriptBlock {
          Get-Process python* -ErrorAction SilentlyContinue | Where-Object { $_.WorkingSet64 -gt 500MB } | ForEach-Object { Stop-Process -Id $_.Id -Force }
          Start-Sleep -Seconds 20
          $env:TRAIN_STATUS_FILE = "C:\training\logs\train_status.json"
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
      $r = Invoke-RestMethod -Uri "http://localhost:8011/api/health" -TimeoutSec 10
    } catch {
      WLog "API caida, relanzando..."
      $np = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine = "$Hive D:\proyectos\expertia\incubator-root\query_api.py" }
      WLog ("API relanzada PID=" + $np.ProcessId)
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
