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
    if (name === 'training' && !this._trainResize) {
      this._trainResize = true;
      window.addEventListener('resize', () => {
        if (this.tab !== 'training') return;
        this.drawTrainLoss();
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
  _fmtDur(s){
    if(s==null||!isFinite(s)||s<0) return '—';
    s=Math.round(s); const h=Math.floor(s/3600), m=Math.floor(s%3600/60);
    return h?`${h}h ${m}m`:(m?`${m}m ${s%60}s`:`${s}s`);
  }
  _trainRate(hist){
    const pts=(hist||[]).filter(h=>h.ts!=null);
    if(pts.length>=2){
      const a=pts[Math.max(0,pts.length-6)], b=pts[pts.length-1];
      const dt=(b.ts-a.ts)/60;
      if(dt>0.5) return {rate:(b.step-a.step)/dt, src:'historial'};
    }
    const now=Date.now();
    this._rateSamples=(this._rateSamples||[]).filter(s=>now-s.t<15*60*1000);
    const last=this._rateSamples[this._rateSamples.length-1];
    const cur=(hist&&hist.length)?hist[hist.length-1].step:null;
    if(cur!=null&&(!last||cur!==last.step)) this._rateSamples.push({t:now,step:cur});
    const s0=this._rateSamples[0], s1=this._rateSamples[this._rateSamples.length-1];
    if(s0&&s1&&(s1.t-s0.t)>120000&&(s1.step-s0.step)>0)
      return {rate:(s1.step-s0.step)/((s1.t-s0.t)/60000), src:'medido'};
    return null;
  }
  updateTrainPanel(d){
    const $=id=>document.getElementById(id);
    const ph=$('train-phase'); if(!ph) return;
    ph.textContent = d.phase || 'idle';
    const worker=$('train-worker');
    if(worker) worker.textContent = d.origen==='3070' ? '◉ RTX 3070' : (d.phase==='training'?'● local':'—');
    const st=$('train-step');
    if(st) st.textContent = d.step ? `${d.step}${d.max_steps?` / ${d.max_steps}`:''} · ep ${d.epoch??'—'}` : 'en espera';
    const hist=d.loss_history||[];
    if(hist.length){
      const lastNew=hist[hist.length-1], prev=this._trainHist||[];
      if(!prev.length || lastNew.step!==prev[prev.length-1]?.step || lastNew.loss!==prev[prev.length-1]?.loss){
        this._trainHist=hist; this._trainView=null;
      }
      this.drawTrainLoss();
    } else if(!this._trainHist?.length){ this.drawTrainLoss(); }
    let rr=this._trainRate(this._trainHist);
    let rate=rr?.rate, rateSrc=rr?.src||'';
    if(!(rate>0)&&d.steps_per_min>0&&d.elapsed_s>600){ rate=d.steps_per_min; rateSrc='worker'; }
    const pct=(d.max_steps&&d.step)?Math.min(100,d.step/d.max_steps*100):null;
    const set=(id,txt)=>{ const e=$(id); if(e) e.textContent=txt; };
    set('kpi-prog', pct!=null?pct.toFixed(1)+'%':'—');
    const pb=$('kpi-prog-bar'); if(pb) pb.style.width=(pct!=null?pct:0)+'%';
    const prog=$('train-progress'), bar=$('train-progress-bar');
    if(prog&&bar){
      if(pct!=null){ prog.style.display=''; bar.style.opacity='1'; bar.style.width=pct+'%'; }
      else if(d.phase==='training'){ prog.style.display=''; bar.style.opacity='.35'; bar.style.width='100%'; }
      else prog.style.display='none';
    }
    let eta='—', etaSub='—';
    if(d.max_steps&&d.step&&rate&&rate>0){
      const rem=(d.max_steps-d.step)/rate*60;
      eta=this._fmtDur(rem); etaSub=`${rate.toFixed(1)} pasos/min (${rateSrc}) · fin aprox.`;
    } else if(d.phase==='training'){ etaSub='calculando ritmo…'; }
    set('kpi-eta',eta); set('kpi-eta-sub',etaSub);
    const losses=this._trainHist.map(h=>h.loss);
    const lmin=losses.length?Math.min(...losses):null;
    set('kpi-loss', d.loss!=null?Number(d.loss).toFixed(4):'—');
    set('kpi-loss-sub', (losses.length>1&&lmin!=null)?`mín ${lmin.toFixed(3)} · −${(100*(losses[0]-d.loss)/losses[0]).toFixed(0)}% desde inicio`:'—');
    set('train-loss', d.loss!=null?Number(d.loss).toFixed(4):'—');
    set('kpi-rate', rate!=null?rate.toFixed(1)+'/min':'—');
    set('kpi-rate-sub', d.elapsed_s!=null?`sesión ${this._fmtDur(d.elapsed_s)}`:'—');
    const util=d.gpu_util, temp=d.gpu_temp;
    set('kpi-gpu', util!=null?Math.round(util)+'%':'—');
    const gbt=$('kpi-gpu-bar'); if(gbt) gbt.style.width=(util!=null?Math.min(100,util):0)+'%';
    let tcol='var(--text)';
    if(temp!=null&&temp>=85) tcol='var(--red,#d96a5c)'; else if(temp!=null&&temp>=75) tcol='var(--gold)';
    const gt=$('kpi-gpu-t'); if(gt){ gt.textContent=temp!=null?temp+'°C':'(sin sonda)'; gt.style.color=tcol; }
    const mu=d.gpu_mem_used, mf=d.gpu_mem_free;
    set('kpi-vram', (mu!=null)?`${(mu/1024).toFixed(1)} / ${((mu+mf)/1024).toFixed(1)} GB`:'—');
    set('kpi-pow', (d.gpu_power!=null)?`${d.gpu_power}W / ${d.gpu_power_limit??'?'}W${temp!=null&&temp>=85?' · ¡REFRIGERAR!':''}`:'—');
    set('train-lr', d.lr!=null?Number(d.lr).toExponential(1):'—');
    set('train-time', d.elapsed_s!=null?this._fmtDur(d.elapsed_s):'—');
    set('train-ds', `${(d.dataset_train||0).toLocaleString()} / ${(d.dataset_val||0).toLocaleString()}`);
    set('train-clock', d.gpu_clock!=null?Math.round(d.gpu_clock)+' MHz':'—');
    set('train-base', d.base_downloaded?'Phi-reasoning ✓':'descargando…');
    set('train-adapter', d.adapter||'r16 · seq2048');
    const ck=[...(d.checkpoints||[])].sort((a,b)=>(parseInt((a.match(/\d+/)||[0])[0],10)||0)-(parseInt((b.match(/\d+/)||[0])[0],10)||0));
    set('train-ckpts', ck.length?ck.slice(-3).join(' · '):'ninguno todavía');
    const log=$('train-log');
    if(log){
      const lines=(d.log_tail||[]).map(x=>{ if(typeof x==='string') return x; if(x&&typeof x.value==='string') return x.value; try{ return JSON.stringify(x); }catch(e){ return String(x); } }).filter(x=>x&&x.trim());
      const txt=lines.length?lines.slice(-2).join('\n'):'sin salida reciente del worker — el entreno sigue corriendo en el 3070';
      const auto=document.getElementById('train-autoscroll');
      const stick=!auto||auto.checked;
      const nearBottom=log.scrollHeight-log.scrollTop-log.clientHeight<60;
      log.textContent=txt;
      if(stick||nearBottom) log.scrollTop=log.scrollHeight;
    }
  }
  updateReports(d){
    const el=document.getElementById('reports-list'); if(!el) return;
    const reps=d.reports||[];
    if(!reps.length){ el.textContent='sin informes todavía — se generan al cierre de cada ciclo de 12h'; return; }
    el.innerHTML=reps.map((r,ix)=>{
      const s=r.summary||{};
      let when=r.ts||'';
      try{ const dt=new Date(r.ts); if(!isNaN(dt)) when=dt.toLocaleString('es-ES',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}); }catch(e){}
      const badge=r.kind==='web'?'WEB':'ENTRENO';
      const det=r.kind==='web'
        ? `ciclos ${s.ciclos??s.cycles??'—'} · q ${s.avg_quality??'—'} · ${s.new_packages!=null?('+'+s.new_packages+' pkgs'):'pkgs —'}`
        : `paso ${s.step??'—'} · loss ${s.loss_last!=null?Number(s.loss_last).toFixed(4):'—'} · ${s.phase??''}`;
      const extra=r.kind==='web'
        ? `<div>por dominio:</div><div>${(s.per_domain||[]).slice(0,18).map(p=>`${escapeHtml(p.domain)} ${p.cycles}× q${p.avg_quality}`).join(' · ')||'—'}</div><div>actividad: ${escapeHtml(JSON.stringify(s.activity||{}))}</div>`
        : `<div>checkpoints: ${escapeHtml((s.checkpoints||[]).join(', ')||'ninguno')}</div><div>dataset ${(s.dataset_train||0).toLocaleString()} / ${(s.dataset_val||0).toLocaleString()}</div>`;
      return `<details style="padding:6px 0; border-bottom:1px solid var(--border);"><summary style="cursor:pointer;"><b style="color:var(--accent)">${badge}</b> · ${when} — ${det}</summary><div style="padding:6px 0 2px 12px; color:var(--text-mute);">${extra}<div style="color:var(--text-faint)">${escapeHtml(r.file||'')}</div></div></details>`;
    }).join('');
  }
  async openReportsFolder(){
    const r=await this.fetchJSON(`${this.apiBase}/reports/open-folder`,{method:'POST'});
    if(r && r.status==='opened') this.toast('Carpeta abierta', r.path+(r.method?` (${r.method})`:''), 'info', 6000);
    else {
      const path=(r&&r.path)||'storage\\reports';
      this.toast('No se pudo abrir solo', `Ruta: ${r?.detail||path}`, 'error', 9000);
      try{ await navigator.clipboard.writeText(path); }catch(e){}
    }
  }
  drawTrainLoss(){
    const svg=document.getElementById('chart-train-loss'); if(!svg) return;
    const hist=this._trainHist||[];
    const W=600, H=240, padL=46, padR=12, padT=16, padB=24, iw=W-padL-padR, ih=H-padT-padB;
    const st=getComputedStyle(document.documentElement);
    const accent=st.getPropertyValue('--accent').trim()||'#7aa2f7';
    const border=st.getPropertyValue('--border').trim()||'#333';
    const mute=st.getPropertyValue('--text-mute').trim()||'#888';
    const NS='http://www.w3.org/2000/svg';
    const el=(t,a)=>{ const e=document.createElementNS(NS,t); for(const k in a) e.setAttribute(k,a[k]); return e; };
    svg.innerHTML='';
    if(!hist.length){
      const tx=el('text',{x:padL+6,y:30,fill:mute,'font-size':11,'font-family':'monospace'});
      tx.textContent='curva disponible tras los primeros pasos…'; svg.appendChild(tx); return;
    }
    let v=this._trainView;
    if(!v || v.i1>hist.length-1 || v.i0<0){ v=this._trainView={i0:0,i1:hist.length-1}; }
    const n=hist.length, i0=Math.max(0,v.i0), i1=Math.min(n-1,Math.max(i0+2,v.i1));
    const win=hist.slice(i0,i1+1);
    const ls=win.map(h=>h.loss), mn=Math.min(...ls), mx=Math.max(...ls), rg=(mx-mn)||1e-6;
    const X=k=>padL+(k/(win.length-1||1))*iw, Y=val=>padT+ih-((val-mn)/rg)*ih;
    for(let g=0; g<=4; g++){
      const y=padT+ih*g/4;
      svg.appendChild(el('line',{x1:padL,y1:y,x2:W-padR,y2:y,stroke:border,'stroke-width':1}));
      const t=el('text',{x:4,y:y+3,fill:mute,'font-size':9,'font-family':'monospace'});
      t.textContent=(mx-rg*g/4).toFixed(2); svg.appendChild(t);
    }
    const pts=win.map((h,k)=>`${X(k).toFixed(1)},${Y(h.loss).toFixed(1)}`).join(' ');
    svg.appendChild(el('polyline',{points:pts,fill:'none',stroke:accent,'stroke-width':2,'stroke-linejoin':'round'}));
    win.forEach((h,k)=>{
      const c=el('circle',{cx:X(k),cy:Y(h.loss),r:3,fill:accent});
      const tt=document.createElementNS(NS,'title'); tt.textContent=`paso ${h.step}: loss ${h.loss}`;
      c.appendChild(tt); svg.appendChild(c);
    });
    const t0=el('text',{x:padL,y:H-6,fill:mute,'font-size':9,'font-family':'monospace'});
    t0.textContent='paso '+win[0].step; svg.appendChild(t0);
    const t1=el('text',{x:W-64,y:H-6,fill:mute,'font-size':9,'font-family':'monospace'});
    t1.textContent='paso '+win[win.length-1].step; svg.appendChild(t1);
    const lg=document.getElementById('train-legend-range');
    if(lg) lg.textContent=`min ${mn.toFixed(3)} · max ${mx.toFixed(3)} · n=${win.length}`+(win.length<n?` (zoom ${i0+1}-${i1+1}/${n})`:'');
    if(!svg._zoomBound){
      svg._zoomBound=true;
      let dragX=null;
      svg.addEventListener('wheel',e=>{
        e.preventDefault();
        const h2=this._trainHist||[]; if(h2.length<4) return;
        const v2=this._trainView||{i0:0,i1:h2.length-1};
        const span=v2.i1-v2.i0, f=e.deltaY>0?1.25:0.8;
        const rect=svg.getBoundingClientRect();
        const frac=Math.min(1,Math.max(0,(e.clientX-rect.left-padL)/Math.max(1,rect.width-padL-padR)));
        const c=v2.i0+span*frac, ns=Math.min(span,Math.max(3,Math.round(span*f)));
        let ni0=Math.round(c-ns*frac), ni1=ni0+ns;
        if(ni0<0){ni1-=ni0;ni0=0;} if(ni1>h2.length-1){ni0-=ni1-(h2.length-1);ni1=h2.length-1;}
        this._trainView={i0:Math.max(0,ni0),i1:ni1}; this.drawTrainLoss();
      },{passive:false});
      svg.addEventListener('pointerdown',e=>{dragX=e.clientX; svg.style.cursor='grabbing'; svg.setPointerCapture(e.pointerId);});
      svg.addEventListener('pointermove',e=>{
        if(dragX==null) return;
        const h2=this._trainHist||[]; if(h2.length<4) return;
        const rect=svg.getBoundingClientRect();
        const dSteps=Math.round((dragX-e.clientX)/Math.max(1,rect.width)* (this._trainView.i1-this._trainView.i0));
        if(!dSteps) return; dragX=e.clientX;
        const v2=this._trainView, span=v2.i1-v2.i0;
        let ni0=v2.i0+dSteps, ni1=v2.i1+dSteps;
        if(ni0<0){ni1-=ni0;ni0=0;} if(ni1>h2.length-1){ni0-=ni1-(h2.length-1);ni1=h2.length-1;}
        this._trainView={i0:ni0,i1:ni1}; this.drawTrainLoss();
      });
      const end=()=>{dragX=null; svg.style.cursor='grab';};
      svg.addEventListener('pointerup',end); svg.addEventListener('pointercancel',end);
      svg.addEventListener('dblclick',()=>{this._trainView=null; this.drawTrainLoss();});
    }
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
    this._activeSpec = status?.current_specialist || overview?.current_specialist || '';
    this._pipeActive = (status?.status || overview?.status || '').toUpperCase() === 'ACTIVE';
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
    this.fetchJSON(`${this.apiBase}/reports?limit=6`).then(d => { if (d) this.updateReports(d); });

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
      const liveActive = !!(this._pipeActive && this._activeSpec && s.domain === this._activeSpec);
      const isActive = status === 'active' || status === 'mining' || status === 'absorbing' || liveActive;
      const statusLbl = liveActive ? 'activo' : status;
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
        <td><span class="status-dot ${isActive ? 'active' : status === 'error' ? 'error' : 'idle'}"></span><span class="status-label">${statusLbl}</span></td>
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
