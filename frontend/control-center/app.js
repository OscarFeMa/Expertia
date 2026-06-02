class App {
  constructor() {
    this.apiBase = '/api';
    this.refreshInterval = null;
    this.theme = localStorage.getItem('expertia-theme') || 'light';
    document.documentElement.setAttribute('data-theme', this.theme);
    this.activeTab = 'dashboard';
    this.dataCache = {};
    this.memoryHistory = [];
    this.apiKey = localStorage.getItem('expertia-api-key') || '';
    this.init();
  }

  async init() {
    await this.loadHealth();
    await this.updateSidebarStats();
    this.startAutoRefresh();
    this.updateClock();
    setInterval(() => this.updateClock(), 5000);
    setInterval(() => this.updateDashboardTimers(), 1000);
  }

  formatRemaining(uptimeSec, durationHours) {
    if (!durationHours || durationHours <= 0) return '∞';
    const total = durationHours * 3600;
    const left = Math.max(0, total - uptimeSec);
    const h = Math.floor(left / 3600);
    const m = Math.floor((left % 3600) / 60);
    const s = Math.floor(left % 60);
    return `${h}h ${m.toString().padStart(2,'0')}m ${s.toString().padStart(2,'0')}s`;
  }

  updateDashboardTimers() {
    const clockEl = document.getElementById('dash-clock');
    if (clockEl) clockEl.textContent = new Date().toLocaleTimeString();
    const remEl = document.getElementById('dash-remaining');
    if (remEl && this._lastPidInfo && this._lastPidInfo.alive) {
      const uptime = this._lastPidInfo.uptime_seconds + Math.floor((Date.now() - this._lastFetchTime) / 1000);
      remEl.textContent = this.formatRemaining(uptime, this._lastPidInfo.duration_hours);
    }
  }

  updateClock() {
    const now = new Date();
    document.getElementById('sb-time').textContent = now.toLocaleTimeString();
  }

  async updateSidebarStats() {
    const [specData, health] = await Promise.all([
      this.fetchJSON(`${this.apiBase}/specialists`),
      this.fetchJSON(`${this.apiBase}/health`),
    ]);
    const setText = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    const specs = specData?.specialists || [];
    setText('ss-specs', specs.length || '-');
    setText('ss-pkgs', (health?.package_count || 0).toLocaleString());
    setText('ss-incidents', health?.incident_count || '-');
    setText('ss-reliable', specs.filter(s => s.is_reliable).length + '/' + specs.length);
    if (specData) this._lastSpecialists = specs;
  }

  startAutoRefresh() {
    if (this.refreshInterval) clearInterval(this.refreshInterval);
    this.refreshInterval = setInterval(async () => {
      if (document.hidden) return;
      await this.refreshActiveTab();
    }, 10000);
  }

  async fetchJSON(url, timeoutMs = 30000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(url, { signal: controller.signal });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (e) {
      if (e.name === 'AbortError') console.error('Fetch timeout:', url);
      else console.error('Fetch error:', url, e);
      return null;
    } finally {
      clearTimeout(timer);
    }
  }

  async postJSON(url, body, timeoutMs = 30000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (this.apiKey) headers['X-API-Key'] = this.apiKey;
      const res = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify(body || {}),
        signal: controller.signal,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      return await res.json();
    } catch (e) {
      if (e.name === 'AbortError') console.error('POST timeout:', url);
      else console.error('POST error:', url, e);
      return { error: e.message };
    } finally {
      clearTimeout(timer);
    }
  }

  async loadHealth() {
    const h = await this.fetchJSON(`${this.apiBase}/health`);
    const sb = document.getElementById('sb-status');
    if (h) {
      const dot = h.database === 'ok' ? '🟢' : '🔴';
      sb.textContent = `${dot} DB: ${h.database} · ${h.specialist_count} specialists · ${h.package_count} packages · ${h.incident_count} incidents`;
    } else {
      sb.textContent = '🔴 Connection error';
    }
  }

  async refreshActiveTab() {
    switch (this.activeTab) {
      case 'dashboard': await this.renderDashboard(); break;
      // Other tabs only refresh on manual switch, not on auto-refresh
    }
  }

  switchTab(tab) {
    this.activeTab = tab;
    document.querySelectorAll('.nav-item').forEach(el => el.classList.toggle('active', el.dataset.tab === tab));
    document.querySelectorAll('.tab-content').forEach(el => el.classList.toggle('active', el.id === `tab-${tab}`));
    switch (tab) {
      case 'dashboard': this.renderDashboard(); break;
      case 'specialists': this.renderSpecialists(); break;
      case 'fleet': this.renderFleet(); break;
      case 'map': this.renderMap(); break;
      case 'super-experts': this.renderSuperExperts(); break;
      case 'certified': this.renderCertified(); break;
      case 'incidents': this.renderIncidents(); break;
      case 'wikidata': this.renderWikidata(); break;
    }
  }

  clickReliable(domain) {
    this._highlightDomain = domain;
    this.switchTab('certified');
  }

  killAll() {
    if (!confirm('Kill all processes? This will stop the pipeline and API.')) return;
    const btn = document.querySelector('.kill-btn');
    if (btn) { btn.textContent = '⏹ Killing...'; btn.disabled = true; }
    this.postJSON(`${this.apiBase}/kill`, {}).then(r => {
      alert('All processes killed. API shutting down.');
    }).catch(() => {
      alert('Kill signal sent. API is shutting down.');
    });
  }

  toggleTheme() {
    this.theme = this.theme === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', this.theme);
    localStorage.setItem('expertia-theme', this.theme);
    this.refreshActiveTab();
  }

  escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  utcToLocal(ts) {
    if (!ts) return '-';
    try {
      const d = new Date(ts);
      if (isNaN(d.getTime())) return String(ts).slice(11, 19);
      return d.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
    } catch {
      return String(ts).slice(11, 19) || '-';
    }
  }

  narrativeHumor(level, message) {
    const msg = String(message).slice(0, 200);
    if (msg.includes('403')) return 'El bibliotecario jefe denegó el acceso a la estantería';
    if (msg.includes('404')) return 'El libro solicitado no se encuentra en los anaqueles';
    if (msg.includes('500')) return 'Los duendes del servidor están de huelga';
    if (msg.includes('Package guardado')) return 'Un tomo más descansa en los estantes del archivo';
    if (msg.toLowerCase().includes('package saved')) return 'Un volumen ha sido catalogado exitosamente';
    if (msg.toLowerCase().includes('timeout')) return 'El mensajero tardó demasiado y perdió la paciencia';
    if ((msg.toLowerCase().includes('connection') || msg.toLowerCase().includes('refused')) && (msg.toLowerCase().includes('error') || msg.toLowerCase().includes('fail')))
      return 'El cableado entre anaqueles falló — alguien tropezó con el cable';
    if (msg.toUpperCase().includes('HTTP') && (msg.toLowerCase().includes('error') || msg.toLowerCase().includes('fail')))
      return 'El archivista reporta problemas técnicos con la conexión';
    if (msg.includes('Buscan') || msg.includes('Search') || msg.includes('DDGS')) return 'Hojeando el catálogo en busca de referencias...';
    if (msg.toLowerCase().includes('trafilatura')) return 'El fotocopiador digital está extrayendo páginas';
    if (msg.includes('Destilando') || msg.toLowerCase().includes('query')) return 'Las neuronas están sudando — proceso cognitivo en marcha';
    if (level === 'ERROR' || level === 'CRITICAL') return `Incidente en la sala de lectura: ${msg.slice(0, 150)}`;
    if (level === 'WARNING') return `El bibliotecario frunce el ceño: ${msg.slice(0, 150)}`;
    if (level === 'DEBUG') return `El archivista anota en sus cuadernos: ${msg.slice(0, 150)}`;
    return msg;
  }

  specSortFn(key) {
    const order = { ACTIVE: 0, IDLE: 1, COMPLETED: 2, ERROR: 3, STOPPED: 4 };
    const sortMap = {
      'domain-asc': (a, b) => a.domain.localeCompare(b.domain),
      'domain-desc': (a, b) => b.domain.localeCompare(a.domain),
      'pkg-asc': (a, b) => (a.packages_absorbed || 0) - (b.packages_absorbed || 0),
      'pkg-desc': (a, b) => (b.packages_absorbed || 0) - (a.packages_absorbed || 0),
      'ema-asc': (a, b) => (a.ema_score || 0) - (b.ema_score || 0),
      'ema-desc': (a, b) => (b.ema_score || 0) - (a.ema_score || 0),
      'status': (a, b) => (order[a.status] || 99) - (order[b.status] || 99),
      'status-desc': (a, b) => (order[b.status] || 99) - (order[a.status] || 99),
      'model': (a, b) => a.model.localeCompare(b.model),
    };
    return sortMap[key] || sortMap['domain-asc'];
  }

  tierIcon(tier) {
    if (tier === 4) return '<span class="tier-legend" title="Legend">👑</span>';
    if (tier === 3) return '<span class="tier-gold" title="Gold">⭐⭐</span>';
    if (tier === 2) return '<span class="tier-silver" title="Silver">⭐</span>';
    if (tier === 1) return '<span class="tier-bronze" title="Bronze">◆</span>';
    return '';
  }

  tierBorder(tier) {
    if (tier === 4) return 'spec-card-legend';
    if (tier === 3) return 'spec-card-gold';
    if (tier === 2) return 'spec-card-silver';
    if (tier === 1) return 'spec-card-bronze';
    return '';
  }

  logIcon(level) {
    return { INFO: '📝', WARNING: '👀', ERROR: '🔥', CRITICAL: '🔥', DEBUG: '📋' }[level] || '📝';
  }

  renderLogEntry(row, highlight) {
    const ts = this.utcToLocal(row.timestamp);
    const icon = this.logIcon(row.level);
    const msg = this.escapeHtml(this.narrativeHumor(row.level, String(row.message).slice(0, 200)));
    const hl = highlight ? ' style="background:rgba(255,107,107,0.1)"' : '';
    return `<div class="log-entry"${hl}><span class="log-ts">${this.escapeHtml(ts)}</span><span class="log-icon">${icon}</span><span class="log-msg">${msg}</span></div>`;
  }

  // ── DASHBOARD ──────────────────────────────────────────────────────────
  async renderDashboard() {
    const el = document.getElementById('tab-dashboard');
    const [status, specialists, logs, health, pidData] = await Promise.all([
      this.fetchJSON(`${this.apiBase}/status`),
      this.fetchJSON(`${this.apiBase}/specialists`),
      this.fetchJSON(`${this.apiBase}/activity-log?limit=1`),
      this.fetchJSON(`${this.apiBase}/health`),
      this.fetchJSON(`${this.apiBase}/pipeline/pid`),
    ]);
    if (!status && !health) { el.innerHTML = '<div class="card">Error connecting to API</div>'; return; }

    const s = status || {};
    const pidInfo = pidData || {};
    this._lastPidInfo = pidInfo;
    this._lastFetchTime = Date.now();
    const procAlive = pidInfo.alive || false;
    const pState = procAlive ? (s.status || 'ACTIVE') : 'STOPPED';
    const isActive = procAlive;
    const specialistsList = specialists?.specialists || [];
    const totalSpec = specialistsList.length;
    const doneSpec = specialistsList.filter(sp => sp.status === 'IDLE' || sp.status === 'COMPLETED').length;
    const progress = totalSpec > 0 ? (doneSpec / totalSpec * 100) : 0;
    const pid = pidInfo.pid;
    const uptime = pidInfo.uptime_seconds || 0;

    const logsList = logs?.logs || [];

    let html = `
      <div class="header-bar">
        <div class="header-cell">
          <div class="header-label">Status</div>
          <div class="header-value" style="color:${isActive ? '#FF6B6B' : '#4ECDC4'}">${isActive ? '<span class="coral-dot"></span>' : ''}${pState}</div>
        </div>
        <div class="header-cell">
          <div class="header-label">Phase</div>
          <div class="header-value sm">${s.phase || '-'}</div>
        </div>
        <div class="header-cell">
          <div class="header-label">Specialist</div>
          <div class="header-value sm">${s.current_specialist || '-'}</div>
        </div>
        <div class="header-cell">
          <div class="header-label">Cycle</div>
          <div class="header-value sm">${s.current_cycle || 0}/${s.total_cycles || 0}</div>
        </div>
        <div class="header-cell">
          <div class="header-label">Elapsed</div>
          <div class="header-value sm">${s.elapsed_seconds ? Math.floor(s.elapsed_seconds / 60) + 'm' : '--'}</div>
        </div>
        <div class="header-cell">
          <div class="header-label">Remaining</div>
          <div class="header-value sm" id="dash-remaining">${isActive ? this.formatRemaining(uptime, pidInfo.duration_hours) : '--'}</div>
        </div>
        <div class="header-cell">
          <div class="header-label">Clock</div>
          <div class="header-value sm" id="dash-clock">${new Date().toLocaleTimeString()}</div>
        </div>
      </div>

      <!-- Synaptic activity pulse -->
      <div class="synaptic-pulse" id="synaptic-pulse">
        <div class="pulse-dot ${isActive ? 'active' : 'idle'}"></div>
        <div class="pulse-label">${isActive ? '🧠 Synaptic activity' : '🌙 Archive dormant'}</div>
        <div class="pulse-sub">${isActive ? (s.phase || 'Processing...') : 'Idle'}</div>
        <div class="wave-bars ${isActive ? '' : 'idle'}" id="wave-bars">
          <div class="bar"></div><div class="bar"></div><div class="bar"></div>
          <div class="bar"></div><div class="bar"></div><div class="bar"></div>
          <div class="bar"></div><div class="bar"></div><div class="bar"></div>
        </div>
        <div class="pulse-activity-text" id="pulse-activity-text">${logsList.length ? this.escapeHtml(this.narrativeHumor(logsList[0].level, logsList[0].message)) : ''}</div>
      </div>
    `;

    if (!isActive) {
      html += `<div class="card" id="launch-form" style="padding:10px 14px">
        <div class="launch-row">
          <div>
            <label>Phase</label>
            <select id="lp-phase" class="lp-phase">
              <option value="full">Full Cascade</option>
              <option value="cascade">Cascade</option>
              <option value="web">Web + LLM</option>
              <option value="nurture">🌱 Nurture</option>
            </select>
            <div class="launch-phase-desc" id="lp-phase-desc">Cascade → Web → LLM</div>
          </div>
          <div>
            <label>Specialists</label>
            <select id="lp-spec" class="lp-spec" onchange="app.onLaunchSpecChange()">
              <option value="all">All</option>
              <option value="model">By Model</option>
              <option value="single">One</option>
            </select>
          </div>
          <div id="lp-model-container" style="display:none">
            <label>Model</label>
            <select id="lp-model" class="lp-dyn"><option value="all">all</option></select>
          </div>
          <div id="lp-single-container" style="display:none">
            <label>Specialist</label>
            <select id="lp-single" class="lp-dyn"></select>
          </div>
          <div>
            <label>Duration (h)</label>
            <input type="number" id="lp-dur" class="lp-dur" value="5.0" min="1" max="24" step="0.5">
          </div>
          <div>
            <button onclick="app.startPipeline()" class="primary lp-start-btn">▶ Start</button>
          </div>
        </div>
        <div id="lp-msg" style="margin-top:4px;font-size:11px"></div>
      </div>`;

      html += `<div class="progress-bar"><div style="width:0%"></div></div>
      <div class="progress-info">System idle</div>`;
    } else {
      html += `<div class="card" style="display:flex;gap:12px;align-items:center">
        <button id="lp-stop-btn" onclick="app.stopPipeline()" style="background:var(--error);color:#fff;border-color:var(--error)">■ Stop</button>
        <span style="font-size:12px;color:var(--dim)">PID: ${pid || '--'} · Uptime: ${Math.floor(uptime / 60)}m</span>
        <div id="lp-msg" style="font-size:12px;flex:1"></div>
      </div>`;

      html += `<div class="progress-bar active"><div style="width:${progress}%"></div></div>
      <div class="progress-info">${doneSpec}/${totalSpec} specialists completed · Cycle ${s.current_cycle || 0} · ${s.phase || ''}</div>`;
    }

    // Specialist tree with sort
    let sortKey = this.dashSpecSort || 'domain-asc';
    const sortedSpecs = [...specialistsList].sort(this.specSortFn(sortKey));
    const roots = sortedSpecs.filter(sp => !sp.parent_id);
    const children = sortedSpecs.filter(sp => sp.parent_id);
    const childMap = {};
    children.forEach(c => { if (!childMap[c.parent_id]) childMap[c.parent_id] = []; childMap[c.parent_id].push(c); });
    const badgeMap = { ACTIVE: 'badge-active', IDLE: 'badge-idle', COMPLETED: 'badge-done', ERROR: 'badge-error', STOPPED: 'badge-idle' };
    const colorMap = { ACTIVE: '#FF6B6B', IDLE: '#4ECDC4', COMPLETED: '#4ECDC4', ERROR: '#C44536', STOPPED: '#6B7A8A' };

    html += `<div class="section-title"><h2>📚 Specialist Registry</h2>
      <select id="dash-spec-sort" onchange="app.dashSpecSort=this.value;app.renderDashboard()" style="font-size:11px;padding:2px 6px;height:auto">
        <option value="domain-asc" ${sortKey==='domain-asc'?'selected':''}>Domain ↑</option>
        <option value="domain-desc" ${sortKey==='domain-desc'?'selected':''}>Domain ↓</option>
        <option value="pkg-desc" ${sortKey==='pkg-desc'?'selected':''}>Packages ↓</option>
        <option value="pkg-asc" ${sortKey==='pkg-asc'?'selected':''}>Packages ↑</option>
        <option value="ema-desc" ${sortKey==='ema-desc'?'selected':''}>EMA ↓</option>
        <option value="ema-asc" ${sortKey==='ema-asc'?'selected':''}>EMA ↑</option>
        <option value="status" ${sortKey==='status'?'selected':''}>⚡ Active ↑</option>
        <option value="status-desc" ${sortKey==='status-desc'?'selected':''}>Status ↓</option>
        <option value="model" ${sortKey==='model'?'selected':''}>Model</option>
      </select>
    </div>`;
    html += '<div class="spec-grid-3">';
    const childSort = this.specSortFn(sortKey);
    roots.forEach(r => {
      const badge = badgeMap[r.status] || 'badge-idle';
      const bc = colorMap[r.status] || '#6B7A8A';
      const tier_class = this.tierBorder(r.tier);
      const ticon = this.tierIcon(r.tier);
      const base_class = `spec-card spec-card-${r.status === 'ACTIVE' ? 'active' : r.status === 'ERROR' ? 'error' : 'idle'}`;
      const card_class = tier_class ? `${base_class} ${tier_class}` : base_class;
      const reliable = r.tier >= 1;
      html += `<div class="${card_class}"${reliable ? ` data-domain="${this.escapeHtml(r.domain)}" onclick="app.clickReliable(this.dataset.domain)" title="Click to view stats"` : ''}>
        <div class="spec-card-inner"><span class="spec-name">${this.escapeHtml(r.domain)} ${ticon}</span><span class="spec-badge ${badge}" style="background:${bc}22;color:${bc}">${this.escapeHtml(r.status)}</span></div>
        <div class="spec-meta">📦 ${r.packages_absorbed} · 📈 ${r.ema_score != null ? r.ema_score.toFixed(3) : '—'} · 🎯 ${this.escapeHtml(r.model || '')}</div>`;
      (childMap[r.id] || []).sort(childSort).forEach(c => {
        html += `<div class="spec-meta" style="margin-top:2px;padding-top:2px;border-top:1px dashed var(--border)">
          └─ ${this.escapeHtml(c.domain)} · 📦${c.packages_absorbed} · 📈${c.ema_score != null ? c.ema_score.toFixed(2) : '—'} · 🎯 ${this.escapeHtml(c.model || '')}
          <span class="spec-badge ${badgeMap[c.status] || 'badge-idle'}" style="background:${colorMap[c.status]}22;color:${colorMap[c.status]};font-size:9px;padding:0 4px;margin-left:4px">${this.escapeHtml(c.status || '')}</span>
        </div>`;
      });
      html += `</div>`;
    });
    html += '</div>';

    // Activity log — single line
    html += `<div class="section-title" style="margin-top:16px"><h2>📜 Library Whispers</h2></div>`;
    if (logsList.length) {
      html += this.renderLogEntry(logsList[0], true);
    } else {
      html += `<div class="card" style="color:var(--dim)">-- silence in the library --</div>`;
    }

    // Save launch form values before re-render
    const savedForm = !isActive ? {
      phase: document.getElementById('lp-phase')?.value,
      spec: document.getElementById('lp-spec')?.value,
      model: document.getElementById('lp-model')?.value,
      single: document.getElementById('lp-single')?.value,
      dur: document.getElementById('lp-dur')?.value,
    } : null;

    el.innerHTML = html;

    // Populate model/specialist selects and restore saved values
    if (!isActive) {
      this.populateLaunchForm(specialistsList);
      if (savedForm) {
        if (savedForm.phase) document.getElementById('lp-phase').value = savedForm.phase;
        if (savedForm.spec) {
          document.getElementById('lp-spec').value = savedForm.spec;
          this.onLaunchSpecChange();
        }
        if (savedForm.model) document.getElementById('lp-model').value = savedForm.model;
        if (savedForm.single) document.getElementById('lp-single').value = savedForm.single;
        if (savedForm.dur) document.getElementById('lp-dur').value = savedForm.dur;
      }
    }
    this.updateSidebarStats();
  }

  onLaunchSpecChange() {
    const v = document.getElementById('lp-spec')?.value;
    document.getElementById('lp-model-container').style.display = v === 'model' ? 'block' : 'none';
    document.getElementById('lp-single-container').style.display = v === 'single' ? 'block' : 'none';
  }

  _toggleNurtureMode(isNurture) {
    const elIds = ['lp-spec', 'lp-model', 'lp-single', 'lp-dur'];
    elIds.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.disabled = isNurture;
    });
    document.getElementById('lp-model-container').style.display = isNurture ? 'none' : (document.getElementById('lp-spec')?.value === 'model' ? 'block' : 'none');
    document.getElementById('lp-single-container').style.display = isNurture ? 'none' : (document.getElementById('lp-spec')?.value === 'single' ? 'block' : 'none');
  }

  populateLaunchForm(specialists) {
    const phaseSel = document.getElementById('lp-phase');
    if (phaseSel) {
      phaseSel.onchange = () => {
        const isNurture = phaseSel.value === 'nurture';
        const desc = { full: 'Cascade → Web → LLM', cascade: 'Wikidata scan only', web: 'Web search + LLM loop', nurture: 'Raise low EMA → 0.96 one by one' };
        document.getElementById('lp-phase-desc').textContent = desc[phaseSel.value] || '';
        this._toggleNurtureMode(isNurture);
      };
      // Apply on initial load if nurture was previously saved
      this._toggleNurtureMode(phaseSel.value === 'nurture');
    }
    const modelSel = document.getElementById('lp-model');
    if (modelSel) {
      const models = [...new Set(specialists.map(s => s.model))];
      modelSel.innerHTML = '<option value="all">all</option>' + models.map(m => `<option value="${this.escapeHtml(m)}">${this.escapeHtml(m)}</option>`).join('');
    }
    const singleSel = document.getElementById('lp-single');
    if (singleSel) {
      const domains = specialists.filter(s => !s.parent_id).map(s => s.domain);
      singleSel.innerHTML = domains.map(d => `<option value="${this.escapeHtml(d)}">${this.escapeHtml(d)}</option>`).join('');
    }
  }

  async startPipeline() {
    const msgEl = document.getElementById('lp-msg');
    if (!msgEl) return;
    const btn = document.querySelector('.lp-start-btn');
    if (btn) btn.disabled = true;
    try {
      const phase = document.getElementById('lp-phase')?.value || 'full';
      let specialist = 'all', model = 'all', duration = 5.0;
      if (phase !== 'nurture') {
        const specMode = document.getElementById('lp-spec')?.value || 'all';
        if (specMode === 'model') model = document.getElementById('lp-model')?.value || 'all';
        if (specMode === 'single') specialist = document.getElementById('lp-single')?.value || 'all';
        duration = parseFloat(document.getElementById('lp-dur')?.value) || 5.0;
      }

      msgEl.textContent = 'Starting...';
      const result = await this.postJSON(`${this.apiBase}/pipeline/start`, { phase, specialist, model, duration });
      if (result.error) {
        msgEl.textContent = `❌ ${result.error}`;
        msgEl.style.color = 'var(--error)';
      } else {
        msgEl.textContent = `✅ Started PID: ${result.pid}`;
        msgEl.style.color = 'var(--inactive)';
        setTimeout(() => this.renderDashboard(), 2000);
      }
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async stopPipeline() {
    const msgEl = document.getElementById('lp-msg');
    if (!msgEl) return;
    const btn = document.getElementById('lp-stop-btn');
    if (btn) btn.disabled = true;
    try {
      msgEl.textContent = 'Stopping...';
      const result = await this.postJSON(`${this.apiBase}/pipeline/stop`, {});
      if (result.error) {
        msgEl.textContent = `❌ ${result.error}`;
        msgEl.style.color = 'var(--error)';
      } else {
        msgEl.textContent = `✅ Stopped PID: ${result.pid}`;
        msgEl.style.color = 'var(--inactive)';
        setTimeout(() => this.renderDashboard(), 2000);
      }
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  // ── SPECIALISTS ─────────────────────────────────────────────────────────
  async renderSpecialists() {
    const el = document.getElementById('tab-specialists');
    const [data, qualifiedData] = await Promise.all([
      this.fetchJSON(`${this.apiBase}/specialists`),
      this.fetchJSON(`${this.apiBase}/qualified-specialists`),
    ]);
    const list = data?.specialists || [];
    const qualified = qualifiedData?.specialists || [];
    let html = `<div class="section-title"><h2>📚 Specialist Registry</h2></div>`;
    html += `<div class="filter-bar">
      <input type="text" id="spec-search" placeholder="🔍 filter by domain or model..." oninput="app.filterSpecialists()">
      <select id="spec-sort" onchange="app.filterSpecialists()">
        <option value="domain-asc">Domain ↑</option>
        <option value="domain-desc">Domain ↓</option>
        <option value="pkg-desc">Packages ↓</option>
        <option value="pkg-asc">Packages ↑</option>
        <option value="ema-desc">EMA ↓</option>
        <option value="ema-asc">EMA ↑</option>
        <option value="status">⚡ Active ↑</option>
        <option value="status-desc">Status ↓</option>
        <option value="model">Model</option>
      </select>
    </div><div id="spec-table"></div>`;

    if (qualified.length > 0) {
      html += `<div class="section-title" style="margin-top:16px"><h2>✨ Spawn Sub-Specialist</h2></div>
        <div class="card">
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px">
            <label style="font-size:12px">Parent:</label>
            <select id="spawn-parent" onchange="app.onSpawnParentChange()" style="flex:1;min-width:180px">
              ${qualified.map(s => `<option value="${s.id}" data-model="${this.escapeHtml(s.model || '')}">${this.escapeHtml(s.domain)} (${s.packages_absorbed} pkgs, EMA ${s.ema_score != null ? s.ema_score.toFixed(3) : '—'})</option>`).join('')}
            </select>
          </div>
          <div id="spawn-expansions" style="max-height:200px;overflow-y:auto;margin-bottom:8px;font-size:12px">
            <span class="dim">Select a qualified specialist to load expansions...</span>
          </div>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <label style="font-size:12px">Model:</label>
            <input type="text" id="spawn-model" style="flex:1;min-width:120px">
            <button id="spawn-btn" onclick="app.spawnSubSpecialists()" disabled class="primary">▶ Spawn Selected</button>
          </div>
          <div id="spawn-log" style="margin-top:8px;max-height:200px;overflow-y:auto;font-size:11px;font-family:monospace;background:var(--bg);padding:4px;border-radius:4px"></div>
        </div>`;
    }

    el.innerHTML = html;
    this.allSpecialistsData = list;
    this.filterSpecialists();
    if (qualified.length > 0) this.onSpawnParentChange();
  }

  async onSpawnParentChange() {
    const sel = document.getElementById('spawn-parent');
    if (!sel) return;
    const sid = sel.value;
    const opt = sel.options[sel.selectedIndex];
    document.getElementById('spawn-model').value = opt?.dataset?.model || '';
    const data = await this.fetchJSON(`${this.apiBase}/specialists/${sid}/expansions`);
    const expansions = data?.expansions || [];
    const container = document.getElementById('spawn-expansions');
    const btn = document.getElementById('spawn-btn');
    if (expansions.length === 0) {
      container.innerHTML = '<span class="dim">No QID expansions available for this specialist</span>';
      btn.disabled = true;
      return;
    }
    const existing = await this.fetchJSON(`${this.apiBase}/specialists`);
    const existingQids = new Set((existing?.specialists || []).filter(s => s.parent_id == sid).map(s => s.root_qid));
    let html = '<table style="width:100%;border-collapse:collapse">';
    html += '<tr style="font-weight:600"><td style="padding:2px 6px"><input type="checkbox" id="spawn-select-all" onchange="app.toggleAllSpawn()" checked></td><td style="padding:2px 6px">QID</td><td style="padding:2px 6px">Label</td><td style="padding:2px 6px">Status</td></tr>';
    let validCount = 0;
    expansions.forEach(e => {
      const alreadyExists = existingQids.has(e.qid);
      const valid = e.valid_p279 && !e.blocklisted && !alreadyExists;
      if (valid) validCount++;
      const status = alreadyExists ? '⚠ already exists' :
        !e.valid_p279 ? '✗ P279 fail' :
        e.blocklisted ? '✗ blocklisted' : '✓ valid';
      const color = alreadyExists ? '#FFA500' : !e.valid_p279 || e.blocklisted ? 'var(--error)' : 'var(--active)';
      html += `<tr>
        <td style="padding:2px 6px"><input type="checkbox" class="spawn-qid-cb" value="${e.qid}" ${valid ? 'checked' : 'disabled'}></td>
        <td style="padding:2px 6px;font-family:monospace">${e.qid}</td>
        <td style="padding:2px 6px">${e.label}</td>
        <td style="padding:2px 6px;color:${color}">${status}</td>
      </tr>`;
    });
    html += '</table>';
    container.innerHTML = html;
    btn.disabled = validCount === 0;
    if (validCount === 0) document.getElementById('spawn-log').innerHTML = '<span class="dim">No valid QIDs available to spawn</span>';
  }

  toggleAllSpawn() {
    const checked = document.getElementById('spawn-select-all')?.checked || false;
    document.querySelectorAll('.spawn-qid-cb:not(:disabled)').forEach(cb => cb.checked = checked);
  }

  async spawnSubSpecialists() {
    const sel = document.getElementById('spawn-parent');
    const sid = parseInt(sel?.value);
    const model = document.getElementById('spawn-model')?.value?.trim();
    const qids = [...document.querySelectorAll('.spawn-qid-cb:checked')].map(cb => cb.value);
    if (!sid || !model || qids.length === 0) return;
    const btn = document.getElementById('spawn-btn');
    const logEl = document.getElementById('spawn-log');
    btn.disabled = true;
    logEl.innerHTML = '<span style="color:var(--active)">Starting spawn...</span>';
    try {
      const res = await fetch(`${this.apiBase}/specialists/${sid}/spawn`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': this.apiKey || '' },
        body: JSON.stringify({ qids, model }),
      });
      if (!res.ok) {
        logEl.innerHTML = `<span style="color:var(--error)">HTTP ${res.status}: ${res.statusText}</span>`;
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      logEl.innerHTML = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          let data;
          try { data = JSON.parse(line.slice(6)); } catch { continue; }
          if (data.type === 'progress') {
            logEl.innerHTML += `<div style="color:var(--dim)">[${data.current}/${data.total}] Validating ${this.escapeHtml(String(data.qid || ''))}...</div>`;
          } else if (data.type === 'done') {
            logEl.innerHTML += `<div style="color:var(--active)">✓ ${this.escapeHtml(String(data.domain || ''))} created</div>`;
          } else if (data.type === 'error') {
            logEl.innerHTML += `<div style="color:var(--error)">✗ ${this.escapeHtml(String(data.qid || ''))}: ${this.escapeHtml(String(data.error || ''))}</div>`;
          }
        }
        logEl.scrollTop = logEl.scrollHeight;
      }
      const finalLine = buffer ? buffer.replace('data:', '').trim() : '';
      if (finalLine) {
        try {
          const fin = JSON.parse(finalLine);
          if (fin.type === 'complete') logEl.innerHTML += '<div style="color:var(--info);font-weight:600">✓ Spawn complete</div>';
        } catch (_) {}
      }
      logEl.scrollTop = logEl.scrollHeight;
      this.renderSpecialists();
    } catch (e) {
      logEl.innerHTML += `<div style="color:var(--error)">Error: ${e.message}</div>`;
    } finally {
      btn.disabled = false;
    }
  }

  filterSpecialists() {
    const search = (document.getElementById('spec-search')?.value || '').toLowerCase();
    const sort = document.getElementById('spec-sort')?.value || 'domain-asc';
    let list = [...(this.allSpecialistsData || [])];

    if (search) {
      list = list.filter(s => s.domain.toLowerCase().includes(search) || s.model.toLowerCase().includes(search));
    }

    const order = { ACTIVE: 0, IDLE: 1, COMPLETED: 2, ERROR: 3, STOPPED: 4 };
    const sortMap = {
      'domain-asc': (a, b) => a.domain.localeCompare(b.domain),
      'domain-desc': (a, b) => b.domain.localeCompare(a.domain),
      'pkg-asc': (a, b) => (a.packages_absorbed || 0) - (b.packages_absorbed || 0),
      'pkg-desc': (a, b) => (b.packages_absorbed || 0) - (a.packages_absorbed || 0),
      'ema-asc': (a, b) => (a.ema_score || 0) - (b.ema_score || 0),
      'ema-desc': (a, b) => (b.ema_score || 0) - (a.ema_score || 0),
      'status': (a, b) => (order[a.status] || 99) - (order[b.status] || 99),
      'status-desc': (a, b) => (order[b.status] || 99) - (order[a.status] || 99),
      'model': (a, b) => a.model.localeCompare(b.model),
    };
    list.sort(sortMap[sort] || sortMap['domain-asc']);

    const badgeMap = { ACTIVE: 'badge-active', IDLE: 'badge-idle', COMPLETED: 'badge-done', ERROR: 'badge-error', STOPPED: 'badge-idle' };
    const colorMap = { ACTIVE: '#FF6B6B', IDLE: '#4ECDC4', COMPLETED: '#4ECDC4', ERROR: '#C44536', STOPPED: '#6B7A8A' };

    const allRoots = list.filter(s => !s.parent_id);
    const childMap = {};
    list.filter(s => s.parent_id).forEach(c => { if (!childMap[c.parent_id]) childMap[c.parent_id] = []; childMap[c.parent_id].push(c); });

    // Only show specialists that have children (sub-specialists)
    const roots = allRoots.filter(r => (childMap[r.id] || []).length > 0);
    let html = '<div class="spec-grid-3">';
    roots.forEach(r => {
      const bc = colorMap[r.status] || '#6B7A8A';
      const tier_class = this.tierBorder(r.tier);
      const ticon = this.tierIcon(r.tier);
      const base_class = `spec-card spec-card-${r.status === 'ACTIVE' ? 'active' : r.status === 'ERROR' ? 'error' : 'idle'}`;
      const card_class = tier_class ? `${base_class} ${tier_class}` : base_class;
      html += `<div class="${card_class}">
        <div class="spec-card-inner"><span class="spec-name">${r.domain} ${ticon}</span><span class="spec-badge ${badgeMap[r.status] || 'badge-idle'}" style="background:${bc}22;color:${bc}">${r.status}</span></div>
        <div class="spec-meta">📦 ${r.packages_absorbed} · 📈 ${r.ema_score?.toFixed(3)} · 🎯 ${r.model}</div>`;
      (childMap[r.id] || []).forEach(c => {
        html += `<div class="spec-meta" style="margin-top:2px;padding-top:2px;border-top:1px dashed var(--border)">
          └─ ${c.domain} · 📦${c.packages_absorbed} · 📈${c.ema_score?.toFixed(2)} · 🎯${c.model}
          <span class="spec-badge ${badgeMap[c.status] || 'badge-idle'}" style="background:${colorMap[c.status]}22;color:${colorMap[c.status]};font-size:9px;padding:0 4px;margin-left:4px">${c.status}</span>
        </div>`;
      });
      html += `</div>`;
    });
    html += '</div>';

    if (roots.length === 0) html = '<div class="card" style="color:var(--dim)">No specialists found</div>';
    document.getElementById('spec-table').innerHTML = html;
  }

  // ── CERTIFIED ───────────────────────────────────────────────────────────
  async renderCertified() {
    const el = document.getElementById('tab-certified');
    const specData = await this.fetchJSON(`${this.apiBase}/specialists`);
    const specialists = specData?.specialists || [];
    const certified = specialists.filter(s => s.is_reliable && !s.parent_id);

    if (certified.length === 0) {
      el.innerHTML = `<div class="section-title"><h2>🏆 Certified Experts</h2></div>
        <div class="card" style="text-align:center;padding:40px;color:var(--dim)">
          <div style="font-size:48px;margin-bottom:12px">🏆</div>
          <div style="font-size:18px;font-weight:600">No certified experts yet</div>
          <div style="font-size:13px;margin-top:6px">Specialists must reach Silver tier or higher to appear here</div>
        </div>`;
      return;
    }

    let html = `<div class="section-title"><h2>🏆 Certified Experts</h2></div>
      <div style="margin-bottom:10px;color:var(--dim);font-size:13px">${certified.length} reliable specialist${certified.length > 1 ? 's' : ''}</div>`;

    certified.sort((a, b) => (b.ema_score || 0) - (a.ema_score || 0));

    html += `<table class="cert-table">
      <thead><tr>
        <th>Tier</th>
        <th>Specialist</th>
        <th>Puntuación</th>
        <th>Paquetes</th>
        <th>Tasa Fallo</th>
        <th>Racha 25</th>
        <th>Modelo</th>
      </tr></thead><tbody>`;

    const tierOrder = {4: 'Legend', 3: 'Gold', 2: 'Silver', 1: 'Bronze'};
    certified.forEach(s => {
      const ticon = this.tierIcon(s.tier);
      const tier_name = tierOrder[s.tier] || 'Unknown';
      const pts = s.tier === 4 ? '100.000' : `${Math.floor(s.ema_score * 100000).toLocaleString()}/100.000`;
      const racha = s.racha_25 != null ? (s.racha_25 * 100).toFixed(1) + '%' : '-';
      const fail_rate = s.fail_rate != null ? (s.fail_rate * 100).toFixed(2) + '%' : '-';
      html += `<tr class="cert-row-${tier_name.toLowerCase()}">
        <td class="cert-tier">${ticon} <span class="tier-label-${tier_name.toLowerCase()}">${tier_name}</span></td>
        <td class="cert-name">${this.escapeHtml(s.domain || '')}</td>
        <td class="cert-pts">${pts}</td>
        <td>${s.packages_absorbed?.toLocaleString() || '-'}</td>
        <td class="${parseFloat(fail_rate) < 5 ? 'cert-good' : 'cert-bad'}">${fail_rate}</td>
        <td class="${parseFloat(racha) >= 90 ? 'cert-good' : 'cert-bad'}">${racha}</td>
        <td class="cert-model">${this.escapeHtml(s.model || '-')}</td>
      </tr>`;
    });

    html += `</tbody></table>`;

    // Summary stats
    const legendCount = certified.filter(s => s.tier === 4).length;
    const goldCount = certified.filter(s => s.tier === 3).length;
    const silverCount = certified.filter(s => s.tier === 2).length;
    const bronzeCount = certified.filter(s => s.tier === 1).length;
    html += `<div class="cert-summary">
      <div class="cert-summary-item"><span class="tier-label-legend">👑 Legend</span> ${legendCount}</div>
      <div class="cert-summary-item"><span class="tier-label-gold">⭐⭐ Gold</span> ${goldCount}</div>
      <div class="cert-summary-item"><span class="tier-label-silver">⭐ Silver</span> ${silverCount}</div>
      <div class="cert-summary-item"><span class="tier-label-bronze">◆ Bronze</span> ${bronzeCount}</div>
    </div>`;

    el.innerHTML = html;

    this._highlightRowIfNeeded(el);
  }

  _highlightRowIfNeeded(el) {
    const domain = this._highlightDomain;
    if (!domain) return;
    this._highlightDomain = null;
    const rows = el.querySelectorAll('.cert-table tbody tr');
    for (const row of rows) {
      const nameCell = row.querySelector('.cert-name');
      if (nameCell && nameCell.textContent.trim() === domain) {
        row.scrollIntoView({ behavior: 'smooth', block: 'center' });
        row.style.transition = 'background 0.8s ease, box-shadow 0.8s ease';
        row.style.background = 'rgba(218,165,32,0.25)';
        row.style.boxShadow = '0 0 16px rgba(218,165,32,0.5)';
        setTimeout(() => {
          row.style.background = '';
          row.style.boxShadow = '';
        }, 3000);
        break;
      }
    }
  }

  // ── FLEET ───────────────────────────────────────────────────────────────
  async renderFleet() {
    const el = document.getElementById('tab-fleet');
    const [specData, health, ollamaData] = await Promise.all([
      this.fetchJSON(`${this.apiBase}/specialists`),
      this.fetchJSON(`${this.apiBase}/health`),
      this.fetchJSON(`${this.apiBase}/ollama/models`),
    ]);
    const specialists = specData?.specialists || [];
    const assignedModels = [...new Set(specialists.map(s => s.model))];
    const availableModels = ollamaData?.models || [];
    const missingModels = assignedModels.filter(m => !availableModels.some(a => a.startsWith(m)));

    let html = `
      <div class="section-title"><h2>⚙️ Configuration</h2></div>
      <div class="grid-2">
        <div class="card">
          <h3>Available Models (Ollama)</h3>
          <pre style="max-height:200px;overflow-y:auto">${availableModels.join('\n') || 'Ollama offline'}</pre>
        </div>
        <div class="card">
          <h3>Missing Models</h3>
          ${missingModels.length ? missingModels.map(m =>
            `<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;border-bottom:1px solid var(--border)">
              <code>${this.escapeHtml(m)}</code>
              <button data-model="${this.escapeHtml(m)}" onclick="app.pullModel(this.dataset.model)" class="primary" style="font-size:11px;padding:3px 10px">📥 Pull</button>
            </div>`
          ).join('') : '<div style="color:var(--inactive);font-size:13px">All models present</div>'}
          <div id="fleet-pull-msg" style="margin-top:6px;font-size:12px"></div>
        </div>
      </div>
      <div class="grid-2" style="margin-top:10px">
        <div class="card">
          <h3>Assigned Models</h3>
          <pre>${assignedModels.join('\n') || 'None'}</pre>
        </div>
        <div class="card">
          <h3>Update Specialist Model</h3>
          <div style="margin-bottom:8px">
            <label style="font-size:12px;color:var(--dim)">Specialist</label>
            <select id="fleet-spec" onchange="app.onFleetSpecChange()">
              ${specialists.filter(s => !s.parent_id).map(s => `<option value="${this.escapeHtml(s.domain)}">${this.escapeHtml(s.domain)}</option>`).join('')}
            </select>
          </div>
          <div style="margin-bottom:8px">
            <label style="font-size:12px;color:var(--dim)">Current Model: <code id="fleet-current-model">${specialists[0]?.model || ''}</code></label>
          </div>
          <div style="margin-bottom:8px">
            <label style="font-size:12px;color:var(--dim)">New Model</label>
            <input type="text" id="fleet-new-model" value="${specialists[0]?.model || ''}" style="width:100%">
          </div>
          <button onclick="app.updateSpecialistModel()" class="primary">Update</button>
          <div id="fleet-msg" style="margin-top:6px;font-size:12px"></div>
        </div>
        <div class="card">
          <h3>API Key (for auth-protected endpoints)</h3>
          <input type="password" id="fleet-apikey" value="${this.apiKey}" style="width:100%" placeholder="Leave empty if auth disabled">
          <button onclick="app.saveApiKey()" style="margin-top:4px" class="primary">Save</button>
          <div id="fleet-apikey-msg" style="margin-top:4px;font-size:12px"></div>
        </div>
      </div>
    `;
    el.innerHTML = html;
    this.onFleetSpecChange();
  }

  saveApiKey() {
    const val = document.getElementById('fleet-apikey')?.value || '';
    this.apiKey = val;
    localStorage.setItem('expertia-api-key', val);
    const msg = document.getElementById('fleet-apikey-msg');
    if (msg) { msg.textContent = '✓ Saved'; msg.style.color = 'var(--active)'; setTimeout(() => msg.textContent = '', 2000); }
  }

  async pullModel(model) {
    const msgEl = document.getElementById('fleet-pull-msg');
    if (!msgEl) return;
    msgEl.textContent = `⏳ Pulling ${model}...`;
    msgEl.style.color = 'var(--dim)';
    const result = await this.postJSON(`${this.apiBase}/ollama/pull`, { model });
    if (result.error) {
      msgEl.textContent = `❌ ${result.error}`;
      msgEl.style.color = 'var(--error)';
    } else {
      msgEl.textContent = `✅ Pulled ${model}`;
      msgEl.style.color = 'var(--inactive)';
      setTimeout(() => this.renderFleet(), 3000);
    }
  }

  onFleetSpecChange() {
    const sel = document.getElementById('fleet-spec');
    const domain = sel?.value;
    if (!domain) return;
    const spec = (this.allSpecialistsData || []).find(s => s.domain === domain);
    if (spec) {
      document.getElementById('fleet-current-model').textContent = spec.model;
      document.getElementById('fleet-new-model').value = spec.model;
    }
  }

  async updateSpecialistModel() {
    const domain = document.getElementById('fleet-spec')?.value;
    const newModel = document.getElementById('fleet-new-model')?.value;
    const msgEl = document.getElementById('fleet-msg');
    if (!domain || !newModel) { msgEl.textContent = 'Fill all fields'; return; }
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (this.apiKey) headers['X-API-Key'] = this.apiKey;
      const res = await fetch(`${this.apiBase}/specialists`, {
        method: 'PATCH',
        headers,
        body: JSON.stringify({ domain, model: newModel }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      msgEl.textContent = `✅ Updated ${domain} → ${newModel}`;
      msgEl.style.color = 'var(--inactive)';
    } catch (e) {
      msgEl.textContent = `❌ ${e.message}`;
      msgEl.style.color = 'var(--error)';
    }
  }

  async loadFleetLogs() {
    const level = document.getElementById('fleet-log-level')?.value || 'INFO,WARNING,ERROR,CRITICAL';
    const limit = document.getElementById('fleet-log-limit')?.value || 100;
    const data = await this.fetchJSON(`${this.apiBase}/activity-log?limit=${limit}&levels=${level}`);
    const logs = data?.logs || [];
    let html = '';
    if (logs.length) {
      logs.forEach((r, i) => { html += this.renderLogEntry(r, i === 0); });
    } else {
      html = '<div style="color:var(--dim);padding:8px">-- silence --</div>';
    }
    document.getElementById('fleet-log-container').innerHTML = html;
  }

  // ── SYNAPTIC MAP ────────────────────────────────────────────────────────
  async renderMap() {
    const el = document.getElementById('tab-map');
    const [status, specData, logs, health, emaHistory, memData, cpuData] = await Promise.all([
      this.fetchJSON(`${this.apiBase}/status`),
      this.fetchJSON(`${this.apiBase}/specialists`),
      this.fetchJSON(`${this.apiBase}/activity-log?limit=20`),
      this.fetchJSON(`${this.apiBase}/health`),
      this.fetchJSON(`${this.apiBase}/activity-log?levels=ERROR,CRITICAL`),
      this.fetchJSON(`${this.apiBase}/system/memory`),
      this.fetchJSON(`${this.apiBase}/system/cpu`),
    ]);
    const specialists = specData?.specialists || [];
    const activeCount = specialists.filter(sp => sp.status === 'ACTIVE').length;
    const incidentCount = health?.incident_count || 0;

    // Fetch EMA history
    const emaData = await this.fetchJSON(`${this.apiBase}/activity-log?limit=500`);

    // Track memory history
    if (memData && !memData.error) {
      if (this.memoryHistory.length === 0 || this.memoryHistory[this.memoryHistory.length - 1].percent !== memData.percent) {
        this.memoryHistory.push({ percent: memData.percent, timestamp: Date.now() });
        if (this.memoryHistory.length > 60) this.memoryHistory.shift();
      }
    }

    let html = `
      <div class="card-row" style="justify-content:center;gap:16px">
        <div id="chart-memory-gauge" style="flex:0 0 auto"></div>
        <div id="chart-cpu-gauge" style="flex:0 0 auto"></div>
      </div>
      <div class="chart-container-full" id="chart-waves"></div>
      <div class="grid-2">
        <div class="chart-container" id="chart-ema"></div>
        <div class="chart-container" id="chart-packages"></div>
      </div>
      <div class="grid-2">
        <div class="chart-container" id="chart-knowledge"></div>
        <div class="chart-container-sm" id="chart-ema-history"></div>
      </div>
    `;

    // Branch events
    const branchLogs = (logs?.logs || []).filter(r =>
      String(r.message).includes('Germinado') || String(r.message).includes('SPAWNED')
    );
    if (branchLogs.length) {
      html += `<div class="card"><div class="section-title"><h3>🌿 Branch Genesis (${branchLogs.length} events)</h3></div>`;
      branchLogs.forEach(r => {
        html += `<div class="log-entry"><span class="log-ts">${this.escapeHtml(this.utcToLocal(r.timestamp))}</span><span class="log-icon">🌱</span><span class="log-msg">${this.escapeHtml(r.message)}</span></div>`;
      });
      html += `</div>`;
    }

    el.innerHTML = html;

    // Render charts
    setTimeout(() => {
      if (memData && !memData.error) {
        makeMemoryGauge(memData, 'chart-memory-gauge');
        makeMemoryHistoryChart(this.memoryHistory, 'chart-memory-history');
      }
      if (cpuData && !cpuData.error) {
        makeCpuGauge(cpuData, 'chart-cpu-gauge');
      }
      makeWavesChart(emaData?.logs || [], 'chart-waves');
      makeSpecialistChart(specialists, 'chart-ema');
      makePackagesChart(specialists, 'chart-packages');
      this.renderKnowledgeChart();
      const emaRecords = emaData?.logs?.filter(r => String(r.message).includes('EMA')) || [];
      if (emaRecords.length) {
        const emaHistory = emaRecords.map(r => ({
          domain: 'system',
          ema_score: parseFloat(String(r.message).match(/[\d.]+/)?.[0] || 0),
          created_at: r.timestamp,
        }));
        makeEMALine(emaHistory, 'chart-ema-history');
      }
    }, 50);
  }

  async renderKnowledgeChart() {
    const stats = await this.fetchJSON(`${this.apiBase}/knowledge-stats`);
    makeKnowledgeChart(stats, 'chart-knowledge');
  }

  renderErrorsChart(logs) {
    const modelCount = {};
    logs.forEach(r => {
      const msg = String(r.message);
      const m = (this.allSpecialistsData || []).find(s => msg.includes(s.model));
      const key = m ? m.model : 'other';
      modelCount[key] = (modelCount[key] || 0) + 1;
    });
    const data = Object.entries(modelCount).map(([model, count]) => ({ model, count }));
    makeErrorsChart(data, 'chart-incidents-errors');
  }

  // ── SUPER-EXPERTS ────────────────────────────────────────────────────────
  async renderSuperExperts() {
    const el = document.getElementById('tab-super-experts');
    const data = await this.fetchJSON(`${this.apiBase}/super-experts`);
    const list = data?.super_experts || [];
    let html = `
      <div class="section-title"><h2>🏛️ Super-Expert Councils</h2></div>
      <div style="font-size:13px;color:var(--dim);margin-bottom:12px">
        Cross-domain councils that combine multiple specialists with weighted expertise.
      </div>
    `;
    if (list.length) {
      html += `<div class="se-grid-2">`;
      list.forEach(se => {
        html += `<div class="se-expander">
          <div class="se-header" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none'">
            <span>🏛️ ${this.escapeHtml(se.domain || '')}</span>
            <span style="font-size:11px;color:var(--dim);font-weight:400">${se.member_count} members · 📈 ${se.weighted_ema != null ? se.weighted_ema.toFixed(3) : '—'} · 📦 ${se.total_packages?.toLocaleString()}</span>
          </div>
          <div class="se-body" style="display:none">
            <div style="font-size:12px;color:var(--dim);margin-bottom:6px">${this.escapeHtml(se.description || '')}</div>`;
        if (se.members && se.members.length) {
          html += `<table><tr><th>Specialist</th><th>Weight</th><th>EMA</th><th>Packages</th><th>Bar</th></tr>`;
          se.members.forEach(m => {
            const pct = (m.weight * 100).toFixed(0);
            html += `<tr><td style="font-weight:600">${this.escapeHtml(m.domain || '')}</td><td>${pct}%</td><td>${m.ema_score != null ? m.ema_score.toFixed(3) : '—'}</td><td>${m.packages_absorbed}</td><td><div style="height:8px;width:${Math.max(2, pct)}px;background:var(--active);border-radius:2px;display:inline-block"></div></td></tr>`;
          });
          html += `</table>`;
        } else {
          html += `<div style="color:var(--dim)">No members</div>`;
        }
        html += `</div></div>`;
      });
      html += `</div>`;
    } else {
      html += '<div class="card" style="color:var(--dim)">🏛️ No super-experts defined yet. Run the pipeline to initialize them.</div>';
    }
    el.innerHTML = html;
  }

  // ── INCIDENTS ────────────────────────────────────────────────────────────
  async renderIncidents() {
    const el = document.getElementById('tab-incidents');
    const [data, specData] = await Promise.all([
      this.fetchJSON(`${this.apiBase}/activity-log?limit=10&levels=ERROR,CRITICAL`),
      this.fetchJSON(`${this.apiBase}/specialists`),
    ]);
    const logs = data?.logs || [];
    this.allSpecialistsData = specData?.specialists || [];
    const totalIncidents = logs.length;

    let html = `
      <div class="section-title"><h2>🔥 Incidents (${totalIncidents})</h2></div>
      <div class="chart-container-sm" id="chart-incidents-errors"></div>
    `;

    if (logs.length) {
      // Latest incident
      html += `<div class="incident-latest">${this.renderLogEntry(logs[0], true)}</div>`;

      // Remaining incidents (hidden by default)
      if (logs.length > 1) {
        html += `<div class="incident-more" id="incident-more" style="display:none">`;
        for (let i = 1; i < logs.length; i++) {
          html += this.renderLogEntry(logs[i], false);
        }
        html += `</div>`;
        html += `<button class="incident-toggle" id="incident-toggle" onclick="app.toggleIncidents()">Show ${logs.length - 1} more incidents</button>`;
      }
    } else {
      html += '<div class="card" style="color:var(--dim)">No incidents — the library is at peace</div>';
    }

    el.innerHTML = html;

    // Render errors chart
    setTimeout(() => {
      const errLogs = logs;
      const modelCount = {};
      errLogs.forEach(r => {
        const msg = String(r.message);
        const m = this.allSpecialistsData.find(s => msg.includes(s.model));
        const key = m ? m.model : 'other';
        modelCount[key] = (modelCount[key] || 0) + 1;
      });
      const chartData = Object.entries(modelCount).map(([model, count]) => ({ model, count }));
      makeErrorsChart(chartData, 'chart-incidents-errors');
    }, 50);
  }

  toggleIncidents() {
    const more = document.getElementById('incident-more');
    const btn = document.getElementById('incident-toggle');
    if (!more || !btn) return;
    const hidden = more.style.display === 'none';
    more.style.display = hidden ? 'block' : 'none';
    btn.textContent = hidden ? 'Hide' : `Show ${more.children.length} more incidents`;
  }

  // ── WIKIDATA ───────────────────────────────────────────────────────────
  async renderWikidata() {
    const el = document.getElementById('tab-wikidata');
    const status = await this.fetchJSON(`${this.apiBase}/wikidata/status`);

    if (!status) {
      el.innerHTML = '<div class="card">Error connecting to API</div>';
      return;
    }

    const pending = status.total_pendientes || 0;
    const dlDays = status.dias_sin_descargar;
    const feedDays = status.dias_pendientes_alimentar;
    const dlRunning = status.download_running || false;
    const running = status.download_running ? '🟢 Downloading...' : '⏹ Idle';

    const dlDisplay = dlDays !== null && dlDays !== undefined
      ? `${dlDays.toFixed(1)} days` : '— never downloaded';
    const feedDisplay = feedDays !== null && feedDays !== undefined
      ? `${feedDays.toFixed(1)} days` : '—';

    const pendingByDomain = status.pendientes_por_dominio || {};
    const domainEntries = Object.entries(pendingByDomain).sort((a, b) => b[1] - a[1]);
    const maxP = Math.max(...domainEntries.map(e => e[1]), 1);

    let domainBars = '';
    for (const [domain, count] of domainEntries) {
      const pct = (count / maxP * 100).toFixed(0);
      domainBars += `
        <div class="wd-domain-row">
          <span class="wd-domain-name">${this.escapeHtml(domain)}</span>
          <div class="wd-bar-wrap">
            <div class="wd-bar" style="width:${pct}%"></div>
          </div>
          <span class="wd-domain-count">${count}</span>
        </div>`;
    }
    if (!domainBars) {
      domainBars = '<div style="color:var(--dim);padding:8px">All packages absorbed — nothing pending</div>';
    }

    const lastDl = status.ultima_descarga ? this.utcToLocal(status.ultima_descarga) : '—';
    const lastFeed = status.ultima_alimentacion ? this.utcToLocal(status.ultima_alimentacion) : '—';

    let progressHtml = '';
    if (dlRunning && status.current_domain) {
      progressHtml = `
        <div class="card" style="text-align:center;padding:12px;background:#1a3a2a;border-color:#2ecc71">
          <div style="font-size:13px;color:#2ecc71">⬇ Descargando: <strong>${this.escapeHtml(status.current_domain)}</strong></div>
          <div style="font-size:24px;font-weight:700;color:#fff;margin:4px 0">${status.packages_downloaded || 0}</div>
          <div style="font-size:12px;color:var(--dim)">paquetes descargados hasta ahora</div>
        </div>`;
    } else if (dlRunning) {
      progressHtml = `
        <div class="card" style="text-align:center;padding:12px;background:#1a3a2a;border-color:#2ecc71">
          <div style="font-size:13px;color:#2ecc71">⬇ Descargando...</div>
          <div style="font-size:24px;font-weight:700;color:#fff;margin:4px 0">${status.packages_downloaded || 0}</div>
          <div style="font-size:12px;color:var(--dim)">paquetes descargados hasta ahora</div>
        </div>`;
    }

    el.innerHTML = `
      <div class="header-bar">
        <div class="header-cell">
          <div class="header-label">Last Download</div>
          <div class="header-value sm">${this.escapeHtml(lastDl)}</div>
        </div>
        <div class="header-cell">
          <div class="header-label">Last Feed</div>
          <div class="header-value sm">${this.escapeHtml(lastFeed)}</div>
        </div>
        <div class="header-cell">
          <div class="header-label">Process</div>
          <div class="header-value sm">${running}</div>
        </div>
      </div>

      ${progressHtml}

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:16px 0">
        <div class="card" style="text-align:center;padding:24px">
          <div style="font-size:36px;font-weight:700;color:${dlDays !== null && dlDays > 2 ? '#FF6B6B' : '#4ECDC4'}">${dlDisplay}</div>
          <div style="color:var(--dim);margin-top:8px">Días sin descargar</div>
          <div style="font-size:12px;color:var(--dim)">Última: ${this.escapeHtml(lastDl)}</div>
        </div>
        <div class="card" style="text-align:center;padding:24px">
          <div style="font-size:36px;font-weight:700;color:${pending > 0 ? '#FFA500' : '#4ECDC4'}">${pending > 0 ? feedDisplay : '0'}</div>
          <div style="color:var(--dim);margin-top:8px">Días pendientes de alimentar</div>
          <div style="font-size:12px;color:var(--dim)">${pending} packages sin absorber</div>
        </div>
      </div>

      <div style="display:flex;gap:12px;margin:12px 0">
        <button class="wd-btn" onclick="app.wikidataDownload()" ${dlRunning ? 'disabled' : ''}>
          📥 Descargar ahora
        </button>
        <button class="wd-btn" onclick="app.wikidataFeed()" ${dlRunning ? 'disabled' : ''}>
          🧠 Alimentar ahora
        </button>
        <button class="wd-btn wd-btn-stop" onclick="app.wikidataStop()" ${!dlRunning ? 'disabled' : ''}>
          ⏹ Detener
        </button>
      </div>

      <div class="section-title" style="margin-top:20px"><h2>Paquetes pendientes por especialista</h2></div>
      <div class="card">${domainBars}</div>
    `;

    if (this._wdPollTimer) {
      clearTimeout(this._wdPollTimer);
      this._wdPollTimer = null;
    }
    if (dlRunning) {
      this._wdPollTimer = setTimeout(() => this.renderWikidata(), 3000);
    }
  }

  async wikidataDownload() {
    const btn = document.querySelector('.wd-btn:first-child');
    if (btn) { btn.textContent = '📥 Descargando...'; btn.disabled = true; }
    const r = await this.postJSON(`${this.apiBase}/wikidata/download`, {});
    if (r && r.status === 'started') {
      setTimeout(() => this.renderWikidata(), 500);
    }
  }

  async wikidataFeed() {
    const btns = document.querySelectorAll('.wd-btn');
    if (btns[1]) { btns[1].textContent = '🧠 Alimentando...'; btns[1].disabled = true; }
    const r = await this.postJSON(`${this.apiBase}/wikidata/feed`, {});
    if (r && r.status === 'started') {
      setTimeout(() => this.renderWikidata(), 500);
    }
  }

  async wikidataStop() {
    if (this._wdPollTimer) {
      clearTimeout(this._wdPollTimer);
      this._wdPollTimer = null;
    }
    const r = await this.postJSON(`${this.apiBase}/wikidata/stop`, {});
    if (r && r.status === 'stopped') {
      this.renderWikidata();
    }
  }
}

const app = new App();
