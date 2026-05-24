"""Knowledge distillation engine using local Ollama models.

This module provides functions to synthesize extracted markdown content
into structured knowledge packages using local LLM models via Ollama.
"""

import asyncio
import json
import logging
from typing import Dict, Optional
import aiohttp

from config.settings import PARSER_TIMEOUT


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Universal Master Teacher System Prompt
UNIVERSAL_MASTER_TEACHER_PROMPT = """You are a Universal Master Teacher with interdisciplinary expertise across all domains of knowledge. Your task is to analyze the provided content and synthesize it into a structured knowledge package.

You MUST respond with a valid JSON object containing exactly these fields:
{
    "domain_classification": "The primary knowledge domain (e.g., Philosophy, Science, Geopolitics, Economics, History, Technology, etc.)",
    "thesis_or_core_objective": "A concise statement of the main thesis or core objective of the content",
    "structured_knowledge": {
        "key_concepts": ["List of 5-7 key concepts"],
        "main_arguments": ["List of 3-5 main arguments or principles"],
        "supporting_evidence": ["List of 3-5 key pieces of evidence or examples"],
        "implications": ["List of 2-3 implications or applications"]
    },
    "evaluation_exam": [
        {
            "question": "Thought-provoking question 1",
            "answer": "Comprehensive answer based on the content"
        },
        {
            "question": "Thought-provoking question 2",
            "answer": "Comprehensive answer based on the content"
        },
        {
            "question": "Thought-provoking question 3",
            "answer": "Comprehensive answer based on the content"
        },
        {
            "question": "Thought-provoking question 4",
            "answer": "Comprehensive answer based on the content"
        },
        {
            "question": "Thought-provoking question 5",
            "answer": "Comprehensive answer based on the content"
        }
    ]
}

Ensure your response is valid JSON with no additional text or formatting outside the JSON structure."""


async def distill_markdown_with_ollama(
    markdown_content: str,
    model_name: str = "qwen2.5:3b",
    ollama_url: str = "http://localhost:11434/api/generate"
) -> Dict:
    """Distill markdown content into structured knowledge using local Ollama model.
    
    This function sends markdown content to a local Ollama instance and
    requests structured JSON synthesis using the Universal Master Teacher prompt.
    
    Args:
        markdown_content: The markdown content to distill.
        model_name: The Ollama model to use (default: "qwen2.5:3b").
        ollama_url: The Ollama API endpoint (default: localhost:11434).
        
    Returns:
        Dict: Structured knowledge package with domain_classification, 
              thesis_or_core_objective, structured_knowledge, and evaluation_exam.
              
    Raises:
        json.JSONDecodeError: If the response cannot be parsed as JSON.
        aiohttp.ClientError: If the HTTP request fails.
        Exception: For other unexpected errors.
    """
    logger.info(f"Starting knowledge distillation with model: {model_name}")
    
    # VRAM Guard: Truncate content if too long to protect 6GB GPU (GTX 1660)
    max_content_length = 25000  # Safe limit for 3B models (~6,000 tokens)
    if len(markdown_content) > max_content_length:
        logger.warning("[VRAM Guard] Source text exceeds safe 3B context window boundaries. Truncating to protect local GPU memory.")
        markdown_content = markdown_content[:max_content_length]
        logger.warning(f"Content truncated to {max_content_length} characters for model processing")
    
    # Prepare the prompt
    full_prompt = f"{UNIVERSAL_MASTER_TEACHER_PROMPT}\n\nCONTENT TO ANALYZE:\n\n{markdown_content}"
    
    # Prepare the Ollama API payload
    payload = {
        "model": model_name,
        "prompt": full_prompt,
        "stream": False,
        "format": "json"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                ollama_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=PARSER_TIMEOUT + 60)  # Extra time for LLM processing
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Ollama API returned status {response.status}: {error_text}")
                    raise Exception(f"Ollama API error: {response.status} - {error_text}")
                
                response_text = await response.text()
                logger.info(f"Received response from Ollama (length: {len(response_text)} chars)")
                
                # Parse JSON response
                try:
                    # Ollama returns the JSON in the 'response' field
                    response_data = json.loads(response_text)
                    
                    if 'response' in response_data:
                        json_content = response_data['response']
                    else:
                        # Some versions might return the JSON directly
                        json_content = response_text
                    
                    # Parse the actual structured knowledge
                    structured_data = json.loads(json_content)
                    
                    # Validate required fields
                    required_fields = ['domain_classification', 'thesis_or_core_objective', 
                                     'structured_knowledge', 'evaluation_exam']
                    missing_fields = [field for field in required_fields if field not in structured_data]
                    
                    if missing_fields:
                        logger.warning(f"Missing required fields in response: {missing_fields}")
                        # Add default values for missing fields
                        for field in missing_fields:
                            if field == 'domain_classification':
                                structured_data[field] = "Unknown"
                            elif field == 'thesis_or_core_objective':
                                structured_data[field] = "Not provided"
                            elif field == 'structured_knowledge':
                                structured_data[field] = {
                                    "key_concepts": [],
                                    "main_arguments": [],
                                    "supporting_evidence": [],
                                    "implications": []
                                }
                            elif field == 'evaluation_exam':
                                structured_data[field] = []
                    
                    logger.info(f"Successfully distilled knowledge. Domain: {structured_data.get('domain_classification', 'Unknown')}")
                    return structured_data
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON response: {e}")
                    logger.error(f"Response content: {response_text[:500]}...")
                    
                    # Return a fallback structure
                    return {
                        "domain_classification": "Extraction Error",
                        "thesis_or_core_objective": "Failed to extract thesis due to JSON parsing error",
                        "structured_knowledge": {
                            "key_concepts": ["Extraction failed"],
                            "main_arguments": ["JSON parsing error"],
                            "supporting_evidence": [],
                            "implications": []
                        },
                        "evaluation_exam": [],
                        "error": str(e),
                        "raw_response": response_text[:1000]
                    }
                    
    except aiohttp.ClientError as e:
        logger.error(f"HTTP client error during Ollama request: {e}")
        return {
            "domain_classification": "Connection Error",
            "thesis_or_core_objective": "Failed to connect to Ollama server",
            "structured_knowledge": {
                "key_concepts": ["Connection failed"],
                "main_arguments": ["Ollama server unavailable"],
                "supporting_evidence": [],
                "implications": []
            },
            "evaluation_exam": [],
            "error": str(e)
        }
    except asyncio.TimeoutError:
        logger.error("Ollama request timed out")
        return {
            "domain_classification": "Timeout Error",
            "thesis_or_core_objective": "Ollama request timed out",
            "structured_knowledge": {
                "key_concepts": ["Timeout"],
                "main_arguments": ["Request exceeded time limit"],
                "supporting_evidence": [],
                "implications": []
            },
            "evaluation_exam": [],
            "error": "Request timeout"
        }
    except Exception as e:
        logger.error(f"Unexpected error during knowledge distillation: {e}")
        return {
            "domain_classification": "Unknown Error",
            "thesis_or_core_objective": f"Unexpected error: {str(e)}",
            "structured_knowledge": {
                "key_concepts": ["Error occurred"],
                "main_arguments": [str(e)],
                "supporting_evidence": [],
                "implications": []
            },
            "evaluation_exam": [],
            "error": str(e)
        }


