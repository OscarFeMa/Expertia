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
    # F-039: db_manager/readonly_db enlazan _DEFAULT_DB_PATH en import;
    # hay que parcharlos tambien o los tests escribirian la BD de produccion.
    import database.db_manager as _dbm
    import database.readonly_db as _ro
    monkeypatch.setattr(_dbm, "_DEFAULT_DB_PATH", test_db)
    monkeypatch.setattr(_ro, "_DEFAULT_DB_PATH", test_db)
    # Inicializar el pool read-only contra la BD de test: los endpoints de la
    # API usan readonly_db y fallaban con "not initialized".
    _ro.init(test_db)
    # Crear el schema en la BD de test (los endpoints consultan tablas).
    from database.db_manager import get_db_manager as _gdm
    try:
        _gdm(test_db).initialize_specialist_tables()
    except Exception as e:
        print(f"WARN: schema init en test_db fallo: {e}")
    # Sembrar las raices para que _find_best_domain / endpoints tengan datos.
    try:
        import json as _json
        from orchestrator import SPECIALIST_REGISTRY
        _dbm_seed = _gdm(test_db)
        for s in SPECIALIST_REGISTRY:
            _dbm_seed.execute_query(
                "INSERT OR IGNORE INTO specialist_registry (domain, model, root_qid, properties) VALUES (?,?,?,?)",
                (s["domain"], s["model"], s["root"], _json.dumps(s.get("props", [])))
            )
    except Exception as e:
        print(f"WARN: seed specialists fallo: {e}")
    monkeypatch.setattr("config.settings.STORAGE_DIR", tmp_path / "storage")
    monkeypatch.setattr("config.settings.PACKAGES_DIR", tmp_path / "storage" / "packages")
    monkeypatch.setattr("config.settings.REPORTS_DIR", tmp_path / "storage" / "reports")

    reset_db_manager()
    yield
    reset_db_manager()
