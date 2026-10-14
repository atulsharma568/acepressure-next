# Specification acceptance map

| Requested area | Implementation / how to verify |
|---|---|
| Public tipping page | `/`, `/tip/acepressure`; responsive form, avatar upload, presets, custom amount, message/email, TTS/voice, one alert-sound picker (sound library with per-sound minimum tip), pending/success/expiry and top supporters |
| UPI directly to bank | Dynamic exact-amount `upi://pay` intent and QR; no intermediary settlement; locally configured recipient |
| Payment verification | `Store.verify`, atomic exact paise match, expiry, reference dedup, session binding, receipt outcomes |
| Ignore unrelated transfers | Round-number and nonmatching credits ignored; coincidental exact paise collision remains an SMS-mode limitation |
| iPhone bridge | Bearer-authenticated `/api/bridge/credit`, structured extractor contract, strict example adapter, detailed action-by-action recipe; real bank adapter/device test outstanding |
| Permanent database | SQLite schema/migration, statuses and audit, no record auto-deletion |
| Dashboard statistics | IST today/yesterday/week/last-week/month/last-month/year/lifetime/stream/custom; count/average/largest/top/frequent/supporter count |
| Supporter history | Private email grouping (unverified), anonymous IDs, all historical rows/messages, first/latest/largest and moderation |
| Leaderboards | Admin 3/5/10, stream/day/week/month/lifetime; compact/large OBS top three |
| Goals | Create/edit/delete/show/hide, target/start offset, period/carry/custom dates, design/progress style, live verified amounts, no destructive resets |
| Alerts | Horizontal/vertical persistent queues, tiers, names/messages (links shown as [link] since 1.6.2), entry/exit, custom sounds from the sound library (viewer picks and a default, or the alert video's own sound), TTS, test/replay; 1.6.4: Skip alert (card, sound and voice), Replay in full, sessions that start when OBS goes live, names filtered and blocked supporters anonymous on the boards |
| Sound library | Admin -> Sound library: one row per uploaded sound (WAV/MP3/OGG up to 30 s and 8 MB; several files at once since 1.6.7), Viewers can pick, minimum tip, volume (1.6.2), default sound, Test on stream; Add starter sounds adds 8 free sound effects made from code for AcePressure (CC0) plus 14 Indian meme slots for your own clips |
| TTS | Engine/voice/minimum/length/filter/mute/skip; browser voices, or audio made by AcePressure for OBS (Windows SAPI, Edge, Piper, Azure); Hindi availability is device/voice-dependent; 1.6.2: voice volume, pronunciations, emoji and long repeats skipped by the voice, sentence-aware Hinglish, and "The voice reads" preview; 1.6.3: "Read whole messages" switch (Live activity, OBS dock, Admin -> TTS) that reads only the first 20-500 characters when off; 1.6.4: a backup voice (Piper or Windows) when Edge or Azure fails, whole messages for tips from an amount, and whole-word filtering |
| Activity Dock | Login-protected dock, connection/totals/top/recent, replay/skip/mute/block/test; 1.6.4: Skip alert, and warnings when the voice fails, OBS stops streaming or viewers can't reach the tip link |
| OBS routes | `/overlay/alert`, `/overlay/goal`, `/overlay/top3`, `/overlay/recent`, `/obs/activity` |
| Admin dashboard | Fifteen functional sections, search/filter/CSV, private analytics, sound library and avatar upload, audit |
| Graphs | Daily/weekly/monthly bucket chart and exact-value table, custom date range and per-stream table |
| Security | Separate capabilities, CSRF, per-visitor rate limits (also behind Tailscale Funnel), XSS-safe DOM, parameterized SQL, fail-closed matching, no SMS logging |
| Windows operation | Installer/start/demo/test/backup scripts, local secrets setup, optional sign-in task; native Windows execution remains to be verified on your PC |
| Cloud option | Stable HTTPS tunnel instructions and example; same source supports persistent-disk VPS; no deployment made |
| Migration | All originals archived, hash manifest, optional backup-before-new-JSON script, no original scene overwrite |
| Simulator | Separate demo DB + authenticated simulate action; labelled test alerts never affect revenue |
| Documentation | README plus deployment, iPhone, OBS, migration, architecture, security, operations and testing guides |

## Explicitly outside this release

There is no bank/PSP signed webhook integration, automatic refund, verified donor email/login, email receipt delivery, cloud TTS subscription, guaranteed iOS retry queue, or claim of exactly-once on-air playback. The original specification did not require the first five as integrations; the latter limitations are documented rather than hidden.
