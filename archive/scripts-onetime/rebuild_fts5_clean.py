import sqlite3
conn = sqlite3.connect('E:/expertia-data/incubator.db')

# Drop FTS5 table completely
print("Dropping FTS5...")
for name in ['knowledge_packages_fts_data', 'knowledge_packages_fts_idx', 'knowledge_packages_fts_content', 'knowledge_packages_fts_docsize', 'knowledge_packages_fts_config', 'knowledge_packages_fts']:
    try:
        conn.execute(f"DROP TABLE IF EXISTS {name}")
        print(f"  Dropped {name}")
    except Exception as e:
        print(f"  Drop {name}: {e}")

# Drop triggers
for t in ['kp_ai', 'kp_ad', 'kp_au']:
    try:
        conn.execute(f"DROP TRIGGER IF EXISTS {t}")
        print(f"  Dropped trigger {t}")
    except Exception as e:
        print(f"  Drop trigger {t}: {e}")

conn.commit()

# Recreate FTS5 with correct syntax - using external content table
print("\nCreating FTS5...")
conn.execute("""
    CREATE VIRTUAL TABLE knowledge_packages_fts USING fts5(
        topic, structured_knowledge, domain,
        content='knowledge_packages',
        content_rowid='id'
    )
""")
print("FTS5 created")

# Populate from content table
print("Populating FTS5...")
conn.execute("""
    INSERT INTO knowledge_packages_fts(rowid, topic, structured_knowledge, domain)
    SELECT id, topic, structured_knowledge, domain FROM knowledge_packages
""")
print(f"Populated: {conn.total_changes} rows")

# Recreate triggers
conn.execute("""
    CREATE TRIGGER IF NOT EXISTS kp_ai AFTER INSERT ON knowledge_packages BEGIN
        INSERT INTO knowledge_packages_fts(rowid, topic, structured_knowledge, domain)
        VALUES (new.id, new.topic, new.structured_knowledge, new.domain);
    END
""")
conn.execute("""
    CREATE TRIGGER IF NOT EXISTS kp_ad AFTER DELETE ON knowledge_packages BEGIN
        INSERT INTO knowledge_packages_fts(knowledge_packages_fts, rowid, topic, structured_knowledge, domain)
        VALUES ('delete', old.id, old.topic, old.structured_knowledge, old.domain);
    END
""")
conn.execute("""
    CREATE TRIGGER IF NOT EXISTS kp_au AFTER UPDATE ON knowledge_packages BEGIN
        INSERT INTO knowledge_packages_fts(knowledge_packages_fts, rowid, topic, structured_knowledge, domain)
        VALUES ('delete', old.id, old.topic, old.structured_knowledge, old.domain);
        INSERT INTO knowledge_packages_fts(rowid, topic, structured_knowledge, domain)
        VALUES (new.id, new.topic, new.structured_knowledge, new.domain);
    END
""")
print("Triggers created")

conn.commit()

# Test
try:
    cur = conn.execute("SELECT count(*) FROM knowledge_packages_fts")
    print(f"\nFTS5 count: {cur.fetchone()[0]}")
    cur = conn.execute("SELECT topic FROM knowledge_packages_fts WHERE knowledge_packages_fts MATCH 'ecosystem' LIMIT 3")
    print("Test query:", cur.fetchall())
except Exception as e:
    print(f"Test error: {e}")

conn.close()