-- PulseMetrics V2 runtime schema. Only the native collector creates/writes this database.
-- Minimum SQLite 3.37 (STRICT tables); retained 3.45.3 supports these statements.
-- Set foreign_keys and busy_timeout on EVERY connection. Writer verifies WAL result.
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;
PRAGMA busy_timeout = 500;
BEGIN IMMEDIATE;
PRAGMA user_version = 1;

CREATE TABLE sessions (
    session_order INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL UNIQUE,
    clock_warning INTEGER NOT NULL DEFAULT 0 CHECK(clock_warning IN (0,1)),
    started_utc_us INTEGER NOT NULL CHECK(started_utc_us > 0),
    ended_utc_us INTEGER,
    state TEXT NOT NULL CHECK(state IN ('running','clean','interrupted','failed')),
    window_seconds INTEGER NOT NULL CHECK(window_seconds BETWEEN 1 AND 60),
    sample_seconds INTEGER NOT NULL CHECK(sample_seconds BETWEEN 1 AND 60),
    config_revision INTEGER NOT NULL CHECK(config_revision >= 1),
    CHECK(ended_utc_us IS NULL OR ended_utc_us >= started_utc_us),
    CHECK(state <> 'clean' OR ended_utc_us IS NOT NULL)
) STRICT;

CREATE TABLE sources (
    source_id INTEGER PRIMARY KEY,
    source_key TEXT NOT NULL UNIQUE CHECK(length(source_key) BETWEEN 1 AND 64),
    kind TEXT NOT NULL CHECK(kind IN ('system','process','application')),
    display_name TEXT NOT NULL CHECK(length(display_name) BETWEEN 1 AND 260),
    pid INTEGER,
    creation_filetime INTEGER, -- exact Windows creation FILETIME, 100ns since 1601
    first_seen_utc_us INTEGER NOT NULL CHECK(first_seen_utc_us > 0),
    last_seen_utc_us INTEGER NOT NULL CHECK(last_seen_utc_us > 0),
    ended_utc_us INTEGER,
    selected INTEGER NOT NULL DEFAULT 0 CHECK(selected IN (0,1)),
    CHECK(source_key GLOB '[A-Za-z]*' AND source_key NOT GLOB '*[^A-Za-z0-9_.-]*'),
    CHECK((kind='process' AND pid IS NOT NULL AND creation_filetime IS NOT NULL
           AND pid > 0 AND creation_filetime > 0)
       OR (kind<>'process' AND pid IS NULL AND creation_filetime IS NULL)),
    CHECK(ended_utc_us IS NULL OR ended_utc_us > 0),
    UNIQUE(pid,creation_filetime)
) STRICT;
CREATE TRIGGER immutable_source_identity BEFORE UPDATE OF source_key,kind,pid,creation_filetime ON sources
BEGIN SELECT RAISE(ABORT,'source identity is immutable'); END;

CREATE TABLE tracking_intervals (
    tracking_id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(source_id),
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    start_utc_us INTEGER NOT NULL CHECK(start_utc_us > 0),
    end_utc_us INTEGER,
    state TEXT NOT NULL DEFAULT 'active' CHECK(state IN ('active','closed','interrupted')),
    end_reason TEXT CHECK(end_reason IN ('untracked','ended','shutdown','interrupted')),
    CHECK((state='active' AND end_utc_us IS NULL AND end_reason IS NULL)
       OR (state='interrupted' AND end_utc_us IS NULL AND end_reason='interrupted')
       OR (state='closed' AND end_utc_us IS NOT NULL AND end_utc_us >= start_utc_us AND end_reason IS NOT NULL))
) STRICT;
CREATE UNIQUE INDEX one_open_tracking ON tracking_intervals(source_id) WHERE state='active';
CREATE INDEX tracking_by_session ON tracking_intervals(session_id,start_utc_us);

CREATE TABLE metrics (
    metric_id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(source_id),
    name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 128),
    kind TEXT NOT NULL CHECK(kind IN ('counter','gauge','timer')),
    unit TEXT NOT NULL CHECK(unit IN ('count','percent','bytes','ms','unit')),
    CHECK(name GLOB '[A-Za-z]*' AND name NOT GLOB '*[^A-Za-z0-9_.-]*'),
    CHECK((kind='counter' AND unit='count') OR (kind='timer' AND unit='ms')
       OR (kind='gauge' AND unit IN ('count','percent','bytes','unit'))),
    UNIQUE(source_id,name),
    UNIQUE(metric_id,kind)
) STRICT;
CREATE TRIGGER immutable_metric_contract BEFORE UPDATE OF source_id,name,kind,unit ON metrics
BEGIN SELECT RAISE(ABORT,'metric contract is immutable; register a new name'); END;

