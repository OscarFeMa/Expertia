"""Automated co-evolution batch supervisor script.

This script orchestrates the automated batch processing of multiple research topics
through the evolution pipeline. It iterates through a predefined list of topics,
triggers the evolution test for each, and implements cooldown guards to protect
the local GPU (GTX 1660 6GB) from overheating during continuous Ollama inference.

Additionally, it implements an hour-based reporting timer that generates comprehensive
status summaries every 60 minutes, highlighting new expert spawn events and operational metrics.
"""

import asyncio
import sys
import logging
import subprocess
import time
from pathlib import Path
from typing import List, Dict, Set
from datetime import datetime
import json

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from database.connection import get_connection, initialize_database
from database.queries import get_all_experts, get_experts_by_tier, get_lowest_ema_expert, is_query_processed, mark_query_processed
from master.auditor.ecosystem_auditor import check_density_and_germinate
from crawler.ollama_manager import ensure_ollama_model_exists
import httpx

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Define robust list of training topics across multiple expertise fields (for manual mode)
TRAINING_TOPICS: List[str] = [
    "PostgreSQL query optimization",
    "Python async bottlenecks",
    "Docker multi-stage builds",
    "Linux kernel tuning",
    "Redis caching strategies",
    "Nginx load balancing"
]

# Ollama configuration for dynamic query generation
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:3b"

# Cooldown duration between iterations (seconds) to allow GPU VRAM to clear
COOLDOWN_SECONDS = 10

# Hourly reporting interval (seconds)
REPORTING_INTERVAL_SECONDS = 3600  # 60 minutes

# Reports directory
REPORTS_DIR = Path(__file__).parent / "storage" / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def get_expert_cache() -> Set[int]:
    """Get current expert IDs from database to serve as baseline cache.

    Returns:
        Set[int]: Set of current expert IDs.
    """
    try:
        experts = get_all_experts()
        return {expert['id'] for expert in experts}
    except Exception as e:
        logger.error(f"Failed to get expert cache: {e}")
        return set()


def get_new_experts(baseline_cache: Set[int]) -> List[Dict]:
    """Identify new experts that have been spawned since baseline cache was taken.

    Args:
        baseline_cache: Set of expert IDs from the beginning of the reporting window.

    Returns:
        List[Dict]: List of new expert dictionaries with their details.
    """
    try:
        current_experts = get_all_experts()
        new_experts = []

        for expert in current_experts:
            if expert['id'] not in baseline_cache:
                new_experts.append(expert)

        return new_experts
    except Exception as e:
        logger.error(f"Failed to identify new experts: {e}")
        return []


