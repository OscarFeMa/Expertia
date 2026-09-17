import hashlib
import logging
import re
import sqlite3
import time
from pathlib import Path

from config.settings import DATABASE_PATH

_LOG = Path(__file__).parent.parent / "logs" / "translate.log"
try:
    logging.basicConfig(filename=str(_LOG), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
except Exception:
    pass

# Per-target Marian caches (BUGFIX: antes un solo global reutilizaba
# el modelo del primer idioma para todos los demas -> solo 'es' funcionaba)
_MARIAN = {}

def _get_db():
    db = sqlite3.connect(str(DATABASE_PATH), timeout=120, check_same_thread=False)
    try:
        db.execute("PRAGMA busy_timeout=120000")
        db.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass
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
    except Exception:
        pass
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
    except Exception:
        pass

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
        _NLLB = (tok, mod)
        return True
    except Exception as e:
        print(f"NLLB load failed: {e}")
        return False

def _load_helsinki(tgt):
    if tgt in _MARIAN:
        return True
    try:
        from transformers import MarianMTModel, MarianTokenizer
        tok = MarianTokenizer.from_pretrained(f"Helsinki-NLP/opus-mt-en-{tgt}")
        mod = MarianMTModel.from_pretrained(f"Helsinki-NLP/opus-mt-en-{tgt}")
        try:
            mod.eval()
        except Exception:
            pass
        _MARIAN[tgt] = (tok, mod)
        logging.info(f"Helsinki loaded en->{tgt}")
        return True
    except Exception as e:
        logging.warning(f"Helsinki load failed en->{tgt}: {e}")
        print(f"Helsinki load failed en->{tgt}: {e}")
        return False

def translate(text, src="en", tgt="es"):
    if not text or not text.strip():
        return text
    if tgt not in _SUPPORTED and tgt != "es":
        return text
    h = _hash(text, src, tgt)
    cached = _cache_get(h)
    if cached:
        return cached
    # Helsinki primero (rapido en CPU); NLLB solo si hay CUDA (600M en CPU
    # es inviable para precache nocturno de 2400 docs)
    use_nllb = False
    try:
        import torch
        use_nllb = torch.cuda.is_available() and tgt in {"zh", "ar", "ru", "hi"}
    except Exception:
        use_nllb = False
    ml = 256 if tgt == "zh" else 384 if tgt == "ar" else 512
    if src == "en" and use_nllb and _load_nllb():
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
            logging.warning(f"translate NLLB error en->{tgt}: {e}")
            print(f"translate NLLB error en->{tgt}: {e}")
    if src == "en" and _load_helsinki(tgt):
        try:
            _tokenizer, _model = _MARIAN[tgt]
            batch = _tokenizer([text], return_tensors="pt", padding=True, truncation=True, max_length=ml)
            gen = _model.generate(**batch, max_length=ml)
            out = _tokenizer.decode(gen[0], skip_special_tokens=True)
            _cache_put(h, src, tgt, text, out)
            return out
        except Exception as e:
            logging.warning(f"translate Helsinki error en->{tgt}: {e}")
            print(f"translate Helsinki error: {e}")
    return text

def translate_stream(text, src="en", tgt="es"):
    sents = re.split(r'(?<=[.!?])\s+', text)
    for s in sents:
        if not s.strip():
            continue
        yield translate(s, src, tgt)
        time.sleep(0.02)
