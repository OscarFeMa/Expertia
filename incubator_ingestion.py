"""Main orchestration script for Async Expert Incubator.

This script acts as the master asynchronous pipeline that coordinates:
- Local Registry Audit
- Web search and scraping
- Knowledge package preparation

It uses native asyncio for efficient sequential execution of web operations
to prevent VRAM/RAM collisions with local LLM inference.
"""

import asyncio
import logging
import sys
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from database.queries import audit_registry, add_knowledge_package, find_best_expert
from crawler.search_engine import LibrarianScraper, search_topic
from crawler.parser import ContentParser, extract_clean_markdown
from crawler.distiller import distill_markdown_with_ollama, format_distillation_summary
from crawler.ollama_manager import ensure_ollama_model_exists
from config.settings import (
    STORAGE_DIR,
    LOGS_DIR,
    MAX_RESULTS_PER_SEARCH,
    SUITABILITY_THRESHOLD,
    DISTILLATION_ENABLED,
    DISTILLATION_MODEL
)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / f"incubator_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class IncubatorOrchestrator:
    """Master orchestrator for the Async Expert Incubator pipeline.
    
    This class coordinates the entire workflow from research topic input
    to knowledge package generation, with intelligent registry checks,
    safe web scraping, and LLM-powered knowledge distillation.
    """
    
    def __init__(self, use_distillation: bool = True, model_name: str = "qwen2.5:3b"):
        """Initialize the orchestrator with required components.
        
        Args:
            use_distillation: Whether to use LLM distillation (default: True).
            model_name: Ollama model name for distillation (default: "qwen2.5:3b").
        """
        self.scraper = LibrarianScraper()
        self.parser = ContentParser()
        self.use_distillation = use_distillation
        self.model_name = model_name
        self.knowledge_packages: List[Dict[str, str]] = []
        self.distilled_packages: List[Dict] = []
    
    async def run_pipeline(self, research_topic: str) -> Dict[str, any]:
        """Execute the complete incubator pipeline.
        
        Args:
            research_topic: The research topic to process.
            
        Returns:
            Dict[str, any]: Pipeline execution results including status,
                           expert found (if any), and knowledge packages.
        """
        logger.info("=" * 80)
        logger.info("ASYNC EXPERT INCUBATOR - PIPELINE START")
        logger.info("=" * 80)
        logger.info(f"Research Topic: {research_topic}")
        logger.info("=" * 80 + "\n")
        
        # Step A: Accept Research Topic (already provided as parameter)
        logger.info("[Step A] Research topic received\n")
        
        # Step B: Run Local Registry Audit
        logger.info("[Step B] Running Local Registry Audit...\n")
        should_halt, best_expert, suitability_score = audit_registry(research_topic)
        
        # Reinforce expert suitability check using find_best_expert
        logger.info("[Orchestrator] Checking expert suitability with Jaccard + EMA formula...\n")
        reinforced_best_expert, reinforced_score = find_best_expert(research_topic)
        
        # Check if we should halt execution based on reinforced check
        if reinforced_score > SUITABILITY_THRESHOLD and reinforced_best_expert:
            expert_name = reinforced_best_expert['name']
            logger.info(f"[Orchestrator] Optimal expert '{expert_name}' already exists with Suitability Score {reinforced_score:.2f}. Halting web ingestion.\n")
            print(f"[Orchestrator] Optimal expert '{expert_name}' already exists with Suitability Score {reinforced_score:.2f}. Halting web ingestion.\n")
            return {
                'status': 'halted',
                'reason': 'optimal_expert_found',
                'expert': reinforced_best_expert,
                'suitability_score': reinforced_score,
                'knowledge_packages': [],
                'distilled_packages': []
            }
        
        # Step C: Proceed with web ingestion
        logger.info("[Step C] Proceeding with web ingestion...\n")
        logger.info(f"Best expert score: {reinforced_score:.2f} (below threshold {SUITABILITY_THRESHOLD})\n")
        
        # Use the reinforced expert and score for consistency
        best_expert = reinforced_best_expert
        suitability_score = reinforced_score
        
        # Search for the topic
        logger.info(f"[Search] Initiating search for: '{research_topic}'")
        try:
            search_results = await self.scraper.search(research_topic, max_results=MAX_RESULTS_PER_SEARCH)
            
            if not search_results:
                logger.warning("[Search] No results found. Pipeline completed with no content.\n")
                return {
                    'status': 'completed',
                    'reason': 'no_search_results',
                    'expert': best_expert,
                    'suitability_score': suitability_score,
                    'knowledge_packages': []
                }
            
            logger.info(f"[Search] Found {len(search_results)} URLs to process\n")
            
            # Scrape URLs sequentially
            logger.info("[Scrape] Starting sequential URL processing...\n")
            for idx, result in enumerate(search_results, 1):
                url = result['href']
                title = result.get('title', 'Untitled')
                logger.info(f"[Scrape {idx}/{len(search_results)}] Processing: {title}")
                logger.info(f"[Scrape {idx}/{len(search_results)}] URL: {url}")
                
                # Parse the URL
                parse_result = await self.parser.parse(url)
                
                if parse_result and parse_result['status'] == 'success':
                    markdown_content = parse_result['markdown']
                    
                    # Save the raw knowledge package
                    package = {
                        'url': url,
                        'title': title,
                        'markdown': markdown_content,
                        'timestamp': datetime.now().isoformat()
                    }
                    self.knowledge_packages.append(package)
                    logger.info(f"[Scrape {idx}/{len(search_results)}] Successfully parsed and saved\n")
                    
                    # Perform knowledge distillation if enabled
                    if self.use_distillation:
                        logger.info(f"[Distill {idx}/{len(search_results)}] Starting LLM knowledge distillation...")
                        try:
                            distilled = await distill_markdown_with_ollama(
                                markdown_content,
                                model_name=self.model_name
                            )
                            
                            # Save distilled package to database
                            domain = distilled.get('domain_classification', 'Unknown')
                            thesis = distilled.get('thesis_or_core_objective', 'Not provided')
                            
                            package_id = add_knowledge_package(
                                topic=research_topic,
                                source_url=url,
                                domain=domain,
                                structured_knowledge=distilled.get('structured_knowledge', {}),
                                exam_dataset=distilled.get('evaluation_exam', [])
                            )
                            
                            # Store distilled package
                            distilled_package = {
                                'id': package_id,
                                'url': url,
                                'title': title,
                                'domain': domain,
                                'thesis': thesis,
                                'structured_knowledge': distilled.get('structured_knowledge', {}),
                                'exam_dataset': distilled.get('evaluation_exam', []),
                                'timestamp': datetime.now().isoformat()
                            }
                            self.distilled_packages.append(distilled_package)
                            
                            # Log beautiful summary
                            summary = format_distillation_summary(distilled, url)
                            logger.info(summary)
                            
                        except Exception as e:
                            logger.error(f"[Distill {idx}/{len(search_results)}] Failed: {e}\n")
                    else:
                        logger.info(f"[Scrape {idx}/{len(search_results)}] Distillation disabled, skipping LLM processing\n")
                else:
                    error_msg = parse_result.get('error', 'Unknown error') if parse_result else 'Parse failed'
                    logger.warning(f"[Scrape {idx}/{len(search_results)}] Failed: {error_msg}\n")
            
            # Summary
            stats = self.parser.get_stats()
            logger.info("=" * 80)
            logger.info("PIPELINE COMPLETION SUMMARY")
            logger.info("=" * 80)
            logger.info(f"Total URLs processed: {stats['total']}")
            logger.info(f"Successful extractions: {stats['success']}")
            logger.info(f"Raw knowledge packages generated: {len(self.knowledge_packages)}")
            if self.use_distillation:
                logger.info(f"Distilled knowledge packages: {len(self.distilled_packages)}")
            logger.info("=" * 80 + "\n")
            
            return {
                'status': 'completed',
                'reason': 'web_ingestion_complete',
                'expert': best_expert,
                'suitability_score': suitability_score,
                'knowledge_packages': self.knowledge_packages,
                'distilled_packages': self.distilled_packages,
                'search_stats': stats
            }
            
        except Exception as e:
            logger.error(f"[Pipeline Error] Exception during web ingestion: {e}\n")
            return {
                'status': 'error',
                'reason': 'pipeline_exception',
                'error': str(e),
                'expert': best_expert,
                'suitability_score': suitability_score,
                'knowledge_packages': self.knowledge_packages,
                'distilled_packages': self.distilled_packages
            }
    
    def save_knowledge_packages(self, output_dir: Optional[Path] = None) -> List[str]:
        """Save knowledge packages to markdown files.
        
        Args:
            output_dir: Directory to save files (default: STORAGE_DIR / 'packages').
            
        Returns:
            List[str]: List of saved file paths.
        """
        if output_dir is None:
            output_dir = STORAGE_DIR / "packages"
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        saved_files = []
        for idx, package in enumerate(self.knowledge_packages, 1):
            filename = f"package_{idx:03d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            filepath = output_dir / filename
            
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(f"# {package['title']}\n\n")
                    f.write(f"**Source URL:** {package['url']}\n\n")
                    f.write(f"**Extracted:** {package['timestamp']}\n\n")
                    f.write("---\n\n")
                    f.write(package['markdown'])
                
                saved_files.append(str(filepath))
                logger.info(f"Saved knowledge package: {filepath}")
            except Exception as e:
                logger.error(f"Failed to save package {idx}: {e}")
        
        return saved_files


