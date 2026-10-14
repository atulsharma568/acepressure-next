"""Disposable browser acceptance of review, approval and real checkout rendering."""
import os,re,sys,tempfile,threading,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from acepressure.app import create_app
from acepressure.domain import now,IST
from datetime import datetime
from werkzeug.security import generate_password_hash
from waitress import create_server
from playwright.sync_api import sync_playwright,expect
with tempfile.TemporaryDirectory() as temp:
 app=create_app(dict(DATA_DIR=temp,SECRET_KEY='s'*48,OVERLAY_TOKEN='o'*48,BRIDGE_TOKEN='b'*48,ADMIN_PASSWORD_HASH=generate_password_hash('test-password'),DEMO_MODE=True,PUBLIC_BASE_URL='http://127.0.0.1:8768'))
 server=create_server(app,host='127.0.0.1',port=8768);threading.Thread(target=server.run,daemon=True).start()
 with sync_playwright() as p:
  b=p.chromium.launch(executable_path=os.getenv('ACE_TEST_BROWSER') or None,args=['--no-sandbox']);page=b.new_page();page.clock.install();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto('http://127.0.0.1:8768/admin');page.locator('[name=password]').fill('test-password');page.get_by_role('button',name='Sign in',exact=True).click();expect(page.locator('#shell')).to_be_visible()
  page.goto('http://127.0.0.1:8768/admin/paytm');expect(page.locator('#connection')).to_contain_text('Disabled');page.on('dialog',lambda d:d.accept());page.locator('#rotate').click();expect(page.locator('#token')).not_to_have_value('');token=page.locator('#token').input_value();page.locator('#enable').click();expect(page.locator('#connection')).to_contain_text('Enabled')
  with app.store.db(True) as db:db.execute('INSERT INTO sessions VALUES(?,?,?,NULL)',('s','Browser session',now()))
  tip=app.store.create_tip({'name':'Immediate Viewer','amount':20,'message':'GG'},True)
  dt=datetime.fromtimestamp(now(),IST);text=f"Received ₹{tip['requested_paise']/100:.2f} from Test Sender Deposited in your Example Bank - 0000 on {dt.day} {dt.strftime('%B')} at {dt.strftime('%I:%M %p')}"
  r=page.request.post('http://127.0.0.1:8768/api/bridge/paytm',headers={'Authorization':'Bearer '+token},data={'text':text});assert r.json()['status']=='REVIEW'
  page.get_by_role('button',name='Refresh inbox').click();expect(page.locator('#inbox')).to_contain_text('REVIEW');page.get_by_placeholder('Audit reason (required)').fill('Confirmed in own payment history');page.get_by_label('I checked this payment').check();page.get_by_label('Play alert').check();page.get_by_role('button',name='Approve checked payment').click();expect(page.locator('#inbox')).to_contain_text('APPROVED')
  a=app.store.create_tip({'name':'Merge Viewer','amount':20},True);z=app.store.create_tip({'name':'Merge Viewer','amount':20},True)
  with app.store.db(True) as db:db.execute("UPDATE tips SET status='VERIFIED',verified=created,actual_paise=requested_paise WHERE id IN (?,?)",(a['id'],z['id']))
  page.goto('http://127.0.0.1:8768/admin');expect(page.locator('#shell')).to_be_visible();page.locator('#nav').get_by_role('button',name='Supporters',exact=True).click()
  row=page.locator('tr').filter(has_text='Merge Viewer').first;row.get_by_role('button',name='Merge duplicate').click()
  dialog=page.locator('.dialog');dialog.locator('select').select_option(z['supporter_id'] if row.count() and dialog.locator('select option[value="'+z['supporter_id']+'"]').count() else a['supporter_id'])
  dialog.get_by_label('Reason for merging').fill('Same person confirmed in test');dialog.get_by_label('I confirmed').check();dialog.get_by_role('button',name='Merge profiles',exact=True).click()
  expect(page.locator('.dialog')).to_have_count(0);expect(page.locator('tr').filter(has_text='Merge Viewer')).to_have_count(1)
  page.locator('#nav').get_by_role('button',name='Design studio',exact=True).click()
  expect(page.get_by_role('button',name='Save appearance')).to_be_visible()
  page.locator('[name=accent]').fill('#a03050');page.get_by_role('button',name='Save appearance').click()
  expect(page.locator('#toast')).to_contain_text('Appearance saved')
  assert page.locator('iframe').count()==4
  for frame in page.locator('iframe').all():
   expect(frame.content_frame.locator('#stage')).not_to_be_empty()
  page.screenshot(path='/tmp/ace-design-studio.png',full_page=True)
  # Render a real URI/QR with fictitious recipient in isolated test data only.
  app.config['DEMO_MODE']=False;app.config['PUBLIC_BASE_URL']='https://tips.example.test'
  with app.store.db(True) as db:
   for k,v in [('upi_id','example@upi'),('payee_name','Example')]:db.execute('UPDATE settings SET value=? WHERE key=?',(json.dumps(v),k))
  page.goto('http://127.0.0.1:8768/');expect(page.locator('#voice-choices button')).to_have_count(2);page.screenshot(path='/tmp/ace-public-desktop.png',full_page=True);page.set_viewport_size({'width':390,'height':844});page.screenshot(path='/tmp/ace-public-mobile.png',full_page=True);page.locator('#amount').fill('20');page.locator('[name=name]').fill('Browser Viewer');page.locator('#pay-button').click();expect(page.get_by_role('button',name='Copy UPI ID')).to_be_visible();expect(page.get_by_role('button',name='Copy exact amount')).to_be_visible();expect(page.get_by_label('Receiving UPI ID')).to_have_value('example@upi');expect(page.locator('.qr')).to_be_visible();page.wait_for_function('document.querySelector(".qr").naturalWidth > 0');expect(page.get_by_role('link',name='Other UPI app')).to_be_visible();assert page.get_by_role('link',name='Other UPI app').get_attribute('href').startswith('upi://pay?')
  from urllib.parse import urlsplit,parse_qs
  base=parse_qs(urlsplit(page.get_by_role('link',name='Other UPI app').get_attribute('href')).query)
  for name,prefix in [('Google Pay','gpay://upi/pay?'),('PhonePe','phonepe://native?'),('Paytm','paytmmp://cash_wallet?')]:
   link=page.get_by_role('link',name=name,exact=True);expect(link).to_be_visible()  # 1.6.8: shown first, not in a closed section
   href=link.get_attribute('href');assert href.startswith(prefix)
   if name!='PhonePe':assert {k:v for k,v in parse_qs(urlsplit(href).query).items() if k!='featuretype'}==base
  page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
  captured=page.evaluate('({...current})');calls=[]
  def status_route(route):
   calls.append(1);route.fulfill(json={**captured,'status':'PENDING','needs_review':False})
  page.route('**/api/public/tips/'+captured['id'],status_route)
  page.clock.run_for(65000);assert 2<=len(calls)<=3,len(calls)
  before=len(calls);page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange'))");page.clock.run_for(60000);assert len(calls)==before
  page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange'))");page.wait_for_timeout(100)
  page.evaluate('current.expires=Math.floor(Date.now()/1000)+1');page.clock.run_for(2000)
  expect(page.get_by_role('heading',name='Payment window closed')).to_be_visible()
  assert page.locator('.qr').count()==0
  before=len(calls);page.clock.run_for(125000);assert 2<=len(calls)-before<=3,len(calls)-before  # 1.6.4: a closed window keeps checking once a minute
  page.unroute('**/api/public/tips/'+captured['id'],status_route)
  page.route('**/api/public/tips/'+captured['id'],lambda route:route.fulfill(json={**captured,'status':'MANUAL'}))
  page.get_by_role('button',name='Check payment status').click()
  expect(page.get_by_role('heading',name=re.compile(r'^Thank you,'))).to_be_visible()
  page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');assert not errors,errors;b.close()
 server.close()
print('PASS: persistent token, immediate review, approval, live QR/UPI/copy controls, mobile layout, 20-second polling, expiry stop, manual late approval; no JS errors')
