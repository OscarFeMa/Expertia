"""Ecosystem Auditor for density-based expert germination.

This module monitors the knowledge_packages table and automatically spawns
specialized experts when a specific sub-theme reaches critical mass (5+ packages).
This implements the Law of Critical Mass for expert ecosystem evolution.
"""

import sqlite3
import logging
import re
from typing import Dict, List, Optional, Tuple
from collections import Counter

from database.connection import get_connection
from database.queries import get_all_experts, add_expert, increment_buffer_encounter, get_buffer_encounter_count, remove_from_buffer, get_frozen_experts, delete_expert


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Law of Critical Mass: Minimum packages required to trigger germination
CRITICAL_MASS_THRESHOLD = 5

# Activation Buffer: Minimum encounters before expert creation
# TEMPORARILY DISABLED TO PREVENT EXPONENTIAL GROWTH
ACTIVATION_BUFFER_THRESHOLD = 999

# Pruning Rule: Minimum hours before considering an expert frozen
FROZEN_EXPERT_THRESHOLD_HOURS = 10

# Hard Limits: Maximum number of experts to prevent exponential growth
MAX_TOTAL_EXPERTS = 30  # 15 general + 15 specialists
MAX_SPECIALISTS_PER_DOMAIN = 5

# Domain mapping: maps granular knowledge package domains to high-level core domains
DOMAIN_MAPPING = {
    # Engineering & Applied Sciences
    'Technology': 'Engineering',
    'Civil Engineering': 'Engineering',
    'Mechanical Engineering': 'Engineering',
    'Software Engineering': 'Engineering',
    'Electrical Engineering': 'Engineering',
    'Chemical Engineering': 'Engineering',
    'Industrial Engineering': 'Engineering',
    'Materials Science': 'Engineering',
    'Infrastructure': 'Engineering',
    'Physics': 'Engineering',
    'Mechanics': 'Engineering',
    'Chemistry': 'Engineering',

    # Humanities & Historical
    'History': 'Humanities',
    'Geopolitics': 'Humanities',
    'Sociology': 'Humanities',
    'Culture': 'Humanities',
    'Philosophy': 'Humanities',
    'Anthropology': 'Humanities',
    'Social Sciences': 'Humanities',
    'Education': 'Humanities',
    'Geopolitics and History': 'Humanities',
    'Geopolitics and Sociology': 'Humanities',
    'Geopolitics, Economics': 'Humanities',
    'Geopolitics, History, Technology': 'Humanities',
    'Geopolitics, Sociology': 'Humanities',
    'Geopolitics, Strategy, History': 'Humanities',

    # Formal Sciences
    'Mathematics': 'Formal_Sciences',
    'Logic': 'Formal_Sciences',
    'Algorithms': 'Formal_Sciences',
    'Statistics': 'Formal_Sciences',
    'Computing': 'Formal_Sciences',
    'Computer Science': 'Formal_Sciences',
    'Formal': 'Formal_Sciences',
    'Science': 'Formal_Sciences',

    # Economy
    'Economics': 'Economy',
    'Finance': 'Economy',
    'Markets': 'Economy',
    'Trade': 'Economy',
    'Macroeconomics': 'Economy',
    'Microeconomics': 'Economy',
    'Game Theory': 'Economy',
    'Business': 'Economy',
    'Competition': 'Economy',

    # Biology
    'Biology': 'Biology',
    'Medicine': 'Biology',
    'Health': 'Biology',
    'Environment': 'Biology',
    'Ecology': 'Biology',
    'Biochemistry': 'Biology',
    'Organic': 'Biology',
    'Microbiology': 'Biology',
    'Cancer Biology': 'Biology',
    'Immunology': 'Biology',
    'Life Sciences': 'Biology',

    # Legal
    'Law': 'Legal',
    'Regulation': 'Legal',
    'Security': 'Legal',
    'Compliance': 'Legal',
    'Policy': 'Legal',
    'Standard': 'Legal',
    'OAuth2': 'Legal',
    'Legal': 'Legal'
}


def map_to_core_domain(granular_domain: str) -> str:
    """Map a granular knowledge package domain to a high-level core domain.

    Args:
        granular_domain: The granular domain from knowledge_packages.

    Returns:
        str: The mapped core domain, or the original if no mapping exists.
    """
    # Direct mapping
    if granular_domain in DOMAIN_MAPPING:
        return DOMAIN_MAPPING[granular_domain]

    # Fuzzy matching for compound domains
    for key, value in DOMAIN_MAPPING.items():
        if key.lower() in granular_domain.lower():
            return value

    # If no match found, return original (will be handled by the caller)
    return granular_domain


