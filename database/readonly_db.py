"""
Read-only DB helper for API endpoints.
Opens a fresh read-only SQLite connection per query (mode=ro URI).
Avoids the single-connection bottleneck from the shared singleton.
"""
import logging
import sqlite3
from pathlib import Path
from typing import Optional

from config.settings import DATABASE_PATH as _DEFAULT_DB_PATH

logger = logging.getLogger(__name__)

_ro_path: Optional[Path] = None


def init(db_path: Optional[Path] = None):
    global _ro_path
    _ro_path = db_path or _DEFAULT_DB_PATH


def _conn():
    if _ro_path is None:
        raise RuntimeError("readonly_db not initialized: call init(db_path) first")
    uri = f"file:{_ro_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=2.0, check_same_thread=False)
    conn.execute("PRAGMA busy_timeout=500")
    conn.execute("PRAGMA cache_size=-64000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def select(query: str, params: tuple = ()) -> list[dict]:
    conn = None
    try:
        conn = _conn()
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        logger.warning(f"RO select failed: {e}")
        return []
    finally:
        if conn:
            try: conn.close()
            except Exception: pass


def select_one(query: str, params: tuple = ()) -> Optional[dict]:
    rows = select(query, params)
    return rows[0] if rows else None
