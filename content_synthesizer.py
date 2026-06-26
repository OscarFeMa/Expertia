"""
Multi-Source Content Synthesizer

When multiple academic sources return content on the same topic/query,
consolidate into a single package with cross-references instead of
writing N individual rows to the database.
"""

import logging
import re
from typing import List, Dict, Optional
from collections import defaultdict
from content_quality import cosine_similarity

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.35


def _extract_key_terms(text: str) -> str:
    words = re.findall(r'[a-zA-Z]{4,}', text.lower())
    return ' '.join(sorted(set(words)))


def _group_similar(contents: List[Dict]) -> List[List[Dict]]:
    """Group similar content items together using cosine similarity on titles."""
    groups = []
    assigned = [False] * len(contents)

    for i in range(len(contents)):
        if assigned[i]:
            continue
        group = [contents[i]]
        assigned[i] = True
        title_i = (contents[i].get('title') or '') + ' ' + (contents[i].get('body') or '')[:200]
        for j in range(i + 1, len(contents)):
            if assigned[j]:
                continue
            title_j = (contents[j].get('title') or '') + ' ' + (contents[j].get('body') or '')[:200]
            sim = cosine_similarity(title_i, title_j)
            if sim >= SIMILARITY_THRESHOLD:
                group.append(contents[j])
                assigned[j] = True
        groups.append(group)

    return groups


def synthesize(query: str, domain: str,
               extracted_contents: List[Dict]) -> List[Dict]:
    """
    Group similar extracted contents by topic and produce consolidated packages.

    Each output dict has:
      - topic: original query
      - source_url: comma-separated URLs of all consolidated sources
      - domain: domain name
      - content: merged/consolidated text
      - source_count: number of sources consolidated
      - sources: list of individual source names
    """
    if not extracted_contents:
        return []

    groups = _group_similar(extracted_contents)

    results = []
    for group in groups:
        if len(group) == 1:
            c = group[0]
            c['source_count'] = 1
            c['sources'] = [c.get('source', c.get('source_url', 'unknown'))]
            results.append(c)
            continue

        best = max(group, key=lambda x: x.get('quality_score', 0) * x.get('trust_score', 50))
        urls = [c.get('url', c.get('source_url', '')) for c in group if c.get('url') or c.get('source_url')]
        source_names = list(set(
            c.get('source', c.get('source_url', '')).split('/')[2] if '//' in (c.get('source_url', '')) else 'web'
            for c in group
        ))

        best['source_url'] = ', '.join(urls[:3])
        if len(urls) > 3:
            best['source_url'] += f' (+{len(urls)-3} more)'
        best['source_count'] = len(group)
        best['sources'] = source_names
        best['topic'] = query
        best['domain'] = domain
        results.append(best)

    singletons = sum(1 for g in groups if len(g) == 1)
    merged = sum(1 for g in groups if len(g) > 1)
    logger.info(f"[SYNTHESIZER] Query '{query[:50]}': {len(groups)} groups "
                f"({singletons} single, {merged} merged) from {len(extracted_contents)} items "
                f"-> {len(results)} packages (saved {len(extracted_contents) - len(results)} writes)")
    return results
