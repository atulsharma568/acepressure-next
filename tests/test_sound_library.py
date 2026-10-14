"""1.6.0 sound library: the one-time migration, the default sound, viewer picks, what each alert plays, claim-time
repairs, the file lifecycle, library uploads, the 1.5.9 pages, dashboards and overlays left open across the upgrade,
and the bundled starter sounds. legacy() builds the exact 1.5.9 state; make_app() then starts 1.6.0 on it, which runs the migration."""
import hashlib
import io
import json
import logging
import re
import shutil
import sqlite3
import wave
from pathlib import Path

import pytest
from PIL import Image
from werkzeug.security import generate_password_hash

from acepressure import app as app_module
from acepressure import domain, video
from acepressure.app import create_app
from acepressure.domain import DEFAULTS, SOUND_MAX_MS, STARTER_AUDIO, STARTER_DIR, STORED_SOUND, Store, now, uid
from acepressure.video import validate_or_fix_audio
from acepressure.visuals import DEFAULT_VISUALS

OV = {'X-Overlay-Token': 'o' * 48}
PASSWORD_HASH = generate_password_hash('test-password-123')
BACKUP = 'before-1.6.0-sound-library.sqlite3'


# ---------- helpers ----------
def make_app(path):
    """The conftest app on an existing data folder."""
    return create_app(dict(TESTING=True, DATA_DIR=str(path), SECRET_KEY='s' * 48, BRIDGE_TOKEN='b' * 48, OVERLAY_TOKEN='o' * 48,
                           ADMIN_PASSWORD_HASH=PASSWORD_HASH, DEMO_MODE=True))


def login(app):
    c = app.test_client()
    return c, {'X-CSRF-Token': c.post('/api/login', json={'password': 'test-password-123'}).json['csrf']}


def wav(sec=0.5):
    """Silent 8 kHz mono PCM WAV."""
    b = io.BytesIO()
    with wave.open(b, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        w.writeframes(b'\x00\x00' * int(8000 * sec))
    return b.getvalue()


def png():
    b = io.BytesIO(); Image.new('RGBA', (32, 32), (220, 54, 85, 255)).save(b, format='PNG'); return b.getvalue()


def legacy(tmp_path, settings=None, rows=(), files=(), tips=()):
    """Build the exact 1.5.9 state and return its folder.
    rows: soundboards rows in display order; files: names written to data/media (a dict maps names to bytes);
    tips: verified tips made before the upgrade. Unset row and tip columns get 1.5.9-like defaults."""
    path = Path(tmp_path)
    store = Store(path, 's' * 48)  # the 001-007 schema and DEFAULTS
    t0 = now() - 3600
    with store.db(True) as db:
        db.execute("DELETE FROM settings WHERE key IN ('default_sound','sound_library_migrated')")  # 1.5.9 had neither key
        for k, v in (settings or {}).items():
            db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (k, json.dumps(v)))
        for i, r in enumerate(rows):
            r = dict(id=uid(), name=f'Slot {i + 1}', emoji='', category='General', min_paise=5000, display_order=10 * (i + 1),
                     enabled=1, media_filename=None, duration_ms=0, created=t0 + i) | r
            db.execute('INSERT INTO soundboards(id,name,emoji,category,min_paise,display_order,enabled,media_filename,duration_ms,created) '
                       'VALUES (:id,:name,:emoji,:category,:min_paise,:display_order,:enabled,:media_filename,:duration_ms,:created)', r)
        for i, t in enumerate(tips):
            t = dict(id=uid(), name=f'Viewer {i + 1}', display_paise=10000, sound='chime', soundboard_id=None, status='VERIFIED',
                     created=t0 + 100 + i) | t
            sup = uid()
            db.execute('INSERT INTO supporters(id,identity_hash,name) VALUES (?,?,?)', (sup, 'legacy-' + sup, t['name']))
            db.execute('INSERT INTO tips(id,token,supporter_id,name,display_paise,requested_paise,message,created,expires,verified,'
                       'status,tts,voice,sound,soundboard_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (t['id'], uid() + uid(), sup, t['name'], t['display_paise'], t['display_paise'] + 7, 'GG', t['created'],
                        t['created'] + 600, t['created'] + 60, t['status'], 0, 'en-IN', t['sound'], t['soundboard_id']))
    media = path / 'media'; media.mkdir(exist_ok=True)
    for name in files:
        (media / name).write_bytes(files[name] if isinstance(files, dict) else wav(0.2))
    return path


def raw_settings(dbfile):
    con = sqlite3.connect(str(dbfile))
    try: return {k: json.loads(v) for k, v in con.execute('SELECT key,value FROM settings')}
    finally: con.close()


def media_listing(path):
    return {f.name: (hashlib.sha256(f.read_bytes()).hexdigest(), f.stat().st_mtime_ns) for f in (Path(path) / 'media').iterdir()}


def put_settings(app, **values):
    with app.store.db(True) as db:
        for k, v in values.items():
            db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (k, json.dumps(v)))


def video_bundle(app, flag=True, **visuals):
    """What an alert bundle leaves for a video with its own sound (built directly, so FFmpeg isn't needed)."""
    media = app.store.path / 'media'; media.mkdir(exist_ok=True)
    (media / 'clip.webm').write_bytes(b'\x1aE\xdf\xa3 webm')
    put_settings(app, visuals=dict(DEFAULT_VISUALS, alert_image='clip.webm', alert_video_has_audio=flag) | visuals)


def upload(c, h, filename='Bell.wav', data=None, **form):
    fields = {'kind': 'sound', 'file': (io.BytesIO(wav() if data is None else data), filename)} | {k: str(v) for k, v in form.items()}
    return c.post('/api/admin/media', data=fields, headers=h, content_type='multipart/form-data')


def slot_upload(c, h, sid, filename='clip.wav', data=None):
    return c.post(f'/api/admin/soundboard/{sid}/media', data={'file': (io.BytesIO(wav() if data is None else data), filename)},
                  headers=h, content_type='multipart/form-data')


def set_default(c, h, value):
    return c.post('/api/admin/soundboard/default', json={'value': value}, headers=h)


def paid_tip(app, **kw):
    """A verified tip made through the real create_tip path."""
    t = app.store.create_tip(dict(amount=100, name='Rahul', message='GG') | kw, True)
    with app.store.db(True) as db: db.execute("UPDATE tips SET status='VERIFIED',verified=? WHERE id=?", (now(), t['id']))
    return t['id']


def replay(c, h, tid):
    r = c.post('/api/admin/alerts', json={'action': 'replay', 'id': tid}, headers=h)
    assert r.status_code == 200, r.json


def send_test_alert(c, h, **kw):
    return c.post('/api/admin/alerts', json={'action': 'test'} | kw, headers=h)


def payloads(app):
    with app.store.db() as db: return [json.loads(r[0]) for r in db.execute('SELECT payload FROM alerts ORDER BY id')]


def last_payload(app): return payloads(app)[-1]


def queue_raw(app, payload, tip_id=None):
    """Queue an alert exactly as an older build stored it."""
    with app.store.db(True) as db:
        cur = db.execute('INSERT INTO alerts(tip_id,payload,created,expires) VALUES (?,?,?,?)', (tip_id, json.dumps(payload), now(), now() + 300))
        for channel in ['horizontal', 'vertical']: db.execute('INSERT INTO deliveries(alert_id,channel) VALUES (?,?)', (cur.lastrowid, channel))


def frozen_159_payload(sound):
    return {'id': 'test-' + uid(), 'name': 'Rahul', 'display_paise': 10000, 'message': 'GG', 'voice': 'en-IN', 'sound': sound,
            'test': True, 'test_label': 'TEST ALERT • NO MONEY RECEIVED', 'tts': False, 'tier': 1, 'seconds': 9}


def claim(c, channel='horizontal'):
    return c.post('/api/overlay/claim', json={'channel': channel, 'owner': 'obs'}, headers=OV).json


def ack(c, alert, channel='horizontal'):
    r = c.post('/api/overlay/ack', json={'event_id': alert['event_id'], 'channel': channel, 'owner': 'obs'}, headers=OV)
    assert r.status_code == 200


def audits(app, action):
    with app.store.db() as db:
        return [{'object_id': r[0], 'detail': json.loads(r[1])} for r in db.execute('SELECT object_id,detail FROM audit WHERE action=? ORDER BY id', (action,))]


def studio_body(**changes):
    """Everything a 1.5.9 Design studio form posts (it never sends alert_video_has_audio)."""
    return {k: v for k, v in DEFAULT_VISUALS.items() if k != 'alert_video_has_audio'} | changes


def boom(*args, **kwargs):
    raise RuntimeError('simulated failure')


