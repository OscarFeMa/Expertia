# ENTRENO · Documento técnico avanzado — ExpertiaMath

**Versión:** 1.0 · **Fecha:** 2026-09-06 · **Estado:** entrenamiento en curso (paso 2140/8436, 25%)

---

## 1. Resumen ejecutivo

Se está adaptando `microsoft/Phi-4-mini-reasoning` (3.8B, MIT) al dominio
matemático de Expertia mediante **QLoRA** (fine-tuning eficiente con modelo base
cuantizado a 4 bits + adaptadores LoRA entrenables). Dataset: 45.000 ejemplos
de matemáticas formales extraídos de la propia base de conocimiento
(`knowledge_packages`, dominio Mathematics) + 5.000 de validación.
Entrenamiento dedicado en RTX 3070 8GB. Objetivo medible: superar al modelo
actual del especialista Mathematics en EMA (+0.01) y quality (+0.05).

## 2. Fundamento: por qué QLoRA y por qué funciona aquí

### 2.1 LoRA (Low-Rank Adaptation)

En vez de actualizar los 3.800M de pesos `W`, LoRA congela `W` y entrena una
descomposición de bajo rango del *delta*:

```
W' = W + (α/r) · B·A,   A ∈ R^(r×k), B ∈ R^(d×r), r = 16 << d
```

Con `r=16` sobre 7 módulos de atención/MLP (`q,k,v,o,gate,up,down`) solo
~27.7M de parámetros son entrenables (**0.73%** del modelo). El conocimiento
previo (5T tokens del base) se conserva; el adaptador aprende el *estilo y
contenido* del dominio: definiciones formales, fórmulas `P2534`, taxonomía
`P31/P279`.

### 2.2 Cuantización NF4 (QLoRA)

El base se carga en 4 bits NormalFloat con doble cuantización
(`bitsandbytes`, ~2.1–2.4GB para 3.8B) y el cómputo se hace en BF16.
La literatura (Dettmers et al., 2023) muestra paridad con fine-tuning FP16
para r≥16 en adaptación de dominio. Sin QLoRA, 3.8B en FP16 (~7.6GB pesos +
optimizador + activaciones) no cabría en 8GB.

### 2.3 Por qué el dominio matemático es ideal para SFT

- Lenguaje formal y verificable (fórmulas, definiciones), mínimo ruido
  subjetivo frente a humanidades.
- Cobertura Wikidata enorme y estructurada: 40.7M entidades `Q395` con
  propiedades `P2534` (fórmula definitoria), `P31/P279` (taxonomía).
- Evaluación objetiva posible: benchmarks GSM8K/MATH + quality del pipeline.

## 3. Selección del modelo base

| Modelo | Params | Licencia | GSM8K / MATH | Contexto | Veredicto |
|---|---|---|---|---|---|
| **Phi-4-mini-reasoning** | 3.8B | **MIT** | 94.6 MATH-500 / 57.5 AIME | 128K | **Elegido** |
| Phi-4-mini-instruct | 3.8B | MIT | 88.6 / 64.0 | 128K | Alternativa |
| Qwen2.5-Math-1.5B | 1.5B | Apache-2.0 | ~89 / ~65 (+79.7 con intérprete) | 4K | Descartado: EN/ZH solo, 4K ctx |
| Qwen2.5-Math-7B | 7B | Apache-2.0 | 95.9 / 83.6 | 4K | Descartado: no cabe en 8GB |
| Mathstral-7B | 7B | Apache-2.0 | 77.1 / 56.6 | 32K | Descartado: peor + grande |
| DeepSeekMath-7B | 7B | Custom | 88.2 / 51.7 | 4K | Descartado: licencia + tamaño |

Criterios: (1) calidad en razonamiento puro, (2) licencia permisiva para
futuro uso comercial (MIT > Apache-2.0 > Qwen/Llama/Gemma-restrictivas),
(3) que quepa en 8GB con QLoRA, (4) multilingüe (pipeline en ES/EN/FR/DE/PT/IT).

