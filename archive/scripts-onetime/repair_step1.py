import sqlite3
conn = sqlite3.connect('E:/expertia-data/incubator.db')

# Bad cycle IDs that were incorrectly recorded as 'knowledge' failures (they were system failures)
bad_cycle_ids = [1141499, 1141498, 1141497, 1141496, 1141495, 1141494,
                 1141447, 1141440, 1141439, 1141438, 1141437, 1141435, 1141434, 1141433, 1141427,
                 1141437, 1141436, 1141435]  # adding the older ones too

print("Bad cycle IDs to process:")
for cid in bad_cycle_ids:
    cur = conn.execute('SELECT specialist_id, ema_before, ema_after, failure_type FROM cycle_history WHERE id = ?', (cid,))
    r = cur.fetchone()
    if r:
        print(f'Cycle {cid}: Spec={r[0]} ema_before={r[1]:.6f} ema_after={r[2]:.6f} type={r[3]}')

conn.close()