# Operations, backups and troubleshooting

## Each stream

1. Confirm server and tunnel are running. Open the tipping page from a phone on mobile data.
2. Check your iPhone automation is enabled and the last test succeeded.
3. Start a new stream session in Admin or Activity Dock. A second concurrent session is refused.
4. Check goals/periods and the OBS sources. Run a labelled Test alert. Test alerts never change support totals.
5. Keep Activity Dock visible privately. A verified alert should match the actual bank entry; investigate unexpected receipts.
6. End the stream session. Records stay in the database; the next session starts at zero. Daily/weekly/monthly goals may still count verified off-session tips in their windows.

## Backups

`run.py` backs up the live SQLite database at startup and every six hours using SQLite's online backup API. Backups are consistent even with WAL enabled; they are not raw copies of an in-use file. They are stored under `data/backups/` with unique timestamped names. Backups are never auto-deleted: watch disk usage and move older copies to encrypted/offsite storage. Demo has its own backups.

For an immediate backup:

- Admin → Settings → Download database backup, or
- `Backup.bat`, or
- `.venv\Scripts\python.exe scripts\manage.py backup`.

Also copy `.env` (secrets), `data/media/` (sound library audio, alert art, avatar) and the code version to a separate protected location. A database-only backup does not restore these. The speech WAV cache can be regenerated. A backup on the same disk protects against a bad edit, not drive failure or ransomware.

## Restore

1. Stop AcePressure completely (console or scheduled task) and pause the tunnel/public intake. With Tailscale Funnel (1.6.5 and later), every live start turns Funnel back on, so first add `TAILSCALE_AUTO_FUNNEL=false` to `.env`, then run `tailscale funnel reset`.
2. Keep a copy of the current directory.
3. Run:

```powershell
.\.venv\Scripts\python.exe scripts\manage.py restore --file "D:\Backups\chosen.sqlite3"
```

4. The script checks integrity and the presence of the tips table, asks you to type RESTORE, and makes a pre-restore database backup. It then replaces the database. **You must stop the server first**; the script does not forcibly terminate your processes.
5. Restore the matching `.env` and media as needed. Preserve `IDENTITY_SECRET` for supporter grouping. If you restore `.env`, add `TAILSCALE_AUTO_FUNNEL=false` to it again: the backup doesn't have it, and without it starting the server turns Funnel back on.
6. With `TAILSCALE_AUTO_FUNNEL=false` still in `.env`, start the server locally, compare totals and recent references, and only then reopen public intake (with Tailscale Funnel: remove `TAILSCALE_AUTO_FUNNEL=false` from `.env` and restart AcePressure, or run Setup_Tailscale_URL.bat). Restoring an older backup can lose later dedup references; reconcile every bank receipt after that backup before accepting replayed messages.

## Manual reconciliation

Admin → Transactions → Details / correct:

- Match the exact request, bank entry, reference and intended donor; do not rely only on a screenshot or a guessed name.
- Use MANUAL for a confirmed payment that missed the automatic window. Enter correct display and actual received amounts, bank reference and required audit reason.
- An existing reference cannot be changed or assigned to another tip. A previously unmatched receipt can be attached deliberately with the same reference.
- The correction updates totals and goals but never automatically alerts. Choose Replay only if you intentionally want it announced.
- Use REFUNDED only after actually refunding through your bank. The app retains the entry but excludes it from net support totals.

## Credentials

From the package directory:

```powershell
.\.venv\Scripts\python.exe scripts\manage.py reset-password
.\.venv\Scripts\python.exe scripts\manage.py rotate-bridge
.\.venv\Scripts\python.exe scripts\manage.py rotate-overlay
```

Restart the server after a change. Reset-password revokes existing signed sessions by rotating APP_SECRET. IDENTITY_SECRET remains stable. Update the Shortcut after bridge rotation and every OBS URL after overlay rotation. Do not share the new values in chat.

## Export

Transactions supports name/ID/reference search, status and IST date range filters. Export CSV downloads every matching row, not only the 2,000-row UI cap. Columns distinguish display/requested/actual amounts in integer paise. Divide by 100 in your analysis tool for rupees. CSV includes private emails/references; do not upload it to OBS or a public page.

The dashboard shows net support totals for VERIFIED + MANUAL. REFUNDED retains the historic received amount in the transaction list but is excluded from net totals. Starting goal offsets are not revenue.

## Common problems

