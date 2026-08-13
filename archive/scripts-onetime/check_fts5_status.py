import sqlite3
conn = sqlite3.connect('E:/expertia-data/incubator.db')
cur = conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name='knowledge_packages_fts'")
print('FTS5 table:', cur.fetchall())
try:
    cur = conn.execute('SELECT count(*) FROM knowledge_packages_fts')
    print('FTS5 count:', cur.fetchone())
except Exception as e:
    print('FTS5 query error:', e)
conn.close()