"""Expert performance evaluation engine.

This module provides functions to evaluate expert performance using
generated exam datasets from knowledge packages and local Ollama models.
"""

import asyncio
import json
import logging
from typing import Dict, Optional
import aiohttp

from database.queries import get_expert_by_id, get_knowledge_package_by_id
from config.settings import PARSER_TIMEOUT


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Grader system prompt for scoring expert answers
GRADER_SYSTEM_PROMPT = """You are an impartial and precise grader. Your task is to evaluate the accuracy and precision of an answer compared to an expected answer.

Rate the answer on a scale from 0.0 to 1.0 based on:
- 0.0: Completely incorrect or irrelevant
- 0.3: Partially correct but missing key information
- 0.5: Mostly correct with minor errors
- 0.7: Correct with good precision
- 1.0: Perfectly accurate and precise

Output ONLY a single number (float) between 0.0 and 1.0. Do not include any explanation or additional text."""


async def prompt_ollama(
    prompt: str,
    system_prompt: str,
    model_name: str = "qwen2.5:3b",
    ollama_url: str = "http://localhost:11434/api/generate"
) -> str:
    """Send a prompt to Ollama and return the response.
    
    Args:
        prompt: The user prompt to send.
        system_prompt: The system prompt to use.
        model_name: The Ollama model name.
        ollama_url: The Ollama API endpoint URL.
        
    Returns:
        str: The response from Ollama.
        
    Raises:
        Exception: If the request fails or times out.
    """
    payload = {
        "model": model_name,
        "prompt": prompt,
        "system": system_prompt,
        "stream": False
    }
    
    timeout = aiohttp.ClientTimeout(total=PARSER_TIMEOUT + 120)
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(ollama_url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Ollama API error {response.status}: {error_text}")
                
                result = await response.json()
                return result.get("response", "").strip()
                
    except asyncio.TimeoutError:
        raise Exception(f"Ollama request timed out after {timeout.total} seconds")
    except aiohttp.ClientError as e:
        raise Exception(f"Ollama connection error: {e}")


async def evaluate_expert_performance(
    expert_id: int,
    package_id: int,
    model_name: str = "qwen2.5:3b"
) -> float:
    """Evaluate expert performance using exam dataset from a knowledge package.
    
    This function retrieves the expert's system prompt and the exam dataset
    (5 QA pairs) from the target knowledge package. For each question, it prompts
    Ollama as the target expert to provide an answer, then acts as an independent
    grader to score the expert's answer against the expected answer.
    
    Args:
        expert_id: The ID of the expert to evaluate.
        package_id: The ID of the knowledge package containing the exam dataset.
        model_name: The Ollama model name to use (default: "qwen2.5:3b").
        
    Returns:
        float: The average score of the 5 questions (0.0 to 1.0).
        
    Raises:
        ValueError: If expert or package not found.
        Exception: If evaluation fails.
    """
    logger.info("=" * 80)
    logger.info("EXPERT PERFORMANCE EVALUATION")
    logger.info("=" * 80)
    logger.info(f"Expert ID: {expert_id}")
    logger.info(f"Package ID: {package_id}")
    logger.info(f"Model: {model_name}")
    logger.info("=" * 80 + "\n")
    
    # Retrieve expert data
    logger.info("Retrieving expert data...")
    expert = get_expert_by_id(expert_id)
    
    if not expert:
        raise ValueError(f"Expert with ID {expert_id} not found")
    
    expert_name = expert['name']
    expert_system_prompt = expert.get('system_prompt', 'You are a helpful expert assistant.')
    logger.info(f"Expert: {expert_name}")
    logger.info(f"System Prompt: {expert_system_prompt[:100]}...\n")
    
    # Retrieve knowledge package data
    logger.info("Retrieving knowledge package data...")
    package = get_knowledge_package_by_id(package_id)
    
    if not package:
        raise ValueError(f"Knowledge package with ID {package_id} not found")
    
    exam_dataset = package.get('exam_dataset', [])
    
    if not exam_dataset or len(exam_dataset) < 5:
        logger.warning(f"Exam dataset has {len(exam_dataset)} questions (expected 5)")
    
    logger.info(f"Exam Dataset: {len(exam_dataset)} questions\n")
    
    # Evaluate each question
    scores = []
    
    for idx, qa_pair in enumerate(exam_dataset, 1):
        question = qa_pair.get('question', '')
        expected_answer = qa_pair.get('answer', '')
        
        if not question or not expected_answer:
            logger.warning(f"Skipping question {idx}: missing question or answer")
            continue
        
        logger.info(f"[Question {idx}/{len(exam_dataset)}] {question[:80]}...")
        
        try:
            # Step 1: Prompt expert to answer
            logger.info(f"  [Step 1] Prompting expert '{expert_name}' to answer...")
            expert_answer = await prompt_ollama(
                prompt=f"Question: {question}\n\nPlease provide a clear and accurate answer.",
                system_prompt=expert_system_prompt,
                model_name=model_name
            )
            logger.info(f"  [Step 1] Expert answer: {expert_answer[:100]}...")
            
            # Step 2: Grade the answer
            logger.info(f"  [Step 2] Grading expert answer against expected answer...")
            grader_prompt = f"""Expert Answer: {expert_answer}

Expected Answer: {expected_answer}

Rate the expert answer's accuracy and precision compared to the expected answer."""
            
            score_str = await prompt_ollama(
                prompt=grader_prompt,
                system_prompt=GRADER_SYSTEM_PROMPT,
                model_name=model_name
            )
            
            # Parse score
            try:
                score = float(score_str.strip())
                score = max(0.0, min(1.0, score))  # Clamp to [0.0, 1.0]
            except ValueError:
                logger.warning(f"  [Step 2] Failed to parse score: {score_str}, defaulting to 0.5")
                score = 0.5
            
            scores.append(score)
            logger.info(f"  [Step 2] Score: {score:.2f}\n")
            
        except Exception as e:
            logger.error(f"  [Error] Failed to evaluate question {idx}: {e}")
            logger.info(f"  [Error] Defaulting to score 0.0 for this question\n")
            scores.append(0.0)
    
    # Calculate average score
    if not scores:
        logger.warning("No valid scores calculated, returning 0.0")
        return 0.0
    
    average_score = sum(scores) / len(scores)
    
    logger.info("=" * 80)
    logger.info("EVALUATION SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Expert: {expert_name}")
    logger.info(f"Questions Evaluated: {len(scores)}/{len(exam_dataset)}")
    logger.info(f"Individual Scores: {[f'{s:.2f}' for s in scores]}")
    logger.info(f"Average Score: {average_score:.2f}")
    logger.info("=" * 80 + "\n")
    
    return average_score
