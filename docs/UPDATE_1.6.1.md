# Update to AcePressure 1.6.1

This is a focused update of the supplied 1.6.0 release. No database migration or payment-policy change is introduced.

## What changed
- TTS sample text and preview voice survive dashboard redraws / Save settings in the same browser tab. Reloading the page resets the preview draft intentionally. Preview text is not a stored donation and is not translated when saved.
- Both server and browser language helpers stop counting English gaming words as evidence of Hindi. Ambiguous words such as main, mat and mere stay unchanged, even in mixed messages. This is conservative dictionary conversion, not a full language translator.
- Piper uses the current synthesize_wav API; its installer pins piper-tts 1.8.0. Invalid or empty newly generated WAV output is rejected. Loaded voices are keyed by full model path so demo/live installations cannot mix models with the same name.
- Piper audio cache version advances; old generated clips are not reused.
- Edge imports its optional provider only when synthesis is actually needed; validation and a valid cached clip do not need that import.
- Piper downloader accepts --data-dir for demo/custom data folders.

## Install safely
1. Pause new tip requests and finish outstanding reviews. Stop AcePressure.
2. Back up the entire existing installation folder, including .env, data, data-demo and any custom media.
3. Extract this ZIP into a separate folder. From its AcePressure folder, copy acepressure, scripts, docs, tests, VERSION, README.md, Install_Piper.bat and both PACKAGE_MANIFEST files into your existing installation, replacing those code files.
4. Preserve .env, .venv, data and data-demo. Do not replace them or run a fresh setup over them.
5. If you use Piper, run Install_Piper.bat once to install the pinned provider. It skips existing starter model files. If you use Edge, no Piper installation is necessary.
6. Restart the same launcher you used before: Start.bat for live or Start_Demo.bat for demo. Keep your existing tunnel setup.
7. Refresh the dashboard. In OBS, refresh the alert Browser Source cache so updated JavaScript loads.

For Piper demo voices, run from the installation folder:
    .venv\Scripts\python.exe scripts\download_piper_voices.py --data-dir data-demo
For a custom data folder, substitute its path. The default installer downloads to data/piper-voices.

## Test without another payment
- Admin → TTS: choose an installed Hindi or multilingual voice from the catalog; use Listen to sample.
- Try: bhai kya khel raha hai
- Try: भाई क्या खेल रहा है
- Try: I play the main role. Put the mouse on the mat.
- Enter your own sample, click Save settings, and confirm it remains unchanged. No Save is needed merely to listen.
- Send a test alert with OBS open. Use the horizontal source for sound; vertical was intentionally muted in your setup.
- Test preview audio and OBS separately. Actual voice quality depends on provider, voice and spelling.
- These tests require no real money and must not increase financial totals.

## Limits
This update does not guarantee natural pronunciation of arbitrary Hinglish. It protects common English words from incorrect replacement and preserves the viewer's original stored message. Edge needs internet and sends spoken text to its provider. Piper is local after installing its models. Azure requires its configured account/key and can incur charges.

Payment notifications are still an imperfect bridge, not bank-signed payment receipts. Existing manual review and matching safeguards remain essential.
