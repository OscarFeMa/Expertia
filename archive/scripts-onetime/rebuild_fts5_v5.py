import sqlite3
import time

# First pass: cleanup with writable_schema
print("=== Pass 1: Cleanup ===")
conn = sqlite3.connect('E:/expertia-data/incubator.db', isolation_level=None)
conn.execute("PRAGMA writable_schema = ON")

# Delete FTS entries
for name in ['knowledge_packages_fts', 'kp_ai', 'kp_ad', 'kp_au']:
    conn.execute(f"DELETE FROM sqlite_master WHERE name='{name}'")
for name in ['knowledge_packages_fts_data', 'knowledge_packages_fts_idx', 
             'knowledge_packages_fts_content', 'knowledge_packages_fts_docsize',
             'knowledge_packages_fts_config']:
    conn.execute(f"DELETE FROM sqlite_master WHERE name='{name}'")

conn.execute("PRAGMA writable_schema = OFF")
conn.close()

print("Cleanup done. Waiting for schema reload...")
time.sleep(2)

# Second pass: recreate with fresh connection
print("\n=== Pass 2: Recreate ===")
conn = sqlite3.connect('E:/expertia-data/incubator.db', isolation_level=None)

try:
    # Create virtual table
    conn.execute("""
        CREATE VIRTUAL TABLE knowledge_packages_fts
        USING fts5(topic, structured_knowledge, domain,
                   content='knowledge_packages', content_rowid='id')
    """)
    print("Created virtual table")
    
    # Populate
    conn.execute("INSERT INTO knowledge_packages_fts SELECT id, topic, structured_knowledge, domain FROM knowledge_packages")
    print("Populated FTS5")
    
    # Create triggers
    conn.execute("""
        CREATE TRIGGER kp_ai AFTER INSERT ON knowledge_packages BEGIN
            INSERT INTO knowledge_packages_fts(rowid, topic, structured_knowledge, domain)
            VALUES (new.id, new.topic, new.structured_knowledge, new.domain);
        END
    """)
    conn.execute("""
        CREATE TRIGGER kp_ad AFTER DELETE ON knowledge_packages BEGIN
            INSERT INTO knowledge_packages_fts(knowledge_packages_fts, rowid, topic, structured_knowledge, domain)
            VALUES ('delete', old.id, old.topic, old.structured_knowledge, old.domain);
        END
    """)
    conn.execute("""
        CREATE TRIGGER kp_au AFTER UPDATE ON knowledge_packages BEGIN
            INSERT INTO knowledge_packages_fts(knowledge_packages_fts, rowid, topic, structured_knowledge, domain)
            VALUES ('delete', old.id, old.topic, old.structured_knowledge, old.domain);
            INSERT INTO knowledge_packages_fts(rowid, topic, structured_knowledge, domain)
            VALUES (new.id, new.topic, new.structured_knowledge, new.domain);
        END
    """)
    print("Created triggers")
    
    # Verify
    cur = conn.execute("SELECT count(*) FROM knowledge_packages_fts")
    print(f"FTS5 count: {cur.fetchone()[0]}")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

conn.close()