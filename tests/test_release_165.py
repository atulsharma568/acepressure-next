"""1.6.5 test builds and 1.6.6: as AcePressure starts in live mode, it turns Tailscale Funnel on for the tip link when Funnel is off."""
import json
import logging
import subprocess
import types
from pathlib import Path

import pytest

from acepressure import tunnel_watch
from acepressure.domain import now
from acepressure.text_filters import name_filter
from acepressure.tunnel_watch import PENDING_INTERVAL, WAITING, check, ensure_funnel

ROOT = Path(__file__).resolve().parents[1]
HOST = 'atul.example.ts.net'
URL = 'https://' + HOST + '/'
ME = {'Online': True, 'DNSName': HOST + '.', 'KeyExpiry': '2099-01-01T00:00:00Z'}
RUNNING = {'BackendState': 'Running', 'Self': ME}
ON = {'AllowFunnel': {HOST + ':443': True}, 'Web': {HOST + ':443': {'Handlers': {'/': {'Proxy': 'http://127.0.0.1:8765'}}}}}
DEMO = {'AllowFunnel': {HOST + ':443': True}, 'Web': {HOST + ':443': {'Handlers': {'/': {'Proxy': 'http://127.0.0.1:8766'}}}}}
WINDOW = {'Foreground': {'session-1': ON}}  # `tailscale funnel 8765` typed without --bg, its window still open
APPROVAL = 'Funnel is not enabled on your tailnet.\nTo enable, visit:\n\n         https://login.tailscale.com/f/funnel?node=nAbC123\n'


class FakeTailscale:
    """Answers `status --json` and `funnel status --json` from its state; `funnel --bg <port>` turns Funnel on unless
    turns_on is False, and prints `prints`."""

    def __init__(self, status=RUNNING, funnel=None, prints='', turns_on=True):
        self.status, self.funnel, self.prints, self.turns_on, self.started = status, funnel or {}, prints, turns_on, []

    def run(self, args):
        if args == ['status', '--json']:
            return self.status if isinstance(self.status, str) else json.dumps(self.status)
        if args == ['funnel', 'status', '--json']:
            return json.dumps(self.funnel)
        raise AssertionError(args)

    def start(self, args):
        self.started.append(args)
        if self.turns_on:
            self.funnel = ON
        return self.prints


def test_funnel_off_is_turned_on_with_the_setup_command():
    ts = FakeTailscale()
    assert ensure_funnel(URL, 8765, ts.run, ts.start) == (True, 'info', f'Turned Tailscale Funnel on: viewers reach your tip page at {URL}')
    assert ts.started == [['funnel', '--bg', '8765']]  # the command Setup_Tailscale_URL.bat runs: it stays on in the background


def test_a_funnel_that_is_on_is_left_alone():
    ts = FakeTailscale(funnel=ON)
    assert ensure_funnel(URL, 8765, ts.run, ts.start) == (True, 'info', f'Tailscale Funnel is on: viewers reach your tip page at {URL}')
    assert ts.started == []


def test_a_funnel_serving_something_else_is_left_alone():
    ts = FakeTailscale(funnel=DEMO)  # demo mode on port 8766, say: the dashboard's tip link check says so
    assert ensure_funnel(URL, 8765, ts.run, ts.start) == (True, None, None) and ts.started == []


def test_the_first_time_approval_link_is_shown():
    ts = FakeTailscale(turns_on=False, prints=APPROVAL)
    done, level, line = ensure_funnel(URL, 8765, ts.run, ts.start)
    assert done and level == 'warning'
    assert line == ('Tailscale needs your OK once before Funnel can start. Open https://login.tailscale.com/f/funnel?node=nAbC123 '
                    'and approve, then restart AcePressure.')


