# BRIEF PARA IA DE DISEÑO — Rediseño Frontend EXPERTIA · Archivo Sináptico

> **Objetivo del brief:** Entregar a una IA de diseño toda la información necesaria para que rediseñe **todo el frontend** de Expertia con **originalidad radical, practicidad y feedback positivo instantáneo** al verlo por primera vez.

---

## 1. Qué es EXPERTIA (producto)

**Expertia** es un **laboratorio de conocimiento vivo** local (hoy Windows 11, RTX 1660 6GB, 32GB RAM, HDD 1TB + futuro M2 2TB) que orquesta **18 especialistas raíz** con modelos Ollama (`qwen2.5-coder:3b` ×5, `phi4-mini:4k` ×9, `gemma3:4b` ×3) más **23 consejos super-expertos** (councils con pesos). No es un chatbot genérico: es un **archivo sináptico** que absorbe conocimiento continuo de la web (6 idiomas: en, es, fr, de, pt, it), lo destila con LLM, lo puntúa (EMA 0.10→0.999) y lo hace escalable en tiers (Bronze→Silver→Gold→Legend).

**Dato diferencial:** 714,961,987 paquetes de conocimiento curados (192.9M mostrados hoy por paginación), 1840 ciclos, FTS5 sobre 1.1M términos, 18.1 GB freelist, WAL 0. Pipeline en modo WEB continuo (query 4/14 para Psychology, 18h24m de este run, 192.9M paquetes totales). No es demo: es motor productivo.

**Visión producto:** Pasar de herramienta técnica a **producto comercializable** individual (knowledge OS local) y asociado a **SynapseCode** (futuro, no priorizar hoy). Debe correr en cualquier plataforma (Docker, cualquier disco, cualquier GPU/CPU) — por eso el diseño no puede estar atado a Windows/HDD.

---

## 2. Qué necesitamos (jobs to be done)

| Usuario | Job | Dolor actual |
|---|---|---|
| **Operador** (tú, técnico) | Ver de un vistazo si la flota está viva, quién avanza, quién se atasca, sin leer logs | Hoy: cabecera `pipeline detenido — hace 0 min` falsa con `procesando 18h` (desincronía PID), tabla con columnas idénticas (Tier todos Legend, Fallos 0), gráficos estáticos (EMA 0.995-0.999 plana) |
| **Curador** | Entender qué especialista absorbe más, cuál necesita atención, cuál está bloqueado | Hoy: tabla sin `Actualizado`, sin `24h Δ`, sin `Latencia`, sin `Web éxito %`; no hay orden por reciente |
| **Visitante** (futuro cliente individual) | Sentir **progreso vivo palpable** en 3 segundos, feedback positivo ("esto está trabajando, es potente, quiero usarlo") | Hoy: gráficos 64×18 mudos, sin tooltip, sin crosshair, sin números que se muevan; todo plano, sin profundidad |

**Criterio de éxito emocional (tú lo pediste):** Al abrir `localhost:8011/neural/` el visitante debe pensar **"esto es un instrumento serio, no una web de IA genérica"** en <3s.

---

## 3. Lo que YA existe (para que no propongas desde cero sin contexto)

### 3.1 Dos frontends hoy (divergentes)
- **Neural Horizon** (`frontend/neural-horizon/` — 619L `app.js`, 437L `style.css`, `index.html` 175L): dark por defecto, `height:100vh; overflow:hidden`, 3 tabs (F1 FLOTA / F2 MÉTRICAS / F3 ACTIVIDAD), polling 3s ×7 fetches (`overview`, `specialists`, `logs`, `health`, `status`, `analytics/insights`, `analytics/ema-history?hours=720`), tabla 11 cols sortable, canvas nativo para EMA/throughput (150L), sin tooltip/zoom, sin virtualización, sin search.
- **Control Center** (`frontend/control-center/` — 1199L `app.js`, 1158L `style.css`): light por defecto, sidebar 200px (7 items: Dashboard, Specialists, Fleet, Map, Super-Experts, Certified, Incidents), Plotly 2.35.2 para 8 charts, 7 tabs con carga a demanda, polling 10s solo dashboard.

**Reversible:** `index.html.bak`, `style.css.bak`, `app.js.bak` en `neural-horizon/` + feature flag `?ui=v4` (viejo) vs `?ui=v6` (nuevo). Puedes proponer ruptura total, volvemos en 1 click.

