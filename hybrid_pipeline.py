"""
Hybrid Architecture Orchestrator Script - Phase 1: Knowledge Dissection

This script handles the local ontological base establishment before releasing 
agents into the active web scraping loop. It slices the 142 GB Wikidata source 
directly on the E: drive using wdsub, establishing foundational core knowledge 
graphs for each expert.

Architecture:
- Phase A (Local Ontological Base): Expert "eats" structured Wikidata taxonomy
- Phase B (Live Web Delta): Web scraping loop acts as high-frequency updater
"""

import time
import subprocess
import logging
import sqlite3
import shutil
from pathlib import Path
from typing import Union, List, Dict, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ============================================================================
# PATH CONFIGURATION
# ============================================================================

BRAIN_DB_PATH = Path("D:/proyectos/expertia/incubator-root/storage/incubator.db")
WIKIDATA_DUMP_PATH = Path("E:/aria2-1.37.0-win-64bit-build1/latest-all.json.gz")
TARGET_OUTPUT_DIR = Path("E:/expertia-data")

# ============================================================================
# WIKIDATA QID MAPPING
# ============================================================================

TAG_TO_QID_MAP: Dict[str, str] = {
    # Formal Sciences
    "mathematics": "Q395",
    "logic": "Q4091",
    "algorithms": "Q21198",
    "statistics": "Q39194",
    "computing": "Q11661",
    "formal": "Q11359",
    
    # Engineering
    "physics": "Q413",
    "mechanics": "Q1016",
    "chemistry": "Q2329",
    "industrial": "Q2329",
    "infrastructure": "Q38833",
    "materials": "Q38672",
    "software": "Q11661",
    
    # Economy
    "finance": "Q43015",
    "markets": "Q37654",
    "competition": "Q486975",
    "macroeconomics": "Q9102",
    "trade": "Q5272",
    "game_theory": "Q131193",
    
    # Legal
    "law": "Q362",
    "regulation": "Q1143825",
    "compliance": "Q188451",
    "policy": "Q373204",
    "standard": "Q163872",
    "oauth2": "Q2301042",
    
    # Humanities
    "history": "Q309",
    "geopolitics": "Q171408",
    "culture": "Q11042",
    "sociology": "Q192525",
    "society": "Q870",
    "empire": "Q1725",
    
    # Biology
    "health": "Q12147",
    "medicine": "Q11190",
    "environment": "Q7150",
    "ecology": "Q17999",
    "biochemistry": "Q1660",
    "organic": "Q23614"
}

# ============================================================================
# PRE-FLIGHT SAFETY CHECKS
# ============================================================================

def verify_wdsub_installed() -> bool:
    """Verify that wdsub is available in the system PATH."""
    try:
        result = subprocess.run(
            ["wdsub", "--version"],
            capture_output=True,
            check=True,
            timeout=10
        )
        logger.info("✅ wdsub is installed and accessible")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning(f"⚠️ wdsub is not installed or not accessible: {e}")
        logger.critical("⚠️ PHASE A (Wikidata Dissection) cannot proceed without wdsub.")
        logger.critical("⚠️ Please install wdsub: cargo install wdsub or download Windows binary")
        logger.critical("⚠️ Activating FALLBACK mechanism for all experts - Phase B (Web Scraping) will proceed")
        return False


def verify_disk_space(drive: str, required_gb: int) -> bool:
    """Verify that the drive has at least the required free space."""
    try:
        import shutil
        usage = shutil.disk_usage(f"{drive}:\\")
        free_gb = usage.free / (1024 ** 3)
        
        if free_gb >= required_gb:
            logger.info(f"✅ Drive {drive}: has {free_gb:.2f} GB free (required: {required_gb} GB)")
            return True
        else:
            logger.error(f"❌ Drive {drive}: has only {free_gb:.2f} GB free (required: {required_gb} GB)")
            return False
    except Exception as e:
        logger.error(f"❌ Failed to check disk space for drive {drive}: {e}")
        return False


def verify_target_directory() -> bool:
    """Verify and create target output directory if missing."""
    try:
        TARGET_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"✅ Target directory verified: {TARGET_OUTPUT_DIR}")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to create target directory: {e}")
        return False