def get_operational_metrics() -> Dict:
    """Collect basic operational metrics for the hourly report.

    Returns:
        Dict: Dictionary containing operational metrics.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Count total knowledge packages
        cursor.execute("SELECT COUNT(*) as count FROM knowledge_packages")
        total_packages = cursor.fetchone()['count']

        # Count total experts
        cursor.execute("SELECT COUNT(*) as count FROM expert_registry")
        total_experts = cursor.fetchone()['count']

        # Count experts by tier
        cursor.execute("SELECT tier, COUNT(*) as count FROM expert_registry GROUP BY tier")
        tier_counts = {row['tier']: row['count'] for row in cursor.fetchall()}

        # Count total EMA history entries
        cursor.execute("SELECT COUNT(*) as count FROM ema_history")
        total_ema_entries = cursor.fetchone()['count']

        return {
            'total_packages': total_packages,
            'total_experts': total_experts,
            'tier_counts': tier_counts,
            'total_ema_entries': total_ema_entries,
            'report_timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to collect operational metrics: {e}")
        return {}
    finally:
        conn.close()


def generate_hourly_report(new_experts: List[Dict], metrics: Dict) -> str:
    """Generate a comprehensive hourly report in Markdown format.

    Args:
        new_experts: List of new experts spawned during the reporting window.
        metrics: Dictionary of operational metrics.

    Returns:
        str: The Markdown report content.
    """
    report_lines = [
        "# Hourly System Report",
        f"**Generated:** {metrics.get('report_timestamp', datetime.now().isoformat())}",
        "",
        "## Operational Metrics",
        "",
        f"- **Total Knowledge Packages:** {metrics.get('total_packages', 0)}",
        f"- **Total Experts:** {metrics.get('total_experts', 0)}",
        f"- **Total EMA History Entries:** {metrics.get('total_ema_entries', 0)}",
        "",
        "### Expert Distribution by Tier",
        ""
    ]

    tier_counts = metrics.get('tier_counts', {})
    for tier in sorted(tier_counts.keys(), reverse=True):
        count = tier_counts[tier]
        report_lines.append(f"- **Tier {tier}:** {count} experts")

    report_lines.extend([
        "",
        "## New Expert Incorporations (Last 60 Minutes)",
        ""
    ])

    if new_experts:
        for expert in new_experts:
            report_lines.extend([
                f"### {expert['name']}",
                f"- **ID:** {expert['id']}",
                f"- **Core Domain:** {expert['core_domain']}",
                f"- **Tier:** {expert.get('tier', 3)}",
                f"- **EMA Score:** {expert['ema_score']:.2f}",
                f"- **Tags:** {expert['tags']}",
                f"- **Parent Expert ID:** {expert.get('parent_expert_id', 'N/A')}",
                f"- **Birth Timestamp:** {expert.get('created_at', 'N/A')}",
                ""
            ])
    else:
        report_lines.append("*No new specialists spawned in this window.*")
        report_lines.append("")

    report_lines.extend([
        "---",
        "",
        "*Report generated automatically by the Async Expert Incubator Ecosystem Auditor.*"
    ])

    return "\n".join(report_lines)


def save_hourly_report(report_content: str) -> Path:
    """Save the hourly report to a Markdown file.

    Args:
        report_content: The Markdown report content.

    Returns:
        Path: The path to the saved report file.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"hourly_report_{timestamp}.md"
    filepath = REPORTS_DIR / filename

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report_content)
        logger.info(f"Hourly report saved to: {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Failed to save hourly report: {e}")
        return None


def print_tier_tables() -> None:
    """Print the 3 distinct tier tables on screen.

    Displays:
    - Tier 1: Ingestion Engine
    - Tier 2: Consolidated Experts
    - Tier 3: In-Training/Specialists
    """
    logger.info("\n" + "=" * 80)
    logger.info("EXPERT ECOSYSTEM STATUS - TIER DISTRIBUTION")
    logger.info("=" * 80 + "\n")

    tier_names = {
        1: "Ingestion Engine",
        2: "Consolidated Experts",
        3: "In-Training/Specialists"
    }

    for tier in [1, 2, 3]:
        experts = get_experts_by_tier(tier)
        tier_name = tier_names.get(tier, f"Tier {tier}")

        logger.info(f"--- {tier_name} (Tier {tier}) ---")
        logger.info(f"Total: {len(experts)} experts\n")

        if experts:
            for expert in experts:
                logger.info(f"  [{expert['id']}] {expert['name']}")
                logger.info(f"      Domain: {expert['core_domain']}")
                logger.info(f"      EMA Score: {expert['ema_score']:.2f}")
                logger.info(f"      Packages Absorbed: {expert['packages_absorbed']}")
                logger.info(f"      Tags: {expert['tags']}")
                logger.info("")
        else:
            logger.info("  No experts in this tier.\n")

    logger.info("=" * 80 + "\n")