# ---------- the one-time migration ----------
class TestMigration:
    def test_fresh_install_writes_only_the_marker_and_chime(self, tmp_path):
        app = make_app(tmp_path)
        s = raw_settings(tmp_path / 'acepressure.sqlite3')
        assert set(s) == set(DEFAULTS) | {'default_sound', 'sound_library_migrated'}
        assert {k: s[k] for k in DEFAULTS} == DEFAULTS and s['default_sound'] == 'chime'
        m = s['sound_library_migrated']
        assert m['version'] == 1 and isinstance(m['at'], int) and m['default'] == 'chime' and m['previous_alert_sound'] is None
        assert (m['imported'], m['linked'], m['skipped'], m['had_fixed_sound'], m['picks_turned_on']) == (0, 0, 0, False, False)
        with app.store.db() as db:
            assert db.execute('SELECT COUNT(*) FROM audit').fetchone()[0] == 0
            assert db.execute('SELECT COUNT(*) FROM soundboards').fetchone()[0] == 0
        assert not (tmp_path / 'backups').exists()

    def test_offered_uploads_become_pickable_items_named_from_labels(self, tmp_path):
        path = legacy(tmp_path, settings={'sounds': ['chime', 'pulse', 'none', 'Aa1.mp3', 'Bb2.wav', 'Lost3.mp3'],
                                          'media_labels': {'Aa1.mp3': 'Airhorn.mp3', 'Bb2.wav': 'Bruh Sound (1).wav'}},
                      files=['Aa1.mp3', 'Bb2.wav'])
        app = make_app(path)
        rows = {r['media_filename']: (r['name'], r['enabled'], r['min_paise'], r['category']) for r in app.store.soundboard_list()}
        assert rows == {'Aa1.mp3': ('Airhorn', 1, 0, 'General'), 'Bb2.wav': ('Bruh Sound (1)', 1, 0, 'General'),
                        'Lost3.mp3': ('Uploaded sound 1', 1, 0, 'General')}, 'a listed sound is imported even if its file is missing'
        s = app.store.settings()
        assert s['default_sound'] == 'chime' and s['sound_library_migrated']['imported'] == 3
        assert [x['name'] for x in app.test_client().get('/api/public/soundboard').json['items']] == ['Airhorn', 'Bruh Sound (1)']
        assert len(audits(app, 'sound_library_migrated')) == 1

    def test_uploads_viewers_could_not_choose_are_imported_hidden(self, tmp_path):
        path = legacy(tmp_path, settings={'sounds': ['pulse', 'Aa1.mp3'], 'allow_sound_choice': False,
                                          'media_labels': {'Aa1.mp3': 'Airhorn.mp3'}}, files=['Aa1.mp3'])
        app = make_app(path)
        [row] = app.store.soundboard_list()
        assert (row['name'], row['enabled'], row['min_paise']) == ('Airhorn', 0, 0)
        s = app.store.settings()
        assert s['default_sound'] == 'pulse' and s['sounds'][0] == 'pulse' and s['allow_sound_choice'] is False

    def test_unlisted_known_upload_is_imported_hidden_and_one_without_a_file_skipped(self, tmp_path):
        path = legacy(tmp_path, settings={'media_labels': {'Un1.mp3': 'Unlisted.mp3', 'Gone2.mp3': 'Gone.mp3'}, 'media_auto_fixed': ['Fx3.mp3']},
                      files=['Un1.mp3', 'Fx3.mp3'])
        app = make_app(path)
        rows = {r['media_filename']: (r['name'], r['enabled']) for r in app.store.soundboard_list()}
        assert rows == {'Fx3.mp3': ('Uploaded sound 1', 0), 'Un1.mp3': ('Unlisted', 0)}
        s = app.store.settings()
        assert s['sounds'] == DEFAULTS['sounds'] and s['default_sound'] == 'chime' and s['sound_library_migrated']['imported'] == 2

    def test_fixed_design_studio_file_becomes_the_default(self, tmp_path):
        vis = dict(DEFAULT_VISUALS, accent='#112233', radius=22, alert_sound='Xx1.mp3')
        app = make_app(legacy(tmp_path / 'offered', settings={'sounds': ['chime', 'pulse', 'none', 'Xx1.mp3'], 'visuals': vis,
                                                              'media_labels': {'Xx1.mp3': 'Bell.mp3'}}, files=['Xx1.mp3']))
        [row] = app.store.soundboard_list()
        s = app.store.settings(); m = s['sound_library_migrated']
        assert (row['name'], row['enabled'], row['media_filename']) == ('Bell', 1, 'Xx1.mp3')
        assert s['default_sound'] == row['id'] and s['sounds'][0] == 'Xx1.mp3'
        assert s['visuals'] == dict(vis, alert_sound='viewer'), 'every other visuals key is kept'
        assert m['had_fixed_sound'] is True and m['previous_alert_sound'] == 'Xx1.mp3' and m['default'] == row['id']
        # Never offered and unlabelled: a hidden row called "Alert sound".
        app2 = make_app(legacy(tmp_path / 'hidden', settings={'visuals': dict(DEFAULT_VISUALS, alert_sound='Yy2.wav')}, files=['Yy2.wav']))
        [row2] = app2.store.soundboard_list()
        assert (row2['name'], row2['enabled']) == ('Alert sound', 0) and app2.store.settings()['default_sound'] == row2['id']

    def test_fixed_builtin_becomes_the_default(self, tmp_path):
        app = make_app(legacy(tmp_path, settings={'sounds': ['chime', 'Aa1.mp3'], 'visuals': dict(DEFAULT_VISUALS, alert_sound='pulse')},
                              files=['Aa1.mp3']))
        s = app.store.settings()
        assert s['default_sound'] == 'pulse' and s['sounds'] == ['pulse', 'chime', 'Aa1.mp3'] and s['visuals']['alert_sound'] == 'viewer'

    def test_video_bundle_with_sound_becomes_video(self, tmp_path):
        vis = dict(DEFAULT_VISUALS, alert_image='Vv1.webm', alert_sound='none', alert_video_has_audio=True)
        app = make_app(legacy(tmp_path, settings={'visuals': vis}, files={'Vv1.webm': b'\x1aE\xdf\xa3'}))
        s = app.store.settings()
        assert s['default_sound'] == 'video' and s['sounds'][0] == 'none'
        assert s['visuals'] == dict(vis, alert_sound='viewer'), 'the flag is kept'
        assert app.store.soundboard_list() == []

    def test_cleared_video_flag_migrates_to_silent(self, tmp_path):
        vis = dict(DEFAULT_VISUALS, alert_image='Vv1.webm', alert_sound='none', alert_video_has_audio=False)
        s = make_app(legacy(tmp_path, settings={'visuals': vis}, files={'Vv1.webm': b'\x1aE\xdf\xa3'})).store.settings()
        assert s['default_sound'] == 'none' and s['sounds'][0] == 'none' and s['visuals']['alert_video_has_audio'] is False

    def test_live_soundboard_turns_picks_on_and_keeps_imports_hidden(self, tmp_path):
        app = make_app(legacy(tmp_path, settings={'sounds': ['chime', 'Aa1.mp3'], 'allow_sound_choice': False},
                              rows=[dict(name='Chai Peelo', media_filename='Cp1.mp3'), dict(name='Thug Life', enabled=0)],
                              files=['Aa1.mp3', 'Cp1.mp3']))
        s = app.store.settings()
        assert s['allow_sound_choice'] is True and s['sound_library_migrated']['picks_turned_on'] is True
        rows = {r['name']: (r['enabled'], r['min_paise'], r['media_filename']) for r in app.store.soundboard_list()}
        assert rows == {'Chai Peelo': (1, 5000, 'Cp1.mp3'), 'Thug Life': (0, 5000, None), 'Uploaded sound 1': (0, 0, 'Aa1.mp3')}
        assert [x['name'] for x in app.test_client().get('/api/public/soundboard').json['items']] == ['Chai Peelo']

    def test_choice_off_without_a_live_board_stays_off(self, tmp_path):
        app = make_app(legacy(tmp_path, settings={'allow_sound_choice': False}, files=['Hc1.mp3'],
                              rows=[dict(name='Thug Life', enabled=0), dict(name='Hidden clip', media_filename='Hc1.mp3', enabled=0),
                                    dict(name='Empty slot', enabled=1)]))
        s = app.store.settings()
        assert s['allow_sound_choice'] is False and s['sound_library_migrated']['picks_turned_on'] is False

    def test_file_already_on_a_row_is_linked_not_duplicated(self, tmp_path):
        app = make_app(legacy(tmp_path, settings={'sounds': ['Cp1.mp3', 'chime'], 'media_labels': {'Cp1.mp3': 'chai.mp3'}},
                              rows=[dict(name='Chai Peelo', media_filename='Cp1.mp3')], files=['Cp1.mp3']))
        [row] = app.store.soundboard_list()
        s = app.store.settings(); m = s['sound_library_migrated']
        assert (row['name'], row['min_paise']) == ('Chai Peelo', 5000) and (m['linked'], m['imported']) == (1, 0)
        assert s['default_sound'] == row['id'] and s['sounds'][0] == 'Cp1.mp3'

    def test_hand_typed_entries_are_skipped_and_kept(self, tmp_path):
        sounds = ['chime', 'my sound', 'https://example.com/a.mp3', '../evil.mp3']
        app = make_app(legacy(tmp_path, settings={'sounds': sounds}))
        s = app.store.settings()
        assert app.store.soundboard_list() == [] and s['sound_library_migrated']['skipped'] == 3
        assert s['sounds'] == sounds and s['default_sound'] == 'chime'

    def test_runs_once_and_a_deleted_import_stays_deleted(self, tmp_path):
        path = legacy(tmp_path, settings={'sounds': ['chime', 'Aa1.mp3']}, files=['Aa1.mp3'])
        app = make_app(path)
        marker = app.store.settings()['sound_library_migrated']
        [row] = app.store.soundboard_list()
        app.store.soundboard_delete(row['id'])
        again = Store(path, 's' * 48)
        assert again.soundboard_list() == [] and again.settings()['sound_library_migrated'] == marker
        assert len(audits(app, 'sound_library_migrated')) == 1

    def test_never_touches_media_files(self, tmp_path):
        path = legacy(tmp_path, settings={'sounds': ['chime', 'Aa1.mp3', 'my sound', 'Lost2.mp3'], 'media_labels': {'Un5.wav': 'old.wav'},
                                          'visuals': dict(DEFAULT_VISUALS, alert_sound='Xx3.ogg', alert_image='Vv4.webm')},
                      rows=[dict(name='Clip', media_filename='Cp6.mp3')],
                      files={'Aa1.mp3': wav(), 'Xx3.ogg': b'OggS', 'Vv4.webm': b'webm', 'Un5.wav': wav(), 'Cp6.mp3': wav(),
                             'notes.txt': b'keep me', 'art.png': png()})
        before = media_listing(path)
        app = make_app(path); make_app(path)
        assert media_listing(path) == before
        assert len(app.store.soundboard_list()) == 5

    def test_backup_written_once_before_migrating(self, tmp_path):
        path = legacy(tmp_path / 'data', settings={'sounds': ['chime', 'Aa1.mp3']}, files=['Aa1.mp3'])
        make_app(path)
        backup = path / 'backups' / BACKUP
        assert [p.name for p in (path / 'backups').iterdir()] == [BACKUP]
        stamp = backup.stat().st_mtime_ns
        peek = tmp_path / 'peek.sqlite3'; peek.write_bytes(backup.read_bytes())  # read a copy, never the backup itself
        old = raw_settings(peek)
        assert 'sound_library_migrated' not in old and 'default_sound' not in old and old['sounds'] == ['chime', 'Aa1.mp3']
        make_app(path)
        assert backup.stat().st_mtime_ns == stamp and [p.name for p in (path / 'backups').iterdir()] == [BACKUP]

    def test_failure_rolls_back_and_is_retried_on_the_next_start(self, tmp_path, monkeypatch, caplog):
        path = legacy(tmp_path, settings={'sounds': ['chime', 'Aa1.mp3']}, files=['Aa1.mp3'])
        before = raw_settings(path / 'acepressure.sqlite3')
        monkeypatch.setattr(Store, '_insert_sound', boom)
        with caplog.at_level(logging.ERROR, logger='acepressure.sounds'):
            app = make_app(path)
        assert 'retried on the next start' in caplog.text
        assert raw_settings(path / 'acepressure.sqlite3') == before and app.store.soundboard_list() == []
        c = app.test_client()
        assert c.get('/health').status_code == 200 and c.get('/api/public/config').json['sounds'] == ['chime']
        backup = path / 'backups' / BACKUP; stamp = backup.stat().st_mtime_ns
        monkeypatch.undo()
        s = make_app(path).store.settings()
        assert s['sound_library_migrated']['imported'] == 1 and s['default_sound'] == 'chime'
        assert backup.stat().st_mtime_ns == stamp, 'the retry keeps the backup taken before the first attempt'