# Common stop words to exclude from sub-theme analysis
STOP_WORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
    'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
    'would', 'could', 'should', 'may', 'might', 'must', 'shall', 'can',
    'this', 'that', 'these', 'those', 'it', 'its', 'they', 'them', 'their',
    'what', 'which', 'who', 'whom', 'when', 'where', 'why', 'how',
    'about', 'into', 'through', 'during', 'before', 'after', 'above', 'below',
    'between', 'under', 'again', 'further', 'then', 'once', 'here', 'there',
    'when', 'where', 'why', 'how', 'all', 'both', 'each', 'few', 'more',
    'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own',
    'same', 'so', 'than', 'too', 'very', 'just', 'also', 'now'
}


def extract_sub_themes(topic: str, domain: str) -> List[str]:
    """Extract recurring sub-theme keywords from a topic string.

    This function tokenizes the topic, removes stop words, and returns
    significant keywords that could represent sub-themes.

    Args:
        topic: The research topic string.
        domain: The domain to filter against (optional).

    Returns:
        List[str]: List of significant sub-theme keywords.
    """
    # Normalize and tokenize
    words = re.findall(r'\b\w+\b', topic.lower())
    
    # Remove stop words
    significant_words = [word for word in words if word not in STOP_WORDS and len(word) > 2]
    
    return significant_words


def get_knowledge_packages_by_domain(domain: str) -> List[Dict]:
    """Retrieve all knowledge packages for a specific domain using domain mapping.

    This function retrieves all knowledge packages and maps their granular domains
    to the high-level core domain, then filters for the requested domain.

    Args:
        domain: The high-level core domain to filter by (e.g., 'Engineering', 'Humanities').

    Returns:
        List[Dict]: List of knowledge package records that map to the requested domain.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Retrieve all knowledge packages (we'll filter by mapping)
        cursor.execute("""
            SELECT id, topic, domain, structured_knowledge
            FROM knowledge_packages
            ORDER BY created_at DESC
        """)
        rows = cursor.fetchall()

        packages = []
        for row in rows:
            granular_domain = row['domain']
            mapped_domain = map_to_core_domain(granular_domain)

            # Only include packages that map to the requested domain
            if mapped_domain == domain:
                packages.append({
                    'id': row['id'],
                    'topic': row['topic'],
                    'domain': row['domain'],  # Keep original granular domain
                    'structured_knowledge': row['structured_knowledge']
                })

        return packages
    except sqlite3.Error as e:
        logger.error(f"Failed to retrieve knowledge packages for domain {domain}: {e}")
        return []
    finally:
        conn.close()


def analyze_sub_theme_density(packages: List[Dict]) -> Dict[str, int]:
    """Analyze the density of sub-themes across knowledge packages.

    This function counts how many packages contain each sub-theme keyword.

    Args:
        packages: List of knowledge package dictionaries.

    Returns:
        Dict[str, int]: Dictionary mapping sub-theme keywords to their package count.
    """
    sub_theme_counter = Counter()
    
    for package in packages:
        topic = package['topic']
        sub_themes = extract_sub_themes(topic, package['domain'])
        
        for theme in sub_themes:
            sub_theme_counter[theme] += 1
    
    return dict(sub_theme_counter)


def check_specialist_exists(specialist_name: str) -> bool:
    """Check if a specialist with the given name already exists.

    This prevents double-germination of the same specialist.

    Args:
        specialist_name: The name of the specialist to check.

    Returns:
        bool: True if the specialist exists, False otherwise.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM expert_registry WHERE name = ?", (specialist_name,))
        row = cursor.fetchone()
        return row is not None
    except sqlite3.Error as e:
        logger.error(f"Failed to check specialist existence: {e}")
        return False
    finally:
        conn.close()


def normalize_sub_theme(sub_theme: str) -> str:
    """Normalize a sub-theme for semantic filtering.

    Args:
        sub_theme: The raw sub-theme keyword.

    Returns:
        str: The normalized sub-theme.
    """
    # Remove special characters and normalize
    normalized = re.sub(r'[^a-zA-Z0-9\s]', '', sub_theme)
    normalized = ' '.join(normalized.split())
    return normalized.lower()


