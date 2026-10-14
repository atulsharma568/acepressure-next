"""Guide the user through enabling Tailscale Funnel for a FREE static public URL.

Zero-cost replacement for ngrok and Cloudflare Tunnel: no domain purchase, no
account warning pages, no per-session random URLs. The streamer's phone
automation that verifies tips can target the stable URL forever.

What this script does (idempotent — safe to re-run):
  1. Checks whether `tailscale` is installed. If not, prints OS-specific install hints.
  2. Checks whether this machine is logged into a tailnet (BackendState "Running").
     If not, runs `tailscale up` and asks the user to complete the browser flow.
  3. Starts a Funnel on the AcePressure port (defaults to 8765 live, override with --port).
     Tailscale's own output is shown as it happens, so a login.tailscale.com
     approval link (HTTPS certificates / Funnel) is never hidden.
  4. Confirms with `tailscale funnel status` that Funnel is on for this PC's DNS name.
     Only then does it write the URL into .env as PUBLIC_BASE_URL, with a
     timestamped .env backup first. Otherwise .env is left untouched.
  5. Prints the next steps: restart AcePressure, UPI details, the Paytm bridge
     at <base>/api/bridge/paytm, the phone automation and a small test tip.

This script never calls out to anything other than the local Tailscale CLI and
AcePressure's own /health page on this PC.
It does NOT store any credentials — Tailscale handles its own auth.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from acepressure.startup import running_instance


def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def run(args, check=True, capture=True):
    kw = dict(check=check)
    if capture:
        kw.update(capture_output=True, text=True)
    return subprocess.run(args, **kw)


def install_hints():
    print()
    print('Tailscale is not installed. Install it (one-time, free for personal use):')
    print()
    if sys.platform == 'darwin':
        print('   macOS (Homebrew):   brew install --cask tailscale')
        print('   macOS (App Store):  https://apps.apple.com/app/tailscale/id1475387142')
    elif sys.platform.startswith('linux'):
        print('   Linux:              curl -fsSL https://tailscale.com/install.sh | sh')
    elif os.name == 'nt':
        print('   Windows:            https://tailscale.com/download/windows')
        print('   or with winget:     winget install Tailscale.Tailscale')
    else:
        print('   See:                https://tailscale.com/download')
    print()
    print('After installing, re-run this script.')


def tailscale_status() -> dict:
    """`tailscale status --json` as a dict, or {} when Tailscale cannot report it."""
    r = run(['tailscale', 'status', '--json'], check=False)
    try:
        data = json.loads(r.stdout or '')
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def ensure_logged_in():
    if tailscale_status().get('BackendState') == 'Running':
        print('Already logged into tailnet.')
        return
    print('Not logged into a tailnet yet. Running `tailscale up`…')
    print('A browser window will open — complete the sign-in and come back here.', flush=True)
    subprocess.run(['tailscale', 'up'], check=True)


def start_funnel(port: int) -> int:
    """Start a background Funnel for the local port; Tailscale's output goes straight to the console."""
    print(f'Starting Tailscale Funnel on port {port}…', flush=True)  # flushed, so our hints stay above Tailscale's output
    # Modern CLI syntax: `tailscale funnel --bg <port>` sets up :443 → http://127.0.0.1:<port>
    # Not captured: the first time, Tailscale prints a login.tailscale.com approval link and waits for it.
    return run(['tailscale', 'funnel', '--bg', str(port)], check=False, capture=False).returncode


def public_url_from_status(status: dict) -> str:
    """The public URL from this PC's canonical DNS name in `tailscale status --json`, or '' if it is missing."""
    name = str(((status or {}).get('Self') or {}).get('DNSName') or '').rstrip('.').lower()
    return 'https://' + name if name else ''


def funnel_confirmed(output: str, host: str) -> bool:
    """True when `tailscale funnel status` lists the host, other than as "tailnet only"."""
    host = (host or '').lower()
    return bool(host) and any(host in line and 'tailnet only' not in line for line in (output or '').lower().splitlines())


def next_steps(url: str, port: int, running: bool) -> str:
    """The steps after Funnel is on, Paytm bridge first. `running`: AcePressure answers on this PC (port 8766 is the demo)."""
    start = 'Start_Demo.bat' if port == 8766 else 'Start.bat'
    lines = ['Next steps:']
    if running:
        lines.append('  AcePressure is running with the OLD address right now. Do step 1 now.')
    lines += [
        f'  1. Restart AcePressure: close its window (or end the AcePressure Tipping task), then double-click {start}.',
        '  2. Admin > Settings: enter your UPI ID and payee name.',
        f'  3. Open {url}/admin/paytm: Generate token, enter your bank marker exactly as Paytm shows it, click Enable bridge.',
        f'  4. Phone automation: POST {url}/api/bridge/paytm with header Authorization: Bearer <token from the Paytm bridge page> and JSON {{"text": "<notification text>"}}.',
        '  5. Start a stream session and send yourself a small test tip.',
        '',
        f'Optional older route: bank SMS -> {url}/api/bridge/credit with BRIDGE_TOKEN from .env (docs/IPHONE.md).',
    ]
    return '\n'.join(lines)


