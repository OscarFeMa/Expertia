import streamlit as st
import pandas as pd
import plotly.express as px
import subprocess
import os
import signal
import time
import re
from datetime import datetime, timedelta
import sys
sys.path.insert(0, os.path.dirname(__file__))
from database.db_manager import get_db_manager
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Synaptic Archive — Expertia", layout="wide", page_icon="🧠")

for k in ("orch_pid","orch_start_time","auto_refresh","prev_phase","last_toast_time","force_idle","auto_launched"):
    if k not in st.session_state:
        if k == "auto_refresh": st.session_state[k] = True
        elif k in ("last_toast_time",): st.session_state[k] = 0
        elif k == "force_idle": st.session_state[k] = False
        elif k == "auto_launched": st.session_state[k] = False
        else: st.session_state[k] = None

if st.session_state.auto_refresh:
    st_autorefresh(interval=5000, key="autorefresh", limit=None)

UTC_OFFSET = timedelta(hours=2)

# ── Palette ──────────────────────────────────────────────────────────────────
ARCHIVE = {
    "bg": "#E3DECE", "card": "#FFFFFF", "text": "#2C363F", "dim": "#555555",
    "border": "#D5CFBF", "shadow": "#C8C0AE",
    "active": "#FF6B6B", "inactive": "#4ECDC4", "error": "#C44536",
    "info": "#00b8d4", "amber": "#E8B730",
}

# ── Data helpers ─────────────────────────────────────────────────────────────
def utc_to_local(ts):
    if pd.isna(ts) or not str(ts).strip(): return "-"
    try:
        dt = datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S") + UTC_OFFSET
        return dt.strftime("%H:%M:%S")
    except: return str(ts)[11:19] if len(str(ts)) >= 19 else "-"

def get_connection():
    return get_db_manager()._get_connection()

def load_specialists():
    return pd.read_sql_query("SELECT id,domain,model,ema_score,packages_absorbed,status,parent_id,qid_path FROM specialist_registry ORDER BY parent_id IS NOT NULL, COALESCE(parent_id,id), domain", get_connection())

def load_pipeline_status():
    try:
        df = pd.read_sql_query("SELECT * FROM pipeline_status ORDER BY id DESC LIMIT 1", get_connection())
        return df.iloc[0].to_dict() if not df.empty else None
    except: return None

def load_activity_logs(limit=50, levels=None):
    try:
        parts, params = [], []
        if levels:
            ph = ",".join("?" for _ in levels)
            parts.append(f"level IN ({ph})"); params.extend(levels)
        where = " WHERE " + " AND ".join(parts) if parts else ""
        params.append(limit)
        return pd.read_sql_query(f"SELECT timestamp,level,message,id FROM activity_log{where} ORDER BY id DESC LIMIT ?", get_connection(), params=params)
    except: return pd.DataFrame()

def load_ema_history():
    try:
        return pd.read_sql_query("SELECT e.timestamp AS created_at, e.ema_score, s.domain FROM ema_history e JOIN specialist_registry s ON e.specialist_id = s.id ORDER BY e.timestamp", get_connection())
    except: return pd.DataFrame()

def load_ema_sparklines(domains):
    if not domains: return {}
    conn = get_connection()
    return {d: [r[0] for r in reversed(conn.execute("SELECT e.ema_score FROM ema_history e JOIN specialist_registry s ON e.specialist_id = s.id WHERE s.domain = ? ORDER BY e.timestamp DESC LIMIT 10", (d,)).fetchall())] for d in domains}

