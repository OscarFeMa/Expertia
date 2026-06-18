# Estado del Proyecto — Expertia Synaptic Archive

**Última actualización:** 2026-06-08

> ⚠️ Documento histórico. Consultar `PROJECT_STATUS.md` para estado actual.

## Resumen

Expertia es un motor de orquestación de agentes especializados para hardware local (Windows 11, RTX 1660 6GB VRAM, 32GB RAM). Opera 18 especialistas raíz con modelos Ollama, pipeline de scraping + destilación LLM, extracción multilingüe (en, es, fr, de, pt, it), y 23 consejos super-expertos.

### Componentes Actuales

- **18 Especialistas** — 14 sobrevivientes + 4 nuevos (Linguistics, Psychology, EnvironmentalScience, Sociology)
- **Pipeline**: Phase A (dump Wikidata → QIDs matched) + Phase B (Nurture v2 con Tier Ascension)
- **Multilingüe**: 6 idiomas en Wikidata labels, descripciones, SPARQL, Wikipedia
- **23 Super-Expertos**: Incluye SocietyAndCulture, LanguagesLinguistics actualizado, NeuroscienceCognition, ClimateEnvironment
- **Dashboard Neural Horizon**: API + frontend estático con control de pipeline, monitor, charts

### 18 Especialistas

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

### 23 Super-Expertos

EconomyFinance, ArtificialIntelligence, BiotechnologyHealth, QuantumPhysics, CybersecurityDefense, ClimateEnvironment, SpaceExploration, DataPrivacyEthics, CulturalHeritage, EnergySustainability, CryptocurrencyBlockchain, EducationTechnology, ManufacturingIndustry, Telecommunications, MaterialsScience, UrbanPlanningSmartCities, DefenseStrategy, NeuroscienceCognition, GeneralKnowledge, LanguagesLinguistics, VisualArts, PerformingArts, **SocietyAndCulture**.

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
