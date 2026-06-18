"""
Multi-core Wikidata extractor using multiprocessing.
Replaces BatchWikidataExtractor for Phase A cascade with parallel workers.
Each worker runs in its own process (no GIL contention) with its own DB connection.
"""

import gzip
import ijson
import json
import time
import logging
import multiprocessing as mp
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple
import sqlite3

from tools.update_wikidata import build_structured_knowledge, _pick_first
from config.settings import LANGUAGES, WIKIDATA_DUMP_PATH

logger = logging.getLogger(__name__)

CHECKPOINT_INTERVAL = 50000
BATCH_SIZE = 1000
FLUSH_SIZE = 10000


def _get_entity_qids(entity: Dict) -> Set[str]:
    qids = set()
    claims = entity.get('claims', {})
    for prop_id in ('P31', 'P279', 'P2579', 'P921', 'P101'):
        for claim in claims.get(prop_id, []):
            try:
                qid = claim.get('mainsnak', {}).get('datavalue', {}).get('value', {}).get('id')
                if qid and qid.startswith('Q'):
                    qids.add(qid)
            except Exception:
                pass
    return qids


def worker_main(
    work_queue: mp.Queue,
    stop_event: mp.Event,
    db_path: str,
    spec_targets: Dict[int, Set[str]],
    specialist_matchers: Dict[int, Dict],
    worker_id: int,
):
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA cache_size=-128000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA busy_timeout=15000")

    pending_qids: List[tuple] = []
    pending_kp: List[tuple] = []

    def flush():
        nonlocal pending_qids, pending_kp
        if not pending_qids and not pending_kp:
            return
        for attempt in range(5):
            try:
                if pending_qids:
                    conn.executemany(
                        "INSERT OR IGNORE INTO matched_qids (qid, specialist_id, entity_id, domain) VALUES (?, ?, ?, ?)",
                        pending_qids
                    )
                    pending_qids.clear()
                if pending_kp:
                    conn.executemany(
                        "INSERT OR IGNORE INTO knowledge_packages (topic, source_url, domain, qid, structured_knowledge, created_at) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                        pending_kp
                    )
                    pending_kp.clear()
                conn.commit()
                return
            except sqlite3.OperationalError as e:
                if 'locked' in str(e) and attempt < 4:
                    time.sleep(1.0 * (attempt + 1))
                    conn.rollback()
                    continue
                logger.error(f"Worker {worker_id} flush error (attempt {attempt}): {e}")
                conn.rollback()
                return

    langs = LANGUAGES.split('|')
    processed = 0

    try:
        while True:
            try:
                batch = work_queue.get(timeout=5)
            except:
                if stop_event.is_set() and work_queue.empty():
                    break
                continue

            for entity in batch:
                entity_qids = _get_entity_qids(entity)
                matched_specs = set()
                for sid, targets in spec_targets.items():
                    if entity_qids & targets:
                        matched_specs.add(sid)

                if not matched_specs:
                    continue

                entity_id = entity.get('id', '')
                if not entity_id:
                    continue

                eid = entity['id']
                label = _pick_first(entity.get('labels') or {}, langs)
                structured = build_structured_knowledge(entity, LANGUAGES)

                if not structured or len(structured.strip()) < 20:
                    continue

                topic = f'{label} — Wikidata entity' if label else f'{eid} — Wikidata entity'
                source_url = f'https://www.wikidata.org/entity/{eid}'

                for sid in matched_specs:
                    domain = specialist_matchers[sid]['domain']
                    for qid in entity_qids:
                        pending_qids.append((qid, sid, entity_id, domain))
                    pending_kp.append((topic, source_url, domain, eid, structured))

                processed += 1
                if len(pending_qids) >= FLUSH_SIZE or len(pending_kp) >= FLUSH_SIZE:
                    flush()

            flush()
            work_queue.task_done()

    except Exception as e:
        logger.error(f"Worker {worker_id} crashed: {e}")
        raise
    finally:
        flush()
        conn.close()
        logger.info(f"Worker {worker_id} finished, processed ~{processed} matched entities")