### 3.2 Datos reales que debes visualizar
- **18 specialists** con: `domain` (Geopolitics, LegalSystem, Sociology...), `model`, `ema_score 0.9954-0.9979`, `tier 4 Legend` (todos hoy), `packages_absorbed 9M-36M`, `total_cycles 98-119`, `status active/idle/blocked`, `updated_at` (hace 2h29m), `avg_quality 0.81-0.87`, `fail_rate`, `racha_25 100%`, `latencia`, `web éxito %`, `24h Δ`
- **Sistema:** EMA medio 0.9971, 192.9M paquetes, 1897 ciclos, WAL 2.4MB, freelist 18GB, CPU/RAM sparklines 40 puntos
- **Pipeline:** `Phase B: Medicine (query 12/14) 18h41m`, `query 4/14` por especialista, 3 en paralelo (gemma3:4b), `circuit breaker` 60s, `watchdog` 20min freeze → `BLOCKED` tras 5
- **Gráficos hoy:** `Evolución EMA` 24h/72h/7d/30d (ahora 1h/24h/7d/30d), `Throughput/hora` barras, `Tiers·Sistema` (Bronze 0/Silver 0...), `Comparativa modelos`, `ETA Legend` (todos `ahora` porque ya son Legend)

### 3.3 Stack técnico (para que propongas sin romper)
- Vanilla JS `class App`, sin npm, sin bundler, sin framework, sin i18n. Solo `Plotly` en control-center vía CDN. No añadas `React/Vue` sin justificar (preferimos seguir vanilla o `lit` ligero).
- Backend `FastAPI 8011` (`query_api.py` + `api_router.py` 1223L) con `APIRouter(prefix=/api)`, endpoints `/status`, `/specialists`, `/analytics/*`, `/knowledge-stats`, `/activity-log`. Polling actual 3s, migraremos a `SSE /api/stream` si propones.
- Fuente tipográfica actual: `Inter` + `JetBrains Mono` + `Fraunces` (nuevo v6) — puedes cambiarla si justificas originalidad (no uses la típica `Inter` sola de IA).

---

## 4. Qué te pedimos: ORIGINALIDAD + PRACTICIDAD + FEEDBACK POSITIVO

### 4.1 Originalidad (no la típica web IA)
- **Prohibido:** fondo oscuro neón `#0B0E13` con `amber #E8913A` genérico, tarjetas planas sin sombra, tipografía `Inter` sola, layout 3 tabs top + tabla densa. Es lo que ya tenemos y es genérico.
- **Pedido:** Sé original. Propuestas que valoramos (elige o inventa otra, pero justifica):
  - **Instrumento de laboratorio editorial:** papel cálido `F5F1E8` + tinta `1A1E26`, acento `oxidized amber C45A1A` + `teal 1B4D4A`, serif con carácter (`Fraunces` display) + sans geométrica (`Instrument Sans`) + mono (`Geist Mono`), bento asimétrico 12-col, `nav-rail` 64px vertical (no tabbar arriba)
  - **Brutalista científico:** grid 1px, tipografía mono grande, bordes 2px, `stark` contrast, sin sombras, datos en primer plano
  - **Tu propuesta atrevida:** sorprende, pero debe seguir siendo legible y no kitsch
- **Tipografía:** Cambia si quieres (ej. `Space Grotesk`, `Instrument Serif`, `Newsreader`, `Geist`), pero que no sea la default de IA. Justifica elección.
- **Disposición:** Cambia lo que quieras: pestañas verticales, drawer, bento, sin pestañas, con `command palette Cmd+K`, etc. No te ates a `F1/F2/F3` si tienes mejor idea.

### 4.2 Practicidad (que se entienda en 3s qué pasa)
- **Cabecera:** Quitar tira reiterativa `◆ LEGEND SoftwareEngineering 0.9967 — Mathematics 0.9989 ...` (ocupa 38px y duplica tabla). Reemplazar por `live-pill` con `progress` fino (query 12/14) + `sparklines` CPU/RAM grandes y etiquetados + `throughput/min` vivo.
- **Tabla FLOTA:** Quitar columnas idénticas en todos (Tier todos Legend, Fallos 0, Racha 100%) → resumir en `Estado` dot + tooltip. **Añadir** `Actualizado (hace 2h29m)`, `24h Δ paquetes`, `Latencia ms`, `Web éxito %` — datos que hoy faltan y son accionables. **Ordenar por** desplegable (no 11 headers clickables confusos): `Actualizado ↓` por defecto.
- **Métricas:** De `24h` estático a **vivo por minuto**: `Throughput/minuto` 60 barras animadas con `crosshair` + `tooltip`, `EMA` con `1h` default (no 24h) y `brush` para 7d, inferiores `Latencia por modelo` + `Cola LLM 4/14` + `VRAM 2.4/6GB` + `WAL 2.4MB` (hoy vacíos con `—`).
- **Feedback positivo:** Al abrir, animación `countUp` en KPIs (Legend 18, Gold 0...), `pulse` en `live-dot`, `shimmer` en barras, `toast` no bloqueante. Que se sienta que **algo está pasando ahora mismo**.

