$ErrorActionPreference = "SilentlyContinue"
$Train = "C:\training"
$Out = Join-Path $Train "out-share"
$PartnerMAC = "F8-3D-C6-75-6B-D5"
New-Item -ItemType Directory -Path $Out -Force | Out-Null
$logs = Join-Path $Train "logs"
if (Test-Path (Join-Path $logs "train_status.json")) {
  Copy-Item (Join-Path $logs "train_status.json") (Join-Path $Out "train_status.json.tmp") -Force
  Move-Item (Join-Path $Out "train_status.json.tmp") (Join-Path $Out "train_status.json") -Force
}
$last = Get-ChildItem (Join-Path $logs "train_*.log") -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
if ($last) { Get-Content $last.FullName -Tail 30 | Set-Content (Join-Path $Out "log_tail.txt") -Encoding utf8 }
$ad = Join-Path $Train "adapters\expertia-math-r16"
$cks = @()
if (Test-Path $ad) { $cks = @(Get-ChildItem $ad -Directory -Filter "checkpoint-*" | Sort-Object Name | Select-Object -ExpandProperty Name) }
@{checkpoints = $cks; ts = (Get-Date -Format o); log_file = $(if ($last) { $last.Name } else { $null })} | ConvertTo-Json | Set-Content (Join-Path $Out "checkpoints.json") -Encoding utf8
try { nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader,nounits | Set-Content (Join-Path $Out "gpu.txt") } catch {}
if (Test-Path (Join-Path $ad "train_info.json")) { Copy-Item (Join-Path $ad "train_info.json") (Join-Path $Out "train_info.json") -Force }
$found = Get-NetNeighbor -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.LinkLayerAddress -eq $PartnerMAC -and $_.State -ne "Unreachable" } | Select-Object -First 1
if (-not $found) {
  1..254 | ForEach-Object { Start-Job -ScriptBlock { param($i) Test-Connection -ComputerName "192.168.1.$i" -Count 1 -TimeoutSeconds 1 -Quiet } -ArgumentList $_ } | Out-Null
  Get-Job | Wait-Job | Out-Null
  Get-Job | Remove-Job -Force
  $found = Get-NetNeighbor -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.LinkLayerAddress -eq $PartnerMAC -and $_.State -ne "Unreachable" } | Select-Object -First 1
}
if ($found) {
  Set-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -RemoteAddress $found.IPAddress -ErrorAction SilentlyContinue
  "partner $($found.IPAddress) $(Get-Date -Format o)" | Set-Content (Join-Path $Out "partner.txt")
} else {
  Set-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -RemoteAddress "192.168.1.0/24" -ErrorAction SilentlyContinue
  "partner no localizado, subred $(Get-Date -Format o)" | Set-Content (Join-Path $Out "partner.txt")
}
"RO solo lectura. Generado $(Get-Date -Format o)" | Set-Content (Join-Path $Out "README.txt")
