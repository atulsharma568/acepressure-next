# Next.js frontend migration

## Why this is staged

AcePressure 1.6.7 already has sensitive, tested behavior around exact paise allocation, payment review, TTS moderation and OBS delivery. The new frontend must not silently recreate those rules in JavaScript. The first migration therefore changes the public UI only and keeps the Flask service as the payment/TTS/OBS boundary.

The new app is under `web/` and is intentionally separate from the existing templates and static files. It uses the existing public JSON endpoints through same-origin Next rewrites:

- `GET /api/public/config`
- `GET /api/public/top`
- `GET /api/public/soundboard`
- `POST /api/public/tips`
- `GET /api/public/tips/:id`
- `GET /api/public/tips/:id/qr`

The existing `/admin`, `/overlay/*`, bridge and OBS routes are left untouched. That is the rollback: stop Next and return viewers to the Flask route.

## Tailscale Funnel boundary

The current Tailscale setup serves the existing Flask process:

```text
https://<this-pc>.ts.net/  ->  http://127.0.0.1:8765
```

The separate Next setup keeps Flask on `8765` as the backend and makes Next on
`3000` the public front door. Next proxies `/api/*`, `/media/*`, `/static/*`,
`/admin`, `/obs/*`, `/overlay/*` and `/health` back to Flask. This preserves the
dashboard, payment bridge and OBS routes at the same public origin.

Do not point Funnel at `3000` until `Start_Next.bat` is running and the local
route smoke checks pass. `Setup_Tailscale_Next.bat` performs that switch. The
old `Setup_Tailscale_URL.bat --port 8765` remains the rollback.

The private `.env` used by the separate setup has `PUBLIC_TUNNEL_PORT=3000`.
That keeps AcePressure's Tailscale watcher aligned with the Next front door;
the Flask backend itself remains on `PORT=8765`.

## Run beside 1.6.7

1. Start AcePressure in demo mode or live mode exactly as before.
2. Install Node.js 20 or newer on Windows if it is not already present.
3. Run `Install_Web.bat` from the package root. It runs `npm ci` from the committed lockfile and creates the local `.env.local` file.
4. Set `ACEPRESSURE_API_URL` to the local Flask origin if it is not the default `http://127.0.0.1:8765`.
5. Run `Start_Web.bat` for local UI staging, or `Start_Next.bat` for the two-process cutover setup, and open `http://localhost:3000/`.
6. In demo mode, create a tip and simulate it in the existing dashboard. In live mode, use a low-value device test and the existing payment verification checklist.

Do not point OBS Browser Sources at the Next page in this slice. Existing overlay URLs remain served by Flask and continue to use the tested 1.6.7 alert delivery path.

## Design constraints

- No new payment provider, client-side verification or private token in a public build.
- Whole-rupee display amount, exact requested paise and review messaging remain server-defined.
- Motion is limited to page entrance and optional scrolling; checkout does not depend on animation.
- One small status component is used as a brand cue. The page does not use a component gallery, generated dashboard cards or a full-screen gradient hero.

## Cutover checklist

Before replacing the current public link, verify in demo mode and then with a real low-value test:

- mobile form validation and keyboard flow;
- minimum/maximum amount and identifying paise suffix;
- QR recipient and exact amount;
- duplicate/retry behavior and review state;
- TTS voice/message settings and moderation;
- soundboard minimums and default fallback;
- verified alert appears in both existing OBS channels;
- old Flask route remains available for rollback.

PostgreSQL is also staged separately. See `docs/POSTGRES_MIGRATION.md`; the shadow import does not change the Flask runtime until row-level verification and a deliberately scheduled cutover are complete.
