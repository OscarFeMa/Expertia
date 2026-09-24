import logging
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import DATABASE_PATH

logger = logging.getLogger(__name__)

_LOG = Path(__file__).parent.parent / "logs" / "translate_precache.log"
logging.basicConfig(filename=str(_LOG), level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

try:
    from tools.translate import translate
except Exception as e:
    logging.error(f"import translate failed: {e}")
    translate = None

TARGETS = ["es", "hi", "fr", "zh", "ar", "ru"]
ROTATE = {"es": 0, "hi": 1, "fr": 2, "zh": 3, "ar": 4, "ru": 5}
# es-first estricto: el primer idioma con trabajo pendiente consume la noche;
# solo se avanza al siguiente cuando un idioma sale saturado (0 nuevos).
BUDGET = {"es": 800, "hi": 400, "fr": 400, "zh": 400, "ar": 400, "ru": 400}

def precache(limit=2000, tgt="es"):
    if translate is None:
        return 0
    import gc
    try:
        import torch
        has_torch = True
    except Exception:
        has_torch = False
    db = sqlite3.connect(str(DATABASE_PATH), timeout=120)
    try:
        db.execute("PRAGMA busy_timeout=120000")
    except Exception as e:
        logger.debug("PRAGMA busy_timeout failed: %s", e)
    # hot-set: high trust + recent, ventana de ids recientes (la tabla tiene
    # 900M+ filas sin indice en language: el ORDER BY global tardaba 10+ min)
    rows = db.execute(
        "SELECT kp.id, kp.topic, kp.structured_knowledge FROM knowledge_packages kp "
        "LEFT JOIN source_reputation sr ON sr.netloc = substr(kp.source_url, instr(kp.source_url, '://')+3, instr(substr(kp.source_url, instr(kp.source_url, '://')+3), '/')-1) "
        "WHERE kp.id > (SELECT COALESCE(MAX(id),0)-200000 FROM knowledge_packages) "
        "AND kp.language='en' ORDER BY COALESCE(sr.trust_score,40) DESC, kp.id DESC LIMIT ?", (limit,)
    ).fetchall()
    done = 0
    for r in rows:
        txt = (r[2] or "")[:800]
        if not txt:
            continue
        h = __import__('hashlib').sha256(f"en->{tgt}:{txt}".encode()).hexdigest()[:16]
        exists = db.execute("SELECT 1 FROM translations_cache WHERE hash=?", (h,)).fetchone()
        if exists:
            continue
        try:
            out = translate(txt, "en", tgt)
        except Exception as e:
            if "bad allocation" in str(e).lower():
                gc.collect()
                if has_torch:
                    try:
                        torch.cuda.empty_cache()
                    except Exception as e:
                        logger.debug("torch.cuda.empty_cache failed (oom path): %s", e)
                time.sleep(0.5)
                continue
            raise
        done += 1
        if done % 50 == 0:
            msg = f"precache {tgt} {done}/{limit}"
            print(msg, flush=True)
            logging.info(msg)
            gc.collect()
            if has_torch:
                try:
                    torch.cuda.empty_cache()
                except Exception as e:
                    logger.debug("torch.cuda.empty_cache failed (periodic): %s", e)
        if not (22 <= datetime.now().hour or datetime.now().hour < 8):
            break
    db.close()
    gc.collect()
    return done

if __name__ == "__main__":
    import argparse as _ap
    _pp = _ap.ArgumentParser()
    _pp.add_argument("--once", action="store_true")
    _pp.add_argument("--ignore-window", action="store_true",
                     help="maraton 24h: ignora la ventana 22-08")
    _pp.add_argument("--budget-es", type=int, default=2400)
    _pp.add_argument("--budget-other", type=int, default=400)
    _aa, _ = _pp.parse_known_args()
    once = _aa.once or ("--once" in sys.argv)
    ignore_window = _aa.ignore_window
    budgets = {"es": _aa.budget_es}
    for _t in TARGETS:
        budgets.setdefault(_t, _aa.budget_other)
    _tgt_stats = {}

    def _write_status(tgt, done, budget):
        try:
            st = _tgt_stats.setdefault(tgt, {"start": time.time(), "done": 0})
            st["done"] = done
            el_h = max((time.time() - st["start"]) / 3600, 1 / 3600)
            rate = done / el_h
            rem = max(budget - done, 0)
            out = {"tgt": tgt, "done": done, "budget": budget,
                   "rate_per_h": round(rate, 1),
                   "eta_min": round(rem / rate * 60, 1) if rate > 0 else None,
                   "updated": datetime.now().isoformat(timespec="seconds")}
            _stf = Path(__file__).parent.parent / "logs" / "translate_status.json"
            _stf.parent.mkdir(parents=True, exist_ok=True)
            _stf.write_text(json.dumps(out), encoding="utf-8")
        except Exception as e:
            logger.debug("translate status fallo: %s", e)

    # Kill-switch sin admin: si existe tools/PAUSE_TRANSLATE, salir sin traducir.
    # (Las tareas programadas son de Administradores; esto permite pausar sin UAC.)
    pause_file = Path(__file__).parent / "PAUSE_TRANSLATE"
    if pause_file.exists():
        logging.info("pausa activa (%s), sin traducir", pause_file.name)
        print("translate pausado por PAUSE_TRANSLATE", flush=True)
        sys.exit(0)
    logging.info("daemon start once=%s ignore_window=%s budgets=%s", once, ignore_window, budgets)
    print("daemon 22:00-08:00 es-first NLLB start", flush=True)
    while True:
        h = datetime.now().hour
        if ignore_window or h >= 22 or h < 8:
            for tgt in TARGETS:
                if not ignore_window and not (22 <= datetime.now().hour or datetime.now().hour < 8):
                    break
                budget = budgets.get(tgt, 400)
                try:
                    n = precache(budget, tgt)
                except Exception as e:
                    logging.error(f"precache {tgt} failed: {e}")
                    n = -1
                msg = f"precached {tgt} {n}"
                print(msg, flush=True)
                logging.info(msg)
                if n >= 0:
                    _write_status(tgt, n, budget)
                # Rotacion real: solo se para si el idioma se agoto (n < budget);
                # si llego al tope, hay mas trabajo -> sigue al siguiente idioma.
                if n > 0 and n < budget * 0.9:
                    logging.info(f"es-first: {tgt} aun con trabajo ({n} nuevos), resto manana")
                    break
                time.sleep(10)
            if once:
                logging.info("once done, exit 0")
                break
            time.sleep(60)
        else:
            msg = "outside window 22-08, exit 0" if once else "outside window, sleep"
            logging.info(msg)
            if once:
                break
            time.sleep(300)