async def main():
    """Main entry point for the Async Expert Incubator.
    
    This function demonstrates the complete pipeline with a test case
    for "PostgreSQL query optimization" including a live connectivity test.
    """
    # Verify Ollama service and model availability
    logger.info("\n" + "=" * 80)
    logger.info("OLLAMA GUARD - SERVICE VERIFICATION")
    logger.info("=" * 80)
    try:
        await ensure_ollama_model_exists(model_name="qwen2.5:3b")
    except Exception as e:
        logger.error(f"Ollama verification failed: {e}")
        logger.error("Please ensure Ollama is running on your system before proceeding.")
        return {'status': 'error', 'reason': 'ollama_not_available', 'error': str(e)}
    
    # Live connectivity test
    logger.info("\n" + "=" * 80)
    logger.info("LIVE CONNECTIVITY TEST")
    logger.info("=" * 80)
    
    # Accept the search topic
    research_topic = "PostgreSQL query optimization"
    logger.info(f"Research Topic: {research_topic}")
    logger.info("=" * 80 + "\n")
    
    # Execute search_topic to retrieve top 3 live URLs
    logger.info("[Step 1] Executing search_topic() to retrieve top 3 URLs...")
    try:
        search_results = await search_topic(query=research_topic, max_results=3)
        
        if not search_results:
            logger.warning("[Step 1] No search results found. Connectivity test failed.")
            return {'status': 'error', 'reason': 'no_search_results'}
        
        logger.info(f"[Step 1] Successfully retrieved {len(search_results)} URLs\n")
        
        # Loop through URLs sequentially and asynchronously
        logger.info("[Step 2] Processing URLs sequentially with extract_clean_markdown()...")
        logger.info("=" * 80 + "\n")
        
        for idx, result in enumerate(search_results, 1):
            url = result['url']
            title = result.get('title', 'Untitled')
            
            logger.info(f"[Processing {idx}/{len(search_results)}]")
            logger.info(f"Title: {title}")
            logger.info(f"URL: {url}")
            
            # Call extract_clean_markdown for each link
            markdown_content = extract_clean_markdown(url)
            
            if markdown_content:
                # Display first 300 characters to verify data structural integrity
                preview = markdown_content[:300]
                logger.info(f"Status: SUCCESS")
                logger.info(f"Markdown Preview (first 300 chars):\n{preview}...\n")
            else:
                logger.warning(f"Status: FAILED - Could not extract content\n")
            
            logger.info("-" * 80 + "\n")
        
        logger.info("=" * 80)
        logger.info("CONNECTIVITY TEST COMPLETED")
        logger.info("=" * 80 + "\n")
        
    except Exception as e:
        logger.error(f"[Connectivity Test Error] Exception during execution: {e}\n")
        return {'status': 'error', 'reason': 'connectivity_test_exception', 'error': str(e)}
    
    # Initialize orchestrator for full pipeline
    # Use DISTILLATION_ENABLED from config settings
    orchestrator = IncubatorOrchestrator(use_distillation=DISTILLATION_ENABLED, model_name=DISTILLATION_MODEL)
    
    logger.info("\n" + "=" * 80)
    logger.info("ASYNC EXPERT INCUBATOR - DEMO EXECUTION")
    logger.info("=" * 80)
    logger.info(f"Test Topic: {research_topic}")
    logger.info(f"Distillation Enabled: {orchestrator.use_distillation}")
    if orchestrator.use_distillation:
        logger.info(f"LLM Model: {orchestrator.model_name}")
    logger.info("=" * 80 + "\n")
    
    # Run the pipeline
    result = await orchestrator.run_pipeline(research_topic)
    
    # Display results
    logger.info("\n" + "=" * 80)
    logger.info("FINAL PIPELINE RESULT")
    logger.info("=" * 80)
    logger.info(f"Status: {result['status']}")
    logger.info(f"Reason: {result['reason']}")
    if result.get('expert'):
        logger.info(f"Best Expert: {result['expert']['name']}")
    logger.info(f"Suitability Score: {result['suitability_score']:.2f}")
    logger.info(f"Raw Knowledge Packages: {len(result['knowledge_packages'])}")
    logger.info(f"Distilled Knowledge Packages: {len(result.get('distilled_packages', []))}")
    
    if result['status'] == 'completed' and result['knowledge_packages']:
        # Save knowledge packages
        saved_files = orchestrator.save_knowledge_packages()
        logger.info(f"\nSaved {len(saved_files)} raw knowledge package files:")
        for filepath in saved_files:
            logger.info(f"  - {filepath}")
    
    if result['status'] == 'completed' and result.get('distilled_packages'):
        logger.info(f"\nDistilled packages saved to database:")
        for pkg in result['distilled_packages']:
            logger.info(f"  - ID: {pkg['id']} | Domain: {pkg['domain']} | Thesis: {pkg['thesis'][:50]}...")
    
    logger.info("=" * 80 + "\n")
    
    return result


if __name__ == "__main__":
    # Run the async main function
    try:
        result = asyncio.run(main())
        sys.exit(0 if result['status'] in ['completed', 'halted'] else 1)
    except KeyboardInterrupt:
        logger.info("\nPipeline interrupted by user.")
        sys.exit(130)
    except Exception as e:
        logger.error(f"\nFatal error in main execution: {e}")
        sys.exit(1)
