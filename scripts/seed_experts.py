"""Expert registry seeding script.

This script intelligently updates existing experts to correct tiers and inserts
the 6 General Pillar Experts representing the core foundations of human knowledge.
It uses item-by-item checking by expert name to prevent duplicates while preserving
existing EMA scores and data.
"""

import sys
import logging
from pathlib import Path
import sqlite3

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.connection import get_connection, initialize_database
from database.queries import add_expert, get_all_experts


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Legacy startup experts for tier re-structuring
LEGACY_STARTUP_EXPERTS = [
    {
        "name": "Web Research Expert",
        "tier": 1  # Ingestion Engine
    },
    {
        "name": "Factual Verifier",
        "tier": 3  # In-Training
    },
    {
        "name": "Epistemological Critic",
        "tier": 3  # In-Training
    }
]

# General Pillar Experts representing core foundations of human knowledge
GENERAL_PILLAR_EXPERTS = [
    {
        "name": "Engineering & Applied Sciences Expert",
        "core_domain": "Engineering",
        "tags": "physics, mechanics, chemistry, industrial, infrastructure, materials, software",
        "ema_score": 0.10,
        "tier": 3,
        "system_prompt": "You are an Engineering & Applied Sciences Expert. Your role is to provide expertise in physics, mechanics, chemistry, industrial processes, infrastructure, materials science, and software engineering. You understand the fundamental principles that govern engineered systems and their practical applications."
    },
    {
        "name": "Humanities & Historical Analyst",
        "core_domain": "Humanities",
        "tags": "history, geopolitics, culture, sociology, society, empire",
        "ema_score": 0.10,
        "tier": 3,
        "system_prompt": "You are a Humanities & Historical Analyst. Your role is to provide expertise in history, geopolitics, cultural studies, sociology, and societal structures. You understand the complex interplay of historical events, cultural movements, and social dynamics across civilizations."
    },
    {
        "name": "Formal Logic & Mathematics Expert",
        "core_domain": "Formal_Sciences",
        "tags": "mathematics, logic, algorithms, statistics, computing, formal",
        "ema_score": 0.10,
        "tier": 3,
        "system_prompt": "You are a Formal Logic & Mathematics Expert. Your role is to provide expertise in mathematics, formal logic, algorithms, statistics, computing theory, and formal systems. You understand the rigorous foundations of abstract reasoning and computational structures."
    },
    {
        "name": "Economic & Market Strategist",
        "core_domain": "Economy",
        "tags": "finance, markets, competition, macroeconomics, trade, game_theory",
        "ema_score": 0.10,
        "tier": 3,
        "system_prompt": "You are an Economic & Market Strategist. Your role is to provide expertise in finance, market dynamics, competitive strategy, macroeconomics, international trade, and game theory. You understand the complex mechanisms that drive economic systems and market behavior."
    },
    {
        "name": "Life Sciences & Biologist",
        "core_domain": "Biology",
        "tags": "health, medicine, environment, ecology, biochemistry, organic",
        "ema_score": 0.10,
        "tier": 3,
        "system_prompt": "You are a Life Sciences & Biologist. Your role is to provide expertise in health, medicine, environmental science, ecology, biochemistry, and organic systems. You understand the intricate processes that govern living organisms and their ecosystems."
    },
    {
        "name": "Legal & Regulatory Advisor",
        "core_domain": "Legal",
        "tags": "law, regulation, security, compliance, policy, standard, oauth2",
        "ema_score": 0.10,
        "tier": 3,
        "system_prompt": "You are a Legal & Regulatory Advisor. Your role is to provide expertise in law, regulation, security frameworks, compliance requirements, policy development, standards, and authentication protocols like OAuth2. You understand the complex legal and regulatory landscape that governs organizations and technology systems."
    }
]


def expert_exists_by_name(name: str) -> bool:
    """Check if an expert with the given name exists in the database.

    Args:
        name: The expert name to check.

    Returns:
        bool: True if the expert exists, False otherwise.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM expert_registry WHERE name = ?", (name,))
        row = cursor.fetchone()
        return row is not None
    except sqlite3.Error as e:
        logger.error(f"Failed to check expert existence: {e}")
        return False
    finally:
        conn.close()


def update_expert_tier(name: str, tier: int) -> bool:
    """Update the tier of an existing expert without modifying other fields.

    Args:
        name: The expert name to update.
        tier: The new tier value.

    Returns:
        bool: True if update succeeded, False otherwise.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE expert_registry
            SET tier = ?, updated_at = CURRENT_TIMESTAMP
            WHERE name = ?
        """, (tier, name))
        conn.commit()
        logger.info(f"[Seed] Updated Tier for existing expert '{name}' to Tier {tier}")
        return True
    except sqlite3.Error as e:
        logger.error(f"Failed to update tier for expert '{name}': {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def seed_experts() -> None:
    """Intelligently seed and update the expert registry.

    This function performs two main operations:
    1. Updates existing legacy experts to correct tiers without resetting EMA scores
    2. Inserts the 6 General Pillar Experts only if they don't already exist

    Raises:
        Exception: If database operations fail.
    """
    logger.info("=" * 80)
    logger.info("INTELLIGENT EXPERT REGISTRY SEEDING")
    logger.info("=" * 80 + "\n")

    # Initialize database
    logger.info("Initializing database...")
    initialize_database()

    # Step 1: Update legacy experts to correct tiers
    logger.info("[Step 1] Updating legacy experts to correct tiers...")
    updated_count = 0
    for legacy_expert in LEGACY_STARTUP_EXPERTS:
        name = legacy_expert["name"]
        target_tier = legacy_expert["tier"]

        if expert_exists_by_name(name):
            success = update_expert_tier(name, target_tier)
            if success:
                updated_count += 1
        else:
            logger.info(f"[Seed] Legacy expert '{name}' not found, skipping tier update")

    logger.info(f"[Step 1] Updated {updated_count}/{len(LEGACY_STARTUP_EXPERTS)} legacy experts\n")

    # Step 2: Insert General Pillar Experts (only if they don't exist)
    logger.info("[Step 2] Inserting General Pillar Experts...")
    inserted_count = 0
    skipped_count = 0

    for expert_data in GENERAL_PILLAR_EXPERTS:
        name = expert_data["name"]

        if expert_exists_by_name(name):
            logger.info(f"[Seed] General Pillar '{name}' already exists, skipping insertion")
            skipped_count += 1
        else:
            try:
                expert_id = add_expert(
                    name=expert_data["name"],
                    core_domain=expert_data["core_domain"],
                    tags=expert_data["tags"],
                    ema_score=expert_data["ema_score"],
                    system_prompt=expert_data["system_prompt"],
                    tier=expert_data["tier"]
                )
                logger.info(f"[Seed] Successfully inserted new General Pillar: '{name}' (ID: {expert_id}, Tier: {expert_data['tier']})")
                inserted_count += 1
            except Exception as e:
                logger.error(f"Failed to insert expert {name}: {e}")

    logger.info(f"[Step 2] Inserted {inserted_count}/{len(GENERAL_PILLAR_EXPERTS)} General Pillar Experts")
    logger.info(f"[Step 2] Skipped {skipped_count} already-existing General Pillar Experts\n")

    # Final summary
    logger.info("=" * 80)
    logger.info("SEEDING SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Legacy experts updated: {updated_count}")
    logger.info(f"General Pillar Experts inserted: {inserted_count}")
    logger.info(f"General Pillar Experts skipped (already exist): {skipped_count}")
    logger.info("=" * 80 + "\n")


def main() -> None:
    """Main entry point for the seeding script."""
    try:
        seed_experts()
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error during seeding: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
