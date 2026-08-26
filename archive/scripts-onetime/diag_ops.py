import sqlite3
import time

DB = 'E:/expertia-data/incubator.db'

conn = sqlite3.connect(DB, isolation_level=None)
conn.execute("PRAGMA busy_timeout = 8000")

print("=== Diag operaciones ===", flush=True)
try:
    cur = conn.execute("PRAGMA journal_mode")
    print("journal_mode =", cur.fetchone(), flush=True)
except Exception as e:
    print("journal error:", repr(e), flush=True)

try:
    t0 = time.time()
    cur = conn.execute("SELECT count(*) FROM knowledge_packages WHERE qid='Q42'")
    print(f"indexed count = {cur.fetchone()} t={time.time()-t0:.1f}s", flush=True)
except Exception as e:
    print("indexed error:", repr(e), flush=True)

try:
    t0 = time.time()
    cur = conn.execute("SELECT max(id) FROM knowledge_packages")
    print(f"max(id) = {cur.fetchone()} t={time.time()-t0:.1f}s", flush=True)
except Exception as e:
    print("max error:", repr(e), flush=True)

conn.close()
print("done", flush=True)