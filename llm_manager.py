"""
LLM Manager - Local Ollama Integration Module

Handles local Ollama model interactions with:
- Offline verification engine (ollama list parsing)
- VRAM-aware Single-Active-Model pattern
- HTTP API communication (localhost:11434/api/generate)
- Performance optimization with async operations
- Production-ready error handling and logging

Hardware Constraints: NVIDIA RTX 1660 (6GB VRAM), 32GB RAM
"""

import subprocess
import time
import logging
import json
import asyncio
import os
import threading
import warnings
from typing import Optional, List, Dict, Callable
from dataclasses import dataclass
from functools import wraps

import aiohttp

from config.settings import (
    OLLAMA_HOST,
    OLLAMA_PORT,
    LLM_TIMEOUT,
    LLM_TEMPERATURE,
    LLM_MAX_TOKENS,
)

logger = logging.getLogger(__name__)


# ============================================================================
# CUSTOM EXCEPTIONS
# ============================================================================

class LocalModelNotFoundError(Exception):
    """Raised when required model is not found in local Ollama cache."""
    pass


class ModelLoadError(Exception):
    """Raised when model loading fails."""
    pass


class LLMQueryError(Exception):
    """Raised when LLM query fails."""
    pass


class ModelTimeoutError(Exception):
    """Raised when model operation times out."""
    pass


# ============================================================================
# RETRY LOGIC WITH EXPONENTIAL BACKOFF
# ============================================================================

def retry_with_exponential_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0
):
    """Decorator for retry logic with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        backoff_factor: Multiplier for delay after each retry
    """
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except (aiohttp.ClientError, asyncio.TimeoutError, LLMQueryError, ModelTimeoutError) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries} failed: {e}. "
                            f"Retrying in {delay:.1f}s..."
                        )
                        await asyncio.sleep(min(delay, max_delay))
                        delay *= backoff_factor
                    else:
                        logger.error(f"All {max_retries} attempts failed")
                        raise
                except Exception as e:
                    # Don't retry on non-retryable exceptions
                    raise
            
            raise last_exception if last_exception else Exception("Retry logic failed")
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries} failed: {e}. "
                            f"Retrying in {delay:.1f}s..."
                        )
                        time.sleep(min(delay, max_delay))
                        delay *= backoff_factor
                    else:
                        logger.error(f"All {max_retries} attempts failed")
                        raise
            
            raise last_exception if last_exception else Exception("Retry logic failed")
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class ModelInfo:
    """Information about a local Ollama model."""
    name: str
    size: str
    modified_at: str


@dataclass
class RunningModel:
    """Information about a currently running model."""
    name: str
    size: str
    status: str


# ============================================================================
# OFFLINE VERIFICATION ENGINE
# ============================================================================

def _find_ollama_binary() -> str:
    """Locate ollama executable in PATH or common install locations."""
    import shutil
    exe = shutil.which("ollama")
    if exe:
        return exe
    if os.name == "nt":
        local = os.environ.get("LOCALAPPDATA", "")
        candidate = os.path.join(local, "Programs", "Ollama", "ollama.exe")
        if os.path.isfile(candidate):
            return candidate
    return "ollama"


