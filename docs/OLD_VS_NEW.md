# AcePressure old vs new setup

The new setup is a frontend migration, not a claim that every server has been
rewritten in one language. The payment and OBS parts are deliberately kept
stable while the public page changes.

| Area | Existing 1.6.7 setup | Separate AcePressure-Next setup |
|---|---|---|
| Public tipping page | Flask/Jinja HTML + vanilla JavaScript | Next.js 16 + React 19 + TypeScript |
| Styling | Static CSS files | Tailwind CSS 4 plus authored CSS |
| Motion | Existing vanilla effects | GSAP entrance motion + optional Lenis scrolling |
| Small branded component | No React component tree | One small `LiveSignal` React component |
| Admin dashboard | Flask/Jinja + existing JavaScript | Still the tested Flask dashboard, proxied through Next |
| Payments and exact paise matching | Python/Flask + SQLite | Same Python/Flask service + same SQLite data |
| Payment bridge and verification | Existing Python routes | Same routes; no client-side verification added |
| TTS and moderation | Existing Python services | Same services and settings |
| OBS overlays and Browser Sources | Existing Flask overlay routes | Same routes, reached through Next rewrites |
| Public network entry | Tailscale Funnel -> Flask `:8765` | Tailscale Funnel -> Next `:3000` -> Flask `:8765` |
| Database | SQLite | PostgreSQL shadow importer is available, but SQLite remains live |

## What moves now

The audience-facing page moves to React/Next. Its browser requests still go to
the existing public JSON API, so exact requested paise, payment expiry, review,
TTS choices, soundboard rules and alert status remain server-controlled.

## What does not move yet

Do not describe this release as a full Python-to-Node rewrite. The backend,
admin, payment verification, TTS, database runtime and OBS delivery remain the
working 1.6.7 Python system. PostgreSQL is a separate shadow migration and is
not enabled by `Start_Next.bat`.

## Rollback

The original folder and ZIP are preserved. To roll back the public route:

1. Stop the new Next setup.
2. Start the original AcePressure folder on Flask port `8765`.
3. Run the original `Setup_Tailscale_URL.bat --port 8765` if Funnel currently points to `3000`.

The new folder contains a copy of the current database and `.env` only for the
local cutover. The clean ZIP never contains those private/runtime files.
