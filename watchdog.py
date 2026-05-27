"""
Watchdog: keeps orchestrator alive by PID file.
Checks every 30s. Restarts if dead.
"""
import subprocess, time, os
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).parent
LOG = BASE / 'logs' / 'watchdog.log'
PIDFILE = BASE / 'logs' / 'orchestrator.pid'

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

def start_orchestrator():
    log("Starting orchestrator...")
    proc = subprocess.Popen(
        ['python', 'orchestrator.py'],
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
        consecutive_failures += 1
        log(f"ORCHESTRATOR PID {pid} DIED — restarting (failure #{consecutive_failures})")
        if consecutive_failures >= MAX_FAILURES:
            log(f"Circuit breaker: too many failures, backing off {BACKOFF_SECONDS}s")
            time.sleep(BACKOFF_SECONDS)
            consecutive_failures = 0
        pid = start_orchestrator()
    else:
        consecutive_failures = 0
        log(f"OK (PID {pid})")
