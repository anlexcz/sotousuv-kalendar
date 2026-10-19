PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT,
  description TEXT
);

INSERT OR IGNORE INTO settings(key, value, description) VALUES
  ('schema_version', '2', 'Canonical D1 schema version'),
  ('production_status', 'DISABLED', 'Production automation stays disabled until explicitly approved'),
  ('scheduler_enabled', 'NE', 'Scheduled source checks'),
  ('discovery_enabled', 'NE', 'Automatic discovery'),
  ('event_creation_enabled', 'NE', 'Automatic event creation');

CREATE TABLE IF NOT EXISTS events (
  event_id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  description TEXT,
  municipality TEXT,
  place TEXT,
  region TEXT,
  country TEXT,
  route TEXT,
  organizer TEXT,
  all_day TEXT NOT NULL CHECK(all_day IN ('ANO','NE')),
  event_state TEXT NOT NULL CHECK(event_state IN ('AKTIVNI','ZRUSENA','SKRYTA')),
  review_state TEXT NOT NULL CHECK(review_state IN ('NEZKONTROLOVANO','ZKONTROLOVANO','KE_KONTROLE')),
  categories TEXT NOT NULL,
  public_source_id TEXT,
  publish TEXT NOT NULL CHECK(publish IN ('ANO','NE')),
  editorial_state TEXT NOT NULL DEFAULT 'DRAFT' CHECK(editorial_state IN ('DRAFT','READY')),
  origin_type TEXT NOT NULL CHECK(origin_type IN ('AUTO','MANUAL','IMPORT')),
  origin_ref TEXT,
  is_active TEXT NOT NULL DEFAULT 'ANO' CHECK(is_active IN ('ANO','NE')),
  row_version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  updated_by TEXT NOT NULL,
  reviewed_at TEXT,
  reviewed_by TEXT,
  effective_hash TEXT,
  deleted_at TEXT,
  deleted_by TEXT,
  note TEXT
);

CREATE TABLE IF NOT EXISTS event_auto (
  event_id INTEGER PRIMARY KEY REFERENCES events(event_id),
  title TEXT,
  description TEXT,
  municipality TEXT,
  place TEXT,
  region TEXT,
  country TEXT,
  route TEXT,
  organizer TEXT,
  all_day TEXT,
  event_state TEXT,
  categories TEXT,
  auto_updated_at TEXT NOT NULL,
  run_id TEXT,
  auto_hash TEXT,
  source_presence TEXT,
  source_missing_since TEXT,
  note TEXT
);

CREATE TABLE IF NOT EXISTS terms (
  term_id TEXT PRIMARY KEY,
  event_id INTEGER NOT NULL REFERENCES events(event_id),
  date_from TEXT NOT NULL,
  date_to TEXT NOT NULL,
  term_state TEXT NOT NULL CHECK(term_state IN ('AKTIVNI','ZRUSENY','PRESUNUTY')),
  replacement_term_id TEXT REFERENCES terms(term_id),
  is_active TEXT NOT NULL DEFAULT 'ANO' CHECK(is_active IN ('ANO','NE')),
  row_version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  updated_by TEXT NOT NULL,
  effective_hash TEXT,
  deleted_at TEXT,
  note TEXT
);

CREATE TABLE IF NOT EXISTS term_auto (
  term_id TEXT PRIMARY KEY,
  event_id INTEGER NOT NULL,
  date_from TEXT NOT NULL,
  date_to TEXT NOT NULL,
  term_state TEXT NOT NULL,
  replacement_term_id TEXT,
  auto_updated_at TEXT NOT NULL,
  run_id TEXT,
  auto_hash TEXT,
  note TEXT
);

CREATE TABLE IF NOT EXISTS sources (
  source_id TEXT PRIMARY KEY,
  url TEXT NOT NULL UNIQUE,
  source_type TEXT NOT NULL,
  source_scope TEXT NOT NULL CHECK(source_scope IN ('EVENT','DISCOVERY','BOTH')),
  label TEXT,
  active TEXT NOT NULL DEFAULT 'ANO' CHECK(active IN ('ANO','NE')),
  origin TEXT NOT NULL,
  parser_key TEXT,
  check_policy TEXT NOT NULL DEFAULT 'ADAPTIVE',
  next_check_at TEXT,
  last_checked_at TEXT,
  last_success_at TEXT,
  last_http_status INTEGER,
  consecutive_errors INTEGER NOT NULL DEFAULT 0,
  etag TEXT,
  last_modified TEXT,
  content_hash TEXT,
  first_seen_at TEXT,
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL,
  note TEXT
);

CREATE TABLE IF NOT EXISTS event_sources (
  link_id TEXT PRIMARY KEY,
  event_id INTEGER NOT NULL REFERENCES events(event_id),
  source_id TEXT NOT NULL REFERENCES sources(source_id),
  source_role TEXT NOT NULL,
  priority_override INTEGER,
  active TEXT NOT NULL DEFAULT 'ANO' CHECK(active IN ('ANO','NE')),
  first_seen_at TEXT,
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL,
  note TEXT,
  UNIQUE(event_id, source_id)
);