# ---------- the default sound ----------
class TestDefaultSound:
    def test_builtin_default_heads_the_mirror_and_is_audited(self, app, admin):
        c, h = admin
        r = set_default(c, h, 'pulse')
        assert r.status_code == 200 and r.json == {'ok': True, 'default': 'pulse'}
        s = app.store.settings()
        assert s['default_sound'] == 'pulse' and s['sounds'] == ['pulse', 'chime', 'none']
        assert audits(app, 'default_sound_changed') == [{'object_id': 'pulse', 'detail': {'from': 'chime', 'to': 'pulse', 'source': 'admin'}}]
        assert set_default(c, h, 'pulse').status_code == 200 and len(audits(app, 'default_sound_changed')) == 1, 'no change, no audit row'

    def test_item_without_audio_gets_409(self, app, admin):
        c, h = admin
        sid = app.store.soundboard_create(name='Thug Life')['id']
        r = set_default(c, h, sid)
        assert r.status_code == 409 and r.json['error'] == 'Upload audio for “Thug Life” first.'
        assert app.store.settings()['default_sound'] == 'chime'

    def test_item_with_a_missing_file_gets_409(self, app, admin):
        c, h = admin
        r = upload(c, h, 'Bell.wav')
        (app.store.path / 'media' / r.json['name']).unlink()
        r2 = set_default(c, h, r.json['entry']['id'])
        assert r2.status_code == 409 and r2.json['error'] == 'The audio file for “Bell” is missing. Replace its audio first.'

    def test_unknown_id_gets_404_and_garbage_400(self, app, admin):
        c, h = admin
        r = set_default(c, h, 'abcdefghijklmnop')
        assert r.status_code == 404 and r.json['error'] == 'That sound no longer exists.'
        for bad in ['ab', '../etc/passwd', '', None, 5, ['chime'], {'value': 'chime'}]:
            r = set_default(c, h, bad)
            assert r.status_code == 400 and r.json['error'] == 'Choose Chime, Pulse, Silent, your alert video’s sound or one of your sounds.', bad
        assert app.store.settings()['default_sound'] == 'chime'

    def test_video_gets_409_without_a_video_with_sound(self, app, admin):
        c, h = admin
        r = set_default(c, h, 'video')
        assert r.status_code == 409 and r.json['error'] == 'Your alert visual has no sound of its own. Upload a video with sound as an alert bundle first.'
        video_bundle(app, flag=False)
        assert set_default(c, h, 'video').status_code == 409
        video_bundle(app)
        assert set_default(c, h, 'video').json == {'ok': True, 'default': 'video'} and app.store.settings()['sounds'][0] == 'none'

    def test_deleting_the_default_item_resets_to_chime(self, app, admin):
        c, h = admin
        other = upload(c, h, 'Other.wav').json['entry']['id']
        r = upload(c, h, 'Bell.wav', make_default=1); sid, name = r.json['entry']['id'], r.json['name']
        assert app.store.settings()['default_sound'] == sid
        assert c.delete('/api/admin/soundboard/' + other, headers=h).json == {'ok': True, 'default_reset': False}
        assert c.delete('/api/admin/soundboard/' + sid, headers=h).json == {'ok': True, 'default_reset': True}
        s = app.store.settings()
        assert s['default_sound'] == 'chime' and s['sounds'][0] == 'chime' and name not in s['sounds']
        assert audits(app, 'default_sound_changed')[-1]['detail'] == {'from': sid, 'to': 'chime', 'source': 'delete'}

    def test_replacing_the_defaults_audio_updates_the_mirror_and_removes_the_old_file(self, app, admin):
        c, h = admin
        r = upload(c, h, 'Bell.wav', make_default=1); sid, old = r.json['entry']['id'], r.json['name']
        assert app.store.settings()['sounds'][0] == old
        new = slot_upload(c, h, sid, 'Bell v2.wav').json['entry']['media_filename']
        s = app.store.settings(); media = app.store.path / 'media'
        assert s['default_sound'] == sid and s['sounds'][0] == new and old not in s['sounds'] and old not in s['media_labels']
        assert not (media / old).exists() and (media / new).exists()

    def test_default_problem_is_reported_and_alerts_play_chime(self, app, admin):
        c, h = admin
        r = upload(c, h, 'Bell.wav', make_default=1); sid = r.json['entry']['id']
        (app.store.path / 'media' / r.json['name']).unlink()
        lib = c.get('/api/admin/soundboard', headers=h).json
        assert (lib['default'], lib['default_kind'], lib['default_name'], lib['default_problem']) == (sid, 'item', 'Bell', 'file_missing')
        assert send_test_alert(c, h).status_code == 200
        assert last_payload(app)['sound'] == 'chime'
        cfg = c.get('/api/public/config').json
        assert cfg['sounds'] == ['chime'] and cfg['sound_labels'] == {}
        video_bundle(app); assert set_default(c, h, 'video').status_code == 200
        (app.store.path / 'media' / 'clip.webm').unlink()
        lib = c.get('/api/admin/soundboard', headers=h).json
        assert (lib['default'], lib['default_kind'], lib['default_problem'], lib['video_audio_available']) == ('video', 'video', 'no_video_audio', False)
        send_test_alert(c, h)
        assert last_payload(app)['sound'] == 'chime'

    def test_settings_post_rejects_default_sound_and_the_marker(self, app, admin):
        c, h = admin
        for key, value in [('default_sound', 'pulse'), ('sound_library_migrated', {'version': 1})]:
            r = c.post('/api/admin/settings', json={key: value}, headers=h)
            assert r.status_code == 400 and r.json['error'] == 'Unknown setting.', key
        s = app.store.settings()
        assert s['default_sound'] == 'chime' and s['sound_library_migrated']['version'] == 1


