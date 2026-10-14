"""1.6.2: per-sound and voice volume, links hidden on stream, the spoken copy (pronunciations, no emoji, no long repeats),
context-aware Hinglish, Piper 1.2 compatibility, and payloads a 1.6.1 overlay still understands."""
import io
import json
import sqlite3
import sys
import types
import wave
from pathlib import Path

import pytest

from acepressure import piper_tts_service as piper
from acepressure import tts_service
from acepressure.domain import Store, now
from acepressure.text_filters import apply_pronunciations, hide_links, normalize_pronunciations, speech_text
from acepressure.tts_service import hindi_speech, is_hinglish, maybe_transliterate, transliterate_hinglish

OV = {'X-Overlay-Token': 'o' * 48}


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


def paid_tip(app, **kw):
    t = app.store.create_tip(dict(amount=100, name='Rahul', message='GG', tts=True) | kw, True)
    with app.store.db(True) as db: db.execute("UPDATE tips SET status='VERIFIED',verified=? WHERE id=?", (now(), t['id']))
    return t['id']


def replay(c, h, tid):
    r = c.post('/api/admin/alerts', json={'action': 'replay', 'id': tid}, headers=h)
    assert r.status_code == 200, r.json


def claim(c):
    return c.post('/api/overlay/claim', json={'channel': 'horizontal', 'owner': 'obs', 'client': 'obs'}, headers=OV).json


def alert_for(app, c, h, **tip):
    """Queue a verified tip, claim it as OBS and acknowledge it, so the next alert can be claimed."""
    replay(c, h, paid_tip(app, **tip))
    got = claim(c)
    c.post('/api/overlay/ack', json={'event_id': got['alert']['event_id'], 'channel': 'horizontal', 'owner': 'obs', 'client': 'obs'}, headers=OV)
    return got


def add_sound(c, h, name='Boom', **form):
    r = c.post('/api/admin/media', data={'kind': 'sound', 'file': (io.BytesIO(wav()), name + '.wav'), 'name': name} | form,
               headers=h, content_type='multipart/form-data')
    assert r.status_code in (200, 201), r.json
    return r.json['entry']


# ---------- links ----------
@pytest.mark.parametrize('text, shown', [
    ('check www.scam.com now', 'check [link] now'), ('visit https://bit.ly/x!', 'visit [link]'),
    ('join discord.gg/abc123 bhai', 'join [link] bhai'), ('t.me/freeskins', '[link]'), ('mail me abc.def@gmail.com', 'mail me [link]'),
    ('scam.xyz', '[link]'), ('amazon.in/deal', '[link]'), ('abc.co.in', '[link]'), ('WWW.SCAM.COM', '[link]'),
    ('bhai.com pe aao', '[link] pe aao'), ('see twitch.tv/name', 'see [link]'), ('http://1.2.3.4/x', '[link]'),
])
def test_links_are_hidden(text, shown):
    assert hide_links(text) == shown


@pytest.mark.parametrize('text', ['great stream.in the end', 'nice play.me too', 'gg.wp', 'e.g. this', 'v1.6.2 is out', 'Rs.500 tip',
                                  '5.30 pm', 'i.e. ok', 'U.S.A', 'No.1 fan', 'op.gg', 'bhai kya clutch tha', 'name@paytm'])
def test_ordinary_text_is_not_a_link(text):
    assert hide_links(text) == text


def test_alert_hides_links_in_message_and_name_but_the_record_keeps_them(app, admin):
    c, h = admin
    a = alert_for(app, c, h, name='visit scam.xyz', message='free skins at www.scam.com bhai')['alert']
    assert a['message'] == 'free skins at [link] bhai' and a['name'] == 'visit [link]'
    assert 'scam' not in a['speech'] and 'link' in a['speech']
    with app.store.db() as db:
        row = db.execute('SELECT name,message FROM tips ORDER BY created DESC LIMIT 1').fetchone()
    assert (row['name'], row['message']) == ('visit scam.xyz', 'free skins at www.scam.com bhai')  # the dashboard sees what was typed


