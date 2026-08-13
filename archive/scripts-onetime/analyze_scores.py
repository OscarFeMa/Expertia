import sqlite3

conn = sqlite3.connect('E:/expertia-data/incubator.db')

cur = conn.execute("""
    SELECT s.id, s.domain, s.ema_score, s.tier, s.weighted_fail, s.weighted_success,
           COUNT(ch.id) as total_cycles,
           SUM(CASE WHEN ch.success=0 AND ch.failure_type="system" THEN 1 ELSE 0 END) as sys_fails,
           SUM(CASE WHEN ch.success=0 AND ch.failure_type="knowledge" THEN 1 ELSE 0 END) as know_fails
    FROM specialist_registry s
    LEFT JOIN cycle_history ch ON s.id = ch.specialist_id
    GROUP BY s.id, s.domain, s.ema_score, s.tier
    ORDER BY s.ema_score
""")

print("Domain               | EMA | Tier | SysFails | KnowFails | TotalCycles")
print("-" * 75)
for r in cur.fetchall():
    print(f"{r[1]:20s} | {r[2]:.4f} | {r[3]} | {r[4]:.1f} | {r[5]:.1f} | {r[6]}")

# Check recent cycles for problematic specialists
print()
for sid in [16, 17, 23, 26, 29]:  # SE, Math, Cybersec, DataScience, Electronics
    cur = conn.execute("""
        SELECT ch.id, ch.success, ch.failure_type, ch.quality, ch.ema_before, ch.ema_after, ch.timestamp
        FROM cycle_history ch
        WHERE ch.specialist_id = ?
        ORDER BY ch.id DESC LIMIT 10
    """, (sid,))
    rows = cur.fetchall()
    if rows:
        domain = conn.execute("SELECT domain FROM specialist_registry WHERE id = ?", (sid,)).fetchone()[0]
        print(f"\n=== {cur.fetchone()[0]} (ID={sid}) ===")
        for r in conn.execute("""
            SELECT id, success, failure_type, quality, ema_before, ema_after, timestamp
            FROM cycle_history
            WHERE specialist_id = ?
            ORDER BY id DESC LIMIT 10
        """, (sid,)).fetchall():
            print(f"  Cycle {r[0]}: success={r[1]} type={r[2]} qual={r[2]:.4f} ema={r[3]:.4f}->{r[4]:.4f} @ {r[5]}")

conn.close()