# Project Status — Expertia Synaptic Archive

**Last Updated:** 2026-08-19

## Current System State

### Fase 0 (2026-08) — Recuperación de Crash y Rebuild FTS + Fase A sellada
- **Recovery de crash dumps (`recover_crash_kps.py`)**: 5,142/5,142 archivos `_kps.json`, **157,652,430 filas** recuperadas en `knowledge_packages` (25,240s). `knowledge_packages` consolidada a **714,961,987 filas** (count verificado post-checkpoint).
- **Checkpoint WAL**: `wal_checkpoint(TRUNCATE)` con conexión única (v5) redujo el WAL de 142 GB a 0 en 232 min; BD consolidada a **684.3 GB**.
- **Rebuild FTS5 (`rebuild_fts5_0c.py`)**: índice FTS5 reconstruido desde cero; triggers `kp_ai/kp_ad/kp_au` presentes; WAL final 0 GB; 240 GB libres en E:
- **Fase A sellada como COMPLETED**: 18 `cartridge_offsets` → `status='COMPLETED'`; `specialist_registry.wikidata_total_entities = packages_absorbed` (18 filas).
- **Fase 4**: endpoints `/api/wikidata/status|download|feed|stop` eliminados de `api_router.py` (la alimentación incremental semanal vía launcher/schtasks reemplaza la vía API). Pestaña Wikidata removida de `control-center` (app.js + index.html). Test S2.3 actualizado (espera 0 rutas).
- **Fase 2**: `specialist_match_cache` regenerada desde `knowledge_packages` (GROUP BY domain, 18 especialistas, 714,961,971 packages; 16 filas con domain huérfano no incluidas). `matched_qids` eliminada y recreada vacía (973M filas → 0; DROP+CREATE en 98 min). VACUUM descartado (auto_vacuum=0, requeriría ~684 GB extra; freelist solo 18 GB — 2.6%).
- **Fase 3**: tarea programada `ExpertiaWikidataIncremental` (domingo 03:00, PY `update_wikidata.py --incremental`, límite 6h). Incremental usa `last_wikidata_download` por especialista (última: 2026-06-28); dedupe garantizado por índice UNIQUE `idx_kp_qid_domain` + `INSERT OR IGNORE`.
- Especialistas: 18 root, todos ACTIVE/IDLE según pipeline; `last_wikidata_download` 2026-06-28.
- ⚠️ COUNT/MAX/GROUP BY sobre `knowledge_packages`: un count(*) completo tarda ~4h en HDD; evitar salvo mantenimiento.
- **State cleanup**: `pipeline_state.json` limpiado (PID 24100 muerto → estado `web` reset a `pid:null, mode:web, watchdog:+api`). Backup en `pipeline_state.json.stale`. Ollama verificado UP.

### Active Components
- **18 Specialist Roots** — 14 legacy + 4 new (Linguistics, Psychology, EnvironmentalScience, Sociology)
- **Pipeline**: Phase A (Wikidata dump scan → matched QIDs) + Phase B (Nurture v2 with Tier Ascension)
- **Multilingual Extraction**: 6 languages (en, es, fr, de, pt, it) for Wikidata + Wikipedia
- **Nurture v2**: Single-target Tier Ascension (Bronze→Silver→Gold→Legend), cascade detection, EMA decay
- **23 Super-Expert Councils**: Includes SocietyAndCulture, updated LanguagesLinguistics, NeuroscienceCognition, ClimateEnvironment
- **Neural Horizon Dashboard**: Static frontend served via API, pipeline control, monitor, dark/light theme
- **Pipeline Monitor**: Independent process, 20-min reporting interval
- **Circuit Breaker**: Auto-reset after 60s, cascade detection (≥20 failures/50 cycles → 5min pause)

