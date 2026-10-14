import json,re
from pathlib import Path
from acepressure.readiness import readiness,startup_summary
ROOT=Path(__file__).resolve().parents[1]

def health(admin):c,h=admin;return c.get('/api/admin/state').json['health']
def failing(admin):return [x['key'] for x in health(admin)['checks'] if not x['ok']]
def check(admin,key):return next(x for x in health(admin)['checks'] if x['key']==key)
def live(app,url='http://localhost:8765'):app.config['DEMO_MODE']=False;app.config['PUBLIC_BASE_URL']=url
def payee(admin):c,h=admin;assert c.post('/api/admin/settings',json=dict(upi_id='example@upi',payee_name='Example'),headers=h).status_code==200
def bridge(admin,action='enable',**kw):c,h=admin;return c.post('/api/admin/paytm/config',json=dict(action=action,**kw),headers=h)
def direct(app,key='restart',**config):
    with app.store.db() as db:return next(x for x in readiness(app.store,db,dict(app.config,**config))['checks'] if x['key']==key)
def configured(app,admin,url='https://tips.example.test'):
    live(app,url);payee(admin);token=bridge(admin,'rotate').json['token']
    assert bridge(admin,recipient='Example Bank - 0000').status_code==200
    return token

def test_live_http_setup_names_every_missing_step(app,admin):
    live(app);h=health(admin)
    assert h['tip_page']=='setup' and h['tip_url']=='http://localhost:8765/'
    assert {'upi','https','verification'}<=set(failing(admin))
    assert [x['key'] for x in h['checks']]==['upi','https','verification','accepting']  # no restart check without a .env
    assert all(set(x)=={'key','ok','title','fix','link'} for x in h['checks'])
    c,_=admin;cfg=c.get('/api/public/config').json
    assert cfg['ready'] is False and cfg['availability']=='setup'

def test_configured_live_app_is_open_everywhere(app,admin):
    configured(app,admin);h=health(admin)
    assert h['tip_page']=='open' and all(x['ok'] for x in h['checks'])
    assert h['paytm']=={'enabled':True,'auto_match':False,'has_token':True,'has_recipient':True,'last_seen':None} and h['sms_bridge'] is False
    c,_=admin;cfg=c.get('/api/public/config').json
    assert cfg['ready'] is True and cfg['availability']=='open'
    assert c.get('/api/admin/paytm').json['health']['tip_page']=='open'

def test_paused_in_both_places_live_and_demo(app,admin):
    c,h=admin
    for demo in [True,False]:
        if not demo:configured(app,admin)
        assert c.post('/api/admin/settings',json={'accepting_tips':False},headers=h).status_code==200
        x=check(admin,'accepting');assert not x['ok'] and x['link']=='resume'
        assert health(admin)['tip_page']=='paused' and c.get('/api/public/config').json['availability']=='paused'
        assert c.post('/api/admin/settings',json={'accepting_tips':True},headers=h).status_code==200
        assert health(admin)['tip_page']==('demo' if demo else 'open')

def test_restart_check_reads_env_file_but_never_changes_tip_page(app,admin,tmp_path):
    env=tmp_path/'real.env';env.write_text('PUBLIC_BASE_URL=https://x.example.ts.net/\nCOOKIE_SECURE=true\nBRIDGE_TOKEN='+'b'*48+'\n',encoding='utf-8')
    app.config['ENV_FILE']=str(env);live(app)
    x=check(admin,'restart')
    assert not x['ok'] and x['link']=='restart' and 'https://x.example.ts.net' in x['fix'] and 'http://localhost:8765' in x['fix'] and 'Start.bat' in x['fix']
    assert health(admin)['checks'][0]['key']=='restart' and health(admin)['tip_page']=='setup'
    configured(app,admin,'https://old.example.ts.net')  # running on an older HTTPS address: still open, plus the advisory
    x=check(admin,'restart');assert not x['ok'] and 'https://old.example.ts.net' in x['fix'] and health(admin)['tip_page']=='open'
    c,h=admin;c.post('/api/admin/settings',json={'accepting_tips':False},headers=h)
    assert 'Payments: PAUSED - New tip requests: New tips are paused' in startup_summary(app)  # the real reason, not the advisory restart
    c.post('/api/admin/settings',json={'accepting_tips':True},headers=h)
    assert direct(app,SESSION_COOKIE_SECURE=True,PUBLIC_BASE_URL='https://x.example.ts.net')['ok']
    x=direct(app,SESSION_COOKIE_SECURE=False,PUBLIC_BASE_URL='https://x.example.ts.net')  # only the cookie setting differs
    assert not x['ok'] and x['fix'].startswith('Restart needed: .env changed')
    app.config['DEMO_MODE']=True
    assert 'restart' not in [x['key'] for x in health(admin)['checks']]