def load_specialists_tree():
    """Build sunburst/treemap hierarchical data: ids, labels, parents, values."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, domain, parent_id, packages_absorbed, ema_score FROM specialist_registry ORDER BY parent_id IS NULL DESC, domain"
    ).fetchall()
    ids, labels, parents, values, colors = [], [], [], [], []
    for r in rows:
        rid, dom, pid, pkgs, ema = r
        ids.append(str(rid))
        labels.append(dom)
        parents.append(str(int(pid)) if pid else "")
        values.append(pkgs or 1)
        colors.append(ema)
    return pd.DataFrame({"ids": ids, "labels": labels, "parents": parents, "values": values, "ema": colors})

def load_hierarchy_stats():
    """Quick stats about tree depth, branches, etc."""
    conn = get_connection()
    roots = conn.execute("SELECT COUNT(*) FROM specialist_registry WHERE parent_id IS NULL").fetchone()[0]
    children = conn.execute("SELECT COUNT(*) FROM specialist_registry WHERE parent_id IS NOT NULL").fetchone()[0]
    depths = conn.execute("SELECT qid_path FROM specialist_registry WHERE parent_id IS NOT NULL AND qid_path IS NOT NULL").fetchall()
    max_depth = max((len(d[0].split('/')) for d in depths if d[0]), default=1)
    return {"roots": roots, "children": children, "max_depth": max_depth}

def load_branch_events(limit=20):
    """Load recent spawning events from activity_log."""
    try:
        return pd.read_sql_query(
            "SELECT timestamp, message FROM activity_log WHERE message LIKE '%Germinado%' OR message LIKE '%SPAWNED%' ORDER BY id DESC LIMIT ?",
            get_connection(), params=(limit,))
    except:
        return pd.DataFrame()

def load_super_experts():
    """Load all super-experts with aggregated info."""
    try:
        return pd.read_sql_query("""
            SELECT se.id, se.domain, se.description,
                   COUNT(sem.id) AS member_count,
                   AVG(s.ema_score) AS avg_ema,
                   SUM(s.packages_absorbed * sem.weight) / SUM(sem.weight) AS weighted_ema,
                   SUM(s.packages_absorbed) AS total_packages
            FROM super_experts se
            LEFT JOIN super_expert_members sem ON sem.super_expert_id = se.id
            LEFT JOIN specialist_registry s ON s.id = sem.specialist_id
            GROUP BY se.id
            ORDER BY se.domain
        """, get_connection())
    except Exception as e:
        return pd.DataFrame()

def load_super_expert_members(se_id):
    """Load members for a specific super-expert."""
    try:
        return pd.read_sql_query("""
            SELECT s.domain, s.ema_score, s.packages_absorbed, s.status, sem.weight
            FROM super_expert_members sem
            JOIN specialist_registry s ON s.id = sem.specialist_id
            WHERE sem.super_expert_id = ?
            ORDER BY sem.weight DESC
        """, get_connection(), params=(se_id,))
    except Exception as e:
        return pd.DataFrame()

def load_blocked_branches(limit=50):
    """Load blocked branch events (blocklist label or SPARQL filtered)."""
    try:
        return pd.read_sql_query(
            "SELECT timestamp, message FROM activity_log WHERE message LIKE '%Bloqueado%' OR message LIKE '%Rama externa%' ORDER BY id DESC LIMIT ?",
            get_connection(), params=(limit,))
    except:
        return pd.DataFrame()

def load_errors_by_model():
    try:
        known = [r[0] for r in get_connection().execute("SELECT DISTINCT model FROM specialist_registry").fetchall()]
        df = pd.read_sql_query("SELECT message FROM activity_log WHERE level IN ('ERROR','CRITICAL') ORDER BY id DESC LIMIT 500", get_connection())
        models = []
        for msg in df['message']:
            matched = False
            for m in known:
                if m in str(msg): models.append(m); matched = True; break
            if not matched: models.append('other')
        return pd.DataFrame({'model':models}).groupby('model').size().reset_index(name='count').sort_values('count', ascending=False)
    except: return pd.DataFrame(columns=['model','count'])

def load_wikidata_speed():
    try:
        df = pd.read_sql_query("SELECT message FROM activity_log WHERE message LIKE '%entity%' OR message LIKE '%extract%' ORDER BY id DESC LIMIT 1000", get_connection())
        if df.empty: return None
        entities = []
        for msg in df['message']:
            m = re.search(r'(\d+)\s*entities', str(msg), re.IGNORECASE)
            if m: entities.append(int(m.group(1)))
        return max(entities) if entities else None
    except: return None

def is_pid_alive(pid):
    if pid is None: return False
    try:
        if os.name == 'nt':
            r = subprocess.run(["tasklist","/FI",f"PID eq {pid}"], capture_output=True, text=True, timeout=5)
            return str(pid) in r.stdout
        else: os.kill(pid, 0); return True
    except: return False

def get_local_models():
    try:
        r = subprocess.run(["ollama","list"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            lines = r.stdout.strip().split('\n')[1:]
            return [line.split()[0] for line in lines if line.strip()]
        return []
    except: return []

def auto_detect_orch():
    try:
        r = subprocess.run(["tasklist","/FI","IMAGENAME eq python.exe","/FO","CSV"], capture_output=True, text=True, timeout=5)
        for line in r.stdout.split('\n'):
            if 'orchestrator.py' in line:
                m = re.search(r'"(\d+)"', line)
                if m:
                    pid = int(m.group(1))
                    if pid != st.session_state.orch_pid:
                        st.session_state.orch_pid = pid
                        st.session_state.orch_start_time = st.session_state.orch_start_time or time.time()
                        st.session_state.force_idle = False
                    return pid
        return None
    except: return None

def get_specialist_state(domain):
    try:
        msg = get_connection().execute("SELECT message FROM activity_log WHERE message LIKE ? ORDER BY id DESC LIMIT 1", (f"%{domain}%",)).fetchone()
        if not msg: return 0
        m = str(msg[0])
        if "Package" in m or "package" in m or "guardado" in m: return 3
        if "Destilando" in m or "query" in m.lower(): return 2
        if "HTTP" in m or "trafilatura" in m: return 1
        if "Buscan" in m or "Search" in m or "DDGS" in m: return 0
        return -1
    except: return -1

def process_notifications(df_logs):
    if df_logs.empty: return
    l = df_logs.iloc[0]
    msg, lvl = str(l['message']), l['level']
    if ("Package guardado" in msg or lvl in ("ERROR","CRITICAL")) and time.time() - st.session_state.last_toast_time >= 30:
        domain = msg.split(">")[0].strip() if ">" in msg else "sys"
        if "Package" in msg: st.toast(f"[PKG] {domain}", icon="📚")
        else: st.toast("[ERR] pipeline", icon="🔥")
        st.session_state.last_toast_time = time.time()

# ── Narrative Humour ─────────────────────────────────────────────────────────
def narrative_humor(level, message):
    msg = str(message)[:200]
    if "403" in msg: return "El bibliotecario jefe denegó el acceso a la estantería"
    if "404" in msg: return "El libro solicitado no se encuentra en los anaqueles"
    if "500" in msg: return "Los duendes del servidor están de huelga"
    if "Package guardado" in msg: return "Un tomo más descansa en los estantes del archivo"
    if "Package saved" in msg.lower(): return "Un volumen ha sido catalogado exitosamente"
    if "timeout" in msg.lower(): return "El mensajero tardó demasiado y perdió la paciencia"
    if "connection" in msg.lower() and ("error" in msg.lower() or "fail" in msg.lower() or "refused" in msg.lower()):
        return "El cableado entre anaqueles falló — alguien tropezó con el cable"
    if "HTTP" in msg.upper() and ("error" in msg.lower() or "fail" in msg.lower()):
        return "El archivista reporta problemas técnicos con la conexión"
    if "Buscan" in msg or "Search" in msg or "DDGS" in msg: return "Hojeando el catálogo en busca de referencias..."
    if "trafilatura" in msg.lower(): return "El fotocopiador digital está extrayendo páginas"
    if "Destilando" in msg or "query" in msg.lower(): return "Las neuronas están sudando — proceso cognitivo en marcha"
    if level in ("ERROR", "CRITICAL"): return f"Incidente en la sala de lectura: {msg[:150]}"
    if level == "WARNING": return f"El bibliotecario frunce el ceño: {msg[:150]}"
    if level == "DEBUG": return f"El archivista anota en sus cuadernos: {msg[:150]}"
    return msg

# ── Rendering helpers ────────────────────────────────────────────────────────
def render_whisper_entry(row, highlight=False):
    ts = utc_to_local(row['timestamp'])
    icon = {"INFO": "📝", "WARNING": "👀", "ERROR": "🔥", "CRITICAL": "🔥", "DEBUG": "📋"}.get(row['level'], "📝")
    msg = narrative_humor(row['level'], str(row['message'])[:200])
    hl = "hl" if highlight else ""
    return f"<div class='whisper-entry {hl}'><span class='whisper-ts'>{ts}</span><span class='whisper-icon'>{icon}</span><span class='whisper-msg'>{msg}</span></div>"

def synaptic_timeline(step):
    steps = [
        ("🕵️", "Husmeando"),
        ("🖨️", "Fotocopiando"),
        ("🧠", "Sudando neuronas"),
        ("📚", "Encuadernado"),
    ]
    parts = []
    for i, (icon, label) in enumerate(steps):
        ac = "syn-on" if i <= step else ""
        parts.append(f"<span class='syn-step {ac}'>{icon} {label}</span>")
    arrows = [ "<span class='syn-arrow'>→</span>" ] * 3
    out = parts[0]
    for i in range(1, 4):
        out += arrows[i-1] + parts[i]
    return f"<div class='syn-tl'>{out}</div>"

def neural_wave_svg(values, w=60, h=20, c="#FF6B6B"):
    if not values or len(values) < 2: return ""
    mn, mx = min(values), max(values)
    rng = mx - mn or 1
    n = len(values)
    pts = []
    for i, v in enumerate(values):
        x = i * w / (n - 1)
        y = h - ((v - mn) / rng) * (h - 4) - 2
        pts.append((x, y))
    d = f"M {pts[0][0]:.1f},{pts[0][1]:.1f}"
    for i in range(1, n):
        p0, p1 = pts[i-1], pts[i]
        c1x = p0[0] + (p1[0] - p0[0]) * 0.35
        c1y = p0[1]
        c2x = p1[0] - (p1[0] - p0[0]) * 0.35
        c2y = p1[1]
        d += f" C {c1x:.1f},{c1y:.1f} {c2x:.1f},{c2y:.1f} {p1[0]:.1f},{p1[1]:.1f}"
    return f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" style="vertical-align:middle;margin-left:4px"><path d="{d}" fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'

def render_lobe_card(row, detailed, ema_values, step):
    s = row['status']; is_act = s == "ACTIVE"
    sc = "act" if is_act else ("idl" if s != "ERROR" else "err")
    badge_cls = {"ACTIVE":"s-active","IDLE":"s-idle","COMPLETED":"s-done","ERROR":"s-err","STOPPED":"s-idle"}.get(s,"s-idle")
    svg = neural_wave_svg(ema_values) if is_act and detailed else ""
    tl = synaptic_timeline(step) if is_act and detailed else ""
    ccp = " cp" if not detailed else ""
    return (f"<div class='lobe-card {sc}{ccp}'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:4px'>"
        f"<span class='name'>{row['domain']}</span>"
        f"<span class='status-badge {badge_cls}'>{s}</span></div>"
        f"<div class='meta'>P: {row['packages_absorbed']} &nbsp; E: {row['ema_score']:.3f}{svg} &nbsp; M: {row['model']}</div>"
        f"{tl}</div>")

bc_map = {"ACTIVE":"#FF6B6B","IDLE":"#4ECDC4","COMPLETED":"#4ECDC4","ERROR":"#C44536","STOPPED":"#6B7A8A"}

def _render_spec_card(r, is_child, bc_map):
    s = r['status']
    card_cls = "spec-card-active" if s=="ACTIVE" else ("spec-card-error" if s=="ERROR" else "spec-card-idle")
    bc = bc_map.get(s, "#6B7A8A")
    prefix = "└─ " if is_child else ""
    ml = "16px" if is_child else "0px"
    return (f"<div class='{card_cls}' style='margin-left:{ml}'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center'>"
        f"<span style='font-size:0.85rem; font-weight:700; color:#000;'>{prefix}{r['domain']}</span>"
        f"<span class='lib-badge' style='background:{bc}; color:#000; padding:1px 6px; border-radius:3px; font-size:0.65rem;'>{s}</span>"
        f"</div>"
        f"<div style='font-size:0.72rem; color:#333; margin-top:3px; font-weight:500;'>"
        f"📦{r['packages_absorbed']} · 📈{r['ema_score']:.2f} · 🎯{r['model']}"
        f"</div></div>")

def apply_archive_theme(fig, t="line"):
    fig.update_layout(template="plotly_white", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#2C363F", family="'Inter','System-UI',sans-serif", size=11),
        margin=dict(l=12,r=12,t=24,b=12),
        xaxis=dict(showgrid=True, gridcolor="#EAE5D9", showline=False, zeroline=False),
        yaxis=dict(showgrid=True, gridcolor="#EAE5D9", showline=False, zeroline=False),
        hovermode="x unified")
    if t == "line":
        fig.update_traces(line=dict(width=1.8), mode="lines")
        for i in range(len(fig.data)):
            if hasattr(fig.data[i], 'line') and fig.data[i].line is not None:
                fig.data[i].line.color = "#FF6B6B"
                fig.data[i].line.width = 1.8
    elif t == "bar":
        fig.update_traces(marker_line_width=0)
        fig.update_layout(bargap=0.45)
    return fig

# ── CSS ──────────────────────────────────────────────────────────────────────
def inject_archive_css():
    st.markdown(f"""
