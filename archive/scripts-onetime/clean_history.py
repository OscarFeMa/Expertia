import sqlite3

conn = sqlite3.connect('E:/expertia-data/incubator.db')
cur = conn.cursor()

print("=== ANTES DE LA LIMPIEZA ===")
cur = conn.execute("""
    SELECT s.id, s.domain, s.ema_score, s.tier, s.weighted_fail, s.weighted_success,
           COUNT(ch.id) as total,
           SUM(CASE WHEN ch.success=0 AND ch.failure_type='system' THEN 1 ELSE 0 END) as sys_fails,
           SUM(CASE WHEN ch.success=0 AND ch.failure_type='knowledge' THEN 1 ELSE 0 END) as know_fails
    FROM specialist_registry s
    LEFT JOIN cycle_history ch ON s.id = ch.specialist_id
    GROUP BY s.id, s.domain, s.ema_score, s.tier
    ORDER BY s.ema_score DESC
""")
for r in cur.fetchall():
    print(f"{r[1]:20s} EMA={r[2]:.4f} tier={r[2]} sys_fails={r[5]} know_fails={r[6]} total={r[4]}")

print("\n=== ELIMINANDO FALLOS DE SISTEMA DEL HISTORIAL ===")
cur.execute('DELETE FROM cycle_history WHERE success = 0 AND failure_type = "system"')
deleted = cur.rowcount
print(f"Eliminados {cur.rowcount} fallos de sistema del historial")

print("\n=== RECALCULANDO EMA Y TIERS ===")
specialists = conn.execute("SELECT id, domain, ema_score FROM specialist_registry").fetchall()

for sid, domain, current_ema in specialists:
    # Obtener historial LIMPIO (solo fallos de conocimiento)
    ch = conn.execute('''
        SELECT success, quality, failure_type 
        FROM cycle_history 
        WHERE specialist_id = ? 
        ORDER BY id
    ''', (sid,)).fetchall()
    
    if not ch:
        continue
        
    # Recalcular EMA desde 0.1 (valor inicial)
    ema = 0.1
    weighted_success = 0.0
    weighted_fail = 0.0
    
    for ch_row in ch:
        success, quality, failure_type = ch_row
        if success:
            if quality > 0 and 5000 > 0:  # content_length > 0 and contents_count > 0
                size_factor = 1.0 - pow(2.71828, -quality / 5000)  # approx math.exp
                coverage_factor = min(1.0, 5000 / 10.0)  # simplified
                trust_factor = 50 / 100.0
                efficiency = min(1.0, 1.0 / max(1, 1))
                quality_score = 0.25 * size_factor + 0.25 * coverage_factor + 0.25 * 0.5 + 0.25 * efficiency
            else:
                quality_score = 0.1
            weighted_success += quality_score
            alpha = 0.08
            ema = ema + alpha * quality_score * (1.0 - ema)
        else:
            # Solo penalizar fallos de CONOCIMIENTO
            if failure_type == 'knowledge':
                penalty = 0.94  # default para tier 0
                ema = ema * penalty
    
    # Calcular tier basado en EMA limpio
    if ema >= 0.97:
        tier = 4
    elif ema >= 0.95:
        tier = 3
    elif ema >= 0.92:
        tier = 2
    elif ema >= 0.90:
        tier = 1
    else:
        tier = 0
    
    conn.execute("""
        UPDATE specialist_registry 
        SET ema_score = ?, tier = ?, weighted_fail = 0, weighted_success = 0 
        WHERE id = ?
    """, (ema, tier, sid))
    # Get domain for printing
    cur2 = conn.execute("SELECT domain FROM specialist_registry WHERE id = ?", (sid,))
    domain = cur2.fetchone()[0]
    print(f"  {domain}: EMA={ema:.4f} -> Tier {tier}")

# Commit cambios
conn.commit()

print("\n=== DESPUÉS DE LA LIMPIEZA ===")
cur = conn.execute("SELECT domain, ema_score, tier FROM specialist_registry ORDER BY ema_score DESC")
for r in cur.fetchall():
    print(f"{r[0]:20s} EMA={r[1]:.4f} tier={r[1]}")

conn.close()