"""Expert registry audits and updates.

This module provides functions to manage the expert registry and knowledge packages,
including keyword matching, suitability scoring, CLI formatting, and knowledge package storage.
"""

import sqlite3
import logging
import json
from typing import List, Dict, Optional, Tuple
import re

from database.connection import get_connection, initialize_database
from config.settings import SUITABILITY_THRESHOLD


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def add_expert(
    name: str,
    core_domain: str,
    tags: str,
    ema_score: float = 0.0,
    system_prompt: Optional[str] = None,
    tier: int = 3,
    parent_expert_id: Optional[int] = None
) -> int:
    """Add a new expert to the registry.

    Args:
        name: Expert name.
        core_domain: Core domain of expertise.
        tags: Comma-separated tags/keywords.
        ema_score: EMA score (default 0.0).
        system_prompt: Optional system prompt.
        tier: Expert tier (default 3).
        parent_expert_id: Optional parent expert ID for germinated specialists.

    Returns:
        int: The ID of the inserted expert.

    Raises:
        sqlite3.Error: If insertion fails.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO expert_registry (name, core_domain, tags, ema_score, system_prompt, tier, parent_expert_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, core_domain, tags, ema_score, system_prompt, tier, parent_expert_id))
        conn.commit()
        expert_id = cursor.lastrowid
        logger.info(f"Expert added: {name} (ID: {expert_id}, Tier: {tier})")
        return expert_id
    except sqlite3.Error as e:
        logger.error(f"Failed to add expert: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def get_all_experts() -> List[Dict]:
    """Retrieve all experts from the registry.
    
    Returns:
        List[Dict]: List of expert records as dictionaries.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM expert_registry ORDER BY ema_score DESC")
        rows = cursor.fetchall()
        experts = [dict(row) for row in rows]
        logger.info(f"Retrieved {len(experts)} experts from registry")
        return experts
    except sqlite3.Error as e:
        logger.error(f"Failed to retrieve experts: {e}")
        raise
    finally:
        conn.close()


def compute_suitability_score(research_topic: str, expert_tags: str, ema_score: float) -> float:
    """Compute suitability score based on keyword intersection (Jaccard-like) and EMA score.
    
    This function implements the definitive project formula:
    Suitability_Score = (Intersection_Ratio * 0.7) + (expert['ema_score'] * 0.3)
    
    Args:
        research_topic: The research topic string.
        expert_tags: Comma-separated tags from the expert.
        ema_score: The expert's EMA score (0.0 to 1.0).
        
    Returns:
        float: Suitability score from 0.0 to 1.0.
    """
    # Common stop words to remove (English)
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
        'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
        'would', 'could', 'should', 'may', 'might', 'must', 'shall', 'can',
        'this', 'that', 'these', 'those', 'it', 'its', 'they', 'them', 'their',
        'what', 'which', 'who', 'whom', 'when', 'where', 'why', 'how'
    }
    
    # Normalize and tokenize the research topic
    topic_words = set(re.findall(r'\b\w+\b', research_topic.lower()))
    # Remove stop words
    topic_words = topic_words - stop_words
    
    # Normalize and tokenize the expert tags (split by comma, then tokenize)
    tag_words = set()
    for tag in expert_tags.split(','):
        tag = tag.strip().lower()
        tag_words.update(re.findall(r'\b\w+\b', tag))
    # Remove stop words from tags as well
    tag_words = tag_words - stop_words
    
    if not topic_words or not tag_words:
        return 0.0
    
    # Calculate keyword intersection ratio (Jaccard-like)
    intersection = topic_words & tag_words
    intersection_ratio = len(intersection) / len(topic_words) if topic_words else 0.0
    
    # Apply the definitive project formula
    # Suitability_Score = (Intersection_Ratio * 0.7) + (ema_score * 0.3)
    suitability_score = (intersection_ratio * 0.7) + (ema_score * 0.3)
    
    # Clamp to [0.0, 1.0]
    return max(0.0, min(1.0, suitability_score))