class ParallelWikidataExtractor:
    def __init__(
        self,
        specialist_matchers: Dict,
        db_path: str,
        num_workers: int = 4,
        progress_callback: Optional[Callable] = None,
        checkpoint_callback: Optional[Callable] = None,
    ):
        self.specialist_matchers = specialist_matchers
        self.db_path = db_path
        self.num_workers = num_workers
        self.progress_callback = progress_callback
        self.checkpoint_callback = checkpoint_callback
        self.entities_processed = 0
        self.matched_counts: Dict[str, int] = {}

    def extract_with_timeout(
        self,
        timeout_hours: float = 8.0,
        sample_size: Optional[int] = None,
        loaded_expansions: Optional[Dict[str, Set[int]]] = None,
        resume_offset: int = 0,
    ) -> bool:
        loaded_expansions = loaded_expansions or {}
        timeout_seconds = timeout_hours * 3600
        start_time = time.time()

        spec_targets: Dict[int, Set[str]] = {}
        for sid, info in self.specialist_matchers.items():
            root_qid = info.get('root_qid')
            if root_qid:
                qid_set = {root_qid}
                for qid, spec_ids in loaded_expansions.items():
                    if sid in spec_ids:
                        qid_set.add(qid)
                spec_targets[sid] = qid_set
                self.matched_counts[sid] = 0

        logger.info(f"Spec targets built for {len(spec_targets)} specialists")
        logger.info(f"Total expansions loaded: {sum(len(v) for v in spec_targets.values())}")

        # self._drop_fts()  # skipped - FTS tables persist during run

        work_queue = mp.JoinableQueue(maxsize=20)
        stop_event = mp.Event()

        workers = []
        for i in range(self.num_workers):
            p = mp.Process(
                target=worker_main,
                args=(work_queue, stop_event, self.db_path, spec_targets, self.specialist_matchers, i),
                daemon=True,
            )
            p.start()
            workers.append(p)

        try:
            entities_processed = 0
            entities_sent = 0
            checkpoint_num = 0
            batch: List[Dict] = []

            with gzip.open(WIKIDATA_DUMP_PATH, 'rb') as f:
                parser = ijson.items(f, 'item')

                if resume_offset > 0:
                    skipped = 0
                    for _ in range(resume_offset):
                        next(parser)
                        skipped += 1
                        if skipped % 500000 == 0:
                            logger.info(f"Reanudando: saltadas {skipped:,} entidades...")
                    entities_processed = resume_offset
                    logger.info(f"Reanudacion: saltadas {resume_offset:,} entidades")

                for entity in parser:
                    entities_processed += 1
                    entities_sent += 1

                    elapsed = time.time() - start_time
                    if elapsed > timeout_seconds:
                        logger.critical("TIMEOUT alcanzado")
                        return False

                    batch.append(entity)

                    if len(batch) >= BATCH_SIZE:
                        work_queue.put(batch)
                        batch = []

                    if entities_processed % 10000 == 0 and self.progress_callback:
                        rate = entities_processed / elapsed if elapsed > 0 else 0
                        self.progress_callback(entities_processed, elapsed, rate)

                    if entities_processed % CHECKPOINT_INTERVAL == 0 and self.checkpoint_callback:
                        checkpoint_num += 1
                        work_queue.join()
                        self.checkpoint_callback(
                            checkpoint_num,
                            entities_processed,
                            self._get_matches_from_db(),
                            {},
                            elapsed,
                        )

            if batch:
                work_queue.put(batch)
                entities_sent += len(batch)
                batch = []

            stop_event.set()
            work_queue.join()

            elapsed = time.time() - start_time
            if self.checkpoint_callback:
                checkpoint_num += 1
                self.checkpoint_callback(
                    checkpoint_num,
                    entities_processed,
                    self._get_matches_from_db(),
                    {},
                    elapsed,
                )

            self.entities_processed = entities_processed
            logger.info(f"Cascade complete: {entities_processed:,} entities in {elapsed:.0f}s")
            return True

        except StopIteration:
            logger.info("Dump fully processed")
            stop_event.set()
            work_queue.join()
            self.entities_processed = entities_processed
            return True
        except Exception as e:
            logger.error(f"Parallel extraction failed: {e}")
            stop_event.set()
            return False
        finally:
            for w in workers:
                if w.is_alive():
                    w.join(timeout=10)

    def _drop_fts(self):
        conn = sqlite3.connect(self.db_path)
        try:
            for name in [
                'knowledge_packages_fts', 'knowledge_packages_fts_data',
                'knowledge_packages_fts_idx', 'knowledge_packages_fts_docsize',
                'knowledge_packages_fts_config',
            ]:
                conn.execute(f"DROP TABLE IF EXISTS {name}")
            conn.commit()
            logger.info("FTS5 tables dropped for write performance")
        finally:
            conn.close()

    def _rebuild_fts(self):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_packages_fts
                USING fts5(topic, structured_knowledge, domain,
                           content='knowledge_packages', content_rowid='id')
            """)
            conn.execute("""
                INSERT INTO knowledge_packages_fts
                SELECT id, topic, structured_knowledge, domain FROM knowledge_packages
            """)
            conn.commit()
            logger.info("FTS5 index rebuilt after cascade")
        except Exception as e:
            logger.warning(f"FTS5 rebuild failed (non-critical): {e}")
        finally:
            conn.close()

    def _get_matches_from_db(self) -> Dict[int, int]:
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.execute(
                "SELECT specialist_id, COUNT(*) as cnt FROM matched_qids GROUP BY specialist_id"
            )
            return {row[0]: row[1] for row in cur.fetchall()}
        finally:
            conn.close()
