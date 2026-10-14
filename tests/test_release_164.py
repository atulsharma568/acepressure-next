"""1.6.4: a session starts when OBS goes live, line breaks and <3 in messages, a cleaner cut, a long test alert, a calm
tip page while a payment waits for approval, "Replay in full" and "read the whole message from ₹X", Skip alert, a
backup voice and a dock warning when the voice fails, the Tailscale tip-link check and stronger moderation."""
import io
import json
import logging
import time
import wave
from pathlib import Path

import pytest

from acepressure import edge_tts_service, tts_service, tunnel_watch
from acepressure.app import TEST_LONG_MESSAGE, TEST_MESSAGE
from acepressure.domain import ANONYMOUS, DEFAULTS, Problem, Store, now
from acepressure.text_filters import first_part, tidy_message, word_filter

ROOT = Path(__file__).resolve().parents[1]
OV = {'X-Overlay-Token': 'o' * 48}
LONG = ('Bhai kya clutch tha, aaj ka stream bahut mast tha. Main tumhara bahut bada fan hoon aur roz stream dekhta hoon, '
        'keep it up and see you in the next match!')


# ---------- helpers ----------
def wav(sec=0.5):
    b = io.BytesIO()
    with wave.open(b, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(b'\x00\x00' * int(8000 * sec))
    return b.getvalue()


def put_settings(app, **values):
    with app.store.db(True) as db:
        for k, v in values.items():
            db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (k, json.dumps(v)))


def settings(app):
    return app.store.settings()


def verified_tip(app, **tip):
    t = app.store.create_tip(dict(amount=100, name='Rahul', message='GG', tts=True) | tip, True)
    with app.store.db(True) as db:
        db.execute("UPDATE tips SET status='VERIFIED',verified=? WHERE id=?", (now(), t['id']))
    return t


def claim(c, channel='horizontal', owner='obs'):
    return c.post('/api/overlay/claim', json={'channel': channel, 'owner': owner, 'client': 'obs'}, headers=OV).json


def ack(c, alert, channel='horizontal', owner='obs', **extra):
    return c.post('/api/overlay/ack', json={'event_id': alert['event_id'], 'channel': channel, 'owner': owner, 'client': 'obs'} | extra, headers=OV)


def replay(c, h, tip, **extra):
    r = c.post('/api/admin/alerts', json={'action': 'replay', 'id': tip['id']} | extra, headers=h)
    assert r.status_code == 200, r.json
    return r


def deliveries(app, alert_id):
    with app.store.db() as db:
        return {r['channel']: r['state'] for r in db.execute('SELECT channel,state FROM deliveries WHERE alert_id=?', (alert_id,))}


def audits(app, action):
    with app.store.db() as db:
        return [dict(r) for r in db.execute('SELECT * FROM audit WHERE action=? ORDER BY id', (action,))]


def record_voice(monkeypatch):
    spoken = []

    def fake(directory, text, voice, engine):
        spoken.append((text, voice, engine)); out = directory / ('fake-' + engine + '.wav'); out.write_bytes(wav()); return out
    monkeypatch.setattr(tts_service, 'synthesize', fake)
    return spoken


def read(name):
    return (ROOT / 'acepressure' / name).read_text(encoding='utf-8')


def live(c, streaming=True, reason='event', headers=OV):
    return c.post('/api/overlay/live', json={'streaming': streaming, 'reason': reason}, headers=headers)


def active(app):
    with app.store.db() as db:
        return app.store.active(db)


# ---------- 1. OBS going live starts a stream session ----------
def test_obs_going_live_starts_a_session_once(app, client):
    assert active(app) is None
    r = live(client)
    assert r.status_code == 200 and r.json == {'ok': True, 'session_started': True, 'session_active': True}
    s = active(app)
    assert s and s['title'].startswith('Live stream · ')
    assert settings(app)['session_auto']['session_id'] == s['id'] and settings(app)['obs_live']['streaming'] is True
    assert json.loads(audits(app, 'start_session')[-1]['detail'])['source'] == 'obs'
    # a second OBS page, or the same page again: still one session
    assert live(client).json == {'ok': True, 'session_started': False, 'session_active': True}
    with app.store.db() as db:
        assert db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 1
    state = client.get('/api/overlay/state', headers=OV).json
    assert state['session_active'] is True and state['auto_session'] is True and state['dismissed'] == []


def test_stopping_never_ends_a_session_and_the_key_is_required(app, client):
    live(client)
    assert live(client, False).json['session_active'] is True and active(app) is not None
    assert settings(app)['obs_live']['streaming'] is False
    assert live(client, headers={}).status_code in (401, 403)
    assert live(client, headers={'X-Overlay-Token': 'x' * 48}).status_code in (401, 403)
    for bad in [{'streaming': 'yes'}, {'streaming': True, 'reason': 'boot'}, {}]:
        assert client.post('/api/overlay/live', json=bad, headers=OV).status_code == 400


