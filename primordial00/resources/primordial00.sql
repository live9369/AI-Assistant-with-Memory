-- Minimal executable projection of the design. Separate from the full schema.
PRAGMA foreign_keys=ON;
PRAGMA application_id=1345335344;
PRAGMA user_version=1;
BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS identity_instances(
 id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at REAL NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('active','degraded','stopped')),
 controller TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runtime_events(
 seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
 instance_id TEXT NOT NULL REFERENCES identity_instances(id),
 source TEXT NOT NULL, source_event_id TEXT NOT NULL, payload TEXT NOT NULL CHECK(json_valid(payload)),
 created_at REAL NOT NULL, UNIQUE(instance_id,source,source_event_id)
);
CREATE TABLE IF NOT EXISTS activities(
 id TEXT PRIMARY KEY, event_id TEXT UNIQUE NOT NULL REFERENCES runtime_events(id),
 state TEXT NOT NULL CHECK(state IN ('pending','running','waiting_input','completed','failed','cancelled')),
 revision INTEGER NOT NULL DEFAULT 0, input_epoch INTEGER NOT NULL DEFAULT 0,
 cancelled INTEGER NOT NULL DEFAULT 0 CHECK(cancelled IN (0,1)), error TEXT
);
CREATE TABLE IF NOT EXISTS jobs(
 id TEXT PRIMARY KEY, activity_id TEXT NOT NULL REFERENCES activities(id),
 due_at REAL NOT NULL, state TEXT NOT NULL CHECK(state IN ('queued','running','waiting','completed','failed','cancelled')),
 attempt INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS memories(
 id TEXT PRIMARY KEY, instance_id TEXT NOT NULL REFERENCES identity_instances(id),
 event_id TEXT NOT NULL REFERENCES runtime_events(id), content TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('observation','outcome')), created_at REAL NOT NULL,
 UNIQUE(event_id,kind)
);
CREATE TABLE IF NOT EXISTS goals(
 id TEXT PRIMARY KEY, activity_id TEXT UNIQUE NOT NULL REFERENCES activities(id),
 content TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('active','completed','cancelled','failed'))
);
CREATE TABLE IF NOT EXISTS thought_requests(
 id TEXT PRIMARY KEY, activity_id TEXT UNIQUE NOT NULL REFERENCES activities(id),
 request_json TEXT NOT NULL CHECK(json_valid(request_json)), request_hash TEXT NOT NULL,
 prepared_revision INTEGER NOT NULL, input_epoch INTEGER NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('prepared','succeeded','cancelled','failed')),
 accepted_result_id TEXT UNIQUE REFERENCES thought_results(id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE IF NOT EXISTS thought_attempts(
 id TEXT PRIMARY KEY, request_id TEXT NOT NULL REFERENCES thought_requests(id),
 attempt_no INTEGER NOT NULL, state TEXT NOT NULL CHECK(state IN ('sent','received','failed')),
 created_at REAL NOT NULL, UNIQUE(request_id,attempt_no)
);
CREATE TABLE IF NOT EXISTS thought_results(
 id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL REFERENCES thought_requests(id),
 attempt_id TEXT UNIQUE NOT NULL REFERENCES thought_attempts(id),
 output_json TEXT NOT NULL CHECK(json_valid(output_json)), accepted_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS action_intents(
 id TEXT PRIMARY KEY, activity_id TEXT UNIQUE NOT NULL REFERENCES activities(id),
 kind TEXT NOT NULL CHECK(kind='write_note'), arguments_json TEXT NOT NULL CHECK(json_valid(arguments_json)),
 arguments_hash TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('awaiting_approval','authorized','running','succeeded','unknown','cancelled')),
 approved_hash TEXT, operation_key TEXT UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS action_attempts(
 id TEXT PRIMARY KEY, intent_id TEXT NOT NULL REFERENCES action_intents(id),
 attempt_no INTEGER NOT NULL, state TEXT NOT NULL CHECK(state IN ('running','succeeded','unknown')),
 receipt_json TEXT CHECK(receipt_json IS NULL OR json_valid(receipt_json)), UNIQUE(intent_id,attempt_no)
);
CREATE TABLE IF NOT EXISTS action_results(
 intent_id TEXT PRIMARY KEY REFERENCES action_intents(id),
 attempt_id TEXT UNIQUE NOT NULL REFERENCES action_attempts(id),
 evidence_json TEXT NOT NULL CHECK(json_valid(evidence_json)), verified_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS commitments(
 id TEXT PRIMARY KEY, instance_id TEXT NOT NULL REFERENCES identity_instances(id),
 content TEXT NOT NULL, due_at REAL NOT NULL, activity_id TEXT REFERENCES activities(id),
 state TEXT NOT NULL CHECK(state IN ('active','fulfilled','cancelled'))
);
CREATE TABLE IF NOT EXISTS health_checks(
 id INTEGER PRIMARY KEY, checked_at REAL NOT NULL, state TEXT NOT NULL,
 evidence_json TEXT NOT NULL CHECK(json_valid(evidence_json))
);
CREATE INDEX IF NOT EXISTS jobs_due ON jobs(state,due_at);
INSERT OR IGNORE INTO schema_migrations VALUES(1,strftime('%s','now'));
COMMIT;
