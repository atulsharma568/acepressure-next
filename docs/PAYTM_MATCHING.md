# Paytm demo matching — 1.0.4

This version adds optional pending-tip matching to the existing Paytm test page.
It is available ONLY under Start_Demo.bat and affects ONLY the demo database.
Live Paytm payments remain disabled. Bank SMS is not required for this demo,
but the original SMS adapter remains available as an alternative.

## Update without losing your settings

Stop the running demo server. Back up your entire existing AcePressure folder.
Extract the new ZIP separately and copy the new acepressure subfolder into your
existing installation, replacing code files. Also copy VERSION and docs.
Preserve .env, .venv, data and data-demo. Start_Demo.bat remains the same.
The new SQLite table is created automatically without deleting history.
Refresh cache of the OBS alert Browser Sources to load the updated test label.

## Shortcut

Keep the endpoint /api/bridge/paytm-test, POST, Authorization: Bearer TOKEN,
Content-Type: application/json and JSON key text with the Text output variable.
The If condition is `contains Received ₹` with NO SPACE AFTER THE RUPEE SIGN.
The uploaded Shortcut failed because its comparison ended with a space.
Do not change the token for every notification. It changes when capture restarts
and expires after 30 minutes. Restarting the Python server also invalidates it.
The optional notification_date field is accepted but not used for identity or
matching: a retry timestamp must not turn a repeat into a new payment.
For normal unattended tests, remove the interactive Show Result action after
successful setup; watch the PC diagnostics instead. The POST must remain inside If.

## Device acceptance: exact-match demo

1. Keep the server and your Cloudflare test tunnel running. Restarting the tunnel
   changes its HTTPS hostname; update the Shortcut URL if that happens.
2. Sign in at http://127.0.0.1:8766/admin and start a demo stream session.
3. Open /admin/paytm-test in the same browser. Check "Enable demo pending-tip
   matching and TEST alerts", then Start 30-minute capture. Put the NEW token
   in your iPhone Shortcut. No live verification is enabled by this checkbox.
4. On the public demo page create a tip with a test name and intended amount
   (at least the configured minimum). Note its exact requested amount, including
   paise. Do NOT click Simulate payment in the dashboard.
5. WAIT UNTIL THE NEXT CLOCK MINUTE after creating the tip. Paytm reports minute
   precision only. Payments in the creation minute are conservatively rejected.
6. If testing with a consenting friend, have them transfer that exact amount to
   the same receiving UPI ID used for the successful notification tests. This is
   a real transfer to your bank, despite the website remaining in demo mode.
   Money is not refunded by this software. Do not send money to an invented QR;
   demo checkout deliberately has no real UPI QR.
7. Keep the iPhone locked and observe the PC. Success says demo_matched; demo
   totals and goals increase by the intended amount, while the transaction retains
   the actual paise amount. OBS displays DEMO / PAYTM NOTIFICATION MATCH.
   API verified remains false: this is not bank/provider verification.
8. Confirm only one tip and one alert event were created. Each configured OBS
   layout receives its own visual delivery, as before.
9. Stop capture after testing. There is no need to repeatedly transfer money to
   test duplicates: automated tests exercise simultaneous retries and changed
   client dates without moving money.

## Rejection outcomes

- unmatched_amount: no active unexpired pending tip has that exact paise amount.
  Expired tips are excluded. The money still stays in your bank.
- stale_or_future_notification: printed payment minute is older than ten minutes
  or in the future relative to the PC clock. Ensure Windows time is correct.
- payment_time_before_or_ambiguous: payment minute begins before tip creation.
  Create a new pending tip and wait until the next minute for a new test.
- payment_time_near_expiry: the printed minute overlaps the tip expiry boundary.
- inactive_stream_session: session ended or differs from the pending tip's session.
- blocked_supporter: dashboard block prevents automatic demo matching.
- unsupported_payment_format: exact observed Paytm wording/date was not recognized.
- duplicate_notification: this notification evidence was already processed. It
  cannot be reused after changing capture mode, rotating token or restarting.

Rejected evidence is not automatically reconsidered later. It produces no totals
or alerts. If used in a future live workflow, missing/ambiguous evidence needs an
explicit bank-history review; there is no silent fallback to approval.

## Reliability and security limits

The bridge has a separate expiring token, CSRF-protected admin control, request
size limits and rate limits. The matching transaction and alert are atomic in
SQLite, so concurrent duplicate calls cannot create multiple matches.

Fingerprints use normalized amount, payer/bank text and the printed payment minute;
only the keyed hash, amount, outcome and linked tip ID persist. Raw notification
text, payer names and bank suffixes are not retained. These fingerprints are NOT
bank references and remain stored separately from the 7-day diagnostic display.
Notification text from a stolen token could still be forged. Live mode cannot
invoke this demo matcher, and this token is not accepted by the SMS verifier.

Missing notifications cannot be recovered from the consumer Paytm app by this
server. A coincidentally matching real transfer is still possible. Minute-level
identity may conflate genuine identical notifications. A bank/provider API with
transaction references remains stronger evidence. No claim of guaranteed payment
verification or production readiness is made by this demo.
