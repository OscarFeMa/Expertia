import sqlite3

conn = sqlite3.connect('E:/expertia-data/incubator.db')

# EnvironmentalScience (id=5028) had legitimate EMA ~0.9856 before bad cycles
# The last good cycle before bad ones was around 1141493 with ema_after=0.9856
# Let's restore it to 0.9856 (Gold tier)

conn.execute("UPDATE specialist_registry SET ema_score = 0.9856, tier = 4, weighted_fail = 0, weighted_success = 0 WHERE id = 5028")
conn.commit()
print("EnvironmentalScience restored to EMA=0.9856, tier=4 (Gold)")

# Also fix Psychology (5027) - was around 0.9645 before bad cycles
# Last good was around 0.9645
conn.execute("UPDATE specialist_registry SET ema_score = 0.9645, tier = 3, weighted_fail = 0, weighted_success = 0 WHERE id = 5027")
conn.commit()
print("Psychology restored to EMA=0.9645, tier=3 (Silver)")

# LegalSystem (19) - was around 0.9777
conn.execute("UPDATE specialist_registry SET ema_score = 0.9777, tier = 3, weighted_fail = 0, weighted_success = 0 WHERE id = 19")
conn.commit()
print("LegalSystem restored to EMA=0.9777, tier=3 (Silver)")

# Geopolitics (25) - was around 0.9814
conn.execute("UPDATE specialist_registry SET ema_score = 0.9814, tier = 3, weighted_fail = 0, weighted_success = 0 WHERE id = 25")
conn.commit()
print("Geopolitics restored to EMA=0.9814, tier=3 (Silver)")

# Linguistics (5026) - was around 0.9714
conn.execute("UPDATE specialist_registry SET ema_score = 0.9714, tier = 3, weighted_fail = 0, weighted_success = 0 WHERE id = 5026")
conn.commit()
print("Linguistics restored to EMA=0.9714, tier=3 (Silver)")

# Sociology (5029) - was around 0.9739
conn.execute("UPDATE specialist_registry SET ema_score = 0.9739, tier = 3, weighted_fail = 0, weighted_success = 0 WHERE id = 5029")
conn.commit()
print("Sociology restored to EMA=0.9739, tier=3 (Silver)")

# Verify
cur = conn.execute('SELECT id, domain, ema_score, tier FROM specialist_registry WHERE id IN (5028, 5027, 19, 25, 5026, 5029)')
for r in conn.fetchall():
    print(f'ID={r[0]} {r[1]:20s} EMA={r[2]:.4f} tier={r[3]}')

conn.close()