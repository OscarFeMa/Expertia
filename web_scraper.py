"""
Modern Web Scraper with Multi-Engine Fallback Chain

Engines tried in order:
   1. Academic sources (ArXiv, PubMed, CrossRef, Semantic Scholar, Wikipedia)
   2. DuckDuckGo (ddgs) — general web search
   3. Wikipedia API — free, reliable fallback
   4. Seed URLs — pre-selected high-quality sources per domain

All extracted content is scored for quality before storage.
"""

import random
import time
import asyncio
import logging
import json
import math
import httpx
from typing import List, Dict, Optional
from pathlib import Path

try:
    from ddgs import DDGS
except ModuleNotFoundError:
    from duckduckgo_search import DDGS

# Low-quality sources to exclude from scraping results
EXCLUDED_DOMAINS = {
    'www.geeksforgeeks.org',
    'www.bbc.co.uk/bitesize',
    'www.mdpi.com',
}
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
    LANGUAGES,
    QUALITY_THRESHOLD_MIN,
    QUALITY_THRESHOLD_ACCEPTABLE,
)
from source_reputation import SourceReputationTracker, is_blocked
from content_quality import ContentQualityScorer
from academic_sources import search_all_academic
from content_synthesizer import synthesize

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
        'developer.apple.com', 'docs.rs', 'go.dev', 'kubernetes.io', 'nginx.org',
        'ncbi.nlm.nih.gov', 'who.int', 'cochrane.org', 'nejm.org',
        'thelancet.com', 'bmj.com', 'jamanetwork.com', 'cell.com',
        'sciencedirect.com', 'springer.com', 'wiley.com',
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
        # Filter out excluded domains
        from urllib.parse import urlparse
        filtered = []
        for r in results:
            host = urlparse(r.get('href', '')).hostname or ''
            if host in EXCLUDED_DOMAINS or any(host.endswith('.' + d) for d in EXCLUDED_DOMAINS):
                continue
            filtered.append(r)
        results = filtered[:max_results]
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
    logger.info(f"[WIKI] Searching Wikipedia ({lang}) for: '{query}'")
    # Build language-specific API URL
    wiki_url = f"https://{lang}.wikipedia.org/w/api.php" if lang != "en" else WIKIPEDIA_API_URL
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
                r = client.get(wiki_url, params=params, headers=headers)
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
    safe_domain = Path(domain).name
    seed_file = SEED_DIR / f"{safe_domain}.json"
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
                "trust_score": s.get("trust", 70),
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

    # Engine 0: Academic sources (high-quality, domain-aware)
    try:
        results = search_all_academic(query, max_results, domain=domain)
        if results:
            logger.info(f"[FALLBACK] Academic returned {len(results)} results — using them")
            return results
    except Exception as e:
        errors.append(f"Academic: {e}")
        logger.warning(f"[FALLBACK] Academic failed: {e}")

    # Engine 1: DuckDuckGo
    try:
        results = search_duckduckgo(query, max_results)
        if results:
            logger.info(f"[FALLBACK] DDGS returned {len(results)} results — using them")
            return results
    except Exception as e:
        errors.append(f"DDGS: {e}")
        logger.warning(f"[FALLBACK] DDGS failed: {e}")

    # Engine 2: Wikipedia (try configured languages)
    for lang in LANGUAGES.split('|'):
        try:
            results = search_wikipedia(query, max_results, lang=lang)
            if results:
                logger.info(f"[FALLBACK] Wikipedia ({lang}) returned {len(results)} results — using them")
                return results
        except Exception as e:
            err_msg = f"Wikipedia({lang}): {e}"
            errors.append(err_msg)
            logger.warning(f"[FALLBACK] {err_msg}")

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
        self.reputation_tracker = SourceReputationTracker()

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
                trust_score = self.reputation_tracker.get_trust_score(url)
                result = {
                    'title': content_dict.get('title', ''),
                    'content': content_dict.get('text', ''),
                    'author': content_dict.get('author', ''),
                    'date': content_dict.get('date', ''),
                    'url': url,
                    'trust_score': trust_score,
                }
                logger.info(f"Successfully extracted content from {url} (trust={trust_score})")
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

    def __del__(self):
        self.client.close()

    def cleanup(self) -> None:
        self.client.close()
        logger.info("ContentExtractor cleanup completed")


# ──────────────────────────────────────────────
#  BLOOM FILTER — en memoria, sin consultas a HDD
# ──────────────────────────────────────────────

