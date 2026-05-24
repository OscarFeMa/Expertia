import pytest
from unittest.mock import Mock, patch, MagicMock
import json

from web_scraper import (
    ModernWebScraper,
    ContentExtractor,
    search_duckduckgo,
    WebScraperError,
    RateLimitError,
    ScraperTimeoutError,
    get_random_user_agent,
    apply_random_delay
)


def test_get_random_user_agent():
    """Test that we get a valid user agent."""
    ua = get_random_user_agent()
    assert isinstance(ua, str)
    assert len(ua) > 10
    assert "Mozilla" in ua or "Chrome" in ua or "Firefox" in ua or "Safari" in ua


def test_content_extractor_init():
    """Test ContentExtractor initialization."""
    extractor = ContentExtractor(timeout=30)
    assert extractor.timeout == 30
    assert hasattr(extractor, 'client')
    extractor.client.close()  # cleanup


@patch('web_scraper.httpx.Client')
def test_content_extractor_extract_success(mock_client_class):
    """Test successful content extraction."""
    # Setup mock
    mock_response = Mock()
    mock_response.text = "<html><body><h1>Test</h1><p>Content here</p></body></html>"
    mock_response.raise_for_status.return_value = None
    
    mock_client = Mock()
    mock_client.get.return_value = mock_response
    mock_client_class.return_value = mock_client
    
    # Mock trafilatura.extract to return JSON
    with patch('web_scraper.extract') as mock_extract:
        mock_extract.return_value = json.dumps({
            'title': 'Test Title',
            'text': 'Test content',
            'author': 'Test Author',
            'date': '2026-01-01'
        })
        
        extractor = ContentExtractor()
        result = extractor.extract_content('http://example.com')
        
        assert result is not None
        assert result['title'] == 'Test Title'
        assert result['content'] == 'Test content'
        assert result['author'] == 'Test Author'
        assert result['date'] == '2026-01-01'
        assert result['url'] == 'http://example.com'
        
        # The client cleanup is handled by the extractor's cleanup method
        # which we're not testing here - we just verify the extraction worked
        extractor.client.close()


@patch('web_scraper.httpx.Client')
def test_content_extractor_extract_failure(mock_client_class):
    """Test content extraction failure raises exception."""
    # Setup mock to raise exception
    mock_client = Mock()
    mock_client.get.side_effect = Exception("Network error")
    mock_client_class.return_value = mock_client
    
    extractor = ContentExtractor()
    # Should raise WebScraperError on network failure
    with pytest.raises(WebScraperError):
        extractor.extract_content('http://example.com')
    # Cleanup
    extractor.client.close()


def test_modern_web_scraper_init():
    """Test ModernWebScraper initialization."""
    scraper = ModernWebScraper(timeout=30)
    assert scraper.timeout == 30
    assert scraper.search_count == 0
    assert hasattr(scraper, 'content_extractor')
    assert hasattr(scraper, 'db_manager')
    scraper.content_extractor.cleanup()


@patch('web_scraper.search_duckduckgo')
@patch('web_scraper.ModernWebScraper._store_content')
def test_search_and_extract(mock_store_content, mock_search):
    """Test the search_and_extract method."""
    # Setup mocks
    mock_search.return_value = [
        {'title': 'Result 1', 'href': 'http://example1.com', 'body': 'Body 1'},
        {'title': 'Result 2', 'href': 'http://example2.com', 'body': 'Body 2'}
    ]
    
    scraper = ModernWebScraper()
    # Mock the content extractor's extract_content method
    scraper.content_extractor.extract_content = Mock()
    scraper.content_extractor.extract_content.side_effect = [
        {'title': 'Content 1', 'content': 'Text 1', 'url': 'http://example1.com'},
        {'title': 'Content 2', 'content': 'Text 2', 'url': 'http://example2.com'}
    ]
    
    # Run the async method
    import asyncio
    results = asyncio.run(scraper.search_and_extract('test query', max_results=2))
    
    assert len(results) == 2
    assert results[0]['title'] == 'Content 1'
    assert results[1]['title'] == 'Content 2'
    assert scraper.search_count == 1
    
    # Verify store_content was called twice
    assert mock_store_content.call_count == 2
    
    scraper.content_extractor.cleanup()


@patch('web_scraper.DDGS')
def test_search_duckduckgo_success(mock_ddgs_class):
    """Test successful DuckDuckGo search."""
    # Setup mock
    mock_ddgs_instance = Mock()
    mock_ddgs_instance.text.return_value = [
        {'title': 'Result 1', 'href': 'http://example1.com', 'body': 'Body 1'},
        {'title': 'Result 2', 'href': 'http://example2.com', 'body': 'Body 2'}
    ]
    mock_ddgs_class.return_value = mock_ddgs_instance
    
    results = search_duckduckgo('test query', max_results=2)
    
    assert len(results) == 2
    assert results[0]['href'] == 'http://example1.com'
    assert results[1]['href'] == 'http://example2.com'
    
    # Verify DDGS was called correctly
    mock_ddgs_class.assert_called_once()
    mock_ddgs_instance.text.assert_called_once_with(
        'test query',
        region='us-en',
        safesearch='moderate',
        max_results=4  # max_results * 2 for trust-based filtering
    )


@patch('web_scraper.DDGS')
def test_search_duckduckgo_rate_limit(mock_ddgs_class):
    """Test rate limit handling."""
    # Setup mock to raise exception with rate limit
    mock_ddgs_instance = Mock()
    mock_ddgs_instance.text.side_effect = Exception("429 Rate limit exceeded")
    mock_ddgs_class.return_value = mock_ddgs_instance
    
    with pytest.raises(RateLimitError):
        search_duckduckgo('test query')


@patch('web_scraper.DDGS')
def test_search_duckduckgo_timeout(mock_ddgs_class):
    """Test timeout handling."""
    # Setup mock to raise timeout exception
    mock_ddgs_instance = Mock()
    mock_ddgs_instance.text.side_effect = Exception("Request timed out")
    mock_ddgs_class.return_value = mock_ddgs_instance
    
    with pytest.raises(ScraperTimeoutError):
        search_duckduckgo('test query')


def test_apply_random_delay():
    """Test that delay function exists and can be called."""
    # Just test it doesn't crash - we won't actually wait in test
    # The function uses time.sleep internally
    assert callable(apply_random_delay)