# Windows installation and internet access

## Recommended topology

Run one Python/Waitress process and its SQLite database on your Windows streaming PC. Expose only that process through a stable HTTPS Cloudflare Tunnel. Viewers and the iPhone reach the HTTPS hostname; OBS may use the same hostname. No inbound router port forwarding is needed. Keep the server and tunnel running while accepting tips.

A self-hosted Windows package is the primary deliverable, not a hosted Sites app. It avoids a second cloud ledger and keeps OBS and payment tracking in one database. Python/Waitress works on Windows; vanilla JavaScript avoids Node/build tooling. SQLite fits a single creator and one server process. Polling at 1–2 seconds avoids holding open a server thread for every overlay.

Your PC sleeping, restarting or losing connectivity makes the public page unavailable. For continuous availability, use the Linux/VPS option below. Free ephemeral hosting without a persistent disk is unsuitable for the permanent database.

## 1. Install and verify locally

1. Extract to `D:\AcePressure-Tips`. Do not put application data inside OBS installation folders or a cloud-sync folder.
2. Install a stable 64-bit Python 3.12+ from python.org. Confirm `py -3 --version` in Command Prompt.
3. Run `Install.bat`. Internet access is needed for Python dependencies. No Administrator privilege is needed for the application.
4. Set a unique password of at least 12 characters. The installer stores only its password hash. `.env` contains separately generated bridge, session, identity and overlay secrets. Keep this file private.
5. Use `Start_Demo.bat` and the README walkthrough. Demo runs on 8766, live runs on 8765; the databases are separate.
6. Run `Test.bat` if you want to run the included backend suite on Windows. This installs test dependencies and creates disposable test databases.
7. Run `Start.bat`. The first live visit is at `http://localhost:8765/admin`. The public checkout stays disabled until the UPI recipient and bridge are ready.

If the window exits, read its error rather than reinstalling. Common causes are another process using the port, a missing `.env`, or a secret shorter than 32 characters. Only run one live server process.

## 2. Publish through a stable HTTPS tunnel

You need a domain/hostname you control and a Cloudflare account configured for that domain. Domain registration can cost money; this package does not promise zero hosting/domain cost. Use Cloudflare's current setup instructions, which may rename dashboard sections:

https://developers.cloudflare.com/tunnel/get-started/

1. Create a Cloudflare Tunnel and select the Windows connector instructions. Install `cloudflared` from Cloudflare's official distribution. Follow the displayed install/start command on your own PC; the tunnel token is a secret and must not be pasted into this chat or a public repository.
2. Add a **published application route**, e.g. `tips.yourdomain.com`, pointing to **HTTP `127.0.0.1:8765`**. This is HTTP between two programs on your own PC; the visitor-facing connection must be HTTPS.
3. Keep cloudflared running, preferably using the Windows service setup in the official connector instructions. This is separate from the AcePressure startup task.
4. Edit `.env` with Notepad:

```dotenv
PUBLIC_BASE_URL=https://tips.yourdomain.com
COOKIE_SECURE=true
TRUST_CLOUDFLARE=true
HOST=127.0.0.1
PORT=8765
```

5. Stop and restart `Start.bat`. `.env` changes take effect on restart. Use the **HTTPS** URL for your admin login and Activity Dock after setting secure cookies. If you use plain HTTP for the dashboard, a secure login cookie will not work reliably.
6. Open `https://tips.yourdomain.com/health` from your iPhone on mobile data. It should return `ok: true` and `demo: false`. Open the public page and admin login. `/api/admin/state` must reject an unauthenticated request.
7. Do **not** put an interactive Cloudflare Access login in front of the entire hostname: viewers and the iPhone Shortcut could not reach it. The admin API already requires authentication. An optional additional Access policy limited to `/admin`, `/obs/activity` and `/api/admin/*` must be configured carefully; it is not necessary for the initial setup.
8. Disable caching of `/api/*`. Do not add a cache-everything rule. If an edge bot challenge blocks the authenticated iPhone POST, adjust the edge rule narrowly for `/api/bridge/credit`; keep the application's bearer authentication and rate limits.
9. Keep Waitress bound to loopback. Trusting Cloudflare's IP header is safe only when requests arrive through the local trusted tunnel; do not expose that listener directly to a LAN or internet proxy that passes user-supplied forwarding headers.

Temporary quick-tunnel URLs can be useful for short tests, but changing URLs breaks the Shortcut and shared tipping link. Use a stable hostname before going live. The included `config/cloudflared.example.yml` is for a locally managed tunnel; you may instead use the remotely managed dashboard workflow.

## 3. Configure live payments

In Admin → Settings:

1. Enter and double-check your UPI ID and payee name. Confirm the recipient in your own UPI app before sharing the page. Neither the secret token nor bank login credentials belong in these fields.
2. Set minimum, maximum, expiry and welcome message. The public form accepts whole rupees, then adds 1–99 paise; exact amounts are held from reuse for 24 hours.
3. Configure the exact bank sender and parser using `IPHONE.md`. Leave the bridge disabled until extraction is tested against credits, debits, balances and duplicates.
4. Enable the bridge and accepting tips only after the device tests pass.
5. Start a stream session. Create a low-value real tip through the page and pay its exact amount once. Confirm recipient, bank receipt, dashboard actual/display amounts, reference, overlay, goal and leaderboards. This is a user-run live test; the package does not initiate a transfer.
6. Close that session after testing. The verified payment remains permanent history. If you refund it, send the refund in your bank app, then record REFUNDED with an audit reason.

## 4. Start automatically at Windows sign-in

After manually confirming everything works, open PowerShell in the package folder:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Install_Startup_Task.ps1
```

This installs a Task Scheduler task called **AcePressure Tipping** for your current account. It starts at sign-in, can restart after failure, and runs without a time limit. It does not run before you sign in. Task registration can depend on your Windows account policy; if denied, create the same task manually in Task Scheduler using `.venv\Scripts\python.exe`, argument `"D:\AcePressure-Tips\run.py"`, and Start in `D:\AcePressure-Tips`.

Do not run `Start.bat` while the scheduled task is already running. Use Task Scheduler → End to stop it before upgrades. `scripts/Remove_Startup_Task.ps1` removes only this task and asks Windows for confirmation.

## 5. Alternative: a small Linux VPS with persistent storage

The same source runs on a VPS:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-lock.txt
.venv/bin/python setup.py
.venv/bin/python run.py
```

Bind to loopback and expose through a trusted HTTPS reverse proxy/tunnel. Set `PUBLIC_BASE_URL`, secure cookies, and the correct proxy IP-trust configuration. `TRUST_CLOUDFLARE` applies only to a local Cloudflare connector; do not enable it for an unrelated reverse proxy. Use a service manager to restart the one process and mount a durable disk for `data/`. Store offsite backups. Do not run multiple workers against separate copies of the SQLite file.

Windows SAPI is unavailable on Linux; use browser TTS only where it is supported, or explicitly choose `off`. A cloud TTS provider is not integrated or secretly billed. A later provider adapter can implement `speech.py` without changing the ledger.

## Sources checked

- Flask's Waitress deployment guide: https://flask.palletsprojects.com/en/stable/deploying/waitress/
- Cloudflare Tunnel setup: https://developers.cloudflare.com/tunnel/get-started/

The shipped code was executed with the pinned packages in `requirements-lock.txt`; later upgrades should rerun the suite before replacing your installation.
