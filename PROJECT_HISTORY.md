# Project History - Async Expert Incubator

## Chronology of Development and Evolution

### Phase 1: Initial Implementation (Pre-2026-05-23)
- **Foundation:** Established Async Expert Incubator as part of "Pensamiento Coral" ecosystem
- **Core Architecture:** Local-first AI multi-agent infrastructure with SQLite expert registry
- **Key Components:**
  - Local Expert Registry with keyword matching and suitability scoring
  - Safe Web Crawling via DuckDuckGo integration
  - Content Extraction using Trafilatura
  - Async Orchestration with native asyncio
  - Ollama integration for knowledge distillation (qwen2.5:3b model)
- **Expert Tiers:** Implemented 3-tier system (Ingestion, Consolidated, In-Training)
- **Database Schema:** Created expert_registry, knowledge_packages, processed_queries tables

### Phase 2: Autonomous Loop Implementation (Pre-2026-05-23)
- **Dynamic Query Generation:** Implemented Ollama-powered query generation
- **Ecosystem Auditor:** Added density-based specialist germination
- **Hourly Reporting:** Automated Markdown reports with operational metrics
- **Growth Control Mechanisms:**
  - Activation Buffer (threshold: 3 encounters)
  - Semantic Filtering and Deduplication
  - Semantic Clustering to prevent micro-specialization
  - Passive Pruning for frozen experts
- **Law of Critical Mass:** 5+ packages per sub-theme to trigger germination

### Phase 3: False Vacuum Bug Discovery (2026-05-23)
- **Issue:** "False Vacuum" bug in ecosystem_auditor.py
- **Root Cause:** Missing domain mapping between granular knowledge package domains and high-level core domains
- **Impact:** Specialists were not germinating correctly due to domain mismatch
- **Solution:** Implemented DOMAIN_MAPPING dictionary to map granular domains to core domains

### Phase 4: Exponential Growth Crisis (2026-05-23)
- **Discovery:** System created 186 specialists, then 107 specialists in 1 hour
- **User Feedback:** "Hay algo que falla, tenemos ahora mismo 186 especialistas" and "Algo esta fallando sigue gerenado especialistas de manera exponencial"
- **Root Cause:** Growth control mechanisms not loaded due to Python caching - running process not picking up updated code
- **Investigation:**
  - Created debug_specialists.py to analyze specialist state
  - Created cleanup_all_frozen.py to remove redundant specialists
  - Temporarily disabled germination (ACTIVATION_BUFFER_THRESHOLD = 999)
- **Initial Fix Attempt:** Set ACTIVATION_BUFFER_THRESHOLD to 999, but process still not loading updated code

### Phase 5: Hard Limits Implementation (2026-05-23)
- **User Decision:** "Tenemos que fijar un maximos de expertos y un maximo de especialistas"
- **Initial Limits:** MAX_TOTAL_EXPERTS = 50, MAX_SPECIALISTS_PER_DOMAIN = 10
- **User Refinement:** "quiero que se fijen un maximo de 15 expertos generales y como maximo 15 especialistas, por lo menos en fase automatica"
- **Final Limits:** MAX_TOTAL_EXPERTS = 30 (15 general + 15 specialists), MAX_SPECIALISTS_PER_DOMAIN = 5
- **Implementation:**
  - Added hard limit checks in check_density_and_germinate()
  - Per-domain limit verification before germination
  - Re-verification after each germination
  - Comprehensive logging of limit status

### Phase 6: Cleanup and Stabilization (2026-05-23)
- **Process Stop:** User stopped running process (Ctrl+C)
- **Database Cleanup:** Deleted 108 redundant specialists (from 114 to 6 experts)
- **System Restart:** Process restarted with hard limits active
- **Monitoring Results (6.5 hours):**
  - Total Knowledge Packages: 243 → 490 (+247)
  - Total Experts: 6 (stable, no new specialists)
  - All EMA scores increased (+0.10 to +0.31)
  - System rotating correctly between experts
  - No exponential growth detected

### Phase 7: Humanities Performance Analysis (2026-05-24)
- **Observation:** Humanities expert absorbing many packages (115 → 210) but EMA growing slowly (0.32 → 0.53)
- **User Hypothesis:** "Supongo que como humanidades depende demasiado de opinion es mas dificil generar conocimiendo contrastable"
- **Analysis:** Subjective nature of humanities knowledge makes objective evaluation difficult
- **Decision:** Continue monitoring, no immediate action required

