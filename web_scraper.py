"""
Modern Web Scraper with Multi-Engine Fallback Chain

Engines tried in order:
  1. DuckDuckGo (ddgs) — primary web search
  2. Wikipedia API — free, reliable fallback
  3. Seed URLs — pre-selected high-quality sources per domain

"""

import random
import time
import asyncio
import logging
import json
import httpx
from typing import List, Dict, Optional
from pathlib import Path

from duckduckgo_search import DDGS
import trafilatura
from trafilatura import extract

from database.db_manager import get_db_manager
from config.settings import (
    USER_AGENTS,
    SEARCH_DELAY_MIN,
    SEARCH_DELAY_MAX,
    MAX_RESULTS_PER_SEARCH,
    SEARCH_TIMEOUT,
    WIKIPEDIA_USER_AGENT,
    WIKIPEDIA_API_URL,
    SEED_DIR,
)

logger = logging.getLogger(__name__)


class WebScraperError(Exception):
    pass


class RateLimitError(WebScraperError):
    pass


class ScraperTimeoutError(WebScraperError):
    pass


def get_random_user_agent() -> str:
    return random.choice(USER_AGENTS)


def apply_random_delay() -> None:
    delay = random.uniform(SEARCH_DELAY_MIN, SEARCH_DELAY_MAX)
    logger.info(f"Applying anti-blocking delay: {delay:.2f} seconds")
    time.sleep(delay)


def validate_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    if not url.startswith(('http://', 'https://')):
        return False
    invalid_patterns = ['javascript:', 'mailto:', 'tel:', 'data:']
    if any(pattern in url.lower() for pattern in invalid_patterns):
        return False
    return True


def score_source_trust(url: str) -> int:
    if not url or not isinstance(url, str):
        return 40
    url_lower = url.lower()
    tier1_patterns = [
        'arxiv.org', 'pubmed', 'ieee.org', 'acm.org', 'nature.com',
        '.edu', 'docs.python.org', 'postgresql.org', 'docs.microsoft.com',
        'developer.apple.com', 'docs.rs', 'go.dev', 'kubernetes.io', 'nginx.org'
    ]
    for pattern in tier1_patterns:
        if pattern in url_lower:
            return 100
    tier2_patterns = [
        'wikipedia.org', 'stackoverflow.com', 'developer.mozilla.org',
        'huggingface.co/docs', 'github.com', 'gitlab.com',
        'readthedocs.io', 'medium.com', 'dev.to'
    ]
    for pattern in tier2_patterns:
        if pattern in url_lower:
            return 70
    return 40


def filter_valid_urls(results: List[Dict[str, str]]) -> List[Dict[str, str]]:
    valid_results = []
    for result in results:
        if validate_url(result.get('href', '')):
            valid_results.append(result)
        else:
            logger.warning(f"Filtered invalid URL: {result.get('href', 'N/A')}")
    logger.info(f"Filtered to {len(valid_results)} valid URLs from {len(results)} results")
    return valid_results


def sort_results_by_trust(results: List[Dict[str, str]], max_results: int) -> List[Dict[str, str]]:
    scored_results = []
    for result in results:
        url = result.get('href', '') or result.get('url', '')
        trust_score = score_source_trust(url)
        scored_results.append({**result, 'trust_score': trust_score})
    scored_results.sort(key=lambda x: x['trust_score'], reverse=True)
    top_results = scored_results[:max_results]
    clean_results = [{k: v for k, v in r.items() if k != 'trust_score'} for r in top_results]
    logger.info(f"Sorted by trust score, returning top {len(clean_results)} results")
    return clean_results


# ──────────────────────────────────────────────
#  ENGINE 1: DuckDuckGo (ddgs)
# ──────────────────────────────────────────────

def search_duckduckgo(
    query: str,
    max_results: Optional[int] = None,
    region: str = "us-en",
    safesearch: str = "moderate",
) -> List[Dict[str, str]]:
    if max_results is None:
        max_results = MAX_RESULTS_PER_SEARCH
    apply_random_delay()
    user_agent = get_random_user_agent()
    logger.info(f"[DDGS] Search query: '{query}'")
    try:
        ddgs = DDGS()
        results = []
        try:
            search_results = ddgs.text(
                query,
                region=region,
                safesearch=safesearch,
                max_results=max_results * 2
            )
            for result in search_results:
                if result and 'href' in result:
                    results.append({
                        'title': result.get('title', ''),
                        'href': result.get('href', ''),
                        'body': result.get('body', '')
                    })
        except Exception as e:
            error_msg = str(e).lower()
            if '429' in error_msg or 'rate limit' in error_msg:
                raise RateLimitError(f"Rate limit exceeded: {e}")
            elif 'timeout' in error_msg or 'timed out' in error_msg:
                raise ScraperTimeoutError(f"Request timeout: {e}")
            else:
                raise WebScraperError(f"DDGS search failed: {e}")
        if not results:
            logger.warning(f"[DDGS] No results for '{query}'")
            return []
        logger.info(f"[DDGS] Found {len(results)} results for '{query}'")
        valid_results = filter_valid_urls(results)
        return sort_results_by_trust(valid_results, max_results)
    except (RateLimitError, ScraperTimeoutError):
        raise
    except Exception as e:
        logger.error(f"[DDGS] Unexpected error: {e}")
        raise WebScraperError(f"Unexpected search error: {e}")


