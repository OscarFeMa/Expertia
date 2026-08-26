import sqlite3, time

log = open(r"C:\Users\usuario\AppData\Local\Temp\opencode\fase2c_integrity.log", "a", encoding="utf-8")
def out(m):
    print(m, flush=True)
    log.write(m + "\n")
    log.flush()

out(f"[{time.strftime('%H:%M:%S')}] abriendo conexion...")
c = sqlite3.connect("E:/expertia-data/incubator.db", timeout=86400, isolation_level=None)
out(f"[{time.strftime('%H:%M:%S')}] inicio integrity_check...")
t0 = time.time()
try:
    cur = c.execute("PRAGMA integrity_check")
    n = 0
    for row in cur:
        n += 1
        out(f"row{n}: {row[0]}")
        if n > 20:
            break
    out(f"[{time.strftime('%H:%M:%S')}] integrity_check terminado en {time.time()-t0:.0f}s, errores={n-1 if n>0 else 0}")
except Exception as e:
    out(f"error: {e}")
# quick_check tambien para validacion final
t0 = time.time()
qc = c.execute("PRAGMA quick_check").fetchone()[0]
out(f"quick_check: {qc} (t={time.time()-t0:.0f}s)")
c.close()
out("[FIN fase2c_integrity]")
log.close()