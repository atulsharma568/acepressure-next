"""1.6.0 release-candidate review fixes: the named pre-1.6.0 backup is written whole or not at all, the overlay's alert
sound can't hang the queue or cut a pick short, Skip TTS cancels a readout that hasn't started yet, Voice Studio explains
voice_missing from an OBS source still on the old overlay page, Fix_Audio.bat names the Sound library, and the browser
smoke test waits for the paid state instead of a fixed 12 s."""
import json
import logging
import re
import sqlite3
from pathlib import Path

import pytest

from acepressure.domain import Store

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'acepressure' / 'static'
BACKUP = 'before-1.6.0-sound-library.sqlite3'
WARNING = f'Could not write {BACKUP}; migrating without it.'


# ---------- helpers ----------
def legacy_159(path):
    """A 1.5.9 data folder that offered one upload, so the first 1.6.0 start backs it up and then migrates it."""
    store = Store(path, 's' * 48)
    with store.db(True) as db:
        db.execute("DELETE FROM settings WHERE key IN ('default_sound','sound_library_migrated')")  # 1.5.9 had neither key
        db.execute("UPDATE settings SET value=? WHERE key='sounds'", (json.dumps(['chime', 'Aa1.mp3']),))
    (path / 'media').mkdir(exist_ok=True); (path / 'media' / 'Aa1.mp3').write_bytes(b'ID3' + bytes(600))
    return path


def settings_in(dbfile):
    con = sqlite3.connect(str(dbfile))
    try: return {k: json.loads(v) for k, v in con.execute('SELECT key,value FROM settings')}
    finally: con.close()


def backup_settings(backup, tmp_path):
    """The settings a backup holds, read from a copy so the backup itself is never opened."""
    peek = tmp_path / 'peek.sqlite3'; peek.write_bytes(backup.read_bytes())
    con = sqlite3.connect(str(peek))
    try: assert con.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
    finally: con.close()
    return settings_in(peek)


class Crash(BaseException):
    """The process dies (window closed, power cut): no except clause or clean-up in the app runs."""


def copy_fails(monkeypatch, error):
    """The migration's src.backup() writes part of the copy, then raises `error`. Every other connection behaves normally."""
    connect = sqlite3.connect

    class Failing(sqlite3.Connection):
        def backup(self, target, *args, **kwargs):
            target.execute('CREATE TABLE half_written(x)')
            raise error
    monkeypatch.setattr(sqlite3, 'connect', lambda *a, **kw: connect(*a, **kw, factory=Failing))


def boom(*args, **kwargs):
    raise RuntimeError('simulated failure')


def overlay_js(): return (STATIC / 'overlay.js').read_text(encoding='utf-8')


def line(src, start): return next(x for x in src.splitlines() if x.startswith(start))