def is_semantic_duplicate(sub_theme: str, domain: str, existing_experts: List[Dict]) -> bool:
    """Check if a sub-theme would create a semantic duplicate.

    Args:
        sub_theme: The sub-theme keyword.
        domain: The domain.
        existing_experts: List of existing experts.

    Returns:
        bool: True if it would be a duplicate, False otherwise.
    """
    normalized_sub = normalize_sub_theme(sub_theme)
    normalized_domain = normalize_sub_theme(domain)

    for expert in existing_experts:
        expert_name = normalize_sub_theme(expert['name'])
        expert_domain = normalize_sub_theme(expert['core_domain'])

        # Check for exact match
        if normalized_sub in expert_name and normalized_domain in expert_name:
            return True

        # Check for root domain duplication (e.g., "Engineering Engineering Specialist")
        if normalized_sub == normalized_domain:
            return True

    return False


def cluster_related_sub_themes(sub_themes: Dict[str, int]) -> Dict[str, int]:
    """Cluster semantically related sub-themes to prevent micro-specialization.

    Args:
        sub_themes: Dictionary of sub-themes and their counts.

    Returns:
        Dict[str, int]: Clustered sub-themes with combined counts.
    """
    # Semantic similarity groups
    thermal_group = ['thermal', 'temperature', 'heat', 'thermodynamics']
    physical_group = ['physical', 'mechanical', 'mechanics', 'physics']
    data_group = ['data', 'analytics', 'statistics', 'analysis']
    security_group = ['security', 'cybersecurity', 'protection', 'defense']

    clustered = {}

    for theme, count in sub_themes.items():
        normalized = normalize_sub_theme(theme)
        clustered_key = theme

        # Check if theme belongs to a semantic group
        for group in [thermal_group, physical_group, data_group, security_group]:
            if any(keyword in normalized for keyword in group):
                # Use the most common keyword as the cluster key
                for keyword in group:
                    if keyword in normalized:
                        clustered_key = keyword.capitalize()
                        break
                break

        if clustered_key in clustered:
            clustered[clustered_key] += count
        else:
            clustered[clustered_key] = count

    return clustered


def generate_specialist_name(sub_theme: str, domain: str) -> str:
    """Generate a specialist name based on sub-theme and domain.

    Args:
        sub_theme: The sub-theme keyword.
        domain: The general domain.

    Returns:
        str: The generated specialist name.
    """
    # Capitalize sub-theme
    formatted_theme = sub_theme.capitalize()
    
    # Map domains to friendly names
    domain_names = {
        'Engineering': 'Engineering',
        'Humanities': 'Humanities',
        'Formal_Sciences': 'Formal Sciences',
        'Economy': 'Economics',
        'Biology': 'Life Sciences',
        'Legal': 'Legal'
    }
    
    friendly_domain = domain_names.get(domain, domain)
    
    return f"{formatted_theme} {friendly_domain} Specialist"


def generate_specialist_tags(general_tags: str, sub_theme: str) -> str:
    """Generate tailored tags for a new specialist.

    Combines the original general domain tags with the new specialized sub-theme.

    Args:
        general_tags: The general expert's tags.
        sub_theme: The sub-theme keyword.

    Returns:
        str: The combined tag string.
    """
    # Add sub-theme to existing tags
    return f"{general_tags}, {sub_theme}"


def generate_specialist_system_prompt(sub_theme: str, domain: str, general_prompt: str) -> str:
    """Generate a tailored system prompt for the new specialist.

    Args:
        sub_theme: The sub-theme keyword.
        domain: The general domain.
        general_prompt: The general expert's system prompt.

    Returns:
        str: The specialized system prompt.
    """
    return f"""{general_prompt}

You have specialized expertise in {sub_theme} within the {domain} domain. Your role is to provide deep, focused insights on {sub_theme}-related topics, leveraging your broad domain knowledge while emphasizing specialized understanding of this sub-theme."""


