# Voices, Hinglish and custom alert media (1.2.0)

## First fix for silent Hindi

A label such as `hi-IN` requests a voice but does not install one. Previously the browser could fail or substitute a voice silently. The overlay now reports missing voices to Admin → TTS → **Check last OBS TTS result**. No diagnostic text is deliberately placed inside the donation card. A speech failure does not interrupt the visual alert or payment record.

AcePressure makes the Edge, Piper, Windows and Azure audio itself and the OBS source just plays it, so OBS needs no installed voice. Only **Browser voices (OBS)** depend on the voices installed on the PC that runs OBS.

1. Update `acepressure`, **scripts**, `docs`, `tests`, `VERSION`, and the optional `Install_Media_Tools.bat`. Preserve `.env`, `.venv`, data folders and your own assets.
2. Restart your normal server and refresh OBS browser sources once.
3. Admin → TTS → Voice source → **Windows installed voices · local** → **Detect available voices**.
4. Select the actual male/female voices you want, then **Use selected voices**. The displayed gender comes from the installed voice metadata; unavailable male/female voices are not invented.
5. Type `GG bhai, kya clutch tha! Thanks for the stream.` and press **Listen to sample**. Try your usual spelling and also plain English. This produces WAV on the PC, so OBS no longer depends on browser speech support when Windows mode is selected.
6. Set TTS enabled, unmute, and check the minimum donation. The default minimum is ₹50: a ₹20 tip will not speak unless you lower that setting. Test with Alertbox → Test alert (₹100), the horizontal source visible, audio enabled. Vertical remains muted to avoid duplicate sound.
7. If no Hindi voice is detected, it is not available to Windows SAPI. Installing a Windows display language alone does not guarantee that SAPI can use its voice. Select an available English voice for Roman-script Hinglish and listen to the result, or configure the optional cloud provider below.

Hinglish has no single spelling/pronunciation standard. This release does not translate or automatically transliterate supporter messages. (That was 1.2.0. Roman Hindi is now converted to Devanagari for Hindi-capable voices: see the 1.6.2 section below.) Neither an English label nor a Hindi label guarantees natural Hinglish. Preview and choose the voice that works for your audience. Browser-mode previews use the viewer's own device and may differ from OBS; Windows/Azure previews use server audio.

## Optional Azure voices

Azure is optional; it is not required for payments or local TTS. It requires your own Microsoft Speech resource, network access, region and key. Check your account's quota/pricing before enabling. No subscription is created by this package. Do not send keys in chat.

Add these to your existing `.env`, using values from your Speech resource, and restart:

```
AZURE_SPEECH_KEY=your_private_key
AZURE_SPEECH_REGION=your_resource_region
```

Admin → TTS → Voice source → Azure Speech → Detect available voices. This queries the provider's current English India and Hindi India catalog, including its male/female labels. Select 1–12 voices, save, then test your English/Hinglish sample. Old pending tips whose selected voice belonged to another engine may not speak after a provider switch; change engines between streams after outstanding tips are complete.

When selected, the moderated message is sent to Microsoft for synthesis. The public page discloses this. Donor email, payment data and bank details are not sent. Credentials stay in `.env`. Viewer text is XML-escaped rather than interpreted as SSML. Public previews use one fixed sample per enabled voice; arbitrary public text synthesis is not offered. Generated cloud WAV files are cached locally; files older than a day are removed on a subsequent synthesis request. Existing backups may retain older files if you back up the whole folder.

The integration was tested with mocked provider responses. Actual cloud synthesis and pronunciation require your account and a listen test. It is not advertised as already tested on your PC.

Reference: https://learn.microsoft.com/azure/ai-services/speech-service/rest-text-to-speech

## Sound library and free starter sounds (1.6.0)

Every alert sound lives in **Admin → Sound library**:

- **Add a sound**: upload a WAV, MP3 or OGG of up to 30 seconds and 8 MB. Give it an optional name, emoji, category and minimum tip (0 = any tip), and choose whether viewers can pick it and whether it becomes your default.
- **Your sounds**: tick **Viewers can pick** and set **Min tip (₹)** right in the table; changes save as you make them. **Make default** makes a sound your default, and **▶ Test on stream** sends it to OBS as a labelled test alert.
- **Viewer picks & default sound**: the switch **Viewers can pick a sound on the tip page**, and the **Default sound** that plays when a viewer doesn't pick one (Chime, Pulse, Silent, the alert video's own sound, or one of your sounds). On the tip page viewers choose under **Alert sound**; its first tile, **Streamer’s default**, plays your default. A paid pick still plays if you hide or reprice that sound afterwards.
- **Add starter sounds** adds 8 free sound effects that viewers can pick straight away (Vine Boom, Air Horn, Cash Register, Victory Fanfare, Clap, Game Over, Ba Dum Tss and Sad Trombone) plus 14 Indian meme slots waiting for your own clips. The 8 effects were made from code for AcePressure with no third-party audio, so they shouldn't trigger copyright claims; they are public domain (CC0 1.0). The bundled files are in `acepressure/starter_sounds` and the scripts that made them are in `scripts/starter_sounds`.
- Famous dialogue, film, TV and song memes are copyrighted, so they can't be bundled. Songs and film or TV dialogue can get copyright claims on YouTube, so prefer short reaction clips for the meme slots.

