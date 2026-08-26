# PLAN vNext v2.0 — Expertia Synaptic Archive
## Ingeniería de Producto Senior — Roadmap Integral Interface / Flujo / Sistema

**Versión:** 2.0  
**Fecha:** 2026-08-23  
**Autor:** Senior Product Engineering (síntesis de 3 auditorías exhaustivas: frontend, backend pipeline, infra DB)  
**Estado actual verificado:** DB 684.3 GB (179M pages × 4KB, freelist 18.1 GB), 714,961,987 rows, 18 specialists Tier 4 Legend, FTS5 rebuild OK, WAL 0 (TRUNCATE 232 min), HDD ST1000DM010 cuello, pipeline web activo PID 19596→22612 (gemma3:4b READY), M2 2TB pendiente  
**Objetivo vNext:** Pasar de monolito HDD-bound batch a plataforma M2-native productiva con búsqueda semántica, trazabilidad `sources[]` y observabilidad Prometheus, manteniendo 18 specialists operativos sin downtime >4h

---

## 0. Resumen Ejecutivo

| Dimensión | Problema raíz hoy | Oportunidad vNext | Impacto | Esfuerzo |
|---|---|---|---|---|
| **Interface** | 2 UIs divergentes (neural 619L canvas vs control 1199L Plotly), sin virtualización, polling 3s ×7 fetches, A11y falla, responsive dispar | Design System unificado, tabla virtual, SSE, command palette, A11y 100 | TTI 1.2s→400ms, Lighthouse 70→95, soporte 500 specialists | M (1 mes) |
| **Flujo** | Singleton `DatabaseManager._execute_lock` serializa writes, WAL bloat 142GB, gzip sequential 110M entities 137min, LLM single-model VRAM 6GB | Queue single-writer async + sharding domain + byte-offset checkpoints + httpx async | Throughput Phase A 0.8→2.8M/min, Phase B 18/día→54/día, WAL estable 2MB | M-L (1-2 meses) |
| **Sistema** | DB en HDD 80-150 IOPS (peor disco), 318GB stale en D, sin backup físico 684GB, `auto_vacuum=0` freelist 18GB no reclamable, Defender no excluido | Migración M2 2TB NVMe (300k IOPS) + `auto_vacuum=INCREMENTAL` + backup nightly `VACUUM INTO` externo + exclusión Defender | `COUNT(*)` 4h→3min, FTS 4.4s→200ms, VACUUM posible, backup 7d | S (1 semana) + M (compra 2TB ~€90) |

**Decisión senior:** Priorizar **P0 Sistema (M2 + backup + Defender)** en semana 1 (desbloquea todo), **P0 Interface quick wins** en paralelo, **P0 Flujo queue+checkpoint** en semanas 2-4. P1 Trust/Observabilidad y P2 Producto semántico en v2.1.

---

## 1. Estado Actual Verificado (23/08/2026 21:37)

### 1.1 Métricas duras

| Métrica | Valor | Fuente | Umbral crítico |
|---|---|---|---|
| DB archivo | 734,726,778,880 B = 684.3 GiB (179,376,655 pages ×4096) | `Get-Item E:\incubator.db` | >800GB excede E |
| Freelist | 4,745,490 pages = 18.1 GB (2.65%) | `PRAGMA freelist_count` | >5% desperdicio |
| WAL | 2.4 MB + shm 32KB (tras TRUNCATE 142GB→0 en 232min) | `Get-Item *.db-wal` | >1GB bloat |
| Rows `knowledge_packages` | 714,961,987 (MAX id 906,773,562 → 192M huecos por dedup) | `PROJECT_STATUS` + `sqlite_sequence` | 1B límite AUTOINCREMENT |
| D libre | 129.7 GB /480GB (27%) | `Get-Volume D` | <50GB full — D tiene 318GB stale `storage/incubator.db` 29/06 |
| E libre | 258 GB /1000GB (25.8%) | `Get-Volume E` | <684GB no VACUUM |
| C NVMe libre | 352 GB /1000GB (35%) | `Get-Volume C` SNV2S1000G (3500 MB/s, 300k IOPS) | ocioso, debería alojar DB |
| `storage/incubator.db` stale | 318.5 GiB, LastWrite 29/06 21:44 | `Get-Item D:\storage\incubator.db` | 66% de D ocupado inútil |
| Logs | 1.82 GB, 861 archivos (Rotating 10MB×5 pero 400×0B crash loops) | `Get-ChildItem logs` | >5GB rotar |
| Specialists | 18 Tier 4 Legend (EMA 0.995-0.998), 9,009,092-36,328,983 pkgs c/u | `specialist_registry` | — |
| Pipeline | web activo PID 19596→22612 (6 min, Geopolitics/LegalSystem/Sociology, gemma3:4b READY) | `api/analytics/insights` | — |
| Tarea semanal | `ExpertiaWikidataIncremental` domingo 03:00 `--incremental` 6h timeout | `Get-ScheduledTask` | — |