# ============================================================================
# DATABASE OPERATIONS
# ============================================================================

def get_active_experts(db_path: Path = BRAIN_DB_PATH) -> List[Dict]:
    """Fetch active Tier 3 experts from the control database."""
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, name, core_domain, tags, tier
                FROM expert_registry
                WHERE tier = 3
                ORDER BY id
            """)
            
            experts = [dict(row) for row in cursor.fetchall()]
            logger.info(f"✅ Found {len(experts)} active Tier 3 experts")
            return experts
            
    except sqlite3.Error as e:
        logger.error(f"❌ Failed to fetch active experts: {e}")
        return []


def initialize_cartridge_tracking_table(db_path: Path = BRAIN_DB_PATH) -> bool:
    """Verify/initialize the cartridge_offsets tracking table."""
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Check if table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='cartridge_offsets'
            """)
            
            if not cursor.fetchone():
                logger.info("Creating cartridge_offsets table...")
                cursor.execute("""
                    CREATE TABLE cartridge_offsets (
                        qid TEXT PRIMARY KEY,
                        cartridge_name TEXT,
                        offset_start INTEGER,
                        offset_end INTEGER,
                        expert_id INTEGER,
                        status TEXT DEFAULT 'Available',
                        FOREIGN KEY (expert_id) REFERENCES expert_registry(id)
                    )
                """)
                
                cursor.execute("""
                    CREATE INDEX idx_cartridge_expert_id
                    ON cartridge_offsets(expert_id)
                """)
                
                conn.commit()
                logger.info("✅ cartridge_offsets table created")
            else:
                logger.info("✅ cartridge_offsets table already exists")
                
            return True
            
    except sqlite3.Error as e:
        logger.error(f"❌ Failed to initialize cartridge_offsets table: {e}")
        return False


def is_expert_inoculated(expert_id: int, db_path: Path = BRAIN_DB_PATH) -> bool:
    """
    Check if an expert has been inoculated with local Wikidata cartridge.
    Returns True if status is 'COMPLETED' or 'FALLBACK_TRIGGERED'.
    """
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT status FROM cartridge_offsets 
                WHERE expert_id = ?
            """, (expert_id,))
            
            result = cursor.fetchone()
            
            if not result:
                return False  # No record, not inoculated
            
            status = result[0]
            return status in ['COMPLETED', 'FALLBACK_TRIGGERED']
            
    except sqlite3.Error as e:
        logger.warning(f"Failed to check inoculation status for expert {expert_id}: {e}")
        return False


def update_inoculation_progress(
    expert_id: int, 
    progress_pct: Union[float, str], 
    db_path: Path = BRAIN_DB_PATH
) -> None:
    """Update the inoculation progress for an expert in the tracking table."""
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE cartridge_offsets 
                SET status = ?
                WHERE expert_id = ?
            """, (f"PROCESSING: {progress_pct}%", expert_id))
            
            conn.commit()
            
    except sqlite3.Error as e:
        # Don't break the script for a visual update failure
        logger.warning(f"Could not update progress for expert {expert_id}: {e}")


