# Expertia — Synaptic Archive

Motor de orquestación de agentes especializados para hardware local. Gestiona una red de 18 micro-modelos LLM (Ollama) con pipeline de scraping web + destilación, validación por Wikidata, y un consejo de 23 super-expertos para síntesis cross-dominio.

## Overview

Expertia es un sistema de conocimiento autónomo, soberano y local-first. Opera mediante:

- **18 especialistas raíz** con modelos ajustados por hardware (RTX 1660 6GB VRAM)
- **Pipeline Phase B** (Web Scraping + LLM distillation) con scoring dinámico EMA
- **Extracción multilingüe** (en, es, fr, de, pt, it) desde Wikidata + Wikipedia
- **23 consejos super-expertos** de referencia estática con miembros ponderados
- **Dashboard Neural Horizon** con control de pipeline, charts y monitor
- **Reportes automáticos** cada 20 min

## 18 Especialistas

| Dominio | Modelo | Root QID |
|---|---|---|
| SoftwareEngineering | qwen2.5-coder:3b | Q80993 |
| Mathematics | qwen2.5-coder:3b | Q395 |
| Medicine | phi4-mini:3.8b | Q11190 |
| LegalSystem | llama3.2:3b | Q7748 |
| PhilosophyHistory | phi4-mini:3.8b | Q5891 |
| FinanceEconomics | phi4-mini:3.8b | Q8134 |
| Physics | phi4-mini:3.8b | Q413 |
| Cybersecurity | qwen2.5-coder:3b | Q3510521 |
| Geopolitics | llama3.2:3b | Q159385 |
| DataScience | qwen2.5-coder:3b | Q2374463 |
| Chemistry | phi4-mini:3.8b | Q2329 |
| ArtHistory | phi4-mini:3.8b | Q50637 |
| Electronics | qwen2.5-coder:3b | Q11650 |
| Astronomy | phi4-mini:3.8b | Q333 |
| **Linguistics** | **phi4-mini:3.8b** | **Q81798** |
| **Psychology** | **phi4-mini:3.8b** | **Q9418** |
| **EnvironmentalScience** | **phi4-mini:3.8b** | **Q188069** |
| **Sociology** | **llama3.2:3b** | **Q21201** |

## 23 Super-Expertos

Consejos estáticos de referencia (sin pipeline propio):

EconomyFinance, ArtificialIntelligence, BiotechnologyHealth, QuantumPhysics, CybersecurityDefense, ClimateEnvironment, SpaceExploration, DataPrivacyEthics, CulturalHeritage, EnergySustainability, CryptocurrencyBlockchain, EducationTechnology, ManufacturingIndustry, Telecommunications, MaterialsScience, UrbanPlanningSmartCities, DefenseStrategy, NeuroscienceCognition, GeneralKnowledge, LanguagesLinguistics, VisualArts, PerformingArts, SocietyAndCulture.

Cada consejo tiene miembros de los 18 especialistas con pesos que suman 1.0.

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
├── web_scraper.py            # Scraper moderno (DDGS + Trafilatura)
├── llm_manager.py            # Gestor de modelos Ollama
├── dissect_wikidata.py       # Extractor Wikidata streaming (ijson+gzip)
├── metrics.py                # Colector de métricas
├── knowledge_ingestor.py     # Ingestor de conocimiento
├── download_models.bat       # Descarga de modelos Ollama
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