def backup_env_file(env_path: Path):
    if not env_path.exists():
        return
    stamp = _dt.datetime.now(_dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup_dir = env_path.parent / 'configuration-backups' / stamp
    backup_dir.mkdir(parents=True, exist_ok=True)
    (backup_dir / '.env').write_text(env_path.read_text(encoding='utf-8'), encoding='utf-8')
    print(f'Backed up .env to configuration-backups/{stamp}/.env')


def update_env_public_url(url: str, demo: bool = False, env_path: Path = ROOT / '.env', public_port: int | None = None):
    if not env_path.exists():
        print('No .env found. Run Install.bat (Windows) or scripts/bootstrap.py (any OS) first.')
        return
    backup_env_file(env_path)
    key = 'DEMO_PUBLIC_BASE_URL' if demo else 'PUBLIC_BASE_URL'
    lines = env_path.read_text(encoding='utf-8').splitlines()
    pattern = re.compile(rf'^{re.escape(key)}\s*=')
    found = False
    out_lines = []
    for line in lines:
        if pattern.match(line):
            out_lines.append(f'{key}={url}')
            found = True
        else:
            out_lines.append(line)
    if not found:
        out_lines.append(f'{key}={url}')
    # Newer templates carry this optional key so a Next front-door setup can
    # keep Flask's Tailscale watcher on the same public port. Older .env files
    # are left byte-compatible and keep their established behavior.
    if public_port is not None:
        for i, line in enumerate(out_lines):
            if line.startswith('PUBLIC_TUNNEL_PORT='):
                out_lines[i] = f'PUBLIC_TUNNEL_PORT={public_port}'
                break
    if not demo:
        # Live mode needs secure cookies — flip COOKIE_SECURE on if present.
        for i, line in enumerate(out_lines):
            if line.startswith('COOKIE_SECURE='):
                out_lines[i] = 'COOKIE_SECURE=true'
                break
        else:
            out_lines.append('COOKIE_SECURE=true')
    env_path.write_text('\n'.join(out_lines) + '\n', encoding='utf-8')
    try:
        os.chmod(env_path, 0o600)
    except Exception:
        pass
    print(f'Wrote {key}={url} to .env')


def main(argv=None, env_path: Path = ROOT / '.env'):
    p = argparse.ArgumentParser(description='Enable Tailscale Funnel for a free, static public URL for AcePressure.')
    p.add_argument('--port', type=int, default=8765, help='Local port AcePressure runs on (default 8765 live, 8766 demo).')
    p.add_argument('--demo', action='store_true', help='Set DEMO_PUBLIC_BASE_URL instead of PUBLIC_BASE_URL.')
    p.add_argument('--only-url', action='store_true', help='Just print the current Funnel URL without reconfiguring.')
    args = p.parse_args(argv)

    if not have('tailscale'):
        install_hints()
        sys.exit(1)

    if args.only_url:
        r = run(['tailscale', 'funnel', 'status'], check=False)
        print(r.stdout or r.stderr)
        return

    ensure_logged_in()
    print()
    print('If Tailscale prints a login.tailscale.com link, open it in your browser, approve HTTPS certificates / Funnel, then come back here.')
    start_funnel(args.port)
    url = public_url_from_status(tailscale_status())
    if not url:
        print()
        print("Tailscale did not report this PC's name. Check that Tailscale is signed in, then run Setup_Tailscale_URL.bat again.")
        sys.exit(2)
    host = url.removeprefix('https://')
    r = run(['tailscale', 'funnel', 'status'], check=False)
    if r.returncode != 0 or not funnel_confirmed(r.stdout, host):
        # Leave .env alone unless Tailscale confirms: a half-configured address is worse than the old one.
        print()
        print(f'Tailscale did not confirm that Funnel is on for {host}. If a login.tailscale.com link appeared above, open it to approve, then run Setup_Tailscale_URL.bat again.')
        print('If Tailscale said a foreground listener already exists, close the window where `tailscale funnel` is running, then run Setup_Tailscale_URL.bat again.')
        sys.exit(2)
    print()
    # Keep this Windows-console line ASCII: the default cp1252 code page cannot
    # print the check-mark and must not crash after Funnel has already started.
    print(f'Public URL: {url}')
    update_env_public_url(url, demo=args.demo, env_path=env_path, public_port=args.port)
    print()
    print(next_steps(url, args.port, running_instance('127.0.0.1', args.port) == 'acepressure'))
    print()
    print('To stop sharing publicly: add TAILSCALE_AUTO_FUNNEL=false to .env, close AcePressure, then run `tailscale funnel reset`.')
    print('(Without that line, AcePressure turns Funnel back on the next time it starts in live mode.)')


if __name__ == '__main__':
    main()
