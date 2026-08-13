import sqlite3, time

conn = sqlite3.connect(r'D:\proyectos\expertia\incubator-root\storage\incubator.db', timeout=30)

tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%fts%'").fetchall()
print(f'FTS tables: {[t[0] for t in tables]}', flush=True)

start = time.time()
conn.execute('DROP TABLE IF EXISTS knowledge_packages_fts')
print(f'DROP FTS: {time.time()-start:.1f}s', flush=True)
conn.commit()
print(f'Committed FTS: {time.time()-start:.1f}s', flush=True)

for name in ['knowledge_packages_fts_data', 'knowledge_packages_fts_idx',
             'knowledge_packages_fts_docsize', 'knowledge_packages_fts_config']:
    start = time.time()
    conn.execute(f'DROP TABLE IF EXISTS {name}')
    print(f'Dropped {name}: {time.time()-start:.1f}s', flush=True)

conn.commit()
conn.close()
print('Done all', flush=True)