def test_switched_off_or_ended_on_purpose_it_stays_off(app, admin):
    c, h = admin
    put_settings(app, auto_session=False)
    assert live(c).json['session_started'] is False and active(app) is None
    assert c.get('/api/overlay/state', headers=OV).json['auto_session'] is False
    put_settings(app, auto_session=True)
    assert c.post('/api/admin/sessions', json={'action': 'start', 'title': 'Ranked'}, headers=h).status_code == 200
    assert c.post('/api/admin/sessions', json={'action': 'end'}, headers=h).status_code == 200
    # the page found OBS already live (a refresh): a session ended in the last 2 hours stays ended
    assert live(c, reason='load').json['session_started'] is False and active(app) is None
    # OBS actually going live again starts one
    assert live(c).json['session_started'] is True


def test_the_dashboard_setting_saves(app, admin):
    c, h = admin
    assert DEFAULTS['auto_session'] is True
    assert c.post('/api/admin/settings', json={'auto_session': False}, headers=h).status_code == 200
    assert settings(app)['auto_session'] is False
    assert c.post('/api/admin/settings', json={'auto_session': 'no'}, headers=h).status_code == 400
    assert c.post('/api/admin/settings', json={'obs_live': {'streaming': True}}, headers=h).status_code == 400  # not a setting


def test_tips_made_just_before_going_live_join_the_session(app, client):
    early = app.store.create_tip(dict(amount=100, name='Early', message='hi', tts=True), True)
    gone = app.store.create_tip(dict(amount=100, name='Gone', message='hi', tts=True), True)
    with app.store.db(True) as db:
        db.execute('UPDATE tips SET expires=? WHERE id=?', (now() - 1, gone['id']))
    assert early['session_id'] is None
    live(client)
    sid = active(app)['id']
    with app.store.db() as db:
        got = {r['id']: r['session_id'] for r in db.execute('SELECT id,session_id FROM tips')}
    assert got[early['id']] == sid and got[gone['id']] is None
    assert json.loads(audits(app, 'start_session')[-1]['detail'])['waiting_tips_joined'] == 1


# ---------- 2. line breaks and <3 ----------
@pytest.mark.parametrize('typed, stored', [
    ('bhai\nkya clutch', 'bhai kya clutch'),
    ('GG\r\n\r\nbro', 'GG bro'),
    ('tab\there', 'tab here'),
    ('love you <3', 'love you ❤️'),
    ('miss you </3', 'miss you 💔'),
    ('<3<3', '❤️❤️'),
])
def test_line_breaks_become_spaces_and_hearts_stay_hearts(typed, stored):
    assert tidy_message(typed) == stored


def test_a_tip_stores_and_shows_the_tidy_message(app, admin):
    c, h = admin
    c.post('/api/admin/sessions', json={'action': 'start', 'title': 'x'}, headers=h)
    t = verified_tip(app, message='GG\nbhai <3', name='Ra\nhul')
    with app.store.db() as db:
        row = db.execute('SELECT name,message FROM tips WHERE id=?', (t['id'],)).fetchone()
    assert row['message'] == 'GG bhai ❤️' and row['name'] == 'Ra hul'
    replay(c, h, t)
    a = claim(c)['alert']
    assert a['message'] == 'GG bhai ❤️' and a['speech'] == 'GG bhai'  # the voice skips the heart (emoji)
    assert tidy_message(None) is None and tidy_message(5) == 5


# ---------- 3. a cleaner cut ----------
@pytest.mark.parametrize('text, limit, part', [
    ('Thanks bro. Great stream', 10, 'Thanks bro'),       # a word ending at the limit is kept, a full stop after it too
    ('Thanks bro, great stream', 10, 'Thanks bro'),
    ('pehla tip of Rs 500 for you', 15, 'pehla tip'),     # never ends on "of Rs"
    ('bhai ka stream mast', 8, 'bhai'),                   # nor on "ka"
    ('Sent ₹1,000 bhai', 7, 'Sent'),                      # a number is never split
    ('Paid 5.30 today', 6, 'Paid'),
    ('gg bhai kya clutch tha', 12, 'gg bhai kya'),        # 1.6.3 cases still hold
    ('a' * 30, 20, 'a' * 20),
    ('the of to my best', 13, 'the'),                     # at most three words dropped
    ('short', 100, 'short'),
])
def test_first_part_keeps_whole_words_and_no_dangling_word(text, limit, part):
    assert first_part(text, limit) == part


# ---------- 4. a long test alert ----------
def test_with_whole_messages_off_the_test_alert_is_long_enough_to_hear_the_cut(app, admin):
    c, h = admin
    assert c.post('/api/admin/alerts', json={'action': 'test'}, headers=h).status_code == 200
    a = claim(c)['alert']
    assert a['message'] == TEST_MESSAGE and a['speech'] == TEST_MESSAGE
    ack(c, a)
    put_settings(app, tts_read_full=False, tts_short_limit=60)
    c.post('/api/admin/alerts', json={'action': 'test'}, headers=h)
    a = claim(c)['alert']
    assert a['message'] == TEST_LONG_MESSAGE and len(TEST_LONG_MESSAGE) > 100
    assert TEST_LONG_MESSAGE.startswith(a['speech']) and len(a['speech']) <= 60 and a['speech'] != a['message']


