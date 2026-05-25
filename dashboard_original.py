import streamlit as st
import sqlite3
import time
import pandas as pd
from pathlib import Path
from datetime import datetime

st.set_page_config(page_title="Expertia Pipeline Dashboard", layout="wide")
st.title("🔬 Expertia Pipeline Monitor")

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "storage" / "incubator.db"
LOGS_DIR = BASE_DIR / "logs"
REFRESH_SECONDS = 3

# ── helpers ──────────────────────────────────────────────────────

def get_db():
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def specialists_table(conn):
    cur = conn.execute("SELECT * FROM specialist_registry ORDER BY id")
    return cur.fetchall()

def ema_history_all(conn):
    cur = conn.execute("""
        SELECT s.domain, h.ema_score, h.timestamp
        FROM ema_history h
        JOIN specialist_registry s ON h.specialist_id = s.id
        ORDER BY h.timestamp ASC
    """)
    return cur.fetchall()

def last_knowledge_packages(conn, limit=5):
    try:
        cur = conn.execute("""
            SELECT topic, source_url, domain, created_at
            FROM knowledge_packages
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        return cur.fetchall()
    except Exception:
        return []

def pipeline_progress(conn):
    cur = conn.execute("SELECT COUNT(*) FROM specialist_registry")
    total = cur.fetchone()[0]
    cur = conn.execute("SELECT COUNT(*) FROM specialist_registry WHERE packages_absorbed > 0")
    processed = cur.fetchone()[0]
    cur = conn.execute("SELECT COUNT(*) FROM knowledge_packages")
    pkgs = cur.fetchone()[0]
    return total, processed, pkgs

def get_pipeline_status(conn):
    try:
        cur = conn.execute("SELECT * FROM pipeline_status WHERE id = 1")
        return cur.fetchone()
    except Exception:
        return None

def format_elapsed(seconds):
    if seconds is None or seconds == 0:
        return "—"
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    if h > 0:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m:02d}m {s:02d}s"

def latest_logs(n=8):
    if not LOGS_DIR.exists():
        return ""
    files = sorted(LOGS_DIR.glob("pipeline_*.log"), reverse=True)
    if not files:
        return ""
    with open(files[0], "r", encoding="utf-8") as f:
        lines = f.readlines()
    return "".join(lines[-n:])

def model_status():
    import subprocess
    try:
        r = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return {}
        models = {}
        for line in r.stdout.strip().split("\n")[1:]:
            parts = line.split()
            if parts:
                models[parts[0]] = True
        return models
    except Exception:
        return {}

# ── status indicators ────────────────────────────────────────────

STATUS_EMOJI = {
    'INIT': '🔄', 'RUNNING': '🔄', 'ACTIVE': '🟢', 'CHECKING_MODEL': '🔍',
    'SKIPPED': '⏭️', 'COMPLETED': '✅', 'ERROR': '❌', 'IDLE': '⏸',
}
STATUS_LABEL = {
    'INIT': 'Iniciando', 'RUNNING': 'Ejecutando', 'ACTIVE': 'Activo',
    'CHECKING_MODEL': 'Verificando modelo', 'SKIPPED': 'Saltado',
    'COMPLETED': 'Completado', 'ERROR': 'Error', 'IDLE': 'Inactivo',
}

# ── main layout ──────────────────────────────────────────────────

db = get_db()
if db is None:
    st.warning("Base de datos no encontrada. Ejecuta el pipeline primero.")
    st.stop()

total, processed, pkgs = pipeline_progress(db)
local_models = model_status()

# ── top bar: metrics ─────────────────────────────────────────────
cols = st.columns([1, 1, 1, 1, 2])
cols[0].metric("Especialistas", total)
cols[1].metric("Procesados", processed)
prog = processed / max(total, 1)
cols[2].markdown(f"**Progreso**  \n{processed}/{total} ({prog:.0%})")
cols[2].progress(prog)
cols[3].metric("Knowledge Pkgs", pkgs)
cols[4].markdown(f"**Última actualización**  \n{datetime.now():%H:%M:%S}  ·  ciclo cada {REFRESH_SECONDS}s")

# ── real‑time status ─────────────────────────────────────────────
status_row = get_pipeline_status(db)
if status_row:
    sr = dict(status_row)
    emoji = STATUS_EMOJI.get(sr["status"], '❓')
    label = STATUS_LABEL.get(sr["status"], sr["status"])
    
    # Compute elapsed locally so the clock ticks every refresh
    start_epoch = sr.get("start_epoch", 0)
    if start_epoch and sr["status"] not in ('IDLE', 'COMPLETED'):
        elapsed_seconds = time.time() - start_epoch
    else:
        elapsed_seconds = sr.get("elapsed_seconds", 0)
    elapsed = format_elapsed(elapsed_seconds)
    
    if sr["status"] in ('ACTIVE', 'RUNNING', 'CHECKING_MODEL', 'INIT'):
        with st.container():
            c1, c2 = st.columns([1, 6])
            c1.markdown(f"## {emoji}")
            parts = []
            if sr.get("current_specialist"):
                parts.append(f"**{sr['current_specialist']}**")
            if sr.get("current_model"):
                parts.append(f"`{sr['current_model']}`")
            if sr.get("current_cycle") and sr.get("total_cycles"):
                parts.append(f"Ciclo {sr['current_cycle']}/{sr['total_cycles']}")
            detail = " · ".join(parts) if parts else ""
            c2.markdown(
                f"### {label}: {sr['phase']}  \n{detail}  ⏱ {elapsed}"
            )
    elif sr["status"] == 'COMPLETED':
        st.success(f"✅ **Pipeline completado** en {elapsed}")
    elif sr["status"] == 'ERROR':
        st.error(f"❌ **Error**: {sr['phase']}  ⏱ {elapsed}")
    else:
        st.info(f"⏸ **Pipeline inactivo**  ·  último: {sr['phase']}")

st.divider()

# ── two‑column body ──────────────────────────────────────────────
left, right = st.columns([1.2, 1])

# ── LEFT: specialist table ───────────────────────────────────────
with left:
    st.subheader("📋 Especialistas")
    col_sort, col_group = st.columns([1, 1])
    with col_sort:
        sort_by = st.selectbox("Ordenar por", ["EMA ↓", "EMA ↑", "Modelo", "Paquetes ↓", "Dominio"], label_visibility="collapsed")
    with col_group:
        group_by_model = st.checkbox("Agrupar por modelo", value=True)

    specialists = specialists_table(db)
    if specialists:
        rows = []
        for s in specialists:
            model_ok = s["model"] in local_models if local_models else True
            icon = "🟢" if model_ok else "🔴"
            rows.append({
                "_icon": icon,
                "_model": s["model"],
                "_ema": s["ema_score"],
                "_pkgs": s["packages_absorbed"],
                "_domain": s["domain"],
                "Dominio": s["domain"],
                "Modelo": s["model"],
                "EMA": f"{s['ema_score']:.3f}",
                "Tier": s["tier"],
                "Estado": s["status"],
                "Pkgs": s["packages_absorbed"],
            })

        if sort_by == "EMA ↓":
            rows.sort(key=lambda r: r["_ema"], reverse=True)
        elif sort_by == "EMA ↑":
            rows.sort(key=lambda r: r["_ema"])
        elif sort_by == "Modelo":
            rows.sort(key=lambda r: (r["_model"], r["_ema"]))
        elif sort_by == "Paquetes ↓":
            rows.sort(key=lambda r: r["_pkgs"], reverse=True)
        elif sort_by == "Dominio":
            rows.sort(key=lambda r: r["_domain"])

        if group_by_model:
            groups = {}
            for r in rows:
                groups.setdefault(r["_model"], []).append(r)
            for model_name, group in sorted(groups.items()):
                is_ok = model_name in local_models if local_models else True
                emoji = "🟢" if is_ok else "🔴"
                with st.expander(f"{emoji} {model_name} ({len(group)})", expanded=True):
                    display = [{k: r[k] for k in ["Dominio", "EMA", "Tier", "Estado", "Pkgs"]} for r in group]
                    st.dataframe(display, width="stretch", hide_index=True)
        else:
            st.dataframe(rows, width="stretch", hide_index=True, column_order=["Dominio", "Modelo", "EMA", "Tier", "Estado", "Pkgs"])
    else:
        st.info("Vacío")

    # ── knowledge packages ───────────────────────────────────────────
    st.subheader("📦 Últimos paquetes")
    pkgs_list = last_knowledge_packages(db)
    if pkgs_list:
        for p in pkgs_list:
            st.caption(f"**{p['topic']}** · {p['domain']} · [{p['source_url'][:50]}…]({p['source_url']})")
    else:
        st.caption("(sin paquetes aún)")

# ── RIGHT: EMA chart + logs ──────────────────────────────────────
with right:
    st.subheader("📈 EMA Scores")
    history = ema_history_all(db)
    mode = st.radio("Modo", ["Todas", "Individual"], horizontal=True, label_visibility="collapsed")

    if history:
        df = pd.DataFrame([{
            "domain": r["domain"],
            "score": r["ema_score"],
            "timestamp": r["timestamp"]
        } for r in history])

        if mode == "Todas":
            df["idx"] = df.groupby("domain").cumcount()
            pivot = df.pivot(index="idx", columns="domain", values="score")
            st.line_chart(pivot, height=250)
        else:
            domain_list = sorted(df["domain"].unique())
            sel = st.selectbox("", domain_list, label_visibility="collapsed")
            sub = df[df["domain"] == sel][["score"]].reset_index(drop=True)
            sub.columns = [f"EMA - {sel}"]
            st.line_chart(sub, height=250)
    else:
        st.info("(sin historial aún — los scores se preservan entre ejecuciones)")

    # ── logs ──────────────────────────────────────────────────────
    st.subheader("📜 Logs")
    st.code(latest_logs(), language="log")

# ── auto‑refresh ─────────────────────────────────────────────────
time.sleep(REFRESH_SECONDS)
st.rerun()