<style>
.stApp {{ background:{ARCHIVE['bg']} !important; color:#121212 !important; font-family:'Inter','System-UI',sans-serif; font-size:14px; }}
h1, h2, h3, h4, h5, h6 {{ font-family:Georgia,'Times New Roman',serif !important; color:{ARCHIVE['text']}; }}
* {{ font-family:'Inter','System-UI',sans-serif; }}
::selection {{ background:rgba(255,107,107,0.2); }}

.archive-header {{ display:flex; justify-content:space-between; align-items:stretch; background:{ARCHIVE['card']}}}
; border-bottom:1px solid {ARCHIVE['border']}; padding:8px 16px; margin-bottom:14px; }}
.archive-header .hcell {{ display:flex; flex-direction:column; justify-content:center; }}
.arc-label {{ color:{ARCHIVE['dim']}; font-size:10px; text-transform:uppercase; letter-spacing:1.2px; }}
.arc-value {{ color:{ARCHIVE['text']}; font-weight:700; font-family:Georgia,'Times New Roman',serif; font-size:18px; }}
.arc-value.sm {{ font-size:13px; font-family:'Inter',sans-serif; }}

.coral-dot {{ display:inline-block; width:9px; height:9px; border-radius:50%; background:{ARCHIVE['active']}; margin-right:5px; vertical-align:middle; }}

