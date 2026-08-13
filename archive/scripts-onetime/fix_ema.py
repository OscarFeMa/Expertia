import sqlite3

conn = sqlite3.connect('E:/expertia-data/incubator.db')

# Expected EMA based on tier
tier_ema = {4: 0.98, 3: 0.96, 2: 0.93, 1: 0.10, 0: 0.10}

cur = conn.execute('SELECT id, tier FROM specialist_registry')
for r in cur.fetchall():
    sid = r[0]
    tier = r[1]
    expected = tier_ema.get(r[1], 0.10)
    conn.execute("UPDATE specialist_registry SET ema_score = ?, weighted_fail = 0, weighted_success = 0 WHERE id = ?", (expected, r[0]))
    print(f"ID={r[0]} updated to EMA={expected:.4f}")

conn.commit()
conn.close()
print("Done!")