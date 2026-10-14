# Validation — 1.6.2
12 October 2026, macOS build machine (Python 3.9 test environment, headless Chrome). Based on the 1.6.1 release.

- Full pytest suite: **784 passed** (702 in 1.6.1). New: `tests/test_release_162.py`, 82 tests covering hidden links (what is and isn't a link, cards, boards and the tip page), the spoken copy (emoji, repeats, numbers kept), pronunciations (matching, limits, duplicates, settings), the copy every engine reads, emoji-only messages, “The voice reads”, the volume migration on an existing library, volume checks and payloads, fields a 1.6.1 overlay reads, a speech failure that must not stop an alert, a 26-sentence Hinglish corpus plus English sentences that must stay English, and Piper 1.2.
- Real Chrome against a local AcePressure (demo mode, throwaway data, no money moved), 53 checks:
  - Admin → TTS: voice volume changed with the keyboard, saved and still there after a reload; both new switches; pronunciations added, a duplicate refused, saved and still there after a reload; “The voice reads” with a pronunciation, a hidden link, skipped emoji, a Hindi voice and an emoji-only sample.
  - Admin → Sound library: 14 quick arrow-key steps save the final volume; **▶ Preview** plays at the row volume; still set after a reload; nothing overlaps at 1440 px; the slider fits on screen at 390 px.
  - Tip page at 1440 and 390 px: sound, default-sound and voice previews play at the set volumes; a Hindi voice sample is read in Devanagari.
  - OBS overlay: the picked sound at its volume; a server voice at the voice volume; the browser voice reading the server's Hindi copy at the voice volume; English kept with an English voice; an older server's payload (full volume, the overlay's own Hinglish lists); the 1.6.1 overlay files served by this server (alert shown with the link hidden, sound and voice played, alert finished).
  - The browser's speech was replaced by a recorder, so nothing was spoken. Server voices were answered with a silent WAV. Zero JavaScript exceptions.
- Tip-page sound picker with real mouse and touch input: 27 checks.
- Rollback: 1.6.2, then 1.6.1, then 1.6.2 again on one data folder, 12 checks.
- Release ZIP: extracted into an empty folder, then checked: manifest and file hashes, no `.env` or data, launchers in ASCII with CRLF line endings, the full suite on the extracted copy, and a fresh install from the ZIP (41 checks).
- No real payments, no production database, and no Windows, OBS or iPhone testing from here. Edge, Piper and Azure audio were mocked, not generated.

Still needs your PC: a listening test of Hinglish with the voices you use, the volume levels in your real OBS source, and Piper on the version you have installed.
