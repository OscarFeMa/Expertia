import sqlite3, os

DB = os.path.join(os.environ.get("WIKIDATA_DB") or "E:/expertia-data", "incubator.db")

conn = sqlite3.connect(DB, timeout=86400)
conn.execute("PRAGMA journal_mode=wal")
cur = conn.cursor()

print("=== cartridge_offsets ===")
for r in cur.execute("SELECT status, COUNT(*) FROM cartridge_offsets GROUP BY status ORDER BY 2 DESC"):
    print(r)

print("=== specialist_registry ===")
cur.execute("SELECT id, domain, model, status, tier, packages_absorbed, wikidata_total_entities, last_wikidata_download FROM specialist_registry ORDER BY id")
for r in cur.fetchall():
    print(r)

print("=== pipeline_status ===")
for r in cur.execute("SELECT * FROM pipeline_status ORDER BY id"):
    print(r)

conn.close()
print("fin")