def test_a_failure_says_what_tailscale_said():
    ts = FakeTailscale(turns_on=False, prints='\nerror: serve config denied\n')
    assert ensure_funnel(URL, 8765, ts.run, ts.start) == (
        True, 'warning', "Couldn't turn Tailscale Funnel on (Tailscale said: error: serve config denied). Run Setup_Tailscale_URL.bat.")
    silent = FakeTailscale(turns_on=False)
    assert ensure_funnel(URL, 8765, silent.run, silent.start)[2] == "Couldn't turn Tailscale Funnel on. Run Setup_Tailscale_URL.bat."


@pytest.mark.parametrize('shared, named', [
    ({'Web': {HOST + ':443': {'Handlers': {'/': {'Proxy': 'http://127.0.0.1:3000'}}}}}, 'http://127.0.0.1:3000'),
    ({'Web': {HOST + ':443': {'Handlers': {'/files/': {'Path': 'C:\\Users\\me\\Videos'}}}}}, 'C:\\Users\\me\\Videos'),
    ({'Web': {HOST + ':443': {'Handlers': {'/': {'Proxy': 'http://127.0.0.1:8765'}, '/note': {'Text': 'hi'}}}}}, 'a text page'),
    ({'TCP': {'443': {'TCPForward': '127.0.0.1:4000'}}}, '127.0.0.1:4000'),
    ({'Foreground': {'s': {'Web': {HOST + ':443': {'Handlers': {'/': {'Proxy': 'http://192.168.1.5:8765'}}}}}}}, 'http://192.168.1.5:8765'),
])
def test_another_program_shared_at_the_tip_link_is_left_alone_and_named(shared, named):
    ts = FakeTailscale(funnel=shared)  # tailnet only: Funnel would make it public, or replace it
    done, level, line = ensure_funnel(URL, 8765, ts.run, ts.start)
    assert (done, level, ts.started) == (True, 'warning', []) and f'Tailscale already shares {named} at {URL} inside your tailnet' in line
    result = check(URL, 8765, ts.run)
    assert result['state'] == 'bad' and f'Tailscale shares {named} at {URL}' in result['message']


def test_a_share_on_another_port_does_not_stop_the_tip_link():
    ts = FakeTailscale(funnel={'Web': {HOST + ':4455': {'Handlers': {'/': {'Proxy': 'http://127.0.0.1:4455'}}}},
                               'AllowFunnel': {HOST + ':8443': True}})  # an OBS remote on :4455, say; Funnel only opens :8443
    assert ensure_funnel(URL, 8765, ts.run, ts.start)[1] == 'info' and ts.started == [['funnel', '--bg', '8765']]


def test_acepressure_shared_inside_the_tailnet_is_opened_up():
    mine = FakeTailscale(funnel={'Web': {HOST + ':443': {'Handlers': {'/': {'Proxy': 'http://127.0.0.1:8765'}}}}})
    assert ensure_funnel(URL, 8765, mine.run, mine.start)[1:] == ('info', f'Turned Tailscale Funnel on: viewers reach your tip page at {URL}')
    assert mine.started == [['funnel', '--bg', '8765']]  # AcePressure shared inside the tailnet only: Funnel opens it up


def test_an_open_tailscale_funnel_window_is_left_on_and_taken_over_once_it_closes():
    ts = FakeTailscale(funnel=WINDOW)
    done, level, line = ensure_funnel(URL, 8765, ts.run, ts.start)
    assert (done, level, ts.started) == (False, 'info', [])  # Tailscale 1.92+ refuses --bg while the window is open
    assert line == (f'Tailscale Funnel is on from an open `tailscale funnel` window: viewers reach your tip page at {URL}. '
                    f'You can close that window: AcePressure then keeps Funnel on by itself, within {PENDING_INTERVAL} seconds.')
    assert check(URL, 8765, ts.run)['state'] == 'ok'  # 1.6.4 said "Funnel is off" while viewers could reach it
    ts.funnel = {}  # the window closed
    assert ensure_funnel(URL, 8765, ts.run, ts.start)[:2] == (True, 'info') and ts.started == [['funnel', '--bg', '8765']]