async def generate_search_query_via_ollama(expert_tags: str, expert_domain: str) -> str:
    """Generate a unique Google search query using Ollama.

    Args:
        expert_tags: The expert's semantic tags.
        expert_domain: The expert's core domain.

    Returns:
        str: The generated search query.
    """
    prompt = f"""Generate a unique, specific Google search query for training an expert in the domain of {expert_domain}.

Expert tags: {expert_tags}

Requirements:
- Generate a specific, technical query that would yield high-quality educational content
- Avoid generic queries
- Focus on advanced or niche topics within the domain
- Return ONLY the search query, no explanation or additional text

Search query:"""

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 50
                    }
                }
            )

            if response.status_code == 200:
                result = response.json()
                query = result.get("response", "").strip()
                # Clean up the query
                query = query.replace('"', '').replace("'", "").strip()
                logger.info(f"Generated search query: '{query}'")
                return query
            else:
                logger.error(f"Ollama API error: {response.status_code}")
                return f"{expert_domain} advanced techniques tutorial"

    except Exception as e:
        logger.error(f"Failed to generate query via Ollama: {e}")
        return f"{expert_domain} best practices guide"


def print_new_incorporations_alert(new_experts: List[Dict]) -> None:
    """Print a standalone alert box for new expert incorporations.

    Args:
        new_experts: List of new experts spawned during the reporting window.
    """
    logger.info("\n" + "=" * 80)
    logger.info("=== NEW EXPERT INCORPORATIONS (LAST 60 MINS) ===")
    logger.info("=" * 80)

    if new_experts:
        for expert in new_experts:
            logger.info(f"\n[NEW SPECIALIST]")
            logger.info(f"  Name: {expert['name']}")
            logger.info(f"  Core Domain: {expert['core_domain']}")
            logger.info(f"  Birth Timestamp: {expert.get('created_at', 'N/A')}")
            logger.info(f"  Tier: {expert.get('tier', 3)}")
            logger.info(f"  EMA Score: {expert['ema_score']:.2f}")
    else:
        logger.info("\nNo new specialists spawned in this window.")

    logger.info("\n" + "=" * 80 + "\n")


async def run_evolution_test(topic: str) -> bool:
    """Run the evolution test script for a specific topic.

    This function executes the run_evolution_test.py script as a subprocess,
    passing the topic as a command-line argument. It uses sys.executable to
    ensure the active virtual environment/Python interpreter is targeted.

    Args:
        topic: The research topic to process.

    Returns:
        bool: True if the execution succeeded, False otherwise.
    """
    logger.info(f"Executing evolution test for topic: '{topic}'")

    # Path to the evolution test script
    script_path = Path(__file__).parent / "scripts" / "run_evolution_test.py"

    try:
        # Run the script as a subprocess with the --topic argument
        result = subprocess.run(
            [sys.executable, str(script_path), "--topic", topic],
            capture_output=True,
            text=True,
            timeout=600  # 10-minute timeout per topic
        )

        # Log the output
        if result.stdout:
            logger.info(result.stdout)
        if result.stderr:
            logger.error(result.stderr)

        # Check return code
        if result.returncode == 0:
            logger.info(f"Evolution test completed successfully for topic: '{topic}'")
            return True
        else:
            logger.error(f"Evolution test failed for topic: '{topic}' (exit code: {result.returncode})")
            return False

    except subprocess.TimeoutExpired:
        logger.error(f"Evolution test timed out for topic: '{topic}'")
        return False
    except Exception as e:
        logger.error(f"Failed to run evolution test for topic '{topic}': {e}")
        return False


