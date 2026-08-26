"""
Watchdog v3 — anti-congelación genérico para Expertia.
- Monitorea el pipeline activo (web/nurture/feed/full) sin hardcodear especialistas.
- Detección de congelación: si updated_at de pipeline_status no avanza Y no hay
  filas nuevas en activity_log durante STUCK_MINUTES → kill + relanzamiento
  con la MISMA config guardada en pipeline_state.json por tools/launcher.py.
- Strike-limit por especialista: tras N congelaciones lo marca BLOCKED en DB.
- Crash-loop guard: más de 5 relanzamientos en 30 min → abandona.
- Hard timeout opcional (--max-hours, 0 = sin límite).
"""
import argparse
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    filename=str(LOG_DIR / "watchdog.log"),
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("watchdog")

PYTHON = os.environ.get(
    "EXPERTIA_PYTHON",
    r"C:\Users\usuario\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe",
)
DB_PATH = Path(os.environ.get("EXPERTIA_DB", r"E:\expertia-data\incubator.db"))
STATE_FILE = REPO_ROOT / "tools" / "watchdog_state.json"
PIPELINE_STATE_FILE = REPO_ROOT / "pipeline_state.json"

STRIKE_LIMIT = 5        # congelaciones por especialista antes de BLOCKED
STUCK_MINUTES = 20      # sin heartbeat ni actividad -> congelado
CHECK_INTERVAL = 60     # segundos entre chequeos
HARD_TIMEOUT_HOURS = 0  # 0 = sin límite
RESTART_BURST = 5       # máx relanzamientos
RESTART_WINDOW = 1800   # en esta ventana (30 min)


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {
        "start_epoch": time.time(),
        "strike_counts": {},
        "blocked": [],
        "last_activity_id": None,
        "last_heartbeat": None,
        "stuck_since": None,
        "current_config": None,
    }


def _save_state(state: dict):
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        logger.warning(f"Failed to save state: {e}")


def _load_pipeline_config() -> dict:
    """Lee la config original escrita por tools/launcher.py."""
    try:
        data = json.loads(PIPELINE_STATE_FILE.read_text())
        return data
    except Exception:
        return {}


def _is_pid_alive(pid: int) -> bool:
    if not pid:
        return False
    try:
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                           capture_output=True, text=True, timeout=5,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return bool(re.search(rf"\b{re.escape(str(pid))}\b", r.stdout))
    except Exception:
        return False


def _get_pipeline_pid() -> int | None:
    cfg = _load_pipeline_config()
    pid = cfg.get("pid")
    if pid and _is_pid_alive(pid):
        return int(pid)
    try:
        r = subprocess.run(["tasklist", "/FO", "CSV", "/FI", "IMAGENAME eq python.exe"],
                           capture_output=True, text=True, timeout=10,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        import csv, io
        for row in csv.reader(io.StringIO(r.stdout)):
            if len(row) >= 2 and row[0].strip('"') == "python.exe":
                pid_candidate = int(row[1].strip('"'))
                if pid_candidate and _is_pid_alive(pid_candidate):
                    try:
                        r2 = subprocess.run(
                            ["wmic", "process", "where", f"ProcessId={pid_candidate}",
                             "get", "CommandLine", "/value"],
                            capture_output=True, text=True, timeout=8,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                        if "orchestrator.py" in r2.stdout and "--phase" in r2.stdout:
                            return pid_candidate
                    except Exception:
                        continue
    except Exception:
        pass
    return None


def _get_pipeline_hb() -> tuple:
    """Returns (updated_at_str, current_specialist) from pipeline_status (fila id=1)."""
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5) as conn:
            row = conn.execute(
                "SELECT updated_at, current_specialist FROM pipeline_status WHERE id=1"
            ).fetchone()
            return row if row else (None, None)
    except Exception:
        return None, None


def _get_max_activity_id() -> int | None:
    try:
        with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5) as conn:
            row = conn.execute("SELECT MAX(id) FROM activity_log").fetchone()
            return row[0] if row and row[0] else None
    except Exception:
        return None