-- One committed collector batch, including health, even if no series has samples.
CREATE TABLE windows (
    window_id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    sequence INTEGER NOT NULL CHECK(sequence >= 0),
    start_utc_us INTEGER NOT NULL CHECK(start_utc_us > 0),
    end_utc_us INTEGER NOT NULL CHECK(end_utc_us > start_utc_us),
    elapsed_us INTEGER NOT NULL CHECK(elapsed_us = end_utc_us-start_utc_us),
    partial INTEGER NOT NULL CHECK(partial IN (0,1)),
    committed_utc_us INTEGER NOT NULL CHECK(committed_utc_us > 0),
    UNIQUE(session_id,sequence),
    UNIQUE(session_id,start_utc_us)
) STRICT;
CREATE INDEX windows_time ON windows(start_utc_us,end_utc_us);
CREATE INDEX windows_retention ON windows(end_utc_us);
CREATE TRIGGER immutable_window BEFORE UPDATE ON windows
BEGIN SELECT RAISE(ABORT,'committed windows are immutable'); END;

CREATE TABLE aggregates (
    window_id INTEGER NOT NULL REFERENCES windows(window_id) ON DELETE CASCADE,
    metric_id INTEGER NOT NULL,
    metric_kind TEXT NOT NULL,
    sample_count INTEGER NOT NULL CHECK(sample_count BETWEEN 1 AND 1000000),
    sample_sum REAL NOT NULL CHECK(sample_sum BETWEEN -1.0e15 AND 1.0e15),
    sample_min REAL NOT NULL CHECK(sample_min BETWEEN -1.0e12 AND 1.0e12),
    sample_max REAL NOT NULL CHECK(sample_max BETWEEN sample_min AND 1.0e12),
    last_value REAL NOT NULL CHECK(last_value BETWEEN sample_min AND sample_max),
    first_received_utc_us INTEGER NOT NULL,
    last_received_utc_us INTEGER NOT NULL CHECK(last_received_utc_us >= first_received_utc_us),
    PRIMARY KEY(window_id,metric_id),
    FOREIGN KEY(metric_id,metric_kind) REFERENCES metrics(metric_id,kind),
    CHECK(metric_kind='gauge' OR (sample_min >= 0 AND sample_sum >= 0))
) STRICT;
CREATE INDEX aggregates_metric_window ON aggregates(metric_id,window_id);
CREATE TRIGGER validate_aggregate BEFORE INSERT ON aggregates BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM windows w WHERE w.window_id=NEW.window_id
        AND NEW.first_received_utc_us >= w.start_utc_us
        AND NEW.last_received_utc_us < w.end_utc_us
    ) THEN RAISE(ABORT,'receipt outside window') END;
    SELECT CASE WHEN EXISTS (
        SELECT 1 FROM metrics m WHERE m.metric_id=NEW.metric_id AND
        ((m.unit='percent' AND (NEW.sample_min < 0 OR NEW.sample_max > 100))
        OR (m.unit IN ('bytes','count','ms') AND NEW.sample_min < 0))
    ) THEN RAISE(ABORT,'invalid unit range') END;
END;
CREATE TRIGGER immutable_aggregate BEFORE UPDATE ON aggregates
BEGIN SELECT RAISE(ABORT,'committed aggregates are immutable'); END;

CREATE TABLE alert_rules (
    rule_id TEXT PRIMARY KEY CHECK(length(rule_id)=36), -- caller UUID; idempotent create
    metric_id INTEGER NOT NULL REFERENCES metrics(metric_id),
    label TEXT NOT NULL CHECK(length(label) BETWEEN 1 AND 120),
    field TEXT NOT NULL CHECK(field IN ('sum','rate','last','mean','min','max')),
    operator TEXT NOT NULL CHECK(operator IN ('gt','ge','lt','le')),
    threshold REAL NOT NULL CHECK(threshold BETWEEN -1.0e300 AND 1.0e300),
    severity TEXT NOT NULL CHECK(severity IN ('warning','critical')),
    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
    created_utc_us INTEGER NOT NULL CHECK(created_utc_us > 0)
) STRICT;
CREATE INDEX rules_metric ON alert_rules(metric_id,enabled);
CREATE TRIGGER validate_rule BEFORE INSERT ON alert_rules BEGIN
    SELECT CASE WHEN NOT EXISTS (
        SELECT 1 FROM metrics m WHERE m.metric_id=NEW.metric_id AND
        ((m.kind='counter' AND NEW.field IN ('sum','rate'))
        OR (m.kind='gauge' AND NEW.field IN ('last','mean','min','max'))
        OR (m.kind='timer' AND NEW.field IN ('mean','min','max')))
    ) THEN RAISE(ABORT,'field not applicable to metric type') END;
