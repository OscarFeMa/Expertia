import logging
import json
from typing import Dict, List, Optional, Set
from config.settings import (
    WIKIDATA_ENTITY_API,
    WIKIDATA_API_USER_AGENT,
    WIKIDATA_LABEL_BATCH_SIZE,
    BLOCKLIST_LABELS,
    BLOCKLIST_LABEL_PREFIXES,
)
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)


def is_blocklisted_label(label: str) -> bool:
    label_lower = label.strip().lower()
    if label_lower in BLOCKLIST_LABELS:
        return True
    for prefix in BLOCKLIST_LABEL_PREFIXES:
        if label_lower.startswith(prefix):
            return True
    return False


def batch_resolve_labels(qids: List[str]) -> Dict[str, str]:
    if not qids:
        return {}
    result = {}
    uncached = list(qids)
    for i in range(0, len(uncached), WIKIDATA_LABEL_BATCH_SIZE):
        batch = uncached[i:i + WIKIDATA_LABEL_BATCH_SIZE]
        try:
            ids_str = '|'.join(batch)
            import requests
            resp = requests.get(
                WIKIDATA_ENTITY_API,
                params={
                    'action': 'wbgetentities',
                    'ids': ids_str,
                    'props': 'labels',
                    'format': 'json',
                    'languages': 'en',
                },
                headers={'User-Agent': WIKIDATA_API_USER_AGENT},
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
            if 'entities' in data:
                for qid, entity in data['entities'].items():
                    label = entity.get('labels', {}).get('en', {}).get('value', qid)
                    result[qid] = label
        except Exception as e:
            logger.warning(f"Label resolution failed for batch starting at {batch[0]}: {e}")
            for qid in batch:
                if qid not in result:
                    result[qid] = qid
    return result


def _fetch_p279_parents(qid: str) -> Set[str]:
    import requests
    try:
        resp = requests.get(
            WIKIDATA_ENTITY_API,
            params={'action': 'wbgetentities', 'ids': qid, 'props': 'claims', 'format': 'json'},
            headers={'User-Agent': WIKIDATA_API_USER_AGENT},
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        entity = data.get('entities', {}).get(qid, {})
        p279 = set()
        for claim in entity.get('claims', {}).get('P279', []):
            try:
                p279.add(claim['mainsnak']['datavalue']['value']['id'])
            except (KeyError, TypeError):
                pass
        return p279
    except Exception as e:
        logger.warning(f"Failed to fetch P279 for {qid}: {e}")
        return set()


def _batch_fetch_p279(qids: List[str], cache: Dict[str, Set[str]]):
    import requests
    uncached = [q for q in qids if q not in cache]
    if not uncached:
        return
    for i in range(0, len(uncached), WIKIDATA_LABEL_BATCH_SIZE):
        batch = uncached[i:i + WIKIDATA_LABEL_BATCH_SIZE]
        try:
            ids_str = '|'.join(batch)
            resp = requests.get(
                WIKIDATA_ENTITY_API,
                params={'action': 'wbgetentities', 'ids': ids_str, 'props': 'claims', 'format': 'json'},
                headers={'User-Agent': WIKIDATA_API_USER_AGENT},
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
            for qid, entity in data.get('entities', {}).items():
                if qid not in cache:
                    p279 = set()
                    for claim in entity.get('claims', {}).get('P279', []):
                        try:
                            p279.add(claim['mainsnak']['datavalue']['value']['id'])
                        except (KeyError, TypeError):
                            pass
                    cache[qid] = p279
        except Exception as e:
            logger.warning(f"Batch P279 fetch failed for batch: {e}")
            for qid in batch:
                if qid not in cache:
                    cache[qid] = set()


def validate_qids(qids: List[str], root_qid: str) -> Dict[str, bool]:
    if not qids:
        return {}
    cache: Dict[str, Set[str]] = {}
    target_root_p279 = _fetch_p279_parents(root_qid)
    _batch_fetch_p279(list(set(qids + [root_qid])), cache)
    valid = {}
    for qid in qids:
        cand_p279 = cache.get(qid, set())
        if root_qid in cand_p279:
            valid[qid] = True
        elif cand_p279 & target_root_p279:
            valid[qid] = True
        else:
            valid[qid] = False
    return valid


def get_qualified_specialists(db: DatabaseManager) -> List[dict]:
    rows = db.execute_query(
        "SELECT id, domain, model, root_qid, packages_absorbed, ema_score, "
        "weighted_success, weighted_fail "
        "FROM specialist_registry WHERE parent_id IS NULL "
        "AND packages_absorbed > 2500 AND ema_score > 0.95 "
        "ORDER BY packages_absorbed DESC",
        fetch=True
    )
    return rows if rows else []


def get_expansions_for_specialist(db: DatabaseManager, specialist_id: int) -> List[dict]:
    parent = db.execute_query(
        "SELECT id, domain, root_qid FROM specialist_registry WHERE id=?",
        (specialist_id,), fetch=True
    )
    if not parent:
        return []
    parent = parent[0]
    rows = db.execute_query(
        "SELECT qid FROM qid_expansions WHERE specialist_id=? ORDER BY discovered_at_checkpoint",
        (specialist_id,), fetch=True
    )
    if not rows:
        return []
    qids = [r['qid'] for r in rows]
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
    return result


def spawn_child(db: DatabaseManager, parent_id: int, qid: str, model: str,
                on_log=None) -> dict:
    parent = db.execute_query(
        "SELECT id, domain, root_qid, properties, qid_path FROM specialist_registry WHERE id=?",
        (parent_id,), fetch=True
    )
    if not parent:
        return {'success': False, 'error': 'Parent not found'}
    parent = parent[0]
    existing = db.execute_query(
        "SELECT id FROM specialist_registry WHERE root_qid=? AND parent_id=?",
        (qid, parent_id), fetch=True
    )
    if existing:
        return {'success': False, 'error': 'Already exists'}
    labels = batch_resolve_labels([qid])
    label = labels.get(qid, qid)
    if is_blocklisted_label(label):
        if on_log:
            on_log('WARNING', f'Label blocklisted: {label}')
        return {'success': False, 'error': f'Label blocklisted: {label}'}
    validation = validate_qids([qid], parent['root_qid'])
    if not validation.get(qid, False):
        if on_log:
            on_log('WARNING', f'P279 validation failed for {qid}')
        return {'success': False, 'error': f'P279 validation failed'}
    child_domain = f"{parent['domain']}/{label}"
    parent_path = parent.get('qid_path') or parent['domain']
    child_path = f"{parent_path}/{label}"
    db.execute_query(
        "INSERT INTO specialist_registry "
        "(domain, model, root_qid, properties, ema_score, tier, status, parent_id, qid_path) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (child_domain, model, qid, parent['properties'], 0.10, 3, 'IDLE', parent_id, child_path)
    )
    if on_log:
        on_log('INFO', f'Spawned {child_domain} (QID: {qid})')
    return {'success': True, 'domain': child_domain, 'qid': qid}
