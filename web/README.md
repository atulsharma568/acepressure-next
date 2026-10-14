# AcePressure Next frontend

This is the first migration slice of the AcePressure UI. It is a Next.js 16 / React 19 App Router frontend with Tailwind CSS 4, a small local React Bits-style `LiveSignal` component, GSAP for restrained entrance motion, and Lenis for optional page scrolling.

## What it owns

- The public `/` and `/tip/acepressure` tipping page.
- Amount, supporter identity, message, TTS voice and soundboard selection.
- Exact-amount UPI checkout, QR display and status polling.
- A warm editorial visual system based on AcePressure's existing identity rather than a template hero or decorative card grid.

## What it deliberately does not own yet

The Flask/Waitress service remains the source of truth for payment creation, paise allocation, bank/Paytm verification, moderation, TTS synthesis, alert queues and OBS routes. The Next server proxies `/api/*` and `/media/*` to that service. This keeps the working 1.6.7 integrations intact while the public UI is migrated.

The current `/admin`, `/overlay/*`, bridge and OBS URLs are not replaced by this first slice. A later dashboard migration can reuse the same typed API boundary without moving payment logic into browser code.

## Local development

From this directory (or run `Install_Web.bat` from the package root):

```powershell
npm install
Copy-Item env.example .env.local
npm run dev
```

Start the existing AcePressure server first. By default the Next rewrite targets `http://127.0.0.1:8765`; set `ACEPRESSURE_API_URL` in `.env.local` for demo mode or another local port.

Checks:

```powershell
npm run typecheck
npm run lint
npm run build
```

The page can be run beside the old Flask page during acceptance testing. Keep the old public route and OBS Browser Sources unchanged until the new route has passed the exact payment, review, alert and mobile checks.

For a final Windows installation, Node.js 20 or newer is required. `Install_Web.bat` uses the committed `package-lock.json` and `npm ci`, then creates `.env.local` from the safe local example. `Start_Web.bat` starts the Next development server on port 3000. The existing `Install.bat` still installs the Flask runtime separately.
