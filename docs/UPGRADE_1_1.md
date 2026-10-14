# Version 1.1 — Paytm bridge, review and public checkout

## Upgrade your existing Windows installation

1. Stop Start_Demo.bat and Start.bat, if running.
2. Copy your entire existing installation to a backup folder. Do not delete it.
3. Extract the new ZIP separately.
4. Copy the new `acepressure`, `docs`, `scripts` and `tests` folders, and `run.py`, `VERSION`, `Configure_Public_URL.bat`, `README.md` and `START_HERE.txt` into your existing installation, replacing those program files.
5. Preserve your existing `.env`, `.venv`, `data`, `data-demo` and OBS sources. Dependencies have not changed from 1.0.4. New database tables are created automatically on startup.
6. Start Start_Demo.bat. Sign in at http://127.0.0.1:8766/admin using the same browser. Open http://127.0.0.1:8766/admin/paytm (the new page, not paytm-test).

Do not roll back only the database while payments are arriving: restoring an old backup also restores old replay protection. Stop the bridge before any restore.

## Connect your existing iPhone automation

1. Keep the Windows server and HTTPS tunnel running. If using the temporary tunnel for this demo, run Configure_Public_URL.bat, choose demo and enter its current HTTPS origin. Restart Start_Demo.bat afterward. This fixes the public form's origin check without disabling protection.
2. On the new Paytm bridge page, click **Generate / rotate persistent token**. Copy it privately; it is shown only once. It survives server restarts and has no 30-minute expiry. Rotation immediately revokes the previous token and disables the bridge until enabled again.
3. Enter the receiving bank marker exactly as your notification shows it: bank name, a hyphen, and the last four account digits. Only a keyed hash is stored. Leave automatic matching **unchecked** for the first test. Click **Enable bridge**.
4. In your existing Shortcut, keep Paytm as the trigger, Text containing the notification, and `If Text contains Received ₹` (no trailing space).
5. Change Get Contents of URL to your current HTTPS origin followed by `/api/bridge/paytm`. Method POST. Header `Authorization` = `Bearer ` followed by the NEW token. Request Body JSON: lowercase key `text`, value the Text variable. Keep Content-Type application/json. Do not use the old capture token.
6. For initial testing, Show Result should contain only **Contents of URL**. Once tested, remove Show Result so the phone does not wait at a popup. Keep the POST action inside the If branch.
7. The old 30-minute capture page is diagnostic only; its checkbox/token no longer controls this new bridge. Do not run two automations forwarding the same notification.

## Test immediate payment and review

First use a synthetic notification in a separate temporary Shortcut Text action to test transport without sending money. Use the exact requested amount, current date/minute and configured bank marker. This is DEMO ONLY; never submit invented receipts to your live bridge.

1. Start a demo stream session and keep the horizontal OBS alert source open.
2. Create a tip on the demo public page. The request expires after 10 minutes by default. It adds paise, for example ₹20.07 for a ₹20 tip. Use the actual generated amount.
3. Forward the notification immediately. There is no instruction to wait until the next minute. In the new page, click **Refresh inbox**.
4. The item should show REVIEW. The public page should say it is awaiting creator review. No automatic OBS alert should play.
5. In a real test, check your own Paytm/bank payment history before approving. In this isolated synthetic demo, record that it is a simulated test in the audit reason. Select the correct tip, tick the history confirmation, optionally tick Play alert, and approve. It becomes MANUAL, totals update once, and the public page confirms it. Demo alerts remain marked as tests.
6. Re-send the identical notification: it must report duplicate_notification without another alert. Expired, ambiguous and late payments must never auto-alert.

The new bridge can optionally auto-match after you acknowledge the risk. Paytm's text gives only minute precision, so payments in the same minute as tip creation still require review. This removes the waiting requirement for viewers, **not** the uncertainty. Transfers from the same sender for the same amount within one minute can be indistinguishable; a fingerprint is not a bank transaction ID. Check history and use the dashboard's audited manual correction for missing notifications or such collisions.

## Stable HTTPS for public launch

A temporary trycloudflare.com address is for testing. For a stable branded address:

1. Use a domain you own in a Cloudflare account. Follow the current [Cloudflare Tunnel guide](https://developers.cloudflare.com/tunnel/get-started/).
2. Create a named tunnel. On your Windows PC, install its connector using the Windows command Cloudflare supplies. Treat the tunnel token as a secret. Its Windows service can run at startup.
3. Add a published application route such as `tips.YOUR-DOMAIN` with service `http://localhost:8765` for live mode (8766 is demo). Do not open router ports.
4. Run Configure_Public_URL.bat, choose live, and enter `https://tips.YOUR-DOMAIN` with no trailing path. It backs up .env and enables secure cookies. Restart Start.bat. Sign in through the HTTPS admin address; HTTP login cookies will no longer work in live mode with secure cookies.
5. Use the existing scripts/Install_Startup_Task.ps1 for the application if desired; read DEPLOYMENT.md. The connector service and application are separate processes. Keep the PC awake and connected.

No domain or tunnel has been provisioned by this package. You must supply/control the domain and configure its DNS/tunnel account.

## Enable real checkout only after the demo passes

Live and demo databases are separate. On the LIVE HTTPS dashboard, configure your actual UPI ID and payee name in Settings. Do not enable the SMS bridge unless you actually configure that separate route. Open `/admin/paytm`, generate a separate live token, configure the recipient marker, and enable the Paytm bridge with automatic matching OFF initially. Change the Shortcut to this live HTTPS endpoint/token.

Live checkout generates a dynamic QR and `upi://pay` link with the exact amount and recipient. It also shows the UPI ID, Copy UPI ID and Copy exact amount. The viewer must authorize payment in their UPI app; nothing withdraws money automatically. App handling of deep links varies, so test on your iPhone and another viewer phone. Validate the payee shown inside the payment app, the paise amount, actual receipt, review and OBS before sharing the page.

Keep the existing OBS setup backed up. Live source URLs use port8765 (or HTTPS), not your demo port8766. Vertical audio can remain muted. A stream QR should point to the tipping PAGE, not a permanent direct-bank QR that bypasses pending-tip creation. Generate_Page_QR.bat can create the page QR.

Bank SMS is not required for this Paytm path. It remains an optional fallback. Paytm notifications are not signed bank receipts; this bridge cannot guarantee delivery, detect all spoofed evidence from a compromised phone/token, or conclusively distinguish coincidental same-amount transfers. Review is the default for that reason.
