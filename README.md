**Version 1.6.8 — Clear payment buttons that fill in the amount.** On the payment step, Google Pay, PhonePe, Paytm and Other UPI app are now large buttons at the top instead of a hidden list. PhonePe and Paytm open on their payment screen with the amount filled in, and tapping any of them also copies the exact amount. Paytm notifications for ₹1,000 or more (shown as ₹1,000.37) now match.

See [update instructions](docs/UPDATE_1.6.8.md), [what changed](docs/CHANGELOG.md) and [project handover](docs/CHAT_HANDOVER.md).

**Version 1.6.7 — Add several sounds or artwork files at once.** In Sound library and Design studio, choose several files in the file picker: AcePressure uploads them one after another and then lists anything it couldn't take. Design studio menus also show the names your files were uploaded with.

See [update instructions](docs/UPDATE_1.6.7.md), [what changed](docs/CHANGELOG.md) and [project handover](docs/CHAT_HANDOVER.md).

**Version 1.6.6 — Start.bat turns your tip link on.** When AcePressure starts in live mode and Tailscale Funnel is off, it runs `tailscale funnel --bg 8765` for you, so you don't have to type it before a stream. Supporter names on stream are also no longer filtered inside words.

See [update instructions](docs/UPDATE_1.6.6.md), [what changed](docs/CHANGELOG.md) and [project handover](docs/CHAT_HANDOVER.md).

**Version 1.6.4 — A stream session starts when OBS goes live, Skip alert stops the whole alert, Replay in full, a backup voice when the voice service fails, a warning when viewers can't reach your tip link, and stronger moderation (names filtered, blocked supporters anonymous on the boards, whole-word filtering).** Line breaks and “<3” in messages are fixed, the cut is cleaner, Test alert is long enough to hear it, and the tip page stays calm while a payment waits for approval.

See [update instructions](docs/UPDATE_1.6.4.md), [what changed](docs/CHANGELOG.md) and [project handover](docs/CHAT_HANDOVER.md).

**Version 1.6.3 — Read whole messages, or only the start of long ones: one button in Live activity and in the OBS dock.** When it's off, the voice reads the first 100 characters (you choose 20–500) and the alert card still shows the whole message.

See [update instructions](docs/UPDATE_1.6.3.md), [what changed](docs/CHANGELOG.md) and [project handover](docs/CHAT_HANDOVER.md).

**Version 1.6.2 — Volume for every sound and the voice, links hidden on stream, your own pronunciations, emoji skipped by the voice, and smarter Hinglish.**

See [update instructions](docs/UPDATE_1.6.2.md), [what changed](docs/CHANGELOG.md) and [project handover](docs/CHAT_HANDOVER.md).

**Version 1.6.1 — TTS draft preservation, conservative Hinglish handling and Piper WAV compatibility.** See [update instructions](docs/UPDATE_1.6.1.md).

**Version 1.6.0 — One sound library: upload each meme once, choose what viewers can pick and at what price, and pick a default. Edge and Piper voices now speak in OBS.** Admin → Sound library replaces Sounds/media and Soundboard, and the tip page has one **Alert sound** picker that starts with **Streamer’s default**. **Add starter sounds** adds 8 free sound effects made for AcePressure from code (Vine Boom, Air Horn, Ba Dum Tss and more, CC0) plus 14 Indian meme slots for your own clips. Your existing sounds move into the library by themselves on first start, after a backup copy of your database is saved. Also in this release: one checklist that says exactly why tips are paused (dashboard, Paytm page, Start window and tip page), mid-stream warnings when no stream session is running or payments wait for your review, an alert status on every tip, OBS sources that take alerts before a forgotten browser tab, "OBS on this PC" links that keep working if Tailscale drops, per-visitor rate limits behind Tailscale Funnel, a second copy that refuses to start, and a Tailscale setup that confirms Funnel before it changes `.env`. 692 tests pass. See `docs/CHANGELOG.md`.

