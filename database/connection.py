"""SQLite database connection handling and table initialization.

This module provides functions to establish database connections,
initialize the expert_registry table, and manage database operations.
"""

import sqlite3
import logging
from typing import Optional
from pathlib import Path

from config.settings import DATABASE_PATH


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_connection() -> sqlite3.Connection:
    """Establish and return a SQLite database connection.
    
    Returns:
        sqlite3.Connection: A connection to the SQLite database.
        
    Raises:
        sqlite3.Error: If connection cannot be established.
    """
    try:
        # Ensure the database file exists
        DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(str(DATABASE_PATH))
        conn.row_factory = sqlite3.Row  # Enable row factory for dict-like access
        logger.info(f"Database connection established: {DATABASE_PATH}")
        return conn
    except sqlite3.Error as e:
        logger.error(f"Failed to establish database connection: {e}")
        raise


def initialize_database(conn: Optional[sqlite3.Connection] = None) -> None:
    """Initialize the expert_registry, knowledge_packages, and ema_history tables if they do not exist.
    
    Args:
        conn: Optional database connection. If None, creates a new connection.
        
    Raises:
        sqlite3.Error: If table initialization fails.
    """
    close_connection = False
    if conn is None:
        conn = get_connection()
        close_connection = True
    
    try:
        cursor = conn.cursor()
        
        # Create expert_registry table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS expert_registry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                core_domain TEXT NOT NULL,
                tags TEXT,
                ema_score REAL DEFAULT 0.0,
                system_prompt TEXT,
                tier INTEGER DEFAULT 3,
                packages_absorbed INTEGER DEFAULT 0,
                parent_expert_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (parent_expert_id) REFERENCES expert_registry(id)
            )
        """)
        
        # Create knowledge_packages table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS knowledge_packages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                source_url TEXT NOT NULL,
                domain TEXT,
                structured_knowledge TEXT,
                exam_dataset TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create ema_history table for tracking EMA score changes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ema_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                expert_id INTEGER NOT NULL,
                old_score REAL NOT NULL,
                new_score REAL NOT NULL,
                test_score REAL NOT NULL,
                alpha REAL NOT NULL,
                change_reason TEXT,
                package_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (expert_id) REFERENCES expert_registry(id)
            )
        """)
        
        # Create index on tags for faster searching
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tags 
            ON expert_registry(tags)
        """)
        
        # Create index on core_domain for faster searching
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_core_domain 
            ON expert_registry(core_domain)
        """)
        
        # Create index on knowledge_packages topic
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_topic 
            ON knowledge_packages(topic)
        """)
        
        # Create index on knowledge_packages domain
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_knowledge_domain 
            ON knowledge_packages(domain)
        """)
        
        # Create index on ema_history expert_id for faster querying
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_ema_expert_id
            ON ema_history(expert_id)
        """)

        # Create processed_queries table to prevent duplicate searches
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL UNIQUE,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create index on processed_queries query for faster lookup
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_processed_query
            ON processed_queries(query)
        """)

        # Create expert_creation_buffer table for demand-driven expert creation
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS expert_creation_buffer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sub_theme TEXT NOT NULL,
                domain TEXT NOT NULL,
                parent_expert_id INTEGER NOT NULL,
                encounter_count INTEGER DEFAULT 1,
                first_encountered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_encountered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(sub_theme, domain, parent_expert_id),
                FOREIGN KEY (parent_expert_id) REFERENCES expert_registry(id)
            )
        """)

        # Create index on expert_creation_buffer for faster lookup
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_buffer_sub_theme
            ON expert_creation_buffer(sub_theme, domain)
        """)

        # Create cartridge_offsets table for Wikidata dissection tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cartridge_offsets (
                qid TEXT PRIMARY KEY,
                cartridge_name TEXT,
                offset_start INTEGER,
                offset_end INTEGER,
                expert_id INTEGER,
                status TEXT DEFAULT 'Available',
                FOREIGN KEY (expert_id) REFERENCES expert_registry(id)
            )
        """)

        # Create index on cartridge_offsets expert_id for faster lookup
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_cartridge_expert_id
            ON cartridge_offsets(expert_id)
        """)

        conn.commit()
        logger.info("Database tables initialized successfully")
        
    except sqlite3.Error as e:
        logger.error(f"Failed to initialize database tables: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if close_connection and conn:
            conn.close()


def close_connection(conn: sqlite3.Connection) -> None:
    """Close a database connection safely.
    
    Args:
        conn: The database connection to close.
    """
    try:
        if conn:
            conn.close()
            logger.info("Database connection closed")
    except sqlite3.Error as e:
        logger.error(f"Error closing database connection: {e}")


def get_database_path() -> Path:
    """Return the path to the database file.
    
    Returns:
        Path: The path to the SQLite database file.
    """
    return DATABASE_PATH