def find_best_expert(research_topic: str) -> Tuple[Optional[Dict], float]:
    """Find the best expert for a given research topic using Jaccard + EMA formula.
    
    This function fetches all experts from the expert_registry, tokenizes the input
    topic string into clean lowercase keywords (removing common stop words), and
    calculates the suitability score for each expert using the definitive formula:
    Suitability_Score = (Intersection_Ratio * 0.7) + (expert['ema_score'] * 0.3)
    
    Args:
        research_topic: The research topic string.
        
    Returns:
        Tuple[Optional[Dict], float]: The best expert (or None) and their suitability score.
    """
    experts = get_all_experts()
    
    if not experts:
        logger.info("No experts found in registry")
        return None, 0.0
    
    best_expert = None
    best_score = 0.0
    
    for expert in experts:
        score = compute_suitability_score(
            research_topic,
            expert['tags'],
            expert['ema_score']
        )
        if score > best_score:
            best_score = score
            best_expert = expert
    
    if best_expert:
        logger.info(f"Best expert found: {best_expert['name']} with suitability score {best_score:.2f}")
    else:
        logger.info("No suitable expert found")
    
    return best_expert, best_score


def format_registry_matrix(experts: List[Dict]) -> str:
    """Format the expert registry as a beautiful ASCII matrix.
    
    Args:
        experts: List of expert records.
        
    Returns:
        str: Formatted ASCII matrix string.
    """
    if not experts:
        return """
+----------------------+----------------------+----------------------+----------------------+
| Detected Expert      | Core Domain / Tags   | Suitability Score    | Suggested Action     |
+----------------------+----------------------+----------------------+----------------------+
| NO EXPERTS FOUND     | -                    | -                    | Initialize Registry  |
+----------------------+----------------------+----------------------+----------------------+
"""
    
    # Calculate column widths
    name_width = max(20, max(len(str(e['name'])) for e in experts))
    domain_width = max(20, max(len(f"{e['core_domain']} / {e['tags']}") for e in experts))
    score_width = 20
    action_width = 20
    
    # Header
    header = f"+{'-' * (name_width + 2)}+{'-' * (domain_width + 2)}+{'-' * (score_width + 2)}+{'-' * (action_width + 2)}+"
    header_row = f"| {'Detected Expert':<{name_width}} | {'Core Domain / Tags':<{domain_width}} | {'Suitability Score':<{score_width}} | {'Suggested Action':<{action_width}} |"
    
    # Rows
    rows = []
    for expert in experts:
        name = str(expert['name'])[:name_width]
        domain_tags = f"{expert['core_domain']} / {expert['tags']}"[:domain_width]
        score = f"{expert['ema_score']:.2f}"[:score_width]
        action = "USE EXPERT" if expert['ema_score'] > SUITABILITY_THRESHOLD else "CONSIDER ALTERNATIVE"
        action = action[:action_width]
        
        row = f"| {name:<{name_width}} | {domain_tags:<{domain_width}} | {score:<{score_width}} | {action:<{action_width}} |"
        rows.append(row)
    
    # Combine
    matrix = header + "\n" + header_row + "\n" + header + "\n"
    matrix += "\n".join(rows) + "\n" + header
    
    return matrix


def audit_registry(research_topic: str) -> Tuple[bool, Optional[Dict], float]:
    """Audit the registry for a given research topic.
    
    Args:
        research_topic: The research topic to audit against.
        
    Returns:
        Tuple[bool, Optional[Dict], float]: 
            - Whether to halt execution (True if suitable expert found)
            - The best expert (or None)
            - The suitability score
    """
    # Ensure database is initialized
    initialize_database()
    
    # Get all experts
    experts = get_all_experts()
    
    # Display inventory report
    matrix = format_registry_matrix(experts)
    print("\n" + "=" * 80)
    print("LOCAL EXPERT REGISTRY AUDIT")
    print("=" * 80)
    print(matrix)
    print("=" * 80 + "\n")
    
    # Find best expert
    best_expert, score = find_best_expert(research_topic)
    
    # Determine if we should halt
    should_halt = score > SUITABILITY_THRESHOLD
    
    if should_halt and best_expert:
        logger.info(f"[Registry Check] Optimal expert detected: {best_expert['name']} (Score: {score:.2f})")
        print(f"[Registry Check] Optimal expert detected: {best_expert['name']} (Score: {score:.2f})")
        print("[Registry Check] Aborting web ingestion.\n")
    else:
        logger.info(f"[Registry Check] No suitable expert found (Best score: {score:.2f})")
        print(f"[Registry Check] No suitable expert found (Best score: {score:.2f})")
        print("[Registry Check] Proceeding with web ingestion.\n")
    
    return should_halt, best_expert, score


