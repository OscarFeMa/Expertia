"""
Modern Web Scraper with Updated DDGS and Trafilatura Integration

Refactored web extraction module using modern duckduckgo-search>=9.14.0
and trafilatura==2.0.0 with robust error handling for Windows environment.

Key improvements:
- Modern DDGS().text() syntax (no deprecated context manager)
- Updated trafilatura extractor integration
- Robust error handling (timeouts, HTTP 429 rate limits)
- Thread-safe database operations via db_manager
"""

import random
import time
import asyncio
import logging
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
    SEARCH_TIMEOUT
)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class WebScraperError(Exception):
    """Custom exception for web scraping errors."""
    pass


class RateLimitError(WebScraperError):
    """Exception raised when rate limit is exceeded."""
    pass


class TimeoutError(WebScraperError):
    """Exception raised when request times out."""
    pass


def get_random_user_agent() -> str:
    """Get a random User-Agent header from the rotation list.
    
    Returns:
        str: A randomly selected User-Agent string.
    """
    return random.choice(USER_AGENTS)


def apply_random_delay() -> None:
    """Apply a randomized delay between search requests.
    
    This helps prevent rate limiting and blocking by mimicking human behavior.
    """
    delay = random.uniform(SEARCH_DELAY_MIN, SEARCH_DELAY_MAX)
    logger.info(f"Applying anti-blocking delay: {delay:.2f} seconds")
    time.sleep(delay)


def search_duckduckgo(
    query: str,
    max_results: Optional[int] = None,
    region: str = "us-en",
    safesearch: str = "moderate",
    timeout: int = 30
) -> List[Dict[str, str]]:
    """Perform a DuckDuckGo search with modern DDGS syntax and error handling.
    
    Uses modern DDGS().text() syntax without deprecated context manager.
    Includes robust error handling for timeouts and rate limits.
    
    Args:
        query: The search query string.
        max_results: Maximum number of results to return (default from settings).
        region: Region for search results (default: "us-en").
        safesearch: Safe search level (default: "moderate").
        timeout: Request timeout in seconds (default: 30).
        
    Returns:
        List[Dict[str, str]]: List of search results with 'title', 'href', and 'body'.
        
    Raises:
        WebScraperError: If search fails or returns no results.
        RateLimitError: If rate limit is exceeded (HTTP 429).
        TimeoutError: If request times out.
    """
    if max_results is None:
        max_results = MAX_RESULTS_PER_SEARCH
    
    # Apply initial delay
    apply_random_delay()
    
    # Get random user agent
    user_agent = get_random_user_agent()
    logger.info(f"Search query: '{query}' with User-Agent: {user_agent[:50]}...")
    
    try:
        # Modern DDGS syntax - no context manager
        ddgs = DDGS()
        results = []
        
        # Use text() method directly with timeout handling
        try:
            search_results = ddgs.text(
                query,
                region=region,
                safesearch=safesearch,
                max_results=max_results * 2  # Fetch more for trust-based filtering
            )
            
            # Process results
            for result in search_results:
                if result and 'href' in result:
                    results.append({
                        'title': result.get('title', ''),
                        'href': result.get('href', ''),
                        'body': result.get('body', '')
                    })
                    
        except Exception as e:
            # Check for rate limit indicators
            error_msg = str(e).lower()
            if '429' in error_msg or 'rate limit' in error_msg:
                logger.error(f"Rate limit exceeded for query '{query}': {e}")
                raise RateLimitError(f"Rate limit exceeded: {e}")
            elif 'timeout' in error_msg or 'timed out' in error_msg:
                logger.error(f"Timeout for query '{query}': {e}")
                raise TimeoutError(f"Request timeout: {e}")
            else:
                raise WebScraperError(f"Search failed: {e}")
        
        if not results:
            logger.warning(f"No results found for query: '{query}'")
            return []
        
        logger.info(f"Found {len(results)} results for query: '{query}'")
        
        # Filter valid URLs
        valid_results = filter_valid_urls(results)
        
        # Sort by trust score and return top results
        sorted_results = sort_results_by_trust(valid_results, max_results)
        
        return sorted_results
        
    except (RateLimitError, TimeoutError):
        raise  # Re-raise specific exceptions
    except Exception as e:
        logger.error(f"Unexpected error in search for query '{query}': {e}")
        raise WebScraperError(f"Unexpected search error: {e}")


