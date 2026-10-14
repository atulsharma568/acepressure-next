# iPhone → bank-credit receipt bridge

## What is and is not ready

The server, authenticated endpoint, matching logic and strict parser interface are implemented. Your **actual bank SMS format is not known**. No generic “find the first number in any SMS” automation is supplied. That can mistake balances or debits for credits.

Apple Shortcuts has Message communication triggers and can make POST requests with Get Contents of URL. The screens and automatic-execution controls vary by iOS version. This guide gives the action sequence; **there is no signed, importable `.shortcut` file**, because it must be created and tested on your iPhone with your sender/format and local secret. Do not download an untrusted SMS-forwarding shortcut with access to your bank messages.

An SMS event is trusted phone evidence, not a bank webhook. Sender filtering is not cryptographic authentication. The endpoint secret protects against unauthenticated web submissions; it cannot protect against a compromised phone, leaked secret or convincingly spoofed bank SMS.

## Preferred mode: extract only the required fields on iPhone

Admin → Settings → parser: `structured-v1`.

Request:

```http
POST https://YOUR-HOST/api/bridge/credit
Authorization: Bearer YOUR_LOCAL_BRIDGE_TOKEN
Content-Type: application/json
```

```json
{
  "sender": "EXACT-BANK-SENDER",
  "direction": "credit",
  "amount": "100.37",
  "reference": "123456789012",
  "received_at": 1791538200
}
```

`amount` is a decimal rupee string with at most two decimals. `reference` is the unique bank/UPI reference (6–100 alphanumeric/hyphen characters). `received_at` is UTC Unix **seconds**, not milliseconds. The number above is an illustrative timestamp; generate the actual timestamp for each message. Do not send your balance, full account number, unrelated SMS or authentication OTP.

The backend compares the sender exactly with `bank_sender`, requires `direction: credit`, a reference and a timestamp, and then matches an active pending exact amount. An authenticated but unmatched receipt is recorded privately as `unmatched`; it contributes nothing to totals or OBS. References remain deduplicated even for unmatched receipts.

## Build the Shortcut action sequence

Start with synthetic test text in demo mode; only later attach the real bank trigger.

1. Open Shortcuts. On versions with an **Automation** tab: create a personal **Message** automation. Select the bank sender and a distinctive **credit** phrase, not just “INR” or “UPI”. Choose **Run Immediately** if your iOS presents it. On versions that attach automation triggers to a shortcut, add the Message communication trigger to a new shortcut instead. Follow your installed iOS version in Apple's guide.
2. Make the incoming message/Shortcut Input available to the actions. Inspect a **synthetic** message with Quick Look during setup to understand what sender/body/date fields your iOS exposes. Remove Quick Look for live unattended use.
3. Check the actual sender against your allowlist when the trigger exposes it. If the automation can filter an alphanumeric bank sender but does not expose the sender to subsequent actions, hard-code the same sender in the request **only after** the trigger has been verified to accept that sender exclusively. If the device cannot reliably discriminate it, do not enable automatic live crediting; use manual reconciliation.
4. Apply **Match Text** to the message body with a strict pattern for your bank's incoming credit format. Require an explicit incoming-credit phrase, the credited amount and the unique reference. Require one match. Stop the Shortcut if it is a debit, balance update, OTP, failed transfer, reversal or ambiguous message. Do not use AI to guess payment fields.
5. Use match groups to extract the **credit amount** and **reference**. Remove comma separators from the amount only if your bank uses them. Preserve the decimal portion and reject multiple candidate amounts. Never extract the available balance.
6. Use the message receipt date if accessible, otherwise Current Date at automation execution. Calculate seconds since a Date action set to **1970-01-01T00:00:00Z**, using Get Time Between Dates → seconds, then Round Number down. A bank transaction time, if reliably available, is preferable; delayed receipt/replay needs manual review. The app rejects a timestamp over 30 seconds in the future or more than 24 hours old and still requires the tip to be unexpired **at ingestion**.
7. Add a **Dictionary** containing exactly `sender`, `direction` (`credit`), `amount` (Text), `reference` (Text), `received_at` (Number).
8. Add **Get Contents of URL** with the HTTPS endpoint. Expand its options, choose **POST**, add the Authorization header with `Bearer ` followed by the `BRIDGE_TOKEN` from your local `.env`, and Content-Type `application/json`. Choose JSON request body and populate those fields from the extracted variables.
9. Read the response dictionary. `outcome: verified` means an existing pending tip was matched. `duplicate: true` means it was already handled. `unmatched` is expected for ordinary family transfers, wrong amounts, expired requests or late receipts. No alert is created for those cases.
10. For a non-success HTTP response or a connection failure, show a **local notification to yourself** so the message can be reconciled manually. Do not send an email or share the original SMS automatically. A retry must reuse the original reference and receipt timestamp; never generate a replacement reference to force a match.
11. Grant only the required network/automation permissions. On iOS versions offering **Allow Running When Locked** in shortcut privacy settings, enable it if required. Some action permissions require a first manual run. Test with the screen locked and over mobile data. Do not assume success because it works while Shortcuts is open.
12. In the dashboard set the exact `bank_sender`, select `structured-v1`, and enable the bridge only after completing the acceptance tests below.

