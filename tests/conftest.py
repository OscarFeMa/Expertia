import sys
import os
import pytest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture(autouse=True)
def isolate_db(tmp_path, monkeypatch):
    from config.settings import STORAGE_DIR
    from database.db_manager import reset_db_manager

    test_db = tmp_path / "test_incubator.db"
    monkeypatch.setattr("config.settings.DATABASE_PATH", test_db)
    monkeypatch.setattr("config.settings.STORAGE_DIR", tmp_path / "storage")
    monkeypatch.setattr("config.settings.PACKAGES_DIR", tmp_path / "storage" / "packages")
    monkeypatch.setattr("config.settings.REPORTS_DIR", tmp_path / "storage" / "reports")

    reset_db_manager()
    yield
    reset_db_manager()