class BloomFilter:
    def __init__(self, capacity: int = 1_000_000, error_rate: float = 0.001):
        self.capacity = capacity
        self.error_rate = error_rate
        self.bit_count = self._optimal_bits(capacity, error_rate)
        self.hash_count = self._optimal_hashes(self.bit_count, capacity)
        self.bit_array = bytearray((self.bit_count + 7) // 8)
        self._inserted = 0

    @staticmethod
    def _optimal_bits(n: int, p: float) -> int:
        return int(-n * math.log(p) / (math.log(2) ** 2)) + 1

    @staticmethod
    def _optimal_hashes(m: int, n: int) -> int:
        return int(m / n * math.log(2)) + 1

    def _hashes(self, item: str) -> List[int]:
        h1 = hash(item)
        h2 = h1 >> 16
        return [(h1 + i * h2) % self.bit_count for i in range(self.hash_count)]

    def add(self, item: str) -> None:
        for bit in self._hashes(item):
            byte_idx = bit >> 3
            bit_offset = bit & 7
            self.bit_array[byte_idx] |= (1 << bit_offset)
        self._inserted += 1

    def __contains__(self, item: str) -> bool:
        for bit in self._hashes(item):
            byte_idx = bit >> 3
            bit_offset = bit & 7
            if not (self.bit_array[byte_idx] & (1 << bit_offset)):
                return False
        return True

    @property
    def size(self) -> int:
        return self._inserted


# ──────────────────────────────────────────────
#  MODERN WEB SCRAPER (public API)
# ──────────────────────────────────────────────

_search_cache: Dict[str, tuple] = {}  # query_key -> (timestamp, results)
_SEARCH_CACHE_TTL = 300  # 5 min — corto para evitar servir resultados obsoletos

_BATCH_FLUSH_INTERVAL_SECONDS = 30  # flush cada 30s aunque no se llene el buffer
_BATCH_FLUSH_SIZE = 50  # flush cada 50 packages


class ModernWebScraper:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.content_extractor = ContentExtractor(timeout)
        self.db_manager = get_db_manager()
        self.search_count = 0
        self.quality_scorer = ContentQualityScorer()
        self.reputation_tracker = SourceReputationTracker()
        self._batch_buffer: List[tuple] = []
        self._last_batch_flush = time.time()
        self._url_bloom = BloomFilter(capacity=500_000)
        self._bloom_enabled = True

    async def search_and_extract(
        self,
        query: str,
        max_results: Optional[int] = None,
        domain: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        self.search_count += 1
        cache_key = f"{query}|{max_results}|{domain}"
        now = time.time()

        # Check search cache before hitting engines
        if cache_key in _search_cache:
            ts, cached = _search_cache[cache_key]
            if now - ts < _SEARCH_CACHE_TTL:
                logger.info(f"ModernWebScraper #{self.search_count}: cache HIT for '{query}' ({len(cached)} results)")
                return cached

        logger.info(f"ModernWebScraper #{self.search_count}: '{query}' (domain={domain})")

        search_results = await asyncio.to_thread(multi_engine_search, query, max_results, domain)

        # Cache results (even empty — avoids repeated empty searches)
        _search_cache[cache_key] = (now, search_results)

        if not search_results:
            logger.warning(f"No results from any engine for '{query}'")
            return []

        sem = asyncio.Semaphore(5)

        async def process_url(result):
            url = result.get('href', '')
            if not url:
                return None
            async with sem:
                try:
                    content = await asyncio.to_thread(self.content_extractor.extract_content, url)
                    if content:
                        trust = self.reputation_tracker.get_trust_score(url)
                        content['trust_score'] = trust
                        qs = self.quality_scorer.score(
                            content.get('content', ''),
                            title=content.get('title', ''),
                        )
                        content['quality_score'] = qs['composite']
                        content['quality_details'] = qs
                        self._store_content(content, query, domain=domain or 'general')
                        return content
                except (RateLimitError, ScraperTimeoutError, WebScraperError) as e:
                    logger.warning(f"Skipping {url}: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error processing {url}: {e}")
                return None

        tasks = [process_url(result) for result in search_results]
        results_gathered = await asyncio.gather(*tasks, return_exceptions=True)
        extracted_contents = [c for c in results_gathered if isinstance(c, dict)]

        if extracted_contents:
            synthesized = synthesize(query, domain or 'general', extracted_contents)
            logger.info(f"Extracted content from {len(extracted_contents)} URLs -> synthesized to {len(synthesized)} packages")
            return synthesized

        logger.info(f"Extracted content from {len(extracted_contents)} URLs")
        return extracted_contents

    def _flush_batch(self) -> None:
        if not self._batch_buffer:
            return
        try:
            self.db_manager.execute_many(
                """INSERT INTO knowledge_packages
                   (topic, source_url, domain, structured_knowledge, created_at)
                   VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                self._batch_buffer
            )
            logger.info(f"Batch flush: {len(self._batch_buffer)} packages written")
            self._batch_buffer.clear()
        except Exception as e:
            logger.error(f"Batch flush failed ({len(self._batch_buffer)} packages lost): {e}")

    def _store_content(self, content: Dict[str, str], query: str, domain: str = 'general') -> None:
        url = content.get('url', '')
        text = content.get('content', '')
        if not text or len(text.strip()) < 200:
            logger.debug(f"Content too short ({len(text or '')} chars) from {url}")
            return
        lower_text = text.lower()
        garbage = ['cookie', 'sign in', 'javascript is disabled', 'loading',
                    'captcha', 'access denied', 'page not found']
        if any(p in lower_text for p in garbage):
            logger.debug(f"Garbage content detected from {url}")
            return
        quality_score = content.get('quality_score', 0.0)
        if quality_score < QUALITY_THRESHOLD_MIN:
            logger.info(f"Quality score {quality_score:.3f} below min threshold {QUALITY_THRESHOLD_MIN} — skipping {url}")
            return
        trust_score = content.get('trust_score', 0)
        if is_blocked(url):
            logger.info(f"Blocked domain — skipping {url}")
            return
        # Bloom filter: dedup rápido en RAM sin consultar HDD
        if self._bloom_enabled:
            if url in self._url_bloom:
                logger.debug(f"Bloom filter HIT — skipping duplicate URL: {url}")
                return
            self._url_bloom.add(url)
        self._batch_buffer.append((query[:100], url, domain, text[:5000]))
        now = time.time()
        if len(self._batch_buffer) >= _BATCH_FLUSH_SIZE or (now - self._last_batch_flush) >= _BATCH_FLUSH_INTERVAL_SECONDS:
            self._flush_batch()
            self._last_batch_flush = now

    def force_flush(self) -> None:
        self._flush_batch()
        self._last_batch_flush = time.time()

    def cleanup(self) -> None:
        self.force_flush()
        self.content_extractor.cleanup()
        logger.info(f"ModernWebScraper cleanup completed (bloom filter had {self._url_bloom.size} unique URLs)")