def test_a_window_on_another_port_counts_as_funnel_elsewhere():
    ts = FakeTailscale(funnel={'Foreground': {'s': DEMO}})
    assert ensure_funnel(URL, 8765, ts.run, ts.start) == (True, None, None) and ts.started == []
    assert 'sends visitors to http://127.0.0.1:8766' in check(URL, 8765, ts.run)['message']


def test_if_a_window_opens_first_tailscale_refuses_and_acepressure_asks_to_close_it():
    ts = FakeTailscale(turns_on=False, prints='sending serve config: updating config: foreground listener already exists for port 443\n')
    done, level, line = ensure_funnel(URL, 8765, ts.run, ts.start)
    assert (done, level) == (False, 'warning') and line.startswith('A `tailscale funnel` window is open')
    assert f'Close that window: AcePressure turns Funnel on within {PENDING_INTERVAL} seconds.' in line


def test_a_funnel_on_another_https_port_is_not_the_tip_link():
    other_port = {'AllowFunnel': {HOST + ':8443': True}, 'Web': {HOST + ':8443': {'Handlers': {'/': {'Proxy': 'http://127.0.0.1:8765'}}}}}
    ts = FakeTailscale(funnel=other_port)  # https://<host>/ is :443: nothing answers there
    assert ensure_funnel(URL, 8765, ts.run, ts.start)[2].startswith('Turned Tailscale Funnel on') and ts.started == [['funnel', '--bg', '8765']]


def test_a_version_warning_does_not_hide_the_reason():
    ts = FakeTailscale(turns_on=False, prints='Warning: client version "1.90.1" != tailscaled server version "1.92.0"\nerror: shields up\n')
    assert '(Tailscale said: error: shields up)' in ensure_funnel(URL, 8765, ts.run, ts.start)[2]


def test_when_tailscale_cannot_say_whether_funnel_is_on_it_asks_again_later():
    class Unreadable(FakeTailscale):
        def run(self, args):
            if args[:2] == ['funnel', 'status']:
                raise subprocess.TimeoutExpired(args, 10)
            return super().run(args)
    ts = Unreadable()
    assert ensure_funnel(URL, 8765, ts.run, ts.start) == (False, None, None) and ts.started == []


@pytest.mark.parametrize('status', [
    {'BackendState': 'Starting'},
    {'BackendState': 'NeedsLogin', 'Self': ME},
    {'BackendState': 'NeedsMachineAuth', 'Self': ME},
    {'BackendState': 'Stopped', 'Self': ME},
    {'BackendState': 'Running', 'Self': ME | {'Online': False}},
    'not json', 'null', '[]',
])
def test_it_waits_until_tailscale_is_ready(status):
    ts = FakeTailscale(status=status)
    assert ensure_funnel(URL, 8765, ts.run, ts.start) == (False, None, None) and ts.started == []


def test_other_links_and_other_pcs_are_left_alone():
    ts = FakeTailscale()
    assert ensure_funnel('https://tips.example.com/', 8765, ts.run, ts.start) == (True, None, None)
    assert ensure_funnel('', 8765, ts.run, ts.start) == (True, None, None)
    other = FakeTailscale(status={'BackendState': 'Running', 'Self': ME | {'DNSName': 'other.example.ts.net.'}})
    assert ensure_funnel(URL, 8765, other.run, other.start) == (True, None, None)
    assert ts.started == other.started == []


def test_without_tailscale_it_says_where_to_get_it(monkeypatch):
    monkeypatch.setattr(tunnel_watch, 'tailscale_cli', lambda: None)
    done, level, line = ensure_funnel(URL, 8765)
    assert done and level == 'warning' and 'https://tailscale.com/download/windows' in line and HOST in line


