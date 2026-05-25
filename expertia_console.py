import streamlit as st
import pandas as pd
import plotly.express as px
import subprocess
import os
import signal
import time
from datetime import datetime
import sys
sys.path.insert(0, os.path.dirname(__file__))
from database.db_manager import get_db_manager

st.set_page_config(page_title="Expertia Console", layout="wide", page_icon="🧠")

if "orch_pid" not in st.session_state:
    st.session_state.orch_pid = None
if "orch_start_time" not in st.session_state:
    st.session_state.orch_start_time = None

def get_connection():
    return get_db_manager()._get_connection()

def load_specialists():
    conn = get_connection()
    return pd.read_sql_query("SELECT id, domain, model, ema_score, packages_absorbed, status FROM specialist_registry ORDER BY domain", conn)

def load_pipeline_status():
    conn = get_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM pipeline_status ORDER BY id DESC LIMIT 1", conn)
        return df.iloc[0].to_dict() if not df.empty else None
    except Exception:
        return None

def load_activity_logs(limit=50, levels=None):
    conn = get_connection()
    try:
        if levels:
            placeholders = ",".join("?" for _ in levels)
            return pd.read_sql_query(f"SELECT timestamp, level, message, id FROM activity_log WHERE level IN ({placeholders}) ORDER BY id DESC LIMIT ?", conn, params=[*levels, limit])
        else:
            return pd.read_sql_query("SELECT timestamp, level, message, id FROM activity_log ORDER BY id DESC LIMIT ?", conn, params=[limit])
    except Exception:
        return pd.DataFrame()

def load_ema_history():
    conn = get_connection()
    try:
        return pd.read_sql_query("""
            SELECT e.timestamp AS created_at, e.ema_score, s.domain 
            FROM ema_history e 
            JOIN specialist_registry s ON e.specialist_id = s.id 
            ORDER BY e.timestamp
        """, conn)
    except Exception:
        return pd.DataFrame()

def load_errors_by_model():
    conn = get_connection()
    try:
        df = pd.read_sql_query("SELECT level, message FROM activity_log WHERE level IN ('ERROR', 'CRITICAL') ORDER BY id DESC LIMIT 500", conn)
        models = []
        for msg in df['message']:
            matched = False
            for m in ['mistral:7b', 'qwen2.5:3b', 'qwen2.5-coder:3b', 'llama3.2:3b', 'gemma2:2b',
                       'phi3:mini', 'adrienbrault/biomistral-7b:Q4_K_M', 'phi3:latest']:
                if m in str(msg):
                    models.append(m)
                    matched = True
                    break
            if not matched:
                models.append('other')
        df['model'] = models
        return df.groupby('model').size().reset_index(name='count').sort_values('count', ascending=False)
    except Exception:
        return pd.DataFrame(columns=['model', 'count'])

def load_wikidata_speed():
    conn = get_connection()
    try:
        df = pd.read_sql_query("""
            SELECT timestamp, message FROM activity_log
            WHERE message LIKE '%entity%' OR message LIKE '%Entity%' OR message LIKE '%wikidata%' OR message LIKE '%extract%'
            ORDER BY id DESC LIMIT 1000
        """, conn)
        if df.empty:
            return None
        import re
        entities = []
        for msg in df['message']:
            m = re.search(r'(\d+)\s*entities', str(msg), re.IGNORECASE)
            if m:
                entities.append(int(m.group(1)))
        return max(entities) if entities else None
    except Exception:
        return None

def is_pid_alive(pid):
    if pid is None:
        return False
    try:
        if os.name == 'nt':
            result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True, timeout=5)
            return str(pid) in result.stdout
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False

def get_local_models():
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')[1:]
            return [line.split()[0] for line in lines if line.strip()]
        return []
    except Exception:
        return []

def auto_detect_orch():
    try:
        result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV"], capture_output=True, text=True, timeout=5)
        for line in result.stdout.split('\n'):
            if 'orchestrator.py' in line:
                import re
                m = re.search(r'"(\d+)"', line)
                if m:
                    pid = int(m.group(1))
                    if pid != st.session_state.orch_pid:
                        st.session_state.orch_pid = pid
                        st.session_state.orch_start_time = st.session_state.orch_start_time or time.time()
                    return pid
        return None
    except Exception:
        return None