END;
CREATE TRIGGER immutable_rule BEFORE UPDATE OF rule_id,metric_id,label,field,operator,threshold,severity,created_utc_us ON alert_rules
BEGIN SELECT RAISE(ABORT,'create a new rule revision'); END;

CREATE TABLE alert_events (
    event_id INTEGER PRIMARY KEY,
    rule_id TEXT NOT NULL REFERENCES alert_rules(rule_id),
    opened_session_order INTEGER NOT NULL REFERENCES sessions(session_order),
    last_session_order INTEGER NOT NULL REFERENCES sessions(session_order),
    closed_session_order INTEGER REFERENCES sessions(session_order),
    opened_utc_us INTEGER NOT NULL CHECK(opened_utc_us > 0),
    last_evaluated_utc_us INTEGER NOT NULL CHECK(last_evaluated_utc_us > 0),
    closed_utc_us INTEGER,
    close_reason TEXT CHECK(close_reason IN ('recovered','rule_disabled','source_ended')),
    first_window_id INTEGER REFERENCES windows(window_id) ON DELETE SET NULL,
    last_window_id INTEGER REFERENCES windows(window_id) ON DELETE SET NULL,
    opening_value REAL NOT NULL CHECK(opening_value BETWEEN -1.0e300 AND 1.0e300),
    last_value REAL NOT NULL CHECK(last_value BETWEEN -1.0e300 AND 1.0e300),
    CHECK(last_session_order >= opened_session_order),
    CHECK(last_session_order <> opened_session_order OR last_evaluated_utc_us >= opened_utc_us),
    CHECK((closed_utc_us IS NULL AND close_reason IS NULL AND closed_session_order IS NULL) OR
          (closed_utc_us IS NOT NULL AND close_reason IS NOT NULL AND closed_session_order >= opened_session_order
           AND (closed_session_order <> opened_session_order OR closed_utc_us >= opened_utc_us)))
) STRICT;
CREATE UNIQUE INDEX one_open_event_per_rule ON alert_events(rule_id) WHERE closed_utc_us IS NULL;
CREATE INDEX events_time ON alert_events(opened_utc_us);
CREATE INDEX events_retention ON alert_events(closed_utc_us);

CREATE TABLE health_samples (
    window_id INTEGER PRIMARY KEY REFERENCES windows(window_id) ON DELETE CASCADE,
    datagrams_received INTEGER NOT NULL CHECK(datagrams_received >= 0),
    datagrams_rejected INTEGER NOT NULL CHECK(datagrams_rejected >= 0),
    lines_received INTEGER NOT NULL CHECK(lines_received >= 0),
    accepted INTEGER NOT NULL CHECK(accepted >= 0),
    rejected INTEGER NOT NULL CHECK(rejected >= 0),
    known_dropped INTEGER NOT NULL CHECK(known_dropped >= 0),
    write_failures INTEGER NOT NULL CHECK(write_failures >= 0),
    pending_batches INTEGER NOT NULL CHECK(pending_batches BETWEEN 0 AND 6),
    last_received_utc_us INTEGER,
    last_successful_commit_utc_us INTEGER,
    clock_warning INTEGER NOT NULL CHECK(clock_warning IN (0,1))
) STRICT;

CREATE VIEW metric_windows AS
SELECT a.*, m.source_id,m.name,m.unit,w.session_id,w.sequence,
       w.start_utc_us,w.end_utc_us,w.elapsed_us,w.partial,
       a.sample_sum/a.sample_count AS sample_mean,
       CASE WHEN a.metric_kind='counter' THEN a.sample_sum*1000000.0/w.elapsed_us
            WHEN a.metric_kind='timer' THEN a.sample_count*1000000.0/w.elapsed_us
            ELSE NULL END AS rate
FROM aggregates a JOIN metrics m ON m.metric_id=a.metric_id
JOIN windows w ON w.window_id=a.window_id;

COMMIT;
-- A schema bootstrap is one-time only. An existing DB must pass version/integrity
-- checks; do not execute this file again or use IF NOT EXISTS to hide mismatch.
-- Transactional insertion order: windows -> aggregates -> alert changes -> health.
-- Only the collector writer modifies the schema/history at runtime.
