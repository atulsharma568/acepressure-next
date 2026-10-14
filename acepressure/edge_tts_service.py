"""Free Edge TTS backend — Microsoft Edge voices via unauthenticated endpoint.

Uses the `edge-tts` Python package. Same Neural voices as paid Azure Cognitive
Services Speech (including Multilingual Neural for Hinglish code-switching),
but with NO API key, NO account, NO credit card. Technically an unofficial
endpoint; Microsoft could change it at any time, but it has been stable for
years and is widely used by open-source projects.

Multilingual voices (e.g. `en-US-AvaMultilingualNeural`) auto-detect Hindi
mid-sentence, so Hinglish is handled natively without SSML <lang> wrapping.
Pure hi-IN voices speak Hindi natively. English voices fall back to the
`<lang hi-IN>` wrapping that the Azure path uses (shared via build_ssml, but
edge-tts also accepts raw text with voice-provided locale handling).
"""
from __future__ import annotations

import asyncio
import hashlib
import re
import threading
import time
from pathlib import Path

from .domain import Problem

LOCK = threading.Lock()
TOTAL_TIMEOUT = 12  # seconds for one clip (1.6.4)


def _timeouts(module):
    """Shorter connect and receive limits, on edge-tts versions that accept them (6.1.x may not)."""
    try:
        import inspect
        params = inspect.signature(module.Communicate.__init__).parameters
    except (TypeError, ValueError):
        return {}
    return {k: v for k, v in (('connect_timeout', 5), ('receive_timeout', 10)) if k in params}
_CACHED_VOICES = None  # tiny in-process cache so admin UI doesn't re-fetch every tab click
_CACHED_VOICES_AT = 0


def _have_edge_tts():
    try:
        import edge_tts  # noqa: F401
        return True
    except ImportError:
        return False


def _install_hint():
    return Problem(
        'Edge TTS is not installed. Run Install_Edge_TTS.bat to add it to your .venv.',
        503,
    )


def catalog():
    """Return the Edge TTS voice catalog filtered for Indian-streamer relevance.

    Keeps:
      - every hi-IN voice (tagged "हिंदी (FREE)")
      - every en-IN voice (tagged "FREE")
      - every Multilingual Neural voice regardless of base locale (tagged "HINGLISH-READY (FREE)")

    Sorted: Multilingual first → hi-IN → en-IN → others. This matches the
    Azure catalog sort order so the admin UI feels consistent across engines.
    """
    global _CACHED_VOICES, _CACHED_VOICES_AT
    if not _have_edge_tts():
        raise _install_hint()

    # Cache catalog for 10 minutes — edge-tts hits a network endpoint each call.
    if _CACHED_VOICES and time.time() - _CACHED_VOICES_AT < 600:
        return _CACHED_VOICES

    import edge_tts
    try:
        voices = asyncio.run(edge_tts.list_voices())
    except Exception:
        raise Problem('Could not fetch Edge TTS voice list. Check your internet connection.', 503)

    out = []
    for v in voices:
        short = v.get('ShortName', '')
        locale = v.get('Locale', '')
        gender = v.get('Gender', '')
        if gender not in ('Male', 'Female'):
            continue
        is_multi = 'Multilingual' in short
        keep = is_multi or locale in ('en-IN', 'hi-IN')
        if not keep:
            continue
        if is_multi:
            tag = ' · HINGLISH-READY (FREE)'
        elif locale == 'hi-IN':
            tag = ' · हिंदी (FREE)'
        else:
            tag = ' · FREE'
        friendly = v.get('FriendlyName') or short
        # FriendlyName is usually "Microsoft Server Speech Text to Speech Voice (en-US, AvaMultilingualNeural)"
        # Shorten by trimming the Microsoft prefix.
        friendly = re.sub(r'^Microsoft (Server )?Speech Text to Speech Voice ', '', friendly).strip()
        label = f"{gender} · {locale} · {friendly[:60]}{tag}"
        out.append({'id': short, 'label': label, 'gender': gender, 'locale': locale})

    out.sort(key=lambda v: (
        0 if 'Multilingual' in v['id'] else 1 if v['locale'] == 'hi-IN' else 2,
        v['id'],
    ))

    _CACHED_VOICES = out
    _CACHED_VOICES_AT = time.time()
    return out


def synthesize(directory: Path, text: str, voice: str) -> Path:
    """Synthesize `text` with Edge TTS and return a cached MP3 path.

    Cache key hashes (voice, final_text, 'edge-v2') so the same message with the
    same voice reuses the file. 'edge-v2' bumps the key when transliteration
    semantics change. Old entries older than 24 h are purged lazily.

    Hinglish fix: if the voice can pronounce Hindi (hi-* locale or Multilingual
    Neural), Roman Hindi tokens are transliterated to Devanagari BEFORE handing
    the text to edge-tts. Without this, "bhai"/"kya"/"tha" come out as "bai"/
    "kiya"/"the" because Edge TTS wraps raw text in its own auto-SSML and reads
    Latin letters with English phonetics even on Hindi voices.
    """
    if not _have_edge_tts():
        raise _install_hint()
    from .tts_service import maybe_transliterate

    if not re.fullmatch(r'[A-Za-z0-9:_-]{3,100}', voice):
        raise Problem('Invalid Edge TTS voice identifier.', 400)
    if not isinstance(text, str) or not text.strip():
        raise Problem('Nothing to say.', 400)

    final_text = maybe_transliterate(text, voice)

    folder = directory / 'speech'
    folder.mkdir(exist_ok=True)
    cache_key = hashlib.sha256((voice + '\0' + final_text + '\0edge-v2').encode()).hexdigest()
    path = folder / f'edge-{cache_key}.mp3'

    with LOCK:
        # Lazy TTL cleanup: purge any edge- or azure- WAV/MP3 older than 24 h.
        now = time.time()
        for old in folder.glob('edge-*.mp3'):
            try:
                if old.stat().st_mtime < now - 86400:
                    old.unlink(missing_ok=True)
            except Exception:
                pass
        if path.exists():
            return path
        try:
            import edge_tts
            async def _save():
                comm = edge_tts.Communicate(final_text, voice, **_timeouts(edge_tts))
                await comm.save(str(path))
            # 1.6.4: a stalled request gives up inside the OBS page's 20 s, leaving time for the backup voice, and no
            # longer holds up the next alert's voice behind this lock.
            async def _limited():
                await asyncio.wait_for(_save(), timeout=TOTAL_TIMEOUT)
            asyncio.run(_limited())
        except Exception:
            # Never log the message content or voice; keep the error generic.
            path.unlink(missing_ok=True)
            raise Problem('Edge TTS synthesis failed. Check your internet connection and voice ID.', 503)

        # Sanity-check: Edge TTS returning a 0-byte file means the voice ID was wrong.
        try:
            if path.stat().st_size < 400:
                path.unlink(missing_ok=True)
                raise Problem('Edge TTS returned an empty audio clip. Verify the voice ID.', 503)
        except FileNotFoundError:
            raise Problem('Edge TTS failed to write an audio file.', 503)

        return path