CREATE TABLE IF NOT EXISTS findings (
  finding_id TEXT PRIMARY KEY,
  finding_type TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('OPEN','RESOLVED','REJECTED')),
  title_hint TEXT,
  source_id TEXT REFERENCES sources(source_id),
  event_id INTEGER REFERENCES events(event_id),
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  next_check_at TEXT,
  resolution TEXT,
  resolved_at TEXT,
  resolved_by TEXT,
  created_run_id TEXT,
  updated_at TEXT NOT NULL,
  note TEXT
);

CREATE TABLE IF NOT EXISTS observations (
  observation_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES sources(source_id),
  subject_type TEXT NOT NULL CHECK(subject_type IN ('EVENT','TERM','FINDING')),
  subject_ref TEXT,
  event_id INTEGER REFERENCES events(event_id),
  finding_id TEXT REFERENCES findings(finding_id),
  field_key TEXT NOT NULL,
  value_state TEXT NOT NULL CHECK(value_state IN ('VALUE','EXPLICIT_EMPTY','MISSING','SOURCE_UNAVAILABLE')),
  value TEXT,
  observed_at TEXT NOT NULL,
  source_published_at TEXT,
  extraction_method TEXT NOT NULL CHECK(extraction_method IN ('DETERMINISTIC','LLM','IMPORT')),
  run_id TEXT,
  content_hash TEXT,
  evidence_ref TEXT,
  request_id TEXT,
  note TEXT
);

CREATE TABLE IF NOT EXISTS overrides (
  override_id TEXT PRIMARY KEY,
  entity_type TEXT NOT NULL CHECK(entity_type IN ('EVENT','TERM')),
  entity_id TEXT NOT NULL,
  field_key TEXT NOT NULL,
  manual_value TEXT,
  mode TEXT NOT NULL CHECK(mode IN ('DO_SHODY','DO_DALSI_ZMENY','TRVALE')),
  base_auto_value TEXT,
  base_auto_hash TEXT,
  active TEXT NOT NULL CHECK(active IN ('ANO','NE')),
  created_at TEXT NOT NULL,
  created_by TEXT NOT NULL,
  ended_at TEXT,
  ended_by TEXT,
  ended_reason TEXT,
  note TEXT
);

CREATE TABLE IF NOT EXISTS history (
  history_id TEXT PRIMARY KEY,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  field_key TEXT,
  old_value TEXT,
  new_value TEXT,
  origin TEXT NOT NULL,
  actor_id TEXT,
  action TEXT NOT NULL,
  run_id TEXT,
  request_id TEXT,
  reference_id TEXT,
  created_at TEXT NOT NULL,
  note TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
  alert_id TEXT PRIMARY KEY,
  event_id INTEGER REFERENCES events(event_id),
  entity_type TEXT,
  entity_id TEXT,
  alert_type TEXT NOT NULL,
  severity TEXT NOT NULL CHECK(severity IN ('INFO','WARNING','CRITICAL')),
  field_key TEXT,
  message TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('OPEN','RESOLVED','IGNORED')),
  run_id TEXT,
  created_at TEXT NOT NULL,
  resolved_at TEXT,
  resolved_by TEXT,
  resolution_note TEXT
);

CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  run_type TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL CHECK(status IN ('STARTED','SUCCESS','PARTIAL','FAILED')),
  input_count INTEGER NOT NULL DEFAULT 0,
  created_events INTEGER NOT NULL DEFAULT 0,
  updated_fields INTEGER NOT NULL DEFAULT 0,
  closed_overrides INTEGER NOT NULL DEFAULT 0,
  alerts_created INTEGER NOT NULL DEFAULT 0,
  error_count INTEGER NOT NULL DEFAULT 0,
  actor TEXT,
  note TEXT
);

CREATE TABLE IF NOT EXISTS requests (
  request_id TEXT PRIMARY KEY,
  operation TEXT NOT NULL,
  entity_type TEXT,
  entity_id TEXT,
  status TEXT NOT NULL CHECK(status IN ('STARTED','SUCCESS','FAILED')),
  started_at TEXT NOT NULL,
  finished_at TEXT,
  result_hash TEXT,
  run_id TEXT,
  actor TEXT,
  error TEXT,
  note TEXT
);

CREATE INDEX IF NOT EXISTS idx_terms_event_id ON terms(event_id);
CREATE INDEX IF NOT EXISTS idx_sources_due ON sources(active, next_check_at);
CREATE INDEX IF NOT EXISTS idx_event_sources_event ON event_sources(event_id, active);
CREATE INDEX IF NOT EXISTS idx_event_sources_source ON event_sources(source_id, active);
CREATE INDEX IF NOT EXISTS idx_observations_event ON observations(event_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_observations_source ON observations(source_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_findings_due ON findings(status, next_check_at);
CREATE INDEX IF NOT EXISTS idx_history_entity ON history(entity_type, entity_id, created_at);
CREATE INDEX IF NOT EXISTS idx_alerts_open ON alerts(status, severity, created_at);