# ---------- viewer picks on the tip page ----------
class TestTipPicks:
    def test_sound_is_ignored_and_the_tip_stores_the_default(self, app, admin):
        c, h = admin
        set_default(c, h, 'pulse')
        for sound in ['none', 'chime', '../../etc/passwd', 42]:
            r = c.post('/api/public/tips', json={'amount': 100, 'name': 'Asha', 'sound': sound})
            assert r.status_code == 201, (sound, r.json)
        with app.store.db() as db:
            assert {row[0] for row in db.execute('SELECT sound FROM tips')} == {'pulse'}
        r = c.post('/api/public/tips', json={'amount': 100, 'name': 'Asha', 'voice': 'xx-XX'})
        assert r.status_code == 400 and r.json['error'] == 'Invalid voice.'

    def test_picks_off_gets_409(self, app, admin):
        c, h = admin
        sid = upload(c, h).json['entry']['id']
        assert c.post('/api/admin/settings', json={'allow_sound_choice': False}, headers=h).status_code == 200
        r = c.post('/api/public/tips', json={'amount': 100, 'name': 'Asha', 'soundboard_id': sid})
        assert r.status_code == 409 and r.json['error'] == 'Sound picks are switched off right now. Clear your sound choice and try again.'
        assert c.post('/api/public/tips', json={'amount': 100, 'name': 'Asha'}).status_code == 201

    def test_missing_file_gets_409_and_older_messages_stay_verbatim(self, app, admin):
        c, h = admin
        r = upload(c, h); (app.store.path / 'media' / r.json['name']).unlink()
        tip = lambda sid, amount=100: c.post('/api/public/tips', json={'amount': amount, 'name': 'Asha', 'soundboard_id': sid})
        r2 = tip(r.json['entry']['id'])
        assert r2.status_code == 409 and r2.json['error'] == 'That sound is unavailable right now. Pick another or clear your choice.'
        slot = app.store.soundboard_create(name='Slot', min_paise=0)['id']
        hidden = upload(c, h, 'Hidden.wav', offered=0).json['entry']['id']
        priced = upload(c, h, 'Priced.wav', min_paise=5000).json['entry']['id']
        for sid, amount, status, message in [(slot, 100, 409, 'That soundboard clip has no audio file yet.'),
                                             (hidden, 100, 409, 'That soundboard clip is disabled.'),
                                             ('abcdefghijklmnop', 100, 404, 'That soundboard clip no longer exists.'),
                                             (priced, 20, 400, 'Tip at least ₹50 to play this sound.'),
                                             ('../x', 100, 400, 'Invalid soundboard id.')]:
            r3 = tip(sid, amount)
            assert (r3.status_code, r3.json['error']) == (status, message)

    def test_public_list_is_empty_when_picks_are_off(self, app, admin):
        c, h = admin
        upload(c, h)
        assert len(c.get('/api/public/soundboard').json['items']) == 1
        c.post('/api/admin/settings', json={'allow_sound_choice': False}, headers=h)
        assert c.get('/api/public/soundboard').json == {'items': []}
        c.post('/api/admin/settings', json={'allow_sound_choice': True}, headers=h)
        assert len(c.get('/api/public/soundboard').json['items']) == 1

    def test_public_list_skips_missing_files(self, app, admin):
        c, h = admin
        a = upload(c, h, 'A.wav').json; upload(c, h, 'B.wav', emoji='🔔', min_paise=2000)
        app.store.soundboard_create(name='Empty slot', min_paise=0)
        (app.store.path / 'media' / a['name']).unlink()
        items = c.get('/api/public/soundboard').json['items']
        assert [x['name'] for x in items] == ['B']
        assert set(items[0]) == {'id', 'name', 'emoji', 'category', 'min_paise', 'duration_ms', 'url', 'volume'}
        assert (items[0]['emoji'], items[0]['min_paise'], items[0]['category']) == ('🔔', 2000, 'General')

    def test_public_config_reports_only_the_default(self, app, admin):
        c, h = admin
        upload(c, h, 'Other.wav')
        r = upload(c, h, 'Bell.wav', make_default=1)
        cfg = c.get('/api/public/config').json
        assert cfg['allow_sound_choice'] is False and cfg['sounds'] == [r.json['name']] and cfg['sound_labels'] == {r.json['name']: 'Bell'}
        set_default(c, h, 'pulse')
        cfg = c.get('/api/public/config').json
        assert cfg['sounds'] == ['pulse'] and cfg['sound_labels'] == {} and cfg['allow_sound_choice'] is False


# ---------- what each alert plays ----------
class TestAlertResolution:
    def test_no_pick_plays_the_current_default(self, app, admin):
        c, h = admin
        tid = paid_tip(app)
        set_default(c, h, 'pulse'); replay(c, h, tid)
        p = last_payload(app)
        assert (p['sound'], p['sound_source']) == ('pulse', 'default') and 'soundboard_clip' not in p
        name = upload(c, h, make_default=1).json['name']
        replay(c, h, tid)
        assert (last_payload(app)['sound'], last_payload(app)['sound_source']) == (name, 'default')

    def test_paid_pick_plays_after_it_is_hidden_and_repriced(self, app, admin):
        c, h = admin
        r = upload(c, h, 'Binod.wav'); sid, name = r.json['entry']['id'], r.json['name']
        tid = paid_tip(app, soundboard_id=sid)
        assert c.post('/api/admin/soundboard/' + sid, json={'enabled': False, 'min_paise': 900000}, headers=h).status_code == 200
        c.post('/api/admin/settings', json={'allow_sound_choice': False}, headers=h)
        replay(c, h, tid)
        p = last_payload(app)
        assert (p['soundboard_clip'], p['soundboard_id'], p['sound'], p['sound_source']) == (name, sid, 'chime', 'pick')

    def test_deleted_pick_falls_back_to_the_default(self, app, admin):
        c, h = admin
        sid = upload(c, h).json['entry']['id']
        tid = paid_tip(app, soundboard_id=sid)
        set_default(c, h, 'pulse')
        assert c.delete('/api/admin/soundboard/' + sid, headers=h).status_code == 200
        replay(c, h, tid)
        p = last_payload(app)
        assert (p['sound'], p['sound_source']) == ('pulse', 'default') and 'soundboard_clip' not in p and 'soundboard_id' not in p
        with app.store.db() as db: assert db.execute('SELECT soundboard_id FROM tips WHERE id=?', (tid,)).fetchone()[0] is None

    def test_tip_from_before_the_upgrade_replays_its_own_sound(self, tmp_path):
        app = make_app(legacy(tmp_path, settings={'sounds': ['chime', 'pulse', 'none', 'Aa1.mp3']}, files=['Aa1.mp3'],
                              tips=[dict(id='tip-rahul', sound='Aa1.mp3'), dict(id='tip-priya', sound='pulse'), dict(id='tip-gone', sound='Gone1.mp3')]))
        c, h = login(app)
        for tid, sound, source in [('tip-rahul', 'Aa1.mp3', 'tip'), ('tip-priya', 'pulse', 'tip'), ('tip-gone', 'chime', 'default')]:
            replay(c, h, tid)
            assert (last_payload(app)['sound'], last_payload(app)['sound_source']) == (sound, source), tid

    def test_tip_from_before_the_upgrade_follows_the_default_when_a_fixed_sound_existed(self, tmp_path):
        app = make_app(legacy(tmp_path, settings={'visuals': dict(DEFAULT_VISUALS, alert_sound='Xx1.mp3')}, files=['Xx1.mp3'],
                              tips=[dict(id='tip-rahul', sound='pulse')]))
        c, h = login(app)
        replay(c, h, 'tip-rahul')
        assert (last_payload(app)['sound'], last_payload(app)['sound_source']) == ('Xx1.mp3', 'default')

    def test_video_default_payload(self, app, admin):
        c, h = admin
        video_bundle(app); assert set_default(c, h, 'video').status_code == 200
        send_test_alert(c, h)
        assert (last_payload(app)['sound'], last_payload(app)['sound_source']) == ('none', 'video')
        replay(c, h, paid_tip(app))
        assert (last_payload(app)['sound'], last_payload(app)['sound_source']) == ('none', 'video')

    def test_pick_under_a_video_default_falls_back_to_chime(self, app, admin):
        c, h = admin
        r = upload(c, h); sid, name = r.json['entry']['id'], r.json['name']
        video_bundle(app); set_default(c, h, 'video')
        replay(c, h, paid_tip(app, soundboard_id=sid))
        p = last_payload(app)
        assert (p['soundboard_clip'], p['sound'], p['sound_source']) == (name, 'chime', 'pick')

    def test_test_alert_with_soundboard_id_plays_that_item(self, app, admin):
        c, h = admin
        r = upload(c, h, offered=0); sid, name = r.json['entry']['id'], r.json['name']
        assert send_test_alert(c, h, soundboard_id=sid).status_code == 200
        p = last_payload(app)
        assert (p['soundboard_clip'], p['soundboard_id'], p['sound_source'], p['test']) == (name, sid, 'pick', True)
        slot = app.store.soundboard_create(name='Slot')['id']
        for value, status, message in [('../x', 400, 'Invalid sound choice.'), (7, 400, 'Invalid sound choice.'),
                                       ('abcdefghijklmnop', 404, 'That sound was removed.'), (slot, 409, 'Upload audio for this sound first.')]:
            r2 = send_test_alert(c, h, soundboard_id=value)
            assert (r2.status_code, r2.json['error']) == (status, message)
        assert len(payloads(app)) == 1


# ---------- /api/overlay/claim ----------
class TestClaim:
    def test_claim_forces_viewer_and_sends_the_per_alert_flag(self, app, admin):
        c, h = admin
        sid = upload(c, h).json['entry']['id']
        video_bundle(app, alert_sound='pulse')  # e.g. saved by 1.5.9 after a downgrade
        assert set_default(c, h, 'video').status_code == 200
        replay(c, h, paid_tip(app, soundboard_id=sid)); send_test_alert(c, h)
        first = claim(c)
        assert first['alert']['soundboard_clip'] and first['visuals']['alert_sound'] == 'viewer' and first['visuals']['alert_video_has_audio'] is False
        ack(c, first['alert'])
        second = claim(c)
        assert (second['alert']['sound'], second['alert']['sound_source']) == ('none', 'video')
        assert second['visuals']['alert_sound'] == 'viewer' and second['visuals']['alert_video_has_audio'] is True
        assert second['visuals']['alert_image'] == 'clip.webm'
        assert app.store.settings()['visuals']['alert_sound'] == 'pulse', 'claim never rewrites settings'

    def test_claim_repairs_a_frozen_159_payload(self, app, admin, tmp_path_factory):
        c, h = admin
        set_default(c, h, 'pulse')
        queue_raw(app, frozen_159_payload('Gone1.mp3')); queue_raw(app, frozen_159_payload('chime'))
        first = claim(c)
        assert first['alert']['sound'] == 'pulse' and first['visuals']['alert_video_has_audio'] is False
        ack(c, first['alert'])
        assert claim(c)['alert']['sound'] == 'chime', "a tip made on a 1.5.9 page keeps the viewer's old choice"
        assert [p['sound'] for p in payloads(app)] == ['Gone1.mp3', 'chime'] and all('sound_source' not in p for p in payloads(app))
        # A 1.5.9 video bundle: its frozen alerts play the video's own sound.
        vis = dict(DEFAULT_VISUALS, alert_image='Vv1.webm', alert_sound='none', alert_video_has_audio=True)
        app2 = make_app(legacy(tmp_path_factory.mktemp('video'), settings={'visuals': vis}, files={'Vv1.webm': b'webm'}))
        queue_raw(app2, frozen_159_payload('chime'))
        r = claim(app2.test_client())
        assert r['alert']['sound'] == 'none' and r['visuals']['alert_video_has_audio'] is True

    def test_claim_drops_a_clip_whose_file_vanished(self, app, admin):
        c, h = admin
        r = upload(c, h); sid, name = r.json['entry']['id'], r.json['name']
        replay(c, h, paid_tip(app, soundboard_id=sid))
        (app.store.path / 'media' / name).unlink()
        a = claim(c)['alert']
        assert 'soundboard_clip' not in a and 'soundboard_id' not in a and a['sound'] == 'chime'
        assert last_payload(app)['soundboard_clip'] == name, 'the stored payload is never rewritten'

    def test_claim_follows_replaced_audio(self, app, admin):
        c, h = admin
        r = upload(c, h); sid, old = r.json['entry']['id'], r.json['name']
        replay(c, h, paid_tip(app, soundboard_id=sid))
        new = slot_upload(c, h, sid, 'Bell v2.wav').json['entry']['media_filename']
        assert not (app.store.path / 'media' / old).exists()
        a = claim(c)['alert']
        assert (a['soundboard_clip'], a['soundboard_id'], a['sound_source']) == (new, sid, 'pick')

    def test_video_source_falls_back_when_the_videos_sound_is_gone(self, app, admin):
        c, h = admin
        video_bundle(app); set_default(c, h, 'video')
        send_test_alert(c, h)
        (app.store.path / 'media' / 'clip.webm').unlink()
        first = claim(c)
        assert first['alert']['sound'] == 'chime' and first['visuals']['alert_video_has_audio'] is False
        ack(c, first['alert'])
        video_bundle(app); set_default(c, h, 'video')
        send_test_alert(c, h)
        set_default(c, h, 'pulse'); video_bundle(app, flag=False)  # a silent visual replaced the video
        second = claim(c)
        assert second['alert']['sound'] == 'pulse' and second['visuals']['alert_video_has_audio'] is False

    def test_unplayable_sound_is_replaced(self, app, admin):
        c, h = admin
        name = upload(c, h, make_default=1).json['name']
        send_test_alert(c, h)
        assert last_payload(app)['sound'] == name
        set_default(c, h, 'pulse')
        (app.store.path / 'media' / name).unlink()
        assert claim(c)['alert']['sound'] == 'pulse'