### 1.2 Deuda técnica crítica

- **Infra:** DB en HDD 80 IOPS vs NVMe 300k IOPS (2000×), `auto_vacuum=0` impide `incremental_vacuum`, `page_size 4096` 179M pages, `temp_store=MEMORY` OOM 17GB, `mmap 1GB` bien pero file default 0, `wal_autocheckpoint 500` vs file 1000 desalineado, `VACUUM` imposible (requiere 684GB extra), sin backup físico 684GB (solo schema 9KB + dumps 235MB activity_log)
- **Flujo:** Singleton lock `db_manager.py:58 _execute_lock` + `BEGIN IMMEDIATE` serializa 3 writers paralelos (60% pérdida), FTS5 triggers `kp_ai/ad/au` duplican writes (MP hace `DROP ALL FTS` y rebuild bloqueante), gzip sequential single-core, `ijson` 0.8M/min, resume_offset re-parsea 80M eventos (60min), `fetch_entities_batch` 50 serial 20k req 7 días, SPARQL sin pagination OOM 2M bindings, `httpx.Client` sync + `Semaphore 5` + `ThreadPool 9` 130s por specialist, `trafilatura` pierde tablas, BloomFilter RAM no persistido, batch flush 50/30s pierde 49 pkgs on crash
- **Interface:** Dual UIs sin tokens compartidos, neural polling 3s×7 (2.3 req/s) sin ETag, `renderFleet` innerHTML rebuild total cada 3s (jank 200 filas), sin virtualización, sin search, sin tooltip/zoom, Plotly 7 charts simultáneos (1.2s TTI), `onclick inline` sin `role=tab`, contraste `dim #4A525C` falla AA, `help-overlay` sin `aria-modal`, `canvas` sin `aria-label`, `prefers-reduced-motion` solo control, `exportCSV` solo neural, `toast` solo neural vs `alert()` control, duplicado `setRange/setActFilter` L91/144, responsive solo 1100px neural vs 900/700/600 control, dark/light incoherente (neural dark default, control light)

---

## 2. Alternativas de Interface — Análisis Senior

### 2.1 Problema: Dualidad "console vs paper" sin sistema

**Alternativa A — Unificar Design System (Recomendada, P0)**
- Crear `frontend/shared/tokens.css` con `--color-*`, `--space-*`, `--radius-2/6/10`, `--font-mono/sans`, `--shadow-*` + `oklch` palette `accent oklch(0.70 0.15 50)` + `color-mix` para `amber-dim`
- `CSS layers` + `container queries` para cards, `prefers-color-scheme` sync + `prefers-contrast:more` high-contrast, `transition: background .2s`
- Unificar `topbar 38px` + `tabbar` `role=tablist` con `aria-selected`, `ArrowLeft/Right`, `focus-visible: outline 2px solid amber`, `skip-to-content` link
- **Pros:** Single source of truth, Lighthouse A11y 90→100, TTV ↓, mantenimiento -50%  
- **Contras:** Refactor 2 semanas, riesgo regresión visual (mitigado con Chromatic)  
- **Archivos:** `neural/style.css:5`, `control/style.css:1`, nuevo `frontend/shared/tokens.css`, `frontend/shared/components/*`

**Alternativa B — Mantener dual con bridge**
- Mantener 2 temas, solo sincronizar `tokens.css` importado, no unificar layout  
- **Pros:** Menor riesgo, 1 semana  
- **Contras:** Deuda persiste, doble mantenimiento, TTI no mejora  
- **Veredicto:** Descartada — deuda supera ahorro

### 2.2 Visualización Flota/Especialistas

**Alternativa A — Tabla virtual unificada (Recomendada, P1)**
- Virtual scroller `tanstack-virtual` o `content-visibility:auto` + sticky `domain` col + column picker + paginación 50 + multi-sort (`neural/app.js:457 sortSpecs` reutilizado)
- Nuevo `frontend/shared/components/fleet-table.js` → `renderFleetVirtual(specs, viewport)` con `DocumentFragment`, `requestAnimationFrame` batched, `ResizeObserver` + DPR `canvas.width=W*dpr`
- Filtros: search debounce 250ms (portar `control/spec-search:569`), tier pills, `fail_rate` slider
- **Pros:** Soporta 500 specialists sin jank, búsqueda <100ms, TTI 400ms  
- **Contras:** Dependencia nueva (5KB)  
- **Alternativa B:** Paginación clásica sin virtual → simple pero scroll infinito roto con 200 filas → descartada

### 2.3 Métricas y Gráficos