def test_voice_studio_can_send_its_sample_to_obs(app, admin):
    c, h = admin
    put_settings(app, banned_words=['noob'])
    assert c.post('/api/admin/alerts', json={'action': 'test', 'message': 'GG noob\nbhai'}, headers=h).status_code == 200
    assert claim(c)['alert']['message'] == 'GG [filtered] bhai'
    for bad in ['', '   ', 5, ['x']]:
        assert c.post('/api/admin/alerts', json={'action': 'test', 'message': bad}, headers=h).status_code == 400
    designer = read('static/designer.js')
    assert "Send to OBS as a test alert" in designer and "A('alerts',{action:'test',message:sample.value})" in designer
    assert 'sample.maxLength=Math.min(500,Math.max(20,Number(state.settings.tts_limit)||180));' in designer


# ---------- 5. a calm tip page ----------
def test_the_tip_page_waits_calmly_and_keeps_checking():
    js = read('static/public.js')
    assert 'Automatic checks have stopped' not in js
    assert 'const LATE_MS=60000,LATE_FOR=7200000;' in js and 'Date.now()<current.expires*1000+LATE_FOR' in js
    assert "el('h2','Waiting for approval')" in js and "el('h2','Payment window closed')" in js
    assert 'leave this page open and it updates by itself' in js and 'current.final' in js
    # a payment in progress comes back before the Top supporters list loads
    assert js.index("safeStore.get('ace-tip','sessionStorage')") < js.index("api('/api/public/top')")
    assert "returnCheck()" in js and "'tts_read_full','tts_short_limit','tts_full_from'" in js


def test_an_expired_tip_with_a_payment_to_review_says_so(app, client):
    t = app.store.create_tip(dict(amount=100, name='Rahul', message='GG'), True)
    with app.store.db(True) as db:
        db.execute('UPDATE tips SET expires=? WHERE id=?', (now() - 5, t['id']))
        db.execute("INSERT INTO paytm_inbox(fingerprint,received,payment_minute,amount,status,reason,tip_id,candidates) VALUES(?,?,?,?,?,?,?,?)",
                   ('f' * 64, now(), None, t['requested_paise'], 'REVIEW', 'ambiguous_match', t['id'], json.dumps([t['id']])))
    d = client.get('/api/public/tips/' + t['id'], headers={'X-Tip-Token': t['token']}).json
    assert d['status'] == 'EXPIRED' and d['needs_review'] is True


# ---------- 6. Replay in full, and big tips read in full ----------
def test_tips_from_an_amount_are_read_in_full(app, admin):
    c, h = admin
    put_settings(app, tts_read_full=False, tts_short_limit=40, tts_full_from=500)
    store, s = app.store, settings(app)
    assert store.speech(LONG, s, 50000) == LONG
    assert store.speech(LONG, s, 49900) == first_part(LONG, 40)
    assert store.speech(LONG, s) == first_part(LONG, 40) and store.speech(LONG, s, full=True) == LONG
    put_settings(app, tts_full_from=0)
    assert store.speech(LONG, settings(app), 10 ** 9) == first_part(LONG, 40)  # 0 = off
    big = verified_tip(app, amount=500, message=LONG)
    put_settings(app, tts_full_from=500)
    replay(c, h, big)
    assert claim(c)['alert']['speech'] == LONG


def test_replay_in_full_reads_everything_once(app, admin, monkeypatch):
    c, h = admin
    spoken = record_voice(monkeypatch)
    put_settings(app, tts_read_full=False, tts_short_limit=40, tts_engine='edge', voices=['en-IN'])
    t = verified_tip(app, message=LONG, voice='en-IN')
    state = c.get('/api/admin/state').json
    assert next(x for x in state['recent'] if x['id'] == t['id'])['cut'] is True
    replay(c, h, t, full=True)
    a = claim(c)['alert']
    assert a['message'] == LONG and a['speech'] == LONG and a['read_full'] is True
    assert c.get(f"/api/overlay/tts/{a['event_id']}", headers=OV).status_code == 200 and spoken[-1][0] == LONG
    assert json.loads(audits(app, 'alert_replay')[-1]['detail']) == {'full': True}
    ack(c, a)
    replay(c, h, t)  # a normal replay is cut again
    a = claim(c)['alert']
    assert a['speech'] == first_part(LONG, 40) and 'read_full' not in a
    c.get(f"/api/overlay/tts/{a['event_id']}", headers=OV)
    assert spoken[-1][0] == first_part(LONG, 40)
    put_settings(app, tts_read_full=True)
    assert next(x for x in c.get('/api/admin/state').json['recent'] if x['id'] == t['id'])['cut'] is False


def test_the_amount_setting_is_checked_and_told_to_the_tip_page(app, admin):
    c, h = admin
    assert DEFAULTS['tts_full_from'] == 0
    for bad in [-1, 1000001, 2.5, '500', True]:
        assert c.post('/api/admin/settings', json={'tts_full_from': bad}, headers=h).status_code == 400, bad
    assert c.post('/api/admin/settings', json={'tts_full_from': 500}, headers=h).status_code == 200
    assert c.get('/api/public/config').json['tts_full_from'] == 500
    js = read('static/public.js')
    assert 'function voiceNote(){' in js and "if(config.tts_read_full===false)" in js and "n.id='tts-short-note'" in js