def status_badge(status):
    colors = {"ACTIVE": "green", "IDLE": "gray", "COMPLETED": "blue", "ERROR": "red", "STOPPED": "orange"}
    c = colors.get(status, "gray")
    return f'<span style="background:{c};color:white;padding:2px 8px;border-radius:4px;font-size:0.8em">{status}</span>'

now = datetime.now().strftime("%H:%M:%S")
col_t, col_r = st.columns([4, 1])
col_t.title("🧠 Expertia Control Console")
col_r.markdown(f"**{now}**")
if col_r.button("🔄 Refresh"):
    st.rerun()

orch_pid = auto_detect_orch() or st.session_state.orch_pid
status = load_pipeline_status()

col_run, col_stat, col_time, col_up = st.columns(4)
col_run.metric("Pipeline", status.get("status", "STOPPED") if status else "STOPPED")
col_stat.metric("Phase", status.get("phase", "-") if status else "-")
col_stat.metric("Specialist", status.get("current_specialist", "-") if status else "-")
col_time.metric("Model", status.get("current_model", "-") if status else "-")

if is_pid_alive(orch_pid):
    if st.session_state.orch_start_time:
        uptime = time.time() - st.session_state.orch_start_time
        col_up.metric("Uptime", f"{uptime/60:.1f} min")
    else:
        col_up.metric("Uptime", "N/A")
else:
    col_up.metric("Uptime", "Stopped")

st.markdown("---")
tab1, tab2, tab3, tab4 = st.tabs(["Control Panel", "Model Manager", "Analytics", "Activity Logs"])

with tab1:
    col_start, col_stop, col_info = st.columns([1, 1, 3])
    with col_start:
        if st.button("▶ Start Orchestrator", type="primary", disabled=is_pid_alive(orch_pid)):
            try:
                proc = subprocess.Popen(["python", "orchestrator.py"], creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0)
                st.session_state.orch_pid = proc.pid
                st.session_state.orch_start_time = time.time()
                st.success(f"Started (PID: {proc.pid})!")
                st.rerun()
            except Exception as e:
                st.error(f"Failed: {e}")
    with col_stop:
        if st.button("⏹ Stop Orchestrator", disabled=not is_pid_alive(orch_pid)):
            pid = st.session_state.orch_pid
            try:
                if os.name == 'nt':
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, timeout=5)
                else:
                    os.kill(pid, signal.SIGTERM)
                st.session_state.orch_pid = None
                st.session_state.orch_start_time = None
                st.success("Stopped!")
                st.rerun()
            except Exception as e:
                st.error(f"Failed: {e}")
    with col_info:
        st.caption(f"PID: {orch_pid or '—'}")

    df_spec = load_specialists()
    st.subheader("Pipeline Progress")
    if status and status.get("status") == "ACTIVE":
        phase = status.get("phase", "")
        specialist = status.get("current_specialist", "")
        cycle = status.get("current_cycle", 1)
        st.write(f"**Cycle {cycle}** — {phase}")
        if specialist:
            st.write(f"Current: `{specialist}`")
        total = len(df_spec)
        done = df_spec['status'].isin(['IDLE', 'COMPLETED']).sum()
        frac = min(done / total, 1.0) if total else 0
        st.progress(frac, text=f"{done}/{total} specialists processed")
    else:
        st.progress(0, text="Pipeline not running")

    st.subheader("Knowledge Packages per Specialist")
    if not df_spec.empty:
        max_pkgs = df_spec['packages_absorbed'].max() or 1
        for _, r in df_spec.iterrows():
            frac = r['packages_absorbed'] / max_pkgs
            st.progress(min(frac, 1.0), text=f"**{r['domain']}** — {r['packages_absorbed']} pkgs — EMA: {r['ema_score']:.2f}")

    st.subheader("Specialists")
    if not df_spec.empty:
        for _, r in df_spec.iterrows():
            cols = st.columns([2, 1, 1, 2, 2])
            cols[0].markdown(f"**{r['domain']}**")
            cols[1].markdown(status_badge(r['status']), unsafe_allow_html=True)
            cols[2].markdown(f"`{r['model']}`")
            cols[3].markdown(f"📦 {r['packages_absorbed']}")
            cols[4].markdown(f"📈 EMA: {r['ema_score']:.2f}")

    st.markdown("---")
    st.subheader("Recent Activity")
    df_logs = load_activity_logs(15)
    if not df_logs.empty:
        for _, r in df_logs.iterrows():
            ts = r['timestamp'][:19] if r['timestamp'] else ''
            level = r['level']
            msg = str(r['message'])[:120]
            color = {"ERROR": "red", "WARNING": "orange", "INFO": "green", "CRITICAL": "red", "DEBUG": "gray"}.get(level, "gray")
            st.markdown(f'<span style="color:{color}">[{ts}] [{level}] {msg}</span>', unsafe_allow_html=True)
    else:
        st.caption("No activity yet")