**Alternativa A — Canvas nativo mejorado (Recomendada)**
- Mantener `neural/charts.js` canvas (ligero) pero añadir `mousemove` tooltip crosshair + legend clickable `hiddenSeries Set` + `ResizeObserver` + `range 7d/30d` brush, `spark` 40 puntos → 120 puntos con `IndexedDB`
- `control/charts.js` Plotly: `dynamic import('plotly')` solo en Map tab + `IntersectionObserver` lazy (7 charts no simultáneos) + `SWR` `ETag`/`Last-Modified` + `EventSource /api/stream` SSE vs `setInterval 3s/10s`
- **Pros:** Neural perf + control riqueza, TTI -60%  
- **Alternativa B:** Migrar todo a Plotly → pesado 500KB CDR siempre → descartada

### 2.4 Navegación, Super-Experts, Certified, Incidentes, Mapa

- **Super-Experts:** `se-expander L882 onclick inline` → `<details><summary>` nativo + `aria-expanded` + search + sort `weighted_ema` + animación `grid-template-rows 0fr→1fr` (P0 Q1)
- **Certified:** Paginación 20 + filtros tier + `fail_rate` badge `cert-good ✔ <5%` + explicar `pts=ema*1000` inline help `?` + `thead sortable` reuse `neural sortBy`
- **Incidentes:** Timeline vertical + pills `level` + agrupación día + drawer `Show logs` + fix `makeErrorsChart` con API `GET /incidents/by_model` vs `string.includes` frágil + `aria-live=polite` para `activity-feed` prepend
- **Mapa Synaptic 2.0:** Separar en 3 sub-tabs `Gauges/Waves/Knowledge` con lazy + único `GET /map/snapshot` vs 7 fetches + `WebGL` force-graph `specialists↔parents` (`sigma.js`/`d3-force`) usando `parent_id`, `MemoryHistory` 60 → `IndexedDB` + spark 1h
- **Command palette `Cmd+K`:** Fuzzy search especialistas + acciones `Kill, Toggle theme, Export` (extiende `neural onKey L42` que ya tiene `F1-3/?`)
- **Responsive parity:** Neural añade `@media 900/600/480` igual control (`control/style.css:989`), topbar collapse @600, tabbar `overflow-x:auto`, table `sticky left0` para domain, `launch-row grid auto-fit 80px` fix @320

### 2.5 Quick Wins P0 (1-2 sprints)

| # | Archivo:Línea | Oportunidad | Criterio aceptación |
|---|---|---|---|
| Q1 | `neural/index.html:43`, `control/index.html:20`, `control/app.js:135` | `span/div onclick` → `<button role=tab aria-selected>` | Lighthouse A11y 100, keyboard nav |
| Q2 | `neural/style.css:5`, `control/style.css:1` | `tokens.css` + `prefers-color-scheme` | Single source |
| Q3 | `neural/app.js:405` | Sticky search `fleet-search` debounce 250ms | <100ms |
| Q4 | `neural/app.js:567` | Portar `exportCSV` a control Certified/Fleet + `clipboard` | Parity |
| Q5 | `neural/style.css:432` | Usar `.skeleton` como loader tablas/charts | CLS ↓ |
| Q6 | `control/app.js:160 alert()` | Portar `toast` neural L54 + `aria-live` | No blocking |
| Q7 | `neural/app.js:91/144` | Eliminar duplicado `setRange/setActFilter` | No regression |

---

## 3. Alternativas de Flujo — Análisis Senior

### 3.1 Cuello #1: Singleton `DatabaseManager._execute_lock` (db_manager.py:58,184-215) serializa 3 writers paralelos → `SQLITE_BUSY` retry, -60% throughput

**Alternativa A — Queue Single-Writer Async + `aiosqlite` (Recomendada, P0)**
- Reemplazar `RLock` + `check_same_thread=False` por `asyncio.Queue` single-writer + `aiosqlite` (`requirements` ya tiene `aiosqlite>=0.20.0` pero no usado)
- `readonly_db.py:17 _MAX_POOL=4` ya existe para reads → mantener pool RO para `api_router`/`query_api`, mover todos writes a queue
- `execute_batch BEGIN IMMEDIATE` ya batch 3 statements `UPDATE ema + INSERT ema_history + INSERT cycle_history` (O4) → mantener pero vía queue
- **Pros:** Elimina 60% contención, `parallel 3` pasa a 6 en NVMe, `checkpoint_callback` no bloquea `update_ema_score`  
- **Contras:** Refactor `DatabaseManager` 2 semanas, test 25 fallos pre-existentes deben pasar  
- **Alternativa B — Mantener lock pero subir `busy_timeout` 60s→120s** → barato pero no escala, descartada

### 3.2 Cuello #2: `knowledge_packages` 430M sin partición (db_manager.py:383) → `FEED` mass `UPDATE absorbed_at` bloquea minutos, `GROUP BY domain` 4h