def handle_wdsub_failure(expert_id: int, db_path: Path = BRAIN_DB_PATH) -> None:
    """
    Activate fallback mechanism. If local inoculation fails, mark the expert
    so Phase B (Trafilatura/DuckDuckGo) can proceed immediately.
    """
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE cartridge_offsets 
                SET status = 'FALLBACK_TRIGGERED' 
                WHERE expert_id = ?
            """, (expert_id,))
            
            conn.commit()
            
        logger.warning(f"🚨 Expert {expert_id} marked as FALLBACK_TRIGGERED. Web gate opened for safety.")
        
    except sqlite3.Error as e:
        logger.critical(f"Failed to register fallback for expert {expert_id}: {e}")


# ============================================================================
# WDUB SCHEMA GENERATION
# ============================================================================

def generate_wdsub_schema(tags: List[str], expert_id: int, domain: str) -> Path:
    """Generate a dynamic wdsub schema JSON for an expert."""
    import json
    
    # Map tags to QIDs
    qids = []
    for tag in tags:
        tag_lower = tag.lower().strip()
        if tag_lower in TAG_TO_QID_MAP:
            qids.append(TAG_TO_QID_MAP[tag_lower])
    
    if not qids:
        logger.warning(f"No QIDs found for tags: {tags}")
        qids = ["Q5"]  # Fallback to "human" if no tags match
    
    # Create schema configuration
    schema = {
        "properties": ["P31", "P279"],  # instance of, subclass of
        "targets": qids
    }
    
    # Save schema to temporary file
    schema_filename = f"schema_expert_{expert_id}_{domain}.json"
    schema_path = TARGET_OUTPUT_DIR / schema_filename
    
    with open(schema_path, 'w', encoding='utf-8') as f:
        json.dump(schema, f, indent=2)
    
    logger.info(f"✅ Generated wdsub schema: {schema_filename}")
    return schema_path


# ============================================================================
# WDUB EXECUTION WITH TIMEOUT
# ============================================================================

def run_wdsub_with_timeout(
    schema_path: Path,
    output_path: Path,
    input_dump: Path,
    expert_id: int,
    timeout_hours: float = 4.0
) -> bool:
    """
    Execute wdsub in streaming with a maximum hour limit.
    Captures output to update progress in the database.
    """
    timeout_seconds = timeout_hours * 3600
    start_time = time.time()
    
    command = [
        "wdsub",
        "-i", str(input_dump),
        "-s", str(schema_path),
        "-o", str(output_path)
    ]
    
    logger.info(f"[Expert {expert_id}] Starting dissection. Timeout set to {timeout_hours} hours.")
    
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding='utf-8',
            errors='replace'
        )
        
        if process.stdout:
            for line in process.stdout:
                clean_line = line.strip()
                
                if clean_line:
                    logger.info(f"[wdsub - Expert {expert_id}] {clean_line}")
                    
                    # Parse line for progress percentage if available
                    if "progress" in clean_line.lower() or "%" in clean_line:
                        try:
                            # Simple percentage extraction
                            import re
                            pct_match = re.search(r'(\d+)%', clean_line)
                            if pct_match:
                                pct = int(pct_match.group(1))
                                update_inoculation_progress(expert_id, pct)
                        except:
                            pass
                
                # Defense: Check execution time on each iteration
                if (time.time() - start_time) > timeout_seconds:
                    logger.critical(f"[Expert {expert_id}] ⏱️ TIMEOUT REACHED ({timeout_hours}h). Killing subprocess...")
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()  # Summary execution if it resists
                    return False
                    
        process.wait()
        
        if process.returncode == 0:
            logger.info(f"[Expert {expert_id}] ✅ Cartridge generated successfully.")
            return True
        else:
            logger.error(f"[Expert {expert_id}] ❌ Error in wdsub (Code {process.returncode})")
            return False
            
    except Exception as e:
        logger.error(f"[Expert {expert_id}] Critical failure launching wdsub: {e}", exc_info=True)
        return False


# ============================================================================
# SPECIALIST SPAWNING BLUEPRINT
# ============================================================================

def spawn_new_specialist_blueprint(domain: str, tags: List[str]) -> Optional[int]:
    """
    Placeholder function to spawn a new Tier 3 specialist agent.
    This will allow the system to programmatically birth new agents
    whenever a new target cartridge is generated in the future.
    
    Args:
        domain: The core domain for the new specialist
        tags: List of tags for the new specialist
        
    Returns:
        Optional[int]: The ID of the newly created specialist, or None if failed
    """
    try:
        with sqlite3.connect(BRAIN_DB_PATH) as conn:
            cursor = conn.cursor()
            
            # Generate specialist name
            specialist_name = f"{domain} Specialist"
            
            # Insert new specialist
            cursor.execute("""
                INSERT INTO expert_registry (
                    name, core_domain, tags, ema_score, tier, packages_absorbed
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (specialist_name, domain, ",".join(tags), 0.10, 3, 0))
            
            specialist_id = cursor.lastrowid
            conn.commit()
            
            logger.info(f"✅ Spawned new specialist: {specialist_name} (ID: {specialist_id})")
            return specialist_id
            
    except sqlite3.Error as e:
        logger.error(f"❌ Failed to spawn new specialist: {e}")
        return None


