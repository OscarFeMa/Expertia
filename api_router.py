import json
import logging
import os
import re
import subprocess
import time
import asyncio
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from database.db_manager import DatabaseManager, get_db_manager
from tools.spawn_specialist import spawn_child, get_expansions_for_specialist, get_qualified_specialists

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

_PIPELINE_STATE_FILE = Path(__file__).parent / "pipeline_state.json"
_WIKIDATA_PID_FILE = Path(__file__).parent.parent / "storage" / "wikidata_download.pid"
_WIKIDATA_PROGRESS_FILE = Path(__file__).parent.parent / "storage" / "wikidata_progress.json"

_pipeline: dict = {"pid": None, "start_time": 0, "duration_hours": 0}
_pipeline_lock = threading.Lock()
_kill_timer: Optional[threading.Timer] = None

_wikidata_process: dict = {"pid": None, "type": None, "start_time": 0}
_wikidata_lock = threading.Lock()

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


def _try_restore_wikidata_pid():
    if _wikidata_process.get("pid"):
        return
    try:
        if _WIKIDATA_PID_FILE.exists():
            raw = _WIKIDATA_PID_FILE.read_text().strip()
            pid = int(raw)
            if _is_pid_alive(pid):
                _wikidata_process["pid"] = pid
                _wikidata_process["type"] = "download"
                _wikidata_process["start_time"] = _WIKIDATA_PROGRESS_FILE.stat().st_mtime if _WIKIDATA_PROGRESS_FILE.exists() else time.time()
                logger.info(f"Restored wikidata download PID={pid}")
            else:
                _WIKIDATA_PID_FILE.unlink()
                logger.info(f"Cleaned stale wikidata PID file (PID={pid} no longer alive)")
    except Exception as e:
        logger.warning(f"Failed to restore wikidata PID: {e}")


_try_restore_wikidata_pid()