### Phase 8: Hybrid Architecture Design (2026-05-24)
- **User Request:** "Analiza este prompt mejorado y dime si cumple con las expectaticas"
- **Architecture Proposal:**
  - Phase A (Local Ontological Base): Wikidata dissection via wdsub
  - Phase B (Live Web Delta): Web scraping as high-frequency updater
  - Goal: Establish structured knowledge base before releasing agents into web scraping loop
- **Technical Requirements:**
  - Cross-drive operations (D: for DB, E: for Wikidata)
  - wdsub tool for 142 GB Wikidata JSON processing
  - Streaming pipeline to avoid RAM bloat
  - Timeout handling and progress tracking
  - Fallback mechanism if wdsub unavailable

### Phase 9: Implementation of Hybrid Pipeline (2026-05-24)
- **Database Schema Update:** Added cartridge_offsets table with expert_id column
- **Script Development:** Created dissect_and_incubate.py (later renamed to hybrid_pipeline.py)
- **Key Functions Implemented:**
  - verify_wdsub_installed() - Pre-flight safety check
  - verify_disk_space() - Drive space verification
  - run_wdsub_with_timeout() - Streaming execution with timeout
  - update_inoculation_progress() - Progress tracking
  - handle_wdsub_failure() - Fallback mechanism
  - is_expert_inoculated() - State checking
  - spawn_new_specialist_blueprint() - Future specialist spawning
- **QID Mapping:** Implemented TAG_TO_QID_MAP for 6 core domains (Formal Sciences, Engineering, Economy, Legal, Humanities, Biology)

### Phase 10: wdsub Dependency Resolution (2026-05-24)
- **Issue:** wdsub not installed on host machine
- **User Decision:** "I explicitly reject Option 3. Parsing and uncompressing a 142 GB JSON dump in pure Python will be prohibitively slow"
- **Architecture Decision:** Maintain wdsub as core streaming extraction engine
- **Fallback Implementation:** Modified verify_wdsub_installed() to activate fallback for all experts if wdsub unavailable
- **Final Script:** hybrid_pipeline.py with graceful fallback to Phase B (Web Scraping)

### Phase 11: Documentation and Status (2026-05-24)
- **User Request:** "Genera un documento del estado actual del proyecto, borra estados anteriores y actualiza el README. Puedes generar un history, donde expongas toda la cronologia del poyecto."
- **Deliverables:**
  - PROJECT_STATUS.md - Current system state and configuration
  - PROJECT_HISTORY.md - Complete chronology (this document)
  - README.md update - Integration of new features

### Phase 12: Production Refactoring — Zero-RAM Wikidata, 15 Specialists, Centralized Config (2026-05-24)
- **Trigger:** wdsub abandoned (deprecated, no Windows binary, Scala dependency)
- **Replaced wdsub with native Python ijson+gzip streaming** → `dissect_wikidata.py`
  - Zero-RAM-bloat: streams 142GB dump without loading into memory
  - `WikidataStreamingExtractor` with optional `custom_matcher` callable
  - Gzip streaming decompression + ijson iterative parsing
  - Progress persisted to `cartridge_offsets` table
- **Thread-safe Singleton Database** → `database/db_manager.py`
  - `threading.RLock` double-checked locking pattern
  - `check_same_thread=False` for cross-thread access
  - Auto-reconnect on health check failure
  - Tables: `specialist_registry`, `cartridge_offsets`, `knowledge_packages`, `ema_history`
- **VRAM-aware LLM Manager** → `llm_manager.py`
  - Single-Active-Model policy (ollama stop/run)
  - `OfflineVerificationEngine` with 60s cache
  - `retry_with_exponential_backoff` decorator (3 retries, 2x backoff)
  - Async query via aiohttp
  - Configurable via `config.settings` (OLLAMA_HOST, OLLAMA_PORT, LLM_TIMEOUT, etc.)
- **Modern Web Scraper** → `web_scraper.py`
  - duckduckgo-search v9.14+ syntax (`DDGS().text()`)
  - trafilatura single-fetch extraction (no double-fetch bug)
  - Rate limit detection (HTTP 429), `apply_random_delay()` (2.5–4.5s)
  - Trust-based URL scoring (Tier 1/2/3)
- **15-Specialist Orchestrator** → `orchestrator.py`
  - `WIKIDATA_SCHEMAS` with 15 domains (SWE, Math, Medicine, Law, etc.)
  - `SPECIALIST_REGISTRY` with domain-specific models
  - `PipelineController` with Phase A (Wikidata) + Phase B (Web scraping + LLM distillation)
  - `MetricsCollector` for performance counters and summary reports
  - Fixed entity matching: exact root QID only (no false-positive property matching)
