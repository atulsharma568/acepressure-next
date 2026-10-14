"""OBS gets the alerts, not a forgotten browser tab: OBS-first claiming, connected-overlay status, Test alert feedback, local OBS links."""
import json,re,time
from pathlib import Path
from werkzeug.security import generate_password_hash
from acepressure.app import create_app,OverlayClients
from acepressure.domain import now
ROOT=Path(__file__).resolve().parents[1]
CHROME='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36'
EMPTY={'horizontal':[],'vertical':[]}

def overlay(app,path,body,ua=None):return app.test_client().post('/api/overlay/'+path,json=body,headers={'X-Overlay-Token':'o'*48}|({'User-Agent':ua} if ua else {}))
def claim(app,owner,client=None,channel='horizontal',ua=None):return overlay(app,'claim',{'channel':channel,'owner':owner}|({'client':client} if client else {}),ua).json
def ack(app,p,owner,client='obs'):return overlay(app,'ack',{'event_id':p['event_id'],'channel':'horizontal','owner':owner,'tts_played':False,'client':client}).status_code
def send_test_alert(admin):c,h=admin;r=c.post('/api/admin/alerts',json={'action':'test'},headers=h);assert r.status_code==200;return r.json
def delivery(app):
    with app.store.db() as db:return db.execute("SELECT state FROM deliveries WHERE channel='horizontal' ORDER BY alert_id LIMIT 1").fetchone()[0]
def summary(app):return app.extensions['ace_overlay_clients'].summary()
def kinds(o):return {ch:sorted((c['client'],c['standby']) for c in o[ch]) for ch in o}
def clock(app,start=0.0):t=[start];app.extensions['ace_overlay_clients'].clock=lambda:t[0];return t
def fresh_app(path):return create_app(dict(TESTING=True,DATA_DIR=str(path),SECRET_KEY='s'*48,BRIDGE_TOKEN='b'*48,OVERLAY_TOKEN='o'*48,ADMIN_PASSWORD_HASH=generate_password_hash('test-password-123'),DEMO_MODE=True,ENV_FILE=str(path/'none.env')))

def test_obs_takes_alerts_and_a_browser_tab_waits(app,admin):  # spec a
    assert claim(app,'obsA','obs')=={'alert':None}
    send_test_alert(admin)
    assert claim(app,'tab1','browser')=={'alert':None,'standby':True}
    assert delivery(app)=='queued'
    assert claim(app,'obsA','obs')['alert']['name']=='Test supporter' and delivery(app)=='playing'

def test_without_obs_a_browser_tab_gets_the_alert(app,admin):  # spec b
    send_test_alert(admin)
    assert claim(app,'tab1','browser')['alert']['name']=='Test supporter'
    assert kinds(summary(app))['horizontal']==[('browser',False)]

def test_older_overlay_scripts_claim_as_before(app,admin):  # spec c
    claim(app,'obsA','obs');send_test_alert(admin)
    assert claim(app,'old',ua='Mozilla/5.0 Chrome/127')['alert']['name']=='Test supporter'
    assert kinds(summary(app))['horizontal']==[('obs',False),('unknown',False)]

def test_obs_user_agent_counts_as_obs(app,admin):  # spec d
    claim(app,'source',ua=CHROME+' OBS/30.2.3');send_test_alert(admin)
    assert claim(app,'tab1','browser')=={'alert':None,'standby':True}
    assert kinds(summary(app))['horizontal']==[('browser',True),('obs',False)]

def test_presence_follows_an_injected_clock(app,admin):  # spec e
    t=clock(app);send_test_alert(admin);p=claim(app,'obsA','obs')['alert']
    t[0]=10;assert ack(app,p,'obsA')==200
    t[0]=11;assert claim(app,'tab1','browser')=={'alert':None,'standby':True}
    t[0]=30;assert summary(app)==EMPTY

