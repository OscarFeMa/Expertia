import sqlite3

conn = sqlite3.connect('E:/expertia-data/incubator.db', timeout=60)
try:
    # Drop FTS5 tables and triggers
    shadow_tables = [
        'knowledge_packages_fts_data', 'knowledge_packages_fts_idx',
        'knowledge_packages_fts_content', 'knowledge_packages_fts_docsize',
        'knowledge_packages_fts_config',
    ]
    for name in shadow_tables:
        conn.execute(f'DROP TABLE IF EXISTS {name}')
    conn.execute('DROP TABLE IF EXISTS knowledge_packages_fts')
    for trigger in ['kp_ai', 'kp_ad', 'kp_au']:
        conn.execute(f'DROP TRIGGER IF EXISTS {trigger}')
    conn.commit()
    print('FTS5 dropped')
    
    # Rebuild FTS5
    conn.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_packages_fts
        USING fts5(topic, structured_knowledge, domain,
                   content="knowledge_packages", content_rowid="id")
    ''')
    conn.execute('INSERT INTO knowledge_packages_fts SELECT id, topic, structured_knowledge, domain FROM knowledge_packages')
    conn.execute('''
        CREATE TRIGGER IF NOT EXISTS kp_ai AFTER INSERT ON knowledge_packages BEGIN
            INSERT INTO knowledge_packages_fts(rowid, topic, structured_knowledge, domain)
            VALUES (new.id, new.topic, new.structured_knowledge, new.domain);
        END
    ''')
    conn.execute('''
        CREATE TRIGGER IF NOT EXISTS kp_ad AFTER DELETE ON knowledge_packages BEGIN
            INSERT INTO knowledge_packages_fts(knowledge_packages_fts, rowid, topic, structured_knowledge, domain)
            VALUES ('delete', old.id, old.topic, old.structured_knowledge, old.domain);
        END
    ''')
    conn.execute('''
        CREATE TRIGGER IF NOT EXISTS kp_au AFTER UPDATE ON knowledge_packages BEGIN
            INSERT INTO knowledge_packages_fts(knowledge_packages_fts, rowid, topic, structured_knowledge, domain)
            VALUES ('delete', old.id, old.topic, old.structured_knowledge, old.domain);
            INSERT INTO knowledge_packages_fts(rowid, topic, structured_knowledge, domain)
            VALUES (new.id, new.topic, new.structured_knowledge, new.domain);
        END
    ''')
    conn.commit()
    print('FTS5 rebuilt successfully')
except Exception as e:
    print(f'Error: {e}')
finally:
    conn.close()