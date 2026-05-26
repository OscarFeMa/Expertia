"""
Report scheduler: generates performance reports every 30 min.
Follows watchdog.py pattern.
"""
import sqlite3, time, os
from pathlib import Path
from datetime import datetime, timezone, timedelta

BASE = Path(__file__).parent
LOG = BASE / 'logs' / 'report_scheduler.log'
REPORTS_DIR = BASE / 'storage' / 'reports'
DB_PATH = BASE / 'storage' / 'incubator.db'
TZ_OFFSET = timedelta(hours=2)
LOOKBACK_HOURS = 2
INTERVAL = 1800  # 30 min

LOG.parent.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

def log(msg):
    line = f"[{datetime.now().strftime('%Y%m%d_%H%M%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')

def generate():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    lookback = (datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)).strftime('%Y-%m-%d %H:%M:%S')

    cur.execute("SELECT id, domain, model, ema_score, packages_absorbed, status, updated_at, parent_id FROM specialist_registry ORDER BY parent_id IS NOT NULL, parent_id, domain")
    specialists = {r[0]: {'id': r[0], 'domain': r[1], 'model': r[2], 'ema': r[3], 'packages': r[4], 'status': r[5], 'updated_at': r[6], 'parent_id': r[7]} for r in cur.fetchall()}

    varied = []
    for sid, spec in sorted(specialists.items(), key=lambda x: x[1]['domain']):
        cur.execute("SELECT ema_score, timestamp FROM ema_history WHERE specialist_id = ? AND timestamp > ? ORDER BY timestamp ASC", (sid, lookback))
        recent_rows = cur.fetchall()
        cur.execute("SELECT COUNT(*) FROM activity_log WHERE timestamp > ? AND message LIKE ?", (lookback, f'%{spec["domain"]}%'))
        recent_activity = cur.fetchone()[0]
        is_active = spec['status'] == 'ACTIVE'
        if len(recent_rows) >= 2 or recent_activity > 0 or is_active:
            first_ema = recent_rows[0][0] if recent_rows else spec['ema']
            last_ema = recent_rows[-1][0] if recent_rows else spec['ema']
            delta = last_ema - first_ema
            varied.append({**spec, 'first_ema': first_ema, 'last_ema': last_ema, 'delta': delta, 'recent_ema_count': len(recent_rows), 'recent_activity_count': recent_activity, 'is_active': is_active})

    total_pkg = sum(s['packages'] for s in specialists.values())
    avg_ema = sum(s['ema'] for s in specialists.values()) / len(specialists)
    now = datetime.now(timezone.utc) + TZ_OFFSET
    ts = now.strftime('%Y%m%d_%H%M%S')
    fname = f'Rendimiento_{ts}.txt'
    fpath = str(REPORTS_DIR / fname)

    lines = []
    lines.append('=' * 68)
    lines.append(f'{"REPORTE DE RENDIMIENTO \u2014 SYNAPTIC ARCHIVE":^68}')
    lines.append(f'{"Generado: " + now.strftime("%Y-%m-%d %H:%M:%S"):^68}')
    lines.append('=' * 68)
    lines.append('')
    n_parents = sum(1 for s in specialists.values() if s.get('parent_id') is None)
    n_children = sum(1 for s in specialists.values() if s.get('parent_id') is not None)
    lines.append(f'Especialistas raiz:    {n_parents}')
    lines.append(f'Sub-especialistas:     {n_children}')
    lines.append(f'Total:                 {len(specialists)}')
    lines.append(f'Activos:               {sum(1 for s in specialists.values() if s["status"] == "ACTIVE")}')
    lines.append(f'Paquetes absorbidos:   {total_pkg}')
    lines.append(f'EMA promedio general:  {avg_ema:.4f}')
    lines.append('')
    if not varied:
        lines.append('  (No se detecto variacion en ningun especialista)')
    else:
        lines.append('-' * 68)
        lines.append(f'{"ESPECIALISTAS CON VARIACION":^68}')
        lines.append('-' * 68)
        lines.append(f'{"Dominio":<25} {"Modelo":<18} {"EMA":>7} {"D EMA":>8} {"Paq.":>5} {"Eventos":>7} {"Estado":<8}')
        lines.append('-' * 68)
        for v in sorted(varied, key=lambda x: (x.get('parent_id') is not None, -abs(x['delta']))):
            prefix = '  \\_ ' if v.get('parent_id') else ''
            ema_s = f"{v['last_ema']:.4f}"
            delta_s = f"{v['delta']:+.4f}" if abs(v['delta']) > 0.0001 else '  --'
            lines.append(f"{prefix}{v['domain']:<{23 if prefix else 25}} {v['model']:<18} {ema_s:>7} {delta_s:>8} {v['packages']:>5} {v['recent_activity_count']:>7} {v['status']:<8}")
        lines.append('')
        lines.append('-' * 68)
        lines.append('DETALLE POR ESPECIALISTA')
        lines.append('-' * 68)
        for v in sorted(varied, key=lambda x: (x.get('parent_id') is not None, -abs(x['delta']))):
            prefix = '  \\_ ' if v.get('parent_id') else ''
            lines.append('')
            lines.append(f"  {prefix}{v['domain']} ({'ACTIVO' if v['is_active'] else v['status']})")
            lines.append(f"    Modelo:          {v['model']}")
            if v['recent_ema_count'] >= 2:
                ema_dir = '\u2191' if v['delta'] > 0 else '\u2193'
                lines.append(f"    EMA (inicio):    {v['first_ema']:.4f}")
                lines.append(f"    EMA (final):     {v['last_ema']:.4f} {ema_dir}")
                lines.append(f"    D EMA:           {v['delta']:+.4f}" if abs(v['delta']) > 0.0001 else '    D EMA:           --')
                lines.append(f"    Registros EMA:   {v['recent_ema_count']}")
            else:
                lines.append(f"    EMA:             {v['last_ema']:.4f}")
            lines.append(f"    Paquetes:        {v['packages']}")
            if v['recent_activity_count'] > 0:
                lines.append(f"    Eventos (act.):  {v['recent_activity_count']}")
            lines.append(f"    Ultima act.:     {v['updated_at']}")

    # ── Super-Experts Section ────────────────────────────────────────────
    try:
        cur.execute("""
            SELECT se.domain, se.description,
                   COUNT(sem.id) AS member_count,
                   AVG(s.ema_score) AS avg_ema,
                   SUM(s.packages_absorbed * sem.weight) / SUM(sem.weight) AS weighted_ema,
                   SUM(s.packages_absorbed) AS total_packages
            FROM super_experts se
            LEFT JOIN super_expert_members sem ON sem.super_expert_id = se.id
            LEFT JOIN specialist_registry s ON s.id = sem.specialist_id
            GROUP BY se.id
            ORDER BY weighted_ema DESC
        """)
        se_rows = cur.fetchall()
        if se_rows:
            lines.append('')
            lines.append('=' * 68)
            lines.append(f'{"SUPER-EXPERT COUNCILS":^68}')
            lines.append('=' * 68)
            lines.append(f'{"Council":<28} {"Members":>7} {"Weighted EMA":>12} {"Total Pkgs":>10}')
            lines.append('-' * 68)
            for r in se_rows:
                lines.append(f'{r[0]:<28} {r[2]:>7} {r[4]:>12.4f} {r[5]:>10}')
            # Per-council member detail
            for r in se_rows:
                se_name = r[0]
                cur.execute("""
                    SELECT s.domain, s.ema_score, sem.weight
                    FROM super_expert_members sem
                    JOIN specialist_registry s ON s.id = sem.specialist_id
                    JOIN super_experts se ON se.id = sem.super_expert_id
                    WHERE se.domain = ?
                    ORDER BY sem.weight DESC
                """, (se_name,))
                members = cur.fetchall()
                if members:
                    lines.append('')
                    lines.append(f'  {se_name}:')
                    for m in members:
                        lines.append(f'    \\_ {m[0]:<30} weight={m[2]:.0%}  EMA={m[1]:.4f}')
    except Exception as e:
        log(f"Super-expert section error: {e}")

    lines.append('')
    lines.append('=' * 68)
    lines.append(f'{"FIN DEL REPORTE \u2014 SYNAPTIC ARCHIVE":^68}')
    lines.append('=' * 68)

    with open(fpath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    conn.close()
    return fname, len(varied)

log("Report scheduler started (30 min interval)")
while True:
    try:
        fname, count = generate()
        log(f"Reporte generado: {fname} ({count} especialistas con variacion)")
    except Exception as e:
        log(f"ERROR generating report: {e}")
    time.sleep(INTERVAL)
