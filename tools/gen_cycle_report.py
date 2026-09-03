import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = REPO_ROOT / "storage" / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = REPORTS_DIR / ".cycle_state.json"
TRAIN_ROOT = Path(r"D:\proyectos\expertia\training")
DB_PATH = r"E:\expertia-data\incubator.db"

WINDOW_H = 12


def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(st):
    STATE_FILE.write_text(json.dumps(st, indent=2), encoding="utf-8")


def db_connect():
    uri = f"file:{DB_PATH}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    return con


def web_report():
    since = (datetime.now(timezone.utc) - timedelta(hours=WINDOW_H + 1)).strftime("%Y-%m-%d %H:%M:%S")
    con = db_connect()
    try:
        cycles = con.execute(
            "SELECT COUNT(*) c, COALESCE(AVG(quality),0) q, COALESCE(SUM(success),0) ok FROM cycle_history WHERE timestamp >= ?", (since,),
        ).fetchone()
        fails = con.execute(
            "SELECT COUNT(*) c FROM cycle_history WHERE timestamp >= ? AND success = 0", (since,),
        ).fetchone()
        per_dom = con.execute(
            "SELECT s.domain, COUNT(*) n, COALESCE(AVG(c.quality),0) q FROM cycle_history c JOIN specialist_registry s ON s.id = c.specialist_id WHERE c.timestamp >= ? GROUP BY s.domain ORDER BY n DESC", (since,),
        ).fetchall()
        max_id = con.execute("SELECT MAX(id) m FROM knowledge_packages").fetchone()
        specs = con.execute("SELECT domain, model, ema_score, tier, packages_absorbed, status FROM specialist_registry ORDER BY ema_score DESC").fetchall()
        acts = con.execute("SELECT level, COUNT(*) n FROM activity_log WHERE timestamp >= ? GROUP BY level", (since,)).fetchall()
    finally:
        con.close()
    st = load_state()
    prev_max = st.get("last_pkg_id")
    cur_max = max_id["m"] if max_id else 0
    new_pkgs = (cur_max - prev_max) if prev_max else None
    st["last_pkg_id"] = cur_max
    st["last_web_report"] = datetime.now(timezone.utc).isoformat()
    save_state(st)
    return {
        "kind": "web",
        "window_h": WINDOW_H,
        "ts": datetime.now(timezone.utc).isoformat(),
        "cycles": (cycles["c"] or 0),
        "cycles_ok": (cycles["ok"] or 0),
        "cycles_fail": (fails["c"] or 0),
        "avg_quality": round(cycles["q"] or 0, 4),
        "new_packages": new_pkgs,
        "per_domain": [{"domain": r["domain"], "cycles": r["n"], "avg_quality": round(r["q"] or 0, 4)} for r in per_dom],
        "activity": {r["level"]: r["n"] for r in acts},
        "specialists": [{"domain": s["domain"], "model": s["model"], "ema": round(s["ema_score"] or 0, 5), "tier": s["tier"], "packages": s["packages_absorbed"], "status": s["status"]} for s in specs],
    }


def training_report():
    logs_dir = TRAIN_ROOT / "logs"
    status = {}
    try:
        status = json.loads((logs_dir / "train_status.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    hist = status.get("loss_history") or []
    losses = [h["loss"] for h in hist if h.get("loss") is not None]
    train_n = val_n = 0
    for name, key in (("expertia-math-puro.jsonl", "train"), ("expertia-math-puro_val.jsonl", "val")):
        p = TRAIN_ROOT / "datasets" / name
        if p.exists():
            with open(p, "rb") as f:
                n = sum(1 for _ in f)
            if key == "train":
                train_n = n
            else:
                val_n = n
    ad = TRAIN_ROOT / "adapters" / "expertia-math-r16"
    ckpts = sorted([p.name for p in ad.glob("checkpoint-*")]) if ad.exists() else []
    train_logs = sorted(logs_dir.glob("train_*.log")) if logs_dir.exists() else []
    return {
        "kind": "training",
        "window_h": WINDOW_H,
        "ts": datetime.now(timezone.utc).isoformat(),
        "phase": status.get("phase", "idle"),
        "step": status.get("step", 0),
        "max_steps": status.get("max_steps"),
        "epoch": status.get("epoch"),
        "loss_last": losses[-1] if losses else None,
        "loss_min": round(min(losses), 4) if losses else None,
        "loss_first": losses[0] if losses else None,
        "loss_points": len(losses),
        "steps_per_min": status.get("steps_per_min"),
        "elapsed_s": status.get("elapsed_s"),
        "dataset_train": train_n,
        "dataset_val": val_n,
        "checkpoints": ckpts,
        "log_file": train_logs[-1].name if train_logs else None,
    }


def to_markdown(rep):
    lines = [f"# Informe ciclo {rep['kind']} — {rep['ts']}", ""]
    if rep["kind"] == "web":
        lines += [
            f"Ciclos: {rep['cycles']} (ok {rep['cycles_ok']}, fail {rep['cycles_fail']})",
            f"Calidad media: {rep['avg_quality']}",
            f"Paquetes nuevos (ventana): {rep['new_packages']}",
            "",
            "## Por dominio",
        ]
        for d in rep["per_domain"][:18]:
            lines.append(f"- {d['domain']}: {d['cycles']} ciclos, q {d['avg_quality']}")
        lines += ["", "## Actividad", json.dumps(rep["activity"], ensure_ascii=False)]
    else:
        lines += [
            f"Fase: {rep['phase']}, paso {rep['step']}/{rep.get('max_steps') or '?'} (ep {rep.get('epoch')})",
            f"Loss: first {rep['loss_first']}, last {rep['loss_last']}, min {rep['loss_min']} ({rep['loss_points']} puntos)",
            f"Ritmo: {rep['steps_per_min']} pasos/min, elapsed {rep['elapsed_s']}s",
            f"Dataset: {rep['dataset_train']} train / {rep['dataset_val']} val",
            f"Checkpoints: {', '.join(rep['checkpoints']) if rep['checkpoints'] else 'ninguno'}",
        ]
    return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--kind", choices=["web", "training"], required=True)
    args = p.parse_args()
    rep = web_report() if args.kind == "web" else training_report()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    jp = REPORTS_DIR / f"cycle_{args.kind}_{ts}.json"
    mp = REPORTS_DIR / f"cycle_{args.kind}_{ts}.md"
    jp.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    mp.write_text(to_markdown(rep), encoding="utf-8")
    print(json.dumps({"json": str(jp), "md": str(mp), "kind": args.kind}, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
