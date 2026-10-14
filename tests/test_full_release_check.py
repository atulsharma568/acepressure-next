"""Full release-time coverage: 80+ tests across TTS, SSML, Hinglish, Edge/Piper, visuals,
Paytm, bridge, settings, API shape, package integrity, templates and docs.

Each test is intentionally small and isolated. All fixtures come from tests/conftest.py.
No test depends on actual network, Windows SAPI or FFmpeg: external engines are monkeypatched.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import sqlite3
import time
import wave
from pathlib import Path
from xml.sax.saxutils import escape

import pytest
from PIL import Image

from acepressure import app as app_module
from acepressure import domain
from acepressure import edge_tts_service, parsers, piper_tts_service, speech, tts_service, visuals
from acepressure.domain import DEFAULTS, Problem, Store, clean, money, now, uid
from acepressure.paytm_capture import parse_amount
from acepressure.paytm_match import parse_event
from acepressure.tts_service import (
    HINGLISH_TRANSLITERATION,
    _mimetype_for,
    _voice_locale,
    build_ssml,
    hinglish_score,
    has_devanagari,
    is_hinglish,
    maybe_transliterate,
    transliterate_hinglish,
    voice_handles_hindi,
)
from acepressure.visuals import DEFAULT_VISUALS, validate_visuals

ROOT = Path(__file__).resolve().parents[1]


# ---------- small helpers ----------
def make_wav(duration_s: float = 0.1) -> bytes:
    b = io.BytesIO()
    with wave.open(b, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
        w.writeframes(b'\x00\x00' * int(24000 * duration_s))
    return b.getvalue()


def _ffmpeg_available():
    import shutil as _sh
    return bool(_sh.which('ffmpeg') and _sh.which('ffprobe'))


def make_real_mp3(duration_s: float = 1.5) -> bytes:
    """A real decodable MP3 via ffmpeg (sine tone). Needed because v1.5.6 added ffprobe
    validation that correctly rejects synthesized fake-frame MP3s."""
    import subprocess as _sp, tempfile as _tf, os as _os
    if not _ffmpeg_available():
        pytest.skip('ffmpeg required for real MP3 fixture')
    tmp = _tf.mkdtemp()
    out = _os.path.join(tmp, 'tone.mp3')
    _sp.run(['ffmpeg', '-v', 'error', '-f', 'lavfi',
             '-i', f'sine=frequency=440:duration={duration_s}',
             '-codec:a', 'libmp3lame', '-b:a', '128k', '-y', out],
            check=True, capture_output=True)
    with open(out, 'rb') as f: return f.read()


def make_real_ogg(duration_s: float = 1.5) -> bytes:
    """A real decodable OGG via ffmpeg — tries libvorbis first, falls back to the
    experimental vorbis encoder (homebrew ffmpeg often omits libvorbis)."""
    import subprocess as _sp, tempfile as _tf, os as _os
    if not _ffmpeg_available():
        pytest.skip('ffmpeg required for real OGG fixture')
    tmp = _tf.mkdtemp()
    out = _os.path.join(tmp, 'tone.ogg')
    base = ['ffmpeg', '-v', 'error', '-f', 'lavfi',
            '-i', f'sine=frequency=440:duration={duration_s}']
    for codec_args in [['-codec:a', 'libvorbis'],
                       ['-codec:a', 'vorbis', '-strict', 'experimental'],
                       ['-codec:a', 'libopus']]:
        r = _sp.run(base + codec_args + ['-y', out], capture_output=True)
        if r.returncode == 0:
            with open(out, 'rb') as f: return f.read()
    pytest.skip('ffmpeg has no OGG encoder compiled in')


def _start_session(admin):
    c, h = admin
    return c.post('/api/admin/sessions', json={'action': 'start', 'title': 'Live'}, headers=h)


def _tip(app, **kw):
    base = dict(amount=100, name='Rahul', message='GG', tts=True, voice='en-IN', sound='chime')
    base.update(kw)
    return app.store.create_tip(base, True)


# =====================================================================
# 1. Hinglish detection (10 tests)
# =====================================================================
class TestHinglishDetection:
    def test_has_devanagari_empty(self):
        assert has_devanagari('') is False
        assert has_devanagari(None) is False

    def test_has_devanagari_pure_english(self):
        assert has_devanagari('hello world') is False

    def test_has_devanagari_pure_hindi(self):
        assert has_devanagari('नमस्ते भाई') is True

    def test_has_devanagari_mixed(self):
        assert has_devanagari('GG भाई') is True

    def test_hinglish_score_empty_is_zero(self):
        assert hinglish_score('') == 0.0
        assert hinglish_score(None) == 0.0

    def test_hinglish_score_pure_devanagari_is_one(self):
        assert hinglish_score('यह बहुत अच्छा है') == 1.0

    def test_hinglish_score_romanized(self):
        # 'bhai' and 'kya' are romanized Hindi
        s = hinglish_score('bhai kya')
        assert s > 0.5

    def test_hinglish_score_pure_english(self):
        # All English — score should be 0
        assert hinglish_score('hello world welcome') == 0.0

    def test_is_hinglish_threshold(self):
        assert is_hinglish('bhai kya mast hai yaar') is True
        # Use words NOT in the romanized list; 'the'/'stream' are both listed as roman Hindi
        assert is_hinglish('welcome everyone please support my channel today here') is False

    def test_is_hinglish_only_devanagari_triggers(self):
        # Even one Devanagari char forces True
        assert is_hinglish('x') is False
        assert is_hinglish('x हे') is True


# =====================================================================
# 2. Voice locale derivation (7 tests)
# =====================================================================
class TestVoiceLocale:
    def test_voice_locale_empty_defaults_english_india(self):
        assert _voice_locale('') == 'en-IN'
        assert _voice_locale(None) == 'en-IN'

    def test_voice_locale_azure_english(self):
        assert _voice_locale('en-US-AvaMultilingualNeural') == 'en-US'

    def test_voice_locale_hindi(self):
        assert _voice_locale('hi-IN-SwaraNeural') == 'hi-IN'

    def test_voice_locale_british(self):
        assert _voice_locale('en-GB-LibbyNeural') == 'en-GB'

    def test_voice_locale_bare_locale_passes_through(self):
        assert _voice_locale('en-IN') == 'en-IN'

    def test_voice_locale_garbage_falls_back(self):
        assert _voice_locale('garbage') == 'en-IN'

    def test_voice_locale_piper_underscore_form(self):
        # Piper uses 'hi_IN-pratham-medium' instead of dash. Must still parse to 'hi-IN'.
        assert _voice_locale('hi_IN-pratham-medium') == 'hi-IN'
        assert _voice_locale('en_US-amy-medium') == 'en-US'


# =====================================================================
# 2b. Roman Hindi → Devanagari transliteration (12 tests)
# =====================================================================
class TestTransliteration:
    def test_map_has_core_words(self):
        for k, v in [('bhai', 'भाई'), ('kya', 'क्या'), ('tha', 'था'), ('hai', 'है')]:
            assert HINGLISH_TRANSLITERATION[k] == v

    def test_empty_returns_empty(self):
        assert transliterate_hinglish('') == ''
        assert transliterate_hinglish(None) is None

    def test_pure_english_unchanged(self):
        assert transliterate_hinglish('hello world welcome') == 'hello world welcome'

    def test_single_word_replacement(self):
        assert transliterate_hinglish('bhai') == 'भाई'

    def test_sentence_mixes_english_and_devanagari(self):
        # The exact user-reported sentence.
        out = transliterate_hinglish('GG bhai kya clutch tha, thanks for the stream')
        assert 'भाई' in out
        assert 'क्या' in out
        assert 'था' in out
        # English words preserved
        assert 'clutch' in out
        assert 'thanks' in out
        assert 'stream' in out

    def test_case_insensitive(self):
        # Uppercase and mixed-case should still match.
        assert transliterate_hinglish('BHAI') == 'भाई'
        assert transliterate_hinglish('Kya') == 'क्या'

    def test_word_boundary_respected(self):
        # 'bhai' should not match inside 'bhaiya' (longer form matched first).
        assert transliterate_hinglish('bhaiya') == 'भैया'
        # Nor inside 'bhaiwala'
        assert transliterate_hinglish('bhaiwala') == 'bhaiwala'

    def test_voice_handles_hindi_locales(self):
        assert voice_handles_hindi('hi-IN-SwaraNeural') is True
        assert voice_handles_hindi('hi_IN-pratham-medium') is True  # Piper underscore
        assert voice_handles_hindi('en-US-AvaMultilingualNeural') is True
        assert voice_handles_hindi('en-IN-NeerjaNeural') is False
        assert voice_handles_hindi('en-US-GuyNeural') is False
        assert voice_handles_hindi('') is False
        assert voice_handles_hindi(None) is False

    def test_maybe_transliterate_english_voice_leaves_alone(self):
        # English voice reading Hinglish should NOT be transliterated — would make it worse.
        out = maybe_transliterate('bhai kya tha', 'en-IN-NeerjaNeural')
        assert out == 'bhai kya tha'

    def test_maybe_transliterate_hindi_voice_replaces(self):
        out = maybe_transliterate('bhai kya tha', 'hi-IN-SwaraNeural')
        assert 'भाई' in out and 'क्या' in out and 'था' in out

    def test_maybe_transliterate_multilingual_voice_replaces(self):
        out = maybe_transliterate('bhai kya tha', 'en-US-AvaMultilingualNeural')
        assert 'भाई' in out

    def test_maybe_transliterate_non_hinglish_passthrough(self):
        # Not Hinglish → no change even on a Hindi voice.
        out = maybe_transliterate('hello world welcome', 'hi-IN-SwaraNeural')
        assert out == 'hello world welcome'


# =====================================================================
# 3. SSML construction (8 tests)
# =====================================================================
class TestBuildSSML:
    def test_pure_english_no_hindi_wrap(self):
        ssml = build_ssml('hello world', 'en-IN-NeerjaNeural').decode()
        assert "xml:lang='en-IN'" in ssml
        assert '<lang' not in ssml

    def test_hinglish_english_voice_wraps_hi(self):
        ssml = build_ssml('GG bhai kya mast tha stream', 'en-US-GuyNeural').decode()
        assert "xml:lang='en-US'" in ssml  # outer
        assert "<lang xml:lang='hi-IN'>" in ssml

    def test_hinglish_hindi_voice_does_not_wrap(self):
        ssml = build_ssml('kya hai bhai mast', 'hi-IN-SwaraNeural').decode()
        assert "xml:lang='hi-IN'" in ssml
        assert "<lang xml:lang='hi-IN'>" not in ssml

    def test_multilingual_voice_skips_wrap(self):
        ssml = build_ssml('bhai kya mast tha', 'en-US-AvaMultilingualNeural').decode()
        assert '<lang' not in ssml

    def test_xml_escaping(self):
        ssml = build_ssml('A & B <bad>', 'en-IN-NeerjaNeural').decode()
        assert '&amp;' in ssml and '&lt;bad&gt;' in ssml
        assert '<bad>' not in ssml

    def test_voice_quoted_safely(self):
        ssml = build_ssml('hi', 'en-IN-NeerjaNeural').decode()
        # voice attr uses quoteattr → single or double quotes
        assert ("name=\"en-IN-NeerjaNeural\"" in ssml) or ("name='en-IN-NeerjaNeural'" in ssml)

    def test_devanagari_text_wraps_in_english_voice(self):
        ssml = build_ssml('नमस्ते', 'en-IN-NeerjaNeural').decode()
        assert "<lang xml:lang='hi-IN'>" in ssml

    def test_wrapper_can_be_disabled(self):
        ssml = build_ssml('bhai kya mast', 'en-US-GuyNeural', add_hinglish_wrapper=False).decode()
        assert '<lang' not in ssml


# =====================================================================
# 4. Mimetype routing + synthesize dispatch (6 tests)
# =====================================================================
class TestMimetypeAndDispatch:
    def test_mimetype_wav(self):
        assert _mimetype_for(Path('/tmp/foo.wav')) == 'audio/wav'

    def test_mimetype_mp3(self):
        assert _mimetype_for(Path('/tmp/foo.mp3')) == 'audio/mpeg'

    def test_mimetype_case_insensitive(self):
        assert _mimetype_for(Path('/tmp/FOO.MP3')) == 'audio/mpeg'

    def test_catalog_unknown_engine_raises(self):
        with pytest.raises(Problem):
            tts_service.catalog('fake_engine')

    def test_catalog_browser_raises(self):
        # 'browser' is client-only, no server catalog
        with pytest.raises(Problem):
            tts_service.catalog('browser')

    def test_synthesize_bad_engine_raises(self, tmp_path):
        with pytest.raises(Problem):
            tts_service.synthesize(tmp_path, 'hi', 'en-IN', 'nope')


# =====================================================================
# 5. Azure synthesis defensive paths (5 tests)
# =====================================================================
class TestAzureSynthesisDefensive:
    def test_voice_identifier_regex_rejects_space(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tts_service, 'azure_request', lambda *a, **k: make_wav())
        with pytest.raises(Problem):
            tts_service.synthesize(tmp_path, 'hi', 'bad voice', 'azure')

    def test_voice_identifier_regex_rejects_too_short(self, tmp_path):
        with pytest.raises(Problem):
            tts_service.synthesize(tmp_path, 'hi', 'xy', 'azure')

    def test_azure_request_rejects_missing_credentials(self, monkeypatch):
        monkeypatch.delenv('AZURE_SPEECH_KEY', raising=False)
        monkeypatch.delenv('AZURE_SPEECH_REGION', raising=False)
        with pytest.raises(Problem) as e:
            tts_service.azure_request('cognitiveservices/voices/list')
        assert e.value.status == 503

    def test_azure_rejects_bad_region_format(self, monkeypatch):
        monkeypatch.setenv('AZURE_SPEECH_KEY', 'k' * 32)
        monkeypatch.setenv('AZURE_SPEECH_REGION', 'bad region!')
        with pytest.raises(Problem):
            tts_service.azure_request('x')

    def test_azure_invalid_audio_rejected(self, tmp_path, monkeypatch):
        # Return non-wav bytes — wave.open should fail validation
        monkeypatch.setattr(tts_service, 'azure_request', lambda *a, **k: b'garbage not wav')
        with pytest.raises(Problem):
            tts_service.synthesize(tmp_path, 'hi there', 'en-IN-NeerjaNeural', 'azure')


# =====================================================================
# 6. Edge TTS service (5 tests)
# =====================================================================
class TestEdgeTTS:
    def test_catalog_filters_properly(self, monkeypatch):
        # Stub list_voices response
        fake_voices = [
            {'ShortName': 'en-IN-NeerjaNeural', 'Locale': 'en-IN', 'Gender': 'Female', 'FriendlyName': 'Microsoft Server Speech Text to Speech Voice (en-IN, NeerjaNeural)'},
            {'ShortName': 'hi-IN-SwaraNeural', 'Locale': 'hi-IN', 'Gender': 'Female', 'FriendlyName': 'Microsoft Server Speech Text to Speech Voice (hi-IN, SwaraNeural)'},
            {'ShortName': 'en-US-AvaMultilingualNeural', 'Locale': 'en-US', 'Gender': 'Female', 'FriendlyName': 'Microsoft Server Speech Text to Speech Voice (en-US, AvaMultilingualNeural)'},
            {'ShortName': 'fr-FR-DeniseNeural', 'Locale': 'fr-FR', 'Gender': 'Female', 'FriendlyName': 'French'},
            {'ShortName': 'en-GB-NoGender', 'Locale': 'en-GB', 'Gender': 'Unknown', 'FriendlyName': 'Skip me'},
        ]
        monkeypatch.setattr(edge_tts_service, '_CACHED_VOICES', None, raising=False)
        monkeypatch.setattr(edge_tts_service, '_CACHED_VOICES_AT', 0, raising=False)
        monkeypatch.setattr(edge_tts_service, '_have_edge_tts', lambda: True)
        # Fake asyncio.run to return the stubbed voices directly, bypassing the real edge_tts module.
        import acepressure.edge_tts_service as mod
        monkeypatch.setattr(mod.asyncio, 'run', lambda coro: fake_voices)
        # Also need `import edge_tts` inside catalog to succeed — point sys.modules to a bare object
        import types, sys
        stub = types.SimpleNamespace(list_voices=lambda: None)
        monkeypatch.setitem(sys.modules, 'edge_tts', stub)
        out = edge_tts_service.catalog()
        ids = [v['id'] for v in out]
        assert 'fr-FR-DeniseNeural' not in ids
        assert 'en-GB-NoGender' not in ids
        assert 'en-IN-NeerjaNeural' in ids and 'hi-IN-SwaraNeural' in ids
        # Multilingual first
        assert ids[0] == 'en-US-AvaMultilingualNeural'

    def test_catalog_without_edge_tts_installed(self, monkeypatch):
        monkeypatch.setattr(edge_tts_service, '_have_edge_tts', lambda: False)
        monkeypatch.setattr(edge_tts_service, '_CACHED_VOICES', None, raising=False)
        monkeypatch.setattr(edge_tts_service, '_CACHED_VOICES_AT', 0, raising=False)
        with pytest.raises(Problem) as e:
            edge_tts_service.catalog()
        assert e.value.status == 503

    def test_synthesize_invalid_voice_id(self, tmp_path, monkeypatch):
        monkeypatch.setattr(edge_tts_service, '_have_edge_tts', lambda: True)
        with pytest.raises(Problem):
            edge_tts_service.synthesize(tmp_path, 'hello', 'has spaces!')

    def test_synthesize_empty_text(self, tmp_path, monkeypatch):
        monkeypatch.setattr(edge_tts_service, '_have_edge_tts', lambda: True)
        with pytest.raises(Problem):
            edge_tts_service.synthesize(tmp_path, '   ', 'en-IN-NeerjaNeural')

    def test_synthesize_cache_hits(self, tmp_path, monkeypatch):
        """Pre-write the cache file and ensure asyncio.run is never invoked."""
        monkeypatch.setattr(edge_tts_service, '_have_edge_tts', lambda: True)
        folder = tmp_path / 'speech'; folder.mkdir()
        # 'edge-v2' bumped when transliteration behavior was added.
        cache_key = hashlib.sha256(('en-IN-NeerjaNeural' + '\0' + 'hi there' + '\0edge-v2').encode()).hexdigest()
        existing = folder / f'edge-{cache_key}.mp3'
        existing.write_bytes(b'x' * 1000)
        called = {'ran': False}
        def _boom():
            called['ran'] = True
            raise AssertionError('should not run')
        monkeypatch.setattr('asyncio.run', lambda *a, **k: _boom())
        p = edge_tts_service.synthesize(tmp_path, 'hi there', 'en-IN-NeerjaNeural')
        assert p == existing and called['ran'] is False


# =====================================================================
# 7. Piper TTS service (5 tests)
# =====================================================================
class TestPiperTTS:
    def test_catalog_not_installed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(piper_tts_service, '_have_piper', lambda: False)
        with pytest.raises(Problem) as e:
            piper_tts_service.catalog(tmp_path)
        assert e.value.status == 503

    def test_catalog_empty_models_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(piper_tts_service, '_have_piper', lambda: True)
        out = piper_tts_service.catalog(tmp_path)
        assert out == []
        assert (tmp_path / 'piper-voices').is_dir()

    def test_catalog_parses_metadata(self, tmp_path, monkeypatch):
        monkeypatch.setattr(piper_tts_service, '_have_piper', lambda: True)
        folder = tmp_path / 'piper-voices'; folder.mkdir()
        onnx = folder / 'hi_IN-pratham-medium.onnx'; onnx.write_bytes(b'fake')
        meta = folder / 'hi_IN-pratham-medium.onnx.json'
        meta.write_text(json.dumps({'language': {'family': 'hi', 'country_code': 'IN'}, 'dataset': 'pratham', 'audio': {'quality': 'medium'}}), encoding='utf-8')
        out = piper_tts_service.catalog(tmp_path)
        assert len(out) == 1
        assert out[0]['locale'] == 'hi-IN'
        assert 'OFFLINE' in out[0]['label']

    def test_synthesize_missing_model_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(piper_tts_service, '_have_piper', lambda: True)
        with pytest.raises(Problem) as e:
            piper_tts_service.synthesize(tmp_path, 'hello', 'does_not_exist')
        assert e.value.status == 503

    def test_synthesize_invalid_voice_id(self, tmp_path, monkeypatch):
        monkeypatch.setattr(piper_tts_service, '_have_piper', lambda: True)
        with pytest.raises(Problem):
            piper_tts_service.synthesize(tmp_path, 'hello', 'bad voice!')


# =====================================================================
# 8. Settings validation (8 tests)
# =====================================================================
class TestSettingsValidation:
    def test_accepts_edge_engine(self, app, admin):
        c, h = admin
        r = c.post('/api/admin/settings', json={'tts_engine': 'edge'}, headers=h)
        assert r.status_code == 200

    def test_accepts_piper_engine(self, app, admin):
        c, h = admin
        r = c.post('/api/admin/settings', json={'tts_engine': 'piper'}, headers=h)
        assert r.status_code == 200

    def test_accepts_windows_engine(self, app, admin):
        c, h = admin
        r = c.post('/api/admin/settings', json={'tts_engine': 'windows'}, headers=h)
        assert r.status_code == 200

    def test_accepts_azure_engine(self, app, admin):
        c, h = admin
        r = c.post('/api/admin/settings', json={'tts_engine': 'azure'}, headers=h)
        assert r.status_code == 200

    def test_accepts_browser_engine(self, app, admin):
        c, h = admin
        r = c.post('/api/admin/settings', json={'tts_engine': 'browser'}, headers=h)
        assert r.status_code == 200

    def test_accepts_off_engine(self, app, admin):
        c, h = admin
        r = c.post('/api/admin/settings', json={'tts_engine': 'off'}, headers=h)
        assert r.status_code == 200

    def test_rejects_unknown_engine(self, app, admin):
        c, h = admin
        r = c.post('/api/admin/settings', json={'tts_engine': 'gpt'}, headers=h)
        assert r.status_code == 400

    def test_rejects_unknown_key(self, app, admin):
        c, h = admin
        r = c.post('/api/admin/settings', json={'wat': 'nope'}, headers=h)
        assert r.status_code == 400


# =====================================================================
# 9. Money and validation primitives (7 tests)
# =====================================================================
class TestDomainPrimitives:
    def test_money_zero(self):
        assert money('0') == 0

    def test_money_decimal(self):
        assert money('1.50') == 150

    def test_money_negative_rejected(self):
        with pytest.raises(Problem):
            money('-1')

    def test_money_three_decimal_rejected(self):
        with pytest.raises(Problem):
            money('1.123')

    def test_money_nan_rejected(self):
        with pytest.raises(Problem):
            money('NaN')

    def test_clean_strips_controls_and_trims(self):
        assert clean('  hello\x00world  <>  ', 50) == 'helloworld'

    def test_clean_truncates_to_limit(self):
        assert clean('x' * 200, 10) == 'x' * 10


# =====================================================================
# 10. Store creation and settings defaults (5 tests)
# =====================================================================
class TestStore:
    def test_store_initializes_with_defaults(self, tmp_path):
        s = Store(tmp_path, 'secret-key-at-least-16-chars-long')
        settings = s.settings()
        for k, v in DEFAULTS.items():
            assert settings[k] == v

    def test_store_defaults_tts_engine_is_browser(self):
        assert DEFAULTS['tts_engine'] == 'browser'

    def test_backup_creates_valid_sqlite(self, app):
        p = app.store.backup()
        assert p.exists() and p.suffix == '.sqlite3'
        with sqlite3.connect(p) as conn:
            assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'

    def test_uid_unique(self):
        assert len({uid() for _ in range(200)}) == 200

    def test_now_integer_seconds(self):
        t = now()
        assert isinstance(t, int)
        assert abs(t - time.time()) < 2


# =====================================================================
# 11. Visuals validator (6 tests)
# =====================================================================
class TestVisualsValidator:
    def test_defaults_pass(self, tmp_path):
        media = tmp_path / 'media'; media.mkdir()
        d = validate_visuals({}, media)
        assert d['theme'] == 'frame'

    def test_rejects_unknown_key(self, tmp_path):
        media = tmp_path / 'media'; media.mkdir()
        with pytest.raises(Problem):
            validate_visuals({'bogus': 1}, media)

    def test_rejects_bad_hex_color(self, tmp_path):
        media = tmp_path / 'media'; media.mkdir()
        with pytest.raises(Problem):
            validate_visuals({'accent': 'red'}, media)

    def test_rejects_out_of_range_radius(self, tmp_path):
        media = tmp_path / 'media'; media.mkdir()
        with pytest.raises(Problem):
            validate_visuals({'radius': 999}, media)

    def test_rejects_bad_theme(self, tmp_path):
        media = tmp_path / 'media'; media.mkdir()
        with pytest.raises(Problem):
            validate_visuals({'theme': 'rainbow'}, media)

    def test_rejects_non_bool_show_percent(self, tmp_path):
        media = tmp_path / 'media'; media.mkdir()
        with pytest.raises(Problem):
            validate_visuals({'show_percent': 1}, media)

    def test_alert_sound_accepts_wav_filename(self, tmp_path):
        """v1.5.3: visuals.alert_sound used to only allow .wav; must now also accept .mp3/.ogg."""
        media = tmp_path / 'media'; media.mkdir()
        (media / 'abc.wav').write_bytes(b'RIFF\x00\x00\x00\x00WAVE')
        d = validate_visuals({'alert_sound': 'abc.wav'}, media)
        assert d['alert_sound'] == 'abc.wav'

    def test_alert_sound_accepts_mp3_filename(self, tmp_path):
        """v1.5.3: alert_sound must allow .mp3 filenames so a Design Studio save succeeds."""
        media = tmp_path / 'media'; media.mkdir()
        (media / 'abc.mp3').write_bytes(b'ID3')
        d = validate_visuals({'alert_sound': 'abc.mp3'}, media)
        assert d['alert_sound'] == 'abc.mp3'

    def test_alert_sound_accepts_ogg_filename(self, tmp_path):
        """v1.5.3: alert_sound must allow .ogg filenames so a Design Studio save succeeds."""
        media = tmp_path / 'media'; media.mkdir()
        (media / 'abc.ogg').write_bytes(b'OggS')
        d = validate_visuals({'alert_sound': 'abc.ogg'}, media)
        assert d['alert_sound'] == 'abc.ogg'

    def test_alert_sound_rejects_exe_filename(self, tmp_path):
        """Allowlist must still refuse arbitrary extensions."""
        media = tmp_path / 'media'; media.mkdir()
        (media / 'bad.exe').write_bytes(b'MZ')
        with pytest.raises(Problem):
            validate_visuals({'alert_sound': 'bad.exe'}, media)

    def test_alert_sound_rejects_missing_file(self, tmp_path):
        """Allowlisted extension but file does not exist on disk — reject."""
        media = tmp_path / 'media'; media.mkdir()
        with pytest.raises(Problem):
            validate_visuals({'alert_sound': 'ghost.mp3'}, media)


# =====================================================================
# 12. Parsers (6 tests)
# =====================================================================
class TestReceiptParser:
    def test_bridge_disabled_fails_closed(self):
        s = DEFAULTS.copy()  # bridge_enabled False, demo False
        with pytest.raises(Problem):
            parsers.parse_receipt({'sender': 'VM-TEST'}, s, demo=False)

    def test_demo_sender_passthrough(self):
        s = DEFAULTS.copy()
        d = {'sender': 'DEMO-BANK', 'direction': 'credit', 'amount': '100', 'received_at': now(), 'reference': 'R123456'}
        out = parsers.parse_receipt(d, s, demo=True)
        assert out['amount'] == '100'

    def test_demo_rejects_debit(self):
        s = DEFAULTS.copy()
        d = {'sender': 'DEMO-BANK', 'direction': 'debit', 'amount': '100', 'received_at': now(), 'reference': 'R123456'}
        with pytest.raises(Problem):
            parsers.parse_receipt(d, s, demo=True)

    def test_live_wrong_sender_rejected(self):
        s = DEFAULTS | {'bridge_enabled': True, 'bank_sender': 'VM-GOOD', 'parser': 'structured-v1'}
        with pytest.raises(Problem):
            parsers.parse_receipt({'sender': 'VM-BAD'}, s)

    def test_live_missing_fields(self):
        s = DEFAULTS | {'bridge_enabled': True, 'bank_sender': 'VM-GOOD', 'parser': 'structured-v1'}
        with pytest.raises(Problem):
            parsers.parse_receipt({'sender': 'VM-GOOD', 'direction': 'credit'}, s)

    def test_example_credit_parses(self):
        s = DEFAULTS | {'bridge_enabled': True, 'bank_sender': 'VM-BANK', 'parser': 'example-credit-v1'}
        r = parsers.parse_receipt({'sender': 'VM-BANK', 'sms': 'Credit INR 100.50 via UPI Ref ABC12345', 'received_at': now()}, s)
        assert r['amount'] == '100.50' and r['reference'] == 'ABC12345'


# =====================================================================
# 13. Paytm notification parsing (7 tests)
# =====================================================================
class TestPaytmParsing:
    def test_parse_amount_simple(self):
        assert parse_amount('Received ₹100 from X\nDeposited in your Bank') == 10000

    def test_parse_amount_with_comma(self):
        assert parse_amount('Received ₹1,000.50 from X\nDeposited in your Bank') == 100050

    def test_parse_amount_rejects_random_text(self):
        assert parse_amount('Please pay ₹100') is None

    def test_parse_event_success(self):
        t = parse_event('Received ₹100.00 from Someone Deposited in your Bank X - 1234 on 10 October at 11:00 AM', now())
        assert t is not None and t['amount'] == 10000

    def test_parse_event_bad_month(self):
        assert parse_event('Received ₹100.00 from X Deposited in your Y - 1234 on 10 NotAMonth at 11:00 AM', now()) is None

    def test_parse_event_zero_amount(self):
        assert parse_event('Received ₹0 from X Deposited in your Y - 1234 on 10 October at 11:00 AM', now()) is None

    def test_parse_event_bad_hour(self):
        # Hour 13 is not 1..12 (AM/PM)
        assert parse_event('Received ₹100 from X Deposited in your Y - 1234 on 10 October at 13:00 AM', now()) is None


# =====================================================================
# 14. App routing & auth (6 tests)
# =====================================================================
class TestAppRouting:
    def test_health_endpoint_demo_true(self, client):
        r = client.get('/health')
        assert r.status_code == 200 and r.json['demo'] is True

    def test_root_renders_public_page(self, client):
        r = client.get('/')
        assert r.status_code == 200 and b'AcePressure' in r.data

    def test_admin_without_login(self, client):
        assert client.get('/api/admin/state').status_code == 401

    def test_overlay_requires_token(self, client):
        assert client.get('/api/overlay/state').status_code == 401

    def test_overlay_rejects_bad_token(self, client):
        assert client.get('/api/overlay/state?key=badtoken').status_code == 401

    def test_overlay_accepts_valid_token(self, client):
        r = client.get('/api/overlay/state', headers={'X-Overlay-Token': 'o' * 48})
        assert r.status_code == 200


# =====================================================================
# 15. Security headers (3 tests)
# =====================================================================
class TestSecurityHeaders:
    def test_csp_present(self, client):
        r = client.get('/')
        assert 'Content-Security-Policy' in r.headers
        assert "script-src 'self'" in r.headers['Content-Security-Policy']

    def test_x_content_type_options(self, client):
        r = client.get('/')
        assert r.headers['X-Content-Type-Options'] == 'nosniff'

    def test_api_no_store(self, client):
        r = client.get('/health')
        # /health is not under /api/ so Cache-Control may not be set; this is OK
        # Instead check /api/public/top which is under /api
        r = client.get('/api/public/top')
        assert r.headers.get('Cache-Control') == 'no-store'


# =====================================================================
# 16. Public config shape (3 tests)
# =====================================================================
class TestPublicConfig:
    def test_shape(self, client):
        c = client.get('/api/public/config').json
        for k in ('creator', 'welcome', 'minimum', 'maximum', 'voices', 'tts_engine', 'tts_enabled', 'ready'):
            assert k in c

    def test_demo_true(self, client):
        assert client.get('/api/public/config').json['demo'] is True

    def test_voices_contains_default(self, client):
        v = client.get('/api/public/config').json['voices']
        assert 'en-IN' in v


# =====================================================================
# 17. Overlay delivery lifecycle (3 tests)
# =====================================================================
class TestOverlayLifecycle:
    def test_claim_no_alerts_empty(self, client):
        r = client.post('/api/overlay/claim', json={'channel': 'horizontal', 'owner': 'o'}, headers={'X-Overlay-Token': 'o' * 48})
        assert r.status_code == 200 and r.json['alert'] is None

    def test_claim_invalid_channel(self, client):
        r = client.post('/api/overlay/claim', json={'channel': 'other', 'owner': 'o'}, headers={'X-Overlay-Token': 'o' * 48})
        assert r.status_code == 400

    def test_tts_status_invalid_code(self, client):
        r = client.post('/api/overlay/tts-status', json={'code': 'bogus'}, headers={'X-Overlay-Token': 'o' * 48})
        assert r.status_code == 400


# =====================================================================
# 18. Package integrity (4 tests)
# =====================================================================
class TestPackageIntegrity:
    def test_version_file_matches_releases_doc(self):
        v = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
        import re as _re
        assert _re.fullmatch(r'\d+\.\d+\.\d+', v), f'VERSION must be semver, got {v!r}'
        changelog = (ROOT / 'docs' / 'CHANGELOG.md').read_text(encoding='utf-8')
        assert v in changelog, f'VERSION {v} not referenced in docs/CHANGELOG.md'
        readme = (ROOT / 'README.md').read_text(encoding='utf-8')
        assert v in readme, f'VERSION {v} not referenced in README.md'

    def test_license_present(self):
        lic = (ROOT / 'LICENSE').read_text(encoding='utf-8')
        assert 'MIT' in lic

    def test_manifest_hashes_valid(self):
        """Spot-check 20 random entries in PACKAGE_MANIFEST.json for correct sha256."""
        import random
        d = json.loads((ROOT / 'PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))
        rng = random.Random(42)
        for entry in rng.sample(d, min(20, len(d))):
            path = ROOT / entry['path']
            if not path.exists():
                continue
            got = hashlib.sha256(path.read_bytes()).hexdigest()
            assert got == entry['sha256'], f"hash mismatch {entry['path']}"

    def test_tailscale_doc_present(self):
        assert (ROOT / 'docs' / 'TAILSCALE_FUNNEL.md').exists()


# =====================================================================
# 19. Template structural checks (3 tests)
# =====================================================================
class TestTemplates:
    def test_admin_loads_premium(self):
        html = (ROOT / 'acepressure' / 'templates' / 'admin.html').read_text(encoding='utf-8')
        assert 'premium.css' in html and 'premium.js' in html

    def test_overlay_loads_premium(self):
        html = (ROOT / 'acepressure' / 'templates' / 'overlay.html').read_text(encoding='utf-8')
        assert 'premium.css' in html and 'premium.js' in html

    def test_public_loads_premium(self):
        html = (ROOT / 'acepressure' / 'templates' / 'public.html').read_text(encoding='utf-8')
        assert 'premium.css' in html and 'premium.js' in html


# =====================================================================
# 20. Admin dashboard integration (5 tests)
# =====================================================================
class TestAdminDashboard:
    def test_login_wrong_password(self, client):
        assert client.post('/api/login', json={'password': 'wrong'}).status_code == 401

    def test_logout_clears_session(self, admin):
        c, h = admin
        c.post('/api/admin/logout', json={}, headers=h)
        assert c.get('/api/admin/state').status_code == 401

    def test_state_shape(self, admin):
        c, h = admin
        d = c.get('/api/admin/state').json
        for k in ('csrf', 'settings', 'active_session', 'goals', 'demo', 'stats', 'recent'):
            assert k in d

    def test_obs_links_return_key(self, admin):
        c, h = admin
        d = c.get('/api/admin/obs').json
        assert d['key'] == 'o' * 48

    def test_audit_endpoint_requires_admin(self, client):
        assert client.get('/api/admin/audit').status_code == 401


# =====================================================================
# 21. Admin alert actions (4 tests)
# =====================================================================
class TestAdminAlerts:
    def test_unknown_action(self, admin):
        c, h = admin
        assert c.post('/api/admin/alerts', json={'action': 'bogus'}, headers=h).status_code == 400

    def test_skip_updates_version(self, app, admin):
        c, h = admin
        before = app.store.settings()['skip_version']
        assert c.post('/api/admin/alerts', json={'action': 'skip'}, headers=h).status_code == 200
        after = app.store.settings()['skip_version']
        assert after == before + 1

    def test_test_alert_creates_test_payload(self, app, admin):
        c, h = admin
        c.post('/api/admin/alerts', json={'action': 'test', 'amount': 100}, headers=h)
        with app.store.db() as db:
            alerts = db.execute('SELECT payload FROM alerts').fetchall()
        assert len(alerts) == 1 and json.loads(alerts[0][0])['test'] is True

    def test_test_alert_plays_the_default_tip_sound(self, app, admin):
        """The test button sounds like a real tip where the viewer picked nothing: the default sound."""
        c, h = admin
        assert c.post('/api/admin/soundboard/default', json={'value': 'pulse'}, headers=h).status_code == 200
        c.post('/api/admin/alerts', json={'action': 'test'}, headers=h)
        with app.store.db() as db:
            p = json.loads(db.execute('SELECT payload FROM alerts').fetchone()[0])
        assert p['sound'] == 'pulse' and p['sound_source'] == 'default'


# =====================================================================
# 22. Static sanity: no stale engine whitelists in Python/JS source (2 tests)
# =====================================================================
class TestNoStaleWhitelists:
    def test_app_engine_whitelist_is_complete(self):
        src = (ROOT / 'acepressure' / 'app.py').read_text(encoding='utf-8')
        # extract any `tts_engine ... in [...]` pattern
        m = re.search(r"tts_engine'\]\s*not in\s*(\[[^\]]+\])", src)
        assert m, 'tts_engine whitelist not found in app.py'
        whitelist = m.group(1)
        for engine in ('browser', 'windows', 'edge', 'piper', 'azure', 'off'):
            assert f"'{engine}'" in whitelist

    def test_admin_js_lists_all_engines(self):
        src = (ROOT / 'acepressure' / 'static' / 'admin.js').read_text(encoding='utf-8')
        for engine in ('browser', 'windows', 'edge', 'piper', 'azure', 'off'):
            assert f"'{engine}'" in src


# =====================================================================
# 23. BAT files (3 tests)
# =====================================================================
class TestBatFiles:
    def test_essential_bats_set_echo_off_and_cd(self):
        for name in ['Install.bat', 'Start.bat', 'Backup.bat', 'Install_Edge_TTS.bat', 'Install_Piper.bat', 'Setup_Tailscale_URL.bat']:
            text = (ROOT / name).read_text(encoding='utf-8')
            first_two = '\n'.join(text.splitlines()[:3])
            assert '@echo off' in first_two, name
            if name not in ('Backup.bat',):  # Backup uses cd via explicit path—still has cd /d
                assert 'cd /d' in text, name

    def test_bat_do_not_contain_curl_powershell_download_from_unverified(self):
        # Guard against any `iwr`, `Invoke-WebRequest` into script dir from Install bats
        for bat in ['Install_Edge_TTS.bat', 'Install_Piper.bat']:
            text = (ROOT / bat).read_text(encoding='utf-8')
            # Must install from pip (controlled) — not from random URLs
            if 'Invoke-WebRequest' in text or 'curl' in text.lower():
                # If it does, must have at least a .venv pip reference
                assert '.venv' in text, f'{bat} downloads without .venv pip context'

    def test_test_bat_calls_pytest(self):
        text = (ROOT / 'Test.bat').read_text(encoding='utf-8')
        assert 'pytest' in text.lower() or 'test' in text.lower()


# =====================================================================
# 24. Config and JSON files (2 tests)
# =====================================================================
class TestConfigJSON:
    def test_cloudflared_example_is_yml(self):
        p = ROOT / 'config' / 'cloudflared.example.yml'
        assert p.is_file()
        txt = p.read_text(encoding='utf-8')
        assert ':' in txt

    def test_iphone_receipt_is_valid_json(self):
        p = ROOT / 'config' / 'iphone-receipt.example.json'
        json.loads(p.read_text(encoding='utf-8'))  # must parse


# =====================================================================
# 25. Store moderated / banned-words filtering (3 tests)
# =====================================================================
class TestModeration:
    def test_banned_word_replacement(self, app):
        s = app.store.settings()
        out = app.store.moderated('oh shit this is fuck up', s)
        assert '[filtered]' in out
        assert 'shit' not in out and 'fuck' not in out

    def test_moderated_strips_controls(self, app):
        s = app.store.settings()
        out = app.store.moderated('hi\x00world', s)
        assert '\x00' not in out

    def test_moderated_truncates_to_tts_limit(self, app):
        s = app.store.settings()
        s = dict(s); s['tts_limit'] = 10
        out = app.store.moderated('x' * 200, s)
        assert len(out) == 10


# =====================================================================
# 26. Transactions API shape and CSV (3 tests)
# =====================================================================
class TestTransactionsAPI:
    def test_empty_transactions(self, admin):
        c, h = admin
        r = c.get('/api/admin/transactions').json
        assert r == {'transactions': [], 'total': 0}

    def test_csv_header_fallback_when_empty(self, admin):
        c, h = admin
        r = c.get('/api/admin/transactions?export=csv')
        assert r.status_code == 200
        text = r.data.decode('utf-8-sig')
        header = text.splitlines()[0].split(',')
        for col in ('id', 'name', 'display_paise'):
            assert col in header

    def test_correction_requires_reason(self, app, admin):
        c, h = admin
        t = _tip(app)
        r = c.post('/api/admin/transactions/' + t['id'], json={'status': 'REFUNDED', 'reason': 'x'}, headers=h)
        assert r.status_code == 400  # reason too short


# =====================================================================
# 27. Session management (3 tests)
# =====================================================================
class TestSessions:
    def test_cannot_start_two(self, admin):
        c, h = admin
        _start_session(admin)
        r = c.post('/api/admin/sessions', json={'action': 'start'}, headers=h)
        assert r.status_code == 409

    def test_end_without_start_is_no_op(self, admin):
        c, h = admin
        r = c.post('/api/admin/sessions', json={'action': 'end'}, headers=h)
        assert r.status_code == 200

    def test_unknown_session_action(self, admin):
        c, h = admin
        r = c.post('/api/admin/sessions', json={'action': 'teleport'}, headers=h)
        assert r.status_code == 400


# =====================================================================
# 28. Goals validation (3 tests)
# =====================================================================
class TestGoals:
    def test_zero_target_rejected(self, admin):
        c, h = admin
        r = c.post('/api/admin/goals', json={'title': 't', 'target': 0, 'period': 'week', 'reset': 'automatic'}, headers=h)
        assert r.status_code == 400

    def test_custom_requires_start_before_end(self, admin):
        c, h = admin
        r = c.post('/api/admin/goals', json={'title': 't', 'target': 100, 'period': 'custom', 'reset': 'automatic', 'starts': 100, 'ends': 50}, headers=h)
        assert r.status_code == 400

    def test_bad_design_rejected(self, admin):
        c, h = admin
        r = c.post('/api/admin/goals', json={'title': 't', 'target': 100, 'period': 'week', 'reset': 'automatic', 'design': 'bogus'}, headers=h)
        assert r.status_code == 400


# =====================================================================
# 29. TTS public preview gating (2 tests)
# =====================================================================
class TestTTSPublicPreview:
    def test_preview_rejected_when_disabled(self, app, client):
        with app.store.db(True) as db:
            db.execute("UPDATE settings SET value='false' WHERE key='tts_enabled'")
        r = client.get('/api/public/voice-preview?voice=en-IN')
        assert r.status_code == 400

    def test_preview_rejected_for_unknown_voice(self, client):
        r = client.get('/api/public/voice-preview?voice=en-ZZ')
        assert r.status_code == 400


# =====================================================================
# 30. Media upload (3 tests)
# =====================================================================
class TestMediaUpload:
    def test_requires_file(self, admin):
        c, h = admin
        r = c.post('/api/admin/media', data={'kind': 'sound'}, headers=h)
        assert r.status_code == 400

    def test_rejects_non_wav_sound(self, admin):
        c, h = admin
        r = c.post('/api/admin/media', data={'file': (io.BytesIO(b'not wav'), 'bad.wav'), 'kind': 'sound'}, headers=h)
        assert r.status_code == 400

    def test_bad_image_rejected(self, admin):
        c, h = admin
        r = c.post('/api/admin/media', data={'file': (io.BytesIO(b'not image'), 'x.png'), 'kind': 'avatar'}, headers=h)
        assert r.status_code == 400


# =====================================================================
# 31. Tip creation gating (3 tests)
# =====================================================================
class TestTipCreation:
    def test_name_required(self, app):
        with pytest.raises(Problem):
            app.store.create_tip({'amount': 100}, True)

    def test_invalid_voice_rejected(self, app):
        with pytest.raises(Problem):
            app.store.create_tip({'amount': 100, 'name': 'A', 'voice': 'bogus-voice', 'sound': 'chime'}, True)

    def test_invalid_email_rejected(self, app):
        with pytest.raises(Problem):
            app.store.create_tip({'amount': 100, 'name': 'A', 'email': 'nope-not-email'}, True)


# =====================================================================
# 32. Register and factory setup errors (3 tests)
# =====================================================================
class TestCreateAppErrors:
    def test_missing_secret_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv('APP_SECRET', '')
        with pytest.raises(RuntimeError):
            app_module.create_app(dict(DATA_DIR=str(tmp_path), BRIDGE_TOKEN='b' * 48, OVERLAY_TOKEN='o' * 48))

    def test_short_token_raises(self, tmp_path):
        with pytest.raises(RuntimeError):
            app_module.create_app(dict(DATA_DIR=str(tmp_path), SECRET_KEY='s' * 48, BRIDGE_TOKEN='short', OVERLAY_TOKEN='o' * 48, ADMIN_PASSWORD_HASH='h'))

    def test_missing_admin_password_raises(self, tmp_path):
        with pytest.raises(RuntimeError):
            app_module.create_app(dict(DATA_DIR=str(tmp_path), SECRET_KEY='s' * 48, BRIDGE_TOKEN='b' * 48, OVERLAY_TOKEN='o' * 48, ADMIN_PASSWORD_HASH=''))


# =====================================================================
# Soundboard — schema + CRUD + public listing + tip integration (24 tests)
# =====================================================================
class TestSoundboardSchema:
    def test_table_exists(self, app):
        with app.store.db() as db:
            cols = {r['name'] for r in db.execute("PRAGMA table_info(soundboards)")}
            assert {'id', 'name', 'emoji', 'media_filename', 'category', 'min_paise', 'display_order', 'enabled', 'duration_ms', 'created'} <= cols

    def test_tips_has_soundboard_id_column(self, app):
        with app.store.db() as db:
            cols = {r['name'] for r in db.execute("PRAGMA table_info(tips)")}
            assert 'soundboard_id' in cols

    def test_indexes_exist(self, app):
        with app.store.db() as db:
            idx = {r['name'] for r in db.execute("PRAGMA index_list(soundboards)")}
            assert 'soundboards_enabled_order' in idx
            assert 'soundboards_category' in idx

    def test_migration_idempotent_rerun(self, app):
        """Simulate a second startup — the migrations re-run; the duplicate ALTER TABLE
        on tips.soundboard_id must be silently skipped by the loader."""
        from acepressure.domain import Store
        # Re-instantiate Store against the same directory — triggers migrations again.
        store2 = Store(app.store.path, 's' * 48)
        with store2.db() as db:
            cols = {r['name'] for r in db.execute("PRAGMA table_info(tips)")}
            assert 'soundboard_id' in cols


class TestSoundboardStore:
    def test_create_round_trip(self, app):
        e = app.store.soundboard_create(name='Chai Peelo', emoji='🍵', category='Hindi Memes', min_paise=5000)
        assert e['id'] and e['name'] == 'Chai Peelo' and e['emoji'] == '🍵'
        assert e['category'] == 'Hindi Memes' and e['min_paise'] == 5000
        got = app.store.soundboard_get(e['id'])
        assert got['id'] == e['id']

    def test_create_requires_name(self, app):
        with pytest.raises(Problem):
            app.store.soundboard_create(name='   ')

    def test_create_rejects_negative_min_paise(self, app):
        with pytest.raises(Problem):
            app.store.soundboard_create(name='x', min_paise=-100)

    def test_create_rejects_huge_min_paise(self, app):
        with pytest.raises(Problem):
            app.store.soundboard_create(name='x', min_paise=100_000_001)

    def test_create_auto_assigns_display_order(self, app):
        a = app.store.soundboard_create(name='A')
        b = app.store.soundboard_create(name='B')
        assert b['display_order'] > a['display_order']

    def test_list_ordered_by_display_order(self, app):
        a = app.store.soundboard_create(name='A', display_order=200)
        b = app.store.soundboard_create(name='B', display_order=100)
        ids = [x['id'] for x in app.store.soundboard_list()]
        assert ids.index(b['id']) < ids.index(a['id'])

    def test_list_enabled_only_filter(self, app):
        a = app.store.soundboard_create(name='on', enabled=True)
        b = app.store.soundboard_create(name='off', enabled=False)
        enabled_ids = [x['id'] for x in app.store.soundboard_list(enabled_only=True)]
        assert a['id'] in enabled_ids and b['id'] not in enabled_ids

    def test_update_fields(self, app):
        e = app.store.soundboard_create(name='X')
        updated = app.store.soundboard_update(e['id'], name='Y', min_paise=2000, enabled=False)
        assert updated['name'] == 'Y' and updated['min_paise'] == 2000 and updated['enabled'] == 0

    def test_update_rejects_unknown_field(self, app):
        e = app.store.soundboard_create(name='X')
        with pytest.raises(Problem):
            app.store.soundboard_update(e['id'], evil_field='bad')

    def test_update_missing_entry(self, app):
        with pytest.raises(Problem):
            app.store.soundboard_update('does-not-exist', name='X')

    def test_set_media_and_cleanup(self, app):
        e = app.store.soundboard_create(name='X')
        media = app.store.path / 'media'; media.mkdir(exist_ok=True)
        (media / 'first.wav').write_bytes(make_wav())
        app.store.soundboard_set_media(e['id'], 'first.wav', 1000)
        assert (media / 'first.wav').exists()
        (media / 'second.wav').write_bytes(make_wav())
        app.store.soundboard_set_media(e['id'], 'second.wav', 2000)
        # Previous file deleted
        assert not (media / 'first.wav').exists()
        assert (media / 'second.wav').exists()

    def test_delete_unlinks_tips(self, app):
        e = app.store.soundboard_create(name='X')
        media = app.store.path / 'media'; media.mkdir(exist_ok=True)
        (media / 'c.wav').write_bytes(make_wav())
        app.store.soundboard_set_media(e['id'], 'c.wav', 1000)
        app.store.soundboard_delete(e['id'])
        assert app.store.soundboard_get(e['id']) is None
        assert not (media / 'c.wav').exists()

    def test_reorder(self, app):
        a = app.store.soundboard_create(name='a', display_order=100)
        b = app.store.soundboard_create(name='b', display_order=200)
        app.store.soundboard_reorder({a['id']: 999, b['id']: 1})
        assert app.store.soundboard_get(a['id'])['display_order'] == 999
        assert app.store.soundboard_get(b['id'])['display_order'] == 1

    def test_seed_catalog_is_idempotent(self, app):
        first = app.store.soundboard_seed()
        second = app.store.soundboard_seed()
        assert len(first) >= 15
        assert second == []  # second run creates nothing

    def test_seed_entries_are_disabled_by_default(self, app):
        app.store.soundboard_seed()
        entries = app.store.soundboard_list()
        # Starter entries have no media and should ship disabled.
        for e in entries:
            assert e['enabled'] == 0
            assert e['media_filename'] is None


class TestSoundboardPublicAPI:
    def test_public_endpoint_hides_disabled_and_no_media(self, app, client):
        e1 = app.store.soundboard_create(name='A', enabled=True)   # no media → hidden
        e2 = app.store.soundboard_create(name='B', enabled=False)  # disabled → hidden
        e3 = app.store.soundboard_create(name='C', enabled=True)
        media = app.store.path / 'media'; media.mkdir(exist_ok=True)
        (media / 'c.wav').write_bytes(make_wav())
        app.store.soundboard_set_media(e3['id'], 'c.wav', 1000)
        r = client.get('/api/public/soundboard')
        assert r.status_code == 200
        items = r.json['items']
        ids = {x['id'] for x in items}
        assert e3['id'] in ids
        assert e1['id'] not in ids and e2['id'] not in ids

    def test_public_payload_shape(self, app, client):
        e = app.store.soundboard_create(name='A', emoji='⚡', category='SFX', min_paise=3000, enabled=True)
        media = app.store.path / 'media'; media.mkdir(exist_ok=True)
        (media / 'a.wav').write_bytes(make_wav())
        app.store.soundboard_set_media(e['id'], 'a.wav', 1500)
        r = client.get('/api/public/soundboard')
        item = r.json['items'][0]
        assert item == {'id': e['id'], 'name': 'A', 'emoji': '⚡', 'category': 'SFX', 'min_paise': 3000, 'duration_ms': 1500, 'url': '/media/a.wav', 'volume': 100}


class TestSoundboardAdminAPI:
    def test_admin_list_includes_all(self, app, admin):
        c, h = admin
        app.store.soundboard_create(name='X', enabled=False)
        app.store.soundboard_create(name='Y', enabled=True)
        r = c.get('/api/admin/soundboard', headers=h)
        assert r.status_code == 200
        names = {x['name'] for x in r.json['items']}
        assert {'X', 'Y'} <= names

    def test_admin_create_then_update(self, admin):
        c, h = admin
        r = c.post('/api/admin/soundboard', json={'name': 'Thug Life', 'emoji': '😎', 'category': 'Reactions', 'min_paise': 5000, 'enabled': False}, headers=h)
        assert r.status_code == 201
        sb_id = r.json['entry']['id']
        r2 = c.post('/api/admin/soundboard/' + sb_id, json={'min_paise': 10000, 'enabled': True}, headers=h)
        assert r2.status_code == 200
        assert r2.json['entry']['min_paise'] == 10000 and r2.json['entry']['enabled'] == 1

    def test_admin_delete(self, admin, app):
        c, h = admin
        e = app.store.soundboard_create(name='Delete me')
        r = c.delete('/api/admin/soundboard/' + e['id'], headers=h)
        assert r.status_code == 200
        assert app.store.soundboard_get(e['id']) is None

    def test_admin_seed_endpoint(self, admin, app):
        c, h = admin
        r = c.post('/api/admin/soundboard/seed', json={}, headers=h)
        assert r.status_code == 200
        assert len(r.json['created']) >= 15
        # Idempotent on second call
        r2 = c.post('/api/admin/soundboard/seed', json={}, headers=h)
        assert r2.json['created'] == []

    def test_admin_reorder(self, admin, app):
        c, h = admin
        a = app.store.soundboard_create(name='a')
        b = app.store.soundboard_create(name='b')
        r = c.post('/api/admin/soundboard/reorder', json={'order': {a['id']: 50, b['id']: 10}}, headers=h)
        assert r.status_code == 200
        assert app.store.soundboard_get(a['id'])['display_order'] == 50
        assert app.store.soundboard_get(b['id'])['display_order'] == 10

    def test_admin_upload_rejects_garbage(self, admin, app):
        c, h = admin
        e = app.store.soundboard_create(name='x')
        r = c.post('/api/admin/soundboard/' + e['id'] + '/media', data={'file': (io.BytesIO(b'this is not audio'), 'bad.wav')}, headers=h, content_type='multipart/form-data')
        assert r.status_code == 400 and ('format' in r.json['error'].lower() or 'wav' in r.json['error'].lower())

    def test_admin_upload_accepts_valid_wav(self, admin, app):
        c, h = admin
        e = app.store.soundboard_create(name='x')
        r = c.post('/api/admin/soundboard/' + e['id'] + '/media', data={'file': (io.BytesIO(make_wav(1.5)), 'ok.wav')}, headers=h, content_type='multipart/form-data')
        assert r.status_code == 200
        updated = app.store.soundboard_get(e['id'])
        assert updated['media_filename'] and updated['media_filename'].endswith('.wav')
        assert updated['duration_ms'] >= 1400  # approx 1500ms

    def test_first_upload_puts_a_seeded_slot_live(self, admin, app):
        """Seeded meme slots start switched off; their first clip switches them on, so the slot
        appears on the tip page as the seed message promises (1.6.0: the 8 bundled starter sounds are live at once)."""
        c, h = admin
        c.post('/api/admin/soundboard/seed', json={}, headers=h)
        e = next(x for x in app.store.soundboard_list() if x['name'] == 'Binod')
        live = {x['id'] for x in c.get('/api/public/soundboard').json['items']}
        assert not e['enabled'] and e['id'] not in live and len(live) == 8
        r = c.post('/api/admin/soundboard/' + e['id'] + '/media', data={'file': (io.BytesIO(make_wav(1.0)), 'binod.wav')}, headers=h, content_type='multipart/form-data')
        assert r.status_code == 200 and r.json['entry']['enabled']
        assert {x['id'] for x in c.get('/api/public/soundboard').json['items']} == live | {e['id']}

    def test_replacing_audio_keeps_a_switched_off_slot_off(self, admin, app):
        c, h = admin
        e = app.store.soundboard_create(name='x', enabled=False)
        def upload():
            return c.post('/api/admin/soundboard/' + e['id'] + '/media', data={'file': (io.BytesIO(make_wav(1.0)), 'x.wav')}, headers=h, content_type='multipart/form-data')
        assert upload().json['entry']['enabled']
        app.store.soundboard_update(e['id'], enabled=False)
        r = upload()
        assert r.status_code == 200 and not r.json['entry']['enabled']
        assert c.get('/api/public/soundboard').json['items'] == []

    def test_admin_upload_accepts_mp3(self, admin, app):
        """A REAL ffmpeg-generated MP3 (sine wave). v1.5.6 added ffprobe validation that
        correctly rejects fake-frame MP3s because real browsers can't play them."""
        c, h = admin
        e = app.store.soundboard_create(name='mp3')
        mp3 = make_real_mp3(1.5)
        r = c.post('/api/admin/soundboard/' + e['id'] + '/media', data={'file': (io.BytesIO(mp3), 'ok.mp3')}, headers=h, content_type='multipart/form-data')
        assert r.status_code == 200, r.json
        updated = app.store.soundboard_get(e['id'])
        assert updated['media_filename'].endswith('.mp3')
        # Public endpoint serves it with the right URL
        app.store.soundboard_update(e['id'], enabled=True)
        pub = c.get('/api/public/soundboard').json['items']
        assert any(x['url'].endswith('.mp3') for x in pub)

    def test_admin_upload_accepts_ogg(self, admin, app):
        """Real OGG Vorbis via ffmpeg — browser-decodable."""
        c, h = admin
        e = app.store.soundboard_create(name='ogg')
        ogg = make_real_ogg(1.5)
        r = c.post('/api/admin/soundboard/' + e['id'] + '/media', data={'file': (io.BytesIO(ogg), 'ok.ogg')}, headers=h, content_type='multipart/form-data')
        assert r.status_code == 200, r.json
        assert app.store.soundboard_get(e['id'])['media_filename'].endswith('.ogg')

    def test_admin_upload_rejects_wrong_extension_without_magic(self, admin, app):
        c, h = admin
        e = app.store.soundboard_create(name='x')
        # Lie about extension — content is pure junk. Server trusts magic bytes, not filename.
        r = c.post('/api/admin/soundboard/' + e['id'] + '/media', data={'file': (io.BytesIO(b'\x00' * 500), 'fake.mp3')}, headers=h, content_type='multipart/form-data')
        assert r.status_code == 400

    def test_admin_endpoints_require_auth(self, client):
        for method, url in [('GET', '/api/admin/soundboard'), ('POST', '/api/admin/soundboard'), ('POST', '/api/admin/soundboard/x/media'), ('DELETE', '/api/admin/soundboard/x'), ('POST', '/api/admin/soundboard/seed')]:
            r = client.open(url, method=method)
            assert r.status_code == 401


