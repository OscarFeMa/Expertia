/**
 * EXPERTIA · Neural Horizon — Command Console (v5)
 * 3 tabs: FLOTA · MÉTRICAS · ACTIVIDAD
 * Tracking denso con especialistas Legend prominentes.
 */
class App {
  constructor() {
    this.apiBase = '/api';
    this.theme = localStorage.getItem('expertia-theme') || 'dark';
    document.documentElement.setAttribute('data-theme', this.theme);
    this.tab = 'fleet';
    this.sortKey = 'ema';
    this.sortDir = -1; // desc
    this.rangeHours = 720;
    this.actFilter = 'ALL';
    this.lang = localStorage.getItem('expertia-lang') || 'es';
    this.pollMs = 3000;
    this._timer = null;
    this._apiKey = sessionStorage.getItem('expertia-api-key') || '';
    this.spark = { cpu: [], ram: [], disk: [] };
    this.emaSeries = {};
    this.emaSeriesEmpty = true;
    this.activityHistory = [];
    this.rawSpecs = [];
    this.rawOverview = null;
    this.init();
  }

  async init() {
    this.updateClock();
    setInterval(() => this.updateClock(), 1000);
    // Restore persistent UI state
    this.legendCollapsed = localStorage.getItem('expertia-legend-collapsed') === '1';
    this.actFilter = localStorage.getItem('expertia-act-filter') || 'ALL';
    let storedRange = localStorage.getItem('expertia-range');
    if (storedRange === '24' || storedRange === '168' || !storedRange) storedRange = '720';
    this.rangeHours = Number(storedRange);
    localStorage.setItem('expertia-range', '720');
    const lb=document.getElementById('lang-btn'); if(lb) lb.textContent=this.lang.toUpperCase();
    await this.refresh();
    this.startPolling();
    document.addEventListener('visibilitychange', () => this.startPolling());
    document.addEventListener('keydown', e => this.onKey(e));
    this.applyLegendState();
  }

  onKey(e) {
    if (e.target.tagName === 'INPUT') return;
    if (e.key === 'F1') { e.preventDefault(); this.switchTab('fleet'); }
    else if (e.key === 'F2') { e.preventDefault(); this.switchTab('metrics'); }
    else if (e.key === 'F3') { e.preventDefault(); this.switchTab('activity'); }
    else if (e.key === 'F4') { e.preventDefault(); this.switchTab('training'); }
    else if (e.key === 'r' || e.key === 'R') { this.refresh(); }
    else if (e.key === 't' || e.key === 'T') { this.toggleTheme(); }
    else if (e.key === '?' || (e.key === '/' && e.shiftKey)) { e.preventDefault(); this.toggleHelp(); }
    else if (e.key === 'Escape') { this.toggleHelp(false); }
  }

  // ── Toast notifications ──
  toast(title, message, kind = 'info', duration = 5000) {
    const c = document.getElementById('toast-container');
    if (!c) return;
    const icons = { success: '✓', error: '✕', info: '◆', 'legend-promo': '★' };
    const t = document.createElement('div');
    t.className = `toast ${kind}`;
    t.innerHTML = `<span class="t-icon">${icons[kind] || '◆'}</span><div class="t-body"><div class="t-title">${escapeHtml(title)}</div><div>${escapeHtml(message)}</div></div>`;
    c.appendChild(t);
    setTimeout(() => {
      t.classList.add('out');
      setTimeout(() => t.remove(), 300);
    }, duration);
  }

  // ── Keyboard help overlay ──
  toggleHelp(force) {
    const el = document.getElementById('help-overlay');
    if (!el) return;
    const show = force !== undefined ? force : !el.classList.contains('show');
    el.classList.toggle('show', show);
  }

  // ── Legend strip collapsable ──
  toggleLegend() {
    this.legendCollapsed = !this.legendCollapsed;
    localStorage.setItem('expertia-legend-collapsed', this.legendCollapsed ? '1' : '0');
    this.applyLegendState();
  }

  applyLegendState() {
    const strip = document.getElementById('legend-strip');
    const btn = document.getElementById('legend-toggle');
    if (strip) strip.classList.toggle('collapsed', this.legendCollapsed);
    if (btn) btn.textContent = this.legendCollapsed ? '▶' : '▼';
  }

  // ── Persistent filters ──
  setRange(h) {
    this.rangeHours = h;
    localStorage.setItem('expertia-range', String(h));
    document.querySelectorAll('.range-btn').forEach(b =>
      b.classList.toggle('active', Number(b.dataset.hours) === h));
    this.loadEmaChart();
  }

  setActFilter(lvl) {
    this.actFilter = lvl;
    localStorage.setItem('expertia-act-filter', lvl);
    document.querySelectorAll('.filter-btn').forEach(b =>
      b.classList.toggle('active', b.dataset.lvl === lvl));
    this.renderActivity();
  }

