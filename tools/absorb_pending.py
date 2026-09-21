"""Absorcion pendiente por bandas: marca absorbed_at en knowledge_packages
con qid, commit por banda (WAL pequeno, reanudable, con guardas).
Replica la contabilidad del pipeline (_run_wikidata_feed) al final.
Recrea el trigger kp_au SIEMPRE (finally).
Uso: python tools/absorb_pending.py [--band 5000000]
"""
import argparse
import json
import logging
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import DATABASE_PATH
from database.db_manager import KP_AU_DDL as KP_AU

PROGRESS = Path(__file__).parent.parent / "storage" / "absorb_progress.json"
logging.basicConfig(filename=str(Path(__file__).parent.parent / "logs" / "absorb.log"),
                    level=logging.INFO, format="%(asctime)s %(message)s")


def guards(db_path, wal_start):
    wal = Path(str(db_path) + "-wal")
    cur = wal.stat().st_size if wal.exists() else 0
    if cur - wal_start > 30 * 1024**3:
        return f"WAL crecido >30GB en esta sesion ({cur/1e9:.1f}GB), abortando"
    free = shutil.disk_usage(str(Path(db_path).parent)).free
    if free < 50 * 1024**3:
        return "disco<50GB libres, abortando"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--band", type=int, default=5000000)
    ap.add_argument("--sleep", type=float, default=2.0)
    args = ap.parse_args()
    run_start = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    db = sqlite3.connect(str(DATABASE_PATH), timeout=300)
    db.execute("PRAGMA busy_timeout=300000")
    try:
        db.execute("DROP TRIGGER IF EXISTS kp_au")
        wal0 = Path(str(DATABASE_PATH) + "-wal")
        wal_start = wal0.stat().st_size if wal0.exists() else 0
        mx = db.execute("SELECT MAX(id) FROM knowledge_packages").fetchone()[0] or 0
        try:
            cur = int(json.loads(PROGRESS.read_text()).get("done_below", 0))
        except Exception:
            cur = 0
        total = 0
        print(f"absorb: ids {cur}..{mx} bandas {args.band}", flush=True)
        logging.info(f"absorb start {cur}..{mx}")
        while cur <= mx:
            hi = cur + args.band
            for attempt in range(4):
                try:
                    cur_db = db.execute(
                        "UPDATE knowledge_packages SET absorbed_at=CURRENT_TIMESTAMP "
                        "WHERE id>=? AND id<? AND absorbed_at IS NULL AND qid IS NOT NULL",
                        (cur, hi))
                    n = cur_db.rowcount
                    db.commit()
                    break
                except sqlite3.OperationalError as e:
                    logging.warning(f"banda <{hi} bloqueada (try {attempt}): {e}")
                    time.sleep(60)
            else:
                logging.error(f"banda <{hi} imposible, abortando")
                break
            total += n
            cur = hi
            PROGRESS.parent.mkdir(parents=True, exist_ok=True)
            PROGRESS.write_text(json.dumps({"done_below": cur}))
            msg = f"banda <{hi}: +{n} total={total}"
            print(msg, flush=True)
            logging.info(msg)
            g = guards(DATABASE_PATH, wal_start)
            if g:
                print(f"ABORT {g}", flush=True)
                logging.info(f"ABORT {g}")
                break
            time.sleep(args.sleep)

        # Contabilidad por dominio (como el pipeline)
        dom_rows = db.execute(
            "SELECT domain, COUNT(*) FROM knowledge_packages "
            "WHERE absorbed_at >= ? GROUP BY domain", (run_start,)).fetchall()
        id_map = {r[0]: r[1] for r in db.execute(
            "SELECT domain, id FROM specialist_registry").fetchall()}
        for dom, cnt in dom_rows:
            sid = id_map.get(dom)
            if sid is None:
                continue
            db.execute("UPDATE specialist_registry SET feed_packages = "
                       "COALESCE(feed_packages,0)+?, packages_absorbed = "
                       "COALESCE(packages_absorbed,0)+?, "
                       "last_wikidata_feed=CURRENT_TIMESTAMP WHERE id=?",
                       (cnt, cnt, sid))
        db.commit()
        print(f"CONTADORES: {len(dom_rows)} dominios actualizados", flush=True)
        logging.info(f"CONTADORES: {len(dom_rows)} dominios")
    finally:
        try:
            db.execute(KP_AU)
            db.commit()
            print("kp_au recreado", flush=True)
            logging.info("kp_au recreado")
        except Exception as e:
            print(f"ERROR recreando kp_au: {e}", flush=True)
            logging.error(f"ERROR recreando kp_au: {e}")
        db.close()
    print("ABSORB DONE", flush=True)
    logging.info("ABSORB DONE")


if __name__ == "__main__":
    main()