# ---------- files: unlinked after commit, only when unused ----------
class TestLibraryFiles:
    def test_row_delete_unlinks_an_unshared_file_after_commit(self, app, admin, monkeypatch):
        c, h = admin
        r = upload(c, h); sid, name = r.json['entry']['id'], r.json['name']
        seen, real = [], app.store._unlink_if_unused
        def spy(f):
            seen.append(app.store.soundboard_get(sid))  # a new connection sees only committed data
            return real(f)
        monkeypatch.setattr(app.store, '_unlink_if_unused', spy)
        assert c.delete('/api/admin/soundboard/' + sid, headers=h).json == {'ok': True, 'default_reset': False}
        assert seen == [None] and not (app.store.path / 'media' / name).exists()
        assert name not in app.store.settings()['media_labels']

    def test_shared_file_survives_a_row_delete(self, app, admin):
        c, h = admin
        r = upload(c, h); sid, name = r.json['entry']['id'], r.json['name']
        twin = app.store.soundboard_create(name='Twin', min_paise=0)['id']; app.store.soundboard_set_media(twin, name, 500)
        c.delete('/api/admin/soundboard/' + sid, headers=h)
        assert (app.store.path / 'media' / name).exists() and name in app.store.settings()['media_labels']
        assert [x['id'] for x in c.get('/api/public/soundboard').json['items']] == [twin]
        c.delete('/api/admin/soundboard/' + twin, headers=h)
        assert not (app.store.path / 'media' / name).exists()

    def test_file_used_by_visuals_is_never_unlinked(self, app):
        media = app.store.path / 'media'; media.mkdir(exist_ok=True)
        (media / 'Held1.mp3').write_bytes(wav()); (media / 'art.webm').write_bytes(b'webm')
        put_settings(app, visuals=dict(DEFAULT_VISUALS, alert_sound='Held1.mp3', alert_image='art.webm'))  # e.g. saved by 1.5.9 after a downgrade
        assert app.store._unlink_if_unused('Held1.mp3') is False and app.store._unlink_if_unused('art.webm') is False
        put_settings(app, visuals=dict(DEFAULT_VISUALS))
        assert app.store._unlink_if_unused('art.webm') is False, 'only stored sounds are ever unlinked'
        assert (media / 'art.webm').exists() and (media / 'Held1.mp3').exists()
        assert app.store._unlink_if_unused('Held1.mp3') is True and not (media / 'Held1.mp3').exists()

    def test_sounds_delete_removes_every_owning_row(self, app, admin):
        c, h = admin
        r = upload(c, h, make_default=1); name = r.json['name']
        twin = app.store.soundboard_create(name='Twin')['id']; app.store.soundboard_set_media(twin, name, 500)
        d = c.delete('/api/admin/sounds/' + name, headers=h)
        assert d.json == {'ok': True, 'name': name, 'default_reset': True}
        assert app.store.soundboard_list() == [] and not (app.store.path / 'media' / name).exists()
        s = app.store.settings()
        assert s['default_sound'] == 'chime' and name not in s['sounds'] and name not in s['media_labels']

    def test_failed_slot_upload_leaves_no_file(self, app, admin, monkeypatch):
        c, h = admin
        sid = app.store.soundboard_create(name='Slot')['id']
        monkeypatch.setattr(app.store, '_set_sound_media', boom)
        with pytest.raises(RuntimeError): slot_upload(c, h, sid)
        assert list((app.store.path / 'media').iterdir()) == [] and app.store.soundboard_get(sid)['media_filename'] is None

    def test_failed_library_insert_leaves_no_file(self, app, admin, monkeypatch):
        c, h = admin
        monkeypatch.setattr(app.store, 'remember_upload', boom)
        with pytest.raises(RuntimeError): upload(c, h)
        assert list((app.store.path / 'media').iterdir()) == [] and app.store.soundboard_list() == []
        assert app.store.settings()['default_sound'] == 'chime'


# ---------- POST /api/admin/media and the alert bundle ----------
class TestLibraryUpload:
    def test_upload_creates_a_pickable_item_named_after_the_file(self, app, admin):
        c, h = admin
        r = upload(c, h, 'Airhorn (remix).mp3', wav(1.0))  # WAV bytes: the content decides, not the filename
        assert r.status_code == 200, r.json
        name, e = r.json['name'], r.json['entry']
        assert name.endswith('.wav') and r.json['original_name'] == 'Airhorn (remix).mp3' and r.json['auto_fixed'] is False
        assert (e['name'], e['enabled'], e['min_paise'], e['category'], e['emoji'], e['media_filename'], e['url']) == \
            ('Airhorn (remix)', 1, 0, 'General', '', name, '/media/' + name)
        assert 900 <= e['duration_ms'] <= 1100
        assert [x['id'] for x in c.get('/api/public/soundboard').json['items']] == [e['id']]
        s = app.store.settings()
        assert s['sounds'] == DEFAULTS['sounds'] and s['default_sound'] == 'chime' and s['media_labels'][name] == 'Airhorn (remix).mp3'

    def test_upload_fields_and_make_default(self, app, admin):
        c, h = admin
        r = upload(c, h, 'x.wav', name='Binod', emoji='🤣', category='Hindi Memes', min_paise=5000, make_default=1)
        assert r.status_code == 200, r.json
        e = r.json['entry']
        assert (e['name'], e['emoji'], e['category'], e['min_paise'], e['enabled']) == ('Binod', '🤣', 'Hindi Memes', 5000, 1)
        s = app.store.settings()
        assert s['default_sound'] == e['id'] and s['sounds'][0] == r.json['name']
        assert audits(app, 'default_sound_changed')[-1]['detail']['source'] == 'upload'
        upload(c, h, 'y.wav', make_default=0)
        assert app.store.settings()['default_sound'] == e['id']

    def test_offered_0_hides_the_item(self, app, admin):
        c, h = admin
        r = upload(c, h, 'Secret.wav', offered=0); e = r.json['entry']
        assert e['enabled'] == 0 and c.get('/api/public/soundboard').json['items'] == []
        item = next(x for x in c.get('/api/admin/sounds/list', headers=h).json['items'] if x['name'] == r.json['name'])
        assert (item['id'], item['offered'], item['listed']) == (e['id'], False, False)
        assert set_default(c, h, e['id']).status_code == 200, 'a hidden sound can still be the default'

    def test_bad_min_paise_is_refused_before_anything_is_written(self, app, admin, monkeypatch):
        c, h = admin
        monkeypatch.setattr(app_module, 'validate_or_fix_audio', lambda *a, **k: pytest.fail('audio was processed before the form was checked'))
        for bad in ['abc', '-1', '10000001', '12.5']:
            r = upload(c, h, 'x.wav', min_paise=bad)
            assert r.status_code == 400 and r.json['error'] == 'Minimum tip must be between ₹0 and ₹100000.', bad
        assert list((app.store.path / 'media').iterdir()) == [] and app.store.soundboard_list() == []

    def test_30_seconds_accepted_and_36_refused(self, app, admin):
        c, h = admin
        r = upload(c, h, 'long.wav', wav(30.0))
        assert r.status_code == 200 and r.json['entry']['duration_ms'] == 30000
        before = set((app.store.path / 'media').iterdir())
        r2 = upload(c, h, 'longer.wav', wav(36.0))
        assert r2.status_code == 400 and r2.json['error'] == 'WAV must be PCM, 30 seconds or less.'
        assert set((app.store.path / 'media').iterdir()) == before and len(app.store.soundboard_list()) == 1
        sid = app.store.soundboard_create(name='Slot', enabled=False)['id']
        assert slot_upload(c, h, sid, data=wav(36.0)).status_code == 400
        assert slot_upload(c, h, sid, data=wav(30.0)).status_code == 200

    def test_bundle_sound_becomes_a_hidden_default(self, app, admin):
        c, h = admin
        r = c.post('/api/admin/alert-bundle', data={'visual': (io.BytesIO(png()), 'art.png'), 'audio': (io.BytesIO(wav()), 'Bell.wav')},
                   headers=h, content_type='multipart/form-data')
        assert r.status_code == 200, r.json
        e = r.json['entry']
        assert (e['name'], e['enabled'], e['min_paise'], e['media_filename'], e['url']) == ('Bell', 0, 0, r.json['audio'], '/media/' + r.json['audio'])
        assert r.json['default'] == e['id'] and r.json['default_reset'] is False
        s = app.store.settings()
        assert s['default_sound'] == e['id'] and s['sounds'][0] == r.json['audio']
        assert (s['visuals']['alert_image'], s['visuals']['alert_sound'], s['visuals']['alert_video_has_audio']) == (r.json['visual'], 'viewer', False)
        assert c.get('/api/public/soundboard').json['items'] == []
        assert audits(app, 'default_sound_changed')[-1]['detail']['source'] == 'bundle'

    def test_silent_visual_resets_a_video_default(self, app, admin):
        c, h = admin
        video_bundle(app); assert set_default(c, h, 'video').status_code == 200
        r = c.post('/api/admin/alert-bundle', data={'visual': (io.BytesIO(png()), 'art.png')}, headers=h, content_type='multipart/form-data')
        assert r.status_code == 200, r.json
        assert (r.json['default_reset'], r.json['default'], r.json['entry']) == (True, 'chime', None)
        s = app.store.settings()
        assert s['default_sound'] == 'chime' and s['sounds'][0] == 'chime' and s['visuals']['alert_video_has_audio'] is False
        assert audits(app, 'default_sound_changed')[-1]['detail'] == {'from': 'video', 'to': 'chime', 'source': 'bundle'}