- **Centralized Configuration** → `config/settings.py`
  - Single source of truth for all paths, timeouts, limits, and model settings
  - All modules import from settings instead of hardcoding values
- **Metrics & Monitoring** → `metrics.py`
  - `PhaseAMetrics` / `PhaseBMetrics` dataclasses
  - Performance counters for entities processed/matched and web contents
  - Summary report printed at pipeline end
- **Code consolidation:**
  - Orchestrator now imports `WikidataStreamingExtractor` from `dissect_wikidata.py` (no duplication)
  - `ContentExtractor` single-fetch (removed redundant `trafilatura.fetch_url`)
  - `validate_paths()` creates output directory if missing
- **Bug fixes:**
  - Singleton: `__new__` captures `db_path` on first call; subsequent calls ignored
  - `db_manager.py` path hardcode replaced with `config.settings.DATABASE_PATH`
  - `dissect_wikidata.py` column `expert_id` → `specialist_id` (schema consistency)
  - Web scraper double-fetch eliminated (pass HTML directly to trafilatura)
  - `Set` import removed from orchestrator (unused)
- **Legacy code remains** (safe to remove after validation):
  - `crawler/search_engine.py` → superseded by `web_scraper.py`
  - `crawler/parser.py` → superseded by `web_scraper.py`
  - `crawler/ollama_manager.py` → superseded by `llm_manager.py`
  - `hybrid_pipeline.py` → superseded by `dissect_wikidata.py`
  - `auto_incubator.py`, `incubator_ingestion.py` → superseded by `orchestrator.py`
  - `database/connection.py`, `database/queries.py` → superseded by `db_manager.py`

## Technical Evolution Summary

### Database Schema Evolution
1. **Initial:** expert_registry, knowledge_packages, processed_queries
2. **Growth Control:** Added expert_creation_buffer table
3. **Wikidata Integration:** Added cartridge_offsets table with expert_id column

### Growth Control Evolution
1. **Initial:** Activation buffer (threshold: 3), semantic filtering, clustering, passive pruning
2. **Crisis Response:** Temporarily disabled (threshold: 999)
3. **Final Solution:** Hard limits (30 total, 5 per domain) + original mechanisms

### Architecture Evolution
1. **Phase 1:** Web scraping only
2. **Phase 2:** Autonomous loop with dynamic queries
3. **Phase 3:** Hybrid architecture (Wikidata + Web Scraping)

## Key Learnings

### Python Caching Issues
- Running processes may not pick up code changes immediately
- Requires explicit process restart for code updates to take effect
- Important for debugging and iterative development

### Growth Control Necessity
- Demand-driven creation alone insufficient for large-scale systems
- Hard limits essential to prevent exponential growth
- Per-domain limits prevent concentration in single areas

### Domain-Specific Evaluation Challenges
- Humanities and social sciences present unique evaluation challenges
- Subjective knowledge harder to assess objectively
- May require domain-specific evaluation criteria in future

### Hybrid Architecture Benefits
- Structured knowledge base provides foundation
- Web scraping provides continuous updates
- Fallback mechanisms ensure system resilience

## Current System Capabilities

### Active Features
- 15 Specialist architecture (SoftwareEngineering, Mathematics, Medicine, LegalSystem, etc.)
- Thread-safe SQLite Singleton for concurrent agent access
- Single-Active-Model VRAM policy (6GB limit)
- Zero-RAM-Bloat Wikidata extraction via ijson+gzip streaming
- Modern web scraping with DDGS v9.14+ + trafilatura single-fetch
- Dynamic EMA scoring (content length × trust score × match bonus)
- Exponential backoff retry logic (3 retries, 2x backoff)
- Centralized configuration (`config/settings.py`)
- Metrics collection and summary reporting
- Rate limiting (2.5–4.5s random delays) with HTTP 429 detection
- Path validation with auto-creation of output directories
- Progress persistence to database (`cartridge_offsets`)

### Ready for Deployment
- Full Phase A (Wikidata Dissection) execution — no wdsub required
- Phase B (Web scraping + LLM distillation) integrated
- Cross-drive operations configured (E: for data, D: for code)
- Fallback mechanism for extraction failures
- Comprehensive error handling with retry logic

### Pending Implementation
- Unit tests (db_manager, web_scraper, dissect_wikidata)
- Transitive P279 traversal for deeper Wikidata ontological matching
- Migration from legacy expert_registry to specialist_registry
- GitHub repository initialization
- Dashboard for real-time monitoring
- Removal/deprecation of legacy modules after validation
- Auto-pull fallback for Ollama models (missing models)

---
*History document generated automatically by Cascade*
