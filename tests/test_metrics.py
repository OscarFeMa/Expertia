import time
from metrics import MetricsCollector


def test_metrics_collector_init():
    """Test MetricsCollector initialization."""
    metrics = MetricsCollector()
    assert len(metrics.phase_a_records) == 0
    assert len(metrics.phase_b_records) == 0
    assert metrics.pipeline_start > 0
    assert metrics.pipeline_end is None


def test_record_phase_a():
    """Test recording Phase A metrics."""
    metrics = MetricsCollector()
    metrics.record_phase_a(
        specialist_id=1,
        domain="TestDomain",
        success=True,
        entities_processed=1000,
        entities_matched=100
    )
    
    assert len(metrics.phase_a_records) == 1
    record = metrics.phase_a_records[0]
    assert record.specialist_id == 1
    assert record.domain == "TestDomain"
    assert record.success is True
    assert record.entities_processed == 1000
    assert record.entities_matched == 100
    assert record.timestamp > 0


def test_record_phase_b():
    """Test recording Phase B metrics."""
    metrics = MetricsCollector()
    metrics.record_phase_b(
        specialist_id=2,
        domain="AnotherDomain",
        success=False,
        contents_count=5
    )
    
    assert len(metrics.phase_b_records) == 1
    record = metrics.phase_b_records[0]
    assert record.specialist_id == 2
    assert record.domain == "AnotherDomain"
    assert record.success is False
    assert record.contents_count == 5
    assert record.timestamp > 0


def test_print_summary(capsys):
    """Test printing summary."""
    metrics = MetricsCollector()
    # Add some records
    metrics.record_phase_a(1, "Domain1", True, 100, 10)
    metrics.record_phase_a(2, "Domain2", False, 50, 0)
    metrics.record_phase_b(1, "Domain1", True, 3)
    metrics.record_phase_b(2, "Domain2", False, 0)
    
    # Print summary
    metrics.print_summary()
    
    # Capture output
    captured = capsys.readouterr()
    output = captured.out
    
    # Verify key elements are in output
    assert "METRICS SUMMARY" in output
    assert "Total time:" in output
    assert "Specialists (A):" in output
    assert "Specialists (B):" in output
    assert "Wikidata processed:" in output
    assert "Wikidata matched:" in output
    assert "Web contents:" in output


def test_summary_dict():
    """Test getting summary as dictionary."""
    metrics = MetricsCollector()
    metrics.record_phase_a(1, "TestDomain", True, 100, 10)
    metrics.record_phase_b(1, "TestDomain", True, 5)
    
    # Small delay to ensure elapsed time > 0
    time.sleep(0.01)
    
    summary = metrics.summary_dict
    assert "elapsed_seconds" in summary
    assert isinstance(summary["elapsed_seconds"], float)
    assert summary["elapsed_seconds"] >= 0
    
    assert "phase_a" in summary
    assert len(summary["phase_a"]) == 1
    assert summary["phase_a"][0]["domain"] == "TestDomain"
    assert summary["phase_a"][0]["success"] is True
    assert summary["phase_a"][0]["entities_processed"] == 100
    assert summary["phase_a"][0]["entities_matched"] == 10
    
    assert "phase_b" in summary
    assert len(summary["phase_b"]) == 1
    assert summary["phase_b"][0]["domain"] == "TestDomain"
    assert summary["phase_b"][0]["success"] is True
    assert summary["phase_b"][0]["contents_count"] == 5