import sqlite3
conn = sqlite3.connect('E:/expertia-data/incubator.db')
cur = conn.execute('''
    SELECT ch.id, ch.specialist_id, s.domain, ch.success, ch.failure_type, ch.quality, ch.ema_before, ch.ema_after, ch.timestamp
    FROM cycle_history ch
    JOIN specialist_registry s ON ch.specialist_id = s.id
    WHERE ch.success = 0
    ORDER BY ch.id DESC LIMIT 20
''')
for r in cur.fetchall():
    print(f'ID={r[0]} Spec={r[1]} {r[2]:20s} success={r[3]} type={r[4]} quality={r[5]} ema={r[6]:.6f}->{r[7]:.6f} @ {r[8]}')
conn.close()