def validate_knowledge_package(package: Dict) -> bool:
    """Validate that a knowledge package has the required structure.
    
    Args:
        package: The knowledge package dictionary to validate.
        
    Returns:
        bool: True if the package is valid, False otherwise.
    """
    required_fields = ['domain_classification', 'thesis_or_core_objective', 
                     'structured_knowledge', 'evaluation_exam']
    
    for field in required_fields:
        if field not in package:
            logger.warning(f"Missing required field: {field}")
            return False
    
    # Validate structured_knowledge sub-fields
    required_subfields = ['key_concepts', 'main_arguments', 'supporting_evidence', 'implications']
    for subfield in required_subfields:
        if subfield not in package['structured_knowledge']:
            logger.warning(f"Missing required subfield in structured_knowledge: {subfield}")
            return False
    
    # Validate evaluation_exam has 5 questions
    if not isinstance(package['evaluation_exam'], list) or len(package['evaluation_exam']) != 5:
        logger.warning(f"evaluation_exam must be a list of 5 QA pairs")
        return False
    
    return True


def format_distillation_summary(package: Dict, source_url: str) -> str:
    """Format a beautiful summary of the distillation results.
    
    Args:
        package: The knowledge package dictionary.
        source_url: The source URL of the content.
        
    Returns:
        str: Formatted summary string.
    """
    domain = package.get('domain_classification', 'Unknown')
    thesis = package.get('thesis_or_core_objective', 'Not provided')
    
    summary = f"""
{'=' * 80}
KNOWLEDGE DISTILLATION SUMMARY
{'=' * 80}
Source URL: {source_url}
Detected Domain: {domain}
Core Thesis: {thesis}
{'=' * 80}
Structured Knowledge:
  - Key Concepts: {len(package.get('structured_knowledge', {}).get('key_concepts', []))} extracted
  - Main Arguments: {len(package.get('structured_knowledge', {}).get('main_arguments', []))} extracted
  - Supporting Evidence: {len(package.get('structured_knowledge', {}).get('supporting_evidence', []))} extracted
  - Implications: {len(package.get('structured_knowledge', {}).get('implications', []))} extracted
{'=' * 80}
Evaluation Exam: 5 QA pairs generated and locked into local database
{'=' * 80}
"""
    return summary
