import hashlib
import re
import sqlite3
import time
from pathlib import Path

from config.settings import DATABASE_PATH

_model = None
_tokenizer = None

def _get_db():
    return sqlite3.connect(str(DATABASE_PATH), timeout=30)

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

def _load_helsinki():
    global _model, _tokenizer
    if _model is not None:
        return True
    try:
        from transformers import MarianMTModel, MarianTokenizer
        _tokenizer = MarianTokenizer.from_pretrained("Helsinki-NLP/opus-mt-en-es")
        _model = MarianMTModel.from_pretrained("Helsinki-NLP/opus-mt-en-es")
        return True
    except Exception as e:
        print(f"Helsinki load failed: {e}")
        return False

def translate(text, src="en", tgt="es"):
    if not text or not text.strip():
        return text
    h = _hash(text, src, tgt)
    cached = _cache_get(h)
    if cached:
        return cached
    if src == "en" and tgt == "es":
        if _load_helsinki():
            try:
                batch = _tokenizer([text], return_tensors="pt", padding=True, truncation=True, max_length=512)
                gen = _model.generate(**batch, max_length=512)
                out = _tokenizer.decode(gen[0], skip_special_tokens=True)
                _cache_put(h, src, tgt, text, out)
                return out
            except Exception as e:
                print(f"translate error: {e}")
    return text

def translate_stream(text, src="en", tgt="es"):
    sents = re.split(r'(?<=[.!?])\s+', text)
    for s in sents:
        if not s.strip():
            continue
        yield translate(s, src, tgt)
        time.sleep(0.02)
