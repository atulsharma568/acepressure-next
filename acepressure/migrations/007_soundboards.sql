-- Soundboard: streamer-curated gallery of alert sounds, each with a minimum tip amount.
-- Tippers browse a grid on the public tip page and pick ONE clip to play on OBS when
-- their tip is confirmed. The admin manages this via Admin -> Soundboard.
--
-- Added in v1.5.0. Backward compatible: tips.sound continues to work for pre-existing
-- clips, soundboard entries are additive. If both are present, the overlay prefers
-- soundboard_clip (unless the admin's Design Studio "Separate alert audio" wins — that
-- override takes priority over everything).

CREATE TABLE IF NOT EXISTS soundboards (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    emoji TEXT NOT NULL DEFAULT '',           -- optional single-char/emoji icon for the tile
    media_filename TEXT,                       -- file under <DATA>/media/, nullable until uploaded
    category TEXT NOT NULL DEFAULT 'General',  -- Hindi Memes / SFX / Reactions / Valorant / Trending / General
    min_paise INTEGER NOT NULL DEFAULT 0 CHECK(min_paise >= 0),
    display_order INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
    duration_ms INTEGER DEFAULT 0,             -- clip duration in ms (0 = unknown)
    created INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS soundboards_enabled_order ON soundboards(enabled, display_order);
CREATE INDEX IF NOT EXISTS soundboards_category ON soundboards(category);

-- Link a tip to the soundboard clip the viewer picked. NULLable: tips created
-- before this migration or without a soundboard pick stay at NULL.
ALTER TABLE tips ADD COLUMN soundboard_id TEXT REFERENCES soundboards(id);
