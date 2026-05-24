"""Test that llm_manager modules can be imported without errors."""

import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')


def test_imports():
    """Test that key modules can be imported."""
    # Test settings
    from config.settings import (
        OLLAMA_HOST,
        OLLAMA_PORT,
        LLM_TIMEOUT,
        LLM_TEMPERATURE,
        LLM_MAX_TOKENS,
    )
    assert OLLAMA_HOST is not None
    assert OLLAMA_PORT is not None
    
    # Test llm_manager
    from llm_manager import LLMRunner, get_llm_runner, OfflineVerificationEngine
    from llm_manager import (
        LocalModelNotFoundError,
        ModelLoadError,
        LLMQueryError,
        ModelTimeoutError,
        retry_with_exponential_backoff,
        ModelInfo,
        RunningModel,
    )
    
    # Test instantiation
    llm_runner = LLMRunner()
    assert llm_runner is not None
    
    # Test verification engine (doesn't require Ollama to be running)
    ve = OfflineVerificationEngine()
    assert ve is not None
    
    # Test that the exception classes exist
    assert LocalModelNotFoundError is not None
    assert ModelLoadError is not None
    assert LLMQueryError is not None
    assert ModelTimeoutError is not None
    
    # Test that the decorator exists
    assert retry_with_exponential_backoff is not None
    
    # Test that the dataclasses exist
    assert ModelInfo is not None
    assert RunningModel is not None
    
    print("OK LLM manager imports successful!")


if __name__ == "__main__":
    test_imports()