$ErrorActionPreference = "Continue"
$srcDir = "F:\expertia\data"
$srcFile = "incubator.db"
$vol = "F:\"
$dst = "E:\expertia-backups\incubator.db"
$log = "E:\expertia-backups\nightly_backup.log"
$minGB = 650

function L($m) { Add-Content $log "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m" }

L "=== backup nocturno inicio (VSS snapshot + copia) ==="
# Mutex: no solapar con otro backup en curso.
$me = $PID
$other = Get-CimInstance Win32_Process -Filter "Name='sqlite3.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.ProcessId -ne $me -and $_.CommandLine -like '*.backup*' }
if ($other) {
  L ("SKIP: .backup ya en curso PID $($other.ProcessId), se omite este ciclo")
  exit 0
}

function Test-Dst($tag) {
  if (-not (Test-Path $dst)) { L "ERROR ($tag): sin destino"; return $false }
  $szGB = [math]::Round((Get-Item $dst).Length / 1GB, 1)
  if ($szGB -lt $minGB) { L "ERROR ($tag): backup $szGB GB < $minGB GB (posible truncado)"; return $false }
  try {
    $sqlite = "C:\Users\usuario\AppData\Local\Microsoft\WinGet\Links\sqlite3.exe"
    $pages = (& $sqlite $dst "PRAGMA page_count;" 2>&1 | Select-Object -First 1)
    $specs = (& $sqlite $dst "SELECT COUNT(*) FROM specialist_registry;" 2>&1 | Select-Object -First 1)
    L "OK ($tag): $szGB GB | pages=$pages | specialists=$specs"
    return $true
  } catch {
    L "ERROR ($tag) validando: $($_.Exception.Message)"
    return $false
  }
}

# --- Via 1: VSS (requiere tarea elevada; congela el escritor) ---
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$vssOk = $false
try {
  $wmc = [wmiclass]"\\.\root\cimv2:Win32_ShadowCopy"
  $res = $wmc.Create($vol, "ClientAccessible")
  if ($res.ReturnValue -ne 0) { throw "Win32_ShadowCopy.Create -> $($res.ReturnValue)" }
  $sh = Get-CimInstance Win32_ShadowCopy -Filter ("ID='" + $res.ShadowID + "'") -ErrorAction Stop
  $dev = $sh.DeviceObject.TrimEnd('\')
  L "VSS snapshot OK ($dev)"
  $rc = robocopy "$dev\expertia\data" "E:\expertia-backups" $srcFile /J /R:3 /W:30 /NFL /NDL /NJH /NJS
  $rc = $LASTEXITCODE
  try { $sh | Remove-CimInstance -ErrorAction SilentlyContinue } catch {}
  if ($rc -ge 8) { throw "robocopy exit $rc" }
  $sw.Stop()
  L "VSS copia en $([math]::Round($sw.Elapsed.TotalMinutes, 1)) min"
  if (Test-Dst "vss") { exit 0 }
  L "VSS copiado pero validacion fallo; se intenta fallback sqlite"
} catch {
  L "VSS no disponible ($($_.Exception.Message)); fallback sqlite .backup"
  try {
    $dead = Get-CimInstance Win32_ShadowCopy -ErrorAction SilentlyContinue | Where-Object { $_.VolumeName -like "*Elements*" -or $_.VolumeName -eq $vol }
    foreach ($d in $dead) { try { $d | Remove-CimInstance -ErrorAction SilentlyContinue } catch {} }
  } catch {}
}

# --- Via 2: sqlite .backup (lento con escritor vivo; ultima opcion) ---
$sqlite = "C:\Users\usuario\AppData\Local\Microsoft\WinGet\Links\sqlite3.exe"
$src = "E:\expertia-data\incubator.db"
if (-not (Test-Path $src)) { L "ERROR: fuente no accesible ($src)"; exit 1 }
if (-not (Test-Path $sqlite)) { L "ERROR: sqlite3 no encontrado ($sqlite)"; exit 1 }
$sw2 = [System.Diagnostics.Stopwatch]::StartNew()
& $sqlite $src ".backup '$($dst)'" 2>&1 | Out-Null
$rc2 = $LASTEXITCODE
$sw2.Stop()
$mins2 = [math]::Round($sw2.Elapsed.TotalMinutes, 1)
if ($rc2 -ne 0) {
  L "ERROR: .backup exit $rc2 a los $mins2 min"
  exit 1
}
if (Test-Dst "sqlite") { exit 0 }
exit 1
