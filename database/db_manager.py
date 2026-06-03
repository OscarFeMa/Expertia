"""
Thread-Safe SQLite Connection Manager

Implements a Singleton pattern with connection pooling for SQLite to allow
multiple agents to read/write concurrently without locking the disk or opening
hundreds of connections.

Architecture:
- Singleton pattern ensures single connection instance
- Thread-safe operations using threading.Lock
- check_same_thread=False for cross-thread access
- Automatic connection recovery on failures
- Tables: specialist_registry, cartridge_offsets, knowledge_packages
"""

import sqlite3
import threading
import logging
from pathlib import Path
from typing import Optional, ContextManager
from contextlib import contextmanager

from config.settings import DATABASE_PATH as _DEFAULT_DB_PATH

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Thread-Safe Singleton Database Manager for SQLite.
    
    Provides a single connection instance with thread-safe operations
    to prevent connection overhead and disk locking issues.
    """
    
    _instance: Optional['DatabaseManager'] = None
    _lock: threading.RLock = threading.RLock()  # RLock for reentrancy
    _connection_lock: threading.RLock = threading.RLock()
    
    def __new__(cls, db_path: Optional[Path] = None) -> 'DatabaseManager':
        """Singleton with double-checked locking; uses first path ever provided."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
                    cls._instance._singleton_db_path = db_path or _DEFAULT_DB_PATH
        return cls._instance
    
    def __init__(self, db_path: Optional[Path] = None):
        """Initialize once. Subsequent calls are no-ops."""
        if self._initialized:
            return
        
        self.db_path: Path = self._singleton_db_path
        self._connection: Optional[sqlite3.Connection] = None
        self._initialized = True
        
        logger.info(f"DatabaseManager initialized with path: {self.db_path}")
    
    def _get_connection(self) -> sqlite3.Connection:
        """
        Get or create the SQLite connection.
        
        Uses check_same_thread=False to allow cross-thread access
        with manual locking for thread safety.
        """
        if self._connection is None:
            with self._connection_lock:
                if self._connection is None:
                    self._connection = self._open_connection()
        else:
            try:
                self._connection.execute("SELECT 1")
            except sqlite3.ProgrammingError:
                with self._connection_lock:
                    self._connection = self._open_connection()
        
        return self._connection
    
    def _open_connection(self):
        try:
            conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=30.0
            )
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA cache_size=-64000;")
            conn.execute("PRAGMA temp_store=MEMORY;")
            conn.execute("PRAGMA busy_timeout=5000;")
            conn.execute("PRAGMA mmap_size=268435456;")
            conn.row_factory = sqlite3.Row
            logger.info("SQLite connection established (WAL + perf pragmas)")
            return conn
        except sqlite3.Error as e:
            logger.error(f"Failed to establish SQLite connection: {e}")
            raise
    
    def _close_connection(self) -> None:
        """Close the SQLite connection if it exists."""
        with self._connection_lock:
            if self._connection is not None:
                try:
                    self._connection.close()
                    self._connection = None
                    logger.info("SQLite connection closed successfully")
                except sqlite3.Error as e:
                    logger.error(f"Failed to close SQLite connection: {e}")
    
    @contextmanager
    def get_cursor(self) -> ContextManager[sqlite3.Cursor]:
        """
        Context manager for thread-safe cursor access.
        
        Yields a cursor with automatic connection management.
        Ensures proper cleanup even on exceptions.
        """
        connection = self._get_connection()
        cursor = None
        
        try:
            cursor = connection.cursor()
            yield cursor
        except sqlite3.Error as e:
            logger.error(f"Database operation failed: {e}")
            connection.rollback()
            raise
        finally:
            if cursor is not None:
                cursor.close()
    
    def execute_query(
        self,
        query: str,
        params: tuple = (),
        fetch: bool = False
    ) -> Optional[list]:
        """
        Execute a SQL query with thread-safe access.
        
        Args:
            query: SQL query string
            params: Query parameters
            fetch: Whether to fetch and return results
            
        Returns:
            List of results if fetch=True, None otherwise
        """
        with self.get_cursor() as cursor:
            try:
                cursor.execute(query, params)
                
                if fetch:
                    results = cursor.fetchall()
                    self._get_connection().commit()
                    return [dict(row) for row in results]
                self._get_connection().commit()
                return None
                
            except sqlite3.Error as e:
                logger.error(f"Query execution failed: {e}")
                self._get_connection().rollback()
                raise
    
    def execute_many(
        self,
        query: str,
        params_list: list[tuple]
    ) -> None:
        """
        Execute multiple SQL queries with thread-safe access.
        
        Args:
            query: SQL query string
            params_list: List of parameter tuples
        """
        with self.get_cursor() as cursor:
            try:
                cursor.executemany(query, params_list)
                self._get_connection().commit()
                logger.info(f"Executed {len(params_list)} queries successfully")
            except sqlite3.Error as e:
                logger.error(f"Batch execution failed: {e}")
                self._get_connection().rollback()

    def execute_batch(self, statements: list[tuple]) -> None:
        """Execute multiple different SQL statements in a single transaction.
        
        Args:
            statements: List of (query, params) tuples
        """
        conn = self._get_connection()
        with self.get_cursor() as cursor:
            try:
                for query, params in statements:
                    cursor.execute(query, params)
                conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Batch execution failed: {e}")
                conn.rollback()
                raise
    
    async def execute_query_async(self, query: str, params: tuple = (), fetch: bool = False):
        """Execute a SQL query asynchronously using aiosqlite."""
        import aiosqlite
        async with aiosqlite.connect(str(self.db_path)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            if fetch:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
            await db.commit()
            return None

    async def execute_batch_async(self, statements: list[tuple]) -> None:
        """Execute multiple SQL statements in a single async transaction."""
        import aiosqlite
        async with aiosqlite.connect(str(self.db_path)) as db:
            for query, params in statements:
                await db.execute(query, params)
            await db.commit()
    
    def table_exists(self, table_name: str) -> bool:
        """
        Check if a table exists in the database.
        
        Args:
            table_name: Name of the table to check
            
        Returns:
            True if table exists, False otherwise
        """
        with self.get_cursor() as cursor:
            try:
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name=?
                """, (table_name,))
                return cursor.fetchone() is not None
            except sqlite3.Error as e:
                logger.error(f"Failed to check table existence: {e}")
                return False
    
    def get_table_count(self, table_name: str) -> int:
        """
        Get the row count of a table.
        
        Args:
            table_name: Name of the table
            
        Returns:
            Row count
        """
        VALID_TABLES = {"specialist_registry", "knowledge_packages", "cartridge_offsets",
                        "super_experts", "super_expert_members", "wikidata_sync_log"}
        if table_name not in VALID_TABLES:
            logger.error(f"Invalid table name: {table_name}")
            return 0
        with self.get_cursor() as cursor:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                return cursor.fetchone()[0]
            except sqlite3.Error as e:
                logger.error(f"Failed to get table count: {e}")
                return 0
    
    def health_check(self) -> bool:
        """
        Perform a health check on the database connection.
        
        Returns:
            True if connection is healthy, False otherwise
        """
        try:
            with self.get_cursor() as cursor:
                cursor.execute("SELECT 1")
                return True
        except sqlite3.Error as e:
            logger.error(f"Database health check failed: {e}")
            # Attempt to reconnect
            self._close_connection()
            try:
                self._get_connection()
                return True
            except:
                return False
    
    def initialize_specialist_tables(self) -> bool:
        """
        Initialize specialist-specific tables for Coral Thought architecture.
        
        Creates:
        - specialist_registry: 15 specialists with models and Wikidata filters
        - cartridge_offsets: Tracking for Wikidata extraction progress
        - knowledge_packages: Knowledge storage
        
        Returns:
            True if initialization successful, False otherwise
        """
        try:
            with self.get_cursor() as cursor:
                # Create specialist_registry table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS specialist_registry (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        domain TEXT NOT NULL UNIQUE,
                        model TEXT NOT NULL,
                        root_qid TEXT NOT NULL,
                        properties TEXT NOT NULL,
                        ema_score REAL DEFAULT 0.10,
                        weighted_success REAL DEFAULT 0.0,
                        weighted_fail REAL DEFAULT 0.0,
                        tier INTEGER DEFAULT 3,
                        packages_absorbed INTEGER DEFAULT 0,
                        status TEXT DEFAULT 'IDLE',
                        parent_id INTEGER DEFAULT NULL,
                        qid_path TEXT DEFAULT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (parent_id) REFERENCES specialist_registry(id)
                    )
                """)
                
                # Create cartridge_offsets table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS cartridge_offsets (
                        qid TEXT PRIMARY KEY,
                        cartridge_name TEXT,
                        offset_start INTEGER,
                        offset_end INTEGER,
                        specialist_id INTEGER,
                        status TEXT DEFAULT 'Available',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (specialist_id) REFERENCES specialist_registry(id)
                    )
                """)
                
                # Create knowledge_packages table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS knowledge_packages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        topic TEXT NOT NULL,
                        source_url TEXT NOT NULL,
                        domain TEXT,
                        qid TEXT DEFAULT NULL,
                        subdomain_path TEXT DEFAULT NULL,
                        structured_knowledge TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create FTS5 index for keyword search on knowledge_packages
                cursor.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_packages_fts USING fts5(
                        topic, structured_knowledge, domain,
                        content='knowledge_packages',
                        content_rowid='id'
                    )
                """)
                
                # Triggers to keep FTS5 index in sync
                cursor.execute("""
                    CREATE TRIGGER IF NOT EXISTS kp_ai AFTER INSERT ON knowledge_packages BEGIN
                        INSERT INTO knowledge_packages_fts(rowid, topic, structured_knowledge, domain)
                        VALUES (new.id, new.topic, new.structured_knowledge, new.domain);
                    END
                """)
                cursor.execute("""
                    CREATE TRIGGER IF NOT EXISTS kp_ad AFTER DELETE ON knowledge_packages BEGIN
                        INSERT INTO knowledge_packages_fts(knowledge_packages_fts, rowid, topic, structured_knowledge, domain)
                        VALUES ('delete', old.id, old.topic, old.structured_knowledge, old.domain);
                    END
                """)
                cursor.execute("""
                    CREATE TRIGGER IF NOT EXISTS kp_au AFTER UPDATE ON knowledge_packages BEGIN
                        INSERT INTO knowledge_packages_fts(knowledge_packages_fts, rowid, topic, structured_knowledge, domain)
                        VALUES ('delete', old.id, old.topic, old.structured_knowledge, old.domain);
                        INSERT INTO knowledge_packages_fts(rowid, topic, structured_knowledge, domain)
                        VALUES (new.id, new.topic, new.structured_knowledge, new.domain);
                    END
                """)
                
                # Create ema_history table for scoring
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ema_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        specialist_id INTEGER NOT NULL,
                        ema_score REAL NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (specialist_id) REFERENCES specialist_registry(id)
                    )
                """)
                
                # Create cycle_history table for per-cycle tracking (success/fail, quality, racha_25)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS cycle_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        specialist_id INTEGER NOT NULL,
                        success INTEGER NOT NULL,
                        quality REAL DEFAULT 0.0,
                        ema_before REAL,
                        ema_after REAL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (specialist_id) REFERENCES specialist_registry(id)
                    )
                """)
                
                # Create indexes
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_specialist_domain
                    ON specialist_registry(domain)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_cartridge_specialist
                    ON cartridge_offsets(specialist_id)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_knowledge_domain
                    ON knowledge_packages(domain)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_knowledge_qid
                    ON knowledge_packages(qid)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_specialist_parent
                    ON specialist_registry(parent_id)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ema_specialist
                    ON ema_history(specialist_id, timestamp)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_cycle_specialist
                    ON cycle_history(specialist_id, id)
                """)
                
                # Migration: add columns if upgrading from old schema
                for col_sql in [
                    "ALTER TABLE specialist_registry ADD COLUMN parent_id INTEGER DEFAULT NULL REFERENCES specialist_registry(id)",
                    "ALTER TABLE specialist_registry ADD COLUMN qid_path TEXT DEFAULT NULL",
                    "ALTER TABLE specialist_registry ADD COLUMN weighted_success REAL DEFAULT 0.0",
                    "ALTER TABLE specialist_registry ADD COLUMN weighted_fail REAL DEFAULT 0.0",
                    "ALTER TABLE specialist_registry ADD COLUMN last_wikidata_download TIMESTAMP DEFAULT NULL",
                    "ALTER TABLE specialist_registry ADD COLUMN last_wikidata_feed TIMESTAMP DEFAULT NULL",
                    "ALTER TABLE knowledge_packages ADD COLUMN qid TEXT DEFAULT NULL",
                    "ALTER TABLE knowledge_packages ADD COLUMN subdomain_path TEXT DEFAULT NULL",
                    "ALTER TABLE knowledge_packages ADD COLUMN absorbed_at TIMESTAMP DEFAULT NULL",
                ]:
                    try:
                        cursor.execute(col_sql)
                    except sqlite3.OperationalError:
                        pass

                # Create wikidata_sync_log table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS wikidata_sync_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        specialist_id INTEGER NOT NULL,
                        domain TEXT NOT NULL,
                        qids_added INTEGER DEFAULT 0,
                        sync_type TEXT DEFAULT 'incremental',
                        status TEXT DEFAULT 'SUCCESS',
                        error_message TEXT,
                        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP,
                        FOREIGN KEY (specialist_id) REFERENCES specialist_registry(id)
                    )
                """)

                # Migration: reset legacy tier default (3 -> 0) to match new enum
                # Only run once — guard with migration_log table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS _migration_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE NOT NULL,
                        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("SELECT id FROM _migration_log WHERE name = 'legacy_tier_reset'")
                if not cursor.fetchone():
                    try:
                        cursor.execute("UPDATE specialist_registry SET tier = 0 WHERE tier = 3")
                        cursor.execute("INSERT INTO _migration_log (name) VALUES ('legacy_tier_reset')")
                        logger.info("Migration 'legacy_tier_reset' applied")
                    except sqlite3.OperationalError:
                        pass

                # Migration: deduplicate knowledge_packages and add UNIQUE(qid,domain)
                cursor.execute("SELECT id FROM _migration_log WHERE name = 'kp_dedup_qid_domain'")
                if not cursor.fetchone():
                    try:
                        cursor.execute("""
                            DELETE FROM knowledge_packages
                            WHERE qid IS NOT NULL AND rowid NOT IN (
                                SELECT MIN(rowid) FROM knowledge_packages
                                WHERE qid IS NOT NULL GROUP BY qid, domain
                            )
                        """)
                        cursor.execute("""
                            CREATE UNIQUE INDEX IF NOT EXISTS idx_kp_qid_domain
                            ON knowledge_packages(qid, domain)
                        """)
                        cursor.execute("INSERT INTO _migration_log (name) VALUES ('kp_dedup_qid_domain')")
                        logger.info("Migration 'kp_dedup_qid_domain' applied")
                    except sqlite3.OperationalError:
                        pass

                # Migration: populate FTS5 index for existing knowledge_packages
                cursor.execute("SELECT id FROM _migration_log WHERE name = 'kp_fts5_populate'")
                if not cursor.fetchone():
                    try:
                        cursor.execute("""
                            INSERT INTO knowledge_packages_fts(rowid, topic, structured_knowledge, domain)
                            SELECT id, topic, structured_knowledge, domain FROM knowledge_packages
                        """)
                        cursor.execute("INSERT INTO _migration_log (name) VALUES ('kp_fts5_populate')")
                        logger.info("Migration 'kp_fts5_populate' applied")
                    except sqlite3.OperationalError as e:
                        logger.warning(f"FTS5 populate migration skipped: {e}")

                # Migration: add feed_packages column for separating feed vs real EMA
                cursor.execute("SELECT id FROM _migration_log WHERE name = 'kp_feed_packages_col'")
                if not cursor.fetchone():
                    try:
                        cursor.execute(
                            "ALTER TABLE specialist_registry ADD COLUMN feed_packages INTEGER DEFAULT 0"
                        )
                        cursor.execute("INSERT INTO _migration_log (name) VALUES ('kp_feed_packages_col')")
                        logger.info("Migration 'kp_feed_packages_col' applied")
                    except sqlite3.OperationalError:
                        pass

                self._get_connection().commit()
                logger.info("Specialist tables initialized successfully")
                return True
                
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize specialist tables: {e}")
            self._get_connection().rollback()
            return False
    
    def cleanup(self) -> None:
        """Cleanup resources and close connection."""
        self._close_connection()
        logger.info("DatabaseManager cleanup completed")

    def backup(self, backup_path: Optional[Path] = None) -> bool:
        """Create a backup of the database using VACUUM INTO.
        
        Args:
            backup_path: Path for the backup file. If None, uses {db_name}.backup.{timestamp}.db
            
        Returns:
            True if backup succeeded, False otherwise
        """
        try:
            if backup_path is None:
                from datetime import datetime
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_path = self._db_path.parent / f"{self._db_path.stem}.backup.{timestamp}.db"
            
            conn = self._get_connection()
            conn.execute(f"VACUUM INTO '{backup_path}'")
            logger.info(f"Database backup created: {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Database backup failed: {e}")
            return False


# Global instance for easy access
_db_manager: Optional[DatabaseManager] = None


def get_db_manager(db_path: Optional[Path] = None) -> DatabaseManager:
    """
    Get the global DatabaseManager instance.
    
    Args:
        db_path: Optional database path (only used on first call)
        
    Returns:
        DatabaseManager singleton instance
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager(db_path)
    return _db_manager


def reset_db_manager() -> None:
    """Reset the global DatabaseManager instance (for testing)."""
    global _db_manager
    if _db_manager is not None:
        _db_manager.cleanup()
    _db_manager = None
    DatabaseManager._instance = None
    DatabaseManager._initialized = False