def update_expert_score(expert_id: int, new_ema_score: float) -> None:
    """Update the EMA score for an expert.
    
    Args:
        expert_id: The ID of the expert to update.
        new_ema_score: The new EMA score.
        
    Raises:
        sqlite3.Error: If update fails.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE expert_registry 
            SET ema_score = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_ema_score, expert_id))
        conn.commit()
        logger.info(f"Expert ID {expert_id} EMA score updated to {new_ema_score}")
    except sqlite3.Error as e:
        logger.error(f"Failed to update expert score: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def add_knowledge_package(
    topic: str,
    source_url: str,
    domain: str,
    structured_knowledge: Dict,
    exam_dataset: Dict
) -> int:
    """Add a new knowledge package to the database.
    
    Args:
        topic: The research topic.
        source_url: The source URL of the content.
        domain: The knowledge domain (e.g., Philosophy, Science, Geopolitics).
        structured_knowledge: Dictionary containing the core synthesis.
        exam_dataset: Dictionary containing 5 evaluation QA pairs.
        
    Returns:
        int: The ID of the inserted knowledge package.
        
    Raises:
        sqlite3.Error: If insertion fails.
        json.JSONEncodeError: If JSON serialization fails.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # Serialize dictionaries to JSON strings
        structured_knowledge_json = json.dumps(structured_knowledge, ensure_ascii=False)
        exam_dataset_json = json.dumps(exam_dataset, ensure_ascii=False)
        
        cursor.execute("""
            INSERT INTO knowledge_packages (topic, source_url, domain, structured_knowledge, exam_dataset)
            VALUES (?, ?, ?, ?, ?)
        """, (topic, source_url, domain, structured_knowledge_json, exam_dataset_json))
        
        conn.commit()
        package_id = cursor.lastrowid
        logger.info(f"Knowledge package added: {topic} (ID: {package_id}, Domain: {domain})")
        return package_id
    except (sqlite3.Error, json.JSONEncodeError) as e:
        logger.error(f"Failed to add knowledge package: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def get_knowledge_packages_by_topic(topic: str) -> List[Dict]:
    """Retrieve all knowledge packages for a given topic.
    
    Args:
        topic: The research topic to search for.
        
    Returns:
        List[Dict]: List of knowledge package records as dictionaries.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM knowledge_packages 
            WHERE topic LIKE ? 
            ORDER BY created_at DESC
        """, (f"%{topic}%",))
        rows = cursor.fetchall()
        
        packages = []
        for row in rows:
            package = dict(row)
            # Deserialize JSON fields
            try:
                package['structured_knowledge'] = json.loads(package['structured_knowledge'])
                package['exam_dataset'] = json.loads(package['exam_dataset'])
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Failed to deserialize JSON for package ID {package['id']}")
            
            packages.append(package)
        
        logger.info(f"Retrieved {len(packages)} knowledge packages for topic: {topic}")
        return packages
    except sqlite3.Error as e:
        logger.error(f"Failed to retrieve knowledge packages: {e}")
        raise
    finally:
        conn.close()


def get_knowledge_packages_by_domain(domain: str) -> List[Dict]:
    """Retrieve all knowledge packages for a given domain.
    
    Args:
        domain: The knowledge domain to search for.
        
    Returns:
        List[Dict]: List of knowledge package records as dictionaries.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM knowledge_packages 
            WHERE domain = ? 
            ORDER BY created_at DESC
        """, (domain,))
        rows = cursor.fetchall()
        
        packages = []
        for row in rows:
            package = dict(row)
            # Deserialize JSON fields
            try:
                package['structured_knowledge'] = json.loads(package['structured_knowledge'])
                package['exam_dataset'] = json.loads(package['exam_dataset'])
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Failed to deserialize JSON for package ID {package['id']}")
            
            packages.append(package)
        
        logger.info(f"Retrieved {len(packages)} knowledge packages for domain: {domain}")
        return packages
    except sqlite3.Error as e:
        logger.error(f"Failed to retrieve knowledge packages: {e}")
        raise
    finally:
        conn.close()


