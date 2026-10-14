# 1.1.1 — ngrok and moving from demo to live

## Upgrade first
Stop the server and back up your entire existing installation. Extract the ZIP separately. Copy `acepressure`, `tests`, `docs`, `VERSION`, `README.md` and `START_HERE.txt` into your existing installation; replace those program files only. Keep .env, .venv, data and data-demo. No dependency change or token rotation is required for this update. Restart the server and reload browser pages to load the new JavaScript.

The public status check interval is now 20 seconds. Checks pause in hidden tabs, stop after expiry and back off after failures. The local countdown still updates each second. A Check payment status button lets a viewer ask for an update, including approval after expiry. Repeated manual checks have a five-second cooldown. Confirmation can take up to the next scheduled check; OBS delivery is independent.

## Existing demo remains available
Start_Demo.bat uses port8766 and data-demo. Use `ngrok http 8766` for demo. Your persistent demo bridge token remains valid. The successful Paytm review/approval test does not activate the live database.

## Prepare live configuration privately
1. Stop the demo and the ngrok tunnel. Do not copy demo donations into data.
2. Run Configure_Public_URL.bat. At the FIRST prompt type `live` and press Enter. At the SECOND prompt paste your assigned ngrok HTTPS origin, with no path. Wait for Saved. This enables secure cookies for live admin login.
3. Start Start.bat from that same installation, then run `ngrok http 8765` in PowerShell. Use the same ngrok account/assigned domain. Keep both processes running.
4. Open your HTTPS address followed by `/admin`, sign in, then open Settings. Secure cookies mean you should use this HTTPS address for the live admin, not local HTTP.
5. Turn accepting_tips OFF while configuring. Enter your real `upi_id` and `payee_name` privately. Keep SMS `bridge_enabled` OFF; the Paytm bridge has its own switch. Save settings. Never post your .env or tokens in chat.
6. Open `/admin/paytm`. The live database starts with its own bridge disabled. Generate a LIVE persistent token, enter the receiving bank marker, leave automatic matching OFF and enable the bridge. Do not turn accepting_tips on yet.
7. In the existing iPhone Shortcut keep the HTTPS URL ending `/api/bridge/paytm`, but replace Authorization with `Bearer ` plus the LIVE bridge token. Your demo token does not authenticate against the live database. Leave ngrok's authtoken unchanged.
8. Use the LIVE Admin > OBS URLs for your sources. For overlays use localhost port8765, preserving their key and other query parameters. Keep old demo sources backed up/hidden, vertical audio muted. The activity dock requires a login; do not weaken secure-cookie settings just to use it over HTTP.
9. Start a live stream session before an alert test. Only when ready for a controlled real payment, turn accepting_tips on. Create one tip, inspect the QR/deep-link payee and exact amount in your UPI app before authorizing, and verify the receiving account independently. Approval should update the public page and the LIVE OBS source. This test is real money and enters live history. Document any later correction/refund in the audit trail; marking REFUNDED does not send money back.
10. Keep accepting_tips off until that device test succeeds and you are ready to share the link.

## Stream routine
Start Start.bat and `ngrok http 8765`, confirm the phone automation is enabled, start a stream session, then enable tips. At the end, pause new tips, allow outstanding ten-minute requests to finish, review received payments, end the session, and close the tunnel/server. Offline notifications cannot reach the PC; reconcile missing entries against your own history. Stopping the website cannot cancel a bank transfer from an already saved QR.

No domain purchase is required with ngrok's assigned domain. Free-plan limits and warning pages still apply. Keep OBS overlays local and close idle HTTPS admin pages: their frequent polling also consumes requests. Check your ngrok Usage dashboard. This update reduces traffic; it cannot guarantee that free quotas cover your audience.

Official references: https://ngrok.com/docs/pricing-limits/free-plan-limits and https://ngrok.com/download/windows