def test_a_browser_tab_takes_over_when_obs_goes_quiet(app,admin):
    t=clock(app,100);claim(app,'obsA','obs');send_test_alert(admin)
    t[0]=105;assert claim(app,'tab1','browser')['standby']  # OBS polled 5 s ago: it still counts
    t[0]=105.5;assert claim(app,'tab1','browser')['alert']['name']=='Test supporter'
    assert kinds(summary(app))['horizontal']==[('browser',False),('obs',False)]

def test_obs_playing_a_long_alert_stays_listed(app,admin):
    t=clock(app);send_test_alert(admin);p=claim(app,'obsA','obs')['alert'];send_test_alert(admin)
    t[0]=40  # an overlay doesn't poll while an alert is on screen
    assert claim(app,'tab1','browser')=={'alert':None,'standby':True}
    assert kinds(summary(app))['horizontal']==[('browser',True),('obs',False)]
    assert ack(app,p,'obsA')==200 and claim(app,'obsA','obs')['alert']['event_id']>p['event_id']
    t[0]=40+179;assert kinds(summary(app))['horizontal']==[('obs',False)]  # listed while its 180 s lease runs
    t[0]=41+180;assert summary(app)==EMPTY  # a source that never acks is dropped with its lease

def test_a_forced_page_and_other_layouts_never_wait(app,admin):
    claim(app,'obsA','obs');send_test_alert(admin)
    assert claim(app,'tabV','browser','vertical')['alert']  # OBS on the horizontal layout only
    assert claim(app,'meld','forced')['alert']['name']=='Test supporter'

def test_unknown_client_values_fall_back_to_the_user_agent(app):
    claim(app,'a','hacker',ua=CHROME);claim(app,'b','OBS',ua=CHROME+' OBS/31.0.0')
    assert kinds(summary(app))['horizontal']==[('obs',False),('unknown',False)]

def test_standby_claims_never_touch_the_database(app,admin,monkeypatch):
    claim(app,'obsA','obs');send_test_alert(admin)
    calls=[];real=app.store.db;monkeypatch.setattr(app.store,'db',lambda *a,**k:(calls.append(a),real(*a,**k))[1])
    assert claim(app,'tab1','browser')=={'alert':None,'standby':True} and calls==[]
    assert claim(app,'obsA','obs')['alert'] and calls

def test_junk_acks_are_not_listed(app):
    assert overlay(app,'ack',{'event_id':1,'channel':'sideways','owner':'x','client':'obs'}).status_code==409
    assert overlay(app,'ack',{'event_id':1,'channel':'horizontal','owner':'','client':'obs'}).status_code==409
    assert summary(app)==EMPTY

def test_registry_rules():
    assert OverlayClients().clock is time.monotonic
    t=[0.0];reg=OverlayClients(clock=lambda:t[0])
    assert reg.record('vertical','obsV','obs') is False and reg.record('horizontal','tab','browser') is False  # OBS on another layout doesn't count
    assert reg.record('horizontal','obsH','obs') is False and reg.record('horizontal','tab','browser') is True
    assert reg.record('horizontal','obsH','browser') is False  # a page never waits for itself
    t[0]=15;assert len(reg.summary()['horizontal'])==2
    t[0]=15.1;assert reg.summary()==EMPTY

def test_dashboard_and_test_alert_report_connected_overlays(app,admin):  # spec f
    c,h=admin
    assert c.get('/api/admin/state').json['overlays']==EMPTY and send_test_alert(admin)['overlays']==EMPTY
    claim(app,'secret-owner-1','obs');claim(app,'secret-owner-2','browser');claim(app,'secret-owner-3','browser','vertical')
    state=c.get('/api/admin/state').json;o=state['overlays']
    assert kinds(o)=={'horizontal':[('browser',True),('obs',False)],'vertical':[('browser',False)]}
    assert all(set(x)=={'client','age','standby'} and x['age']>=0 for x in o['horizontal'])
    r=send_test_alert(admin);assert r['ok'] is True and kinds(r['overlays'])==kinds(o)
    assert 'secret-owner' not in json.dumps(state) and 'secret-owner' not in json.dumps(r)  # owner ids are never exposed
    assert c.post('/api/admin/alerts',json={'action':'skip'},headers=h).json=={'ok':True}