async def run_autonomous_auditor_loop() -> None:
    """Run the autonomous auditor loop indefinitely.

    This function runs the full autonomous lifecycle:
    - At start of every cycle, invokes EcosystemAuditor
    - Prints 3 distinct tier tables
    - Identifies expert with lowest EMA
    - Generates dynamic search query via Ollama
    - Checks against processed_queries to prevent duplicates
    - Triggers subprocess pipeline with dynamic query
    - Implements hourly reporting
    - Maintains VRAM cooldown between cycles
    """
    logger.info("=" * 80)
    logger.info("AUTONOMOUS AUDITOR LOOP INITIATED")
    logger.info("=" * 80 + "\n")

    # Initialize database
    initialize_database()

    # Verify Ollama service
    try:
        await ensure_ollama_model_exists(model_name=OLLAMA_MODEL)
        logger.info("Ollama service verified and ready.\n")
    except Exception as e:
        logger.error(f"Ollama verification failed: {e}")
        logger.error("Please ensure Ollama is running on your system.")
        return

    # Initialize hourly reporting
    baseline_expert_cache = get_expert_cache()
    last_report_time = time.time()
    total_pages_scraped = 0
    total_ollama_inference_time = 0.0
    total_database_transactions = 0
    cycle_count = 0

    while True:
        cycle_count += 1
        cycle_start = time.time()

        logger.info("\n" + "=" * 80)
        logger.info(f"CYCLE {cycle_count}: AUTONOMOUS AUDITOR EXECUTION")
        logger.info("=" * 80 + "\n")

        # Step 1: Invoke EcosystemAuditor for density-based germination
        logger.info("[Step 1] Running EcosystemAuditor for density-based germination...")
        try:
            germinated_count = check_density_and_germinate()
            if germinated_count > 0:
                logger.info(f"[Auditor] {germinated_count} new specialists germinated during this cycle\n")
            else:
                logger.info("[Auditor] No new specialists germinated (critical mass not reached)\n")
        except Exception as e:
            logger.error(f"[Auditor] Density check failed: {e}\n")

        # Step 2: Print 3 distinct tier tables
        logger.info("[Step 2] Displaying expert ecosystem status by tier...")
        print_tier_tables()

        # Step 3: Identify expert with lowest EMA (highest training priority)
        logger.info("[Step 3] Identifying expert with lowest EMA score...")
        target_expert = get_lowest_ema_expert(tier=3)  # Focus on Tier 3 for training

        if not target_expert:
            logger.warning("No experts found in Tier 3. Checking all tiers...")
            target_expert = get_lowest_ema_expert()

        if not target_expert:
            logger.error("No experts found in database. Cannot proceed with autonomous loop.")
            logger.info("Please run seed_experts.py to initialize the expert registry.")
            break

        logger.info(f"Target expert: {target_expert['name']} (ID: {target_expert['id']}, EMA: {target_expert['ema_score']:.2f})")
        logger.info(f"Domain: {target_expert['core_domain']}")
        logger.info(f"Tags: {target_expert['tags']}\n")

        # Step 4: Generate dynamic search query via Ollama
        logger.info("[Step 4] Generating dynamic search query via Ollama...")
        search_query = await generate_search_query_via_ollama(
            expert_tags=target_expert['tags'],
            expert_domain=target_expert['core_domain']
        )

        # Step 5: Check if query has been processed
        logger.info("[Step 5] Checking if query has been previously processed...")
        if is_query_processed(search_query):
            logger.warning(f"Query '{search_query}' has already been processed. Generating alternative...")
            # Add timestamp to make it unique
            search_query = f"{search_query} {datetime.now().strftime('%Y%m%d')}"
            logger.info(f"Alternative query: '{search_query}'\n")
        else:
            logger.info(f"Query '{search_query}' is unique. Proceeding...\n")

        # Step 6: Mark query as processed
        mark_query_processed(search_query)

        # Step 7: Trigger subprocess pipeline with dynamic query
        logger.info(f"[Step 6] Triggering evolution pipeline with query: '{search_query}'")
        success = await run_evolution_test(search_query)

        if success:
            total_pages_scraped += 1
            total_database_transactions += 5
            logger.info(f"Cycle {cycle_count} completed successfully")
        else:
            logger.error(f"Cycle {cycle_count} failed")

        # Calculate elapsed time
        cycle_elapsed = time.time() - cycle_start
        total_ollama_inference_time += cycle_elapsed
        logger.info(f"Cycle {cycle_count} completed in {cycle_elapsed:.2f} seconds\n")

        # Step 8: Check if hourly reporting interval has elapsed
        current_time = time.time()
        if current_time - last_report_time >= REPORTING_INTERVAL_SECONDS:
            logger.info("\n" + "=" * 80)
            logger.info("HOURLY REPORTING TRIGGERED")
            logger.info("=" * 80 + "\n")

            # Identify new experts spawned since last report
            new_experts = get_new_experts(baseline_expert_cache)

            # Print alert box for new incorporations
            print_new_incorporations_alert(new_experts)

            # Collect operational metrics
            metrics = get_operational_metrics()
            metrics['total_pages_scraped'] = total_pages_scraped
            metrics['average_ollama_inference_time'] = (
                total_ollama_inference_time / cycle_count if cycle_count > 0 else 0.0
            )
            metrics['total_database_transactions'] = total_database_transactions
            metrics['total_cycles'] = cycle_count

            # Generate and save hourly report
            report_content = generate_hourly_report(new_experts, metrics)
            save_hourly_report(report_content)

            # Reset baseline cache and report timer
            baseline_expert_cache = get_expert_cache()
            last_report_time = current_time

            logger.info("[Reporting] Baseline cache reset. Next report in 60 minutes.\n")

        # Step 9: VRAM cooldown guard
        logger.info(f"\n[Cooldown Guard] Waiting {COOLDOWN_SECONDS} seconds to clear GPU VRAM...")
        try:
            await asyncio.sleep(COOLDOWN_SECONDS)
            logger.info("[Cooldown Guard] VRAM cooldown complete. Proceeding to next cycle.\n")
        except KeyboardInterrupt:
            logger.info("\nAutonomous loop interrupted by user during cooldown.")
            break


