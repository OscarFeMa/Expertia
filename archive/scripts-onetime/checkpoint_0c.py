import sqlite3
import time
import os

DB = 'E:/expertia-data/incubator.db'
LOG = r'C:\Users\usuario\AppData\Local\Temp\opencode\checkpoint_0c.log'

def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')

log("=== Checkpoint v5 (TRUNCATE, conexion unica, sin competencia) ===")
t0 = time.time()

conn = sqlite3.connect(DB, isolation_level=None, timeout=7200)
conn.execute("PRAGMA busy_timeout = 7200000")
log("conexion abierta")

last_log = time.time()
last_prog = None
while True:
    try:
        cur = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        row = cur.fetchone()
    except sqlite3.OperationalError as e:
        log(f"checkpoint error: {e!r}")
        break
    busy, logf, chkf = (row[0], row[1], row[2]) if len(row) >= 3 else (None, None, None)
    prog = f"{logf}log/{chkf}chk"
    now = time.time()
    if prog != last_prog or (now - last_log) >= 300:
        db = os.path.getsize(DB) / 1e9
        wal = os.path.getsize(DB + '-wal') / 1e9 if os.path.exists(DB + '-wal') else 0
        log(f"busy={busy} frames={prog} db={db:.1f}GB wal={wal:.1f}GB t={(now-t0)/60:.0f}min")
        last_log = now
        last_prog = prog
    if busy == 0 and logf == 0:
        break
    if busy == 0 and chkf >= logf and logf > 0:
        break
    time.sleep(30)

dt = time.time() - t0
log(f"checkpoint completo en {dt/60:.1f} min")

try:
    cur = conn.execute("SELECT count(*) FROM knowledge_packages")
    log(f"knowledge_packages total = {cur.fetchone()[0]}")
except Exception as e:
    log(f"count error: {e!r}")

db = os.path.getsize(DB) / 1e9
wal = os.path.getsize(DB + '-wal') / 1e9 if os.path.exists(DB + '-wal') else 0
log(f"FIN: db={db:.1f}GB wal={wal:.1f}GB")
conn.close()
log("=== fin ===")