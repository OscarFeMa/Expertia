import json
import logging
import os
import re
import signal
import sqlite3
import subprocess
import sys
import time
import asyncio
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Security
from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, field_validator

from database.db_manager import get_db_manager
from database.readonly_db import select, select_one
from tools.spawn_specialist import spawn_child
from config.settings import DATABASE_PATH

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

_PIPELINE_STATE_FILE = Path(__file__).parent / "pipeline_state.json"
LOGS_DIR = Path(__file__).parent / "logs"

_pipeline: dict = {"pid": None, "start_time": 0, "duration_hours": 0}
_pipeline_lock = threading.RLock()
_kill_timer: Optional[threading.Timer] = None

_monitor_process: dict = {"pid": None, "start_time": 0}
_monitor_lock = threading.Lock()
_MONITOR_PID_FILE = Path(__file__).parent / "storage" / "monitor.pid"
_MONITOR_REPORT_FILE = Path(__file__).parent / "storage" / "monitor_reports.json"

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
EXPERTIA_API_KEY = os.environ.get("EXPERTIA_API_KEY", "")

if not EXPERTIA_API_KEY:
    logger.warning("EXPERTIA_API_KEY not set — API endpoints are unprotected (local mode)")


def verify_api_key(x_api_key: Optional[str] = Security(_api_key_header)):
    if EXPERTIA_API_KEY and x_api_key != EXPERTIA_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return x_api_key


def _save_pipeline_state():
    try:
        with _pipeline_lock:
            state = dict(_pipeline)
        _PIPELINE_STATE_FILE.write_text(json.dumps(state))
    except Exception as e:
        logger.warning(f"Failed to save pipeline state: {e}")


def _schedule_kill_timer():
    global _kill_timer
    end_epoch = _pipeline.get("end_epoch")
    pid = _pipeline.get("pid")
    if not end_epoch or not pid:
        return
    now = time.time()
    remaining = end_epoch - now
    if remaining <= 0:
        logger.info(f"Pipeline PID={pid} exceeded its duration on reload — cleaning up")
        _pipeline["pid"] = None
        _pipeline["end_epoch"] = None
        _save_pipeline_state()
        return
    if _kill_timer is not None:
        _kill_timer.cancel()
    _kill_timer = threading.Timer(remaining, _kill_pipeline, [pid])
    _kill_timer.daemon = True
    _kill_timer.start()
    logger.info(f"Kill timer restored: PID={pid}, {remaining:.0f}s remaining")


def _load_pipeline_state():
    try:
        if _PIPELINE_STATE_FILE.exists():
            data = json.loads(_PIPELINE_STATE_FILE.read_text())
            _pipeline.update(data)
            _schedule_kill_timer()
    except Exception as e:
        logger.warning(f"Failed to load pipeline state: {e}")


# Restore state from disk on module load
_load_pipeline_state()