## GIF/video plus your alert sound

1. Admin → **Design studio** → **Upload your artwork**.
2. Upload a PNG, WebP or GIF (8 MB max), or a short MP4/WebM clip (24 MB, at most 20 seconds and 4 megapixels). Since 1.6.7 you can select several files at once; the menus show each file's uploaded name next to its stored name, sorted by that name.
3. Choose its filename under **Alert image / GIF / video**. Adjust art size, colors, radius, width and animation. Inspect the four previews.
4. Admin → **Sound library** → **Add a sound**: upload a **WAV, MP3 or OGG of up to 30 seconds and 8 MB** (since 1.6.7, several at once: each is named after its file). With FFmpeg installed (below), a file a browser can't play is converted to a standard MP3 automatically; longer clips are refused, never cut. Chime, Pulse and Silent are still available as your default.
5. In **Viewer picks & default sound**, choose it as **Default sound** (or click **Make default** on its row). Viewers who pick a sound on the tip page hear their pick instead.
6. Save appearance and test an alert from Alertbox. Design previews are intentionally silent; Test alert checks the complete live output without changing totals.

Video uploaded in Design studio is transcoded to WebM with its embedded audio removed. It loops during the alert and stops when the card exits. Your default sound, or the viewer's pick, plays once, followed by TTS when eligible. To keep a video's own sound, upload it in **Sound library → Upload alert bundle · visual + sound** without a separate sound: **Alert video’s own sound** then becomes your default, and a viewer's pick still plays instead, with the video muted. Visuals are shared across tiers; tier thresholds and display duration remain editable in Alertbox. Goal backgrounds/logos accept images, not video. Alpha playback may vary with the input codec and OBS browser build; PNG/GIF is a simpler transparent-art option.

### One-time FFmpeg install (video uploads and audio auto-fix)

PNG/GIF/WebP and ordinary MP3/OGG/WAV files need no extra tools. Video uploads, and the automatic conversion of audio files a browser can't play, require **FFmpeg and ffprobe** on your Windows PC. Double-click the optional `Install_Media_Tools.bat`, which runs Windows Package Manager for `Gyan.FFmpeg`; review its prompts. Close/reopen the server after installation.

Manual alternative: obtain a Windows build through https://ffmpeg.org/download.html and place `ffmpeg.exe` and `ffprobe.exe` under `AcePressure\tools\bin`, or install them on PATH. Do not place random executables from viewers there. The package checks duration/dimensions and decodes the uploaded container with a local protocol allowlist before saving a new silent clip. No remote media URL uploads or executable HTML/SVG assets are allowed.

## Volume, hidden links, the spoken copy and Hinglish (1.6.2)

**Volume.** Every sound in **Admin → Sound library** has a slider (10–100 %), and **Admin → TTS** has **Voice volume**. OBS, **▶ Preview**, **▶ Preview default**, **Listen to sample** and the tip page's previews all use them. 100 % is the file as uploaded, so a slider can only make a sound quieter. For more, raise the source in OBS's Audio Mixer. Chime, Pulse and an alert video's own sound keep their level.

**What every voice reads.** The server makes one spoken copy of each message and every engine reads it. It filters your banned words, hides links (when that switch is on) and applies your pronunciations. Then it drops emoji and shortens long repeats (when that switch is on). The alert card and your dashboard keep the original. For a Hindi-capable voice (a hi-IN voice or a Multilingual Neural voice), Roman Hindi in that copy is converted to Devanagari. Under **Try English or Hinglish**, “The voice reads” shows the result for the selected voice.

**How Hinglish is converted.**
- A sentence is read in parts, split at . , ! ? ; : or a danda. A part is Hindi when its Hindi words outnumber its English grammar words (the, is, my …), or equal them and include a word that is only Hindi.
- Words that are only Hindi in a tipping chat (bhai, kya, gaya, hai …) are always converted.
- Short words that are also names, abbreviations or other languages (ka, se, lo, hum, tu, ye …) are converted only in a Hindi part.
- Words that are also English (main, mat, mere, din, mast, na, ho, to, do, ko, ram, yeh, sun, log, par, jab) are converted only in a Hindi part, and not when the words around them make them English:
  - “the main”, “main account”, “Jett main” and “mera main” keep main;
  - “mouse mat” keeps mat, and ram is converted only in “jai shri ram”, “siya ram” or “ram ji”;
  - a word in capitals inside lower-case text, such as NA, stays as typed;
  - to, do, ko, log, par and jab also need a Hindi word next to them.
