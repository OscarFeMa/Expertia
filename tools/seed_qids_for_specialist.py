"""
Seed QIDs for a specialist via SPARQL + Wikidata API, bypassing dump scan.
Inserts directly into knowledge_packages and pre-seeds qid_expansions.
Safe to run concurrently with nurture (writes different package data).
"""

import sys, time, logging, argparse
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.update_wikidata import (
    run_sparql, fetch_entities_batch, build_structured_knowledge,
    _pick_first, LANGUAGES,
)
from database.db_manager import get_db_manager

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger('seed_qids')

def sparql_subclasses(root_qid: str, max_results: int = 5000) -> List[str]:
    """Find all entities transitively under root_qid via wdt:P279*."""
    query = f"""
SELECT DISTINCT ?qid WHERE {{
  {{ ?qid wdt:P279* wd:{root_qid} . }}
  ?qid wikibase:statements ?statementCount .
  FILTER(?statementCount > 0)
}}
LIMIT {max_results}
"""
    bindings = run_sparql(query)
    if not bindings:
        logger.warning(f"No subclasses found for {root_qid}")
        return []
    qids = []
    for b in bindings:
        qid_raw = b.get('qid', {}).get('value', '')
        qid = qid_raw.split('/')[-1] if '/' in qid_raw else qid_raw
        if qid:
            qids.append(qid)
    logger.info(f"SPARQL wdt:P279* {root_qid}: {len(qids)} subclasses")
    return qids


def sparql_instances(root_qid: str, max_results: int = 5000) -> List[str]:
    """Find instances of a given root QID (P31 = root_qid)."""
    query = f"""
SELECT DISTINCT ?qid WHERE {{
  ?qid wdt:P31 wd:{root_qid} .
  ?qid wikibase:statements ?statementCount .
  FILTER(?statementCount > 0)
}}
LIMIT {max_results}
"""
    bindings = run_sparql(query)
    if not bindings:
        logger.warning(f"No instances found for {root_qid}")
        return []
    qids = []
    for b in bindings:
        qid_raw = b.get('qid', {}).get('value', '')
        qid = qid_raw.split('/')[-1] if '/' in qid_raw else qid_raw
        if qid:
            qids.append(qid)
    logger.info(f"SPARQL wdt:P31 {root_qid}: {len(qids)} instances")
    return qids


def process_qids(qids: List[str], specialist_id: int, domain: str, db) -> int:
    """Fetch QIDs via API, build knowledge, insert into knowledge_packages + qid_expansions."""
    if not qids:
        return 0

    total_inserted = 0
    total_expanded = 0
    batch_size = 50

    for i in range(0, len(qids), batch_size):
        batch = qids[i:i + batch_size]
        try:
            entities = fetch_entities_batch(batch)
        except Exception as e:
            logger.warning(f"Batch fetch failed: {e}")
            continue

        packages = []
        for qid in batch:
            entity = entities.get(qid)
            if not entity:
                continue
            structured = build_structured_knowledge(entity)
            if not structured or len(structured.strip()) < 20:
                continue
            label = _pick_first(entity.get('labels') or {}, LANGUAGES.split('|'))
            topic = f'{label} — Wikidata entity' if label else f'{qid} — Wikidata entity'
            source_url = f'https://www.wikidata.org/entity/{qid}'
            packages.append((topic, source_url, domain, qid, structured))

        if packages:
            try:
                db.execute_many(
                    """INSERT OR IGNORE INTO knowledge_packages
                       (topic, source_url, domain, qid, structured_knowledge, created_at)
                       VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                    packages
                )
                total_inserted += len(packages)
            except Exception as e:
                logger.warning(f"Package insert batch failed: {e}")

        # Seed qid_expansions for this specialist
        expansion_rows = [(specialist_id, qid, 0) for qid in batch]
        try:
            db.execute_many(
                """INSERT OR IGNORE INTO qid_expansions
                   (specialist_id, qid, discovered_at_checkpoint)
                   VALUES (?, ?, ?)""",
                expansion_rows
            )
            total_expanded += len(batch)
        except Exception as e:
            logger.warning(f"Expansion insert batch failed: {e}")

        if (i + batch_size) % 500 == 0 or (i + batch_size) >= len(qids):
            logger.info(f"  Progress: {min(i+batch_size, len(qids))}/{len(qids)} QIDs, {total_inserted} packages inserted, {total_expanded} expansions seeded")

    return total_inserted


def main():
    parser = argparse.ArgumentParser(description='Seed QIDs for a specialist via SPARQL + API')
    parser.add_argument('--domain', required=True, help='Domain name (e.g. Linguistics)')
    parser.add_argument('--specialist-id', type=int, required=True, help='Specialist DB id')
    parser.add_argument('--root-qid', required=True, help='Root QID for P279 subclass traversal')
    parser.add_argument('--extra-qids', nargs='*', default=[], help='Extra root QIDs for P31 instance matching')
    parser.add_argument('--max-per-query', type=int, default=3000, help='Max results per SPARQL query')
    parser.add_argument('--skip-packages', action='store_true', help='Only seed expansions, skip packages')
    args = parser.parse_args()

    db = get_db_manager()
    all_qids: set = set()

    # 1. Recursive subclasses via P279*
    logger.info(f"Querying SPARQL for subclasses of {args.root_qid}...")
    sub_qids = sparql_subclasses(args.root_qid, args.max_per_query)
    all_qids.update(sub_qids)

    # 2. Extra root QIDs for P31 matching
    extra_roots = list(dict.fromkeys(args.extra_qids))  # deduplicate, preserve order
    if extra_roots:
        logger.info(f"Querying SPARQL for instances of extra roots: {extra_roots}")
        for extra_qid in extra_roots:
            inst_qids = sparql_instances(extra_qid, args.max_per_query)
            all_qids.update(inst_qids)
            # Also add the root itself as an expansion
            all_qids.add(extra_qid)

    # Ensure root QID is in the set
    all_qids.add(args.root_qid)

    # Filter out anything that's not a valid QID
    all_qids = {q for q in all_qids if q.startswith('Q')}

    logger.info(f"Total unique QIDs to process: {len(all_qids):,}")

    if not all_qids:
        logger.error("No QIDs found. Cannot seed.")
        return

    if not args.skip_packages:
        # 3. Fetch + build + insert packages
        qids_list = sorted(all_qids)
        inserted = process_qids(qids_list, args.specialist_id, args.domain, db)
        logger.info(f"Inserted {inserted} knowledge packages for {args.domain}")

        # 4. Update packages_absorbed in specialist_registry
        cur_count = db.execute_query(
            "SELECT COUNT(*) as cnt FROM knowledge_packages WHERE domain=?", (args.domain,), fetch=True
        )
        actual = cur_count[0]['cnt'] if cur_count else 0
        db.execute_query(
            "UPDATE specialist_registry SET packages_absorbed = ? WHERE id = ?",
            (actual, args.specialist_id)
        )
        logger.info(f"Updated {args.domain} packages_absorbed to {actual:,}")
    else:
        # Only seed expansions (no packages)
        expansion_rows = [(args.specialist_id, qid, 0) for qid in all_qids]
        try:
            db.execute_many(
                """INSERT OR IGNORE INTO qid_expansions
                   (specialist_id, qid, discovered_at_checkpoint)
                   VALUES (?, ?, ?)""",
                expansion_rows
            )
            logger.info(f"Seeded {len(expansion_rows)} qid_expansions for {args.domain}")
        except Exception as e:
            logger.warning(f"Failed to seed expansions: {e}")

    logger.info(f"Done seeding {args.domain}")


if __name__ == '__main__':
    main()
