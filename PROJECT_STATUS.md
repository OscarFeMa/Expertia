# Project Status - Async Expert Incubator

**Last Updated:** 2026-05-24

## Current System State

### Active Components
- **6 General Pillar Experts** (Tier 3) operating with hard limits
- **Hybrid Pipeline** implemented (Phase A: Wikidata + Phase B: Web Scraping)
- **Growth Control** active (MAX_TOTAL_EXPERTS = 30, MAX_SPECIALISTS_PER_DOMAIN = 5)
- **Autonomous Loop** running with dynamic query generation
- **Hourly Reporting** operational

### Expert Ecosystem Status (2026-05-24 05:43)
- **Total Experts:** 6 (all Tier 3)
- **Total Knowledge Packages:** 490
- **Total EMA History Entries:** 166

**Expert Performance:**
1. Legal & Regulatory Advisor - EMA: 0.66, Packages: 46
2. Life Sciences & Biologist - EMA: 0.60, Packages: 2
3. Formal Logic & Mathematics Expert - EMA: 0.60, Packages: 22
4. Engineering & Applied Sciences Expert - EMA: 0.59, Packages: 52
5. Economic & Market Strategist - EMA: 0.59, Packages: 173
6. Humanities & Historical Analyst - EMA: 0.53, Packages: 210

### Database Schema Updates
- **cartridge_offsets table** added for Wikidata dissection tracking
- **expert_id column** added to cartridge_offsets for expert-level tracking
- **Status tracking:** Available, PROCESSING, COMPLETED, FALLBACK_TRIGGERED

### Growth Control Configuration
- **MAX_TOTAL_EXPERTS:** 30 (15 general + 15 specialists)
- **MAX_SPECIALISTS_PER_DOMAIN:** 5
- **ACTIVATION_BUFFER_THRESHOLD:** 999 (temporarily disabled)
- **CRITICAL_MASS_THRESHOLD:** 5
- **FROZEN_EXPERT_THRESHOLD_HOURS:** 10

### Integration Status
- **hybrid_pipeline.py** implemented and ready
- **wdsub dependency** required for Phase A (Wikidata Dissection)
- **Fallback mechanism** active for Phase B (Web Scraping)
- **Cross-drive operations** configured (D: for DB, E: for Wikidata)

## Recent Achievements

### Exponential Growth Issue Resolved (2026-05-23)
- **Problem:** System created 100+ redundant specialists in 1 hour
- **Root Cause:** Growth control mechanisms not loaded due to Python caching
- **Solution:** 
  - Implemented hard limits (30 total, 5 per domain)
  - Cleaned up 108 redundant specialists
  - Restarted process with updated code
- **Result:** Stable operation with 6 General Pillars, no exponential growth

### Hybrid Architecture Implementation (2026-05-24)
- **Phase A (Local Ontological Base):** Wikidata dissection via wdsub
- **Phase B (Live Web Delta):** Web scraping as high-frequency updater
- **Integration:** Seamless fallback mechanism if wdsub unavailable
- **Benefits:** Structured knowledge base + continuous web updates

## System Architecture

### Current Pipeline Flow
1. **Ecosystem Auditor** checks density and germination (with hard limits)
2. **Hybrid Pipeline** (optional) establishes local Wikidata base
3. **Autonomous Loop** selects expert with lowest EMA
4. **Dynamic Query Generation** via Ollama (qwen2.5:3b)
5. **Evolution Pipeline** processes web content
6. **EMA Evaluation** updates expert performance scores
7. **Hourly Reporting** generates operational metrics

### Storage Architecture
- **D:\proyectos\expertia\incubator-root\** - Application code and database
- **E:\aria2-1.37.0-win-64bit-build1\** - Wikidata dump (142 GB)
- **E:\expertia-data\** - Target zone for sliced Wikidata cartridges

## Technical Stack

### Core Technologies
- **Python 3.10+** on Windows 11 (Native, NO Docker, NO WSL)
- **SQLite** for expert registry and tracking
- **Ollama** with qwen2.5:3b model for query generation
- **DuckDuckGo** for web search
- **Trafilatura** for HTML-to-Markdown conversion
- **wdsub** (planned) for Wikidata subsetting

### Key Dependencies
- asyncio for async orchestration
- httpx for HTTP requests
- ijson (planned) for JSON streaming
- subprocess for external tool integration

## Known Issues & Observations

### Humanities Domain Performance
- **Observation:** Humanities expert absorbs many packages but EMA grows slowly
- **Hypothesis:** Subjective nature of humanities knowledge makes objective evaluation difficult
- **Status:** Under monitoring, no immediate action required

### wdsub Installation
- **Status:** Not yet installed on host machine
- **Action Required:** Manual installation via `cargo install wdsub` or Windows binary
- **Fallback:** System automatically activates Phase B if wdsub unavailable

## Next Steps

### Immediate
1. Install wdsub tool on host machine
2. Test hybrid_pipeline.py with small dataset
3. Verify cross-drive operations (D: ↔ E:)

### Short-term
1. Run Phase A (Wikidata Dissection) for all 6 experts
2. Monitor cartridge generation and expert inoculation
3. Restart auto_incubator.py with Wikidata integration active

### Long-term
1. Evaluate specialist germination with structured knowledge base
2. Adjust growth limits based on operational needs
3. Implement dashboard for real-time monitoring

## System Health Metrics

### Performance Indicators
- **Expert EMA Growth:** +0.10 to +0.31 per 6.5 hours (healthy)
- **Package Acquisition:** +247 packages in 6.5 hours (stable)
- **Specialist Creation:** 0 new specialists (growth control working)
- **Database Size:** Stable, no bloat

### Operational Stability
- **Autonomous Loop:** Running continuously without issues
- **Hourly Reports:** Generated successfully every 60 minutes
- **Passive Pruning:** Operational (no frozen experts currently)
- **Query Tracking:** Preventing duplicate searches effectively

## Configuration Files

### Active Configuration
- **config/settings.py** - Search delays, user-agents, DB paths
- **master/auditor/ecosystem_auditor.py** - Growth limits and thresholds
- **database/connection.py** - Schema definitions and initialization
- **hybrid_pipeline.py** - Wikidata integration and fallback logic

### Path Configuration
- **BRAIN_DB_PATH:** D:/proyectos/expertia/incubator-root/storage/incubator.db
- **WIKIDATA_DUMP_PATH:** E:/aria2-1.37.0-win-64bit-build1/latest-all.json.gz
- **TARGET_OUTPUT_DIR:** E:/expertia-data

## Development Notes

### Code Quality
- **Type Hinting:** Implemented throughout hybrid_pipeline.py
- **Error Handling:** Defensive try/except blocks with logging
- **Documentation:** Comprehensive docstrings and comments
- **Modularity:** Clean separation of concerns across modules

### Testing Strategy
- **Unit Testing:** Not yet implemented
- **Integration Testing:** Manual testing with small datasets
- **Stress Testing:** 6.5-hour continuous operation completed

---
*Status document generated automatically by Cascade*
