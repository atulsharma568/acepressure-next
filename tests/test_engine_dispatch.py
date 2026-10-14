"""Tests for engine dispatch in acepressure.tts_service (v1.4.0 / v1.4.1 features).

Covers:
    - _mimetype_for extension handling (.mp3 vs .wav/fallback)
    - synthesize(engine=...) dispatches to the correct backend module
    - catalog(engine=...) dispatches to the correct backend, with Piper
      requiring a data directory
    - Admin /api/admin/settings accepts the 1.4.1 engine whitelist additions
      (edge, piper) and still rejects unknown engines.

Backend side effects are stubbed via monkeypatch so these tests never touch
the Edge TTS network endpoint, the Piper ONNX loader, or Windows SAPI.
"""
import os
from pathlib import Path

import pytest

from acepressure import tts_service
from acepressure.domain import Problem


# ---- _mimetype_for ---------------------------------------------------------

def test_mimetype_returns_audio_mpeg_for_mp3():
    assert tts_service._mimetype_for('clip.mp3') == 'audio/mpeg'
    assert tts_service._mimetype_for(Path('/tmp/anything.mp3')) == 'audio/mpeg'
    # Extension check is case-insensitive via .lower().
    assert tts_service._mimetype_for('CAPS.MP3') == 'audio/mpeg'


def test_mimetype_returns_audio_wav_for_non_mp3_and_fallback():
    assert tts_service._mimetype_for('clip.wav') == 'audio/wav'
    assert tts_service._mimetype_for('CAPS.WAV') == 'audio/wav'
    # Fallback: no extension or unknown extension defaults to audio/wav.
    assert tts_service._mimetype_for('no_extension') == 'audio/wav'
    assert tts_service._mimetype_for('weird.ogg') == 'audio/wav'
    assert tts_service._mimetype_for(Path('/tmp/piper-abc.wav')) == 'audio/wav'


# ---- synthesize dispatch ---------------------------------------------------

def test_synthesize_engine_edge_dispatches_to_edge_tts_service(tmp_path, monkeypatch):
    from acepressure import edge_tts_service
    calls = []

    def fake(directory, text, voice):
        calls.append((directory, text, voice))
        p = Path(directory) / 'edge-fake.mp3'
        p.write_bytes(b'fake-mp3-bytes')
        return p

    monkeypatch.setattr(edge_tts_service, 'synthesize', fake)
    out = tts_service.synthesize(tmp_path, 'Hello Edge', 'en-US-AvaMultilingualNeural', 'edge')
    assert calls == [(tmp_path, 'Hello Edge', 'en-US-AvaMultilingualNeural')]
    assert out.name == 'edge-fake.mp3'
    # Confirm the dispatched return path is the one we wrote.
    assert out.read_bytes() == b'fake-mp3-bytes'


def test_synthesize_engine_piper_dispatches_to_piper_tts_service(tmp_path, monkeypatch):
    from acepressure import piper_tts_service
    calls = []

    def fake(directory, text, voice):
        calls.append((directory, text, voice))
        p = Path(directory) / 'piper-fake.wav'
        p.write_bytes(b'fake-wav-bytes')
        return p

    monkeypatch.setattr(piper_tts_service, 'synthesize', fake)
    out = tts_service.synthesize(tmp_path, 'Namaste bhai', 'hi_IN-pratham-medium', 'piper')
    assert calls == [(tmp_path, 'Namaste bhai', 'hi_IN-pratham-medium')]
    assert out.name == 'piper-fake.wav'


def test_synthesize_engine_windows_on_non_windows_raises_problem_503(tmp_path):
    if os.name == 'nt':
        pytest.skip('render_speech only raises Problem(503) off Windows.')
    with pytest.raises(Problem) as exc:
        tts_service.synthesize(tmp_path, 'hi', 'Microsoft David Desktop', 'windows')
    assert exc.value.status == 503
    assert 'Windows' in exc.value.message


def test_synthesize_engine_bogus_raises_problem(tmp_path):
    with pytest.raises(Problem) as exc:
        tts_service.synthesize(tmp_path, 'hi', 'anything', 'bogus')
    # The dispatch falls through to the "not azure" branch -> Problem(..., 400).
    assert exc.value.status == 400


# ---- catalog dispatch ------------------------------------------------------

def test_catalog_engine_edge_dispatches_to_edge_tts_service(monkeypatch):
    from acepressure import edge_tts_service
    sentinel = [{'id': 'en-US-FakeNeural', 'label': 'fake · FREE',
                 'gender': 'Female', 'locale': 'en-US'}]
    calls = []

    def fake():
        calls.append(True)
        return sentinel

    monkeypatch.setattr(edge_tts_service, 'catalog', fake)
    out = tts_service.catalog('edge')
    assert out is sentinel
    assert calls == [True]


def test_catalog_engine_piper_without_directory_raises_problem_500():
    with pytest.raises(Problem) as exc:
        tts_service.catalog('piper', directory=None)
    assert exc.value.status == 500
    assert 'Piper' in exc.value.message


def test_catalog_engine_piper_with_directory_dispatches_to_piper_tts_service(tmp_path, monkeypatch):
    from acepressure import piper_tts_service
    sentinel = [{'id': 'hi_IN-pratham-medium', 'label': 'hi-IN · pratham · OFFLINE',
                 'gender': 'Any', 'locale': 'hi-IN'}]
    calls = []

    def fake(directory):
        calls.append(directory)
        return sentinel

    monkeypatch.setattr(piper_tts_service, 'catalog', fake)
    out = tts_service.catalog('piper', directory=tmp_path)
    assert out is sentinel
    assert calls == [tmp_path]


def test_catalog_engine_bogus_raises_problem():
    with pytest.raises(Problem) as exc:
        tts_service.catalog('bogus')
    # Default Problem status is 400.
    assert exc.value.status == 400


# ---- /api/admin/settings 1.4.1 engine-whitelist regression tests ----------

def test_settings_accepts_tts_engine_edge(admin):
    c, h = admin
    r = c.post('/api/admin/settings', json={'tts_engine': 'edge'}, headers=h)
    assert r.status_code == 200, r.json
    # Belt-and-suspenders: the 1.4.1 rejection message must NOT appear.
    assert 'Invalid TTS engine' not in str(r.json)


def test_settings_accepts_tts_engine_piper(admin):
    c, h = admin
    r = c.post('/api/admin/settings', json={'tts_engine': 'piper'}, headers=h)
    assert r.status_code == 200, r.json
    assert 'Invalid TTS engine' not in str(r.json)


def test_settings_rejects_tts_engine_bogus(admin):
    c, h = admin
    r = c.post('/api/admin/settings', json={'tts_engine': 'bogus'}, headers=h)
    assert r.status_code == 400
    assert r.json.get('error') == 'Invalid TTS engine.'