.lobe-card {{ background:{ARCHIVE['card']}; border:1px solid {ARCHIVE['border']}; border-radius:12px; padding:14px; margin-bottom:8px; box-shadow:0 1px 3px {ARCHIVE['shadow']}; transition:box-shadow .2s; }}
.lobe-card:hover {{ box-shadow:0 2px 10px {ARCHIVE['shadow']}; }}
.lobe-card.cp {{ padding:7px 14px; }}
.lobe-card.act {{ border-left:3px solid {ARCHIVE['active']}; }}
.lobe-card.idl {{ border-left:3px solid {ARCHIVE['inactive']}; }}
.lobe-card.err {{ border-left:3px solid {ARCHIVE['error']}; }}
.lobe-card .name {{ font-weight:700; color:{ARCHIVE['text']}; font-family:Georgia,'Times New Roman',serif; font-size:15px; }}
.lobe-card .meta {{ color:{ARCHIVE['dim']}; font-size:12px; margin-top:2px; }}

.status-badge {{ font-size:10px; text-transform:uppercase; letter-spacing:1px; padding:2px 10px; border-radius:4px; font-weight:600; }}
.s-active {{ background:rgba(255,107,107,0.1); color:{ARCHIVE['active']}; }}
.s-idle {{ background:rgba(78,205,196,0.1); color:{ARCHIVE['inactive']}; }}
.s-err {{ background:rgba(196,69,54,0.1); color:{ARCHIVE['error']}; }}
.s-done {{ background:rgba(0,184,212,0.1); color:{ARCHIVE['info']}; }}

