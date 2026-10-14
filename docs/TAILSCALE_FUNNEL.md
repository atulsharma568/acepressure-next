# Free static public URL via Tailscale Funnel

AcePressure 1.3.0 ships a one-click setup for exposing your local tip page to the
internet with a stable, free, HTTPS URL — no ngrok warning page, no domain
purchase, no monthly bill. The URL stays the same, so the iPhone Shortcut
automation that verifies tips keeps working after reboots, as long as this PC
stays signed in to Tailscale (see **Key expiry** below).

**What you get:** a URL like `your-pc-name.tail-xxxxx.ts.net` that always
points to your local AcePressure server at `127.0.0.1:8765`.

---

## Why Tailscale Funnel over ngrok / Cloudflare Tunnel

| Need | ngrok free | Cloudflare Tunnel | Tailscale Funnel |
|---|---|---|---|
| Zero cost | ✅ | needs ~$10/yr domain for a static URL | ✅ |
| **Static URL** that never changes | ❌ (random each session) | ✅ (needs own domain) | ✅ |
| No "trust this site" warning page | ❌ | ✅ | ✅ |
| Works with iPhone Shortcut automation | ❌ (URL changes break it) | ✅ | ✅ |
| Rock-solid uptime | medium | excellent | excellent |

**Winner for a solo streamer on a zero budget: Tailscale Funnel.**

---

## One-time setup on your Windows PC

### 1. Install Tailscale (free)

Download from <https://tailscale.com/download/windows> and install it
(or `winget install Tailscale.Tailscale` from PowerShell).

Sign in with Google, Microsoft, GitHub, or email — no credit card required.
Tailscale's "Personal" plan is free for up to 100 devices.

### 2. Enable HTTPS certificates for your tailnet

Visit <https://login.tailscale.com/admin/dns> → scroll to
**"HTTPS Certificates"** → click **Enable HTTPS**. This is required for
Funnel to serve a trusted HTTPS URL. One-time flip, no cost.

### 3. Run the AcePressure setup

Double-click **`Setup_Tailscale_URL.bat`** in the AcePressure folder.

It will:
- Verify Tailscale is installed
- Prompt you to sign in if you haven't already
- Enable Funnel on port 8765 (live) in the background. The first time, Tailscale
  may print a `login.tailscale.com` link: open it, approve HTTPS certificates /
  Funnel, then come back to the window
- Check with Tailscale that Funnel is really on, then print your public URL
- Write that URL into `.env` as `PUBLIC_BASE_URL` (only after that check; if
  Tailscale does not confirm, `.env` stays as it was and you can run it again)
- Flip `COOKIE_SECURE=true` for live mode
- Print your next steps in order

### 4. Restart AcePressure

AcePressure reads the public URL only when it starts. Close the AcePressure
window first (or end the **AcePressure Tipping** task in Task Scheduler if you
installed it), then double-click `Start.bat`. While the old copy is still
running, a new one refuses to start and tells you why. Visit the printed URL —
your tip page should load.

### 5. After that, AcePressure keeps Funnel on (1.6.5)

Every time AcePressure starts in live mode (Start.bat, or the AcePressure
Tipping task at sign-in), it asks Tailscale whether Funnel serves your tip
link. If Funnel is off, AcePressure runs the same command as the setup,
`tailscale funnel --bg 8765`, and its window says “Turned Tailscale Funnel
on”. If Tailscale is still starting, signed out or disconnected, it tries
again every 15 seconds. While Tailscale doesn't answer at all, the window
and the dashboard say so.

You don't need a `tailscale funnel 8765` window any more. If one is open,
AcePressure leaves it on and says so. Once you close it, AcePressure turns
Funnel on in the background within 15 seconds. If you type
`tailscale funnel 8765` after AcePressure has turned Funnel on, Tailscale
answers “listener already exists for port 443”. That only means Funnel is
already on: close that window, and don't run `tailscale funnel reset`.

AcePressure leaves Funnel alone when Funnel already sends visitors somewhere
else (demo mode on 8766, say), or when `tailscale serve` already shares
another program at your tip link's address, because Funnel would make that
public too. It never turns Funnel on in demo mode. Once it has turned Funnel
on, or found it on without a `tailscale funnel` window, it doesn't touch it
again until the next start. While a window still keeps Funnel on, AcePressure
turns Funnel on in the background whenever it goes off, even after
`tailscale funnel reset`, so close AcePressure first to keep Funnel off.

The first time, Tailscale may ask you to approve Funnel. The AcePressure
window shows the `login.tailscale.com` link: open it, approve, then restart
AcePressure.

To switch this off, add `TAILSCALE_AUTO_FUNNEL=false` to `.env` and restart
AcePressure.

---

## Pointing your phone automation (Paytm bridge)

Once you have the static URL (e.g. `https://streaming-pc.tail-abc12.ts.net`):

