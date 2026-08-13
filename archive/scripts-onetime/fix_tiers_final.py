import sqlite3

conn = sqlite3.connect('E:/expertia-data/incubator.db')

# Fix tiers based on EMA scores
# Tier logic:
# EMA >= 0.97 -> Tier 4 (Gold)
# EMA >= 0.95 -> Tier 3 (Silver)
# EMA >= 0.92 -> Tier 2 (Bronze)
# EMA >= 0.90 -> Tier 1 (Copper)
# else -> Tier 0

cur = conn.execute("SELECT id, domain, ema_score FROM specialist_registry")
for r in cur.fetchall():
    sid, domain, ema = r
    if ema >= 0.97:
        tier = 4  # Gold
    elif ema >= 0.95:
        tier = 3  # Silver
    elif ema >= 0.92:
        tier = 2  # Bronze
    elif ema >= 0.90:
        tier = 1  # Copper
    else:
        tier = 0
    
    conn.execute("UPDATE specialist_registry SET tier = ? WHERE id = ?", (tier, r[0]))
    print(f"ID={r[0]} {r[1]:20s} EMA={r[2]:.4f} -> Tier {tier}")

conn.commit()
conn.close()
print("Done!")