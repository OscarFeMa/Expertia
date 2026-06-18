# Project Status — Expertia Synaptic Archive

**Last Updated:** 2026-06-08

## Current System State

### Active Components
- **18 Specialist Roots** — 14 legacy + 4 new (Linguistics, Psychology, EnvironmentalScience, Sociology)
- **Pipeline**: Phase A (Wikidata dump scan → matched QIDs) + Phase B (Nurture v2 with Tier Ascension)
- **Multilingual Extraction**: 6 languages (en, es, fr, de, pt, it) for Wikidata + Wikipedia
- **Nurture v2**: Single-target Tier Ascension (Bronze→Silver→Gold→Legend), cascade detection, EMA decay
- **23 Super-Expert Councils**: Includes SocietyAndCulture, updated LanguagesLinguistics, NeuroscienceCognition, ClimateEnvironment
- **Neural Horizon Dashboard**: Static frontend served via API, pipeline control, monitor, dark/light theme
- **Pipeline Monitor**: Independent process, 20-min reporting interval
- **Circuit Breaker**: Auto-reset after 60s, cascade detection (≥20 failures/50 cycles → 5min pause)

### Specialist Ecosystem
- **Total Specialists:** 18 root (10 specialists deleted: Bioinformatics, Geriatrics, plant physiology, criminal/civil/family/sharia/Turkish law, Astronomy/biology)
- **Database:** `storage/incubator.db` with 10+ tables (matched_qids, wiki_monitor, activity_log)
- **Pipeline:** Phase A (dump scan) then auto-feed to Phase B Nurture
- **Models:** phi4-mini:3.8b (12 specialists), llama3.2:3b (3), qwen2.5-coder:3b (5)
- **7,315 packages** reassigned from deleted specialists to surviving domains
- **16,477 duplicate packages** removed, 1,139,560 circuit-breaker WARNINGs cleaned from activity_log

### Super-Expert Councils (23)
EconomyFinance, ArtificialIntelligence, BiotechnologyHealth, QuantumPhysics, CybersecurityDefense, ClimateEnvironment, SpaceExploration, DataPrivacyEthics, CulturalHeritage, EnergySustainability, CryptocurrencyBlockchain, EducationTechnology, ManufacturingIndustry, Telecommunications, MaterialsScience, UrbanPlanningSmartCities, DefenseStrategy, NeuroscienceCognition, GeneralKnowledge, LanguagesLinguistics, VisualArts, PerformingArts, **SocietyAndCulture**.

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
