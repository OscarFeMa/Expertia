import sqlite3
conn = sqlite3.connect('E:/expertia-data/incubator.db')
cur = conn.execute('SELECT * FROM pragma_module_list WHERE name="fts5"')
print(cur.fetchall())
conn.close()