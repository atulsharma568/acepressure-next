"""Optional real-browser regression: python tests/browser_tts_161.py."""
import sys
import tempfile
import threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright
from acepressure.app import create_app

with tempfile.TemporaryDirectory() as folder:
    app = create_app(dict(TESTING=True, DATA_DIR=folder, SECRET_KEY='s'*48,
        BRIDGE_TOKEN='b'*48, OVERLAY_TOKEN='o'*48,
        ADMIN_PASSWORD_HASH=generate_password_hash('test-password-123'),
        DEMO_MODE=True, ENV_FILE=str(Path(folder)/'absent.env')))
    server = make_server('127.0.0.1', 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=['--no-sandbox'])
            page = browser.new_page()
            page.goto(f'http://127.0.0.1:{server.server_port}/admin')
            page.locator('input[name=password]').fill('test-password-123')
            page.locator('#login-form button').click()
            page.locator('#nav').get_by_role('button', name='TTS', exact=True).click()
            sample = page.locator('input[name=sample]')
            sample.fill('भाई क्या खेल रहा है')
            page.get_by_role('button', name='Save settings', exact=True).click()
            page.wait_for_timeout(800)
            assert sample.input_value() == 'भाई क्या खेल रहा है'
            sample.fill('bhai kya khel raha hai')
            page.locator('#nav').get_by_role('button', name='Overview', exact=True).click()
            page.locator('#nav').get_by_role('button', name='TTS', exact=True).click()
            assert sample.input_value() == 'bhai kya khel raha hai'
            result = page.evaluate("""() => ({
                english: maybeTransliterate('I play the main role', {lang:'hi-IN'}),
                hindi: maybeTransliterate('bhai kya khel raha hai', {lang:'hi-IN'}),
                detected: isHinglish('Enjoy the live stream and donate a tip')
            })""")
            assert result == {'english':'I play the main role',
                              'hindi':'भाई क्या खेल रहा है', 'detected':False}
            browser.close()
            print('PASS: save/redraw/navigation preserve sample; browser conversion protects English.')
    finally:
        server.shutdown()
