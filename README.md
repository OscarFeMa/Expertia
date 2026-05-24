# Expertia
Expertia es un motor de orquestación de agentes especializados para hardware local. Gestiona redes de micro-modelos LLM (vía Ollama) con un sistema lazy-loading que optimiza la VRAM, permitiendo ejecutar expertos en distintos ámbitos sin saturar el sistema. Diseñado para un conocimiento estructurado, eficiente y soberano.

## Overview

The Coral Thought Ecosystem is designed for local-first AI multi-agent infrastructure with optimized resource usage for hardware-constrained environments (NVIDIA RTX 1660, 6GB VRAM, 32GB RAM). It provides:

- **15-Specialist Architecture**: Domain-specific experts with hardware-optimized models
- **Thread-Safe Database**: Singleton SQLite connection pool with RLock for reentrancy
- **Zero-RAM-Bloat Wikidata Extraction**: Streaming via ijson for 142GB dump processing
- **Single-Active-Model Policy**: VRAM-aware lazy loading with ollama stop/run
- **Hybrid Pipeline**: Phase A (Wikidata) + Phase B (Web Scraping) with fallback
- **Dynamic EMA Scoring**: Quality-based expert performance evaluation
- **Retry Logic**: Exponential backoff for HTTP operations
- **Path Validation**: Pre-flight checks for all required paths
- **Error Cleanup**: Guaranteed VRAM cleanup on errors
- **Modern Web Scraping**: Updated DDGS (>=9.14.0) and Trafilatura (==2.0.0)

## Project Structure

```
incubator-root/
├── config/
│   ├── __init__.py
│   └── settings.py         # Search delays, user-agents, and DB paths
├── database/
│   ├── __init__.py
│   ├── connection.py       # SQLite connection handling and table initialization
│   └── queries.py          # Expert registry audits and updates
├── crawler/
│   ├── __init__.py
│   ├── search_engine.py    # DuckDuckGo integration with safe anti-blocking delays
│   ├── parser.py           # Trafilatura HTML-to-Markdown processing
│   ├── distiller.py        # Ollama-powered knowledge distillation
│   └── ollama_manager.py   # Ollama model management
├── master/
│   ├── auditor/
│   │   ├── __init__.py
│   │   └── ecosystem_auditor.py  # Density-based specialist germination
│   └── evaluation/
│       ├── __init__.py
│       └── evaluator.py   # Expert performance evaluation
├── scripts/
│   ├── seed_experts.py     # Initial expert seeding
│   └── run_evolution_test.py  # Expert evolution pipeline
├── logs/                   # Directory for operational execution logs
├── storage/
│   ├── incubator.db        # SQLite database
│   ├── packages/           # Knowledge packages storage
│   └── reports/            # Hourly Markdown reports
├── incubator_ingestion.py  # Main entry point orchestration script
├── auto_incubator.py       # Autonomous batch supervisor with interactive menu
├── orchestrator.py         # Main pipeline controller (15 specialists)
├── llm_manager.py          # Ollama model manager with Single-Active-Model policy
├── web_scraper.py          # Modern web scraper with DDGS and Trafilatura
├── database/
│   ├── __init__.py
│   ├── connection.py       # Legacy SQLite connection handling
│   ├── queries.py          # Expert registry audits and updates
│   └── db_manager.py       # Thread-Safe Singleton Database Manager
├── PROJECT_STATUS.md       # Current system state and configuration
└── PROJECT_HISTORY.md      # Complete project chronology
```

## Requirements

- Python 3.10+
- Windows 11 (Native execution, NO Docker, NO WSL)
- NVIDIA RTX 1660 (6GB VRAM), 32GB RAM
- Ollama with models for 15 specialists
- Dependencies listed in `requirements.txt`

## Installation

1. Navigate to the project directory:
```bash
cd incubator-root
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Install Ollama and pull required models:
```bash
# Install Ollama (Windows)
winget install Ollama.Ollama

