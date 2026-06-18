$procs = Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match 'watchdog' }

if ($procs) {
    $p = $procs[0]
    $uptime = [math]::Round(((Get-Date) - $p.StartTime).TotalMinutes)
    Write-Host "  🐕  Watchdog: CORRIENDO  (PID: $($p.Id))  Uptime: ${uptime}min"
    Write-Host ""
    Write-Host "  Deteniendo..."
    $procs | Stop-Process -Force
    Write-Host "  Watchdog DETENIDO"
}
else {
    Write-Host "  🐕  Watchdog: DETENIDO"
    Write-Host ""
    Write-Host "  Iniciando..."
    $uvPy = 'C:\Users\usuario\AppData\Roaming\uv\python\cpython-3.11-windows-x86_64-none\python.exe'
    $null = Start-Process -FilePath $uvPy -ArgumentList 'tools\watchdog.py' -WorkingDirectory (Get-Location) -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 2
    $newPid = (Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match 'watchdog' } | Select-Object -ExpandProperty Id)
    if ($newPid) {
        Write-Host "  Watchdog INICIADO (PID: $newPid)"
    } else {
        Write-Host "  ERROR: No se pudo iniciar el watchdog"
    }
}
