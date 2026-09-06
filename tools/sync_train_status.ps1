$ErrorActionPreference = "Continue"
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
Invoke-Command -Session $S -ScriptBlock {
  $l = Get-ChildItem C:\training\logs\train_*.log | Sort-Object LastWriteTime | Select-Object -Last 1
  $ad = "C:\training\adapters\expertia-math-r16"
  $g = try { nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.free,power.draw,power.limit,clocks.sm --format=csv,noheader,nounits 2>$null } catch { $null }
  [pscustomobject]@{
    log_tail = $(if ($l) { Get-Content $l.FullName -Tail 25 })
    log_file = $(if ($l) { $l.Name } else { $null })
    checkpoints = @()
    gpu_raw = $g
  }
} | ConvertTo-Json -Depth 3 | Set-Content (Join-Path $inc "remote_extra.json") -Encoding utf8
Remove-PSSession $S