def validate_url(url: str) -> bool:
    """Validate if a URL is properly formatted and accessible.
    
    Args:
        url: The URL to validate.
        
    Returns:
        bool: True if URL appears valid, False otherwise.
    """
    if not url or not isinstance(url, str):
        return False
    
    # Basic URL validation
    if not url.startswith(('http://', 'https://')):
        return False
    
    # Check for common invalid patterns
    invalid_patterns = ['javascript:', 'mailto:', 'tel:', 'data:']
    if any(pattern in url.lower() for pattern in invalid_patterns):
        return False
    
    return True


def score_source_trust(url: str) -> int:
    """Calculate trust score for a source URL based on domain tiers.
    
    Tier 1 (Score: 100): Academic and official documentation sources
    Tier 2 (Score: 70): Community knowledge and technical documentation
    Tier 3 (Score: 40): Standard blogs and other domains
    
    Args:
        url: The URL to score.
        
    Returns:
        int: Trust score (100, 70, or 40).
    """
    if not url or not isinstance(url, str):
        return 40
    
    url_lower = url.lower()
    
    # Tier 1: Academic and official documentation sources
    tier1_patterns = [
        'arxiv.org',
        'pubmed',
        'ieee.org',
        'acm.org',
        'nature.com',
        '.edu',
        'docs.python.org',
        'postgresql.org',
        'docs.microsoft.com',
        'developer.apple.com',
        'docs.rs',
        'go.dev',
        'kubernetes.io',
        'nginx.org'
    ]
    
    for pattern in tier1_patterns:
        if pattern in url_lower:
            logger.debug(f"Tier 1 source detected: {url}")
            return 100
    
    # Tier 2: Community knowledge and technical documentation
    tier2_patterns = [
        'wikipedia.org',
        'stackoverflow.com',
        'developer.mozilla.org',
        'huggingface.co/docs',
        'github.com',
        'gitlab.com',
        'readthedocs.io',
        'medium.com',
        'dev.to'
    ]
    
    for pattern in tier2_patterns:
        if pattern in url_lower:
            logger.debug(f"Tier 2 source detected: {url}")
            return 70
    
    # Tier 3: Standard blogs and other domains
    logger.debug(f"Tier 3 source detected: {url}")
    return 40