def _relaunch_pipeline(state: dict) -> bool:
    """Relanza el pipeline con la config original de pipeline_state.json."""
    cfg = _load_pipeline_config() or state.get("current_config") or {}
    mode = cfg.get("mode") or "web"
    cmd = [str(PYTHON), "orchestrator.py", "--phase", mode]
    if cfg.get("duration_hours"):
        cmd += ["--duration", str(cfg["duration_hours"])]
    if cfg.get("specialist") and cfg["specialist"] not in ("", "all"):
        cmd += ["--specialist", cfg["specialist"]]
    if cfg.get("model") and cfg["model"] not in ("", "all"):
        cmd += ["--model", cfg["model"]]
    if cfg.get("skip"):
        cmd += ["--skip", cfg["skip"]]
    if cfg.get("max_cycles"):
        cmd += ["--max-cycles", str(cfg["max_cycles"])]
    if cfg.get("max_duration"):
        cmd += ["--max-duration", str(cfg["max_duration"])]
    blocked = state.get("blocked", [])
    if blocked and not cfg.get("skip"):
        cmd += ["--skip", ",".join(blocked)]

    try:
        log_path = LOG_DIR / f"pipeline_watchdog_{int(time.time())}.log"
        log_file = open(log_path, "w", encoding="utf-8")
        proc = subprocess.Popen(cmd, stdout=log_file, stderr=log_file,
                                cwd=str(REPO_ROOT),
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        cfg["pid"] = proc.pid
        cfg["watchdog"] = True
        PIPELINE_STATE_FILE.write_text(json.dumps(cfg, indent=2))
        logger.info(f"Pipeline {mode} relanzado PID={proc.pid} (cmd={' '.join(cmd)})")
        return True
    except Exception as e:
        logger.error(f"Fallo al relanzar pipeline: {e}")
        return False


def _kill_process(pid: int):
    try:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                       capture_output=True, timeout=10,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        logger.info(f"Killed PID {pid}")
    except Exception as e:
        logger.warning(f"Failed to kill PID {pid}: {e}")


def _mark_blocked(domain: str):
    try:
        with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
            conn.execute(
                "UPDATE specialist_registry SET status='BLOCKED', updated_at=CURRENT_TIMESTAMP "
                "WHERE domain=?", (domain,))
        logger.warning(f"Specialist {domain} marcado BLOCKED en DB")
    except Exception as e:
        logger.error(f"Fallo al marcar BLOCKED {domain}: {e}")


def _shutdown(reason: str):
    logger.warning(f"WATCHDOG APAGADO: {reason}")
    logger.info("Watchdog finaliza — no apaga el PC (solo monitorea)")


def main():
    parser = argparse.ArgumentParser(description="Watchdog v3 anti-congelación")
    parser.add_argument("--check-interval", type=int, default=CHECK_INTERVAL)
    parser.add_argument("--stuck-minutes", type=int, default=STUCK_MINUTES)
    parser.add_argument("--strike-limit", type=int, default=STRIKE_LIMIT)
    parser.add_argument("--max-hours", type=float, default=HARD_TIMEOUT_HOURS)
    args = parser.parse_args()

    state = _load_state()
    logger.info("=" * 60)
    logger.info("WATCHDOG V3 STARTED (anti-congelación genérico)")
    logger.info(f"Check: {args.check_interval}s | Stuck: {args.stuck_minutes}min | Strikes: {args.strike_limit}")
    logger.info(f"Hard timeout: {args.max_hours}h" if args.max_hours else "Sin hard timeout")
    logger.info(f"DB: {DB_PATH}")
    logger.info(f"PID inicial: {_get_pipeline_pid()}")
    logger.info("=" * 60)

    start_epoch = state.get("start_epoch", time.time())
    deadline = start_epoch + args.max_hours * 3600 if args.max_hours else None
    restart_attempts: list[float] = []
    cycle_count = 0

    while True:
        now = time.time()
        cycle_count += 1
        if cycle_count % 10 == 0:
            logger.info(f"Heartbeat cycle={cycle_count} blocked={state.get('blocked', [])}")

        if deadline and now >= deadline:
            _shutdown(f"Hard timeout de {args.max_hours}h alcanzado")
            break

        pid = _get_pipeline_pid()

        # ── Crash / proceso muerto: relanzar con la config original ──
        if not pid:
            logger.warning("Pipeline NOT RUNNING. Relanzando...")
            restart_attempts = [t for t in restart_attempts if now - t < RESTART_WINDOW]
            if len(restart_attempts) >= RESTART_BURST:
                logger.error(f"Crash loop ({RESTART_BURST} restarts en {RESTART_WINDOW}s). Abandonando.")
                _shutdown("Crash loop detectado")
                break
            restart_attempts.append(now)
            if _relaunch_pipeline(state):
                time.sleep(10)
            else:
                logger.error("Relanzamiento falló — reintento en 60s")
            time.sleep(args.check_interval)
            continue

        # ── Congelación: heartbeat sin avanzar + sin actividad nueva ──
        updated_at, specialist = _get_pipeline_hb()
        max_activity = _get_max_activity_id()
        hb_key = (updated_at or "") + f":{specialist or ''}:{max_activity or ''}"

        if hb_key != state.get("last_heartbeat"):
            state["last_heartbeat"] = hb_key
            state["stuck_since"] = None
            _save_state(state)
            time.sleep(args.check_interval)
            continue

        # heartbeat sin cambios desde el último chequeo
        if state.get("stuck_since") is None:
            state["stuck_since"] = now
            _save_state(state)
        else:
            stuck = now - state["stuck_since"]
            if stuck >= args.stuck_minutes * 60:
                domain = specialist or "desconocido"
                strikes = state.setdefault("strike_counts", {}).get(domain, 0) + 1
                state["strike_counts"][domain] = strikes
                logger.warning(
                    f"CONGELADO: {domain} sin heartbeat/actividad {stuck/60:.0f}min "
                    f"(updated_at={updated_at}, activity_id={max_activity}) — Strike {strikes}/{args.strike_limit}")

                if pid:
                    _kill_process(pid)
                    time.sleep(3)

                if strikes >= args.strike_limit and domain != "desconocido":
                    logger.warning(f">>> {domain} BLOQUEADO tras {strikes} congelaciones <<<")
                    state.setdefault("blocked", [])
                    if domain not in state["blocked"]:
                        state["blocked"].append(domain)
                    _mark_blocked(domain)
                    state["strike_counts"][domain] = 0

                state["stuck_since"] = None
                _save_state(state)

                restart_attempts = [t for t in restart_attempts if now - t < RESTART_WINDOW]
                if len(restart_attempts) >= RESTART_BURST:
                    logger.error("Crash loop tras congelación. Abandonando.")
                    _shutdown("Crash loop detectado")
                    break
                restart_attempts.append(now)
                if _relaunch_pipeline(state):
                    time.sleep(10)
                time.sleep(5)

        time.sleep(args.check_interval)

    logger.info("Watchdog exiting.")


if __name__ == "__main__":
    main()