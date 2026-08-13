import sqlite3
conn = sqlite3.connect('E:/expertia-data/incubator.db')

# Force delete from sqlite_master
print("Force removing FTS5 from sqlite_master...")
conn.execute("DELETE FROM sqlite_master WHERE name='knowledge_packages_fts'")
conn.commit()

# Also clean shadow tables if any remain
for name in ['knowledge_packages_fts_data', 'knowledge_packages_fts_idx', 'knowledge_packages_fts_content', 'knowledge_packages_fts_docsize', 'knowledge_packages_fts_config']:
    try:
        conn.execute(f"DELETE FROM sqlite_master WHERE name='{name}'")
    except:
        pass
conn.commit()

print("Force removed from sqlite_master")

# Verify
cur = conn.execute("SELECT name FROM sqlite_master WHERE name LIKE '%fts%'")
print("Remaining FTS:", cur.fetchall())

conn.close()