# ──────────────────────────────────────────────
#  ENGINE 2: Wikipedia API
# ──────────────────────────────────────────────

def search_wikipedia(
    query: str,
    max_results: Optional[int] = None,
    lang: str = "en",
) -> List[Dict[str, str]]:
    if max_results is None:
        max_results = MAX_RESULTS_PER_SEARCH
    apply_random_delay()
    logger.info(f"[WIKI] Searching Wikipedia for: '{query}'")
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "format": "json",
        "srlimit": min(max_results * 2, 50),
        "srprop": "snippet|titlesnippet",
    }
    headers = {"User-Agent": WIKIPEDIA_USER_AGENT}
    last_error = None
    for attempt in range(3):
        try:
            with httpx.Client(timeout=SEARCH_TIMEOUT) as client:
                r = client.get(WIKIPEDIA_API_URL, params=params, headers=headers)
                r.raise_for_status()
                data = r.json()
            search_results = data.get("query", {}).get("search", [])
            if not search_results:
                logger.warning(f"[WIKI] No Wikipedia results for '{query}'")
                return []
            results = []
            for s in search_results[:max_results]:
                title = s.get("title", "")
                page_url = f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}"
                results.append({
                    "title": title,
                    "href": page_url,
                    "body": s.get("snippet", "").replace("<span class=\"searchmatch\">", "").replace("</span>", ""),
                })
            logger.info(f"[WIKI] Found {len(results)} results for '{query}'")
            return sort_results_by_trust(results, max_results)
        except httpx.HTTPStatusError as e:
            last_error = e
            if e.response.status_code in (429, 403):
                wait = 5 * (attempt + 1)
                logger.warning(f"[WIKI] HTTP {e.response.status_code}, retrying in {wait}s (attempt {attempt+1}/3)")
                time.sleep(wait)
                continue
            raise WebScraperError(f"Wikipedia search failed: {e}")
        except Exception as e:
            last_error = e
            logger.error(f"[WIKI] Search failed for '{query}' (attempt {attempt+1}/3): {e}")
            if attempt < 2:
                time.sleep(3 * (attempt + 1))
                continue
            raise WebScraperError(f"Wikipedia search failed: {e}")
    raise WebScraperError(f"Wikipedia search failed after 3 attempts: {last_error}")


# ──────────────────────────────────────────────
#  ENGINE 3: Seed URLs
# ──────────────────────────────────────────────

def load_seeds_for_domain(domain: str) -> List[Dict[str, str]]:
    seed_file = SEED_DIR / f"{domain}.json"
    if not seed_file.exists():
        return []
    try:
        with open(seed_file, "r", encoding="utf-8") as f:
            seeds = json.load(f)
        results = []
        for s in seeds:
            results.append({
                "title": s.get("title", ""),
                "href": s.get("url", ""),
                "body": s.get("description", ""),
            })
        logger.info(f"[SEED] Loaded {len(results)} seed URLs for '{domain}'")
        return results
    except Exception as e:
        logger.error(f"[SEED] Failed to load seeds for '{domain}': {e}")
        return []