class OfflineVerificationEngine:
    """Verifies local Ollama model availability without network calls."""
    
    def __init__(self):
        """Initialize the verification engine."""
        self._cached_models: Optional[List[str]] = None
        self._cache_timestamp: float = 0.0
        self._cache_ttl: float = 60.0  # Cache for 60 seconds
    
    def _run_ollama_list(self) -> List[str]:
        """Execute `ollama list` and parse output.
        
        Returns:
            List[str]: List of available model names
        """
        ollama_bin = _find_ollama_binary()
        try:
            result = subprocess.run(
                [ollama_bin, "list"],
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
            
            if result.returncode != 0:
                logger.error(f"ollama list failed: {result.stderr}")
                return []
            
            # Parse output (format: "NAME    ID    SIZE    MODIFIED")
            lines = result.stdout.strip().split('\n')
            models = []
            
            for line in lines[1:]:  # Skip header
                if line.strip():
                    parts = line.split()
                    if parts:
                        model_name = parts[0].strip()
                        models.append(model_name)
            
            return models
            
        except subprocess.TimeoutExpired:
            logger.error("ollama list timed out")
            return []
        except Exception as e:
            logger.error(f"Failed to run ollama list: {e}")
            return []
    
    def get_available_models(self, force_refresh: bool = False) -> List[str]:
        """Get list of available local models.
        
        Args:
            force_refresh: Force cache refresh
            
        Returns:
            List[str]: List of available model names
        """
        current_time = time.time()
        
        # Use cache if valid
        if not force_refresh and self._cached_models is not None:
            if (current_time - self._cache_timestamp) < self._cache_ttl:
                return self._cached_models
        
        # Refresh cache
        self._cached_models = self._run_ollama_list()
        self._cache_timestamp = current_time
        
        return self._cached_models if self._cached_models else []
    
    def verify_model_exists(self, model_name: str) -> bool:
        """Verify that a model exists in local Ollama cache.
        
        Args:
            model_name: Name of the model to verify
            
        Returns:
            bool: True if model exists, False otherwise
        """
        available_models = self.get_available_models()
        
        # Check exact match
        if model_name in available_models:
            logger.info(f"Model '{model_name}' found in local cache")
            return True
        
        # Check tag-preserving match (require exact name or name as prefix with same tag)
        for available in available_models:
            available_tag = available.split(':')[-1] if ':' in available else ''
            model_tag = model_name.split(':')[-1] if ':' in model_name else ''
            if model_name == available:
                logger.info(f"Model '{model_name}' found in local cache")
                return True
            if model_tag and available_tag == model_tag and available.startswith(model_name.split(':')[0]):
                logger.info(f"Model '{model_name}' found as '{available}' in local cache")
                return True
        
        logger.warning(f"Model '{model_name}' not found in local cache")
        return False
    
    def require_model(self, model_name: str) -> None:
        """Require a model to exist locally, raise exception if not found.
        
        Args:
            model_name: Name of the model to require
            
        Raises:
            LocalModelNotFoundError: If model is not found locally
        """
        if not self.verify_model_exists(model_name):
            available = self.get_available_models()
            error_msg = (
                f"Required model '{model_name}' not found in local Ollama cache. "
                f"Available models: {', '.join(available) if available else 'None'}. "
                f"Please install with: ollama pull {model_name}"
            )
            logger.critical(error_msg)
            raise LocalModelNotFoundError(error_msg)


# ============================================================================
# VRAM-AWARE MODEL HANDLER
# ============================================================================

class LLMRunner:
    """VRAM-aware LLM runner with Single-Active-Model pattern."""
    
    def __init__(self, ollama_host: str = None, ollama_port: int = None):
        """Initialize the LLM runner.
        
        Args:
            ollama_host: Ollama server host (default from config.settings)
            ollama_port: Ollama server port (default from config.settings)
        """
        self.ollama_host = ollama_host or OLLAMA_HOST
        self.ollama_port = ollama_port or OLLAMA_PORT
        self.verification_engine = OfflineVerificationEngine()
        self.current_model: Optional[str] = None
        self._lock: Optional[asyncio.Lock] = None
        self._lock_init_lock = threading.Lock()
        self._session: Optional[aiohttp.ClientSession] = None
        self.api_base_url = f"http://{self.ollama_host}:{self.ollama_port}"
    
    def _get_running_models(self) -> List[RunningModel]:
        """Get list of currently running models via `ollama ps`."""
        ollama_bin = _find_ollama_binary()
        try:
            result = subprocess.run(
                [ollama_bin, "ps"],
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
            
            if result.returncode != 0:
                logger.error(f"ollama ps failed: {result.stderr}")
                return []
            
            lines = result.stdout.strip().split('\n')
            running_models = []
            
            for line in lines[1:]:
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 4:
                        running_models.append(RunningModel(
                            name=parts[0],
                            size=parts[1],
                            status=parts[3]
                        ))
            
            return running_models
            
        except subprocess.TimeoutExpired:
            logger.error("ollama ps timed out")
            return []
        except Exception as e:
            logger.error(f"Failed to run ollama ps: {e}")
            return []
    
    def _stop_model(self, model_name: str) -> bool:
        """Stop a running model via `ollama stop`."""
        ollama_bin = _find_ollama_binary()
        try:
            logger.info(f"UNLOADING model: {model_name}")
            result = subprocess.run(
                [ollama_bin, "stop", model_name],
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
            
            if result.returncode == 0:
                logger.info(f"Successfully unloaded model: {model_name}")
                return True
            else:
                logger.warning(f"Failed to unload model: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout unloading model: {model_name}")
            return False
        except Exception as e:
            logger.error(f"Error unloading model: {e}")
            return False
    
    def _start_model(self, model_name: str) -> bool:
        """Start a model via `ollama run` (lazy loading)."""
        ollama_bin = _find_ollama_binary()
        try:
            logger.info(f"LOADING model: {model_name}")
            result = subprocess.run(
                [ollama_bin, "run", model_name, "exit"],
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=300,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )

            if result.returncode == 0:
                logger.info(f"Successfully loaded model: {model_name}")
                return True
            else:
                logger.error(f"Failed to load model: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout loading model: {model_name}")
            return False
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            return False
    
    def verify_model_exists(self, model_name: str) -> bool:
        """Verify that a model exists in local Ollama cache.
        
        Args:
            model_name: Name of the model to verify
            
        Returns:
            bool: True if model exists, False otherwise
        """
        return self.verification_engine.verify_model_exists(model_name)
    
    def require_model(self, model_name: str) -> None:
        """Require a model to exist locally.
        
        Args:
            model_name: Name of the model to require
            
        Raises:
            LocalModelNotFoundError: If model is not found locally
        """
        self.verification_engine.require_model(model_name)
    
    async def ensure_model_ready(self, model_name: str) -> bool:
        """Check if model exists locally; auto-pull with retry if missing.

        Args:
            model_name: Name of the model to ensure is available.

        Returns:
            bool: True if model is available (either existed or was pulled).
        """
        if self.verify_model_exists(model_name):
            return True

        logger.warning(f"MODEL '{model_name}' missing locally. Attempting auto-pull...")

        for attempt in range(3):
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ollama", "pull", model_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
                if proc.returncode == 0:
                    logger.info(f"Model '{model_name}' pulled successfully")
                    self.verification_engine.get_available_models(force_refresh=True)
                    return True
                else:
                    logger.error(f"Pull attempt {attempt+1} failed: {stderr.decode().strip()}")
            except asyncio.TimeoutError:
                logger.error(f"Pull attempt {attempt+1} timed out after 600s")
            except Exception as e:
                logger.error(f"Pull attempt {attempt+1} error: {e}")

            if attempt < 2:
                wait = 5 * (attempt + 1)
                logger.info(f"Retrying in {wait}s...")
                await asyncio.sleep(wait)

        logger.error(f"Failed to pull model '{model_name}' after 3 attempts")
        return False

    @staticmethod
    def _check_vram(min_free_mb: int = 1024) -> bool:
        """Check available VRAM via pynvml. Returns True if enough VRAM is free."""
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", FutureWarning)
                import pynvml
                pynvml.nvmlInit()
                try:
                    handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                    info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    free_mb = info.free // (1024 ** 2)
                    logger.debug(f"VRAM: {free_mb}MB free (need {min_free_mb}MB)")
                    return free_mb >= min_free_mb
                finally:
                    pynvml.nvmlShutdown()
        except ImportError:
            logger.debug("pynvml not installed — skipping VRAM check")
            return True
        except Exception as e:
            logger.debug(f"VRAM check failed: {e}")
            return True

    async def ensure_model_loaded(self, model_name: str) -> bool:
        """Ensure a model is loaded in VRAM (Single-Active-Model pattern).
        
        Args:
            model_name: Name of the model to load
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Lazy initialize lock to avoid creating it outside event loop
        if self._lock is None:
            with self._lock_init_lock:
                if self._lock is None:
                    self._lock = asyncio.Lock()
        async with self._lock:
            # Verify model exists locally
            if not self.verify_model_exists(model_name):
                self.require_model(model_name)
                return False
            
            # Check current running models FIRST to avoid unnecessary VRAM wait
            running_models = await asyncio.to_thread(self._get_running_models)
            
            # If the target model is already running, we're done
            for running in running_models:
                if running.name == model_name:
                    logger.info(f"Model '{model_name}' already loaded in VRAM")
                    self.current_model = model_name
                    return True
            
            # VRAM watchdog — wait until enough VRAM is free (only if needed)
            for attempt in range(5):
                if self._check_vram(min_free_mb=1024):
                    break
                logger.warning(f"VRAM low, waiting 10s (attempt {attempt+1}/5)")
                await asyncio.sleep(10)
            else:
                logger.warning("VRAM still low after 5 retries — proceeding anyway")
            
            # If a different model is running, stop it
            if running_models:
                for running in running_models:
                    if running.name != model_name:
                        logger.info(f"Different model '{running.name}' is active, stopping...")
                        if not await asyncio.to_thread(self._stop_model, running.name):
                            logger.warning(f"Failed to stop model '{running.name}'")
            
            # Give Ollama time to actually release VRAM after unload
            await asyncio.sleep(3)
            for attempt in range(3):
                if self._check_vram(min_free_mb=1024):
                    break
                logger.warning(f"VRAM still low after unload, waiting 5s (attempt {attempt+1}/3)")
                await asyncio.sleep(5)
            
            # Start the target model
            if not await asyncio.to_thread(self._start_model, model_name):
                logger.error(f"Failed to load model '{model_name}'")
                return False
            
            # Wait for model to fully initialize in VRAM via active polling
            logger.info(f"Waiting for model '{model_name}' to initialize in VRAM...")
            max_attempts = 15
            for attempt in range(max_attempts):
                running_models = await asyncio.to_thread(self._get_running_models)
                for running in running_models:
                    if running.name == model_name:
                        logger.info(f"READY for inference: {model_name} (loaded in ~{attempt*2}s)")
                        self.current_model = model_name
                        return True
                await asyncio.sleep(2)
            
            logger.error(f"Model '{model_name}' failed to initialize in VRAM after {max_attempts*2}s")
            return False
    
    @retry_with_exponential_backoff(max_retries=3, initial_delay=1.0)
    async def query_llm(
        self,
        model_name: str,
        prompt: str,
        timeout: int = None,
        temperature: float = None,
        max_tokens: int = None
    ) -> str:
        """Query the LLM via Ollama HTTP API with retry logic.
        
        Args:
            model_name: Name of the model to use
            prompt: Prompt to send to the model
            timeout: Request timeout in seconds
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            
        Returns:
            str: Generated response
            
        Raises:
            LLMQueryError: If query fails
            ModelTimeoutError: If query times out
        """
        # Ensure model is loaded
        if not await self.ensure_model_loaded(model_name):
            raise ModelLoadError(f"Failed to load model '{model_name}'")
        
        timeout = timeout or LLM_TIMEOUT
        temperature = temperature or LLM_TEMPERATURE
        max_tokens = max_tokens or LLM_MAX_TOKENS
        
        url = f"{self.api_base_url}/api/generate"
        
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }
        
        logger.info(f"Sending query to model '{model_name}'")
        
        try:
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout))

            async with self._session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=timeout)) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise LLMQueryError(f"API returned status {response.status}: {error_text}")
                
                result = await response.json()
                
                if "response" in result:
                    logger.info(f"Query completed successfully")
                    return result["response"]
                else:
                    raise LLMQueryError("No response in API result")
                        
        except asyncio.TimeoutError:
            logger.error(f"Query timed out after {timeout} seconds")
            raise ModelTimeoutError(f"Query timed out after {timeout} seconds")
        except aiohttp.ClientError as e:
            logger.error(f"HTTP client error: {e}")
            raise LLMQueryError(f"HTTP client error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during query: {e}")
            raise LLMQueryError(f"Unexpected error: {e}")
    
    def query_llm_sync(
        self,
        model_name: str,
        prompt: str,
        timeout: int = 30,
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> Optional[str]:
        """Synchronous wrapper for query_llm (for non-async contexts).
        
        Args:
            model_name: Name of the model to use
            prompt: Prompt to send to the model
            timeout: Request timeout in seconds
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            
        Returns:
            str: Generated response
        """
        try:
            loop = asyncio.get_running_loop()
            if threading.current_thread() is threading.main_thread():
                return asyncio.run(self.query_llm(
                    model_name=model_name, prompt=prompt,
                    timeout=timeout, temperature=temperature,
                    max_tokens=max_tokens
                ))
            future = asyncio.run_coroutine_threadsafe(
                self.query_llm(model_name=model_name, prompt=prompt,
                               timeout=timeout, temperature=temperature,
                               max_tokens=max_tokens),
                loop
            )
            return future.result(timeout=timeout)
        except RuntimeError:
            return asyncio.run(self.query_llm(
                model_name=model_name, prompt=prompt,
                timeout=timeout, temperature=temperature,
                max_tokens=max_tokens
            ))
    
    async def cleanup(self) -> None:
        """Cleanup - stop current model if running and close HTTP session."""
        if self.current_model:
            logger.info(f"Cleanup: Unloading model '{self.current_model}'")
            await asyncio.to_thread(self._stop_model, self.current_model)
            self.current_model = None
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            logger.info("HTTP session closed")
        logger.info("LLMRunner cleanup completed")


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def get_llm_runner(ollama_host: str = None, ollama_port: int = None) -> LLMRunner:
    """Factory function to get LLMRunner instance.
    
    Args:
        ollama_host: Ollama server host (default from config.settings)
        ollama_port: Ollama server port (default from config.settings)
        
    Returns:
        LLMRunner: Configured LLM runner instance
    """
    return LLMRunner(ollama_host=ollama_host, ollama_port=ollama_port)


# ============================================================================
# MAIN ENTRY POINT (FOR TESTING)
# ============================================================================

async def main():
    """Main entry point for testing."""
    runner = get_llm_runner()
    
    try:
        # Test model verification
        model_name = "qwen2.5:3b"
        
        if runner.verify_model_exists(model_name):
            print(f"Model '{model_name}' is available locally")
            
            # Test query
            response = await runner.query_llm(
                model_name=model_name,
                prompt="What is 2+2?",
                timeout=30
            )
            print(f"Response: {response}")
        else:
            print(f"Model '{model_name}' is not available locally")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
