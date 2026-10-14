# Validation — 1.6.3
12 October 2026, macOS build machine (Python 3.9 test environment, headless Chrome). Based on the 1.6.2 release.

- Full pytest suite: **800 passed** (784 in 1.6.2). New: `tests/test_release_163.py`, 16 tests covering where the cut falls (whole words, a word ending exactly at the limit, punctuation left at the end, Hindi, one long word), whole messages by default and after upgrading a 1.6.2 database, the alert card and spoken copy with the switch off (including the Hindi copy), emoji and repeats that use up no characters, server voices reading the same start, the setting checks, “The voice reads” and **Listen to sample**, the tip page's settings, and the page controls.
- Real Chrome against a local AcePressure (demo mode, throwaway data, no money moved), 40 checks:
  - Admin → TTS: the switch and “read up to” (default 100, limits 20–500), Chrome refusing 10 before anything is sent, saved and still there after a reload, the server refusing 600 with a readable message, and “The voice reads” with and without “Cut short”.
  - Overview and the OBS Activity dock (`/obs/activity`): the chip, the Live activity button in both directions and the chip's own button. No overlapping buttons at 1440 and 390 px, and no sideways scroll.
  - Tip page at 1440 and 390 px: the note on its own line, without clipping, only while the switch is off. Viewers can still type the full length.
  - OBS overlay: the card shows the whole message, and the voice reads only the start (the Hindi copy, as “The voice reads” shows for a Hindi voice). Switched back on, it reads everything.
  - The browser's speech was replaced by a recorder, so nothing was spoken. Zero JavaScript exceptions.
- The 1.6.2 browser check (53 checks) and the tip-page sound picker check (27 checks) still pass.
- Rollback: 1.6.3, then 1.6.2, then 1.6.3 again on one data folder.
- Release ZIP: extracted into an empty folder, then checked: manifest and file hashes, no `.env` or data, launchers in ASCII with CRLF line endings, the full suite on the extracted copy, and a fresh install from the ZIP.
- No real payments, no production database, and no Windows, OBS or iPhone testing from here.

Still needs your PC: switch it off, type a long sample in Admin → TTS and press **Listen to sample** to hear where the voice stops. (Corrected in 1.6.4: the test alert's 40-character message is too short to be cut, so a test alert can't show it in 1.6.3.)
