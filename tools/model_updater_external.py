#!/usr/bin/env python3
"""
Model Updater Externo — App standalone para probar sin integrar.
Busca diario los mejores modelos para la máquina host y genera lista con confirmación.
No hace ollama pull ni toca specialist_registry hasta aprobación.
Uso: python tools/model_updater_external.py --dry-run
      python tools/model_updater_external.py --check
"""
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
PENDING = ROOT / "storage" / "model_updater" / "pending.json"
PENDING.parent.mkdir(parents=True, exist_ok=True)

def get_vram():
    try:
        out = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"], text=True)
        return int(out.strip().split()[0])
    except Exception:
        return 6144

def get_ollama_models():
    try:
        import requests
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []

def search_candidates(vram_mb):
    # Simulación basada en conocimiento 2026-08-30 (sin red en offline, usa lista curada)
    # En modo online haría fetch a https://ollama.com/library y HF API
    candidates = []
    if vram_mb >= 24000:
        candidates.append({"model":"qwen2.5-coder:14b","size":"8.2GB","gain":"+8% HumanEval vs 3b","risk":"Necesita 24GB, OK","for_domain":"SoftwareEngineering"})
    if vram_mb >= 12000:
        candidates.append({"model":"qwen2.5-coder:7b","size":"4.4GB","gain":"+6% vs 3b, 78% HumanEval","risk":"Roza 6GB con KV 8K, contención con phi4","for_domain":"DataScience"})
    # Siempre propone optimizaciones sin cambio de familia
    candidates.append({"model":"qwen2.5-coder:3b:Q5_K_M","size":"2.2GB (+0.3GB)","gain":"+1-2% HumanEval","risk":"Bajo, probar 1 dominio canario","for_domain":"SoftwareEngineering","replaces":"qwen2.5-coder:3b"})
    candidates.append({"model":"phi4-mini:latest","size":"2.5GB (mismo hash)","gain":"Desbloquea 128K ctx (vs 4K capado)","risk":"Nulo (renombrar tag)","for_domain":"Medicine,PhilosophyHistory","replaces":"phi4-mini:4k"})
    candidates.append({"model":"gemma3:4b:Q5_K_M","size":"3.0GB (+0.5GB)","gain":"+1% instruction","risk":"Deja 2.7GB libres con KV 8K, justo","for_domain":"LegalSystem","replaces":"gemma3:4b"})
    return [c for c in candidates if "GB" not in c["size"] or float(c["size"].split("GB")[0].replace("+","").strip()) < vram_mb*0.6]

def main():
    import argparse
    p = argparse.ArgumentParser(description="Model Updater Externo")
    p.add_argument("--dry-run", action="store_true", help="Solo genera pending.json sin tocar DB")
    p.add_argument("--check", action="store_true", help="Muestra recomendación sin escribir")
    p.add_argument("--json", action="store_true", help="Salida JSON")
    args = p.parse_args()

    vram = get_vram()
    installed = get_ollama_models()
    cands = search_candidates(vram)

    report = {
        "ts": datetime.now().isoformat(),
        "vram_mb": vram,
        "installed": installed,
        "candidates": cands,
        "note": "App externa: no hace pull ni UPDATE specialist_registry. Requiere confirmación en /api/admin/models/pending"
    }

    if args.check or args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    PENDING.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Generado {PENDING} con {len(cands)} candidatos para {vram}MB VRAM")
    for c in cands:
        print(f" - {c['model']} para {c['for_domain']}: {c['gain']} | Riesgo: {c['risk']}")

if __name__ == "__main__":
    main()
