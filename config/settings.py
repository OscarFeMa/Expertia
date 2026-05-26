"""
Centralized Configuration for Coral Thought Ecosystem.

All configurable parameters live here. Every module imports from this
single source of truth instead of hardcoding paths or values.
"""

import os
from typing import List, Optional
from pathlib import Path


# ============================================================================
# BASE PATHS
# ============================================================================

BASE_DIR = Path(__file__).parent.parent
STORAGE_DIR = BASE_DIR / "storage"
LOGS_DIR = BASE_DIR / "logs"
PACKAGES_DIR = STORAGE_DIR / "packages"
REPORTS_DIR = STORAGE_DIR / "reports"

# Ensure directories exist
for d in (STORAGE_DIR, LOGS_DIR, PACKAGES_DIR, REPORTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ============================================================================
# DATABASE
# ============================================================================

DATABASE_PATH = STORAGE_DIR / "incubator.db"

# ============================================================================
# WIKIDATA (Phase A)
# ============================================================================

WIKIDATA_DUMP_PATH = Path("E:/aria2-1.37.0-win-64bit-build1/latest-all.json.gz")
WIKIDATA_OUTPUT_DIR = Path("E:/expertia-data")
WIKIDATA_EXTRACTION_TIMEOUT_HOURS = 4.0

# ============================================================================
# OLLAMA / LLM
# ============================================================================

OLLAMA_HOST = "localhost"
OLLAMA_PORT = 11434
OLLAMA_BASE_URL = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}"

DISTILLATION_ENABLED = True
DISTILLATION_MODEL = "qwen2.5:3b"

# LLM query defaults
LLM_TIMEOUT = 60
LLM_TEMPERATURE = 0.7
LLM_MAX_TOKENS = 1000
LLM_RETRY_MAX_ATTEMPTS = 3
LLM_RETRY_INITIAL_DELAY = 1.0

# ============================================================================
# SEARCH ENGINE (Phase B)
# ============================================================================

SEARCH_DELAY_MIN = 2.5
SEARCH_DELAY_MAX = 4.5
MAX_RESULTS_PER_SEARCH = 5
SEARCH_TIMEOUT = 30

# Wikipedia API fallback
WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_USER_AGENT = "Expertia/1.0 (https://github.com/OscarFeMa/Expertia) Python/3.12"

# Seed URLs directory (last-resort fallback)
SEED_DIR = STORAGE_DIR / "seed"
SEED_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
]

# ============================================================================
# PARSER
# ============================================================================

PARSER_TIMEOUT = 30
INCLUDE_LINKS = True

# ============================================================================
# SUITABILITY SCORING
# ============================================================================

SUITABILITY_THRESHOLD = 0.85

# ============================================================================
# SUB-SPECIALIST SPAWNING
# ============================================================================

SUBSPECIALIST_THRESHOLD = 100       # min packages per sub-QID to spawn
MAX_SUBSPECIALISTS = 20             # absolute cap on sub-specialists
SUBSPECIALIST_CYCLE_INTERVAL = 10   # process child every N parent cycles
MAX_CHILDREN_PER_PARENT = 3         # max children spawned per specialist per cycle

# Labels whose QIDs should never spawn as sub-specialists (catch-all drawer)
BLOCKLIST_LABELS = frozenset({
    "field of study", "academic discipline", "branch of science",
    "branch of biology", "branch of geology", "social system",
    "business", "profession", "medical specialty",
    "scientific discipline", "academic major", "interdisciplinary science",
})
BLOCKLIST_LABEL_PREFIXES = frozenset({
    "branch of ", "field of ", "subclass of ", "type of ",
})

# Wikidata API endpoints
WIKIDATA_ENTITY_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
WIKIDATA_API_USER_AGENT = "Expertia/1.0 (incubator) Python/3.12"
WIKIDATA_LABEL_BATCH_SIZE = 50  # max QIDs per wbgetentities request

# ============================================================================
# METRICS / MONITORING
# ============================================================================

REPORTING_INTERVAL_SECONDS = 3600  # 60 minutes
COOLDOWN_SECONDS = 10

# ============================================================================
# LOGGING
# ============================================================================

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
