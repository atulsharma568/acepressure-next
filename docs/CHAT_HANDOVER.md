# AcePressure project handover for a new ChatGPT conversation
Prepared 12 October 2026. Current delivered version: 1.6.3 (1.6.2 plus the changes under “What 1.6.3 changes” below). 1.6.1 was derived from the user's uploaded 1.6.0 ZIP.

## Instructions for the next assistant
Read this document and inspect the attached 1.6.3 source before changing code. Treat the ZIP as the implementation authority, this document as context, and the user's actual Windows settings as unknown until checked. Do not rebuild from scratch or downgrade to an older package. Do not invent previous work, credentials, payment confirmation or device test results. The user wants completed, tested changes and a Windows ZIP, not architecture or pseudocode. Give short, beginner-friendly installation steps. Preserve existing settings, databases, media and OBS scenes. Ask only for information genuinely needed.

## Why we are building this
AcePressure is a YouTube gaming/Valorant channel in India. The creator streams from Windows using OBS and Aitum Vertical. He wants his own donation/tipping experience, supporter history, goals and alerts without relying on a hosted tipping platform. Money must go directly to his UPI/bank account. Our app manages checkout, matching/review, records, statistics and overlays; it does not custody money or automatically refund it.

The desired look is original AcePressure branding: dark charcoal, ivory text, restrained crimson accents, clean esports styling. StreamTipz's zishu tipping page was a functionality/UI reference only; no proprietary code/design is to be copied.

## Environment and operating preferences
- Windows streaming PC; horizontal canvas 2560×1440, Aitum vertical 1080×1920.
- iPhone, reported iOS 27.0.1; no Android notification bridge.
- Regular Paytm account receiving UPI transfers from different apps.
- Bank credit SMS sometimes late or absent, so real-device work moved to Paytm notification automation.
- User confirmed FFmpeg/media tools installed.
- Horizontal OBS source plays chime/TTS; vertical source intentionally muted to avoid duplicate audio.
- Live launcher Start.bat normally port 8765; demo Start_Demo.bat normally 8766. Verify the actual launcher/config before giving URLs.
- Use local OBS URLs on the streaming PC to avoid public tunnel interstitials.
- The user initially used a temporary Cloudflare tunnel, then a free ngrok assigned hostname. 1.6.0 also contains Tailscale Funnel setup. Do not assume he switched to Tailscale.
- The PC, app server and chosen tunnel must run while accepting internet tips. He prefers stream-only uptime and avoiding domain costs.
- Never request/post .env, passwords, bridge tokens, ngrok authtokens, raw banking records or full private database exports in public.

## Main checkout and payment flow
1. Viewer visits the public page, selects an amount, enters name/message and optional supporter identity/email, TTS voice and allowed sound.
2. Backend creates a PENDING tip, generally expiring after ten minutes.
3. A unique paise component distinguishes pending requests, e.g. displayed support ₹20 but exact requested payment ₹20.76.
4. Checkout offers payment QR, copy UPI ID, copy exact amount and app-opening options. QR/deep links should prefill exact amount; user still authorizes payment in their UPI app.
5. iPhone receives Paytm credit notification and forwards it with authenticated HTTPS POST.
6. Backend parses recipient/amount/time, checks pending candidates and duplicate fingerprints, then matches or sends to review according to settings.
7. Only an eligible verified/approved transaction updates support records and queues a live alert, with session rules applied. Pending or uncertain notifications must not alert.
8. Store intended/display amount separately from actual received amount including paise.

Friends/family use the same UPI account. A generic incoming transfer must never become a donation merely because it arrived. Unmatched amounts, expired requests, suspicious timing, wrong recipients or repeated input must not blindly trigger OBS. Unique paise helps but cannot prove payer intent. There can be coincidental transfers.

## iPhone Shortcut already built and tested
Name used: Payment Received.
- Trigger: notification from Paytm.
- Obtain notification text.
- If Text contains "Received ₹" (contains, not equals).
- Get Contents of URL: HTTPS public address + /api/bridge/paytm.
- POST; Authorization: Bearer <persistent AcePressure bridge token>; Content-Type: application/json.
- JSON field text (lowercase) = actual Text variable, not literal "Text".
- Show Result → Contents of URL used during testing. This blocking diagnostic display should not be mistaken for necessary production behavior.
- Don't forward loan/marketing notifications just because they contain ₹.
- Receiving bank name + last four account digits are used privately to check destination. Do not expose them on overlays.
- Trigger reliability was intermittent during initial setup; later captures worked. One successful trigger does not guarantee all future deliveries.

Earlier /api/bridge/paytm-test is a separate DEMO capture endpoint with a short-lived token. Captures initially did not verify or alert; later demo matching was added. Do not confuse its token/mode with the persistent live bridge.