**Alternativa A — Sharding por `domain` (Recomendada, P1)**
- 18 shards `knowledge_packages_{domain}.db` (38 GB c/u) → 18 writers sin WAL contention, hospedar en D+E+G distribuido, `api_router UNION` 18 `ATTACH`
- O partición lógica: `knowledge_packages_wikidata` vs `knowledge_packages_web` + índice parcial `WHERE absorbed_at IS NULL`
- **Pros:** Paraleliza 18×, `FEED` por shard <10s, `VACUUM` por shard cabe en D (38GB <129GB libre)  
- **Contras:** Migración `split_by_domain.py` con `ATTACH` 18 shards, `INSERT SELECT WHERE domain='Physics'` 1-2 días en HDD, 1h en NVMe  
- **Alternativa B — Índice parcial `idx_absorbed_at WHERE absorbed_at IS NULL`** (ya warning `db_manager` `kp_idx_absorbed_at` no creado) → 1h dev, mejora FEED pero no resuelve lock → P0 quick win, no sustituto sharding

### 3.3 Cuello #3: `validate_paths()` exige dump para `web` (orchestrator.py:399,1827) → pipeline detenido sin `latest-all.json.gz` (borrado 143GB)

**Fix aplicado v2.0:** `validate_paths(require_dump=(phase in ('full','cascade')))` + dummy 0B en `E:/aria2/.../latest-all.json.gz`  
**Alternativa definitiva:** `phase` param ya fijado, no requiere más

### 3.4 Cuello #4: Single gzip sequential 142GB + `ijson` 0.8M/min + resume_offset re-parsea 80M (60min)

**Alternativa A — Byte-offset checkpoints (Recomendada, P0)**
- Guardar `gzip file offset` en `cascade_checkpoints` + `seek` → resume 0s vs 60min, `dissect_wikidata.py:398` + `dissect_wikidata_mp.py:211`
- + `wdsub Rust` (45min vs 137min) como alternativa si Python no alcanza 2.8M/min con `BATCH_SIZE 5000` + `JoinableQueue(20)` + 4 workers (ya 2.8M/min)

### 3.5 Cuello #5: Wikidata `fetch_entities_batch` 50 serial 20k req 7 días + SPARQL sin pagination OOM 2M

**Alternativa A — Paginated + async (Recomendada, P0)**
- `tools/update_wikidata.py:210 LIMIT 10000 OFFSET` loop hasta `len<10000` + `httpx.AsyncClient` pools 10 `http2=True` vs `requests.get` serial
- Añadir `retry_with_exponential_backoff` ya existe para SPARQL `[5,15,30]` pero no para `wbgetentities` → portar `tenacity` + `429` bucket per engine
- **Alternativa B — Mantener serial** → 7 días no viable para incremental semanal → descartada

### 3.6 Cuello #6: `httpx.Client` sync + `to_thread` + `Semaphore 5` (web_scraper.py:417,585) 130s por specialist

**Alternativa A — `httpx.AsyncClient` nativo (Recomendada, P0)**
- `AsyncClient limits 10, http2=True` + `asyncio.gather` → 3× throughput, elimina `Semaphore 5` workaround, `apply_random_delay 0.2-0.5s` per engine → `AsyncLimiter`
- `trafilatura extract include_tables False` → `True` para química/finanzas tabulares

### 3.7 Cuello #7: FTS5 triggers `kp_ai/ad/au` (db_manager.py:405) duplican writes → MP hace `DROP ALL FTS` y rebuild bloqueante

**Alternativa A — `content=''` + `rebuild` incremental (Recomendada, P1)**
- `CREATE VIRTUAL ... content='', triggers OFF` durante bulk + `INSERT INTO fts SELECT WHERE id>?` incremental (evita rebuild 430M)
- Ya existe workaround `DROP kp_au` en `orchestrator.py:1725` para `FEED`, extender a bulk

### 3.8 LLM / Ollama (llm_manager.py:516,646,31-33)

**Alternativa A — Pre-warm + `keep_alive 0` (Recomendada, P0)**
- `OLLAMA_KEEP_ALIVE 0` per query + `ensure_model_loaded` con `num_ctx 8192` → libera VRAM instant si pipeline pausa (vs `keep_alive 30m` mantiene 6GB)
- `MODEL_PHASE_B_CONCURRENCY phi4-mini:2` → con `parallel 3` + NVMe subir a 6-8, RTX 1660 6GB límite 2 para phi4, con RTX 4060 16GB → 4

**Alternativa B — Streaming parcial commit (P1)**
- `stream=True` chunks → commit cada summary parcial → no perder 6 items si batch timeout 360s

---

## 4. Alternativas de Sistema — Análisis Senior

### 4.1 Almacenamiento: HDD vs NVMe (Cuello #1)

