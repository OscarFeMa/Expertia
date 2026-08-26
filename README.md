# Expertia — Synaptic Archive

Motor de orquestación de agentes especializados para hardware local. Gestiona una red de 18 micro-modelos LLM (Ollama) con pipeline de scraping web + destilación, validación por Wikidata, y scoring dinámico EMA.

## Overview

Expertia es un sistema de conocimiento autónomo, soberano y local-first. Opera mediante:

- **18 especialistas raíz** con modelos ajustados por hardware (RTX 1660 6GB VRAM)
- **Pipeline Phase B** (Web Scraping + LLM distillation) con scoring dinámico EMA
- **Extracción multilingüe** (en, es, fr, de, pt, it) desde Wikidata + Wikipedia
- **Dashboard Neural Horizon** (API + frontend) con control de pipeline, charts y monitor
- **Launcher parametrizable** (`launcher.cmd`) y **watchdog** anti-congelación

## 18 Especialistas

Modelos activos: `gemma3:4b` (3), `phi4-mini:4k` (10), `qwen2.5-coder:3b` (5). Dominios gestionados: SoftwareEngineering, Mathematics, Medicine, LegalSystem, PhilosophyHistory, FinanceEconomics, Physics, Cybersecurity, Geopolitics, DataScience, Chemistry, ArtHistory, Electronics, Astronomy, Linguistics, Psychology, EnvironmentalScience, Sociology.

## Project Structure

```
incubator-root/
├── config/
│   └── settings.py           # Configuración centralizada (DB_PATH → E:/expertia-data/incubator.db)
├── database/
│   ├── __init__.py
│   ├── db_manager.py         # SQLite singleton thread-safe
│   └── readonly_db.py        # Conexión de solo lectura (API)
├── tools/
│   ├── launcher.py           # Lanzador con menú interactivo + CLI
│   ├── watchdog.py           # Watchdog anti-congelación y reinicio
│   ├── spawn_specialist.py   # Alta manual de sub-especialistas (P279)
│   ├── pipeline_monitor.py   # Monitor en vivo del pipeline
│   └── update_wikidata.py    # Utilidades de actualización Wikidata
├── archive/
│   ├── scripts-onetime/      # Scripts one-off (check_*, clean_*, fix_*, rebuild_fts5_*)
│   └── docs/                 # Manuales de arquitectura heredada
├── orchestrator.py           # Pipeline controller principal (--phase full|web|nurture|feed|cascade)
├── web_scraper.py            # Scraper moderno (DDGS + Trafilatura)
├── llm_manager.py            # Gestor de modelos Ollama
├── dissect_wikidata_mp.py    # Extractor Wikidata streaming multiproceso
├── query_api.py              # API Neural Horizon (puerto 8011)
├── api_router.py             # Rutas de la API
├── metrics.py                # Colector de métricas
├── content_synthesizer.py    # Destilador de packages desde contenido
├── launcher.cmd              # Acceso directo al launcher (menú interactivo)
├── launch_all.cmd            # (legacy) lanza pipeline full + API
└── requirements.txt
```

Base de datos: `E:/expertia-data/incubator.db` (no está en el repo).

## Requirements

- Python 3.11+ (`uv` recommended)
- Windows 11 (nativo, sin Docker/WSL)
- NVIDIA RTX 1660 (6GB VRAM), 32GB RAM
- Ollama con modelos: `gemma3:4b`, `phi4-mini:4k`, `qwen2.5-coder:3b`
- Dependencias en `requirements.txt`

## Installation

```bash
cd incubator-root
pip install -r requirements.txt
```

Instalar Ollama y modelos:
```bash
winget install Ollama.Ollama
ollama pull qwen2.5-coder:3b
ollama pull phi4-mini:4k
ollama pull gemma3:4b
```

## Usage

### Launcher (recomendado)

```bash
launcher.cmd                       # menú interactivo
launcher.cmd --mode web            # pipeline web continuo
launcher.cmd --mode web --duration 24 --specialist Physics
launcher.cmd --mode nurture --with-watchdog
launcher.cmd --mode feed --api     # también arranca query_api.py
```

Modos disponibles:
- `web` — alimentación web continua (sin límite temporal salvo señal, `--max-duration`, `--max-cycles` o congelación)
- `nurture` — crecimiento/mantenimiento continuo
- `feed` — una pasada de absorción de packages Wikidata
- `full` — cascade + feed + nurture (legacy)
- `cascade` — solo Phase A (Wikidata streaming)

### API (Neural Horizon)

```bash
python query_api.py
```

Panel web en `http://localhost:8011/neural/`.

### Pipeline directo (CLI)

```bash
# Alimentación web continua
python orchestrator.py --phase web --duration 999999

# Nurture continuo
python orchestrator.py --phase nurture

# Una pasada de feed
python orchestrator.py --phase feed

# Pipeline completo (cascade + feed + nurture)
python orchestrator.py --phase full
```

## Database Schema

### specialist_registry
- `id`, `domain`, `model`, `root_qid`, `properties`, `ema_score`, `tier`
- `packages_absorbed`, `status`, `parent_id`, `qid_path`, `created_at`, `updated_at`

### knowledge_packages
- `id`, `topic`, `source_url`, `domain`, `structured_knowledge`, `qid`, `subdomain_path`, `created_at`
- FTS5 virtual: `knowledge_packages_fts` (búsqueda fulltext)

### ema_history
- `id`, `specialist_id`, `ema_score`, `timestamp`

### pipeline_status
- `id`, `status`, `current_specialist`, `current_model`, `current_cycle`, `phase`, `elapsed_seconds`, `started_at`, `updated_at`

### activity_log / cycle_history / matched_qids / cascade_checkpoints / stored_packages
- Trazabilidad de actividad, ciclos, matching QIDs y checkpoints de Phase A.

## Pipeline Flow

1. **Inicialización**: Valida paths, registra especialistas en DB
2. **Phase A** (`full`/`cascade`): Wikidata streaming scanning con extracción progresiva (reanudable por checkpoint)
3. **Phase B** (`web`/`nurture`): Web scraping (DDGS) + destilación LLM + scoring EMA
4. **Auto-feed** (`full`/`feed`): absorbe packages Wikidata sin procesar
5. **Watchdog** (opcional): detecta congelación sin heartbeat y reinicia con la misma config

## Configuration

Editar `config/settings.py` para:
- Rutas de Wikidata dump y salida
- Timeouts y delays de búsqueda
- Intervalo de reportes
- Blocklist de labels QID

## License

Proyecto parte del ecosistema «Pensamiento Coral».

## Repository

https://github.com/OscarFeMa/Expertia