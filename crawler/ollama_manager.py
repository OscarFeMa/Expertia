"""Ollama service and model management module.

This module provides functions to verify Ollama service availability,
check for model existence, and automatically download missing models.
"""

import asyncio
import json
import logging
from typing import Optional
import aiohttp

from config.settings import PARSER_TIMEOUT


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def ensure_ollama_model_exists(
    model_name: str = "qwen2.5:3b",
    ollama_url: str = "http://localhost:11434"
) -> bool:
    """Ensure Ollama service is running and the specified model exists locally.
    
    This function performs three steps:
    1. Ping the Ollama API to verify the service is running
    2. Check if the specified model exists in the local library
    3. If missing, automatically pull the model from Ollama registry
    
    Args:
        model_name: The name of the Ollama model to ensure exists (default: "qwen2.5:3b").
        ollama_url: The base URL of the Ollama service (default: "http://localhost:11434").
        
    Returns:
        bool: True if the model exists or was successfully downloaded, False otherwise.
        
    Raises:
        Exception: If Ollama service is not running or model download fails.
    """
    logger.info("=" * 80)
    logger.info("OLLAMA GUARD - MODEL VERIFICATION")
    logger.info("=" * 80)
    logger.info(f"Target Model: {model_name}")
    logger.info(f"Ollama URL: {ollama_url}")
    logger.info("=" * 80 + "\n")
    
    # Step 1: Ping Ollama API to verify service is running
    logger.info("[Step 1] Verifying Ollama service availability...")
    tags_url = f"{ollama_url}/api/tags"
    
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(tags_url) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Ollama API returned status {response.status}: {error_text}")
                
                tags_data = await response.json()
                logger.info("[Step 1] Ollama service is running and responsive.\n")
                
    except aiohttp.ClientConnectorError as e:
        logger.error("[Ollama Guard] Ollama service is not running. Please open Ollama on Windows before running the script.")
        logger.error(f"Connection error: {e}")
        raise Exception("[Ollama Guard] Ollama service is not running. Please open Ollama on Windows before running the script.")
    except asyncio.TimeoutError:
        logger.error("[Ollama Guard] Ollama service timeout. Please ensure Ollama is running.")
        raise Exception("[Ollama Guard] Ollama service timeout. Please ensure Ollama is running.")
    except Exception as e:
        logger.error(f"[Ollama Guard] Error connecting to Ollama service: {e}")
        raise
    
    # Step 2: Check if model exists in local library
    logger.info(f"[Step 2] Checking if model '{model_name}' exists locally...")
    
    models = tags_data.get("models", [])
    model_exists = False
    
    for model in models:
        model_full_name = model.get("name", "")
        if model_name in model_full_name:
            model_exists = True
            logger.info(f"[Step 2] Model '{model_name}' found locally: {model_full_name}\n")
            break
    
    if model_exists:
        logger.info("=" * 80)
        logger.info("OLLAMA GUARD - VERIFICATION COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Model '{model_name}' is available and ready for use.")
        logger.info("=" * 80 + "\n")
        return True
    
    # Step 3: Auto-pull the model if missing
    logger.info(f"[Step 3] Model '{model_name}' not found locally. Initiating automated background download...")
    
    pull_url = f"{ollama_url}/api/pull"
    payload = {"name": model_name, "stream": False}
    
    try:
        # Use a longer timeout for model pulling (can take several minutes)
        pull_timeout = aiohttp.ClientTimeout(total=600)  # 10 minutes
        async with aiohttp.ClientSession(timeout=pull_timeout) as session:
            logger.info(f"[Ollama Guard] Downloading model '{model_name}' from Ollama registry...")
            logger.info("[Ollama Guard] This may take several minutes depending on your internet connection and model size.\n")
            
            async with session.post(pull_url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"[Ollama Guard] Failed to pull model: {error_text}")
                    raise Exception(f"Failed to pull model '{model_name}': {error_text}")
                
                result = await response.json()
                logger.info(f"[Ollama Guard] Model download completed successfully.")
                logger.info(f"[Ollama Guard] Response: {result.get('status', 'completed')}\n")
                
    except asyncio.TimeoutError:
        logger.error(f"[Ollama Guard] Model download timed out after 10 minutes.")
        raise Exception(f"Model download for '{model_name}' timed out. Please check your internet connection and try again.")
    except Exception as e:
        logger.error(f"[Ollama Guard] Error during model download: {e}")
        raise
    
    logger.info("=" * 80)
    logger.info("OLLAMA GUARD - VERIFICATION COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Model '{model_name}' has been successfully downloaded and is ready for use.")
    logger.info("=" * 80 + "\n")
    
    return True


async def get_ollama_models(ollama_url: str = "http://localhost:11434") -> list:
    """Get list of all available models in the local Ollama library.
    
    Args:
        ollama_url: The base URL of the Ollama service.
        
    Returns:
        list: List of model names available locally.
        
    Raises:
        Exception: If Ollama service is not running or request fails.
    """
    tags_url = f"{ollama_url}/api/tags"
    
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(tags_url) as response:
                if response.status != 200:
                    raise Exception(f"Ollama API returned status {response.status}")
                
                tags_data = await response.json()
                models = tags_data.get("models", [])
                model_names = [model.get("name", "") for model in models]
                
                return model_names
                
    except Exception as e:
        logger.error(f"Failed to get Ollama models: {e}")
        raise


async def check_ollama_service(ollama_url: str = "http://localhost:11434") -> bool:
    """Quick check if Ollama service is running and accessible.
    
    Args:
        ollama_url: The base URL of the Ollama service.
        
    Returns:
        bool: True if service is running, False otherwise.
    """
    tags_url = f"{ollama_url}/api/tags"
    
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(tags_url) as response:
                return response.status == 200
    except Exception:
        return False