async def process_batch(topics: List[str]) -> None:
    """Process a batch of training topics sequentially with hourly reporting.

    This function iterates through the list of topics, runs the evolution test
    for each, implements cooldown guards to protect the local GPU from overheating,
    and generates hourly reports highlighting new expert incorporations.

    Args:
        topics: List of research topics to process.
    """
    total_topics = len(topics)
    logger.info("=" * 80)
    logger.info("AUTOMATED CO-EVOLUTION BATCH SUPERVISOR")
    logger.info("=" * 80)
    logger.info(f"Total topics to process: {total_topics}")
    logger.info(f"Cooldown between iterations: {COOLDOWN_SECONDS} seconds")
    logger.info(f"Hourly reporting interval: {REPORTING_INTERVAL_SECONDS} seconds")
    logger.info("=" * 80 + "\n")

    # Initialize database
    initialize_database()

    # Initialize hourly reporting
    baseline_expert_cache = get_expert_cache()
    last_report_time = time.time()
    total_pages_scraped = 0
    total_ollama_inference_time = 0.0
    total_database_transactions = 0

    successful_count = 0
    failed_count = 0

    for idx, topic in enumerate(topics, 1):
        iteration_start = time.time()

        logger.info(f"\n{'=' * 80}")
        logger.info(f"ITERATION {idx}/{total_topics}: Feeding topic...")
        logger.info(f"{'=' * 80}")
        logger.info(f"Topic: '{topic}'")
        logger.info(f"{'=' * 80}\n")

        # Run evolution test for this topic
        success = await run_evolution_test(topic)

        # Track results
        if success:
            successful_count += 1
            total_pages_scraped += 1  # Approximate count
            total_database_transactions += 5  # Approximate transaction count
        else:
            failed_count += 1

        # Calculate elapsed time
        iteration_elapsed = time.time() - iteration_start
        total_ollama_inference_time += iteration_elapsed  # Approximate inference time
        logger.info(f"Iteration {idx}/{total_topics} completed in {iteration_elapsed:.2f} seconds")

        # Check if hourly reporting interval has elapsed
        current_time = time.time()
        if current_time - last_report_time >= REPORTING_INTERVAL_SECONDS:
            logger.info("\n" + "=" * 80)
            logger.info("HOURLY REPORTING TRIGGERED")
            logger.info("=" * 80 + "\n")

            # Identify new experts spawned since last report
            new_experts = get_new_experts(baseline_expert_cache)

            # Print alert box for new incorporations
            print_new_incorporations_alert(new_experts)

            # Collect operational metrics
            metrics = get_operational_metrics()
            metrics['total_pages_scraped'] = total_pages_scraped
            metrics['average_ollama_inference_time'] = (
                total_ollama_inference_time / successful_count if successful_count > 0 else 0.0
            )
            metrics['total_database_transactions'] = total_database_transactions

            # Generate and save hourly report
            report_content = generate_hourly_report(new_experts, metrics)
            save_hourly_report(report_content)

            # Reset baseline cache and report timer
            baseline_expert_cache = get_expert_cache()
            last_report_time = current_time

            logger.info("[Reporting] Baseline cache reset. Next report in 60 minutes.\n")

        # Cooldown guard (except after last iteration)
        if idx < total_topics:
            logger.info(f"\n[Cooldown Guard] Waiting {COOLDOWN_SECONDS} seconds to clear GPU VRAM...")
            await asyncio.sleep(COOLDOWN_SECONDS)
            logger.info("[Cooldown Guard] VRAM cooldown complete. Proceeding to next topic.\n")

    # Final summary
    logger.info("\n" + "=" * 80)
    logger.info("BATCH PROCESSING COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Total topics processed: {total_topics}")
    logger.info(f"Successful: {successful_count}")
    logger.info(f"Failed: {failed_count}")
    logger.info(f"Total pages scraped: {total_pages_scraped}")
    logger.info(f"Average Ollama inference time: {total_ollama_inference_time / successful_count if successful_count > 0 else 0:.2f} seconds")
    logger.info(f"Total database transactions: {total_database_transactions}")
    logger.info("=" * 80 + "\n")


