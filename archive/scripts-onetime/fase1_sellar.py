import sqlite3, os

DB = os.path.join(os.environ.get("WIKIDATA_DB") or "E:/expertia-data", "incubator.db")

conn = sqlite3.connect(DB, timeout=86400)
conn.execute("PRAGMA journal_mode=wal")
conn.execute("PRAGMA synchronous=NORMAL")
cur = conn.cursor()

# 1. Sellar cartridge_offsets
n_co = cur.execute("UPDATE cartridge_offsets SET status='COMPLETED'").rowcount
print(f"cartridge_offsets -> COMPLETED: {n_co} filas")

# 2. wikidata_total_entities = packages_absorbed (proxy Fase A)
n_wd = cur.execute("UPDATE specialist_registry SET wikidata_total_entities = packages_absorbed").rowcount
print(f"specialist_registry wikidata_total_entities: {n_wd} filas")

# 3. pipeline_status -> Phase A COMPLETED (sin tocar la ejecución Phase B viva)
n_ps = cur.execute(
    "UPDATE pipeline_status SET phase='Phase A: COMPLETED - dump scan + matched QIDs', status='IDLE' WHERE phase LIKE 'Phase A%'"
).rowcount
print(f"pipeline_status Phase A -> COMPLETED: {n_ps} filas")

conn.commit()

print("=== Verificacion ===")
for r in cur.execute("SELECT status, COUNT(*) FROM cartridge_offsets GROUP BY status"):
    print(r)
for r in cur.execute("SELECT COUNT(*), SUM(wikidata_total_entities=packages_absorbed) FROM specialist_registry"):
    print("specialist_registry total / con proxy aplicado:", r)
for r in cur.execute("SELECT id, phase, status FROM pipeline_status"):
    print("pipeline_status:", r)

conn.close()
print("fin fase1_sellar.py")