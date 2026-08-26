import json
import os
import sqlite3
import sys
import time

CRASH_DIR = "E:/aria2-1.37.0-win-64bit-build1/crash_dumps"
MAIN_DB = "E:/expertia-data/incubator.db"
TEMP_DB = "C:/Users/usuario/AppData/Local/Temp/opencode/dryrun_analysis.db"

args = [a for a in sys.argv[1:] if not a.startswith("--")]
LIMIT = int(args[0]) if args else None
KPS_ONLY = "--kps-only" in sys.argv


def walk_files():
    files = []
    for name in sorted(os.listdir(CRASH_DIR)):
        if name.endswith("_kps.json"):
            files.append(("kps", os.path.join(CRASH_DIR, name)))
        elif not KPS_ONLY and name.endswith("_qids.json"):
            files.append(("qids", os.path.join(CRASH_DIR, name)))
    if LIMIT:
        files = files[:LIMIT]
    return files


def main():
    if os.path.exists(TEMP_DB):
        os.remove(TEMP_DB)
    files = walk_files()
    n_kps = sum(1 for kind, _ in files if kind == "kps")
    n_qids = sum(1 for kind, _ in files if kind == "qids")
    print(f"[init] archivos: {n_kps} kps + {n_qids} qids", flush=True)

    conn = sqlite3.connect(MAIN_DB, timeout=300)
    conn.execute("ATTACH DATABASE ? AS ana", (TEMP_DB,))
    conn.execute("CREATE TABLE ana.eids(eid TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE ana.pairs(eid TEXT, domain TEXT, PRIMARY KEY(eid, domain))")

    t0 = time.time()
    for i, (kind, path) in enumerate(files):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
        if kind == "kps":
            eids = [(row[3],) for row in data if len(row) >= 4 and row[3]]
            pairs = [(row[3], row[2]) for row in data if len(row) >= 4 and row[3] and row[2]]
        else:
            eids = [(row[2],) for row in data if len(row) >= 3 and row[2]]
            pairs = []
        if eids:
            conn.executemany("INSERT OR IGNORE INTO ana.eids(eid) VALUES(?)", eids)
        if pairs:
            conn.executemany("INSERT OR IGNORE INTO ana.pairs(eid, domain) VALUES(?,?)", pairs)
        if (i + 1) % 250 == 0:
            print(f"[scan] {i+1}/{len(files)} ({kind}) "
                  f"eids={conn.execute('SELECT count(*) FROM ana.eids').fetchone()[0]} "
                  f"pairs={conn.execute('SELECT count(*) FROM ana.pairs').fetchone()[0]} "
                  f"t={int(time.time()-t0)}s", flush=True)
    conn.commit()
    print(f"[scan] done t={int(time.time()-t0)}s", flush=True)

    total_eids = conn.execute("SELECT count(*) FROM ana.eids").fetchone()[0]
    total_pairs = conn.execute("SELECT count(*) FROM ana.pairs").fetchone()[0]
    print(f"[unique] eids={total_eids} pairs={total_pairs}", flush=True)

    print("[check] falta_x_qid (idx_knowledge_qid)...", flush=True)
    t1 = time.time()
    row = conn.execute("""
        SELECT count(*) FROM ana.eids e
        WHERE NOT EXISTS (SELECT 1 FROM knowledge_packages k WHERE k.qid = e.eid)
    """).fetchone()
    missing_eids = row[0]
    print(f"[check] eids sin qid en knowledge_packages: {missing_eids} t={int(time.time()-t1)}s", flush=True)

    if total_pairs:
        print("[check] pares faltantes (idx_kp_qid_domain)...", flush=True)
        t2 = time.time()
        row = conn.execute("""
            SELECT count(*) FROM ana.pairs p
            WHERE NOT EXISTS (SELECT 1 FROM knowledge_packages k
                              WHERE k.qid = p.eid AND k.domain = p.domain)
        """).fetchone()
        missing_pairs = row[0]
        print(f"[check] pares (eid,domain) sin fila: {missing_pairs} t={int(time.time()-t2)}s", flush=True)
        print("GRAN TOTAL kps a re-insertar (pares), FACTOR vs eids únicos:", flush=True)
        print(f"  missing_pairs={missing_pairs}  (ratio={missing_pairs/missing_eids:.2f})", flush=True)

    print(f"RESULTADO eids_unicos={total_eids} missing_eids={missing_eids} t_total={int(time.time()-t0)}s", flush=True)
    conn.close()


if __name__ == "__main__":
    main()