### Fase 1 — Launcher, Watchdog y Web Continua
- **P1 Web continua** (`orchestrator.py`): `--duration` ahora opcional (default `None`). En `--phase web`, `None`/`0` → `min_duration_hours=999999` y `max_cycles=0` (bucle infinito); `full`/`cascade` conservan 5.0h; feed 1 pasada. `--max-duration`/`--max-cycles` como opt-outs explícitos.
- **P2 Launcher** (`tools/launcher.py` + `launcher.cmd`): menú interactivo + CLI (`--mode web|nurture|feed|full|cascade --duration --specialist --model --skip --max-cycles --max-duration --parallel --with-watchdog --api`). Valida Python/Ollama/DB, detecta pipeline previo, lanza `CREATE_NO_WINDOW`, escribe `pipeline_state.json` (`{pid, mode, duration_hours, specialist, model, skip, max_cycles, max_duration, watchdog, api}`). Acceso directo en escritorio: `Expertia Launcher.lnk`.
- **P3 Watchdog v3** (`tools/watchdog.py`): DB real `E:\expertia-data\incubator.db`, sin `NURTURE_IDS` hardcode, lectura de `pipeline_state.json` para relanzar idénticamente. Congelación = `updated_at` sin avanzar + sin filas nuevas en `activity_log` 20 min → kill + relaunch; strike-limit 5 → `status='BLOCKED'` en `specialist_registry`; crash-loop guard 5 restarts/30 min.
- **Fix alerta web**: `/analytics/insights` usa señal de vida real (`activity_log` + PID de `pipeline_state.json`) en vez de `pipeline_status.updated_at` (stale en nurture); alert **info** con modo y tiempo transcurrido; warning si >30 min sin actividad; error si detenido. `/status` expone `mode`. Frontends (neural-horizon y control-center) muestran modo/tiempo.

### Fase 2 — Optimizaciones (O1-O5)
- **O1** `api_router.py` `/knowledge/search`: `ORDER BY rank` (FTS5) + `id DESC` (fallback LIKE). Medido **34.2s → 4.4s (~8×)** en frío; divergencia rowids FTS5 vs `knowledge_packages.id`: 0/200 muestreados.
- **O2** `llm_manager.py`: cache TTL 30s de "modelo cargado" (`_loaded_model`/`_loaded_ts`), cortocircuito en `ensure_model_loaded`, invalidación en `_stop_model`.
- **O3** `web_scraper.py`: `lru_cache` keyed (domain, mtime) en carga de seeds.
- **O4** `orchestrator.py`: `update_ema_score` agrupado en 1 transacción (`execute_batch`: UPDATE specialist_registry + INSERT ema_history + INSERT cycle_history + UPDATE tier condicional).
- **O5** `db_manager.py`: `CREATE INDEX IF NOT EXISTS idx_matched_qids_specialist ON matched_qids(specialist_id, processed)` movido fuera del bloque de migración guardado (la migración `kp_matched_qids` ya estaba logueada y el índice nunca se crearía; se aplica al reiniciar el pipeline).

### Specialist Ecosystem
- **Total Specialists:** 18 root
- **Database:** `E:\expertia-data\incubator.db` (192M filas en `knowledge_packages`; nunca COUNT/MAX/GROUP BY sobre ella)
- **Models:** phi4-mini:4k (mayoría), gemma3:4b, qwen2.5-coder:3b
- **Baseline pytest:** 196 passed / 25 failed (fallos pre-existentes conocidos, ver Known Issues)

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
| status | TEXT | IDLE, ACTIVE, PROCESSING, BLOCKED |
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

## Known Issues

- **Fallos pytest pre-existentes (25)**: API tests (`readonly_db not initialized`), nurture refiere `_check_subspecialist_expansion` eliminado, TestB1 espera `start_all.bat` inexistente, TestB7 caso chino, TestS24/S25, TestB2/B3. No relacionados con Fase 1+2.
- **Índice O5 pendiente de aplicar**: la DB está bloqueada por el pipeline en marcha; se crea automáticamente en el próximo reinicio.
- **Sin Phase A activa**: Wikidata dump path no disponible; fase nurture es la activa.

## Next Steps

### Fase 3 — Roadmap (no implementado, planificado)
1. **Autenticación multiusuario**: login/roles para la web (admin vs readonly).
2. **Trust layer `sources[]`**: trazar cada claim hasta su fuente (URL/entidad), puntuación de confianza por paquete.
3. **`/metrics` Prometheus**: exponer health/rendimiento del pipeline para Grafana.
4. **Fase P1 semántica vectorial**: búsqueda por embeddings, export de conocimiento, chat con el archivo.
5. **Fase P2 producción**: Docker, escalado horizontal, backups automáticos.

## Config

- `SUBSPECIALIST_THRESHOLD = 100`
- `MAX_SUBSPECIALISTS = 20`
- `SUBSPECIALIST_CYCLE_INTERVAL = 10`
- `MAX_CHILDREN_PER_PARENT = 3`
- Wikidata API batch: 50 QIDs per request
- `PHASE_B_PER_SPECIALIST_TIMEOUT = 7200` (2h por especialista)

---
*Status document generado automáticamente por Cascade*