## Known successful user tests (reported in this thread)
- Demo confirmation and dashboard totals, supporter entry and OBS name/message were seen.
- Chime and a male test voice played horizontally.
- Notification captures of ₹1.00 and ₹1.37 reached backend with amount_paise 100 and 137.
- Demo exact ₹20.07 matched and public page confirmed.
- Review mode caught a wrong ₹20.07 transfer against a ₹20.76 request.
- A ₹20.76 review item matched the intended pending supporter after correcting the amount.
- The user later reported the live manual-review test worked: viewer confirmation, totals and OBS alert.
These reports are not newly independently verified in 1.6.1.

## Implemented areas in the supplied 1.6.0 baseline
- Flask/Waitress Python service with SQLite schema migrations, separate demo/live data.
- Branded mobile public page, configurable minimum/presets, exact-amount UPI checkout.
- Private authenticated dashboard: overview, transactions, pending, supporters, leaderboards, goals, alertbox, TTS, sound library, design studio, sessions, analytics, OBS, settings and audit.
- Permanent records, exports, statistics over standard/custom periods, sessions, supporter profiles and private grouping/merge controls.
- Configurable periodic/campaign/custom goals; reset displayed period progress without deleting historical donations.
- OBS alert, goal, top supporters and recent overlays; horizontal/vertical layouts; activity dock; queues, replay, skip/mute, tests and delivery/connection diagnostics.
- Private Paytm inbox, manual approval with audit reason, matching checks and persistent authentication. Automatic matching is optional with risk acknowledgement; last confirmed user workflow was manual review.
- Sound library with viewer eligibility/minimums, default sound, uploaded media and starter sounds. Design studio supports image/GIF/video styling; bundles can use video audio.
- TTS engines: browser/Windows, Azure, Edge and Piper, with moderation/minimum/length controls and previews.
- Windows launch/install/backup/configuration scripts, optional FFmpeg and TTS installers, readiness checks, tunnel guidance.
- Security controls include admin auth/CSRF/origin checks, rate limits, escaping, duplicate handling and backups.
Inspect source and tests for precise behavior rather than assuming every requested feature is perfect.

## Important prior support issues
- Cross-origin request rejected: often the configured public origin did not match the actual tunnel URL, or local hostnames/session origins were mixed. Use the provided URL configuration flow; never disable CSRF/origin protection.
- ngrok warning in OBS: use local overlay URLs while keeping the public address for viewers/iPhone.
- Duplicate supporter names: same visible name is not reliable identity. Do not automatically merge strangers by name. Prefer optional private identifier/email or explicit admin merge; privacy and impersonation must be considered.
- iOS generic UPI links opened WhatsApp for one friend; app-specific buttons and QR fallback were requested. Actual installed-app/browser behavior must be tested on devices. A deep link cannot guarantee an OS app chooser.
- Goals originally used D:\Stream Assets\AcePressure\weekly_support_goal.html. Preserve legacy tools as emergency fallback, but verified database totals are authoritative.
- No raw HTML/JS from supporter text; no private email or bank notification contents on OBS.
- REFUNDED status is an accounting record, not an API refund to the bank.

## TTS issue that prompted 1.6.1
The user wants Roman Hindi/Hinglish such as "bhai kya khel raha hai", not a requirement for viewers to type Devanagari. Hindi voice labels alone did not deliver natural Hinglish. Typing "भाई क्या खेल रहा है" then Save settings appeared to change it to English; the cause was UI redraw replacing the sample with a hard-coded default, not automatic translation.

Review of 1.6.0 found:
- Preview sample reset on dashboard redraw.
- Blind dictionary substitutions could change English main→मैं and mat→मत; ordinary gaming words falsely counted as Hindi evidence.
- Piper used old synthesize(text, wav) API though the installer fetched a modern provider.
- 689 tests passed, 3 failed due to premature optional Edge import in mocked validation/cache tests.

## What 1.6.1 changes
- In-tab TTS sample draft and saved preview selection survive redraw. Reload intentionally clears draft; no sensitive preview is persisted to disk/browser storage.
- Server and browser helpers remove ambiguous English/Hindi homographs from substitution and English gaming terms from detection.
- Normal Roman Hindi conversion still works, but intentionally ambiguous words may remain Roman. No guarantee of arbitrary natural Hinglish; this is a small dictionary, not transliteration AI.
- Piper uses synthesize_wav; installer pins 1.8.0; invalid/empty newly generated WAV is rejected; model cache keyed by absolute path; synthesis cache bumped.
- Downloader accepts --data-dir for demo/custom models.
- Edge defers provider import until it needs to generate uncached speech.
- No payment-policy changes, no new database migration, no production activation.

