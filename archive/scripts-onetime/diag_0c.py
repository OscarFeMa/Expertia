import sqlite3
import time

DB = 'E:/expertia-data/incubator.db'

conn = sqlite3.connect(DB, isolation_level=None)
conn.execute("PRAGMA busy_timeout = 10000")

print("=== Diagnostico ===", flush=True)
try:
    cur = conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
    print("PASSIVE row =", cur.fetchone(), flush=True)
except Exception as e:
    print("PASSIVE error:", repr(e), flush=True)

try:
    cur = conn.execute("SELECT count(*) FROM knowledge_packages")
    print("count knowledge_packages =", cur.fetchone(), flush=True)
except Exception as e:
    print("count error:", repr(e), flush=True)

try:
    cur = conn.execute("PRAGMA integrity_check")
    r = cur.fetchone()
    print("integrity_check =", r, flush=True)
except Exception as e:
    print("integrity error:", repr(e), flush=True)

conn.close()
print("done", flush=True)