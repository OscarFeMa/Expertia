import json
import os
import sqlite3
import sys
import time

CRASH_DIR = "E:/aria2-1.37.0-win-64bit-build1/crash_dumps"
MAIN_DB = "E:/expertia-data/incubator.db"
PROGRESS_FILE = "C:/Users/usuario/AppData/Local/Temp/opencode/recover_progress.txt"

BATCH_SIZE = 50000
if os.environ.get("RECOVER_BATCH"):
    BATCH_SIZE = int(os.environ["RECOVER_BATCH"])


def load_done():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return {ln.strip() for ln in f if ln.strip()}
    return set()


def save_done(done):
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(done)))


def main():
    done = load_done()
    files = sorted(f for f in os.listdir(CRASH_DIR) if f.endswith("_kps.json"))
    if os.environ.get("RECOVER_LIMIT"):
        files = files[: int(os.environ["RECOVER_LIMIT"])]
    todo = [f for f in files if f not in done]
    print(f"[init] total={len(files)} completados={len(done)} pendientes={len(todo)}", flush=True)

    conn = sqlite3.connect(MAIN_DB, timeout=600)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA cache_size = -4000000")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA wal_autocheckpoint = 0")

    try:
        conn.execute("DROP TRIGGER IF EXISTS kp_ai")
        print("[triggers] kp_ai caido (re-recreado al final)", flush=True)
    except Exception as e:
        print(f"[triggers] WARN no puedo soltar kp_ai: {e}", flush=True)

    t0 = time.time()
    total_inserted = 0
    for idx, name in enumerate(todo):
        path = os.path.join(CRASH_DIR, name)
        f_t0 = time.time()
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[error] {name}: parse {e} (omitido, re-procesar en siguiente pasada)", flush=True)
            continue

        valid = []
        for row in data:
            if len(row) >= 5 and row[3] and row[2]:
                valid.append((row[0], row[1], row[2], row[4], row[3]))
        if not valid:
            done.add(name)
            save_done(done)
            continue

        before = conn.total_changes
        for i in range(0, len(valid), BATCH_SIZE):
            chunk = valid[i:i + BATCH_SIZE]
            conn.executemany(
                "INSERT OR IGNORE INTO knowledge_packages "
                "(topic, source_url, domain, structured_knowledge, qid, created_at) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                chunk,
            )
        after = conn.total_changes
        inserted = after - before
        total_inserted += inserted
        conn.commit()

        done.add(name)
        save_done(done)
        if (idx + 1) % 25 == 0 or idx == len(todo) - 1:
            print(
                f"[{idx+1}/{len(todo)}] {name} rows={len(valid)} inserted={inserted} "
                f"acum={total_inserted} file_t={time.time()-f_t0:.1f}s t={int(time.time()-t0)}s",
                flush=True,
            )

    print(f"[insert] TOTAL inserted={total_inserted} t={int(time.time()-t0)}s", flush=True)
    conn.commit()
    _restore_trigger(conn)
    conn.close()
    print("[done]", flush=True)


def _restore_trigger(conn):
    print("[fts] recreando trigger kp_ai (rebuild FTS se ejecuta aparte)...", flush=True)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS kp_ai AFTER INSERT ON knowledge_packages BEGIN
            INSERT INTO knowledge_packages_fts(rowid, topic, structured_knowledge, domain)
            VALUES (new.id, new.topic, new.structured_knowledge, new.domain);
        END
    """)
    conn.commit()
    print("[fts] trigger kp_ai recreado. (rebuild FTS por script separado)", flush=True)


if __name__ == "__main__":
    main()