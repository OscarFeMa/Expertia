const ChartTemplates = {
  light: {
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: { color: '#2C363F', family: "'Inter','System-UI',sans-serif", size: 11 },
    xaxis: { showgrid: true, gridcolor: '#EAE5D9', showline: false, zeroline: false },
    yaxis: { showgrid: true, gridcolor: '#EAE5D9', showline: false, zeroline: false },
    hovermode: 'x unified',
    margin: { l: 12, r: 12, t: 24, b: 12 },
  },
  dark: {
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: { color: '#E8E6E3', family: "'Inter','System-UI',sans-serif", size: 11 },
    xaxis: { showgrid: true, gridcolor: '#3D424D', showline: false, zeroline: false },
    yaxis: { showgrid: true, gridcolor: '#3D424D', showline: false, zeroline: false },
    hovermode: 'x unified',
    margin: { l: 12, r: 12, t: 24, b: 12 },
  },
};

function getTheme() {
  return document.documentElement.getAttribute('data-theme') || 'light';
}

function getTemplate() {
  return ChartTemplates[getTheme()] || ChartTemplates.light;
}

function makeSpecialistChart(specialists, containerId) {
  const el = document.getElementById(containerId);
  if (!el || !specialists.length) return;
  const roots = specialists.filter(s => !s.parent_id);
  const n = roots.length;
  const h = n > 12 ? Math.max(300, n * 28) : 300;
  el.style.minHeight = h + 'px';
  const data = [{
    type: 'bar',
    x: roots.map(s => s.domain),
    y: roots.map(s => s.ema_score),
    marker: {
      color: roots.map(s => s.status === 'ACTIVE' ? '#FF6B6B' : '#4ECDC4'),
      line: { width: 0 },
    },
    hovertemplate: '<b>%{x}</b><br>EMA: %{y:.3f}<br>Packages: %{customdata}<extra></extra>',
    customdata: roots.map(s => s.packages_absorbed),
  }];
  const layout = Object.assign({}, getTemplate(), {
    title: 'EMA Scores by Domain',
    yaxis: Object.assign({}, getTemplate().yaxis, { title: 'EMA', range: [0, 1] }),
    xaxis: Object.assign({}, getTemplate().xaxis, { tickangle: n > 8 ? -45 : -30, automargin: true }),
    bargap: 0.55,
    showlegend: false,
    height: h,
  });
  Plotly.newPlot(el, data, layout, { responsive: true, displayModeBar: false });
}

function makeKnowledgeChart(stats, containerId) {
  const el = document.getElementById(containerId);
  if (!el || !stats || !stats.total_packages) return;
  const labels = stats.by_domain.map(d => d.domain);
  const values = stats.by_domain.map(d => d.cnt);
  const n = labels.length;
  const data = [{
    type: 'pie',
    labels,
    values,
    hole: 0.4,
    marker: {
      colors: ['#FF6B6B', '#4ECDC4', '#E8B730', '#00b8d4', '#C44536', '#85D4B0', '#B8D89A'],
    },
    textinfo: n > 6 ? 'percent' : 'label+percent',
    textfont: { size: 10 },
    insidetextorientation: 'auto',
    automargin: true,
    hovertemplate: '<b>%{label}</b><br>%{value} packages (%{percent})<extra></extra>',
  }];
  const layout = Object.assign({}, getTemplate(), {
    title: 'Knowledge Packages by Domain',
    showlegend: n > 6,
    legend: n > 6 ? { font: { size: 9 }, orientation: 'v', y: 0.5 } : undefined,
    margin: { l: 4, r: 4, t: 40, b: 4 },
  });
  Plotly.newPlot(el, data, layout, { responsive: true, displayModeBar: false });
}

function makeEMALine(historyData, containerId) {
  const el = document.getElementById(containerId);
  if (!el || !historyData.length) return;
  const domains = [...new Set(historyData.map(d => d.domain))];
  const domainColors = {};
  const palette = ['#FF6B6B', '#4ECDC4', '#E8B730', '#00b8d4', '#C44536', '#85D4B0', '#B8D89A', '#6B7A8A'];
  domains.forEach((d, i) => { domainColors[d] = palette[i % palette.length]; });
  const traces = domains.map(domain => {
    const pts = historyData.filter(d => d.domain === domain).sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
    return {
      type: 'scatter',
      mode: 'lines+markers',
      name: domain,
      x: pts.map(p => p.created_at),
      y: pts.map(p => p.ema_score),
      line: { width: 1.8, color: domainColors[domain] },
      marker: { size: 4, color: domainColors[domain] },
    };
  });
  const layout = Object.assign({}, getTemplate(), {
    title: 'EMA per Domain Over Time',
    yaxis: Object.assign({}, getTemplate().yaxis, { range: [0, 1] }),
    hovermode: 'closest',
    showlegend: true,
    legend: { font: { size: 10 } },
  });
  Plotly.newPlot(el, traces, layout, { responsive: true, displayModeBar: false });
}