async def main():
    """Main entry point for the automated incubator supervisor.

    This function presents an interactive menu and delegates to the appropriate
    execution mode based on user selection.
    """
    print("\n" + "=" * 80)
    print("ASYNC EXPERT INCUBATOR - AUTOMATED SUPERVISOR")
    print("=" * 80 + "\n")

    print("Select execution mode:")
    print("  [1] Run Autonomous Auditor Loop (Full automated background mode)")
    print("  [2] Manual Expert Feeding & Target Creation")
    print("")

    try:
        choice = input("Enter your choice [1-2]: ").strip()

        if choice == "1":
            print("\n[Mode] Autonomous Auditor Loop selected")
            print("The system will run indefinitely, generating dynamic queries and")
            print("training experts based on EMA scores and density thresholds.\n")
            confirm = input("Confirm start? [y/N]: ").strip().lower()

            if confirm == 'y':
                await run_autonomous_auditor_loop()
                return 0
            else:
                print("\nOperation cancelled by user.")
                return 0

        elif choice == "2":
            print("\n[Mode] Manual Expert Feeding selected")
            print("Processing predefined topic batch...\n")
            await process_batch(TRAINING_TOPICS)
            return 0

        else:
            print("\nInvalid choice. Please select 1 or 2.")
            return 1

    except KeyboardInterrupt:
        print("\n\nOperation interrupted by user.")
        return 130
    except Exception as e:
        logger.error(f"\nFatal error during execution: {e}")
        return 1


if __name__ == "__main__":
    # Set event loop policy for Windows
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        result = asyncio.run(main())
        sys.exit(result)
    except KeyboardInterrupt:
        logger.info("\nBatch processing interrupted by user.")
        sys.exit(130)
    except Exception as e:
        logger.error(f"\nFatal error during execution: {e}")
        sys.exit(1)
