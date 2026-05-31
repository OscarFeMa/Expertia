@echo off
cd /d "%~dp0.."
powershell -NoProfile -Command ^
  "$p=netstat -ano | Select-String ':8011';" ^
  "$p | ForEach-Object { $_.ToString().Split()[-1] } | Select-Object -Unique | ForEach-Object { taskkill /f /pid $_ 2>$null };" ^
  "try { $s=Get-Content pipeline_state.json -Raw | ConvertFrom-Json; if ($s.pid) { taskkill /f /pid $s.pid 2>$null } } catch {};" ^
  "'{""pid"": null}' | Set-Content pipeline_state.json"