# Pull required models for 15 specialists
ollama pull qwen2.5:3b
ollama pull qwen2.5-coder:3b
ollama pull phi3:mini
ollama pull llama3.2:3b
ollama pull gemma2:2b
ollama pull mistral:7b
```

4. Verify Wikidata dump path:
```bash
# Ensure E:\aria2-1.37.0-win-64bit-build1\latest-all.json.gz exists
# Create E:\expertia-data\ for output cartridges
```

5. Initialize specialist registry:
```bash
python orchestrator.py
```

## Usage

### Coral Thought Orchestrator (15-Specialist Pipeline)

Run the main orchestrator to process all 15 specialists:

```bash
python orchestrator.py
```

The system will:
1. Validate required paths (Wikidata dump, output directory)
2. Initialize specialist registry in database
3. Process each specialist with:
   - Phase A: Wikidata extraction via ijson streaming (zero-RAM-bloat)
   - Phase B: Web scraping with modern DDGS and Trafilatura
   - Dynamic EMA scoring based on content quality
4. Apply Single-Active-Model policy (VRAM optimization)
5. Handle errors with retry logic and exponential backoff
6. Guarantee VRAM cleanup on errors

### Web Scraper (Standalone)

Run the modern web scraper independently:

```bash
python web_scraper.py
```

### LLM Manager (Standalone)

Test Ollama model management:

```bash
python llm_manager.py
```

### Autonomous Mode (Legacy)

Run the legacy autonomous batch supervisor with interactive menu:

```bash
python auto_incubator.py
```

Select option [1] for autonomous loop. The system will:
1. Run EcosystemAuditor for density-based germination (with hard limits)
2. Display expert ecosystem status by tier
3. Identify expert with lowest EMA score
4. Generate dynamic search query via Ollama
5. Trigger evolution pipeline with the query
6. Generate hourly reports every 60 minutes
7. Apply passive pruning for frozen experts

## Database Schema

### specialist_registry (Coral Thought 15-Specialist Architecture)
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `domain` (TEXT NOT NULL UNIQUE) - Specialist domain (e.g., SoftwareEngineering)
- `model` (TEXT NOT NULL) - Hardware-optimized Ollama model
- `root_qid` (TEXT NOT NULL) - Wikidata root QID for filtering
- `properties` (TEXT NOT NULL) - Wikidata properties (JSON array)
- `ema_score` (REAL DEFAULT 0.10) - Dynamic EMA score
- `tier` (INTEGER DEFAULT 3) - 3: In-Training
- `packages_absorbed` (INTEGER DEFAULT 0)
- `status` (TEXT DEFAULT 'IDLE') - IDLE, ACTIVE, PROCESSING
- `created_at` (TIMESTAMP)
- `updated_at` (TIMESTAMP)

### cartridge_offsets (Wikidata Extraction Tracking)
- `qid` (TEXT PRIMARY KEY)
- `cartridge_name` (TEXT)
- `offset_start` (INTEGER)
- `offset_end` (INTEGER)
- `specialist_id` (INTEGER)
- `status` (TEXT DEFAULT 'Available') - Available, PROCESSING, COMPLETED, FALLBACK_TRIGGERED
- `created_at` (TIMESTAMP)
- FOREIGN KEY (specialist_id) REFERENCES specialist_registry(id)

### knowledge_packages (Knowledge Storage)
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `topic` (TEXT NOT NULL)
- `source_url` (TEXT NOT NULL)
- `domain` (TEXT)
- `structured_knowledge` (TEXT)
- `created_at` (TIMESTAMP)

### ema_history (EMA Score History)
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `specialist_id` (INTEGER NOT NULL)
- `ema_score` (REAL NOT NULL)
- `timestamp` (TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
- FOREIGN KEY (specialist_id) REFERENCES specialist_registry(id)

## 15-Specialist Architecture

The Coral Thought ecosystem implements 15 domain-specific specialists with hardware-optimized models:

1. **SoftwareEngineering** - qwen2.5-coder:3b (Q11661)
2. **Mathematics** - qwen2.5:3b (Q395)
3. **Medicine** - phi3:mini (Q11190)
4. **LegalSystem** - llama3.2:3b (Q7748)
5. **PhilosophyHistory** - gemma2:2b (Q315)
6. **FinanceEconomics** - mistral:7b (Q8134)
7. **Physics** - qwen2.5:3b (Q11424)
8. **Cybersecurity** - llama3.2:3b (Q151211)
9. **Bioinformatics** - phi3:mini (Q193635)
10. **Geopolitics** - llama3.2:3b (Q79461)
11. **DataScience** - qwen2.5-coder:3b (Q1156829)
12. **Chemistry** - qwen2.5:3b (Q11158)
13. **ArtHistory** - gemma2:2b (Q178561)
14. **Electronics** - qwen2.5:3b (Q11663)
15. **Astronomy** - qwen2.5:3b (Q333)

Each specialist has:
- Hardware-optimized model (2b-7b parameters)
- Wikidata QID mapping for domain filtering
- Dynamic EMA scoring based on content quality
- Single-Active-Model policy for VRAM optimization

## Key Improvements (Refactoring 2026-05-24)

### Database Layer
- **Thread-Safe Singleton**: RLock for reentrancy, double-checked locking
- **Connection Pool**: Single connection instance with thread-safe operations
- **Specialist Tables**: specialist_registry, cartridge_offsets, ema_history

### Model Management
- **Unified Architecture**: Single LLMRunner (llm_manager.py) across all modules
- **Single-Active-Model Policy**: VRAM-aware lazy loading with ollama stop/run
- **Offline Verification**: Local model cache validation before operations
- **HTTP API Communication**: Direct API calls (localhost:11434) instead of subprocess

### Error Handling
- **Retry Logic**: Exponential backoff for HTTP operations (max 3 retries)
- **Path Validation**: Pre-flight checks for all required paths
- **Error Cleanup**: Guaranteed VRAM cleanup on errors (try/finally)
- **Custom Exceptions**: LocalModelNotFoundError, ModelLoadError, LLMQueryError, ModelTimeoutError

### Performance
- **Zero-RAM-Bloat**: ijson streaming for 142GB Wikidata dump
- **Dynamic EMA Scoring**: Quality-based evaluation (content length + trust score)
- **Batch Processing**: Periodic entity writes to avoid memory buildup
- **Timeout Protection**: 4-hour timeout for Wikidata extraction

### Web Scraping
- **Modern DDGS**: Updated to duckduckgo-search>=9.14.0
- **Updated Trafilatura**: Version 2.0.0 with improved extraction
- **Rate Limiting**: Anti-blocking delays and User-Agent rotation
- **Trust Scoring**: Tier-based source evaluation

## Configuration

Edit `config/settings.py` to customize:
- Search delays and timeouts
- User-Agent rotation list
- Database paths
- Suitability score threshold
- Maximum results per search

## Logging

Operational logs are saved to the `logs/` directory with timestamped filenames.

Hourly reports are saved to `storage/reports/` with format `hourly_report_YYYYMMDD_HHMM.md`.

## License

This project is part of the "Pensamiento Coral" ecosystem.

## GitHub Repository

Ready for GitHub repository creation with:
- Complete refactoring documentation
- 15-specialist architecture implementation
- Hardware-optimized configuration
- Production-ready error handling
=======
Expertia es un motor de orquestación de agentes especializados para hardware local. Gestiona redes de micro-modelos LLM (vía Ollama) con un sistema lazy-loading que optimiza la VRAM, permitiendo ejecutar expertos en distintos ámbitos sin saturar el sistema. Diseñado para un conocimiento estructurado, eficiente y soberano.
>>>>>>> 0a232b871b0aa6d5bd8abbc7909f59cb2b35a8a5
