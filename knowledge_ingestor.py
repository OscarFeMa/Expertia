"""
Knowledge Ingestor - Local RAG System Context Provider

Reads knowledge packages from FTS5 index instead of filesystem,
providing "System Context" for LLM distillation prompts with
relevance scoring and domain filtering.
"""

import logging
from pathlib import Path
from typing import Optional

from database.db_manager import get_db_manager

logger = logging.getLogger(__name__)


class KnowledgeIngestor:
    """Provides FTS5-backed knowledge as System Context for LLM prompts."""

    def __init__(self, packages_dir: Path, reports_dir: Path):
        self.packages_dir = packages_dir
        self.reports_dir = reports_dir
        self.db_manager = get_db_manager()

    def get_system_context(self, domain: Optional[str] = None, max_chars: int = 3000) -> str:
        """Build a System Context block from FTS5 full-text search, filtered by domain.

        Args:
            domain: If set, only include packages matching this domain.
            max_chars: Maximum total characters for the context block.

        Returns:
            Formatted context string ready for prompt injection.
        """
        parts = []

        try:
            if domain:
                rows = self.db_manager.execute_query(
                    """SELECT kp.topic, kp.structured_knowledge, kp.domain, kp.source_url
                       FROM knowledge_packages_fts
                       JOIN knowledge_packages kp ON kp.rowid = knowledge_packages_fts.rowid
                       WHERE knowledge_packages_fts MATCH ?
                       ORDER BY rank
                       LIMIT 8""",
                    (domain,),
                    fetch=True,
                )
            else:
                rows = self.db_manager.execute_query(
                    """SELECT topic, structured_knowledge, domain, source_url
                       FROM knowledge_packages
                       WHERE structured_knowledge IS NOT NULL
                       ORDER BY created_at DESC
                       LIMIT 8""",
                    fetch=True,
                )

            for row in rows:
                topic = row.get('topic', '')
                content = row.get('structured_knowledge', '') or ''
                pkg_domain = row.get('domain', '') or ''
                url = row.get('source_url', '') or ''
                if len(content.strip()) < 20:
                    continue
                header = f"[Knowledge: {topic}]"
                if pkg_domain:
                    header += f" (domain: {pkg_domain})"
                if url:
                    header += f"\nSource: {url}"
                parts.append(f"{header}\n{content[:800]}")

        except Exception as e:
            logger.warning(f"FTS5 query failed, falling back to DB scan: {e}")
            try:
                if domain:
                    rows = self.db_manager.execute_query(
                        """SELECT topic, structured_knowledge, domain, source_url
                           FROM knowledge_packages
                           WHERE domain = ? AND structured_knowledge IS NOT NULL
                           ORDER BY created_at DESC
                           LIMIT 8""",
                        (domain,),
                        fetch=True,
                    )
                else:
                    rows = self.db_manager.execute_query(
                        """SELECT topic, structured_knowledge, domain, source_url
                           FROM knowledge_packages
                           WHERE structured_knowledge IS NOT NULL
                           ORDER BY created_at DESC
                           LIMIT 8""",
                        fetch=True,
                    )
                for row in rows:
                    topic = row.get('topic', '')
                    content = row.get('structured_knowledge', '') or ''
                    pkg_domain = row.get('domain', '') or ''
                    url = row.get('source_url', '') or ''
                    if len(content.strip()) < 20:
                        continue
                    header = f"[Knowledge: {topic}]"
                    if pkg_domain:
                        header += f" (domain: {pkg_domain})"
                    if url:
                        header += f"\nSource: {url}"
                    parts.append(f"{header}\n{content[:800]}")
            except Exception as fallback_e:
                logger.warning(f"Fallback DB query also failed: {fallback_e}")

        # Legacy file fallback only if DB returned nothing
        if not parts:
            parts = self._legacy_file_fallback(domain)

        if not parts:
            return ""

        combined = "\n\n".join(parts)
        if len(combined) > max_chars:
            combined = combined[:max_chars] + "\n[...truncated]"

        return f"=== System Context (Local Knowledge) ===\n{combined}"

    def _legacy_file_fallback(self, domain: Optional[str] = None) -> list:
        """Fallback: read .md files from disk if DB is empty."""
        import re
        parts = []
        if self.packages_dir.exists():
            for f in sorted(self.packages_dir.rglob("*.md"), reverse=True)[:5]:
                try:
                    content = f.read_text(encoding="utf-8")
                    content = re.sub(r'!\[.*?\]\(.*?\)', '', content)
                    if domain is None or domain.lower() in content.lower():
                        parts.append(f"[Package: {f.stem}]\n{content[:800]}")
                except Exception as e:
                    logger.debug(f"Ignoring package {f.name}: {e}")
        if self.reports_dir.exists():
            for f in sorted(self.reports_dir.rglob("*.md"), reverse=True)[:3]:
                try:
                    content = f.read_text(encoding="utf-8")
                    content = re.sub(r'!\[.*?\]\(.*?\)', '', content)
                    if domain is None or domain.lower() in content.lower():
                        parts.append(f"[Report: {f.stem}]\n{content[:800]}")
                except Exception as e:
                    logger.debug(f"Ignoring report {f.name}: {e}")
        return parts
