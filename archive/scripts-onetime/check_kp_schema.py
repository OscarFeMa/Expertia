import sqlite3

conn = sqlite3.connect('E:/expertia-data/incubator.db')
cur = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='knowledge_packages'")
row = cur.fetchone()
if row:
    print(row[0])
conn.close()