def test_links_show_when_the_streamer_turns_hiding_off(app, admin):
    c, h = admin
    assert c.post('/api/admin/settings', json={'hide_links': False}, headers=h).status_code == 200
    a = alert_for(app, c, h, message='my clips: youtube.com/@me')['alert']
    assert a['message'] == 'my clips: youtube.com/@me'


def test_boards_and_tip_page_leaderboard_hide_links_in_names(app, admin):
    c, h = admin
    paid_tip(app, name='buy at scam.xyz', message='see t.me/x')
    state = c.get('/api/overlay/state?period=lifetime', headers=OV).json
    assert state['top'][0]['name'] == 'buy at [link]' and state['recent'][0]['name'] == 'buy at [link]'
    assert state['recent'][0]['message'] == 'see [link]'
    assert c.get('/api/public/top').json['supporters'][0]['name'] == 'buy at [link]'


# ---------- the spoken copy ----------
def test_speech_drops_emoji_and_long_repeats_but_never_numbers():
    assert speech_text('lol 😂😂😂😂😂 hahahahahaha') == 'lol hahaha'
    assert speech_text('hiiiiiiii ₹100000 tip 1111111 !!!!!!') == 'hiii ₹100000 tip 1111111!!!'
    assert speech_text('nice 🔥, bro 😂 .') == 'nice, bro.'  # no space left before punctuation
    assert speech_text('❤️❤️❤️❤️ love you 🇮🇳') == 'love you'
    assert speech_text('😂😂😂') == ''
    assert speech_text('😂😂 hahahaha', cleanup=False) == '😂😂 hahahaha'


def test_pronunciations_are_whole_word_case_insensitive_and_longest_first():
    entries = [{'word': 'AcePressure', 'say': 'Ace Pressure'}, {'word': 'gg', 'say': 'good game'}, {'word': 'gg ez', 'say': 'easy game'},
               {'word': '😂', 'say': 'haha'}, {'word': 'lol', 'say': ''}]
    assert speech_text('GG bhai, acepressure op! gg ez lol', entries) == 'good game bhai, Ace Pressure op! easy game'
    assert speech_text('ggwp 😂', entries) == 'ggwp haha'
    assert speech_text('Great stream AcePressure, gg', entries) == 'Great stream Ace Pressure, good game'
    assert speech_text('lol😂😂, gg', entries) == 'haha haha, good game'
    assert apply_pronunciations('भाई', [{'word': 'भ', 'say': 'x'}]) == 'भाई'  # a vowel sign is part of the word


def test_pronunciation_list_is_checked():
    assert normalize_pronunciations([{'word': ' Ace ', 'say': ' Ace Pressure '}, {'word': '', 'say': 'x'}]) == [{'word': 'Ace', 'say': 'Ace Pressure'}]
    for bad in ['x', [{'word': 'a', 'say': '1'}, {'word': 'A', 'say': '2'}], [{'word': 5}], [{'word': 'w', 'say': ''}] * 101]:
        with pytest.raises(ValueError):
            normalize_pronunciations(bad)


def test_pronunciations_save_through_settings(admin):
    c, h = admin
    r = c.post('/api/admin/settings', json={'pronunciations': [{'word': 'AcePressure', 'say': 'Ace Pressure'}, {'word': '  ', 'say': ''}]}, headers=h)
    assert r.status_code == 200
    assert c.get('/api/admin/state').json['settings']['pronunciations'] == [{'word': 'AcePressure', 'say': 'Ace Pressure'}]
    r = c.post('/api/admin/settings', json={'pronunciations': [{'word': 'gg', 'say': 'a'}, {'word': 'GG', 'say': 'b'}]}, headers=h)
    assert r.status_code == 400 and 'twice' in r.json['error']
    assert c.post('/api/admin/settings', json={'pronunciations': 'gg=good game'}, headers=h).status_code == 400


