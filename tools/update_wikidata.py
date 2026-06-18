import argparse
import gzip
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.settings import (
    WIKIDATA_ENTITY_API, WIKIDATA_SPARQL_ENDPOINT,
    WIKIDATA_API_USER_AGENT, WIKIDATA_LABEL_BATCH_SIZE,
    LANGUAGES,
)
from database.db_manager import get_db_manager

logging.basicConfig(
    level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger('update_wikidata')

HEADERS = {'User-Agent': WIKIDATA_API_USER_AGENT}
SPARQL_URL = WIKIDATA_SPARQL_ENDPOINT
ENTITY_API = WIKIDATA_ENTITY_API
PROGRESS_FILE = Path(__file__).parent.parent / 'storage' / 'wikidata_progress.json'

# Garbage patterns to reject from Wikidata content
_GARBAGE_PATTERNS = [
    "cookie", "javascript is disabled", "sign in",
    "page not found", "access denied", "forbidden",
    "loading", "captcha", "robot",
]


def is_garbage_content(text: str) -> bool:
    """Check if text matches known garbage patterns."""
    if not text or len(text.strip()) < 20:
        return True
    lower = text.lower()
    return any(p in lower for p in _GARBAGE_PATTERNS)


# Common Wikidata property labels for human-readable output
PROPERTY_LABELS = {
    'P31': 'instance of', 'P279': 'subclass of', 'P17': 'country',
    'P361': 'part of', 'P527': 'has part', 'P3095': 'practiced by',
    'P106': 'occupation', 'P101': 'field of work', 'P108': 'employer',
    'P131': 'located in', 'P159': 'headquarters', 'P176': 'manufacturer',
    'P178': 'developer', 'P180': 'depicts', 'P195': 'collection',
    'P276': 'location', 'P571': 'inception', 'P576': 'dissolved',
    'P585': 'point in time', 'P625': 'coordinate location',
    'P646': 'Freebase ID', 'P268': 'BnF ID', 'P214': 'VIAF ID',
    'P227': 'GND ID', 'P213': 'ISNI', 'P2002': 'Twitter username',
    'P856': 'official website', 'P673': 'IMDb ID', 'P495': 'country of origin',
    'P2860': 'cites work', 'P50': 'author', 'P175': 'performer',
    'P136': 'genre', 'P364': 'used language', 'P407': 'language of work',
    'P910': 'topic category', 'P610': 'highest point', 'P2044': 'elevation',
    'P1101': 'charges', 'P2067': 'mass', 'P2048': 'height',
    'P2562': 'married name', 'P26': 'father', 'P25': 'mother',
    'P40': 'child', 'P3373': 'sibling', 'P22': 'father',
    'P39': 'position held', 'P27': 'country of citizenship',
    'P569': 'date of birth', 'P570': 'date of death',
    'P166': 'award received', 'P1411': 'nominated for',
    'P800': 'notable work', 'P1559': 'notable work',
    'P973': 'described at URL', 'P851': 'image',
}


def write_progress(state: dict):
    try:
        PROGRESS_FILE.write_text(json.dumps(state))
    except Exception as e:
        logger.warning(f'Failed to write progress: {e}')


def run_sparql(query: str) -> Optional[List[Dict]]:
    delays = [5, 15, 30]
    last_error = None
    for attempt, delay in enumerate(delays):
        try:
            resp = requests.get(
                SPARQL_URL, params={'format': 'json', 'query': query},
                headers=HEADERS, timeout=120
            )
            if resp.status_code == 502:
                logger.warning(f'SPARQL 502 (attempt {attempt+1}/{len(delays)}), retrying in {delay}s')
                time.sleep(delay)
                continue
            resp.raise_for_status()
            data = resp.json()
            return data.get('results', {}).get('bindings', [])
        except requests.exceptions.Timeout:
            last_error = f'timeout (attempt {attempt+1}/{len(delays)})'
            logger.warning(f'{last_error}, retrying in {delay}s')
            time.sleep(delay)
        except Exception as e:
            last_error = f'{e} (attempt {attempt+1}/{len(delays)})'
            logger.warning(f'SPARQL {last_error}, retrying in {delay}s')
            time.sleep(delay)
    logger.error(f'SPARQL failed after {len(delays)} attempts: {last_error}')
    return None


def fetch_entities_batch(qids: List[str]) -> Dict[str, Dict]:
    result = {}
    for i in range(0, len(qids), WIKIDATA_LABEL_BATCH_SIZE):
        batch = qids[i:i + WIKIDATA_LABEL_BATCH_SIZE]
        try:
            ids_str = '|'.join(batch)
            resp = requests.get(
                ENTITY_API,
                params={
                    'action': 'wbgetentities',
                    'ids': ids_str,
                    'props': 'labels|descriptions|aliases|claims|sitelinks',
                    'format': 'json',
                    'languages': LANGUAGES,
                },
                headers=HEADERS,
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            if 'entities' in data:
                result.update(data['entities'])
        except Exception as e:
            logger.warning(f'Failed to fetch batch {batch[0]}..{batch[-1]}: {e}')
    return result


def _pick_first(values: Dict, langs: List[str], key: str = 'value'):
    """Pick the first available value from a language-keyed dict using the ordered language list."""
    if not values:
        return ''
    for lang in langs:
        v = values.get(lang, {}).get(key, '')
        if v:
            return v
    # fallback to any language
    for v in values.values():
        val = v.get(key, '')
        if val:
            return val
    return ''


def build_structured_knowledge(entity: Dict, languages: str = LANGUAGES) -> str:
    langs = languages.split('|')
    label = _pick_first(entity.get('labels') or {}, langs)
    desc = _pick_first(entity.get('descriptions') or {}, langs)
    aliases_list = []
    aliases_dict = entity.get('aliases') or {}
    for lang in langs:
        if lang in aliases_dict:
            aliases_list = [a.get('value', '') for a in aliases_dict[lang][:5]]
            break
    if not aliases_list:
        for v in aliases_dict.values():
            aliases_list = [a.get('value', '') for a in v[:5]]
            break
    alias_text = '; '.join(aliases_list)

    claims = entity.get('claims') or {}
    claim_lines = []
    for prop_id, claim_list in list(claims.items())[:8]:
        for claim in claim_list[:2]:
            try:
                mainsnak = claim.get('mainsnak', {})
                if mainsnak.get('snaktype') != 'value':
                    continue
                datavalue = mainsnak.get('datavalue', {})
                value = datavalue.get('value', {})
                if isinstance(value, dict):
                    val_str = value.get('id', value.get('time', json.dumps(value)))
                else:
                    val_str = str(value)
                property_label = PROPERTY_LABELS.get(prop_id, prop_id)
                claim_lines.append(f'  {property_label}: {val_str[:200]}')
            except Exception:
                pass

    parts = []
    if label:
        parts.append(f'Entity: {label}')
    if desc:
        parts.append(f'Description: {desc}')
    if alias_text:
        parts.append(f'Aliases: {alias_text}')
    if claim_lines:
        parts.append('Properties:\n' + '\n'.join(claim_lines))

    return '\n'.join(parts)


def build_sparql_query(root_qid: str, since: Optional[str] = None) -> str:
    date_filter = ''
    if since:
        if not re.match(r'^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2})?$', since):
            logger.warning(f"Invalid timestamp format for SPARQL filter: {since}")
            since = since[:19]
        date_filter = f'\n  FILTER(?modified >= "{since}"^^xsd:dateTime)'

    return f'''
SELECT DISTINCT ?qid ?qidLabel ?qidDescription ?modified ?altLabel WHERE {{
  {{
    ?qid wdt:P31 wd:{root_qid} .
  }} UNION {{
    ?qid wdt:P279 wd:{root_qid} .
  }} UNION {{
    ?qid wdt:P31/wdt:P279 wd:{root_qid} .
  }}
  ?qid schema:dateModified ?modified .
  ?qid wikibase:statements ?statementCount .
  FILTER(?statementCount > 0)
  {date_filter}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{LANGUAGES.replace('|', ',')},en". }}
}}
ORDER BY DESC(?modified)
'''


def update_specialist(
    specialist_id: int, domain: str, root_qid: str,
    since: Optional[str] = None, limit: int = 0,
    dry_run: bool = False
) -> int:
    query = build_sparql_query(root_qid, since)
    logger.info(f'[{domain}] SPARQL query for {root_qid} (since={since or "ALL"})')

    bindings = run_sparql(query)
    if bindings is None:
        logger.error(f'[{domain}] SPARQL failed')
        return 0

    qids_seen = set()
    qid_to_info = {}
    for b in bindings:
        qid_raw = b.get('qid', {}).get('value', '')
        qid = qid_raw.split('/')[-1] if '/' in qid_raw else qid_raw
        modified = b.get('modified', {}).get('value', '')
        label = b.get('qidLabel', {}).get('value', '')
        desc = b.get('qidDescription', {}).get('value', '')

        if not qid or qid in qids_seen:
            continue
        qids_seen.add(qid)
        qid_to_info[qid] = {
            'modified': modified,
            'label': label,
            'description': desc,
        }

    logger.info(f'[{domain}] Found {len(qid_to_info)} new/modified QIDs')

    if limit > 0:
        qid_to_info = dict(list(qid_to_info.items())[:limit])
        logger.info(f'[{domain}] Limited to {limit} QIDs')

    if not qid_to_info:
        return 0

    qids_list = list(qid_to_info.keys())
    if dry_run:
        logger.info(f'[{domain}] DRY RUN — would process {len(qids_list)} QIDs')
        for qid in qids_list[:5]:
            info = qid_to_info[qid]
            logger.info(f'  {qid}: {info["label"]} ({info["modified"]})')
        if len(qids_list) > 5:
            logger.info(f'  ... and {len(qids_list) - 5} more')
        return len(qids_list)

    entities = fetch_entities_batch(qids_list)
    logger.info(f'[{domain}] Fetched {len(entities)} entity details')

    db = get_db_manager()
    added = 0
    for qid in qids_list:
        entity = entities.get(qid)
        if not entity:
            logger.warning(f'[{domain}] No entity data for {qid}')
            continue

        structured = build_structured_knowledge(entity)
        if not structured:
            logger.warning(f'[{domain}] Empty knowledge for {qid}')
            continue

        if is_garbage_content(structured):
            logger.debug(f'[{domain}] Garbage content rejected for {qid}')
            continue

        label = qid_to_info[qid]['label'] or qid
        topic = f'{label} — Wikidata entity'

        try:
            db.execute_query(
                '''INSERT OR IGNORE INTO knowledge_packages
                   (topic, source_url, domain, qid, structured_knowledge, created_at)
                   VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)''',
                (
                    topic,
                    f'https://www.wikidata.org/entity/{qid}',
                    domain,
                    qid,
                    structured,
                )
            )
            added += 1
        except Exception as e:
            logger.warning(f'[{domain}] Failed to insert {qid}: {e}')

    logger.info(f'[{domain}] Added {added} packages')
    return added


def main():
    parser = argparse.ArgumentParser(description='Download Wikidata entities for specialists')
    parser.add_argument('--full', action='store_true',
                        help='Download ALL entities (ignore last sync timestamp)')
    parser.add_argument('--incremental', action='store_true', default=True,
                        help='Only download entities modified since last sync (default)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be downloaded without inserting')
    parser.add_argument('--limit', type=int, default=0,
                        help='Max QIDs per specialist (0 = unlimited)')
    parser.add_argument('--specialist', type=str, default='all',
                        help='Only update this specialist domain')
    args = parser.parse_args()

    db = get_db_manager()
    rows = db.execute_query(
        '''SELECT id, domain, root_qid, last_wikidata_download
           FROM specialist_registry
           WHERE parent_id IS NULL
           ORDER BY domain''',
        fetch=True
    )

    if args.specialist != 'all':
        rows = [r for r in rows if r['domain'] == args.specialist]
        if not rows:
            logger.error(f'Specialist "{args.specialist}" not found')
            return

    total_added = 0
    progress = {
        'pid': os.getpid(),
        'started_at': datetime.utcnow().isoformat(),
        'current_domain': '',
        'packages_this_domain': 0,
        'total_added': 0,
        'finished': False,
    }
    write_progress(progress)

    for row in rows:
        sid = row['id']
        domain = row['domain']
        root_qid = row['root_qid']
        last_sync = row.get('last_wikidata_download')

        since = None
        if not args.full and last_sync:
            since = last_sync.replace(' ', 'T') if 'T' not in last_sync else last_sync

        progress['current_domain'] = domain
        progress['packages_this_domain'] = 0
        write_progress(progress)

        added = update_specialist(
            sid, domain, root_qid,
            since=since, limit=args.limit,
            dry_run=args.dry_run
        )
        total_added += added
        progress['packages_this_domain'] = added
        progress['total_added'] = total_added
        write_progress(progress)

        if added > 0 and not args.dry_run:
            db.execute_query(
                '''UPDATE specialist_registry
                   SET last_wikidata_download = CURRENT_TIMESTAMP
                   WHERE id = ?''',
                (sid,)
            )
            db.execute_query(
                '''INSERT INTO wikidata_sync_log
                   (specialist_id, domain, qids_added, sync_type, status, completed_at)
                   VALUES (?, ?, ?, ?, 'SUCCESS', CURRENT_TIMESTAMP)''',
                (sid, domain, added, 'full' if args.full else 'incremental')
            )

    progress['current_domain'] = ''
    progress['finished'] = True
    write_progress(progress)

    logger.info(f'Total added: {total_added} packages')
    if args.dry_run:
        logger.info('DRY RUN — no changes were made')


if __name__ == '__main__':
    main()
