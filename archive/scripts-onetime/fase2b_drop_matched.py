import sqlite3, os, time, sys

DB = os.path.join(os.environ.get("WIKIDATA_DB") or "E:/expertia-data", "incubator.db")
log = open(r"C:\Users\usuario\AppData\Local\Temp\opencode\fase2b.log", "a", encoding="utf-8")
def out(m):
    print(m, flush=True); log.write(m + "\n"); log.flush()

t0 = time.time()
out(f"[{time.strftime('%H:%M:%S')}] abriendo conexion...")
conn = sqlite3.connect(DB, timeout=86400, isolation_level=None)
conn.execute("PRAGMA busy_timeout=86400000")
t1 = time.time()
out(f"[{time.strftime('%H:%M:%S')}] conexion ok en {t1-t0:.0f}s")
try:
    conn.execute("PRAGMA journal_mode=wal")
    out(f"[{time.strftime('%H:%M:%S')}] journal ok")
except Exception as e:
    out(f"journal_mode: {e}")
try:
    conn.execute("PRAGMA synchronous=NORMAL")
except Exception as e:
    out(f"synchronous: {e}")

out(f"[{time.strftime('%H:%M:%S')}] DROP TABLE matched_qids...")
cur = conn.cursor()
cur.execute("DROP TABLE IF EXISTS matched_qids")
cur.execute("""
    CREATE TABLE matched_qids (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        qid TEXT NOT NULL,
        specialist_id INTEGER NOT NULL,
        entity_id TEXT,
        domain TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        processed INTEGER DEFAULT 0,
        FOREIGN KEY (specialist_id) REFERENCES specialist_registry(id),
        UNIQUE(qid, specialist_id)
    )
""")
cur.execute("CREATE INDEX IF NOT EXISTS idx_matched_qids_specialist ON matched_qids(specialist_id, processed)")
out(f"[{time.strftime('%H:%M:%S')}] DROP+CREATE ok en {time.time()-t1:.0f}s desde conexion")

# checkpoint suave para liberar WAL (sin TRUNCATE forzado; el DROP es DDL -> auto checkpoint en WAL)
try:
    out("wal_checkpoint(TEST,1)")
    r = conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
    out(f"checkpoint: {r}")
except Exception as e:
    out(f"checkpoint: {e}")

conn.close()
out("[FIN fase2b]")
log.close()