def test_sms_bridge_on_http_is_not_ready(app,admin):
    c,h=admin
    r=c.post('/api/admin/settings',headers=h,json=dict(upi_id='example@bank',payee_name='Example',bank_sender='VM-TEST',parser='structured-v1',bridge_enabled=True));assert r.status_code==200
    live(app);cfg=c.get('/api/public/config').json
    assert cfg['ready'] is False and cfg['availability']=='setup' and cfg['accepting_tips'] is True
    assert health(admin)['sms_bridge'] is True and check(admin,'verification')['ok'] and failing(admin)==['https']
    assert c.post('/api/public/tips',json={'name':'A','amount':100}).status_code==503

def test_verification_fix_names_the_missing_piece(app,admin):
    live(app,'https://tips.example.test');payee(admin)
    assert 'Generate token' in check(admin,'verification')['fix'] and check(admin,'verification')['link']=='/admin/paytm'
    bridge(admin,'rotate');assert 'bank marker' in check(admin,'verification')['fix']
    assert bridge(admin,recipient='Example Bank - 0000').status_code==200 and check(admin,'verification')['ok']
    bridge(admin,'rotate')  # a new token silently switches the bridge off
    x=check(admin,'verification');assert not x['ok'] and x['fix'].startswith('Open Paytm bridge and click Enable bridge')
    assert health(admin)['tip_page']=='setup' and health(admin)['paytm']['enabled'] is False

def test_enable_on_http_names_running_url(app,admin):
    live(app);payee(admin);bridge(admin,'rotate')
    r=bridge(admin,recipient='Example Bank - 0000')
    assert r.status_code==400 and 'http://localhost:8765' in r.json['error'] and 'Start.bat' in r.json['error']

def test_health_never_contains_secrets(app,admin,tmp_path):
    env=tmp_path/'secret.env';env.write_text('PUBLIC_BASE_URL=https://x.example.ts.net\nBRIDGE_TOKEN='+'b'*48+'\nOVERLAY_TOKEN='+'o'*48+'\nAPP_SECRET='+'s'*48+'\n',encoding='utf-8')
    app.config['ENV_FILE']=str(env);token=configured(app,admin)
    c,_=admin
    for h in [health(admin),c.get('/api/admin/paytm').json['health']]:
        text=json.dumps(h)
        for secret in ['token_hash','recipient_hash','b'*48,'o'*48,'s'*48,token,'Example Bank']:assert secret not in text

def test_readiness_never_raises(app):
    app.config['DEMO_MODE']=False
    h=readiness(app.store,None,app.config)
    assert h['checks']==[] and h['tip_page']=='setup' and h['review_count']==0

def test_startup_summary_is_plain_ascii(app,admin):
    text=startup_summary(app);text.encode('ascii')
    assert 'DEMO MODE - no real money.' in text and 'Keep this window open' in text and '/admin' in text
    live(app);text=startup_summary(app);text.encode('ascii')
    assert 'Payments: PAUSED - UPI ID and payee name: Add your UPI ID and payee name in Settings -> Creator & payments.' in text
    configured(app,admin);text=startup_summary(app)
    assert 'Payments: READY' in text and 'Tip page: https://tips.example.test/' in text and 'Keep this window open while you stream.' in text
    assert 'startup_summary(app)' in (ROOT/'run.py').read_text(encoding='utf-8')

def test_public_page_uses_availability_and_safe_storage():
    js=(ROOT/'acepressure/static/public.js').read_text(encoding='utf-8')
    assert 'config.availability' in js and 'safeStore.get(' in js and 'function setPayEnabled' in js
    assert "localStorage.getItem('ace-remember')" not in js and "sessionStorage.getItem('ace-tip')" not in js
    assert 'Tips are paused while payment verification is being configured.' not in js
    assert 'is finishing payment setup.' in js and 'isn’t taking new tips right now. Please check back soon.' in js
    assert re.search(r"setInterval\(recheckConfig,60000\)",js)
    admin=(ROOT/'acepressure/static/admin.js').read_text(encoding='utf-8')
    assert "first=failing.find(c=>c.key!=='restart')" in admin and "if(restart)line('warn',restart.fix)" in admin and "'health-line '" in admin
