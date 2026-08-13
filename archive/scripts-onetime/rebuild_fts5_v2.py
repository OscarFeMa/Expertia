import sqlite3
conn = sqlite3.connect('E:/expertia-data/incubator.db')

# Try DROP TABLE on the virtual table
print("Trying DROP TABLE on virtual table...")
try:
    conn.execute("DROP TABLE IF EXISTS knowledge_packages_fts")
    print("Dropped virtual table")
except Exception as e:
    print(f"Drop virtual table error: {e}")

# Try dropping shadow tables
for name in ['knowledge_packages_fts_data', 'knowledge_packages_fts_idx', 'knowledge_packages_fts_content', 'knowledge_packages_fts_docsize', 'knowledge_packages_fts_config']:
    try:
        conn.execute(f"DROP TABLE IF EXISTS {name}")
        print(f"Dropped {name}")
    except Exception as e:
        print(f"Drop {name}: {e}")

# Drop triggers
for t in ['kp_ai', 'kp_ad', 'kp_au']:
    try:
        conn.execute(f"DROP TRIGGER IF EXISTS {t}")
        print(f"Dropped trigger {t}")
    except Exception as e:
        print(f"Drop trigger {t}: {e}")

conn.commit()

# Verify
cur = conn.execute("SELECT name FROM sqlite_master WHERE name LIKE '%fts%'")
print("Remaining FTS:", cur.fetchall())

# Now try creating fresh
print("\nCreating fresh FTS5...")
try:
    conn.execute("""
        CREATE VIRTUAL TABLE knowledge_packages_fts USING fts5(
            topic, structured_knowledge, domain,
            content='knowledge_packages',
            content_rowid='id'
        )
    """)
    print("FTS5 created successfully")
    
    # Populate
    conn.execute("""
        INSERT INTO knowledge_packages_fts(rowid, topic, structured_knowledge, domain)
        SELECT id, topic, structured_knowledge, domain FROM knowledge_packages
    """)
    print(f"Populated: {conn.total_changes} rows")
    
    # Triggers
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
    conn.commit()
    print("Triggers created, committed")
    
    # Test
    cur = cur.execute("SELECT count(*) FROM knowledge_packages_fts")
    cur = conn.execute("SELECT count(*) FROM knowledge_packages_fts")
    print(f"FTS5 count: {cur.fetchone()[0]}")
    
except Exception as e:
    print(f"Error: {e}")

conn.close()