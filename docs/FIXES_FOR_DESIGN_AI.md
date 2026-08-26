# FIXES PARA IA DE DISEÑO — Feedback experto sobre tu V7 "Telemetría de Precisión"

> Reenvía tal cual a la IA de diseño. Es feedback accionable, no crítica vacía.

---

## Contexto que debes respetar (no inventes)

- **Producto real, no mock:** 18 especialistas (Geopolitics, LegalSystem, Sociology, Medicine, Linguistics...), 3 modelos (`qwen2.5-coder:3b`×5, `phi4-mini:4k`×9, `gemma3:4b`×3), 192,987,552 paquetes, 1897 ciclos, pipeline WEB Phase B query 12/14, EMA 0.992-0.998, WAL 2.4MB, Freelist 18.1GB. Todo viene de `GET /api/specialists`, `/api/analytics/ema-history?hours=720`, `/api/analytics/insights`, `/api/activity-log`. **No uses datos dummy.**
- **Stack:** Vanilla JS `class App`, sin React/Vue, sin npm, sin bundler. Solo `Plotly` opcional en control-center. Mantener ligero. `?ui=v4` debe seguir funcionando para revert.
- **Constraints:** `height:100vh; overflow:hidden` ya no, usamos `overflow:auto` + bento. Dark/light debe funcionar (`data-theme="warm"` y `data-theme="dark"`). Responsive 1100/720.

---

## Qué mantener de tu V7 (aciertos)

1. **Tokens editoriales:** `Warm Paper #F5F1E8 / Deep Ink #1A1E26 / Teal #1B4D4A / Amber #C45A1A` + `Fraunces 600 + Instrument Sans + Geist Mono` — es la dirección correcta contra neón IA. Conservar 100%.
2. **Bento 2fr/1fr + gap 1px `var(--c-grid)` + `live-pill` con `pulse-dot` + `sparklines 60×20` + `KPI row` 3 métricas — da autoridad de instrumento.
3. **Vanilla + `?ui=v4` reversible** — correcto.

---

## FIXES CRÍTICOS (si no los haces, suspende)

### Fix 1 — Datos reales, no dummy (bloqueante)
**Tu error:** `app.js: renderDummyData()` con 4 filas hardcodeadas `Psychology hace 2m` + `simulateHeartbeat() Math.random()` + `animateKPIs()` con `setInterval` fake. En producción con 18 especialistas reales y `192M pkg` el usuario verá desfase y perderá confianza.
**Arreglo:** Borra `renderDummyData` y `simulateHeartbeat`. Usa el `fetchJSON` real ya existente en v6:
```js
const [specs, overview, insights] = await Promise.all([
  fetchJSON('/api/specialists'),
  fetchJSON('/api/analytics/overview'),
  fetchJSON('/api/analytics/insights')
]);
this.rawSpecs = specs; this.renderFleet(); this.renderInsights();
```
Y `CountUp` sobre `totalPkg 192987552` real, no `190000000→192900000` fake. Mantén `initSSE()` comentado hasta que `GET /api/stream` (SSE) exista, no simules.

### Fix 2 — Dark + Responsive + A11y (bloqueante)
**Tu error:** Solo `:root` papel, sin `[data-theme="dark"]`, sin `@media 1100/720`, sin `focus-visible`, sin `prefers-reduced-motion`. Tu `nav-rail` con `⚑ ◱ ⚡` no tiene `aria-label` ni `rail-label` visible.
**Arreglo:** Copia de v6:
```css
[data-theme="dark"]{ --paper:#0F1419; --paper-2:#131A22; --ink:#E8E6E3; --border:#1E2A32; --accent:#E8913A; --accent-2:#4ECDC4; }
@media (max-width:1100px){.bento-container{grid-template-columns:repeat(6,1fr)}}
.rail-item:focus-visible{outline:2px solid var(--accent); outline-offset:2px}
@media (prefers-reduced-motion: reduce){ .pulse-dot{animation:none} }
```
Y en `index.html` cada `nav-item` debe tener `<span class="rail-label">Flota</span><span class="rail-key">F1</span>` como v6, no solo `⚑`.

### Fix 3 — Métricas vacías (bloqueante)
**Tu error:** `charts-wrapper` tiene `<div class="shimmer-bar-placeholder"></div>` — placeholder, no `canvas`. `system-metrics` solo `WAL/Freelist` estáticos. No hay `throughput/minuto` vivo.
**Arreglo:** Restaura de v6:
```html
<div class="canvas-wrap"><canvas id="chart-ema"></canvas></div>
<div class="canvas-wrap small"><canvas id="chart-throughput"></canvas></div>
```
Y en `app.js` mantén `drawEmaMultiLine('chart-ema', data.series)` + `drawThroughputBars` con `crosshair` + `tooltip 4 decimales` + `range 1h/24h/7d/30d`.

---

## FIXES MAYORES (si no los haces, nota baja)

### Fix 4 — Iconos nav incomprensibles
**Tu error:** `⚑ ◱ ⚡` no comunica `Flota/Métricas/Vivo` sin label. En test de 3s el usuario no sabe dónde clicar.
**Arreglo:** Usa `⬢ Flota (F1)` / `◈ Métrica (F2)` / `⬣ Vivo (F3)` con `rail-label` siempre visible (como v6), no solo `title`.

### Fix 5 — Tabla incompleta
**Tu error:** `fleet-table` solo 5 cols (`Dominio/Modelo, Estado, Actualizado, 24h Δ, Latencia`) — faltan `EMA Δ`, `Paquetes`, `Ciclos`, `Web éxito %` que sí tienes en v6 y son accionables.
**Arreglo:** Mantén 10 cols de v6.2: `Especialista | EMA Δ | Actualizado | 24h Δ | Latencia | Web éxito | Paquetes | Ciclos | Estado` + `Ordenar por ▾` (Actualizado/EMA/Paquetes/Dominio) + `Filtrar dominio` + `content-visibility:auto` + virtual 50.

### Fix 6 — Tipografía con carácter pero sin jerarquía
**Tu error:** `Fraunces 600` solo en `.logo`, no en `h1 Flota` ni `panel-head h3`. `Instrument Sans` no se usa en `panel-tools`.
**Arreglo:** Aplica `font-display: Fraunces 700` en `.bento-title h1` (26px, -0.03em) y `.panel-head h3` (11px, 800, .08em), como v6.2.

---

## Qué esperamos de tu v7.1

- **Entregable:** `index.html` + `style.css` + `app.js` vanilla funcionales (no solo tokens), con `fetch` real, `720h` por defecto (no 24h), `localStorage` migración `24→720`, y `?ui=v4` intacto.
- **Originalidad que sí valoramos:** mantén tu `bento 1px` + `live-pill` + `kpi-row` 3 métricas, pero añade lo que falta: `sparklines` etiquetados `CPU/RAM`, `queue-bars` con `VRAM 2.4/6GB`, `throughput/minuto` latiendo.
- **No repitas:** dummy data, `⚑` sin label, `shimmer` vacío, sin dark.

Reenvía v7.1 y lo evaluamos con el mismo criterio: originalidad + practicidad + vivo en 3s + reversible.

