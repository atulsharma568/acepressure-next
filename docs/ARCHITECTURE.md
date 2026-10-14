# Architecture and data contract

## One ledger, two types of clients

- **Server**: Flask HTTP API served by Waitress, one process, 12 threads. Before it creates the app, `run.py` checks the port (`acepressure/startup.py`) and refuses to start a second copy. Waitress trusts `X-Forwarded-For` only from 127.0.0.1 (the local tunnel), so rate limits apply per visitor behind Tailscale Funnel.
- **Storage**: SQLite WAL on a local disk. A new connection per operation; `BEGIN IMMEDIATE` serializes monetary decisions and queue claims. Amounts are integer paise; no floating-point comparison is used in matching.
- **Viewer**: original HTML/CSS/vanilla JS, no build/CDN dependency. Public checkout creates a bearer-protected pending request and a dynamic UPI QR.
- **Phone**: trusted sender-filtered Shortcut submits a minimal authenticated credit receipt over HTTPS.
- **Admin**: password-hash login, signed HttpOnly session, SameSite Strict cookie and per-session CSRF header on every mutation.
- **OBS**: separate read/playback token. No admin or bridge credentials in OBS URLs. Small authenticated polling requests update widgets and consume queue entries. OBS pages get alerts before normal browser tabs (see Overlay delivery).

## Payment sequence

1. Viewer enters a whole-rupee display amount.
2. Under an immediate database transaction, allocate an available paise suffix 01–99 for that amount. Reserve it for 24 hours even if the pending request expires.
3. Save PENDING with `created`, `expires`, optional current `session_id`, display amount, exact requested amount, supporter, moderated message and TTS preferences. Default expiry is 10 minutes.
4. Generate UPI intent/QR directly to the configured recipient. `am` contains the exact rupee amount. The server never takes possession of money. UPI apps may ignore/change intent parameters, so instruct the payer to check recipient and amount; wrong amounts do not auto-match.
5. Authenticated bridge validates sender/parser/direction/reference/time, then calls `Store.verify`.
6. In one transaction: expire overdue requests, reject/reuse duplicate references, find exactly one matching PENDING with matching exact amount and compatible receipt time, and record the receipt outcome.
7. Set VERIFIED, actual amount, bank reference, receipt timestamp and verification source. Create the event plus horizontal/vertical delivery rows only when the pending request belongs to the still-active session.
8. Stats and goals query VERIFIED/MANUAL tips. Public amounts use `display_paise`, financial totals use `actual_paise`.

Retries are idempotent by reference. A receipt first recorded as unmatched remains unmatched on a simple retry: it cannot accidentally attach to a later request. An admin can explicitly reconcile it with a manual correction and audit reason.

## State transitions

- New request → `PENDING`.
- Valid receipt before expiry → `VERIFIED`.
- Deadline passes → `EXPIRED`.
- Admin bank reconciliation → `MANUAL` (no automatic alert).
- Admin marks an actual refund → `REFUNDED` (excluded from current support/revenue totals; original record and actual amount remain).
- Admin rejects an incorrect request → `REJECTED`.

Corrections can also expire/exclude an incorrect record. The audit records old/new status/amount/reference and mandatory reason. An existing bank reference is immutable. The dashboard cannot turn a record into automatic VERIFIED; only the bridge matcher can do that. A refund cannot be reactivated through the UI. Marking a status never sends or reverses bank money.

## Identity and supporter grouping

An optional normalized email is privately hashed with a stable identity secret to find a supporter ID. The email is also stored for the private dashboard. It is **not verified** and is not used for authentication. Someone can claim another person's email/name. Anonymous requests get separate random supporter IDs, even if names repeat; this avoids falsely merging unrelated people with common names. Moderator block/mute applies to that supporter identity and is not a complete ban system.

Email verification, donor logins and cryptographically verified supporter identity are not implemented. A future optional identity provider can attach to supporter IDs without changing tip amounts/history.

## Database tables

| Table | Purpose |
|---|---|
| `tips` | Permanent requests and payment history, amounts, status, reference, session, TTS and acknowledgment flags |
| `supporters` | Private identity hash/email, current name, block/mute settings |
| `sessions` | Stream title and start/end; unique active session |
| `receipts` | Permanent unique bank reference and minimal normalized receipt/outcome |
| `amount_leases` | Exact payment-amount reuse quarantine |
| `goals` | Editable target, starting amount, date/reset rules and overlay appearance |
| `alerts` | Durable event payload, tip association and five-minute delivery window |
| `deliveries` | Per-horizontal/vertical channel claim, owner, lease and completion |
| `audit` | Admin correction/settings/session/alert history |
| `settings` | Non-secret creator/payment/alert settings, including `default_sound` and the one-time `sound_library_migrated` marker |
| `soundboards` | Sound library: one row per uploaded sound (name, emoji, category, minimum tip to pick, viewer-pickable flag, audio file) |
| `rate_limits` | Expiring rate buckets; no permanent visitor IP history |
| `schema_version` | Applied schema version |