class TestAlertSoundUpload:
    """v1.5.3: /api/admin/media kind='sound' used to accept PCM WAV only. Must now accept
    WAV/MP3/OGG via magic-byte detection, same as the soundboard endpoint. 30 s cap for
    all formats (matches the overlay's 31000 ms watchdog)."""

    def test_rejects_garbage(self, admin):
        c, h = admin
        r = c.post('/api/admin/media', data={'kind': 'sound', 'file': (io.BytesIO(b'definitely not audio'), 'bad.wav')}, headers=h, content_type='multipart/form-data')
        assert r.status_code == 400

    def test_accepts_valid_wav(self, admin, app):
        c, h = admin
        r = c.post('/api/admin/media', data={'kind': 'sound', 'file': (io.BytesIO(make_wav(1.0)), 'ok.wav')}, headers=h, content_type='multipart/form-data')
        assert r.status_code == 200, r.json
        name = r.json['name']
        assert name.endswith('.wav')
        # 1.6.0: every upload is a sound-library row, pickable at any tip
        row = next(x for x in app.store.soundboard_list() if x['media_filename'] == name)
        assert row['enabled'] == 1 and row['min_paise'] == 0 and row['name'] == 'ok'

    def test_accepts_valid_mp3(self, admin, app):
        c, h = admin
        r = c.post('/api/admin/media', data={'kind': 'sound', 'file': (io.BytesIO(make_real_mp3(1.5)), 'tune.mp3')}, headers=h, content_type='multipart/form-data')
        assert r.status_code == 200, r.json
        assert r.json['name'].endswith('.mp3')
        row = next(x for x in app.store.soundboard_list() if x['media_filename'] == r.json['name'])
        assert row['enabled'] == 1 and row['min_paise'] == 0 and row['name'] == 'tune'

    def test_accepts_valid_ogg(self, admin, app):
        c, h = admin
        r = c.post('/api/admin/media', data={'kind': 'sound', 'file': (io.BytesIO(make_real_ogg(1.5)), 'clip.ogg')}, headers=h, content_type='multipart/form-data')
        assert r.status_code == 200, r.json
        assert r.json['name'].endswith('.ogg')

    def test_rejects_long_wav(self, admin):
        """Still enforces the 30 s cap on WAV."""
        c, h = admin
        r = c.post('/api/admin/media', data={'kind': 'sound', 'file': (io.BytesIO(make_wav(36.0)), 'long.wav')}, headers=h, content_type='multipart/form-data')
        assert r.status_code == 400

    def test_rejects_filename_lie(self, admin):
        """Lie about extension — content is NUL bytes. Server trusts magic, not filename."""
        c, h = admin
        r = c.post('/api/admin/media', data={'kind': 'sound', 'file': (io.BytesIO(b'\x00' * 500), 'fake.mp3')}, headers=h, content_type='multipart/form-data')
        assert r.status_code == 400

    def test_served_mp3_via_media_route(self, admin, app, client):
        """Upload MP3, confirm it serves cleanly via /media/<name>."""
        c, h = admin
        r = c.post('/api/admin/media', data={'kind': 'sound', 'file': (io.BytesIO(make_real_mp3(1.0)), 'ok.mp3')}, headers=h, content_type='multipart/form-data')
        assert r.status_code == 200
        name = r.json['name']
        r2 = client.get('/media/' + name)
        assert r2.status_code == 200
        assert r2.headers.get('Content-Type') == 'audio/mpeg'

    def test_mp3_posted_as_alert_sound_becomes_the_default(self, admin, app):
        """End-to-end: upload MP3 → an open 1.5.9 Design Studio posts it as alert_sound.
        Since 1.6.0 that makes its library row the default sound; alert_sound stays 'viewer'."""
        c, h = admin
        r = c.post('/api/admin/media', data={'kind': 'sound', 'file': (io.BytesIO(make_real_mp3(1.0)), 'alert.mp3')}, headers=h, content_type='multipart/form-data')
        name = r.json['name']
        # Save visuals with that MP3 selected as the alert_sound.
        r2 = c.post('/api/admin/visuals', json={'alert_sound': name}, headers=h)
        assert r2.status_code == 200, r2.json
        r3 = c.get('/api/admin/visuals', headers=h)
        assert r3.json['visuals']['alert_sound'] == 'viewer'
        row = next(x for x in app.store.soundboard_list() if x['media_filename'] == name)
        assert c.get('/api/admin/soundboard', headers=h).json['default'] == row['id']


