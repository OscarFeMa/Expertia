@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set "USB=%~dp0"
set "PAYLOAD=%USB%payload"
set "DEST=C:\training"
set "LOG=%TEMP%\expertia-train-install.log"
echo [%date% %time%] Instalando ExpertiaMath Train > "%LOG%"

echo [1/8] Verificando payload en %USB% ...
if not exist "%PAYLOAD%\base\phi-4-mini-reasoning\config.json" echo FALTA base en USB & echo FALTA base, revise el USB. >> "%LOG%" & pause & exit /b 1
if not exist "%PAYLOAD%\base\phi-4-mini-reasoning\model-00001-of-00002.safetensors" echo FALTA shard 1 & pause & exit /b 1
if not exist "%PAYLOAD%\base\phi-4-mini-reasoning\model-00002-of-00002.safetensors" echo FALTA shard 2 & pause & exit /b 1
if not exist "%PAYLOAD%\datasets\expertia-math-puro.jsonl" echo FALTA dataset & pause & exit /b 1
if not exist "%PAYLOAD%\wheels\torch-2.3.1+cu121-cp311-cp311-win_amd64.whl" echo FALTAN wheels & pause & exit /b 1
echo      payload OK

echo [2/8] Comprobando 50GB libres en C: ...
for /f "tokens=3" %%A in ('dir C:\ ^| find "bytes libres"') do set FREEC=%%A
set FREEC=%FREEC:.=%
set FREEC=%FREEC:,=%
if %FREEC% LSS 50000000000 echo C: sin 50GB libres & pause & exit /b 1
echo      espacio OK

echo [3/8] Detectando Python 3.11 ...
set "PY311="
py -3.11 --version >nul 2>&1
if not errorlevel 1 set "PY311=py -3.11"
if not defined PY311 if exist "%LocalAppData%\Programs\Python\Python311\python.exe" set "PY311=%LocalAppData%\Programs\Python\Python311\python.exe"
if not defined PY311 (
  echo      instalando Python 3.11 desde USB ...
  "%PAYLOAD%\redist\python-3.11.9-amd64.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 >> "%LOG%" 2>&1
  set "PY311=%LocalAppData%\Programs\Python\Python311\python.exe"
)
if not defined PY311 set "PY311=python"
echo      python OK

echo [4/8] Copiando a %DEST% ...
mkdir "%DEST%\base" 2>nul
mkdir "%DEST%\datasets" 2>nul
mkdir "%DEST%\adapters" 2>nul
mkdir "%DEST%\logs" 2>nul
mkdir "%DEST%\offload" 2>nul
mkdir "%DEST%\monitor" 2>nul
robocopy "%PAYLOAD%\base" "%DEST%\base" /E /Z /NFL /NDL /NJH /NJS >> "%LOG%" 2>&1
robocopy "%PAYLOAD%\datasets" "%DEST%\datasets" /E /Z /NFL /NDL /NJH /NJS >> "%LOG%" 2>&1
robocopy "%PAYLOAD%\scripts" "%DEST%" train_expertia_math.py requirements-train.txt Modelfile-ExpertiaMath download_base.py Start-Training.cmd Start-Monitor.cmd /NFL /NDL /NJH /NJS >> "%LOG%" 2>&1
robocopy "%PAYLOAD%\monitor" "%DEST%\monitor" /E /NFL /NDL /NJH /NJS >> "%LOG%" 2>&1
echo      copia OK

echo [5/8] Creando venv (puede tardar unos minutos) ...
%PY311% -m venv "%DEST%\.venv-train" >> "%LOG%" 2>&1
if errorlevel 1 echo FALLO venv, revise "%LOG%" & pause & exit /b 1

echo [6/8] Instalando dependencias OFFLINE desde USB ...
"%DEST%\.venv-train\Scripts\python.exe" -m pip install --upgrade pip --no-index --find-links "%PAYLOAD%\wheels" pip >> "%LOG%" 2>&1
"%DEST%\.venv-train\Scripts\pip.exe" install --no-index --find-links "%PAYLOAD%\wheels" -r "%DEST%\requirements-train.txt" >> "%LOG%" 2>&1
if errorlevel 1 echo FALLO pip, revise "%LOG%" & pause & exit /b 1
echo      dependencias OK

echo [7/8] Verificando GPU y modelo ...
nvidia-smi --query-gpu=name,memory.total --format=csv >> "%LOG%" 2>&1
"%DEST%\.venv-train\Scripts\python.exe" -c "import torch;print('cuda',torch.cuda.is_available());print('bf16',torch.cuda.is_bf16_supported() if torch.cuda.is_available() else False)" >> "%LOG%" 2>&1
"%DEST%\.venv-train\Scripts\python.exe" -c "from transformers import AutoConfig;c=AutoConfig.from_pretrained(r'%DEST%\base\phi-4-mini-reasoning',trust_remote_code=True);print('CONFIG',c.model_type,c.hidden_size)" >> "%LOG%" 2>&1
if errorlevel 1 echo FALLO verificacion, revise "%LOG%" & pause & exit /b 1

echo [8/8] Accesos directos ...
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([IO.Path]::Combine([Environment]::GetFolderPath('Desktop'),'ExpertiaMath Train.lnk'));$s.TargetPath='%DEST%\Start-Training.cmd';$s.Save()" >> "%LOG%" 2>&1
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([IO.Path]::Combine([Environment]::GetFolderPath('Desktop'),'ExpertiaMath Monitor.lnk'));$s.TargetPath='%DEST%\Start-Monitor.cmd';$s.Save()" >> "%LOG%" 2>&1

echo.
echo INSTALACION COMPLETA en %DEST%
echo   - Entrenar:  %DEST%\Start-Training.cmd
echo   - Monitor:   %DEST%\Start-Monitor.cmd  (http://localhost:8077/)
echo   - Log:       %LOG%
echo.
pause
endlocal
