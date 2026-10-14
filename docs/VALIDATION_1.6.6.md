# Validation — 1.6.6
13 October 2026, macOS build machine (the app and tests on Python 3.14, the check scripts on Python 3.9, headless Chrome). Based on the 1.6.4 release and the 1.6.5 test builds.

- Full pytest suite: **954 passed** (870 in 1.6.4). New: `tests/test_release_165.py`, 84 tests:
  - Funnel off is turned on with `tailscale funnel --bg 8765`. A Funnel that's on and one that sends visitors to another port are left alone. So is another program shared at the tip link's address with `tailscale serve`, and the window names that share.
  - An open `tailscale funnel` window: Funnel is left on, the window says so once, and AcePressure takes over within 15 seconds once that window closes. If Tailscale refuses because the window is open, the window says to close it.
  - The first-time approval link reaches the window, the 25-second wait is cut short, and a refusal shows what Tailscale said (its “Warning:” lines are skipped).
  - It tries again every 15 seconds while Tailscale is starting, signed out, disconnected, offline or not answering, or can't say whether Funnel is on. While Tailscale isn't answering, the dashboard and the window say so. It turns Funnel on once Tailscale is ready, then never again until the next start. A warning that comes after the “isn't answering” line (sign-in expiry, a tip link for another PC) is still written to the window, and “reachable” is written as information, not as a warning.
  - Live mode only, `TAILSCALE_AUTO_FUNNEL=false`, other tip links, a tip link for another PC, and no Tailscale installed.
  - Names on stream always match whole words, where `_`, a digit or a capital starting a new part starts a new word (noob_master, Noob69, BigNoob, BIGNoob, SHITLord), while “Kshitij”, “Harshit”, “Shital”, “BIGSHIT” and “BULLSHIT” stay whole. This also holds on a database upgraded from 1.6.3, while messages follow **Filter whole words only**. Also the admin labels, and Install_Piper.bat's text, characters and line endings.
- The real `run.py` in live mode with a stand-in `tailscale` program (no real Tailscale), 31 checks, passed on the source folder and on the extracted ZIP:
  - Funnel off: turned on once, for AcePressure's port. The window and the server log say so, and the server answers meanwhile.
  - Funnel already on, Funnel on another port, demo mode, `TAILSCALE_AUTO_FUNNEL=false` in `.env`, and a tip link for another PC: nothing is started.
  - The approval link shows after the 25-second wait, and the waiting command is stopped. A refusal shows what Tailscale said. Without Tailscale, the window says where to get it.
  - Signed out at start, or Tailscale not answering: the window says so once, then Funnel is turned on within 15 seconds once Tailscale is ready, and “reachable” is written as information.
  - Not answering at start, then answering with the sign-in expiring in 5 days: the expiry warning still reaches the window. Both new checks fail on the second 1.6.5 test build.
  - An open `tailscale funnel` window: the window says so once and nothing is started while it stays open. After it closes, Funnel is turned on in the background within 15 seconds.
  - Another share at the tip link's address: Funnel stays off, and the window names that share, with no contradicting line after it.
  - Every “Tip link” line is plain ASCII, so the Windows console shows it whatever its code page.
- The 1.6.4 browser check in real Chrome (80 checks) passed on the source folder and on the extracted ZIP.
- Straight upgrades to 1.6.6 from the 1.6.0, 1.6.1, 1.6.2, 1.6.3 and 1.6.4 ZIPs and from both 1.6.5 test builds, with the files copied over as UPDATE_1.6.6.md says (10 checks each):
  - settings, tips, sounds and the running session are kept;
  - “Kshitij” stays whole on stream, while messages keep the old-style filter;
  - alerts play and the pages load.
- Rollback, 11 checks: 1.6.6, then 1.6.4, then 1.6.6 again on one installation and data folder.
- Release ZIP: extracted into an empty folder and checked for:
  - the manifest and file hashes;
  - no `.env` or data;
  - launchers in ASCII with CRLF line endings;
  - on the extracted copy: the full suite, the live-mode check (31), the browser check (80), the straight upgrades and the rollback;
  - a fresh install from the ZIP (41 checks).
- Not tested here: real Tailscale, Windows, OBS, real payments and the production database.

Still needs your PC:
- Run Start.bat and read the “Tip link:” line in the AcePressure window.
- Open your tip page on your phone with Wi-Fi off.