### 4.3 Feedback positivo solo al verlo
- En 3s el visitante debe ver: **18 especialistas ordenados por reciente**, **EMA subiendo aunque sea 0.0001**, **throughput latiendo por minuto**, **actividad en vivo con timestamps relativos** (`hace 2 min`), sin leer manual.
- Evita jerga vacía. Usa números con contexto: `9.010.706 +124 (24h)` mejor que `9.010.706` solo.

---

## 5. Características completas para que no inventes datos

- **18 dominios fijos:** SoftwareEngineering, Mathematics, Medicine, LegalSystem, PhilosophyHistory, FinanceEconomics, Physics, Cybersecurity, Geopolitics, DataScience, Chemistry, ArtHistory, Electronics, Astronomy, Linguistics, Psychology, EnvironmentalScience, Sociology
- **3 modelos:** `qwen2.5-coder:3b` (5), `phi4-mini:4k` (9), `gemma3:4b` (3) — cada uno con `packages` y `avg_ema`
- **23 super-experts:** councils con pesos (ej. `ArtificialIntelligence: DataScience 0.30 + SoftwareEng 0.25...`)
- **Estados:** `active` (verde), `idle` (gris), `blocked` (rojo tras 5 congelaciones 20min), `mining/absorbing`
- **Métricas por especialista:** `ema_score`, `Δ24h`, `updated_at`, `packages_absorbed`, `total_cycles`, `avg_quality [min–max]`, `fail_rate`, `racha_25`, `latencia`, `web éxito`, `ETA Legend`
- **Sistema:** `EMA medio 0.9971`, `192.9M paquetes`, `1897 ciclos`, `WAL`, `freelist`, `CPU`, `RAM`, `pipeline 18h41m`, `query 12/14`
- **Restricciones:** No uses `latest-all.json.gz` (borrado 143GB, dummy 0B), no asumas `VACUUM` posible (258GB libres <684GB), respeta `EXPERTIA_*` env para paths

---

## 6. Entregables que esperamos de ti

1. **Propuesta visual completa:** paleta (con `oklch` si quieres), tipografías, layout (wireframe bento o tu idea), componentes (tabla, gráficos, topbar, rail/sidebar)
2. **Rediseño de las 3 vistas:** FLOTA (tabla + KPIs), MÉTRICAS (EMA + throughput + tiers + modelos + cola), ACTIVIDAD (feed 60 eventos con filtros TODO/INFO/WARN/ERROR)
3. **Interacciones:** `Ordenar por ▾`, `Filtrar dominio`, `range 1h/24h/7d/30d`, `F1/F2/F3` o tu navegación, `Ctrl+F5` no necesario, `?ui=v4` revert
4. **Código o mock:** Si generas código, que sea `index.html` + `style.css` + `app.js` vanilla (o `lit`) sin romper `fetch /api/*` (endpoints arriba). Si es mock Figma, describe tokens `—color-*`, `—space-*`, `—radius-*`
5. **Justificación:** 1 párrafo por qué tu diseño es original, práctico y genera feedback positivo vs IA genérica

---

## 7. Criterios de éxito (cómo te evaluaremos)

- **Originalidad:** ¿Podría confundirse con otro dashboard de IA? Si sí, suspende. Queremos `editorial/instrumento`, no `neón oscuro`.
- **Practicidad:** ¿En 3s sabes quién está activo, quién se actualizó hace 2h29m y cuál es la latencia? Si no, suspende.
- **Vivo:** ¿Gráficos laten por minuto, no por hora? ¿Hay `crosshair` + `tooltip` con 4 decimales? Si no, suspende.
- **Reversible:** ¿Se puede volver a `?ui=v4` en 1 click sin perder datos? Si no, suspende.

---

**Contexto final:** Hoy `localhost:8011/neural/` muestra `v6 atrevido` (warm paper, Fraunces, bento) pero aún plano y con `pipeline detenido — hace 0 min` falso (ya corregido a `activo 20h40m` tras fix `api_router:460`). Te lo enseñaremos para que critiques sin piedad y propongas el v7 definitivo.

¡Sorpréndenos!