**Version 1.5.9 — Broken audio is fixed when you upload it, and your own filenames are kept.** Upload any MP3/OGG/WAV (myinstants.com downloads included) on Sounds/media, a Soundboard tile or the alert bundle: files that already play are stored untouched, and files a browser can't play are converted to a standard MP3 automatically (needs FFmpeg: run `Install_Media_Tools.bat` once). Clips over the limit (20 s alert sounds, 30 s soundboard clips) are refused, never silently cut. The name you uploaded is shown instead of the random stored name. Also in this release: a redesigned payment step, Sounds/media chips and per-file status, OBS overlays that fit their Browser Source sizes on Windows, clear messages for over-size uploads, Windows hardening (CRLF batch files, UTF-8 everywhere, pinned MIME types, a path-safe `Fix_Audio.bat`), soundboard clips that go live on your tip page when you upload them, and a test alert that plays your own default sound. 503 tests pass. See `docs/CHANGELOG.md`.

**Version 1.5.8 — Fix_Audio.bat + 👨 Male 1 / 👩 Female 1 explicit voice labels.** Direct response to two user asks: *"i have downlaoded it from myinstant.com — can you make a bat file which can fix the broken mp3?"* and *"for the tts voice you have written voice 1 ,2,3,4 — write male and female as well — and add male and female emojis — and for male 2 voices are there so there right male 1, male 2."* **(1)** New drag-and-drop `Fix_Audio.bat` at the repo root: drop any MP3 / OGG / WAV from myinstants.com (or any site that serves non-standard audio) → outputs `<name>_fixed.mp3` next to the original, guaranteed browser-safe (MPEG Layer 3, 128 kbps CBR, 48 kHz stereo, metadata stripped, 20 s cap). Admin panel surfaces a yellow banner pointing to it whenever any BROKEN sounds are detected. **(2)** Voice picker on the tipping page: labels are now `👨 Male 1`, `👨 Male 2`, `👩 Female 1`, `👩 Female 2` with proper emoji + gender-coloured borders (was `♂ Male voice 1` with text symbol). Server now auto-backfills `voice_genders` from voice IDs for admins who upgraded from <1.5.4 without re-saving — fixes the "Voice 1, 2, 3, 4" generic bucket. Regex upgraded to catch CamelCase voice IDs like `en-US-AvaMultilingualNeural`. 10 new tests (428 total). See `docs/CHANGELOG.md`.

**Version 1.5.7 — Sounds manager: see + preview + delete every uploaded sound, with a red "BROKEN" badge next to any file that won't play.** Direct response to "Preview failed: This audio format is not supported by your browser" when previewing on the tipping page — that error is correct for broken files, but admins had no way to see WHICH file was broken or delete it. New Admin → Sounds/media table at the top of the panel lists every uploaded sound with ffprobe-detected codec, duration, and a green OK / red BROKEN badge (with the specific reason). Each row has ▶ Preview and Delete buttons; deleting removes the file from disk, from `settings.sounds`, and reverts `visuals.alert_sound` to 'viewer' if it was pointing at the deleted file. Also tightened the upload validator so an AAC file renamed to .mp3 is rejected at upload (ffprobe says "that's AAC", server refuses with a clear message). 14 new tests (418 total). See `docs/CHANGELOG.md`.

**Version 1.5.6 — Audio uploads: ffprobe validation catches "no supported source" MP3/OGG at upload time.** Direct response to "upload a mp3 file and it's saying failed to load because no supported source was found when on the tipping page i did preview sound on uploaded alert sound". Root cause: 1.5.3 validated by magic bytes only, so ID3-tag-only MP3s, AAC-ADTS files renamed to .mp3, and MPEG Layer 1/2 files all passed admin upload but then couldn't be decoded by the browser. 1.5.6 adds `probe_audio_file()` using ffprobe to confirm every uploaded audio file has at least one real decodable audio stream before accepting it — admin now sees a specific reason at upload time instead of the browser's cryptic error at playback. Falls back to magic-byte check when ffmpeg isn't installed. Also wires a MediaError-code-to-actionable-text handler on the public page's preview button so legacy broken uploads show "Re-export as standard MP3 (constant bitrate Layer 3) or WAV" instead of raw DOMException text. 6 new tests + existing MP3/OGG tests updated to use real ffmpeg-generated audio (409 total). See `docs/CHANGELOG.md`.

