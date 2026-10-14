"""Hinglish detection and SSML language-tagging tests for acepressure.tts_service.

Covers v1.3.0+ behaviour where SSML xml:lang is derived from the voice id and
Hindi-looking content wrapped in <lang xml:lang='hi-IN'> when the chosen voice
is English-primary (but not Multilingual).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from acepressure.tts_service import (
    build_ssml,
    has_devanagari,
    hinglish_score,
    is_hinglish,
    _voice_locale,
)


def test_detects_devanagari_text():
    assert has_devanagari('नमस्ते') is True
    assert has_devanagari('hello') is False
    assert has_devanagari('') is False


def test_hinglish_score_distinguishes_hindi_from_english():
    # All three tokens ('bhai', 'kya', 'hai') live in the romanized-Hindi set,
    # so the score should sit at the top of the range.
    assert hinglish_score('bhai kya hai') > 0.5
    # Pure English with no streamer loanwords collapses to zero.
    assert hinglish_score('hello world') == 0
    # Any Devanagari char short-circuits to the maximum score of 1.0.
    assert hinglish_score('नमस्ते जी') == 1.0


def test_is_hinglish_handles_empty_and_boundary_cases():
    # Pure English with no romanized-Hindi tokens stays below the 0.15 cutoff.
    # (avoid 'the' / 'stream' / 'live' / 'tip' — those are in the Hindi-roman set).
    assert is_hinglish('Hello everyone, welcome back') is False
    # Mixed romanized Hindi crosses the threshold comfortably.
    assert is_hinglish('GG bhai, kya baat hai') is True
    # Empty input must not crash and must not count as Hinglish.
    assert is_hinglish('') is False


def test_voice_locale_parses_azure_voice_ids():
    assert _voice_locale('hi-IN-SwaraNeural') == 'hi-IN'
    assert _voice_locale('en-US-AvaMultilingualNeural') == 'en-US'
    assert _voice_locale('en-IN-NeerjaNeural') == 'en-IN'


def test_voice_locale_fallback_and_bare_locale():
    # Garbage input falls back to the original hardcoded en-IN default.
    assert _voice_locale('bad voice') == 'en-IN'
    # Bare locale strings pass through unchanged via the leading-anchor match.
    assert _voice_locale('en-IN') == 'en-IN'
    # Empty / None also fall back without raising.
    assert _voice_locale('') == 'en-IN'
    assert _voice_locale(None) == 'en-IN'


def test_build_ssml_english_text_english_voice_has_no_lang_wrap():
    ssml = build_ssml('hello', 'en-IN-NeerjaNeural').decode('utf-8')
    assert "xml:lang='en-IN'" in ssml
    # No inner <lang ...> wrapper because the text is not Hinglish.
    assert '<lang' not in ssml


def test_build_ssml_hinglish_text_with_english_voice_wraps_as_hindi():
    ssml = build_ssml('kya bhai hai', 'en-IN-NeerjaNeural').decode('utf-8')
    # English-primary voice must engage the Hindi phoneme model via <lang>.
    assert "<lang xml:lang='hi-IN'>" in ssml
    assert '</lang>' in ssml


def test_build_ssml_hindi_voice_never_wraps():
    # The voice itself is Hindi, so wrapping would be redundant and is skipped.
    ssml = build_ssml('kya bhai hai', 'hi-IN-SwaraNeural').decode('utf-8')
    assert '<lang' not in ssml
    assert "xml:lang='hi-IN'" in ssml


def test_build_ssml_multilingual_voice_never_wraps():
    # MultilingualNeural voices code-switch natively — no manual wrap.
    ssml = build_ssml('kya bhai hai', 'en-US-AvaMultilingualNeural').decode('utf-8')
    assert '<lang' not in ssml
    assert "xml:lang='en-US'" in ssml


def test_build_ssml_escapes_html_entities():
    ssml = build_ssml('<script>', 'en-IN-NeerjaNeural').decode('utf-8')
    # Raw angle brackets must be XML-escaped so operators cannot inject SSML.
    assert '&lt;script&gt;' in ssml
    assert '<script>' not in ssml
