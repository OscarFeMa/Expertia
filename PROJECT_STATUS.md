# Project Status — Expertia Synaptic Archive

**Last Updated:** 2026-05-26

## Current System State

### Active Components
- **15 Specialist Roots** with corrected Wikidata QIDs
- **Pipeline Phase B**: Web scraping (DDGS) + LLM distillation + EMA scoring
- **Sub-Specialist Spawning**: Validated via Wikidata P279 parent-sharing + API label resolution
- **22 Super-Expert Councils**: Static reference tables with weighted members
- **Synaptic Archive Console**: Streamlit UI with sunburst hierarchy, control panel, auto-refresh
- **Report Scheduler**: Automatic `Rendimiento_<ts>.txt` every 30 min

### Specialist Ecosystem
- **Total Specialists:** 15 root + 1 sub-specialist (Medicine/Geriatrics #1774)
- **Database:** `storage/incubator.db` with 7 tables
- **Pipeline:** Phase B (web+LLM) loop per specialist, spawning check every 10 cycles

### Super-Expert Councils (22)
EconomyFinance, ArtificialIntelligence, BiotechnologyHealth, QuantumPhysics, CybersecurityDefense, ClimateEnvironment, SpaceExploration, DataPrivacyEthics, CulturalHeritage, EnergySustainability, CryptocurrencyBlockchain, EducationTechnology, ManufacturingIndustry, Telecommunications, MaterialsScience, UrbanPlanningSmartCities, DefenseStrategy, NeuroscienceCognition, GeneralKnowledge, LanguagesLinguistics, VisualArts, PerformingArts.

## Database Schema

### specialist_registry
| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| domain | TEXT UNIQUE | Specialist name |
| model | TEXT | Ollama model |
| root_qid | TEXT | Wikidata QID |
| properties | TEXT | JSON array of Wikidata properties |
| ema_score | REAL | Dynamic EMA score |
| tier | INTEGER | 3 = In-Training |
| packages_absorbed | INTEGER | Total packages processed |
| status | TEXT | IDLE, ACTIVE, PROCESSING |
| parent_id | INTEGER NULL | FK to parent specialist |
| qid_path | TEXT | Hierarchical QID path |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

### knowledge_packages
| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment |
| topic | TEXT | Search topic |
| source_url | TEXT | Source URL |
| domain | TEXT | Specialist domain |
| structured_knowledge | TEXT | Distilled JSON |
| qid | TEXT | Wikidata QID |
| subdomain_path | TEXT | Hierarchical path |
| created_at | TIMESTAMP | |

### super_experts / super_expert_members
- 22 councils with weighted member links

## Key Improvements

### Sub-Specialist Spawning
- **Wikidata API label resolution**: Replaces hardcoded 68-entry dict (which had wrong mappings)
- **P279 parent-sharing validation**: Direct child (P279 includes root) or sibling (share P279 parent)
- **Blocklist**: Filters 13 generic labels + 4 label prefixes
- **Limits**: 20 max total, 3 max per parent per cycle, 100 packages threshold

### Root QID Corrections (May 2026)
9 root QIDs were corrected after Wikidata API verification — examples: Cybersecurity was Q151211 (no label) → Q3510521 (computer security), Bioinformatics was Q193635 (Alan Greenspan) → Q128570 (bioinformatics).

### Dead Code Removal
Removed 7 legacy modules: auto_incubator, hybrid_pipeline, dashboard files, ecosystem_auditor, seed_experts, run_evolution_test, legacy database/connection + queries.

## Known Issues

- **Auto-launch fires immediately**: Pipeline auto-starts Physics on console load without user confirmation
- **No Phase A active**: Wikidata dump path may not exist (Phase B only runs)
- **Sub-specialists only in Medicine**: Other domains have not yet triggered spawning threshold

## Next Steps

1. Run pipeline with corrected QIDs to validate spawning
2. Expand sub-specialists beyond Medicine
3. Monitor cross-domain contamination in new expansions
4. Consider making auto-launch configurable or delayed

## Config

- `SUBSPECIALIST_THRESHOLD = 100`
- `MAX_SUBSPECIALISTS = 20`
- `SUBSPECIALIST_CYCLE_INTERVAL = 10`
- `MAX_CHILDREN_PER_PARENT = 3`
- Wikidata API batch: 50 QIDs per request

---
*Status document generated automatically by Cascade*