- Words joined to something else (lo-fi, bhai's, @bhai, #bhai, 2din) and web addresses are never converted.
- With a Hindi voice, a pronunciation can force a stubborn word, for example kya → क्या. Don't do this with English voices, because they can't read Devanagari.

**Hidden links.** These count as links: addresses starting with http://, https:// or www.; emails; names ending in a link-only ending such as .com, .net, .org, .io, .xyz, .tv, .shop, .site, .online, .app or .co.in; and shorter endings that are also words (.in, .me, .gg, .to …) when a path follows, as in t.me/x, discord.gg/x or amazon.in/deal. “op.gg”, “v1.6.2”, “Rs.500” and UPI IDs such as name@paytm are not links.

**Emoji and repeats.** Emoji, arrows and shapes are dropped from the spoken copy. A group of up to 6 characters repeated 4 or more times is cut to 3 (hahahahaha → hahaha, !!!!!! → !!!), but numbers are never touched. A message that is only emoji shows its card without the voice. Give an emoji words with a pronunciation (😂 → haha) to have it read.

## Read whole messages (1.6.3)

**Live activity** (and the Activity dock in OBS) has a button that switches between reading every message in full and reading only the start of long ones. The setting is also in **Admin → TTS**, with **When “Read whole messages” is off, read up to this many characters** (20–500, default 100).

When the switch is off, the server cuts the spoken copy after the last whole word that fits, and drops a comma or dash left at the end. It does this after pronunciations, hidden links, filtered words and the emoji and repeat clean-up, so skipped emoji use up no characters. Every engine reads that start, including browser voices with the Hindi copy. The alert card, the boards and your dashboard show the whole message.

**Longest message viewers can type** (up to 500) is the limit on the tip page's message box. It is separate from what the voice reads.

## Replay in full, big tips, the backup voice and moderation (1.6.4)

- **Replay in full** appears in Live activity on a tip whose voice was cut. Only that replay reads the whole message.
- **…but read the whole message for tips from this amount (₹)** in Admin → TTS reads big tips in full even when **Read whole messages** is off (0 = never). The tip page tells viewers.
- The cut keeps a word that ends right at the limit, never ends on a word like “of”, “Rs” or “ka”, and never splits a number.
- **Send to OBS as a test alert** (Admin → TTS) sends your sample to OBS. With **Read whole messages** off, **Test alert** uses a long message so you hear the cut.
- **If you see the voice fail**: the dashboard and the OBS dock say when the last alert's voice didn't play and why. **If the voice service fails** in Admin → TTS picks an offline voice (Piper, or a Windows voice) that reads the alert when Edge or Azure fails or takes more than about 12 seconds. It keeps reading for 2 minutes, then the main voice is tried again. **Listen** plays it in this browser.
- Filtered words also apply to names on stream, always as whole words (1.6.5). In a name, `_`, a digit or a capital starting a new part also starts a word, so “noob” catches “noob_master”, “BigNoob” and “BIGNoob” (1.6.6), and “shit” leaves “Kshitij” alone (a name typed like “HARShit” counts as HAR + Shit, though). A word inside a longer name needs its own entry: “shit” doesn't catch “BULLSHIT”, so add `bullshit*`, or `fuck*` for “fuckyou” and “fucker”. For messages, **Filter whole words only** matches a word on its own (“hell” leaves “hello” alone); end a word with * to catch its endings (noob* → noobs). New installs start with it on; an upgraded database keeps filtering messages inside words until you tick it.
- Line breaks in a message become spaces, and “<3” becomes ❤️. The voice skips emoji, so add **+ ❤ → love** in Pronunciations if you want hearts read.

## Reference page comparison

Inspected https://streamtipz.in/tip/zishu on 11 October 2026. Its visible page offers amount presets, name/email/message, male/female labels, a large sound list with a minimum amount, and a 30-day Top 3. It says email receipts are sent. Inspection of the public page does not establish how its payment verification or internal voice engine works.

AcePressure already has presets, name/message, sound previews, payment QR, verification/review and permanent history. This update adds actual-provider voice labels and samples, a new original responsive layout, remembered supporter recognition and creator-uploaded visuals/audio. Remaining differences: our public Top 3 is all-time, our email field groups history rather than sending email receipts, and this package does not include that service's sound library, meme audio or proprietary design. Since 1.6.0 AcePressure has its own Sound library: one **Alert sound** picker with a minimum tip per sound, 8 free starter sound effects made for AcePressure, and slots for your own meme clips. We do not claim feature parity with its private backend.