# ---------- upgrade[2]: the named backup before the sound library migration ----------
class TestNamedBackup:
    def test_a_crash_mid_copy_leaves_no_backup_and_the_next_start_writes_one(self, tmp_path, monkeypatch):
        path = legacy_159(tmp_path / 'data'); backups = path / 'backups'; before = settings_in(path / 'acepressure.sqlite3')
        copy_fails(monkeypatch, Crash())
        with pytest.raises(Crash): Store(path, 's' * 48)
        monkeypatch.undo()
        assert not (backups / BACKUP).exists() and (backups / (BACKUP + '.partial')).exists(), 'the half copy keeps its temporary name'
        assert settings_in(path / 'acepressure.sqlite3') == before, 'nothing was migrated'
        store = Store(path, 's' * 48)
        assert sorted(p.name for p in backups.iterdir()) == [BACKUP], 'the stale partial copy is cleaned up'
        old = backup_settings(backups / BACKUP, tmp_path)
        assert old['sounds'] == ['chime', 'Aa1.mp3'] and 'sound_library_migrated' not in old and 'default_sound' not in old
        assert store.settings()['sound_library_migrated']['imported'] == 1

    def test_a_failed_copy_is_removed_and_the_retry_of_a_failed_migration_writes_it(self, tmp_path, monkeypatch, caplog):
        path = legacy_159(tmp_path / 'data'); backups = path / 'backups'; before = settings_in(path / 'acepressure.sqlite3')
        copy_fails(monkeypatch, OSError('disk full'))
        monkeypatch.setattr(Store, '_insert_sound', boom)
        with caplog.at_level(logging.WARNING, logger='acepressure.sounds'): Store(path, 's' * 48)
        assert WARNING in caplog.text and 'retried on the next start' in caplog.text
        assert list(backups.iterdir()) == [], 'no copy under either name'
        assert settings_in(path / 'acepressure.sqlite3') == before, 'the migration rolled back as before'
        monkeypatch.undo()
        store = Store(path, 's' * 48)
        assert sorted(p.name for p in backups.iterdir()) == [BACKUP]
        assert backup_settings(backups / BACKUP, tmp_path)['sounds'] == ['chime', 'Aa1.mp3']
        assert store.settings()['sound_library_migrated']['imported'] == 1

    def test_stale_partial_files_are_removed_before_copying(self, tmp_path):
        path = legacy_159(tmp_path / 'data'); backups = path / 'backups'; backups.mkdir()
        (backups / (BACKUP + '.partial')).write_bytes(b'half a page ' * 40)  # SQLite can't back up into this
        (backups / (BACKUP + '.partial-journal')).write_bytes(bytes(512))
        Store(path, 's' * 48)
        assert sorted(p.name for p in backups.iterdir()) == [BACKUP]
        assert backup_settings(backups / BACKUP, tmp_path)['sounds'] == ['chime', 'Aa1.mp3']

    def test_an_existing_backup_is_never_replaced(self, tmp_path):
        path = legacy_159(tmp_path / 'data'); backups = path / 'backups'; backups.mkdir()
        (backups / BACKUP).write_bytes(b'the copy an earlier attempt finished')
        store = Store(path, 's' * 48)
        assert (backups / BACKUP).read_bytes() == b'the copy an earlier attempt finished'
        assert sorted(p.name for p in backups.iterdir()) == [BACKUP] and store.settings()['sound_library_migrated']['imported'] == 1

    def test_a_file_held_open_for_a_moment_is_renamed_on_a_retry(self, tmp_path, monkeypatch, caplog):
        path = legacy_159(tmp_path / 'data'); real = Path.replace; calls = []
        def briefly_held(self, target):  # an antivirus scan holds the just-closed copy for the first two attempts
            calls.append(1)
            if len(calls) < 3: raise PermissionError('The process cannot access the file because it is being used by another process')
            return real(self, target)
        monkeypatch.setattr(Path, 'replace', briefly_held); monkeypatch.setattr('acepressure.domain.time.sleep', lambda s: None)
        with caplog.at_level(logging.WARNING, logger='acepressure.sounds'): store = Store(path, 's' * 48)
        monkeypatch.undo()
        assert len(calls) == 3 and 'Could not' not in caplog.text and 'Saved the backup as' not in caplog.text
        assert sorted(p.name for p in (path / 'backups').iterdir()) == [BACKUP]
        assert backup_settings(path / 'backups' / BACKUP, tmp_path)['sounds'] == ['chime', 'Aa1.mp3']
        assert store.settings()['sound_library_migrated']['imported'] == 1

    def test_a_rename_that_keeps_failing_keeps_the_complete_copy_and_still_migrates(self, tmp_path, monkeypatch, caplog):
        path = legacy_159(tmp_path / 'data')
        def held_open(self, target): raise PermissionError('The process cannot access the file because it is being used by another process')
        monkeypatch.setattr(Path, 'replace', held_open); monkeypatch.setattr('acepressure.domain.time.sleep', lambda s: None)
        with caplog.at_level(logging.WARNING, logger='acepressure.sounds'): store = Store(path, 's' * 48)
        monkeypatch.undo()
        assert f'Saved the backup as {BACKUP}.partial because it could not be renamed to {BACKUP}; migrating.' in caplog.text
        assert WARNING not in caplog.text and sorted(p.name for p in (path / 'backups').iterdir()) == [BACKUP + '.partial']
        assert backup_settings(path / 'backups' / (BACKUP + '.partial'), tmp_path)['sounds'] == ['chime', 'Aa1.mp3'], 'the copy is complete'
        assert store.settings()['sound_library_migrated']['imported'] == 1


