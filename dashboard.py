import streamlit as st
import sqlite3
import time
import pandas as pd
from pathlib import Path
from datetime import datetime

st.set_page_config(page_title="Expertia Pipeline", layout="wide")
st.title("🔬 Expertia Pipeline Monitor")

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "storage" / "incubator.db"
LOGS_DIR = BASE_DIR / "logs"
REFRESH_SECONDS = 3

def get_db():
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def get_pipeline_status(conn):
    try:
        r = conn.execute("SELECT * FROM pipeline_status WHERE id = 1").fetchone()
        return dict(r) if r else None
    except:
        return None

def get_checkpoints(conn):
    try:
        return conn.execute("SELECT * FROM cascade_checkpoints ORDER BY checkpoint_num ASC").fetchall()
    except:
        return []

def get_specialists(conn):
    return conn.execute("SELECT * FROM specialist_registry ORDER BY id").fetchall()

def get_ema_history(conn):
    return conn.execute("""
        SELECT s.domain, h.ema_score, h.timestamp
        FROM ema_history h JOIN specialist_registry s ON h.specialist_id = s.id
        ORDER BY h.timestamp ASC
    """).fetchall()

def get_qid_expansions_per_specialist(conn):
    try:
        rows = conn.execute("SELECT specialist_id, COUNT(*) as cnt FROM qid_expansions GROUP BY specialist_id").fetchall()
        return {r['specialist_id']: r['cnt'] for r in rows}
    except:
        return {}

def get_cartridge_status(conn):
    try:
        rows = conn.execute("SELECT specialist_id, status FROM cartridge_offsets").fetchall()
        return {r['specialist_id']: r['status'] for r in rows}
    except:
        return {}

def get_packages(conn, n=3):
    try:
        return conn.execute("""
            SELECT topic, domain, created_at FROM knowledge_packages
            ORDER BY created_at DESC LIMIT ?
        """, (n,)).fetchall()
    except:
        return []

def get_logs(n=4):
    if not LOGS_DIR.exists():
        return ""
    files = sorted(LOGS_DIR.glob("pipeline_*.log"), reverse=True)
    if not files:
        return ""
    with open(files[0], "r", encoding="utf-8") as f:
        return "".join(f.readlines()[-n:])

def fmt(t):
    if not t:
        return "—"
    h, r = divmod(int(t), 3600)
    m, s = divmod(r, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m:02d}m{s:02d}s"

db = get_db()
if db is None:
    st.warning("Base de datos no encontrada")
    st.stop()

sr = get_pipeline_status(db)
status = sr.get('status', 'IDLE') if sr else 'IDLE'
phase = sr.get('phase', '') if sr else ''
ce = sr.get('cascade_entities', 0) if sr else 0
cm = sr.get('cascade_max', 0) if sr else 0
cp = sr.get('cascade_checkpoint', 0) if sr else 0
spec = sr.get('current_specialist', '') if sr else ''
smodel = sr.get('current_model', '') if sr else ''
cycle = sr.get('current_cycle', 0) if sr else 0
tcycle = sr.get('total_cycles', 0) if sr else 0
se = sr.get("start_epoch", 0) if sr else 0
el = sr.get('elapsed_seconds', 0) if sr else 0
if status in ('ACTIVE', 'RUNNING', 'CHECKING_MODEL', 'INIT') and se:
    el = time.time() - se

rate = ce / el if el > 0 and ce > 0 else 0
cp_total = max(cm // 500_000, 1)
eta_s = (cm - ce) / rate if rate > 0 else 0

# ── HEADER ──
c = st.columns(6)
c[0].metric("Estado", status)
c[0].caption(phase[:50])
c[1].metric("⏱️", fmt(el))
c[2].metric("🎯 ETA", fmt(eta_s))
c[3].metric("📊 Cascade", f"{cp}/{cp_total}" if cm else "—")
c[4].metric("🧬 QIDs", sum(get_qid_expansions_per_specialist(db).values()))
c[5].metric("⚡/s", f"{rate:.0f}" if rate else "—")

if spec:
    st.info(f"🟢 **{spec}** · {smodel} · Ciclo {cycle}/{tcycle}")

if cm > 0:
    st.progress(min(ce / cm, 1.0))
    st.caption(f"{ce:,} / {cm:,} entidades  ·  checkpoint: {ce % 500_000:,}/500.000")

st.divider()

# ── BODY: 3 columns ──
col1, col2, col3 = st.columns([1.3, 1, 0.9])

# ── COL 1: Specialists table ──
with col1:
    st.subheader("📋 Especialistas")
    specialists = get_specialists(db)
    qid_exp = get_qid_expansions_per_specialist(db)
    cart = get_cartridge_status(db)

    if specialists:
        rows = []
        for s in specialists:
            sid = s['id']
            c_status = cart.get(sid, '—')
            c_status_short = '✅' if c_status == 'COMPLETED' else '⏳' if 'PROCESSING' in str(c_status) else '❌' if 'FAIL' in str(c_status) else '—'
            rows.append({
                "Dominio": s["domain"],
                "EMA": f"{s['ema_score']:.3f}",
                "Md": s["model"].split(":")[0][:8],
                "Pkgs": s["packages_absorbed"],
                "QIDexp": qid_exp.get(sid, 0),
                "P-A": c_status_short,
            })
        st.dataframe(rows, width="stretch", hide_index=True, height=18*len(rows)+10)

# ── COL 2: Charts ──
with col2:
    # EMA chart
    st.subheader("📈 EMA")
    history = get_ema_history(db)
    if history:
        df = pd.DataFrame([{"d": r["domain"], "s": r["ema_score"]} for r in history])
        df["i"] = df.groupby("d").cumcount()
        pivot = df.pivot(index="i", columns="d", values="s")
        st.line_chart(pivot, height=120)
    else:
        st.caption("(esperando Phase B...)")

    # Speed chart
    st.subheader("⚡ Velocidad")
    checkpoints = get_checkpoints(db)
    if len(checkpoints) >= 2:
        cp_data = []
        prev_ent = 0
        prev_el = 0
        for i, cp in enumerate(checkpoints):
            if i == 0:
                speed = cp['entities_processed'] / cp['elapsed_seconds'] if cp['elapsed_seconds'] > 0 else 0
            else:
                d_ent = cp['entities_processed'] - prev_ent
                d_el = cp['elapsed_seconds'] - prev_el
                speed = d_ent / d_el if d_el > 0 else 0
            cp_data.append({"cp": cp['checkpoint_num'], "speed": speed})
            prev_ent = cp['entities_processed']
            prev_el = cp['elapsed_seconds']
        df_speed = pd.DataFrame(cp_data)
        st.line_chart(df_speed.set_index("cp"), height=100)
    elif len(checkpoints) == 1:
        spd = checkpoints[0]['entities_processed'] / checkpoints[0]['elapsed_seconds']
        st.metric("Throughput", f"{spd:.0f} ent/s")
    else:
        st.caption("(recopilando datos...)")

# ── COL 3: Packages + Logs ──
with col3:
    st.subheader("📦 Paquetes")
    for p in get_packages(db):
        st.caption(f"{p['domain']}: {p['topic'][:25]}")
    if not get_packages(db):
        st.caption("(esperando Phase B...)")

    st.subheader("📜 Logs")
    st.code(get_logs(), language="log")

time.sleep(REFRESH_SECONDS)
st.rerun()