def test_alert_carries_the_spoken_copy_for_every_engine(app, admin, monkeypatch):
    c, h = admin
    put_settings(app, pronunciations=[{'word': 'AcePressure', 'say': 'Ace Pressure'}])
    a = alert_for(app, c, h, message='GG AcePressure 😂😂😂 bhai kya clutch tha')['alert']
    assert a['message'] == 'GG AcePressure 😂😂😂 bhai kya clutch tha'  # the card shows what was typed
    assert a['speech'] == 'GG Ace Pressure bhai kya clutch tha'
    assert a['speech_hi'] == 'GG Ace Pressure भाई क्या clutch था' and a['hinglish'] is True
    spoken = []

    def fake(directory, text, voice, engine):
        spoken.append(text); out = directory / 'fake.wav'; out.write_bytes(wav()); return out
    monkeypatch.setattr(tts_service, 'synthesize', fake)
    assert c.get(f"/api/overlay/tts/{a['event_id']}", headers=OV).status_code == 200
    assert spoken == ['GG Ace Pressure bhai kya clutch tha']  # the server voices read the same copy


def test_an_emoji_only_message_is_not_read(app, admin):
    c, h = admin
    a = alert_for(app, c, h, message='😂😂😂🔥🔥')['alert']
    assert a['tts'] is False and a['speech'] == '' and a['message'] == '😂😂😂🔥🔥'
    put_settings(app, tts_cleanup=False)
    assert alert_for(app, c, h, message='😂🔥')['alert']['tts'] is True


def test_voice_studio_preview_and_what_the_voice_reads(app, admin, monkeypatch):
    c, h = admin
    put_settings(app, pronunciations=[{'word': 'valo', 'say': 'Valorant'}])
    spoken = []

    def fake(directory, text, voice, engine):
        spoken.append(text); out = directory / 'fake.wav'; out.write_bytes(wav()); return out
    monkeypatch.setattr(tts_service, 'synthesize', fake)
    assert c.post('/api/admin/tts/preview', json={'voice': 'hi-IN', 'text': 'valo khelo 😂 www.x.com'}, headers=h).status_code == 200
    assert spoken == ['Valorant khelo [link]']
    r = c.post('/api/admin/tts/preview', json={'voice': 'hi-IN', 'text': '😂😂'}, headers=h)
    assert r.status_code == 400 and 'Nothing to read' in r.json['error']
    d = c.post('/api/admin/tts/spoken', json={'voice': 'hi-IN', 'text': 'bhai main aa gaya, valo time'}, headers=h).json
    assert d == {'reads': 'भाई मैं आ गया, Valorant time', 'hindi': None, 'shortened': False}
    d = c.post('/api/admin/tts/spoken', json={'voice': 'en-IN', 'text': 'bhai main aa gaya'}, headers=h).json
    assert d == {'reads': 'bhai main aa gaya', 'hindi': 'भाई मैं आ गया', 'shortened': False}
    assert c.post('/api/admin/tts/spoken', json={'voice': 'xx', 'text': 'hi'}, headers=h).status_code == 400


# ---------- volume ----------
def test_volume_column_is_added_to_an_existing_library(tmp_path):
    if sqlite3.sqlite_version_info < (3, 35):
        pytest.skip('DROP COLUMN needs SQLite 3.35')
    store = Store(tmp_path, 's' * 48)
    with store.db(True) as db:
        db.execute('ALTER TABLE soundboards DROP COLUMN volume')  # the 1.6.1 table
        db.execute("INSERT INTO soundboards(id,name,created) VALUES ('old-row','Old',1)")
    store = Store(tmp_path, 's' * 48)
    store = Store(tmp_path, 's' * 48)  # migrations are replayed on every start
    assert store.soundboard_get('old-row')['volume'] == 100


def test_sound_volume_saves_and_is_checked(admin):
    c, h = admin
    e = add_sound(c, h)
    assert e['volume'] == 100
    assert c.post(f"/api/admin/soundboard/{e['id']}", json={'volume': 35}, headers=h).json['entry']['volume'] == 35
    for bad in [5, 101, True, 50.5, '50', None]:
        assert c.post(f"/api/admin/soundboard/{e['id']}", json={'volume': bad}, headers=h).status_code == 400, bad
    for raw in ['NaN', 'Infinity']:  # Python's JSON parser accepts these
        r = c.post(f"/api/admin/soundboard/{e['id']}", data='{"volume": %s}' % raw, headers=h, content_type='application/json')
        assert r.status_code == 400, raw