# ---------- sound[1], sound[3], sound[5]: overlay.js (static checks) ----------
class TestOverlayAudio:
    def test_skip_tts_during_the_alert_sound_cancels_the_readout(self):
        js = overlay_js()
        run = re.search(r'async function runQueue\(\).*?finally\{busy=false;\}\}', js, re.S).group(0)
        # A Skip pressed before this claim is absorbed by update() first, so only a Skip during this alert cancels its readout.
        assert 'p=result.alert;if(!p)return;await update();const gen=speechGeneration;' in run
        assert "spoken=gen===speechGeneration&&await speak(p,result.tts_engine,volumeLevel(result.tts_volume));if(spoken)reportSpeech('played');" in run
        assert run.index('const gen=speechGeneration;') < run.index('await sound(') < run.index('gen===speechGeneration&&')
        # Skip TTS and Mute reach the overlay through the state poll, which bumps the generation and stops speech in progress.
        assert 'function stopSpeech(){speechGeneration++;' in js and 'skipVersion!==s.skip_version)||s.muted)stopSpeech();' in js
        assert run.count('client:clientType') == 3 and 'tts_played:spoken' in run

    def test_a_sound_file_gets_10_s_to_start_then_31_s_from_its_first_playing(self):
        js = overlay_js(); play = line(js, 'async function playAudio(')
        assert 'timer=setTimeout(()=>finish(false),isSpeech?timeout:10000);' in play, 'a clip that never starts resolves false: the default plays'
        assert ("if(isSpeech)ttsCancel=finish;else a.addEventListener('playing',()=>{started=true;clearTimeout(timer);"
                "timer=setTimeout(()=>finish(true),timeout);},{once:true});") in play, 'the cap starts at the first playing and counts as played'
        assert 'a.onended=()=>finish(true);a.onerror=()=>finish(started);a.play().catch(()=>finish(false));' in play
        assert "return playAudio('/media/'+encodeURIComponent(name),31000,false,volume)" in js and 'playAudio(url,50000,true,volume)' in js

    def test_a_suspended_audio_context_gives_up_after_a_second(self):
        sound = line(overlay_js(), 'async function sound(')
        assert "try{await Promise.race([c.resume(),pause(1000)]);if(c.state!=='running')return false;" in sound
        assert 'await c.resume();' not in sound and 'finally{await c.close();}' in sound


# ---------- E1: Voice Studio's TTS health line (static check) ----------
def test_voice_studio_explains_voice_missing_for_a_server_engine():
    js = (STATIC / 'designer.js').read_text(encoding='utf-8')
    assert "health.textContent=ttsHealthText(await A('tts/health'),state.settings.tts_engine);" in js and 'function ttsHealthText(d,engine){' in js
    fn = js[js.index('function ttsHealthText('):]
    hint = ("if(last.code==='voice_missing'&&['edge','piper','windows','azure'].includes(engine))return 'The last OBS report ('+date(last.at)+') "
            "found no voice. If you’ve already chosen an Edge, Piper, Windows or Azure voice, OBS is probably still running the old overlay page: "
            "in OBS, right-click the alert source → Properties → “Refresh cache of current page” (or restart OBS), then send a test alert.';")
    assert hint in fn and fn.index(hint) < fn.index('voice_missing:')
    assert "voice_missing:'OBS doesn’t have that browser voice, so nothing was read. Choose an Edge, Piper, Windows or Azure voice above and save.'" in fn


# ---------- admin[3]: Fix_Audio.bat ----------
def test_fix_audio_bat_points_to_the_sound_library():
    raw = (ROOT / 'Fix_Audio.bat').read_bytes(); text = raw.decode('ascii')
    assert raw.count(b'\n') == raw.count(b'\r\n') and raw.endswith(b'\r\n'), 'CRLF line endings for cmd.exe'
    for gone in ('Sounds/media', 'Soundboard', 'soundboard', 'Upload alert sound', 'the alert sound limit'):
        assert gone not in text, gone
    for echo in ('echo        Admin -^> Sound library -^> Add a sound', 'echo        Admin -^> Sound library -^> Replace audio (or Upload audio on a meme slot)',
                 'echo    Then: Admin -^> Sound library -^> Add a sound -^> pick ^<name^>_fixed.mp3',
                 'echo    This tool cuts clips at 20 seconds. Library sounds may run up to 30 seconds,'):
        assert echo + '\r\n' in text, echo
    assert '-t 20 "%OUT%"' in text and 'OPTIONAL' in text


# ---------- security[0]: the browser acceptance script ----------
def test_browser_smoke_waits_for_the_paid_state_deterministically():
    src = (ROOT / 'tests' / 'browser_smoke.py').read_text(encoding='utf-8'); compile(src, 'browser_smoke.py', 'exec')
    start = src.index("admin.get_by_role('button',name='Simulate payment').click()")
    step = src[start:src.index("checks.append('Admin simulator → verified public success')")]
    assert "expect(admin.get_by_role('button',name='Simulate payment')).to_have_count(0,timeout=15000)" in step, 'the simulator has answered'
    assert "status=public.get_by_role('button',name='Check payment status')" in step and 'status.click()' in step
    assert "re.compile(r'^Thank you,'))).to_be_visible(timeout=30000)" in step and 'timeout=12000' not in src
    assert "button('Check payment status',manualCheck" in (STATIC / 'public.js').read_text(encoding='utf-8'), 'the selector exists'
