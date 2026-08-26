import sqlite3
import time

DB = 'E:/expertia-data/incubator.db'

print("=== Diag read-only ===", flush=True)
try:
    conn = sqlite3.connect('file:' + DB + '?mode=ro', uri=True)
    conn.execute("PRAGMA busy_timeout = 8000")
    t0 = time.time()
    cur = conn.execute("SELECT count(*) FROM knowledge_packages")
    print(f"readonly count = {cur.fetchone()} t={time.time()-t0:.1f}s", flush=True)
    conn.close()
except Exception as e:
    print("readonly error:", repr(e), flush=True)

print("done", flush=True)