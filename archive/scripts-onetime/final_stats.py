import sqlite3

conn = sqlite3.connect('E:/expertia-data/incubator.db')
cur = conn.execute("""
    SELECT s.domain, s.ema_score, s.tier, s.weighted_fail, s.weighted_success, s.packages_absorbed,
           COUNT(ch.id) as cycles,
           SUM(CASE WHEN ch.success=0 AND ch.failure_type='system' THEN 1 ELSE 0 END) as sys_fails,
           SUM(CASE WHEN ch.success=0 AND ch.failure_type='knowledge' THEN 1 ELSE 0 END) as know_fails
    FROM specialist_registry s
    LEFT JOIN cycle_history ch ON s.id = ch.specialist_id
    GROUP BY s.id, s.domain, s.ema_score, s.tier
    ORDER BY s.ema_score DESC
""")

print(f"{'Domain':20s} | EMA    | Tier | SysF | KnowF | Cycles | Packages")
print("-" * 75)
for r in cur.fetchall():
    print(f"{r[0]:20s} | {r[1]:.4f} | {int(r[2]):4d} | {int(r[6]):4d} | {int(r[7]):4d} | {int(r[8]):5d} | {int(r[5]):6d}")

conn.close()