| Symptom | Check / action |
|---|---|
| Installer cannot find `py` | Install the official Python Launcher with stable Python, reopen terminal, rerun Install.bat |
| Dependency installation fails | Check internet/proxy access; read pip's error; do not run an unrelated downloaded installer |
| “AcePressure is already running on port 8765 …” | Another AcePressure window or the 'AcePressure Tipping' startup task already owns the port. Close that window, or end the task in Task Scheduler, then run Start.bat again |
| “Port 8765 is already used by another program” | Close that program, or set a different `PORT` in `.env` and point your tunnel at it (for example `Setup_Tailscale_URL.bat --port 8780`) |
| Admin login repeats after HTTPS setup | Open the HTTPS hostname when COOKIE_SECURE=true; clear stale cookies if needed |
| Tip page says “Tips open soon — [your name] is finishing payment setup.” or “[your name] isn’t taking new tips right now. Please check back soon.” | Open Admin: the red line names the missing step. Admin > Settings > Payment verification lists every check, and the Start window prints the first missing one. After changing the public URL, close the AcePressure window and run Start.bat again; live defaults are deliberately closed |
| Phone cannot reach server | Use stable public HTTPS, not `localhost` (which means the phone itself); check tunnel and mobile-data access |
| Bridge 401 | Missing/wrong Bearer token; never put overlay/admin credentials there |
| Bridge 422 | Exact sender, credit direction, parser pattern or required fields failed |
| Bridge 429 “Too many requests. Please wait about N minutes.” | Rate limit; stop repeated loops and retry after the time the message gives, with the same reference/time. Wrong-token posts have their own per-address limit, so they cannot use up your phone's allowance |
| `unmatched` receipt | No unexpired matching exact amount, wrong amount or old request; reconcile against bank manually |
| Payment sent but viewer sees expired | Do not ask for another payment; inspect receipt and mark MANUAL with a reason if confirmed |
| Alert absent for a verified payment | Was the same session active when pending was created and verified? Was OBS connected within five minutes? Replay explicitly if appropriate |
| Alert in one scene but not another, or missing in OBS | Check the “Alert overlays” line on the dashboard or Activity Dock. Red “A normal browser tab is taking … alerts”: close that tab. “Two OBS sources …”: use one source per layout and add it to every scene. “No horizontal alert overlay is connected”: open OBS or check the Browser Source URL (Admin → OBS) |
| TTS silent | Check selected engine, minimum, opt-in, mute, installed voice, browser audio routing; use List_Voices.bat for Windows mode |
| Alerts play Chime instead of your default sound | Admin → Sound library shows a notice when the default's audio file is missing, the sound was removed, or your alert visual has no sound of its own. Replace its audio or choose another default |
| No sound picker on the tip page | Admin → Sound library: turn on “Viewers can pick a sound on the tip page” and tick “Viewers can pick” on at least one sound that has audio |
| A long sound stops after about 21 seconds in OBS | That source still runs the old overlay script: right-click it → Properties → Refresh cache of current page, once |
| Edge or Piper voice silent in OBS after upgrading; Admin → TTS says OBS is probably still running the old overlay page | Right-click the alert source → Properties → Refresh cache of current page (or restart OBS), then send a test alert |
| A sound or the voice is too loud or too quiet in OBS | Admin → Sound library: the slider next to ▶ Preview (10–100 %). Admin → TTS → Voice volume, then Save settings. 100 % is the file as uploaded; for more, raise the source in OBS’s Audio Mixer |
| Volume sliders change nothing in OBS | That source still runs the 1.6.1 overlay page: right-click it → Properties → Refresh cache of current page, once |
| An alert shows “[link]” | Admin → TTS → “Hide links in messages and names” is on (the default). Turn it off to show viewers’ links. The dashboard always shows what was typed |
| The voice stops partway through a long message | “Read whole messages” is off: a chip at the top of the dashboard says so. Press **Read whole messages** (Live activity or the chip), or raise “read up to” in Admin → TTS |
| Viewers can't type a long message | Admin → TTS → **Longest message viewers can type** (up to 500), then Save settings |
| The voice skips a word or an emoji | Admin → TTS: check Pronunciations (an empty “Say it as” skips that word) and “Don’t read emoji aloud”. “The voice reads” under Try English or Hinglish shows what will be spoken |
| A Hindi voice reads a Roman word in English, or an English word in Hindi | Type the sentence in Try English or Hinglish and read “The voice reads”. With a Hindi voice, a pronunciation can force a word (kya → क्या); English voices can’t read Devanagari |
| Queue repeats after a crash | At-least-once delivery after lease expiry is possible; ledger amounts are not duplicated |
| Goal looks wrong | Check selected goal ID, display-vs-actual amounts, starting offset, period, carry dates and India timezone |
| Paise allocation busy | 99 slots for this rupee amount are quarantined for 24 hours; choose another rupee amount; investigate abuse before changing the hold |
| Dashboard totals are stale | Check connection indicator and refresh; inspect `/health`; do not overwrite the DB to “reset” |
| Backup failure logged | Check disk space, permissions and data directory; copy a backup off-machine after resolving |

## Upgrades

Back up DB, `.env`, media and source first. Stop the server; replace only application code/dependency files; preserve data and `.env`; install the new locked dependencies; run tests; start locally and check version/migration notes. Do not delete the old source until rollback is tested. Never unzip a future package blindly over user data.

Upgrading to 1.6.0: on first start AcePressure saves `data/backups/before-1.6.0-sound-library.sqlite3`, then moves your sounds into Admin → Sound library once (no media file is renamed or deleted). Keep that backup until you have checked your sounds. If you never uploaded a sound, used the soundboard or changed a sound setting, there is nothing to move and no backup is made. If the move can't finish, AcePressure still starts with your old sound settings, shows a message in its window and tries again on the next start.

Upgrading to 1.6.7: no database change. Design studio uploads remember the name they were uploaded with, in one new setting that 1.6.6 ignores, so 1.6.6 still runs on the same data.

Upgrading to 1.6.6 (from 1.6.4 or a 1.6.5 test build): no database change. Each live start turns Tailscale Funnel on when it is off (`TAILSCALE_AUTO_FUNNEL=false` in `.env` stops this). Names on stream are always filtered as whole words. 1.6.4 still runs on the same data.

Upgrading to 1.6.4: no database change. The new settings are added on start (sessions start when OBS goes live; whole-word filtering stays off on an upgraded database until you tick it). `run.py` changed, and each OBS alert source needs one refresh. 1.6.3 still runs on the same data.

Upgrading to 1.6.3: no database change. The two “Read whole messages” settings are added on start, switched to read whole messages, and 1.6.2 still runs on the same data.

Upgrading to 1.6.2: on first start, migration 009 adds a volume column to your sounds (all start at 100 %). Nothing else changes in your data, and 1.6.1 still runs on it if you need to go back.