def test_alert_and_previews_carry_the_volumes(app, admin):
    c, h = admin
    pick = add_sound(c, h, 'Pick', offered='1', min_paise='0')
    default = add_sound(c, h, 'Default', make_default='1')
    c.post(f"/api/admin/soundboard/{pick['id']}", json={'volume': 40}, headers=h)
    c.post(f"/api/admin/soundboard/{default['id']}", json={'volume': 70}, headers=h)
    c.post('/api/admin/settings', json={'tts_volume': 55}, headers=h)
    got = alert_for(app, c, h, soundboard_id=pick['id'])
    a = got['alert']
    assert a['volumes'] == {a['soundboard_clip']: 40, a['sound']: 70} and got['tts_volume'] == 55
    items = c.get('/api/public/soundboard').json['items']
    assert [i['volume'] for i in items if i['id'] == pick['id']] == [40]
    cfg = c.get('/api/public/config').json
    assert cfg['tts_volume'] == 55 and cfg['default_volume'] == 70
    c.post('/api/admin/soundboard/default', json={'value': 'chime'}, headers=h)
    a = alert_for(app, c, h)['alert']
    assert a['sound'] == 'chime' and a['volumes'] == {}  # built-in sounds have no library row
    assert c.get('/api/public/config').json['default_volume'] == 100


def test_voice_volume_is_checked(admin):
    c, h = admin
    for bad in [9, 101, 50.5, True, '80']:
        assert c.post('/api/admin/settings', json={'tts_volume': bad}, headers=h).status_code == 400, bad
    assert c.post('/api/admin/settings', json={'tts_volume': 10}, headers=h).status_code == 200


def test_a_161_overlay_still_gets_every_field_it_reads(app, admin):
    c, h = admin
    a = alert_for(app, c, h, message='GG')['alert']
    for key in ['event_id', 'id', 'name', 'display_paise', 'message', 'voice', 'sound', 'sound_source', 'test', 'test_label', 'tts', 'tier', 'seconds']:
        assert key in a, key


def test_a_failure_preparing_speech_never_stops_the_alert(app, admin, monkeypatch):
    c, h = admin
    monkeypatch.setattr(app.store, 'speech', lambda *a: 1 / 0)
    a = alert_for(app, c, h, message='GG bhai')['alert']
    assert a['message'] == 'GG bhai' and 'speech' not in a and 'volumes' not in a


# ---------- Hinglish ----------
HINDI_VOICE = 'hi-IN-MadhurNeural'
CORPUS = [
    ('bhai main tera bahut bada fan hoon', 'भाई मैं तेरा बहुत बड़ा fan हूँ'),
    ('aaj ka din mast tha', 'आज का दिन मस्त था'),
    ('main aa gaya bhai, tension mat lo', 'मैं आ गया भाई, tension मत लो'),
    ('Jett main hoon bhai', 'Jett main हूँ भाई'),
    ('bhai tu mera main duelist hai', 'भाई तू मेरा main duelist है'),
    ('mera main account ban ho gaya', 'मेरा main account ban हो गया'),
    ('main duelist hoon', 'मैं duelist हूँ'),
    ('mere bhai ko shoutout de do', 'मेरे भाई को shoutout दे दो'),
    ('bhai welcome to the stream', 'भाई welcome to the stream'),
    ('ye to op hai', 'ये तो op है'),
    ('main to gaya', 'मैं तो गया'),
    ('jai shri ram', 'जय श्री राम'),
    ('16gb ram hai bhai', '16gb ram है भाई'),
    ('mouse mat kaha se liya bhai', 'mouse mat कहा से लिया भाई'),
    ('mat kar na yaar', 'मत कर ना यार'),
    ('sab log aa gaye', 'सब लोग आ गए'),
    ('log in kar bhai', 'log in कर भाई'),
    ('Great stream bro, aaj ka din mast tha', 'Great stream bro, आज का दिन मस्त था'),
    ('NA server pe ho kya', 'NA server पे हो क्या'),
    ('BHAI MAIN AA GAYA', 'भाई मैं आ गया'),
    ('lo-fi music chala do bhai', 'lo-fi music चला दो भाई'),
    ('kya baat hai bhai, kamaal kar diya', 'क्या बात है भाई, कमाल कर दिया'),
    ('agli baar pakka jeetenge', 'अगली बार पक्का जीतेंगे'),
    ('sun bhai, ek baat bolu', 'सुन भाई, एक बात बोलूँ'),
    ('happy birthday bhai, janamdin mubarak', 'happy birthday भाई, जन्मदिन मुबारक'),
    ('भाई tu मेरा main duelist है', 'भाई तू मेरा main duelist है'),
]


