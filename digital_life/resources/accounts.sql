CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY,username TEXT NOT NULL UNIQUE,display_name TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('root','admin','member','guest')),status TEXT NOT NULL CHECK(status IN ('provisioning','active','disabled')),password_hash TEXT,revision INTEGER NOT NULL DEFAULT 0,created_at REAL NOT NULL,CHECK(role='root' OR password_hash IS NOT NULL));
CREATE UNIQUE INDEX IF NOT EXISTS accounts_single_root ON accounts(role) WHERE role='root';
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,account_id TEXT NOT NULL REFERENCES accounts(id),account_revision INTEGER NOT NULL,created_at REAL NOT NULL,last_seen REAL NOT NULL,expires_at REAL NOT NULL,revoked INTEGER NOT NULL DEFAULT 0 CHECK(revoked IN (0,1)));
CREATE INDEX IF NOT EXISTS account_session_owner ON sessions(account_id);
CREATE TABLE IF NOT EXISTS login_attempts(bucket TEXT NOT NULL,at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS account_login_window ON login_attempts(at,bucket);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,at REAL NOT NULL,actor_id TEXT,action TEXT NOT NULL,target_id TEXT,details TEXT NOT NULL);
