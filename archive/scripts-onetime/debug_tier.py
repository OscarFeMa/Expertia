import sqlite3

conn = sqlite3.connect('E:/expertia-data/incubator.db')

# Check tier criteria for each specialist
cur = conn.execute("""
    SELECT s.id, s.domain, s.ema_score, s.tier, s.weighted_fail, s.weighted_success, s.packages_absorbed,
           COUNT(ch.id) as total_cycles,
           SUM(CASE WHEN ch.success=0 AND ch.failure_type='knowledge' THEN 1 ELSE 0 END) as fails,
           AVG(CASE WHEN ch.success=1 THEN ch.quality ELSE NULL END) as avg_quality
    FROM specialist_registry s
    LEFT JOIN cycle_history ch ON s.id = ch.specialist_id
    GROUP BY s.id, s.domain, s.ema_score, s.tier, s.weighted_fail, s.weighted_success, s.packages_absorbed
    ORDER BY s.ema_score DESC
""")

print("ID | Domain              | EMA   | Tier | pkgs  | cycles | fails | fail_rate | avg_q | Should be")
print("-" * 100)

for r in cur.fetchall():
    sid = r[0]
    domain = r[1]
    ema = r[2]
    tier = r[3]
    pkgs = r[6]
    total_cycles = r[7]
    fails = r[8] or 0
    avg_q = r[9] or 0
    
    fail_rate = fails / max(1, total_cycles) if total_cycles > 0 else 0
    avg_q = avg_q if avg_q else 0
    
    should_be = 0
    if ema >= 0.97 and r[5] >= 1500 and fail_rate < 0.03 and r[8] >= 0.78:
        should_be = 4
    elif ema >= 0.95 and r[5] >= 500 and r[4] < 0.08 and r[8] >= 0.70:
        should_be = 3
    elif ema >= 0.92 and r[5] >= 200 and fails / max(1, total_cycles) < 0.15 and r[8] >= 0.60:
        should_be = 2
    elif ema >= 0.90 and r[5] >= 50 and r[8] >= 0.50:
        should_be = 1
    else:
        should_be = 0
    
    tier_names = {0: "None", 1: "Bronze", 2: "Silver", 3: "Gold", 4: "Legend"}
    print(f"{r[0]:4d} | {r[1]:20s} | {r[2]:.4f} | {tier_names.get(tier, '?')} | {r[4]:2d} | {total_cycles:6d} | {fails:5d} | {fail_rate:.4f} | {avg_q:.4f} | {tier_names.get(should_be, '?')}")

conn.close()