**Version 1.5.5 — OBS alert bundle: upload GIF/MP4 + audio in one step; MP4-with-audio works without double chime.** Direct response to "for the obs alert is there an option to upload a gif or mp4 with the audio or not if not please add and test it" and "test every functionality in this zip file before giving it to me". New Admin → Sounds/media → "Upload alert bundle" form: pick a visual (PNG/WebP/GIF/MP4/WebM) + optional audio (WAV/MP3/OGG), one click to save both into `visuals.alert_image` + `visuals.alert_sound` atomically. If you upload an MP4 that already has its own audio and no separate audio file, the bundle probes it via ffprobe, keeps the embedded audio, sets a new `alert_video_has_audio` flag, and the OBS overlay suppresses the separate chime to avoid double audio. If you provide both, the uploaded audio wins (video audio stripped). 27 new tests (398 total — including 11-area comprehensive sanity sweep). See `docs/CHANGELOG.md`.

**Version 1.5.4 — Public tip page: friendly voice labels + per-card preview.** Direct response to "in the tipping page it's showing the users the whole voice name it should be mail voice 1,2 and same female voice 1,2 and and audio or sound symbol near to it". Voice picker now renders `♂ Male voice 1`, `♀ Female voice 1`, etc. with gender-coloured left borders (blue/pink/grey), a tinted gender icon badge, and a 🔊 speaker button on each card for one-tap preview. Gender comes from the catalog's own gender metadata (now persisted via a new `voice_genders` settings map) OR a client-side name-token regex fallback that covers all 17 of the common Edge/Azure voices. Full voice ID is still what the backend synthesises — only the display changed. 8 new tests (370 total). See `docs/CHANGELOG.md`.

