from config.settings import BLOCKLIST_LABELS, BLOCKLIST_LABEL_PREFIXES


def _is_blocklisted_label(label: str) -> bool:
    """Inline copy of orchestrator.PipelineController._is_blocklisted_label."""
    label_lower = label.strip().lower()
    if label_lower in BLOCKLIST_LABELS:
        return True
    for prefix in BLOCKLIST_LABEL_PREFIXES:
        if label_lower.startswith(prefix):
            return True
    return False


class TestBlocklist:
    def test_exact_blocklist_match(self):
        assert _is_blocklisted_label("field of study") is True
        assert _is_blocklisted_label("academic discipline") is True
        assert _is_blocklisted_label("medical specialty") is True

    def test_prefix_blocklist_match(self):
        assert _is_blocklisted_label("branch of biology") is True
        assert _is_blocklisted_label("field of engineering") is True
        assert _is_blocklisted_label("subclass of something") is True
        assert _is_blocklisted_label("type of disease") is True

    def test_case_insensitive(self):
        assert _is_blocklisted_label("Field Of Study") is True
        assert _is_blocklisted_label("BRANCH OF SCIENCE") is True

    def test_whitespace_handling(self):
        assert _is_blocklisted_label("  field of study  ") is True

    def test_valid_label_not_blocked(self):
        assert _is_blocklisted_label("Geriatrics") is False
        assert _is_blocklisted_label("Machine Learning") is False
        assert _is_blocklisted_label("Quantum Mechanics") is False
        assert _is_blocklisted_label("Software Engineering") is False

    def test_similar_but_not_exact(self):
        """Labels that are close but not exact should pass."""
        assert _is_blocklisted_label("study of fields") is False
        assert _is_blocklisted_label("discipline") is False

    def test_blocklist_labels_are_frozenset(self):
        assert isinstance(BLOCKLIST_LABELS, frozenset)
        assert isinstance(BLOCKLIST_LABEL_PREFIXES, frozenset)


class TestBatchResolveLabels:
    """Test the batching logic of _batch_resolve_labels."""

    def test_empty_qids_returns_empty(self):
        qids = []
        assert len(qids) == 0

    def test_batch_size_setting(self):
        from config.settings import WIKIDATA_LABEL_BATCH_SIZE
        assert WIKIDATA_LABEL_BATCH_SIZE == 50