def test_the_approval_wait_is_cut_short_and_its_link_kept(monkeypatch):
    def waits(cmd, **kw):
        assert cmd == ['tailscale', 'funnel', '--bg', '8765'] and kw['timeout'] == tunnel_watch.START_TIMEOUT
        raise subprocess.TimeoutExpired(cmd, kw['timeout'], output=APPROVAL.encode(), stderr=None)
    monkeypatch.setattr(tunnel_watch.subprocess, 'run', waits)
    assert 'https://login.tailscale.com/f/funnel?node=nAbC123' in tunnel_watch._starter('tailscale')(['funnel', '--bg', '8765'])

    def missing(cmd, **kw):
        raise FileNotFoundError(cmd[0])
    monkeypatch.setattr(tunnel_watch.subprocess, 'run', missing)
    assert tunnel_watch._starter('tailscale')(['funnel', '--bg', '8765']) == ''


def test_live_mode_only_and_it_can_be_switched_off(monkeypatch):
    live, demo = types.SimpleNamespace(config={'DEMO_MODE': False}), types.SimpleNamespace(config={'DEMO_MODE': True})
    monkeypatch.delenv('TAILSCALE_AUTO_FUNNEL', raising=False)
    assert tunnel_watch.auto_funnel(live) is True and tunnel_watch.auto_funnel(demo) is False
    for off in ('false', 'False', ' 0 ', 'no', 'off'):
        monkeypatch.setenv('TAILSCALE_AUTO_FUNNEL', off)
        assert tunnel_watch.auto_funnel(live) is False
    monkeypatch.setenv('TAILSCALE_AUTO_FUNNEL', 'true')
    assert tunnel_watch.auto_funnel(live) is True


OK = {'state': 'ok', 'message': 'Tip link reachable through Tailscale Funnel.', 'checked': 1}


def run_watch(app, monkeypatch, ensures, checks, rounds):
    """Runs TunnelWatch._loop for a number of rounds with stand-ins; returns (ensure calls, sleeps, tunnel log lines)."""
    ensures, checks, calls, sleeps = iter(ensures), iter(checks), [], []

    def ensure(url, port):
        calls.append(port)
        return next(ensures)
    monkeypatch.setattr(tunnel_watch, 'ensure_funnel', ensure)
    monkeypatch.setattr(tunnel_watch, 'check', lambda url, port: next(checks))

    def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == rounds:
            raise SystemExit
    monkeypatch.setattr(tunnel_watch.time, 'sleep', sleep)
    log = logging.getLogger('acepressure.tunnel')
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    log.addHandler(handler); log.setLevel(logging.INFO)
    try:
        with pytest.raises(SystemExit):
            tunnel_watch.TunnelWatch(app, 8765, ensure=True)._loop()
    finally:
        log.removeHandler(handler)
    return calls, sleeps, [(r.levelno, r.getMessage()) for r in records]


def test_the_watch_turns_funnel_on_once_retrying_until_tailscale_is_ready(app, monkeypatch):
    calls, sleeps, lines = run_watch(app, monkeypatch, [(False, None, None), (False, None, None), (True, 'info', 'Turned Tailscale Funnel on → ok’')],
                                     [None, None, OK, OK, OK], 5)
    assert calls == [8765, 8765, 8765]  # not ready, not ready, done: never again, so a Funnel switched off later stays off
    assert sleeps == [PENDING_INTERVAL, PENDING_INTERVAL, 60, 60, 60]  # quick retries only while Funnel still has to be turned on
    assert lines == [(logging.WARNING, 'Tip link: ' + WAITING.replace('’', "'")),  # said once, and shown on the dashboard
                     (logging.INFO, "Tip link: Turned Tailscale Funnel on -> ok'"),
                     (logging.INFO, 'Tip link: Tip link reachable through Tailscale Funnel.')]  # good news, not a warning (1.6.6)


