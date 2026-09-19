$ErrorActionPreference = "Continue"
$sqlite = "C:\Users\usuario\AppData\Local\Microsoft\WinGet\Links\sqlite3.exe"
$src = "E:\expertia-data\incubator.db"
$dst = "E:\expertia-backups\incubator.db"
$log = "E:\expertia-backups\nightly_backup.log"
$minGB = 650

function L($m) { Add-Content $log "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m" }

L "=== backup nocturno inicio (online-safe .backup) ==="
if (-not (Test-Path $src)) { L "ERROR: fuente no accesible ($src)"; exit 1 }
if (-not (Test-Path $sqlite)) { L "ERROR: sqlite3 no encontrado ($sqlite)"; exit 1 }

$sw = [System.Diagnostics.Stopwatch]::StartNew()
& $sqlite $src ".backup '$($dst)'" 2>&1 | Out-Null
$rc = $LASTEXITCODE
$sw.Stop()
$mins = [math]::Round($sw.Elapsed.TotalMinutes, 1)

if ($rc -ne 0) {
    L "ERROR: .backup exit $rc a los $mins min (backup previo queda intacto en la medida posible)"
    exit 1
}

$szGB = if (Test-Path $dst) { [math]::Round((Get-Item $dst).Length / 1GB, 1) } else { 0 }
$pages = (& $sqlite $dst "PRAGMA page_count;" 2>&1 | Select-Object -First 1)
$specs = (& $sqlite $dst "SELECT COUNT(*) FROM specialist_registry;" 2>&1 | Select-Object -First 1)

if ($szGB -lt $minGB) {
    L "ERROR: backup $szGB GB < $minGB GB (posible truncado)"
    exit 1
}
L "OK: $szGB GB en $mins min | pages=$pages | specialists=$specs"
exit 0