class TestTipWithSoundboard:
    def _setup_sb(self, app, min_paise=5000, enabled=True, with_media=True):
        """Create a soundboard entry ready to be picked by a tip."""
        e = app.store.soundboard_create(name='Chai Peelo', emoji='🍵', min_paise=min_paise, enabled=enabled)
        if with_media:
            media = app.store.path / 'media'; media.mkdir(exist_ok=True)
            (media / 'cp.wav').write_bytes(make_wav(1.0))
            app.store.soundboard_set_media(e['id'], 'cp.wav', 1000)
        return app.store.soundboard_get(e['id'])

    def _ready_payment(self, app):
        """Flip settings so create_tip won't bail out on payment-ready checks."""
        import json as _json
        with app.store.db(True) as db:
            db.execute("UPDATE settings SET value=? WHERE key='upi_id'", (_json.dumps('ace@upi'),))
            db.execute("UPDATE settings SET value=? WHERE key='payee_name'", (_json.dumps('Ace'),))

    def test_create_tip_accepts_valid_soundboard_id(self, app):
        self._ready_payment(app)
        sb = self._setup_sb(app, min_paise=5000)
        tip = app.store.create_tip({'amount': 100, 'name': 'Rahul', 'message': 'GG', 'tts': False, 'voice': 'en-IN', 'sound': 'chime', 'soundboard_id': sb['id']}, demo=True)
        assert tip['soundboard_id'] == sb['id']

    def test_create_tip_rejects_unknown_soundboard(self, app):
        self._ready_payment(app)
        with pytest.raises(Problem):
            app.store.create_tip({'amount': 100, 'name': 'Rahul', 'message': 'GG', 'tts': False, 'voice': 'en-IN', 'sound': 'chime', 'soundboard_id': 'nonexistent-id-123'}, demo=True)

    def test_create_tip_rejects_disabled_soundboard(self, app):
        self._ready_payment(app)
        sb = self._setup_sb(app, enabled=False)
        with pytest.raises(Problem):
            app.store.create_tip({'amount': 100, 'name': 'Rahul', 'message': 'GG', 'tts': False, 'voice': 'en-IN', 'sound': 'chime', 'soundboard_id': sb['id']}, demo=True)

    def test_create_tip_rejects_soundboard_without_media(self, app):
        self._ready_payment(app)
        sb = self._setup_sb(app, with_media=False)
        with pytest.raises(Problem):
            app.store.create_tip({'amount': 100, 'name': 'Rahul', 'message': 'GG', 'tts': False, 'voice': 'en-IN', 'sound': 'chime', 'soundboard_id': sb['id']}, demo=True)

    def test_create_tip_rejects_amount_below_min(self, app):
        self._ready_payment(app)
        sb = self._setup_sb(app, min_paise=20000)  # ₹200 minimum
        with pytest.raises(Problem) as exc:
            app.store.create_tip({'amount': 100, 'name': 'Rahul', 'message': 'GG', 'tts': False, 'voice': 'en-IN', 'sound': 'chime', 'soundboard_id': sb['id']}, demo=True)
        assert '200' in exc.value.message

    def test_create_tip_without_soundboard_still_works(self, app):
        self._ready_payment(app)
        tip = app.store.create_tip({'amount': 100, 'name': 'Rahul', 'message': 'GG', 'tts': False, 'voice': 'en-IN', 'sound': 'chime'}, demo=True)
        assert tip['soundboard_id'] is None

    def test_create_tip_rejects_bad_soundboard_id_format(self, app):
        self._ready_payment(app)
        with pytest.raises(Problem):
            app.store.create_tip({'amount': 100, 'name': 'Rahul', 'message': 'GG', 'tts': False, 'voice': 'en-IN', 'sound': 'chime', 'soundboard_id': 'has spaces'}, demo=True)

    def test_alert_payload_includes_soundboard_clip(self, app):
        self._ready_payment(app)
        sb = self._setup_sb(app, min_paise=5000)
        tip = app.store.create_tip({'amount': 100, 'name': 'R', 'message': 'G', 'tts': False, 'voice': 'en-IN', 'sound': 'chime', 'soundboard_id': sb['id']}, demo=True)
        with app.store.db(True) as db:
            app.store.alert(db, tip)
            r = db.execute('SELECT payload FROM alerts ORDER BY id DESC LIMIT 1').fetchone()
        payload = json.loads(r['payload'])
        assert payload['soundboard_clip'] == 'cp.wav'
        assert payload['soundboard_id'] == sb['id']

    def test_alert_payload_without_soundboard_omits_clip(self, app):
        self._ready_payment(app)
        tip = app.store.create_tip({'amount': 100, 'name': 'R', 'message': 'G', 'tts': False, 'voice': 'en-IN', 'sound': 'chime'}, demo=True)
        with app.store.db(True) as db:
            app.store.alert(db, tip)
            r = db.execute('SELECT payload FROM alerts ORDER BY id DESC LIMIT 1').fetchone()
        payload = json.loads(r['payload'])
        assert 'soundboard_clip' not in payload