# ============================================================================
# MAIN ORCHESTRATION
# ============================================================================

def main():
    """Main orchestration function for Phase 1: Knowledge Dissection."""
    logger.info("=" * 80)
    logger.info("HYBRID PIPELINE - PHASE 1: KNOWLEDGE DISSECTION")
    logger.info("=" * 80 + "\n")

    # Pre-flight safety checks
    logger.info("[Pre-Flight] Running safety checks...")

    wdsub_available = verify_wdsub_installed()

    if wdsub_available:
        if not verify_disk_space("E", 50):
            logger.critical("❌ Insufficient disk space on E:. Aborting.")
            return

        if not verify_target_directory():
            logger.critical("❌ Failed to verify target directory. Aborting.")
            return
    else:
        logger.warning("⚠️ Skipping disk space and directory checks (Phase A disabled)")

    if not initialize_cartridge_tracking_table():
        logger.critical("❌ Failed to initialize tracking table. Aborting.")
        return

    # Fetch active experts
    logger.info("\n[Database] Fetching active Tier 3 experts...")
    experts = get_active_experts()

    if not experts:
        logger.warning("No active experts found. Aborting.")
        return

    # Process each expert
    logger.info(f"\n[Orchestration] Processing {len(experts)} experts...\n")

    for expert in experts:
        expert_id = expert['id']
        domain = expert['core_domain']
        tags = expert['tags'].split(',') if expert['tags'] else []

        logger.info(f"\n{'=' * 60}")
        logger.info(f"Processing Expert: {expert['name']} (ID: {expert_id})")
        logger.info(f"Domain: {domain}")
        logger.info(f"Tags: {tags}")
        logger.info(f"{'=' * 60}")

        # Check if already inoculated
        if is_expert_inoculated(expert_id):
            logger.info(f"✅ Expert {expert_id} already inoculated. Skipping.")
            continue

        # If wdsub is not available, activate fallback immediately
        if not wdsub_available:
            logger.warning(f"⚠️ wdsub not available. Activating fallback for expert {expert_id}")
            handle_wdsub_failure(expert_id)
            continue

        # Generate wdsub schema
        schema_path = generate_wdsub_schema(tags, expert_id, domain)

        # Define output cartridge path
        cartridge_filename = f"cartridge_{domain}.json.gz"
        cartridge_path = TARGET_OUTPUT_DIR / cartridge_filename

        # Initialize tracking record
        try:
            with sqlite3.connect(BRAIN_DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO cartridge_offsets
                    (qid, cartridge_name, expert_id, status)
                    VALUES (?, ?, ?, ?)
                """, (f"expert_{expert_id}", cartridge_filename, expert_id, "PROCESSING: 0%"))
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize tracking record: {e}")

        # Update progress to 0%
        update_inoculation_progress(expert_id, "0.0")

        # Execute wdsub with timeout
        success = run_wdsub_with_timeout(
            schema_path=schema_path,
            output_path=cartridge_path,
            input_dump=WIKIDATA_DUMP_PATH,
            expert_id=expert_id,
            timeout_hours=4.0
        )

        # Clean up temporary schema file
        try:
            schema_path.unlink()
            logger.info(f"✅ Cleaned up schema file: {schema_path.name}")
        except Exception as e:
            logger.warning(f"Failed to clean up schema file: {e}")

        # Update final status
        if success:
            update_inoculation_progress(expert_id, "COMPLETED")
            logger.info(f"✅ Expert {expert_id} inoculation completed successfully.")
        else:
            handle_wdsub_failure(expert_id)
            logger.warning(f"⚠️ Expert {expert_id} inoculation failed. Fallback activated.")

    logger.info("\n" + "=" * 80)
    logger.info("HYBRID PIPELINE COMPLETE")
    logger.info("=" * 80)
    logger.info("\nNext Step: Phase B (Live Web Delta) can now proceed.")
    logger.info("Experts with 'COMPLETED' status will skip web scraping.")
    logger.info("Experts with 'FALLBACK_TRIGGERED' will proceed with web scraping.\n")


if __name__ == "__main__":
    main()
