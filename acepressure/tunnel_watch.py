"""Can viewers reach the tip link? (1.6.4) A background check of Tailscale Funnel once a minute, shown on the dashboard
and in the OBS dock. Advisory only: it never pauses tips. It asks the local Tailscale program, in a hidden window, and
sends nothing anywhere. Other tunnels (ngrok, cloudflared) are not checked.
1.6.5: in live mode it also turns Funnel on as AcePressure starts, when Funnel is off (ensure_funnel), and takes over
from an open `tailscale funnel` window once that window closes.
"""
import json, logging, math, os, re, shutil, subprocess, threading, time
from datetime import datetime
from urllib.parse import urlparse

INTERVAL = 60
WARN_DAYS = 14
KEY_EXPIRY_FIX = 'login.tailscale.com → Machines → this PC → ⋯ → Disable key expiry (free)'
START_TIMEOUT = 25  # `tailscale funnel --bg` waits for an approval in the browser the first time: give up and show the link
APPROVE = re.compile(r'https://login\.tailscale\.com/[^\s"\'<>]+')
PENDING_INTERVAL = 15  # seconds between rounds while Funnel still has to be turned on (1.6.5)
WAITING = ('Tailscale on this PC isn’t answering (not running, or still starting), so viewers may not reach your tip link. '
           'Open Tailscale and check it says Connected: AcePressure turns Funnel on, if needed, as soon as it answers.')


def tailscale_cli():
    """The Tailscale program, or None when it isn't installed."""
    found = shutil.which('tailscale')
    if found:
        return found
    if os.name == 'nt':
        for base in (os.environ.get('ProgramFiles') or r'C:\Program Files', os.environ.get('ProgramFiles(x86)') or ''):
            path = os.path.join(base, 'Tailscale', 'tailscale.exe') if base else ''
            if path and os.path.isfile(path):
                return path
    return None


def _runner(cli):
    def run(args):
        kw = dict(capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=10)
        if os.name == 'nt':
            kw['creationflags'] = subprocess.CREATE_NO_WINDOW  # no console window flashing up every minute
        return subprocess.run([cli, *args], **kw).stdout or ''
    return run


def _starter(cli):
    """Runs a Tailscale command that changes something, in a hidden window, and returns everything it printed. After
    START_TIMEOUT seconds it is stopped, and what it printed so far (an approval link, say) is returned."""
    text = lambda x: x.decode('utf-8', 'replace') if isinstance(x, bytes) else (x or '')

    def start(args):
        kw = dict(capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=START_TIMEOUT)
        if os.name == 'nt':
            kw['creationflags'] = subprocess.CREATE_NO_WINDOW
        try:
            r = subprocess.run([cli, *args], **kw)
            return text(r.stdout) + text(r.stderr)
        except subprocess.TimeoutExpired as e:  # its output arrives as bytes here, whatever text= says
            return text(e.stdout) + text(e.stderr)
        except OSError:
            return ''
    return start


def _when(value):
    """An RFC 3339 time from Tailscale ("2027-04-10T10:00:00.123456789Z") as epoch seconds, or None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(re.sub(r'\.\d+', '', value).replace('Z', '+00:00')).timestamp()
    except ValueError:
        return None


def _ours(proxy, port):
    """True when a Tailscale proxy target is AcePressure on this PC: http://127.0.0.1:<port>, localhost or a bare port."""
    p = str(proxy or '').strip()
    if re.fullmatch(r'\d+', p):
        return int(p) == port
    try:
        u = urlparse(p if '://' in p else 'http://' + p)
        return u.port == port and (u.hostname or '').lower() in ('127.0.0.1', 'localhost', '::1')
    except ValueError:
        return False


def _serve_config(run):
    """`tailscale funnel status --json` as a dict, or None when Tailscale can't give one."""
    try:
        cfg = json.loads(run(['funnel', 'status', '--json']) or 'null')
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return cfg if isinstance(cfg, dict) else None


def _configs(cfg):
    """The serve configs in it: the one `--bg` keeps, then one for each open `tailscale funnel` window, which Tailscale
    keeps under Foreground until that window closes (1.6.5)."""
    fg = cfg.get('Foreground') if isinstance(cfg.get('Foreground'), dict) else {}
    return [cfg] + [c for c in fg.values() if isinstance(c, dict)]


