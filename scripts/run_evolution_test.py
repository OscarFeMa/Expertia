"""Expert evaluation and EMA evolution test script.

This script demonstrates the complete Phase 2 pipeline:
1. Verify Ollama service and model availability
2. Seed experts if registry is empty
3. Perform live search and sequential extraction on a specific topic
4. Run Universal Teacher distillation via Ollama to generate structured knowledge package
5. Save the package into the database (knowledge_packages table)
6. Query the database to find the best expert profile based on Jaccard suitability match
7. Invoke evaluate_expert_performance() to make that local expert take the 5-question test
8. Apply EMA evolution based on evaluation results
"""

import asyncio
import sys
import logging
import argparse
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.connection import initialize_database
from database.queries import (
    get_all_experts,
    get_knowledge_packages_by_topic,
    apply_ema_evolution,
    find_best_expert,
    add_knowledge_package
)
from crawler.ollama_manager import ensure_ollama_model_exists
from crawler.search_engine import search_topic
from crawler.parser import ContentParser, extract_clean_markdown
from crawler.distiller import distill_markdown_with_ollama, format_distillation_summary
from master.evaluation.evaluator import evaluate_expert_performance
from master.auditor.ecosystem_auditor import check_density_and_germinate, increment_packages_absorbed
from config.settings import DISTILLATION_MODEL, MAX_RESULTS_PER_SEARCH


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main(args):
    """Main entry point for the evolution test script.

    This function runs the complete Phase 2 pipeline:
    - Ollama verification
    - Expert seeding (if needed)
    - Live search and extraction
    - Knowledge distillation
    - Expert matching
    - Expert evaluation
    - EMA evolution

    Args:
        args: Parsed command-line arguments containing the topic.
    """
    logger.info("=" * 80)
    logger.info("EXPERT EVALUATION AND EMA EVOLUTION TEST - COMPLETE PIPELINE")
    logger.info("=" * 80 + "\n")
    
    # Step 1: Verify Ollama service and model availability
    logger.info("[Step 1] Verifying Ollama service and model availability...")
    try:
        await ensure_ollama_model_exists(model_name=DISTILLATION_MODEL)
    except Exception as e:
        logger.error(f"Ollama verification failed: {e}")
        logger.error("Please ensure Ollama is running on your system before proceeding.")
        sys.exit(1)
    
    # Step 2: Initialize database
    logger.info("\n[Step 2] Initializing database...")
    try:
        initialize_database()
        logger.info("Database initialized successfully.\n")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        sys.exit(1)
    
    # Step 3: Seed experts if registry is empty
    logger.info("[Step 3] Checking expert registry...")
    experts = get_all_experts()
    
    if not experts:
        logger.warning("No experts found in registry. Seeding startup experts...")
        try:
            # Import and run seed_experts logic
            from scripts.seed_experts import seed_experts
            seed_experts()
            experts = get_all_experts()
            logger.info(f"Seeding completed. Found {len(experts)} experts in registry.\n")
        except Exception as e:
            logger.error(f"Failed to seed experts: {e}")
            sys.exit(1)
    else:
        logger.info(f"Found {len(experts)} experts in registry:\n")
        for expert in experts:
            logger.info(f"  - {expert['name']} (ID: {expert['id']}, Domain: {expert['core_domain']}, Score: {expert['ema_score']:.2f})")
        logger.info("")
    
    # Step 4: Perform live search and sequential extraction on a specific topic
    research_topic = args.topic
    logger.info(f"[Step 4] Performing live search for topic: '{research_topic}'")
    logger.info("=" * 80 + "\n")
    
    try:
        search_results = await search_topic(query=research_topic, max_results=MAX_RESULTS_PER_SEARCH)
        
        if not search_results:
            logger.warning("No search results found. Pipeline completed with no content.")
            sys.exit(0)
        
        logger.info(f"Found {len(search_results)} URLs to process\n")
        
        # Initialize parser
        parser = ContentParser()
        knowledge_packages = []
        
        # Process URLs sequentially
        for idx, result in enumerate(search_results, 1):
            url = result['url']
            title = result.get('title', 'Untitled')
            
            logger.info(f"[Processing {idx}/{len(search_results)}]")
            logger.info(f"Title: {title}")
            logger.info(f"URL: {url}")
            
            # Parse the URL
            parse_result = await parser.parse(url)
            
            if parse_result and parse_result['status'] == 'success':
                markdown_content = parse_result['markdown']
                logger.info(f"Status: SUCCESS - Extracted {len(markdown_content)} characters")
                
                # Step 5: Run Universal Teacher distillation via Ollama
                logger.info(f"[Distill {idx}/{len(search_results)}] Starting LLM knowledge distillation...")
                try:
                    distilled = await distill_markdown_with_ollama(
                        markdown_content,
                        model_name=DISTILLATION_MODEL
                    )
                    
                    # Step 6: Save the package into the database
                    domain = distilled.get('domain_classification', 'Unknown')
                    thesis = distilled.get('thesis_or_core_objective', 'Not provided')
                    
                    package_id = add_knowledge_package(
                        topic=research_topic,
                        source_url=url,
                        domain=domain,
                        structured_knowledge=distilled.get('structured_knowledge', {}),
                        exam_dataset=distilled.get('evaluation_exam', [])
                    )

                    # Find the best expert for this domain to increment their packages_absorbed counter
                    try:
                        best_expert_for_domain, _ = find_best_expert(domain)
                        if best_expert_for_domain:
                            increment_packages_absorbed(best_expert_for_domain['id'])
                            logger.info(f"Incremented packages_absorbed for expert: {best_expert_for_domain['name']}")
                    except Exception as e:
                        logger.warning(f"Failed to increment packages_absorbed: {e}")

                    # Store package info
                    package = {
                        'id': package_id,
                        'url': url,
                        'title': title,
                        'domain': domain,
                        'thesis': thesis,
                        'structured_knowledge': distilled.get('structured_knowledge', {}),
                        'exam_dataset': distilled.get('evaluation_exam', [])
                    }
                    knowledge_packages.append(package)
                    
                    # Log beautiful summary
                    summary = format_distillation_summary(distilled, url)
                    logger.info(summary)
                    
                except Exception as e:
                    logger.error(f"[Distill {idx}/{len(search_results)}] Failed: {e}\n")
            else:
                error_msg = parse_result.get('error', 'Unknown error') if parse_result else 'Parse failed'
                logger.warning(f"Status: FAILED - {error_msg}\n")
            
            logger.info("-" * 80 + "\n")
        
        if not knowledge_packages:
            logger.warning("No knowledge packages were successfully distilled. Pipeline cannot continue.")
            sys.exit(0)
        
        logger.info(f"Successfully distilled {len(knowledge_packages)} knowledge packages\n")
        
        # Step 6.5: Run Ecosystem Auditor to check for density-based germination
        logger.info("[Step 6.5] Running Ecosystem Auditor for density-based germination check...")
        try:
            germinated_count = check_density_and_germinate()
            if germinated_count > 0:
                logger.info(f"[Auditor] {germinated_count} new specialists germinated during this run\n")
            else:
                logger.info("[Auditor] No new specialists germinated (critical mass not reached)\n")
        except Exception as e:
            logger.error(f"[Auditor] Density check failed: {e}\n")
        
    except Exception as e:
        logger.error(f"Search or extraction failed: {e}")
        sys.exit(1)
    
    # Step 7: Query the database to find the best expert profile based on Jaccard suitability match
    logger.info("[Step 7] Finding best expert based on Jaccard suitability match...")
    best_expert, suitability_score = find_best_expert(research_topic)
    
    if not best_expert:
        logger.error("No suitable expert found for evaluation.")
        sys.exit(1)
    
    logger.info(f"Best expert: {best_expert['name']} (ID: {best_expert['id']})")
    logger.info(f"Suitability score: {suitability_score:.2f}\n")
    
    # Step 8: Select the first knowledge package for evaluation
    test_package = knowledge_packages[0]
    logger.info(f"[Step 8] Selected knowledge package for evaluation:")
    logger.info(f"  Package ID: {test_package['id']}")
    logger.info(f"  Domain: {test_package['domain']}")
    logger.info(f"  Thesis: {test_package['thesis'][:100]}...\n")
    
    # Step 9: Invoke evaluate_expert_performance() to make the expert take the 5-question test
    logger.info("[Step 9] Running expert performance evaluation...")
    logger.info(f"Expert: {best_expert['name']} (ID: {best_expert['id']})")
    logger.info(f"Package: ID {test_package['id']}")
    logger.info("")
    
    try:
        evaluation_score = await evaluate_expert_performance(
            expert_id=best_expert['id'],
            package_id=test_package['id'],
            model_name=DISTILLATION_MODEL
        )
        
        logger.info(f"\n[Evaluation Result] Expert '{best_expert['name']}' scored {evaluation_score:.2f}\n")
        
        # Step 10: Apply EMA evolution based on evaluation results
        logger.info("[Step 10] Applying EMA evolution...")
        evolution_result = await apply_ema_evolution(
            expert_id=best_expert['id'],
            current_test_score=evaluation_score,
            alpha=0.2,
            change_reason="Performance evaluation test",
            package_id=test_package['id']
        )
        
        logger.info(f"\n[Evolution Result] Expert '{best_expert['name']}' score updated:")
        logger.info(f"  Old Score: {evolution_result['old_score']:.2f}")
        logger.info(f"  New Score: {evolution_result['new_score']:.2f}")
        logger.info(f"  Change: {evolution_result['change']:+.2f}")
        logger.info("")
        
    except Exception as e:
        logger.error(f"Evaluation or evolution failed: {e}")
        sys.exit(1)
    
    logger.info("=" * 80)
    logger.info("EVOLUTION TEST COMPLETED SUCCESSFULLY")
    logger.info("=" * 80)
    logger.info("Summary:")
    logger.info(f"  - Research Topic: {research_topic}")
    logger.info(f"  - Knowledge Packages Distilled: {len(knowledge_packages)}")
    logger.info(f"  - Best Expert: {best_expert['name']} (ID: {best_expert['id']})")
    logger.info(f"  - Evaluation Score: {evaluation_score:.2f}")
    logger.info(f"  - Final EMA Score: {evolution_result['new_score']:.2f}")
    logger.info("=" * 80 + "\n")
    
    return 0


if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Expert evaluation and EMA evolution test script"
    )
    parser.add_argument(
        "--topic",
        type=str,
        default="PostgreSQL query optimization",
        help="Research topic to process (default: 'PostgreSQL query optimization')"
    )
    args = parser.parse_args()

    # Set event loop policy for Windows
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        result = asyncio.run(main(args))
        sys.exit(result)
    except KeyboardInterrupt:
        logger.info("\nTest interrupted by user.")
        sys.exit(130)
    except Exception as e:
        logger.error(f"\nFatal error during execution: {e}")
        sys.exit(1)