# ---------- 7. Skip alert ----------
def test_skip_alert_stops_the_alert_on_both_layouts(app, admin):
    c, h = admin
    assert c.post('/api/admin/alerts', json={'action': 'dismiss'}, headers=h).status_code == 409  # nothing playing
    t = verified_tip(app)
    replay(c, h, t)
    a = claim(c)['alert']
    before = settings(app)['skip_version']
    r = c.post('/api/admin/alerts', json={'action': 'dismiss'}, headers=h)
    assert r.status_code == 200
    assert deliveries(app, a['event_id']) == {'horizontal': 'playing', 'vertical': 'cancelled'}  # vertical never starts it
    state = c.get('/api/overlay/state', headers=OV).json
    assert a['event_id'] in state['dismissed'] and state['skip_version'] == before + 1
    assert json.loads(audits(app, 'alert_dismiss')[-1]['detail']) == {'alerts': [a['event_id']]}
    assert ack(c, a, skipped=True, tts_played=False).status_code == 200
    assert deliveries(app, a['event_id'])['horizontal'] == 'skipped'
    assert next(x for x in c.get('/api/admin/state').json['recent'] if x['id'] == t['id'])['alert_state'] == 'skipped'
    assert claim(c, 'vertical', 'obs-v')['alert'] is None


def test_a_skipped_alert_never_comes_back_after_its_lease(app, admin):
    c, h = admin
    replay(c, h, verified_tip(app))
    a = claim(c)['alert']
    c.post('/api/admin/alerts', json={'action': 'dismiss'}, headers=h)
    with app.store.db(True) as db:
        db.execute('UPDATE deliveries SET lease=? WHERE alert_id=?', (now() - 1, a['event_id']))  # the OBS page closed
    assert claim(c, owner='obs-2')['alert'] is None
    assert deliveries(app, a['event_id'])['horizontal'] == 'skipped'


def test_dismissed_list_keeps_the_last_twenty(app):
    with app.store.db(True) as db:
        for i in range(1, 26):
            app.store.dismiss(db, [i])
        app.store.dismiss(db, ['x', None])
    assert settings(app)['dismissed_alerts'] == list(range(6, 26))


def test_a_playing_alert_never_expires_and_the_queue_behind_it_waits(app, admin, monkeypatch):
    c, h = admin
    record_voice(monkeypatch)
    put_settings(app, tts_engine='edge', voices=['en-IN'])
    first, second = verified_tip(app, voice='en-IN'), verified_tip(app, voice='en-IN', name='Second')
    replay(c, h, first); replay(c, h, second)
    with app.store.db(True) as db:
        db.execute('UPDATE alerts SET expires=?', (now() + 5,))  # both waited almost 5 minutes (approvals after a match)
        db.execute("UPDATE deliveries SET state='done' WHERE channel='vertical'")
    a = claim(c)['alert']
    with app.store.db() as db:  # the one playing can still make its voice, and the one behind it doesn't run out
        assert all(r[0] >= now() + 170 for r in db.execute('SELECT expires FROM alerts'))
    assert c.get(f"/api/overlay/tts/{a['event_id']}", headers=OV).status_code == 200
    with app.store.db(True) as db:
        db.execute('UPDATE alerts SET expires=? WHERE id=?', (now() - 1, a['event_id']))  # a long alert, a slow voice
    assert claim(c, owner='obs')['alert'] is None  # still playing: the channel is busy
    assert deliveries(app, a['event_id'])['horizontal'] == 'playing'  # 1.6.3 marked it missed here
    assert ack(c, a).status_code == 200
    b = claim(c)['alert']
    assert b and b['name'] == 'Second'
    assert c.get(f"/api/overlay/tts/{b['event_id']}", headers=OV).status_code == 200


def test_block_and_mute_act_on_the_alert_on_screen(app, admin):
    c, h = admin
    t = verified_tip(app)
    replay(c, h, t); replay(c, h, t)
    a = claim(c)['alert']
    v = settings(app)['skip_version']
    assert c.post('/api/admin/supporters/' + t['supporter_id'], json={'muted': True}, headers=h).status_code == 200
    assert settings(app)['skip_version'] == v + 1 and a['event_id'] not in settings(app).get('dismissed_alerts', [])
    assert c.post('/api/admin/supporters/' + t['supporter_id'], json={'blocked': True}, headers=h).status_code == 200
    assert a['event_id'] in settings(app)['dismissed_alerts']
    with app.store.db() as db:
        states = [r[0] for r in db.execute("SELECT state FROM deliveries WHERE alert_id<>?", (a['event_id'],))]
    assert states and set(states) == {'cancelled'}


def test_the_paytm_review_shows_the_message_before_approving(app, admin):
    c, h = admin
    put_settings(app, hide_links=True, banned_words=['noob'])
    app.store.create_tip(dict(amount=100, name='Rahul', message='visit spam.xyz noob', tts=False), True)
    pending = c.get('/api/admin/paytm').json['pending']
    assert pending[0]['message'] == 'visit [link] [filtered]' and pending[0]['tts'] is False
    js = read('static/paytm_bridge.js')
    assert "'On stream: “'+t.message+'”'" in js and 'box.append(select,said,reason,label,al,approve,ignore);' in js