def _at(table, key):
    """table[key] for Tailscale's "host:port" keys, ignoring capitals."""
    return next((v for k, v in table.items() if str(k).lower() == key), None) if isinstance(table, dict) else None


def _handlers(cfg, key):
    web = _at(cfg.get('Web'), key)
    return web.get('Handlers') if isinstance(web, dict) and isinstance(web.get('Handlers'), dict) else {}


def funnel_state(run, host, port):
    """'on', 'fg' (only an open `tailscale funnel` window keeps it on, until that window closes: 1.6.5), 'off',
    'port:<target>' (Funnel serves something else) or None when Tailscale can't say."""
    cfg = _serve_config(run)
    if cfg is not None:
        key = host + ':443'  # the tip link has no port, and Tailscale opens Funnel per host:port
        found = [(i == 0, [h['Proxy'] for h in _handlers(c, key).values() if isinstance(h, dict) and h.get('Proxy')])
                 for i, c in enumerate(_configs(cfg)) if _at(c.get('AllowFunnel'), key)]  # (kept with --bg?, proxy targets)
        for kept in (True, False):
            if any(k == kept and (not proxies or any(_ours(x, port) for x in proxies)) for k, proxies in found):
                return 'on' if kept else 'fg'
        other = next((x for _, proxies in found for x in proxies), None)
        return 'port:' + str(other) if other else 'off'
    try:  # older Tailscale without --json: "https://name.ts.net (Funnel on)" or "(tailnet only)"
        text = (run(['funnel', 'status']) or '').lower()
    except (OSError, subprocess.SubprocessError):
        return None
    lines = [line for line in text.splitlines() if host in line]
    if any('funnel on' in line for line in lines):
        return 'on'
    if lines or 'no serve config' in text:
        return 'off'
    return None


def _serves_elsewhere(run, host, port):
    """What `tailscale serve` already shares at https://<host>/ inside your tailnet, other than AcePressure, or ''.
    Funnel opens all of <host>:443 to the internet, so turning it on would make that public too, or replace it (1.6.5)."""
    cfg, key = _serve_config(run), host + ':443'
    for c in _configs(cfg) if cfg else []:
        fwd = _at(c.get('TCP'), '443')
        if isinstance(fwd, dict) and fwd.get('TCPForward'):
            return str(fwd['TCPForward'])
        for mount, h in _handlers(c, key).items():
            if isinstance(h, dict) and not (h.get('Proxy') and _ours(h['Proxy'], port)):
                return str(h.get('Proxy') or h.get('Path') or ('a text page' if 'Text' in h else 'a redirect' if 'Redirect' in h else mount))
    return ''


def check(public_url, port, run=None, clock=time.time):
    """{'state': 'ok'|'warn'|'bad', 'message', 'checked'} for a Tailscale Funnel tip link, or None when the link isn't
    a Tailscale one or Tailscale can't say (not installed, starting up, unreadable): then the dashboard shows nothing."""
    host = (urlparse(public_url or '').hostname or '').lower()
    if not host.endswith('.ts.net'):
        return None
    if run is None:
        cli = tailscale_cli()
        if not cli:
            return None
        run = _runner(cli)
    try:
        status = json.loads(run(['status', '--json']) or 'null')
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if not isinstance(status, dict):
        return None
    t = int(clock())
    out = lambda state, message: {'state': state, 'message': message, 'checked': t}
    me = status.get('Self') if isinstance(status.get('Self'), dict) else {}
    backend = status.get('BackendState')
    if backend in ('NeedsLogin', 'NeedsMachineAuth'):
        return out('bad', 'Viewers can’t reach your tip link: Tailscale on this PC is signed out. Open Tailscale and sign in, '
                          'then turn off key expiry so it doesn’t happen again: ' + KEY_EXPIRY_FIX + '.')
    if backend == 'Stopped':
        return out('bad', 'Viewers can’t reach your tip link: Tailscale is disconnected on this PC. Open Tailscale and click Connect.')
    if backend != 'Running':
        return None  # starting up, or a state this version doesn't know: say nothing yet
    if me.get('Online') is False:
        return out('bad', 'Viewers can’t reach your tip link: this PC is offline in Tailscale. Check the internet connection.')
    name = str(me.get('DNSName') or '').rstrip('.').lower()
    if name and name != host:
        return out('warn', f'Your tip link uses {host}, but Tailscale calls this PC {name}. Run Setup_Tailscale_URL.bat again.')
    funnel = funnel_state(run, host, port)
    if funnel == 'off':
        other = _serves_elsewhere(run, host, port)
        if other:
            return out('bad', f'Viewers can’t reach your tip link: Tailscale Funnel is off, and Tailscale shares {other} at https://{host}/ '
                              'inside your tailnet. Turning Funnel on would make that public too, so move or remove that share first.')
        return out('bad', 'Viewers can’t reach your tip link: Tailscale Funnel is off. Run Setup_Tailscale_URL.bat again.')
    if funnel and funnel.startswith('port:'):
        return out('bad', f'Viewers can’t reach your tip link: Tailscale Funnel sends visitors to {funnel[5:]}, not to AcePressure '
                          f'on port {port}. Run Setup_Tailscale_URL.bat again.')
    expiry = _when(me.get('KeyExpiry'))
    if expiry is not None and expiry - t <= WARN_DAYS * 86400:
        days = max(0, math.ceil((expiry - t) / 86400))
        when = 'today' if days == 0 else 'tomorrow' if days == 1 else f'in {days} days'
        return out('warn', f'This PC’s Tailscale sign-in expires {when}, and your tip link stops working then. '
                           f'Turn off key expiry: {KEY_EXPIRY_FIX}.')
    if funnel == 'fg':
        return out('ok', 'Tip link reachable through Tailscale Funnel, from an open `tailscale funnel` window.')
    return out('ok', 'Tip link reachable through Tailscale Funnel.') if funnel == 'on' else None


