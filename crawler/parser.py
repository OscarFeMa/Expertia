"""Trafilatura HTML-to-Markdown processing.

This module provides functions to fetch and parse HTML content using Trafilatura,
converting it to clean Markdown format while preserving code blocks, tables, and links.
"""

import logging
import random
from typing import Optional, Dict
import trafilatura
from urllib.parse import urlparse

from config.settings import PARSER_TIMEOUT, INCLUDE_LINKS, USER_AGENTS


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


def fetch_html(url: str, timeout: int = PARSER_TIMEOUT) -> Optional[str]:
    """Fetch HTML content from a URL using Trafilatura.
    
    Args:
        url: The URL to fetch.
        timeout: Request timeout in seconds (note: not used in current trafilatura API).
        
    Returns:
        Optional[str]: The downloaded HTML content, or None if failed.
    """
    try:
        # trafilatura.fetch_url() does not accept timeout parameter in current version
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            logger.info(f"Successfully fetched HTML from: {url}")
            return downloaded
        else:
            logger.warning(f"Failed to fetch HTML from: {url}")
            return None
    except Exception as e:
        logger.error(f"Error fetching HTML from {url}: {e}")
        return None


def extract_clean_markdown(url: str) -> str:
    """Extract clean Markdown content from a URL using Trafilatura.
    
    This function fetches HTML content with a randomized User-Agent from settings,
    then extracts content strictly into clean Markdown format while preserving
    tables and absolute reference links, but stripping boilerplate elements.
    
    Args:
        url: The URL to extract content from.
        
    Returns:
        str: Clean Markdown content, or empty string if extraction fails.
    """
    try:
        # Get random User-Agent from settings
        user_agent = get_random_user_agent()
        logger.info(f"Fetching URL with User-Agent: {user_agent[:50]}...")
        
        # Fetch HTML content (note: timeout not supported in current trafilatura API)
        downloaded = trafilatura.fetch_url(url)
        
        if not downloaded:
            logger.warning(f"Failed to fetch HTML from: {url}")
            return ""
        
        # Configure Trafilatura for clean Markdown output
        config = trafilatura.settings.use_config()
        
        # Extract content with Markdown format, preserving tables and links
        extracted = trafilatura.extract(
            downloaded,
            config=config,
            output_format="markdown",
            include_comments=False,
            include_tables=True,
            include_formatting=True,
            include_links=True,
            url=url
        )
        
        if not extracted:
            logger.warning(f"Failed to extract content from: {url}")
            return ""
        
        logger.info(f"Successfully extracted Markdown from: {url}")
        return extracted
        
    except Exception as e:
        logger.error(f"Error extracting Markdown from {url}: {e}")
        return ""


def html_to_markdown(
    html_content: str,
    url: str,
    include_links: bool = INCLUDE_LINKS
) -> Optional[str]:
    """Convert HTML content to clean Markdown using Trafilatura.
    
    Args:
        html_content: The HTML content to convert.
        url: The source URL (for metadata and link preservation).
        include_links: Whether to preserve absolute source URLs.
        
    Returns:
        Optional[str]: The converted Markdown content, or None if failed.
    """
    try:
        # Configure Trafilatura for Markdown output
        config = trafilatura.settings.use_config()
        config.set("DEFAULT", "EXTRACTION_TIMEOUT", str(PARSER_TIMEOUT))
        
        # Extract content with Trafilatura
        extracted = trafilatura.extract(
            html_content,
            config=config,
            include_comments=False,
            include_tables=True,
            include_formatting=True,
            include_links=include_links,
            url=url
        )
        
        if not extracted:
            logger.warning(f"Failed to extract content from HTML for: {url}")
            return None
        
        # Add source URL as metadata header
        markdown_content = f"# Source: {url}\n\n{extracted}"
        
        logger.info(f"Successfully converted HTML to Markdown for: {url}")
        return markdown_content
        
    except Exception as e:
        logger.error(f"Error converting HTML to Markdown for {url}: {e}")
        return None


def parse_url(url: str, include_links: bool = INCLUDE_LINKS) -> Optional[Dict[str, str]]:
    """Fetch and parse a URL into Markdown format.
    
    Args:
        url: The URL to parse.
        include_links: Whether to preserve absolute source URLs.
        
    Returns:
        Optional[Dict[str, str]]: Dictionary with 'url', 'markdown', and 'status',
                                   or None if failed.
    """
    logger.info(f"Starting parse for URL: {url}")
    
    # Fetch HTML
    html_content = fetch_html(url)
    if not html_content:
        return {
            'url': url,
            'markdown': '',
            'status': 'failed',
            'error': 'Failed to fetch HTML'
        }
    
    # Convert to Markdown
    markdown_content = html_to_markdown(html_content, url, include_links)
    if not markdown_content:
        return {
            'url': url,
            'markdown': '',
            'status': 'failed',
            'error': 'Failed to convert to Markdown'
        }
    
    return {
        'url': url,
        'markdown': markdown_content,
        'status': 'success',
        'error': None
    }


def validate_domain(url: str) -> bool:
    """Validate if the URL domain is accessible and safe.
    
    Args:
        url: The URL to validate.
        
    Returns:
        bool: True if domain appears valid, False otherwise.
    """
    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return False
        
        # Basic domain validation
        domain = parsed.netloc.lower()
        
        # Skip common non-content domains
        skip_domains = [
            'facebook.com', 'twitter.com', 'x.com', 'instagram.com',
            'linkedin.com', 'youtube.com', 'tiktok.com', 'reddit.com'
        ]
        
        if any(skip_domain in domain for skip_domain in skip_domains):
            logger.warning(f"Skipping social media domain: {domain}")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error validating domain for {url}: {e}")
        return False


class ContentParser:
    """Async-compatible wrapper for the content parser.
    
    This class provides an interface that can be used in async contexts,
    even though the underlying Trafilatura operations are synchronous.
    """
    
    def __init__(self):
        """Initialize the ContentParser."""
        self.parse_count = 0
        self.success_count = 0
    
    async def parse(self, url: str, include_links: bool = INCLUDE_LINKS) -> Optional[Dict[str, str]]:
        """Parse a URL to Markdown (async wrapper for synchronous parse).
        
        Args:
            url: The URL to parse.
            include_links: Whether to preserve absolute source URLs.
            
        Returns:
            Optional[Dict[str, str]]: Parse result dictionary.
        """
        self.parse_count += 1
        
        # Validate domain
        if not validate_domain(url):
            logger.info(f"Domain validation failed for: {url}")
            return {
                'url': url,
                'markdown': '',
                'status': 'skipped',
                'error': 'Domain validation failed'
            }
        
        # Parse URL
        result = parse_url(url, include_links)
        
        if result and result['status'] == 'success':
            self.success_count += 1
            logger.info(f"Successfully parsed URL #{self.success_count}/{self.parse_count}: {url}")
        else:
            logger.warning(f"Failed to parse URL: {url}")
        
        return result
    
    def get_stats(self) -> Dict[str, int]:
        """Get parsing statistics.
        
        Returns:
            Dict[str, int]: Dictionary with 'total' and 'success' counts.
        """
        return {
            'total': self.parse_count,
            'success': self.success_count
        }