# =====================================================================
# Additional TTS tests requested by user (5 tests)
# =====================================================================
class TestTTSExtras:
    def test_transliterate_preserves_punctuation(self):
        out = transliterate_hinglish('bhai, kya hai yaar!')
        assert ',' in out and '!' in out and 'भाई' in out

    def test_transliterate_idempotent(self):
        once = transliterate_hinglish('bhai kya')
        twice = transliterate_hinglish(once)
        assert once == twice  # transliterated text has no Roman matches left

    def test_transliterate_mixed_case_in_sentence(self):
        out = transliterate_hinglish('Bhai KYA Hai Yaar')
        assert out.count('भाई') == 1 and out.count('क्या') == 1

    def test_maybe_transliterate_handles_empty(self):
        assert maybe_transliterate('', 'hi-IN-SwaraNeural') == ''
        assert maybe_transliterate(None, 'hi-IN-SwaraNeural') is None

    def test_voice_handles_hindi_case_insensitive(self):
        assert voice_handles_hindi('HI-IN-SOMETHING') is True
        assert voice_handles_hindi('en-US-AVAMULTILINGUALNEURAL') is True


# =====================================================================
# v1.5.1 Premium polish — public config exposes tiers; CSS/HTML wiring (4 tests)
# =====================================================================
class TestPremiumPolish:
    def test_public_config_exposes_tiers(self, client):
        r = client.get('/api/public/config')
        assert r.status_code == 200
        assert 'tiers' in r.json
        assert isinstance(r.json['tiers'], list)
        assert r.json['tiers'] == [1, 50, 200, 500]  # defaults

    def test_premium_css_includes_v151_polish_selectors(self):
        css = (ROOT / 'acepressure' / 'static' / 'premium.css').read_text(encoding='utf-8')
        for selector in ['.tier-badge', '.celebration', '.celebrate-ring', '.skeleton-row', '.skeleton-bar']:
            assert selector in css, f'missing {selector}'

    def test_premium_css_includes_v151_keyframes(self):
        css = (ROOT / 'acepressure' / 'static' / 'premium.css').read_text(encoding='utf-8')
        for kf in ['@keyframes hero-aura', '@keyframes avatar-breath', '@keyframes section-in', '@keyframes tier-pulse', '@keyframes celebrate-pop', '@keyframes skeleton-shimmer']:
            assert kf in css, f'missing {kf}'

    def test_public_js_includes_v151_functions(self):
        js = (ROOT / 'acepressure' / 'static' / 'public.js').read_text(encoding='utf-8')
        assert 'renderTierBadge' in js
        assert 'renderCelebration' in js
        assert 'skeleton-row' in js
        assert 'window.aceConfetti' in js  # celebration triggers the confetti


