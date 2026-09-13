CREATE TABLE _migration_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE NOT NULL,
                        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
CREATE TABLE activity_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    level TEXT DEFAULT 'INFO',
                    message TEXT NOT NULL
                );
CREATE TABLE cartridge_offsets (
                        qid TEXT PRIMARY KEY,
                        cartridge_name TEXT,
                        offset_start INTEGER,
                        offset_end INTEGER,
                        specialist_id INTEGER,
                        status TEXT DEFAULT 'Available',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (specialist_id) REFERENCES specialist_registry(id)
                    );
CREATE TABLE cascade_checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                checkpoint_num INTEGER NOT NULL,
                entities_processed INTEGER NOT NULL,
                total_matches INTEGER DEFAULT 0,
                elapsed_seconds REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            , specialist_matches TEXT);
CREATE TABLE cycle_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        specialist_id INTEGER NOT NULL,
        success INTEGER NOT NULL,
        quality REAL DEFAULT 0.0,
        ema_before REAL,
        ema_after REAL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    , failure_type TEXT DEFAULT 'knowledge');
CREATE TABLE ema_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        specialist_id INTEGER NOT NULL,
                        ema_score REAL NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (specialist_id) REFERENCES specialist_registry(id)
                    );
CREATE INDEX idx_activity_log_level
                ON activity_log(level, id)
            ;
CREATE INDEX idx_cartridge_specialist
                    ON cartridge_offsets(specialist_id)
                ;
CREATE INDEX idx_cycle_specialist
                    ON cycle_history(specialist_id, id)
                ;
CREATE INDEX idx_ema_specialist
                    ON ema_history(specialist_id, timestamp)
                ;
CREATE INDEX idx_knowledge_domain
                    ON knowledge_packages(domain)
                ;
CREATE INDEX idx_knowledge_qid
                    ON knowledge_packages(qid)
                ;
CREATE INDEX idx_kp_domain_created ON knowledge_packages(domain, created_at DESC);
CREATE UNIQUE INDEX idx_kp_qid_domain
                        ON knowledge_packages(qid, domain)
                    ;
CREATE INDEX idx_qid_expansions_specialist_checkpoint
            ON qid_expansions(specialist_id, discovered_at_checkpoint)
        ;
CREATE INDEX idx_source_reputation_score
                            ON source_reputation(trust_score DESC)
                        ;
CREATE INDEX idx_specialist_domain
                    ON specialist_registry(domain)
                ;
CREATE INDEX idx_specialist_parent
                    ON specialist_registry(parent_id)
                ;
CREATE TABLE knowledge_packages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        topic TEXT NOT NULL,
                        source_url TEXT NOT NULL,
                        domain TEXT,
                        structured_knowledge TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    , qid TEXT DEFAULT NULL, subdomain_path TEXT DEFAULT NULL, absorbed_at TIMESTAMP DEFAULT NULL, batch_run_id INTEGER DEFAULT 0);
CREATE VIRTUAL TABLE knowledge_packages_fts
        USING fts5(topic, structured_knowledge, domain,
                   content='knowledge_packages', content_rowid='id');
CREATE TABLE 'knowledge_packages_fts_config'(k PRIMARY KEY, v) WITHOUT ROWID;
CREATE TABLE 'knowledge_packages_fts_data'(id INTEGER PRIMARY KEY, block BLOB);
CREATE TABLE 'knowledge_packages_fts_docsize'(id INTEGER PRIMARY KEY, sz BLOB);
CREATE TABLE 'knowledge_packages_fts_idx'(segid, term, pgno, PRIMARY KEY(segid, term)) WITHOUT ROWID;
CREATE TABLE matched_qids (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                qid TEXT NOT NULL,
                                specialist_id INTEGER NOT NULL,
                                entity_id TEXT,
                                domain TEXT,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                processed INTEGER DEFAULT 0,
                                FOREIGN KEY (specialist_id) REFERENCES specialist_registry(id),
                                UNIQUE(qid, specialist_id)
                            );
CREATE TABLE pipeline_status (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    current_specialist TEXT DEFAULT '',
                    current_model TEXT DEFAULT '',
                    current_cycle INTEGER DEFAULT 0,
                    total_cycles INTEGER DEFAULT 0,
                    phase TEXT DEFAULT '',
                    status TEXT DEFAULT 'IDLE',
                    elapsed_seconds REAL DEFAULT 0,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                , start_epoch REAL DEFAULT 0, cascade_entities INTEGER DEFAULT 0, cascade_max INTEGER DEFAULT 0, cascade_checkpoint INTEGER DEFAULT 0);
CREATE TABLE qid_expansions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                specialist_id INTEGER NOT NULL,
                qid TEXT NOT NULL,
                discovered_at_checkpoint INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (specialist_id) REFERENCES specialist_registry(id),
                UNIQUE(specialist_id, qid)
            );
CREATE TABLE source_reputation (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                netloc TEXT NOT NULL UNIQUE,
                                trust_score INTEGER NOT NULL DEFAULT 40,
                                tier INTEGER NOT NULL DEFAULT 3,
                                access_count INTEGER DEFAULT 0,
                                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            );
CREATE TABLE specialist_match_cache (
        specialist_id INTEGER PRIMARY KEY,
        domain TEXT,
        match_count INTEGER,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
CREATE TABLE specialist_registry (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        domain TEXT NOT NULL UNIQUE,
                        model TEXT NOT NULL,
                        root_qid TEXT NOT NULL,
                        properties TEXT NOT NULL,
                        ema_score REAL DEFAULT 0.10,
                        tier INTEGER DEFAULT 3,
                        packages_absorbed INTEGER DEFAULT 0,
                        status TEXT DEFAULT 'IDLE',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    , parent_id INTEGER DEFAULT NULL REFERENCES specialist_registry(id), qid_path TEXT DEFAULT NULL, weighted_success REAL DEFAULT 0.0, weighted_fail REAL DEFAULT 0.0, last_wikidata_download TIMESTAMP DEFAULT NULL, last_wikidata_feed TIMESTAMP DEFAULT NULL, feed_packages INTEGER DEFAULT 0, wikidata_total_entities INTEGER DEFAULT 0);
CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE super_expert_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        super_expert_id INTEGER NOT NULL,
        specialist_id INTEGER NOT NULL,
        weight REAL NOT NULL DEFAULT 0.1,
        FOREIGN KEY (super_expert_id) REFERENCES super_experts(id),
        FOREIGN KEY (specialist_id) REFERENCES specialist_registry(id),
        UNIQUE(super_expert_id, specialist_id)
    );
CREATE TABLE super_experts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        domain TEXT NOT NULL UNIQUE,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
CREATE TABLE wikidata_sync_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        specialist_id INTEGER NOT NULL,
        domain TEXT NOT NULL,
        qids_added INTEGER DEFAULT 0,
        sync_type TEXT DEFAULT 'incremental',
        status TEXT DEFAULT 'SUCCESS',
        error_message TEXT,
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP,
        FOREIGN KEY (specialist_id) REFERENCES specialist_registry(id)
    );
