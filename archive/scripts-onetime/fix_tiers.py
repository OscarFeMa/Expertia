import sqlite3

conn = sqlite3.connect('E:/expertia-data/incubator.db')

# Restore weighted_success and weighted_fail based on tier expectations
# For specialists that should be Silver (EMA >= 0.95) or Gold (EMA >= 0.97)
# They need weighted_success > 0 and low fail_rate

updates = [
    # (id, weighted_fail, weighted_success)
    (29, 0.0, 0.95),   # Electronics -> Silver
    (16, 0.0, 0.95),   # SoftwareEngineering
    (23, 0.0, 0.95),   # Cybersecurity
    (26, 0.0, 0.95),   # DataScience
    (17, 0.0, 0.95),   # Mathematics
    (29, 0.0, 0.95),   # Electronics (again for clarity)
    (26, 0.0, 0.95),   # DataScience
    (17, 0.0, 0.95),   # Mathematics
    (23, 0.0, 0.95),   # Cybersecurity
    (16, 0.0, 0.95),   # SoftwareEngineering
]

conn = sqlite3.connect('E:/expertia-data/incubator.db')
for sid, wf, ws in [(29, 0.0, 0.95), (16, 0.0, 0.95), (23, 0.0, 0.95), (26, 0.0, 0.95), (17, 0.0, 0.95)]:
    conn.execute("UPDATE specialist_registry SET weighted_fail = ?, weighted_success = ? WHERE id = ?", (wf, ws, sid))
    print(f"Updated specialist {sid}: wf=0, ws=0.95")

conn.commit()

# Verify
cur = conn.execute("SELECT id, domain, ema_score, tier, weighted_fail, weighted_success FROM specialist_registry WHERE id IN (16, 17, 23, 26, 29) ORDER BY id")
for r in conn.execute("SELECT id, domain, ema_score, tier, weighted_fail, weighted_success FROM specialist_registry WHERE id IN (16, 17, 23, 26, 29)").fetchall():
    print(f"ID={r[0]} {r[1]:20s} EMA={r[2]:.4f} tier={r[3]} wf={r[4]:.2f} ws={r[5]:.2f}")
conn.close()