"""
Knowledge Ingestor - Local RAG System Context Provider

Reads local knowledge packages and reports as "System Context"
for LLM distillation prompts.
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class KnowledgeIngestor:
    """Provides local file content as System Context for LLM prompts."""

    def __init__(self, packages_dir: Path, reports_dir: Path):
        self.packages_dir = packages_dir
        self.reports_dir = reports_dir

    def get_system_context(self, domain: Optional[str] = None, max_chars: int = 3000) -> str:
        """Build a System Context block from local files, optionally filtered by domain.

        Args:
            domain: If set, only include files mentioning this domain.
            max_chars: Maximum total characters for the context block.

        Returns:
            Formatted context string ready for prompt injection.
        """
        parts = []

        # Load knowledge packages (recursive: domain subdirectories)
        if self.packages_dir.exists():
            for f in sorted(self.packages_dir.rglob("*.md"), reverse=True)[:5]:
                try:
                    content = f.read_text(encoding="utf-8")
                    if domain is None or domain.lower() in content.lower():
                        parts.append(f"[Package: {f.stem}]\n{content[:800]}")
                except Exception as e:
                    logger.debug(f"Ignoring package {f.name}: {e}")

        # Load recent reports (last 3)
        if self.reports_dir.exists():
            for f in sorted(self.reports_dir.rglob("*.md"), reverse=True)[:3]:
                try:
                    content = f.read_text(encoding="utf-8")
                    if domain is None or domain.lower() in content.lower():
                        parts.append(f"[Report: {f.stem}]\n{content[:800]}")
                except Exception as e:
                    logger.debug(f"Ignoring report {f.name}: {e}")

        if not parts:
            return ""

        combined = "\n\n".join(parts)
        if len(combined) > max_chars:
            combined = combined[:max_chars] + "\n[...truncated]"

        return f"=== System Context (Local Knowledge) ===\n{combined}"
