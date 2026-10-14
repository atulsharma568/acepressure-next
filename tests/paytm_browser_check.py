"""Disposable Chromium check for diagnostic UI and its no-alert boundary."""
import os, sys, tempfile, threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from acepressure.app import create_app
from acepressure.domain import now, IST
from datetime import datetime
from werkzeug.security import generate_password_hash
from waitress import create_server
from playwright.sync_api import sync_playwright, expect

with tempfile.TemporaryDirectory() as temp:
    app=create_app(dict(DATA_DIR=temp,SECRET_KEY='s'*48,OVERLAY_TOKEN='o'*48,
        BRIDGE_TOKEN='b'*48,ADMIN_PASSWORD_HASH=generate_password_hash('test-password'),
        DEMO_MODE=True,PUBLIC_BASE_URL='http://127.0.0.1:8768'))
    server=create_server(app,host='127.0.0.1',port=8768)
    threading.Thread(target=server.run,daemon=True).start()
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=os.getenv('ACE_TEST_BROWSER') or None,args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1280,'height':900})
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:8768/admin')
        page.locator('[name=password]').fill('test-password')
        page.get_by_role('button',name='Sign in',exact=True).click()
        expect(page.locator('#shell')).to_be_visible()
        page.goto('http://127.0.0.1:8768/admin/paytm-test')
        expect(page.locator('#status')).to_have_text('Capture stopped')
        page.locator('#start').click()
        expect(page.locator('#status')).to_contain_text('Capture active')
        token=page.locator('#token').input_value()
        assert len(token)>32
        response=page.request.post('http://127.0.0.1:8768/api/bridge/paytm-test',
            headers={'Authorization':'Bearer '+token},data={'text':
            'Received ₹11.37 from Test Sender\nDeposited in your Example Bank - 0000 on 10 October at 12:29 AM'})
        assert response.ok and response.json()['verified'] is False
        expect(page.locator('#results')).to_contain_text('₹11.37',timeout=6000)
        assert page.locator('#token').get_attribute('type')=='password'
        page.locator('#stop').click()
        expect(page.locator('#status')).to_have_text('Capture stopped')
        assert page.locator('#token').input_value()==''
        page.locator('#matching').check()
        page.locator('#start').click()
        expect(page.locator('#status')).to_contain_text('Demo matching active')
        token=page.locator('#token').input_value()
        clock=now();stamp=clock//60*60
        with app.store.db(True) as db:db.execute('INSERT INTO sessions VALUES(?,?,?,NULL)',('demo-session','Browser test',stamp-120))
        tip=app.store.create_tip({'name':'Demo Match','amount':100,'message':'Matching test'},True)
        with app.store.db(True) as db:db.execute('UPDATE tips SET created=? WHERE id=?',(stamp-60,tip['id']))
        dt=datetime.fromtimestamp(stamp,IST)
        text=f"Received ₹{tip['requested_paise']/100:.2f} from Demo Sender Deposited in your Example Bank - 0000 on {dt.day} {dt.strftime('%B')} at {dt.strftime('%I:%M %p')}"
        r=page.request.post('http://127.0.0.1:8768/api/bridge/paytm-test',headers={'Authorization':'Bearer '+token},data={'text':text})
        assert r.json()['outcome']=='demo_matched'
        expect(page.locator('#results')).to_contain_text('demo_matched',timeout=6000)
        overlay=browser.new_page()
        overlay.goto('http://127.0.0.1:8768/overlay/alert?layout=horizontal&audio=0&key='+'o'*48)
        expect(overlay.locator('.test-tag')).to_have_text('DEMO • PAYTM NOTIFICATION MATCH',timeout=6000)
        expect(overlay.locator('.name')).to_have_text('Demo Match')
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors,errors
        browser.close()
    server.close()
print('PASS: login, capture start/stop, authenticated ingest, live display, masked token, demo match and TEST overlay, mobile width; zero JS errors')