def filter_valid_urls(results: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Filter search results to only include valid URLs.
    
    Args:
        results: List of search results.
        
    Returns:
        List[Dict[str, str]]: Filtered list with only valid URLs.
    """
    valid_results = []
    for result in results:
        if validate_url(result.get('href', '')):
            valid_results.append(result)
        else:
            logger.warning(f"Filtered invalid URL: {result.get('href', 'N/A')}")
    
    logger.info(f"Filtered to {len(valid_results)} valid URLs from {len(results)} results")
    return valid_results


def sort_results_by_trust(results: List[Dict[str, str]], max_results: int) -> List[Dict[str, str]]:
    """Sort search results by source trust score and return top results.
    
    Args:
        results: List of search results.
        max_results: Maximum number of results to return.
        
    Returns:
        List[Dict[str, str]]: Sorted list with top results by trust score.
    """
    # Add trust score to each result
    scored_results = []
    for result in results:
        url = result.get('href', '') or result.get('url', '')
        trust_score = score_source_trust(url)
        scored_results.append({
            **result,
            'trust_score': trust_score
        })
    
    # Sort by trust score (descending)
    scored_results.sort(key=lambda x: x['trust_score'], reverse=True)
    
    # Log trust scores for debugging
    for idx, result in enumerate(scored_results[:5], 1):
        url = result.get('href', '') or result.get('url', '')
        logger.debug(f"Result {idx}: Trust Score {result['trust_score']} - {url[:60]}...")
    
    # Return top results
    top_results = scored_results[:max_results]
    
    # Remove trust_score field before returning (clean output)
    clean_results = []
    for result in top_results:
        clean_result = {k: v for k, v in result.items() if k != 'trust_score'}
        clean_results.append(clean_result)
    
    logger.info(f"Sorted by trust score, returning top {len(clean_results)} results")
    return clean_results


class ContentExtractor:
    """Modern content extractor using updated trafilatura==2.0.0."""
    
    def __init__(self, timeout: int = 30):
        """Initialize the content extractor.
        
        Args:
            timeout: HTTP request timeout in seconds.
        """
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)
    
    def extract_content(self, url: str) -> Optional[Dict[str, str]]:
        """Extract main content from a URL using trafilatura.
        
        Args:
            url: The URL to extract content from.
            
        Returns:
            Optional[Dict[str, str]]: Dictionary with 'title', 'content', 'author',
                                       'date', or None if extraction fails.
        """
        try:
            # Fetch HTML content (single request, no double-fetch)
            response = self.client.get(url, follow_redirects=True)
            response.raise_for_status()
            
            html = response.text
            
            # Use trafilatura to extract content from already-fetched HTML
            content = extract(
                html,
                output_format='json',
                include_comments=False,
                include_tables=False
            )
            
            if content:
                import json
                content_dict = json.loads(content)
                
                result = {
                    'title': content_dict.get('title', ''),
                    'content': content_dict.get('text', ''),
                    'author': content_dict.get('author', ''),
                    'date': content_dict.get('date', ''),
                    'url': url
                }
                
                logger.info(f"Successfully extracted content from {url}")
                return result
            
            logger.warning(f"Failed to extract content from {url}")
            return None
            
        except httpx.TimeoutException:
            logger.error(f"Timeout while fetching {url}")
            raise TimeoutError(f"Timeout while fetching {url}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.error(f"Rate limit while fetching {url}")
                raise RateLimitError(f"Rate limit while fetching {url}")
            else:
                logger.error(f"HTTP error {e.response.status_code} while fetching {url}")
                raise WebScraperError(f"HTTP error {e.response.status_code}")
        except Exception as e:
            logger.error(f"Failed to extract content from {url}: {e}")
            raise WebScraperError(f"Content extraction failed: {e}")
    
    def cleanup(self) -> None:
        """Cleanup HTTP client resources."""
        self.client.close()
        logger.info("ContentExtractor cleanup completed")


class ModernWebScraper:
    """Modern web scraper with updated DDGS and trafilatura integration."""
    
    def __init__(self, timeout: int = 30):
        """Initialize the modern web scraper.
        
        Args:
            timeout: Request timeout in seconds.
        """
        self.timeout = timeout
        self.content_extractor = ContentExtractor(timeout)
        self.db_manager = get_db_manager()
        self.search_count = 0
    
    async def search_and_extract(
        self,
        query: str,
        max_results: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """Search for query and extract content from results.
        
        Args:
            query: The search query string.
            max_results: Maximum number of results to process.
            
        Returns:
            List[Dict[str, str]]: List of extracted content dictionaries.
        """
        self.search_count += 1
        logger.info(f"ModernWebScraper search #{self.search_count}: '{query}'")
        
        # Search for URLs
        try:
            search_results = search_duckduckgo(query, max_results)
        except (RateLimitError, TimeoutError) as e:
            logger.error(f"Search failed: {e}")
            raise
        except WebScraperError as e:
            logger.error(f"Search failed: {e}")
            raise
        
        # Extract content from each URL
        extracted_contents = []
        for result in search_results:
            url = result.get('href', '')
            
            try:
                content = self.content_extractor.extract_content(url)
                if content:
                    extracted_contents.append(content)
                    
                    # Store in database using thread-safe manager
                    self._store_content(content, query)
                    
            except (RateLimitError, TimeoutError) as e:
                logger.warning(f"Skipping {url} due to error: {e}")
                continue
            except WebScraperError as e:
                logger.warning(f"Failed to extract from {url}: {e}")
                continue
        
        logger.info(f"Extracted content from {len(extracted_contents)} URLs")
        return extracted_contents
    
    def _store_content(self, content: Dict[str, str], query: str) -> None:
        """Store extracted content in database using thread-safe manager.
        
        Args:
            content: Content dictionary to store.
            query: Original search query.
        """
        try:
            self.db_manager.execute_query(
                """
                INSERT INTO knowledge_packages 
                (topic, source_url, domain, structured_knowledge, created_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (query, content.get('url', ''), 'general', content.get('content', ''))
            )
            logger.debug(f"Stored content from {content.get('url', '')}")
        except Exception as e:
            logger.error(f"Failed to store content: {e}")
    
    def cleanup(self) -> None:
        """Cleanup resources."""
        self.content_extractor.cleanup()
        logger.info("ModernWebScraper cleanup completed")
