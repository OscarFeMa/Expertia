# ENTRENO — ExpertiaMath

**Actualizado:** 2026-09-06 (paso 2110/8436, 25%)

## Objetivo

Dotar a Expertia de un especialista matemático propio, **ExpertiaMath**: un modelo
fine-tuneado con el conocimiento matemático puro acumulado por el pipeline
(40M+ paquetes Wikidata del dominio Mathematics), desplegable en Ollama como
cualquier otro especialista y evaluable contra su modelo base.

Meta final: `ollama create ExpertiaMath` → registrarlo como modelo del
especialista Mathematics → medir ganancia de calidad (EMA/quality) frente a
`Qwen2.5-Math-1.5B` actual.

## Qué estamos haciendo

Fine-tuning **QLoRA** (adaptadores de bajo rango sobre modelo cuantizado 4-bit)
de `microsoft/Phi-4-mini-reasoning` (3.8B, licencia MIT, apta para futuro uso
comercial) con 45.000 ejemplos de matemáticas formales + 5.000 de validación.

Elegido frente a `Qwen2.5-Math-1.5B` por: mejor razonamiento general (MATH 64.0),
128K de contexto, español + 22 lenguas y licencia MIT.

## Cómo

| Pieza | Detalle |
|---|---|
| Dataset | `expertia-math-puro.jsonl` (45k) + `_val` (5k). Extraído en solo-lectura de `knowledge_packages WHERE domain='Mathematics'` con `qid NOT NULL` y fórmula `P2534` preferente. Formato instrucción/respuesta, sin opiniones web. Generador: `tools/build_expertia_math_dataset.py` |
| Método | QLoRA NF4 double-quant, LoRA r16/alpha32 sobre 7 módulos, `seq2048`, `batch 1 × accum 16`, `adamw_8bit`, `BF16`, checkpoint cada 200 pasos, resume automático. Script: `training/train_expertia_math.py` (copia versionada en `tools/usb-install/`) |
| Dónde | PC dedicado **RTX 3070 Laptop 8GB** (`MAKEDERPC`, usuario local `expertia`), acceso WinRM desde el PC principal. Sin turnos: entrena 24/7 hasta completar (8436 pasos, 3 épocas) |
| Resiliencia | Watchdog local (`Watch-Train.ps1`, relanza con resume) + auto-relanzamiento desde el PC principal (sync cada 5 min). Checkpoints 200/400/…/2000 verificados |
| Monitor | Pestaña **ENTRENO** en `http://localhost:8011/neural/` (curva SVG con zoom, KPIs, ETA, GPU, log, informes) alimentada por espejo cada 5 min (`tools/sync_train_status.ps1`) |
| Informes | `storage/reports/cycle_*.json/.md` por ciclo de 12h (web + training) |

## Estado actual

- Paso **2110/8436 (25%)**, época 0.75, loss **5.30 → 0.68** (convergencia sana, sin divergencias)
- Checkpoints hasta **2000**. Cero pérdida neta gracias al resume (3 muertes silenciosas ya absorbidas, causa aún bajo investigación: ni tapa, ni energía, ni RAM, ni temperatura)
- GPU 72°C tras reparar ventilador (antes 86-89°C con throttling), ~11.5s/paso → ETA restante **~20h**

## Próximos hitos

1. Completar 8436 pasos (3 épocas)
2. `merge LoRA → quant Q4_K_M (llama.cpp) → ollama create ExpertiaMath`
3. Registrar en `SPECIALIST_REGISTRY` (Mathematics) y test A/B 1h contra base
4. Decisión: promocionar a modelo oficial del especialista si `EMA +0.01` y `quality +0.05`
