@echo off
REM Launch Expertia Pipeline and API Web
REM Run this if both processes die (power outage, crash, etc.)
REM Make sure DB is at E:\expertia-data\incubator.db

REM === LAUNCH PIPELINE ===
echo [%date% %time%] Launching Pipeline...
start /MIN /HIGH "" "C:\Users\usuario\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe" "D:\proyectos\expertia\incubator-root\orchestrator.py" --phase full > "D:\proyectos\expertia\incubator-root\logs\pipeline_wmi.log" 2> "D:\proyectos\expertia\incubator-root\logs\pipeline_wmi_err.log"

REM === LAUNCH API WEB ===
echo [%date% %time%] Launching API Web...
start /MIN /HIGH "" "C:\Users\usuario\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe" "D:\proyectos\expertia\incubator-root\query_api.py" > "D:\proyectos\expertia\incubator-root\logs\api_server.log" 2> "D:\proyectos\expertia\incubator-root\logs\api_server_err.log"

echo [%date% %time%] Both launched. Check logs for status.
echo   Pipeline: logs\pipeline_wmi.log
echo   API Web:  http://localhost:8011/neural/
