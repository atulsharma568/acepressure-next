# Update to AcePressure 1.6.4

Installs over 1.6.0, 1.6.1, 1.6.2 or 1.6.3. Your data, `.env`, sounds and OBS sources are kept. There is no database change.

## What's new
- **A stream session starts when OBS goes live.** Ending it stays your call: when OBS stops, the dashboard and the OBS dock offer **End session**. Switch it off in **Admin → OBS**.
- **Skip alert** stops the alert on stream: card, sound and voice. It's in Live activity, the OBS dock and Alertbox. **Skip TTS** still stops only the voice.
- **Replay in full** on tips whose voice was cut, and **…but read the whole message for tips from this amount (₹)** in Admin → TTS.
- **Test alert** is long enough to hear the cut when **Read whole messages** is off, and **Send to OBS as a test alert** in Admin → TTS sends your own sample.
- **A backup voice** (Admin → TTS → If the voice service fails), and a warning on the dashboard and in the dock when an alert's voice didn't play.
- **A warning when viewers can't reach your tip link** because Tailscale is signed out, disconnected or offline, or Funnel is off.
- **Stronger moderation**: filtered words apply to names, blocked supporters show as “Anonymous supporter” on the boards, and **Filter whole words only**.
- Messages typed on two lines no longer glue words together, and “<3” shows as ❤️ instead of “3”.
- The tip page stays calm while a payment waits for approval and keeps checking for 2 hours.
- If you are coming from 1.6.2 or older, also read UPDATE_1.6.3.md (and UPDATE_1.6.2.md from 1.6.1 or 1.6.0).

Details: CHANGELOG.md.

## Install safely
1. Finish outstanding payment reviews, then close the AcePressure window.
2. Back up the whole installation folder, including `.env`, `data`, `data-demo` and your own media.
3. Extract this ZIP into a new, empty folder. From its AcePressure folder, copy `acepressure`, `scripts`, `docs`, `tests`, `run.py`, `VERSION`, `README.md`, `Install_Piper.bat` and both `PACKAGE_MANIFEST` files into your existing installation, replacing those files. `run.py` is new in this list: it starts the tip-link check.
4. Keep `.env`, `.venv`, `data` and `data-demo`. Don't replace them or run a fresh setup over them.
5. Start AcePressure with the same launcher as before: `Start.bat` for live or `Start_Demo.bat` for demo. Keep your tunnel as it is.
6. Reload the dashboard.
7. In OBS, refresh each alert source once: right-click it → Properties → **Refresh cache of current page** (or restart OBS). Until you do, OBS keeps the old alert page: alerts still play, but it doesn't start sessions, and **Skip alert** stops only the voice.

## Check the OBS permission (once)
Right-click the horizontal alert source → Properties → **Page permissions**. Leave it at the default, **Read access to OBS status information**, or anything higher. “No access to OBS” stops sessions from starting when you go live.

## Turn off Tailscale key expiry (once, free)
Tailscale signs a PC out every 180 days unless you turn this off, and your tip link stops working then. Open login.tailscale.com → **Machines** → this PC → **⋯** → **Disable key expiry**. AcePressure warns 14 days before, but this stops it happening at all.

## Try it without spending money
- **Session**: next time you go live, don't press Start stream session. Within a few seconds of OBS going live, the dashboard shows a session “Live stream · <date>” and the line “OBS went live, so your stream session started by itself”. When you stop streaming, the dashboard and the dock offer **End session**.
- **Skip alert**: press **Test alert**, then **Skip alert** while it plays. The card leaves and the sound and voice stop, within about 2 seconds.
- **The cut**: in **Overview**, press **Shorten long messages**, then **Test alert**. The voice stops after about 100 characters. Press **Replay in full** on a real tip to hear one in full.
- **Your own sample**: in **Admin → TTS**, type a long message in **Try English or Hinglish** and press **Send to OBS as a test alert**.
- **Backup voice**: in **Admin → TTS → If the voice service fails**, choose a voice and press **Listen**. You hear it from this browser, not OBS.
- Listen on the horizontal source, because the vertical source is muted on purpose.
- None of these move real money or change your totals.

## If you need to go back
Close AcePressure, copy the code folders and `run.py` from your backup (or from the 1.6.3 ZIP, the same way as step 3), then start it again. 1.6.3 runs on the data 1.6.4 used and ignores the new settings. It shows skipped alerts as “No alert”. Refresh the OBS alert sources once more. Tested both ways.

## Limits
- Sessions start only from the OBS alert source, and only when OBS itself streams. Aitum Vertical streaming on its own doesn't start one.
- **Skip alert** acts on the next status check, so it can take up to about 2 seconds.
- The backup voice needs Piper (Install_Piper.bat) or a Windows voice on this PC. It doesn't cover the browser voice engine.
- The tip-link check only asks Tailscale on this PC. It can't see your router, your internet provider or Tailscale's own servers, and it doesn't check other tunnels.
- The tip page keeps checking only while a viewer keeps it open.
- Still needs your PC: OBS going live, Skip alert, the backup voice and the Tailscale warning were tested on a Mac with stand-ins, not with real OBS, Edge, Piper or Tailscale.