.syn-tl {{ display:flex; align-items:center; gap:2px; margin-top:10px; padding-top:10px; border-top:1px solid {ARCHIVE['border']}; font-size:12px; flex-wrap:wrap; }}
.syn-step {{ color:#8A867A; transition:color .3s; white-space:nowrap; }}
.syn-step.syn-on {{ color:{ARCHIVE['active']}; font-weight:600; }}
.syn-arrow {{ color:{ARCHIVE['border']}; font-size:10px; margin:0 2px; }}

.whisper-entry {{ display:flex; gap:8px; padding:5px 8px; align-items:center; border-bottom:1px solid {ARCHIVE['border']}; font-size:13px; line-height:1.4; }}
.whisper-entry:hover {{ background:rgba(200,195,185,0.35); }}
.whisper-entry.hl {{ animation:loghl .5s ease-out; }}
.whisper-ts {{ color:{ARCHIVE['dim']}; min-width:68px; font-family:'Inter',monospace; font-size:11px; flex-shrink:0; }}
.whisper-icon {{ min-width:22px; text-align:center; flex-shrink:0; }}
.whisper-msg {{ color:{ARCHIVE['text']}; word-break:break-word; }}

.archive-progress {{ height:5px; background:{ARCHIVE['border']}; border-radius:3px; overflow:hidden; }}
.archive-progress > div {{ height:5px; background:{ARCHIVE['active']}; transition:width .5s; border-radius:3px; }}

.stButton button {{ font-family:'Inter',sans-serif !important; border-radius:8px !important; }}
.stTabs [role="tab"] {{ font-family:Georgia,'Times New Roman',serif !important; font-size:15px; letter-spacing:0.3px; color:#2C363F !important; }}
.stTabs [role="tab"][aria-selected="true"] {{ color:{ARCHIVE['active']} !important; }}
.stTabs [role="tab"]:hover {{ color:#000 !important; }}
.stToggle label, .stCheckbox label {{ color:#121212 !important; }}
.st-emotion-cache-1h9usn1 {{ color:{ARCHIVE['dim']}; }}
.metric {{ background:{ARCHIVE['card']}; border:1px solid {ARCHIVE['border']}; border-radius:12px; padding:8px 12px; }}

.spec-card-active, .spec-card-idle, .spec-card-error {{
    background:#FFFFFF; border:2px solid #5C584E !important;
    border-radius:8px; padding:6px 10px; margin-bottom:4px;
    box-shadow:2px 2px 0 #5C584E !important;
}}
.spec-card-active  {{ border-left:4px solid #FF6B6B !important; }}
.spec-card-idle    {{ border-left:4px solid #4ECDC4 !important; }}
.spec-card-error   {{ border-left:4px solid #C44536 !important; }}

.stMetric, .stTextInput>label, .stSelectbox>label {{ color:#121212 !important; }}

.stApp, .stApp div, .stApp p, .stApp span, .stApp li,
.stApp label, .stApp h1, .stApp h2, .stApp h3,
.stApp h4, .stApp h5, .stApp h6 {{ color:#121212 !important; }}

.js-plotly-plot .plotly .main-svg {{ background:transparent !important; }}

.stApp input {{ background:#FFF !important; border:1px solid #555 !important; color:#000 !important; }}

.stApp pre, .stApp code {{ background:#F4F1EA !important; color:#121212 !important; border:1px solid #D5CFBF !important; border-radius:6px !important; }}
.stApp .stCodeBlock {{ background:#F4F1EA !important; color:#121212 !important; }}
.stApp .stSelectbox div[data-baseweb="select"] {{ background:#FFF !important; color:#121212 !important; }}
.stApp .stSelectbox div[data-baseweb="select"] * {{ color:#121212 !important; }}
.stApp .stExpander summary {{ color:#121212 !important; font-weight:600 !important; }}
.stApp button[kind="secondary"] {{ background:#FFF !important; color:#121212 !important; border:1px solid #5C584E !important; }}

section[data-testid="stAppViewContainer"] .block-container {{ padding-top:0 !important; padding-bottom:0 !important; }}
header[data-testid="stHeader"] {{ display:none !important; }}
.stApp .stExpander details {{ background:#FFF !important; border:1px solid #D5CFBF !important; border-radius:8px !important; }}
.stApp .stExpander details summary {{ background:#FFF !important; color:#121212 !important; }}
.stApp .stSelectbox div[data-baseweb="select"] > div {{ background:#FFF !important; color:#121212 !important; border:1px solid #D5CFBF !important; }}
div[data-baseweb="menu"] {{ background:#FFF !important; border:1px solid #D5CFBF !important; }}
div[data-baseweb="menu"] * {{ color:#121212 !important; }}
div[data-testid="metric-container"] {{ padding:0 8px !important; min-width:auto !important; flex:1 !important; }}
.stPlotlyChart {{ margin-top:4px !important; margin-bottom:4px !important; }}
.stMarkdown {{ margin-bottom:0 !important; }}

@keyframes loghl {{ 0%{{background:rgba(255,107,107,0.1)}} 100%{{background:transparent}} }}
</style>
""", unsafe_allow_html=True)

# ── Module-level data ────────────────────────────────────────────────────────
if not st.session_state.force_idle:
    orch_pid = auto_detect_orch() or st.session_state.orch_pid
else:
    orch_pid = st.session_state.orch_pid
status = load_pipeline_status()
df_spec = load_specialists()
is_active = is_pid_alive(orch_pid) and not st.session_state.force_idle

# Auto-launch: si no hay pipeline ni se ha lanzado antes, arrancar Physics + reports
if not is_active and not st.session_state.auto_launched:
    try:
        # Launch Physics pipeline in new window
        proc = subprocess.Popen(
            ["python","orchestrator.py","--phase","web","--specialist","Physics",
             "--model","deepseek-r1:1.5b","--duration","3.0"],
            creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
        )
        st.session_state.orch_pid = proc.pid
        st.session_state.orch_start_time = time.time()
        st.session_state.force_idle = False

        # Launch report_scheduler in background (hidden)
        subprocess.Popen(
            ["python","report_scheduler.py"],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        st.session_state.auto_launched = True
    except Exception as e:
        pass
p_state = status.get("status","STOPPED") if status else "STOPPED"

ac = df_spec[df_spec['status']=='ACTIVE']['domain'].tolist() if not df_spec.empty else []
ema_spark = load_ema_sparklines(ac)

STATE_COLORS = {"ACTIVE": ARCHIVE['active'], "IDLE": ARCHIVE['inactive'], "COMPLETED": ARCHIVE['info'], "ERROR": ARCHIVE['error'], "STOPPED": ARCHIVE['amber']}
cur_phase = status.get('phase','-') if status else '-'
st.session_state.prev_phase = cur_phase

inject_archive_css()

# ── Header ───────────────────────────────────────────────────────────────────
h1, h2, h3, h4, h5, h6 = st.columns([2.2, 2, 2, 2, 1.5, 1.2])
h1.markdown(f"<div style='font-family:Georgia,\"Times New Roman\",serif;font-size:22px;font-weight:700;color:{ARCHIVE['text']}'>🧠 Synaptic Archive</div>", unsafe_allow_html=True)
dot = f'<span class="coral-dot"></span>' if is_active and p_state=="ACTIVE" else ""
h2.markdown(f"<div class='arc-label'>Status</div><div class='arc-value' style='color:{STATE_COLORS.get(p_state, ARCHIVE['dim'])}'>{dot}{p_state}</div>", unsafe_allow_html=True)
h3.markdown(f"<div class='arc-label'>Phase</div><div class='arc-value sm'>{cur_phase}</div>", unsafe_allow_html=True)
h4.markdown(f"<div class='arc-label'>Specialist</div><div class='arc-value sm'>{status.get('current_specialist','-') if status else '-'}</div>", unsafe_allow_html=True)
if is_active:
    el = time.time() - (st.session_state.orch_start_time or time.time())
    h5.markdown(f"<div class='arc-label'>Uptime</div><div class='arc-value sm'>{el/60:.1f}m</div>", unsafe_allow_html=True)
else:
    h5.markdown(f"<div class='arc-label'>Uptime</div><div class='arc-value sm'>--</div>", unsafe_allow_html=True)
st_ar = st.session_state.auto_refresh
clk = datetime.now().strftime("%H:%M")
h6.markdown(f"<div class='arc-value' style='font-size:20px'>{clk}</div>", unsafe_allow_html=True)
if h6.button("⏹" if st_ar else "▶", key="refresh_toggle"):
    st.session_state.auto_refresh = not st.session_state.auto_refresh
    st.rerun()

tabs = st.tabs(["🧠 Command Center", "📚 Fleet", "🔬 Synaptic Map", "🏛️ Super-Experts"])

# ── COMMAND CENTER ────────────────────────────────────────────────────────────
with tabs[0]:
    cl, cr = st.columns([3, 2])
    with cl:
        if not is_active:
            with st.expander("⚙️ Launch Pipeline", expanded=True):
                phase = st.radio("Phase", ["full","cascade","web"],
                    format_func=lambda x:{"full":"Full Cascade","cascade":"Cascade Only","web":"Web + LLM"}[x], key="lp_phase", horizontal=True)
                st.caption({"full":"Cascade → Web → LLM","cascade":"Wikidata scan only","web":"Web search + LLM loop"}[phase])
                sm = st.radio("Specialists", ["all","model","single"],
                    format_func=lambda x:{"all":"All","model":"By Model","single":"One"}[x], key="lp_spec", horizontal=True)
                sf='all'; mf='all'
                if sm == 'model':
                    ms = df_spec['model'].unique().tolist() if not df_spec.empty else []
                    mf = st.selectbox("Model", ms, key="lp_model")
                elif sm == 'single':
                    ds = df_spec['domain'].tolist() if not df_spec.empty else []
                    sf = st.selectbox("Specialist", ds, key="lp_spec_sel")
                dh = st.slider("Duration (h)", 1.0, 24.0, 5.0, 0.5, key="lp_dur")
        cs, ce = st.columns([1, 1])
        with cs:
            if st.button("▶ Start", type="primary", key="start_orch", disabled=is_active, width='stretch'):
                cmd = ["python","orchestrator.py","--phase",phase,"--specialist",sf,"--model",mf,"--duration",str(dh)]
                try:
                    proc = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0)
                    st.session_state.orch_pid = proc.pid; st.session_state.orch_start_time = time.time()
                    st.session_state.force_idle = False; st.success(f"PID: {proc.pid}"); st.rerun()
                except Exception as e: st.error(f"FAIL: {e}")
        with ce:
            if st.button("■ Stop", key="stop_orch", disabled=not is_active, width='stretch'):
                try:
                    target = st.session_state.orch_pid
                    if target:
                        for attempt in range(3):
                            if os.name == 'nt':
                                subprocess.run(["taskkill","/F","/T","/PID",str(target)], capture_output=True, timeout=5)
                            else:
                                os.kill(target, signal.SIGTERM)
                            time.sleep(1)
                            if not is_pid_alive(target):
                                break
                    st.session_state.orch_pid = None
                    st.session_state.orch_start_time = None
                    st.session_state.force_idle = True
                    st.success("Stopped"); st.rerun()
                except Exception as e: st.error(f"FAIL: {e}")
        st.caption(f"PID: {orch_pid or '--'}  ·  REFR: {'ON' if st.session_state.auto_refresh else 'OFF'}")

        t = len(df_spec)
        d = df_spec['status'].isin(['IDLE','COMPLETED']).sum() if is_active else 0
        f = min(d/t, 1.0) if t else 0
        if is_active and status:
            st.markdown(f"<div class='archive-progress'><div style='width:{f*100:.0f}%'></div></div><div style='font-size:12px;color:{ARCHIVE['dim']};margin-top:3px'>{d}/{t} specialists · Cycle {status.get('current_cycle',1)}</div>", unsafe_allow_html=True)
            st.markdown(f"<span style='font-size:13px'>{status.get('phase','')} — {status.get('current_specialist','')}</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='archive-progress'><div style='width:0%'></div></div><div style='font-size:12px;color:{ARCHIVE['dim']};margin-top:3px'>System idle</div>", unsafe_allow_html=True)

        st.subheader("📜 Library Whispers", divider=True)
        df_logs = load_activity_logs(12)
        process_notifications(df_logs)
        if not df_logs.empty:
            nid = df_logs.iloc[0]['id']
            for _, r in df_logs.iterrows():
                st.markdown(render_whisper_entry(r, highlight=r['id']==nid), unsafe_allow_html=True)
        else: st.caption("-- silence in the library --")

    with cr:
        n_root = df_spec['parent_id'].isna().sum() if 'parent_id' in df_spec.columns else len(df_spec)
        n_child = len(df_spec) - n_root
        subtitle = f"📚 Lobe Cards ({n_root} raíz + {n_child} sub)" if n_child else f"📚 Lobe Cards ({len(df_spec)})"
        st.subheader(subtitle, divider=True)
        if not df_spec.empty:
            search = st.text_input("🔍", placeholder="filter...", key="spec_search", label_visibility="collapsed")
            sk = st.selectbox("Sort", ["DOMAIN","PKGv","PKG^","EMAv","EMA^","STATUS","MODEL"], key="spec_sort", label_visibility="collapsed")
            smap = {"DOMAIN":("domain",True),"PKGv":("packages_absorbed",False),"PKG^":("packages_absorbed",True),
                    "EMAv":("ema_score",False),"EMA^":("ema_score",True),"STATUS":("status",True),"MODEL":("model",True)}
            ck, asc = smap[sk]
            df_f = df_spec[df_spec['domain'].str.contains(search,case=False)|df_spec['model'].str.contains(search,case=False)] if search else df_spec
            om = {"ACTIVE":0,"IDLE":1,"COMPLETED":2,"ERROR":3,"STOPPED":4}
            df_sorted = df_f.assign(_s=df_f["status"].map(om)).sort_values("_s" if ck=="status" else ck, ascending=asc).drop(columns="_s") if ck=="status" else df_f.sort_values(ck, ascending=asc)

            parent_map = {}
            for _, r in df_sorted.iterrows():
                pid = r.get('parent_id')
                if pd.notna(pid):
                    parent_map.setdefault(int(pid), []).append(r)
                else:
                    if int(r['id']) not in parent_map:
                        parent_map[int(r['id'])] = []
            for _, r in df_sorted.iterrows():
                if pd.notna(r.get('parent_id')):
                    continue
                st.markdown(_render_spec_card(r, False, bc_map), unsafe_allow_html=True)
                for child in parent_map.get(int(r['id']), []):
                    st.markdown(_render_spec_card(child, True, bc_map), unsafe_allow_html=True)

        hstat = load_hierarchy_stats()
        if hstat['children'] > 0:
            st.markdown(
                f"<div style='font-size:0.75rem; color:#555; margin-top:6px; padding:6px 8px; background:#FFF; border:1px solid #D5CFBF; border-radius:6px;'>"
                f"🌳 <b>{hstat['roots']}</b> raíces · <b>{hstat['children']}</b> sub · profundidad <b>{hstat['max_depth']}</b> niveles"
                f"</div>", unsafe_allow_html=True)

# ── FLEET ─────────────────────────────────────────────────────────────────────
with tabs[1]:
    st.subheader("⚙️ Configuration", divider=True)
    df_s2 = load_specialists()
    if not df_s2.empty:
        lm = get_local_models()
        asgn = df_s2['model'].unique().tolist()
        miss = [m for m in asgn if m not in lm and not any(l.startswith(m) for l in lm)]
        ca, cb = st.columns([1, 1])
        with ca:
            st.markdown("**Available Models**")
            st.code("\n".join(lm) if lm else "Ollama offline")
        with cb:
            st.markdown("**Missing Models**")
            if miss:
                for m in miss:
                    if st.button(f"📥 Pull {m}", key=f"dl_{m}"):
                        with st.spinner(f"Pulling {m}..."):
                            try:
                                subprocess.run(["ollama","pull",m], check=True)
                                st.success(f"OK {m}"); st.rerun()
                            except Exception as e: st.error(f"FAIL: {e}")
            else: st.success("All models present")
        st.markdown("---")
        dom = st.selectbox("Specialist", df_s2['domain'].tolist())
        cur = df_s2[df_s2['domain']==dom]['model'].values[0]
        st.markdown(f"Current: `{cur}`")
        nw = st.text_input("Model", value=cur)
        if st.button("Update", key="upd_spec"):
            if nw and nw != cur:
                conn = get_connection()
                conn.execute("UPDATE specialist_registry SET model=? WHERE domain=?", (nw, dom))
                conn.commit(); st.success(f"Updated → {nw}"); st.rerun()
            else: st.warning("No change")
    st.markdown("---")
    with st.expander("📜 Fleet Registry"):
        l2 = st.multiselect("Level", ["INFO","WARNING","ERROR","CRITICAL","DEBUG"], default=["INFO","WARNING","ERROR","CRITICAL"], key="spec_log_lvl")
        li2 = st.slider("Entries", 20, 500, 100, key="spec_log_lim")
        df_l2 = load_activity_logs(li2, levels=l2 if l2 else None)
        if not df_l2.empty:
            nid2 = df_l2.iloc[0]['id']
            for _, r in df_l2.iterrows():
                st.markdown(render_whisper_entry(r, highlight=r['id']==nid2), unsafe_allow_html=True)

# ── SYNAPTIC MAP ─────────────────────────────────────────────────────────────
with tabs[2]:
    m1, m2, m3, m4 = st.columns(4)
    tp = df_spec['packages_absorbed'].sum() if not df_spec.empty else 0
    m1.metric("📚 Packages", f"{tp:,}")
    ac_ = (df_spec['status']=='ACTIVE').sum() if not df_spec.empty else 0
    m2.metric("🧠 Active", ac_)
    ws = load_wikidata_speed()
    m3.metric("🏛️ Entities", f"{ws:,}" if ws else "N/A")
    conn = get_connection()
    try: m4.metric("🔥 Incidents", f"{conn.execute('SELECT COUNT(*) FROM activity_log WHERE level IN (\"ERROR\",\"CRITICAL\")').fetchone()[0]:,}")
    except: m4.metric("🔥 Incidents", "0")
    # ── Tree Visualization ────────────────────────────────────────────────
    st.subheader("🌳 Árbol de Especialización", divider=True)
    df_tree = load_specialists_tree()
    if not df_tree.empty:
        col_tree, col_legend = st.columns([4, 1])
        with col_tree:
            fig_tree = px.sunburst(
                df_tree, ids="ids", names="labels", parents="parents", values="values",
                color="ema", color_continuous_scale=["#4ECDC4", "#85D4B0", "#B8D89A", "#E8C070", "#FF6B6B"],
                range_color=[0, 1], title="",
                branchvalues="total",
                hover_data={"ema": ":.3f", "values": True}
            )
            fig_tree.update_traces(
                hovertemplate="<b>%{label}</b><br>📦 %{value}<br>📈 %{customdata[0]:.3f}<br>%{percentRoot:.1%} del total",
                textinfo="label+percent root",
                textfont=dict(family="Inter", size=10, color="#2C363F"),
                marker=dict(line=dict(width=1, color="#5C584E"))
            )
            fig_tree.update_layout(
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color="#2C363F"), margin=dict(l=4, r=4, t=4, b=4),
                coloraxis_colorbar=dict(title="EMA", tickformat=".2f",
                    thicknessmode="pixels", thickness=12, lenmode="pixels", len=180)
            )
            # Rotate root labels outward for readability
            fig_tree.update_layout(
                sunburstcolorway=["#E3DECE"],
            )
            st.plotly_chart(fig_tree, width='stretch')
        with col_legend:
            st.markdown("""
            <div style='font-size:12px; color:#555; padding:8px; background:#FFF; border:1px solid #D5CFBF; border-radius:8px;'>
            <b>🌳 Leyenda</b><br><br>
            <span style='color:#4ECDC4'>■</span> Bajo (0–0.3)<br>
            <span style='color:#B8D89A'>■</span> Medio (0.3–0.6)<br>
            <span style='color:#FF6B6B'>■</span> Alto (0.6–1.0)<br><br>
            <b>Sector</b> = paquetes<br>
            <b>Color</b> = EMA<br>
            <b>Anillo ext.</b> = sub-especialistas
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("🌱 Aún no hay ramas — los sub-especialistas aparecerán aquí cuando el pipeline los genere.")

    # ── Branch Genesis Feed ───────────────────────────────────────────────
    df_branches = load_branch_events()
    if not df_branches.empty:
        with st.expander(f"🌿 Branch Genesis ({len(df_branches)} eventos)", expanded=True):
            for _, r in df_branches.iterrows():
                ts = utc_to_local(r['timestamp'])
                st.markdown(
                    f"<div class='whisper-entry'>"
                    f"<span class='whisper-ts'>{ts}</span>"
                    f"<span class='whisper-icon'>🌱</span>"
                    f"<span class='whisper-msg'>{r['message']}</span></div>",
                    unsafe_allow_html=True)

    # ── Non-domain Branches (Cajón de Sastre) ────────────────────────────
    df_blocked = load_blocked_branches()
    if not df_blocked.empty:
        with st.expander(f"📦 Non-domain branches ({len(df_blocked)} bloqueados)", expanded=False):
            st.caption("QIDs que no pertenecen al dominio y fueron filtrados por blocklist o SPARQL")
            for _, r in df_blocked.iterrows():
                ts = utc_to_local(r['timestamp'])
                st.markdown(
                    f"<div class='whisper-entry'>"
                    f"<span class='whisper-ts'>{ts}</span>"
                    f"<span class='whisper-icon'>📦</span>"
                    f"<span class='whisper-msg'>{r['message']}</span></div>",
                    unsafe_allow_html=True)

    st.markdown("---")
    df_ema = load_ema_history()
    if not df_ema.empty:
        parent_lookup = {}
        for _, r in df_spec.iterrows():
            parent_lookup[r['domain']] = 'child' if pd.notna(r.get('parent_id')) else 'root'
        df_ema['type'] = df_ema['domain'].map(parent_lookup).fillna('root')
        fig = px.line(df_ema, x="created_at", y="ema_score", color="domain", line_dash="type", markers=True,
                      title="EMA per Domain", template="plotly_white")
        fig.update_layout(font=dict(color="#2C363F"), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        fig.update_xaxes(color="#2C363F", tickfont=dict(color="#2C363F"))
        fig.update_yaxes(color="#2C363F", tickfont=dict(color="#2C363F"))
        st.plotly_chart(fig, width='stretch')
    if not df_spec.empty:
        df_display = df_spec.copy()
        df_display['parent_label'] = df_display.apply(
            lambda r: 'child' if pd.notna(r.get('parent_id')) else 'root', axis=1)
        fig2 = px.bar(df_display, x="domain", y="packages_absorbed", color="parent_label",
                      title="Packages by Specialist", template="plotly_white",
                      color_discrete_map={'root': '#4ECDC4', 'child': '#FF6B6B'},
                      pattern_shape="parent_label")
        fig2.update_layout(font=dict(color="#2C363F"), bargap=0.5,
                          paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                          legend_title="Type")
        fig2.update_xaxes(color="#2C363F", tickfont=dict(color="#2C363F"))
        fig2.update_yaxes(color="#2C363F", tickfont=dict(color="#2C363F"))
        st.plotly_chart(fig2, width='stretch')
    st.markdown("---")
    df_err = load_errors_by_model()
    if not df_err.empty:
        fig3 = px.bar(df_err, x="model", y="count", color="model", title="Errors by Model",
                      template="plotly_white",
                      color_discrete_sequence=px.colors.qualitative.Dark24)
        fig3.update_layout(font=dict(color="#2C363F"), bargap=0.5,
                          paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False)
        fig3.update_xaxes(color="#2C363F", tickfont=dict(color="#2C363F"))
        fig3.update_yaxes(color="#2C363F", tickfont=dict(color="#2C363F"))
        st.plotly_chart(fig3, width='stretch')
    else: st.info("No incidents — the library is at peace")

# ── SUPER-EXPERTS ────────────────────────────────────────────────────────────
with tabs[3]:
    st.subheader("🏛️ Super-Expert Councils", divider=True)
    st.caption("Cross-domain councils that combine multiple specialists with weighted expertise. "
               "When the archive matures, asking a question here will route to the right experts.")

    df_se = load_super_experts()
    if not df_se.empty:
        for _, se in df_se.iterrows():
            se_id = se['id']
            with st.expander(f"🏛️ {se['domain']}  —  {se['member_count']} members · "
                            f"📈 {se['weighted_ema']:.3f} weighted EMA · "
                            f"📦 {se['total_packages']:,} total packages", expanded=False):
                st.markdown(f"<div style='font-size:0.85rem; color:#555; margin-bottom:8px;'>{se['description']}</div>",
                           unsafe_allow_html=True)

                df_members = load_super_expert_members(se_id)
                if not df_members.empty:
                    # Build a visual table
                    member_lines = []
                    member_lines.append("<table style='width:100%; font-size:0.85rem; border-collapse:collapse;'>")
                    member_lines.append("<tr style='border-bottom:1px solid #D5CFBF;'>"
                                        "<th style='text-align:left;padding:4px 8px;'>Specialist</th>"
                                        "<th style='text-align:center;padding:4px 8px;'>Weight</th>"
                                        "<th style='text-align:center;padding:4px 8px;'>EMA</th>"
                                        "<th style='text-align:center;padding:4px 8px;'>Packages</th>"
                                        "<th style='text-align:center;padding:4px 8px;'>Status</th>"
                                        "<th style='text-align:center;padding:4px 8px;'>Bar</th></tr>")
                    for _, m in df_members.iterrows():
                        pct = m['weight'] * 100
                        bar_w = max(2, int(m['weight'] * 100))
                        bar = f"<div style='height:10px; width:{bar_w}px; background:#FF6B6B; border-radius:3px; display:inline-block;'></div>"
                        member_lines.append(
                            f"<tr style='border-bottom:1px solid #F0EDE4;'>"
                            f"<td style='padding:4px 8px; font-weight:600;'>{m['domain']}</td>"
                            f"<td style='text-align:center;padding:4px 8px;'>{pct:.0f}%</td>"
                            f"<td style='text-align:center;padding:4px 8px;'>{m['ema_score']:.3f}</td>"
                            f"<td style='text-align:center;padding:4px 8px;'>{m['packages_absorbed']}</td>"
                            f"<td style='text-align:center;padding:4px 8px;'>{m['status']}</td>"
                            f"<td style='padding:4px 8px;'>{bar}</td></tr>"
                        )
                    member_lines.append("</table>")
                    st.markdown("\n".join(member_lines), unsafe_allow_html=True)
    else:
        st.info("🏛️ No super-experts defined yet. Run the pipeline to initialize them.")
