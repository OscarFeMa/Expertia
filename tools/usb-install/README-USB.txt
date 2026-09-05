EXPERTIA-TRAIN - Paquete offline ExpertiaMath (Phi-4-mini-reasoning QLoRA)
================================================================================
Contenido verificado: 91 archivos, 9.92 GB
- payload/base/phi-4-mini-reasoning: 2 safetensors (4903637712 + 2768428504 bytes) + config/tokenizer
- payload/datasets: expertia-math-puro.jsonl 45000 lineas + _val 5000 lineas + sample1k
- payload/wheels: 59 wheels offline (torch cu121 2.26GB + dependencias)
- payload/redist: python-3.11.9-amd64.exe 25MB
- payload/scripts: train_expertia_math.py, requirements-train.txt, Modelfile, Start-Training.cmd, Start-Monitor.cmd, download_base.py
- payload/monitor: monitor_train.py (standalone, sin dependencias)

INSTALACION (PC destino RTX 3070, Windows, 50GB libres en C:)
1. Enchufar USB y ejecutar Install-ExpertiaTrain.cmd (doble clic)
2. El instalador verifica payload, instala Python 3.11 si falta, copia a C:\training,
   crea venv e instala TODO offline desde el USB (sin descargas)
3. Al terminar: escritorio con "ExpertiaMath Train" y "ExpertiaMath Monitor"
4. Entrenar: Start-Training.cmd (resume automatico entre sesiones)
5. Vigilar: Start-Monitor.cmd -> http://localhost:8077/

MANUAL (si el .cmd falla, ver %TEMP%\expertia-train-install.log):
- Requisitos: Python 3.11, git opcional, driver NVIDIA + CUDA 12.x, 50GB en C:
- Venv: py -3.11 -m venv C:\training\.venv-train
- Deps: C:\training\.venv-train\Scripts\pip install --no-index --find-links <USB>\payload\wheels -r requirements-train.txt
- Train: Start-Training.cmd (mismos parametros que el instalador)
- Los adapters resultantes quedan en C:\training\adapters\expertia-math-r16