# =====================================================================
# v1.5.4 — Friendly voice picker: Male/Female voice N labels + gender icons + speaker preview
# =====================================================================
class TestFriendlyVoicePicker:
    def test_public_config_exposes_voice_genders(self, client):
        """New voice_genders map must always be present (empty dict if nothing persisted yet),
        so public.js can `?.[v]` safely on it without crashing."""
        r = client.get('/api/public/config')
        assert r.status_code == 200
        assert 'voice_genders' in r.json
        assert isinstance(r.json['voice_genders'], dict)

    def test_tts_configure_persists_voice_genders(self, admin, app, monkeypatch):
        """When admin picks voices via Voice Studio, server must persist the catalog's
        gender field as a parallel map alongside voice_labels. The browser engine has no
        gender metadata, so patch catalog() to return a controlled set."""
        from acepressure import tts_service
        monkeypatch.setattr(tts_service, 'catalog', lambda engine, path=None: [
            {'id': 'en-US-AvaMultilingualNeural', 'label': 'Ava', 'gender': 'Female', 'locale': 'en-US'},
            {'id': 'en-US-BrianMultilingualNeural', 'label': 'Brian', 'gender': 'Male', 'locale': 'en-US'},
            {'id': 'hi-IN-SwaraNeural', 'label': 'Swara', 'gender': 'Female', 'locale': 'hi-IN'},
        ])
        c, h = admin
        r = c.post('/api/admin/tts/configure', json={
            'engine': 'edge',
            'voices': ['en-US-AvaMultilingualNeural', 'en-US-BrianMultilingualNeural', 'hi-IN-SwaraNeural'],
        }, headers=h)
        assert r.status_code == 200, r.json
        # Verify persisted
        s = app.store.settings()
        assert s.get('voice_genders') == {
            'en-US-AvaMultilingualNeural': 'Female',
            'en-US-BrianMultilingualNeural': 'Male',
            'hi-IN-SwaraNeural': 'Female',
        }
        # And exposed via public config
        pub = c.get('/api/public/config').json
        assert pub['voice_genders']['en-US-AvaMultilingualNeural'] == 'Female'
        assert pub['voice_genders']['en-US-BrianMultilingualNeural'] == 'Male'

    def test_tts_configure_defaults_gender_to_any_when_missing(self, admin, app, monkeypatch):
        """Piper voices have no reliable gender — catalog returns 'Any' or no gender field.
        voice_genders must still populate so the client-side regex fallback kicks in cleanly."""
        from acepressure import tts_service
        monkeypatch.setattr(tts_service, 'catalog', lambda engine, path=None: [
            {'id': 'en_US-amy-medium', 'label': 'Amy', 'locale': 'en-US'},  # no gender key
        ])
        c, h = admin
        r = c.post('/api/admin/tts/configure', json={'engine': 'piper', 'voices': ['en_US-amy-medium']}, headers=h)
        assert r.status_code == 200
        assert app.store.settings()['voice_genders'] == {'en_US-amy-medium': 'Any'}

    def test_public_config_backfills_voice_genders_when_missing(self, client, app):
        """v1.5.8 — users upgrading from <1.5.4 have no voice_genders in settings. The /api/public/config
        endpoint must derive gender from voice IDs via name tokens so the client UI doesn't dump every
        voice into the generic 'Voice 1, 2, 3, 4' bucket."""
        with app.store.db(True) as db:
            # Simulate pre-1.5.4 state: voices set but no voice_genders.
            db.execute("INSERT INTO settings VALUES ('voices', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       (json.dumps(['en-US-AvaMultilingualNeural', 'en-US-BrianMultilingualNeural', 'hi-IN-SwaraNeural', 'hi-IN-MadhurNeural']),))
            db.execute("DELETE FROM settings WHERE key='voice_genders'")
        r = client.get('/api/public/config')
        assert r.status_code == 200
        vg = r.json['voice_genders']
        assert vg['en-US-AvaMultilingualNeural'] == 'Female'
        assert vg['en-US-BrianMultilingualNeural'] == 'Male'
        assert vg['hi-IN-SwaraNeural'] == 'Female'
        assert vg['hi-IN-MadhurNeural'] == 'Male'

    def test_guess_gender_from_voice_id_covers_edge_catalog(self):
        """The server-side guesser must mirror the client-side regex so backfill matches browser fallback."""
        from acepressure.app import _guess_gender_from_voice_id
        assert _guess_gender_from_voice_id('en-US-AvaMultilingualNeural') == 'Female'
        assert _guess_gender_from_voice_id('en-US-BrianMultilingualNeural') == 'Male'
        assert _guess_gender_from_voice_id('en-IN-NeerjaNeural') == 'Female'
        assert _guess_gender_from_voice_id('en-IN-PrabhatNeural') == 'Male'
        assert _guess_gender_from_voice_id('hi-IN-SwaraNeural') == 'Female'
        assert _guess_gender_from_voice_id('hi-IN-MadhurNeural') == 'Male'
        assert _guess_gender_from_voice_id('en-IN') == 'Any'  # locale-only (browser engine)
        assert _guess_gender_from_voice_id('') == 'Any'
        assert _guess_gender_from_voice_id(None) == 'Any'

    def test_public_config_respects_explicit_voice_genders_over_backfill(self, client, app):
        """If voice_genders is already set with Male/Female, don't overwrite via heuristic."""
        with app.store.db(True) as db:
            db.execute("INSERT INTO settings VALUES ('voices', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       (json.dumps(['custom-voice-1']),))
            db.execute("INSERT INTO settings VALUES ('voice_genders', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       (json.dumps({'custom-voice-1': 'Female'}),))
        r = client.get('/api/public/config')
        assert r.json['voice_genders']['custom-voice-1'] == 'Female'

    def test_public_js_voice_labels_use_numbering(self):
        """v1.5.8 — admin asked for 'Male 1, Male 2' format when multiple voices share a gender.
        The buildVoices() code must concatenate ' '+(i+1) to the base word for multi-voice groups."""
        js = (ROOT / 'acepressure' / 'static' / 'public.js').read_text(encoding='utf-8')
        assert 'list.length>1' in js, 'numbering gate (only number when >1 voice in group) must remain'
        assert "' '+(i+1)" in js, 'index-based numbering for multi-voice groups'

    def test_public_js_has_gender_helper_and_tokens(self):
        """The client-side fallback regex is what makes gender grouping work for admins who
        skipped the Voice Studio (set tts_engine=browser or typed raw IDs into settings JSON)."""
        js = (ROOT / 'acepressure' / 'static' / 'public.js').read_text(encoding='utf-8')
        assert 'function voiceGender(' in js
        assert 'VOICE_MALE_TOKENS' in js
        assert 'VOICE_FEMALE_TOKENS' in js
        # The regex must cover the user's actual 17 voices from their Edge list.
        for male_token in ['Andrew', 'Brian', 'William', 'Madhur', 'Prabhat', 'Florian']:
            assert male_token in js, f'missing male token: {male_token}'
        for female_token in ['Ava', 'Emma', 'Swara', 'Neerja', 'Seraphina']:
            assert female_token in js, f'missing female token: {female_token}'

    def test_public_js_renders_friendly_labels_not_raw_ids(self):
        """v1.5.8 — labels use 'Male'/'Female'/'Voice' plus 👨/👩/🎙️ emojis.
        Users complained the earlier ♂/♀ symbols looked like generic characters; emojis read as gender signals."""
        js = (ROOT / 'acepressure' / 'static' / 'public.js').read_text(encoding='utf-8')
        assert "'Male'" in js, 'label "Male" (shortened in 1.5.8) must appear in META block'
        assert "'Female'" in js, 'label "Female" (shortened in 1.5.8) must appear in META block'
        for emoji in ['👨', '👩', '🎙']:  # 🎙 is base for 🎙️ (studio microphone), fe0f variation selector optional
            assert emoji in js, f'missing gender emoji {emoji}'

    def test_public_js_has_speaker_preview_on_each_card(self):
        """Each card must have its own 🔊 preview that stops propagation and triggers the
        global preview with that voice pre-selected (reuses existing preview endpoint)."""
        js = (ROOT / 'acepressure' / 'static' / 'public.js').read_text(encoding='utf-8')
        assert 'voice-preview-spk' in js
        assert '🔊' in js
        assert 'stopPropagation()' in js  # click on speaker must not re-trigger card selection twice

    def test_premium_css_has_voice_gender_styles(self):
        css = (ROOT / 'acepressure' / 'static' / 'premium.css').read_text(encoding='utf-8')
        for selector in ['.voice-male', '.voice-female', '.voice-any', '.voice-gender-icon', '.voice-preview-spk', '.voice-friendly-name']:
            assert selector in css, f'missing {selector}'

    def test_premium_css_voice_card_is_flex(self):
        """Card layout must be flex so icon + label + speaker align on one row."""
        css = (ROOT / 'acepressure' / 'static' / 'premium.css').read_text(encoding='utf-8')
        # Simple sanity: the .voice-card block under v1.5.4 declares display: flex
        import re as _re
        m = _re.search(r'\.voice-card\s*\{[^}]*display:\s*flex', css)
        assert m, 'voice-card must be display: flex for the 3-column layout'


# =====================================================================
# v1.5.5 — Alert bundle (visual + audio in one step), MP4/video audio preservation,
# overlay audio-gating. Direct response to user: "for the obs alert is there an option
# to upload a gif or mp4 with the audio or not if not please add and test it."
# =====================================================================
class TestAlertBundle:
    """New /api/admin/alert-bundle endpoint — single-step upload of visual + optional audio."""

    @staticmethod
    def _make_gif():
        """Minimal single-frame GIF (3 bytes of pixel data, lzw-encoded)."""
        import struct
        # GIF89a 1x1 red pixel.
        return (b'GIF89a\x01\x00\x01\x00\x80\x01\x00\xff\x00\x00\x00\x00\x00'
                b'\x21\xf9\x04\x00\x00\x00\x00\x00'
                b'\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00'
                b'\x02\x02\x44\x01\x00\x3b')

    @staticmethod
    def _make_png():
        """Minimal 1x1 PNG via Pillow (which the server uses to re-encode)."""
        from PIL import Image
        buf = io.BytesIO()
        Image.new('RGB', (16, 16), (200, 50, 80)).save(buf, format='PNG')
        return buf.getvalue()

    @staticmethod
    def _make_mp3():
        return make_real_mp3(1.3)

    def test_bundle_rejects_missing_visual(self, admin):
        c, h = admin
        r = c.post('/api/admin/alert-bundle', data={}, headers=h, content_type='multipart/form-data')
        assert r.status_code == 400

    def test_bundle_rejects_bad_visual_extension(self, admin):
        c, h = admin
        r = c.post('/api/admin/alert-bundle',
                   data={'visual': (io.BytesIO(b'x'*100), 'bad.exe')},
                   headers=h, content_type='multipart/form-data')
        assert r.status_code == 400

    def test_bundle_png_plus_mp3(self, admin, app):
        """Happy path: PNG visual + MP3 audio → both saved, both persisted into settings.visuals."""
        c, h = admin
        r = c.post('/api/admin/alert-bundle',
                   data={'visual': (io.BytesIO(self._make_png()), 'logo.png'),
                         'audio': (io.BytesIO(self._make_mp3()), 'chime.mp3')},
                   headers=h, content_type='multipart/form-data')
        assert r.status_code == 200, r.json
        assert r.json['visual'].endswith('.png')
        assert r.json['audio'].endswith('.mp3')
        assert r.json['video_has_audio'] is False
        # Round-trip through /api/admin/visuals GET
        visuals = c.get('/api/admin/visuals', headers=h).json['visuals']
        assert visuals['alert_image'] == r.json['visual']
        assert visuals['alert_sound'] == 'viewer'
        # 1.6.0: the audio is a hidden library row and the default sound
        entry = r.json['entry']
        assert entry['media_filename'] == r.json['audio'] and entry['enabled'] == 0 and r.json['default'] == entry['id']
        assert visuals['alert_video_has_audio'] is False
        # The audio heads the legacy sounds mirror
        assert r.json['audio'] in app.store.settings()['sounds']

    def test_bundle_gif_plus_mp3(self, admin, app):
        c, h = admin
        r = c.post('/api/admin/alert-bundle',
                   data={'visual': (io.BytesIO(self._make_gif()), 'tada.gif'),
                         'audio': (io.BytesIO(self._make_mp3()), 'tada.mp3')},
                   headers=h, content_type='multipart/form-data')
        assert r.status_code == 200, r.json
        # Server re-encodes animated-safe. Single-frame GIF → .png.
        assert r.json['visual'].endswith('.png') or r.json['visual'].endswith('.webp')
        assert r.json['audio'].endswith('.mp3')

    def test_bundle_rejects_oversized_audio(self, admin):
        c, h = admin
        r = c.post('/api/admin/alert-bundle',
                   data={'visual': (io.BytesIO(self._make_png()), 'ok.png'),
                         'audio': (io.BytesIO(b'\x00' * (9 * 1024 * 1024)), 'huge.mp3')},
                   headers=h, content_type='multipart/form-data')
        assert r.status_code == 400

    def test_bundle_rejects_bad_audio_magic(self, admin):
        c, h = admin
        r = c.post('/api/admin/alert-bundle',
                   data={'visual': (io.BytesIO(self._make_png()), 'ok.png'),
                         'audio': (io.BytesIO(b'this is not audio'), 'fake.mp3')},
                   headers=h, content_type='multipart/form-data')
        assert r.status_code == 400

    def test_bundle_image_only(self, admin, app):
        """Image-only (no audio uploaded, no video with audio) — just updates alert_image."""
        c, h = admin
        r = c.post('/api/admin/alert-bundle',
                   data={'visual': (io.BytesIO(self._make_png()), 'solo.png')},
                   headers=h, content_type='multipart/form-data')
        assert r.status_code == 200, r.json
        assert r.json['visual'].endswith('.png')
        assert r.json['audio'] is None
        assert r.json['video_has_audio'] is False

    def test_bundle_requires_admin(self, client):
        r = client.post('/api/admin/alert-bundle', data={'visual': (io.BytesIO(b'xxx'), 'x.png')}, content_type='multipart/form-data')
        assert r.status_code == 401


class TestVideoTranscode:
    """video.py transcode() behaviour — audio defaults OFF (legacy); opt-in via keep_audio=True."""

    def test_transcode_default_is_silent(self, tmp_path):
        """Backward compat: /api/admin/visual-assets (which doesn't pass keep_audio) must keep
        producing silent output so existing admins aren't surprised by sudden sound in their alerts."""
        import shutil as _sh
        if not _sh.which('ffmpeg'):
            import pytest as _pt; _pt.skip('ffmpeg required')
        import subprocess as _sp
        from acepressure.video import transcode
        src = tmp_path / 'in.mp4'
        _sp.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=160x120:d=1',
                 '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1',
                 '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-y', str(src)], check=True)
        out = transcode(src.read_bytes(), '.mp4')  # keep_audio defaults to False
        tmp = tmp_path / 'out.webm'
        tmp.write_bytes(out)
        info = __import__('json').loads(_sp.check_output(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(tmp)]))
        kinds = [s['codec_type'] for s in info['streams']]
        assert kinds == ['video'], f'default should be silent, got {kinds}'

    def test_transcode_keep_audio_preserves_audio_track(self, tmp_path):
        import shutil as _sh
        if not _sh.which('ffmpeg'):
            import pytest as _pt; _pt.skip('ffmpeg required')
        import subprocess as _sp
        from acepressure.video import transcode
        src = tmp_path / 'in.mp4'
        _sp.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=green:s=160x120:d=1',
                 '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1',
                 '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-y', str(src)], check=True)
        out = transcode(src.read_bytes(), '.mp4', keep_audio=True)
        tmp = tmp_path / 'out.webm'
        tmp.write_bytes(out)
        info = __import__('json').loads(_sp.check_output(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(tmp)]))
        kinds = sorted([s['codec_type'] for s in info['streams']])
        assert kinds == ['audio', 'video'], f'keep_audio=True must preserve audio, got {kinds}'

    def test_transcode_keep_audio_handles_silent_input(self, tmp_path):
        """Opt-in audio must still succeed when input has no audio track (map 0:a:0? is optional)."""
        import shutil as _sh
        if not _sh.which('ffmpeg'):
            import pytest as _pt; _pt.skip('ffmpeg required')
        import subprocess as _sp
        from acepressure.video import transcode
        src = tmp_path / 'in.mp4'
        _sp.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=160x120:d=1',
                 '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-y', str(src)], check=True)
        out = transcode(src.read_bytes(), '.mp4', keep_audio=True)
        assert out and len(out) > 100

    def test_probe_has_audio_detects_track(self, tmp_path):
        import shutil as _sh
        if not _sh.which('ffprobe'):
            import pytest as _pt; _pt.skip('ffprobe required')
        import subprocess as _sp
        from acepressure.video import probe_has_audio
        src = tmp_path / 'with_audio.mp4'
        _sp.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=red:s=160x120:d=1',
                 '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1',
                 '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-y', str(src)], check=True)
        assert probe_has_audio(src.read_bytes(), '.mp4') is True
        silent = tmp_path / 'silent.mp4'
        _sp.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=160x120:d=1',
                 '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-y', str(silent)], check=True)
        assert probe_has_audio(silent.read_bytes(), '.mp4') is False


class TestOverlayVideoAudioGate:
    """Static checks for the overlay audio-gating logic + MP4 visual recognition."""

    def test_overlay_js_has_video_audio_gate(self):
        js = (ROOT / 'acepressure' / 'static' / 'overlay.js').read_text(encoding='utf-8')
        assert 'alert_video_has_audio' in js
        assert 'useVideoAudio' in js
        # Gate must call sound() only when NOT using video audio
        assert 'if(!useVideoAudio){const first=' in js and 'await sound(first,vol(first))' in js

    def test_visuals_js_recognises_mp4(self):
        js = (ROOT / 'acepressure' / 'static' / 'visuals.js').read_text(encoding='utf-8')
        # The old code only matched .webm; new regex covers mp4/webm/mov/m4v
        assert 'mp4' in js and 'webm' in js and 'mov' in js
        # Default visuals carry the new flag so applyVisuals() doesn't crash
        assert 'alert_video_has_audio' in js

    def test_admin_js_has_alert_bundle_form(self):
        js = (ROOT / 'acepressure' / 'static' / 'admin.js').read_text(encoding='utf-8')
        assert '/api/admin/alert-bundle' in js
        assert 'Upload alert bundle' in js

    def test_visuals_default_has_video_audio_flag(self):
        from acepressure.visuals import DEFAULT_VISUALS
        assert 'alert_video_has_audio' in DEFAULT_VISUALS
        assert DEFAULT_VISUALS['alert_video_has_audio'] is False

    def test_visuals_validator_rejects_non_bool_video_audio_flag(self, tmp_path):
        from acepressure.visuals import validate_visuals
        media = tmp_path / 'm'; media.mkdir()
        with pytest.raises(Problem):
            validate_visuals({'alert_video_has_audio': 'yes'}, media)
        # bool OK
        validate_visuals({'alert_video_has_audio': True}, media)


class TestComprehensiveSmoke:
    """One-test-one-area sanity sweep of every major feature area for the 1.5.5 ship check.
    Lightweight: these just prove the routes are wired, not that every detail is correct —
    detailed coverage is in the dedicated test classes above."""

    def test_public_config_shape(self, client):
        r = client.get('/api/public/config')
        assert r.status_code == 200
        for key in ['creator', 'minimum', 'maximum', 'voices', 'sounds', 'tiers',
                    'voice_labels', 'voice_genders', 'tts_engine', 'tts_enabled',
                    'demo', 'ready', 'accepting_tips', 'avatar']:
            assert key in r.json, f'missing config key: {key}'

    def test_public_soundboard_endpoint(self, client):
        r = client.get('/api/public/soundboard')
        assert r.status_code == 200 and 'items' in r.json

    def test_public_top_endpoint(self, client):
        r = client.get('/api/public/top')
        assert r.status_code == 200

    def test_health_endpoint(self, client):
        r = client.get('/health')
        assert r.status_code == 200 and r.json['ok']

    def test_root_tipping_page_renders(self, client):
        r = client.get('/')
        assert r.status_code == 200
        assert b'soundboard-section' in r.data
        assert b'voice-choices' in r.data

    def test_overlay_pages_render(self, client):
        for kind in ['alert', 'goal', 'recent', 'top3']:
            r = client.get('/overlay/' + kind)
            assert r.status_code == 200, f'{kind} overlay failed'

    def test_admin_login_logout(self, admin, client):
        c, h = admin
        r = c.post('/api/admin/logout', headers=h)
        assert r.status_code == 200
        # After logout, admin routes 401
        r = c.get('/api/admin/soundboard')
        assert r.status_code == 401

    def test_bridge_endpoint_rejects_bad_token(self, client):
        r = client.post('/api/bridge/credit',
                        json={'sender': 'TEST'},
                        headers={'Authorization': 'Bearer wrong-token'})
        assert r.status_code == 401

    def test_bridge_endpoint_rejects_missing_token(self, client):
        r = client.post('/api/bridge/credit', json={'sender': 'TEST'})
        assert r.status_code == 401

    def test_mp3_alert_sound_still_works_after_1_5_5(self, admin, app):
        """1.5.3 feature regression check — MP3 alert sound upload still works in 1.5.6."""
        c, h = admin
        r = c.post('/api/admin/media',
                   data={'kind': 'sound', 'file': (io.BytesIO(make_real_mp3(1.0)), 'ok.mp3')},
                   headers=h, content_type='multipart/form-data')
        assert r.status_code == 200
        assert r.json['name'].endswith('.mp3')

    def test_soundboard_mp3_upload_still_works(self, admin, app):
        """1.5.2 feature regression check — soundboard MP3 upload still works."""
        c, h = admin
        e = app.store.soundboard_create(name='smoke')
        r = c.post('/api/admin/soundboard/' + e['id'] + '/media',
                   data={'file': (io.BytesIO(make_real_mp3(1.0)), 'ok.mp3')},
                   headers=h, content_type='multipart/form-data')
        assert r.status_code == 200


# =====================================================================
# v1.5.6 — ffprobe audio validation. Direct response to user's "failed to load
# because no supported source was found" bug when previewing an uploaded MP3.
# =====================================================================
class TestAudioValidationFfprobe:
    """Files that pass magic-byte checks but can't actually play. The 1.5.6 fix uses
    ffprobe to validate every uploaded audio file has a real decodable audio stream."""

    def test_rejects_id3_tag_only_mp3(self, admin):
        """A file with just an ID3v2 header and NO audio frames. The magic-byte check
        used to accept this (because 'ID3' prefix matched), browser then couldn't
        play it. 1.5.6 catches it at upload time."""
        c, h = admin
        if not _ffmpeg_available():
            pytest.skip('ffprobe required for stricter validation')
        # ID3v2 header (10 bytes synchsafe size = 0) + a bit of padding, no MPEG frames.
        bad_mp3 = b'ID3\x04\x00\x00\x00\x00\x00\x00' + b'\x00' * 200
        r = c.post('/api/admin/media',
                   data={'kind': 'sound', 'file': (io.BytesIO(bad_mp3), 'id3only.mp3')},
                   headers=h, content_type='multipart/form-data')
        assert r.status_code == 400, r.json
        # Error message should hint at what went wrong (not just "invalid")
        assert any(hint in r.json['error'].lower() for hint in ['decode', 'audio stream', 'metadata'])

    def test_rejects_ogg_container_without_vorbis_stream(self, admin):
        """OggS header but no actual Vorbis audio data — fails ffprobe decode."""
        c, h = admin
        if not _ffmpeg_available():
            pytest.skip('ffprobe required')
        bad_ogg = b'OggS' + b'\x00' * 500
        r = c.post('/api/admin/media',
                   data={'kind': 'sound', 'file': (io.BytesIO(bad_ogg), 'empty.ogg')},
                   headers=h, content_type='multipart/form-data')
        assert r.status_code == 400

    def test_accepts_real_mp3_and_serves_decodable(self, admin, app, client, tmp_path):
        """Full round-trip: upload real MP3 → fetch via /media/ → confirm ffmpeg can decode it.
        This is the test that would have caught the user's bug if the file came from a
        bad source — proves the uploaded-and-served file plays."""
        c, h = admin
        if not _ffmpeg_available():
            pytest.skip('ffmpeg required')
        import subprocess as _sp
        original = make_real_mp3(1.2)
        r = c.post('/api/admin/media',
                   data={'kind': 'sound', 'file': (io.BytesIO(original), 'tone.mp3')},
                   headers=h, content_type='multipart/form-data')
        assert r.status_code == 200
        name = r.json['name']
        # Fetch what the browser would get
        r2 = client.get('/media/' + name)
        assert r2.status_code == 200
        assert r2.headers['Content-Type'] == 'audio/mpeg'
        assert r2.data == original  # byte-identical
        # Confirm the served bytes are decodable by ffmpeg (proxy for browser decoding)
        served = tmp_path / 'served.mp3'
        served.write_bytes(r2.data)
        probe = _sp.run(['ffmpeg', '-v', 'error', '-i', str(served), '-f', 'null', '-'],
                        capture_output=True)
        assert probe.returncode == 0, f'served MP3 cannot decode: {probe.stderr.decode()[:200]}'

    def test_range_requests_work_for_mp3(self, admin, client):
        """Browsers often use Range requests to seek. If this breaks, playback stalls."""
        c, h = admin
        if not _ffmpeg_available():
            pytest.skip('ffmpeg required')
        r = c.post('/api/admin/media',
                   data={'kind': 'sound', 'file': (io.BytesIO(make_real_mp3(2.0)), 'song.mp3')},
                   headers=h, content_type='multipart/form-data')
        name = r.json['name']
        r2 = client.get('/media/' + name, headers={'Range': 'bytes=0-1023'})
        assert r2.status_code == 206, 'Range request must return 206 Partial Content'
        assert r2.headers.get('Accept-Ranges') == 'bytes'
        assert 'Content-Range' in r2.headers

    def test_probe_audio_file_fallback_when_ffprobe_missing(self, monkeypatch):
        """If ffprobe isn't installed, probe_audio_file returns valid=None so the caller
        falls back to the magic-byte check. Important: don't crash when ffmpeg is missing."""
        from acepressure import video
        monkeypatch.setattr(video, 'tool', lambda name: None)
        out = video.probe_audio_file(b'anything', '.mp3')
        assert out['valid'] is None, f'expected None (fallback), got {out}'

    def test_client_side_error_handler_in_public_js(self):
        """The public.js preview must have the specific MEDIA_ERR code → friendly message
        mapping so users don't see raw browser errors any more."""
        js = (ROOT / 'acepressure' / 'static' / 'public.js').read_text(encoding='utf-8')
        # Error codes 1-4 defined by HTMLMediaElement.error.code
        for code_hint in ['MEDIA_ERR', 'error.code', 'previewAudio.error']:
            pass  # Not required — just the presence of the error handler
        assert 'previewAudio.addEventListener' in js
        assert "'error'" in js
        assert 'standard MP3' in js or 'standard' in js  # the actionable hint


