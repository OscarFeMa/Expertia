import sqlite3
conn = sqlite3.connect('E:/expertia-data/incubator.db')
cur = conn.execute('SELECT name FROM sqlite_master WHERE type="table" AND name="specialist_registry"')
print('Table exists:', cur.fetchone())
cur = conn.execute('PRAGMA table_info(specialist_registry)')
for r in cur.fetchall():
    print(r)
conn.close()