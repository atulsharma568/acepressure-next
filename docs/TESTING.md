## Version 1.6.7 validation

987 automated tests pass (954 in 1.6.6). `test_release_167.py` (33 tests) checks the server side of several files at once and Design studio files keeping the names they were uploaded with. It also pins the batch code in Sound library and Design studio: a failing file listed while the rest go up, and a batch stopping on a sign-out or lost connection. The real-Chrome check below runs the batches.

Also checked:
- several files at once in real Chrome, on a desktop and a phone screen (65 checks);
- the 1.6.4 browser check (80) and the 1.6.6 live-mode check with a stand-in Tailscale (31);
- straight upgrades from 1.6.0 to 1.6.4, both 1.6.5 test builds and 1.6.6;
- a 1.6.7 → 1.6.6 → 1.6.7 rollback, and back to 1.6.4;
- a fresh install from the ZIP (41).

Details and limits: VALIDATION_1.6.7.md.

Still required on your Windows PC:
- Add two or three sounds at once in Sound library.

## Version 1.6.6 validation

954 automated tests pass (870 in 1.6.4). `test_release_165.py` (84 tests) covers Start.bat turning Tailscale Funnel on, and when it leaves Funnel alone:
- Funnel on, or sending visitors elsewhere;
- an open `tailscale funnel` window, or another share at the tip link's address;
- the approval link and refusals;
- Tailscale not ready or not answering;
- the switch in `.env`, and demo mode.

It also covers names on stream matching whole words.

Also checked:
- the real `run.py` in live mode with a stand-in Tailscale (31 checks);
- the 1.6.4 browser check (80);
- straight upgrades from 1.6.0 to 1.6.4 and from both 1.6.5 test builds (10 checks each);
- a 1.6.6 → 1.6.4 → 1.6.6 rollback (11);
- a fresh install from the ZIP (41).

Details and limits: VALIDATION_1.6.6.md.

Still required on your Windows PC:
- Run Start.bat and read the “Tip link:” line.
- Open your tip page on your phone with Wi-Fi off.

## Version 1.6.4 validation

870 automated tests pass (800 in 1.6.3). `test_release_164.py` (70 tests) covers each change:
- OBS going live;
- line breaks and hearts;
- the cut and the long test alert;
- the tip page while a payment waits;
- reading in full from ₹X and **Replay in full**;
- **Skip alert** and the queue;
- the Paytm preview;
- the backup voice and the voice warning;
- the Tailscale check;
- the stronger filter.

Also checked:
- in real Chrome, 80 checks for the new screens and the OBS alert page, with stand-ins for OBS's page API and for Tailscale;
- in real Chrome, 8 checks for an alert page still running 1.6.3;
- the 1.6.3 and 1.6.2 browser checks;
- a 1.6.4 → 1.6.3 → 1.6.4 rollback (17 checks);
- straight upgrades to 1.6.4 from 1.6.0, 1.6.1 and 1.6.2 (9 checks each).

Details and limits: VALIDATION_1.6.4.md.

Still required on your Windows PC:
- Go live in OBS once and watch the session start.
- Press **Skip alert** on a real alert.
- Listen to the backup voice if you choose one.
- Check that no tip-link warning shows while your tip page works.

## Version 1.6.3 validation

800 automated tests pass (784 in 1.6.2). `test_release_163.py` (16 tests) covers where the cut falls (whole words, punctuation, Hindi, one long word), whole messages by default and after upgrading a 1.6.2 database, the alert card and spoken copy with the switch off, emoji and repeats that use up no characters, server voices reading the same start, the setting checks, “The voice reads” and **Listen to sample**, and the tip page note. Checked in real Chrome: 40 checks for the switch (Admin → TTS, Live activity, the OBS dock, the tip page at 1440 and 390 px, the OBS overlay), plus the 53 checks from 1.6.2.

