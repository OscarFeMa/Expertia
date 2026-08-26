"""
Read-only DB helper for API endpoints.
Uses a small connection pool (mode=ro URI) to avoid per-query open/close overhead.
Avoids the single-connection bottleneck from the shared singleton.
"""
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Optional

from config.settings import DATABASE_PATH as _DEFAULT_DB_PATH

logger = logging.getLogger(__name__)

_ro_path: Optional[Path] = None
_pool: list[sqlite3.Connection] = []
_pool_lock = threading.Lock()
_MAX_POOL = 4


def init(db_path: Optional[Path] = None):
    global _ro_path
    _ro_path = db_path or _DEFAULT_DB_PATH


def _open_conn() -> sqlite3.Connection:
    if _ro_path is None:
        raise RuntimeError("readonly_db not initialized: call init(db_path) first")
    uri = f"file:{_ro_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10.0, check_same_thread=False)
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA cache_size=-256000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def _is_alive(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("SELECT 1")
        return True
    except sqlite3.Error:
        return False


def _acquire() -> sqlite3.Connection:
    with _pool_lock:
        while _pool:
            conn = _pool.pop()
            if _is_alive(conn):
                return conn
            try:
                conn.close()
            except Exception:
                pass
    return _open_conn()


def _release(conn: sqlite3.Connection):
    if conn is None or not _is_alive(conn):
        try:
            conn.close()
        except Exception:
            pass
        return
    with _pool_lock:
        if len(_pool) < _MAX_POOL:
            _pool.append(conn)
        else:
            try:
                conn.close()
            except Exception:
                pass


def select(query: str, params: tuple = ()) -> list[dict]:
    conn = _acquire()
    try:
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        logger.warning(f"RO select failed: {e}")
        return []
    finally:
        _release(conn)


def select_one(query: str, params: tuple = ()) -> Optional[dict]:
    rows = select(query, params)
    return rows[0] if rows else None