  switchTab(name) {
    this.tab = name;
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    const panel = document.getElementById('tab-' + name);
    if (panel) panel.classList.add('active');
    this.render();
    if (name === 'metrics') {
      requestAnimationFrame(() => {
        this.renderMetrics();
        this.renderInsights();
        this.loadEmaChart();
      });
    }
    if (name === 'training') {
      requestAnimationFrame(() => {
        this.fetchJSON(`${this.apiBase}/training/status`).then(d => { if (d) this.updateTrainPanel(d); });
      });
    }
  }

  startPolling() {
    if (this._timer) clearInterval(this._timer);
    this.pollMs = document.hidden ? 30000 : 3000;
    this._timer = setInterval(() => {
      if (document.hidden) return;
      this.refresh();
    }, this.pollMs);
  }

  updateClock() {
    const el = document.getElementById('sb-time');
    if (el) el.textContent = new Date().toLocaleTimeString();
  }

  toggleTheme() {
    this.theme = this.theme === 'dark' ? 'light' : 'dark';
    localStorage.setItem('expertia-theme', this.theme);
    document.documentElement.setAttribute('data-theme', this.theme);
  }

  toggleLang() {
    this.lang = this.lang === 'es' ? 'en' : 'es';
    localStorage.setItem('expertia-lang', this.lang);
    const b=document.getElementById('lang-btn'); if(b) b.textContent=this.lang.toUpperCase();
  }

  setRange(h) {
    this.rangeHours = h;
    document.querySelectorAll('.range-btn').forEach(b =>
      b.classList.toggle('active', Number(b.dataset.hours) === h));
    this.loadEmaChart();
  }

  setActFilter(lvl) {
    this.actFilter = lvl;
    document.querySelectorAll('.filter-btn').forEach(b =>
      b.classList.toggle('active', b.dataset.lvl === lvl));
    this.renderActivity();
  }

  showExpertMetrics(domain){
    if(!domain){ document.getElementById('sys-cpu').textContent='—%'; return; }
    const s=this.rawSpecs.find(x=>x.domain===domain);
    if(!s) return;
    const upd = s.updated_at ? new Date(s.updated_at.replace(' ','T')+'Z').toLocaleString('es-ES') : '—';
    this.toast(`Foco: ${domain}`, `EMA ${Number(s.ema_score).toFixed(4)} · ${s.packages_absorbed.toLocaleString()} pkg · Actualizado ${upd}`, 'info', 4000);
  }

  sortBy(key) {
    if (this.sortKey === key) this.sortDir *= -1;
    else { this.sortKey = key; this.sortDir = -1; }
    this.render();
  }

