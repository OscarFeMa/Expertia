"""
Metrics Collector for Coral Thought Ecosystem.

Provides performance counters, progress tracking, and summary reports
for Phase A (Wikidata extraction) and Phase B (Web scraping + LLM).
"""

import time
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PhaseAMetrics:
    """Metrics collected during Phase A (Wikidata extraction)."""
    specialist_id: int
    domain: str
    success: bool
    entities_processed: int = 0
    entities_matched: int = 0
    timestamp: float = 0.0


@dataclass
class PhaseBMetrics:
    """Metrics collected during Phase B (Web scraping + LLM)."""
    specialist_id: int
    domain: str
    success: bool
    contents_count: int = 0
    timestamp: float = 0.0


class MetricsCollector:
    """Collects and reports performance metrics for pipeline runs."""

    def __init__(self):
        """Initialize the metrics collector."""
        self.phase_a_records: List[PhaseAMetrics] = []
        self.phase_b_records: List[PhaseBMetrics] = []
        self.pipeline_start: float = time.time()
        self.pipeline_end: Optional[float] = None

    def record_phase_a(
        self,
        specialist_id: int,
        domain: str,
        success: bool,
        entities_processed: int = 0,
        entities_matched: int = 0,
    ) -> None:
        """Record Phase A metrics for a specialist.

        Args:
            specialist_id: Specialist ID
            domain: Specialist domain name
            success: Whether extraction succeeded
            entities_processed: Total entities processed
            entities_matched: Total entities matched
        """
        self.phase_a_records.append(PhaseAMetrics(
            specialist_id=specialist_id,
            domain=domain,
            success=success,
            entities_processed=entities_processed,
            entities_matched=entities_matched,
            timestamp=time.time(),
        ))
        logger.info(
            f"[METRICS] Phase A | {domain} | "
            f"{'OK' if success else 'FAIL'} | "
            f"processed={entities_processed} matched={entities_matched}"
        )

    def record_phase_b(
        self,
        specialist_id: int,
        domain: str,
        success: bool,
        contents_count: int = 0,
    ) -> None:
        """Record Phase B metrics for a specialist.

        Args:
            specialist_id: Specialist ID
            domain: Specialist domain name
            success: Whether scraping succeeded
            contents_count: Number of contents extracted
        """
        self.phase_b_records.append(PhaseBMetrics(
            specialist_id=specialist_id,
            domain=domain,
            success=success,
            contents_count=contents_count,
            timestamp=time.time(),
        ))
        logger.info(
            f"[METRICS] Phase B | {domain} | "
            f"{'OK' if success else 'FAIL'} | "
            f"contents={contents_count}"
        )

    def print_summary(self) -> None:
        """Print a summary of all collected metrics."""
        self.pipeline_end = time.time()
        elapsed = self.pipeline_end - self.pipeline_start

        phase_a_ok = sum(1 for r in self.phase_a_records if r.success)
        phase_b_ok = sum(1 for r in self.phase_b_records if r.success)
        total_processed = sum(r.entities_processed for r in self.phase_a_records)
        total_matched = sum(r.entities_matched for r in self.phase_a_records)
        total_contents = sum(r.contents_count for r in self.phase_b_records)

        print()
        print("=" * 60)
        print("  METRICS SUMMARY")
        print("=" * 60)
        print(f"  Total time:         {elapsed:.1f}s")
        print(f"  Specialists (A):    {len(self.phase_a_records)} ({phase_a_ok} OK)")
        print(f"  Specialists (B):    {len(self.phase_b_records)} ({phase_b_ok} OK)")
        print(f"  Wikidata processed: {total_processed}")
        print(f"  Wikidata matched:   {total_matched}")
        print(f"  Web contents:       {total_contents}")
        print("=" * 60)
        print()

        logger.info(
            f"Pipeline complete: {elapsed:.1f}s, "
            f"{phase_a_ok}/{len(self.phase_a_records)} Phase A OK, "
            f"{phase_b_ok}/{len(self.phase_b_records)} Phase B OK, "
            f"{total_contents} web contents"
        )

    @property
    def summary_dict(self) -> Dict:
        """Return metrics as a dictionary for serialization.

        Returns:
            Dict with all collected metrics
        """
        return {
            "elapsed_seconds": (self.pipeline_end or time.time()) - self.pipeline_start,
            "phase_a": [
                {"domain": r.domain, "success": r.success,
                 "entities_processed": r.entities_processed,
                 "entities_matched": r.entities_matched}
                for r in self.phase_a_records
            ],
            "phase_b": [
                {"domain": r.domain, "success": r.success,
                 "contents_count": r.contents_count}
                for r in self.phase_b_records
            ],
        }