def get_expert_by_id(expert_id: int) -> Optional[Dict]:
    """Retrieve an expert by ID from the database.
    
    Args:
        expert_id: The ID of the expert to retrieve.
        
    Returns:
        Optional[Dict]: The expert record or None if not found.
    """
    experts = get_all_experts()
    for expert in experts:
        if expert['id'] == expert_id:
            return expert
    return None


def get_knowledge_package_by_id(package_id: int) -> Optional[Dict]:
    """Retrieve a knowledge package by ID from the database.
    
    Args:
        package_id: The ID of the knowledge package to retrieve.
        
    Returns:
        Optional[Dict]: The knowledge package record or None if not found.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM knowledge_packages WHERE id = ?", (package_id,))
        row = cursor.fetchone()
        
        if row:
            package = dict(row)
            # Deserialize JSON fields
            try:
                package['structured_knowledge'] = json.loads(package['structured_knowledge'])
                package['exam_dataset'] = json.loads(package['exam_dataset'])
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Failed to deserialize JSON for package ID {package_id}")
            
            return package
        return None
    except sqlite3.Error as e:
        logger.error(f"Failed to retrieve knowledge package: {e}")
        return None
    finally:
        conn.close()


async def apply_ema_evolution(
    expert_id: int,
    current_test_score: float,
    alpha: float = 0.2,
    change_reason: str = "Performance evaluation",
    package_id: Optional[int] = None
) -> Dict[str, any]:
    """Apply EMA (Exponential Moving Average) evolution to an expert's score.
    
    This function fetches the existing ema_score from expert_registry, calculates
    the new score using the project formula: EMA_new = (alpha * current_test_score) + ((1 - alpha) * EMA_old),
    updates the ema_score and updated_at fields in expert_registry, and logs a new
    audit entry into the ema_history table.
    
    Args:
        expert_id: The ID of the expert to update.
        current_test_score: The test score from the current evaluation (0.0 to 1.0).
        alpha: The smoothing factor for EMA calculation (default: 0.2).
        change_reason: The reason for the score change (default: "Performance evaluation").
        package_id: Optional ID of the knowledge package used for evaluation.
        
    Returns:
        Dict[str, any]: Dictionary containing the expert_id, old_score, new_score, and change.
        
    Raises:
        ValueError: If expert not found or scores are invalid.
        sqlite3.Error: If database operations fail.
    """
    logger.info("=" * 80)
    logger.info("EMA EVOLUTION - EXPERT SCORE UPDATE")
    logger.info("=" * 80)
    logger.info(f"Expert ID: {expert_id}")
    logger.info(f"Current Test Score: {current_test_score:.2f}")
    logger.info(f"Alpha: {alpha}")
    logger.info(f"Change Reason: {change_reason}")
    if package_id:
        logger.info(f"Package ID: {package_id}")
    logger.info("=" * 80 + "\n")
    
    # Validate inputs
    if not 0.0 <= current_test_score <= 1.0:
        raise ValueError(f"current_test_score must be between 0.0 and 1.0, got {current_test_score}")
    
    if not 0.0 <= alpha <= 1.0:
        raise ValueError(f"alpha must be between 0.0 and 1.0, got {alpha}")
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        # Fetch existing expert data
        logger.info(f"Fetching expert data for ID {expert_id}...")
        cursor.execute("SELECT id, name, ema_score FROM expert_registry WHERE id = ?", (expert_id,))
        row = cursor.fetchone()
        
        if not row:
            raise ValueError(f"Expert with ID {expert_id} not found")
        
        expert_name = row['name']
        old_score = row['ema_score']
        
        logger.info(f"Expert: {expert_name}")
        logger.info(f"Old EMA Score: {old_score:.2f}\n")
        
        # Calculate new EMA score
        # Formula: EMA_new = (alpha * current_test_score) + ((1 - alpha) * EMA_old)
        new_score = (alpha * current_test_score) + ((1 - alpha) * old_score)
        new_score = max(0.0, min(1.0, new_score))  # Clamp to [0.0, 1.0]
        
        logger.info(f"Calculating new EMA score...")
        logger.info(f"Formula: EMA_new = ({alpha} * {current_test_score:.2f}) + ((1 - {alpha}) * {old_score:.2f})")
        logger.info(f"New EMA Score: {new_score:.2f}\n")
        
        # Update expert_registry
        logger.info(f"Updating expert_registry...")
        cursor.execute("""
            UPDATE expert_registry
            SET ema_score = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_score, expert_id))
        
        # Log audit entry to ema_history
        logger.info(f"Logging audit entry to ema_history...")
        cursor.execute("""
            INSERT INTO ema_history (expert_id, old_score, new_score, test_score, alpha, change_reason, package_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (expert_id, old_score, new_score, current_test_score, alpha, change_reason, package_id))
        
        conn.commit()
        
        score_change = new_score - old_score
        change_indicator = "+" if score_change > 0 else ""
        
        logger.info("=" * 80)
        logger.info("EMA EVOLUTION COMPLETED")
        logger.info("=" * 80)
        logger.info(f"Expert: {expert_name} (ID: {expert_id})")
        logger.info(f"Old Score: {old_score:.2f}")
        logger.info(f"New Score: {new_score:.2f}")
        logger.info(f"Change: {change_indicator}{score_change:.2f}")
        logger.info(f"Reason: {change_reason}")
        logger.info("=" * 80 + "\n")
        
        return {
            'expert_id': expert_id,
            'expert_name': expert_name,
            'old_score': old_score,
            'new_score': new_score,
            'change': score_change,
            'alpha': alpha,
            'test_score': current_test_score
        }
        
    except sqlite3.Error as e:
        logger.error(f"Database error during EMA evolution: {e}")
        conn.rollback()
        raise
    except ValueError as e:
        logger.error(f"Validation error during EMA evolution: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def is_query_processed(query: str) -> bool:
    """Check if a query has already been processed.

    Args:
        query: The search query to check.

    Returns:
        bool: True if the query has been processed, False otherwise.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM processed_queries WHERE query = ?", (query,))
        row = cursor.fetchone()
        return row is not None
    except sqlite3.Error as e:
        logger.error(f"Failed to check if query is processed: {e}")
        return False
    finally:
        conn.close()


def mark_query_processed(query: str) -> bool:
    """Mark a query as processed in the database.

    Args:
        query: The search query to mark as processed.

    Returns:
        bool: True if the operation succeeded, False otherwise.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO processed_queries (query) VALUES (?)", (query,))
        conn.commit()
        logger.info(f"Query marked as processed: {query}")
        return True
    except sqlite3.IntegrityError:
        # Query already exists, which is fine
        logger.warning(f"Query already marked as processed: {query}")
        return True
    except sqlite3.Error as e:
        logger.error(f"Failed to mark query as processed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def get_experts_by_tier(tier: int) -> List[Dict]:
    """Get all experts for a specific tier.

    Args:
        tier: The tier number to filter by.

    Returns:
        List[Dict]: List of expert dictionaries.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, core_domain, tags, ema_score, tier, packages_absorbed, created_at
            FROM expert_registry
            WHERE tier = ?
            ORDER BY ema_score DESC
        """, (tier,))
        rows = cursor.fetchall()

        experts = []
        for row in rows:
            experts.append({
                'id': row['id'],
                'name': row['name'],
                'core_domain': row['core_domain'],
                'tags': row['tags'],
                'ema_score': row['ema_score'],
                'tier': row['tier'],
                'packages_absorbed': row['packages_absorbed'],
                'created_at': row['created_at']
            })

        return experts
    except sqlite3.Error as e:
        logger.error(f"Failed to get experts by tier {tier}: {e}")
        return []
    finally:
        conn.close()


def get_lowest_ema_expert(tier: Optional[int] = None) -> Optional[Dict]:
    """Get the expert with the lowest EMA score.

    Args:
        tier: Optional tier filter. If None, searches across all tiers.

    Returns:
        Optional[Dict]: The expert with the lowest EMA score, or None if no experts found.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        if tier is not None:
            cursor.execute("""
                SELECT id, name, core_domain, tags, ema_score, tier, packages_absorbed
                FROM expert_registry
                WHERE tier = ?
                ORDER BY ema_score ASC
                LIMIT 1
            """, (tier,))
        else:
            cursor.execute("""
                SELECT id, name, core_domain, tags, ema_score, tier, packages_absorbed
                FROM expert_registry
                ORDER BY ema_score ASC
                LIMIT 1
            """)

        row = cursor.fetchone()
        if row:
            return {
                'id': row['id'],
                'name': row['name'],
                'core_domain': row['core_domain'],
                'tags': row['tags'],
                'ema_score': row['ema_score'],
                'tier': row['tier'],
                'packages_absorbed': row['packages_absorbed']
            }
        return None
    except sqlite3.Error as e:
        logger.error(f"Failed to get lowest EMA expert: {e}")
        return None
    finally:
        conn.close()


def increment_buffer_encounter(sub_theme: str, domain: str, parent_expert_id: int) -> int:
    """Increment the encounter count for a sub-theme in the creation buffer.

    Args:
        sub_theme: The sub-theme keyword.
        domain: The domain.
        parent_expert_id: The parent expert ID.

    Returns:
        int: The updated encounter count.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO expert_creation_buffer (sub_theme, domain, parent_expert_id, encounter_count)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(sub_theme, domain, parent_expert_id)
            DO UPDATE SET
                encounter_count = encounter_count + 1,
                last_encountered_at = CURRENT_TIMESTAMP
        """, (sub_theme, domain, parent_expert_id))
        conn.commit()

        # Get the updated count
        cursor.execute("""
            SELECT encounter_count FROM expert_creation_buffer
            WHERE sub_theme = ? AND domain = ? AND parent_expert_id = ?
        """, (sub_theme, domain, parent_expert_id))
        row = cursor.fetchone()
        return row['encounter_count'] if row else 1
    except sqlite3.Error as e:
        logger.error(f"Failed to increment buffer encounter: {e}")
        conn.rollback()
        return 0
    finally:
        conn.close()


