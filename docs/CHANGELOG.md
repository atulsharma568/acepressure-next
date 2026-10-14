# 1.6.7 — Add several sounds or artwork files at once

You asked to upload several files at once in the Sound library and the Design studio. Your data, `.env`, sounds and OBS sources are kept. Install steps are in UPDATE_1.6.7.md.

- **Sound library → Add a sound** takes several files at once: select them together in the file picker (Ctrl-click or Shift-click). They go up one after another while the button counts (“Adding 2 of 5…”). Each sound is named after its file, and the emoji, category, minimum tip and “Viewers can pick” you set apply to all of them. With several files, Name and “Make it my default sound” are switched off: choose your default under **Default sound** afterwards.
- A file that can't be added (over 8 MB, longer than 30 seconds, not audio) doesn't stop the others. When the upload ends, a list under Add a sound shows what was added and why any file wasn't.
- If you're signed out, or AcePressure stops answering (for example a phone loses its connection), the upload stops there. The list names the files it didn't try, so you can add just those again.
- The emoji, category, minimum tip and “Viewers can pick” are read when you click Add: changing them while files upload doesn't change the files still to go.
- While files upload, the button keeps counting even if you switch tabs and come back, and the browser asks before you close or reload the page, because files not sent yet would be lost.
- **Design studio → Upload your artwork** takes several images or videos at once in the same way, including the stop when you're signed out or AcePressure stops answering. If you leave Design studio before the upload ends, the list is shown when you come back.
- The Design studio's image menus show the name a file was uploaded with next to its stored name (for example “logo.png · Kq3x9_abCdEfGh12.png”), so files uploaded together can be told apart. The menus are sorted by that name, and the message after an upload names files the same way. Files uploaded before 1.6.7 show only the stored name, as before.
- One file at a time works as before. The alert bundle (one visual and one sound) still takes one of each.

## Also fixed

- In the Design studio, clicking Upload again while a file was uploading uploaded it twice (a video can take a while to convert). A second click is now ignored, as in the Sound library, and the button says “Uploading…” until the file is in.

## Compatibility

- Copy the same files as for 1.6.6. No database change: uploaded names are kept in one new setting, which 1.6.6 ignores.
- Going back to 1.6.6 works on the same data folder: copy the same items from the 1.6.6 ZIP, then delete `tests\test_release_167.py`, or Test.bat stops with an error.

# 1.6.6 — Start.bat turns your tip link on

You asked for Start.bat to switch Tailscale Funnel on, so you don't have to type the command before a stream. Your data, `.env`, sounds and OBS sources are kept. Install steps are in UPDATE_1.6.6.md. 1.6.6 is the finished version of the 1.6.5 test build: if you installed 1.6.5, update the same way.

- When AcePressure starts in live mode and your tip link is a Tailscale address, it asks Tailscale whether Funnel is on. If it's off, AcePressure runs `tailscale funnel --bg 8765`, the command Setup_Tailscale_URL.bat uses. The AcePressure window then says “Turned Tailscale Funnel on”, and Funnel stays on until you turn it off. This happens on every live start: Start.bat, and the **AcePressure Tipping** startup task at sign-in.
- If Tailscale is still starting, signed out or disconnected, AcePressure tries again every 15 seconds and turns Funnel on once Tailscale is ready. While Tailscale doesn't answer at all, the window and the dashboard say so.
- If a `tailscale funnel 8765` window is still open, AcePressure leaves it on and says so. You can close that window: AcePressure turns Funnel on in the background within 15 seconds, so you don't need the window any more. After that, typing `tailscale funnel 8765` gets “listener already exists for port 443” from Tailscale: that only means Funnel is already on.
- The first time, Tailscale may ask you to approve Funnel. The AcePressure window shows the link: open it, approve, then restart AcePressure.
- AcePressure leaves Funnel alone when it already sends visitors somewhere else (demo mode on port 8766, say), or when Tailscale already shares another program at your tip link's address. It never turns Funnel on in demo mode. Once it has turned Funnel on, or found it on without a `tailscale funnel` window, it doesn't touch it again until the next start. While it is still waiting for such a window to close, it turns Funnel on in the background whenever Funnel goes off, even after `tailscale funnel reset`, so close AcePressure first to keep Funnel off.
- To switch this off, add `TAILSCALE_AUTO_FUNNEL=false` to `.env`. To stop sharing publicly, add that line first, then close AcePressure and run `tailscale funnel reset`. Without the line, the next start turns Funnel back on.
- The dashboard's tip-link check no longer says “Funnel is off” while a `tailscale funnel` window keeps your tip link reachable. It also counts only Funnel on your tip link's own address (port 443).

## Also fixed

- Supporter names on stream match filtered words as whole words. In a name, a space, `_`, a digit, or a capital starting a new part (NoobMaster, BIGNoob) starts a new word, as in gamer names. With “noob” in the list, “noob_master”, “Noob69”, “BigNoob” and “BIGNoob” are filtered; with “shit” in the list, “Kshitij” stays whole. In 1.6.4, an upgraded install also filtered inside names, so “Kshitij” showed as “K[filtered]ij” on the alert card, the OBS boards and the tip page. That also hid words run together, like “BULLSHIT” or “fuckyou”: to keep hiding those, add them to the list (`bullshit*`, `fuck*`, `motherfucker*`; see UPDATE_1.6.6.md). Messages still follow **Filter whole words only**.
- Install_Piper.bat no longer tells you to just switch the engine to Piper: that kept your old voices and left the alerts silent. It now gives both ways: Piper as your main voice with **Use selected voices**, or as the backup under **If the voice service fails**.

## Compatibility

- Copy the same files as for 1.6.4. No database, settings or OBS change.
- Going back to 1.6.4 works on the same data folder: copy the same items from the 1.6.4 ZIP, then delete `tests\test_release_165.py`, or Test.bat stops with an error.

# 1.6.5 — Test build, replaced by 1.6.6

Two test builds of 1.6.5 were made on 13 October 2026. Neither was a release. 1.6.6 has everything in them, plus fixes found by review:
- after the first build: an open `tailscale funnel` window is handled, more kinds of other Tailscale shares are spotted and named, names like noob_master or Noob69 are filtered, and Install_Piper.bat explains both ways to use Piper;
- after the second build: the window no longer hides a sign-in-expiry or other-PC warning after a slow Tailscale start, or shows “reachable” as a warning; names like BIGNoob or SHITLord are filtered; and the docs now cover going private while a `tailscale funnel` window is open, Tailscale's “listener already exists” message, words run together in names, restoring a backup, and going back to 1.6.4.

If you have either build, install 1.6.6 the same way (UPDATE_1.6.6.md). Your data, `.env` and sounds are kept.

# 1.6.4 — Sessions that start when OBS goes live, Skip alert, a backup voice, a tip-link warning and stronger moderation

You asked for all ten improvements from the list after 1.6.3. Your data, `.env`, sounds and OBS sources are kept. Install steps are in UPDATE_1.6.4.md.

## 1. A stream session starts when OBS goes live

- When OBS starts streaming, the alert source tells AcePressure and a session starts, named like “Live stream · 12 Oct”. A session that's already running is kept.
- A tip made just before the session started still gets its alert when the payment arrives.
- Sessions never end by themselves. When OBS stops streaming, the dashboard and the OBS dock say so and offer **End session**. A session still running after 8 hours offers **Start a new session**.
- If you end a session while OBS is still live, refreshing OBS doesn't restart it for 2 hours. Going live again does.
- Switch it off in **Admin → OBS → When OBS goes live**. It needs the alert source's Page permissions at the default, “Read access to OBS status information”, or higher.

## 2. Line breaks and hearts in messages

- A message typed on two lines (“bhai” Enter “kya”) used to show and be read as “bhaikya”. Line breaks and tabs now become spaces.
- “<3” used to show as “3” and be read as “three”. It now becomes ❤️ (and “</3” becomes 💔). The voice skips the heart like other emoji. To hear it, use **+ ❤ → love** in Admin → TTS → Pronunciations.

## 3. A cleaner cut when the voice reads only the start

- A word that ends exactly at the limit is kept, even when a full stop or comma follows it.
- The cut never ends on a word that leads into the part left out, such as “of”, “Rs”, “ka” or “ki”, and never splits a number like ₹1,000.

## 4. A test alert long enough to hear the cut

- With **Read whole messages** off, **Test alert** now uses a long Hinglish message, so you hear where the voice stops on stream.
- **Admin → TTS → Send to OBS as a test alert** sends your own sample to OBS as a test. The sample box takes as many characters as viewers can type.

## 5. A calmer tip page while a payment waits for approval

- “Automatic checks have stopped” is gone. When the payment window closes, the tip page keeps checking once a minute for 2 hours and tells viewers they can leave it open.
- When AcePressure has seen a payment that waits for your review, the page says “Waiting for approval” instead.
- A payment in progress comes back first when the page is reopened, and the note about how much the voice reads stays up to date.

## 6. Replay in full, and big tips read in full

- With **Read whole messages** off, a tip whose voice was cut has **Replay in full** in Live activity. Only that replay reads everything.
- **Admin → TTS → …but read the whole message for tips from this amount (₹)** reads the whole message for big tips (0 = never). The tip page and the dashboard chip say so.

## 7. Skip alert

- **Skip alert** (Live activity, the OBS dock and Alertbox) stops the alert on stream: card, sound and voice, on both layouts. **Skip TTS** still stops only the voice.
- **Block** also stops that supporter's alert on stream and drops any still waiting. **Mute** stops their voice at once.
- The Paytm review page shows each tip's message as it would appear on stream, before you approve it.
- Fixed: an alert that played while others waited could be marked “Missed” halfway through, and its server voice could fail to load.

## 8. A warning when the voice fails, and a backup voice

- When the last alert's voice didn't play, the dashboard and the OBS dock say why and what to do. Live activity marks such tips “Voice not read”.
- **Admin → TTS → If the voice service fails**: choose a Piper or Windows voice. If Edge or Azure fails or takes too long, that voice reads the alert instead, for 2 minutes, then the main voice is tried again.
- Edge and Azure now give up after about 12 seconds, so the backup has time to speak.
- Browser voices play inside OBS, where AcePressure can't step in, so the backup doesn't cover them. Admin → TTS says so when browser voices are chosen.

## 9. A warning when viewers can't reach your tip link

- Every minute, AcePressure asks Tailscale on this PC whether Funnel still serves your tip link. If Tailscale is signed out, disconnected or offline, Funnel is off, or the sign-in expires within 14 days, the dashboard and the OBS dock say so, with the fix. The AcePressure window shows it too.
- Tailscale signs a PC out every 180 days unless key expiry is turned off. The warning links the free fix: login.tailscale.com → Machines → this PC → ⋯ → Disable key expiry.
- Only checks your own PC. Other tunnels (ngrok, cloudflared) aren't checked.

## 10. Stronger moderation

- Filtered words now apply to names too: in alerts, on the OBS boards and in the tip page's Top supporters.
- A blocked supporter shows as “Anonymous supporter” on those boards, without a message. Totals and your dashboard stay exact.
- **Filter whole words only** stops a filtered word from catching other words (“hell” leaves “hello” alone). End a word with * to catch its endings (noob* → noobs). New installs start with it on. Upgrades keep the old way until you tick it.

## Compatibility

- No database change. The new settings are added when AcePressure starts.
- OBS: refresh each alert source once (right-click → Properties → **Refresh cache of current page**) or restart OBS, so it loads the new alert page. Until then, alerts still play, but OBS doesn't start sessions, and **Skip alert** stops only the voice.
- `run.py` changed (it starts the tip-link check), so copy it when you update.
- Going back to 1.6.3 works on the same data folder. 1.6.3 shows skipped alerts as “No alert”.

# 1.6.3 — Read whole messages, or only the start of long ones

You asked for a switch to choose whether the voice reads a long message in full, because sometimes you want the whole message read and sometimes you don't. Your data, `.env` and OBS sources are kept. Install steps are in UPDATE_1.6.3.md.

## 1. Read whole messages

