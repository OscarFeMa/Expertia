"""Limpieza quirurgica del scaffolding Wikidata en paquetes destilados.
Reescribe structured_knowledge sin cabeceras Entity/Properties ni P-codigos,
conservando definiciones y valores legibles. Por lotes, con progreso,
guardas WAL/disco y pausa. Requiere pipeline parado para maxima velocidad
(tolera convivencia).
Uso: python tools/clean_archive.py [--domains Math,Physics] [--batch 1000]
"""
import argparse
import json
import logging
import re
import shutil
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import DATABASE_PATH

logger = logging.getLogger(__name__)

PROGRESS = Path(__file__).parent.parent / "storage" / "clean_progress.json"
logging.basicConfig(filename=str(Path(__file__).parent.parent / "logs" / "clean_archive.log"),
                    level=logging.INFO, format="%(asctime)s %(message)s")

MARKERS = ("Entity:", "Properties: P", "Properties:\n")


def needs_clean(sk):
    return ("Entity:" in sk) or ("Properties: P" in sk)


def clean_sk(text):
    lines = []
    for ln in (text or "").splitlines():
        s = ln.strip()
        low = s.lower()
        if low.startswith("description:"):
            s = s[len("description:"):].strip()
        elif any(low.startswith(p) for p in ("entity:", "aliases:",
                                             "properties:", "source:")):
            continue
        elif re.match(r"^P\d+\s*:", s):
            continue
        if s:
            lines.append(s)
    return "\n".join(lines)


def load_progress():
    try:
        return json.loads(PROGRESS.read_text())
    except Exception as e:
        logger.debug("load_progress failed: %s", e)
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--domains", default="Mathematics,Physics,Chemistry,Electronics")
    ap.add_argument("--batch", type=int, default=1000)
    ap.add_argument("--sleep", type=float, default=2.0)
    args = ap.parse_args()
    domains = [d.strip() for d in args.domains.split(",") if d.strip()]

    db = sqlite3.connect(str(DATABASE_PATH), timeout=300)
    db.execute("PRAGMA busy_timeout=300000")
    st = load_progress()
    total_fixed = 0
    for dom in domains:
        start_after = int(st.get(dom, {}).get("done_below", 0))
        while True:
            rows = db.execute(
                "SELECT id, structured_knowledge FROM knowledge_packages "
                "WHERE domain=? AND id>? AND (structured_knowledge LIKE '%Entity: %' "
                "OR structured_knowledge LIKE '%Properties: P%') "
                "ORDER BY id ASC LIMIT ?", (dom, start_after, args.batch)).fetchall()
            if not rows:
                break
            fixed = 0
            for _id, sk in rows:
                new = clean_sk(sk)
                if new and new != sk and len(new) >= 50:
                    db.execute("UPDATE knowledge_packages SET structured_knowledge=? "
                               "WHERE id=?", (new, _id))
                    fixed += 1
                start_after = _id
            db.commit()
            total_fixed += fixed
            st[dom] = {"done_below": start_after}
            save_progress(st)
            msg = f"{dom}: lote hasta id={start_after} fixed={fixed} total={total_fixed}"
            print(msg, flush=True)
            logging.info(msg)
            g = guards(DATABASE_PATH)
            if g:
                print(f"ABORT {g}", flush=True)
                logging.info(f"ABORT {g}")
                return
            time.sleep(args.sleep)
    db.close()
    print(f"DONE fixed={total_fixed}", flush=True)
    logging.info(f"DONE fixed={total_fixed}")


if __name__ == "__main__":
    main()