def get_buffer_encounter_count(sub_theme: str, domain: str, parent_expert_id: int) -> int:
    """Get the current encounter count for a sub-theme in the buffer.

    Args:
        sub_theme: The sub-theme keyword.
        domain: The domain.
        parent_expert_id: The parent expert ID.

    Returns:
        int: The encounter count, or 0 if not found.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT encounter_count FROM expert_creation_buffer
            WHERE sub_theme = ? AND domain = ? AND parent_expert_id = ?
        """, (sub_theme, domain, parent_expert_id))
        row = cursor.fetchone()
        return row['encounter_count'] if row else 0
    except sqlite3.Error as e:
        logger.error(f"Failed to get buffer encounter count: {e}")
        return 0
    finally:
        conn.close()


def remove_from_buffer(sub_theme: str, domain: str, parent_expert_id: int) -> bool:
    """Remove a sub-theme from the creation buffer after expert creation.

    Args:
        sub_theme: The sub-theme keyword.
        domain: The domain.
        parent_expert_id: The parent expert ID.

    Returns:
        bool: True if successful, False otherwise.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM expert_creation_buffer
            WHERE sub_theme = ? AND domain = ? AND parent_expert_id = ?
        """, (sub_theme, domain, parent_expert_id))
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Failed to remove from buffer: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def get_frozen_experts(cycle_threshold: int = 10) -> List[Dict]:
    """Get experts that are frozen (baseline EMA and zero packages absorbed).

    Args:
        cycle_threshold: Minimum cycles since creation to consider frozen.

    Returns:
        List[Dict]: List of frozen expert dictionaries.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, core_domain, ema_score, packages_absorbed, created_at
            FROM expert_registry
            WHERE tier = 3
            AND ema_score <= 0.11
            AND packages_absorbed = 0
            AND parent_expert_id IS NOT NULL
            AND datetime(created_at) < datetime('now', '-' || ? || ' hours')
        """, (cycle_threshold,))
        rows = cursor.fetchall()

        experts = []
        for row in rows:
            experts.append({
                'id': row['id'],
                'name': row['name'],
                'core_domain': row['core_domain'],
                'ema_score': row['ema_score'],
                'packages_absorbed': row['packages_absorbed'],
                'created_at': row['created_at']
            })

        return experts
    except sqlite3.Error as e:
        logger.error(f"Failed to get frozen experts: {e}")
        return []
    finally:
        conn.close()


def delete_expert(expert_id: int) -> bool:
    """Delete an expert from the registry.

    Args:
        expert_id: The ID of the expert to delete.

    Returns:
        bool: True if successful, False otherwise.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM expert_registry WHERE id = ?", (expert_id,))
        conn.commit()
        logger.info(f"Deleted expert ID {expert_id}")
        return True
    except sqlite3.Error as e:
        logger.error(f"Failed to delete expert ID {expert_id}: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()