def test_obs_tab_offers_a_local_link(app,admin,monkeypatch,tmp_path):  # spec g
    for k in ['PORT','HOST']:monkeypatch.delenv(k,raising=False)
    c,_=admin;d=c.get('/api/admin/obs').json
    assert d['local_base']=='http://127.0.0.1:8765' and d['base']==app.config['PUBLIC_BASE_URL'] and d['key']=='o'*48
    monkeypatch.setenv('PORT','8766');other=fresh_app(tmp_path/'second').test_client()
    other.post('/api/login',json={'password':'test-password-123'})
    assert other.get('/api/admin/obs').json['local_base']=='http://127.0.0.1:8766'

def test_local_link_follows_a_specific_host(admin,monkeypatch):
    c,_=admin;monkeypatch.setenv('PORT','8780')
    for host,base in [('127.0.0.1','http://127.0.0.1:8780'),('0.0.0.0','http://127.0.0.1:8780'),('localhost','http://127.0.0.1:8780'),('192.168.1.20','http://192.168.1.20:8780'),('::','http://[::1]:8780'),('::1','http://[::1]:8780'),('fd7a:115c:a1e0::5','http://[fd7a:115c:a1e0::5]:8780')]:
        monkeypatch.setenv('HOST',host);assert c.get('/api/admin/obs').json['local_base']==base,host

def test_overlay_script_reports_its_client_type():  # spec h
    js=(ROOT/'acepressure/static/overlay.js').read_text(encoding='utf-8')
    assert 'obsstudio' in js and 'client:clientType' in js and 'visibilityState' in js
    run=re.search(r'async function runQueue\(\).*?finally\{busy=false;\}\}',js,re.S).group(0)
    assert run.count('client:clientType')==3 and "(!isOBS&&!forced&&document.visibilityState==='hidden'))return;" in run
    assert "query.get('claim')==='always'" in js and 'Preview only: OBS is taking alerts for this layout. Close this tab, or add &claim=always to use it.' in js
    assert "'Overlay key rejected'" in js and '++failures<3' in js and 'function clearError(){failures=0;' in js

def test_dashboard_copy_and_overlay_styles():
    admin=(ROOT/'acepressure/static/admin.js').read_text(encoding='utf-8')
    for text in ["'Alert overlays · '","obs:'OBS'","browser:'browser tab'","forced:'forced page'","unknown:'older overlay (refresh it in OBS)'","' (standby)'","'not connected'",
                 "'A normal browser tab is taking '+name+' alerts. Alerts it takes won’t show in OBS. Close that tab.'","' OBS sources are polling '+name+' alerts and compete for them. Use one source and add it to every scene.'",
                 'No horizontal alert overlay is connected. Open OBS or check the Browser Source URL (Admin → OBS).',"'Test alert sent. '",
                 'Test alert queued, but no alert overlay is connected. Open OBS (or refresh the source). Tests expire after 5 minutes.',
                 'OBS on this PC (recommended)','OBS on another PC','Sources you already added keep working, so there’s nothing to change. Local links keep alerts working if Tailscale drops. Other streaming apps (not OBS): add &claim=always to the alert link.']:
        assert text in admin,text
    assert admin.count("button('Test alert',testAlert)")==2 and "linkRow('Activity Dock',d.base+'/obs/activity')" in admin
    css=(ROOT/'acepressure/static/overlay.css').read_text(encoding='utf-8')
    error=re.search(r'#error\{([^}]*)\}',css).group(1);standby=re.search(r'\.overlay-standby\{([^}]*)\}',css).group(1)
    assert all(x in error for x in ['position:fixed','right:8px','bottom:8px','font:12px Arial','max-width:420px','opacity:.9'])
    assert all(x in standby for x in ['position:fixed','left:8px','top:8px','12px']) and 'display' not in error+standby  # the hidden attribute must still hide them