def auto_funnel(app):
    """1.6.5: AcePressure turns Funnel on as it starts in live mode (demo mode has its own port). TAILSCALE_AUTO_FUNNEL=false
    in .env switches that off."""
    return not app.config.get('DEMO_MODE') and os.getenv('TAILSCALE_AUTO_FUNNEL', 'true').strip().lower() not in ('0', 'false', 'no', 'off')


def ensure_funnel(public_url, port, run=None, start=None):
    """1.6.5: turn Tailscale Funnel on for a Tailscale tip link when it is off, as Setup_Tailscale_URL.bat does
    (`tailscale funnel --bg <port>`, which stays on until `tailscale funnel reset`). A Funnel that sends visitors elsewhere
    (demo mode on its own port, say), another program shared at the tip link's address, and a tip link for another PC are
    left alone.

    Returns (done, level, line). done=False: try again next round, because Tailscale isn't ready (starting, signed out,
    disconnected, offline) or an open `tailscale funnel` window keeps Funnel on for now; check() tells the dashboard what to
    do meanwhile. line: what to write to the AcePressure window, or None."""
    host = (urlparse(public_url or '').hostname or '').lower()
    if not host.endswith('.ts.net'):
        return True, None, None
    if run is None:
        cli = tailscale_cli()
        if not cli:
            return True, 'warning', (f'Tailscale isn\'t installed on this PC, so viewers can\'t reach https://{host}/. Install it free '
                                     'from https://tailscale.com/download/windows, then run Setup_Tailscale_URL.bat.')
        run, start = _runner(cli), _starter(cli)
    try:
        status = json.loads(run(['status', '--json']) or 'null')
    except (OSError, subprocess.SubprocessError, ValueError):
        return False, None, None
    me = status.get('Self') if isinstance(status, dict) and isinstance(status.get('Self'), dict) else {}
    if not isinstance(status, dict) or status.get('BackendState') != 'Running' or me.get('Online') is False:
        return False, None, None
    name = str(me.get('DNSName') or '').rstrip('.').lower()
    if name and name != host:
        return True, None, None  # the tip link names another PC: check() warns about it
    link = f'https://{host}/'
    state = funnel_state(run, host, port)
    if state is None:
        return False, None, None  # Tailscale can't say right now: ask again next round rather than guess
    if state == 'on':
        return True, 'info', f'Tailscale Funnel is on: viewers reach your tip page at {link}'
    if state == 'fg':  # Tailscale 1.92+ refuses --bg while that window is open: take over once it closes
        return False, 'info', (f'Tailscale Funnel is on from an open `tailscale funnel` window: viewers reach your tip page at {link}. '
                               f'You can close that window: AcePressure then keeps Funnel on by itself, within {PENDING_INTERVAL} seconds.')
    if state.startswith('port:'):
        return True, None, None  # Funnel sends visitors elsewhere, on purpose or by mistake: check() says where
    other = _serves_elsewhere(run, host, port)
    if other:
        return True, 'warning', (f'Tailscale already shares {other} at {link} inside your tailnet, so AcePressure left Funnel off: '
                                 'Funnel would make that public too. Move or remove that share, then restart AcePressure.')
    output = start(['funnel', '--bg', str(port)])
    if funnel_state(run, host, port) == 'on':
        return True, 'info', f'Turned Tailscale Funnel on: viewers reach your tip page at {link}'
    if 'foreground listener already exists' in (output or '').lower():
        return False, 'warning', ('A `tailscale funnel` window is open, so Tailscale won\'t let AcePressure turn Funnel on in the background. '
                                  f'Close that window: AcePressure turns Funnel on within {PENDING_INTERVAL} seconds.')
    approve = APPROVE.search(output or '')
    if approve:
        return True, 'warning', f'Tailscale needs your OK once before Funnel can start. Open {approve.group(0)} and approve, then restart AcePressure.'
    said = next((x.strip() for x in (output or '').splitlines() if x.strip() and not x.strip().lower().startswith('warning:')), '')
    return True, 'warning', 'Couldn\'t turn Tailscale Funnel on' + (f' (Tailscale said: {said[:160]})' if said else '') + '. Run Setup_Tailscale_URL.bat.'