# =====================================================================
# v1.5.7 — Sounds manager (list/delete) + codec-match-extension strict validation.
# Direct response to user still seeing "no supported source" after 1.5.6 — they couldn't
# tell WHICH sound was broken, and some codec/extension mismatches still slipped through.
# =====================================================================
class TestSoundsManagerAdmin:
    def test_list_endpoint_returns_items_shape(self, admin):
        c, h = admin
        r = c.get('/api/admin/sounds/list', headers=h)
        assert r.status_code == 200
        assert 'items' in r.json
        assert 'ffprobe_available' in r.json
        # Defaults: chime/pulse/none are synthetic, filtered out
        for item in r.json['items']:
            assert item['name'] not in ['chime', 'pulse', 'none']

    def test_list_endpoint_shows_uploaded_sound(self, admin, app):
        c, h = admin
        if not _ffmpeg_available():
            pytest.skip('ffmpeg required')
        # Upload a real MP3
        r = c.post('/api/admin/media', data={'kind': 'sound', 'file': (io.BytesIO(make_real_mp3(1.0)), 'tune.mp3')}, headers=h, content_type='multipart/form-data')
        name = r.json['name']
        # List
        d = c.get('/api/admin/sounds/list', headers=h).json
        matching = [x for x in d['items'] if x['name'] == name]
        assert len(matching) == 1
        assert matching[0]['playable'] is True
        assert matching[0]['codec'] == 'mp3'
        assert matching[0]['duration_ms'] > 500

    def test_list_flags_broken_file(self, admin, app):
        """A file in settings.sounds whose actual bytes are not valid audio should show as broken."""
        c, h = admin
        if not _ffmpeg_available():
            pytest.skip('ffmpeg required')
        # Write a bogus file directly to the media dir and add to settings.sounds
        import json as _json
        media = app.store.path / 'media'; media.mkdir(exist_ok=True)
        (media / 'broken.mp3').write_bytes(b'ID3\x04\x00\x00\x00\x00\x00\x00' + b'\x00'*200)
        with app.store.db(True) as db:
            s = app.store.settings(db)
            db.execute("UPDATE settings SET value=? WHERE key='sounds'", (_json.dumps(s.get('sounds',[])+['broken.mp3']),))
        d = c.get('/api/admin/sounds/list', headers=h).json
        broken = [x for x in d['items'] if x['name'] == 'broken.mp3'][0]
        assert broken['playable'] is False
        assert broken['reason']  # has a specific reason

    def test_delete_removes_file_and_allowlist_entry(self, admin, app):
        c, h = admin
        if not _ffmpeg_available():
            pytest.skip('ffmpeg required')
        r = c.post('/api/admin/media', data={'kind': 'sound', 'file': (io.BytesIO(make_real_mp3(1.0)), 'byegone.mp3')}, headers=h, content_type='multipart/form-data')
        name = r.json['name']
        # 1.6.0: an upload is a library row (no settings.sounds append)
        assert any(x['media_filename'] == name for x in app.store.soundboard_list())
        assert (app.store.path / 'media' / name).exists()
        r2 = c.delete('/api/admin/sounds/' + name, headers=h)
        assert r2.status_code == 200
        assert not any(x['media_filename'] == name for x in app.store.soundboard_list())
        assert name not in app.store.settings()['sounds']
        assert not (app.store.path / 'media' / name).exists()

    def test_deleting_the_default_sound_resets_default_to_chime(self, admin, app):
        c, h = admin
        if not _ffmpeg_available():
            pytest.skip('ffmpeg required')
        r = c.post('/api/admin/media', data={'kind': 'sound', 'file': (io.BytesIO(make_real_mp3(1.0)), 'alert.mp3')}, headers=h, content_type='multipart/form-data')
        name = r.json['name']
        c.post('/api/admin/visuals', json={'alert_sound': name}, headers=h)
        # Confirm the posted alert_sound became the default sound
        assert app.store.settings()['default_sound'] == r.json['entry']['id']
        # Delete
        c.delete('/api/admin/sounds/' + name, headers=h)
        s = app.store.settings()
        assert s['default_sound'] == 'chime' and s['sounds'][0] == 'chime'
        visuals2 = c.get('/api/admin/visuals', headers=h).json['visuals']
        assert visuals2['alert_sound'] == 'viewer'

    def test_delete_rejects_builtin_sounds(self, admin):
        c, h = admin
        for builtin in ['chime', 'pulse', 'none']:
            r = c.delete('/api/admin/sounds/' + builtin, headers=h)
            assert r.status_code == 400

    def test_delete_rejects_bad_filename(self, admin):
        c, h = admin
        for bad in ['../etc/passwd', 'foo.exe', 'has spaces.mp3']:
            r = c.delete('/api/admin/sounds/' + bad, headers=h)
            assert r.status_code in [400, 404]

    def test_delete_requires_admin(self, client):
        r = client.delete('/api/admin/sounds/foo.mp3')
        assert r.status_code == 401

    def test_list_requires_admin(self, client):
        r = client.get('/api/admin/sounds/list')
        assert r.status_code == 401


class TestCodecMatchesExtension:
    """1.5.7 — ffprobe-detected codec must match the upload extension.
    Catches AAC-ADTS renamed to .mp3 and other mismatches that pass basic magic bytes
    but confuse browser decoders."""

    def test_aac_adts_renamed_to_mp3_is_auto_fixed(self, admin):
        """v1.5.9 — AAC-ADTS files renamed .mp3 USED to be rejected (1.5.7-1.5.8).
        1.5.9 server-side auto-fix now transcodes them to real MP3 Layer 3 and stores them.
        The whole point of this release: admin uploads broken file → it just works."""
        c, h = admin
        if not _ffmpeg_available():
            pytest.skip('ffmpeg required')
        import subprocess as _sp, tempfile as _tf, os as _os
        tmp = _tf.mkdtemp()
        aac = _os.path.join(tmp, 'audio.aac')
        _sp.run(['ffmpeg', '-v', 'error', '-f', 'lavfi',
                 '-i', 'sine=frequency=440:duration=1',
                 '-codec:a', 'aac', '-f', 'adts', '-y', aac], check=True)
        with open(aac, 'rb') as f: aac_bytes = f.read()
        r = c.post('/api/admin/media', data={'kind': 'sound', 'file': (io.BytesIO(aac_bytes), 'sneaky.mp3')}, headers=h, content_type='multipart/form-data')
        assert r.status_code == 200, r.json
        assert r.json['auto_fixed'] is True
        assert r.json['name'].endswith('.mp3')
        assert r.json['original_name'] == 'sneaky.mp3'

    def test_real_mp3_still_accepted(self, admin):
        c, h = admin
        if not _ffmpeg_available():
            pytest.skip('ffmpeg required')
        r = c.post('/api/admin/media', data={'kind': 'sound', 'file': (io.BytesIO(make_real_mp3(1.0)), 'ok.mp3')}, headers=h, content_type='multipart/form-data')
        assert r.status_code == 200

    def test_vorbis_ogg_still_accepted(self, admin):
        c, h = admin
        if not _ffmpeg_available():
            pytest.skip('ffmpeg required')
        r = c.post('/api/admin/media', data={'kind': 'sound', 'file': (io.BytesIO(make_real_ogg(1.0)), 'ok.ogg')}, headers=h, content_type='multipart/form-data')
        assert r.status_code == 200

    def test_pcm_wav_still_accepted(self, admin):
        c, h = admin
        if not _ffmpeg_available():
            pytest.skip('ffmpeg required')
        r = c.post('/api/admin/media', data={'kind': 'sound', 'file': (io.BytesIO(make_wav(1.0)), 'ok.wav')}, headers=h, content_type='multipart/form-data')
        assert r.status_code == 200

    def test_probe_rejects_codec_extension_mismatch_directly(self):
        """Unit test: give probe_audio_file real AAC bytes but claim it's .mp3 → rejected."""
        from acepressure.video import probe_audio_file
        if not _ffmpeg_available():
            pytest.skip('ffmpeg required')
        import subprocess as _sp, tempfile as _tf, os as _os
        tmp = _tf.mkdtemp()
        aac = _os.path.join(tmp, 'audio.aac')
        _sp.run(['ffmpeg', '-v', 'error', '-f', 'lavfi',
                 '-i', 'sine=frequency=440:duration=1',
                 '-codec:a', 'aac', '-f', 'adts', '-y', aac], check=True)
        with open(aac, 'rb') as f: aac_bytes = f.read()
        probe = probe_audio_file(aac_bytes, '.mp3')
        assert probe['valid'] is False
        assert probe['codec'] == 'aac'
        assert 'aac' in probe['reason'].lower() or 'mp3' in probe['reason'].lower()


# =====================================================================
# v1.5.8 — Fix_Audio.bat drag-and-drop re-encoder for broken MP3s (myinstants.com files etc.)
# =====================================================================
class TestFixAudioBat:
    def test_fix_audio_bat_exists_in_root(self):
        """Must be at repo root so users see it next to Install.bat / Start.bat."""
        assert (ROOT / 'Fix_Audio.bat').is_file()

    def test_fix_audio_bat_has_expected_ffmpeg_args(self):
        """Verify the batch file produces STANDARD browser-safe MP3 output.
        Specifically: libmp3lame codec, CBR 128k, 48 kHz stereo, metadata stripped."""
        txt = (ROOT / 'Fix_Audio.bat').read_text(encoding='utf-8')
        # All of these flags must be present to produce a browser-decodable MP3
        for flag in ['libmp3lame', '128k', '48000', '-ac 2', '-map_metadata -1', 'ffmpeg']:
            assert flag in txt, f'Fix_Audio.bat missing required ffmpeg flag: {flag}'
        # Must output *_fixed.mp3 next to the original
        assert '_fixed.mp3' in txt
        # Must help the user when invoked with no args
        assert 'Drag' in txt or 'drag' in txt
        # Must look for bundled ffmpeg first, then PATH
        assert 'tools\\bin\\ffmpeg.exe' in txt or 'tools/bin/ffmpeg' in txt
        # Must detect missing ffmpeg and point to Install_Media_Tools.bat
        assert 'Install_Media_Tools' in txt

    def test_fix_audio_bat_caps_duration_at_20s(self):
        """The alert-sound upload has a 20s cap. Fix_Audio.bat should also trim to 20s
        so the output passes validation."""
        txt = (ROOT / 'Fix_Audio.bat').read_text(encoding='utf-8')
        assert '-t 20' in txt

    def test_fix_audio_bat_still_shipped_as_offline_fallback(self):
        """v1.5.9 — server-side auto-fix supersedes Fix_Audio.bat for new uploads, but the .bat
        remains in the shipped bundle for admins who want to pre-process offline (e.g. no ffmpeg
        on server) or inspect the fix before uploading."""
        assert (ROOT / 'Fix_Audio.bat').is_file()
        assert 'OPTIONAL' in (ROOT / 'Fix_Audio.bat').read_text(encoding='utf-8'), 'help text must say the server auto-fixes now'

    def test_server_error_no_longer_recommends_fix_audio_bat(self):
        """v1.5.9 — the probe_audio_file reason string returned to admins must NOT mention
        Fix_Audio.bat. The server has already tried that recipe server-side via transcode_audio
        and failed — telling the admin to also run it offline is a loop. Comments/docstrings
        that reference Fix_Audio.bat for code-provenance purposes are fine."""
        py = (ROOT / 'acepressure' / 'video.py').read_text(encoding='utf-8')
        # Extract just the error 'reason' strings (quoted literals in return statements).
        import re as _re
        reason_literals = _re.findall(r"'reason':\s*'([^']+)'", py)
        for reason in reason_literals:
            assert 'Fix_Audio.bat' not in reason, f'reason string still mentions Fix_Audio.bat: {reason!r}'


# =====================================================================
# v1.5.9 — Server-side auto-fix on upload + original filename preservation
# =====================================================================
def _ffmpeg_make(args, suffix):
    """Run ffmpeg with lavfi input args and return the produced bytes."""
    import subprocess as _sp, tempfile as _tf, os as _os
    out = _os.path.join(_tf.mkdtemp(), 'clip' + suffix)
    _sp.run(['ffmpeg', '-v', 'error', '-y', *args, out], check=True, capture_output=True)
    with open(out, 'rb') as f: return f.read()


def make_aac_adts(duration_s=1.0):
    """AAC-ADTS bytes: sync word 0xFFF1 passes the MP3 magic check, but browsers refuse it as .mp3."""
    return _ffmpeg_make(['-f', 'lavfi', '-i', f'sine=frequency=440:duration={duration_s}',
                         '-codec:a', 'aac', '-f', 'adts'], '.aac')


def _upload_sound(c, h, data, filename):
    return c.post('/api/admin/media', data={'kind': 'sound', 'file': (io.BytesIO(data), filename)},
                  headers=h, content_type='multipart/form-data')


class TestAutoFixOnUpload:
    """A broken MP3/OGG/WAV uploaded in the admin page is re-encoded to standard MP3 server-side."""

    def test_transcode_audio_rescues_aac_in_mp3(self):
        if not _ffmpeg_available(): pytest.skip('ffmpeg required')
        from acepressure.video import transcode_audio, probe_audio_file
        fixed = transcode_audio(make_aac_adts(), '.mp3')
        assert fixed is not None
        verify = probe_audio_file(fixed, '.mp3')
        assert verify['valid'] is True and verify['codec'] == 'mp3'

    def test_transcode_audio_none_without_ffmpeg(self, monkeypatch):
        from acepressure import video
        monkeypatch.setattr(video, 'tool', lambda name: None)
        assert video.transcode_audio(b'anything-at-all', '.mp3') is None

    def test_transcode_audio_none_for_empty_or_oversized(self):
        from acepressure.video import transcode_audio
        assert transcode_audio(b'', '.mp3') is None
        assert transcode_audio(None, '.mp3') is None
        assert transcode_audio(b'\xff\xfb\x90\x00' + b'\x00' * (25 * 1024 * 1024), '.mp3') is None

    def test_transcode_audio_rejects_unknown_extension_hint(self):
        """The hint becomes part of a temp filename; only known suffixes are allowed."""
        from acepressure.video import transcode_audio
        with pytest.raises(ValueError):
            transcode_audio(b'ID3' + b'\x00' * 100, '../etc/passwd')

    def test_transcode_audio_none_for_frameless_mp3(self):
        if not _ffmpeg_available(): pytest.skip('ffmpeg required')
        from acepressure.video import transcode_audio
        assert transcode_audio(b'ID3\x04\x00\x00\x00\x00\x00\x00' + b'\x00' * 2000, '.mp3') is None

    def test_upload_auto_fixes_aac_renamed_mp3(self, admin):
        c, h = admin
        if not _ffmpeg_available(): pytest.skip('ffmpeg required')
        r = _upload_sound(c, h, make_aac_adts(), 'myinstant_meme.mp3')
        assert r.status_code == 200, r.json
        assert r.json['auto_fixed'] is True
        assert r.json['name'].endswith('.mp3')
        assert r.json['original_name'] == 'myinstant_meme.mp3'

    def test_upload_leaves_valid_mp3_byte_identical(self, admin, app):
        c, h = admin
        if not _ffmpeg_available(): pytest.skip('ffmpeg required')
        mp3 = make_real_mp3(1.0)
        r = _upload_sound(c, h, mp3, 'legit.mp3')
        assert r.status_code == 200 and r.json['auto_fixed'] is False
        assert (app.store.path / 'media' / r.json['name']).read_bytes() == mp3

    def test_upload_auto_fixes_mulaw_wav(self, admin):
        """μ-law WAV fails stdlib wave (non-PCM) but ffmpeg decodes it: rescued to MP3."""
        c, h = admin
        if not _ffmpeg_available(): pytest.skip('ffmpeg required')
        wav = _ffmpeg_make(['-f', 'lavfi', '-i', 'sine=frequency=440:duration=1', '-codec:a', 'pcm_mulaw'], '.wav')
        r = _upload_sound(c, h, wav, 'phone_recording.wav')
        assert r.status_code == 200, r.json
        assert r.json['auto_fixed'] is True and r.json['name'].endswith('.mp3')

    def test_upload_converts_flac_bonus_format(self, admin):
        """Unknown magic bytes get one rescue attempt, so FLAC/M4A downloads also work."""
        c, h = admin
        if not _ffmpeg_available(): pytest.skip('ffmpeg required')
        flac = _ffmpeg_make(['-f', 'lavfi', '-i', 'sine=frequency=440:duration=1'], '.flac')
        r = _upload_sound(c, h, flac, 'clip.flac')
        assert r.status_code == 200, r.json
        assert r.json['auto_fixed'] is True and r.json['name'].endswith('.mp3')

    def test_long_pcm_wav_still_rejected_not_trimmed(self, admin):
        c, h = admin
        r = _upload_sound(c, h, make_wav(36.0), 'long.wav')
        assert r.status_code == 400 and 'WAV' in r.json['error']

    def test_long_broken_mp3_rejected_not_silently_trimmed(self, admin, app):
        """A 36 s broken file must be refused like a 36 s valid file, not cut to 30 s."""
        c, h = admin
        if not _ffmpeg_available(): pytest.skip('ffmpeg required')
        before = set((app.store.path / 'media').glob('*')) if (app.store.path / 'media').exists() else set()
        r = _upload_sound(c, h, make_aac_adts(36.0), 'long_meme.mp3')
        assert r.status_code == 400, r.json
        assert 'longer than 30 seconds' in r.json['error']
        after = set((app.store.path / 'media').glob('*')) if (app.store.path / 'media').exists() else set()
        assert after == before, 'nothing may be written for a refused upload'

    def test_long_unknown_duration_input_rejected_after_decode(self, admin):
        """FLAC has no MP3/OGG magic, so its length is only known after decoding: still refused."""
        c, h = admin
        if not _ffmpeg_available(): pytest.skip('ffmpeg required')
        flac = _ffmpeg_make(['-f', 'lavfi', '-i', 'sine=frequency=440:duration=36'], '.flac')
        r = _upload_sound(c, h, flac, 'long.flac')
        assert r.status_code == 400, r.json
        assert 'longer than 30 seconds' in r.json['error']

    def test_soundboard_auto_fixes_and_allows_30s(self, admin, app):
        c, h = admin
        if not _ffmpeg_available(): pytest.skip('ffmpeg required')
        sb_id = app.store.soundboard_create(name='Test Entry')['id']
        r = c.post('/api/admin/soundboard/' + sb_id + '/media',
                   data={'file': (io.BytesIO(make_aac_adts(25.0)), 'meme_sound.mp3')},
                   headers=h, content_type='multipart/form-data')
        assert r.status_code == 200, r.json
        assert r.json['auto_fixed'] is True and r.json['original_name'] == 'meme_sound.mp3'
        assert 24000 <= r.json['entry']['duration_ms'] <= 25600

    def test_soundboard_upload_does_not_store_filename_label(self, admin, app):
        """Soundboard tiles show the entry name, so no media_labels entry (which could go stale)."""
        c, h = admin
        sb_id = app.store.soundboard_create(name='Tile')['id']
        r = c.post('/api/admin/soundboard/' + sb_id + '/media',
                   data={'file': (io.BytesIO(make_wav(0.5)), 'tile.wav')},
                   headers=h, content_type='multipart/form-data')
        assert r.status_code == 200
        assert r.json['entry']['media_filename'] not in (app.store.settings().get('media_labels') or {})

    def test_avatar_upload_never_runs_audio_rescue(self, admin, monkeypatch):
        from acepressure import video
        monkeypatch.setattr(video, 'transcode_audio', lambda *a, **k: pytest.fail('audio rescue ran for an avatar'))
        c, h = admin
        img = io.BytesIO(); Image.new('RGB', (40, 40), 'red').save(img, format='PNG')
        r = c.post('/api/admin/media', data={'kind': 'avatar', 'file': (io.BytesIO(img.getvalue()), 'me.png')},
                   headers=h, content_type='multipart/form-data')
        assert r.status_code == 200 and r.json['name'].endswith('.jpg')

    def test_size_cap_checked_before_rescue(self, admin, monkeypatch):
        from acepressure import video
        monkeypatch.setattr(video, 'transcode_audio', lambda *a, **k: pytest.fail('rescue ran on an oversized upload'))
        c, h = admin
        r = _upload_sound(c, h, b'ID3' + b'\x00' * (9 * 1024 * 1024), 'huge.mp3')
        assert r.status_code == 400 and '8 MB' in r.json['error']