def test_the_overlay_stops_card_sound_and_voice():
    js = read('static/overlay.js')
    assert 'if(alertNow&&Array.isArray(s.dismissed)&&s.dismissed.includes(alertNow.id))alertNow.stop();' in js
    assert "stopSpeech();stopSound();for(const v of card.querySelectorAll('video')){v.muted=true;v.pause();}wake();" in js
    assert 'await Promise.race([pause(Math.max(0,p.seconds*1000-(Date.now()-start))),skip]);' in js
    assert 'tts_played:spoken,client:clientType,skipped});' in js
    assert "if(!isSpeech)soundCancel=()=>finish(false);" in js and 'soundCancel=()=>{try{gain.disconnect();}catch(_){}};' in js
    assert "if(ttsFetch){ttsFetch.abort();ttsFetch=null;}" in js
    assert "u.onerror=e=>{if(!['interrupted','canceled'].includes(e&&e.error))reportSpeech('playback_failed');finish(false);};" in js
    assert "window.addEventListener('obsStreamingStarted',()=>tellLive(true,'event'));" in js
    assert "window.obsstudio.getStatus(st=>{if(st&&st.streaming)tellLive(true,'load');});" in js


# ---------- 8. the backup voice and the voice warning ----------
def engines(monkeypatch, fail=()):
    calls = []

    def fake(directory, text, voice, engine):
        calls.append(engine)
        if engine in fail:
            raise Problem(engine + ' is down.', 503)
        out = directory / ('v-' + engine + '.wav'); out.write_bytes(wav()); return out
    monkeypatch.setattr(tts_service, 'synthesize', fake)
    return calls


def test_the_backup_voice_reads_when_the_engine_fails_then_holds_for_two_minutes(app, monkeypatch):
    s = settings(app) | {'tts_engine': 'edge', 'tts_backup': 'piper:hi_IN-priyamvada'}
    calls = engines(monkeypatch, fail={'edge'})
    path, used = tts_service.synthesize_alert(app, app.store, 'GG', 'en-IN', s)
    assert used is True and calls == ['edge', 'piper'] and path.name == 'v-piper.wav'
    assert app.extensions['ace_tts_error']['message'] == 'edge is down.' and app.extensions['ace_tts_backup']['engine'] == 'piper'
    tts_service.synthesize_alert(app, app.store, 'GG', 'en-IN', s)
    assert calls == ['edge', 'piper', 'piper']  # inside the hold: the backup first
    app.extensions['ace_tts_backup_until'] = now() - 1
    calls[:] = []; engines_ok = engines(monkeypatch)
    path, used = tts_service.synthesize_alert(app, app.store, 'GG', 'en-IN', s)
    assert used is False and engines_ok == ['edge'] and 'ace_tts_backup_until' not in app.extensions


def test_without_a_working_backup_the_engine_error_stands(app, monkeypatch):
    base = settings(app) | {'tts_engine': 'edge'}
    engines(monkeypatch, fail={'edge'})
    with pytest.raises(Problem, match='edge is down'):
        tts_service.synthesize_alert(app, app.store, 'GG', 'en-IN', base | {'tts_backup': ''})
    engines(monkeypatch, fail={'edge', 'windows'})
    with pytest.raises(Problem, match='edge is down'):
        tts_service.synthesize_alert(app, app.store, 'GG', 'en-IN', base | {'tts_backup': 'windows:Microsoft Heera'})
    calls = engines(monkeypatch, fail={'piper'})
    with pytest.raises(Problem, match='piper is down'):  # the backup is the same voice: nothing to fall back to
        tts_service.synthesize_alert(app, app.store, 'GG', 'hi', base | {'tts_engine': 'piper', 'tts_backup': 'piper:hi'})
    assert calls == ['piper']


def test_the_dashboard_hears_about_a_failed_or_backup_voice(app, admin, monkeypatch):
    c, h = admin
    report = lambda code: c.post('/api/overlay/tts-status', json={'code': code}, headers=OV)
    assert c.get('/api/admin/state').json['voice'] is None
    app.extensions['ace_tts_error'] = {'message': 'Edge TTS synthesis failed.', 'engine': 'edge', 'at': now()}
    report('provider_failed')
    v = c.get('/api/admin/state').json['voice']
    assert v['code'] == 'provider_failed' and v['error'] == 'Edge TTS synthesis failed.' and v['engine'] == 'edge' and v['backup'] is False
    app.extensions['ace_tts_backup'] = {'at': now(), 'engine': 'piper'}
    report('played')
    v = c.get('/api/admin/state').json['voice']
    assert v['code'] == 'played' and v['backup'] is True and v['error'] == 'Edge TTS synthesis failed.'
    assert c.get('/api/admin/tts/health').json['backup_used'] is True
    app.extensions.pop('ace_tts_backup')
    report('played')
    v = c.get('/api/admin/state').json['voice']
    assert v['code'] == 'played' and v['backup'] is False and v['error'] is None and v['engine'] is None


