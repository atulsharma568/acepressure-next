## Paytm notification bridge (1.1.0)

The persistent /api/bridge/paytm token is hashed in SQLite and can be revoked or rotated in /admin/paytm. Review is the default. Optional automatic matching is notification evidence, not bank verification. Same-minute, expired, late and uncertain candidates stay in review. Matching fingerprints are retained permanently for replay resistance, but identical input is not proof of a duplicate bank transaction. Raw notification text is not retained. Secure the phone, token, database and backups. A compromised authorized bridge can submit invented notifications. The receiving-bank marker is keyed-hashed and mismatches cannot be approved through this queue. Missing notifications require an independent history check and audited manual correction.

# Security and privacy notes

## Trust boundary

Payment verification means **an authenticated receipt from your trusted iPhone matched a pending request**. It does not mean the bank signed a webhook. This limitation is intrinsic to SMS forwarding, not fixable with a better regex.

- A random unauthenticated caller cannot confirm a ₹50,000 donation: the bridge requires a high-entropy bearer token; the reference must be new; the amount must exactly match an active pending request; and the timestamp must fit.
- If the token/phone is compromised, the attacker could fabricate a matching credit. Rotate the token, disable intake and reconcile against the bank immediately.
- A same-amount family transfer with paise could coincide with a pending request. A unique amount identifies a candidate, not the payer's intention. Round-number transfers are naturally excluded because generated requests always include 01–99 paise. For strict separation, use a dedicated bank/UPI destination or a supported authoritative payment-provider webhook in a future adapter.
- A 24-hour reuse quarantine mitigates late receipts; it cannot prove the identity of extremely delayed transfers once an amount is eventually reused.
- `tr`/`tn` in the UPI intent are helpful metadata, not authoritative proof and may not appear in the bank SMS.

## Implemented controls

- Cryptographically random session/bridge/overlay secrets created on your machine; hashed admin password. No secrets hard-coded in app source.
- Secure-cookie switch for HTTPS; HttpOnly/SameSite Strict sessions; CSRF header on all admin mutations; no third-party CORS; origin checks.
- Distinct admin, overlay and receipt-verification capabilities. iPhone Authorization token is never served by the public or admin web API.
- The go-live checklist (dashboard, Paytm page, Start window) reads `.env` only to spot a pending restart. It never returns a token, a token or bank-marker hash, or any `.env` value except your public address.
- Persistent per-visitor rate limits: tip requests 15 per 10 minutes per address plus a shared safety net of 200 per 10 minutes; “forget this browser” 10 per 10 minutes per address; sign-in attempts 8 per 15 minutes per address, plus 40 per 15 minutes shared by internet addresses (sign-ins from this PC, your LAN or your tailnet never count towards that shared limit). Both bridges check the token first: wrong-token posts are limited to 30 per minute per address and never use up the authenticated allowance (120 per minute per bridge). Behind Tailscale Funnel, cloudflared or ngrok every request reaches Waitress from 127.0.0.1, so the visitor's address comes from the tunnel's X-Forwarded-For header. That header is trusted only from a loopback proxy (127.0.0.1, last hop only); from any other address it is discarded, and X-Forwarded-Host/Proto are always discarded. The server log notes once when tunnel addresses are in use. These are basic abuse controls, not distributed-DDoS protection. Many viewers behind one NAT or mobile carrier can share a limit; monitor before tuning.
- Database transactions and uniqueness for reference deduplication and exact-amount allocation. A failed/expired/ambiguous/unmatched event cannot trigger OBS or enter revenue.
- Source-safe text rendering with DOM textContent, text length bounds, control/angle-bracket removal, moderation filter and a Content Security Policy. Viewer data never becomes JavaScript or HTML. The filter is a configurable phrase filter, not a guarantee against all abusive language or Unicode evasion.
- Prepared SQL parameters; no viewer-controlled shell commands. Windows speech uses fixed-script JSON stdin.
- Audio uploads (WAV/MP3/OGG) are verified by content, at most 8 MB and 30 seconds, re-encoded only when a browser could not play them and stored under random names; avatars are re-encoded JPEG. No public arbitrary file upload; deleting a sound removes its file only when nothing else uses it. The 8 bundled starter sounds are copied under new random names, so the originals in `acepressure/starter_sounds` are never changed.
- CSV values beginning with spreadsheet formula prefixes are neutralized. Export remains private supporter/payment data.
- No raw SMS/body/token logging. Error logs contain error type and route only. Receipt table retains reference, amount and timestamps, needed for dedup/reconciliation; bank account numbers/balances are not required.
- Automatic consistent SQLite backups. No automatic deletion of historical tips, references, corrections or backups.

## Operational duties

Keep `.env`, database/backups, tunnel credentials, private OBS source URLs and original scene exports off public repositories. OBS exports may already contain Streamlabs/BotRix tokens. The bundled `legacy` files are private backups of your originals; do not publish them.

Use HTTPS for every off-PC request. Do not port-forward plain HTTP. Leave `HOST=127.0.0.1` with the tunnel and enable `TRUST_CLOUDFLARE` only for that trusted local topology. Restrict filesystem access to your Windows account. Python's chmod on Windows does not substitute for Windows ACLs; keep the folder in an account-private location or set its Security permissions appropriately.

SQLite is not encrypted at rest. Use full-disk encryption where appropriate and protect backups separately. The audit trail is append-only through the application, but a machine/database administrator can edit the file; it is not cryptographically tamper-proof accounting evidence.

The stable `IDENTITY_SECRET` must be retained with backups so email-group hashes remain consistent. Resetting the admin password rotates only `APP_SECRET` (sessions), not identity grouping. Bridge and overlay tokens can be rotated separately. After rotation restart the service and replace the affected Shortcut/OBS links.

No automatic email or analytics trackers are included. Online TTS is optional: Edge TTS and Azure send the message text to Microsoft when selected; Piper, Windows and browser voices stay on this PC. Public media uploaded for alerts/avatar is intentionally readable without admin login. Do not upload private documents or personal bank images as media.

## Recovery scenarios

- **Leaked overlay URL:** rotate overlay token, restart, update OBS sources. The key cannot authorize admin actions or bank receipts, but can consume/spoil alert playback.
- **Leaked bridge token:** disable bridge, rotate token, audit receipts and reconcile bank transactions; do not assume past entries are trustworthy solely because they are VERIFIED.
- **Forgot admin password:** stop the server, run `scripts/manage.py reset-password`, restart. Existing sessions become invalid.
- **Wrong amount or late credit:** inspect bank app and reference, find the request, record MANUAL with correct display/actual amounts and reference plus reason. Never infer a deposit from a viewer screenshot alone. A reused reference is rejected.
- **Refund:** issue money through your bank, then mark REFUNDED with a reason. The app does not initiate refunds. Net support totals exclude the refunded tip; gross receipts remain visible in transaction history.
- **Phone offline:** automated delivery may fail. There is no guaranteed background retry queue in the provided Shortcut recipe. Check local errors and manually reconcile late receipts.

## Future stronger verification

A bank/PSP merchant integration with a signed server-to-server webhook can replace the SMS adapter while keeping pending tips, ledger, goals and overlays. Availability, onboarding, fees, settlement and whether money lands directly in your chosen account must be checked with that provider. This release does not claim such an integration exists.