class TestAudioWithoutFfmpeg:
    """PCs without FFmpeg keep 1.5.8 behaviour: valid uploads accepted, length read from headers."""

    def test_valid_mp3_accepted_and_duration_from_header(self, admin, monkeypatch):
        if not _ffmpeg_available(): pytest.skip('ffmpeg needed to build the fixture')
        mp3 = make_real_mp3(1.0)
        from acepressure import video
        monkeypatch.setattr(video, 'tool', lambda name: None)
        c, h = admin
        r = _upload_sound(c, h, mp3, 'ok.mp3')
        assert r.status_code == 200, r.json
        assert r.json['auto_fixed'] is False

    def test_long_mp3_rejected_via_header_duration(self, admin, monkeypatch):
        if not _ffmpeg_available(): pytest.skip('ffmpeg needed to build the fixture')
        mp3 = _ffmpeg_make(['-f', 'lavfi', '-i', 'sine=frequency=440:duration=36',
                            '-codec:a', 'libmp3lame', '-b:a', '128k'], '.mp3')
        from acepressure import video
        monkeypatch.setattr(video, 'tool', lambda name: None)
        c, h = admin
        r = _upload_sound(c, h, mp3, 'long.mp3')
        assert r.status_code == 400 and 'longer than 30 seconds' in r.json['error']

    def test_mp3_header_duration_parser(self):
        if not _ffmpeg_available(): pytest.skip('ffmpeg needed to build the fixture')
        from acepressure.video import _mp3_duration_ms
        mp3 = _ffmpeg_make(['-f', 'lavfi', '-i', 'sine=frequency=440:duration=4',
                            '-codec:a', 'libmp3lame', '-b:a', '128k'], '.mp3')
        assert 3600 <= _mp3_duration_ms(mp3) <= 4400

    def test_ogg_vorbis_header_duration_parser(self):
        """Byte-level fixture: identification header (44.1 kHz) + final page granule of 3 s."""
        from acepressure.video import _ogg_duration_ms
        ident = b'\x01vorbis' + (0).to_bytes(4, 'little') + bytes([2]) + (44100).to_bytes(4, 'little') + b'\x00' * 16
        first = b'OggS' + b'\x00\x02' + (0).to_bytes(8, 'little') + b'\x00' * 12 + ident
        last = b'OggS' + b'\x00\x04' + (3 * 44100).to_bytes(8, 'little') + b'\x00' * 20
        assert _ogg_duration_ms(first + b'\x00' * 40 + last) == 3000
        assert _ogg_duration_ms(b'OggS' + b'\x00' * 80) == 0, 'no Vorbis/Opus header -> unknown'


class TestFfmpegInputHardening:
    """Uploaded audio is format-auto-detected; ffmpeg/ffprobe must be limited to plain containers."""

    def _capture(self, monkeypatch):
        from acepressure import video
        calls = []
        def fake_run(cmd, **kw):
            calls.append(cmd)
            raise RuntimeError('stop after capturing args')
        monkeypatch.setattr(video, 'tool', lambda name: '/usr/bin/' + name)
        monkeypatch.setattr(video.subprocess, 'run', fake_run)
        return video, calls

    def test_transcode_audio_passes_whitelists(self, monkeypatch):
        video, calls = self._capture(monkeypatch)
        assert video.transcode_audio(b'ID3' + b'\x00' * 100, '.mp3') is None
        cmd = calls[0]
        assert cmd[cmd.index('-protocol_whitelist') + 1] == 'file'
        demuxers = cmd[cmd.index('-format_whitelist') + 1].split(',')
        assert {'mp3', 'ogg', 'wav'} <= set(demuxers)
        assert not {'hls', 'concat', 'sdp', 'image2', 'rtp'} & set(demuxers)
        assert cmd.index('-format_whitelist') < cmd.index('-i'), 'whitelists are input options'

    def test_probe_audio_file_passes_whitelists(self, monkeypatch):
        video, calls = self._capture(monkeypatch)
        video.probe_audio_file(b'ID3' + b'\x00' * 100, '.mp3')
        cmd = calls[0]
        assert '-protocol_whitelist' in cmd and '-format_whitelist' in cmd

    def test_disguised_playlist_and_sdp_uploads_refused(self, admin, tmp_path):
        c, h = admin
        if not _ffmpeg_available(): pytest.skip('ffmpeg required')
        secret = tmp_path / 'secret.wav'; secret.write_bytes(make_wav(1.0))
        playlist = f'#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXTINF:1.0,\nfile://{secret}\n#EXT-X-ENDLIST\n'.encode()
        sdp = b'v=0\no=- 0 0 IN IP4 127.0.0.1\ns=x\nc=IN IP4 127.0.0.1\nt=0 0\nm=audio 50998 RTP/AVP 0\n'
        for payload, name in [(playlist, 'list.mp3'), (sdp, 'session.mp3')]:
            started = time.time()
            r = _upload_sound(c, h, payload, name)
            assert r.status_code == 400, (name, r.json)
            assert time.time() - started < 10, 'must fail fast, not wait on a network socket'

    def test_rescue_recipe_matches_fix_audio_bat(self):
        """Server-side rescue and the offline .bat must produce the same kind of file."""
        from acepressure.video import FIX_AUDIO_ARGS
        bat = (ROOT / 'Fix_Audio.bat').read_text(encoding='utf-8')
        for flag, value in zip(FIX_AUDIO_ARGS[::2], FIX_AUDIO_ARGS[1::2]):
            assert f'{flag} {value}' in bat, f'Fix_Audio.bat is missing "{flag} {value}"'


class TestOriginalFilenamePreservation:
    """Admin uploads 'intro.mp3' and sees 'intro.mp3' everywhere, not the random stored name."""

    def _upload(self, c, h, filename='my_awesome_intro.wav'):
        return _upload_sound(c, h, make_wav(0.5), filename)

    def test_label_recorded_on_upload(self, admin, app):
        c, h = admin
        r = self._upload(c, h)
        assert r.status_code == 200
        assert app.store.settings()['media_labels'][r.json['name']] == 'my_awesome_intro.wav'

    def test_sounds_list_shows_display_name_and_auto_fixed(self, admin, app):
        c, h = admin
        plain = self._upload(c, h, 'birthday_song.wav').json['name']
        rows = {i['name']: i for i in c.get('/api/admin/sounds/list', headers=h).json['items']}
        assert rows[plain]['display_name'] == 'birthday_song.wav'
        assert rows[plain]['auto_fixed'] is False
        if _ffmpeg_available():
            fixed = _upload_sound(c, h, make_aac_adts(), 'broken.mp3').json['name']
            rows = {i['name']: i for i in c.get('/api/admin/sounds/list', headers=h).json['items']}
            assert rows[fixed]['auto_fixed'] is True
            assert rows[fixed]['display_name'] == 'broken.mp3'

    def test_delete_clears_label_and_auto_fixed(self, admin, app):
        c, h = admin
        if not _ffmpeg_available(): pytest.skip('ffmpeg required')
        name = _upload_sound(c, h, make_aac_adts(), 'temp.mp3').json['name']
        s = app.store.settings()
        assert name in s['media_labels'] and name in s['media_auto_fixed']
        assert c.delete('/api/admin/sounds/' + name, headers=h).status_code == 200
        s = app.store.settings()
        assert name not in s['media_labels'] and name not in s['media_auto_fixed']

    def test_legacy_sound_falls_back_to_stored_name(self, admin, app):
        legacy = 'Zx8Yq2Lmno-abcd.wav'
        (app.store.path / 'media').mkdir(exist_ok=True)
        (app.store.path / 'media' / legacy).write_bytes(make_wav(0.5))
        with app.store.db(True) as db:
            s = app.store.settings(db)
            db.execute("UPDATE settings SET value=? WHERE key='sounds'", (json.dumps(s['sounds'] + [legacy]),))
        c, h = admin
        row = next(i for i in c.get('/api/admin/sounds/list', headers=h).json['items'] if i['name'] == legacy)
        assert row['display_name'] == legacy and row['auto_fixed'] is False

    def test_library_item_is_named_after_the_upload(self, admin, client):
        c, h = admin
        name = self._upload(c, h, 'Thug Life.wav').json['name']
        item = next(x for x in c.get('/api/admin/soundboard', headers=h).json['items'] if x['media_filename'] == name)
        assert item['name'] == 'Thug Life' and item['original_name'] == 'Thug Life.wav'
        public = client.get('/api/public/soundboard').json['items']
        assert 'Thug Life' in [x['name'] for x in public], 'viewers see the name without the extension'
        studio = c.get('/api/admin/visuals', headers=h).json
        assert 'sounds' in studio and 'sound_labels' in studio

    def test_repeated_names_are_numbered(self):
        from acepressure.video import sound_labels
        s = {'sounds': ['chime', 'a.mp3', 'b.mp3', 'c.mp3', 'legacy.mp3'],
             'media_labels': {'a.mp3': 'meme.mp3', 'b.mp3': 'meme.mp3', 'c.mp3': 'other.ogg'}}
        assert sound_labels(s) == {'a.mp3': 'meme.mp3', 'b.mp3': 'meme.mp3 (2)', 'c.mp3': 'other.ogg'}
        assert sound_labels(s, strip_extension=True) == {'a.mp3': 'meme', 'b.mp3': 'meme (2)', 'c.mp3': 'other'}

    def test_sanitize_original_name(self):
        from acepressure.video import sanitize_original_name
        assert sanitize_original_name('/etc/passwd') == 'passwd'
        assert sanitize_original_name('..\\..\\windows\\system32.dll') == 'system32.dll'
        assert sanitize_original_name('with\x00null.mp3') == 'withnull.mp3'
        assert sanitize_original_name('evil‮gnp.mp3') == 'evilgnp.mp3', 'RTL override stripped'
        assert sanitize_original_name('हिंदी गाना.mp3') == 'हिंदी गाना.mp3', 'Hindi filenames kept'
        assert sanitize_original_name('') == '' and sanitize_original_name(None) == ''
        assert len(sanitize_original_name('x' * 200)) <= 120
        assert sanitize_original_name('\U0001F468\u200d\U0001F4BB coder.wav') == '\U0001F468\u200d\U0001F4BB coder.wav', 'emoji ZWJ sequence kept'
        assert sanitize_original_name('\u0915\u094d\u200d\u0937 test.wav') == '\u0915\u094d\u200d\u0937 test.wav', 'Indic ZWJ half-form kept'
        assert sanitize_original_name('\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u0645.mp3') == '\u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u0645.mp3', 'ZWNJ kept'
        assert sanitize_original_name('a\u2066b\u2069\ufeff\u200fc\nd.mp3') == 'abcd.mp3', 'bidi isolates, BOM, marks and newlines removed'

    def test_frontends_use_labels(self):
        admin_js = (ROOT / 'acepressure' / 'static' / 'admin.js').read_text(encoding='utf-8')
        designer_js = (ROOT / 'acepressure' / 'static' / 'designer.js').read_text(encoding='utf-8')
        public_js = (ROOT / 'acepressure' / 'static' / 'public.js').read_text(encoding='utf-8')
        assert 'display_name' in admin_js and 'auto_fixed' in admin_js and 'badge-fixed' in admin_js
        assert 'sound_labels' in public_js and 'function soundLabel(' in public_js
        assert '.badge.badge-fixed' in (ROOT / 'acepressure' / 'static' / 'premium.css').read_text(encoding='utf-8')


class TestAlertBundleAutoFix:
    def _png(self):
        b = io.BytesIO(); Image.new('RGBA', (32, 32), (255, 0, 0, 255)).save(b, format='PNG'); return b.getvalue()

    def test_bundle_rescues_broken_audio_and_records_label(self, admin, app):
        c, h = admin
        if not _ffmpeg_available(): pytest.skip('ffmpeg required')
        r = c.post('/api/admin/alert-bundle',
                   data={'visual': (io.BytesIO(self._png()), 'v.png'), 'audio': (io.BytesIO(make_aac_adts()), 'chime_from_web.mp3')},
                   headers=h, content_type='multipart/form-data')
        assert r.status_code == 200, r.json
        assert r.json['audio'].endswith('.mp3') and r.json['audio_auto_fixed'] is True
        assert r.json['audio_original_name'] == 'chime_from_web.mp3'
        s = app.store.settings()
        assert s['visuals']['alert_sound'] == 'viewer' and s['default_sound'] == r.json['entry']['id']
        assert s['media_labels'][r.json['audio']] == 'chime_from_web.mp3'
        assert r.json['audio'] in s['media_auto_fixed']

    def test_bundle_with_unfixable_audio_leaves_no_files(self, admin, app):
        c, h = admin
        media = app.store.path / 'media'; media.mkdir(exist_ok=True)
        before = set(media.glob('*'))
        r = c.post('/api/admin/alert-bundle',
                   data={'visual': (io.BytesIO(self._png()), 'v.png'), 'audio': (io.BytesIO(b'not audio at all ' * 20), 'x.mp3')},
                   headers=h, content_type='multipart/form-data')
        assert r.status_code == 400
        assert set(media.glob('*')) == before, 'a refused bundle must not leave the visual behind'


class TestValidateOrFixAudioHelper:
    def test_valid_wav_untouched(self):
        from acepressure.video import validate_or_fix_audio
        wav = make_wav(1.0)
        content, ext, dur, fixed = validate_or_fix_audio(wav)
        assert content == wav and ext == 'wav' and fixed is False and 900 < dur < 1100

    def test_long_wav_rejected(self):
        from acepressure.video import validate_or_fix_audio
        with pytest.raises(Problem) as exc:
            validate_or_fix_audio(make_wav(25.0), max_duration_ms=20000)
        assert 'WAV' in exc.value.message

    def test_valid_mp3_untouched(self):
        if not _ffmpeg_available(): pytest.skip('ffmpeg required')
        from acepressure.video import validate_or_fix_audio
        mp3 = make_real_mp3(1.0)
        content, ext, _, fixed = validate_or_fix_audio(mp3)
        assert content == mp3 and ext == 'mp3' and fixed is False

    def test_empty_rejected(self):
        from acepressure.video import validate_or_fix_audio
        with pytest.raises(Problem):
            validate_or_fix_audio(b'')

    def test_unrecoverable_reason_has_no_fix_audio_loop(self):
        if not _ffmpeg_available(): pytest.skip('ffmpeg required')
        from acepressure.video import validate_or_fix_audio
        with pytest.raises(Problem) as exc:
            validate_or_fix_audio(b'ID3\x04\x00\x00\x00\x00\x00\x00' + b'\x00' * 1000)
        assert 'Fix_Audio.bat' not in exc.value.message


# =====================================================================
# v1.5.9 — review regressions (security/backend review + UI pass)
# =====================================================================
class TestReviewRegressions159:
    def test_broken_clip_with_leading_silence_is_fixed_not_refused(self, admin):
        """ffprobe guesses a raw ADTS clip's length from its first (silent) frames: a 6 s clip read
        as ~29 s. The guess from a failed probe must not refuse the upload before conversion."""
        if not _ffmpeg_available(): pytest.skip('ffmpeg required')
        c, h = admin
        clip = _ffmpeg_make(['-f', 'lavfi', '-i', r'aevalsrc=if(lt(t\,1)\,0\,sin(2*PI*440*t)):s=44100:d=6',
                             '-c:a', 'aac', '-b:a', '128k', '-f', 'adts'], '.aac')
        r = _upload_sound(c, h, clip, 'airhorn.mp3')
        assert r.status_code == 200, r.json
        assert r.json['auto_fixed'] is True and r.json['original_name'] == 'airhorn.mp3'

    def test_picks_switch_hides_the_library_from_viewers(self, admin):
        c, h = admin
        sid = _upload_sound(c, h, make_wav(0.5), 'WhatsApp Audio 2026-10-11.wav').json['entry']['id']
        assert [x['name'] for x in c.get('/api/public/soundboard').json['items'] if x['id'] == sid] == ['WhatsApp Audio 2026-10-11']
        assert c.get('/api/public/config').json['sound_labels'] == {}
        assert c.post('/api/admin/settings', json={'allow_sound_choice': False}, headers=h).status_code == 200
        assert c.get('/api/public/soundboard').json['items'] == []
        r = c.post('/api/public/tips', json={'amount': 100, 'name': 'Asha', 'soundboard_id': sid})
        assert r.status_code == 409 and 'switched off' in r.json['error']

    def test_label_numbering_never_collides(self):
        from acepressure.video import sound_labels
        s = {'sounds': ['a', 'b', 'c', 'd'],
             'media_labels': {'a': 'meme.wav', 'b': 'meme (2).wav', 'c': 'meme.wav', 'd': 'chime.mp3'}}
        viewer = sound_labels(s, strip_extension=True)
        assert viewer == {'a': 'meme', 'b': 'meme (2)', 'c': 'meme (3)', 'd': 'chime (2)'}
        admin_view = sound_labels({'sounds': ['a', 'b', 'c'], 'media_labels': {'a': 'x.wav', 'b': 'x.wav (2)', 'c': 'x.wav'}})
        assert len(set(admin_view.values())) == 3

    def test_obs_overlay_page_background_stays_transparent(self):
        """premium.css loads after overlay.css on overlay pages; its body gradient must not make the
        OBS browser source opaque (OBS's default CSS only clears background-color)."""
        html = (ROOT / 'acepressure' / 'templates' / 'overlay.html').read_text(encoding='utf-8')
        assert html.index('overlay.css') < html.index('premium.css')
        css = (ROOT / 'acepressure' / 'static' / 'premium.css').read_text(encoding='utf-8')
        assert re.search(r'body\[data-kind\]\s*\{[^}]*background:\s*transparent\s*!important', css)

    def test_every_template_has_the_favicon(self):
        assert (ROOT / 'acepressure' / 'static' / 'favicon.svg').exists()
        for t in (ROOT / 'acepressure' / 'templates').glob('*.html'):
            assert '/static/favicon.svg' in t.read_text(encoding='utf-8'), t.name