**Alternativa A — Migración M2 2TB NVMe dedicada (Recomendada, P0) — Diferida a próxima semana (usuario confirmó)**
- **Por qué:** DB 684GB en HDD ST1000DM010 (80-150 IOPS, 150 MB/s seq) → `COUNT(*)` 4h, `wal_checkpoint TRUNCATE` 232min, FTS 4.4s. En NVMe SNV2S1000G (300k IOPS, 3500 MB/s) → `COUNT` 3-5min (50×), checkpoint 15min, FTS <200ms
- **Plan migración (ventana pipeline parado, WAL0):**
  1. Formatear M2 NTFS 2TB, letra `F:\`, `F:\expertia-data\` (confirmar letra, retención 7d en E: como backup)
  2. `robocopy E:\expertia-data\incubator.db F:\expertia-data\incubator.db /J /Z` (unbuffered, reanudable, 684GB ~12min en NVMe, 75min en HDD→NVMe)
  3. `PRAGMA integrity_check` en M2 (~1-2h vs 90h en HDD) + `quick_check` + `PRAGMA freelist_count` verify 18GB
  4. Cambiar `EXPERTIA_DATABASE_PATH=F:/expertia-data/incubator.db` en `.env` + `DATABASE_PATH` en `config/settings.py` + `pipeline_state.json` + Tasks `ExpertiaWikidataIncremental`/`ExpertiaIntegrityPoll`/`ExpertiaPipeline`
  5. Symlink opcional `E:\expertia-data\incubator.db -> F:\...` por compatibilidad, mantener `E:\` backup 7d antes de `del`
- **Interina HDD:** Liberar `D:\storage\incubator.db` stale 318GB → D free 448GB (no cabe 684GB, pero sirve staging sharding)
- **Alternativa B — Sharding sin M2:** 18 shards 38GB c/u en D+E+G distribuido → paraleliza 18 writers sin WAL contention, cabe en discos actuales → P1 si M2 se retrasa
- **Alternativa C — Mantener HDD + `auto_vacuum=INCREMENTAL`:** Rebuild DB con `page_size 8192` + `auto_vacuum=INCREMENTAL` → `PRAGMA incremental_vacuum(N)` gradual sin copiar 684GB → mitiga pero no resuelve IOPS → descartada como única

### 4.2 WAL, `page_size`, `auto_vacuum`

- **WAL actual:** `wal_autocheckpoint 500` runtime vs file 1000 desalineado, `wal_checkpoint(RESTART)` cada 10 batches + `PASSIVE` cada 60s por `query_api.py:31` → `RESTART` bloquea readers (dashboard 503). **Recomendada:** `wal_autocheckpoint 1000` + `PRAGMA journal_size_limit=100MB` + `PASSIVE` siempre, `TRUNCATE` nocturno cron (no cada 60s)
- **`page_size 4096`:** 179M pages, freelist 4.7M. `8192` reduciría a 89M pages, freelist 2.3M, seq I/O +10%. **Requiere VACUUM rebuild** (imposible hoy, 258GB libres <684GB) → hacer en M2 con `VACUUM INTO`
- **`auto_vacuum 0 NONE`:** 18GB freelist no reclamable. **Recomendada:** `INCREMENTAL` en nuevo DB file → `incremental_vacuum` gradual
- **`temp_store MEMORY`:** `db_manager` pone `MEMORY` pero `VACUUM` 684GB OOM 17GB RAM (documentado `batch_run_id` índice evitado). **Recomendada:** `temp_store=FILE` para `VACUUM`, `MEMORY` solo queries

### 4.3 Windows Defender

- `Get-MpPreference ExclusionPath` requiere admin → no verificado. Sin exclusión, Defender escanea cada WAL sync (500 pages ~2MB) y cada `INSERT` JSON con MsMpEng → picos CPU+I/O HDD. **Recomendada (P0):** `Add-MpPreference -ExclusionPath "E:\expertia-data", "D:\proyectos\expertia\incubator-root"` + `ExclusionProcess "python.exe"` (admin PowerShell) — ya documentado, requiere admin

### 4.4 Backup & Seguridad

- **Backup hoy:** Solo `VACUUM INTO` method en código no ejecutado, dumps 235MB `activity_log`/`cascade_checkpoints` en `.github/workflows`, schema 9KB, sin snapshot físico 684GB → riesgo pérdida meses. **Recomendada P0:** Nightly `VACUUM INTO` a disco externo USB 2TB `G:\backups\incubator.daily.db` (1h NVMe, 4h HDD) retención 7d `robocopy /MIR` + WAL archiving horario (2MB) + VSS cada 6h + `PRAGMA integrity_check` weekly (20min NVMe)
- **Secrets:** `.env` plano con `EXPERTIA_PUBMED_API_KEY`, `OPENALEX_API_KEY` (plain), `EXPERTIA_API_KEY` vacío → `/api` desprotegido en LAN. **Recomendada:** Rotar keys, mover a `System Env` + `Vault`/`Doppler`, forzar API key en prod, `CORS allow localhost` bien, añadir `healthz` DB `SELECT 1`, FTS `MATCH` sanitizar `"` (injection), `EXCLUDED_DOMAINS` solo 3 → ampliar

---

## 5. Epics Detallados v2.0 — Historias con Criterios de Aceptación

### Epic 1 — Sistema M2 + DB Hardening (P0, 1 semana, desbloqueador)

