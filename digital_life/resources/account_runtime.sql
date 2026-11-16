CREATE TABLE IF NOT EXISTS acct_activity_owners(activity_id TEXT PRIMARY KEY REFERENCES activities(id),account_id TEXT NOT NULL,scope_tier TEXT NOT NULL CHECK(scope_tier IN ('privileged','scoped')));
CREATE INDEX IF NOT EXISTS acct_activity_account ON acct_activity_owners(account_id,activity_id);
CREATE TABLE IF NOT EXISTS acct_conversation_turns(ordinal INTEGER PRIMARY KEY AUTOINCREMENT,account_id TEXT NOT NULL,activity_id TEXT NOT NULL UNIQUE REFERENCES activities(id));
CREATE INDEX IF NOT EXISTS acct_conversation_account ON acct_conversation_turns(account_id,ordinal);
CREATE TABLE IF NOT EXISTS acct_memory_domains(memory_id TEXT PRIMARY KEY REFERENCES memory_items(id),domain TEXT NOT NULL CHECK(domain IN ('private','shared')),owner_account_id TEXT NOT NULL,scope_tier TEXT NOT NULL CHECK(scope_tier IN ('privileged','scoped')));
CREATE TABLE IF NOT EXISTS acct_object_owners(object_id TEXT PRIMARY KEY,account_id TEXT NOT NULL,scope_tier TEXT NOT NULL CHECK(scope_tier IN ('privileged','scoped')),activity_id TEXT REFERENCES activities(id));
CREATE TABLE IF NOT EXISTS acct_policy_state(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL);
INSERT OR IGNORE INTO acct_policy_state VALUES(1,0);
