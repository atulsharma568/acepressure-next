-- Diagnostics only. Never referenced by payment verification or revenue queries.
CREATE TABLE IF NOT EXISTS paytm_captures (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 fingerprint TEXT UNIQUE NOT NULL,
 captured_at INTEGER NOT NULL,
 amount_paise INTEGER,
 outcome TEXT NOT NULL,
 repeats INTEGER NOT NULL DEFAULT 0
);
