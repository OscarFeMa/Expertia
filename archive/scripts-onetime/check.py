import sqlite3
conn = sqlite3.connect("E:/expertia-data/incubator.db")
cur = conn.execute("SELECT s.domain, s.ema_score, s.tier, COUNT(ch.id) as cyc, SUM(CASE WHEN ch.success=0 AND ch.failure_type=
system THEN 1 ELSE 0 END) as sys_f, SUM(CASE WHEN ch.success=0 AND ch.failure_type=\"knowledge\" THEN 1 ELSE 0 END) as kf FROM specialist_registry s LEFT JOIN cycle_history ch ON s.id = ch.specialist_id GROUP BY s.id ORDER BY s.ema_score DESC")
for r in cur.fetchall():
    print(f"{r[0]:20s} EMA={r[1]:.4f} tier={r[2]} cyc={r[3]} sys_f={r[4]} know_f={r[5]}")
conn.close()
