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

# Exclusion mutua entre instancias (maraton vs tarea 22:00): lock de fichero
# no bloqueante; si otra instancia lo tiene, salir sin traducir.
_LOCK_FH = None


def _take_singleton_lock():
    global _LOCK_FH
    try:
        lock_path = Path(__file__).parent / ".translate_daemon.lock"
        _LOCK_FH = open(lock_path, "a+b")
        try:
            import msvcrt
            msvcrt.locking(_LOCK_FH.fileno(), msvcrt.LK_NBLCK, 1)
        except ImportError:
            import fcntl
            fcntl.flock(_LOCK_FH.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except Exception:
        return False

# Estado vivo para el panel (/api/translate/status): ventana deslizante de
# marcas de tiempo (ritmo real, no media desde el arranque) + acumulados
# persistentes por idioma (el done por pasada engañaba).
_MTOTALS = Path(__file__).parent.parent / "logs" / "translate_totals.json"


def _load_totals():
    try:
        if _MTOTALS.exists():
            return json.loads(_MTOTALS.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}
_MSTATE = {"tgt": None, "budget": 0, "done": 0, "times": []}


def _mstatus_touch(final=False):
    try:
        now = time.time()
        ts = _MSTATE["times"]
        if not final:
            ts.append(now)
            del ts[:-100]
        n = len(ts)
        rate = 0.0
        if n >= 5 and ts[-1] > ts[0]:
            rate = (n - 1) / ((ts[-1] - ts[0]) / 3600)
        rem = max(_MSTATE["budget"] - _MSTATE["done"], 0)
        out = {"tgt": _MSTATE["tgt"], "done": _MSTATE["done"],
               "total_lang": _MSTATE.get("total_lang", 0),
               "budget": _MSTATE["budget"], "rate_per_h": round(rate, 1),
               "eta_min": round(rem / rate * 60, 1) if rate > 0 else None,
               "updated": datetime.now().isoformat(timespec="seconds")}
        _stf = Path(__file__).parent.parent / "logs" / "translate_status.json"
        _stf.parent.mkdir(parents=True, exist_ok=True)
        _stf.write_text(json.dumps(out), encoding="utf-8")
    except Exception as e:
        logger.debug("translate status fallo: %s", e)
ROTATE = {"es": 0, "hi": 1, "fr": 2, "zh": 3, "ar": 4, "ru": 5}
# es-first estricto: el primer idioma con trabajo pendiente consume la noche;
# solo se avanza al siguiente cuando un idioma sale saturado (0 nuevos).
BUDGET = {"es": 800, "hi": 400, "fr": 400, "zh": 400, "ar": 400, "ru": 400}
# True en modo maraton 24h: ignora tambien el control horario POR FILA de precache().
_IGNORE_WINDOW = False

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
            out = translate(txt, "en", tgt, strict=True)
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
        _MSTATE["done"] = _MSTATE.get("done", 0) + 1
        if done % 50 == 0:
            msg = f"precache {tgt} {done}/{limit}"
            print(msg, flush=True)
            logging.info(msg)
            _mstatus_touch()
            gc.collect()
            if has_torch:
                try:
                    torch.cuda.empty_cache()
                except Exception as e:
                    logger.debug("torch.cuda.empty_cache failed (periodic): %s", e)
        if not _IGNORE_WINDOW and not (22 <= datetime.now().hour or datetime.now().hour < 8):
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
    _IGNORE_WINDOW = ignore_window
    budgets = {"es": _aa.budget_es}
    for _t in TARGETS:
        budgets.setdefault(_t, _aa.budget_other)

    # Kill-switch sin admin: si existe tools/PAUSE_TRANSLATE, salir sin traducir.
    # (Las tareas programadas son de Administradores; esto permite pausar sin UAC.)
    pause_file = Path(__file__).parent / "PAUSE_TRANSLATE"
    if pause_file.exists():
        logging.info("pausa activa (%s), sin traducir", pause_file.name)
        print("translate pausado por PAUSE_TRANSLATE", flush=True)
        sys.exit(0)
    logging.info("daemon start once=%s ignore_window=%s budgets=%s", once, ignore_window, budgets)
    if not _take_singleton_lock():
        logging.info("otra instancia activa, exit 0")
        print("translate: otra instancia activa, exit 0", flush=True)
        sys.exit(0)
    print("daemon 22:00-08:00 es-first NLLB start", flush=True)
    while True:
        h = datetime.now().hour
        if ignore_window or h >= 22 or h < 8:
            for tgt in TARGETS:
                if not ignore_window and not (22 <= datetime.now().hour or datetime.now().hour < 8):
                    break
                budget = budgets.get(tgt, 400)
                _MSTATE.update(tgt=tgt, budget=budget, done=0, times=[])
                _mstatus_touch()
                try:
                    n = precache(budget, tgt)
                except Exception as e:
                    logging.error(f"precache {tgt} failed: {e}")
                    n = -1
                msg = f"precached {tgt} {n}"
                print(msg, flush=True)
                logging.info(msg)
                if n >= 0:
                    _MSTATE["done"] = n
                    try:
                        _tots = _load_totals()
                        _tots[tgt] = _tots.get(tgt, 0) + n
                        _MTOTALS.write_text(json.dumps(_tots), encoding="utf-8")
                        _MSTATE["total_lang"] = _tots[tgt]
                    except Exception as e:
                        logger.debug("totals fallo: %s", e)
                    _mstatus_touch(final=True)
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
