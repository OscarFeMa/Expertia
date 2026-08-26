"""
Launcher de Expertia — menú interactivo + CLI.
Lanza el pipeline (orchestrator.py) desacoplado de la terminal, con watchdog
opcional y API opcional, escribiendo pipeline_state.json para que el watchdog
pueda relanzar con la misma config.

Uso:
  python tools/launcher.py [--mode web|nurture|feed|full|cascade]
                           [--duration H] [--specialist DOM] [--model M]
                           [--skip "A,B"] [--max-cycles N] [--max-duration H]
                           [--with-watchdog] [--api] [--parallel N]
Solo double-click / sin args: menú interactivo.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = REPO_ROOT / "logs"
LOGS_DIR.mkdir(exist_ok=True)

PYTHON = os.environ.get(
    "EXPERTIA_PYTHON",
    r"C:\Users\usuario\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe",
)
DATABASE_PATH = Path(os.environ.get("EXPERTIA_DB", r"E:\expertia-data\incubator.db"))
OLLAMA_API = os.environ.get("EXPERTIA_OLLAMA", "http://localhost:11434")

MODES = ["web", "nurture", "feed", "full", "cascade"]
MODES_DESC = {
    "web": "Alimentación web continua (sin límite temporal; timeout 2h/especialista)",
    "nurture": "Crecimiento/mantenimiento continuo (1 especialista a la vez)",
    "feed": "Una pasada de absorción de packages Wikidata",
    "full": "Cascade + feed + nurture (legacy)",
    "cascade": "Solo Phase A: Wikidata streaming",
}


def _db_ok() -> bool:
    try:
        import sqlite3
        with sqlite3.connect(DATABASE_PATH, timeout=5) as c:
            c.execute("SELECT COUNT(*) FROM specialist_registry").fetchone()
        return True
    except Exception as e:
        print(f"  [X] DB no accesible ({DATABASE_PATH}): {e}")
        return False


def _ollama_ok() -> bool:
    try:
        import urllib.request
        with urllib.request.urlopen(f"{OLLAMA_API}/api/tags", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def _list_specialists() -> list:
    import sqlite3
    try:
        with sqlite3.connect(DATABASE_PATH, timeout=5) as c:
            c.row_factory = sqlite3.Row
            rows = c.execute(
                "SELECT id, domain, model FROM specialist_registry ORDER BY domain"
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception:
        return []


def _get_pipeline_pid() -> int | None:
    try:
        import psutil
    except ImportError:
        return None
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cl = " ".join(proc.info["cmdline"] or [])
            if "orchestrator.py" in cl and "--phase" in cl and proc.info["pid"] != os.getpid():
                return proc.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return None


def _write_state(cfg: dict):
    state = {
        "pid": cfg.get("pid"),
        "start_time": time.time(),
        "end_epoch": None,
        "mode": cfg["mode"],
        "duration_hours": cfg.get("duration"),
        "specialist": cfg.get("specialist") or "all",
        "model": cfg.get("model") or "all",
        "skip": cfg.get("skip") or "",
        "max_cycles": cfg.get("max_cycles") or 0,
        "max_duration": cfg.get("max_duration") or 0,
        "watchdog": bool(cfg.get("watchdog")),
        "api": bool(cfg.get("api")),
    }
    (REPO_ROOT / "pipeline_state.json").write_text(json.dumps(state, indent=2))


def _launch(cfg: dict) -> subprocess.Popen:
    cmd = [str(PYTHON), "orchestrator.py", "--phase", cfg["mode"]]
    if cfg.get("duration") is not None:
        cmd += ["--duration", str(cfg["duration"])]
    if cfg.get("specialist"):
        cmd += ["--specialist", cfg["specialist"]]
    if cfg.get("model"):
        cmd += ["--model", cfg["model"]]
    if cfg.get("skip"):
        cmd += ["--skip", cfg["skip"]]
    if cfg.get("max_cycles"):
        cmd += ["--max-cycles", str(cfg["max_cycles"])]
    if cfg.get("max_duration"):
        cmd += ["--max-duration", str(cfg["max_duration"])]
    if cfg.get("parallel"):
        cmd += ["--parallel", str(cfg["parallel"])]

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"pipeline_launcher_{ts}.log"
    log_file = open(log_path, "w", encoding="utf-8")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(cmd, cwd=str(REPO_ROOT), stdout=log_file,
                            stderr=subprocess.STDOUT, creationflags=flags)
    cfg["pid"] = proc.pid
    _write_state(cfg)
    print(f"  [OK] Pipeline {cfg['mode']} desacoplado PID={proc.pid}")
    print(f"       Log: {log_path.name}")
    return proc


def _launch_api():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"api_launcher_{ts}.log"
    log_file = open(log_path, "w", encoding="utf-8")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen([str(PYTHON), "query_api.py"], cwd=str(REPO_ROOT),
                            stdout=log_file, stderr=subprocess.STDOUT, creationflags=flags)
    print(f"  [OK] API Neural Horizon PID={proc.pid} (http://localhost:8011/neural/)")
    print(f"       Log: {log_path.name}")
    return proc


def _launch_watchdog(cfg: dict):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"watchdog_launcher_{ts}.log"
    log_file = open(log_path, "w", encoding="utf-8")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    cmd = [str(PYTHON), "tools/watchdog.py"]
    proc = subprocess.Popen(cmd, cwd=str(REPO_ROOT), stdout=log_file,
                            stderr=subprocess.STDOUT, creationflags=flags)
    print(f"  [OK] Watchdog PID={proc.pid} (relanzará con la config del launcher)")
    print(f"       Log: {log_path.name}")
    return proc


def _menu() -> dict:
    print()
    print("=" * 64)
    print("  EXPERTIA — LAUNCHER")
    print("=" * 64)

    print("\nModos disponibles:")
    for i, m in enumerate(MODES, 1):
        print(f"  {i}. {m:<10} {MODES_DESC[m]}")
    while True:
        try:
            sel = input(f"Modo (1-{len(MODES)}) [{MODES[0]}]: ").strip()
            if not sel:
                mode = MODES[0]
                break
            mode = MODES[int(sel) - 1]
            break
        except (ValueError, IndexError):
            print("  Entrada inválida.")

    dur = input("Duración en horas (Enter = sin límite): ").strip()
    duration = float(dur) if dur else None

    spec_in = input("Especialista (Enter = todos; ? lista): ").strip()
    specialist = None
    if spec_in == "?":
        for s in _list_specialists():
            print(f"   {s['domain']:<24} {s['model']}")
        spec_in = input("Especialista: ").strip()
    if spec_in:
        specialist = spec_in

    model_in = input("Modelo (Enter = todos): ").strip()
    model = model_in or None

    wd = input("¿Watchdog anti-congelación? (s/N): ").strip().lower()
    api = input("¿Arrancar también la API Neural Horizon? (s/N): ").strip().lower()

    return {
        "mode": mode, "duration": duration, "specialist": specialist,
        "model": model, "watchdog": wd == "s", "api": api == "s",
        "skip": None, "max_cycles": None, "max_duration": None, "parallel": None,
    }


def main():
    parser = argparse.ArgumentParser(description="Launcher Expertia (menú + CLI)")
    parser.add_argument("--mode", choices=MODES, default=None)
    parser.add_argument("--duration", type=float, default=None,
                        help="Horas; omitir = sin límite temporal")
    parser.add_argument("--specialist", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--skip", default=None)
    parser.add_argument("--max-cycles", type=int, default=0)
    parser.add_argument("--max-duration", type=float, default=0)
    parser.add_argument("--parallel", type=int, default=1)
    parser.add_argument("--with-watchdog", action="store_true")
    parser.add_argument("--api", action="store_true")
    args = parser.parse_args()

    if args.mode:
        cfg = {
            "mode": args.mode, "duration": args.duration,
            "specialist": args.specialist or None, "model": args.model or None,
            "skip": args.skip or None, "max_cycles": args.max_cycles or None,
            "max_duration": args.max_duration or None, "parallel": args.parallel,
            "watchdog": args.with_watchdog, "api": args.api,
        }
    else:
        cfg = _menu()

    print("\n--- Validación previa ---")
    ok_py = Path(PYTHON).exists()
    print(f"  Python:  {'[OK]' if ok_py else '[X] no existe: '+PYTHON}")
    if not ok_py:
        print("  Define EXPERTIA_PYTHON con la ruta correcta.")
        sys.exit(1)
    print(f"  Ollama:  {'[OK]' if _ollama_ok() else '[X] no responde (arranca Ollama primero)'}")
    print(f"  DB:      {'[OK]' if _db_ok() else '[X]'}")
    print(f"  Modo:    {cfg['mode']}")
    print(f"  Duración:{cfg['duration'] if cfg['duration'] else 'sin límite (continuo)'}h")
    print(f"  Especialista: {cfg['specialist'] or 'todos'} | Modelo: {cfg['model'] or 'todos'}")

    existing = _get_pipeline_pid()
    if existing:
        print(f"\n  [!] Ya hay un pipeline corriendo (PID {existing}).")
        ans = input("      ¿Matarlo y relanzar? (s/N): ").strip().lower()
        if ans != "s":
            print("      Abortado (pipeline en curso intacto).")
            sys.exit(0)
        subprocess.run(["taskkill", "/F", "/PID", str(existing)],
                       capture_output=True, timeout=10,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        time.sleep(3)

    print("\n--- Lanzando ---")
    _launch(cfg)
    if cfg["api"] or cfg["mode"] in ("full", "feed"):
        _launch_api()
    if cfg["watchdog"]:
        _launch_watchdog(cfg)
    print("\nProcesos desacoplados de esta terminal. Config guardada en pipeline_state.json.")
    print("El pipeline ya no depende de esta ventana — puedes cerrarla.")


if __name__ == "__main__":
    main()