# Watch pipeline progress
Write-Output "=============================="
Write-Output "PIPELINE MONITOR"
Write-Output "=============================="
python D:\proyectos\expertia\incubator-root\scripts\watch_pipeline.py
Write-Output ""
Write-Output "=============================="
Write-Output "Processes:"
Get-Process -Name python* -ErrorAction SilentlyContinue | Where-Object { $_.Id -ne $pid } | Select-Object Id, @{N='CPU(s)';E={[math]::Round($_.TotalProcessorTime.TotalSeconds,0)}}, @{N='MemMB';E={[math]::Round($_.WorkingSet64/1MB,0)}} | Format-Table -AutoSize