def _console(text):
    """A line the Windows console can show whatever its code page."""
    plain = text.replace('’', "'").replace('→', '->').replace('⋯', '...')
    return plain.encode('ascii', 'replace').decode('ascii')


class TunnelWatch:
    """Runs check() every INTERVAL seconds in a daemon thread. The latest result is app.extensions['ace_tunnel'], and a
    change to or from a problem is written to the AcePressure window and the server log. With ensure (1.6.5, live mode
    unless TAILSCALE_AUTO_FUNNEL=false), Funnel is turned on first, retried every PENDING_INTERVAL seconds while Tailscale
    isn't ready or a `tailscale funnel` window keeps it on, then never again until the next start: a Funnel you switch off
    after that stays off. While it is still retrying, a Funnel that goes off (that window closes, or `tailscale funnel
    reset`) is turned on in the background."""

    def __init__(self, app, port=None, interval=INTERVAL, ensure=None):
        self.app, self.port, self.interval = app, port or int(os.getenv('PORT', '8765')), interval
        self.ensure = auto_funnel(app) if ensure is None else ensure

    def start(self):
        threading.Thread(target=self._loop, name='acepressure-tunnel-watch', daemon=True).start()
        return self

    def _loop(self):
        log, last, said = logging.getLogger('acepressure.tunnel'), None, None
        while True:
            pending = warned = False
            if self.ensure:
                try:
                    done, level, line = ensure_funnel(self.app.config.get('PUBLIC_BASE_URL', ''), self.port)
                except Exception:
                    done, level, line = True, None, None
                if line and line != said:  # an open `tailscale funnel` window gives the same line every round: say it once
                    log.log(logging.WARNING if level == 'warning' else logging.INFO, 'Tip link: %s', _console(line))
                    said, warned = line, level == 'warning'
                self.ensure = pending = not done
            try:
                result = check(self.app.config.get('PUBLIC_BASE_URL', ''), self.port)
            except Exception:
                result = None
            if pending and result is None:  # check() stays quiet while Tailscale doesn't answer: say so (1.6.5)
                result = {'state': 'warn', 'message': WAITING, 'checked': int(time.time())}
            self.app.extensions['ace_tunnel'] = result
            state = result and result['state']
            seen = 'wait' if result is not None and result['message'] == WAITING else state  # a warning after it is still said
            if warned and state == 'bad':
                last = seen  # the line just written already says what to do
            if seen != last and (seen in ('bad', 'warn', 'wait') or last in ('bad', 'warn', 'wait')):
                log.log(logging.INFO if state == 'ok' else logging.WARNING, 'Tip link: %s',  # reachable again is good news (1.6.6)
                        _console(result['message'] if result else 'The tip link check is unavailable.'))
            last = seen
            time.sleep(min(PENDING_INTERVAL, self.interval) if self.ensure else self.interval)
