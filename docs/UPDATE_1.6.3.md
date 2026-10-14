# Update to AcePressure 1.6.3

Installs over 1.6.0, 1.6.1 or 1.6.2. Your data, `.env`, sounds and OBS sources are kept. There is no database change.

## What's new
- **Read whole messages**, or only the start of long ones. Use the button in **Live activity**, next to **Mute TTS**. It is also in the Activity dock inside OBS.
- When it's off, the voice reads the first 100 characters and stops after a whole word. The alert card still shows the whole message.
- Change the 100 in **Admin → TTS → When “Read whole messages” is off, read up to this many characters** (20–500).
- **Maximum message characters** is now called **Longest message viewers can type (up to 500)**.
- If you are coming from 1.6.1 or 1.6.0, also read UPDATE_1.6.2.md: volume controls, hidden links, pronunciations and smarter Hinglish.

Details: CHANGELOG.md.

## Install safely
1. Finish outstanding payment reviews, then close the AcePressure window.
2. Back up the whole installation folder, including `.env`, `data`, `data-demo` and your own media.
3. Extract this ZIP into a new, empty folder. From its AcePressure folder, copy `acepressure`, `scripts`, `docs`, `tests`, `VERSION`, `README.md`, `Install_Piper.bat` and both `PACKAGE_MANIFEST` files into your existing installation, replacing those files.
4. Keep `.env`, `.venv`, `data` and `data-demo`. Don't replace them or run a fresh setup over them.
5. Start AcePressure with the same launcher as before: `Start.bat` for live or `Start_Demo.bat` for demo. Keep your tunnel as it is.
6. Reload the dashboard. OBS needs no refresh when you come from 1.6.2. From 1.6.1 or 1.6.0, right-click the alert Browser Source → Properties → **Refresh cache of current page**, once.

## Try it without spending money
- **Admin → TTS**: in **Try English or Hinglish**, type a long sample such as `Bhai kya clutch tha, aaj ka stream bahut mast tha. Main tumhara bahut bada fan hoon, keep it up!`. “The voice reads” shows all of it.
- Go to **Overview** and press **Shorten long messages**. A chip at the top says the voice reads only the first 100 characters.
- Back in **Admin → TTS**, type the sample again. “The voice reads” now stops after about 100 characters and says “Cut short”. Press **Listen to sample**.
- **Test alert** can't show the cut in 1.6.3: its message is only 40 characters, so it's always read in full. Use **Listen to sample** as above. (1.6.4 makes the test alert long enough.)
- Press **Read whole messages** to switch back.
- None of these move real money or change your totals.

## If you need to go back
Close AcePressure, copy the code folders from your backup (or from the 1.6.2 ZIP, the same way as step 3), then start it again. 1.6.2 runs on the data 1.6.3 used and ignores the new settings, so it reads whole messages. Tested both ways.

## Limits
- The voice cuts the message after a whole word, not at the end of a sentence, so it can stop mid-sentence. Raise the number if it cuts too much.
- **Skip TTS** in Live activity still stops a message that is being read.
- The voice still needs a listening test on your PC.
