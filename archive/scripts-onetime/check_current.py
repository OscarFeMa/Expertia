import sqlite3

conn = sqlite3.connect('E:/expertia-data/incubator.db')
cur = conn.execute('SELECT id, domain, ema_score, tier, weighted_fail, weighted_success FROM specialist_registry ORDER BY ema_score DESC')
for r in cur.fetchall():
    print(f'ID={r[0]} {r[1]:20s} EMA={r[2]:.6f} tier={r[3]} wf={r[4]} ws={r[5]}')

# Check what the EMA scores should be based on their tier
# Gold >= 0.97, Silver >= 0.95, Bronze >= 0.92
print("\nExpected EMA based on tier:")
tiers = {4: 0.98, 3: 0.96, 2: 0.93, 1: 0.90, 0: 0.10}
cur = conn.execute('SELECT id, domain, tier FROM specialist_registry ORDER BY tier DESC')
for r in cur.fetchall():
    expected = tiers.get(r[2], 0.10)
    print(f'ID={r[0]} {r[1]:20s} tier={r[2]} expected_ema={expected:.2f}')

conn.close()