def test_choosing_and_hearing_the_backup_voice(app, admin, monkeypatch):
    c, h = admin
    voices = [{'value': 'piper:hi_IN-priyamvada', 'label': 'Piper · Priyamvada', 'hindi': True}, {'value': 'windows:Microsoft Heera', 'label': 'Windows · Heera', 'hindi': True}]
    monkeypatch.setattr(tts_service, 'offline_voices', lambda directory: voices)
    assert c.get('/api/admin/tts/backup').json == {'voices': voices, 'value': ''}
    assert c.post('/api/admin/tts/preview', json={'backup': True}, headers=h).status_code == 400  # nothing saved yet
    assert c.post('/api/admin/tts/backup', json={'voice': 'edge:en-IN'}, headers=h).status_code == 400
    assert c.post('/api/admin/tts/backup', json={'voice': 'windows:Microsoft Heera'}, headers=h).status_code == 200
    assert settings(app)['tts_backup'] == 'windows:Microsoft Heera' and c.get('/api/admin/tts/backup').json['value'] == 'windows:Microsoft Heera'
    spoken = record_voice(monkeypatch)
    r = c.post('/api/admin/tts/preview', json={'backup': True}, headers=h)
    assert r.status_code == 200 and spoken[-1][1:] == ('Microsoft Heera', 'windows')
    assert c.post('/api/admin/tts/backup', json={'voice': ''}, headers=h).status_code == 200 and settings(app)['tts_backup'] == ''
    assert [json.loads(a['detail'])['voice'] for a in audits(app, 'tts_backup_voice')] == ['windows:Microsoft Heera', 'stay silent']
    assert c.post('/api/admin/settings', json={'tts_backup': 'edge:en-IN'}, headers=h).status_code == 400


def test_offline_voices_lists_piper_and_windows_hindi_first(monkeypatch, tmp_path):
    def catalog(engine, directory=None):
        if engine == 'windows':
            raise Problem('Windows voices need Windows.', 503)
        return [{'id': 'en_US-amy', 'label': 'Amy', 'locale': 'en-US'}, {'id': 'hi_IN-priyamvada', 'label': 'Priyamvada', 'locale': 'hi-IN'}]
    monkeypatch.setattr(tts_service, 'catalog', catalog)
    assert [v['value'] for v in tts_service.offline_voices(tmp_path)] == ['piper:hi_IN-priyamvada', 'piper:en_US-amy']


