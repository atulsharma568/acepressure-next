"""1.6.3: "Read whole messages". Switched off, the voice reads only the first characters of a long message, cut after a
whole word, while the alert card still shows all of it."""
import io
import json
import wave

import pytest

from acepressure import tts_service
from acepressure.domain import DEFAULTS, Store, now
from acepressure.text_filters import first_part

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


def alert_for(app, c, h, **tip):
    """Queue a verified tip, claim it as OBS and acknowledge it, so the next alert can be claimed."""
    t = app.store.create_tip(dict(amount=100, name='Rahul', message='GG', tts=True) | tip, True)
    with app.store.db(True) as db: db.execute("UPDATE tips SET status='VERIFIED',verified=? WHERE id=?", (now(), t['id']))
    assert c.post('/api/admin/alerts', json={'action': 'replay', 'id': t['id']}, headers=h).status_code == 200
    got = c.post('/api/overlay/claim', json={'channel': 'horizontal', 'owner': 'obs', 'client': 'obs'}, headers=OV).json
    c.post('/api/overlay/ack', json={'event_id': got['alert']['event_id'], 'channel': 'horizontal', 'owner': 'obs', 'client': 'obs'}, headers=OV)
    return got['alert']


def record_voice(monkeypatch):
    spoken = []

    def fake(directory, text, voice, engine):
        spoken.append(text); out = directory / 'fake.wav'; out.write_bytes(wav()); return out
    monkeypatch.setattr(tts_service, 'synthesize', fake)
    return spoken


# ---------- where the cut falls ----------
@pytest.mark.parametrize('text, limit, part', [
    ('gg bhai kya clutch tha', 12, 'gg bhai kya'),
    ('gg bhai kya clutch', 11, 'gg bhai kya'),          # the limit lands on the end of a word
    ('Thanks bro, great stream', 11, 'Thanks bro'),      # no comma left hanging
    ('GG! Next one', 5, 'GG!'),
    ('भाई क्या क्लच था', 9, 'भाई क्या'),                  # Hindi words are kept whole too
    ('a' * 30, 20, 'a' * 20),                            # one long word is cut where the limit falls
    ('short message', 100, 'short message'),
    ('', 20, ''),
])
def test_first_part_ends_after_a_whole_word(text, limit, part):
    assert first_part(text, limit) == part


def test_whole_messages_are_read_by_default_and_after_upgrading_from_162(tmp_path):
    assert DEFAULTS['tts_read_full'] is True and DEFAULTS['tts_short_limit'] == 100
    store = Store(tmp_path, 's' * 48)
    with store.db(True) as db:
        db.execute("DELETE FROM settings WHERE key IN ('tts_read_full','tts_short_limit')")  # a 1.6.2 database
    s = Store(tmp_path, 's' * 48).settings()
    assert s['tts_read_full'] is True and s['tts_short_limit'] == 100
    assert Store(tmp_path, 's' * 48).speech(LONG, s) == LONG


# ---------- the alert ----------
def test_switched_off_the_voice_reads_the_first_part_and_the_card_shows_everything(app, admin):
    c, h = admin
    a = alert_for(app, c, h, message=LONG)
    assert a['message'] == LONG and a['speech'] == LONG
    put_settings(app, tts_read_full=False)
    a = alert_for(app, c, h, message=LONG)
    assert a['message'] == LONG  # the card
    assert a['speech'] == first_part(LONG, 100) and len(a['speech']) <= 100 and LONG.startswith(a['speech'])
    assert 'match' not in a['speech_hi'] and a['speech_hi'].startswith('भाई क्या clutch था')  # the Hindi copy is made from the cut copy
    assert a['tts'] is True
    put_settings(app, tts_short_limit=40)
    assert alert_for(app, c, h, message=LONG)['speech'] == 'Bhai kya clutch tha, aaj ka stream bahut'
    assert alert_for(app, c, h, message='GG bhai')['speech'] == 'GG bhai'  # short messages are read whole


