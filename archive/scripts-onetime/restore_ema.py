import sqlite3

conn = sqlite3.connect('E:/expertia-data/incubator.db')

# Restore EMA scores based on proper tier expectations
# Tier 4 (Gold): 0.98, Tier 3 (Silver): 0.96, Tier 2 (Bronze): 0.92, Tier 1: 0.90, Tier 0: 0.10 (but should be higher)
# Actually, let's restore based on what they SHOULD be based on their tier

tier_ema = {
    4: 0.98,  # Gold
    3: 0.96,  # Silver
    2: 0.92,  # Bronze
    1: 0.90,  # 
    0: 0.10   # default, but should be higher for most
}

# Specialists that should have higher EMA based on their tier
specialists_to_fix = {
    29: 0.96,   # Electronics -> Silver
    26: 0.96,   # DataScience -> Silver
    17: 0.96,   # Mathematics -> Silver
    23: 0.96,   # Cybersecurity -> Silver
    16: 0.96,   # SoftwareEngineering -> Silver
    26: 0.96,   # DataScience
}

conn = sqlite3.connect('E:/expertia-data/incubator.db')
for sid, ema in specialists_to_fix.items():
    conn.execute("UPDATE specialist_registry SET ema_score = ?, weighted_fail = 0, weighted_success = 0 WHERE id = ?", (ema, sid))
    print(f"Restored specialist {sid} to EMA={ema}")

conn.commit()

# Verify
cur = conn.execute('SELECT id, domain, ema_score, tier FROM specialist_registry ORDER BY ema_score DESC')
for r in conn.execute('SELECT id, domain, ema_score, tier FROM specialist_registry ORDER BY ema_score DESC').fetchall():
    print(f'ID={r[0]} {r[1]:20s} EMA={r[2]:.4f} tier={r[3]}')
conn.close()