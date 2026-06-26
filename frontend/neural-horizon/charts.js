/**
 * Neural Horizon Charts
 * Lightweight chart rendering for the dashboard.
 * Only historical EMA trend chart and activity wave chart are kept.
 */

// ── Historical EMA Trend ────────────────────────────────────
function makeEMAHistoryChart(canvasId, data) {
    if (!data || data.length === 0) return;
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const { width, height } = canvas.parentElement.getBoundingClientRect();
    canvas.width = width || 600;
    canvas.height = height || 200;

    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    const fg = isDark ? '#E8EDF5' : '#1A1A2E';
    const dim = isDark ? '#6B7B8D' : '#8A9BAB';
    const grid = isDark ? 'rgba(0,212,255,0.08)' : 'rgba(0,153,204,0.1)';
    const accent = isDark ? '#00D4FF' : '#0099CC';
    const pulse = isDark ? '#FF6B9D' : '#D32F2F';

    const pad = { top: 10, bottom: 20, left: 40, right: 10 };
    const plotW = canvas.width - pad.left - pad.right;
    const plotH = canvas.height - pad.top - pad.bottom;

    // Parse timestamps -> labels
    const labels = data.map(d => {
        const t = new Date(d.created_at);
        return t.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    });
    const values = data.map(d => d.ema_score);
    const minVal = Math.min(...values);
    const maxVal = Math.max(...values);
    const range = maxVal - minVal || 0.1;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Grid lines
    ctx.strokeStyle = grid;
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
        const y = pad.top + (plotH * i / 4);
        ctx.beginPath();
        ctx.moveTo(pad.left, y);
        ctx.lineTo(canvas.width - pad.right, y);
        ctx.stroke();
        ctx.fillStyle = dim;
        ctx.font = '10px Inter, sans-serif';
        ctx.textAlign = 'right';
        const v = maxVal - (range * i / 4);
        ctx.fillText(v.toFixed(2), pad.left - 4, y + 4);
    }

    // Data line
    ctx.beginPath();
    ctx.strokeStyle = accent;
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    for (let i = 0; i < values.length; i++) {
        const x = pad.left + (i / (values.length - 1)) * plotW;
        const y = pad.top + plotH - ((values[i] - minVal) / range) * plotH;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Dot on latest
    if (values.length > 1) {
        const lx = pad.left + plotW;
        const ly = pad.top + plotH - ((values[values.length-1] - minVal) / range) * plotH;
        ctx.fillStyle = pulse;
        ctx.beginPath();
        ctx.arc(lx, ly, 3, 0, Math.PI * 2);
        ctx.fill();
    }
}

// ── Activity Wave / Packages by Time ────────────────────────
function makeActivityWaveChart(canvasId, data) {
    if (!data || data.length === 0) return;
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const { width, height } = canvas.parentElement.getBoundingClientRect();
    canvas.width = width || 600;
    canvas.height = height || 80;

    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    const accent = isDark ? '#00D4FF' : '#0099CC';
    const fillColor = isDark ? 'rgba(0,212,255,0.12)' : 'rgba(0,153,204,0.12)';

    const pad = { left: 0, right: 0, top: 4, bottom: 4 };
    const plotW = canvas.width - pad.left - pad.right;
    const plotH = canvas.height - pad.top - pad.bottom;

    const values = data.map(d => d.count || 0);
    const maxVal = Math.max(...values) || 1;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Fill area
    ctx.beginPath();
    ctx.moveTo(pad.left, pad.top + plotH);
    for (let i = 0; i < values.length; i++) {
        const x = pad.left + (i / (values.length - 1)) * plotW;
        const y = pad.top + plotH - (values[i] / maxVal) * plotH;
        ctx.lineTo(x, y);
    }
    ctx.lineTo(pad.left + plotW, pad.top + plotH);
    ctx.closePath();
    ctx.fillStyle = fillColor;
    ctx.fill();

    // Line
    ctx.beginPath();
    ctx.strokeStyle = accent;
    ctx.lineWidth = 1.5;
    ctx.lineJoin = 'round';
    for (let i = 0; i < values.length; i++) {
        const x = pad.left + (i / (values.length - 1)) * plotW;
        const y = pad.top + plotH - (values[i] / maxVal) * plotH;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    }
    ctx.stroke();
}

// ── Pie Chart for Specialist Knowledge Share ────────────────
function makeKnowledgePieChart(canvasId, data) {
    if (!data || data.length === 0) return;
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const size = Math.min(canvas.width, canvas.height) || 180;

    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    const colors = ['#00D4FF', '#FF6B9D', '#FFD700', '#00E676', '#FF8A65', '#CE93D8', '#4FC3F7', '#AED581'];

    const total = data.reduce((s, d) => s + (d.value || 0), 0) || 1;
    const cx = canvas.width / 2;
    const cy = canvas.height / 2;
    const r = size / 2 - 10;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    let angle = -Math.PI / 2;
    data.forEach((d, i) => {
        const slice = ((d.value || 0) / total) * Math.PI * 2;
        if (slice < 0.001) return;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.arc(cx, cy, r, angle, angle + slice);
        ctx.closePath();
        ctx.fillStyle = colors[i % colors.length];
        ctx.fill();
        angle += slice;
    });

    ctx.fillStyle = isDark ? '#0A0E17' : '#F0F2F5';
    ctx.beginPath();
    ctx.arc(cx, cy, r * 0.55, 0, Math.PI * 2);
    ctx.fill();
}
