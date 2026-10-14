"""Regression for outer .widget.bar accidentally receiving progress-track height."""
import json,sys,tempfile,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from werkzeug.security import generate_password_hash
from waitress import create_server
from playwright.sync_api import sync_playwright,expect
from acepressure.app import create_app
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as tmp:
 app=create_app(dict(DATA_DIR=tmp,SECRET_KEY='s'*48,BRIDGE_TOKEN='b'*48,OVERLAY_TOKEN='o'*48,ADMIN_PASSWORD_HASH=generate_password_hash('layout-check'),DEMO_MODE=True))
 with app.store.db(True) as db:db.execute("INSERT INTO goals VALUES ('test','Weekly support',200000,10000,'week','automatic',NULL,NULL,1,'compact','bar',NULL)")
 server=create_server(app,host='127.0.0.1',port=8771);threading.Thread(target=server.run,daemon=True).start()
 results=[]
 with sync_playwright() as p:
  browser=p.chromium.launch(args=['--no-sandbox']);page=browser.new_page(viewport={'width':700,'height':180})
  page.goto('http://127.0.0.1:8771/overlay/goal?key='+'o'*48);expect(page.locator('.goal-line')).to_contain_text('₹100 / ₹2,000')
  old=(ROOT/'acepressure/static/overlay.css').read_text(encoding='utf-8').replace('.widget > .bar{height:13px;','.bar{height:13px;')
  style=page.add_style_tag(content=old)
  def sizes():return page.evaluate('''()=>{const rect=s=>{const r=document.querySelector(s).getBoundingClientRect();return {top:r.top,bottom:r.bottom,height:r.height,width:r.width}};return {card:rect('.widget'),text:rect('.goal-line'),track:rect('.widget > .bar'),fill:rect('.fill')}}''')
  broken=sizes();assert broken['track']['bottom']>broken['card']['bottom'];style.evaluate('(s)=>s.remove()')
  for width in [700,390]:
   page.set_viewport_size({'width':width,'height':180});box=sizes();assert box['text']['bottom']<=box['card']['bottom'];assert box['track']['bottom']<=box['card']['bottom'];assert box['card']['bottom']<=180;assert abs(box['fill']['width']/box['track']['width']-.05)<.005;results.append({'width':width,**box})
   page.screenshot(path=str(ROOT/'docs/screenshots'/f'goal-fixed-{width}.png'),omit_background=True)
  page.set_viewport_size({'width':700,'height':180});page.add_style_tag(content=old)
  page.add_style_tag(content='.widget.bar {height:auto !important; overflow:visible !important; background:rgba(15,17,22,.94) !important; border-radius:12px !important; margin-top:0 !important;}')
  workaround=sizes();assert workaround['track']['bottom']<=workaround['card']['bottom'];assert workaround['card']['bottom']<=180
  browser.close()
 server.close()
 report={'reproduced_original_clipping':True,'fixed_checks':results,'obs_custom_css_workaround_passed':True}
 (ROOT/'docs/goal-layout-test.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
