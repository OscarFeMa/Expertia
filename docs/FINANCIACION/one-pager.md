# Expertia — one-pager (EN)

**Expertia** is a 24/7 autonomous knowledge-incubation system: 18 domain
specialists continuously absorb, distill and consolidate web + Wikidata knowledge
into a structured 193M+ package database.

**Proven results (2026, commodity hardware):**
- 2 house fine-tunes in production (ExpertiaMath, ExpertiaPhysics): eval
  perplexity -92%/-93% vs base, 0.89-0.91 production quality, 100% cycle success.
- 11/18 specialists upgraded to current-gen 4B models with measured before/after.
- Full pipeline: scraping → LLM distillation → EMA quality scoring → reporting.

**What we need:** burst compute for fine-tuning (spot GPU hours), not 24/7
(feeding already runs free on owned hardware).

**Ask:** cloud credits to run ~10 domain fine-tunes (~30h each on 4090-class)
plus eval overflow. Open-source outputs (models + datasets on Hugging Face).
