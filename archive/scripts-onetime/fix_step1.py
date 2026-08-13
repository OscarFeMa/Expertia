import sqlite3
conn = sqlite3.connect('E:/expertia-data/incubator.db')
cur = conn.execute('''
    SELECT s.id, s.domain, s.ema_score, s.tier, s.weighted_fail, s.weighted_success, s.packages_absorbed
    FROM specialist_registry s
    WHERE s.id IN (5027, 5028, 19, 25, 5026)
    ORDER BY s.id
''')
for r in cur.fetchall():
    print(f'ID={r[0]} {r[1]:20s} EMA={r[2]:.6f} tier={r[3]} wf={r[3]} ws={r[4]} pkgs={r[5]}')

# Find the last GOOD ema for each affected specialist
bad_cycle_ids = [1141499, 1141498, 1141497, 1141496, 1141495, 1141494,
                 1141447, 1141440, 1141439, 1141438, 1141437, 1141435, 1141434, 1141433, 1141427]

print('\nLast GOOD ema_before for each specialist:')
for cid in [1141499, 1141498, 1141497, 1141496, 1141495, 1141494,
            1141447, 1141440, 1141439, 1141438, 1141437, 1141435, 1141434, 1141433, 1141427]:
    cur = conn.execute('SELECT specialist_id, ema_before, ema_after, failure_type FROM cycle_history WHERE id = ?', (cid,))
    r = cur.fetchone()
    if r:
        print(f'Cycle {cid}: Spec={r[0]} ema_before={r[1]:.6f} ema_after={r[2]:.6f} type={r[3]}')

conn.close()