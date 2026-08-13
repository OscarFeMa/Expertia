import sqlite3

# Connect fresh
conn = sqlite3.connect('E:/expertia-data/incubator.db', isolation_level=None)  # autocommit mode

# First, let's check what's in sqlite_master for the FTS table
cur = conn.execute("SELECT sql FROM sqlite_master WHERE name='knowledge_packages_fts'")
row = cur.fetchone()
if row:
    print("Existing FTS5 SQL:")
    print(row[0])

# Try to use the FTS5 "rebuild" command
print("\nTrying FTS5 rebuild command...")
try:
    conn.execute("INSERT INTO knowledge_packages_fts(knowledge_packages_fts) VALUES('rebuild')")
    print("Rebuild command executed")
except Exception as e:
    print(f"Rebuild error: {e}")

# Try to query the table to see the actual error
try:
    cur = conn.execute("SELECT * FROM knowledge_packages_fts LIMIT 1")
    print("Query worked:", cur.fetchone())
except Exception as e:
    print(f"Query error: {e}")

# Check if there's a way to force drop
# Let's try using the sqlite3 command line tool via subprocess
import subprocess
import tempfile
import os

# Create a SQL script
sql_script = """
DROP TABLE IF EXISTS knowledge_packages_fts_data;
DROP TABLE IF EXISTS knowledge_packages_fts_idx;
DROP TABLE IF EXISTS knowledge_packages_fts_content;
DROP TABLE IF EXISTS knowledge_packages_fts_docsize;
DROP TABLE IF EXISTS knowledge_packages_fts_config;
DROP TABLE IF EXISTS knowledge_packages_fts;
DROP TRIGGER IF EXISTS kp_ai;
DROP TRIGGER IF EXISTS kp_ad;
DROP TRIGGER IF EXISTS kp_au;
"""

with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
    f.write(sql_script)
    sql_file = f.name

print("\nRunning sqlite3 command line...")
result = subprocess.run(['sqlite3', 'E:/expertia-data/incubator.db', sql_script], capture_output=True, text=True)
print("STDOUT:", result.stdout)
print("STDERR:", result.stderr)
print("Return code:", result.returncode)

os.unlink(sql_file)

# Verify
conn = sqlite3.connect('E:/expertia-data/incubator.db')
cur = conn.execute("SELECT name FROM sqlite_master WHERE name LIKE '%fts%'")
print("Remaining FTS:", cur.fetchall())
conn.close()