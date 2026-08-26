import sqlite3
import time

DB = 'E:/expertia-data/incubator.db'

conn = sqlite3.connect(DB, isolation_level=None, timeout=15)
print("opened", flush=True)
t0 = time.time()
try:
    cur = conn.execute("SELECT count(*) FROM knowledge_packages")
    print(f"count = {cur.fetchone()} t={time.time()-t0:.1f}s", flush=True)
except Exception as e:
    print("count error:", repr(e), flush=True)
conn.close()
print("done", flush=True)