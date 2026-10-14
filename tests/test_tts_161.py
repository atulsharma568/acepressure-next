"""1.6.1 regressions; fake providers exercise their WAV API contract."""
import sys
import types
import wave
import pytest
from acepressure.tts_service import is_hinglish, maybe_transliterate
from acepressure import piper_tts_service as piper
from acepressure.domain import Problem

@pytest.mark.parametrize('text', [
    'I play the main role', 'Put the mouse on the mat',
    'That was a nice clutch', 'Enjoy the live stream and donate a tip',
    'A mere detail', 'Upgrade the RAM',
])
def test_english_is_not_hindi(text):
    assert not is_hinglish(text)
    assert maybe_transliterate(text, 'hi-IN-MadhurNeural') == text

def test_mixed_preserves_homographs():
    # 1.6.2 converts "tu" inside a Hindi sentence; "main" after "mera" is still the English word ("my main").
    assert maybe_transliterate('bhai tu mera main duelist hai', 'hi-IN-MadhurNeural') == 'भाई तू मेरा main duelist है'

def test_hindi_original_and_roman():
    original = 'भाई क्या खेल रहा है'
    assert maybe_transliterate(original, 'hi-IN-SwaraNeural') == original
    assert maybe_transliterate('bhai kya khel raha hai', 'hi-IN-SwaraNeural') == original

@pytest.mark.parametrize('empty', [False, True])
def test_piper_wav_contract(tmp_path, monkeypatch, empty):
    loaded = []
    class Voice:
        @staticmethod
        def load(path):
            loaded.append(path)
            return Voice()
        def synthesize_wav(self, text, wav_file):
            wav_file.setparams((1, 2, 22050, 0, 'NONE', 'not compressed'))
            wav_file.writeframes(b'' if empty else b'\0\0' * 2205)
    monkeypatch.setitem(sys.modules, 'piper', types.SimpleNamespace(PiperVoice=Voice))
    monkeypatch.setattr(piper, '_LOADED_VOICES', {})
    for mode in ['live', 'demo']:
        folder = tmp_path / mode
        piper.models_dir(folder).joinpath('hi_IN-test-medium.onnx').touch()
        if empty:
            with pytest.raises(Problem):
                piper.synthesize(folder, 'bhai kya', 'hi_IN-test-medium')
            assert not list((folder / 'speech').glob('*.wav'))
        else:
            output = piper.synthesize(folder, 'bhai kya', 'hi_IN-test-medium')
            with wave.open(str(output)) as wav_file:
                assert wav_file.getnframes() == 2205
            assert piper.synthesize(folder, 'bhai kya', 'hi_IN-test-medium') == output
    assert len(loaded) == 2
    assert loaded[0] != loaded[1]
