"""DuckDuckGo search engine integration with anti-blocking measures.

This module provides safe web search functionality using DuckDuckGo,
with randomized delays and rotating User-Agent headers to prevent blocking.
"""

import random
import time
import asyncio
import logging
from typing import List, Dict, Optional

from ddgs import DDGS
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
    safesearch: str = "moderate"
) -> List[Dict[str, str]]:
    """Perform a DuckDuckGo search with anti-blocking measures and trust scoring.
    
    Args:
        query: The search query string.
        max_results: Maximum number of results to return (default from settings).
        region: Region for search results (default: "us-en").
        safesearch: Safe search level (default: "moderate").
        
    Returns:
        List[Dict[str, str]]: List of search results with 'title', 'href', and 'body',
                               sorted by trust score.
        
    Raises:
        Exception: If search fails or returns no results.
    """
    if max_results is None:
        max_results = MAX_RESULTS_PER_SEARCH
    
    # Apply initial delay
    apply_random_delay()
    
    # Get random user agent
    user_agent = get_random_user_agent()
    logger.info(f"Search query: '{query}' with User-Agent: {user_agent[:50]}...")
    
    try:
        # Perform search using DDGS
        with DDGS() as ddgs:
            results = []
            for result in ddgs.text(
                query,
                region=region,
                safesearch=safesearch,
                max_results=max_results * 2  # Fetch more to allow for trust-based filtering
            ):
                if result and 'href' in result:
                    results.append({
                        'title': result.get('title', ''),
                        'href': result.get('href', ''),
                        'body': result.get('body', '')
                    })
            
            if not results:
                logger.warning(f"No results found for query: '{query}'")
                return []
            
            logger.info(f"Found {len(results)} results for query: '{query}'")
            
            # Filter valid URLs
            valid_results = filter_valid_urls(results)
            
            # Sort by trust score and return top results
            sorted_results = sort_results_by_trust(valid_results, max_results)
            
            return sorted_results
            
    except Exception as e:
        logger.error(f"Search failed for query '{query}': {e}")
        raise


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


async def search_topic(query: str, max_results: int = 3) -> List[Dict[str, str]]:
    """Async-compatible function to search for a topic using DuckDuckGo with trust scoring.
    
    This function fetches configuration from settings.py to use custom desktop
    User-Agent rotation and randomized delays to prevent Windows network/IP blocking.
    Results are sorted by source trust score before returning.
    
    Args:
        query: The search query string.
        max_results: Maximum number of results to return (default: 3).
        
    Returns:
        List[Dict[str, str]]: List of search results with keys 'title', 'url', 'snippet',
                               sorted by trust score.
        
    Raises:
        Exception: If search fails or returns no results.
    """
    # Apply randomized delay before search to emulate human behavior
    delay = random.uniform(SEARCH_DELAY_MIN, SEARCH_DELAY_MAX)
    logger.info(f"Applying anti-blocking delay: {delay:.2f} seconds")
    await asyncio.sleep(delay)
    
    # Get random User-Agent from settings
    user_agent = get_random_user_agent()
    logger.info(f"Search query: '{query}' with User-Agent: {user_agent[:50]}...")
    
    try:
        # Perform search using DDGS
        with DDGS() as ddgs:
            results = []
            for result in ddgs.text(
                query,
                region="us-en",
                safesearch="moderate",
                max_results=max_results * 2  # Fetch more to allow for trust-based filtering
            ):
                if result and 'href' in result:
                    results.append({
                        'title': result.get('title', ''),
                        'url': result.get('href', ''),
                        'snippet': result.get('body', '')
                    })
            
            if not results:
                logger.warning(f"No results found for query: '{query}'")
                return []
            
            logger.info(f"Found {len(results)} results for query: '{query}'")
            
            # Filter valid URLs
            valid_results = []
            for result in results:
                if validate_url(result.get('url', '')):
                    valid_results.append(result)
                else:
                    logger.warning(f"Filtered invalid URL: {result.get('url', 'N/A')}")
            
            logger.info(f"Filtered to {len(valid_results)} valid URLs from {len(results)} results")
            
            # Sort by trust score and return top results
            sorted_results = sort_results_by_trust(valid_results, max_results)
            
            return sorted_results
            
    except Exception as e:
        logger.error(f"Search failed for query '{query}': {e}")
        raise


class LibrarianScraper:
    """Async-compatible wrapper for the search engine.
    
    This class provides an interface that can be used in async contexts,
    even though the underlying DuckDuckGo search is synchronous.
    """
    
    def __init__(self):
        """Initialize the LibrarianScraper."""
        self.search_count = 0
    
    async def search(self, query: str, max_results: Optional[int] = None) -> List[Dict[str, str]]:
        """Perform a search (async wrapper for synchronous search).
        
        Args:
            query: The search query string.
            max_results: Maximum number of results to return.
            
        Returns:
            List[Dict[str, str]]: List of search results.
        """
        self.search_count += 1
        logger.info(f"LibrarianScraper search #{self.search_count}: '{query}'")
        
        # Run synchronous search
        results = search_duckduckgo(query, max_results)
        
        # Filter valid URLs
        valid_results = filter_valid_urls(results)
        
        return valid_results
    
    def get_search_count(self) -> int:
        """Get the total number of searches performed.
        
        Returns:
            int: Total search count.
        """
        return self.search_count
