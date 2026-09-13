@echo off
cd /d "D:\proyectos\expertia\incubator-root"
start /b "" "C:\Users\usuario\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe" "orchestrator.py" --phase cascade --from-zero --max-duration 0 > "logs\cascade_clean.log" 2>&1
