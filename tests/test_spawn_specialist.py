"""Tests for tools/spawn_specialist.py — QID validation, label resolution, spawn."""
import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestBatchResolveLabels:
    """Tests for batch_resolve_labels() function exists and is callable."""

    def test_import_exists(self):
        from tools.spawn_specialist import batch_resolve_labels
        assert callable(batch_resolve_labels)

    def test_function_signature(self):
        import inspect
        from tools.spawn_specialist import batch_resolve_labels
        sig = inspect.signature(batch_resolve_labels)
        params = list(sig.parameters.keys())
        assert 'qids' in params


class TestGetQualifiedSpecialists:
    """Tests for get_qualified_specialists() query."""

    def test_import_exists(self):
        from tools.spawn_specialist import get_qualified_specialists
        assert callable(get_qualified_specialists)

    def test_function_signature(self):
        import inspect
        from tools.spawn_specialist import get_qualified_specialists
        sig = inspect.signature(get_qualified_specialists)
        params = list(sig.parameters.keys())
        assert 'db' in params


class TestSpawnChild:
    """Tests for spawn_child() specialist creation."""

    def test_import_exists(self):
        from tools.spawn_specialist import spawn_child
        assert callable(spawn_child)

    def test_function_signature(self):
        import inspect
        from tools.spawn_specialist import spawn_child
        sig = inspect.signature(spawn_child)
        params = list(sig.parameters.keys())
        assert 'db' in params
        assert 'parent_id' in params
        assert 'qid' in params
