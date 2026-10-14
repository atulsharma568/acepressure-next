CREATE TABLE IF NOT EXISTS browser_supporters (
 token_hash TEXT PRIMARY KEY, supporter_id TEXT NOT NULL REFERENCES supporters(id), expires INTEGER NOT NULL
);
