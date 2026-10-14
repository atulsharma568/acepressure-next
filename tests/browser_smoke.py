"""Runs a disposable server and Chromium acceptance flows; never contacts a bank."""
import json,re,sys,tempfile,threading,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from werkzeug.security import generate_password_hash
from waitress import create_server
from playwright.sync_api import sync_playwright,expect
from acepressure.app import create_app

def main():
    with tempfile.TemporaryDirectory() as temp:
        app=create_app(dict(DATA_DIR=temp,SECRET_KEY='s'*48,OVERLAY_TOKEN='o'*48,BRIDGE_TOKEN='b'*48,ADMIN_PASSWORD_HASH=generate_password_hash('acceptance-password'),DEMO_MODE=True,PUBLIC_BASE_URL='http://127.0.0.1:8767'))
        server=create_server(app,host='127.0.0.1',port=8767,threads=12);threading.Thread(target=server.run,daemon=True).start()
        shots=Path(__file__).resolve().parents[1]/'docs'/'screenshots';shots.mkdir(exist_ok=True)
        errors=[];checks=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'])
            context=browser.new_context(viewport={'width':1440,'height':1080})
            public=context.new_page();public.on('pageerror',lambda e:errors.append(str(e)))
            public.goto('http://127.0.0.1:8767/');expect(public.locator('#pay-button')).to_be_enabled();public.screenshot(path=str(shots/'public-desktop.png'),full_page=True)
            admin=context.new_page();admin.on('pageerror',lambda e:errors.append(str(e)))
            admin.goto('http://127.0.0.1:8767/admin');admin.locator('[name=password]').fill('acceptance-password');admin.get_by_role('button',name='Sign in',exact=True).click();expect(admin.locator('#shell')).to_be_visible()
            admin.once('dialog',lambda dialog:dialog.accept('Acceptance stream'));admin.get_by_role('button',name='Start stream session').first.click();expect(admin.get_by_role('button',name='End session')).to_be_visible();checks.append('Admin login and start session')
            public.locator('[name=name]').fill('QA Supporter');public.locator('[name=email]').fill('qa@example.test');public.locator('[name=message]').fill('Clean shot. Keep going!');public.locator('#pay-button').click();expect(public.locator('#payment')).to_be_visible();expect(public.locator('.pending')).to_be_visible();checks.append('Viewer pending checkout; no payment QR in demo')
            admin.get_by_role('button',name='Pending payments',exact=True).click();expect(admin.get_by_role('button',name='Simulate payment')).to_be_visible();admin.get_by_role('button',name='Simulate payment').click()
            # The tip page checks every 20 s by itself. The Simulate button goes once the simulator has answered; then ask the page to check now (30 s still covers its next automatic check).
            expect(admin.get_by_role('button',name='Simulate payment')).to_have_count(0,timeout=15000);status=public.get_by_role('button',name='Check payment status')
            if status.is_visible():status.click()
            expect(public.get_by_role('heading',name=re.compile(r'^Thank you,'))).to_be_visible(timeout=30000);checks.append('Admin simulator → verified public success')
            overlay=context.new_page();overlay.on('pageerror',lambda e:errors.append(str(e)));overlay.goto('http://127.0.0.1:8767/overlay/alert?layout=horizontal&audio=0&key='+'o'*48);expect(overlay.locator('.alert')).to_be_visible(timeout=7000);expect(overlay.locator('.alert .name')).to_have_text('QA Supporter');overlay.screenshot(path=str(shots/'alert-horizontal.png'));checks.append('Verified horizontal overlay alert')
            vertical=context.new_page();vertical.set_viewport_size({'width':1080,'height':1920});vertical.goto('http://127.0.0.1:8767/overlay/alert?layout=vertical&audio=0&key='+'o'*48);expect(vertical.locator('.alert')).to_be_visible(timeout=7000);vertical.screenshot(path=str(shots/'alert-vertical.png'));checks.append('Verified vertical overlay alert')
            admin.get_by_role('button',name='Goals',exact=True).click();admin.get_by_role('button',name='Create a goal').click();admin.locator('.dialog [name=title]').fill('Weekly support');admin.locator('.dialog [name=target]').fill('2000');admin.get_by_role('button',name='Save goal',exact=True).click();expect(admin.locator('.goal-preview')).to_be_visible();checks.append('Goal created through dashboard')
            goal=context.new_page();goal.goto('http://127.0.0.1:8767/overlay/goal?key='+'o'*48);expect(goal.locator('.goal-line')).to_contain_text('₹100 / ₹2,000');checks.append('Goal live progress matches verified tip')
            for name in ['Overview','Transactions','Pending payments','Supporters','Leaderboards','Goals','Alertbox','TTS','Sound library','Stream sessions','Analytics','OBS','Settings','Audit']:
                admin.get_by_role('button',name=name,exact=True).first.click();expect(admin.locator('.page-title h2')).to_have_text(name);admin.wait_for_timeout(150)
                assert not admin.locator('#content > .error').count(),name
            checks.append('All 14 admin sections render')
            admin.get_by_role('button',name='Supporters',exact=True).click();admin.get_by_role('button',name='History',exact=True).click();expect(admin.locator('.dialog')).to_contain_text('Clean shot. Keep going!');admin.get_by_role('button',name='Close',exact=True).click();checks.append('Supporter history')
            admin.get_by_role('button',name='Overview',exact=True).click();admin.screenshot(path=str(shots/'dashboard.png'),full_page=True)
            dock=context.new_page();dock.goto('http://127.0.0.1:8767/obs/activity');expect(dock.locator('.activity-item')).to_be_visible();checks.append('Authenticated OBS dock')
            mobile=browser.new_page(viewport={'width':390,'height':844},is_mobile=True,device_scale_factor=1);mobile.goto('http://127.0.0.1:8767/');expect(mobile.locator('#pay-button')).to_be_enabled();mobile.screenshot(path=str(shots/'public-mobile.png'),full_page=True);assert mobile.evaluate('document.documentElement.scrollWidth <= innerWidth');checks.append('390px mobile layout without horizontal overflow')
            # A hostile viewer name/message must remain inert in every rendered surface.
            page=context.new_page();page.goto('http://127.0.0.1:8767/');page.locator('[name=name]').fill('<img src=x onerror=alert(1)>');page.locator('[name=message]').fill('<script>window.xss=true</script>');page.locator('#pay-button').click();expect(page.locator('.pending')).to_be_visible();assert not page.evaluate('!!window.xss');checks.append('Hostile input remains text')
            assert not errors,errors
            browser.close()
        server.close()
        report={'checks':checks,'javascript_errors':errors,'note':'Chromium on Linux; iPhone, Windows SAPI, OBS and live bank payments require device acceptance.'}
        (shots.parent/'browser-test-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))
if __name__=='__main__':main()