def test_a_warning_after_the_waiting_line_is_still_written(app, monkeypatch):
    expiry = {'state': 'warn', 'message': 'This PC’s Tailscale sign-in expires in 5 days, and your tip link stops working then.', 'checked': 1}
    calls, sleeps, lines = run_watch(app, monkeypatch, [(False, None, None), (True, 'info', 'Turned Tailscale Funnel on')],
                                     [None, expiry, expiry], 3)
    assert lines == [(logging.WARNING, 'Tip link: ' + WAITING.replace('’', "'")), (logging.INFO, 'Tip link: Turned Tailscale Funnel on'),
                     (logging.WARNING, "Tip link: This PC's Tailscale sign-in expires in 5 days, and your tip link stops working then.")]
    assert app.extensions['ace_tunnel'] == expiry  # both waiting and the expiry are 'warn', yet the window gets the second one


def test_the_waiting_line_reaches_the_dashboard(app, monkeypatch):
    run_watch(app, monkeypatch, [(False, None, None)], [None], 1)
    assert app.extensions['ace_tunnel']['state'] == 'warn' and app.extensions['ace_tunnel']['message'] == WAITING


def test_a_window_line_is_written_once(app, monkeypatch):
    window = (False, 'info', 'Tailscale Funnel is on from an open `tailscale funnel` window')
    calls, sleeps, lines = run_watch(app, monkeypatch, [window, window, window, (True, 'info', 'Turned Tailscale Funnel on')], [OK] * 5, 5)
    assert lines == [(logging.INFO, 'Tip link: Tailscale Funnel is on from an open `tailscale funnel` window'), (logging.INFO, 'Tip link: Turned Tailscale Funnel on')]
    assert sleeps[:3] == [PENDING_INTERVAL] * 3 and app.extensions['ace_tunnel'] == OK


def test_a_warning_is_not_followed_by_a_contradicting_one(app, monkeypatch):
    bad = {'state': 'bad', 'message': 'Viewers can’t reach your tip link: Tailscale Funnel is off. Run Setup_Tailscale_URL.bat again.', 'checked': 1}
    calls, sleeps, lines = run_watch(app, monkeypatch, [(True, 'warning', 'Tailscale needs your OK once')], [bad, bad], 2)
    assert lines == [(logging.WARNING, 'Tip link: Tailscale needs your OK once')] and app.extensions['ace_tunnel'] == bad


def test_problems_are_warnings_in_the_window(app, monkeypatch, caplog):
    monkeypatch.setattr(tunnel_watch, 'ensure_funnel', lambda url, port: (True, 'warning', 'Tailscale needs your OK once'))
    monkeypatch.setattr(tunnel_watch, 'check', lambda url, port: None)

    def stop(seconds):
        raise SystemExit
    monkeypatch.setattr(tunnel_watch.time, 'sleep', stop)
    with caplog.at_level(logging.INFO, logger='acepressure.tunnel'), pytest.raises(SystemExit):
        tunnel_watch.TunnelWatch(app, 8765, ensure=True)._loop()
    assert [(r.levelno, r.getMessage()) for r in caplog.records if r.name == 'acepressure.tunnel'] == [(logging.WARNING, 'Tip link: Tailscale needs your OK once')]


def test_demo_mode_never_touches_funnel(app, monkeypatch):
    monkeypatch.setattr(tunnel_watch, 'ensure_funnel', lambda url, port: pytest.fail('demo mode turned Funnel on'))
    monkeypatch.setattr(tunnel_watch, 'check', lambda url, port: None)

    def stop(seconds):
        raise SystemExit
    monkeypatch.setattr(tunnel_watch.time, 'sleep', stop)
    watch = tunnel_watch.TunnelWatch(app, 8766)  # the test app runs in demo mode
    assert watch.ensure is False
    with pytest.raises(SystemExit):
        watch._loop()



# ---------- names on stream, and the Piper installer (fixed in 1.6.5) ----------
OV = {'X-Overlay-Token': 'o' * 48}


def put_settings(app, **values):
    with app.store.db(True) as db:
        for k, v in values.items():
            db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (k, json.dumps(v)))


def verified_tip(app, **tip):
    t = app.store.create_tip(dict(amount=100, name='Rahul', message='GG', tts=True) | tip, True)
    with app.store.db(True) as db:
        db.execute("UPDATE tips SET status='VERIFIED',verified=? WHERE id=?", (now(), t['id']))
    return t


