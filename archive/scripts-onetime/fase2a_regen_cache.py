"""Fase 2a: regenerar specialist_match_cache desde knowledge_packages (GROUP BY domain).
Reemplaza la fuente original (matched_qids), que se elimina en Fase 2b."""
import sqlite3, os, time

DB = os.path.join(os.environ.get("WIKIDATA_DB") or "E:/expertia-data", "incubator.db")

conn = sqlite3.connect(DB, timeout=86400)
conn.execute("PRAGMA journal_mode=wal")
conn.execute("PRAGMA synchronous=NORMAL")

start = time.time()
rows = conn.execute("""
    SELECT s.id, s.domain, COUNT(*) as match_count
    FROM knowledge_packages k
    JOIN specialist_registry s ON s.domain = k.domain
    GROUP BY s.id, s.domain
    ORDER BY match_count DESC
""").fetchall()
scan_time = time.time() - start
print(f"Scan complete: {len(rows)} specialists in {scan_time:.0f}s", flush=True)

conn.execute("DELETE FROM specialist_match_cache")
conn.executemany(
    "INSERT INTO specialist_match_cache (specialist_id, domain, match_count) VALUES (?, ?, ?)",
    rows
)
conn.commit()

total = sum(r[2] for r in rows)
for r in rows[:5]:
    print(f"  {r[1]:24s} {r[2]:>14,}")
print(f"Cached {len(rows)} specialists, {total:,} total packages", flush=True)
print(f"Fase2a terminada en {time.time()-start:.0f}s", flush=True)
conn.close()