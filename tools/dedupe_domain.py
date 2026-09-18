"""Deduplicado por lotes de knowledge_packages (exactos por contenido).
Seguro para produccion: ventanas por id, borra conservando min(id),
pausa entre ventanas, aborta si WAL>20GB o disco<50GB, reanudable.
Uso: python tools/dedupe_domain.py --domain Linguistics [--batch 100000]
Requiere pipeline parado para maxima velocidad (tolera convivencia).
"""
import argparse
import hashlib
import json
import logging
import shutil
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import DATABASE_PATH

PROGRESS = Path(__file__).parent.parent / "storage" / "dedupe_progress.json"
logging.basicConfig(filename=str(Path(__file__).parent.parent / "logs" / "dedupe.log"),
                    level=logging.INFO, format="%(asctime)s %(message)s")


def load_progress():
    try:
        return json.loads(PROGRESS.read_text())
    except Exception:
        return {}


def save_progress(state):
    try:
        PROGRESS.parent.mkdir(parents=True, exist_ok=True)
        PROGRESS.write_text(json.dumps(state))
    except Exception as e:
        print(f"WARN progress: {e}", flush=True)


def guards(db_path):
    wal = Path(str(db_path) + "-wal")
    if wal.exists() and wal.stat().st_size > 20 * 1024**3:
        return "WAL>20GB, abortando"
    free = shutil.disk_usage(str(Path(db_path).parent)).free
    if free < 50 * 1024**3:
        return "disco<50GB libres, abortando"
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--domain", required=True)
    p.add_argument("--batch", type=int, default=100000)
    p.add_argument("--sleep", type=float, default=5.0)
    p.add_argument("--max-windows", type=int, default=0)
    p.add_argument("--start-after", type=int, default=0)
    args = p.parse_args()

    db = sqlite3.connect(str(DATABASE_PATH), timeout=300)
    db.execute("PRAGMA busy_timeout=300000")
    mx = db.execute("SELECT MAX(id) FROM knowledge_packages").fetchone()[0] or 0
    st = load_progress().get(args.domain, {})
    lo = max(args.start_after, int(st.get("done_below", 0)))
    print(f"dedupe {args.domain}: ids {lo}..{mx} ventanas {args.batch}", flush=True)
    logging.info(f"dedupe {args.domain}: ids {lo}..{mx}")

    windows = deleted = scanned = 0
    cur = lo
    while cur <= mx:
        hi = cur + args.batch
        rows = db.execute(
            "SELECT id, structured_knowledge FROM knowledge_packages "
            "WHERE domain=? AND id>=? AND id<?", (args.domain, cur, hi)).fetchall()
        scanned += len(rows)
        groups = {}
        for _id, sk in rows:
            if not sk:
                continue
            h = hashlib.sha256(sk.encode("utf-8", "ignore")).hexdigest()
            groups.setdefault(h, []).append(_id)
        dups = []
        for ids in groups.values():
            if len(ids) > 1:
                dups.extend(sorted(ids)[1:])
        for i in range(0, len(dups), 1000):
            chunk = dups[i:i + 1000]
            db.execute(
                f"DELETE FROM knowledge_packages WHERE id IN ({','.join('?'*len(chunk))})",
                chunk)
            db.commit()
        deleted += len(dups)
        cur = hi
        windows += 1
        save_progress({args.domain: {"done_below": cur}})
        print(f"ventana <{hi}: filas={len(rows)} dupes={len(dups)} "
              f"total_del={deleted}", flush=True)
        logging.info(f"ventana <{hi}: filas={len(rows)} dupes={len(dups)} "
                     f"total_del={deleted}")
        g = guards(DATABASE_PATH)
        if g:
            print(f"ABORT {g}", flush=True)
            break
        if args.max_windows and windows >= args.max_windows:
            break
        time.sleep(args.sleep)
    db.close()
    print(f"DONE {args.domain}: scanned={scanned} deleted={deleted}", flush=True)
    logging.info(f"DONE {args.domain}: scanned={scanned} deleted={deleted}")


if __name__ == "__main__":
    main()
