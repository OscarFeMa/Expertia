import os
from typing import List, Optional, FrozenSet
from pathlib import Path
from pydantic_settings import BaseSettings


class ExpertiaSettings(BaseSettings):
    model_config = {"env_file": ".env", "env_prefix": "EXPERTIA_", "extra": "ignore"}

    ollama_host: str = "localhost"
    ollama_port: int = 11434
    distillation_enabled: bool = True
    distillation_model: str = "qwen2.5:3b"
    llm_timeout: int = 60
    llm_temperature: float = 0.7
    llm_max_tokens: int = 1000
    llm_retry_max_attempts: int = 3
    llm_retry_initial_delay: float = 1.0

    search_delay_min: float = 2.5
    search_delay_max: float = 4.5
    max_results_per_search: int = 5
    search_timeout: int = 30
    parser_timeout: int = 30
    include_links: bool = True
    suitability_threshold: float = 0.85

    wikidata_dump_path: str = "E:/aria2-1.37.0-win-64bit-build1/latest-all.json.gz"
    wikidata_output_dir: str = "E:/expertia-data"
    wikidata_extraction_timeout_hours: float = 4.0
    wikidata_entity_api: str = "https://www.wikidata.org/w/api.php"
    wikidata_sparql_endpoint: str = "https://query.wikidata.org/sparql"
    wikidata_api_user_agent: str = "Expertia/1.0 (incubator) Python/3.12"
    wikidata_label_batch_size: int = 50

    subspecialist_threshold: int = 100
    max_subspecialists: int = 20
    max_cascade_entities: int = 50000
    subspecialist_cycle_interval: int = 10
    max_children_per_parent: int = 3

    reporting_interval_seconds: int = 3600
    cooldown_seconds: int = 10

    blocklist_labels: FrozenSet[str] = frozenset({
        "field of study", "academic discipline", "branch of science",
        "branch of biology", "branch of geology", "social system",
        "business", "profession", "medical specialty",
        "scientific discipline", "academic major", "interdisciplinary science",
    })
    blocklist_label_prefixes: FrozenSet[str] = frozenset({
        "branch of ", "field of ", "subclass of ", "type of ",
    })

    wikipedia_api_url: str = "https://en.wikipedia.org/w/api.php"
    wikipedia_user_agent: str = "Expertia/1.0 (https://github.com/OscarFeMa/Expertia) Python/3.12"


_SETTINGS = ExpertiaSettings()

BASE_DIR = Path(__file__).parent.parent
STORAGE_DIR = BASE_DIR / "storage"
LOGS_DIR = BASE_DIR / "logs"
PACKAGES_DIR = STORAGE_DIR / "packages"
REPORTS_DIR = STORAGE_DIR / "reports"
for d in (STORAGE_DIR, LOGS_DIR, PACKAGES_DIR, REPORTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

DATABASE_PATH = STORAGE_DIR / "incubator.db"
SEED_DIR = STORAGE_DIR / "seed"
SEED_DIR.mkdir(parents=True, exist_ok=True)

WIKIDATA_DUMP_PATH = Path(_SETTINGS.wikidata_dump_path)
WIKIDATA_OUTPUT_DIR = Path(_SETTINGS.wikidata_output_dir)
WIKIDATA_EXTRACTION_TIMEOUT_HOURS = _SETTINGS.wikidata_extraction_timeout_hours

OLLAMA_HOST = _SETTINGS.ollama_host
OLLAMA_PORT = _SETTINGS.ollama_port
OLLAMA_BASE_URL = f"http://{_SETTINGS.ollama_host}:{_SETTINGS.ollama_port}"
DISTILLATION_ENABLED = _SETTINGS.distillation_enabled
DISTILLATION_MODEL = _SETTINGS.distillation_model
LLM_TIMEOUT = _SETTINGS.llm_timeout
LLM_TEMPERATURE = _SETTINGS.llm_temperature
LLM_MAX_TOKENS = _SETTINGS.llm_max_tokens
LLM_RETRY_MAX_ATTEMPTS = _SETTINGS.llm_retry_max_attempts
LLM_RETRY_INITIAL_DELAY = _SETTINGS.llm_retry_initial_delay

SEARCH_DELAY_MIN = _SETTINGS.search_delay_min
SEARCH_DELAY_MAX = _SETTINGS.search_delay_max
MAX_RESULTS_PER_SEARCH = _SETTINGS.max_results_per_search
SEARCH_TIMEOUT = _SETTINGS.search_timeout
PARSER_TIMEOUT = _SETTINGS.parser_timeout
INCLUDE_LINKS = _SETTINGS.include_links
SUITABILITY_THRESHOLD = _SETTINGS.suitability_threshold

SUBSPECIALIST_THRESHOLD = _SETTINGS.subspecialist_threshold
MAX_SUBSPECIALISTS = _SETTINGS.max_subspecialists
SUBSPECIALIST_CYCLE_INTERVAL = _SETTINGS.subspecialist_cycle_interval
MAX_CHILDREN_PER_PARENT = _SETTINGS.max_children_per_parent
MAX_CASCADE_ENTITIES = _SETTINGS.max_cascade_entities
BLOCKLIST_LABELS = _SETTINGS.blocklist_labels
BLOCKLIST_LABEL_PREFIXES = _SETTINGS.blocklist_label_prefixes

WIKIDATA_ENTITY_API = _SETTINGS.wikidata_entity_api
WIKIDATA_SPARQL_ENDPOINT = _SETTINGS.wikidata_sparql_endpoint
WIKIDATA_API_USER_AGENT = _SETTINGS.wikidata_api_user_agent
WIKIDATA_LABEL_BATCH_SIZE = _SETTINGS.wikidata_label_batch_size

WIKIPEDIA_API_URL = _SETTINGS.wikipedia_api_url
WIKIPEDIA_USER_AGENT = _SETTINGS.wikipedia_user_agent

REPORTING_INTERVAL_SECONDS = _SETTINGS.reporting_interval_seconds
COOLDOWN_SECONDS = _SETTINGS.cooldown_seconds

USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
]

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