def test_voice_services_give_up_in_time(monkeypatch):
    class Old:
        def __init__(self, text, voice): pass

    class New:
        def __init__(self, text, voice, connect_timeout=10, receive_timeout=60): pass
    assert edge_tts_service._timeouts(type('m', (), {'Communicate': Old})) == {}
    assert edge_tts_service._timeouts(type('m', (), {'Communicate': New})) == {'connect_timeout': 5, 'receive_timeout': 10}
    assert edge_tts_service.TOTAL_TIMEOUT == 12
    seen = []

    class Response(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def urlopen(req, timeout):
        seen.append(timeout); return Response(b'[]')
    monkeypatch.setenv('AZURE_SPEECH_KEY', 'k'); monkeypatch.setenv('AZURE_SPEECH_REGION', 'centralindia')
    monkeypatch.setattr(tts_service.urllib.request, 'urlopen', urlopen)
    tts_service.azure_request('cognitiveservices/voices/list'); tts_service.azure_request('cognitiveservices/v1', b'<speak/>')
    assert seen == [25, 12]


def test_dashboard_voice_controls():
    admin, designer = read('static/admin.js'), read('static/designer.js')
    assert 'function backupVoice(root){' in admin and "A('tts/backup',{voice:sel.value})" in admin and "body:JSON.stringify({backup:true})" in admin
    assert "else if(v.code==='provider_failed')line('bad'" in admin and "if(v.backup)line('warn'" in admin
    assert "'Voice not read'" in admin and "button('Replay in full'" in admin and "skipped:['Skipped','EXPIRED']" in admin
    assert "button('Skip alert',skipAlert)" in admin and "button('Skip current alert',skipAlert)" in admin and "A('alerts',{action:'dismiss'})" in admin
    assert "key:'tts_full_from'" in admin and "key:'filter_whole_words'" in admin and "key:'auto_session'" in admin
    assert "' are read in full'" in admin and "if(s.tts_read_full===false)line('muted'" in admin
    assert "if(last.code==='played'&&d.backup_used)" in designer


def test_the_backup_voice_is_offered_only_where_it_can_help():
    admin = read('static/admin.js')
    # Browser voices play inside OBS, where the backup can't step in: neither the dashboard nor Admin -> TTS offers it for them.
    assert "(s.tts_backup||s.tts_engine==='browser'?'':' Choose a backup voice in Admin → TTS" in admin
    assert "engine==='browser'?'The backup voice works with Edge, Azure, Piper and Windows." in admin
    assert "why={edge:' (internet down, Microsoft busy)',azure:' (internet down, Azure busy)'}[engine]||''" in admin


def test_short_fields_keep_their_gap_after_a_switch():
    css = read('static/premium.css')
    # Three short fields to a row, counted per run of them: the TTS pair after "Read whole messages" keeps its gap.
    assert 'nth-child(3n of' not in css
    start = (':is(label:has(> input:is([type=number], [type=color])):first-child, '
             ':not(label:has(> input:is([type=number], [type=color]))) + label:has(> input:is([type=number], [type=color])))')
    assert css.count(start) == 3  # the 3rd, 6th and 9th field of a run


# ---------- 9. can viewers reach the tip link? ----------
def runner(status, funnel=None, text=None):
    def run(args):
        if args == ['status', '--json']:
            return json.dumps(status) if not isinstance(status, str) else status
        if args == ['funnel', 'status', '--json']:
            if funnel is None:
                return ''
            return json.dumps(funnel)
        if args == ['funnel', 'status']:
            return text or ''
        raise AssertionError(args)
    return run


HOST = 'atul.example.ts.net'
URL = 'https://' + HOST + '/'
ME = {'Online': True, 'DNSName': HOST + '.', 'KeyExpiry': '2099-01-01T00:00:00Z'}
ON = {'AllowFunnel': {HOST + ':443': True}, 'Web': {HOST + ':443': {'Handlers': {'/': {'Proxy': 'http://127.0.0.1:8765'}}}}}


@pytest.mark.parametrize('status, funnel, state, words', [
    ({'BackendState': 'Running', 'Self': ME}, ON, 'ok', 'reachable'),
    ({'BackendState': 'NeedsLogin', 'Self': ME}, ON, 'bad', 'signed out'),
    ({'BackendState': 'NeedsMachineAuth', 'Self': ME}, ON, 'bad', 'Disable key expiry'),
    ({'BackendState': 'Stopped', 'Self': ME}, ON, 'bad', 'click Connect'),
    ({'BackendState': 'Running', 'Self': ME | {'Online': False}}, ON, 'bad', 'offline'),
    ({'BackendState': 'Running', 'Self': ME | {'DNSName': 'other.example.ts.net.'}}, ON, 'warn', 'other.example.ts.net'),
    ({'BackendState': 'Running', 'Self': ME}, {'AllowFunnel': {}}, 'bad', 'Funnel is off'),
    ({'BackendState': 'Running', 'Self': ME}, ON | {'Web': {HOST + ':443': {'Handlers': {'/': {'Proxy': 'http://127.0.0.1:3000'}}}}}, 'bad', 'port 8765'),
])
def test_the_tailscale_check(status, funnel, state, words):
    out = tunnel_watch.check(URL, 8765, runner(status, funnel), clock=lambda: 1_700_000_000)
    assert out['state'] == state and words in out['message'] and out['checked'] == 1_700_000_000


def test_a_key_that_expires_soon_is_a_warning():
    t = 1_700_000_000
    soon = time.strftime('%Y-%m-%dT%H:%M:%S.123456789Z', time.gmtime(t + 3 * 86400 - 60))
    out = tunnel_watch.check(URL, 8765, runner({'BackendState': 'Running', 'Self': ME | {'KeyExpiry': soon}}, ON), clock=lambda: t)
    assert out['state'] == 'warn' and 'in 3 days' in out['message'] and tunnel_watch.KEY_EXPIRY_FIX in out['message']


def test_the_check_says_nothing_when_it_cannot_tell():
    good = {'BackendState': 'Running', 'Self': ME}
    assert tunnel_watch.check('https://tips.example.com/', 8765, runner(good, ON)) is None  # not a Tailscale link
    assert tunnel_watch.check(URL, 8765, runner('not json', ON)) is None
    assert tunnel_watch.check(URL, 8765, runner({'BackendState': 'Starting'}, ON)) is None

    def broken(args):
        raise OSError('no tailscale')
    assert tunnel_watch.check(URL, 8765, broken) is None
    # older Tailscale without --json
    assert tunnel_watch.check(URL, 8765, runner(good, None, f'https://{HOST} (Funnel on)\n|-- / proxy http://127.0.0.1:8765'))['state'] == 'ok'
    assert tunnel_watch.check(URL, 8765, runner(good, None, f'https://{HOST} (tailnet only)'))['state'] == 'bad'
    assert tunnel_watch.check(URL, 8765, runner(good, None, 'something else')) is None


def test_the_watch_tells_the_dashboard_and_the_window(app, admin, monkeypatch, caplog):
    c, h = admin
    bad = {'state': 'bad', 'message': 'Viewers can’t reach your tip link: Tailscale is disconnected → reconnect.', 'checked': now()}
    monkeypatch.setattr(tunnel_watch, 'check', lambda url, port: bad)

    def stop(seconds):
        raise SystemExit
    monkeypatch.setattr(tunnel_watch.time, 'sleep', stop)
    with caplog.at_level(logging.WARNING, logger='acepressure.tunnel'), pytest.raises(SystemExit):
        tunnel_watch.TunnelWatch(app, 8765)._loop()
    assert app.extensions['ace_tunnel'] is bad
    logged = [r.getMessage() for r in caplog.records if r.name == 'acepressure.tunnel']
    assert logged and logged[0].isascii() and "can't reach" in logged[0] and '->' in logged[0]
    assert c.get('/api/admin/state').json['tunnel'] == bad
    app.extensions['ace_tunnel'] = bad | {'checked': now() - 301}
    assert c.get('/api/admin/state').json['tunnel'] is None  # an old result is not shown
    run = (ROOT / 'run.py').read_text(encoding='utf-8')
    assert 'TunnelWatch(app,port).start()' in run
    admin_js = read('static/admin.js')
    assert "if(tunnel)line(tunnel.state,tunnel.message);" in admin_js and "h.tip_page==='open'&&tunnel?.state!=='bad'" in admin_js


# ---------- 10. stronger moderation ----------
@pytest.mark.parametrize('text, words, whole, out', [
    ('Kshitij says hi', ['shit'], True, 'Kshitij says hi'),
    ('Kshitij says hi', ['shit'], False, 'K[filtered]ij says hi'),
    ('what the shit', ['shit'], True, 'what the [filtered]'),
    ('SHIT happens', ['shit'], True, '[filtered] happens'),
    ('noobs and noob and snoob', ['noob*'], True, '[filtered] and [filtered] and snoob'),
    ('you are a total noob', ['total noob'], True, 'you are a [filtered]'),
    ('भाई गाली', ['गाली'], True, 'भाई [filtered]'),
    ('गालीयाँ', ['गाली'], True, 'गालीयाँ'),
    ('hello', ['hell', ' ', '*', 5], True, 'hello'),
    ('anything', [], True, 'anything'),
])
def test_word_filter(text, words, whole, out):
    assert word_filter(text, words, whole) == out


def test_new_installs_match_whole_words_and_upgrades_keep_the_old_way(tmp_path):
    assert DEFAULTS['filter_whole_words'] is True
    assert Store(tmp_path / 'new', 's' * 48).settings()['filter_whole_words'] is True
    old = Store(tmp_path / 'old', 's' * 48)
    with old.db(True) as db:
        db.execute("DELETE FROM settings WHERE key='filter_whole_words'")  # a 1.6.3 database
    assert Store(tmp_path / 'old', 's' * 48).settings()['filter_whole_words'] is False
    assert Store(tmp_path / 'new', 's' * 48).settings()['filter_whole_words'] is True  # a restart changes nothing


def test_names_are_filtered_on_stream_and_blocked_trolls_leave_the_boards(app, admin):
    c, h = admin
    put_settings(app, banned_words=['noob'], hide_links=True)
    troll = verified_tip(app, name='noob.xyz', amount=900, message='spam')
    fan = verified_tip(app, name='Big noob fan', amount=500, message='GG')
    replay(c, h, fan)
    assert claim(c)['alert']['name'] == 'Big [filtered] fan'
    top = c.get('/api/public/top').json['supporters']
    assert [p['name'] for p in top] == ['[link]', 'Big [filtered] fan']
    c.post('/api/admin/supporters/' + troll['supporter_id'], json={'blocked': True}, headers=h)
    top = c.get('/api/public/top').json['supporters']
    assert top[0] == {'name': ANONYMOUS, 'total': 90000, 'count': 1}
    state = c.get('/api/overlay/state?period=lifetime', headers=OV).json
    assert state['top'][0]['name'] == ANONYMOUS and state['top'][0]['total'] == 90000
    recent = {r['name']: r for r in state['recent']}
    assert recent[ANONYMOUS]['message'] == '' and recent['Big [filtered] fan']['message'] == 'GG'
    assert all(set(r) == {'name', 'display_paise', 'message'} for r in state['recent'])  # no supporter ids on stream
    names = {t['name'] for t in c.get('/api/admin/state').json['recent']}
    assert {'noob.xyz', 'Big noob fan'} <= names  # the dashboard keeps the real names


def test_the_filter_switch_saves(app, admin):
    c, h = admin
    assert c.post('/api/admin/settings', json={'filter_whole_words': False}, headers=h).status_code == 200
    assert settings(app)['filter_whole_words'] is False
    assert c.post('/api/admin/settings', json={'filter_whole_words': 1}, headers=h).status_code == 400
    put_settings(app, banned_words=['shit'])
    assert app.store.moderated('Kshitij', settings(app)) == 'K[filtered]ij'
    put_settings(app, filter_whole_words=True)
    assert app.store.moderated('Kshitij', settings(app)) == 'Kshitij'


# ---------- the release ----------
def test_version_and_docs():
    assert tuple(int(x) for x in (ROOT / 'VERSION').read_text(encoding='utf-8').strip().split('.')) >= (1, 6, 4)
    docs = lambda name: (ROOT / 'docs' / name).read_text(encoding='utf-8')
    changelog = docs('CHANGELOG.md')
    assert ('\n' + changelog).count('\n# 1.6.4 — ') == 1 and changelog.index('# 1.6.4') < changelog.index('# 1.6.3')
    update = docs('UPDATE_1.6.4.md')
    assert '`run.py`' in update and 'Refresh cache of current page' in update and 'Disable key expiry' in update
    assert (ROOT / 'docs' / 'VALIDATION_1.6.4.md').is_file()
    # the 1.6.3 guide told you to hear the cut with Test alert, whose 40-character message is never cut
    assert 'press **Test alert**. Listen on the horizontal source' not in docs('UPDATE_1.6.3.md')
    assert 'press the button during a test alert' not in docs('VALIDATION_1.6.3.md')
    assert 'forever' not in docs('TAILSCALE_FUNNEL.md') and 'permanent' not in docs('TAILSCALE_FUNNEL.md')
