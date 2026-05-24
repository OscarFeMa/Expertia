"""
Model Checker - Verifica y descarga modelos requeridos por los especialistas.

Uso:
    python check_models.py              # Solo verificar
    python check_models.py --download   # Descargar los que falten
"""

import subprocess
import sys
import json
from typing import Dict, List, Set

# Copia directa del SPECIALIST_REGISTRY de orchestrator.py
SPECIALIST_REGISTRY = [
    {"domain": "SoftwareEngineering", "model": "qwen2.5-coder:3b"},
    {"domain": "Mathematics", "model": "qwen2.5:3b"},
    {"domain": "Medicine", "model": "phi3:mini"},
    {"domain": "LegalSystem", "model": "llama3.2:3b"},
    {"domain": "PhilosophyHistory", "model": "gemma2:2b"},
    {"domain": "FinanceEconomics", "model": "mistral:7b"},
    {"domain": "Physics", "model": "qwen2.5:3b"},
    {"domain": "Cybersecurity", "model": "llama3.2:3b"},
    {"domain": "Bioinformatics", "model": "phi3:mini"},
    {"domain": "Geopolitics", "model": "llama3.2:3b"},
    {"domain": "DataScience", "model": "qwen2.5-coder:3b"},
    {"domain": "Chemistry", "model": "qwen2.5:3b"},
    {"domain": "ArtHistory", "model": "gemma2:2b"},
    {"domain": "Electronics", "model": "qwen2.5:3b"},
    {"domain": "Astronomy", "model": "qwen2.5:3b"},
]


def get_local_models() -> Set[str]:
    """Returns set of model names available in local Ollama."""
    try:
        r = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            print(f"  Error: {r.stderr}")
            return set()
        models = set()
        for line in r.stdout.strip().split("\n")[1:]:
            parts = line.split()
            if parts:
                models.add(parts[0])
        return models
    except FileNotFoundError:
        print("  ERROR: Ollama no está instalado o no está en el PATH.")
        return set()
    except Exception as e:
        print(f"  Error: {e}")
        return set()


def main():
    download = "--download" in sys.argv

    print("=" * 70)
    print("  EXPERTIA - Model Checker")
    print("=" * 70)

    local = get_local_models()
    if not local:
        print("\n  No se pudieron detectar modelos locales.")
        sys.exit(1)

    print(f"\n  Modelos locales ({len(local)}):")
    for m in sorted(local):
        print(f"    • {m}")

    # Collect unique required models
    required: Dict[str, List[str]] = {}
    for s in SPECIALIST_REGISTRY:
        m = s["model"]
        if m not in required:
            required[m] = []
        required[m].append(s["domain"])

    print(f"\n  Modelos requeridos ({len(required)}):")
    for m, domains in sorted(required.items()):
        status = "[OK]" if m in local else "[MISSING]"
        print(f"    {status} {m}")
        for d in domains:
            print(f"         -> {d}")

    missing = [m for m in required if m not in local]
    if not missing:
        print(f"\n  [OK] Todos los modelos estan disponibles.")
        return

    print(f"\n  [MISSING] Faltan {len(missing)} modelo(s):")
    for m in missing:
        domains = required[m]
        size = ""
        if "7b" in m or "7B" in m:
            size = " (~4.7 GB)"
        elif "3b" in m or "3B" in m:
            size = " (~1.9 GB)"
        elif "2b" in m or "2B" in m:
            size = " (~1.3 GB)"
        print(f"    - {m}{size}")
        for d in domains:
            print(f"         -> {d}")

    if download:
        print(f"\n  Descargando modelos faltantes...")
        for m in missing:
            print(f"    -> ollama pull {m} ...")
            r = subprocess.run(["ollama", "pull", m], timeout=1800)
            if r.returncode == 0:
                print(f"    [OK] {m} descargado")
            else:
                print(f"    [FAIL] {m} fallo")
    else:
        total_gb = 0
        for m in missing:
            if "7b" in m or "7B" in m:
                total_gb += 4.7
            elif "3b" in m or "3B" in m:
                total_gb += 1.9
            elif "2b" in m or "2B" in m:
                total_gb += 1.3
            else:
                total_gb += 3.0
        print(f"\n  [WARN] Espacio estimado: ~{total_gb:.1f} GB")
        print(f"\n  Para descargarlos todos:")
        print(f"    python check_models.py --download")
        print(f"\n  O uno por uno:")
        for m in missing:
            print(f"    ollama pull {m}")


if __name__ == "__main__":
    main()