- **Live activity** has a new button next to **Mute TTS**. **Shorten long messages** makes the voice read only the start of long messages, and **Read whole messages** switches back. The Activity dock you can keep inside OBS has the same button. The change applies from the next alert.
- When it's off, the voice reads the first 100 characters and stops after a whole word. The alert card still shows the whole message, and short messages are read in full. Change the number in **Admin → TTS → When “Read whole messages” is off, read up to this many characters** (20–500).
- While it's off, a chip at the top of the dashboard says “The voice reads only the first 100 characters”, with a **Read whole messages** button, like the one shown when TTS is muted.
- Emoji and long repeats are skipped before the characters are counted, so they don't use any up.
- Every engine reads the same start: browser voices in OBS, Windows SAPI, Edge, Piper and Azure. **Listen to sample** plays it too. When your sample is cut, “The voice reads” adds “Cut short: “Read whole messages” is off”.
- The tip page tells viewers under **Read my message aloud**: “The voice reads the first 100 characters of your message.”
- The switch starts on, so nothing changes until you press the button.

## 2. Clearer settings

- **Maximum message characters** is now **Longest message viewers can type (up to 500)**. It is still the most a viewer can type, and it is separate from how much the voice reads. Raise it if you want room for longer messages.
- A number setting outside its range now names the setting and the allowed range, for example “Minimum display duration (seconds) must be a whole number from 3 to 30.”

## Compatibility

- No database change. The two new settings are added when AcePressure starts.
- OBS needs no refresh: the 1.6.2 alert page already reads the spoken copy the server sends, and that copy is now cut when the switch is off.
- Going back to 1.6.2 works on the same data folder. 1.6.2 ignores the new settings, so it reads whole messages. Tested: 1.6.3, then 1.6.2, then 1.6.3 again.

# 1.6.2 — Volume for every sound and the voice, links hidden on stream, pronunciations and smarter Hinglish

You asked for more polish on top of 1.6.1. This release adds volume controls, keeps links off your stream, lets you teach the voice your own words, skips emoji in the voice and reads Hinglish more naturally. Your data, `.env` and OBS sources are kept. Install steps are in UPDATE_1.6.2.md.

## 1. Volume for every sound and for the voice

- **Admin → Sound library**: every sound that has audio now has a volume slider (10–100 %) next to **▶ Preview**. It saves when you let go of it (with the arrow keys, it saves where you stop). OBS plays that sound at this volume, and so do **▶ Preview**, **▶ Preview default** and the tip page's previews.
- **Admin → TTS → Voice volume** (10–100 %, default 100 %) sets how loud the voice reads messages in OBS for every engine, and in **Listen to sample** and the tip page's voice preview. Press **Save settings**.
- Your sounds start at 100 %, so nothing gets quieter until you move a slider. Chime and Pulse keep their fixed level, and an alert video's own sound isn't changed.

## 2. Links never reach your stream

- **Hide links in messages and names** (Admin → TTS, on by default): a web address or email in a tip's message or name shows as “[link]” on the alert card, the leaderboards, the recent-tips list and the tip page's top supporters, and the voice never reads it. For example: www.scam.com, bit.ly/x, discord.gg/x, t.me/x, freeskins.xyz, amazon.in/deal, someone@gmail.com.
- Ordinary text is left alone: “great stream.in the end”, “gg.wp”, “v1.6.2”, “Rs.500”, “5.30 pm”, “op.gg” and UPI IDs such as name@paytm.
- Your dashboard still shows exactly what the viewer typed, so you can see who posted a link. Turn the switch off if you want viewers' links shown.

## 3. The voice skips emoji and long repeats

- **Don’t read emoji aloud, and shorten long repeats** (Admin → TTS, on by default): the voice no longer reads emoji names, “hahahahahaha” becomes “hahaha” and “!!!!!!” becomes “!!!”. Numbers are never shortened (₹100000 stays ₹100000). The alert card still shows the emoji.
- A message that is only emoji shows its card without the voice.

## 4. Pronunciations

- **Admin → TTS → Pronunciations**: teach the voice your channel name, agent names and slang as **Word** → **Say it as**, for example AcePressure → Ace Pressure or gg → good game. Leave **Say it as** empty to skip a word, or give an emoji words (😂 → haha).
- Whole words only, in any capitals, and the longest match wins (“gg ez” before “gg”). Up to 100 words. A word listed twice is refused with a message.
- Pronunciations apply in OBS for every engine, in **Listen to sample** and in the tip page's server-voice preview. The alert card still shows what the viewer typed.

## 5. See what the voice will read

- Under **Try English or Hinglish** a new line, “The voice reads: …”, shows exactly what the selected voice will say for your sample, with pronunciations, hidden links, skipped emoji and Hinglish conversion applied. It updates as you type, before you press **Listen to sample**. When the voice is English and the sample is Hinglish, it also shows what a Hindi voice would read.

## 6. Smarter Hinglish

- 1.6.1 stopped converting words that are also English (main, mat, mere, din, mast …) anywhere, so Hindi sentences lost them: “main aa gaya” kept an English “main”. 1.6.2 reads each part of a sentence (split at . , ! ? ; :) and converts those words when that part is Hindi:
  - “main aa gaya bhai, tension mat lo” → “मैं आ गया भाई, tension मत लो”
  - “aaj ka din mast tha” → “आज का दिन मस्त था”
  - “jai shri ram” → “जय श्री राम”
- English stays English: “I play the main role”, “Put the mouse on the mat”, “Reyna main here”, “Jett main hoon bhai” (Jett main), “mera main account” (main account), “16gb ram hai bhai”, “NA server”, “lo-fi”, @names, #tags and web addresses.
- About 440 everyday Hinglish words are now known, up from about 120 (agli baar, pakka, jeetenge, ek baat bolu, janamdin mubarak …).
- With **Browser voices (OBS)**, the overlay now reads the same converted text the server makes for Edge, Piper and Azure. An OBS source still on the 1.6.1 page keeps working with its own shorter lists until you refresh it.
- This is still a dictionary, not a translator: spellings it doesn't know stay as typed. Listen to your voices before you choose one.

## 7. Fixes

- Piper works with piper-tts 1.2 again (older installs), as well as 1.8. 1.6.1 needed the newer `synthesize_wav`.
- On the tip page, the browser-voice sample reads Roman Hindi as Devanagari when the viewer picked a Hindi voice, as OBS does.

## Compatibility

- Database migration 009 adds the sound volume column on first start. There is nothing to do, and existing sounds play at 100 %.
- Refresh the OBS alert source's cache once to get the volumes. Until then the old page keeps working: alerts, sounds and the voice play at full volume.
- Going back to 1.6.1 works on the same data folder. Tested: 1.6.2, then 1.6.1, then 1.6.2 again, with volumes and settings kept.

# 1.6.1 — Focused TTS corrections

Preserve the preview draft during dashboard saves; protect English words in server/browser Hinglish conversion; use Piper synthesize_wav with pinned 1.8.0, reject bad audio and isolate model caches; defer optional Edge imports; allow explicit Piper download data directory. No payment or database migration changes. See UPDATE_1.6.1.md.

# 1.6.0 — One sound library for your memes, free starter sounds, Edge and Piper voices in OBS, and a go-live checklist

Your memes now live in one **Sound library**, with 8 free starter sounds to get going (sections 1 and 2). Sections 3 to 8 fix six problems: Edge and Piper voices that were silent in OBS, a tip page that said "paused" without saying why, tips that never got an alert, alerts taken by a forgotten browser tab, rate limits shared by every viewer behind Tailscale Funnel, and a second copy of AcePressure starting by accident.

## 1. One sound library for your memes

