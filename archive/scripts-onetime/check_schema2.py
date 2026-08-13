import sqlite3
conn = sqlite3.connect('E:/expertia-data/incubator.db')
cur = conn.execute('PRAGMA table_info(cycle_history)')
for r in cur.fetchall():
    print(r)
conn.close()