# ---------- pages, dashboards and overlays left open across the upgrade ----------
class TestLegacyClients:
    def test_159_tip_payload_with_sound_and_soundboard_id_works(self, app, admin):
        c, h = admin
        r = upload(c, h, 'Binod.wav', min_paise=5000); sid, name = r.json['entry']['id'], r.json['name']
        body = {'amount': 100, 'name': 'Rahul', 'email': '', 'message': 'GG', 'tts': True, 'voice': 'en-IN', 'sound': 'pulse',
                'soundboard_id': sid, 'remember': False}
        t = c.post('/api/public/tips', json=body)
        assert t.status_code == 201, t.json
        with app.store.db(True) as db:
            row = db.execute('SELECT sound,soundboard_id FROM tips WHERE id=?', (t.json['id'],)).fetchone()
            db.execute("UPDATE tips SET status='VERIFIED',verified=? WHERE id=?", (now(), t.json['id']))
        assert (row['sound'], row['soundboard_id']) == ('chime', sid)
        replay(c, h, t.json['id'])
        assert (last_payload(app)['soundboard_clip'], last_payload(app)['sound_source']) == (name, 'pick')
        assert c.post('/api/public/tips', json=body | {'sound': 'gone.mp3', 'soundboard_id': None}).status_code == 201
        r2 = c.post('/api/public/tips', json=body | {'amount': 20})
        assert r2.status_code == 400 and r2.json['error'] == 'Tip at least ₹50 to play this sound.'

    def test_159_save_sound_choices_gets_409(self, app, admin):
        c, h = admin
        before = app.store.settings()
        r = c.post('/api/admin/settings', json={'allow_sound_choice': False, 'sounds': ['pulse', 'chime']}, headers=h)
        assert r.status_code == 409 and r.json['error'] == 'Sound choices moved to the Sound library in 1.6.0. Reload the dashboard.'
        after = app.store.settings()
        assert after['sounds'] == before['sounds'] and after['allow_sound_choice'] is True

    def test_159_design_studio_file_save_sets_the_default(self, app, admin):
        c, h = admin
        r = upload(c, h, 'Bell.wav'); sid, name = r.json['entry']['id'], r.json['name']
        v = c.post('/api/admin/visuals', json=studio_body(alert_sound=name), headers=h)
        assert v.status_code == 200 and v.json == {'ok': True, 'default_changed': True, 'default_reset': False}
        s = app.store.settings()
        assert s['default_sound'] == sid and s['visuals']['alert_sound'] == 'viewer'
        assert audits(app, 'default_sound_changed')[-1]['detail']['source'] == 'design_studio'
        assert c.post('/api/admin/visuals', json=studio_body(alert_sound='pulse'), headers=h).status_code == 200
        assert app.store.settings()['default_sound'] == 'pulse'
        (app.store.path / 'media' / 'Stray1.mp3').write_bytes(wav())
        r2 = c.post('/api/admin/visuals', json=studio_body(alert_sound='Stray1.mp3'), headers=h)
        assert r2.status_code == 400 and r2.json['error'] == 'Choose a sound from the Sound library.'
        assert app.store.settings()['default_sound'] == 'pulse'

    def test_viewer_save_changes_nothing(self, app, admin):
        c, h = admin
        set_default(c, h, 'pulse')
        changes = len(audits(app, 'default_sound_changed'))
        v = c.post('/api/admin/visuals', json=studio_body(alert_sound='viewer', accent='#123456'), headers=h)
        assert v.json == {'ok': True, 'default_changed': False, 'default_reset': False}
        s = app.store.settings()
        assert s['default_sound'] == 'pulse' and s['sounds'][0] == 'pulse' and s['visuals']['accent'] == '#123456'
        assert len(audits(app, 'default_sound_changed')) == changes

    def test_visuals_save_keeps_unsent_keys_and_the_video_flag(self, app, admin):
        c, h = admin
        video_bundle(app, accent='#112233'); set_default(c, h, 'video')
        v = c.post('/api/admin/visuals', json={'radius': 30}, headers=h)
        assert v.json == {'ok': True, 'default_changed': False, 'default_reset': False}
        vis = app.store.settings()['visuals']
        assert (vis['radius'], vis['accent'], vis['alert_image'], vis['alert_video_has_audio']) == (30, '#112233', 'clip.webm', True)
        c.post('/api/admin/visuals', json={'alert_video_has_audio': False}, headers=h)
        assert app.store.settings()['visuals']['alert_video_has_audio'] is True, 'only the alert bundle sets the flag'
        (app.store.path / 'media' / 'art.png').write_bytes(png())
        v = c.post('/api/admin/visuals', json={'alert_image': 'art.png'}, headers=h)
        assert v.json == {'ok': True, 'default_changed': False, 'default_reset': True}
        s = app.store.settings()
        assert s['visuals']['alert_video_has_audio'] is False and s['default_sound'] == 'chime' and s['visuals']['accent'] == '#112233'

    def test_sounds_list_includes_library_files_with_ids(self, app, admin):
        c, h = admin
        a = upload(c, h, 'A.wav', make_default=1).json; b = upload(c, h, 'B.wav', offered=0).json
        slot = app.store.soundboard_create(name='Slot', enabled=False)['id']
        slot_file = slot_upload(c, h, slot).json['entry']['media_filename']
        put_settings(app, sounds=app.store.settings()['sounds'] + ['my sound'])
        d = c.get('/api/admin/sounds/list', headers=h).json
        items = {x['name']: x for x in d['items']}
        assert [x['name'] for x in d['items']] == [a['name'], b['name'], slot_file, 'my sound']
        pick = lambda n: (items[n]['id'], items[n]['offered'], items[n]['default'], items[n]['listed'])
        assert pick(a['name']) == (a['entry']['id'], True, True, True) and items[a['name']]['display_name'] == 'A.wav'
        assert pick(b['name']) == (b['entry']['id'], False, False, False)
        assert pick(slot_file) == (slot, True, False, True)
        assert pick('my sound') == (None, None, False, True) and items['my sound']['missing'] is True


# ---------- the bundled starter sounds ----------
STARTER_PRICES = {'Vine Boom': 2000, 'Air Horn': 2000, 'Cash Register': 2000, 'Victory Fanfare': 5000, 'Clap': 2000, 'Game Over': 5000,
                  'Ba Dum Tss': 2000, 'Sad Trombone': 2000}


def seed(c, h):
    r = c.post('/api/admin/soundboard/seed', json={}, headers=h)
    assert r.status_code == 200, r.json
    return r.json


def bundled(name): return (STARTER_DIR / STARTER_AUDIO[name]).read_bytes()


def by_name(app): return {e['name']: e for e in app.store.soundboard_list()}