- You asked for every tip alert to be a meme, the way StreamTipz lists its memes under "alert sound". Now every sound you upload lives in one library, and viewers pick from it on the tip page.
- **Admin → Sound library** replaces the **Sounds/media** and **Soundboard** tabs. Upload each sound once under **Add a sound**, with an optional name, emoji, category and minimum tip, whether viewers can pick it, and whether it becomes your default. Each upload is one row under **Your sounds**.
- In **Your sounds**, tick **Viewers can pick** and type the **Min tip (₹)** right in the table (0 = any tip). Changes save as you make them. **Edit** still changes the name, emoji, category and display order, and it no longer turns a ₹0 sound into ₹50 when you save.
- **Viewer picks & default sound** sets the sound that plays when a viewer doesn't pick one: **Chime**, **Pulse**, **Silent**, **Alert video’s own sound** (only when your alert visual has sound) or any of your sounds. **Make default** on a row does the same, and **▶ Preview default** plays it in your browser. If the default's audio file goes missing, alerts play Chime and the panel says why.
- One switch, **Viewers can pick a sound on the tip page**, turns viewer picks on and off. When it's off, the tip page hides the picker and every tip plays your default.
- The tip page has one picker, **Alert sound**. Its first tile is **Streamer’s default**, followed by the sounds you let viewers pick, with search, categories and each sound's minimum tip. Tapping a sound that needs a bigger tip says how much, on the tile itself as well. If a viewer lowers the amount below their pick's minimum, the pick stays and **Pay** asks for a bigger tip or another sound, so a pick is never dropped without the viewer knowing. Chime, Pulse and Silent are no longer viewer choices.
- A viewer's paid pick still plays if you untick or reprice that sound after they tipped. Only deleting the sound, or losing its file, drops the pick, and then your default plays.
- **Design studio** no longer has **Separate alert audio**; its new **Open Sound library** button takes you to your sounds. **Upload alert bundle · visual + sound** moved to Sound library. A sound uploaded with a bundle becomes your default and stays hidden from viewers until you tick **Viewers can pick**. A video with its own sound and no separate file makes **Alert video’s own sound** your default. If you later switch to an alert visual with no sound, that default goes back to Chime and the page tells you.
- Every library sound can be up to 30 seconds and 8 MB (alert sounds used to stop at 20 seconds). Longer clips are still refused, never cut. **Fix_Audio.bat** still cuts at 20 seconds, so for a longer clip upload the original and let the admin page convert it.
- **▶ Test on stream** on any row sends that sound to OBS as a labelled test alert, even when viewers can't pick it. **Test alert** in the default panel plays your default.
- **Delete** asks first. The sound's file is removed from this PC only when nothing else uses it, and tips that picked it play your default.
- The avatar upload moved to **Settings → Creator avatar**.
- In OBS, an alert plays the viewer's pick, otherwise your default. If a picked clip can't load, your default plays instead (Chime, when your default is the alert video's own sound). If the alert video's own sound can't play, Chime plays instead of silence. Once a sound file starts, the overlay lets it play for up to 31 seconds (before, it allowed 21 seconds from the moment it asked for the file), so 30-second sounds aren't cut off. A clip that hasn't started after 10 seconds is skipped and your default plays.

## 2. Free starter sounds

You asked: *"can you collect the few suggested soundboard memes and add those as well"*.

- **Add starter sounds** (**Admin → Sound library → Your sounds**) adds 8 free sound effects that viewers can pick straight away: Vine Boom, Air Horn, Cash Register, Victory Fanfare, Clap, Game Over, Ba Dum Tss and Sad Trombone. Each is under 4 seconds and costs ₹20 to pick (₹50 for Victory Fanfare and Game Over). Rename, reprice, replace or delete them like any of your sounds.
- They were made from code for AcePressure, with no samples, recordings or third-party audio, and are released into the public domain under CC0 1.0. Because they are made from code with no third-party audio, they shouldn't trigger copyright claims. The files are in `acepressure/starter_sounds`, and the scripts that made them are in `scripts/starter_sounds`.
- The same click adds 14 Indian meme slots for your own clips: Thug Life, Chai Peelo, Babu Bhaiya, 440 Volt Ka Jhatka, Rasode Mein Kaun Tha, Pawri Ho Rahi Hai, Binod, Beta Tumse Na Ho Payega, Papa Kehte Hain, Ye Chemical Hai, Dhoondho Dhoondho, Mauka Mauka, Hum Honge Kaamyab and Hera Pheri Laughter. Famous dialogue, film, TV and song memes are copyrighted, so they can't be bundled. The slots wait under **Starter slots waiting for audio**, and a slot's first clip makes it pickable. Songs and film or TV dialogue can get copyright claims on YouTube, so prefer short reaction clips.
- Only the button adds them. It never changes your default sound or the picks switch, and nothing is added at startup. Clicking again skips what is already there. Deleted a starter sound by mistake? Click again to get it back. A slot that already has your own clip is never replaced.
- Each copy gets a new random name in `data/media`, so the bundled files are never changed or deleted.
- If you already added the 1.5.9 starter catalog, the button fills its empty Vine Boom, Air Horn, Cash Register, Victory Fanfare, Clap and Game Over slots and adds Ba Dum Tss and Sad Trombone.

## 3. Edge and Piper voices speak in OBS

- With **Edge TTS** or **Piper** selected, viewer messages and **Test alert** were silent in OBS. The overlay looked for a browser voice with that name, never found one and reported `voice_missing`. Voice previews worked because the server makes them, which is why TTS looked fine on the admin page.
- The OBS overlay now gets the spoken audio from AcePressure for Edge, Piper, Windows and Azure, so OBS needs no installed voice. **Browser voices (OBS)** work as before.
- If the audio can't be made, or takes more than 20 seconds, the alert card still shows without the voice and **Admin → TTS** tells you. If OBS gets the audio but can't play it, that is reported too.
- **Admin → TTS** checks the last OBS readout as soon as you open it and says what happened in plain words: "Last OBS readout played (time)", a missing browser voice, or why AcePressure couldn't make the audio (for example "Edge TTS is not installed. Run Install_Edge_TTS.bat…"). **Check last OBS TTS result** still refreshes it.
- If OBS still runs the overlay page from before the upgrade, Edge and Piper stay silent, and **Admin → TTS** now says to refresh the OBS source instead of asking you to choose the voice you already chose.
- **Skip TTS** pressed while the alert sound is still playing now cancels that alert's readout. Before, the message was still read once the sound ended.
- Privacy: the engine guide and the tip page now say that Edge TTS sends the message to Microsoft's online voice service, as Azure does. Piper, Windows and browser voices stay on this PC.
- The OBS overlay and dashboard pages load their scripts and styles with `?v=<version>`, so OBS picks up new code after an upgrade.

## 4. Tips paused? One checklist shows exactly why

- The tip page used to say "Tips are paused while payment verification is being configured." whatever the reason. Now one checklist decides whether viewers can tip, and the dashboard, the Paytm page, the Start window and the tip page all show it. It checks, in this order: **UPI ID and payee name**, **Public HTTPS address**, **Payment verification** (the Paytm bridge, or the older SMS bridge) and **New tip requests** (Settings → Accept new tip requests).
- If `.env` changed after AcePressure started (for example after Setup_Tailscale_URL.bat), an amber "Restart needed" line tells you to close the AcePressure window and run Start.bat again.
- On every dashboard page and in the Activity Dock, a red line, "Viewers can't tip right now. …", names the first missing step. The dashboard adds a button for it: **Open Settings**, **Open Paytm bridge ↗** or **Resume tips**. When everything is ready, a green line shows "Tip page is live: <your link>" with **Copy link**. In the dock these lines are text only.
- **Settings** opens with a new **Payment verification** panel: every check with ✓ or ✗, your tip link, the last phone notification and whether automatic matching is on. The SMS form is now called **Advanced: iPhone SMS bridge (optional, older method)**.
- **/admin/paytm** shows the same checklist and a one-line status (enabled, matching mode, token, bank marker, last notification). The address for your phone appears only once AcePressure runs on its https address. Generating a new token now warns that the bridge switches off and your tip page pauses until you paste the new token into your phone automation and click **Enable bridge**.
- Viewers see "Tips open soon — <your name> is finishing payment setup." or "<your name> isn't taking new tips right now. Please check back soon." The pay button stays off until tips are open. The page checks again every minute and when the viewer returns to the tab, so it opens by itself once you finish. Before, a tip page on a plain-http address looked ready and checkout then failed.
- The Start window prints the dashboard link on this PC, your tip link, and **Payments: READY**, **Payments: PAUSED - <the missing step>** or **DEMO MODE - no real money.**
- The tip page also works when the browser blocks storage (some private windows). If the form can't load, it says "Couldn't load the tip form. Check your connection." with a **Retry** button.

## 5. Mid-stream: why no alert?

- Alerts and automatic Paytm matching only work for tips created while a stream session is running, and nothing told you. Now, when you're accepting tips but no stream session is running, the dashboard and Activity Dock show a red line, "No stream session running. Tips won't play OBS alerts, and Paytm payments will wait for your review. …", with **Start stream session**.
- Payments waiting for your review show as an amber line, "N payment notification(s) need your review (oldest M min).", with **Review ↗** on the dashboard (text only in the dock).
- A "TTS is muted" chip has an **Unmute** button, and Live activity has **Pause new tips** / **Resume new tips** (pausing asks first).
- Every tip in Live activity shows what happened to its alert: **On stream**, **Playing**, **Queued**, **Missed – use Replay**, **Cancelled** or **No alert**. Hover over **No alert** for the reason: alerts play only for tips created and paid while a stream session is running, and Replay shows it now.
- **/admin/paytm** refreshes itself every 10 seconds, but waits while you're typing a reason or have changed a choice. The tab title shows how many payments wait, for example "(2) AcePressure payments". Each review reason is explained in plain words under its code. **Play alert on stream** is ticked for you only when that tip's stream session is still running.
- The viewer's thank-you is honest: "Your ₹X support is on its way to the stream. Watch for your alert!" only when an alert is queued, otherwise "Thank you! <your name> has received your ₹X support."
- Muting a supporter no longer unblocks them. Mute and Block now change only the setting you click.

## 6. OBS gets the alerts, not a forgotten browser tab

- Every open overlay page competed for alerts, so a forgotten alert tab in Chrome could take alerts that never reached OBS. Now OBS sources get alerts first. While an OBS source is connected, a normal browser tab with the same link shows "Preview only: OBS is taking alerts for this layout. Close this tab, or add &claim=always to use it." and takes none. A normal tab also stops taking alerts while it's hidden.
- Other streaming apps (not OBS): add `&claim=always` to the alert link.
- The dashboard's Overview and the Activity Dock show which alert overlays are connected, for example "Alert overlays · Horizontal: OBS ✓ · Vertical: not connected". A red line means a normal browser tab is taking alerts. An amber line means two OBS sources compete for one layout, or a session is running with no horizontal overlay connected.
- **Test alert** now says where it went ("Test alert sent. Horizontal: OBS ✓ · Vertical: not connected."), or that no overlay is connected (test alerts expire after 5 minutes).
- **Admin → OBS** gives each overlay an **OBS on this PC (recommended)** link, which keeps alerts working if Tailscale drops, and, once you have an https address, **OBS on another PC** with your public link. Sources you already added keep working, so there's nothing to change.
- One failed connection no longer flashes a big red error on stream. A small label appears in the bottom-right corner only after 3 failures in a row (at once for a wrong overlay key).

## 7. Each visitor gets their own limits behind Tailscale Funnel

- Behind Tailscale Funnel every request reaches AcePressure from this PC, so all viewers shared one limit. One raid or bot could block everyone's tips, 8 sign-in attempts from anyone locked you out for 15 minutes, and junk posts could block your Paytm phone.
- AcePressure now uses the visitor's address that the tunnel passes along (the `X-Forwarded-For` header, trusted only from this PC). Each visitor gets 15 tip requests per 10 minutes, with a shared safety net of 200. "Forget this browser" has its own limit. Sign-in allows 8 attempts per 15 minutes per visitor, plus 40 shared by all internet addresses; sign-ins from this PC, your home network or your tailnet never count towards the shared 40.
- Both phone bridges check the token first, so wrong-token posts have their own limit and can't use up your phone's allowance.
- "Too many requests" now says how long to wait, for example "Please wait about 10 minutes."
- `data/logs/server.log` notes once that per-visitor limits are active. No address is logged.

## 8. Safe restarts and a checked Tailscale Funnel setup

- A second copy no longer starts by accident. If AcePressure is already running (another window, or the **AcePressure Tipping** startup task), Start.bat says "AcePressure is already running on port 8765 … Close that window - or end the task in Task Scheduler - then run Start.bat again." If another program has the port, it says so and suggests a different `PORT` in `.env`. Before, Windows could quietly run two servers.
- **Setup_Tailscale_URL.bat** shows Tailscale's approval link instead of hiding it, and writes your public address to `.env` only after Tailscale confirms Funnel is on. If it can't confirm, `.env` stays as it was and you can run it again. The address comes from the exact name Tailscale gives your PC.
- It then prints your next steps in order: restart AcePressure, enter your UPI ID and payee name, set up the Paytm bridge, point your phone automation at `/api/bridge/paytm`, start a stream session and send yourself a small test tip. If AcePressure is still running with the old address, it says to restart first.
- `docs/TAILSCALE_FUNNEL.md` and `START_HERE.txt` follow the same Paytm-first steps. The bank-SMS route is optional.

## Upgrading from 1.5.9

- Close the AcePressure window (and stop the **AcePressure Tipping** task if you installed it) before you copy the new files: a second copy now refuses to start.
- On first start AcePressure saves `data/backups/before-1.6.0-sound-library.sqlite3`, then moves your sounds into the library once. Files are never renamed or deleted. Sounds viewers could choose stay pickable at any tip. Your Design studio sound, or your first listed sound, becomes the default, and a video bundle with its own sound becomes **Alert video’s own sound**. Keep the backup until you have checked your sounds. If the PC crashes or loses power while the backup is being saved, the half-written copy is thrown away and a complete one is saved on the next start.
- Your other uploads arrive hidden from viewers: tick **Viewers can pick** to offer one. Soundboard clips keep their names, prices and on/off state.
- Viewers can no longer choose Chime, Pulse or Silent; they are default-only.
- If viewer sound choice was off but your soundboard was live, **Viewers can pick** is turned on so the soundboard keeps working; your other uploads start hidden.
- A viewer's paid pick now plays even if Design studio had a fixed sound or a video bundle had its own sound. In 1.5.9 the fixed sound replaced every pick, and a video with its own sound silenced picks. The video now stays muted while a pick plays.
- **Design studio** no longer has **Separate alert audio**. Choose your default in **Sound library** instead.
- Every sound can now be up to 30 seconds (alert sounds were capped at 20). **Fix_Audio.bat** still cuts at 20 seconds.
- Names typed by hand in an older version aren't moved. They are listed under **Older sound files outside the library**, where you can delete them.
- If the move can't finish, AcePressure still starts with your old sound settings, shows a message in its window and tries again on the next start.
- If an OBS source stays silent after upgrading, or a long sound stops at 21 seconds, right-click the source → **Properties** → **Refresh cache of current page** once.
- No `.env` or OBS Browser Source URL changes. Pages left open across the upgrade keep working; reload them to see the new picker and Sound library.

## Tests

- 692 automated tests pass (503 in 1.5.9). New tests cover:
  - the sound library (`test_sound_library.py`): the one-time move from 1.5.9, the default sound, tip picks, which sound each alert plays, file clean-up, uploads, pages left open across the upgrade, the starter sounds, and static checks of the new tip-page and overlay code;
  - the go-live checklist (`test_readiness.py`);
  - the no-session warning, review count, alert status and thank-you text (`test_attention.py`), and mute versus block (`test_supporter_moderation.py`);
  - OBS-first claiming, connected overlays and local OBS links (`test_overlay_clients.py`);
  - Edge and Piper audio for OBS, Voice Studio messages and versioned scripts (`test_overlay_server_tts.py`);
  - per-visitor rate limits behind a tunnel (`test_rate_limits.py`);
  - the single-copy guard (`test_startup_guard.py`) and the Tailscale setup script (`test_tailscale_setup.py`);
  - fixes from an independent review before release (`test_review_fixes_overlay.py`, `test_review_fixes_ui.py`): the crash-safe backup, Skip TTS during the alert sound, the overlay's sound timers, the OBS-refresh hint in Admin → TTS, a pick that survives a new amount, and the Sound library's upload and phone-layout fixes.
- Checked in Chrome during development: Edge audio reaching the overlay and Voice Studio's messages, the go-live checklist and tip-page notices, /admin/paytm refreshing itself, OBS-first claiming with an OBS page next to a normal tab, and the sound picker with real mouse and touch input (a pick survives a new amount, and Pay asks for more instead of dropping it).
- Still to check on your Windows PC: Edge and Piper speaking through OBS, a meme played with **▶ Test on stream**, a second Start.bat being refused, and Setup_Tailscale_URL.bat showing Tailscale's approval link.

---

# 1.5.9 — Broken audio fixed on upload, your own filenames, and a release-hardening pass

Answers two requests: *"will this new bat file fix the mp3 file if it's broken, as soon as we upload it on the admin website?"* (yes, now it does) and *"the audio files for alert I am uploading, their name gets changed after uploading to some random number mixed with alphabets"* (your filename is now shown everywhere). A full review of the release followed; everything it found is fixed below.

## 1. Broken audio is fixed when you upload it

- Works on all three audio uploads: **Sounds/media → Upload alert sound**, **Soundboard → upload audio on a tile**, and **Sounds/media → Upload alert bundle · visual + sound**.
- Files are checked by their content (file signature plus an FFmpeg probe of the actual codec), never by the filename.
- Files that already play in browsers are stored byte-for-byte. Only unplayable ones (AAC renamed to .mp3, MPEG Layer I/II, μ-law or ADPCM WAV, files with no real audio frames, and similar) are converted with Fix_Audio.bat's recipe: MPEG Layer 3, 128 kbps CBR, 48 kHz stereo, metadata stripped. The upload toast says when this happened, and the Sounds/media table marks the file **Auto-fixed**.
- **Nothing is silently cut.** Clips over the limit (20 s for alert sounds, 30 s for soundboard clips) are refused with "trim it first".
- Lengths come from real frame counts:
  - Xing/Info/VBRI headers for MP3;
  - the last page's granule position for Ogg Vorbis and Opus;
  - only the frames actually present for WAVs written by streaming tools (which declare a bogus 13-hour size).
  When a header looks stale (a short clip cut out of a longer VBR file keeps the old frame count), the server decodes the audio to measure it before refusing. LAME's ~50 ms encoder padding is tolerated, so a clip right at the limit is accepted.
- A broken file's reported length is only a bitrate guess (raw AAC with a silent intro read 5x too long), so broken files are measured after conversion, not before.
- **Without FFmpeg:**
  - valid MP3/OGG/WAV files upload exactly as before;
  - an "MP3" that is really AAC, MPEG Layer I/II or has no audio is refused, with a pointer to `Install_Media_Tools.bat`, instead of being stored and failing later on the tip page.
- FFmpeg only reads plain local audio containers (protocol and demuxer whitelists), so a disguised playlist file cannot make it open URLs or other files on the PC.
- Alert bundle: the sound is validated before the visual is written, and a failed disk write removes what was already written, so a rejected upload never leaves orphan files.

## 2. Your own filenames, everywhere

- Files are still stored under random names on disk (safety, unchanged). The name you uploaded is shown in Sounds/media (with a small "stored as …" line), the Design Studio's alert-sound list, upload toasts and the tip page's alert-sound buttons. Soundboard tiles keep the tile name you typed.
- Repeated names are numbered (`meme (2)`) so lists stay unambiguous. Viewer-facing labels drop the extension and never collide with Chime, Pulse or Silent.
- Names are display-only. Folder parts and invisible direction-override or control characters are stripped. Emoji sequences and Indic or Persian joiners (ZWJ/ZWNJ) are kept. Names are capped at 120 characters.
- Privacy: when "Let viewers choose a sound" is off, the public page no longer receives your sound names at all.

## 3. Sounds/media page

- **Viewer sound choices** uses chips: tick a sound to offer it, and click **Make default** to pick the sound that plays when viewers can't choose or don't.
- Unticked uploads stay listed under **Uploaded sounds**, marked **Not offered**, so you can offer them again or delete them. Before, they became invisible files on disk.
- Each sound shows a status: **OK**, **Broken** (with the reason), **Auto-fixed**, **Unchecked** (FFmpeg not installed), or **Missing** (the file is gone from `data/media`). Phones get stacked cards instead of a wide table.
- The server only accepts built-in sounds, entries already in the list, or files that really exist in `data/media`.
- Deleting an entry typed by hand in an older build only removes it from the list and never touches disk. Deleting the last sound falls back to Chime.

## 4. Windows reliability

- Every `.bat` file uses Windows (CRLF) line endings and plain ASCII; cmd.exe can skip labels in files with Unix line endings.
- Every launcher sets `PYTHONUTF8=1`, and every text file read or write names UTF-8. Python 3.12–3.14 on Windows otherwise uses the ANSI code page and can crash on ₹ or Hindi text.
- MIME types for scripts, styles, SVG, fonts and media are pinned in the app. Some Windows registry entries map `.js` to `text/plain`, which together with the `nosniff` header blocks every script on the page.
- **Fix_Audio.bat** was rewritten so names like `bruh (1).mp3`, `Tom & Jerry.mp3` or `wow!.mp3` work. It cuts at 20 s (the alert limit) and says so. For soundboard clips up to 30 s, upload the original instead: the admin page converts without cutting.
- `setup.py` stops with a clear message when `.env.example` is missing (a partly extracted zip) instead of a traceback.
- Over-size uploads get a readable message ("That file is too large. Sounds and images can be up to 8 MB, videos up to 24 MB.") instead of a bare error page. Waitress's body limit (36 MB) now sits above Flask's own limits: 26 MB, or 34 MB for the alert bundle so a 24 MB video plus an 8 MB sound fits in one upload. The admin page also shows a readable message when the server returns a non-JSON error.

## 5. Look and feel

**Tip page**

- Redesigned payment step: the exact amount to pay stands out, the time left is a small chip, "waiting for payment" is shown in amber, and every copy button looks the same.
- Tapping a preset amount (₹20, ₹50, …) now updates the soundboard unlock meter, the locked tiles and the tier badge straight away. Before, they stayed on the old amount until you typed.
- On phones every soundboard tile is shown. Before, the last row (including Binod, the only ₹20 clip) was hidden in a small inner scroll box.
- Voice cards show gender as a thin coloured bar inside the card, and the selected card gets one clean red outline.
- Smaller polish: no number spinner in the amount box, a styled "Try opening an installed UPI app" section, a larger thank-you heading, and matching buttons on the thank-you card.

**OBS overlays**

- Every widget was checked at its Browser Source size with nothing clipped: horizontal alert 2560×1440, vertical alert 1080×1920, goal 700×180, top 3 700×260 (900×500 for BRB), recent tips 700×400. **Admin → OBS** lists the sizes next to each link.
- The Inter font now ships with the app (see **Fonts**), so alerts look the same on every PC.

**Dashboard**

- Tables: amounts are right-aligned with fixed-width digits, statuses are coloured badges, the top three get gold, silver and bronze medals, and the Audit header stays visible while you scroll.
- Live activity: Replay, Mute supporter and Block sit next to each tip's time. Test alert, Skip TTS and Mute TTS stay on one row on phones and in the OBS dock.
- OBS activity dock: the Paytm link is hidden, because tapping it replaced the dock with another page mid-stream. On the full dashboard it opens in a new tab.
- Settings screens: dropdowns have a custom arrow, secondary buttons share one style, file pickers look like drop zones, number and colour fields line up in three even columns, and the OBS link names read as captions under one section title.
- Lists (tier thresholds, filtered words, allowed voices) are typed as plain comma-separated text, e.g. `1, 50, 200, 500`, instead of JSON. JSON is still accepted, and so is ₹ in tier amounts. Every settings form confirms with a "… saved." message.
- Soundboard: a **▶ Preview** button replaces the browser's grey audio player, **Upload audio** is a gradient call to action, and **Delete** is a red outline.
- Goals: even spacing inside each goal card and a quieter outlined **Delete**.
- Design Studio: alert previews are drawn at the real OBS size and scaled down, so line breaks match what viewers see, and the alert-width setting now visibly changes the preview. The preview grid has no empty gaps.
- **Listen to sample** (TTS) replays the sample it already made when the voice and text haven't changed.
- Phones: Soundboard entries are stacked cards, **At a glance** shows all four columns, and the tab strip fades at its edge and scrolls the current tab into view.
- Paytm page: helper text is dimmed under its label, the POST endpoint is shown as a code chip, and "last received" times are in IST (e.g. `11 Oct 2026, 5:56 pm`) whatever the PC's region setting.

**Fonts**

- Inter (variable font, SIL Open Font License 1.1) is bundled in `acepressure/static/fonts/`, with its licence in `LICENSE-Inter.txt`. Nothing is loaded from the internet. Before, Windows PCs fell back to Segoe UI.

## 6. Soundboard clips go live, and the test alert plays your sound

- Uploading a clip to an empty soundboard slot now switches the slot on, as the **Seed Indian meme starter catalog** message says. Before, the slot stayed off, so the **Soundboard** box never appeared on your tip page. Replacing the clip on a slot you switched off keeps it off. The upload message says whether the clip is on your tip page.
- **Send test alert** plays the sound a real tip gets when the viewer picks nothing: the first sound in **Viewer sound choices**. Before, it always played the chime, so a meme you set as your tip sound seemed not to work.

## Upgrading from 1.5.8

- No data migration. New settings (`media_labels`, `media_auto_fixed`) are additive; sounds uploaded before 1.5.9 show their stored name until re-uploaded.
- Auto-fix needs FFmpeg: run `Install_Media_Tools.bat` once.
- Compare your OBS Browser Source sizes with the list on **Admin → OBS** (width × height to enter in OBS).
- Soundboard slots that already had a clip before 1.5.9 stay as they were. To show one on your tip page, open **Soundboard → Edit**, tick **Enabled on public page** and save.

## Tests

- 503 automated tests pass (428 in 1.5.8). New tests cover upload repair and length checks, original filenames, the Sounds/media page, Windows launchers and line endings, upload size limits, the release package, soundboard clips going live on upload and the test alert's sound.
- Checked in a real browser before release: settings saved through the admin forms, every OBS widget measured at its Browser Source size, a test alert timed from click to screen, the bundled font loading, and a fresh install started from the extracted zip.

---

# 1.5.8 — Fix_Audio.bat + explicit Male 1 / Female 1 voice labels with 👨 👩 emojis

Two separate user-reported issues bundled into one release:

## 1. Voice labels: 👨 Male 1, 👩 Female 1 (was: ♂ Male voice 1)

Direct response to *"for the tts voice you have written voice 1 ,2,3,4 write male and female as well — and add male and female emojis — and for male 2 voices are there so there right male 1, male 2."*

**Why admins were seeing generic "Voice 1, 2, 3, 4"**: before 1.5.4, `voice_genders` wasn't persisted. Admins who upgraded without re-saving their TTS voices had an empty `voice_genders` map, which dropped every voice into the "any" bucket. The client-side name-token regex was *supposed* to catch it as a fallback — but `\bAva\b` doesn't match 'Ava' in 'en-US-**Ava**MultilingualNeural' because 'a' and 'M' are both word characters (no `\b` between them).

**Fixes:**
- **Server-side backfill** (`acepressure/app.py`): `/api/public/config` now derives `voice_genders` from voice IDs via name-token regex when the stored map is empty or incomplete. Admins upgrading from <1.5.4 get the correct Male/Female grouping without needing to re-save voices.
- **Regex pattern upgraded** (both `app.py` and `public.js`): changed from `\bName\b` to `(^|[^A-Za-z])Name(?![a-z])` — matches CamelCase boundaries (`AvaMultilingual` ✓) while still rejecting partial matches (`Avatar` ✗).
- **Expanded name-token lists**: added more Indian/multilingual voices (Ananya, Kavya, Pooja, Priya, Lekha, Shruti, Pallavi, Heera, Aditi, Alonso, Rehaan, Arnav, Ravi, etc.) so Edge TTS catalog hits don't fall through to "any".
- **Shorter labels**: "Male voice 1" → "Male 1", "Female voice 1" → "Female 1" (user asked for terseness).
- **Emoji badges**: ♂ → 👨, ♀ → 👩, ◉ → 🎙️. Readable at a glance on any OS; older symbols read as generic text.

The gender-coloured left border stays blue/pink/grey so the group is still visually distinct even without the emoji.

## 2. Fix_Audio.bat: one-click drag-and-drop re-encoder for broken MP3s

Direct response to *"i have downlaoded it from myinstant.com — can you make a bat file which can fix the broken mp3?"*

Many free-sound sites (myinstants.com, orangefreesounds, zedge, etc.) serve MP3s with non-standard encoding: variable bitrate, odd sample rates (22050 Hz, 11025 Hz), ID3v2 with embedded cover art, or container/codec mismatches. They pass casual "is this an MP3?" checks but either refuse to play in Chromium's HTML5 audio or play unreliably. **Fix_Audio.bat** re-encodes any such file to a browser-safe standard MP3 with one drag-and-drop.

**New: [Fix_Audio.bat](Fix_Audio.bat) at the repo root**
- **Drag one or more MP3 / OGG / WAV files onto it.** For each file, outputs `<name>_fixed.mp3` next to the original.
- The fixed file is guaranteed browser-compatible: **MPEG Layer 3** (the only MP3 variant browsers decode), **128 kbps constant bitrate**, **48 kHz stereo**, **all metadata and cover art stripped**, **trimmed to 20 s** (matches the alert sound cap).
- Uses bundled `tools\bin\ffmpeg.exe` if present, otherwise falls back to PATH. If neither works, points the user at Install_Media_Tools.bat.
- Shows a help banner when invoked with no files (user double-clicks instead of drag).
- Processes files one at a time with per-file status (OK / FAIL / SKIP) and a summary count.

**Admin UI integration**
- When Admin → Sounds/media detects any BROKEN sounds in the table, the panel now shows a yellow banner: "**N broken sounds detected.** To fix: drag the ORIGINAL file onto `Fix_Audio.bat` in your AcePressure folder. That outputs a browser-safe `*_fixed.mp3` you can re-upload below."
- The ffprobe-fail server error at upload time now ends with "Fix: drag the file onto Fix_Audio.bat and upload the _fixed.mp3." — so admins see the fix path right next to the problem.

## Tests (10 new, 428 total)
- `TestFixAudioBat` (5): file exists at repo root; contains all required ffmpeg flags (libmp3lame, 128k, 48000 sample rate, -ac 2 stereo, -map_metadata -1 to strip metadata); outputs *_fixed.mp3; caps at 20 s; falls back to PATH when bundled ffmpeg missing; mentions Install_Media_Tools.bat on failure; admin.js and video.py both surface the fix path.
- `TestFriendlyVoicePicker` additions (5): `test_public_config_backfills_voice_genders_when_missing` (simulate pre-1.5.4 settings → verify Male/Female populated); `test_guess_gender_from_voice_id_covers_edge_catalog`; `test_public_config_respects_explicit_voice_genders_over_backfill`; `test_public_js_voice_labels_use_numbering`; updated `test_public_js_renders_friendly_labels_not_raw_ids` to assert new emoji + "Male"/"Female" (no "voice") wording.

## Recovery workflow (what to do if you have broken sounds from before 1.5.6)
1. Upgrade to 1.5.8.
2. Admin → Sounds/media — look for red BROKEN badges.
3. Find the ORIGINAL downloads on your computer (the ones from myinstants.com etc.).
4. Drag them onto `Fix_Audio.bat` in the AcePressure folder.
5. Upload the `*_fixed.mp3` outputs via Admin → Sounds/media → Upload alert sound.
6. Click Delete on the old broken rows.

**No breaking changes.** Fix_Audio.bat is a pure utility — doesn't touch your data or settings. The voice-label changes are display-only; stored voice IDs and the `/api/public/tips` payload format are unchanged.

# 1.5.7 — Sounds manager (list + preview + delete legacy broken uploads) + codec-matches-extension strict validation

Direct response to "Preview failed: This audio format is not supported by your browser. Re-export as standard MP3 (constant bitrate Layer 3) or WAV. got this error while previewed the audio on tipping page".

That error (added in 1.5.6) correctly refuses to play a broken file — but didn't actually SOLVE the problem for admins who had already uploaded broken MP3s under 1.5.3-1.5.5 (where the magic-byte check accepted them). There was no UI to see WHICH sound was broken, let alone delete it. 1.5.7 adds that UI.

**New: Admin → Sounds/media → Uploaded sounds table (top of panel)**
- Lists every uploaded sound (chime/pulse/none are built-in synthetic, filtered out).
- Each row shows: filename, ffprobe-detected codec (MP3 / VORBIS / OPUS / PCM_S16LE / etc.), duration, and a **green "OK" or red "BROKEN" badge** with the specific reason if broken.
- **▶ Preview button** per row — plays via `/media/<name>` directly, so the admin can hear the exact same file the viewer would get.
- **Delete button** — removes the file from disk AND from `settings.sounds` AND reverts `visuals.alert_sound` to 'viewer' if it was pointing at the deleted file (prevents orphaned "Choose an uploaded sound" errors in Design Studio).
- **Refresh button** re-scans after any change.
- New backend endpoints: `GET /api/admin/sounds/list` (ffprobe scan of every uploaded sound), `DELETE /api/admin/sounds/<name>` (atomic file + allowlist removal).

**New: codec-matches-extension strict validation**
- 1.5.6's `probe_audio_file()` checked that ffprobe could decode the audio. 1.5.7 adds a stricter check: the detected codec must match the upload extension — a file uploaded as `.mp3` must actually contain MP3 audio (codec_name=`mp3`), not AAC or Opus or MPEG Layer 2.
- Catches the specific case where someone drags an AAC file into a renamer and calls it `.mp3` — ffprobe says "yes this is valid audio" but Chromium's HTML5 audio player refuses because the container/codec combination is invalid.
- New allowlist in [acepressure/video.py](acepressure/video.py) `_ALLOWED_CODECS`: `.mp3→{mp3}`, `.ogg→{vorbis,opus}`, `.wav→{pcm_s16le,pcm_s24le,pcm_s32le,pcm_u8,pcm_f32le,pcm_f64le,pcm_alaw,pcm_mulaw}`.
- Error message when mismatched: "File is AAC audio but was uploaded as MP3. Re-export as actual MP3 or rename the file to the correct extension."

**Tests (14 new, 418 total)**
- `TestSoundsManagerAdmin` (9): list endpoint shape; shows uploaded sounds with correct codec/duration/playable; flags broken files in the allowlist; delete removes file + allowlist entry; delete reverts alert_sound to 'viewer'; builtin sounds can't be deleted; bad filenames rejected; both endpoints require admin auth.
- `TestCodecMatchesExtension` (5): AAC renamed to .mp3 rejected with specific error; real MP3/OGG/WAV still accepted; probe_audio_file direct unit test for mismatch.

**For admins hitting the 1.5.6 preview error:** go to Admin → Sounds/media, look for red "BROKEN" badges in the Uploaded sounds table, click Delete on each. Then upload a fresh file (the 1.5.7 validator will tell you immediately if something's wrong, with the specific codec that was detected).

**No breaking changes.** Existing valid MP3/OGG/WAV uploads keep working. Only the stricter codec check adds new rejection paths — and only for files that wouldn't play in browsers anyway.

---

# 1.5.6 — Audio uploads: ffprobe stream validation catches "no supported source" MP3/OGG before they ever reach the browser

Direct response to "upload a mp3 file and it's saying failed to load because no supported source was found when on the tipping page i did preview sound on uploaded alert sound".

Root cause: v1.5.3 validated uploaded audio by **magic bytes only** (`ID3` tag OR `0xFF 0xEx` MPEG sync, `OggS` for OGG). That accepts files that look like audio but aren't actually decodable:
- MP3 files with just an ID3 tag and no audio frames (common in cover-art-stripped files)
- AAC-ADTS files renamed to `.mp3` (sync bytes identical to MPEG)
- MPEG Layer 1 / Layer 2 files (browsers only decode Layer 3)
- Corrupt or truncated MP3/OGG

All three pass the magic check, land on disk, and then produce the user's exact error — `Failed to load because no supported source was found` — when the HTMLMediaElement tries to decode them.

**Server-side fix: ffprobe-backed validation**
- New helper [acepressure/video.py](acepressure/video.py) `probe_audio_file(content, extension)` — uses `ffprobe` to confirm the uploaded audio file has at least one real decodable audio stream (not just metadata). Returns `{'valid': bool|None, 'codec': ..., 'duration_ms': ..., 'reason': ...}`.
- `valid: None` is returned when ffprobe isn't installed on the host, letting the caller fall back to the current magic-byte check. This keeps zero-ffmpeg installs working.
- `valid: False` with a specific `reason` is returned when the file passes magic but can't decode — the admin sees exactly WHY ("File has no audio stream (ID3 tag or metadata only).", "MPEG Layer 2 audio (mp2) is not supported by browsers. Re-export as standard MP3 (Layer 3) or OGG.", "ffprobe could not decode this file as audio.").
- Wired into all three audio upload paths: `/api/admin/media` (alert sound), `/api/admin/soundboard/<id>/media` (soundboard clip), `/api/admin/alert-bundle` (bundle audio).

**Client-side fix: friendly preview error**
- [acepressure/static/public.js](acepressure/static/public.js) `#preview-sound` click handler used to surface the browser's cryptic DOMException message verbatim. 1.5.6 adds an `error` event listener on the `Audio` element and maps `MediaError.code` (1-4) to actionable text — code 4 (`MEDIA_ERR_SRC_NOT_SUPPORTED`) now reads **"This audio format is not supported by your browser. Re-export as standard MP3 (constant bitrate Layer 3) or WAV."** instead of the raw browser error.

**Tests updated to use REAL audio**
- The 1.5.2 / 1.5.3 tests synthesized fake MP3/OGG from frame-header bytes. These passed the old magic-byte check but ffprobe correctly rejects them (because they're not actually decodable). Updated all MP3/OGG upload tests to use real ffmpeg-generated audio via two new fixtures `make_real_mp3()` and `make_real_ogg()` (with graceful fallback across libvorbis / vorbis-experimental / libopus so the tests work on any ffmpeg build).

**New tests (6, 409 total):**
- `TestAudioValidationFfprobe::test_rejects_id3_tag_only_mp3` — the exact bug class the user hit.
- `test_rejects_ogg_container_without_vorbis_stream`.
- `test_accepts_real_mp3_and_serves_decodable` — round-trip real MP3 → `/media/` → confirm ffmpeg can decode the served bytes (proxy for browser decode).
- `test_range_requests_work_for_mp3` — confirm browsers can seek (206 Partial Content).
- `test_probe_audio_file_fallback_when_ffprobe_missing` — ffmpeg-less installs still work.
- `test_client_side_error_handler_in_public_js` — the new friendly error wiring exists.

**No breaking changes** for admins whose uploaded sounds are already valid. The validator is strictly tighter — any file that was decodable before is still accepted. Only previously-silent-corrupt files are now caught at upload time with a useful error, instead of showing up as "no supported source" on the tipping page later.

**Requires:** ffmpeg installed. The 1.5.5 release already recommended `Install_Media_Tools.bat` for video+audio bundles; 1.5.6 extends the recommendation to all audio uploads. If ffmpeg isn't installed, upload validation falls back to the 1.5.3 magic-byte check (same behavior as before 1.5.6).

---

# 1.5.5 — OBS alert bundle (GIF/MP4 + audio in ONE upload) + MP4 video audio preserved + overlay double-audio gate

Direct response to "for the obs alert is there an option to upload a gif or mp4 with the audio or not if not please add and test it" and "have you tested everything if not please do please test every functionality in this zip file before giving it to me, the mp3 format is working or not".

Shipped under a 3-parallel-agent audit workflow that mapped every upload path, the overlay audio-mixing path, and a 21-area test matrix.

**New: single-step alert bundle upload**
- New endpoint [acepressure/visuals.py](acepressure/visuals.py) `POST /api/admin/alert-bundle` — one multipart POST with up to two files: `visual` (PNG/WebP/GIF/MP4/WebM, required) + `audio` (WAV/MP3/OGG, optional). Both get routed through the SAME validators as the existing single-asset endpoints, then atomically persisted into `settings.visuals.alert_image` + `settings.visuals.alert_sound` in a single transaction (no half-updated state on partial failure).
- New Admin → **Sounds/media** → **"Upload alert bundle (video+sound in one step)"** form with two file inputs — admin picks a visual and (optionally) a matching audio file, one click to save both.
- Smart audio mixing (no manual flag needed): if the admin uploads an MP4 that already has its own audio AND doesn't attach a separate audio file, the bundle endpoint probes the video via `ffprobe`, keeps the embedded audio, and sets a new `visuals.alert_video_has_audio=True` flag — the OBS overlay reads this and skips the separate chime so there's no double audio. If the admin DOES upload a separate audio file alongside an MP4-with-audio, the video audio is stripped (explicit upload wins) and only the uploaded sound plays.

**New: MP4 video audio preserved (opt-in)**
- [acepressure/video.py](acepressure/video.py) `transcode(content, extension, keep_audio=False)` — added `keep_audio` parameter. Default is still **False** so the existing `/api/admin/visual-assets` endpoint keeps producing silent output (backward compat: existing admins' alert images don't suddenly gain sound). The alert-bundle endpoint explicitly passes `keep_audio=True` when there's no separate audio file.
- When keep_audio=True: ffmpeg args switch from `-an` to `-map 0:a:0? -c:a libopus -b:a 96k -ac 2 -ar 48000` (Opus is the standard WebM audio codec; the trailing `?` on `0:a:0?` makes it OK if the input happens to have no audio).
- Added `probe_has_audio(content, extension)` helper so the bundle endpoint can detect whether to use embedded audio or require a separate upload.

**New: overlay audio gate (prevents double audio)**
- [acepressure/static/overlay.js](acepressure/static/overlay.js) `runQueue()` — before playing the separate chime, checks if the alert visual is a `<video>` AND the admin flagged `alert_video_has_audio=true`. If so, unmutes the video and skips the chime; if the browser blocks autoplay-with-sound, falls back to the separate chime (defensive — `video.muted` stays true on block).
- [acepressure/static/visuals.js](acepressure/static/visuals.js) `visualImage()` — regex widened from `endsWith('.webm')` to `/\.(mp4|webm|mov|m4v)$/i` so MP4/MOV also render as `<video>` (not broken `<img>`) if admins put them in /media via other paths.

**Validator additions:**
- [acepressure/visuals.py](acepressure/visuals.py) `DEFAULT_VISUALS` now includes `alert_video_has_audio=False`; `validate_visuals()` rejects anything other than a bool for this field.

**Comprehensive sanity-sweep tests added (TestComprehensiveSmoke):**
- Public config shape (14 required keys)
- Public soundboard + top endpoints
- Health endpoint
- Root tipping page renders with soundboard + voice sections
- All four overlay types render (alert/goal/recent/top3)
- Admin login+logout+auth gating
- Bridge token: missing + wrong both 401
- Regression check: 1.5.3 MP3 alert sound still works in 1.5.5
- Regression check: 1.5.2 soundboard MP3 upload still works in 1.5.5

**Full test matrix (27 new, 398 total, ~383 run on this box + 15 release-integrity + 0 skip when ffmpeg installed):**
- `TestAlertBundle` (7): missing visual rejected; bad extension rejected; PNG+MP3 happy path round-trip; GIF+MP3 happy path; oversized audio rejected; bad audio magic rejected; image-only (no audio) succeeds; admin auth required.
- `TestVideoTranscode` (4): default is silent (backward compat); keep_audio=True preserves audio; keep_audio=True handles silent input via `-map 0:a:0?`; `probe_has_audio()` detects audio tracks correctly.
- `TestOverlayVideoAudioGate` (5): overlay.js has gate; visuals.js recognises MP4/MOV; admin.js has bundle form; DEFAULT_VISUALS carries the new flag; validator rejects non-bool.
- `TestComprehensiveSmoke` (11): the 11 sanity-sweep tests above.

**Downstream verified unchanged (no code change needed):**
- Soundboard pipeline, viewer sound picker, bridge, backups, supporter identity, tier badge, friendly voice picker all untouched.
- Existing `/api/admin/visual-assets` behavior preserved (still produces silent output).

**No breaking changes.** Existing WAV alert sounds, existing silent WebM alert visuals, existing admin-configured sounds — all keep working. Upgrade is a straight file-replace.

---

# 1.5.4 — Public tip page: friendly voice labels (Male / Female voice N) with gender icons + per-card speaker preview

Direct response to "in the tipping page it's showing the users the whole voice name it should be mail voice 1,2 and same female voice 1,2 and and audio or sound symbol near to it male voice or a male symbol and same with female".

The public tip page's voice picker used to render raw technical IDs (e.g. "Microsoft AvaMultilingualNeural Online (Natural) - English (United States)"). Tippers don't care about the voice's full name — they want to know "is this a male or female voice, and can I hear it before I pay?". 1.5.4 rebuilds the picker around that.

**New voice picker UX (public tip page):**
- Cards now show `♂ Male voice 1`, `♂ Male voice 2`, `♀ Female voice 1`, `♀ Female voice 2`, `◉ Voice 1` (for Piper / unknown-gender voices). The N numbering is stable within each gender group and tracks the admin's own voice order.
- Each card has a coloured left border (blue = male, pink = female, grey = neutral) and a tinted circular gender icon badge.
- Each card has its own **🔊 preview speaker** on the right — click it to hear THAT voice without first picking it. Reuses the existing `/api/public/voice-preview` endpoint on server engines; browser engine uses `speechSynthesis` directly.
- Tooltip (`title` + `aria-label`) still carries the full real voice name for screen readers and curious hover-ers.

**Backend changes:**
- [acepressure/tts_service.py](acepressure/tts_service.py) `/api/admin/tts/configure` now also persists a `voice_genders` map (`{voice_id: 'Male'|'Female'|'Any'}`) alongside the existing `voice_labels` and `voice_locales` maps. Pulled from each catalog entry's `gender` field (Edge/Azure populate it; Piper falls back to `'Any'`).
- [acepressure/app.py](acepressure/app.py) `/api/public/config` exposes `voice_genders` to the public page so it can group without duplicating catalog logic.

**Frontend changes:**
- [acepressure/static/public.js](acepressure/static/public.js) rewrites `buildVoices()` with gender grouping + per-group numbering + icon + speaker preview. Adds a client-side name-token fallback (`VOICE_MALE_TOKENS` / `VOICE_FEMALE_TOKENS` regex) so admins who skipped the Voice Studio (set `tts_engine='browser'` or typed raw IDs into the TTS settings JSON array) still get correct grouping — covers all 17 voices from the user's Edge TTS list.
- [acepressure/static/premium.css](acepressure/static/premium.css) ~65 lines of new rules: flex layout for the card, tinted gender icon badges, hover-scaling speaker, gender-coloured left borders.

**Fallback behaviour (no backend change needed for existing installs):**
- Admins who upgraded without re-running Voice Studio: `voice_genders` is empty, but the client-side regex covers the Edge/Azure/SAPI name tokens anyway — Male voice / Female voice labels still appear correctly.
- Any truly unknown voice (not in the token regex, not in `voice_genders`) lands in the neutral `◉ Voice` group — still friendlier than the raw ID.

**Preserved behaviour:**
- The hidden `<select name="voice">` still holds the FULL voice ID — the backend's TTS lookup is unchanged. Only the DISPLAY text changed.
- The global `#preview-voice` button still works and now dispatches via the per-card speaker handler.
- `voice_labels` tooltip fallback preserved — hover any card to see the real voice name.
- Keyboard/aria: cards are still `aria-pressed`; speaker buttons have `role=button` + `aria-label`.

**Tests (8 new, 370 total; 354 run + 15 release-integrity + 1 skip)**
- `TestFriendlyVoicePicker`: public config exposes `voice_genders`; configure handler persists it; defaults to `'Any'` when catalog has no gender; public.js has the `voiceGender()` helper + token regexes covering all 17 of the user's Edge voices; buttons render friendly labels with ♂/♀/◉ symbols; each card has `voice-preview-spk` with `stopPropagation()`; premium.css has `.voice-male`/`.voice-female`/`.voice-any`/`.voice-gender-icon`/`.voice-preview-spk`/`.voice-friendly-name` + flex layout on `.voice-card`.

**No breaking changes.** The real voice ID is still what the backend synthesizes; the hidden form field is unchanged. Upgrade is a straight file-replace. For best grouping, re-run Admin → Voice Studio → Use selected voices (populates `voice_genders`); otherwise the client-side regex handles it.

---

# 1.5.3 — Alert sound upload: MP3 / OGG support (same magic-byte validator)

Direct response to "upload alert sound is still asking for PCM WAV files". v1.5.2 fixed the SOUNDBOARD upload but there's a second, separate audio-upload path — **Admin → Media → Upload alert sound** (the chime that plays on every new tip in the OBS overlay) — which was still rejecting MP3/OGG. 1.5.3 ports the 1.5.2 magic-byte validator to that endpoint so every audio-upload surface in the app now accepts the same formats.

**Audit (via workflow) found exactly ONE broken endpoint:**
- `/api/admin/media` with `kind='sound'` at [acepressure/app.py:382](acepressure/app.py#L382) — the alert-sound upload. (The avatar branch `kind='avatar'` was untouched.)
- Plus a downstream regex at [acepressure/visuals.py:20](acepressure/visuals.py#L20) that would reject the uploaded `.mp3`/`.ogg` filename when the admin tried to save a Design Studio layout using it (`'Choose an uploaded sound.'`).
- All three visual-asset / soundboard endpoints and the `/media/<name>` serving route were already correct.

**Changes in [acepressure/app.py](acepressure/app.py)**
- `upload_media()` `kind='sound'` branch replaced the WAV-only wave.open check with the same magic-byte branching used by `admin_soundboard_upload`: `RIFF`/`WAVE` → wave.open (PCM only, ≤20 s), `ID3` or `0xFF 0xEx` MPEG frame sync → `_mp3_duration_ms` (≤20 s), `OggS` → `_ogg_vorbis_duration_ms` (≤20 s). Written file suffix follows the detected format, not the client-supplied filename.
- **Duration cap kept at 20 s across all three formats** (not 30 s like the soundboard) — this matches the overlay's existing 21000 ms `playAudio` watchdog, so a longer clip would be cut off anyway.

**Changes in [acepressure/visuals.py](acepressure/visuals.py)**
- `validate_visuals()` `alert_sound` allowlist regex widened from `[A-Za-z0-9_-]+\.wav` → `[A-Za-z0-9_-]+\.(wav|mp3|ogg)` so Design Studio can now save a `.mp3`/`.ogg` as the per-tip alert sound. All other extensions still rejected.

**Changes in [acepressure/static/admin.js](acepressure/static/admin.js)**
- Media panel's alert-sound input: `accept` widened `.wav` → `.wav,.mp3,.ogg,audio/wav,audio/mpeg,audio/ogg` (file picker now shows your MP3s instead of greying them out).
- Help text updated `PCM WAV · 20 seconds maximum` → `WAV / MP3 / OGG · 20 seconds maximum`.

**Downstream verified unchanged (audit confirmed no code change needed):**
- `/media/<name>` already allowed `mp3|ogg` since 1.5.2.
- OBS overlay plays `.mp3`/`.ogg` natively via HTML5 `<audio>` (`overlay.js` path untouched).
- Viewer sound picker in `domain.py` validates by exact-string match against `settings.sounds`, so any filename admin uploaded is accepted.
- Soundboard, visual-assets, and avatar upload paths all unaffected.

**Tests (13 new, 362 total; 346 run + 15 release-integrity + 1 skip)**
- `TestAlertSoundUpload` (8): rejects garbage, accepts WAV / MP3 / OGG, rejects 25 s WAV (still enforces cap), rejects filename lie about MP3, serves uploaded MP3 via `/media/`, end-to-end "upload MP3 → set as alert_sound in visuals → round-trip via GET".
- `TestVisualsValidator` (5 new): alert_sound accepts `.wav`/`.mp3`/`.ogg` filenames when the file exists; rejects `.exe`; rejects missing files.

**No breaking changes.** Existing `.wav` alert sounds continue to work. The upgrade is a straight file-replace.

---

# 1.5.2 — Soundboard: native MP3 and OGG upload support

Direct response to "the files i have they are in mp3 and OGG file". The 1.5.0 soundboard validator only accepted PCM WAV; most meme/SFX libraries on the internet ship MP3 or OGG. This release accepts all three natively — no local conversion step needed.

**Changes in [acepressure/app.py](acepressure/app.py)**
- `admin_soundboard_upload()` replaced the WAV-only validator with **magic-byte detection**: inspects the first bytes of the uploaded file rather than trusting the extension. Accepts PCM WAV (`RIFF`…`WAVE`), MP3 (`ID3` tag OR `0xFF 0xEx` MPEG frame sync), and OGG (`OggS` + Vorbis header). Rejects anything else, even if the file is named `.mp3`.
- New helpers `_mp3_duration_ms(data)` (parses ID3v2 synchsafe size + the first MPEG frame header with bitrate/sample tables for MPEG1 Layer3 + MPEG2 Layer3) and `_ogg_vorbis_duration_ms(data)` (reads last `OggS` page's `granule_position` ÷ first identification header's `sample_rate`).
- WAV keeps the 20 s cap for compatibility. MP3/OGG upload cap raised to **30 s** (reflects typical soundboard clip lengths). 8 MB file-size cap unchanged.

**Changes in [acepressure/static/admin.js](acepressure/static/admin.js)**
- Soundboard upload button `accept` list widened from `.wav` to `.wav,.mp3,.ogg,audio/wav,audio/mpeg,audio/ogg` — the OS file picker now shows your MP3/OGG files instead of greying them out.
- Panel helper text updated from "WAV upload (PCM, ≤ 20 s, ≤ 8 MB)" to "audio upload (WAV/MP3/OGG, ≤ 30 s, ≤ 8 MB)".

**Note:** `/media/<name>` already allowed `.mp3`/`.ogg` since 1.5.0 (regex: `(wav|jpg|png|webp|gif|webm|mp3|ogg)`), so playback was never the blocker — only validation was. OBS browser-source overlay plays MP3/OGG natively via the HTML5 `<audio>` tag that fires on each tip.

**Tests (4 new, 349 total passing)**
- `test_admin_upload_accepts_mp3` — synthesises a minimal MPEG1 Layer3 128 kbps CBR stream with ID3v2 header, 100 frames (~2.6 s), and confirms it's accepted + served under `/media/*.mp3`.
- `test_admin_upload_accepts_ogg` — synthesises a minimal `OggS` page + `\x01vorbis` identification header and confirms acceptance.
- `test_admin_upload_rejects_wrong_extension_without_magic` — upload a 500-byte NUL blob named `fake.mp3`; server rejects because magic bytes don't match. Confirms we trust CONTENT, not FILENAME.
- `test_admin_upload_rejects_garbage` — plain text file rejected regardless of extension.

**No breaking changes.** Existing WAV sounds continue to work. Upgrade is a straight file-replace.

---

# 1.5.1 — Premium polish v2: hero aura, tier badge, celebration screen, skeleton loaders

Focused end-user polish pass on the public tip page in response to "it should look like a premium website to the end user." All visual, no breaking changes.

**New in [acepressure/static/premium.css](acepressure/static/premium.css) (+180 lines)**
- **SVG noise/grain overlay** (`.tip-focused::before`) fixes faint gradient banding on dark backgrounds — mix-blend-mode overlay at 8 % opacity, data-URI so no extra network request.
- **Hero avatar aura** (`.tip-focused .creator::before`) — slow 8 s pulsing radial glow (crimson → violet) behind the avatar/mark. Avatar itself gets a subtle breathing animation (`@keyframes avatar-breath`).
- **Section stagger-in** (`@keyframes section-in`) — creator / tip-card / supporters sections fade + rise in sequence (0 / 80 ms / 160 ms) on load.
- **Micro-interactions** — amount preset chips, voice/sound cards, soundboard tiles, and primary CTA all compress on `:active` (translateY + scale). Mobile users feel the press.
- **Tier badge** (`.tier-badge`) — a live chip under the amount input that lights up as the amount grows: Starter → Supporter → Big fan → Legend → Icon. Tier 3 (Legend+) uses the full gradient fill + animated pulse glow. Respects admin-defined tier thresholds (surfaced in `/api/public/config.tiers` — new field).
- **Skeleton loaders** (`.skeleton-row` / `.skeleton-bar`) — Top supporters section now shows 3 shimmering placeholder rows while `/api/public/top` loads. No more blank "Be the first to support" flash.
- **Celebration success screen** (`.celebration`) — replaces the plain "THANK YOU" card after a VERIFIED tip. Animated 🎉 ring with a pop-in bounce, gradient heading, dashed receipt card with the tip ID (copy to clipboard), and "Send another tip" primary CTA. Full-viewport confetti burst (140 particles via existing `window.aceConfetti`) fires on reveal.

**New in [acepressure/static/public.js](acepressure/static/public.js)**
- Skeleton rows injected into `#top` at the very start of `init()` so the slot never blanks.
- `renderTierBadge()` wired to amount input, chip clicks, and page load — recomputes the tier label + icon + visual class from `config.tiers`.
- `renderCelebration(box, d)` builds the new post-payment screen with copy-receipt + send-another-tip buttons.
- Empty Top supporters now shows a friendly "Be the first to support the stream." instead of nothing.

**New in [acepressure/app.py](acepressure/app.py)**
- `/api/public/config` now also returns `tiers` so the public page can render the tier badge against the admin's own thresholds.

**Tests (4 new, 349 total passing)**
- `TestPremiumPolish` covers: public config exposes `tiers`, premium.css contains all v1.5.1 selectors (`.tier-badge`, `.celebration`, `.celebrate-ring`, `.skeleton-row`, `.skeleton-bar`), premium.css contains all 6 new keyframe blocks (`hero-aura`, `avatar-breath`, `section-in`, `tier-pulse`, `celebrate-pop`, `skeleton-shimmer`), public.js references `renderTierBadge` / `renderCelebration` / `skeleton-row` / `window.aceConfetti`.
- All 341 pre-existing tests still pass.
- CSS brace balance verified (230 rules).

**No breaking changes.** Pure polish layer on top of 1.5.0. Upgrade is a straight file-replace.

---

# 1.5.0 — Soundboard: streamer-curated meme/SFX gallery for tippers

Big one. Tippers now browse a gallery of your sounds on the public tip page and pick ONE to play on OBS when their tip is confirmed — exactly the StreamTipz pattern you asked for, but with the gaps I spotted in that reference closed: search, category pills, per-sound minimum tip badges, favorites, preview-play, locked/unlocked state tied to tip amount, premium glass tiles.

**What tippers see** ([acepressure/templates/public.html](acepressure/templates/public.html), [acepressure/static/public.js](acepressure/static/public.js))
- New `<section id="soundboard-section">` under the voice picker (hidden when the catalog is empty).
- Instant-search input + category pills (All, ★ Favorites, Hindi Memes, SFX, Reactions, Sports, Patriotic, General…).
- Live tier meter: a progress bar + "Your ₹X tip unlocks N of M sounds" that updates as the amount changes.
- Responsive grid (auto-fill 140 px minimum; 2 cols on mobile, 3-4 on desktop).
- Each tile: emoji icon, name, per-sound minimum tip badge, ☆ favorite toggle, ▶ preview button. Locked tiles grey out with a hover tooltip telling tippers which amount unlocks them. The selected tile gets a gold-ringed glass-glow treatment and plays an animated sweep when previewing.
- Favorites persist in `localStorage` per browser. Favorites tab filters to your saved ones.

**What the streamer sees** ([acepressure/static/admin.js](acepressure/static/admin.js))
- New Admin → Soundboard tab (between Sounds/media and Stream sessions).
- CRUD table: emoji, name, category, min ₹, order, enabled, inline audio preview (`<audio controls>`), upload / replace WAV, edit modal, delete (with safe tip-unlink).
- One-click **Seed Indian meme starter catalog** button adds 20 well-known Hindi meme templates (Thug Life, Chai Peelo, Babu Bhaiya, 440 Volt Ka Jhatka, Rasode Mein Kaun Tha, Pawri Ho Rahi Hai, Binod, Papa Kehte Hain, Ye Chemical Hai, Hera Pheri Laughter, Mauka Mauka, Hum Honge Kaamyab, Vine Boom, Air Horn, Cash Register, Victory Fanfare, Clap, Game Over, Beta Tumse Na Ho Payega, Dhoondho) — each disabled by default so you upload your own royalty-free audio before they appear on the tip page. Idempotent: re-running skips names you already have.

**Backend** ([acepressure/migrations/007_soundboards.sql](acepressure/migrations/007_soundboards.sql), [acepressure/domain.py](acepressure/domain.py), [acepressure/app.py](acepressure/app.py))
- New `soundboards` table: `id, name, emoji, media_filename, category, min_paise, display_order, enabled, duration_ms, created`. Indexes on `(enabled, display_order)` and `category`.
- New `tips.soundboard_id` column (nullable, references `soundboards.id`). Added via `ALTER TABLE`; the migration loader in `domain.py` now splits per-statement and silently skips "duplicate column name" on re-run so additive column migrations are replay-safe.
- `Store.soundboard_list / _get / _create / _update / _set_media / _delete / _reorder / _seed` cover the full CRUD.
- `Store.create_tip` accepts `soundboard_id`, validates existence + enabled + media + amount ≥ `min_paise`, raises a friendly `Problem` with "Tip at least ₹X to play this sound." when under.
- `Store.alert` resolves `soundboard_id → media_filename` into `payload.soundboard_clip` so the overlay doesn't need DB access.
- Routes: `GET /api/public/soundboard` (enabled + media only, with `/media/<file>` URL), `GET/POST /api/admin/soundboard`, `POST /api/admin/soundboard/<id>` (update), `POST /api/admin/soundboard/<id>/media` (WAV upload: PCM, ≤ 20 s, ≤ 8 MB, same validator as the legacy sound uploader), `POST /api/admin/soundboard/reorder`, `POST /api/admin/soundboard/seed`, `DELETE /api/admin/soundboard/<id>`.
- `/media/<name>` now also allows `.mp3` and `.ogg` extensions alongside the existing `.wav/.jpg/.png/.webp/.gif/.webm`.

**OBS overlay** ([acepressure/static/overlay.js](acepressure/static/overlay.js))
- New `resolveAlertSound(visuals, p)` precedence: (1) admin's Design Studio "Separate alert audio" override wins (unchanged), (2) `p.soundboard_clip` wins over `p.sound`, (3) legacy `p.sound` fallback. Zero schema changes to `alerts.payload` (it was already JSON; we just added fields).

**Premium UI** ([acepressure/static/premium.css](acepressure/static/premium.css))
- 180 new lines of CSS for the soundboard: glass section, animated gradient-fill tier meter (mint → gold → crimson), category pills with gradient selected-state + 4 px lift on hover, grid tiles with hover-lift + crimson rim + 10 % lightness, selected state with gold ring + violet-crimson gradient fill, locked state with 40 % opacity + grayscale emoji, playing state with animated sweep, mobile breakpoint overrides.
- Keeps the existing design-token palette (`--accent`, `--accent-cool`, `--accent-mint`, `--accent-3`) so the gallery feels native to the app.

**Tests (43 new, 341 total passing)**
- `TestSoundboardSchema` (4): table + column + indexes exist; migration re-run is idempotent.
- `TestSoundboardStore` (14): create/get/list round-trips, validation (empty name, negative/huge `min_paise`), auto display_order, enabled filter, update field whitelist, missing-entry rejection, media cleanup, tip-unlink on delete, reorder, seed count + idempotency, seed entries ship disabled.
- `TestSoundboardPublicAPI` (2): disabled + no-media hidden; payload shape locked.
- `TestSoundboardAdminAPI` (8): list / create / update / delete / seed / reorder / upload (reject non-WAV + accept valid WAV) / auth gating on all 5 endpoints.
- `TestTipWithSoundboard` (9): create_tip accepts valid; rejects unknown / disabled / no-media / below-min / bad-id-format; works without a soundboard; alert payload includes `soundboard_clip` + `soundboard_id` when set; omits them otherwise.
- `TestTTSExtras` (5): transliteration preserves punctuation, is idempotent, handles mixed case within a sentence, handles empty/None input, `voice_handles_hindi` is case-insensitive.
- Smoke test (manual): booted the app in demo mode, hit `/`, `/tip/acepressure`, `/admin`, `/obs/activity`, `/health`, `/api/public/config`, `/api/public/soundboard` (empty → populated), full admin login → seed → create → upload WAV → enable → public visibility. All green.

**No breaking changes.** Upgrade is a straight file-replace over 1.4.3 — no `.env`, no DB data loss (new column is additive). Existing tips keep working; the soundboard section stays hidden until you upload and enable at least one entry.

---

# 1.4.3 — Hinglish pronunciation fix: Roman → Devanagari transliteration

**The real Hinglish fix.** In 1.3.0 we added SSML `<lang hi-IN>` tagging so Azure engaged its Hindi phoneme model for mixed-script segments. That solved it for paid Azure, but **Edge TTS wraps raw text in its own auto-generated SSML**, discarding any `<lang>` tags you try to inject. So when Edge TTS was given "GG bhai kya clutch tha" with a Hindi or Multilingual voice, it still read the Latin letters with English phonetics — "bhai" came out as "bai", "kya" as "kiya", "tha" as "the".

**The fix (this release)**: Roman Hindi tokens are now **transliterated to Devanagari BEFORE** being handed to any TTS engine, when the chosen voice can pronounce Hindi (any `hi-*` locale OR a Multilingual Neural voice). "bhai" → "भाई", "kya" → "क्या", "tha" → "था", etc. The engine then receives real Devanagari and produces authentic Hindi phonetics. ~90 commonly-code-switched Hindi words are mapped (greetings, pronouns, question words, verbs, qualities, quantifiers, time, money, gaming slang). English homographs — "do", "me", "to" — are intentionally excluded to avoid false matches in English text.

**Applied in all four engines plus the browser:**
- `acepressure/tts_service.py` — `HINGLISH_TRANSLITERATION` map, `transliterate_hinglish()`, `voice_handles_hindi()`, `maybe_transliterate()`. Called from the Azure synth path before `build_ssml()`. Updated `_voice_locale()` to accept Piper's underscore form (`hi_IN-pratham-medium` → `hi-IN`).
- `acepressure/edge_tts_service.py` — `maybe_transliterate()` called before `edge_tts.Communicate()`. Cache key bumped to `edge-v2`.
- `acepressure/piper_tts_service.py` — `maybe_transliterate()` called before `voice.synthesize()`. Cache key bumped to `piper-v2`.
- `acepressure/static/common.js` — mirror JS map and `maybeTransliterate(text, voice)`.
- `acepressure/static/overlay.js` — browser `speak()` now transliterates before `SpeechSynthesisUtterance` when the resolved voice is Hindi-capable, so browser Hindi/Multilingual voices also benefit.

**English-voice safety.** If the operator picked an English-only voice (e.g. `en-IN-NeerjaNeural`, `en-US-GuyNeural`), transliteration is skipped — pushing Devanagari into an English-only voice would make it silent or noisy, which is strictly worse than mispronunciation. The admin voice catalog continues to tag Hinglish-ready voices clearly: pick a `HINGLISH-READY` (Multilingual) or `हिंदी` tagged voice and transliteration kicks in automatically.

**Cache invalidation.** Edge, Piper and Azure cache files from 1.4.x are harmless but will be regenerated the first time each (voice, text) pair is spoken under 1.4.3 (new cache keys include the transliteration-version marker). Old files age out of the 24h lazy cleanup window.

**New tests (12).** `TestTransliteration` in `tests/test_full_release_check.py` covers the empty/English/single-word/sentence paths, case-insensitive matching, word boundary respect (`bhaiya` doesn't match `bhai` first), locale handling (Piper underscore form, Multilingual detection), and the English-voice skip. Plus one new `TestVoiceLocale` test for the Piper underscore form. 297+ tests pass locally; no behaviour change for pure-English messages.

**No breaking changes.** Upgrade is a straight file-replace over 1.4.2 — no `.env`, no DB changes.

---

# 1.4.2 — Verified release: 285-test full-coverage run + minor .bat consistency fixes

**Test coverage pass (0 failures)**
- Added `tests/test_full_release_check.py` with 144 new tests covering the 1.3.0, 1.4.0 and 1.4.1 features: Hinglish detection (`has_devanagari`, `hinglish_score`, `is_hinglish`), SSML `build_ssml` wrapping logic, voice-locale derivation, mimetype dispatch, engine catalog/synthesize routing for all 4 server engines, admin settings whitelist (all 6 engines now accepted), Azure defensive paths, Edge TTS catalog filtering and cache behavior, Piper not-installed / missing-model / metadata-parse paths, domain primitives (money / clean), store defaults and backup integrity, visuals validator, receipt parser (fail-closed / live-sender rejection / example-credit-v1 regex), Paytm amount & event parsing, security headers (CSP / X-Content-Type-Options / Cache-Control), overlay lifecycle, package integrity (VERSION ↔ CHANGELOG ↔ README consistency; LICENSE presence; manifest SHA-256 round-trip), template integrity (all public-facing templates load premium.css + premium.js), admin dashboard flows, moderation, transactions, sessions, goals, TTS public preview guards, media upload validation, tip-creation validation and `create_app` error gates.
- Final tally: **285 passed, 1 skipped (FFmpeg-dependent, intentionally gated on `shutil.which('ffmpeg')`), 0 failures.** JUnit XML at `docs/final-test-results.xml`.
- All 24 user-facing HTTP routes smoke-tested (`/`, `/tip/<channel>`, `/overlay/{alert,goal,recent,top3}`, `/obs/activity`, `/admin`, `/health`, `/api/public/config`, `/api/admin/*` auth gates, `/static/premium.{css,js}`). Every route returned the expected status.

**Minor .bat fixes**
- `List_Voices.bat` and `Install_Media_Tools.bat` now `cd /d "%~dp0"` after `@echo off`, matching the project's double-click-safe convention used by every other .bat.

**No breaking changes.** Upgrade is a straight file-replace over 1.4.1 — no `.env`, no DB changes.

---

# 1.4.1 — Hotfix: unblock Edge / Piper engine selection

- Fixed "Invalid TTS engine" error when selecting `edge` or `piper` in the admin Settings → Text-to-speech form. The settings-save validator in `acepressure/app.py:301` still had the old 4-engine whitelist (`browser/windows/azure/off`); extended it to the full 6-engine list.
- Fixed the voice-detector drop-down inside the TTS tab (`acepressure/static/designer.js`) which was only offering Windows + Azure as voice sources. Now offers Edge TTS, Piper, Windows and Azure, with Edge as the default when the project is set up fresh.
- No data or configuration changes required when upgrading from 1.4.0 — just replace the two files and hard-refresh the admin page.

---

# 1.4.0 — Free TTS engines (Edge TTS + Piper)

**Two new free TTS engines, no Azure subscription required:**

- **Edge TTS** (`engine: "edge"`) — Uses Microsoft Edge's public TTS endpoint. Same Neural voices as paid Azure Cognitive Services Speech, including every HINGLISH-READY Multilingual voice and all hi-IN voices. **Zero cost, no API key, no credit card, no account.** One-click install: double-click `Install_Edge_TTS.bat`. Admin voice catalog now sorts Multilingual → Hindi → English and labels free voices with " (FREE)".
- **Piper TTS** (`engine: "piper"`) — Local, offline neural TTS. Runs entirely on your CPU; no internet calls at synthesis time. One-click install: double-click `Install_Piper.bat` (installs the package and downloads 4 starter voices — Hindi male/female + English male/female — ~200 MB total). Voices live under `data/piper-voices/`; add more from <https://huggingface.co/rhasspy/piper-voices/tree/main> by dropping `*.onnx` + `*.onnx.json` pairs into that folder.

**Dispatch and polish**

- `tts_service.catalog(engine, directory)` and `tts_service.synthesize(directory, text, voice, engine)` now dispatch to the four server-side engines (`edge`, `piper`, `azure`, `windows`). The browser engine stays client-side.
- Overlay TTS endpoint (`/api/overlay/tts/<event_id>`), admin preview, and public voice preview all serve the right mimetype automatically (`audio/mpeg` for Edge MP3 output, `audio/wav` for Azure/Piper/Windows WAV).
- Public voice-preview endpoint now accepts `edge` and `piper` alongside `windows` and `azure`.
- Loaded Piper voices are kept in memory (LRU cap of 4) so repeat alerts don't re-load the ONNX model.
- Admin TTS note rewritten to steer operators to the right engine for their situation and budget.

**Recommendation:** If you want the absolute best Hinglish quality for free, use **Edge TTS** with a voice tagged **HINGLISH-READY** (e.g. `en-US-AvaMultilingualNeural`). If you want offline operation (no internet dependency during a stream), use **Piper** with `hi_IN-pratham-medium`.

---

# 1.3.0 — Hinglish TTS, premium UI, free static URL

**TTS**
- Fixed Hinglish mispronunciation. SSML `xml:lang` is now derived from the selected voice's own locale instead of being hardcoded to `en-IN`. Hindi segments in Hinglish messages are wrapped in `<lang xml:lang="hi-IN">` so Hindi words get Hindi phonetics even on English-primary voices.
- Added Devanagari + romanized-Hindi detection (~100 common Hindi tokens: `bhai`, `kya`, `hai`, `bahut`, `badhiya`, etc.) in both the server (`acepressure/tts_service.py`) and the browser (`static/common.js`).
- Browser overlay TTS now auto-switches to any installed Hindi voice when a message is Hinglish, even if the streamer picked an English voice.
- Azure "Multilingual Neural" voices (code-switching) are now surfaced in the admin voice catalog with a "HINGLISH-READY" tag and sorted first. hi-IN voices are tagged "हिंदी".
- `voice_locales` is now persisted alongside `voice_labels` for richer admin UI hints.
- Default TTS preview text updated to be Hinglish so operators can hear code-switching quality immediately.

**Public URL — now free and static**
- New `Setup_Tailscale_URL.bat` + `scripts/setup_tailscale_funnel.py` enable a free, permanent public HTTPS URL via Tailscale Funnel. No domain purchase, no ngrok warning page, no per-session URL rotation — the URL stays stable so the iPhone Shortcut automation keeps working forever.
- New `docs/TAILSCALE_FUNNEL.md` guide covers install, auth, enabling HTTPS on the tailnet, and pointing the iPhone Shortcut at the stable URL. Includes a comparison table (ngrok vs Cloudflare Tunnel vs Tailscale Funnel) and free-fallback options (zrok, serveo, localtunnel).
- `cloudflared` and `ngrok` paths remain available as alternatives in the docs.

**Premium UI**
- New `static/premium.css` layered on top of `style.css`: deeper multi-layer dark palette, glass-morphism tip card and admin panels (backdrop-filter blur), animated conic-gradient border on the hero tip card, premium type scale with Noto Sans Devanagari fallback for Hindi script, gold-accent gradient wordmark, premium metric tiles with hover lift, animated progress bar shimmer, polished scrollbars, premium login screen.
- New `static/premium.js` adds a confetti burst on tip success (public page) and new OBS alert fires (overlay), smooth number-counter animations on admin metric tiles, and a subtle 3D parallax on the hero tip card (desktop only, respects `prefers-reduced-motion`).
- Overlay alerts gain a glass surface with a gold rim and 100 px glow — reads premium on stream.
- Zero new runtime deps; strict CSP (`default-src 'self'`) preserved. All fonts come from the system stack (Segoe UI Variable + Nirmala UI on Windows), no external CDN.

**Shipping discipline**
- Added root-level `LICENSE` (MIT) so the project can be shared and reused.
- `PACKAGE_MANIFEST.json` + `PACKAGE_MANIFEST.txt` regenerated to match the live 1.3.0 tree.

---

# 1.2.0

- Original responsive tipping-page refresh and selectable voice cards with samples.
- Windows voice discovery with male/female metadata, listen tests and OBS TTS diagnostics. Optional Azure Speech with dynamic India voice catalog; credentials remain local.
- Short MP4/WebM re-encoding through optional FFmpeg, separate selectable audio, and image/GIF uploads.

- QR saving and visible exact-amount scan instructions; optional app links with launch cooldown. Payment-app restrictions remain outside the server.
- Opt-in private browser supporter recognition, forget control and merge alias support.
- Shared live/preview visual renderer, four silent previews, bounded appearance controls and decoded image uploads.
- No payment verification rules or existing records changed.

# 1.0.4 — Paytm demo matching

Added optional exact-paise matching, strict printed-time checks, persistent semantic fingerprints, atomic duplicate handling and labelled demo OBS alerts. Live mode remains blocked. Existing capture-only mode remains the default.

# 1.0.2 — goal card clipping fix

Fixed CSS class collision: an outer goal card with class `bar` was receiving the progress track height and overflow. Scoped track styling to `.widget > .bar`. Reproduced the original clipping in Chromium, then verified that the full title and track fit inside the card at 700x180 and 390x180, with 5% fill. Verified the OBS Custom CSS workaround below too. Earlier text-presence tests missed visual clipping; a geometry regression is now included in tests/goal_layout_check.py and docs/goal-layout-test.json.

For an existing installation, back up and replace only acepressure/static/overlay.css, then use OBS Browser Source Properties > Refresh cache of current page. No reinstall or database changes are needed.

Alternatively paste this into that goal source's Custom CSS to fix v1.0.0/v1.0.1 immediately:

```css
.widget.bar {
  height: auto !important;
  overflow: visible !important;
  background: rgba(15,17,22,.94) !important;
  border-radius: 12px !important;
  margin-top: 0 !important;
}
```

# 1.0.1 — public tip page refinement

The public page now uses a compact centered creator profile above a focused tipping form, with presets, visible minimum, message counter, readable voice labels, selectable sound buttons and a sound preview. The top three supporters appear below the form on desktop and mobile. AcePressure charcoal/crimson branding is retained. No StreamTipz source code, graphics or meme audio was copied.

The 12 Chromium acceptance checks were rerun and passed with zero JavaScript errors. A targeted browser check also passed sound selection/preview, character counting, preset selection and checkout. The payment backend was unchanged; the prior 44 backend/packaging test results remain included. Live verification is still disabled by default.

If installing for the first time, use this package. If already installed, stop the app, back up the installation and replace only acepressure/templates/public.html, acepressure/static/public.js and acepressure/static/style.css; preserve .env and data. Restart and refresh the page.
# 1.0.3 — Paytm notification diagnostics

Added demo-only capture endpoint and private /admin/paytm-test screen. Separate
30-minute capture tokens, bounded redacted diagnostic storage, exact-input
fingerprints, and strict no-verification/no-alert behavior. Includes iPhone
HTTPS setup guide and tests. No live Paytm verification enabled.