def germinate_specialist(
    sub_theme: str,
    domain: str,
    parent_expert_id: int,
    general_tags: str,
    general_prompt: str,
    existing_experts: List[Dict]
) -> Optional[int]:
    """Germinate a new specialist expert based on sub-theme critical mass with demand-driven constraints.

    This function implements the activation buffer, semantic filtering, and deduplication
    before creating a new specialist in the expert_registry.

    Args:
        sub_theme: The sub-theme keyword that triggered germination.
        domain: The general domain.
        parent_expert_id: The ID of the parent General Pillar Expert.
        general_tags: The general expert's tags.
        general_prompt: The general expert's system prompt.
        existing_experts: List of existing experts for semantic filtering.

    Returns:
        Optional[int]: The ID of the newly created specialist, or None if failed/blocked.
    """
    # Step 1: Check for semantic duplicates
    if is_semantic_duplicate(sub_theme, domain, existing_experts):
        logger.info(f"[Auditor - Buffer] Sub-theme '{sub_theme}' would create semantic duplicate. Routing to parent expert.")
        return None

    # Step 2: Increment buffer encounter count
    encounter_count = increment_buffer_encounter(sub_theme, domain, parent_expert_id)
    logger.info(f"[Auditor - Buffer] Sub-theme '{sub_theme}' encounter count: {encounter_count}/{ACTIVATION_BUFFER_THRESHOLD}")

    # Step 3: Check if activation threshold is met
    if encounter_count < ACTIVATION_BUFFER_THRESHOLD:
        logger.info(f"[Auditor - Buffer] Threshold not met. Sub-theme '{sub_theme}' remains in buffer.")
        return None

    # Step 4: Threshold met - proceed with germination
    logger.info(f"[Auditor - Buffer] Threshold met for '{sub_theme}'. Proceeding with germination.")

    # Generate specialist details
    specialist_name = generate_specialist_name(sub_theme, domain)

    # Prevent double-germination
    if check_specialist_exists(specialist_name):
        logger.warning(f"[Auditor - Germination] Specialist '{specialist_name}' already exists. Skipping germination.")
        remove_from_buffer(sub_theme, domain, parent_expert_id)
        return None

    # Generate tailored attributes
    specialist_tags = generate_specialist_tags(general_tags, sub_theme)
    specialist_prompt = generate_specialist_system_prompt(sub_theme, domain, general_prompt)

    try:
        # Insert new specialist
        specialist_id = add_expert(
            name=specialist_name,
            core_domain=domain,
            tags=specialist_tags,
            ema_score=0.10,  # Base score for new specialists
            system_prompt=specialist_prompt,
            tier=3,  # Tier 3 (In-Training)
            parent_expert_id=parent_expert_id
        )

        # Remove from buffer after successful creation
        remove_from_buffer(sub_theme, domain, parent_expert_id)

        # Log major system announcement
        logger.info("=" * 80)
        logger.info(f"[Auditor - Germination] Critical mass reached for sub-theme '{sub_theme}'")
        logger.info(f"[Auditor - Germination] Spawning Specific Specialist: '{specialist_name}' in Tier 3")
        logger.info(f"[Auditor - Germination] Parent Expert ID: {parent_expert_id}")
        logger.info(f"[Auditor - Germination] Specialist ID: {specialist_id}")
        logger.info(f"[Auditor - Germination] Buffer encounters: {encounter_count}")
        logger.info("=" * 80 + "\n")

        return specialist_id

    except Exception as e:
        logger.error(f"Failed to germinate specialist '{specialist_name}': {e}")
        return None


