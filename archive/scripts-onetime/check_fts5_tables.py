import sqlite3
conn = sqlite3.connect('E:/expertia-data/incubator.db')
cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%fts%'")
print("FTS tables:", cur.fetchall())
cur = conn.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE '%kp_%'")
print("Triggers:", cur.fetchall())
cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'knowledge_packages_fts%'")
print("Shadow tables:", cur.fetchall())
conn.close()