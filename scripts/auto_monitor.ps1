# Auto-monitor: refreshes pipeline status every 20 minutes
while ($true) {
    Clear-Host
    python D:\proyectos\expertia\incubator-root\scripts\watch_pipeline.py
    Write-Output ""
    Write-Output "=============================="
    Write-Output "Next refresh in 20 min..."
    Start-Sleep -Seconds 1200
}