@pytest.mark.parametrize('whole_words', [False, True])
def test_names_on_stream_match_filtered_words_as_whole_words(app, whole_words):
    put_settings(app, banned_words=['shit', 'gand', 'noob*'], filter_whole_words=whole_words)
    s, name = app.store.settings(), app.store.stream_name
    assert name('Kshitij Gandhi', s) == 'Kshitij Gandhi'  # an upgraded 1.6.4 showed "K[filtered]ij [filtered]hi"
    assert name('shit GAND', s) == '[filtered] [filtered]'
    assert name('NoobSlayer noobs', s) == '[filtered]Slayer [filtered]'  # a capital after a small letter starts a word
    assert app.store.moderated('Kshitij', s) == ('Kshitij' if whole_words else 'K[filtered]ij')  # messages follow the switch


def test_an_upgraded_install_keeps_names_whole_on_the_alert_and_the_boards(app, admin):
    c, h = admin
    put_settings(app, banned_words=['shit'], filter_whole_words=False)  # a database from before 1.6.4
    tip = verified_tip(app, name='Kshitij', amount=500, message='shit happens')
    assert c.post('/api/admin/alerts', json={'action': 'replay', 'id': tip['id']}, headers=h).status_code == 200
    alert = c.post('/api/overlay/claim', json={'channel': 'horizontal', 'owner': 'obs', 'client': 'obs'}, headers=OV).json['alert']
    assert alert['name'] == 'Kshitij' and alert['message'] == '[filtered] happens'
    assert [p['name'] for p in c.get('/api/public/top').json['supporters']] == ['Kshitij']
    state = c.get('/api/overlay/state?period=lifetime', headers=OV).json
    assert state['top'][0]['name'] == 'Kshitij' and state['recent'][0]['name'] == 'Kshitij'


@pytest.mark.parametrize('name, words, shown', [
    ('Kshitij', ['shit'], 'Kshitij'), ('KShitij', ['shit'], 'KShitij'), ('Kshitij Gandhi', ['shit', 'gand'], 'Kshitij Gandhi'),
    ('Shit_Lord', ['shit'], '[filtered]_Lord'), ('fuck_you', ['fuck'], '[filtered]_you'), ('Fuck69', ['fuck'], '[filtered]69'),
    ('Big_Shit', ['shit'], 'Big_[filtered]'), ('BigShit', ['shit'], 'Big[filtered]'), ('FuckYou', ['fuck'], '[filtered]You'),
    ('SHIT lord', ['shit'], '[filtered] lord'), ('BIGSHIT', ['shit'], 'BIGSHIT'), ('bigshit', ['bigshit'], '[filtered]'),
    ('noob_master69', ['noob*'], '[filtered]_master69'), ('NoobsRule', ['noob*'], '[filtered]Rule'), ('Big Noob fan', ['noob', 'noob*'], 'Big [filtered] fan'),
    ('xXshitXx', ['shit'], 'xXshitXx'), ('Hello_world', ['hell'], 'Hello_world'), ('AssassinX', ['ass'], 'AssassinX'),
    ('ClassyGamer', ['ass'], 'ClassyGamer'), ('Born 1969', ['69'], 'Born 1969'), ('Born 69', ['69'], 'Born [filtered]'),
    ('GG EZ bro', ['gg ez'], '[filtered] bro'), ('राहुल गाली', ['गाली'], 'राहुल [filtered]'), ('गालीयाँ', ['गाली'], 'गालीयाँ'),
    ('', ['x'], ''), ('Rahul', [], 'Rahul'), ('Rahul', ['*', '  '], 'Rahul'),
])
def test_words_in_names_end_at_spaces_underscores_digits_and_capitals(name, words, shown):
    assert name_filter(name, words) == shown


