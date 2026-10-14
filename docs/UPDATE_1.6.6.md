# Update to AcePressure 1.6.6

Installs over 1.6.0 to 1.6.4, and over a 1.6.5 test build. Your data, `.env`, sounds and OBS sources are kept. There is no database change.

## What's new
- **Start.bat turns your tip link on.** When AcePressure starts in live mode and Tailscale Funnel is off, it runs `tailscale funnel --bg 8765` for you and says so in its window. If Tailscale is still starting or signed out, it tries again every 15 seconds.
- **No more `tailscale funnel` window.** If you keep a window open with `tailscale funnel 8765` running, you can close it: AcePressure turns Funnel on in the background within 15 seconds and keeps it on. Don't type `tailscale funnel 8765` any more: once Funnel is on in the background, Tailscale answers “listener already exists for port 443”, which only means Funnel is already on. Close that window, and don't run `tailscale funnel reset`.
- **Names on stream.** Filtered words match whole words in names, where `_`, a digit or a capital starting a new part also starts a word. “Kshitij” no longer shows as “K[filtered]ij”, while names like “noob_master”, “BigNoob” or “BIGNoob” are still filtered. Messages still follow **Filter whole words only**.
- **Words run together in names.** On an install upgraded from 1.6.3 or older, 1.6.4 also hid a filtered word inside a longer name. Now it doesn't: with “fuck” and “shit” in the list, names like “fuckyou”, “BULLSHIT” or “MOTHERFUCKER” show on the alert card, the OBS boards and the tip page, although the same word is still hidden in the message. Add the forms you want hidden in the TTS tab, under **Filtered words and phrases**: `fuck*` (fuckyou, fucker, fucking), `motherfucker*`, `bullshit*`, `madarchod`, `behenchod`. Avoid `shit*`, `gand*` and `chut*`: they also hide Shital, Gandhi and Chutki.
- Install_Piper.bat explains both ways to use Piper: as your main voice, or as a backup that keeps your main voice.
- Coming from 1.6.3 or older? Also do the OBS and Tailscale steps in UPDATE_1.6.4.md: refresh the OBS alert sources once, and turn off Tailscale key expiry.

Details: CHANGELOG.md.

## Install safely
1. Finish outstanding payment reviews, then close the AcePressure window. If you use the **AcePressure Tipping** startup task, also end it in Task Scheduler.
2. Back up the whole installation folder, including `.env`, `data`, `data-demo` and your own media.
3. Extract this ZIP into a new, empty folder. From its AcePressure folder, copy `acepressure`, `scripts`, `docs`, `tests`, `run.py`, `VERSION`, `README.md`, `Install_Piper.bat` and both `PACKAGE_MANIFEST` files into your existing installation, replacing those files.
4. Keep `.env`, `.venv`, `data` and `data-demo`. Don't replace them or run a fresh setup over them.
5. Start AcePressure with the same launcher as before: `Start.bat` for live or `Start_Demo.bat` for demo.

## Try it
- Within a few seconds of `Start.bat`, once Tailscale is connected, the AcePressure window shows “Tip link: Tailscale Funnel is on” or “Tip link: Turned Tailscale Funnel on”, with your tip page address. If Tailscale isn't answering yet, the window says that first.
- To watch it switch Funnel on: close AcePressure, run `tailscale funnel reset`, then run `Start.bat` again. Open your tip page on your phone with Wi-Fi off.

## Switch it off
Add this line to `.env`, then restart AcePressure:

    TAILSCALE_AUTO_FUNNEL=false

To stop sharing your tip page publicly, add that line first. Then close AcePressure (and end the **AcePressure Tipping** task if you use it) and run `tailscale funnel reset`. Without the line, AcePressure turns Funnel back on the next time it starts, including at sign-in through the startup task.

## If you need to go back
Close AcePressure (and end the **AcePressure Tipping** task if you use it). From the 1.6.4 ZIP, extracted as in step 3, copy the same items over your installation: `acepressure`, `scripts`, `docs`, `tests`, `run.py`, `VERSION`, `README.md`, `Install_Piper.bat` and both `PACKAGE_MANIFEST` files. Then delete `tests\test_release_165.py` (otherwise Test.bat stops with an error on 1.6.4) and start AcePressure again. Your backup works the same way if it holds 1.6.4; if you came from a 1.6.5 test build, use the 1.6.4 ZIP. Tested both ways.

## Limits
- It only turns Funnel on when it's off. If Funnel sends visitors somewhere else (another port, or demo mode on 8766), AcePressure leaves it, and the dashboard says so. It also leaves Funnel off if Tailscale already shares another program at your tip link's address, because Funnel would make that public too.
- It doesn't sign Tailscale in or reconnect it. If Tailscale is signed out or disconnected, open Tailscale and sign in or click Connect; AcePressure turns Funnel on within 15 seconds after that.
- Once AcePressure has turned Funnel on, or found it on without a `tailscale funnel` window, it leaves Funnel alone until the next start: if you turn Funnel off after that, it stays off. While a `tailscale funnel` window keeps Funnel on, or Tailscale isn't ready yet, AcePressure keeps checking every 15 seconds, so closing that window or running `tailscale funnel reset` makes it turn Funnel on in the background. To go private, close AcePressure first (see Switch it off).
- Tested on a Mac with a stand-in for Tailscale, not with real Tailscale on Windows.