**Version 1.5.3 — Alert sound upload now accepts MP3 and OGG.** Direct response to "upload alert sound is still asking for PCM WAV files" — 1.5.2 fixed the soundboard upload but the SEPARATE alert-sound upload (Admin → Media → Upload alert sound, the chime that fires on every tip in the OBS overlay) still rejected non-WAV. 1.5.3 ports the same magic-byte validator to that endpoint, widens the Design Studio allowlist regex so a `.mp3`/`.ogg` can be saved as `alert_sound`, and updates the admin UI accept/help text. 20 s duration cap kept for all formats (matches the overlay's 21000 ms playback watchdog). 13 new tests (362 total). See `docs/CHANGELOG.md`.

**Version 1.5.2 — Soundboard accepts MP3 and OGG uploads.** Direct response to "the files i have they are in mp3 and OGG file" — the 1.5.0 soundboard validator only accepted PCM WAV, so most meme/SFX libraries required a local conversion step first. 1.5.2 natively accepts WAV, MP3 and OGG via magic-byte detection (trusts file content, not the filename extension), with duration parsed from MPEG frame headers / Ogg Vorbis granule positions. Cap raised from 20 s to 30 s for MP3/OGG; 8 MB file-size cap unchanged. 4 new tests (349 total passing). See `docs/CHANGELOG.md`.

**Version 1.5.1 — Premium polish v2.** End-user polish pass on the public tip page: hero avatar aura (slow pulsing crimson→violet glow), section stagger-in on load, live tier badge under the amount input (Starter → Supporter → Big fan → Legend, respects admin tier thresholds via new `/api/public/config.tiers`), skeleton loaders for Top supporters, celebration success screen with 🎉 pop-in + copy-receipt + 140-particle confetti burst after a VERIFIED tip, SVG noise/grain overlay, press-depress micro-interactions on chips/tiles/CTA. +4 tests, 345 total passing. See `docs/CHANGELOG.md`.

**Version 1.5.0 — Soundboard: streamer-curated meme/SFX gallery for tippers.** Tippers browse your sounds on the public tip page and pick ONE to play on OBS when their tip is confirmed. Grid of glass tiles with instant search, category pills, per-sound minimum tip badges, favorites, preview-play, live tier meter. Admin → Soundboard tab manages everything with inline WAV upload, edit modal, delete, reorder, and a one-click **Seed Indian meme starter catalog** button (20 well-known Hindi meme templates: Thug Life, Chai Peelo, Babu Bhaiya, 440 Volt Ka Jhatka, Rasode Mein Kaun Tha, Pawri Ho Rahi Hai, Binod, Papa Kehte Hain, Ye Chemical Hai, Hera Pheri Laughter, …). 43 new tests + smoke test (341 total green). See `docs/CHANGELOG.md`.

**Version 1.4.3 — Hinglish pronunciation fix (Roman → Devanagari transliteration).** The 1.3.0 SSML `<lang>` fix helped only paid Azure. Edge TTS rewrites its own SSML and ignored the Hindi hints, so "bhai"/"kya"/"tha" still came out as "bai"/"kiya"/"the". This release transliterates ~90 common Roman Hindi words to Devanagari BEFORE handing text to the engine, applied in all four server engines + the browser overlay — but only when the operator-selected voice can speak Hindi (any `hi-*` locale or Multilingual Neural), so English-only voices stay safe. 12 new tests cover the mapping, case-insensitivity, word boundaries, and voice detection. See `docs/CHANGELOG.md`.

**Version 1.4.2 — Verified release with 285-test full-coverage run (0 failures).** New `tests/test_full_release_check.py` (144 tests) plus the 141 existing tests cover Hinglish detection, SSML wrapping, engine dispatch, admin settings whitelist, security headers, overlay lifecycle, package integrity, template loading, and more. See `docs/CHANGELOG.md` and `docs/final-test-results.xml`.

**Version 1.4.1 — Hotfix: unblock Edge / Piper engine selection in Admin → Settings.**

**Version 1.4.0 — Two new FREE TTS engines (Edge TTS + Piper), no Azure subscription required.**
- **Edge TTS**: Microsoft Neural voices (including HINGLISH-READY Multilingual) via Edge's public endpoint. Zero cost, no key, no account. Install: `Install_Edge_TTS.bat`.
- **Piper**: Local offline neural TTS. Zero network calls at synthesis time. Install: `Install_Piper.bat` (downloads starter Hindi + English voices).
- Admin → TTS → Engine now includes `edge` and `piper`. For best Hinglish quality for free, pick an Edge voice tagged HINGLISH-READY.

**Version 1.3.0 — Hinglish TTS fix, premium UI, free static URL via Tailscale Funnel.**
- Hinglish messages now pronounce Hindi words correctly on Azure (SSML `xml:lang` derived from voice; `<lang hi-IN>` wrapping) and on the browser engine (auto-switches to any installed Hindi voice when Hinglish is detected).
- Azure Multilingual Neural voices (code-switching) are surfaced in the admin voice catalog, tagged `HINGLISH-READY`.
- Public tip page, admin dashboard and OBS overlays get a premium polish layer (`static/premium.css` + `static/premium.js`): glass-morphism tip card, animated gradient border, premium typography with Devanagari fallback, confetti burst on tip success and new alerts, smooth number counters on admin metrics.
- New `Setup_Tailscale_URL.bat` gives you a **free, permanent public HTTPS URL** so your iPhone Shortcut automation keeps working forever. No domain purchase, no ngrok warning page, no per-session URL rotation. See [docs/TAILSCALE_FUNNEL.md](docs/TAILSCALE_FUNNEL.md).
- Added a root `LICENSE` (MIT).

Version 1.2.0: Refreshed checkout, optional browser recognition, OBS Design studio with image/video uploads, detected voice choices and TTS diagnostics. Start with [upgrade instructions](docs/UPGRADE_1_2.md).

Version 1.1.3: audited supporter-profile merge. Instructions: docs/SUPPORTER_MERGE.md

Version 1.1.2: separate Google Pay, PhonePe and Paytm checkout buttons. Read docs/PAYMENT_APPS.md for upgrade and device checks.

Version 1.1.1: lower-traffic payment checks. Upgrade and live ngrok instructions: docs/NGROK_LIVE.md

> Version 1.1.0: persistent Paytm bridge, immediate-payment review, real checkout copy controls and HTTPS configuration. Start with [the upgrade and launch guide](docs/UPGRADE_1_1.md).

> Historical 1.0.4 release: optional Paytm pending-tip matching in DEMO ONLY. Read [Paytm matching setup](docs/PAYTM_MATCHING.md). Live Paytm verification remains disabled.

> Historical 1.0.3 release added demo-only Paytm notification diagnostics. See [the Paytm test guide](docs/PAYTM_TEST.md). This does not enable live Paytm verification.

# AcePressure — self-hosted tipping control room

A working Python + SQLite application with a public UPI tipping page, authenticated admin dashboard, permanent payment history, configurable goals, supporter profiles, statistics, OBS alerts and an iPhone credit-receipt bridge.

**Start with demo mode. Live payments are disabled until you configure UPI, HTTPS and either the Paytm review bridge or a tested bank-credit parser/Shortcut.** The package contains no live credentials and never installs over your current OBS setup.

## Windows quick start

1. Extract the complete `AcePressure` folder to `D:\AcePressure-Tips` (or another writable folder). Keep it outside OneDrive/network shares.
2. Install **64-bit Python 3.12 or newer** from https://www.python.org/downloads/windows/ including the Python Launcher. This package was tested on Python 3.12. Avoid a preview Python release.
3. Double-click `Install.bat`. It creates an isolated `.venv`, installs the pinned dependencies and asks you to set an admin password. It generates random local secrets in `.env`.
4. Double-click `Start_Demo.bat`. Leave its window running. Open **http://localhost:8766/admin** and sign in with that password.
5. Click **Start stream session**. Open **http://localhost:8766/** in another tab. Create a test tip. In Admin → Pending payments click **Simulate payment**. The public page should show confirmation.
6. Create a goal in Admin → Goals. Admin → OBS supplies the Browser Source URLs. Open one alert URL before creating the next test tip, or use **Test alert** to see a clearly labelled preview.
7. Close the demo server window when done. Its data stays in `data-demo`; it never enters live totals and never creates a real UPI QR.
8. Read [deployment](docs/DEPLOYMENT.md), [iPhone setup](docs/IPHONE.md) and [OBS setup](docs/OBS.md) before starting live mode with `Start.bat` on port **8765**.

The staged Next.js public page has its own Windows setup scripts. After `Install.bat`, run `Install_Web.bat` once, then use `Start_Web.bat` to run the page at `http://localhost:3000/`. The separate cutover setup uses `Start_Next.bat` for Flask + Next and `Setup_Tailscale_Next.bat` to move the existing Funnel from `:8765` to `:3000` only after local checks pass. `Test.bat` installs the Python test dependencies and the Chromium browser used by the browser checks. Node.js is needed for the staged frontend; PostgreSQL is not needed yet because the live Flask runtime still uses SQLite.

## What is implemented

- Mobile-first branded tipping page: presets/custom whole-rupee amount, name, optional private email, message, TTS/voice, one alert-sound picker from your sound library, exact-amount UPI link and dynamically generated QR, pending/expired/confirmed state and public top three.
- SQLite migrations, integer paise accounting, atomic matching, 10-minute default expiry, 24-hour amount reuse quarantine, permanent unique receipt references and stream-session-aware alerts.
- Private dashboard: overview; transaction search/filter/CSV; pending payments; supporter history and moderation; top 3/5/10; editable goals; tiers; TTS; sound library (viewer picks, prices, default), avatar upload; session history; charts; OBS links; settings; receipt outcomes and correction audit.
- Daily/yesterday/weekly/last-week/monthly/last-month/year/lifetime/custom and per-stream statistics in **Asia/Kolkata**. Weeks begin Monday. Financial totals retain actual paise, while support/goal/leaderboard totals use display amounts.
- Responsive horizontal/vertical alert sources, persistent ordered queues, independent layout delivery, silent vertical default, entry/exit animation, synthesized chimes or your own sound-library sounds (WAV/MP3/OGG), browser voices or speech made by AcePressure (Windows, Edge, Piper, Azure), replay/mute/skip.
- Separate authenticated Activity Dock; live updates through lightweight polling without manual refresh.
- Startup/every-six-hour consistent SQLite backups, CSV export, backup/restore and credential-rotation tools.
- Demo simulator, automated backend tests and Chromium end-to-end acceptance script.

## What cannot be preconfigured here

- Your real **bank SMS format** and exact sender were not supplied. A generic parser would be unsafe. `structured-v1` accepts fields extracted by a tested Shortcut; `example-credit-v1` is a strict illustrative parser, not a bank integration. `disabled` is the default.
- Your **UPI ID and payee name** must be confirmed locally. The old attached QR is not silently activated as the payment recipient.
- Public hosting requires your own stable HTTPS hostname/tunnel or VPS. No account has been created or deployment made on your behalf.
- iPhone automation, bank receipt timing, UPI deep-link handling, OBS audio and installed Windows voices require acceptance testing on your devices. Browser tests on Linux cannot certify these.

## Important verification boundary

An authenticated SMS bridge is evidence from your trusted phone, **not bank-signed proof**. An outsider without the bridge token cannot submit accepted receipts. However, a compromised token/phone can forge a receipt for an existing pending amount, and an unrelated transfer could coincidentally equal that amount. Exact paise matching reduces accidental matches; it cannot mathematically distinguish every family payment. Use a dedicated tip UPI/account or a bank/payment-provider integration for stronger attribution. See [security](docs/SECURITY.md).

No public “I paid” button confirms money. Unknown, missing-reference, stale, expired, duplicate or mismatching receipts never create automatic alerts. A valid payment made after expiry may need manual bank reconciliation; never ask someone to pay a second time before checking.

## Documentation

- [Detailed Windows / public deployment guide](docs/DEPLOYMENT.md)
- [iPhone Shortcuts build and bank parser integration](docs/IPHONE.md)
- [OBS and Aitum Vertical setup, TTS and audio](docs/OBS.md)
- [Migration and preserved original files](docs/MIGRATION.md)
- [Architecture, schema and API contract](docs/ARCHITECTURE.md)
- [Security and privacy boundaries](docs/SECURITY.md)
- [Backups, restore, troubleshooting and operations](docs/OPERATIONS.md)
- [PostgreSQL shadow migration and verification](docs/POSTGRES_MIGRATION.md)
- [Test report and remaining device checks](docs/TESTING.md)
- [Feature acceptance map](docs/FEATURES.md)
- [Next.js / React frontend migration](docs/NEXT_FRONTEND.md)
- [Old versus new setup](docs/OLD_VS_NEW.md)

## Source tree

```text
acepressure/
  app.py                 Flask routes, auth, validation, APIs
  domain.py              Ledger, matching, periods, goals, queues, backups
  parsers.py             Fail-closed bank adapter interface
  speech.py              Windows TTS adapter
  migrations/001_initial.sql
  templates/             Public page, dashboard, overlays
  static/                Original CSS and vanilla JavaScript
scripts/                 Windows speech, startup task, backup/restore, migration
config/                  Receipt/tunnel examples (no secrets)
tests/                   Backend tests and browser acceptance flow
docs/                    Detailed guides and acceptance screenshots
web/                     Next.js 16 / React 19 public tipping frontend (staged)
legacy/                  Private copies of the supplied original setup files
run.py                   Waitress production entry point
setup.py                 Interactive credential creation
.env.example             Configuration reference
```

The application does not send emails, move or refund money, deduct fees, connect to AdSense, or treat your YouTube Super Chats as UPI receipts. Optional supporter email is for private grouping only. Refund status is an accounting record; perform the actual refund through your bank separately.