| Historia | Archivos:Líneas | Criterio aceptación | Estimación |
|---|---|---|---|
| E1.1 Migrar DB a M2 F:\ | `config/settings.py:27`, `.env:EXPERTIA_DATABASE_PATH`, `tools/launcher.py:29`, `Get-ScheduledTask Expertia*` | `robocopy` 684GB <20min, `PRAGMA integrity_check` en M2 `ok` <2h, `COUNT(*)` <5min, Tasks actualizadas, symlink E→F, backup 7d en E | 1d |
| E1.2 `auto_vacuum=INCREMENTAL` + `page_size 8192` | `database/db_manager.py:114-122`, nuevo `VACUUM INTO` | Nuevo DB `F:\` con `PRAGMA auto_vacuum=1`, `page_size=8192`, `freelist 0`, `incremental_vacuum` test `PRAGMA freelist_count` ↓ | 1d (en M2) |
| E1.3 Defender exclusiones | `powershell Admin` | `Get-MpPreference` muestra `E:\expertia-data`, `D:\...incubator-root`, `python.exe` | 0.5d (requiere admin) |
| E1.4 Backup nightly `VACUUM INTO` externo | `database/db_manager.py:backup()`, `G:\backups\` | `schtasks /create ExpertiaBackupDaily 02:00 VACUUM INTO` retención 7d, `integrity_check` weekly | 0.5d |

### Epic 2 — Interface Unificada (P0/P1, 1 mes)

| Historia | Archivos:Líneas | Criterio |
|---|---|---|
| E2.1 `tokens.css` + A11y tabs | `neural/style.css:5`, `control/style.css:1`, `neural/index.html:43` | `role=tablist/tab`, `aria-selected`, `ArrowLeft/Right`, `focus-visible`, Lighthouse A11y 100 |
| E2.2 Tabla flota virtual | `neural/app.js:405`, nuevo `frontend/shared/components/fleet-table.js` | 500 rows sin jank, search 250ms <100ms, paginación 50, column picker |
| E2.3 SSE vs polling | `neural/app.js:124 startPolling 3s`, `control/app.js:67 10s` | `EventSource /api/stream` SSE, `ETag`/`Last-Modified`, TTI 1.2s→400ms |
| E2.4 Command palette `Cmd+K` | `neural/app.js:42 onKey` | Fuzzy search especialistas, acciones `Kill, Theme, Export` |

### Epic 3 — Flujo Pipeline (P0, 2-4 semanas)

| Historia | Archivos | Criterio |
|---|---|---|
| E3.1 Queue single-writer `aiosqlite` | `database/db_manager.py:58`, `readonly_db.py:17` | `parallel 3` → 6, contención -60%, `SQLITE_BUSY` 0 |
| E3.2 Byte-offset checkpoints | `dissect_wikidata.py:398`, `dissect_wikidata_mp.py:211` | Resume 60min→0s, `cascade_checkpoints` guarda `gzip offset` |
| E3.3 `httpx.AsyncClient` pools | `web_scraper.py:417,585`, `academic_sources.py:256` | 130s→40s por specialist, `http2`, `AsyncLimiter` |
| E3.4 FTS `content=''` incremental | `dissect_wikidata_mp.py:386`, `orchestrator.py:1725` | Rebuild 430M → `WHERE id>?` incremental <10s |

### Epic 4 — Calidad & Trust (P1, 1 mes)

| Historia | Archivos | Criterio |
|---|---|---|
| E4.1 `sources[]` por claim | `tools/update_wikidata.py:154 build_structured_knowledge`, `knowledge_ingestor.py` | JSON `{"claim","source_url","confidence","retrieved_at"}`, UI badge, tests `test_s3` |
| E4.2 Quality gate 0.90 + fastText | `content_quality.py`, `web_scraper.py:595` | `suitability 0.30→0.40` Medicine, `is_garbage` fastText, `EXCLUDED_DOMAINS` ampliar |
| E4.3 `source_reputation` tier promotion | `source_reputation.py`, `academic_sources.py:99` | `search_openalex` con `trust_score` DB, CB `tenacity` |

### Epic 5 — Observabilidad (P1, 2 semanas)

| Historia | Archivos | Criterio |
|---|---|---|
| E5.1 `/metrics` Prometheus | `metrics.py:137`, nuevo `query_api.py: /metrics` | `prometheus_client` counters `knowledge_packages_total`, `wal_size`, `ema_score`, Grafana dashboard |
| E5.2 Structured JSON logs | `config/log_setup.py`, `logs/` 1.82GB | `structlog` + `orjson`, Loki, `healthz` DB `SELECT 1` |
| E5.3 Watchdog hardening | `tools/watchdog.py:43` | `stuck 20min` + `freelist>5%` + `WAL>1GB` alertas, `pipeline_monitor.py` 5min |

### Epic 6 — Producto Semántico & Auth (P2, 1-2 meses)

| Historia | Archivos | Criterio |
|---|---|---|
| E6.1 Embeddings local | `knowledge_ingestor.py:26`, nuevo `knowledge_embeddings` | `all-MiniLM-L6-v2` 80MB, `sqlite-vec` HNSW, `POST /knowledge/semantic_search` <300ms |
| E6.2 Auth RBAC | `api_router.py:53 verify_api_key`, `.env:EXPERTIA_API_KEY` | JWT, `admin/readonly`, `X-API-Key` obligatorio prod |
| E6.3 Export Parquet | `api_router.py` | `GET /export?domain=Physics&format=parquet` 38GB shard |

---

## 6. Herramientas Nuevas vNext

| Herramienta | Ubicación | Propósito | Estado |
|---|---|---|---|
| `tools/poll_integrity.ps1` | Ya existe 1708B | Poll `fase2c_integrity.log` cada 2h, auto-relanza pipeline | Activo PID 20080 (deshabilitado tras assumed ok) |
| `tools/check_integrity_once.ps1` | Ya existe 829B | Check `ok` → relanza pipeline (respaldo Scheduled Task) | Task `ExpertiaIntegrityPoll` cada 2h |
| `tools/migrate_to_m2.ps1` | **Nuevo** | `robocopy /J /Z`, `PRAGMA integrity_check`, cambio `.env`, Tasks | Pendiente M2 |
| `frontend/shared/tokens.css` | **Nuevo** | Design tokens unificados | Pendiente |
| `frontend/shared/components/fleet-table.js` | **Nuevo** | Tabla virtual + search + paginación | Pendiente |
| `scripts/auto_monitor.ps1` | Existe 310B | Monitor progreso → integrar Prometheus | Existe |
| `database/migrate_incremental_vacuum.py` | **Nuevo** | `VACUUM INTO` con `page_size 8192` + `auto_vacuum=INCREMENTAL` | Pendiente |

---

## 7. Arquitectura Objetivo

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Frontend (unificado)                                                    │
│  tokens.css + fleet-table.js + SSE /api/stream + Cmd+K                 │
│  neural (canvas) + control (Plotly lazy) + shared components           │
└──────────────────────────┬──────────────────────────────────────────────┘
                           │ REST + SSE + JWT
┌──────────────────────────▼──────────────────────────────────────────────┐
│  API (FastAPI 8011) + readonly_db pool 4 + /metrics Prometheus        │
│  /knowledge/search (FTS trigram <200ms) + /semantic_search (vec)      │
└──────────────────────────┬──────────────────────────────────────────────┘
                           │ aiosqlite Queue single-writer
┌──────────────────────────▼──────────────────────────────────────────────┐
│  DB M2 F:\expertia-data\incubator.db (684GB→750GB, page 8192,          │
│  auto_vacuum INCREMENTAL, WAL 100MB limit, TRUNCATE nightly)           │
│  18 shards lógicos (38GB c/u) + FTS content='' incremental             │
└──────────────────────────┬──────────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────────┐
│  Pipeline (orchestrator) — 6-8 parallel en NVMe (3 en HDD)             │
│  Phase A: byte-offset checkpoints + MP 4 workers 2.8M/min              │
│  Phase B: httpx.AsyncClient pools 10, LLM keep_alive 0, streaming      │
│  Phase C: queue writer + Bloom persistido + CB per engine              │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Riesgos, Mitigaciones y Tradeoffs

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| HDD cuello persiste hasta M2 | Alta | 90h integrity, 4h count | M2 P0 semana 1, sharding interino |
| `VACUUM` sin M2 falla (258GB libres <684GB) | Alta | No reclamar 18GB freelist | `INCREMENTAL` en M2, no intentar VACUUM en E |
| Dual python (`hermes` + `uv`) WAL contention | Media | 2× RAM, busy | Dejar solo hermes (kill uv 3620/2888), fix `launch_all.cmd` |
| Secrets en `.env` plano | Alta | Exposición PubMed/OpenAlex | Rotar, `System Env` + Vault, forzar `EXPERTIA_API_KEY` |
| Logs 1.82GB 861 files sin agregación | Alta | Diagnóstico imposible | `structlog` + Loki, `RotatingFileHandler` central + `VSS` |
| FTS syntax injection `MATCH "` | Media | 500 error | Sanitizar `re.escape` FTS5 |
| SPARQL OOM 2M bindings | Media | Incremental semanal falla | Pagination `LIMIT 10000 OFFSET` + `since` cursor |
| Ollama VRAM 6GB single model | Alta | 4min overhead por ronda | `keep_alive 0` + `parallel 2` phi4, `stream` parcial |