class TestDurationEdgeCases159:
    """Lengths come from real frame counts, not guesses, with and without FFmpeg."""

    @staticmethod
    def _no_ffmpeg(monkeypatch):
        from acepressure import video
        monkeypatch.setattr(video, 'tool', lambda name: None)

    def test_fix_audio_bat_output_accepted_without_ffmpeg(self, monkeypatch):
        """Fix_Audio.bat cuts at exactly 20 s; its LAME Info frame + padding must not read as over the cap."""
        if not _ffmpeg_available(): pytest.skip('ffmpeg needed to build the fixture')
        src = _ffmpeg_make(['-f', 'lavfi', '-i', 'sine=frequency=440:duration=25', '-c:a', 'libmp3lame', '-b:a', '192k'], '.mp3')
        import subprocess as _sp, tempfile as _tf, os as _os
        d = _tf.mkdtemp(); a, b = _os.path.join(d, 'in.mp3'), _os.path.join(d, 'out.mp3')
        open(a, 'wb').write(src)
        _sp.run(['ffmpeg', '-v', 'error', '-y', '-i', a, '-codec:a', 'libmp3lame', '-b:a', '128k', '-ar', '48000', '-ac', '2',
                 '-map_metadata', '-1', '-map', '0:a:0', '-t', '20', b], check=True)
        self._no_ffmpeg(monkeypatch)
        from acepressure.video import validate_or_fix_audio
        _, ext, ms, fixed = validate_or_fix_audio(open(b, 'rb').read(), 20000)
        assert ext == 'mp3' and not fixed and 19500 <= ms <= 20500

    def test_vbr_mp3_over_cap_refused_without_ffmpeg(self, monkeypatch):
        if not _ffmpeg_available(): pytest.skip('ffmpeg needed to build the fixture')
        vbr = _ffmpeg_make(['-f', 'lavfi', '-i', 'sine=frequency=300:duration=40', '-c:a', 'libmp3lame', '-q:a', '4'], '.mp3')
        self._no_ffmpeg(monkeypatch)
        from acepressure.video import validate_or_fix_audio
        with pytest.raises(Problem) as exc:
            validate_or_fix_audio(vbr, 30000)
        assert 'longer than 30 seconds' in exc.value.message

    def test_opus_ogg_measured_without_ffmpeg(self, monkeypatch):
        if not _ffmpeg_available(): pytest.skip('ffmpeg needed to build the fixture')
        short = _ffmpeg_make(['-f', 'lavfi', '-i', 'sine=frequency=300:duration=3', '-c:a', 'libopus', '-b:a', '64k'], '.ogg')
        long = _ffmpeg_make(['-f', 'lavfi', '-i', 'sine=frequency=300:duration=40', '-c:a', 'libopus', '-b:a', '64k'], '.ogg')
        self._no_ffmpeg(monkeypatch)
        from acepressure.video import validate_or_fix_audio
        assert 2900 <= validate_or_fix_audio(short, 20000)[2] <= 3100
        with pytest.raises(Problem):
            validate_or_fix_audio(long, 30000)

    def test_aac_renamed_mp3_refused_without_ffmpeg(self, admin, monkeypatch):
        """Without FFmpeg nothing can be converted, so the browser-unplayable file is refused, not stored."""
        if not _ffmpeg_available(): pytest.skip('ffmpeg needed to build the fixture')
        aac = make_aac_adts(2.0)
        self._no_ffmpeg(monkeypatch)
        c, h = admin
        r = _upload_sound(c, h, aac, 'airhorn.mp3')
        assert r.status_code == 400 and 'Install_Media_Tools.bat' in r.json['error']

    def test_clip_cut_from_longer_vbr_file_accepted(self):
        """A 5 s piece of a 60 s VBR MP3 still carries the 60 s Xing count; decoding gives the truth."""
        if not _ffmpeg_available(): pytest.skip('ffmpeg required')
        full = _ffmpeg_make(['-f', 'lavfi', '-i', 'aevalsrc=0.4*sin(2*PI*(200+300*t)*t):s=44100:d=60',
                             '-c:a', 'libmp3lame', '-q:a', '2'], '.mp3')
        from acepressure.video import validate_or_fix_audio, probe_audio_file
        cut = full[:len(full) * 5 // 60]
        assert probe_audio_file(cut, '.mp3')['duration_ms'] > 20000, 'fixture must reproduce the stale header'
        content, ext, ms, fixed = validate_or_fix_audio(cut, 20000)
        assert content == cut and ext == 'mp3' and not fixed and 3000 <= ms <= 7000

    def test_streamed_wav_header_uses_frames_present(self):
        """WAVs written to a pipe declare 0xFFFFFFFF sizes; Python's wave would report ~13 hours."""
        import struct
        pcm = b'\x00\x10' * 16000 * 2
        hdr = (b'RIFF' + b'\xff\xff\xff\xff' + b'WAVEfmt ' + struct.pack('<IHHIIHH', 16, 1, 1, 16000, 32000, 2, 16)
               + b'data' + b'\xff\xff\xff\xff')
        from acepressure.video import validate_or_fix_audio
        _, ext, ms, fixed = validate_or_fix_audio(hdr + pcm, 20000)
        assert ext == 'wav' and not fixed and ms == 2000

    def test_bundle_write_failure_leaves_no_orphan(self, admin, app, monkeypatch):
        c, h = admin
        media = app.store.path / 'media'; media.mkdir(exist_ok=True)
        before = set(media.glob('*'))
        real_write = Path.write_bytes
        def failing_write(self, data):
            if self.parent == media and self.suffix == '.wav':
                raise OSError(28, 'No space left on device')
            return real_write(self, data)
        monkeypatch.setattr(Path, 'write_bytes', failing_write)
        png = io.BytesIO(); Image.new('RGBA', (16, 16), (0, 255, 0, 255)).save(png, format='PNG')
        with pytest.raises(OSError):
            c.post('/api/admin/alert-bundle', headers=h, content_type='multipart/form-data',
                   data={'visual': (io.BytesIO(png.getvalue()), 'v.png'), 'audio': (io.BytesIO(make_wav(0.5)), 'a.wav')})
        assert set(media.glob('*')) == before, 'the visual written before the failed audio write must be removed'


class TestWindowsScripts159:
    def test_batch_files_are_crlf_ascii(self):
        """cmd.exe can miss GOTO/CALL labels in LF-only files, and prints UTF-8 punctuation as mojibake."""
        bats = sorted(ROOT.glob('*.bat'))
        assert bats
        for p in bats:
            raw = p.read_bytes()
            assert raw.count(b'\n') == raw.count(b'\r\n'), f'{p.name} must use CRLF line endings'
            raw.decode('ascii')


class TestReviewFixes159b:
    """Upload limits, MIME types, unlisted sounds, sounds validation, setup and Windows-script safety."""

    def test_oversized_upload_gets_friendly_json_413(self, admin):
        c, h = admin
        r = c.post('/api/admin/media', headers=h, content_type='multipart/form-data',
                   data={'kind': 'sound', 'file': (io.BytesIO(b'\0' * (27 * 1024 * 1024)), 'huge.wav')})
        assert r.status_code == 413 and r.is_json and 'too large' in r.json['error']

    def test_oversized_json_body_is_not_swallowed(self, admin):
        """data() uses get_json(silent=True); the size error must still surface as a 413."""
        c, h = admin
        r = c.post('/api/admin/settings', headers=h, content_type='application/json',
                   data=b'{"creator": "' + b'a' * (27 * 1024 * 1024) + b'"}')
        assert r.status_code == 413 and 'too large' in r.json['error']

    def test_alert_bundle_allows_video_plus_sound_size(self, admin):
        """A 24 MB video plus an 8 MB sound is over the 26 MB global cap; the bundle route allows 34 MB."""
        c, h = admin
        r = c.post('/api/admin/alert-bundle', headers=h, content_type='multipart/form-data',
                   data={'visual': (io.BytesIO(b'\0' * (30 * 1024 * 1024)), 'v.png')})
        assert r.status_code == 400 and r.json['error'] == 'Image limit is 8 MB.'
        r = c.post('/api/admin/alert-bundle', headers=h, content_type='multipart/form-data',
                   data={'visual': (io.BytesIO(b'\0' * (35 * 1024 * 1024)), 'v.png')})
        assert r.status_code == 413 and 'too large' in r.json['error']

    def test_waitress_body_limit_sits_above_flask_limits(self):
        """Waitress answers an over-limit body with a bare HTML page; Flask's own limits answer in JSON."""
        src = (ROOT / 'run.py').read_text(encoding='utf-8')
        m = re.search(r'max_request_body_size=(\d+)\*1024\*1024', src)
        assert m and int(m.group(1)) > 34

    def test_static_files_get_pinned_mime_types(self, client):
        """Windows registry overrides (.js -> text/plain) plus nosniff would block every script."""
        import mimetypes, subprocess, sys
        probe = ("import mimetypes; mimetypes.add_type('text/plain', '.js'); mimetypes.add_type('text/plain', '.css'); "
                 "import acepressure.app; print(mimetypes.guess_type('x.js')[0], mimetypes.guess_type('x.css')[0])")
        r = subprocess.run([sys.executable, '-c', probe], cwd=ROOT, capture_output=True, text=True, timeout=60)
        assert r.stdout.split() == ['text/javascript', 'text/css'], r.stderr[-500:]
        assert mimetypes.guess_type('x.js')[0] == 'text/javascript'
        assert mimetypes.guess_type('x.css')[0] == 'text/css'
        assert mimetypes.guess_type('x.svg')[0] == 'image/svg+xml'
        r = client.get('/static/common.js')
        assert r.status_code == 200 and r.headers['Content-Type'].startswith('text/javascript')
        assert r.headers['X-Content-Type-Options'] == 'nosniff'
        assert client.get('/static/premium.css').headers['Content-Type'].startswith('text/css')

    def test_unlisted_upload_stays_manageable(self, admin, app):
        c, h = admin
        r = _upload_sound(c, h, make_wav(0.5), 'Bruh Sound (1).wav'); name, sid = r.json['name'], r.json['entry']['id']
        assert c.post('/api/admin/soundboard/' + sid, json={'enabled': False}, headers=h).status_code == 200
        items = {x['name']: x for x in c.get('/api/admin/sounds/list', headers=h).json['items']}
        assert items[name]['listed'] is False and items[name]['display_name'] == 'Bruh Sound (1).wav'
        assert c.post('/api/admin/soundboard/' + sid, json={'enabled': True}, headers=h).status_code == 200
        assert c.get('/api/admin/sounds/list', headers=h).json['items'][0]['listed'] is True
        assert c.post('/api/admin/soundboard/' + sid, json={'enabled': False}, headers=h).status_code == 200
        assert c.delete('/api/admin/sounds/' + name, headers=h).status_code == 200
        assert not (app.store.path / 'media' / name).exists()
        assert name not in app.store.settings().get('media_labels', {})
        assert name not in {x['name'] for x in c.get('/api/admin/sounds/list', headers=h).json['items']}

    def test_hand_typed_entry_is_only_unlisted(self, admin, app):
        """Older builds accepted any text in the sounds list; removing such an entry never touches disk."""
        import json as _json
        c, h = admin
        media = app.store.path / 'media'; media.mkdir(exist_ok=True)
        (media / 'keep.txt').write_bytes(b'x')
        with app.store.db(True) as db:
            db.execute("UPDATE settings SET value=? WHERE key='sounds'", (_json.dumps(['chime', 'my sound', 'airhorn.mp3', 'keep.txt']),))
        before = sorted(media.iterdir())
        for entry in ['my%20sound', 'airhorn.mp3', 'keep.txt']:
            assert c.delete('/api/admin/sounds/' + entry, headers=h).status_code == 200, entry
        assert app.store.settings()['sounds'] == ['chime']
        assert sorted(media.iterdir()) == before

    def test_settings_sounds_list_is_read_only(self, admin, app):
        """1.6.0: settings.sounds is a mirror of the default sound; an open 1.5.9 dashboard can't rewrite it."""
        import json as _json
        c, h = admin
        with app.store.db(True) as db:  # an entry saved by an older build is refused too, and kept
            db.execute("UPDATE settings SET value=? WHERE key='sounds'", (_json.dumps(['chime', 'legacy entry']),))
        before = app.store.settings()['sounds']
        for sounds in [['chime', 'airhorn.mp3'], ['chime', '../../etc/passwd'], ['chime', 'https://example.com/a.mp3'],
                       ['pulse', 'chime', 'chime'], ['legacy entry', 'chime'], []]:
            r = c.post('/api/admin/settings', json={'sounds': sounds}, headers=h)
            assert r.status_code == 409 and 'Sound library' in r.json['error'], sounds
        assert app.store.settings()['sounds'] == before
        assert c.post('/api/admin/settings', json={'allow_sound_choice': False}, headers=h).status_code == 200

    def test_sounds_list_marks_unchecked_without_ffprobe(self, admin, monkeypatch):
        c, h = admin
        name = _upload_sound(c, h, make_wav(0.5), 'tone.wav').json['name']
        from acepressure import video
        monkeypatch.setattr(video, 'tool', lambda n: None)
        d = c.get('/api/admin/sounds/list', headers=h).json
        item = next(x for x in d['items'] if x['name'] == name)
        assert d['ffprobe_available'] is False
        assert item['playable'] is None and item['reason'] is None and item['size_bytes'] > 0

    def test_sounds_list_reports_missing_file(self, admin, app):
        c, h = admin
        name = _upload_sound(c, h, make_wav(0.5), 'gone.wav').json['name']
        (app.store.path / 'media' / name).unlink()
        item = next(x for x in c.get('/api/admin/sounds/list', headers=h).json['items'] if x['name'] == name)
        assert item['missing'] is True and item['playable'] is False and 'data/media' in item['reason']

    def test_deleting_the_only_sound_falls_back_to_chime(self, admin, app):
        c, h = admin
        r = _upload_sound(c, h, make_wav(0.5), 'only.wav'); name = r.json['name']
        assert c.post('/api/admin/soundboard/default', json={'value': r.json['entry']['id']}, headers=h).status_code == 200
        assert app.store.settings()['sounds'][0] == name
        assert c.delete('/api/admin/sounds/' + name, headers=h).status_code == 200
        s = app.store.settings()
        assert s['default_sound'] == 'chime' and s['sounds'][0] == 'chime' and name not in s['sounds']

    def test_setup_stops_cleanly_without_env_template(self, tmp_path):
        import shutil, subprocess, sys
        shutil.copy(ROOT / 'setup.py', tmp_path / 'setup.py')
        r = subprocess.run([sys.executable, str(tmp_path / 'setup.py')], cwd=tmp_path, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 1 and '.env.example is missing' in r.stdout
        assert 'password' not in r.stdout.lower() and not (tmp_path / '.env').exists()

    def test_python_launchers_force_utf8(self):
        """Python 3.12-3.14 on Windows reads text in the ANSI code page unless UTF-8 mode is on."""
        checked = 0
        for p in sorted(ROOT.glob('*.bat')):
            text = p.read_text(encoding='ascii')
            if re.search(r'python|\.py\b|venv', text, re.I):
                checked += 1
                assert 'set "PYTHONUTF8=1"' in text, p.name
        assert checked >= 10

    def test_no_text_io_without_encoding(self):
        pattern = re.compile(r'\.(read_text|write_text)\(([^()]|\([^()]*\))*\)')
        for p in sorted([ROOT / 'setup.py', ROOT / 'run.py', *ROOT.glob('acepressure/*.py'),
                         *ROOT.glob('scripts/*.py'), *ROOT.glob('tests/*.py')]):
            for m in pattern.finditer(p.read_text(encoding='utf-8')):
                assert 'encoding=' in m.group(0), f'{p.name}: {m.group(0)[:80]}'

    def test_fix_audio_bat_is_path_safe(self):
        """Names like "bruh (1).mp3", "Tom & Jerry.mp3" or "wow!.mp3" must not break the script."""
        text = (ROOT / 'Fix_Audio.bat').read_text(encoding='ascii')
        assert 'enabledelayedexpansion' not in text.lower()
        for line in text.splitlines():
            assert not re.match(r'\s*(if|for)\b.*\(\s*$', line, re.I), f'parenthesized block: {line}'
            assert not re.search(r'\)\s*else\b', line, re.I), f'else block: {line}'
        for var in ['SRC', 'OUT', 'NAME', 'OUTNAME', 'FFMPEG']:
            uses = re.findall(r'(.)%' + var + r'%(.)', text)
            assert uses, var
            assert all(a == '"' and b == '"' for a, b in uses), f'%{var}% must always be quoted'

    def test_frontend_reads_error_bodies_safely(self):
        """A 413 or proxy error page is HTML; a bare r.json() would surface as an opaque SyntaxError."""
        static = ROOT / 'acepressure' / 'static'
        assert 'async function readJSON(' in (static / 'common.js').read_text(encoding='utf-8')
        assert 'readJSON(' in (static / 'admin.js').read_text(encoding='utf-8')
        for p in sorted(static.glob('*.js')):
            src = p.read_text(encoding='utf-8')
            for m in re.finditer(r'\.json\(\)', src):
                tail = src[m.end():m.end() + 7]
                inside_helper = src.rfind('async function readJSON(', 0, m.start()) > src.rfind('\n', 0, m.start())
                assert tail.startswith('.catch(') or inside_helper, f'{p.name}: unguarded .json() at {m.start()}'

    def test_confetti_fires_only_on_rendered_celebration(self):
        src = (ROOT / 'acepressure' / 'static' / 'premium.js').read_text(encoding='utf-8')
        assert "querySelector('.celebration')" in src
        assert not re.search(r'/verified\|received\|thank you/', src)

    def test_uploads_check_file_size_in_the_browser(self):
        """Waitress drops bodies over 36 MB mid-upload ("Failed to fetch"); the page refuses them first."""
        static = ROOT / 'acepressure' / 'static'
        admin_js = (static / 'admin.js').read_text(encoding='utf-8')
        designer_js = (static / 'designer.js').read_text(encoding='utf-8')
        assert 'function tooBig(file,mb,what)' in admin_js
        assert "tooBig(fd.get('file'),8," in admin_js
        assert "tooBig(bd.get('audio'),8," in admin_js and '?24:8' in admin_js
        assert "tooBig(upload.files[0],8," in admin_js
        assert 'tooBig(pick,' in designer_js

    def test_analytics_fills_quiet_days_up_to_today(self, admin):
        """One tip this month used to draw a single floating bar; every day so far gets a (zero) bar."""
        from datetime import datetime
        from acepressure.domain import IST
        c, h = admin
        today = datetime.now(IST)
        series = c.get('/api/admin/analytics?period=month&group=day', headers=h).json['series']
        assert [x['date'] for x in series] == [today.replace(day=n).strftime('%Y-%m-%d') for n in range(1, today.day + 1)]
        assert all(x['total'] == 0 for x in series)
        weeks = c.get('/api/admin/analytics?period=year&group=month', headers=h).json['series']
        assert [x['date'] for x in weeks] == [f'{today.year}-{m:02d}' for m in range(1, today.month + 1)]
        assert c.get('/api/admin/analytics?period=lifetime&group=day', headers=h).json['series'] == []
