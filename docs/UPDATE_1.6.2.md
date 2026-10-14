# Update to AcePressure 1.6.2

Installs over 1.6.0 or 1.6.1. Your data, `.env`, sounds and OBS sources are kept. One small database change, a volume column for sounds, runs by itself on first start.

## What's new
- A volume slider for every sound (Admin → Sound library) and **Voice volume** for the voice (Admin → TTS).
- Links in messages and names show as “[link]” on stream and are never read aloud. Your dashboard keeps what was typed.
- The voice skips emoji and shortens long repeats (hahahahaha → hahaha). The card still shows the emoji.
- **Pronunciations**: teach the voice words, for example AcePressure → Ace Pressure.
- “The voice reads” shows what the voice will say for your sample before you listen.
- Smarter Hinglish: “main aa gaya bhai, tension mat lo” → “मैं आ गया भाई, tension मत लो”, while “I play the main role” stays English.
- Piper works with piper-tts 1.2 as well as 1.8.

Details: CHANGELOG.md.

## Install safely
1. Finish outstanding payment reviews, then close the AcePressure window.
2. Back up the whole installation folder, including `.env`, `data`, `data-demo` and your own media.
3. Extract this ZIP into a new, empty folder. From its AcePressure folder, copy `acepressure`, `scripts`, `docs`, `tests`, `VERSION`, `README.md`, `Install_Piper.bat` and both `PACKAGE_MANIFEST` files into your existing installation, replacing those files.
4. Keep `.env`, `.venv`, `data` and `data-demo`. Don't replace them or run a fresh setup over them.
5. Start AcePressure with the same launcher as before: `Start.bat` for live or `Start_Demo.bat` for demo. Keep your tunnel as it is.
6. Reload the dashboard. In OBS, right-click the alert Browser Source → Properties → **Refresh cache of current page**, once, so the overlay gets the volumes.

## Try it without spending money
- **Admin → Sound library**: move a sound's volume slider and press **▶ Preview**. With OBS open, press **▶ Test on stream** on that sound: OBS should play it at that volume.
- **Admin → TTS → Voice volume**: set 50 %, press **Save settings**, then **Listen to sample**.
- **Admin → TTS → Pronunciations**: add AcePressure → Ace Pressure and press **Save pronunciations**. In **Try English or Hinglish** type `GG AcePressure 😂😂😂 www.test.com`. “The voice reads” should show `GG Ace Pressure [link]`. Press **Listen to sample**.
- With your Hindi voice, try `main aa gaya bhai, tension mat lo` and `aaj ka din mast tha`. Then try `I play the main role. Put the mouse on the mat.`, which should stay English.
- **Alertbox → Test alert** with OBS open. Listen on the horizontal source, because your vertical source is muted on purpose.
- None of these move real money or change your totals.

## If you need to go back
Close AcePressure, copy the code folders from your backup (or from the 1.6.1 ZIP, the same way as step 3), then start it again. 1.6.1 runs on the data 1.6.2 used: it ignores the volume column and the new settings. Tested both ways.

## Limits
- The voice still needs a listening test on your PC. Pronunciation depends on the engine, the voice and the spelling. Hinglish conversion is a dictionary with sentence rules, not a translator.
- Links are recognised by their pattern. Spelled-out addresses (“scam dot com”) or addresses with spaces inside are not hidden. Your filtered-words list still applies.
- Edge needs internet and sends the spoken text to Microsoft. Piper runs on your PC once installed. Azure needs your own account and key, and may cost money.
- Payment notifications are still an imperfect bridge, not bank-signed receipts. Keep using manual review.
