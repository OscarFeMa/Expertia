param([string]$OutDir = $env:TEMP)
$Out = Join-Path $OutDir "new-user-3070.txt"
$Log = Join-Path $OutDir "new-user-3070.log"
function Step($m) { Add-Content $Log "$(Get-Date -Format 'HH:mm:ss') $m" }
Step "inicio"
$log = @()
try {
  Step "generando clave"
  $chars = (48..57) + (65..90) + (97..122)
  $pw = -join ($chars | Get-Random -Count 24 | ForEach-Object { [char]$_ })
  Step "borrando previo"
  try { net user expertia /delete 2>$null | Out-Null } catch {}
  Step "creando usuario"
  net user expertia $pw /add /expires:never /passwordchg:no | Out-Null
  Step "flags usuario"
  Set-LocalUser -Name expertia -PasswordNeverExpires $true -UserMayChangePassword $false
  $log += "usuario expertia creado"
  Step "carpeta training"
  New-Item -ItemType Directory -Path C:\training -Force | Out-Null
  icacls C:\training /grant 'expertia:(OI)(CI)F' | Out-Null
  $log += "C:\training accesible"
  Step "clave ssh"
  $prof = 'C:\Users\expertia'
  New-Item -ItemType Directory -Path (Join-Path $prof ".ssh") -Force | Out-Null
  $k = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGogcxnaZ3xhz8B3KP9offEsipuuUCzS0KsTMhzaDztY expertia-sobremesa'
  [IO.File]::WriteAllText((Join-Path $prof ".ssh\authorized_keys"), $k + "`r`n")
  icacls (Join-Path $prof ".ssh\authorized_keys") /inheritance:r /grant 'SYSTEM:F' /grant '*S-1-5-32-544:F' /grant 'expertia:F' | Out-Null
  icacls (Join-Path $prof ".ssh") /inheritance:r /grant 'SYSTEM:(OI)(CI)F' /grant '*S-1-5-32-544:(OI)(CI)F' /grant 'expertia:(OI)(CI)F' | Out-Null
  Step "fingerprint"
  $log += 'fingerprint: ' + (& 'C:\Program Files\OpenSSH\ssh-keygen.exe' -l -f (Join-Path $prof '.ssh\authorized_keys') 2>&1 | Out-String).Trim()
  Step "fin"
  $ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.AddressState -eq 'Preferred' -and $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } | Select-Object -First 1).IPAddress
  $log += "listo: expertia@$ip"
} catch {
  Step ("FALLO: " + $_.Exception.Message)
  $log += "FALLO: " + $_.Exception.Message
}
$log | Set-Content $Out -Encoding utf8
$log | Write-Output
