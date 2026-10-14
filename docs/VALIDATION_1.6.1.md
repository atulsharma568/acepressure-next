# Validation — 1.6.1
12 October 2026, Linux build environment. Based on supplied 1.6.0 source.

- Full pytest suite: **702 passed in 112.31 seconds**.
- Ten new regressions cover English/Hindi separation, mixed gaming text, Devanagari preservation, Piper WAV contract, empty-output rejection and model-path cache isolation.
- Actual headless Chromium against a temporary local AcePressure server: admin login, TTS sample editing, Save settings, navigation away/back, and browser English/Hinglish helper behavior passed. Script: tests/browser_tts_161.py.
- JavaScript syntax check passed for modified designer.js.
- Installed piper-tts 1.8.0 and checked its actual synthesize_wav method. Backend integration using that installed writer with synthetic audio chunks passed (22,050 Hz, 2,205 frames). No real ONNX voice inference or acoustic quality evaluation was performed.
- No real payments sent, no production database opened, no Windows/OBS/iPhone remotely tested during this release.
- Final ZIP manifest and CRC checked after packaging.

The first intermediate run stopped on stale changelog/README/manifest metadata, which was updated before the complete passing run. The original 1.6.0 had three optional-Edge-import test failures; all now pass without installing Edge.

Provider API references:
- https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md
- https://pypi.org/project/piper-tts/1.8.0/

Pronunciation still requires the creator's own listening check. Unit tests and synthetic audio prove code behavior, not natural Hinglish speech.
