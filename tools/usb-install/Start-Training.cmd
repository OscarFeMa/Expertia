@echo off
setlocal
cd /d "%~dp0"
set "PY=%~dp0.venv-train\Scripts\python.exe"
if not exist "%PY%" echo Falta .venv-train, ejecute Install-ExpertiaTrain.cmd primero & pause & exit /b 1
set "STAMP=%date:~6,4%%date:~3,2%%date:~0,2%_%time:~0,2%%time:~3,2%%time:~6,2%"
set "STAMP=%STAMP: =0%"
set "LOG=%~dp0logs\train_%STAMP%.log"
echo [%date% %time%] Entrenando ExpertiaMath (resume automatico) ...
echo Log: %LOG%
"%PY%" "%~dp0train_expertia_math.py" --model "%~dp0base\phi-4-mini-reasoning" --train "%~dp0datasets\expertia-math-puro.jsonl" --out "%~dp0adapters\expertia-math-r16" --offload "%~dp0offload" --epochs 3 --seq-len 1024 --batch 1 --accum 16 --save-steps 200 > "%LOG%" 2>&1
if errorlevel 1 echo FALLO, revise %LOG% & pause & exit /b 1
echo COMPLETADO
pause
endlocal
