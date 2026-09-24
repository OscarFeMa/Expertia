import hashlib
import logging
import re
import sqlite3
import time
from pathlib import Path

from config.settings import DATABASE_PATH

logger = logging.getLogger(__name__)

_LOG = Path(__file__).parent.parent / "logs" / "translate.log"
try:
    logging.basicConfig(filename=str(_LOG), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
except Exception as e:
    logger.debug("logging.basicConfig failed: %s", e)

# Motor unico: NLLB-200-distilled-600M (acordado). Sin Helsinki.
_NLLB = (None, None)
_NLLB_FAILS = 0

def _get_db():
    db = sqlite3.connect(str(DATABASE_PATH), timeout=120, check_same_thread=False)
    try:
        db.execute("PRAGMA busy_timeout=120000")
        db.execute("PRAGMA journal_mode=WAL")
    except Exception as e:
        logger.debug("PRAGMA setup failed: %s", e)
    return db

def _hash(text, src, tgt):
    return hashlib.sha256(f"{src}->{tgt}:{text}".encode()).hexdigest()[:16]

def _cache_get(h):
    try:
        db = _get_db()
        row = db.execute("SELECT translated_text FROM translations_cache WHERE hash=?", (h,)).fetchone()
        if row:
            db.execute("UPDATE translations_cache SET hits=hits+1, last_hit=CURRENT_TIMESTAMP WHERE hash=?", (h,))
            db.commit()
            db.close()
            return row[0]
        db.close()
    except Exception as e:
        logger.debug("translations_cache get failed: %s", e)
    return None

def _cache_put(h, src, tgt, src_text, trans_text):
    try:
        size = len(trans_text.encode())
        db = _get_db()
        total = db.execute("SELECT COALESCE(SUM(size_bytes),0) FROM translations_cache").fetchone()[0] or 0
        if total + size > 50 * 1024**3:
            for _ in range(100):
                row = db.execute("SELECT hash FROM translations_cache ORDER BY hits ASC, last_hit ASC LIMIT 1").fetchone()
                if not row:
                    break
                sz = db.execute("SELECT size_bytes FROM translations_cache WHERE hash=?", (row[0],)).fetchone()
                sz = sz[0] if sz else 0
                db.execute("DELETE FROM translations_cache WHERE hash=?", (row[0],))
                total -= sz
                if total + size <= 50 * 1024**3:
                    break
        db.execute("INSERT OR REPLACE INTO translations_cache (hash, source_lang, target_lang, source_text, translated_text, size_bytes) VALUES (?,?,?,?,?,?)",
                   (h, src, tgt, src_text, trans_text, size))
        db.commit()
        db.close()
    except Exception as e:
        logger.debug("translations_cache put failed: %s", e)

_SUPPORTED = {"es", "zh", "hi", "ar", "fr", "ru"}
_NLLB = (None, None)

def _load_nllb():
    global _NLLB
    if _NLLB[0] is not None:
        return True
    try:
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        tok = AutoTokenizer.from_pretrained("facebook/nllb-200-distilled-600M", local_files_only=False, trust_remote_code=False)
        mod = AutoModelForSeq2SeqLM.from_pretrained("facebook/nllb-200-distilled-600M")
        try:
            mod.eval()
        except Exception as e:
            logger.debug("NLLB eval failed: %s", e)
        _NLLB = (tok, mod)
        logging.info("NLLB loaded")
        return True
    except Exception as e:
        logging.warning(f"NLLB load failed: {e}")
        print(f"NLLB load failed: {e}")
        return False

def translate(text, src="en", tgt="es", strict=False):
    if not text or not text.strip():
        return text
    if tgt not in _SUPPORTED and tgt != "es":
        return text
    h = _hash(text, src, tgt)
    cached = _cache_get(h)
    if cached:
        return cached
    # NLLB puro: unico motor. Sin fallback (si falla, se devuelve el
    # original y el precache lo reintentara la proxima noche).
    ml = 256 if tgt == "zh" else 384 if tgt == "ar" else 512
    if src == "en" and _load_nllb():
        try:
            tok, mod = _NLLB
            tok.src_lang = f"eng_Latn"
            tgt_code = {"es": "spa_Latn", "zh": "zho_Hans", "hi": "hin_Deva", "ar": "arb_Arab", "fr": "fra_Latn", "ru": "rus_Cyrl"}[tgt]
            batch = tok([text], return_tensors="pt", padding=True, truncation=True, max_length=ml)
            gen = mod.generate(**batch, forced_bos_token_id=tok.convert_tokens_to_ids(tgt_code), max_length=ml)
            out = tok.batch_decode(gen, skip_special_tokens=True)[0]
            _cache_put(h, src, tgt, text, out)
            return out
        except Exception as e:
            global _NLLB_FAILS
            _NLLB_FAILS += 1
            logging.warning(f"translate NLLB error en->{tgt} (#{_NLLB_FAILS}): {e}")
            print(f"translate NLLB error en->{tgt}: {e}")
            if strict:
                raise
    return text

def translate_stream(text, src="en", tgt="es"):
    sents = re.split(r'(?<=[.!?])\s+', text)
    for s in sents:
        if not s.strip():
            continue
        yield translate(s, src, tgt)
        time.sleep(0.02)