@pytest.mark.parametrize('name, words, shown', [
    ('BIGNoob', ['noob'], 'BIG[filtered]'), ('SHITLord', ['shit'], '[filtered]Lord'), ('BSDKRahul', ['bsdk'], '[filtered]Rahul'),
    ('FUCKYou', ['fuck'], '[filtered]You'), ('NOOBMaster', ['noob'], '[filtered]Master'), ('xXNoobXx', ['noob'], 'xX[filtered]Xx'),
    ('GGShit', ['shit'], 'GG[filtered]'), ('NOOBSMaster', ['noob*'], '[filtered]Master'), ('NOOBMASTER', ['noob*'], '[filtered]'),
    ('KShital RKSharma', ['shit', 'ass'], 'KShital RKSharma'), ('DJAssam MSDhoni', ['ass'], 'DJAssam MSDhoni'),
    ('Harshit Shital', ['shit'], 'Harshit Shital'), ('BULLSHIT', ['shit'], 'BULLSHIT'),
    ('BULLSHIT fuckyou MOTHERFUCKER', ['bullshit', 'fuck*', 'motherfucker'], '[filtered] [filtered] [filtered]'),
])
def test_a_capital_before_small_letters_also_starts_a_word_after_capitals(name, words, shown):
    assert name_filter(name, words) == shown  # 1.6.6: BIG|Noob as well as Noob|Master; a word inside another needs its own entry


def test_the_settings_say_names_match_whole_words():
    admin = (ROOT / 'acepressure' / 'static' / 'admin.js').read_text(encoding='utf-8')
    assert 'Names are filtered too, always as whole words: in a name, _, a digit or a capital starting a new part also starts a word' in admin
    assert 'A word inside a longer name, like bullshit, needs its own entry' in admin
    assert 'Off: messages are also filtered inside other words' in admin


def test_install_piper_offers_the_backup_voice_without_replacing_yours():
    raw = (ROOT / 'Install_Piper.bat').read_bytes()
    assert raw.isascii() and raw.count(b'\r\n') == raw.count(b'\n')  # cmd.exe reads it as written
    text = raw.decode('ascii')
    assert text.count('"If the voice service fails"') == 2 and text.count('"Use selected voices"') == 2 and '"Save backup voice"' in text
    assert 'engine = "piper"' not in text.lower() and 'Detect voices' not in text  # the engine alone keeps the old voices: silence
    assert not any(ch in text for ch in '<>&|^')  # in an echo line cmd.exe would act on these

def test_version_and_docs():
    assert tuple(int(x) for x in (ROOT / 'VERSION').read_text(encoding='utf-8').strip().split('.')) >= (1, 6, 6)
    docs = lambda name: (ROOT / 'docs' / name).read_text(encoding='utf-8')
    changelog = docs('CHANGELOG.md')
    assert (changelog.startswith('# 1.6.6 — ') or '\n# 1.6.6 — ' in changelog) and changelog.index('# 1.6.6 — ') < changelog.index('\n# 1.6.5 — ') < changelog.index('\n# 1.6.4 — ')
    final = changelog[changelog.index('# 1.6.6 — '):changelog.index('\n# 1.6.5 — ')]  # 1.6.6 is the finished 1.6.5, whose test builds the user may have
    assert 'K[filtered]ij' in final and 'Install_Piper.bat' in final and 'test build' in final and '@@' not in changelog
    update = docs('UPDATE_1.6.6.md')
    assert '1.6.5 test build' in update
    assert '`run.py`' in update and 'TAILSCALE_AUTO_FUNNEL=false' in update and 'UPDATE_1.6.4.md' in update
    assert 'tests\\test_release_165.py' in update and 'listener already exists' in update and '`fuck*`' in update
    assert (ROOT / 'docs' / 'VALIDATION_1.6.6.md').is_file()
    funnel = docs('TAILSCALE_FUNNEL.md')
    assert 'TAILSCALE_AUTO_FUNNEL=false' in funnel and 'tailscale funnel --bg 8765' in funnel
