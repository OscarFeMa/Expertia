/**
 * EXPERTIA · Charts (v5) — Command Console palette
 * Canvas sin dependencias. Multi-línea EMA, throughput bars, sparklines.
 */
const EMA_COLORS = [
  '#E8913A','#D4A843','#4BAE6C','#5B8DB8','#D96A5C',
  '#9B7EB8','#5BB5A0','#C98A4B','#6A9DC6','#B8A24A',
  '#7D8BB0','#C47D5A','#5BA08A','#A87DAD','#8A8A5A',
  '#CC6E5A','#4A8DB8','#D4A07A',
];

function parseDbUtcToLocal(s) {
  if (!s) return NaN;
  const m = /(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/.exec(s);
  if (!m) return NaN;
  return Date.UTC(+m[1], +m[2]-1, +m[3], +m[4], +m[5], +m[6]);
}

function _chartTheme() {
  const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
  return {
    isDark,
    fg: isDark ? '#C8CDD4' : '#2A2520',
    dim: isDark ? '#6B747F' : '#7A7063',
    grid: isDark ? 'rgba(232,145,58,0.06)' : 'rgba(196,100,26,0.08)',
    accent: isDark ? '#E8913A' : '#C4641A',
    accent2: isDark ? '#D4A843' : '#B8892A',
    fill: isDark ? 'rgba(232,145,58,0.10)' : 'rgba(196,100,26,0.10)',
  };
}

function _prepareCanvas(canvas, height) {
  const wrap = canvas.parentElement;
  const dpr = window.devicePixelRatio || 1;
  const W = Math.max((wrap.clientWidth || 600), 120);
  const H = height || (wrap.clientHeight || 240);
  canvas.width = W * dpr; canvas.height = H * dpr;
  canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  return { ctx, W, H, dpr };
}

function drawEmaMultiLine(canvasId, series, legendEl, rangeHours) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !series || !series.length) return;
  const C = _chartTheme();
  const { ctx, W, H } = _prepareCanvas(canvas, 230);
  const pad = { top:12, bottom:26, left:44, right:12 };
  const plotW = W - pad.left - pad.right;
  const plotH = H - pad.top - pad.bottom;
  const now = Date.now();
  const rangeMs = (rangeHours > 0 ? rangeHours : 24) * 3600 * 1000;
  const tStart = now - rangeMs;
  const tEnd = now;

  let eMin = Infinity, eMax = -Infinity;
  const usable = [];
  series.forEach((s, i) => {
    const pts = (s.points || []).filter(p => p && p.e != null);
    if (pts.length < 2) return;
    const color = EMA_COLORS[i % EMA_COLORS.length];
    usable.push({ ...s, points: pts, color });
    pts.forEach(p => {
      const t = parseDbUtcToLocal(p.t);
      if (t >= tStart && t <= tEnd) { if (p.e < eMin) eMin = p.e; if (p.e > eMax) eMax = p.e; }
    });
  });
  if (!usable.length || !isFinite(eMin)) {
    if (ctx) { ctx.clearRect(0,0,W,H); ctx.fillStyle=C.dim; ctx.font='11px '+getComputedStyle(document.body).getPropertyValue('--mono'); ctx.fillText('Sin datos en el rango', pad.left, H/2); }
    return;
  }
  const spare = (eMax - eMin) || 0.05;
  eMin = Math.max(0, eMin - spare * 0.15);
  eMax = Math.min(1.2, eMax + spare * 0.15);

  ctx.clearRect(0, 0, W, H);
  ctx.strokeStyle = C.grid; ctx.lineWidth = 1;
  const mono = getComputedStyle(document.body).getPropertyValue('--mono').trim();
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + (plotH * i / 4);
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(W - pad.right, y); ctx.stroke();
    ctx.fillStyle = C.dim; ctx.font = '10px ' + mono; ctx.textAlign = 'right';
    ctx.fillText((eMax - (eMax - eMin) * i / 4).toFixed(3), pad.left - 6, y + 4);
  }
  ctx.textAlign = 'center';
  const xTicks = 5;
  for (let i = 0; i <= xTicks; i++) {
    const t = tStart + (tEnd - tStart) * i / xTicks;
    const x = pad.left + plotW * i / xTicks;
    ctx.fillText(new Date(t).toLocaleTimeString([], { hour:'2-digit', minute:'2-digit' }), x, H - 8);
  }

  usable.forEach(s => {
    ctx.beginPath(); ctx.strokeStyle = s.color; ctx.lineWidth = 1.5; ctx.lineJoin = 'round';
    let drawn = false;
    s.points.forEach(p => {
      const t = parseDbUtcToLocal(p.t);
      if (t < tStart || t > tEnd) return;
      const x = pad.left + ((t - tStart) / (tEnd - tStart)) * plotW;
      const y = pad.top + plotH - ((p.e - eMin) / (eMax - eMin)) * plotH;
      if (!drawn) { ctx.moveTo(x, y); drawn = true; } else ctx.lineTo(x, y);
    });
    ctx.stroke();
    // end point
    let lastPt = null;
    for (const p of s.points) { const t = parseDbUtcToLocal(p.t); if (p.e != null && t >= tStart && t <= tEnd) lastPt = p; }
    if (lastPt) {
      const lt = parseDbUtcToLocal(lastPt.t);
      const lx = pad.left + ((lt - tStart) / (tEnd - tStart)) * plotW;
      const ly = pad.top + plotH - ((lastPt.e - eMin) / (eMax - eMin)) * plotH;
      ctx.fillStyle = s.color; ctx.beginPath(); ctx.arc(lx, ly, 3, 0, Math.PI * 2); ctx.fill();
      // legend-highlight: thicker + glow for Legend-tier series
    }
  });

  if (legendEl) {
    const top = usable.slice(0, 10);
    legendEl.innerHTML = top.map(s =>
      `<span class="lg"><span class="sw" style="background:${s.color}"></span>${escapeHtml(s.domain)}</span>`
    ).join('');
  }
}

function drawThroughputBars(canvasId, data) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !data || !data.length) return;
  const C = _chartTheme();
  const { ctx, W, H } = _prepareCanvas(canvas, 160);
  const pad = { top:10, bottom:22, left:34, right:8 };
  const plotW = W - pad.left - pad.right;
  const plotH = H - pad.top - pad.bottom;
  const max = Math.max(...data.map(d => d.cycles || 0), 1);
  const mono = getComputedStyle(document.body).getPropertyValue('--mono').trim();

  ctx.clearRect(0, 0, W, H);
  ctx.strokeStyle = C.grid; ctx.lineWidth = 1;
  for (let i = 0; i <= 3; i++) {
    const y = pad.top + (plotH * i / 3);
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(W - pad.right, y); ctx.stroke();
    ctx.fillStyle = C.dim; ctx.font = '9px ' + mono; ctx.textAlign = 'right';
    ctx.fillText(Math.round(max - max * i / 3), pad.left - 5, y + 3);
  }
  const barW = plotW / data.length;
  data.forEach((d, i) => {
    const h = (d.cycles / max) * plotH;
    const x = pad.left + i * barW + barW * 0.15;
    const y = pad.top + plotH - h;
    ctx.fillStyle = C.fill;
    ctx.fillRect(x, y, Math.max(2, barW * 0.7), h);
    ctx.fillStyle = C.accent;
    ctx.fillRect(x, y, Math.max(2, barW * 0.7), 2);
  });
}