`001_initial.sql` is idempotent and provides indexes/checks/foreign keys. Future schema versions must add migrations before use, backed by a database backup. There are no default live tip records or hard-coded goal targets.

Every SQLite SQL migration (`001`–`009`) is idempotent and runs on each start. `007_soundboards.sql` created the sound library table; `008_alert_tip_index.sql` (1.6.0) adds an index on `alerts(tip_id)` for the alert status in Live activity and the tip page's `alert_queued`; `009_sound_volume.sql` (1.6.2) adds the per-sound volume. The 1.6.0 move into the sound library is a one-time Python step, not SQL: it first writes `data/backups/before-1.6.0-sound-library.sqlite3` (only when there are sounds to move), runs in one transaction, never touches media files and records the `sound_library_migrated` marker. If it fails it rolls back, logs to the console and is retried on the next start.

## PostgreSQL shadow migration (1.6.7)

`acepressure/migrations/postgresql/001_shadow_schema.sql` is a separate,
replay-safe PostgreSQL 14+ baseline for SQLite migrations `001`–`009`; it is
never loaded by the Flask SQLite startup runner. `scripts/migrate_sqlite_to_postgres.py`
is an opt-in importer for a consistent SQLite backup. It validates SQLite
integrity and schema, checkpoints tables in a staging schema, verifies row
counts and SHA-256 checksums before each checkpoint commit, and verifies all
tables and identity high-water marks before publishing `acepressure_shadow`.
It never prints row values or credentials. A non-empty target requires the
explicit `--replace-target` flag, and the previous target is archived.

This is a shadow copy and verification step only. The Flask runtime remains on
SQLite until a separately reviewed cutover, rollback, payment-reconciliation,
and operational verification is complete. See
[`POSTGRES_MIGRATION.md`](POSTGRES_MIGRATION.md) for the commands and recovery
workflow.

## Time and goals

Receipt/request storage uses UTC epoch seconds. Reporting windows use Asia/Kolkata; weeks start Monday. Intervals are `[start, end)`; custom end dates are exclusive at the API. The dashboard's date-range selector turns an inclusive last date into next-day midnight IST.

Automatic goals query their current period, plus optional configured start/end boundaries. Carry-forward goals query from their start date and do not reset. A pinned carry-forward stream goal uses its creation-time active session if available. For an unambiguous fixed-session campaign, create it while the session is active. Starting amounts are display offsets, not ledger donations and not financial revenue.

## Sound library (1.6.0)