def test_emoji_and_repeats_do_not_use_up_the_characters(app, admin):
    c, h = admin
    put_settings(app, tts_read_full=False, tts_short_limit=20)
    a = alert_for(app, c, h, message='😂' * 40 + ' hahahahahahaha GG bhai, next match jeetenge')
    assert a['speech'] == 'hahaha GG bhai, next'


def test_server_voices_read_the_same_first_part(app, admin, monkeypatch):
    c, h = admin
    put_settings(app, tts_read_full=False)
    spoken = record_voice(monkeypatch)
    a = alert_for(app, c, h, message=LONG)
    assert c.get(f"/api/overlay/tts/{a['event_id']}", headers=OV).status_code == 200
    assert spoken == [a['speech']] and a['speech'] != LONG


# ---------- saving the switch ----------
def test_the_switch_saves_and_is_checked(admin):
    c, h = admin
    assert c.post('/api/admin/settings', json={'tts_read_full': False}, headers=h).status_code == 200
    assert c.post('/api/admin/settings', json={'tts_short_limit': 60}, headers=h).status_code == 200
    s = c.get('/api/admin/state').json['settings']
    assert s['tts_read_full'] is False and s['tts_short_limit'] == 60
    for bad in ['no', 0, 1, None]:
        assert c.post('/api/admin/settings', json={'tts_read_full': bad}, headers=h).status_code == 400, bad
    for bad in [19, 501, 50.5, True, '60', None]:
        r = c.post('/api/admin/settings', json={'tts_short_limit': bad}, headers=h)
        assert r.status_code == 400 and 'from 20 to 500' in r.json['error'], bad
    assert c.post('/api/admin/settings', json={'tts_limit': True}, headers=h).status_code == 400  # True is not 1 character
    assert c.post('/api/admin/settings', json={'tts_read_full': True}, headers=h).status_code == 200


def test_voice_studio_shows_when_the_sample_is_cut(app, admin, monkeypatch):
    c, h = admin
    put_settings(app, tts_read_full=False, tts_short_limit=20)
    d = c.post('/api/admin/tts/spoken', json={'voice': 'en-IN', 'text': LONG}, headers=h).json
    assert d['reads'] == 'Bhai kya clutch tha' and d['shortened'] is True
    assert c.post('/api/admin/tts/spoken', json={'voice': 'en-IN', 'text': 'GG bhai'}, headers=h).json['shortened'] is False
    spoken = record_voice(monkeypatch)
    assert c.post('/api/admin/tts/preview', json={'voice': 'en-IN', 'text': LONG}, headers=h).status_code == 200
    assert spoken == ['Bhai kya clutch tha']  # Listen plays what OBS would


def test_the_tip_page_is_told(app, client):
    cfg = client.get('/api/public/config').json
    assert cfg['tts_read_full'] is True and cfg['tts_short_limit'] == 100
    put_settings(app, tts_read_full=False, tts_short_limit=80)
    cfg = client.get('/api/public/config').json
    assert cfg['tts_read_full'] is False and cfg['tts_short_limit'] == 80


# ---------- pages ----------
def read(name):
    from pathlib import Path
    return (Path(__file__).resolve().parents[1] / 'acepressure' / name).read_text(encoding='utf-8')


def test_dashboard_voice_studio_and_tip_page_controls():
    admin, designer, public = read('static/admin.js'), read('static/designer.js'), read('static/public.js')
    assert "key:'tts_read_full'" in admin and "key:'tts_short_limit'" in admin and "attrs:{min:20,max:500,step:1}" in admin
    assert "state.settings.tts_read_full===false?'Read whole messages':'Shorten long messages'" in admin  # Live activity and the OBS dock
    assert "A('settings',{tts_read_full:state.settings.tts_read_full===false})" in admin
    assert "if(s.tts_read_full===false)line('muted'" in admin
    assert "d.shortened?" in designer and 'state.settings.tts_read_full,state.settings.tts_short_limit' in designer
    assert "if(config.tts_read_full===false)" in public and "n.id='tts-short-note'" in public