class TestStarterSounds:
    def test_bundled_files_pass_the_upload_validator_unchanged(self, monkeypatch):
        readme = (STARTER_DIR / 'README.txt').read_text(encoding='ascii')
        assert 'CC0' in readme and 'creativecommons.org/publicdomain/zero/1.0' in readme and 'scripts/starter_sounds' in readme
        assert sorted(p.name for p in STARTER_DIR.glob('*.mp3')) == sorted(STARTER_AUDIO.values())
        generators = STARTER_DIR.parents[1] / 'scripts' / 'starter_sounds'
        assert all((generators / f.replace('.mp3', '.py')).is_file() for f in STARTER_AUDIO.values())
        for ffmpeg in (True, False):  # without FFmpeg (often the case on the streaming PC) the MP3 header gives the length
            if not ffmpeg: monkeypatch.setattr(video, 'tool', lambda name: None)
            for name in STARTER_AUDIO:
                data = bundled(name)
                assert 0 < len(data) <= 8 * 1024 * 1024
                content, ext, duration_ms, auto_fixed = validate_or_fix_audio(data, max_duration_ms=SOUND_MAX_MS)
                assert (content == data, ext, auto_fixed) == (True, 'mp3', False) and 500 <= duration_ms <= SOUND_MAX_MS, (name, ffmpeg)

    def test_seeding_a_fresh_install_fills_the_eight_and_leaves_the_meme_slots_empty(self, app, admin):
        c, h = admin
        media = app.store.path / 'media'
        make_app(app.store.path)  # a second start
        assert app.store.soundboard_list() == [] and not (media.exists() and any(media.iterdir())), 'nothing is added on its own'
        before = app.store.settings()
        r = seed(c, h)
        rows = app.store.soundboard_list(); names = by_name(app)
        assert r['ok'] is True and len(rows) == 22 and r['created'] == [e['name'] for e in rows] and r['ready'] == list(STARTER_AUDIO)
        assert (names['Ba Dum Tss']['display_order'], names['Sad Trombone']['display_order']) == (300, 310)
        labels = app.store.settings()['media_labels']
        for name, file in STARTER_AUDIO.items():
            e = names[name]; stored = e['media_filename']
            assert (e['enabled'], e['min_paise']) == (1, STARTER_PRICES[name]) and e['duration_ms'] > 0, name
            assert re.fullmatch(STORED_SOUND, stored) and stored.endswith('.mp3') and stored != file, stored
            assert (media / stored).read_bytes() == bundled(name) and labels[stored] == name + '.mp3'
        slots = [e for e in rows if e['name'] not in STARTER_AUDIO]
        assert len(slots) == 14 and all(e['media_filename'] is None and e['enabled'] == 0 for e in slots)
        assert sorted(p.name for p in media.iterdir()) == sorted(names[n]['media_filename'] for n in STARTER_AUDIO)
        after = app.store.settings()
        assert [after[k] for k in ('default_sound', 'sounds', 'allow_sound_choice')] == [before[k] for k in ('default_sound', 'sounds', 'allow_sound_choice')]
        assert [a['object_id'] for a in audits(app, 'starter_sound_added')] == [names[n]['id'] for n in STARTER_AUDIO]

    def test_viewers_can_pick_them_and_a_pick_plays_its_clip(self, app, admin):
        c, h = admin
        seed(c, h); names = by_name(app)
        items = c.get('/api/public/soundboard').json['items']
        assert [x['name'] for x in items] == list(STARTER_AUDIO)
        assert all(x['url'] == '/media/' + names[x['name']]['media_filename'] and x['min_paise'] == STARTER_PRICES[x['name']] for x in items)
        vine = names['Vine Boom']
        assert c.post('/api/admin/sessions', json={'action': 'start'}, headers=h).status_code == 200
        r = c.post('/api/public/tips', json={'amount': 20, 'name': 'Rahul', 'message': 'GG', 'soundboard_id': vine['id']})
        assert r.status_code == 201, r.json
        assert c.post('/api/admin/simulate/' + r.json['id'], headers=h).json['outcome'] == 'verified'
        p = last_payload(app)
        assert (p['soundboard_clip'], p['soundboard_id'], p['sound_source'], p['sound']) == (vine['media_filename'], vine['id'], 'pick', 'chime')
        assert claim(c)['alert']['soundboard_clip'] == vine['media_filename']
        m = c.get('/media/' + vine['media_filename'])
        assert m.status_code == 200 and m.mimetype == 'audio/mpeg' and m.data == bundled('Vine Boom')
        m.close()
        r = c.post('/api/public/tips', json={'amount': 20, 'name': 'Priya', 'soundboard_id': names['Victory Fanfare']['id']})
        assert r.status_code == 400 and r.json['error'] == 'Tip at least ₹50 to play this sound.'

    def test_seeding_again_adds_nothing(self, app, admin):
        c, h = admin
        seed(c, h)
        files, rows, added = media_listing(app.store.path), app.store.soundboard_list(), len(audits(app, 'starter_sound_added'))
        assert seed(c, h) == {'ok': True, 'created': [], 'ready': []}
        assert media_listing(app.store.path) == files and app.store.soundboard_list() == rows and len(audits(app, 'starter_sound_added')) == added

    def test_an_existing_159_board_keeps_the_owners_clip(self, tmp_path):
        ref = Store(tmp_path / 'ref', 's' * 48); ref.soundboard_seed()
        old = [e for e in ref.soundboard_list() if e['name'] not in ('Ba Dum Tss', 'Sad Trombone')]  # the 1.5.9 catalog
        assert len(old) == 20
        rows = [{k: e[k] for k in ('name', 'emoji', 'category', 'min_paise', 'display_order')} | {'enabled': 0} for e in old]
        next(r for r in rows if r['name'] == 'Air Horn').update(media_filename='OwnHorn_1.wav', duration_ms=200)  # uploaded, then hidden
        path = legacy(tmp_path / 'data', settings={'allow_sound_choice': False}, rows=rows, files={'OwnHorn_1.wav': wav(0.2)})
        app = make_app(path); c, h = login(app)
        r = seed(c, h)
        assert r['created'] == ['Ba Dum Tss', 'Sad Trombone'] and r['ready'] == [n for n in STARTER_AUDIO if n != 'Air Horn']
        names = by_name(app)
        assert (names['Air Horn']['media_filename'], names['Air Horn']['enabled']) == ('OwnHorn_1.wav', 0)
        assert (path / 'media' / 'OwnHorn_1.wav').read_bytes() == wav(0.2)
        assert all(names[n]['enabled'] == 1 and (path / 'media' / names[n]['media_filename']).read_bytes() == bundled(n) for n in r['ready'])
        assert all(e['media_filename'] is None and e['enabled'] == 0 for e in names.values() if e['name'] not in STARTER_AUDIO)
        s = app.store.settings()
        assert (s['allow_sound_choice'], s['default_sound']) == (False, 'chime'), "the picks switch and the default are the owner's"
        assert c.get('/api/public/soundboard').json['items'] == []

    def test_a_missing_bundled_file_skips_only_that_sound(self, app, admin, monkeypatch, tmp_path_factory, caplog):
        partial = tmp_path_factory.mktemp('starter')
        for f in STARTER_AUDIO.values():
            if f != 'clap.mp3': shutil.copyfile(STARTER_DIR / f, partial / f)
        monkeypatch.setattr(domain, 'STARTER_DIR', partial)
        c, h = admin
        with caplog.at_level(logging.WARNING, logger='acepressure.sounds'):
            r = seed(c, h)
        assert len(r['created']) == 22 and r['ready'] == [n for n in STARTER_AUDIO if n != 'Clap']
        clap = by_name(app)['Clap']
        assert (clap['media_filename'], clap['enabled']) == (None, 0) and len(list((app.store.path / 'media').iterdir())) == 7
        assert 'Starter sound Clap was skipped' in caplog.text
        monkeypatch.undo()
        assert seed(c, h)['ready'] == ['Clap'], 'the next click fills it once the file is back'

    def test_a_failing_write_drops_its_copy_and_the_rest_still_arrive(self, app, admin, monkeypatch, caplog):
        real = Store.remember_upload
        def flaky(self, db, name, original_name, auto_fixed):
            if original_name == 'Game Over.mp3': raise sqlite3.OperationalError('database is locked')
            return real(self, db, name, original_name, auto_fixed)
        monkeypatch.setattr(Store, 'remember_upload', flaky)
        c, h = admin
        with caplog.at_level(logging.WARNING, logger='acepressure.sounds'):
            r = seed(c, h)
        assert r['ready'] == [n for n in STARTER_AUDIO if n != 'Game Over'] and 'database is locked' in caplog.text
        names = by_name(app)
        assert (names['Game Over']['media_filename'], names['Game Over']['enabled'], names['Game Over']['duration_ms']) == (None, 0, 0), 'rolled back'
        assert sorted(p.name for p in (app.store.path / 'media').iterdir()) == sorted(names[n]['media_filename'] for n in r['ready'])

    def test_deleting_a_starter_row_removes_only_its_copy(self, app, admin):
        c, h = admin
        originals = {f: hashlib.sha256((STARTER_DIR / f).read_bytes()).hexdigest() for f in STARTER_AUDIO.values()}
        seed(c, h); vine = by_name(app)['Vine Boom']; media = app.store.path / 'media'
        others = media_listing(app.store.path); others.pop(vine['media_filename'])
        r = c.delete('/api/admin/soundboard/' + vine['id'], headers=h)
        assert r.status_code == 200 and r.json == {'ok': True, 'default_reset': False}
        assert not (media / vine['media_filename']).exists() and media_listing(app.store.path) == others
        assert vine['media_filename'] not in app.store.settings()['media_labels']
        assert {f: hashlib.sha256((STARTER_DIR / f).read_bytes()).hexdigest() for f in STARTER_AUDIO.values()} == originals
        r = seed(c, h)  # the slot comes back with a fresh copy
        again = by_name(app)['Vine Boom']
        assert r['created'] == r['ready'] == ['Vine Boom'] and again['media_filename'] != vine['media_filename']
        assert (media / again['media_filename']).read_bytes() == bundled('Vine Boom') and again['display_order'] == vine['display_order']

    def test_sounds_list_and_the_library_show_their_names(self, app, admin):
        c, h = admin
        seed(c, h); names = by_name(app)
        items = {x['name']: x for x in c.get('/api/admin/sounds/list', headers=h).json['items']}
        assert list(items) == [names[n]['media_filename'] for n in STARTER_AUDIO]
        for n in STARTER_AUDIO:
            x = items[names[n]['media_filename']]
            assert (x['display_name'], x['id'], x['offered'], x['listed'], x['default'], x['missing'], x['auto_fixed']) == \
                (n + '.mp3', names[n]['id'], True, True, False, False, False)
        lib = {e['name']: e for e in c.get('/api/admin/soundboard', headers=h).json['items']}
        assert all(lib[n]['original_name'] == n + '.mp3' and not lib[n]['is_default'] and not lib[n]['missing'] for n in STARTER_AUDIO)

    def test_rows_sharing_a_name_get_one_copy_and_any_owner_clip_wins(self, app, admin):
        c, h = admin
        media = app.store.path / 'media'; media.mkdir(exist_ok=True); (media / 'Own_1.wav').write_bytes(wav(0.2))
        claps = [app.store.soundboard_create(name='Clap', min_paise=0, display_order=o, enabled=False)['id'] for o in (5, 6)]
        horns = [app.store.soundboard_create(name='Air Horn', min_paise=0, display_order=o, enabled=False)['id'] for o in (7, 8)]
        app.store.soundboard_set_media(horns[1], 'Own_1.wav', 200)  # the owner's clip on the second Air Horn
        r = seed(c, h)
        assert not {'Clap', 'Air Horn'} & set(r['created']) and 'Clap' in r['ready'] and 'Air Horn' not in r['ready']
        a, b = (app.store.soundboard_get(i) for i in claps)
        assert a['media_filename'] and a['enabled'] == 1 and (b['media_filename'], b['enabled']) == (None, 0)
        assert [app.store.soundboard_get(i)['media_filename'] for i in horns] == [None, 'Own_1.wav']
        assert seed(c, h)['ready'] == [], 'one Clap has audio now, so the other is left for the owner'

    def test_a_slot_filled_meanwhile_keeps_the_owners_clip(self, app, admin, monkeypatch):
        """An upload (or a second click) can fill a slot between the first check and the write: the copy goes, the clip stays."""
        c, h = admin
        app.store.soundboard_seed(); vine = by_name(app)['Vine Boom']; media = app.store.path / 'media'; media.mkdir(exist_ok=True)
        real = video.validate_or_fix_audio
        def upload_meanwhile(content, **kw):
            if content == bundled('Vine Boom'):
                (media / 'Own_1.wav').write_bytes(wav(0.2)); app.store.soundboard_set_media(vine['id'], 'Own_1.wav', 200)
            return real(content, **kw)
        monkeypatch.setattr(video, 'validate_or_fix_audio', upload_meanwhile)
        r = seed(c, h)
        assert r['created'] == [] and r['ready'] == [n for n in STARTER_AUDIO if n != 'Vine Boom']
        assert app.store.soundboard_get(vine['id'])['media_filename'] == 'Own_1.wav'
        assert sorted(p.name for p in media.iterdir()) == sorted(['Own_1.wav'] + [by_name(app)[n]['media_filename'] for n in r['ready']])


