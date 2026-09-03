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


def fetch_rows(db_path, where, limit, offset):
    uri = f"file:{db_path}?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT qid, topic, structured_knowledge, source_url FROM knowledge_packages "
            f"WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
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
    offset = 0
    seen = set()
    while len(collected) < args.limit:
        rows = fetch_rows(args.db, where, BATCH, offset)
        if not rows:
            break
        offset += len(rows)
        for r in rows:
            key = (r.get("qid"), r.get("topic"))
            if key in seen:
                continue
            seen.add(key)
            rec = to_record(r)
            if rec:
                collected.append(rec)
            if len(collected) >= args.limit:
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

    print(json.dumps({"train": len(train), "val": len(val), "out": str(out_path), "val_out": str(val_path), "offset_scanned": offset}, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
