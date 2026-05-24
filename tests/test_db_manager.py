import os
import tempfile
from pathlib import Path

from database.db_manager import get_db_manager, reset_db_manager


def test_singleton_same_instance():
    """Test that get_db_manager returns the same instance."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        # First call
        db1 = get_db_manager(db_path)
        # Second call with same path (should return same instance)
        db2 = get_db_manager(db_path)
        assert db1 is db2
        # Cleanup
        reset_db_manager()


def test_singleton_different_paths_first_call_wins():
    """Test that the first path used wins for singleton."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path1 = Path(tmpdir) / "test1.db"
        db_path2 = Path(tmpdir) / "test2.db"
        # First call with path1
        db1 = get_db_manager(db_path1)
        # Second call with path2 (should ignore path2 and return db1's instance)
        db2 = get_db_manager(db_path2)
        assert db1 is db2
        assert db1.db_path == db_path1  # Should be the first path
        reset_db_manager()


def test_initialize_tables():
    """Test that tables can be created."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = get_db_manager(db_path)
        # Initialize tables
        result = db.initialize_specialist_tables()
        assert result is True
        # Check that tables exist
        assert db.table_exists('specialist_registry') is True
        assert db.table_exists('cartridge_offsets') is True
        assert db.table_exists('knowledge_packages') is True
        assert db.table_exists('ema_history') is True
        reset_db_manager()


def test_insert_and_fetch_specialist():
    """Test inserting a specialist and fetching it."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = get_db_manager(db_path)
        db.initialize_specialist_tables()
        # Insert a specialist
        db.execute_query(
            """
            INSERT INTO specialist_registry 
            (domain, model, root_qid, properties, ema_score, tier, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ('TestDomain', 'test_model:1b', 'Q123', '["P31"]', 0.5, 3, 'IDLE')
        )
        # Fetch it
        rows = db.execute_query(
            "SELECT * FROM specialist_registry WHERE domain = ?",
            ('TestDomain',),
            fetch=True
        )
        assert len(rows) == 1
        row = rows[0]
        assert row['domain'] == 'TestDomain'
        assert row['model'] == 'test_model:1b'
        assert row['root_qid'] == 'Q123'
        assert row['ema_score'] == 0.5
        reset_db_manager()


def test_health_check():
    """Test health check on a fresh database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = get_db_manager(db_path)
        # Before initializing tables, health_check should still work (SELECT 1)
        # but table_exists will fail. However health_check just does SELECT 1.
        healthy = db.health_check()
        assert healthy is True
        reset_db_manager()