Still required on your Windows PC: switch it off, type a long sample in Admin → TTS and press **Listen to sample**. (Corrected in 1.6.4: the 1.6.3 test alert's message is too short to be cut.)

## Version 1.6.2 validation

784 automated tests pass (702 in 1.6.1). `test_release_162.py` (82 tests) covers hidden links, the spoken copy (emoji, repeats, numbers), pronunciations, the copy every engine reads, “The voice reads”, the volume migration, volume checks and payloads, the fields a 1.6.1 overlay reads, a 26-sentence Hinglish corpus with English sentences that must stay English, and Piper 1.2. Checked in real Chrome (53 checks), with the tip-page picker (27), a 1.6.2 → 1.6.1 → 1.6.2 rollback (12) and a fresh install from the ZIP (41). Details and limits: VALIDATION_1.6.2.md.

Still required on your Windows PC: a listening test of Hinglish with your voices, and the volume levels in the real OBS source.

## Version 1.6.0 validation

692 automated tests pass (503 in 1.5.9). The new test files cover:

- `test_sound_library.py`: the one-time move of 1.5.9 sounds into the library (backup first, runs once, media files never touched, retried after a failure), the default sound, tip picks and the picks switch, which sound each alert and overlay claim plays, file clean-up after deletes, uploads and the 30-second cap, dashboards and tip pages left open across the upgrade, and the 8 starter sounds (first seed, repeat clicks, a 1.5.9 board, a missing bundled file, deleting a copy), plus static checks of the new tip-page and overlay code.
- `test_readiness.py`: the go-live checklist in live, paused and demo mode, the restart check, no secrets in the checklist, and the plain-ASCII Start window summary.
- `test_attention.py`: the review count, each tip's alert status, `alert_queued` for the thank-you text, stream sessions on the Paytm page, plain-language review reasons and the 008 index migration.
- `test_supporter_moderation.py`: muting keeps a block, and unblocking keeps a mute.
- `test_overlay_clients.py`: OBS-first claiming, standby browser tabs, `&claim=always`, connected overlays on the dashboard and in the test-alert reply, and the local OBS links.
- `test_overlay_server_tts.py`: Edge and Piper audio served to the overlay, provider errors reaching Voice Studio, and versioned overlay and dashboard scripts.
- `test_rate_limits.py`: per-visitor limits through Waitress's real proxy-header handling, the forget-browser and sign-in limits, junk posts that can't block either phone bridge, and forwarded host/proto headers that are still ignored.
- `test_startup_guard.py`: a running AcePressure, or another program on the port, stops `run.py` before the app is created.
- `test_tailscale_setup.py`: the canonical Tailscale address, Funnel confirmed before `.env` is written, and Paytm-first next steps.
- `test_review_fixes_overlay.py`: fixes from the pre-release review. The pre-1.6.0 backup is written whole or not at all (a crash mid-copy, a stale partial file, a rename retried while Windows holds the file, an existing backup never replaced). Skip TTS during the alert sound cancels that readout, but a Skip pressed before the alert was claimed doesn't. A sound file gets 10 s to start and 31 s once playing. Chime gives up after 1 s when audio is blocked. Voice Studio explains `voice_missing` from an OBS source still on the old overlay page. Fix_Audio.bat names the Sound library, and the browser smoke test waits for the paid state.
- `test_review_fixes_ui.py`: the tip page keeps a pick while the amount changes. Pay (or Enter) refuses a pick the tip doesn't cover, where the viewer can see it, and the message clears once the cause is gone. The page also covers the locked-tile nudge, keyboard focus after picking, the live region, category `aria-selected` and double-tap previews. In the admin: one upload per click, toasts that say when viewer picks are off, long names wrapping on phones, and the server's price backstop.

Checked in Chrome during development, with disposable data and no money moved: Edge audio reaching the overlay and Voice Studio's messages, the readiness strip and tip-page notices at phone width, `/admin/paytm` refreshing itself without losing a half-typed reason, OBS-first claiming with an OBS page next to a normal tab, and the sound picker with real mouse and touch input at 1440 and 390 px (typing 1 → 15 → 150 keeps a ₹100 pick; Pay or Enter at ₹50 sends nothing and shows the reason on screen).

Still required on your Windows PC: Edge and Piper speaking through the real OBS source; a meme played with **▶ Test on stream**; a second Start.bat (or the startup task) being refused; Setup_Tailscale_URL.bat showing Tailscale's approval link and changing `.env` only after Funnel is confirmed; and two phones on different networks getting separate tip limits through Funnel.

## Version 1.1.1 validation

85 backend tests pass, including expired-only notification rejection and replay after manual approval. Chromium validates reduced polling frequency, hidden-tab pause, QR removal at expiry, stopping automatic requests and manual retrieval of late approval. No real payments were sent by automated tests. Windows and iPhone live operation still require device validation.

## Version 1.1.0 validation

83 automated backend tests pass, including persistent token restart/rotation, concurrent duplicate submissions, immediate/expired review, recipient mismatch, CSRF and live configuration gates. Chromium acceptance verifies token generation, immediate review/approval, real checkout QR rendering, UPI link, copy controls and mobile width with no JavaScript errors. Tests use disposable databases and fictitious recipients; no money is sent. Windows service installation, actual iPhone deep-link behavior and live OBS/device delivery still require the owner’s device checks described in UPGRADE_1_1.md.

# Paytm matching update — 10 October 2026

75 backend/packaging tests passed on Linux/Python 3.12. Chromium acceptance passed login, capture start/stop, authenticated ingest, live results, masked token, optional demo matching, matching TEST overlay and mobile width with zero JS errors. Tests include concurrent duplicate calls, persistent fingerprints after reopening the database, expiry, ambiguous amounts, inactive sessions, blocked supporters, timestamp ambiguity and changed retry dates. Actual Windows/iPhone full matching still requires user device acceptance.

# Paytm capture update — 10 October 2026

59 backend/packaging tests passed on Linux/Python 3.12. New diagnostic UI passed Chromium checks for login, token start/stop, authenticated ingestion, auto-refresh, masked token, 390px mobile layout and zero JavaScript errors. Tests prove capture does not verify an exact matching pending tip or create alerts. Windows/iPhone HTTPS and locked-device POST still require device acceptance.

# Test report — 9 October 2026

## Completed in the build environment

**44 automated backend/packaging tests passed.** Python 3.12, SQLite and the pinned dependency versions in requirements-lock.txt, running on Linux.

Coverage includes:

- Pending tips never contribute to totals or alerts.
- Exact received/display amount separation and active-session alert creation.
- Ordinary round-number family transfers remain unmatched.
- Idempotent and concurrent repeated references; concurrent unique amount allocation.
- Expired payments, amount quarantine, suffix exhaustion, missing references and stale/future receipt timestamps.
- Off-session and previous-session verification without automatic live alerts.
- Bridge auth, sender, direction, raw format rejection, disabled production gate and disabled live simulator.
- Admin login/CSRF/origin checks, private-field isolation, public rate limits and safe text rendering.
- Supporter grouping and blocks, labelled tests without revenue, channel claim ownership/ack.
- Refund cancellation/exclusion, audited manual corrections and manual-reference dedup.
- Goal CRUD, campaign dates, automatic period rollover without deletion, India-time boundaries and custom analytics.
- CSV formula neutralization, live-only QR generation, database backup integrity.
- Migration writes a separate collection/backup, leaves the original untouched and preserves unrelated sources.
- All 12 attached originals match their stored SHA-256 manifests.

Machine-readable test output: `backend-test-results.xml`.

**12 Chromium acceptance checks passed with zero JavaScript page errors.**

1. Admin login and session start.
2. Viewer checkout enters pending with no real payment QR in demo.
3. Authenticated simulation changes the viewer page to confirmed.
4. Horizontal verified alert displays the correct supporter.
5. Vertical verified alert displays independently.
6. A goal can be created through the dashboard.
7. Goal overlay shows the verified contribution.
8. All 14 dashboard sections render.
9. Private supporter history displays the message.
10. Authenticated OBS Activity Dock displays activity.
11. 390px mobile layout has no horizontal overflow.
12. Hostile submitted text remains inert.

Results: `browser-test-results.json`. Desktop, mobile, dashboard and both alert screenshots are in `screenshots/`. These are **synthetic QA data**, not actual donations.

**Production-entry smoke test passed:** launched the actual `run.py` Waitress entry point, fetched `/health`, confirmed demo status, and checked the automatic startup SQLite backup with `PRAGMA integrity_check`.

## Tests corrected during development

The final review hardened a few concrete edge cases before release:

- Admin password rotation now preserves a separate stable supporter identity secret.
- Explicit campaign start/end bounds now constrain goal progress.
- Manual reconciliation can attach a bank reference and refuses reference reuse.
- Alert claim leases cover bounded Windows speech rendering/playback time.
- Global TTS mute/skip does not intentionally mute a custom alert sound.
- Invalid field types fail with a 400 response instead of an opaque server error.
- Mobile top supporters remain accessible below the tipping form.

## Not executed here — required on your devices

The build environment (Linux for older versions, a Mac since 1.6.2) is not your Windows PC, iPhone or OBS. Therefore these are **not certified by the passing tests**:

- Running Install/Start/Task Scheduler scripts on your Windows account, Python setup, Windows permissions and firewall/tunnel behavior.
- Rendering and routing actual Windows SAPI/browser speech through your OBS and Aitum audio tracks.
- iPhone Message trigger sender/body access, locked-phone execution and network permissions.
- Your bank's actual SMS extraction, delayed SMS handling and unique reference format.
- UPI deep-link behavior in your viewers' installed payment apps, actual recipient identity and a real bank transfer.
- Live HTTPS tunnel availability and public traffic/abuse load.

Do not enable live payment intake until the documented iPhone/OBS/low-value payment checks pass. A passing demo proves application wiring, not a bank integration.

## Reproduce

From the package directory:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe tests\browser_smoke.py
```

Browser acceptance uses port 8767 and a disposable directory. Stop anything else on that port before running. It updates synthetic screenshots/test output, never the live database. The real app demo runs separately on 8766. Tests do not send money, contact a bank or modify installed OBS profiles.
