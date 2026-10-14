CREATE TABLE IF NOT EXISTS supporter_aliases (
 source_id TEXT PRIMARY KEY REFERENCES supporters(id),
 target_id TEXT NOT NULL REFERENCES supporters(id),
 CHECK(source_id != target_id)
);