## 4. Dataset: `expertia-math-puro.jsonl`

### 4.1 Construcción (`tools/build_expertia_math_dataset.py`)

```sql
SELECT qid, topic, structured_knowledge, source_url
FROM knowledge_packages
WHERE domain='Mathematics' AND qid IS NOT NULL
ORDER BY id DESC  -- paginación keyset, sin COUNT(*) (4h en HDD)
```

Filtros: longitud 50–2000 chars, URL `wikidata.org/entity/`, descarte de
basura (`cookie/sign in/captcha`), preferencia `P2534`/`defining formula`,
deduplicación por `(qid, topic)`, shuffle semilla 42, split 90/10.

### 4.2 Estadísticas

- Train 45.000 líneas / ~44MB · Val 5.000 / ~4.9MB.
- Formato Alpaca extendido: `{system, instruction, input:"", output, metadata}`.
- Ejemplo: `instruction: "Explica Pythagorean theorem [Q11518]"`,
  `output: "Entity/Description/Properties (defining formula: a²+b²=c²) + Source"`.
- 100% inglés en muestra (Wikidata EN dominante); el multilingüe vendrá del
  propio base (MGSM 63.9).

### 4.3 Validez y leakage

Riesgo conocido: el val puede contener entidades vistas en train con otro
`topic` (deduplicación solo por par exacto). Mitigación aplicada: el val se usa
solo como señal de divergencia, no como benchmark; la evaluación real será
A/B en pipeline + GSM8K/MATH held-out.

## 5. Configuración de entrenamiento

| Hiperparámetro | Valor | Justificación |
|---|---|---|
| `r / alpha / dropout` | 16 / 32 / 0.05 | Compromiso capacidad/estabilidad; α=2r estándar |
| `target_modules` | q,k,v,o,gate,up,down | Atención + MLP (ganancia medida vs solo atención) |
| `seq_len` | 2048 | Cubre el 99% de ejemplos (<2000 chars); 4096 no cabe sin offload |
| `batch × accum` | 1 × 16 | Batch efectivo 16 (fórmula de max_steps: 45000×3/16 = 8436) |
| `epochs` | 3 | Suficiente para adaptación sin sobreajuste en 45k |
| `lr / scheduler / warmup` | 2e-4 / coseno / 0.03 | Estándar QLoRA; warmup evita divergencia inicial (loss 5.3→3.4) |
| `optim` | `paged_adamw_8bit` | -75% memoria de optimizer con paginación anti-picos |
| `compute` | BF16 (Ampere nativo) | +estabilidad vs FP16 en razonamiento; Turing no lo soporta |
| `gradient_checkpointing` | sí | Recomputo vs VRAM: -40% memoria, +30% tiempo |
| `save_steps / limit` | 200 / 3 | Un checkpoint por ~45min; resume siempre posible |
| `logging_steps` | 10 | Curva densa (120 pts en panel) |

Stack pinnneado: `torch 2.3.1+cu121, transformers 4.49.0, peft 0.12.0,
trl 0.9.6, accelerate 1.14.0, bitsandbytes 0.43.3` (`training/requirements-train.txt`).

### Presupuesto VRAM 8GB (medido, no teórico)

Pesos NF4 ~2.3GB + LoRA/grad/opt ~0.25GB + activaciones ckpt ~2.2GB +
overhead CUDA ~0.9GB ≈ **5.6–6.8GB**. Picos observados 7997MB. Sin offload.
Margen ~1GB: justo pero estable (0 OOM en 2000+ pasos).

## 6. Infraestructura

| | PC-3070 (entreno) | PC principal (web) |
|---|---|---|
| GPU | RTX 3070 Laptop 8GB, driver 616.56 | GTX 1660 6GB |
| Régimen | Dedicado 24/7, BF16, ~13s/paso | Pipeline web 18 esp., 8192 ctx |
| Rendimiento | ~4.5–16 pasos/min (×16 vs 1660) | — |
| Acceso | WinRM `expertia` + SSH (clave, en reparación) | local |

