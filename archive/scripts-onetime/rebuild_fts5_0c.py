import sqlite3
import sys
import time
import os

DB = 'E:/expertia-data/incubator.db'
LOG = r'C:\Users\usuario\AppData\Local\Temp\opencode\fts_rebuild_0c.log'

def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')

TRIGGERS = {
    'kp_ai': """CREATE TRIGGER kp_ai AFTER INSERT ON knowledge_packages BEGIN
            INSERT INTO knowledge_packages_fts(rowid, topic, structured_knowledge, domain)
            VALUES (new.id, new.topic, new.structured_knowledge, new.domain);
        END""",
    'kp_ad': """CREATE TRIGGER kp_ad AFTER DELETE ON knowledge_packages BEGIN
            INSERT INTO knowledge_packages_fts(knowledge_packages_fts, rowid, topic, structured_knowledge, domain)
            VALUES ('delete', old.id, old.topic, old.structured_knowledge, old.domain);
        END""",
    'kp_au': """CREATE TRIGGER kp_au AFTER UPDATE ON knowledge_packages BEGIN
            INSERT INTO knowledge_packages_fts(knowledge_packages_fts, rowid, topic, structured_knowledge, domain)
            VALUES ('delete', old.id, old.topic, old.structured_knowledge, old.domain);
            INSERT INTO knowledge_packages_fts(rowid, topic, structured_knowledge, domain)
            VALUES (new.id, new.topic, new.structured_knowledge, new.domain);
        END""",
}

def fts_shadow_gb():
    total = 0.0
    for sfx in ('_data', '_idx', '_content', '_docsize', '_config'):
        p = DB + '-' + sfx
        if os.path.exists(p):
            total += os.path.getsize(p) / 1e9
    return total

def main():
    log("=== Fase 0c: Rebuild FTS5 ===")
    conn = sqlite3.connect(DB, isolation_level=None, timeout=7200)
    conn.execute("PRAGMA busy_timeout = 7200000")
    conn.execute("PRAGMA wal_autocheckpoint = 0")
    conn.execute("PRAGMA cache_size = -4000000")
    conn.execute("PRAGMA synchronous = NORMAL")

    # 1) Verificar / recrear triggers
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='knowledge_packages'")
    existing = {r[0] for r in cur.fetchall()}
    for name in ('kp_ai', 'kp_ad', 'kp_au'):
        if name in existing:
            log(f"trigger {name}: presente")
        else:
            log(f"trigger {name}: AUSENTE -> recreando")
            conn.execute(TRIGGERS[name])
    conn.commit() if not conn.in_transaction else None

    # 2) Verificar tabla FTS existe
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_packages_fts'")
    if not cur.fetchone():
        log("FTS5 no existe. Creando virtual table + repoblando...")
        conn.execute("""
            CREATE VIRTUAL TABLE knowledge_packages_fts
            USING fts5(topic, structured_knowledge, domain,
                       content='knowledge_packages', content_rowid='id')
        """)
    else:
        log("FTS5 existe. Reconstruyendo indice (rebuild)...")

    # 3) Monitorear shadow tables mientras corre el rebuild
    last_log = time.time()
    last_size = fts_shadow_gb()
    t0 = time.time()
    # El rebuild corre en el hilo principal; compartimos progreso via el archivo
    # de shadow en cada vuelta de check CHEAP no es posible sin interrumpir SQLite.
    # Mejor: medir simplemente al inicio y reportar al final + logs de control.
    log(f"shadow_fts_inicial={last_size:.1f}GB")
    conn.execute("INSERT INTO knowledge_packages_fts(knowledge_packages_fts) VALUES ('rebuild')")
    dt = time.time() - t0
    log(f"rebuild completado en {dt/60:.1f} min")
    conn.commit() if conn.in_transaction else None

    size_final = fts_shadow_gb()
    log(f"shadow_fts_final={size_final:.1f}GB")

    # 4) Checkpoint TRUNCATE (metodo comprobado: una sola conexion)
    tc0 = time.time()
    while True:
        cur = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        row = cur.fetchone()
        logf, chkf = (row[1], row[2]) if len(row) >= 3 else (row[0], None)
        if row == (0, 0, 0) or (chkf == 0 and logf == 0):
            break
        time.sleep(30)
    log(f"checkpoint TRUNCATE en {(time.time()-tc0)/60:.1f} min")

    # 5) Conteos + integrity (no bloqueamos el pipeline de nuevo; se loguea)
    t1 = time.time()
    cur = conn.execute("SELECT count(*) FROM knowledge_packages")
    src = cur.fetchone()[0]
    log(f"knowledge_packages = {src} (count t={(time.time()-t1)/60:.1f}min)")
    cur = conn.execute("SELECT count(*) FROM knowledge_packages_fts")
    fts = cur.fetchone()[0]
    log(f"fts5 = {fts}")
    log("OK: conteos coinciden" if src == fts else f"WARN: diff={src-fts}")

    try:
        conn.execute("INSERT INTO knowledge_packages_fts(knowledge_packages_fts) VALUES ('integrity-check')")
        log("integrity-check FTS: OK")
    except Exception as e:
        log(f"integrity-check error: {e!r}")

    conn.close()
    db = os.path.getsize(DB) / 1e9
    log(f"FIN: db={db:.1f}GB")
    log("=== Fase 0c terminada ===")

if __name__ == '__main__':
    main()