with tab2:
    st.header("Model Manager")
    st.info("Assign different Ollama models to experts dynamically.")
    df_spec = load_specialists()
    if not df_spec.empty:
        local_models = get_local_models()
        assigned_models = df_spec['model'].unique().tolist()
        missing_models = [m for m in assigned_models if m not in local_models and not any(lm.startswith(m) for lm in local_models)]
        col_list, col_warn = st.columns([1, 1])
        with col_list:
            st.write("**Local Models:**")
            st.code("\n".join(local_models) if local_models else "None / Ollama offline")
        with col_warn:
            if missing_models:
                st.warning(f"Missing: {', '.join(missing_models)}")
                for missing in missing_models:
                    if st.button(f"Download {missing}", key=f"dl_{missing}"):
                        with st.spinner(f"Downloading {missing}..."):
                            try:
                                subprocess.run(["ollama", "pull", missing], check=True)
                                st.success(f"Downloaded {missing}!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed: {e}")
            else:
                st.success("All models available")
        st.markdown("---")
        domain_to_edit = st.selectbox("Select Expert Domain:", df_spec['domain'].tolist())
        current_model = df_spec[df_spec['domain'] == domain_to_edit]['model'].values[0]
        st.write(f"**Current:** `{current_model}`")
        new_model = st.text_input("New Model:", value=current_model)
        if st.button("Update Model"):
            if new_model and new_model != current_model:
                conn = get_connection()
                conn.execute("UPDATE specialist_registry SET model = ? WHERE domain = ?", (new_model, domain_to_edit))
                conn.commit()
                st.success(f"Updated {domain_to_edit} → `{new_model}`!")
                st.rerun()
            else:
                st.warning("No change")

with tab3:
    st.header("Analytics")
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    df_spec = load_specialists()
    total_pkgs = df_spec['packages_absorbed'].sum() if not df_spec.empty else 0
    col_m1.metric("Total Packages", f"{total_pkgs:,}")
    active = (df_spec['status'] == 'ACTIVE').sum() if not df_spec.empty else 0
    col_m2.metric("Active Specialists", active)
    wikidata_speed = load_wikidata_speed()
    col_m3.metric("Max Entities", f"{wikidata_speed:,}" if wikidata_speed else "N/A")
    conn = get_connection()
    try:
        c = conn.execute("SELECT COUNT(*) FROM activity_log WHERE level IN ('ERROR','CRITICAL')")
        total_errs = c.fetchone()[0]
    except Exception:
        total_errs = 0
    col_m4.metric("Total Errors", f"{total_errs:,}")
    st.markdown("---")
    df_ema = load_ema_history()
    if not df_ema.empty:
        st.subheader("EMA Evolution")
        fig = px.line(df_ema, x="created_at", y="ema_score", color="domain", markers=True, title="EMA per Domain")
        st.plotly_chart(fig, width='stretch')
    else:
        st.info("No EMA data yet — run the pipeline to collect scores")
    if not df_spec.empty:
        st.subheader("Knowledge Packages")
        fig2 = px.bar(df_spec, x="domain", y="packages_absorbed", color="domain", title="Packages by Specialist")
        st.plotly_chart(fig2, width='stretch')
    st.markdown("---")
    st.subheader("Errors by Model")
    df_errors = load_errors_by_model()
    if not df_errors.empty:
        fig3 = px.bar(df_errors, x="model", y="count", color="model", title="Error Count")
        st.plotly_chart(fig3, width='stretch')
    else:
        st.info("No errors recorded")

with tab4:
    st.header("Activity Logs")
    col_f1, col_f2 = st.columns([1, 3])
    with col_f1:
        level_filter = st.multiselect("Level", ["INFO", "WARNING", "ERROR", "CRITICAL", "DEBUG"], default=["INFO", "WARNING", "ERROR", "CRITICAL"])
    with col_f2:
        limit = st.slider("Entries", 50, 1000, 200)
    df_logs = load_activity_logs(limit, levels=level_filter if level_filter else None)
    if not df_logs.empty:
        st.dataframe(df_logs, width='stretch')
    else:
        st.info("No logs yet")
