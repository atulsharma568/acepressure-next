"""Premium UI integration tests (AcePressure 1.4.1).

Covers the 1.3.0 Hinglish detection helpers + the premium.css/premium.js
assets added across the public, admin, and OBS overlay templates. These are
the user-facing "polish" layer: if any of them fail to load, the site either
loses its brand look or breaks the Hinglish-aware browser TTS fallback.
"""
import re


# ---------------------------------------------------------------------------
# Static asset payloads: premium.css / premium.js
# ---------------------------------------------------------------------------

def test_premium_css_served_with_tokens_and_glass(client):
    """premium.css must be reachable and carry the design-token marker + glass look."""
    r = client.get('/static/premium.css')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    # Design-token root is the hinge of the whole premium theme.
    assert '--font-sans' in body, 'premium.css is missing the --font-sans design token'
    # The premium look is explicitly glass-morphism; either the keyword or the
    # browser property must appear or the "premium" look is gone.
    assert ('glass' in body) or ('backdrop-filter' in body), \
        'premium.css lost its glass-morphism styling'
    # Content-Type should be CSS (Flask serves .css as text/css).
    assert 'css' in r.headers.get('Content-Type', '').lower()


def test_premium_js_exposes_confetti_api(client):
    """premium.js must expose the confetti burst used by public + overlay flows."""
    r = client.get('/static/premium.js')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    # window.aceConfetti is the public hook; spawnConfetti is the internal fn.
    assert 'aceConfetti' in body, 'premium.js no longer exposes window.aceConfetti'
    assert 'spawnConfetti' in body, 'premium.js is missing the spawnConfetti engine'
    assert 'javascript' in r.headers.get('Content-Type', '').lower()


# ---------------------------------------------------------------------------
# Public tipping page: /tip/acepressure
# ---------------------------------------------------------------------------

def test_tip_page_loads_both_stylesheets(client):
    """The public tipping page must load the base + premium stylesheets together."""
    r = client.get('/tip/acepressure')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    # Both link tags must be present; premium layers *on top of* style.css,
    # so dropping either breaks the page look.
    assert re.search(r'<link[^>]+href="/static/style\.css"', html), \
        'tip page is missing /static/style.css link'
    assert re.search(r'<link[^>]+href="/static/premium\.css"', html), \
        'tip page is missing /static/premium.css link'


def test_tip_page_loads_premium_js(client):
    """The public tipping page must also pull in premium.js (confetti etc.)."""
    r = client.get('/tip/acepressure')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert re.search(r'<script[^>]+src="/static/premium\.js"', html), \
        'tip page is not loading /static/premium.js'


def test_tip_page_csp_is_strict_and_premium_js_external(client):
    """CSP must stay strict; premium.js has to be an external same-origin file."""
    r = client.get('/tip/acepressure')
    assert r.status_code == 200
    csp = r.headers.get('Content-Security-Policy', '')
    # default-src 'self' and script-src 'self' guarantee external-only JS.
    assert "default-src 'self'" in csp, 'CSP default-src is not self'
    assert "script-src 'self'" in csp, 'CSP script-src is not self (would allow inline)'
    html = r.get_data(as_text=True)
    # Spot-check that premium.js is loaded as a same-origin external file, not inline.
    # If someone accidentally inlined the script it would violate script-src 'self'.
    assert '<script src="/static/premium.js"' in html, \
        'premium.js must be loaded as an external /static/ file to satisfy CSP'


# ---------------------------------------------------------------------------
# Admin control room: /admin
# ---------------------------------------------------------------------------

def test_admin_page_loads_premium_assets(client):
    """The admin control room page must also wear the premium theme."""
    r = client.get('/admin')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert '/static/premium.css' in html, 'admin page is missing premium.css'
    assert '/static/premium.js' in html, 'admin page is missing premium.js'


# ---------------------------------------------------------------------------
# OBS overlays: /overlay/<kind>
# ---------------------------------------------------------------------------

def test_overlay_alert_loads_premium_assets(client):
    """OBS alert overlay must load premium.css + premium.js so alerts match the brand."""
    r = client.get('/overlay/alert')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert '/static/premium.css' in html, 'overlay/alert is missing premium.css'
    assert '/static/premium.js' in html, 'overlay/alert is missing premium.js'


def test_overlay_goal_still_renders(client):
    """Goal overlay must still render 200 after the premium rework."""
    r = client.get('/overlay/goal')
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    # Sanity check: the overlay template body should at least carry the stage element.
    assert 'id="stage"' in html, 'overlay/goal lost its #stage mount point'


# ---------------------------------------------------------------------------
# Hinglish helpers (1.3.0): common.js + overlay.js
# ---------------------------------------------------------------------------

def test_common_js_exposes_hinglish_helpers(client):
    """common.js must still expose isHinglish and pickVoiceForText (added in 1.3.0)."""
    r = client.get('/static/common.js')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'isHinglish' in body, 'common.js lost the isHinglish helper'
    assert 'pickVoiceForText' in body, 'common.js lost the pickVoiceForText helper'
    # Sanity: hasDevanagari and the HINGLISH_WORDS set should also still be present.
    assert 'hasDevanagari' in body, 'common.js lost hasDevanagari'
    assert 'HINGLISH_WORDS' in body, 'common.js lost HINGLISH_WORDS'


def test_overlay_js_uses_pick_voice_for_text(client):
    """overlay.js must route browser TTS through pickVoiceForText, not raw voice lookup."""
    r = client.get('/static/overlay.js')
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert 'pickVoiceForText' in body, \
        'overlay.js is no longer using pickVoiceForText (Hinglish fallback is broken)'
