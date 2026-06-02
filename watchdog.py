"""
Watchdog: keeps orchestrator alive by PID file.
Checks every 30s. Restarts if dead.
Will NOT restart if pipeline completed normally (PID file cleaned up)
or if intentionally stopped via API (pipeline_state.json pid is null).
"""
import subprocess, time, os, json
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).parent
LOG = BASE / 'logs' / 'watchdog.log'
PIDFILE = BASE / 'logs' / 'orchestrator.pid'
STATE_FILE = BASE / 'pipeline_state.json'

LOG.parent.mkdir(parents=True, exist_ok=True)

def log(msg):
    line = f"[{datetime.now().strftime('%Y%m%d_%H%M%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')

def read_pid():
    if PIDFILE.exists():
        try:
            return int(PIDFILE.read_text().strip())
        except:
            return None
    return None

def write_pid(pid):
    PIDFILE.write_text(str(pid))

def is_alive(pid):
    if not pid: return False
    try:
        out = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'],
                             capture_output=True, text=True, timeout=10)
        return str(pid) in out.stdout
    except:
        return False

def was_intentional_stop():
    """Return True if the pipeline was intentionally stopped or completed normally."""
    # Check pipeline_state.json — if pid is null, API stop or kill timer fired
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
            if state.get("pid") is None:
                return True
        except:
            pass
    # Check PID file — if missing, orchestrator cleaned up on normal exit
    if not PIDFILE.exists():
        return True
    return False

def start_orchestrator():
    log("Starting orchestrator...")
    proc = subprocess.Popen(
        ['pythonw', 'orchestrator.py'],
        cwd=str(BASE),
        creationflags=subprocess.CREATE_NO_WINDOW,
        stdout=open(BASE / 'logs' / 'orchestrator_stdout.log', 'a'),
        stderr=open(BASE / 'logs' / 'orchestrator_stderr.log', 'a'),
    )
    write_pid(proc.pid)
    log(f"PID {proc.pid}")
    return proc.pid

MAX_FAILURES = 5
BACKOFF_SECONDS = 300
consecutive_failures = 0

log("Watchdog started")
pid = read_pid()
if pid and is_alive(pid):
    log(f"Orchestrator already running (PID {pid})")
else:
    pid = start_orchestrator()
    consecutive_failures = 0

while True:
    time.sleep(30)
    if not is_alive(pid):
        if was_intentional_stop():
            log(f"Orchestrator PID {pid} exited intentionally — watchdog shutting down")
            break
        consecutive_failures += 1
        log(f"ORCHESTRATOR PID {pid} DIED — restarting (failure #{consecutive_failures})")
        if consecutive_failures >= MAX_FAILURES:
            log(f"Circuit breaker: too many failures, backing off {BACKOFF_SECONDS}s")
            time.sleep(BACKOFF_SECONDS)
            consecutive_failures = 0
        pid = start_orchestrator()
    else:
        consecutive_failures = 0
