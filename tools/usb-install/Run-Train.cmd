@echo off
setlocal
for /f %%M in ('powershell -NoProfile -Command "$s=Get-ChildItem C:\training\logs\train_status.json -ErrorAction SilentlyContinue; if($s){[int]((Get-Date)-$s.LastWriteTime).TotalMinutes}else{9999}"') do set AGEMIN=%%M
if %AGEMIN% LSS 15 echo YA HAY UN ENTRENO ACTIVO (status hace %AGEMIN% min). Cierre esta ventana. & pause & exit /b 0
set TRAIN_STATUS_FILE=C:\training\logs\train_status.json
set PYTHONUNBUFFERED=1
start "train" /min cmd /c "C:\training\python311\python.exe -u C:\training\train_expertia_math.py --model C:\training\base\phi-4-mini-reasoning --train C:\training\datasets\expertia-math-puro.jsonl --out C:\training\adapters\expertia-math-r16 --offload C:\training\offload --epochs 3 --seq-len 2048 --batch 1 --accum 16 --bf16 --no-offload --save-steps 200 > C:\training\logs\train_local.log 2> C:\training\logs\train_local.err.log"
start "watch" /min powershell -NoProfile -ExecutionPolicy Bypass -File C:\training\Watch-Train.ps1
echo lanzado (entreno + watchdog). Cierre esta ventana.
pause
endlocal