def _is_pid_alive(pid):
    if pid is None:
        return False
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
        "COALESCE(weighted_fail, 0) as weighted_fail, "
        "status, parent_id, qid_path, created_at, updated_at "
        "FROM specialist_registry ORDER BY parent_id IS NOT NULL, COALESCE(parent_id,id), domain"
    )

    # Batched: cycle_history aggregates for ALL specialists (1 query)
    ch_agg = _fetch_all(
        "SELECT specialist_id, COUNT(*) as total, "
        "SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) as fails "
        "FROM cycle_history GROUP BY specialist_id"
    )
    ch_map = {r["specialist_id"]: r for r in ch_agg}

    # Batched: racha_25 (last 25 per specialist) via window function (1 query)
    ch_raw = _fetch_all(
        "SELECT specialist_id, success FROM ("
        "  SELECT specialist_id, success, "
        "  ROW_NUMBER() OVER (PARTITION BY specialist_id ORDER BY id DESC) as rn "
        "  FROM cycle_history"
        ") WHERE rn <= 25 ORDER BY specialist_id, rn"
    )
    racha_map = {}
    for r in ch_raw:
        sid = r["specialist_id"]
        if sid not in racha_map:
            racha_map[sid] = []
        racha_map[sid].append(r["success"])

    # Batched: ema_history counts for fallback (specialists without cycle_history)
    ema_agg = _fetch_all(
        "SELECT specialist_id, COUNT(*) as cnt FROM ema_history GROUP BY specialist_id"
    )
    ema_map = {r["specialist_id"]: r["cnt"] for r in ema_agg}

    for r in rows:
        tier = r.get("tier", 0) or 0
        r["is_reliable"] = 1 if tier >= 1 else 0
        sid = r["id"]

        if sid in ch_map:
            total = ch_map[sid]["total"]
            fails = ch_map[sid]["fails"] or 0
            successes = racha_map.get(sid, [])
            racha_25 = sum(1 for s in successes if s) / len(successes) if successes else 0.0
            r["fail_rate"] = round(fails / total, 4)
            r["racha_25"] = round(racha_25, 4)
            r["total_cycles"] = total
            r["failures"] = fails
        else:
            total = ema_map.get(sid, 0)
            wf = r.get("weighted_fail", 0)
            r["fail_rate"] = round(wf / max(total, 1), 4) if total > 0 else 0
            r["racha_25"] = 0.0
            r["total_cycles"] = total
            r["failures"] = int(wf)

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
                   ORDER BY kp.created_at DESC LIMIT ?""",
                (fts_query, domain, limit)
            )
        else:
            rows = _fetch_all(
                """SELECT kp.topic, kp.structured_knowledge, kp.source_url, kp.domain, kp.created_at
                   FROM knowledge_packages_fts fts
                   JOIN knowledge_packages kp ON fts.rowid = kp.id
                   WHERE knowledge_packages_fts MATCH ?
                   ORDER BY kp.created_at DESC LIMIT ?""",
                (fts_query, limit)
            )
    except Exception:
        # Fallback to LIKE search
        like_pattern = f"%{q}%"
        if domain:
            rows = _fetch_all(
                """SELECT topic, structured_knowledge, source_url, domain, created_at
                   FROM knowledge_packages
                   WHERE (topic LIKE ? OR structured_knowledge LIKE ?) AND domain = ?
                   ORDER BY created_at DESC LIMIT ?""",
                (like_pattern, like_pattern, domain, limit)
            )
        else:
            rows = _fetch_all(
                """SELECT topic, structured_knowledge, source_url, domain, created_at
                   FROM knowledge_packages
                   WHERE topic LIKE ? OR structured_knowledge LIKE ?
                   ORDER BY created_at DESC LIMIT ?""",
                (like_pattern, like_pattern, limit)
            )
    
    return {"query": q, "domain": domain, "count": len(rows), "results": rows}


class StartPipelineRequest(BaseModel):
    phase: str = "full"
    specialist: str = "all"
    model: str = "all"
    duration: float = 5.0


class WikidataDownloadRequest(BaseModel):
    phase: str = "incremental"


@router.post("/pipeline/start", dependencies=[Depends(verify_api_key)])
def start_pipeline(req: StartPipelineRequest):
    with _pipeline_lock:
        if _pipeline["pid"] and _is_pid_alive(_pipeline["pid"]):
            raise HTTPException(status_code=409, detail="Pipeline already running")

        duration_hours = req.duration
        if req.phase == 'nurture':
            duration_hours = 99999  # nurture runs until manual stop

        cmd = [
            "pythonw", "orchestrator.py",
            "--phase", req.phase,
            "--specialist", req.specialist,
            "--model", req.model,
            "--duration", str(duration_hours),
            "--max-duration", str(duration_hours),
        ]
        try:
            proc = subprocess.Popen(
                cmd,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
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
            _pipeline["end_epoch"] = None
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
            "timestamp": datetime.utcnow().isoformat(),
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
            "timestamp": datetime.utcnow().isoformat(),
        }
    except ImportError:
        return {"error": "psutil not installed"}


@router.get("/health")
def get_health():
    db_ok = _db().health_check()
    # Single query for all counts instead of 5 separate queries
    stats = _fetch_one(
        "SELECT "
        "(SELECT COUNT(*) FROM specialist_registry) AS specialist_count, "
        "(SELECT COUNT(*) FROM knowledge_packages) AS package_count, "
        "(SELECT COUNT(*) FROM activity_log WHERE level IN ('ERROR','CRITICAL')) AS incident_count"
    )
    last_activity = _fetch_one(
        "SELECT timestamp, level, message FROM activity_log ORDER BY id DESC LIMIT 1"
    )
    return {
        "database": "ok" if db_ok else "error",
        "last_activity": last_activity,
        "specialist_count": stats.get("specialist_count", 0) if stats else 0,
        "package_count": stats.get("package_count", 0) if stats else 0,
        "incident_count": stats.get("incident_count", 0) if stats else 0,
        "timestamp": datetime.utcnow().isoformat(),
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

    # Schedule self-destruct (kill the API process after responding)
    def _suicide():
        import os as _os
        _os._exit(0)

    threading.Timer(0.5, _suicide).start()
    logger.warning("Kill-all invoked — API shutting down in 0.5s")
    return {"status": "killed", "message": "All processes stopped. API shutting down."}


class SpawnRequest(BaseModel):
    qids: List[str]
    model: str


@router.get("/qualified-specialists")
def get_qualified():
    db = get_db_manager()
    return {"specialists": get_qualified_specialists(db)}


@router.get("/specialists/{specialist_id}/expansions")
def get_expansions(specialist_id: int):
    db = get_db_manager()
    expansions = get_expansions_for_specialist(db, specialist_id)
    return {"expansions": expansions}


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


# ── WIKIDATA FEED ENDPOINTS ──────────────────────────────────────────────────

@router.get("/wikidata/status")
def wikidata_status():
    db = get_db_manager()
    pending_by_domain = db.execute_query(
        """SELECT domain, COUNT(*) AS cnt
           FROM knowledge_packages
           WHERE qid IS NOT NULL AND absorbed_at IS NULL
           GROUP BY domain ORDER BY cnt DESC""",
        fetch=True
    )
    last_download = db.execute_query(
        "SELECT MAX(last_wikidata_download) AS ts FROM specialist_registry",
        fetch=True
    )
    last_feed = db.execute_query(
        "SELECT MAX(last_wikidata_feed) AS ts FROM specialist_registry",
        fetch=True
    )

    now = datetime.utcnow()
    dl_ts = last_download[0]['ts'] if last_download and last_download[0]['ts'] else None
    feed_ts = last_feed[0]['ts'] if last_feed and last_feed[0]['ts'] else None

    def hours_since(ts_str):
        if not ts_str:
            return None
        try:
            dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00').replace(' ', 'T'))
            return (now - dt).total_seconds() / 3600
        except:
            return None

    dl_hours = hours_since(dl_ts)
    feed_hours = hours_since(feed_ts)

    total_pending = sum(r['cnt'] for r in (pending_by_domain or []))

    with _wikidata_lock:
        dl_running = bool(_wikidata_process.get("pid") and _is_pid_alive(_wikidata_process["pid"]))

    total_downloaded = db.execute_query(
        "SELECT COUNT(*) AS cnt FROM knowledge_packages WHERE qid IS NOT NULL",
        fetch=True
    )
    total_downloaded = total_downloaded[0]['cnt'] if total_downloaded else 0

    current_domain = ''
    packages_this_domain = 0
    started_at = None
    if dl_running:
        started_at = _wikidata_process.get("start_time")
        started_at = datetime.fromtimestamp(started_at).isoformat() if started_at else None
        try:
            if _WIKIDATA_PROGRESS_FILE.exists():
                prog = json.loads(_WIKIDATA_PROGRESS_FILE.read_text())
                current_domain = prog.get('current_domain', '')
                packages_this_domain = prog.get('packages_this_domain', 0)
        except Exception:
            pass
        if not current_domain:
            last_row = db.execute_query(
                """SELECT domain FROM knowledge_packages
                   WHERE qid IS NOT NULL
                   ORDER BY id DESC LIMIT 1""",
                fetch=True
            )
            if last_row:
                current_domain = last_row[0]['domain']

    return {
        "ultima_descarga": dl_ts,
        "ultima_alimentacion": feed_ts,
        "dias_sin_descargar": round(dl_hours / 24, 1) if dl_hours is not None else None,
        "dias_pendientes_alimentar": round(feed_hours / 24, 1) if feed_hours is not None else None,
        "total_pendientes": total_pending,
        "pendientes_por_dominio": {r['domain']: r['cnt'] for r in (pending_by_domain or [])},
        "download_running": dl_running,
        "current_domain": current_domain,
        "packages_downloaded": total_downloaded,
        "packages_this_domain": packages_this_domain,
        "download_started_at": started_at,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post("/wikidata/download", dependencies=[Depends(verify_api_key)])
def wikidata_download(req: WikidataDownloadRequest = None):
    db = get_db_manager()
    with _wikidata_lock:
        if _wikidata_process.get("pid") and _is_pid_alive(_wikidata_process["pid"]):
            raise HTTPException(status_code=409, detail="Wikidata download already running")

        use_full = bool(req and req.phase == 'full')
        cmd = ["pythonw", "tools/update_wikidata.py"]
        if use_full:
            cmd.append("--full")

        try:
            proc = subprocess.Popen(
                cmd,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            _wikidata_process["pid"] = proc.pid
            _wikidata_process["type"] = "download"
            _wikidata_process["start_time"] = time.time()
            try:
                _WIKIDATA_PID_FILE.write_text(str(proc.pid))
            except Exception as e:
                logger.warning(f"Failed to save wikidata PID file: {e}")
            logger.info(f"Wikidata download started PID={proc.pid}")
            return {"status": "started", "pid": proc.pid}
        except Exception as e:
            logger.error(f"Failed to start wikidata download: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@router.post("/wikidata/feed", dependencies=[Depends(verify_api_key)])
def wikidata_feed():
    with _wikidata_lock:
        if _wikidata_process.get("pid") and _is_pid_alive(_wikidata_process["pid"]):
            raise HTTPException(status_code=409, detail="Wikidata process already running")

        cmd = ["pythonw", "orchestrator.py", "--phase", "feed", "--duration", "0.1"]

        try:
            proc = subprocess.Popen(
                cmd,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            _wikidata_process["pid"] = proc.pid
            _wikidata_process["type"] = "feed"
            _wikidata_process["start_time"] = time.time()
            logger.info(f"Wikidata feed started PID={proc.pid}")
            return {"status": "started", "pid": proc.pid}
        except Exception as e:
            logger.error(f"Failed to start wikidata feed: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@router.post("/wikidata/stop", dependencies=[Depends(verify_api_key)])
def wikidata_stop():
    with _wikidata_lock:
        pid = _wikidata_process.get("pid")
        if not pid or not _is_pid_alive(pid):
            _wikidata_process["pid"] = None
            raise HTTPException(status_code=404, detail="No wikidata process running")

    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, timeout=5,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            os.kill(pid, 15)
        with _wikidata_lock:
            _wikidata_process["pid"] = None
        try:
            if _WIKIDATA_PID_FILE.exists():
                _WIKIDATA_PID_FILE.unlink()
        except Exception as e:
            logger.warning(f"Failed to remove wikidata PID file: {e}")
        logger.info(f"Wikidata process PID={pid} stopped")
        return {"status": "stopped", "pid": pid}
    except Exception as e:
        logger.error(f"Failed to stop wikidata process PID={pid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
