# Estado del Proyecto — Expertia Synaptic Archive

**Última actualización:** 2026-05-26

> ⚠️ Este documento ha sido reemplazado por `PROJECT_STATUS.md` (en inglés).
> Se mantiene por compatibilidad histórica. Consultar `PROJECT_STATUS.md` para el estado actual.

## Resumen

Expertia es un motor de orquestación de agentes especializados para hardware local (Windows 11, RTX 1660 6GB VRAM, 32GB RAM). Opera 15 especialistas raíz con modelos Ollama, pipeline de web scraping + destilación LLM, spawning de sub-especialistas validado por Wikidata, y 22 consejos super-expertos.

### Componentes Actuales

- **15 Especialistas** con QIDs corregidos vía Wikidata API
- **Pipeline Phase B**: Web scraping (DuckDuckGo) + destilación LLM + scoring EMA dinámico
- **Sub-especialistas**: Spawning con validación P279 (parentesco directo/hermano), resolución de labels por API
- **22 Super-Expertos**: Consejos estáticos con miembros ponderados
- **Consola "Synaptic Archive"**: Streamlit con tarjetas, sunburst, control de pipeline, reportes automáticos

### 15 Especialistas

| Dominio | Modelo | Root QID |
|---|---|---|
| SoftwareEngineering | qwen2.5-coder:3b | Q80993 |
| Mathematics | deepseek-r1:1.5b | Q395 |
| Medicine | phi4-mini:3.8b | Q11190 |
| LegalSystem | llama3.2:3b | Q7748 |
| PhilosophyHistory | gemma3:4b | Q5891 |
| FinanceEconomics | gemma3:4b | Q8134 |
| Physics | deepseek-r1:1.5b | Q413 |
| Cybersecurity | qwen2.5-coder:3b | Q3510521 |
| Bioinformatics | phi4-mini:3.8b | Q128570 |
| Geopolitics | llama3.2:3b | Q159385 |
| DataScience | qwen2.5-coder:3b | Q2374463 |
| Chemistry | phi4-mini:3.8b | Q2329 |
| ArtHistory | gemma3:4b | Q50637 |
| Electronics | qwen2.5-coder:3b | Q11650 |
| Astronomy | phi4-mini:3.8b | Q333 |

### 22 Super-Expertos

EconomyFinance, ArtificialIntelligence, BiotechnologyHealth, QuantumPhysics, CybersecurityDefense, ClimateEnvironment, SpaceExploration, DataPrivacyEthics, CulturalHeritage, EnergySustainability, CryptocurrencyBlockchain, EducationTechnology, ManufacturingIndustry, Telecommunications, MaterialsScience, UrbanPlanningSmartCities, DefenseStrategy, NeuroscienceCognition, GeneralKnowledge, LanguagesLinguistics, VisualArts, PerformingArts.

### Correcciones de QIDs Raíz (Mayo 2026)

9 QIDs corregidos tras verificación en Wikidata API:
- SoftwareEngineering: Q11661 (tecnología de la información) → Q80993 (ingeniería de software)
- PhilosophyHistory: Q315 (lenguaje) → Q5891 (filosofía)
- Cybersecurity: Q151211 (sin label) → Q3510521 (seguridad informática)
- Bioinformatics: Q193635 (Alan Greenspan) → Q128570 (bioinformática)
- Geopolitics: Q79461 (Daphne) → Q159385 (geopolítica)
- DataScience: Q1156829 (sin label) → Q2374463 (ciencia de datos)
- Chemistry: Q11158 (ácido) → Q2329 (química)
- ArtHistory: Q178561 (batalla) → Q50637 (historia del arte)
- Electronics: Q11663 (clima) → Q11650 (electrónica)

### Archivos Eliminados (Limpieza Mayo 2026)

`auto_incubator.py`, `hybrid_pipeline.py`, `dashboard_original.py`, `database/connection.py`, `database/queries.py`, `master/auditor/ecosystem_auditor.py`, `scripts/seed_experts.py`, `scripts/run_evolution_test.py`, `original_dash.py`.

---
*Generado por Cascade*
