import json
import logging
import os
import re
import subprocess
import time
from threading import Lock
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from database.db_manager import get_db_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

_PIPELINE_STATE_FILE = Path(__file__).parent / "pipeline_state.json"

_pipeline: dict = {"pid": None, "start_time": 0, "duration_hours": 0}
_pipeline_lock = Lock()

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
EXPERTIA_API_KEY = os.environ.get("EXPERTIA_API_KEY", "")


def verify_api_key(x_api_key: Optional[str] = Security(_api_key_header)):
    if EXPERTIA_API_KEY and x_api_key != EXPERTIA_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return x_api_key


def _save_pipeline_state():
    try:
        _PIPELINE_STATE_FILE.write_text(json.dumps(_pipeline))
    except Exception as e:
        logger.warning(f"Failed to save pipeline state: {e}")


def _load_pipeline_state():
    try:
        if _PIPELINE_STATE_FILE.exists():
            data = json.loads(_PIPELINE_STATE_FILE.read_text())
            _pipeline.update(data)
    except Exception as e:
        logger.warning(f"Failed to load pipeline state: {e}")


# Restore state from disk on module load
_load_pipeline_state()


def _is_pid_alive(pid):
    if pid is None:
        return False
    try:
        if os.name == "nt":
            r = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True, timeout=5,
            )
            return bool(re.search(rf"\b{re.escape(str(pid))}\b", r.stdout))
        else:
            os.kill(pid, 0)
            return True
    except Exception:
        return False

UTC_OFFSET = timedelta(hours=2)


def _db():
    return get_db_manager()


def _fetch_all(query: str, params: tuple = ()):
    return _db().execute_query(query, params, fetch=True) or []


def _fetch_one(query: str, params: tuple = ()):
    rows = _db().execute_query(query, params, fetch=True)
    return rows[0] if rows else None


def _execute(query: str, params: tuple = ()):
    _db().execute_query(query, params)
    _db()._get_connection().commit()


@router.get("/status")
def get_status():
    row = _fetch_one("SELECT * FROM pipeline_status ORDER BY id DESC LIMIT 1")
    if not row:
        return {"status": "IDLE", "phase": "System idle"}
    return {
        "status": row.get("status", "IDLE"),
        "phase": row.get("phase", ""),
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


@router.get("/specialists")
def get_specialists():
    rows = _fetch_all(
        "SELECT id, domain, model, root_qid, ema_score, tier, packages_absorbed, "
        "status, parent_id, qid_path, created_at, updated_at "
        "FROM specialist_registry ORDER BY parent_id IS NOT NULL, COALESCE(parent_id,id), domain"
    )
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
    for se in rows:
        se["members"] = _fetch_all(
            "SELECT s.domain, s.ema_score, s.packages_absorbed, s.status, sem.weight "
            "FROM super_expert_members sem "
            "JOIN specialist_registry s ON s.id = sem.specialist_id "
            "WHERE sem.super_expert_id = ? ORDER BY sem.weight DESC",
            (se["id"],),
        )
    return {"super_experts": rows}


@router.get("/knowledge-stats")
def get_knowledge_stats():
    total = _fetch_one("SELECT COUNT(*) AS cnt FROM knowledge_packages")
    by_domain = _fetch_all(
        "SELECT COALESCE(domain, 'unknown') AS domain, COUNT(*) AS cnt "
        "FROM knowledge_packages GROUP BY domain ORDER BY cnt DESC"
    )
    return {
        "total_packages": total["cnt"] if total else 0,
        "by_domain": by_domain,
    }


class StartPipelineRequest(BaseModel):
    phase: str = "full"
    specialist: str = "all"
    model: str = "all"
    duration: float = 5.0


@router.post("/pipeline/start", dependencies=[Depends(verify_api_key)])
def start_pipeline(req: StartPipelineRequest):
    with _pipeline_lock:
        if _pipeline["pid"] and _is_pid_alive(_pipeline["pid"]):
            raise HTTPException(status_code=409, detail="Pipeline already running")

    cmd = [
        "python", "orchestrator.py",
        "--phase", req.phase,
        "--specialist", req.specialist,
        "--model", req.model,
        "--duration", str(req.duration),
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0,
        )
        with _pipeline_lock:
            _pipeline["pid"] = proc.pid
            _pipeline["start_time"] = time.time()
            _pipeline["duration_hours"] = req.duration
        _save_pipeline_state()
        logger.info(f"Pipeline started PID={proc.pid} cmd={' '.join(cmd)}")
        return {"status": "started", "pid": proc.pid}
    except Exception as e:
        logger.error(f"Failed to start pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pipeline/stop", dependencies=[Depends(verify_api_key)])
def stop_pipeline():
    with _pipeline_lock:
        pid = _pipeline.get("pid")
        if not pid or not _is_pid_alive(pid):
            _pipeline["pid"] = None
            _save_pipeline_state()
            raise HTTPException(status_code=404, detail="No running pipeline found")

    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True, timeout=5,
            )
        else:
            os.kill(pid, 15)
        with _pipeline_lock:
            _pipeline["pid"] = None
        _save_pipeline_state()
        logger.info(f"Pipeline PID={pid} stopped")
        return {"status": "stopped", "pid": pid}
    except Exception as e:
        logger.error(f"Failed to stop pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pipeline/pid")
def get_pipeline_pid():
    with _pipeline_lock:
        pid = _pipeline.get("pid")
        start_time = _pipeline.get("start_time", 0)
        duration_hours = _pipeline.get("duration_hours", 0)
    alive = _is_pid_alive(pid) if pid else False
    if not alive:
        with _pipeline_lock:
            _pipeline["pid"] = None
        _save_pipeline_state()
    uptime = time.time() - start_time if start_time and alive else 0
    return {
        "pid": pid if alive else None,
        "alive": alive,
        "uptime_seconds": round(uptime),
        "duration_hours": duration_hours,
    }


@router.get("/ollama/models")
def get_ollama_models():
    try:
        r = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=10,
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
            "timestamp": datetime.utcnow().isoformat(),
        }
    except ImportError:
        return {"error": "psutil not installed"}


@router.get("/health")
def get_health():
    db_ok = _db().health_check()
    last_activity = _fetch_one(
        "SELECT timestamp, level, message FROM activity_log ORDER BY id DESC LIMIT 1"
    )
    specialist_count = (
        _fetch_one("SELECT COUNT(*) AS cnt FROM specialist_registry") or {}
    ).get("cnt", 0)
    package_count = (
        _fetch_one("SELECT COUNT(*) AS cnt FROM knowledge_packages") or {}
    ).get("cnt", 0)
    incident_count = (
        _fetch_one(
            "SELECT COUNT(*) AS cnt FROM activity_log WHERE level IN ('ERROR','CRITICAL')"
        )
        or {}
    ).get("cnt", 0)
    return {
        "database": "ok" if db_ok else "error",
        "last_activity": last_activity,
        "specialist_count": specialist_count,
        "package_count": package_count,
        "incident_count": incident_count,
        "timestamp": datetime.utcnow().isoformat(),
    }