function makePackagesChart(specialists, containerId) {
  const el = document.getElementById(containerId);
  if (!el || !specialists.length) return;
  const roots = specialists.filter(s => !s.parent_id);
  const n = roots.length;
  const h = n > 12 ? Math.max(300, n * 28) : 300;
  el.style.minHeight = h + 'px';
  const data = [{
    type: 'bar',
    x: roots.map(s => s.domain),
    y: roots.map(s => s.packages_absorbed),
    marker: {
      color: roots.map(s => s.status === 'ACTIVE' ? '#FF6B6B' : '#4ECDC4'),
      line: { width: 0 },
    },
    hovertemplate: '<b>%{x}</b><br>Packages: %{y}<extra></extra>',
  }];
  const layout = Object.assign({}, getTemplate(), {
    title: 'Packages by Specialist',
    xaxis: Object.assign({}, getTemplate().xaxis, { tickangle: n > 8 ? -45 : -30, automargin: true }),
    bargap: 0.6,
    showlegend: false,
    height: h,
  });
  Plotly.newPlot(el, data, layout, { responsive: true, displayModeBar: false });
}

function makeWavesChart(logEntries, containerId) {
  const el = document.getElementById(containerId);
  if (!el || !logEntries || !logEntries.length) return;
  const bins = {};
  logEntries.forEach(r => {
    const msg = String(r.message || '');
    const level = String(r.level || '');
    const minute = (r.timestamp || '').slice(0, 16);
    if (!minute) return;
    if (!bins[minute]) bins[minute] = { web_search: 0, llm_query: 0, package_saved: 0, spawn: 0, error: 0 };
    if (msg.includes('Buscando')) bins[minute].web_search++;
    else if (msg.includes('Destilando')) bins[minute].llm_query++;
    else if (msg.includes('Package guardado')) bins[minute].package_saved++;
    else if (msg.includes('Germinado') || msg.includes('SPAWNED')) bins[minute].spawn++;
    if (level === 'ERROR' || level === 'CRITICAL') bins[minute].error++;
  });
  const minutes = Object.keys(bins).sort();
  if (!minutes.length) return;
  const categories = [
    { key: 'llm_query', label: 'LLM Queries', color: 'rgba(78, 205, 196, 0.85)' },
    { key: 'web_search', label: 'Web Searches', color: 'rgba(232, 183, 48, 0.75)' },
    { key: 'package_saved', label: 'Packages Saved', color: 'rgba(0, 184, 212, 0.7)' },
    { key: 'spawn', label: 'Spawning', color: 'rgba(133, 212, 176, 0.7)' },
    { key: 'error', label: 'Errors', color: 'rgba(196, 69, 54, 0.7)' },
  ];
  const traces = categories.map(cat => ({
    type: 'scatter', mode: 'none', name: cat.label,
    x: minutes, y: minutes.map(m => bins[m][cat.key]),
    stackgroup: 'one', fillcolor: cat.color, line: { width: 0 },
    hovertemplate: '%{x}<br>' + cat.label + ': %{y}<extra></extra>',
  }));
  const layout = Object.assign({}, getTemplate(), {
    title: '\u{1F30A} Activity Waves (Real-time)',
    yaxis: Object.assign({}, getTemplate().yaxis, { title: 'Events / min' }),
    xaxis: Object.assign({}, getTemplate().xaxis, { title: 'Time' }),
    hovermode: 'x unified', showlegend: true,
    legend: { font: { size: 10 }, orientation: 'h', y: -0.25 },
    height: 220,
    margin: { l: 12, r: 12, t: 32, b: 48 },
  });
  Plotly.newPlot(el, traces, layout, { responsive: true, displayModeBar: false });
}

function makeErrorsChart(errors, containerId) {
  const el = document.getElementById(containerId);
  if (!el || !errors.length) return;
  const data = [{
    type: 'bar',
    x: errors.map(e => e.model),
    y: errors.map(e => e.count),
    marker: {
      color: '#C44536',
      line: { width: 0 },
    },
    hovertemplate: '<b>%{x}</b><br>Errors: %{y}<extra></extra>',
  }];
  const layout = Object.assign({}, getTemplate(), {
    title: 'Errors by Model',
    bargap: 0.5,
    showlegend: false,
    xaxis: Object.assign({}, getTemplate().xaxis, { tickangle: -30 }),
  });
  Plotly.newPlot(el, data, layout, { responsive: true, displayModeBar: false });
}
