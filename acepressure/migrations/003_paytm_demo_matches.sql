-- Persistent deduplication records, separate from short-lived diagnostic rows.
-- These are notification fingerprints, not bank references.
CREATE TABLE IF NOT EXISTS paytm_events (
 fingerprint TEXT PRIMARY KEY,
 ingested INTEGER NOT NULL,
 amount_paise INTEGER,
 outcome TEXT NOT NULL,
 tip_id TEXT,
 repeats INTEGER NOT NULL DEFAULT 0
);
