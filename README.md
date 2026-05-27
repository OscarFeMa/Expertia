# Expertia — Synaptic Archive

Motor de orquestación de agentes especializados para hardware local. Gestiona una red de 15 micro-modelos LLM (Ollama) con pipeline de scraping web + destilación, spawning de sub-especialistas validado por Wikidata, y un consejo de 22 super-expertos para síntesis cross-dominio.

## Overview

Expertia es un sistema de conocimiento autónomo, soberano y local-first. Opera mediante:

- **15 especialistas raíz** con modelos ajustados por hardware (RTX 1660 6GB VRAM)
- **Pipeline Phase B** (Web Scraping + LLM distillation) con scoring dinámico EMA
- **Spawning de sub-especialistas** con validación vía Wikidata P279 (parentesco directo/hermano)
- **Resolución de labels** por API Wikidata (`wbgetentities`) — sin diccionarios hardcodeados
- **22 consejos super-expertos** de referencia estática con miembros ponderados
- **Consola Streamlit** "Synaptic Archive" con estética pergamino, gráficos sunburst y control de pipeline
- **Reportes automáticos** cada 30 min

## 15 Especialistas

| Dominio | Modelo | Root QID | Corrección |
|---|---|---|---|
| SoftwareEngineering | qwen2.5-coder:3b | Q80993 | ✅ |
| Mathematics | deepseek-r1:1.5b | Q395 | ✅ |
| Medicine | phi4-mini:3.8b | Q11190 | ✅ |
| LegalSystem | llama3.2:3b | Q7748 | ✅ |
| PhilosophyHistory | gemma3:4b | Q5891 | ✅ |
| FinanceEconomics | gemma3:4b | Q8134 | ✅ |
| Physics | deepseek-r1:1.5b | Q413 | ✅ |
| Cybersecurity | qwen2.5-coder:3b | Q3510521 | ✅ corregido |
| Bioinformatics | phi4-mini:3.8b | Q128570 | ✅ corregido |
| Geopolitics | llama3.2:3b | Q159385 | ✅ corregido |
| DataScience | qwen2.5-coder:3b | Q2374463 | ✅ corregido |
| Chemistry | phi4-mini:3.8b | Q2329 | ✅ corregido |
| ArtHistory | gemma3:4b | Q50637 | ✅ corregido |
| Electronics | qwen2.5-coder:3b | Q11650 | ✅ corregido |
| Astronomy | phi4-mini:3.8b | Q333 | ✅ |

## 22 Super-Expertos

Consejos estáticos de referencia (sin pipeline propio):

EconomyFinance, ArtificialIntelligence, BiotechnologyHealth, QuantumPhysics, CybersecurityDefense, ClimateEnvironment, SpaceExploration, DataPrivacyEthics, CulturalHeritage, EnergySustainability, CryptocurrencyBlockchain, EducationTechnology, ManufacturingIndustry, Telecommunications, MaterialsScience, UrbanPlanningSmartCities, DefenseStrategy, NeuroscienceCognition, GeneralKnowledge, LanguagesLinguistics, VisualArts, PerformingArts.

Cada consejo tiene miembros de los 15 especialistas con pesos que suman 1.0.

## Sub-especialistas

Cuando un especialista acumula ≥100 packages por sub-QID, el pipeline puede spawnear un sub-especialista hijo:
1. **Filtro rápido**: label blocklist (generic/umbrella terms)
2. **Validación P279**: llama a Wikidata API para verificar parentesco directo (hijo) o hermano (comparte padre P279)
3. **Límites**: máx 20 total, máx 3 hijos por padre por ciclo

## Project Structure

```
incubator-root/
├── config/
│   └── settings.py           # Configuración centralizada
├── database/
│   ├── __init__.py
│   └── db_manager.py         # SQLite singleton thread-safe
├── crawler/                  # (legacy, no usado)
├── storage/
│   ├── incubator.db          # Base de datos SQLite
│   ├── packages/             # Paquetes de conocimiento
│   └── reports/              # Reportes automáticos
├── orchestrator.py           # Pipeline controller principal
├── expertia_console.py       # Consola Streamlit "Synaptic Archive"
├── web_scraper.py            # Scraper moderno (DDGS + Trafilatura)
├── llm_manager.py            # Gestor de modelos Ollama
├── dissect_wikidata.py       # Extractor Wikidata streaming (ijson+gzip)
├── metrics.py                # Colector de métricas
├── knowledge_ingestor.py     # Ingestor de conocimiento
├── launch_expertia.bat       # Lanzador Streamlit (PowerShell oculto)
├── install_models.bat        # Descarga de modelos Ollama
├── download_models.bat
└── requirements.txt
```

## Requirements

- Python 3.10+
- Windows 11 (nativo, sin Docker/WSL)
- NVIDIA RTX 1660 (6GB VRAM), 32GB RAM
- Ollama con modelos para 15 especialistas
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
ollama pull deepseek-r1:1.5b
ollama pull phi4-mini:3.8b
ollama pull llama3.2:3b
ollama pull gemma3:4b
```

## Usage

### Consola Synaptic Archive

```bash
streamlit run expertia_console.py
```

O desde el acceso directo de escritorio «Expertia Control Center».

La consola permite:
- Visualizar los 15 especialistas en tarjetas con métricas EMA, packages, status
- Gráfico de sol (sunburst) de la jerarquía de especialistas y sub-especialistas
- Control del pipeline: lanzar/parar, elegir especialista, modelo, fase, duración
- Pestalla de Super-Expertos con miembros ponderados
- Auto-refresh cada 5s, reportes cada 30 min

### Pipeline (CLI)

```bash
# Phase B: web scraping + LLM para un especialista
python orchestrator.py --phase web --specialist Physics --model deepseek-r1:1.5b --duration 3.0

# Sin especificar: ejecuta todos los especialistas en cascada
python orchestrator.py
```

## Database Schema

### specialist_registry
- `id`, `domain`, `model`, `root_qid`, `properties`, `ema_score`, `tier`
- `packages_absorbed`, `status`, `parent_id`, `qid_path`, `created_at`, `updated_at`

### knowledge_packages
- `id`, `topic`, `source_url`, `domain`, `structured_knowledge`, `qid`, `subdomain_path`, `created_at`

### ema_history
- `id`, `specialist_id`, `ema_score`, `timestamp`

### pipeline_status
- `id`, `status`, `current_specialist`, `phase`, `cycle`, `packages_this_session`, `started_at`, `updated_at`

### super_experts / super_expert_members
- Consejos de super-expertos (22) con miembros y pesos

## Pipeline Flow

1. **Inicialización**: Valida paths, registra especialistas en DB
2. **Phase A** (opcional): Wikidata streaming scanning con extracción progresiva
3. **Phase B** (principal): Web scraping (DDGS) + destilación LLM + scoring EMA
4. **Spawning** (cada 10 ciclos): Verifica QIDs candidatos, valida P279, crea sub-especialistas
5. **Reportes**: `orchestrator.py` genera gráficos EMA en `storage/reports/` al finalizar

## Configuration

Editar `config/settings.py` para:
- Rutas de Wikidata dump y salida
- Timeouts y delays de búsqueda
- Límites de sub-especialistas (`SUBSPECIALIST_THRESHOLD`, `MAX_SUBSPECIALISTS`, etc.)
- Blocklist de labels QID
- Intervalo de reportes

## License

Proyecto parte del ecosistema «Pensamiento Coral».

## Repository

https://github.com/OscarFeMa/Expertia
