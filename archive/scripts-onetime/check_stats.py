import sqlite3

conn = sqlite3.connect('E:/expertia-data/incubator.db')
cur = conn.execute("""
    SELECT s.id, s.domain, s.ema_score, s.tier,
           COUNT(ch.id) as total,
           SUM(CASE WHEN ch.success=0 AND ch.failure_type='system' THEN 1 ELSE 0 END) as sys_fails,
           SUM(CASE WHEN ch.success=0 AND ch.failure_type='knowledge' THEN 1 ELSE 0 END) as know_fails
    FROM specialist_registry s
    LEFT JOIN cycle_history ch ON s.id = ch.specialist_id
    GROUP BY s.id, s.domain, s.ema_score, s.tier
    ORDER BY s.ema_score
""")

print("Domain               | EMA    | Tier | SysFails | KnowFails | Total")
print("-" * 75)
for r in cur.fetchall():
    print(f"{r[1]:20s} | {r[2]:.4f} | {r[3]:4d} | {r[4]:8d} | {r[5]:9d} | {r[6]:5d}")

conn.close()