  async fetchJSON(url, opts = {}) {
    const headers = { ...(opts.headers || {}) };
    if (this._apiKey) headers['X-API-Key'] = this._apiKey;
    try {
      const r = await fetch(url, { ...opts, headers, cache: 'no-store' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return await r.json();
    } catch (e) {
      console.warn(`[Expertia] fetchJSON falló ${url}: ${e.message}`);
      return null;
    }
  }

  async updateWikiBar(){
    const w=await this.fetchJSON(`${this.apiBase}/wiki/status`);
    const s=this.rawStatus || this.rawOverview;
    const isFeeding = s && s.status==='FEEDING_WIKI';
    const el=document.getElementById('wiki-days'), last=document.getElementById('wiki-last'), st=document.getElementById('wiki-status'), eta=document.getElementById('wiki-eta'), mode=document.getElementById('wiki-mode'), prog=document.getElementById('wiki-progress'), bar=document.getElementById('wiki-progress-bar'), btn=document.getElementById('wiki-feed-btn');
    if(!w) return;
    if(el) el.textContent = w.days_since_update==null ? '— días' : `${w.days_since_update} días sin actualizar`;
    if(last) last.textContent = w.last_update ? `· última ${w.last_update}` : '';
    if(st) st.textContent = isFeeding ? '· Alimentando Wiki...' : (w.needs_update ? '· ¡Actualizar recomendado!' : '· al día');
    if(eta) {
      if(isFeeding && s.elapsed_seconds){
        const remain = Math.max(0, 900 - s.elapsed_seconds);
        const m=Math.floor(remain/60), sec=Math.floor(remain%60);
        eta.textContent = `· ETA ~${m}m ${sec}s`;
      } else if(w.days_since_update!=null) {
        const est = Math.round(w.days_since_update * 1.2);
        eta.textContent = w.needs_update ? `· Est. ${est} min` : '';
      } else eta.textContent='';
    }
    if(mode) { mode.textContent = isFeeding ? 'Modo: feed (Wikidata/Wikipedia → knowledge_packages, calidad preferente)' : ''; mode.style.display = isFeeding ? '' : 'none'; }
    if(prog) prog.style.display = isFeeding ? '' : 'none';
    if(bar && isFeeding && s.elapsed_seconds) bar.style.width = `${Math.min(95, (s.elapsed_seconds/900)*100)}%`;
    if(btn) { btn.textContent = isFeeding ? '⏳ Alimentando...' : '⟳ Alimentar Wiki ahora'; btn.disabled = !!isFeeding; }
  }
  async wikiFeedNow(){
    if(!confirm('¿Parar pipeline actual y alimentar Wiki ahora (Wikidata/Wikipedia, modo feed)?')) return;
    const r=await this.fetchJSON(`${this.apiBase}/wiki/feed-now`,{method:'POST'});
    if(r && r.status==='started') this.toast('Wiki feed iniciado', `PID ${r.pid} — ${r.message}`, 'info', 6000);
    else this.toast('Error', r?.detail || 'No se pudo iniciar Wiki feed', 'error');
    this.updateWikiBar();
  }
  updateTrainPanel(d){
    const ph=document.getElementById('train-phase'), st=document.getElementById('train-step'),
      loss=document.getElementById('train-loss'), lr=document.getElementById('train-lr'),
      spm=document.getElementById('train-spm'), tm=document.getElementById('train-time'),
      ds=document.getElementById('train-ds'), base=document.getElementById('train-base'),
      ad=document.getElementById('train-adapter'), prog=document.getElementById('train-progress'),
      bar=document.getElementById('train-progress-bar'), log=document.getElementById('train-log');
    if(!ph) return;
    ph.textContent = d.phase || 'idle';
    if(st) st.textContent = d.step ? `${d.step}${d.max_steps?` / ${d.max_steps}`:''} · ep ${d.epoch??'—'}` : 'en espera';
    if(loss) loss.textContent = d.loss!=null ? Number(d.loss).toFixed(4) : '—';
    if(lr) lr.textContent = d.lr!=null ? Number(d.lr).toExponential(1) : '—';
    if(spm) spm.textContent = d.steps_per_min!=null ? d.steps_per_min : '—';
    if(tm) tm.textContent = d.elapsed_s!=null ? `${Math.floor(d.elapsed_s/60)}m ${d.elapsed_s%60}s` : '—';
    if(ds) ds.textContent = `${(d.dataset_train||0).toLocaleString()} / ${(d.dataset_val||0).toLocaleString()}`;
    if(base) base.textContent = d.base_downloaded ? 'Phi-reasoning ✓' : 'descargando…';
    if(ad) ad.textContent = d.adapter || 'r16 · seq1024';
    if(d.max_steps && d.step && prog && bar){ prog.style.display=''; bar.style.width=`${Math.min(100,(d.step/d.max_steps)*100)}%`; }
    else if(prog) prog.style.display = (d.phase==='training') ? '' : 'none';
    if(d.loss_history) this.drawTrainLoss(d.loss_history);
    if(log && d.log_tail) log.textContent = d.log_tail.join('\n');
  }
  drawTrainLoss(hist){
    const cv=document.getElementById('chart-train-loss'); if(!cv) return;
    const ctx=cv.getContext('2d'), W=cv.width=Math.max(300,cv.parentElement?.clientWidth||600), H=cv.height=220;
    ctx.clearRect(0,0,W,H);
    const st=getComputedStyle(document.documentElement);
    ctx.fillStyle=st.getPropertyValue('--text-mute')||'#888'; ctx.font='11px monospace';
    if(!hist.length){ ctx.fillText('curva disponible tras los primeros 25 pasos…', 12, 24); return; }
    const ls=hist.map(h=>h.loss), mn=Math.min(...ls), mx=Math.max(...ls), rg=(mx-mn)||1;
    ctx.strokeStyle=st.getPropertyValue('--border')||'#333'; ctx.lineWidth=1;
    ctx.beginPath(); ctx.moveTo(0,H-20); ctx.lineTo(W,H-20); ctx.stroke();
    ctx.strokeStyle=st.getPropertyValue('--accent')||'#7aa2f7'; ctx.lineWidth=2; ctx.beginPath();
    hist.forEach((h,i)=>{ const x=(i/(hist.length-1||1))*(W-8)+4, y=H-28-((h.loss-mn)/rg)*(H-48); i?ctx.lineTo(x,y):ctx.moveTo(x,y); });
    ctx.stroke();
    ctx.fillText(`min ${mn.toFixed(3)} · max ${mx.toFixed(3)} · n=${hist.length}`, 12, 16);
  }
  async refresh() {
    const t0 = Date.now();
    const [overview, cpu, mem, specs, logs, health, status] = await Promise.all([
      this.fetchJSON(`${this.apiBase}/analytics/overview`),
      this.fetchJSON(`${this.apiBase}/system/cpu`),
      this.fetchJSON(`${this.apiBase}/system/memory`),
      this.fetchJSON(`${this.apiBase}/specialists`),
      this.fetchJSON(`${this.apiBase}/activity-log?limit=60&levels=INFO,WARNING,ERROR,CRITICAL`),
      this.fetchJSON(`${this.apiBase}/health`),
      this.fetchJSON(`${this.apiBase}/status`),
    ]);

    // Detect Legend promotions (tier jumped to 4 since last poll)
    if (this.rawSpecs.length && specs?.specialists) {
      const prev = new Map(this.rawSpecs.map(s => [s.id, s.tier]));
      for (const s of specs.specialists) {
        if (s.tier >= 4 && (prev.get(s.id) || 0) < 4) {
          this.toast('★ Promoción a Legend', `${s.domain} alcanzó EMA ${Number(s.ema_score).toFixed(4)}`, 'legend-promo', 8000);
        }
      }
    }

    // Load insights (predictions, alerts, models) — non-blocking
    this.fetchJSON(`${this.apiBase}/analytics/insights`).then(d => {
      this.rawInsights = d;
      if (d?.alerts?.length) this.renderAlerts(d.alerts);
      if (this.tab === 'metrics') this.renderInsights();
    });

    this.rawOverview = overview;
    this.rawSpecs = specs?.specialists || [];
    this.rawHealth = health;
    this._logs = logs?.logs || [];
    this.updatePill(overview, status);
    this.render();

    // EMA chart data (lazy load)
    this._lastEmaLoad = this._lastEmaLoad || 0;
    if (this.tab === 'metrics' && (this.emaSeriesEmpty || (Date.now() - this._lastEmaLoad) > 60000)) {
      this.emaSeriesEmpty = false;
      this._lastEmaLoad = Date.now();
      await this.loadEmaChart();
    }

    // System sparklines (legacy + nueva barra superior)
    if (cpu) { this.pushSpark('cpu', cpu.percent, 'spark-cpu'); this.pushSpark('cpu', cpu.percent, 'sys-cpu-spark'); }
    if (mem) { this.pushSpark('ram', mem.percent, 'spark-ram'); this.pushSpark('ram', mem.percent, 'sys-ram-spark'); }
    const sc = document.getElementById('kpi-cpu'); if (sc) sc.textContent = cpu ? `${Math.round(cpu.percent)}%` : '—%';
    const sr = document.getElementById('kpi-ram'); if (sr) sr.textContent = mem ? `${Math.round(mem.percent)}%` : '—%';
    const ssc = document.getElementById('sys-cpu'); if (ssc) ssc.textContent = cpu ? `${Math.round(cpu.percent)}%` : '—%';
    const ssr = document.getElementById('sys-ram'); if (ssr) ssr.textContent = mem ? `${Math.round(mem.percent)}%` : '—%';
    const ssd = document.getElementById('sys-disk'); if (ssd && health) {
      const freeGB = health.disk_free_gb ?? health.free_gb ?? null;
      if (freeGB != null) ssd.textContent = `${Math.round(freeGB)} GB libres`;
      else if (health.disk) ssd.textContent = health.disk;
    }
    if (health && health.disk_free_gb != null) {
      const pct = health.disk_free_gb && health.disk_total_gb ? Math.round((health.disk_free_gb/health.disk_total_gb)*100) : null;
      const sdSpark = document.getElementById('sys-disk-spark');
      if (sdSpark && pct != null) this.pushSpark('disk', 100-pct, 'sys-disk-spark');
    }
    this.updateWikiBar();
    this.fetchJSON(`${this.apiBase}/training/status`).then(d => { if (d) this.updateTrainPanel(d); });

    // statusbar + refresh indicator
    const ok = overview && health;
    this.updateRefreshDot(ok);
    const pkg = health?.package_count;
    const dbEl = document.getElementById('sb-db');
    if (dbEl) dbEl.textContent = pkg != null ? `${health.database || 'ok'} · ${pkg.toLocaleString()} pkg` : (health?.database || '—');
    const pipEl = document.getElementById('sb-pip');
    if (pipEl && overview) pipEl.textContent = `${overview.status || '—'} · ${this.shortPhase(overview.phase)}`;
    const upEl = document.getElementById('sb-last-update');
    if (upEl) upEl.textContent = `actualización: ${new Date().toLocaleTimeString()} · ${((Date.now()-t0)/1000).toFixed(1)}s`;
  }

  updateRefreshDot(ok) {
    const el = document.getElementById('sb-refresh');
    if (el) el.className = `refresh-dot ${ok ? 'ok' : 'err'}`;
  }

  render() {
    this.renderLegendStrip();
    this.renderFleetSummary();
    this.renderFleet();
    this.renderMetrics();
    this.renderActivity();
  }

  shortPhase(phase) {
    if (!phase) return '';
    const m = phase.match(/\((\d+) de (\d+)\)/);
    return m ? `${m[1]}/${m[2]}` : phase;
  }

  updatePill(o, st) {
    const pill = document.getElementById('pipeline-pill');
    const statusEl = document.getElementById('pp-status');
    if (!pill || !o) return;
    const s = (o.status || 'IDLE').toUpperCase();
    const mode = (st?.mode || '').toUpperCase();
    const modeTxt = mode ? ` · ${mode}` : '';
    let elapsed = '';
    if (st?.start_epoch) {
      const el = Math.max(0, (Date.now() / 1000) - st.start_epoch);
      const h = Math.floor(el / 3600), m = Math.floor((el % 3600) / 60);
      elapsed = h > 0 ? `${h}h ${m}m` : `${m} min`;
    }
    pill.className = 'pipeline-pill';
    if (s === 'ACTIVE') { pill.classList.add('work'); statusEl.textContent = `procesando${modeTxt} · ${this.shortPhase(o.phase)} · ${elapsed}`; }
    else if (s === 'IDLE') { pill.classList.add('live'); statusEl.textContent = `en espera${modeTxt} · ${elapsed}`; }
    else if (s === 'ERROR' || s === 'DOWN') { pill.classList.add('down'); statusEl.textContent = 'detenido'; }
    else { pill.classList.add('live'); statusEl.textContent = `${s}${modeTxt} · ${elapsed}`; }
  }

  // ── LEGEND STRIP ─────────────────────────
  renderLegendStrip() {
    const strip = document.getElementById('legend-strip');
    const cards = document.getElementById('legend-cards');
    if (!strip || !cards) return;
    const legends = this.rawSpecs.filter(s => s.tier >= 4);
    if (!legends.length) { strip.classList.remove('visible'); return; }
    strip.classList.add('visible');

    const deltaMap = {};
    (this.rawOverview?.ema_deltas || []).forEach(d => { deltaMap[d.specialist_id] = d; });

    cards.innerHTML = legends.map(s => {
      const ema = Number(s.ema_score || 0);
      const d = deltaMap[s.specialist_id];
      const deltaVal = d ? ema - Number(d.ema_24h_ago || ema) : 0;
      const dCls = deltaVal > 0.0005 ? 'up' : (deltaVal < -0.0005 ? 'down' : '');
      const dTxt = !d ? '—' : `${deltaVal >= 0 ? '+' : ''}${deltaVal.toFixed(4)}`;
      const q = s.avg_quality ? s.avg_quality.toFixed(2) : '—';
      return `<div class="legend-card">
        <span class="lc-tier">◆</span>
        <span class="lc-domain">${escapeHtml(s.domain)}</span>
        <span class="lc-ema">${ema.toFixed(4)}</span>
        <span class="lc-sub">q:${q}</span>
        <span class="lc-delta ${dCls}">${dTxt}</span>
      </div>`;
    }).join('');
  }

  // ── Count-up animation ──
  countUp(el, target, suffix = '', duration = 600) {
    const isFloat = String(target).includes('.');
    const start = performance.now();
    const from = 0;
    const tick = (now) => {
      const p = Math.min((now - start) / duration, 1);
      const ease = 1 - Math.pow(1 - p, 3); // easeOutCubic
      const val = from + (target - from) * ease;
      el.textContent = (isFloat ? val.toFixed(4) : Math.round(val).toLocaleString()) + suffix;
      if (p < 1) requestAnimationFrame(tick);
      else el.textContent = (isFloat ? Number(target).toFixed(4) : Number(target).toLocaleString()) + suffix;
    };
    requestAnimationFrame(tick);
  }

  // ── FLEET SUMMARY ────────────────────────
  renderFleetSummary() {
    const el = document.getElementById('fleet-summary');
    if (!el || !this.rawSpecs.length) return;
    const total = this.rawSpecs.length;
    const legends = this.rawSpecs.filter(s => s.tier >= 4).length;
    const golds = this.rawSpecs.filter(s => s.tier === 3).length;
    const avgEma = this.rawSpecs.reduce((a, s) => a + Number(s.ema_score || 0), 0) / total;
    const totalPkg = this.rawSpecs.reduce((a, s) => a + (s.packages_absorbed || 0), 0);
    const totalCyc = this.rawSpecs.reduce((a, s) => a + (s.total_cycles || 0), 0);

    el.innerHTML = `
      <div class="stat-chip highlight"><span class="sl">Legend</span><span class="sv">0</span></div>
      <div class="stat-chip"><span class="sl">Gold</span><span class="sv">0</span></div>
      <div class="stat-chip"><span class="sl">Total</span><span class="sv">0</span></div>
      <div class="stat-chip"><span class="sl">EMA medio</span><span class="sv">0</span></div>
      <div class="stat-chip"><span class="sl">Paquetes</span><span class="sv">0</span></div>
      <div class="stat-chip"><span class="sl">Ciclos</span><span class="sv">0</span></div>
    `;
    // Animate each value
    const chips = el.querySelectorAll('.stat-chip .sv');
    this.countUp(chips[0], legends);
    this.countUp(chips[1], golds);
    this.countUp(chips[2], total);
    this.countUp(chips[3], avgEma);
    this.countUp(chips[4], totalPkg);
    this.countUp(chips[5], totalCyc);
  }

  // ── ALERTS BAR ───────────────────────────
  renderAlerts(alerts) {
    const bar = document.getElementById('alerts-bar');
    if (!bar || !alerts.length) { bar.classList.remove('visible'); return; }
    bar.classList.add('visible');
    const iconFor = (l) => l === 'error' ? '✕' : (l === 'info' ? '●' : '⚠');
    bar.innerHTML = alerts.map(a =>
      `<span class="alert-chip ${a.level}">${iconFor(a.level)} ${escapeHtml(a.msg)}</span>`
    ).join('');
  }

  // ── INSIGHTS (models + ETA) ───────────────
  renderInsights() {
    const ins = this.rawInsights;
    if (!ins) return;

    // Model comparison
    const modelEl = document.getElementById('model-bars');
    if (modelEl && ins.models?.length) {
      const maxEma = Math.max(...ins.models.map(m => m.avg_ema || 0), 0.01);
      const colors = ['var(--amber)','var(--gold)','var(--green)','var(--blue)'];
      modelEl.innerHTML = ins.models.map((m, i) => {
        const pct = ((m.avg_ema || 0) / maxEma) * 100;
        return `<div class="model-row">
          <span class="model-name" title="${escapeHtml(m.model)}">${escapeHtml(m.model)}</span>
          <span class="model-track"><span class="model-fill" style="width:${pct}%;background:${colors[i%colors.length]}"></span></span>
          <span class="model-ema">${(m.avg_ema||0).toFixed(4)}</span>
        </div>`;
      }).join('');
    }

    // ETA predictions
    const etaEl = document.getElementById('eta-bars');
    if (etaEl && ins.predictions?.length) {
      const preds = [...ins.predictions].sort((a, b) => (a.eta_days ?? 999) - (b.eta_days ?? 999));
      etaEl.innerHTML = preds.map(p => {
        let cls = '', label;
        if (p.eligible_now || p.eta_days === 0) { cls = 'eligible'; label = '◆ ahora'; }
        else if (p.eta_days == null) { cls = 'stalled'; label = '—'; }
        else if (p.eta_days <= 7) { cls = ''; label = `${p.eta_days}d`; }
        else if (p.eta_days <= 30) { cls = 'slow'; label = `${p.eta_days}d`; }
        else { cls = 'stalled'; label = '>30d'; }
        const pct = p.eligible_now ? 100 : Math.max(5, Math.min(100, 100 - Math.min(p.eta_days || 99, 200) / 2));
        return `<div class="eta-row">
          <span class="eta-domain">${escapeHtml(p.domain)}</span>
          <span class="eta-track"><span class="eta-fill ${cls}" style="width:${pct}%"></span></span>
          <span class="eta-val ${cls}">${label}</span>
        </div>`;
      }).join('');
    }
  }

  // ── FLEET TABLE ──────────────────────────
  renderFleet() {
    const tbody = document.getElementById('fleet-tbody');
    if (!tbody) return;
    const specs = this.sortSpecs();
    const deltaMap = {};
    (this.rawOverview?.ema_deltas || []).forEach(d => { deltaMap[d.specialist_id] = d; });

    tbody.innerHTML = specs.map(s => {
      const ema = Number(s.ema_score || 0);
      const d = deltaMap[s.specialist_id];
      const deltaVal = d ? ema - Number(d.ema_24h_ago || ema) : 0;
      const dCls = deltaVal > 0.0005 ? 'delta-up' : (deltaVal < -0.0005 ? 'delta-down' : 'delta-flat');
      const dTxt = !d ? '—' : `${deltaVal >= 0 ? '+' : ''}${deltaVal.toFixed(4)}`;
      const tier = s.tier || 0;
      const tierCls = tier >= 4 ? 'legend' : tier === 3 ? 'gold' : tier === 2 ? 'silver' : 'none';
      const tierLbl = tier >= 4 ? 'LEGEND' : tier === 3 ? 'GOLD' : tier === 2 ? 'SILVER' : '—';
      const q = s.avg_quality || 0;
      const qMax = s.max_quality || 0;
      const qMin = s.min_quality || 0;
      const qTxt = q ? `${q.toFixed(2)} <span style="color:var(--text-mute)">[${qMin.toFixed(1)}–${qMax.toFixed(1)}]</span>` : '—';
      const racha = s.racha_25 || 0;
      const rachaPct = Math.round(racha * 100);
      const status = (s.status || 'idle').toLowerCase();
      const isActive = status === 'active' || status === 'mining' || status === 'absorbing';
      const failRate = s.fail_rate != null ? (s.fail_rate * 100).toFixed(1) + '%' : '—';
      // ETA from insights
      let etaTxt = '—';
      if (this.rawInsights?.predictions) {
        const pred = this.rawInsights.predictions.find(p => p.specialist_id === s.id);
        if (pred) {
          if (pred.eligible_now || pred.eta_days === 0) etaTxt = '<span style="color:var(--gold)">◆ ahora</span>';
          else if (pred.eta_days != null) etaTxt = `${pred.eta_days}d`;
        }
      }

      const iconMap={SoftwareEngineering:'01-software-engineering',Mathematics:'02-mathematics',Medicine:'03-medicine',LegalSystem:'04-legal-system',PhilosophyHistory:'05-philosophy-history',FinanceEconomics:'06-finance-economics',Physics:'07-physics',Cybersecurity:'08-cybersecurity',Geopolitics:'09-geopolitics',DataScience:'10-data-science',Chemistry:'11-chemistry',ArtHistory:'12-art-history',Electronics:'13-electronics',Astronomy:'14-astronomy',Linguistics:'15-linguistics',Psychology:'16-psychology',EnvironmentalScience:'17-environmental-science',Sociology:'18-sociology'};
      const icon=iconMap[s.domain]||'01-software-engineering';
      return `<tr class="row-${tierCls}">
        <td><span class="tier-badge ${tierCls}">${tierLbl}</span></td>
        <td class="domain-cell"><span style="display:flex;align-items:center;gap:8px;"><img src="assets/grafia/icons/${icon}.svg" alt="" width="22" height="22" style="flex-shrink:0;background:var(--paper-2);border:1px solid var(--border);border-radius:50%;padding:3px;"><span>${escapeHtml(s.domain)}</span></span></td>
        <td class="model-cell">${escapeHtml(s.model || '')}</td>
        <td class="num ema-val">${ema.toFixed(4)}</td>
        <td class="num ${dCls}">${dTxt}</td>
        <td class="num eta-cell">${etaTxt}</td>
        <td class="num">${qTxt}</td>
        <td class="num">${s.failures ?? '—'} <span style="color:var(--text-mute)">(${failRate})</span></td>
        <td class="num"><span class="racha-bar"><span class="racha-bar-fill" style="width:${rachaPct}%"></span></span><span class="racha-pct">${rachaPct}%</span></td>
        <td class="num">${(s.packages_absorbed || 0).toLocaleString()}</td>
        <td class="num">${(s.total_cycles || 0).toLocaleString()}</td>
        <td><span class="status-dot ${isActive ? 'active' : status === 'error' ? 'error' : 'idle'}"></span><span class="status-label">${status}</span></td>
      </tr>`;
    }).join('');
  }

  sortSpecs() {
    const arr = [...this.rawSpecs];
    const k = this.sortKey, dir = this.sortDir;
    const etaMap = {};
    if (this.rawInsights?.predictions) {
      this.rawInsights.predictions.forEach(p => { etaMap[p.specialist_id] = p.eta_days ?? 999; });
    }
    const getv = s => {
      if (k === 'domain') return s.domain || '';
      if (k === 'ema') return Number(s.ema_score || 0);
      if (k === 'quality') return s.avg_quality || 0;
      if (k === 'packages') return s.packages_absorbed || 0;
      if (k === 'eta') return etaMap[s.id] ?? 999;
      return 0;
    };
    arr.sort((a, b) => {
      const va = getv(a), vb = getv(b);
      if (typeof va === 'string') return va.localeCompare(vb) * dir;
      return (va - vb) * dir;
    });
    return arr;
  }

  // ── METRICS ──────────────────────────────
  renderMetrics() {
    // throughput
    const data = this.rawOverview?.throughput || [];
    if (data.length) {
      const last = data.slice(-48);
      drawThroughputBars('chart-throughput', last);
      const total = last.reduce((a, r) => a + (r.cycles || 0), 0);
      const el = document.getElementById('tp-total'); if (el) el.textContent = total.toLocaleString();
    }
    // tier bars
    this.renderTierBars();
  }

  renderTierBars() {
    const el = document.getElementById('tier-bars');
    if (!el) return;
    const tiers = { 4: { label: 'Legend', color: 'var(--gold)' }, 3: { label: 'Gold', color: 'var(--amber)' }, 2: { label: 'Silver', color: 'var(--blue)' }, 1: { label: 'Bronze', color: 'var(--text-mute)' } };
    const total = this.rawSpecs.length || 1;
    el.innerHTML = Object.entries(tiers).map(([t, info]) => {
      const cnt = this.rawSpecs.filter(s => s.tier === Number(t)).length;
      const pct = (cnt / total) * 100;
      return `<div class="tier-bar-row">
        <span class="tier-bar-label">${info.label}</span>
        <span class="tier-bar-track"><span class="tier-bar-fill" style="width:${pct}%;background:${info.color}"></span></span>
        <span class="tier-bar-count">${cnt}</span>
      </div>`;
    }).join('');
  }

  // ── ACTIVITY ─────────────────────────────
  renderActivity() {
    const feed = document.getElementById('activity-feed');
    if (!feed) return;
    let logs = this.rawOverview?._logs || [];
    // use logs from a dedicated fetch stored in this._logs
    logs = this._logs || [];
    if (this.actFilter !== 'ALL') logs = logs.filter(l => l.level === this.actFilter);
    if (!logs.length) { if (!feed.children.length) feed.innerHTML = '<div style="padding:20px;color:var(--text-mute)">Sin actividad registrada</div>'; return; }

    // incremental render
    const existing = new Set();
    feed.querySelectorAll('[data-id]').forEach(el => existing.add(Number(el.dataset.id)));
    const fresh = logs.filter(l => !existing.has(l.id));
    if (!fresh.length) return;
    const frag = document.createDocumentFragment();
    fresh.slice(0, 15).forEach(l => {
      const t = document.createElement('div');
      t.className = 'activity-item fade-in';
      t.dataset.id = l.id;
      const time = l.timestamp ? new Date(l.timestamp.replace(' ', 'T') + 'Z').toLocaleTimeString('es-ES', {hour:'2-digit',minute:'2-digit',second:'2-digit'}) : '--:--:--';
      t.innerHTML = `<span class="t">${time}</span><span class="lvl lvl-${l.level}">${l.level}</span><span class="m">${escapeHtml(l.message || '')}</span>`;
      frag.appendChild(t);
    });
    feed.prepend(frag);
    while (feed.children.length > 80) feed.removeChild(feed.lastChild);
  }

  pushSpark(key, value, canvasId) {
    const arr = this.spark[key];
    arr.push(value);
    if (arr.length > 40) arr.shift();
    const canvas = document.getElementById(canvasId);
    if (canvas) drawSparkline(canvas, arr);
  }

  // ── EMA CHART ────────────────────────────
  async loadEmaChart() {
    const data = await this.fetchJSON(`${this.apiBase}/analytics/ema-history?hours=${this.rangeHours}`);
    if (!data || !data.series) return;
    this.emaSeries = {};
    data.series.forEach(s => { this.emaSeries[s.specialist_id] = s; });
    drawEmaMultiLine('chart-ema', data.series, document.getElementById('legend-ema'), this.rangeHours);
    this.emaSeriesEmpty = false;
  }

  async killAll() {
    if (!confirm('¿Detener todos los procesos de Expertia?')) return;
    await this.fetchJSON(`${this.apiBase}/kill`, {
      method: 'POST',
      headers: { 'X-API-Key': this._apiKey || 'local', 'Content-Type': 'application/json' },
      body: '{}',
    });
    const pill = document.getElementById('pp-status');
    if (pill) pill.textContent = 'procesos detenidos';
  }

  exportCSV() {
    const specs = this.sortSpecs();
    const etaMap = {};
    if (this.rawInsights?.predictions) {
      this.rawInsights.predictions.forEach(p => { etaMap[p.specialist_id] = p.eta_days; });
    }
    const headers = ['Tier','Specialist','Model','EMA','Delta24h','ETA_Legend_d','Quality','Failures','Racha25','Packages','Cycles','Status'];
    const rows = specs.map(s => {
      const ema = Number(s.ema_score || 0).toFixed(4);
      const d = (this.rawOverview?.ema_deltas || []).find(x => x.specialist_id === s.id);
      const delta = d ? (ema - Number(d.ema_24h_ago || ema)).toFixed(4) : '0';
      const eta = etaMap[s.id];
      const etaVal = eta == null ? '' : (s.tier >= 4 ? 'LEGIBLE' : `${eta}`);
      return [s.tier >= 4 ? 'Legend' : s.tier === 3 ? 'Gold' : 'Silver',
        s.domain, s.model || '', ema, delta, etaVal,
        (s.avg_quality || 0).toFixed(2), s.failures ?? 0,
        ((s.racha_25 || 0) * 100).toFixed(0) + '%',
        s.packages_absorbed || 0, s.total_cycles || 0, s.status || ''].join(',');
    });
    const csv = headers.join(',') + '\n' + rows.join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `expertia_fleet_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
    this.toast('Exportado', `${specs.length} filas descargadas`, 'success', 3000);
  }
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
}

function drawSparkline(canvas, values) {
  const ctx = canvas.getContext('2d');
  const W = canvas.clientWidth || 100, H = canvas.clientHeight || 30;
  canvas.width = W; canvas.height = H;
  const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
  const accent = isDark ? '#E8913A' : '#C4641A';
  const max = Math.max(...values, 1), min = Math.min(...values, 0);
  const range = (max - min) || 1;
  ctx.clearRect(0, 0, W, H);
  ctx.beginPath();
  for (let i = 0; i < values.length; i++) {
    const x = (i / (values.length - 1)) * W;
    const y = H - ((values[i] - min) / range) * (H - 4) - 2;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  }
  ctx.strokeStyle = accent; ctx.lineWidth = 1.5; ctx.lineJoin = 'round'; ctx.stroke();
}

const app = new App();
