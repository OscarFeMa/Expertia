"""
Pipeline Monitor Agent
Corre en segundo plano y reporta estado del pipeline cada 20 minutos.
Uso: python tools/pipeline_monitor.py
Read-only: no modifica DB ni archivos del pipeline, solo crea storage/monitor_reports.json
"""
import time
import logging
import sqlite3
import os
import json
import subprocess
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "storage" / "incubator.db"
LOGS_DIR = BASE_DIR / "logs"
REPORT_FILE = BASE_DIR / "storage" / "monitor_reports.json"
INTERVAL_MINUTES = 20


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def check_pipeline_alive() -> Optional[Dict]:
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM pipeline_status ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        logger.warning(f"check_pipeline_alive: {e}")
        return None


def get_specialist_stats() -> List[Dict]:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT domain, tier, ema_score, packages_absorbed,
               weighted_success, weighted_fail, status
        FROM specialist_registry ORDER BY domain
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_latest_logs(n_lines: int = 30) -> List[str]:
    log_files = sorted(LOGS_DIR.glob("orchestrator_*.log"), key=os.path.getmtime, reverse=True)
    if not log_files:
        return []
    latest = log_files[0]
    try:
        size = os.path.getsize(latest)
        if size == 0:
            # Empty file — try pipeline log
            pipeline_logs = sorted(LOGS_DIR.glob("pipeline_*.log"), key=os.path.getmtime, reverse=True)
            if pipeline_logs:
                latest = pipeline_logs[0]
        with open(latest, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        return lines[-n_lines:]
    except Exception as e:
        logger.warning(f"get_latest_logs: {e}")
        return []


def estimate_completion(logs: List[str]) -> Dict:
    result = {"phase": "unknown", "detail": ""}
    for line in reversed(logs):
        if "Reanudando: saltadas" in line:
            try:
                parts = line.split("saltadas")
                num_str = parts[1].strip().split()[0].replace(",", "")
                skipped = int(num_str)
                total_to_skip = 57_900_000  # initial checkpoint
                remaining = max(0, total_to_skip - skipped)
                pct = (skipped / total_to_skip) * 100 if total_to_skip > 0 else 0
                result.update({
                    "phase": "phase_a_skip",
                    "skipped": skipped,
                    "total_to_skip": total_to_skip,
                    "remaining": remaining,
                    "pct": round(pct, 1)
                })
                return result
            except (ValueError, IndexError):
                pass
        if "Wikidata API fetch" in line:
            result["phase"] = "phase_a_fetch"
            result["detail"] = line.strip()
            return result
        if "Nurture cycle" in line:
            result["phase"] = "nurture"
            result["detail"] = line.strip()
            return result
        if "Nurture v2" in line:
            result["phase"] = "nurture"
            return result
        if "PHASE A" in line:
            result["phase"] = "phase_a"
            return result
        if "PHASE B" in line or "Phase B" in line:
            result["phase"] = "phase_b"
            return result
    return result


def get_pipeline_pid() -> Optional[int]:
    try:
        # Check from api_router's pipeline_state.json
        state_file = BASE_DIR / "pipeline_state.json"
        if state_file.exists():
            data = json.loads(state_file.read_text())
            pid = data.get("pid")
            if pid:
                return pid
        # Fallback: check running python processes
        r = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV"],
            capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for line in r.stdout.splitlines()[1:]:
            parts = line.split(",")
            if len(parts) >= 2:
                pid_str = parts[1].strip().strip('"')
                try:
                    return int(pid_str)
                except ValueError:
                    pass
        return None
    except Exception:
        return None


def generate_report() -> Dict:
    status = check_pipeline_alive()
    specialists = get_specialist_stats()
    logs = get_latest_logs()
    estimate = estimate_completion(logs)
    pid = get_pipeline_pid()

    # CPU/memory check via WMIC
    cpu_pct = None
    mem_mb = None
    if pid:
        try:
            r = subprocess.run(
                ["wmic", "process", "where", f"ProcessId={pid}", "get", "WorkingSetSize,PercentProcessorTime",
                 "/FORMAT:CSV"],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            for line in r.stdout.splitlines():
                if str(pid) in line:
                    cols = line.split(",")
                    if len(cols) >= 3:
                        try:
                            mem_mb = round(int(cols[2]) / (1024 * 1024), 1)
                        except (ValueError, IndexError):
                            pass
        except Exception:
            pass

    report: Dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "pipeline_alive": status is not None,
        "pid": pid,
        "cpu_pct": cpu_pct,
        "mem_mb": mem_mb,
        "pipeline_status": status,
        "completion_estimate": estimate,
        "specialist_count": len(specialists),
        "tier_distribution": {
            "legend": sum(1 for s in specialists if s['tier'] == 4),
            "gold": sum(1 for s in specialists if s['tier'] == 3),
            "silver": sum(1 for s in specialists if s['tier'] == 2),
            "bronze": sum(1 for s in specialists if s['tier'] == 1),
            "none": sum(1 for s in specialists if s['tier'] == 0),
        },
        "total_packages": sum(s['packages_absorbed'] for s in specialists),
        "avg_ema": round(sum(s['ema_score'] for s in specialists) / max(len(specialists), 1), 4),
    }

    # Save cumulative report
    try:
        reports = []
        if REPORT_FILE.exists():
            reports = json.loads(REPORT_FILE.read_text())
        reports.append(report)
        REPORT_FILE.write_text(json.dumps(reports, indent=2))
    except Exception as e:
        logger.warning(f"Failed to save report: {e}")

    return report


def print_report(report: Dict):
    ts = report['timestamp'][:19]
    status_icon = "🟢" if report['pipeline_alive'] else "🔴"
    print(f"\n{'='*60}")
    print(f"  Pipeline Monitor — {ts}  {status_icon}")
    print(f"{'='*60}")
    print(f"  PID: {report.get('pid', 'N/A')}")
    if report.get('mem_mb'):
        print(f"  RAM: {report['mem_mb']} MB")

    est = report.get('completion_estimate', {})
    phase = est.get('phase', 'unknown')

    if phase == 'phase_a_skip':
        pct = est.get('pct', 0)
        skipped = est.get('skipped', 0)
        remaining = est.get('remaining', 0)
        bar_len = 30
        filled = int(bar_len * pct / 100)
        bar = '█' * filled + '░' * (bar_len - filled)
        rate_k = 220  # approximate rate in K/min
        eta_min = remaining // (rate_k * 1000) * (1000 / rate_k) if rate_k > 0 else 0
        eta_min = max(1, int(remaining / (rate_k * 1000) * 1000 / rate_k)) if rate_k > 0 else 0
        print(f"  Fase: PHASE A — SKIP")
        print(f"  [{bar}] {pct:.1f}%")
        print(f"  Skip: {skipped:,} / {est.get('total_to_skip', 0):,} entidades")
        print(f"  Restante: {remaining:,} entidades (~{eta_min} min @ {rate_k}K/min)")
    elif phase == 'phase_a_fetch':
        print(f"  Fase: PHASE A — FETCH (API Wikidata)")
        print(f"  Detalle: {est.get('detail', '')[:80]}")
    elif phase == 'nurture':
        print(f"  Fase: PHASE B — NURTURE")
        if est.get('detail'):
            print(f"  {est['detail'][:80]}")
    elif phase == 'phase_a':
        print(f"  Fase: PHASE A — CASCADE")
    elif phase == 'phase_b':
        print(f"  Fase: PHASE B — WEB + LLM")
    else:
        print(f"  Fase: {phase}")

    print(f"\n  Especialistas: {report['specialist_count']}")
    td = report.get('tier_distribution', {})
    print(f"  Tiers: L:{td.get('legend', 0)} G:{td.get('gold', 0)} S:{td.get('silver', 0)} B:{td.get('bronze', 0)} N:{td.get('none', 0)}")
    print(f"  Total packages: {report['total_packages']:,}")
    print(f"  EMA promedio: {report.get('avg_ema', 0):.4f}")
    print(f"{'='*60}\n")


def main():
    print("Pipeline Monitor Agent iniciado")
    print(f"  DB: {DB_PATH}")
    print(f"  Reportes acumulados: {REPORT_FILE}")
    print(f"  Intervalo: {INTERVAL_MINUTES} minutos")
    print("  Presiona Ctrl+C para detener.\n")

    while True:
        try:
            report = generate_report()
            print_report(report)
        except KeyboardInterrupt:
            print("\nMonitor detenido por el usuario.")
            break
        except Exception as e:
            logger.error(f"Error en ciclo de monitoreo: {e}")
        time.sleep(INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    main()