- Each uploaded sound is one `soundboards` row: `enabled` means viewers can pick it, `min_paise` is the minimum tip to pick it (0 = any tip), and `media_filename` is the stored file in `data/media` (empty for a starter slot still waiting for audio).
- `settings.default_sound` is `chime`, `pulse`, `none` (Silent), `video` (the alert video's own sound) or a row id, and `settings.allow_sound_choice` is the picks switch. `settings.sounds` is kept only as a mirror for older pages and downgrades; its first entry is always the default's sound.
- What an alert plays: the viewer's pick (`soundboard_clip`), even if that sound was later hidden or repriced; otherwise the default. A default with a problem (missing file, removed row, or a visual without sound) plays Chime. A tip made before the upgrade replays its own saved sound when there was no fixed Design studio sound. The payload's `sound_source` is `pick`, `tip`, `default` or `video`. `/api/overlay/claim` repairs a queued alert whose clip was deleted or replaced and sends `alert_video_has_audio` for that alert only; the stored payload is never rewritten.
- Files: uploads are written before the transaction and removed if it fails. A file is deleted only after commit, and only when no row, setting or visual still uses it.
- Starter sounds: 8 CC0 MP3s in `acepressure/starter_sounds`, made by the scripts in `scripts/starter_sounds`. `POST /api/admin/soundboard/seed` adds any missing starter rows (14 meme slots and 8 sound-effect rows), then copies each bundled MP3 under a new random name into the empty row with that name and switches it on. It returns `created` (rows added now) and `ready` (rows that got bundled audio now). It never changes the default or the picks switch, and nothing seeds at startup.

## Readiness (1.6.0)

`acepressure/readiness.py` answers "can viewers tip right now?" in one place. `readiness(store, db, config, settings)` returns the checks in fix order, each `{key, ok, title, fix, link}`: `restart` (live mode, advisory: the `.env` on disk differs from the running `PUBLIC_BASE_URL` or `COOKIE_SECURE`), `upi`, `https`, `verification` (Paytm bridge or SMS bridge enabled) and `accepting`. It also returns `tip_page` (`open`, `setup`, `paused` or `demo`), `tip_url`, the Paytm bridge status, `sms_bridge`, and `review_count` and `oldest_review_at` (notifications waiting for review from the last 24 hours). It never raises and never returns a token, hash or `.env` value other than the public address. `/api/admin/state` and `/api/admin/paytm` return it as `health`. `/api/public/config` adds `availability` (the `tip_page` value) and reports `ready` only in demo mode or when payment is ready on an https address. `startup_summary(app)` builds the plain-ASCII summary the Start window prints.

## Overlay delivery (1.6.0)

An in-memory registry (`app.extensions['ace_overlay_clients']`) records each overlay page per channel: its client type (`obs`, `browser`, `forced` for `&claim=always`, or `unknown` for overlay scripts from before 1.6.0), when it was last seen and whether it is on standby. Entries unseen for 15 seconds are pruned, except a page that is playing an alert, which stays listed for its 180-second lease. While an OBS page on the same channel was seen in the last 5 seconds, a `browser` claim returns `{alert: null, standby: true}` without touching the database; every other client claims as before. Nothing is stored in the database and owner ids are never exposed. `/api/admin/state` returns the summary as `overlays`, and the test-alert reply includes it.

## API summary

All JSON bodies must be objects. Errors are JSON with `error` and a non-2xx status. No CORS permission is granted to third-party websites.

| Route | Method / auth | Behavior |
|---|---|---|
| `/api/public/config` | GET | Public preferences/readiness only (`availability`: open, setup, paused or demo; `sounds` holds only the default sound) |
| `/api/public/tips` | POST, rate-limited | New pending request with an optional sound pick (`soundboard_id`; `sound` is ignored since 1.6.0); returns private tip status token |
| `/api/public/tips/:id` | GET, X-Tip-Token | Own request status (including `alert_queued`), no bank/email data |
| `/api/public/tips/:id/qr` | GET, token query | Dynamic QR for active live payment only |
| `/api/public/top` | GET | Public-safe lifetime top three |
| `/api/public/soundboard` | GET | Sounds viewers can pick, with their minimum tips (empty when picks are off) |
| `/api/bridge/credit` | POST, Bearer bridge token | Parse/minimize/deduplicate/match bank credit |
| `/api/login` | POST, login rate limit | Password login, session and CSRF token |
| `/api/admin/state` | GET, session | Settings, summaries, goals, recent activity with alert status, readiness `health`, connected `overlays` |
| `/api/admin/transactions` | GET, session | Filter/search, `export=csv` |
| `/api/admin/transactions/:id` | POST, session+CSRF | Audited manual corrections |
| `/api/admin/supporters[/:id]` | GET/POST, admin | Profiles and mute/block |
| `/api/admin/sessions` | GET/POST, admin | History/start/end |
| `/api/admin/analytics` | GET, admin | Period/custom summary and day/week/month series |
| `/api/admin/goals` | POST, admin | Create/edit/delete by ID |
| `/api/admin/settings` | POST, admin | Validated settings updates (`sounds` is read-only since 1.6.0) |
| `/api/admin/alerts` | POST, admin | Test/replay/skip; a test can play one library sound (`soundboard_id`) and reports connected overlays |
| `/api/admin/media` | POST multipart, admin | Sound-library upload (WAV/MP3/OGG ≤30 s, 8 MB) or re-encoded avatar |
| `/api/admin/soundboard[/:id[/media]]` | GET/POST/DELETE, admin | List, add, edit, delete and replace the audio of library sounds (`enabled` = viewers can pick, `min_paise` = minimum tip) |
| `/api/admin/soundboard/default` | POST, admin | Set the default sound |
| `/api/admin/soundboard/seed` | POST, admin | Add the starter rows and copy the bundled starter sounds into empty ones; returns `created` and `ready` |
| `/api/admin/obs` | GET, admin | Overlay token, source URLs and `local_base` for OBS on this PC |
| `/api/admin/audit` | GET, admin | Corrections and minimal receipt outcomes |
| `/api/admin/backup` | POST, admin | Consistent database download |
| `/api/admin/simulate/:id` | POST, admin+DEMO_MODE | Disposable demonstration credit |
| `/api/overlay/state` | GET, overlay key | Public-safe goals/top/recent, audio controls |
| `/api/overlay/claim` | POST, overlay key | One queue claim per channel; lease 180 seconds; a normal browser tab gets standby while OBS is connected |
| `/api/overlay/ack` | POST, key+claim owner | Complete own delivery and update flags |
| `/api/overlay/tts/:event_id` | GET, overlay key | Server-rendered speech (Windows, Azure, Edge, Piper) for unexpired alert |

Viewer status tokens, bridge bearer tokens and overlay keys are random. They are different capabilities; possession of an overlay URL does not let someone mark payments verified.

## Scaling limits

This is a single-creator application, not a multi-tenant payments platform. SQLite writes are serialized, amount suffixes allow at most 99 allocations per whole-rupee amount within the 24-hour quarantine, and the admin view shows up to 2,000 filtered rows while CSV exports all matches. Lifetime summaries currently aggregate ledger rows in memory; for very large histories, add SQL aggregation/pagination. These limits should be measured before expanding to many simultaneous streamers.