Nota térmica: 86–89°C sostenidos con un ventilador averiado; tras
reparación + base elevada: 72°C, relojes 945→1605MHz (+40% rendimiento).
Límite 90W no aplicable (laptop no lo soporta por hardware).

## 7. Dinámica observada

- Loss **5.30 → 0.65** en 2070 pasos: caída rápida fase 1 (warmup), meseta
  0.70–0.77 desde paso ~500 (típico SFT convergente, sin divergencias).
- Throughput: ~13s/paso medio (seq2048, ckpt, WDDM). ETA total ~30h desde cero.
- 3 muertes silenciosas sin traceback (20:15, ~10:00, 14:01), siempre sin
  reboot ni cierre de sesión; RAM plana (2.89GB), temperatura estable.
  Hipótesis abiertas: reset driver (TDR), intervención externa, sesión.
  Mitigación: checkpoints + resume + doble watchdog + forense automático.
  Experimento canario en curso para discriminar causa sistema vs proceso.

## 8. Resiliencia (diseño anti-pérdida)

1. `save_steps=200` → pérdida máxima 45 min.
2. `resume_from_checkpoint` automático (último `checkpoint-*`).
3. Watchdog local 3070 (`Watch-Train.ps1`, cada 2 min, relanza con resume).
4. Auto-relanzamiento desde el PC principal (sync cada 5 min, si stale >25 min).
5. Forense previo a relanzar (GPU + última línea de log).
6. Historial de loss persistente entre sesiones (curva continua).

## 9. Observabilidad

- Pestaña **ENTRENO** (`/neural/`, v23): KPIs (progreso, ETA con ritmo medido,
  loss, GPU util/temp, VRAM/potencia), curva SVG con zoom/pan/leyenda, log
  vivo 2 líneas, informes plegables, botón de carpeta.
- Espejo cada 5 min (`tools/sync_train_status.ps1` + schtasks
  `ExpertiaSyncTrainIn`) con credencial DPAPI; API expone `origen: 3070`.
- Monitor standalone en el 3070 (`monitor_train.py`, `:8077`, stdlib).

## 10. Plan de promoción a producción

1. Completar 8436 pasos → `trainer.save_model()` + `train_info.json`.
2. `merge LoRA→FP16 → quant Q4_K_M (llama.cpp)` → `ollama create ExpertiaMath`
   (ver `Modelfile-ExpertiaMath`).
3. Registrar en `SPECIALIST_REGISTRY` (Mathematics) y canario 1h en pipeline.
4. Criterio de promoción: `EMA +0.01` y `quality +0.05` vs base, sin timeouts.
5. Si no supera: el adaptador queda versionado en `adapters/` y se itera
   (más épocas, r32, o dataset ampliado).

## 11. Riesgos

| Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|
| Muerte silenciosa recurrente | media | retraso 45min c/u | ya mitigado (6 capas §8) |
| Sobreajuste (loss→0) | baja | modelo inútil | early stopping por val + A/B |
| Térmica portátil | media | throttling/muerte | ventilador reparado, monitor 89°C→alerta |
| Deriva dataset (EN-only) | media | peor ES | evaluar MGSM; ampliar ES en v2 |
| Licencia futura | baja | — | MIT desde el día 1 |

## 12. Reproducibilidad

- USB `EXPERTIA-TRAIN` (9.9GB): base + datasets + wheels offline + Python
  redist + `Install-ExpertiaTrain.cmd` plug-and-run → `C:\training`.
- Todo el código versionado: `tools/usb-install/` (scripts), `training/`
  (requisitos), este documento.
- Semillas fijas (dataset seed 42); entrenamiento determinista salvo
  paralelismo CUDA (documentado, no garantizado bit a bit).
