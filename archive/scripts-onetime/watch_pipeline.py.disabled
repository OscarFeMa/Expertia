"""Watch pipeline progress - called by watch_pipeline.ps1"""
import sqlite3, sys

DB = r'D:\proyectos\expertia\incubator-root\storage\incubator.db'
db = sqlite3.connect(DB)

cur = db.execute('SELECT status, phase, elapsed_seconds, updated_at FROM pipeline_status WHERE id=1')
r = cur.fetchone()
if r:
    s, p, e, u = r
    print(f'STATUS:  {s}')
    print(f'PHASE:   {p}')
    print(f'ELAPSED: {e:.0f}s ({(e/3600):.2f}h)')
    print(f'UPDATED: {u}')

cur = db.execute('SELECT checkpoint_num, entities_processed, total_matches, elapsed_seconds FROM cascade_checkpoints ORDER BY rowid DESC LIMIT 1')
r = cur.fetchone()
if r:
    cp, ents, matches, elapsed = r
    rate = ents / elapsed if elapsed > 0 else 0
    total_est = 59000000
    pct = ents / total_est * 100
    rem = total_est - ents
    eta = rem / rate if rate > 0 else 0
    print()
    print(f'CHECKPOINT {cp}:')
    print(f'  Entities:  {ents:,} / {total_est:,} ({pct:.1f}%)')
    print(f'  Matches:   {matches:,}')
    print(f'  Rate:      {rate:.0f} ents/s')
    print(f'  ETA:       {eta/60:.0f} min ({eta/3600:.1f}h)')

cur = db.execute("SELECT domain, COUNT(*) FROM knowledge_packages WHERE domain IN ('Linguistics','EnvironmentalScience') GROUP BY domain")
pkgs = {r[0]: r[1] for r in cur.fetchall()}
print()
print('PACKAGES:')
for d in ('Linguistics','EnvironmentalScience'):
    print(f'  {d}: {pkgs.get(d, 0):,}')

db.close()
