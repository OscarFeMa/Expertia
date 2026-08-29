import sqlite3
import time
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import DATABASE_PATH

try:
    from tools.translate import translate
except Exception:
    translate = None

def precache(limit=2000):
    if translate is None:
        return 0
    db = sqlite3.connect(str(DATABASE_PATH), timeout=30)
    rows = db.execute("SELECT id, topic, structured_knowledge FROM knowledge_packages WHERE language='en' ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    done = 0
    for r in rows:
        txt = (r[2] or "")[:800]
        if not txt:
            continue
        h = __import__('hashlib').sha256(f"en->es:{txt}".encode()).hexdigest()[:16]
        exists = db.execute("SELECT 1 FROM translations_cache WHERE hash=?", (h,)).fetchone()
        if exists:
            continue
        out = translate(txt, "en", "es")
        time.sleep(0.02)
        done += 1
        if done % 100 == 0:
            print(f"precache {done}/{limit}")
        if datetime.now().hour >= 6:
            break
    db.close()
    return done

if __name__ == "__main__":
    print("daemon 00:00-06:00 start")
    while True:
        h = datetime.now().hour
        if 0 <= h < 6:
            n = precache(500)
            print(f"precached {n}")
            time.sleep(60)
        else:
            time.sleep(300)