Keep the token in the private Shortcut. Do not place it in a URL query parameter, screenshot it or share the Shortcut. The app rejects a missing/incorrect token before parsing a receipt.

## Why there is no guessed production regex

We need one **redacted incoming UPI credit SMS**, plus ideally a debit/failure example. Replace account digits, sender names, balances and real reference digits with same-length placeholders; preserve punctuation, ordering, amount format, the credit/debit wording and whether a timestamp is present. Never supply OTPs or bank login information.

Illustrative format only:

```text
Credit INR 100.37 via UPI Ref ABC123456
```

The included `example-credit-v1` parser accepts only that entire sentence, via Python `re.fullmatch`. It rejects “Debit”, balances and altered formats. Do not select this parser for your bank unless its actual format is exactly that sentence (unlikely).

## Alternative mode: a narrow bank-text adapter

If Shortcuts cannot extract groups reliably, send the **single matching credit SMS body**, exact sender and receipt timestamp to the same endpoint. A bank-specific adapter can validate it server-side. It must:

- Check the exact sender before parsing.
- Use an anchored, documented pattern with tests for credits, debits, balances, OTPs, reversals, malformed messages and multiple amounts.
- Return only `{amount, reference, received_at}` to `Store.verify`.
- Reject missing references and ambiguities. Never manufacture a reference.
- Avoid logging/storing raw text. The current app stores only the normalized amount/reference/time/outcome.

Add the adapter in `acepressure/parsers.py` and its name in the allowlist in `app.py`. Add test samples to `tests/`. No database or matching redesign is needed. Limit inputs to 4 KB. Sending a full matching credit SMS increases privacy exposure in transit; prefer the structured mode once exact extraction is tested.

## Acceptance before enabling live alerts

1. Synthetic credit on demo: exact pending amount verifies once.
2. Same receipt sent twice: one tip and one queued event, not two.
3. Wrong token, sender, debit, missing reference or wrong amount: no verified tip.
4. An ordinary round-number transfer: no match.
5. Expired tip or previous-session pending tip: never produces a new-session alert.
6. Locked-phone test on Wi-Fi and mobile data: request actually reaches the endpoint with correct fields.
7. One real low-value test: actual bank credit, receipt parsing, reference, displayed amount, actual paise and OBS are all reconciled.
8. Offline test: stop the server briefly; ensure failure is visible and manual reconciliation works. There is **no guaranteed iOS store-and-forward queue** in this release. Late retries after expiry must not auto-credit a new request.

## Official references

- Message communication triggers: https://support.apple.com/guide/shortcuts/apdd711f9dff/ios
- Adding and automatically running automations: https://support.apple.com/guide/shortcuts/add-automations-apdfbdbd7123/ios
- HTTP requests / Get Contents of URL: https://support.apple.com/guide/shortcuts/apd58d46713f/ios

Use the version selector in Apple's documentation for your installed iOS. The Apple docs confirm the building blocks; they do not guarantee your bank sender, permissions or locked-phone behavior.