class TestSoundLibraryAdminUI:
    """Static checks on the admin pages: spec 12, frontend checks 1, 2 and 5, plus the starter-sounds copy (addendum C)."""
    STATIC = Path(app_module.__file__).resolve().parent / 'static'

    def read(self, name): return (self.STATIC / name).read_text(encoding='utf-8')

    def test_one_sound_library_tab_and_nav_groups(self):
        admin_js, css = self.read('admin.js'), self.read('premium.css')
        tabs = re.findall(r"'([^']+)'", re.search(r'const sections=\[([^\]]*)\]', admin_js).group(1))
        assert 'Sound library' in tabs and 'Sounds/media' not in tabs and 'Soundboard' not in tabs and len(tabs) == 15
        assert "if(tab==='Sound library')return library(root);" in admin_js
        assert 'function media(' not in admin_js and 'function soundboard(' not in admin_js and 'Sounds/media' not in admin_js
        # The nav groups (money · alerts & media · insights · setup) start at Alertbox, Stream sessions and OBS.
        assert [tabs.index(t) + 1 for t in ('Alertbox', 'Stream sessions', 'OBS')] == [7, 11, 13]
        assert 'nav button:is(:nth-child(7), :nth-child(11), :nth-child(13))' in css

    def test_upload_limits_bundle_and_badges(self):
        admin_js, css = self.read('admin.js'), self.read('premium.css')
        for literal in ("tooBig(fd.get('file'),8,'That sound')", "tooBig(fd.get('file'),8,'That image')", "tooBig(upload.files[0],8,'That clip')",
                        "tooBig(vis,/\\.(mp4|webm)$/i.test(vis?.name||'')?24:8,'The visual');tooBig(bd.get('audio'),8,'The sound');",
                        'Upload alert bundle · visual + sound', '/api/admin/alert-bundle', 'display_name', 'badge-fixed', 'badge-default',
                        "fd.set('offered',offered.checked?'1':'0')", "fd.set('make_default',makeDefault.checked?'1':'0')"):
            assert literal in admin_js, literal
        for rule in ('.badge.badge-fixed', '.badge.badge-default', '.library-table', '.library-slots summary'):
            assert rule in css, rule
        assert '.sb-table' not in css

    def test_design_studio_points_to_the_sound_library(self):
        designer_js = self.read('designer.js')
        assert 'Separate alert audio' not in designer_js and 'Sounds/media' not in designer_js
        assert 'Open Sound library' in designer_js and "tab='Sound library';draw();" in designer_js and 'r.default_reset?' in designer_js

    def test_library_copy_avatar_and_editor(self):
        admin_js = self.read('admin.js')
        for literal in ("button('Add starter sounds'", 'plus 14 Indian meme slots for your own clips.', 'Starter sounds already added.',
                        'Starter slots waiting for audio (', "A('soundboard/default',{value:", "A('alerts',{action:'test',soundboard_id:e.id})",
                        ' Your default sound went back to Chime.', "panel('Creator avatar')", "modal('Edit sound'", '(e.min_paise??0)/100'):
            assert literal in admin_js, literal
        assert '||5000' not in admin_js and 'Add soundboard entry' not in admin_js, 'the editor is edit-only and keeps ₹0 sounds at ₹0'


# ---------- the overlay and the tip page (static checks) ----------
class TestSoundLibraryFrontends:
    """Spec 12, checks 3 and 4: the overlay plays the viewer's pick first, gives a file 31 s and gates the alert video's own
    sound; the tip page has one Alert sound picker that starts on “Streamer’s default” and never sends `sound`."""
    @staticmethod
    def read(rel): return (Path(__file__).resolve().parents[1] / 'acepressure' / rel).read_text(encoding='utf-8')

    def test_overlay_plays_the_pick_first_and_gives_a_file_31_seconds(self):
        js = self.read('static/overlay.js')
        assert '31000' in js and '21000' not in js
        start = js.index('function resolveAlertSound('); resolve = js[start:js.index('\n}', start)]
        assert resolve.index('p.soundboard_clip') < resolve.index('visuals.alert_sound') < resolve.index('p.sound)')
        assert "(p&&p.sound)||'none'" in resolve
        sound = next(line for line in js.splitlines() if line.startswith('async function sound('))
        assert 'return true' in sound and 'return false' in sound, 'sound() reports whether it played'
        assert "return playAudio('/media/'+encodeURIComponent(name),31000,false,volume)" in sound

    def test_overlay_video_gate_and_fallbacks(self):
        js = self.read('static/overlay.js')
        assert '!videoEl.paused' in js and 'useVideoAudio=!videoEl.muted;' not in js, 'the 1.5.9 gate was always true'
        assert 'const wantVideo=!!(videoEl&&visuals.alert_video_has_audio&&audioOn&&!p.soundboard_clip);' in js, 'never under a pick'
        assert "const first=wantVideo?'chime':resolveAlertSound(visuals,p);await sound(first,vol(first))" in js, 'a blocked unmute plays Chime'
        assert 'if(!ok&&p.soundboard_clip&&p.sound!==p.soundboard_clip)return sound(p.sound,vol(p.sound));' in js, 'a pick that fails plays the default'

    def test_tip_page_has_one_alert_sound_picker(self, client):
        html = self.read('templates/public.html')
        for gone in ('sound-choices', 'id="sound-label"', 'name="sound"', 'preview-sound', 'Clear sound selection'):
            assert gone not in html, gone
        assert 'id="soundboard-section"' in html and 'id="voice-choices"' in html
        assert 'Alert sound <span class="pill-tag">PLAYS ON STREAM</span>' in html
        assert 'Pick a sound to play on stream when your tip lands, or keep the streamer’s default. Some sounds unlock at higher amounts.' in html
        assert 'placeholder="Search sounds…" aria-label="Search sounds"' in html
        assert 'role="radiogroup" aria-label="Alert sound"></div><p id="soundboard-note" class="field-hint" role="status" aria-live="polite"></p>' in html
        assert '>Use the streamer’s default</button>' in html
        page = client.get('/').get_data(as_text=True)
        assert 'id="soundboard-note"' in page and 'sound-choices' not in page

    def test_tip_page_never_sends_a_sound_and_starts_on_the_streamers_default(self):
        js = self.read('static/public.js')
        for gone in ("sound:fd.get('sound')", 'buildSounds', "$('#sound')", '#sound-label', '#preview-sound', 'tile.disabled'):
            assert gone not in js, gone
        assert 'Streamer’s default' in js and 'aria-disabled' in js and "'soundboard-tile default-tile'" in js
        for fn in ('defaultTile', 'keepPickAffordable', 'sbNote', 'playPreview'):
            assert f'function {fn}(' in js, fn
        assert ' to pick “' in js and 'so your pick was cleared. The streamer’s default will play.' in js
        assert 'if(sbId)await buildSoundboard();' in js and 'try{localStorage.setItem(SOUNDBOARD_FAV_KEY' in js
        amount = "$('#amount').addEventListener('input',()=>{renderSoundboardGrid();updateTierMeter();});"
        assert js.count(amount) == 1 and js.index('if(!soundboardWired){soundboardWired=true;') < js.index(amount), 'wired once, so a rebuild adds no listener'

    def test_tip_page_styles_the_default_tile_and_locked_tiles(self):
        css = self.read('static/premium.css')
        assert '#soundboard-note:empty { margin: 0; }' in css
        assert css.index('.soundboard-tile.default-tile { border-color: var(--accent); }') < css.index('.soundboard-tile.selected {'), 'selected wins'
        assert '.soundboard-tile:hover:not(.locked)' in css and '.tip-focused .soundboard-tile:active:not(.locked)' in css
        assert 'soundboard-tile:hover:not(:disabled)' not in css and 'soundboard-tile:active:not(:disabled)' not in css