1. In **Admin > Settings**, enter your UPI ID and payee name.
2. Open `https://streaming-pc.tail-abc12.ts.net/admin/paytm`, click
   **Generate / rotate persistent token** and copy the token privately. Enter
   your bank marker exactly as Paytm shows it, then click **Enable bridge**.
3. In your phone automation (for example the iPhone Shortcut that runs on the
   Paytm notification), send a POST request to
   `https://streaming-pc.tail-abc12.ts.net/api/bridge/paytm` with the header
   `Authorization: Bearer <token from the Paytm bridge page>` and the JSON body
   `{"text": "<notification text>"}`.
4. Start a stream session and send yourself a small test tip.

Because the URL never changes, you only ever edit the automation once.

**Optional, older route:** a bank-SMS Shortcut can still POST to
`https://streaming-pc.tail-abc12.ts.net/api/bridge/credit` with
`Authorization: Bearer <BRIDGE_TOKEN from .env>` (see `docs/IPHONE.md`).

---

## Demo mode (port 8766)

For the sandbox:

    Setup_Tailscale_URL.bat --demo --port 8766

This writes `DEMO_PUBLIC_BASE_URL` instead, keeping your live URL intact.

Note: a free Tailscale account can only Funnel one port per device. If you
want BOTH demo and live reachable publicly at the same time, stop one Funnel
before starting the other with `tailscale funnel reset`.

---

## Checking the current public URL

    Setup_Tailscale_URL.bat --only-url

Or from PowerShell:

    tailscale funnel status

---

## Stopping public exposure

Since 1.6.5, AcePressure turns Funnel back on every time it starts in live
mode (Start.bat, or the AcePressure Tipping task at sign-in). To take your
tip page off the internet, first add `TAILSCALE_AUTO_FUNNEL=false` to
`.env`, then close AcePressure (or end the task) and run:

    tailscale funnel reset

AcePressure keeps working on this PC; it just stops being reachable from the
public internet. To share it again, remove that line and restart AcePressure,
or run `Setup_Tailscale_URL.bat`.

---

## Troubleshooting

**"HTTPS not enabled for your tailnet"** — See step 2 above. One-time admin
console flip.

**"Funnel not available"** — Make sure you're on the free Personal plan.
Tailscale Funnel is available to all plans including free.

**The URL loads but shows "Service not configured"** — AcePressure isn't
running yet. Double-click `Start.bat`.

**My phone automation gets 401** — The Paytm bridge token was rotated, and
rotating also switches the bridge off. Put the newest token from `/admin/paytm`
in the automation's `Authorization: Bearer …` header (it is shown only once;
generate another if you lost it) and click **Enable bridge** again. On the older
SMS route, `/api/bridge/credit` uses `BRIDGE_TOKEN` from `.env`: after
`scripts/manage.py rotate-bridge`, restart AcePressure and re-copy the new value.

**The Funnel URL hasn't survived a reboot** — Funnel stays on across reboots
unless you run `tailscale funnel reset`, and since 1.6.5 starting AcePressure
turns it back on. If Windows restarted and the service didn't auto-start, open
Services → Tailscale → set Startup type to Automatic.

**Key expiry: the link stopped working after months** — Tailscale signs a PC
out every 180 days unless key expiry is off, and Funnel stops with it. Sign in
again from the Tailscale icon, then turn it off for good (free):
login.tailscale.com → Machines → this PC → ⋯ → **Disable key expiry**.

**The dashboard says viewers can't reach your tip link** (1.6.4) — every minute
AcePressure asks Tailscale on this PC whether it is signed in, connected and
online, and whether Funnel still sends your tip link to AcePressure. The
message names the fix. It also warns 14 days before the sign-in expires. It
only asks the Tailscale program on this PC and sends nothing anywhere.

**Something feels slow** — Funnel adds minimal latency (traffic goes through
Tailscale's edge, which is well-provisioned). If your home upload is slow,
that will be the bottleneck, not Funnel. QR + a simple HTTPS tip page is
tiny; this is not a bandwidth-heavy use case.

---

## Fallback options (also free)

If Tailscale Funnel doesn't fit:

- **`zrok` by OpenZiti** — static reserved subdomain, free. See <https://zrok.io>.
- **`serveo.net`** — SSH-based tunnels with reserved names, free, no account. Can be flaky.
- **`localtunnel`** with `--subdomain acepressure` — free, but shows a one-time
  "friendly" interstitial on first visit per IP.

For paid-but-branded routes (your own domain):

- **Cloudflare Named Tunnel** + ~$10/yr domain — see `config/cloudflared.example.yml` and `docs/DEPLOYMENT.md`.
- **ngrok paid** — $8-20/month, removes URL rotation and warning page.

For most solo streamers, Tailscale Funnel is the right call.
