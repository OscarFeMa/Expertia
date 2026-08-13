import sqlite3

conn = sqlite3.connect('E:/expertia-data/incubator.db')

# Drop everything FTS5 related
shadow_tables = [
    'knowledge_packages_fts_data', 'knowledge_packages_fts_idx',
    'knowledge_packages_fts_content', 'knowledge_packages_fts_docsize',
    'knowledge_packages_fts_config',
]
for name in shadow_tables:
    try:
        conn.execute(f"DROP TABLE IF EXISTS {name}")
        print(f"Dropped {name}")
    except Exception as e:
        print(f"Drop {name}: {e}")

try:
    conn.execute("DROP TRIGGER IF EXISTS kp_ai")
    conn.execute("DROP TRIGGER IF EXISTS kp_ad")
    conn.execute("DROP TRIGGER IF EXISTS kp_au")
    conn.execute("DROP TABLE IF EXISTS knowledge_packages_fts")
    print("Dropped FTS5 virtual table and triggers")
except Exception as e:
    print(f"Drop FTS5: {e}")

conn.commit()

# Recreate FTS5 virtual table
try:
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_packages_fts
        USING fts5(topic, structured_knowledge, domain,
                   content='knowledge_packages', content_rowid='id')
    """)
    print("Created FTS5 virtual table")
except Exception as e:
    print(f"Create FTS5: {e}")

# Populate FTS5
try:
    conn.execute("""
        INSERT INTO knowledge_packages_fts
        SELECT id, topic, structured_knowledge, domain FROM knowledge_packages
    """)
    print(f"Populated FTS5: {conn.total_changes} rows")
except Exception as e:
    print(f"Populate FTS5: {e}")

# Recreate triggers
try:
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
    print("Recreated triggers")
except Exception as e:
    print(f"Create triggers: {e}")

conn.commit()
print("Done!")
conn.close()