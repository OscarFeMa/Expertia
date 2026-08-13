"""
Crea índices faltantes en knowledge_packages para acelerar las consultas de
absorción de paquetes (feed/cascade). Seguro de re-ejecutar (IF NOT EXISTS).

Uso:
    python create_index.py [--dry-run]
"""
import sqlite3
import sys
import time

DB_PATH = r"E:\expertia-data\incubator.db"

INDEXES = [
    # Índice parcial: cubre exactamente el UPDATE del feed
    # (WHERE absorbed_at IS NULL AND qid IS NOT NULL). Mucho más rápido de
    # construir que un índice completo sobre una tabla de cientos de GB.
    ("idx_knowledge_packages_absorbed", "knowledge_packages", "absorbed_at", "absorbed_at IS NULL"),
    ("idx_knowledge_packages_qid_absorbed", "knowledge_packages", "qid, absorbed_at", None),
    ("idx_knowledge_packages_batch", "knowledge_packages", "batch_run_id", None),
]


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    conn = sqlite3.connect(DB_PATH, timeout=600)
    conn.execute("PRAGMA busy_timeout = 600000")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        existing = {r[1] for r in conn.execute("PRAGMA index_list('knowledge_packages')")}
        for name, table, cols, where in INDEXES:
            if name in existing:
                print(f"[SKIP] {name} ya existe")
                continue
            suffix = f" WHERE {where}" if where else ""
            ddl = f"CREATE INDEX IF NOT EXISTS {name} ON {table}({cols}){suffix}"
            print(f"[{'DRY-RUN ' if dry_run else ''}CREATE] {name} ON {table}({cols}){suffix}")
            if not dry_run:
                start = time.time()
                conn.execute(ddl)
                conn.commit()
                print(f"  -> OK en {time.time() - start:.1f}s")
    finally:
        conn.close()
    if dry_run:
        print("(dry-run: no se modificó nada)")


if __name__ == "__main__":
    main()
