import logging
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
    once = "--once" in sys.argv
    # Kill-switch sin admin: si existe tools/PAUSE_TRANSLATE, salir sin traducir.
    # (Las tareas programadas son de Administradores; esto permite pausar sin UAC.)
    pause_file = Path(__file__).parent / "PAUSE_TRANSLATE"
    if pause_file.exists():
        logging.info("pausa activa (%s), sin traducir", pause_file.name)
        print("translate pausado por PAUSE_TRANSLATE", flush=True)
        sys.exit(0)
    logging.info("daemon start once=%s", once)
    print("daemon 22:00-08:00 es-first NLLB start", flush=True)
    while True:
        h = datetime.now().hour
        if h >= 22 or h < 8:
            for tgt in TARGETS:
                if not (22 <= datetime.now().hour or datetime.now().hour < 8):
                    break
                try:
                    n = precache(BUDGET.get(tgt, 400), tgt)
                except Exception as e:
                    logging.error(f"precache {tgt} failed: {e}")
                    n = -1
                msg = f"precached {tgt} {n}"
                print(msg, flush=True)
                logging.info(msg)
                if n > 0:
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
