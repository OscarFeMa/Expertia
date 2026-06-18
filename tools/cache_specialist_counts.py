"""
Standalone script to cache per-specialist matched_qid counts.
Runs the slow GROUP BY query with a generous timeout and writes
results to specialist_match_cache. Designed to be called periodically
(e.g. every 5 min) while the cascade is running, without blocking it.
"""
import sqlite3
import time
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "storage" / "incubator.db"
QUERY_TIMEOUT_SEC = 600  # 10 min max for the full scan


def refresh_cache():
    conn = sqlite3.connect(str(DB_PATH), timeout=QUERY_TIMEOUT_SEC)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        start = time.time()
        rows = conn.execute("""
            SELECT m.specialist_id, s.domain, COUNT(*) as match_count
            FROM matched_qids m
            JOIN specialist_registry s ON s.id = m.specialist_id
            GROUP BY m.specialist_id
            ORDER BY match_count DESC
        """).fetchall()
        scan_time = time.time() - start
        print(f"Scan complete: {len(rows)} specialists in {scan_time:.0f}s", flush=True)

        conn.execute("DELETE FROM specialist_match_cache")
        conn.executemany(
            "INSERT INTO specialist_match_cache (specialist_id, domain, match_count) VALUES (?, ?, ?)",
            rows
        )
        conn.commit()
        total = sum(r[2] for r in rows)
        print(f"Cached {len(rows)} specialists, {total:,} total matches", flush=True)
    except Exception as e:
        print(f"Cache refresh failed: {e}", flush=True)
    finally:
        conn.close()


if __name__ == "__main__":
    refresh_cache()
