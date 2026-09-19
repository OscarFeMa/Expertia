$logDir = "D:\proyectos\expertia\incubator-root\logs"
$totalSkip = 57900000

while ($true) {
    Clear-Host
    Write-Host "=== Monitor de Progreso - Expertia Pipeline ===" -ForegroundColor Cyan
    Write-Host (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    Write-Host ""

    $logFile = Get-ChildItem -Path $logDir -Name "*orchestrator_*" -Exclude "*stdout*" |
        Sort-Object -Descending | Select-Object -First 1

    if (-not $logFile) {
        Write-Host "No se encuentra log del pipeline" -ForegroundColor Red
        Start-Sleep -Seconds 600
        continue
    }

    $logPath = Join-Path $logDir $logFile
    $lastLine = Get-Content -Path $logPath -Tail 1

    # Check if pipeline is alive
    $proc = Get-Process -Name "python" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match "orchestrator" } |
        Select-Object -First 1

    if (-not $proc) {
        Write-Host "PIPELINE DETENIDO" -ForegroundColor Red
        Start-Sleep -Seconds 600
        continue
    }

    # Parse "saltadas X entidades" line
    if ($lastLine -match "saltadas\s+([\d,]+)\s+entidades") {
        $skipped = $($matches[1] -replace ',', '') -as [long]
        $pct = [math]::Round($skipped / $totalSkip * 100, 1)
        $remaining = $totalSkip - $skipped

        # Calculate rate from log timestamps
        $allLines = Get-Content -Path $logPath
        $skipLines = $allLines | Select-String -Pattern "saltadas\s+([\d,]+)\s+entidades" | Select-Object -Last 10
        if ($skipLines.Count -ge 2) {
            $first = $skipLines | Select-Object -First 1
            $last = $skipLines | Select-Object -Last 1
            $t1 = [DateTime]::ParseExact($first -replace '^.*?(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}).*', '$1', $null)
            $t2 = [DateTime]::ParseExact($last -replace '^.*?(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}).*', '$1', $null)
            $span = ($t2 - $t1).TotalMinutes
            if ($span -gt 0) {
                $f1 = $first -replace '^.*?saltadas\s+([\d,]+)\s+entidades.*', '$1' -replace ',', ''
                $f2 = $last -replace '^.*?saltadas\s+([\d,]+)\s+entidades.*', '$1' -replace ',', ''
                $rate = [math]::Round(([long]$f2 - [long]$f1) / $span, 0)
                $etaMin = [math]::Round($remaining / $rate, 0)
                Write-Host "Pipeline activo (PID: $($proc.Id))" -ForegroundColor Green
                Write-Host ""
                Write-Host "Skip:        $($skipped.ToString('N0')) / $($totalSkip.ToString('N0')) ($pct%)"
                Write-Host "Ritmo:       $($rate.ToString('N0')) entidades/min"
                Write-Host "Restan:      $($remaining.ToString('N0')) entidades"
                Write-Host "ETA skip:    ~$etaMin min (~$([math]::Round($etaMin/60,1))h)"
                Write-Host "Log actual:  $logFile"
                Write-Host "Último:      $($lastLine -replace '^.*?\[INFO\]\s+','')"
            }
        } else {
            Write-Host "Pipeline iniciando..." -ForegroundColor Yellow
        }
    } elseif ($lastLine -match "PIPELINE COMPLETE") {
        Write-Host "PIPELINE COMPLETADO" -ForegroundColor Green
        Get-Content -Path $logPath | Select-String -Pattern "METRICS SUMMARY" -Context 0,10
    } else {
        Write-Host "Última línea del log:" -ForegroundColor Yellow
        Write-Host "  $lastLine"
    }

    Write-Host ""
    Write-Host "Próxima actualización en 10 min..." -ForegroundColor DarkGray
    Start-Sleep -Seconds 600
}
