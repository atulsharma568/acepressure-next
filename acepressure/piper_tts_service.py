"""Local, offline, open-source Piper TTS backend.

Uses the `piper-tts` Python package with ONNX voice models stored under
`<DATA_DIR>/piper-voices/`. Zero network calls at synthesis time, zero cost,
runs entirely on CPU.

Operator onboarding:
    1. Install_Piper.bat             → installs piper-tts into .venv
    2. scripts/download_piper_voices → downloads starter Hindi + English voices
    3. Admin → TTS → Find and test real voices: Voice source Piper → Detect available voices → Use selected voices
       (or If the voice service fails → a Piper voice → Save backup voice, to keep the main voice)

Hinglish handling: Piper has no SSML or <lang> wrapping. Multilingual mixing
is handled at the engine-selection layer (tts_service.synthesize dispatches to
a Hindi voice when `is_hinglish(text)` is true, if one is available). Pure
Devanagari text in a Hindi voice sounds great. Roman Hinglish ("bhai", "kya")
read by a Hindi voice is approximate but usually comprehensible.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import wave
from pathlib import Path

from .domain import Problem

LOCK = threading.Lock()
_LOADED_VOICES = {}  # id -> PiperVoice (loaded ONNX kept in memory for reuse)


def _have_piper():
    try:
        import piper  # noqa: F401
        return True
    except ImportError:
        return False


def _install_hint():
    return Problem(
        'Piper TTS is not installed. Run Install_Piper.bat to add it and download starter voices.',
        503,
    )


def models_dir(directory: Path) -> Path:
    """Return (and create) the folder where .onnx voice models live."""
    folder = Path(directory) / 'piper-voices'
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def catalog(directory: Path):
    """Enumerate .onnx voices under models_dir(directory).

    Each .onnx file is expected to have a sibling .onnx.json metadata file
    (as shipped by rhasspy/piper-voices). If metadata is missing, we fall back
    to the filename.
    """
    if not _have_piper():
        raise _install_hint()
    folder = models_dir(directory)
    out = []
    for onnx in sorted(folder.glob('*.onnx')):
        meta_path = onnx.with_suffix('.onnx.json')
        locale, dataset, quality = '', onnx.stem, ''
        if meta_path.exists():
            try:
                data = json.loads(meta_path.read_text(encoding='utf-8'))
                lang = data.get('language', {})
                family = lang.get('family') or lang.get('code', '').split('_')[0]
                country = lang.get('country_code') or (lang.get('code', '').split('_')[1] if '_' in lang.get('code', '') else '')
                if family and country:
                    locale = f"{family.lower()}-{country.upper()}"
                elif family:
                    locale = family.lower()
                dataset = data.get('dataset', dataset)
                quality = data.get('audio', {}).get('quality', '')
            except Exception:
                pass
        if not locale:
            # Try to infer locale from standard naming like hi_IN-pratham-medium
            m = re.match(r'^([a-z]{2})_([A-Z]{2})', onnx.stem)
            if m:
                locale = f"{m.group(1)}-{m.group(2)}"
            else:
                locale = 'en-US'
        if locale.startswith('hi'):
            tag = ' · हिंदी (OFFLINE)'
        else:
            tag = ' · OFFLINE'
        label = f"{locale} · {dataset}{(' · ' + quality) if quality else ''}{tag}"
        out.append({'id': onnx.stem, 'label': label, 'gender': 'Any', 'locale': locale})
    return out


def synthesize(directory: Path, text: str, voice_id: str) -> Path:
    """Synthesize `text` with Piper and return a cached WAV path.

    Loaded PiperVoice objects are kept in memory keyed by absolute model path so the
    second call for the same voice doesn't re-load the ONNX model.

    Hinglish fix: when the selected voice is a hi-* Piper model, Roman Hindi
    tokens ("bhai", "kya", "tha") are transliterated to Devanagari before
    synthesis. Piper's Hindi models produce much cleaner audio for Devanagari
    input than for Latin-script Hinglish.
    """
    if not _have_piper():
        raise _install_hint()
    from .tts_service import maybe_transliterate

    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,120}', voice_id):
        raise Problem('Invalid Piper voice identifier.', 400)
    if not isinstance(text, str) or not text.strip():
        raise Problem('Nothing to say.', 400)

    folder = models_dir(directory)
    onnx_path = folder / f'{voice_id}.onnx'
    if not onnx_path.exists():
        raise Problem(
            f'Piper model "{voice_id}" not found under data/piper-voices/. '
            'Run scripts/download_piper_voices.py to install starter voices.',
            503,
        )

    final_text = maybe_transliterate(text, voice_id)

    speech_folder = directory / 'speech'
    speech_folder.mkdir(exist_ok=True)
    # 'piper-v3' bumps the cache key when transliteration behavior changes.
    cache_key = hashlib.sha256((voice_id + '\0' + final_text + '\0piper-v3').encode()).hexdigest()
    out_path = speech_folder / f'piper-{cache_key}.wav'

    with LOCK:
        if out_path.exists():
            return out_path
        try:
            from piper import PiperVoice
            model_key = str(onnx_path.resolve())
            voice = _LOADED_VOICES.get(model_key)
            if voice is None:
                voice = PiperVoice.load(str(onnx_path))
                # Keep up to 4 voices in memory. If we're at the limit, drop one.
                if len(_LOADED_VOICES) >= 4:
                    _LOADED_VOICES.pop(next(iter(_LOADED_VOICES)))
                _LOADED_VOICES[model_key] = voice
            with wave.open(str(out_path), 'wb') as wf:
                write_wav = getattr(voice, 'synthesize_wav', None)  # piper-tts 1.3+
                if callable(write_wav):
                    write_wav(final_text, wf)
                else:  # piper-tts 1.2 and older, until Install_Piper.bat is run again
                    voice.synthesize(final_text, wf)
        except Exception as e:
            out_path.unlink(missing_ok=True)
            raise Problem(f'Piper synthesis failed ({type(e).__name__}).', 503)

    # Validate the output has at least ~0.1 s of audio.
    try:
        with wave.open(str(out_path), 'rb') as wf:
            dur = wf.getnframes() / max(wf.getframerate(), 1)
            if dur < 0.05:
                out_path.unlink(missing_ok=True)
                raise Problem('Piper produced an empty audio clip.', 503)
    except Problem:
        raise
    except Exception:
        out_path.unlink(missing_ok=True)
        raise Problem('Piper produced an invalid WAV clip.', 503)

    return out_path