**Tradeoff senior:** Invertir 1 semana + €90 M2 2TB corrige 70% riesgo con 10-50× ganancia perf vs 1 mes de micro-optimizaciones HDD-bound que solo dan 10%.

---

## 9. Timeline & Milestones

| Semana | Milestone | Entregables | Métrica éxito |
|---|---|---|---|
| **W1 (ahora)** | **P0 Sistema** | M2 comprado, `pipeline_assumed_ok.flag`, pipeline web activo, `tokens.css` + A11y Q1-Q7, `poll_integrity` service, Defender exclusiones (admin) | Pipeline activo 24h sin freeze, Lighthouse 90 |
| **W2-3** | **P0 Flujo** | Queue `aiosqlite`, byte-offset checkpoints, `httpx.AsyncClient`, FTS incremental, `validate_paths` fix ya hecho | Phase A 137min→45min, Phase B 130s→40s por specialist |
| **W4** | **Migración M2** | `migrate_to_m2.ps1` ejecutado, `integrity_check` <2h `ok`, `page_size 8192` + `INCREMENTAL`, `VACUUM INTO` externo nightly | `COUNT(*)` 4h→3min, `VACUUM` posible |
| **W5-6** | **P1 Calidad/Observabilidad** | `sources[]` + fastText, `source_reputation` CB, `/metrics` Prometheus + Grafana, `healthz` | `suitability` 0.85→0.90, Grafana dashboard |
| **W7-8** | **P2 Producto** | Embeddings MiniLM + `sqlite-vec` + `/semantic_search` + Auth JWT + Export Parquet | Semantic <300ms, export 38GB shard |