def search_seeds(query: str, domain: Optional[str] = None) -> List[Dict[str, str]]:
    if not domain:
        return []
    results = load_seeds_for_domain(domain)
    if not results:
        return []
    query_lower = query.lower()
    query_terms = query_lower.split()
    scored = []
    for r in results:
        title = (r.get("title") or "").lower()
        body = (r.get("body") or "").lower()
        match_count = sum(1 for t in query_terms if t in title or t in body)
        if match_count > 0:
            scored.append((match_count, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [r for _, r in scored[:MAX_RESULTS_PER_SEARCH]]
    if top:
        logger.info(f"[SEED] Matched {len(top)} seeds for query '{query}'")
    return top


# ──────────────────────────────────────────────
#  MASTER: Try engines in chain
# ──────────────────────────────────────────────

def multi_engine_search(
    query: str,
    max_results: Optional[int] = None,
    domain: Optional[str] = None,
) -> List[Dict[str, str]]:
    errors = []

    # Engine 1: DuckDuckGo
    try:
        results = search_duckduckgo(query, max_results)
        if results:
            logger.info(f"[FALLBACK] DDGS returned {len(results)} results — using them")
            return results
    except Exception as e:
        errors.append(f"DDGS: {e}")
        logger.warning(f"[FALLBACK] DDGS failed: {e}")

    # Engine 2: Wikipedia
    try:
        results = search_wikipedia(query, max_results)
        if results:
            logger.info(f"[FALLBACK] Wikipedia returned {len(results)} results — using them")
            return results
    except Exception as e:
        errors.append(f"Wikipedia: {e}")
        logger.warning(f"[FALLBACK] Wikipedia failed: {e}")

    # Engine 3: Seed URLs (domain-specific)
    try:
        results = search_seeds(query, domain)
        if results:
            logger.info(f"[FALLBACK] Seeds returned {len(results)} results — using them")
            return results
    except Exception as e:
        errors.append(f"Seeds: {e}")
        logger.warning(f"[FALLBACK] Seeds failed: {e}")

    logger.error(f"[FALLBACK] All engines failed for '{query}': {'; '.join(errors)}")
    return []


# ──────────────────────────────────────────────
#  CONTENT EXTRACTOR (unchanged core)
# ──────────────────────────────────────────────

class ContentExtractor:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.headers = {"User-Agent": WIKIPEDIA_USER_AGENT}
        self.client = httpx.Client(timeout=timeout, headers=self.headers)

    def extract_content(self, url: str) -> Optional[Dict[str, str]]:
        try:
            response = self.client.get(url, follow_redirects=True)
            response.raise_for_status()
            html = response.text
            content = extract(
                html,
                output_format='json',
                include_comments=False,
                include_tables=False
            )
            if content:
                content_dict = json.loads(content)
                from urllib.parse import urlparse
                domain = urlparse(url).netloc.lower()
                high_trust = any(d in domain for d in [
                    'wikipedia', 'britannica', 'nature.com', 'sciencedirect',
                    'ieee', 'acm.org', 'arxiv', 'springer', 'pubmed',
                    'reuters', 'bloomberg', 'ft.com', 'wsj',
                ])
                trust_score = 85 if high_trust else 65
                result = {
                    'title': content_dict.get('title', ''),
                    'content': content_dict.get('text', ''),
                    'author': content_dict.get('author', ''),
                    'date': content_dict.get('date', ''),
                    'url': url,
                    'trust_score': trust_score,
                }
                logger.info(f"Successfully extracted content from {url}")
                return result
            logger.warning(f"Failed to extract content from {url}")
            return None
        except httpx.TimeoutException:
            raise ScraperTimeoutError(f"Timeout while fetching {url}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise RateLimitError(f"Rate limit while fetching {url}")
            raise WebScraperError(f"HTTP error {e.response.status_code}")
        except Exception as e:
            raise WebScraperError(f"Content extraction failed: {e}")

    def cleanup(self) -> None:
        self.client.close()
        logger.info("ContentExtractor cleanup completed")


# ──────────────────────────────────────────────
#  MODERN WEB SCRAPER (public API)
# ──────────────────────────────────────────────

class ModernWebScraper:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.content_extractor = ContentExtractor(timeout)
        self.db_manager = get_db_manager()
        self.search_count = 0

    async def search_and_extract(
        self,
        query: str,
        max_results: Optional[int] = None,
        domain: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        self.search_count += 1
        logger.info(f"ModernWebScraper #{self.search_count}: '{query}' (domain={domain})")

        search_results = multi_engine_search(query, max_results, domain=domain)

        if not search_results:
            logger.warning(f"No results from any engine for '{query}'")
            return []

        extracted_contents = []
        sem = asyncio.Semaphore(5)

        async def process_url(result):
            url = result.get('href', '')
            if not url:
                return None
            async with sem:
                try:
                    content = await asyncio.to_thread(self.content_extractor.extract_content, url)
                    if content:
                        self._store_content(content, query)
                        return content
                except (RateLimitError, ScraperTimeoutError, WebScraperError) as e:
                    logger.warning(f"Skipping {url}: {e}")
                return None

        tasks = [process_url(result) for result in search_results]
        results_gathered = await asyncio.gather(*tasks)
        extracted_contents = [c for c in results_gathered if c is not None]

        logger.info(f"Extracted content from {len(extracted_contents)} URLs")
        return extracted_contents

    def _store_content(self, content: Dict[str, str], query: str) -> None:
        try:
            self.db_manager.execute_query(
                """INSERT INTO knowledge_packages
                   (topic, source_url, domain, structured_knowledge, created_at)
                   VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                (query, content.get('url', ''), 'general', content.get('content', ''))
            )
        except Exception as e:
            logger.error(f"Failed to store content: {e}")

    def cleanup(self) -> None:
        self.content_extractor.cleanup()
        logger.info("ModernWebScraper cleanup completed")