def check_density_and_germinate() -> int:
    """Check density of sub-themes and germinate specialists if critical mass is reached.

    This function scans the knowledge_packages table, analyzes sub-theme density
    within each General Expert's domain, applies semantic clustering, and triggers
    germination events when the Law of Critical Mass is satisfied (5+ packages per sub-theme).

    Returns:
        int: The number of specialists germinated during this check.
    """
    logger.info("=" * 80)
    logger.info("ECOSYSTEM AUDITOR - DENSITY CHECK AND GERMINATION")
    logger.info("=" * 80 + "\n")

    # Check hard limits before proceeding
    experts = get_all_experts()
    total_experts = len(experts)

    if total_experts >= MAX_TOTAL_EXPERTS:
        logger.warning(f"[Auditor - Limits] Hard limit reached: {total_experts}/{MAX_TOTAL_EXPERTS} experts")
        logger.warning("[Auditor - Limits] Skipping germination to prevent exponential growth")
        return 0

    logger.info(f"[Auditor - Limits] Current experts: {total_experts}/{MAX_TOTAL_EXPERTS}")

    # Get all General Pillar Experts (Tier 3, no parent)
    general_experts = [e for e in experts if e.get('tier', 3) == 3 and e.get('parent_expert_id') is None]

    if not general_experts:
        logger.warning("No General Pillar Experts found. Skipping density check.")
        return 0

    logger.info(f"Found {len(general_experts)} General Pillar Experts to monitor\n")

    germinated_count = 0

    for expert in general_experts:
        domain = expert['core_domain']
        expert_id = expert['id']
        expert_name = expert['name']

        logger.info(f"[Auditor] Analyzing domain: {domain} (Expert: {expert_name})")

        # Check per-domain limit
        domain_specialists = [e for e in experts if e.get('core_domain') == domain and e.get('parent_expert_id') is not None]
        if len(domain_specialists) >= MAX_SPECIALISTS_PER_DOMAIN:
            logger.warning(f"[Auditor - Limits] Domain limit reached: {len(domain_specialists)}/{MAX_SPECIALISTS_PER_DOMAIN} specialists for {domain}")
            logger.warning(f"[Auditor - Limits] Skipping germination for domain {domain}")
            continue

        logger.info(f"[Auditor - Limits] Domain specialists: {len(domain_specialists)}/{MAX_SPECIALISTS_PER_DOMAIN}")

        # Get knowledge packages for this domain
        packages = get_knowledge_packages_by_domain(domain)

        if not packages:
            logger.info(f"[Auditor] No knowledge packages found for domain {domain}\n")
            continue

        logger.info(f"[Auditor] Found {len(packages)} knowledge packages for domain {domain}")

        # Analyze sub-theme density
        sub_theme_density = analyze_sub_theme_density(packages)

        if not sub_theme_density:
            logger.info(f"[Auditor] No significant sub-themes detected in domain {domain}\n")
            continue

        logger.info(f"[Auditor] Sub-theme density analysis (pre-clustering):")
        for theme, count in sorted(sub_theme_density.items(), key=lambda x: x[1], reverse=True):
            logger.info(f"  - '{theme}': {count} packages")

        # Apply semantic clustering to prevent micro-specialization
        clustered_density = cluster_related_sub_themes(sub_theme_density)

        logger.info(f"[Auditor] Sub-theme density analysis (post-clustering):")
        for theme, count in sorted(clustered_density.items(), key=lambda x: x[1], reverse=True):
            logger.info(f"  - '{theme}': {count} packages")

        # Check for critical mass
        for sub_theme, count in clustered_density.items():
            if count >= CRITICAL_MASS_THRESHOLD:
                logger.info(f"[Auditor] Critical mass detected: '{sub_theme}' has {count} packages (threshold: {CRITICAL_MASS_THRESHOLD})")

                # Germinate specialist with demand-driven constraints
                specialist_id = germinate_specialist(
                    sub_theme=sub_theme,
                    domain=domain,
                    parent_expert_id=expert_id,
                    general_tags=expert['tags'],
                    general_prompt=expert.get('system_prompt', ''),
                    existing_experts=experts
                )

                if specialist_id:
                    germinated_count += 1
                    # Re-check total limit after each germination
                    if len(get_all_experts()) >= MAX_TOTAL_EXPERTS:
                        logger.warning(f"[Auditor - Limits] Hard limit reached after germination. Stopping.")
                        break
                else:
                    logger.info(f"[Auditor] Germination blocked for sub-theme '{sub_theme}' (buffer/threshold/duplicate)")

        logger.info("")

    # Step 2: Passive Pruning Rule - Remove frozen experts
    logger.info("[Auditor - Pruning] Checking for frozen experts...")
    frozen_experts = get_frozen_experts(cycle_threshold=FROZEN_EXPERT_THRESHOLD_HOURS)

    if frozen_experts:
        logger.info(f"[Auditor - Pruning] Found {len(frozen_experts)} frozen experts for removal")
        for frozen_expert in frozen_experts:
            logger.info(f"[Auditor - Pruning] Deleting frozen expert: {frozen_expert['name']} (ID: {frozen_expert['id']})")
            delete_expert(frozen_expert['id'])
    else:
        logger.info("[Auditor - Pruning] No frozen experts found")

    logger.info("")

    logger.info("=" * 80)
    logger.info(f"DENSITY CHECK COMPLETE: {germinated_count} specialists germinated")
    logger.info(f"PRUNING COMPLETE: {len(frozen_experts)} frozen experts removed")
    logger.info(f"LIMITS CHECK: {len(get_all_experts())}/{MAX_TOTAL_EXPERTS} total experts")
    logger.info("=" * 80 + "\n")

    return germinated_count


def increment_packages_absorbed(expert_id: int) -> None:
    """Increment the packages_absorbed counter for an expert.

    This function should be called when a knowledge package is successfully
    processed and associated with an expert.

    Args:
        expert_id: The ID of the expert to update.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE expert_registry
            SET packages_absorbed = packages_absorbed + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (expert_id,))
        conn.commit()
        logger.info(f"Incremented packages_absorbed for expert ID {expert_id}")
    except sqlite3.Error as e:
        logger.error(f"Failed to increment packages_absorbed for expert ID {expert_id}: {e}")
        conn.rollback()
    finally:
        conn.close()
