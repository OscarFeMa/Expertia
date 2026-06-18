"""
Watchdog v2 for nurture pipeline.
- Kills + restarts nurture if stuck for 3h on same specialist
- 10 strikes per specialist → marks BLOCKED, skips on restart
- All fed (non-blocked >= Legend) → shutdown
- All blocked → shutdown
- Hard 96h timeout → shutdown
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

STATE_FILE = REPO_ROOT / "tools" / "watchdog_state.json"
PIPELINE_STATE_FILE = REPO_ROOT / "pipeline_state.json"
DB_PATH = REPO_ROOT / "storage" / "incubator.db"
UV_PYTHON = os.environ.get("WATCHDOG_PYTHON_PATH") or shutil.which("python") or "python"

STRIKE_LIMIT = 10       # max stuck detections per specialist before BLOCKED
STUCK_HOURS = 3         # hours without new cycle to consider stuck
HARD_TIMEOUT_HOURS = 96  # max total runtime
CHECK_INTERVAL = 60      # seconds between checks

# ── Nurture target specialist IDs ──────────────────────────────────────
NURTURE_IDS = {5026: "Linguistics", 5027: "Psychology",
               5028: "EnvironmentalScience", 5029: "Sociology"}
ID_BY_DOMAIN = {v: k for k, v in NURTURE_IDS.items()}


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {
        "start_epoch": time.time(),
        "stuck_counts": {d: 0 for d in NURTURE_IDS.values()},
        "blocked": [],
        "last_cycle_id": {},
        "stuck_since": None,
        "current_specialist": None,
    }


def _save_state(state: dict):
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        logger.warning(f"Failed to save state: {e}")


def _find_pwsh() -> str:
    candidates = [
        r"C:\Program Files\PowerShell\7\pwsh.exe",
        r"C:\Program Files\PowerShell\6\pwsh.exe",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    try:
        r = subprocess.run(["where", "pwsh"], capture_output=True, text=True, timeout=3,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        if r.returncode == 0:
            return r.stdout.strip().splitlines()[0].strip()
    except Exception:
        pass
    return "pwsh"


def _is_pid_alive(pid: int) -> bool:
    if not pid:
        return False
    try:
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                           capture_output=True, text=True, timeout=5,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        return bool(re.search(rf"\b{re.escape(str(pid))}\b", r.stdout))
    except Exception:
        return False


def _get_nurture_pid() -> int | None:
    try:
        if PIPELINE_STATE_FILE.exists():
            data = json.loads(PIPELINE_STATE_FILE.read_text())
            pid = data.get("pid")
            if pid and _is_pid_alive(pid):
                return pid
    except Exception:
        pass
    try:
        pwsh = _find_pwsh()
        r = subprocess.run([pwsh, "-NoProfile", "-Command",
            "Get-Process python -ErrorAction SilentlyContinue | "
            "Where-Object { $_.CommandLine -match 'orchestrator' } | "
            "Select-Object -ExpandProperty Id"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW)
        for line in r.stdout.strip().splitlines():
            line = line.strip()
            if line.isdigit():
                return int(line)
    except Exception:
        pass
    return None


def _get_pipeline_info() -> tuple:
    """Returns (current_specialist, current_cycle, updated_at_str) or None tuple."""
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=2.0)
        row = conn.execute(
            "SELECT current_specialist, current_cycle, updated_at "
            "FROM pipeline_status ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row:
            return row[0], row[1], row[2]
    except Exception:
        pass
    return None, None, None


def _get_max_cycle_id_for_specialist(domain: str) -> int | None:
    sid = ID_BY_DOMAIN.get(domain)
    if not sid:
        return None
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=2.0)
        row = conn.execute(
            "SELECT MAX(id) FROM cycle_history WHERE specialist_id = ?", (sid,)
        ).fetchone()
        conn.close()
        return row[0] if row and row[0] else None
    except Exception:
        return None


def _get_non_blocked_tiers(state: dict) -> dict:
    """Returns {domain: tier} for all non-blocked specialists."""
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=2.0)
        blocked = set(state.get("blocked", []))
        rows = conn.execute(
            "SELECT domain, tier FROM specialist_registry"
        ).fetchall()
        conn.close()
        return {r[0]: r[1] for r in rows if r[0] not in blocked}
    except Exception:
        return {}


def _start_nurture(skip_list: list[str] = None) -> bool:
    skip_list = skip_list or []
    cmd = [str(UV_PYTHON), "orchestrator.py", "--phase", "nurture", "--duration", "99999"]
    if skip_list:
        cmd += ["--skip", ",".join(skip_list)]
    try:
        log_path = LOG_DIR / f"orchestrator_watchdog_{int(time.time())}.log"
        log_file = open(log_path, "w", encoding="utf-8")
        proc = subprocess.Popen(cmd, stdout=log_file, stderr=log_file,
                                 cwd=str(REPO_ROOT),
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        logger.info(f"Nurture started PID={proc.pid}, skip={skip_list}, log={log_path.name}")
        return True
    except Exception as e:
        logger.error(f"Failed to start nurture: {e}")
        return False


def _kill_process(pid: int):
    try:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                       capture_output=True, timeout=5,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        logger.info(f"Killed PID {pid}")
    except Exception as e:
        logger.warning(f"Failed to kill PID {pid}: {e}")


def _mark_blocked(domain: str):
    sid = ID_BY_DOMAIN.get(domain)
    if not sid:
        return
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=5.0)
        conn.execute("UPDATE specialist_registry SET status = 'BLOCKED' WHERE id = ?", (sid,))
        conn.commit()
        conn.close()
        logger.warning(f"Marked {domain} as BLOCKED in DB")
    except Exception as e:
        logger.error(f"Failed to mark BLOCKED: {e}")


def _shutdown_pc(reason: str):
    logger.warning(f"SHUTDOWN DISABLED: {reason}")
    logger.info("Shutdown skipped — watchdog solo monitorea, no apaga")


def main():
    parser = argparse.ArgumentParser(description="Watchdog v2")
    parser.add_argument("--max-hours", type=float, default=HARD_TIMEOUT_HOURS)
    parser.add_argument("--check-interval", type=int, default=CHECK_INTERVAL)
    parser.add_argument("--stuck-hours", type=float, default=STUCK_HOURS)
    parser.add_argument("--strike-limit", type=int, default=STRIKE_LIMIT)
    args = parser.parse_args()

    state = _load_state()
    initial_pid = _get_nurture_pid()

    logger.info("=" * 60)
    logger.info("WATCHDOG V2 STARTED")
    logger.info(f"Check: {args.check_interval}s | Stuck: {args.stuck_hours}h | Strike limit: {args.strike_limit}")
    logger.info(f"Hard timeout: {args.max_hours}h")
    logger.info(f"Nurture PID: {initial_pid}")
    logger.info(f"Blocked so far: {state.get('blocked', [])}")
    logger.info(f"Strikes: {state.get('stuck_counts', {})}")
    logger.info("=" * 60)

    start_epoch = state.get("start_epoch", time.time())
    deadline = start_epoch + args.max_hours * 3600
    cycle_count = 0
    restart_rate: list[float] = []

    while True:
        now = time.time()
        cycle_count += 1

        # ── Heartbeat ──
        if cycle_count % 10 == 0:
            logger.info(f"Heartbeat cycle={cycle_count} blocked={state.get('blocked',[])} strikes={state.get('stuck_counts',{})}")

        # ── Hard timeout ──
        if now >= deadline:
            _shutdown_pc(f"Tiempo maximo de {args.max_hours}h alcanzado")
            break

        # ── Check if ALL blocked ──
        blocked = set(state.get("blocked", []))
        all_targets = set(NURTURE_IDS.values())
        if all_targets.issubset(blocked):
            _shutdown_pc("Todos los especialistas estan bloqueados — nada que hacer")
            break

        # ── Check all non-blocked reached Legend ──
        remaining = _get_non_blocked_tiers(state)
        non_blocked_done = all(tier >= 4 for tier in remaining.values()) if remaining else False
        if non_blocked_done and remaining:
            done_list = [d for d, t in remaining.items() if t >= 4]
            logger.info(f"All non-blocked done: {done_list}")
            _shutdown_pc("Todos los especialistas no bloqueados alcanzaron Legend")
            break

        # ── Get pipeline status ──
        specialist, pipeline_cycle, updated_at = _get_pipeline_info()
        if not specialist:
            time.sleep(args.check_interval)
            continue

        # ── Check if specialist changed ──
        if specialist != state.get("current_specialist"):
            logger.info(f"Specialist changed: {state.get('current_specialist')} -> {specialist}")
            state["current_specialist"] = specialist
            state["stuck_since"] = None
            _save_state(state)

        # ── Check for new cycle ──
        if specialist in ID_BY_DOMAIN:
            max_id = _get_max_cycle_id_for_specialist(specialist)
            prev_id = state.get("last_cycle_id", {}).get(specialist)
            if max_id and max_id != prev_id:
                logger.info(f"New cycle #{max_id} for {specialist} (was {prev_id})")
                state.setdefault("last_cycle_id", {})[specialist] = max_id
                state["stuck_since"] = None
                _save_state(state)

        # ── Stuck detection ──
        if specialist in ID_BY_DOMAIN:
            if state.get("stuck_since") is None:
                state["stuck_since"] = now
                _save_state(state)
            else:
                stuck_duration = now - state["stuck_since"]
                if stuck_duration > args.stuck_hours * 3600:
                    strikes = state.setdefault("stuck_counts", {}).get(specialist, 0) + 1
                    state["stuck_counts"][specialist] = strikes
                    logger.warning(f"STUCK: {specialist} ({stuck_duration/3600:.1f}h) Strike {strikes}/{args.strike_limit}")

                    # Kill nurture
                    nurture_pid = _get_nurture_pid()
                    if nurture_pid:
                        _kill_process(nurture_pid)
                        time.sleep(3)

                    # Check if strike limit reached
                    if strikes >= args.strike_limit:
                        logger.warning(f">>> {specialist} BLOQUEADO tras {strikes} strikes <<<")
                        state.setdefault("blocked", [])
                        if specialist not in state["blocked"]:
                            state["blocked"].append(specialist)
                        _mark_blocked(specialist)
                        # Reset strike counter for this specialist
                        state["stuck_counts"][specialist] = 0

                    # Restart nurture with current skip list
                    current_skip = state.get("blocked", [])
                    _start_nurture(current_skip if current_skip else None)

                    # Reset stuck timer
                    state["stuck_since"] = None
                    _save_state(state)

                    # Brief pause after restart
                    time.sleep(10)

        # ── Process alive check ──
        pid = _get_nurture_pid()
        if not pid:
            logger.warning("Nurture not running. Launching...")
            restart_rate = [t for t in restart_rate if now - t < 1800]
            if len(restart_rate) >= 5:
                logger.error("Crash loop (5 restarts in 30min). Shutting down.")
                _shutdown_pc("Crash loop detectado")
                break
            restart_rate.append(now)
            current_skip = state.get("blocked", [])
            _start_nurture(current_skip if current_skip else None)
            time.sleep(5)

        time.sleep(args.check_interval)

    logger.info("Watchdog exiting.")


if __name__ == "__main__":
    main()