@pytest.mark.parametrize('text, spoken', CORPUS)
def test_hinglish_corpus(text, spoken):
    assert maybe_transliterate(text, HINDI_VOICE) == spoken
    assert maybe_transliterate(text, 'en-IN-NeerjaNeural') == text  # English voices are never given Devanagari


@pytest.mark.parametrize('text', ['I play the main role', 'Put the mouse on the mat', 'Reyna main here', 'A mere detail', 'Upgrade the RAM',
                                  'lo and behold, nice play', 'I hum this song', 'That was a nice clutch', 'Do it to win', 'Ram is cheap now'])
def test_english_stays_english(text):
    assert not is_hinglish(text)
    assert transliterate_hinglish(text) == text


def test_hindi_copy_for_the_browser_engine():
    assert hindi_speech('gg bhai') == ('gg भाई', True)
    assert hindi_speech('nice clutch') == ('nice clutch', False)


def test_links_and_handles_are_never_converted():
    assert transliterate_hinglish('bhai.com pe aao bhai') == 'bhai.com पे आओ भाई'
    assert transliterate_hinglish("@bhai #bhai bhai's") == "@bhai #bhai bhai's"


# ---------- Piper ----------
def test_piper_12_without_synthesize_wav_still_works(tmp_path, monkeypatch):
    class OldVoice:  # piper-tts 1.2: synthesize(text, wav_file)
        @staticmethod
        def load(path):
            return OldVoice()

        def synthesize(self, text, wav_file):
            wav_file.setparams((1, 2, 22050, 0, 'NONE', 'not compressed')); wav_file.writeframes(b'\0\0' * 2205)
    monkeypatch.setitem(sys.modules, 'piper', types.SimpleNamespace(PiperVoice=OldVoice))
    monkeypatch.setattr(piper, '_LOADED_VOICES', {})
    monkeypatch.setattr(piper, '_have_piper', lambda: True)
    piper.models_dir(tmp_path).joinpath('hi_IN-test-medium.onnx').touch()
    with wave.open(str(piper.synthesize(tmp_path, 'bhai kya', 'hi_IN-test-medium'))) as w:
        assert w.getnframes() == 2205


# ---------- pages ----------
def read(name):
    return (Path(__file__).resolve().parents[1] / 'acepressure' / name).read_text(encoding='utf-8')


def test_overlay_uses_the_new_fields_and_falls_back_without_them():
    js = read('static/overlay.js')
    assert "const text=typeof p.speech==='string'?p.speech:p.message;" in js
    assert "typeof p.speech_hi==='string'?p.speech_hi:maybeTransliterate(text,voice)" in js and 'pickVoiceForText(text,p.voice,voices,p.hinglish)' in js
    assert 'try{a.volume=volume;}catch(_){}' in js and 'u.volume=volume;' in js and 'volumeLevel((p.volumes||{})[name])' in js
    assert "function volumeLevel(v){return typeof v==='number'&&v>=0&&v<=100?v/100:1;}" in read('static/common.js')


def test_dashboard_and_tip_page_controls():
    admin, designer, public = read('static/admin.js'), read('static/designer.js'), read('static/public.js')
    assert "vol.type='range';vol.min='10';vol.max='100'" in admin and "A('soundboard/'+e.id,{volume:v})" in admin
    assert "function pronunciations(root)" in admin and "A('settings',{pronunciations:items})" in admin
    assert "key:'tts_volume'" in admin and "key:'hide_links'" in admin and "key:'tts_cleanup'" in admin
    assert "A('tts/spoken',{text,voice})" in designer and 'player.volume=volumeLevel(state.settings.tts_volume)' in designer
    assert 'soundboardAudio.volume=previewVolume(item.volume)' in public and 'previewAudio.volume=previewVolume(config.default_volume)' in public
    assert 'volumeLevel' not in public  # the tip page may still hold the 1.6.1 common.js
