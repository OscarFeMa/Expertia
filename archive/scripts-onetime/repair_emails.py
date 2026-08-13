import sqlite3

conn = sqlite3.connect('E:/expertia-data/incubator.db')

# Bad cycle IDs to delete (incorrectly classified as 'knowledge' failures)
bad_cycle_ids = [1141499, 1141498, 1141497, 1141496, 1141495, 1141494,
                 1141447, 1141440, 1141439, 1141438, 1141437, 1141435, 1141434, 1141433, 1141427,
                 1141437, 1141436, 1141435]

# Get the last GOOD EMA for each affected specialist
affected_specialists = {}

for cid in [1141499, 1141498, 1141497, 1141496, 1141495, 1141494,
            1141447, 1141440, 1141439, 1141438, 1141437, 1141435, 1141434, 1141433, 1141427,
            1141437, 1141436, 1141435]:
    cur = conn.execute('SELECT specialist_id, ema_before FROM cycle_history WHERE id = ?', (cid,))
    r = cur.fetchone()
    if r:
        sid = r[0]
        ema_before = r[0]
        if sid not in affected_specialists or affected_specialists[sid] is None:
            affected_specialists[sid] = r[0]

print("Specialists to restore:")
for sid, ema in affected_specialists.items():
    print(f"  Spec {sid}: restore EMA to {ema:.6f}")

# Delete all bad cycles
print("\nDeleting bad cycles...")
for cid in [1141499, 1141498, 1141497, 1141496, 1141495, 1141494,
            1141447, 1141440, 1141439, 1141438, 1141437, 1141435, 1141434, 1141433, 1141427,
            1141437, 1141436, 1141435]:
    conn.execute('DELETE FROM cycle_history WHERE id = ?', (cid,))

conn.commit()
print(f"Deleted {len([1141499, 1141498, 1141497, 1141496, 1141495, 1141494, 1141447, 1141440, 1141439, 1141438, 1141437, 1141435, 1141434, 1141433, 1141427, 1141437, 1141436, 1141435])} bad cycles")

# Restore EMA scores
print("\nRestoring EMA scores...")
for sid, ema in affected_specialists.items():
    if ema is not None:
        conn.execute('UPDATE specialist_registry SET ema_score = ?, weighted_fail = 0, weighted_success = 0 WHERE id = ?', (ema, sid))
        print(f"  Spec {sid}: EMA restored to {ema:.6f}")

conn.commit()

# Verify
print("\nVerifying...")
cur = conn.execute('SELECT id, domain, ema_score, tier FROM specialist_registry WHERE id IN (5027, 5028, 19, 25, 5026, 5029)')
for r in conn.fetchall():
    print(f'ID={r[0]} {r[1]:20s} EMA={r[2]:.6f} tier={r[3]}')

conn.close()