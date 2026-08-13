import sqlite3

# Enable writable schema to manually fix sqlite_master
conn = sqlite3.connect('E:/expertia-data/incubator.db', isolation_level=None)
conn.execute("PRAGMA writable_schema = ON")

# First, let's see the exact entries
cur = conn.execute("SELECT type, name, tbl_name, rootpage, sql FROM sqlite_master WHERE name LIKE '%fts%' OR name LIKE '%kp_%'")
for row in cur.fetchall():
    print(f"Entry: type={row[0]}, name={row[1]}, tbl_name={row[2]}, rootpage={row[3]}")
    if row[4]:
        print(f"  SQL: {row[4][:100]}...")

# Delete the FTS table entry from sqlite_master
print("\nDeleting knowledge_packages_fts from sqlite_master...")
conn.execute("DELETE FROM sqlite_master WHERE name='knowledge_packages_fts'")

# Also delete triggers
for trigger in ['kp_ai', 'kp_ad', 'kp_au']:
    conn.execute(f"DELETE FROM sqlite_master WHERE name='{trigger}'")
    print(f"Deleted trigger {trigger}")

# Delete shadow tables if any remain
shadow_tables = [
    'knowledge_packages_fts_data', 'knowledge_packages_fts_idx',
    'knowledge_packages_fts_content', 'knowledge_packages_fts_docsize',
    'knowledge_packages_fts_config',
]
for name in shadow_tables:
    conn.execute(f"DELETE FROM sqlite_master WHERE name='{name}'")
    print(f"Deleted shadow table entry: {name}")

print("\nChanges made. Now need to recreate FTS5...")
print("Verifying cleanup...")
cur = conn.execute("SELECT name FROM sqlite_master WHERE name LIKE '%fts%' OR name LIKE '%kp_%'")
remaining = cur.fetchall()
print(f"Remaining: {remaining}")

# Disable writable schema
conn.execute("PRAGMA writable_schema = OFF")

# Now recreate FTS5
print("\nRecreating FTS5...")
try:
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
    print(f"Error during recreate: {e}")
    import traceback
    traceback.print_exc()