## Remaining limits / sensible next work
- Real voice quality and latency need listening on the user's PC and OBS; compare Hindi/multilingual male/female voices on realistic mixed sentences.
- Dictionary conversion is deliberately limited. If adding a smarter transliterator, preserve original donation text and avoid corrupting English names/game terms. Do not silently send messages to an additional paid/cloud service.
- Paytm notifications lack a reliable bank transaction reference in the observed format. Fingerprint duplicate detection means identical input, not proven duplicate bank transaction. Two legitimate similar payments and replayed notifications require cautious handling.
- Missing/delayed phone notifications must not cause false success. Keep review available and monitor bridge health.
- Public tunnel uptime/service limits, UPI app interoperability and actual Windows audio remain device/environment checks.
- Do not claim public-launch readiness merely because unit tests pass.
- Keep demo and live histories/tokens/settings distinct. Use test alerts and mock-provider tests before requesting another real payment.

## Architecture navigation
acepressure/app.py: HTTP routes and dashboard/server integration.
domain.py: records, settings, stats, sessions and core behavior.
paytm_bridge.py / paytm_match.py / paytm_capture.py: bridge and matching/capture.
tts_service.py / edge_tts_service.py / piper_tts_service.py / speech.py: speech providers and conversion.
static/admin.js / designer.js / common.js / overlay.js: dashboard, preview and overlays.
migrations/: SQLite migrations.
tests/: regression suite. requirements-dev.txt includes pytest/Playwright.
docs/: deployment, payment testing, security and update guides.
Read VERSION, docs/CHANGELOG.md, docs/UPDATE_1.6.3.md and docs/VALIDATION_1.6.3.md first (the 1.6.2 and 1.6.1 versions explain the earlier TTS work).

## Suggested first message to the other chat
"I am building AcePressure, a self-hosted UPI tipping system for my YouTube stream. Read the attached CHAT_HANDOVER.md and inspect the attached 1.6.3 ZIP. This is an existing working project: preserve its features, data, security and Windows setup. First summarize what you understand and any concrete code risks; do not rebuild it or assume access to my PC. I will then tell you the next change."

## Final 1.6.1 validation
702 pytest tests passed. A real headless Chromium session verified the sample survives Save settings and navigation, and browser conversion preserves the English examples. Installed Piper 1.8.0 WAV-writer integration passed with synthetic chunks; no real voice-model inference was performed. Windows, OBS audio, iPhone automation and real-money flow were not independently retested for this update. See VALIDATION_1.6.1.md for scope.

## What 1.6.3 changes
- settings.tts_read_full (default true) and settings.tts_short_limit (20–500, default 100). When tts_read_full is false, Store.speech cuts the spoken copy with text_filters.first_part after a whole word. The alert's speech and speech_hi, the server TTS endpoint, the Voice Studio preview and “The voice reads” (which also returns shortened) all use the cut copy; the card keeps the whole message.
- Live activity and the OBS dock have a “Shorten long messages” / “Read whole messages” button; a health chip shows while it's off. The tip page shows a note (public config sends both settings). tts_limit's label is now “Longest message viewers can type (up to 500)”. Number settings outside their range get a readable error, and true/false are no longer accepted as numbers.
- No migration. 1.6.2 runs on a 1.6.3 database (rollback tested) and reads whole messages.

## Final 1.6.3 validation
800 pytest tests passed, plus 40 real-Chrome checks for the switch and the 53 checks from 1.6.2, a rollback (1.6.3, then 1.6.2, then 1.6.3) and a fresh install from the ZIP. See VALIDATION_1.6.3.md. The voices were not listened to, and Windows, OBS, iPhone automation and real money were not tested for this update.

## What 1.6.2 changes
- Volume: soundboards.volume (migration 009, 10–100, default 100) per library sound; settings.tts_volume for the voice. The claim response sends alert.volumes {file: %} and tts_volume; the overlay, admin previews and tip-page previews apply them.
- Viewer text on stream (acepressure/text_filters.py): hide_links (default on) shows “[link]” in alert messages and names, overlay boards and the public top list; stored tips keep the original. The spoken copy (Store.speech) applies pronunciations (settings.pronunciations, at most 100), then drops emoji and shortens long repeats (tts_cleanup, default on). Every engine reads it; an empty copy sets tts false.
- Hinglish (tts_service.py): sentence parts with always-Hindi words, short words and English homographs guarded by their neighbours. The server sends speech, speech_hi and hinglish with each alert, so the browser engine matches the server voices. common.js keeps its short lists only as a fallback for older servers.
- “The voice reads” (POST /api/admin/tts/spoken) shows the spoken copy for the selected voice. Piper falls back to synthesize() for piper-tts 1.2.
- A 1.6.1 overlay still works with the 1.6.2 payload, and the 1.6.2 overlay works with a 1.6.1 payload. 1.6.1 runs on a 1.6.2 database (rollback tested).

## Final 1.6.2 validation
784 pytest tests passed, plus 53 real-Chrome checks, 27 tip-page picker checks, a 12-check rollback and a 41-check fresh install from the ZIP. See VALIDATION_1.6.2.md. The voices were not listened to, and Windows, OBS, iPhone automation and real money were not tested for this update.
