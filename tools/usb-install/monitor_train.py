import json
import subprocess
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

_HERE = Path(__file__).resolve().parent
ROOT = _HERE.parent if (_HERE.parent / "logs").exists() else _HERE
if not (ROOT / "logs").exists():
    _ALT = Path(r"C:\training")
    if (_ALT / "logs").exists():
        ROOT = _ALT
LOGS = ROOT / "logs"
DATASETS = ROOT / "datasets"
ADAPTERS = ROOT / "adapters" / "expertia-math-r16"
BASE = ROOT / "base" / "phi-4-mini-reasoning"
PORT = 8077

PAGE = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ExpertiaMath - Monitor</title>
<style>
body{background:#0d1117;color:#e6edf3;font-family:Consolas,monospace;margin:0;padding:16px}
h1{font-size:16px;letter-spacing:.08em;margin:0 0 4px}
#phase{color:#7aa2f7;font-weight:bold}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;margin:12px 0}
.card{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:8px 10px}
.k{font-size:10px;color:#8b949e}.v{font-size:16px;font-weight:bold}
canvas{width:100%;height:200px;background:#161b22;border:1px solid #30363d;border-radius:6px}
#log{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:8px 12px;font-size:11px;white-space:pre-wrap;max-height:320px;overflow:auto;margin-top:12px}
.bar{height:8px;background:#30363d;border-radius:99px;overflow:hidden;margin:8px 0}#barfill{height:100%;width:0%;background:#7aa2f7}
</style></head><body>
<h1>EXPERTIAMATH - ENTRENAMIENTO EN VIVO</h1>
<div>fase: <span id="phase">...</span> &middot; <span id="clock"></span></div>
<div class="bar"><div id="barfill"></div></div>
<div class="grid">
<div class="card"><div class="k">PASO</div><div class="v" id="s-step">-</div></div>
<div class="card"><div class="k">LOSS</div><div class="v" id="s-loss">-</div></div>
<div class="card"><div class="k">LR</div><div class="v" id="s-lr">-</div></div>
<div class="card"><div class="k">PASOS/MIN</div><div class="v" id="s-spm">-</div></div>
<div class="card"><div class="k">TIEMPO</div><div class="v" id="s-time">-</div></div>
<div class="card"><div class="k">DATASET</div><div class="v" id="s-ds">-</div></div>
<div class="card"><div class="k">GPU</div><div class="v" id="s-gpu">-</div></div>
<div class="card"><div class="k">CHECKPOINTS</div><div class="v" id="s-ck">-</div></div>
</div>
<canvas id="cv" width="800" height="200"></canvas>
<div id="log">conectando...</div>
<script>
async function tick(){
  try{
    const d = await (await fetch('/api/status')).json();
    document.getElementById('phase').textContent = d.phase || 'idle';
    document.getElementById('s-step').textContent = d.step!=null ? d.step + (d.max_steps ? ' / '+d.max_steps : '') : '-';
    document.getElementById('s-loss').textContent = d.loss!=null ? Number(d.loss).toFixed(4) : '-';
    document.getElementById('s-lr').textContent = d.lr!=null ? Number(d.lr).toExponential(1) : '-';
    document.getElementById('s-spm').textContent = d.steps_per_min ?? '-';
    document.getElementById('s-time').textContent = d.elapsed_s!=null ? Math.floor(d.elapsed_s/3600)+'h '+Math.floor(d.elapsed_s%3600/60)+'m' : '-';
    document.getElementById('s-ds').textContent = (d.dataset_train||0).toLocaleString() + ' / ' + (d.dataset_val||0).toLocaleString();
    document.getElementById('s-gpu').textContent = d.gpu || '-';
    document.getElementById('s-ck').textContent = (d.checkpoints||[]).join(', ') || 'ninguno';
    if(d.max_steps && d.step) document.getElementById('barfill').style.width = Math.min(100, d.step/d.max_steps*100) + '%';
    const h = d.loss_history || [];
    const cv = document.getElementById('cv'), ctx = cv.getContext('2d');
    ctx.clearRect(0,0,cv.width,cv.height);
    if(h.length){
      const ls = h.map(x=>x.loss), mn = Math.min(...ls), mx = Math.max(...ls), rg = (mx-mn)||1;
      ctx.strokeStyle = '#7aa2f7'; ctx.lineWidth = 2; ctx.beginPath();
      h.forEach((p,i)=>{ const x = 8+(i/(h.length-1||1))*(cv.width-16), y = cv.height-16-((p.loss-mn)/rg)*(cv.height-32); i?ctx.lineTo(x,y):ctx.moveTo(x,y); });
      ctx.stroke();
      ctx.fillStyle = '#8b949e'; ctx.font = '11px monospace';
      ctx.fillText('min '+mn.toFixed(3)+' max '+mx.toFixed(3)+' n='+h.length, 10, 14);
    } else { ctx.fillStyle = '#8b949e'; ctx.font = '12px monospace'; ctx.fillText('curva tras los primeros pasos...', 12, 24); }
    document.getElementById('log').textContent = (d.log_tail||[]).join('\n');
    document.getElementById('clock').textContent = new Date().toLocaleTimeString();
  }catch(e){ document.getElementById('log').textContent = 'sin conexion con el monitor: ' + e; }
}
setInterval(tick, 3000); tick();
</script></body></html>
"""


def count_lines(p):
    try:
        with open(p, "rb") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def snapshot():
    out = {"phase": "idle", "step": 0, "loss": None}
    try:
        out.update(json.loads((LOGS / "train_status.json").read_text(encoding="utf-8")))
    except Exception:
        pass
    out["dataset_train"] = count_lines(DATASETS / "expertia-math-puro.jsonl")
    out["dataset_val"] = count_lines(DATASETS / "expertia-math-puro_val.jsonl")
    out["base_ok"] = (BASE / "config.json").exists()
    try:
        out["checkpoints"] = sorted([p.name for p in ADAPTERS.glob("checkpoint-*")])
    except Exception:
        out["checkpoints"] = []
    try:
        logs = sorted(LOGS.glob("train_*.log"), key=lambda p: p.stat().st_mtime)
        if logs:
            out["log_tail"] = logs[-1].read_text(encoding="utf-8", errors="ignore").splitlines()[-25:]
            out["log_file"] = logs[-1].name
    except Exception:
        out["log_tail"] = []
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.free", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=10)
        parts = r.stdout.strip().split(",")
        out["gpu"] = f"{parts[0].strip()} usadas / {parts[1].strip()} libres MB"
    except Exception:
        out["gpu"] = None
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/api/status":
            body = json.dumps(snapshot(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


if __name__ == "__main__":
    print(f"ExpertiaMath monitor en http://localhost:{PORT}/  ({datetime.now():%H:%M:%S})")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