---

## 10. Métricas & Criterios de Éxito

| Métrica | Hoy | Objetivo v2.0 | Cómo medir |
|---|---|---|---|
| `COUNT(*)` knowledge_packages | 4h | 3-5min | `time sqlite3 "SELECT COUNT(*)"` en M2 |
| FTS `MATCH` frío | 4.4s | <200ms | `pytest` benchmark `benchmarks/` |
| Phase A throughput | 0.8M/min | 2.8M/min | `metrics.py` |
| Phase B parallel | 3 | 6-8 | `orchestrator --parallel` |
| WAL size | 2.4MB (truncado) | <100MB estable | `Get-Item *.db-wal` |
| Freelist | 18GB (2.65%) | 0 | `PRAGMA freelist_count` |
| Backup | 0 físico | Nightly `VACUUM INTO` 7d | `G:\backups\` |
| Lighthouse A11y | ~70 | 100 | `axe-core` CI |
| TTI Map | 1.2s | 400ms | `lighthouse` |
| EMA avg | 0.995 Legend | estable | `specialist_registry` |

---

## 11. Apéndice — Inventario y Decisiones

### 11.1 Archivos clave y líneas

| Concepto | Path:Línea |
|---|---|
| Tiers/EMA | `orchestrator.py:38-66`, `643-701`, `53-59`, `809-911` |
| Cascade | `425-807`, `994-1184` |
| Nurture/Web | `1437-1489`, `1491-1649`, `1904-2013` |
| LLM VRAM | `llm_manager.py:309,516-600,493` |
| DB pragmas | `database/db_manager.py:114-122`, `dissect_wikidata_mp.py:78-81` |
| Frontend neural | `frontend/neural-horizon/app.js:91/144,405`, `style.css:5,132,242` |
| Frontend control | `frontend/control-center/app.js:135,559,773,1001,1100,1140`, `style.css:1,115,589,682,874,1101` |
| Watchdog | `tools/watchdog.py:43,145,208` |
| Launcher | `tools/launcher.py:29,92,110,152` |
| Incremental | `tools/update_wikidata.py:83,111,210` |
| Storage stale | `D:\storage\incubator.db` 318GB 29/06 |

### 11.2 Decisiones registradas

- **M2 2TB dedicado F:\** — Confirmado usuario 23/08, ventana pipeline parado, retención 7d en E: (pendiente instalación)
- **Fallback `quick_check` diferido** — 100-120h en HDD, no viable ahora, se hará en M2 (1-2h)
- **Integridad asumida** — 92.8h sin error + validaciones previas, flag `integrity_assumed_ok.flag` 23/08 21:26, pipeline relanzado web con fix `validate_paths(require_dump=phase in cascade/full)` + dummy 0B
- **Dual python** — `hermes venv` parent → `uv cpython-3.11` child es normal (shim), no duplicado real

### 11.3 Próximos pasos inmediatos (mañana)

1. Revisar este plan y priorizar P0 vs P1 (¿Auth P0?)
2. Comprar M2 2TB NVMe (C SNV2S1000G ya ocioso pero 1TB <684GB, necesita 2TB)
3. Ejecutar `Add-MpPreference -ExclusionPath` (admin) + `migrate_to_m2.ps1` dry-run
4. Implementar `tokens.css` + Q1-Q7 (1-2 sprints)

---

*Documento generado 2026-08-23 21:40 — Síntesis de 3 auditorías muy exhaustivas (frontend 8 archivos, backend 14.5k líneas, infra 684GB DB + 4 discos). Listo para revisión y ejecución Build Mode.*
