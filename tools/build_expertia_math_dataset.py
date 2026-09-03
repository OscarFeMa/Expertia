import argparse
import json
import random
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = r"E:\expertia-data\incubator.db"
DEFAULT_OUT = r"D:\proyectos\expertia\training\datasets\expertia-math-puro.jsonl"
SYSTEM_PROMPT = "Eres ExpertiaMath, matematico puro. Responde solo con definicion formal y formula. Sin opinion web."
BATCH = 2000

STRICT_WHERE = """domain='Mathematics' AND qid IS NOT NULL AND structured_knowledge IS NOT NULL AND structured_knowledge LIKE '%P2534%' AND LENGTH(structured_knowledge) BETWEEN 50 AND 2000 AND source_url LIKE '%wikidata.org/entity/%'"""
RELAXED_WHERE = """domain='Mathematics' AND qid IS NOT NULL AND structured_knowledge IS NOT NULL AND (structured_knowledge LIKE '%P2534%' OR structured_knowledge LIKE '%defining formula%') AND LENGTH(structured_knowledge) BETWEEN 50 AND 2000 AND source_url LIKE '%wikidata.org/entity/%'"""

GARBAGE_MARKERS = ("cookie", "sign in", "captcha", "subscribe", "javascript")


def is_garbage(text):
    low = text.lower()
    return any(m in low for m in GARBAGE_MARKERS)


def fetch_batch(db_path, max_id, batch):
    uri = f"file:{db_path}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        if max_id is None:
            rows = con.execute(
                "SELECT id, qid, topic, structured_knowledge, source_url FROM knowledge_packages "
                "WHERE domain='Mathematics' AND qid IS NOT NULL "
                "ORDER BY id DESC LIMIT ?",
                (batch,),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT id, qid, topic, structured_knowledge, source_url FROM knowledge_packages "
                "WHERE domain='Mathematics' AND qid IS NOT NULL AND id < ? "
                "ORDER BY id DESC LIMIT ?",
                (max_id, batch),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def to_record(row):
    topic = (row.get("topic") or "").strip()
    sk = (row.get("structured_knowledge") or "").strip()
    qid = (row.get("qid") or "").strip()
    url = (row.get("source_url") or "").strip()
    if not topic or not sk:
        return None
    if is_garbage(sk):
        return None
    instruction = f"Explica {topic} [{qid}]" if qid else f"Explica {topic}"
    return {
        "system": SYSTEM_PROMPT,
        "instruction": instruction[:300],
        "input": "",
        "output": f"{sk}\nSource: {url}"[:2000],
        "metadata": {"domain": "Mathematics", "qid": qid, "source_url": url, "origin": "wikidata_pure"},
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--out", default=DEFAULT_OUT)
    p.add_argument("--limit", type=int, default=50000)
    p.add_argument("--val-split", type=float, default=0.1)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--relaxed", action="store_true")
    p.add_argument("--val-out", default="")
    args = p.parse_args()

    where = RELAXED_WHERE if args.relaxed else STRICT_WHERE
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    val_path = Path(args.val_out) if args.val_out else out_path.with_name(out_path.stem + "_val.jsonl")

    rnd = random.Random(args.seed)
    collected = []
    scanned = 0
    max_id = None
    seen = set()
    strict = not args.relaxed
    while len(collected) < args.limit:
        rows = fetch_batch(args.db, max_id, BATCH)
        if not rows:
            break
        max_id = min(r["id"] for r in rows)
        scanned += len(rows)
        for r in rows:
            sk = r.get("structured_knowledge") or ""
            if len(sk) < 50 or len(sk) > 2000:
                continue
            if strict and "P2534" not in sk:
                continue
            src = r.get("source_url") or ""
            if "wikidata.org/entity/" not in src:
                continue
            key = (r.get("qid"), r.get("topic"))
            if key in seen:
                continue
            seen.add(key)
            rec = to_record(r)
            if rec:
                collected.append(rec)
            if len(collected) >= args.limit:
                break
        if scanned > args.limit * 200:
            break

    rnd.shuffle(collected)
    n_val = int(len(collected) * args.val_split)
    val = collected[:n_val]
    train = collected[n_val:]

    with open(out_path, "w", encoding="utf-8") as f:
        for rec in train:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    with open(val_path, "w", encoding="utf-8") as f:
        for rec in val:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(json.dumps({"train": len(train), "val": len(val), "out": str(out_path), "val_out": str(val_path), "scanned": scanned}, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