def _is_pid_alive(pid):
    if pid is None:
        return False
    try:
        import psutil
        return psutil.pid_exists(pid) and psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except (ImportError, psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    # Fallback if psutil unavailable
    try:
        if os.name == "nt":
            r = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
            return bool(re.search(rf"\b{re.escape(str(pid))}\b", r.stdout))
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False


def _fetch_all(query: str, params: tuple = ()):
    return select(query, params)


def _fetch_one(query: str, params: tuple = ()):
    return select_one(query, params)


def _execute(query: str, params: tuple = ()):
    get_db_manager().execute_query(query, params)


@router.get("/status")
def get_status():
    row = _fetch_one("SELECT * FROM pipeline_status ORDER BY id DESC LIMIT 1")
    mode = None
    try:
        if _PIPELINE_STATE_FILE.exists():
            _st = json.loads(_PIPELINE_STATE_FILE.read_text())
            mode = _st.get("mode")
    except Exception:
        pass
    if not row:
        return {"status": "IDLE", "phase": "System idle", "mode": mode}
    return {
        "status": row.get("status", "IDLE"),
        "phase": row.get("phase", ""),
        "mode": mode,
        "current_specialist": row.get("current_specialist", ""),
        "current_model": row.get("current_model", ""),
        "current_cycle": row.get("current_cycle", 0),
        "total_cycles": row.get("total_cycles", 0),
        "elapsed_seconds": row.get("elapsed_seconds", 0),
        "cascade_entities": row.get("cascade_entities", 0),
        "cascade_max": row.get("cascade_max", 0),
        "start_epoch": row.get("start_epoch", 0),
        "updated_at": row.get("updated_at", ""),
    }


@router.get("/cascade/checkpoints")
def get_cascade_checkpoints(since_id: int = 0):
    """Return cascade checkpoint history for real-time monitoring charts.
    
    Auto-detects run restarts (--from-zero) via SQL self-join (no full table load).
    Only returns checkpoints from the latest run, unless since_id is specified.
    """
    if since_id <= 0:
        restart_row = _fetch_one("""
            SELECT c1.id FROM cascade_checkpoints c1
            JOIN cascade_checkpoints c2 ON c2.id = c1.id - 1
            WHERE c1.entities_processed < c2.entities_processed
            ORDER BY c1.id DESC LIMIT 1
        """)
        if restart_row:
            since_id = restart_row["id"] - 1

    if since_id > 0:
        rows = _fetch_all(
            "SELECT id, checkpoint_num, entities_processed, total_matches, "
            "elapsed_seconds, created_at "
            "FROM cascade_checkpoints WHERE id > ? ORDER BY id ASC",
            (since_id,)
        )
    else:
        last_id = _fetch_one("SELECT MAX(id) as mid FROM cascade_checkpoints")
        since_id = max(0, last_id["mid"] - 200) if last_id and last_id.get("mid") is not None else 0
        rows = _fetch_all(
            "SELECT id, checkpoint_num, entities_processed, total_matches, "
            "elapsed_seconds, created_at "
            "FROM cascade_checkpoints WHERE id > ? ORDER BY id ASC",
            (since_id,)
        )
    latest_entities = rows[-1]["entities_processed"] if rows else 0
    latest_id = rows[-1]["id"] if rows else 0
    return {
        "checkpoints": rows or [],
        "latest_entities": latest_entities,
        "latest_id": latest_id,
    }


@router.get("/cascade/per-specialist")
def get_cascade_per_specialist():
    """Return per-specialist match counts from cache table (fast)."""
    rows = _fetch_all(
        "SELECT specialist_id, domain, match_count "
        "FROM specialist_match_cache "
        "ORDER BY match_count DESC"
    )
    if rows:
        return {"matches": rows, "cached": True}
    return {"matches": [], "cached": False, "loading": True}


@router.get("/specialists")
def get_specialists():
    rows = _fetch_all(
        "SELECT id, domain, model, root_qid, ema_score, tier, packages_absorbed, "
        "COALESCE(weighted_fail, 0) as weighted_fail, "
        "status, parent_id, qid_path, created_at, updated_at "
        "FROM specialist_registry ORDER BY parent_id IS NOT NULL, COALESCE(parent_id,id), domain"
    )

    # Batched: rolling 25-cycle failures (knowledge only) + total per specialist
    ch_raw = _fetch_all(
        "SELECT specialist_id, success, failure_type FROM ("
        "  SELECT specialist_id, success, failure_type, "
        "  ROW_NUMBER() OVER (PARTITION BY specialist_id ORDER BY id DESC) as rn "
        "  FROM cycle_history"
        ") WHERE rn <= 25 ORDER BY specialist_id, rn"
    )
    racha_map = {}
    fail_map = {}
    for r in ch_raw:
        sid = r["specialist_id"]
        if sid not in racha_map:
            racha_map[sid] = []
            fail_map[sid] = 0
        racha_map[sid].append(r["success"])
        if r["success"] == 0 and r.get("failure_type", "knowledge") == "knowledge":
            fail_map[sid] += 1

    # Batched: total cycle count per specialist (ALL-TIME, for display only)
    ch_totals = _fetch_all(
        "SELECT specialist_id, COUNT(*) as total FROM cycle_history GROUP BY specialist_id"
    )
    ch_total_map = {r["specialist_id"]: r["total"] for r in ch_totals}

    # Batched: ema_history counts for fallback (specialists without cycle_history)
    ema_agg = _fetch_all(
        "SELECT specialist_id, COUNT(*) as cnt FROM ema_history GROUP BY specialist_id"
    )
    ema_map = {r["specialist_id"]: r["cnt"] for r in ema_agg}

    # Batched: avg quality over last 50 cycles per specialist (server-side aggregate)
    qual_agg = _fetch_all(
        "SELECT specialist_id, AVG(quality) as avg_q, MAX(quality) as max_q, "
        "MIN(quality) as min_q FROM ("
        "  SELECT specialist_id, quality, success, "
        "  ROW_NUMBER() OVER (PARTITION BY specialist_id ORDER BY id DESC) as rn "
        "  FROM cycle_history WHERE success=1"
        ") WHERE rn <= 50 GROUP BY specialist_id"
    )
    qual_map = {r["specialist_id"]: r for r in qual_agg}

    for r in rows:
        tier = r.get("tier", 0) or 0
        r["is_reliable"] = 1 if tier >= 1 else 0
        sid = r["id"]

        successes = racha_map.get(sid, [])
        if successes:
            total = len(successes)
            fails = fail_map.get(sid, 0)
            racha_25 = sum(1 for s in successes if s) / total if total > 0 else 0.0
            r["fail_rate"] = round(fails / total, 4)  # rolling 25, knowledge only
            r["racha_25"] = round(racha_25, 4)
            r["total_cycles"] = ch_total_map.get(sid, 0)
            r["failures"] = fails
        else:
            total = ema_map.get(sid, 0)
            wf = r.get("weighted_fail", 0)
            r["fail_rate"] = round(wf / max(total, 1), 4) if total > 0 else 0
            r["racha_25"] = 0.0
            r["total_cycles"] = total
            r["failures"] = int(wf)

        q = qual_map.get(sid)
        if q:
            r["avg_quality"] = round(q["avg_q"], 3)
            r["max_quality"] = round(q["max_q"], 3)
            r["min_quality"] = round(q["min_q"], 3)
        else:
            r["avg_quality"] = 0.0
            r["max_quality"] = 0.0
            r["min_quality"] = 0.0

    return {"specialists": rows}


@router.get("/activity-log")
def get_activity_log(
    limit: int = Query(50, ge=1, le=500),
    levels: Optional[str] = Query(None, description="Comma-separated levels"),
):
    if levels:
        level_list = [l.strip() for l in levels.split(",") if l.strip()]
        placeholders = ",".join("?" for _ in level_list)
        rows = _fetch_all(
            f"SELECT id, timestamp, level, message FROM activity_log "
            f"WHERE level IN ({placeholders}) ORDER BY id DESC LIMIT ?",
            (*level_list, limit),
        )
    else:
        rows = _fetch_all(
            "SELECT id, timestamp, level, message FROM activity_log ORDER BY id DESC LIMIT ?",
            (limit,),
        )
    return {"logs": rows}


@router.get("/super-experts")
def get_super_experts():
    rows = _fetch_all(
        "SELECT se.id, se.domain, se.description, "
        "COUNT(sem.id) AS member_count, "
        "AVG(s.ema_score) AS avg_ema, "
        "CASE WHEN SUM(sem.weight) > 0 THEN SUM(s.packages_absorbed * sem.weight) / SUM(sem.weight) ELSE 0 END AS weighted_ema, "
        "COALESCE(SUM(s.packages_absorbed), 0) AS total_packages "
        "FROM super_experts se "
        "LEFT JOIN super_expert_members sem ON sem.super_expert_id = se.id "
        "LEFT JOIN specialist_registry s ON s.id = sem.specialist_id "
        "GROUP BY se.id ORDER BY se.domain"
    )
    # Batch fetch all members in one query instead of N+1
    all_members = _fetch_all(
        "SELECT sem.super_expert_id, s.domain, s.ema_score, s.packages_absorbed, s.status, sem.weight "
        "FROM super_expert_members sem "
        "JOIN specialist_registry s ON s.id = sem.specialist_id "
        "ORDER BY sem.weight DESC"
    )
    # Group members by super_expert_id
    members_by_se = {}
    for m in all_members:
        se_id = m["super_expert_id"]
        if se_id not in members_by_se:
            members_by_se[se_id] = []
        members_by_se[se_id].append({k: v for k, v in m.items() if k != "super_expert_id"})
    for se in rows:
        se["members"] = members_by_se.get(se["id"], [])
    return {"super_experts": rows}


@router.get("/analytics/overview")
def get_analytics_overview():
    """Métricas agregadas y de progreso en tiempo real para el dashboard unificado."""
    # Estado del pipeline
    prow = _fetch_one("SELECT * FROM pipeline_status ORDER BY id DESC LIMIT 1")
    status = prow.get("status", "IDLE") if prow else "IDLE"
    phase = prow.get("phase", "") if prow else ""
    model = prow.get("current_model", "") if prow else ""
    spec = prow.get("current_specialist", "") if prow else ""

    # Throughput de las últimas horas (cycle_history agregado por hora)
    last_24 = _fetch_all(
        "SELECT strftime('%Y-%m-%d %H:00:00', timestamp) AS bucket, "
        "COUNT(*) AS cycles, "
        "SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) AS succ "
        "FROM cycle_history WHERE timestamp > datetime('now','-24 hours') "
        "GROUP BY bucket ORDER BY bucket"
    )

    # Delta EMA por especialista (últimas 24h)
    ema_deltas = _fetch_all(
        "SELECT h.specialist_id, s.domain, s.model, s.ema_score AS current_ema,"
        " (SELECT ema_score FROM ema_history eh WHERE eh.specialist_id = h.specialist_id "
        "  AND eh.timestamp < datetime('now','-24 hours') ORDER BY eh.timestamp DESC LIMIT 1) AS ema_24h_ago "
        "FROM ema_history h JOIN specialist_registry s ON s.id = h.specialist_id "
        "WHERE h.timestamp > datetime('now','-1 hour') "
        "GROUP BY h.specialist_id"
    )

    # Distribución de estados
    states = _fetch_all("SELECT status, COUNT(*) AS cnt FROM specialist_registry GROUP BY status")
    tier_counts = _fetch_all("SELECT tier, COUNT(*) AS cnt FROM specialist_registry GROUP BY tier")

    # Incidentes recientes (errores en activity_log últimas 24h)
    incidents = _fetch_one(
        "SELECT COUNT(*) AS cnt FROM activity_log WHERE level IN ('ERROR','CRITICAL') "
        "AND timestamp > datetime('now','-24 hours')"
    )

    return {
        "status": status,
        "phase": phase,
        "current_model": model,
        "current_specialist": spec,
        "throughput": last_24,
        "ema_deltas": ema_deltas,
        "specialist_states": states,
        "tier_counts": tier_counts,
        "incidents_24h": incidents["cnt"] if incidents else 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/analytics/insights")
def get_insights():
    """ETA predictions to Legend, health alerts, and model comparison."""
    LEGEND_MIN = 0.995

    # --- EMA velocity per specialist (last 7 days) ---
    vel_rows = _fetch_all("""
        SELECT s.id, s.domain, s.ema_score, s.tier, s.model,
               (SELECT ema_score FROM ema_history eh
                WHERE eh.specialist_id = s.id AND eh.timestamp <= datetime('now','-7 days')
                ORDER BY eh.timestamp DESC LIMIT 1) AS ema_7d_ago
        FROM specialist_registry s ORDER BY s.ema_score DESC
    """)

    predictions = []
    for r in vel_rows:
        ema = r["ema_score"] or 0
        ema_old = r["ema_7d_ago"]
        if ema_old and ema_old > 0.5:
            velocity = (ema - ema_old) / 7.0  # per day
        else:
            velocity = 0.001  # assume slow climb if no history
        gap = LEGEND_MIN - ema
        if gap <= 0:
            eta = 0  # already Legend-eligible on EMA
        elif velocity > 0:
            eta = gap / velocity  # days to reach threshold
        else:
            eta = 999  # not climbing
        predictions.append({
            "specialist_id": r["id"],
            "domain": r["domain"],
            "model": r["model"],
            "tier": r["tier"],
            "ema": round(ema, 4),
            "velocity_per_day": round(velocity, 5),
            "eta_days": round(eta, 1) if eta < 999 else None,
            "eligible_now": gap <= 0 and r["tier"] < 4,
        })

    # --- Health alerts ---
    alerts = []
    prow = _fetch_one("SELECT * FROM pipeline_status ORDER BY id DESC LIMIT 1")
    mode = None
    proc_alive = False
    start_epoch = prow.get("start_epoch") if prow else None
    try:
        if _PIPELINE_STATE_FILE.exists():
            _st = json.loads(_PIPELINE_STATE_FILE.read_text())
            mode = _st.get("mode")
            p_pid = _st.get("pid")
            proc_alive = bool(p_pid) and _is_pid_alive(p_pid)
            if not start_epoch:
                start_epoch = _st.get("start_time")
    except Exception:
        pass

    last_act = _fetch_one("SELECT timestamp, message FROM activity_log ORDER BY id DESC LIMIT 1")
    life_age_min = None
    if last_act and last_act.get("timestamp"):
        try:
            from datetime import datetime as _dt, timezone as _tz
            ts_raw = last_act["timestamp"]
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
                try:
                    dt = _dt.strptime(ts_raw.split(".")[0].replace("T", " ").replace("Z", ""), "%Y-%m-%d %H:%M:%S")
                    break
                except Exception:
                    continue
            else:
                dt = _dt.fromisoformat(ts_raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_tz.utc)
            life_age_min = (_dt.now(_tz.utc) - dt).total_seconds() / 60
        except Exception:
            pass

    elapsed_str = "--"
    if start_epoch and start_epoch > 0:
        el = time.time() - float(start_epoch)
        if el < 0:
            el = 0
        if _st and _st.get("start_time"):
            try:
                alt_el = time.time() - float(_st.get("start_time"))
                if alt_el > el:
                    el = alt_el
            except Exception:
                pass
        h, rem = int(el // 3600), int(el % 3600)
        m = int(rem // 60)
        elapsed_str = f"{h}h {m:02d}m" if h else f"{m} min"

    cur = prow.get("current_specialist", "") if prow else ""
    mode_lbl = (mode or (prow.get("phase", "") or "pipeline") if prow else "pipeline").upper()
    if life_age_min is not None and life_age_min <= 5:
        alerts.append({"level": "info",
                       "msg": f"Pipeline activo · Modo {mode_lbl} · {elapsed_str} transcurridos · {cur or '—'}"})
    elif proc_alive:
        if life_age_min is not None and life_age_min > 30:
            alerts.append({"level": "warning",
                           "msg": f"Pipeline en modo {mode_lbl} sin actividad hace {int(life_age_min)} min (posible congelación) · {cur or '—'}"})
        else:
            alerts.append({"level": "info",
                           "msg": f"Pipeline activo · Modo {mode_lbl} · {elapsed_str} transcurridos · {cur or '—'}"})
    elif life_age_min is not None and life_age_min <= 30:
        alerts.append({"level": "warning",
                       "msg": f"Pipeline detenido — última actividad hace {int(life_age_min)} min"})
    else:
        alerts.append({"level": "error", "msg": "Pipeline detenido — sin actividad reciente"})

    # EMA dropping specialists (lost >0.005 in 7d)
    dropping = _fetch_all("""
        SELECT s.domain, s.ema_score,
               (SELECT ema_score FROM ema_history eh WHERE eh.specialist_id = s.id
                AND eh.timestamp <= datetime('now','-7 days') ORDER BY eh.timestamp DESC LIMIT 1) AS old
        FROM specialist_registry s
        WHERE old > 0.5 AND (s.ema_score - old) < -0.005
    """)
    for d in dropping:
        alerts.append({"level": "warning", "msg": f"{d['domain']} EMA cayó {d['old']-d['ema_score']:.4f} en 7d"})

    # Recent errors
    errs = _fetch_one("SELECT COUNT(*) AS cnt FROM activity_log WHERE level IN ('ERROR','CRITICAL') AND timestamp > datetime('now','-24 hours')")
    if errs and errs["cnt"] > 0:
        alerts.append({"level": "error", "msg": f"{errs['cnt']} errores en últimas 24h"})

    # --- Model comparison ---
    models = _fetch_all("""
        SELECT model,
               COUNT(*) AS specialists,
               ROUND(AVG(ema_score), 4) AS avg_ema,
               SUM(packages_absorbed) AS total_packages,
               (SELECT COUNT(*) FROM cycle_history ch JOIN specialist_registry sr2 ON sr2.id = ch.specialist_id
                WHERE sr2.model = s.model AND ch.timestamp > datetime('now','-7 days')) AS cycles_7d
        FROM specialist_registry s GROUP BY model ORDER BY AVG(ema_score) DESC
    """)

    return {
        "predictions": predictions,
        "alerts": alerts,
        "models": [{k: v for k, v in m.items()} for m in models],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/analytics/ema-history")
def get_ema_history(hours: int = Query(168, ge=1, le=720)):
    """Serie temporal de EMA por especialista para el gráfico multilínea en vivo."""
    rows = _fetch_all(
        "SELECT h.specialist_id, s.domain, h.ema_score, h.timestamp FROM ema_history h "
        "JOIN specialist_registry s ON s.id = h.specialist_id "
        "WHERE h.timestamp > datetime('now', '-' || ? || ' hours') ORDER BY h.timestamp",
        (hours,)
    )
    # Agrupar por especialista: mantener solo el último valor por minuto para reducir ruido
    series = {}
    order = []
    for r in rows:
        sid = r["specialist_id"]
        if sid not in series:
            series[sid] = {"domain": r["domain"], "points": []}
            order.append(sid)
        series[sid]["points"].append({"t": r["timestamp"], "e": r["ema_score"]})
    out = []
    for sid in order:
        out.append({"specialist_id": sid, "domain": series[sid]["domain"], "points": series[sid]["points"]})
    return {"series": out}


@router.get("/knowledge-stats")
def get_knowledge_stats():
    total = _fetch_one("SELECT MAX(id) AS cnt FROM knowledge_packages")
    by_domain = _fetch_all(
        "SELECT domain, SUM(packages_absorbed) AS cnt "
        "FROM specialist_registry "
        "WHERE packages_absorbed > 0 "
        "GROUP BY domain ORDER BY cnt DESC"
    )
    return {
        "total_packages": total["cnt"] if total else 0,
        "by_domain": by_domain if by_domain else [],
    }


@router.get("/knowledge/search")
def search_knowledge(q: str = "", domain: str = "", limit: int = 10):
    """Search knowledge packages by keyword (FTS5 or LIKE fallback)."""
    if not q or len(q.strip()) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")
    
    limit = min(max(limit, 1), 50)
    
    try:
        # Try FTS5 first
        keywords = [w for w in q.split() if len(w) >= 2][:5]
        fts_query = " OR ".join(keywords)
        if domain:
            rows = _fetch_all(
                """SELECT kp.topic, kp.structured_knowledge, kp.source_url, kp.domain, kp.created_at
                   FROM knowledge_packages_fts fts
                   JOIN knowledge_packages kp ON fts.rowid = kp.id
                   WHERE knowledge_packages_fts MATCH ? AND kp.domain = ?
                   ORDER BY rank LIMIT ?""",
                (fts_query, domain, limit)
            )
        else:
            rows = _fetch_all(
                """SELECT kp.topic, kp.structured_knowledge, kp.source_url, kp.domain, kp.created_at
                   FROM knowledge_packages_fts fts
                   JOIN knowledge_packages kp ON fts.rowid = kp.id
                   WHERE knowledge_packages_fts MATCH ?
                   ORDER BY rank LIMIT ?""",
                (fts_query, limit)
            )
    except Exception:
        # Fallback to LIKE search (id DESC ≈ recent-first, sin índice en created_at)
        like_pattern = f"%{q}%"
        if domain:
            rows = _fetch_all(
                """SELECT topic, structured_knowledge, source_url, domain, created_at
                   FROM knowledge_packages
                   WHERE (topic LIKE ? OR structured_knowledge LIKE ?) AND domain = ?
                   ORDER BY id DESC LIMIT ?""",
                (like_pattern, like_pattern, domain, limit)
            )
        else:
            rows = _fetch_all(
                """SELECT topic, structured_knowledge, source_url, domain, created_at
                   FROM knowledge_packages
                   WHERE topic LIKE ? OR structured_knowledge LIKE ?
                   ORDER BY id DESC LIMIT ?""",
                (like_pattern, like_pattern, limit)
            )
    
    return {"query": q, "domain": domain, "count": len(rows), "results": rows}


class StartPipelineRequest(BaseModel):
    phase: str = "full"
    specialist: str = "all"
    model: str = "all"
    duration: float = 5.0
    parallel: int = 1

    class Config:
        json_schema_extra = {"duration": {"gt": 0, "description": "Duration in hours (must be positive)"}}

    @field_validator("duration")
    @classmethod
    def _validate_duration(cls, v):
        if v is not None:
            import math
            if v <= 0 or math.isnan(v) or math.isinf(v):
                raise ValueError("duration must be a positive finite number")
        return v


@router.post("/pipeline/start", dependencies=[Depends(verify_api_key)])
def start_pipeline(req: StartPipelineRequest):
    with _pipeline_lock:
        if _pipeline["pid"] and _is_pid_alive(_pipeline["pid"]):
            raise HTTPException(status_code=409, detail="Pipeline already running")

        duration_hours = req.duration
        if req.phase == 'nurture':
            duration_hours = 99999  # nurture runs until manual stop

        cmd = [
            "python", "orchestrator.py",
            "--phase", req.phase,
            "--specialist", req.specialist,
            "--model", req.model,
            "--duration", str(duration_hours),
            "--max-duration", str(duration_hours),
            "--parallel", str(req.parallel),
        ]
        try:
            log_path = LOGS_DIR / f"orchestrator_{int(time.time())}.log"
            log_file = open(log_path, "w", encoding="utf-8")
            proc = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            log_file.close()  # Close parent fd; child keeps its copy via handle inheritance
            now = time.time()
            _pipeline["pid"] = proc.pid
            _pipeline["start_time"] = now
            _pipeline["duration_hours"] = duration_hours
            _pipeline["end_epoch"] = now + duration_hours * 3600

            if req.phase != 'nurture':
                _schedule_kill_timer()

            _save_pipeline_state()
            logger.info(f"Pipeline started PID={proc.pid} cmd={' '.join(cmd)}")
            kill_after_s = duration_hours * 3600
            logger.info(f"Kill timer set for {duration_hours}h ({kill_after_s}s)")
            return {"status": "started", "pid": proc.pid}
        except Exception as e:
            logger.error(f"Failed to start pipeline: {e}")
            raise HTTPException(status_code=500, detail=str(e))


def _kill_pipeline(pid: int):
    logger.warning(f"Kill timer fired — pipeline PID {pid} exceeded max duration")
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            os.kill(pid, 15)
        with _pipeline_lock:
            if _pipeline.get("pid") == pid:
                _pipeline["pid"] = None
                _pipeline["end_epoch"] = None
        _save_pipeline_state()
        logger.info(f"Pipeline PID={pid} force-killed by timer")
    except Exception as e:
        logger.error(f"Failed to kill pipeline PID={pid}: {e}")


@router.post("/pipeline/stop", dependencies=[Depends(verify_api_key)])
def stop_pipeline():
    with _pipeline_lock:
        pid = _pipeline.get("pid")
        if not pid or not _is_pid_alive(pid):
            _pipeline["pid"] = None
            _save_pipeline_state()
            raise HTTPException(status_code=404, detail="No running pipeline found")

        global _kill_timer
        if _kill_timer is not None:
            _kill_timer.cancel()
            _kill_timer = None

    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            os.kill(pid, 15)
        with _pipeline_lock:
            _pipeline["pid"] = None
            _pipeline["end_epoch"] = None
        _save_pipeline_state()
        logger.info(f"Pipeline PID={pid} stopped")
        return {"status": "stopped", "pid": pid}
    except Exception as e:
        logger.error(f"Failed to stop pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _get_pipeline_pid_info() -> dict:
    with _pipeline_lock:
        pid = _pipeline.get("pid")
        start_time = _pipeline.get("start_time", 0)
        duration_hours = _pipeline.get("duration_hours", 0)
        alive = _is_pid_alive(pid) if pid else False
        if not alive:
            _pipeline["pid"] = None
            _pipeline["end_epoch"] = None
    _save_pipeline_state()
    uptime = time.time() - start_time if start_time and alive else 0
    return {
        "pid": pid if alive else None,
        "alive": alive,
        "uptime_seconds": round(uptime),
        "duration_hours": duration_hours,
    }


@router.get("/pipeline/pid")
def get_pipeline_pid():
    return _get_pipeline_pid_info()


@router.get("/ollama/models")
def get_ollama_models():
    try:
        r = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )
        if r.returncode != 0:
            return {"models": []}
        lines = r.stdout.strip().split("\n")[1:]
        models = [line.split()[0] for line in lines if line.strip()]
        return {"models": models}
    except Exception as e:
        logger.warning(f"ollama list failed: {e}")
        return {"models": []}


class PullModelRequest(BaseModel):
    model: str


@router.post("/ollama/pull", dependencies=[Depends(verify_api_key)])
def pull_model(req: PullModelRequest):
    try:
        logger.info(f"Pulling model {req.model}...")
        r = subprocess.run(
            ["ollama", "pull", req.model],
            capture_output=True, text=True, timeout=600,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )
        if r.returncode != 0:
            raise HTTPException(status_code=500, detail=r.stderr.strip() or "Pull failed")
        return {"status": "pulled", "model": req.model}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ollama pull failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class SpecialistUpdateRequest(BaseModel):
    domain: str
    model: str


@router.patch("/specialists", dependencies=[Depends(verify_api_key)])
def update_specialist_model(req: SpecialistUpdateRequest):
    existing = _fetch_one(
        "SELECT id FROM specialist_registry WHERE domain = ?", (req.domain,)
    )
    if not existing:
        raise HTTPException(status_code=404, detail=f"Specialist '{req.domain}' not found")
    _execute(
        "UPDATE specialist_registry SET model = ?, updated_at = CURRENT_TIMESTAMP WHERE domain = ?",
        (req.model, req.domain),
    )
    logger.info(f"Specialist {req.domain} model updated to {req.model}")
    return {"status": "ok", "domain": req.domain, "model": req.model}


@router.get("/system/memory")
def get_system_memory():
    try:
        import psutil
        mem = psutil.virtual_memory()
        return {
            "total": mem.total,
            "available": mem.available,
            "percent": mem.percent,
            "used": mem.used,
            "free": mem.free,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except ImportError:
        return {"error": "psutil not installed"}


@router.get("/system/cpu")
def get_system_cpu():
    try:
        import psutil
        return {
            "percent": psutil.cpu_percent(interval=0.5),
            "count": psutil.cpu_count(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except ImportError:
        return {"error": "psutil not installed"}


@router.get("/health")
def get_health():
    specialist_count = _fetch_one("SELECT COUNT(*) AS cnt FROM specialist_registry")
    incident_count = _fetch_one(
        "SELECT COUNT(*) AS cnt FROM activity_log WHERE level IN ('ERROR','CRITICAL')"
    )
    last_activity = _fetch_one(
        "SELECT timestamp, level, message FROM activity_log ORDER BY id DESC LIMIT 1"
    )
    pkg_row = _fetch_one("SELECT SUM(packages_absorbed) AS s FROM specialist_registry")
    package_count = pkg_row["s"] if pkg_row and pkg_row["s"] else 0
    try:
        import shutil
        du = shutil.disk_usage(str(DATABASE_PATH.parent if 'DATABASE_PATH' in globals() else "E:/expertia-data"))
        disk_total_gb = round(du.total / (1024**3))
        disk_free_gb = round(du.free / (1024**3))
    except Exception:
        disk_total_gb = disk_free_gb = None
    return {
        "database": "ok",
        "last_activity": last_activity,
        "specialist_count": specialist_count["cnt"] if specialist_count else 0,
        "package_count": package_count,
        "incident_count": incident_count["cnt"] if incident_count else 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "disk_total_gb": disk_total_gb,
        "disk_free_gb": disk_free_gb,
        "disk": f"{disk_free_gb} GB libres / {disk_total_gb} GB" if disk_free_gb else "ok",
    }


class KillRateLimiter:
    """Rate limiter for /kill endpoint: max 3 kills per 10 minutes."""
    def __init__(self, max_calls: int = 3, window_seconds: int = 600):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.calls: list[float] = []
        self._lock = threading.Lock()

    def is_allowed(self) -> bool:
        now = time.time()
        with self._lock:
            self.calls = [t for t in self.calls if now - t < self.window_seconds]
            if len(self.calls) >= self.max_calls:
                return False
            self.calls.append(now)
            return True


_kill_limiter = KillRateLimiter()


@router.post("/kill", dependencies=[Depends(verify_api_key)])
def kill_all():
    if not _kill_limiter.is_allowed():
        raise HTTPException(status_code=429, detail="Kill limit exceeded (max 3 per 10 minutes)")
    # Stop pipeline first
    with _pipeline_lock:
        pid = _pipeline.get("pid")
        if pid and _is_pid_alive(pid):
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(pid)],
                        capture_output=True, timeout=5,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                else:
                    os.kill(pid, 15)
                logger.warning(f"Killed pipeline PID={pid} via kill-all")
            except Exception as e:
                logger.error(f"Failed to kill pipeline PID={pid}: {e}")
        _pipeline["pid"] = None
        _pipeline["end_epoch"] = None
    _save_pipeline_state()

    global _kill_timer
    if _kill_timer is not None:
        _kill_timer.cancel()
        _kill_timer = None

    # Kill monitor
    with _monitor_lock:
        mpid = _monitor_process.get("pid")
        if mpid and _is_pid_alive(mpid):
            try:
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(mpid)],
                        capture_output=True, timeout=5,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                else:
                    os.kill(mpid, 15)
                logger.warning(f"Killed monitor PID={mpid} via kill-all")
            except Exception as e:
                logger.error(f"Failed to kill monitor PID={mpid}: {e}")
        _monitor_process["pid"] = None
    if _MONITOR_PID_FILE.exists():
        _MONITOR_PID_FILE.unlink()

    # Graceful self-shutdown: PASSIVE checkpoint (non-blocking) + SIGTERM
    def _graceful_shutdown():
        try:
            import sqlite3 as _sq
            _conn = _sq.connect(DATABASE_PATH, timeout=5)
            _conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            _conn.close()
            logger.info("WAL checkpointed before shutdown")
        except Exception as e:
            logger.warning(f"WAL checkpoint skipped (non-fatal): {e}")
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Timer(0.5, _graceful_shutdown).start()
    logger.warning("Kill-all invoked — API shutting down gracefully in 0.5s")
    return {"status": "killed", "message": "All processes stopped. API shutting down."}


class SpawnRequest(BaseModel):
    qids: List[str]
    model: str


@router.get("/qualified-specialists")
def get_qualified():
    rows = select(
        "SELECT id, domain, model, root_qid, packages_absorbed, ema_score, "
        "weighted_success, weighted_fail "
        "FROM specialist_registry WHERE parent_id IS NULL "
        "AND packages_absorbed > 2500 AND ema_score > 0.95 "
        "ORDER BY packages_absorbed DESC"
    )
    return {"specialists": rows}


@router.get("/specialists/{specialist_id}/expansions")
def get_expansions(specialist_id: int):
    parent = select_one(
        "SELECT id, domain, root_qid FROM specialist_registry WHERE id=?",
        (specialist_id,)
    )
    if not parent:
        return {"expansions": []}
    rows = select(
        "SELECT qid FROM qid_expansions WHERE specialist_id=? ORDER BY discovered_at_checkpoint",
        (specialist_id,)
    )
    if not rows:
        return {"expansions": []}
    qids = [r['qid'] for r in rows]
    from tools.spawn_specialist import batch_resolve_labels, validate_qids, is_blocklisted_label
    labels = batch_resolve_labels(qids)
    validation = validate_qids(qids, parent['root_qid'])
    result = []
    for qid in qids:
        label = labels.get(qid, qid)
        result.append({
            'qid': qid,
            'label': label,
            'valid_p279': validation.get(qid, False),
            'blocklisted': is_blocklisted_label(label),
        })
    return {"expansions": result}


@router.post("/specialists/{specialist_id}/spawn", dependencies=[Depends(verify_api_key)])
async def spawn_specialists(specialist_id: int, req: SpawnRequest):
    db = get_db_manager()
    parent = db.execute_query(
        "SELECT id, domain FROM specialist_registry WHERE id=?", (specialist_id,), fetch=True
    )
    if not parent:
        raise HTTPException(status_code=404, detail="Specialist not found")

    async def event_stream():
        results = []
        total = len(req.qids)
        for i, qid in enumerate(req.qids):
            yield f"data: {json.dumps({'type': 'progress', 'qid': qid, 'current': i+1, 'total': total})}\n\n"
            await asyncio.sleep(0)
            result = spawn_child(db, specialist_id, qid, req.model,
                                 on_log=lambda lvl, msg: None)
            results.append({'qid': qid, **result})
            if result['success']:
                yield f"data: {json.dumps({'type': 'done', 'qid': qid, 'domain': result['domain']})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'qid': qid, 'error': result['error']})}\n\n"
        yield f"data: {json.dumps({'type': 'complete', 'results': results})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── MONITOR ENDPOINTS ─────────────────────────────────────────────────────────

def _try_restore_monitor_pid():
    with _monitor_lock:
        if _monitor_process.get("pid"):
            return
        if _MONITOR_PID_FILE.exists():
            try:
                raw = _MONITOR_PID_FILE.read_text().strip()
                pid = int(raw)
                if _is_pid_alive(pid):
                    _monitor_process["pid"] = pid
                    _monitor_process["start_time"] = _MONITOR_REPORT_FILE.stat().st_mtime if _MONITOR_REPORT_FILE.exists() else time.time()
                    logger.info(f"Restored monitor PID={pid}")
                else:
                    _MONITOR_PID_FILE.unlink()
            except Exception as e:
                logger.warning(f"Failed to restore monitor PID: {e}")


_try_restore_monitor_pid()


@router.post("/monitor/start", dependencies=[Depends(verify_api_key)])
def monitor_start():
    with _monitor_lock:
        if _monitor_process.get("pid") and _is_pid_alive(_monitor_process["pid"]):
            raise HTTPException(status_code=409, detail="Monitor already running")

        cmd = ["python", "tools/pipeline_monitor.py"]
        try:
            log_path = LOGS_DIR / f"monitor_{int(time.time())}.log"
            log_file = open(log_path, "w", encoding="utf-8")
            proc = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            log_file.close()
            _monitor_process["pid"] = proc.pid
            _monitor_process["start_time"] = time.time()
            _MONITOR_PID_FILE.write_text(str(proc.pid))
            logger.info(f"Monitor started PID={proc.pid}")
            return {"status": "started", "pid": proc.pid}
        except Exception as e:
            logger.error(f"Failed to start monitor: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@router.post("/monitor/stop", dependencies=[Depends(verify_api_key)])
def monitor_stop():
    with _monitor_lock:
        pid = _monitor_process.get("pid")
        if not pid or not _is_pid_alive(pid):
            _monitor_process["pid"] = None
            raise HTTPException(status_code=404, detail="No monitor running")

    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=5,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            os.kill(pid, 15)
        with _monitor_lock:
            _monitor_process["pid"] = None
        _MONITOR_PID_FILE.unlink(missing_ok=True)
        logger.info(f"Monitor PID={pid} stopped")
        return {"status": "stopped", "pid": pid}
    except Exception as e:
        logger.error(f"Failed to stop monitor PID={pid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/monitor/status")
def monitor_status():
    with _monitor_lock:
        pid = _monitor_process.get("pid")
        start_time = _monitor_process.get("start_time", 0)
        alive = _is_pid_alive(pid) if pid else False
        if not alive:
            _monitor_process["pid"] = None

    reports = []
    if _MONITOR_REPORT_FILE.exists():
        try:
            data = json.loads(_MONITOR_REPORT_FILE.read_text())
            reports = data if isinstance(data, list) else [data]
        except Exception as e:
            logger.warning("Failed to load monitor reports: %s", e)

    return {
        "alive": alive,
        "pid": pid if alive else None,
        "started_at": datetime.fromtimestamp(start_time).isoformat() if start_time else None,
        "uptime_seconds": int(time.time() - start_time) if start_time and alive else 0,
        "reports": reports[-5:],
    }


@router.post("/admin/cleanup", dependencies=[Depends(verify_api_key)])
def admin_cleanup():
    """Manually purge activity_log and ema_history older than 90 days."""
    try:
        conn = sqlite3.connect(DATABASE_PATH, timeout=30)
        a = conn.execute("DELETE FROM activity_log WHERE timestamp < datetime('now', '-90 days')").rowcount
        e = conn.execute("DELETE FROM ema_history WHERE timestamp < datetime('now', '-90 days')").rowcount
        conn.commit()
        remaining_a = conn.execute("SELECT COUNT(*) FROM activity_log").fetchone()[0]
        remaining_e = conn.execute("SELECT COUNT(*) FROM ema_history").fetchone()[0]
        conn.close()
        return {
            "status": "ok",
            "purged": {"activity_log": a, "ema_history": e},
            "remaining": {"activity_log": remaining_a, "ema_history": remaining_e},
        }
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


@router.get("/stream")
async def sse_dashboard(request: Request):
    """SSE endpoint that pushes full dashboard state every 5 seconds.
    Cleans up automatically when the client disconnects."""
    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    logger.info("SSE client disconnected — stopping stream")
                    break
                try:
                    snapshot = await asyncio.to_thread(_build_dashboard_snapshot)
                    yield f"data: {json.dumps(snapshot)}\n\n"
                except Exception as e:
                    logger.error(f"SSE error: {e}")
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
                await asyncio.sleep(5)
        except GeneratorExit:
            logger.info("SSE stream closed by client")
            raise
        finally:
            logger.debug(f"SSE stream ended for {request.client.host if request.client else 'unknown'}")

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _build_dashboard_snapshot() -> dict:
    """Build a single snapshot of all dashboard data."""
    return {
        "specialists": _fetch_all(
            "SELECT id, domain, model, root_qid, ema_score, tier, packages_absorbed, "
            "COALESCE(weighted_fail, 0) as weighted_fail, "
            "status, parent_id, qid_path, created_at, updated_at "
            "FROM specialist_registry ORDER BY parent_id IS NOT NULL, COALESCE(parent_id,id), domain"
        ) or [],
        "status": _fetch_one("SELECT * FROM pipeline_status ORDER BY id DESC LIMIT 1"),
        "health": {
            "database": "ok",
            "specialist_count": (_fetch_one("SELECT COUNT(*) AS cnt FROM specialist_registry") or {}).get("cnt", 0),
            "incident_count": (_fetch_one("SELECT COUNT(*) AS cnt FROM activity_log WHERE level IN ('ERROR','CRITICAL')") or {}).get("cnt", 0),
            "last_activity": _fetch_one("SELECT timestamp, level, message FROM activity_log ORDER BY id DESC LIMIT 1"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }


@router.get("/dashboard")
def get_dashboard():
    """Batch endpoint returning all dashboard data in one call."""
    snapshot = _build_dashboard_snapshot()
    snapshot["activity_log"] = _fetch_all("SELECT id, timestamp, level, message FROM activity_log ORDER BY id DESC LIMIT 1") or []
    snapshot["pipeline_pid"] = _get_pipeline_pid_info()
    return snapshot
