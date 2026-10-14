"""Behind Tailscale Funnel every request reaches Waitress from 127.0.0.1: the tunnel's X-Forwarded-For gives each visitor their own limits."""
import logging, re
from pathlib import Path
import pytest
from flask import request
from waitress.adjustments import Adjustments
from waitress.proxy_headers import proxy_headers_middleware
import acepressure.domain
from acepressure.app import WAITRESS_PROXY_OPTIONS
from acepressure.domain import Problem, now
ROOT=Path(__file__).resolve().parents[1]

GOOD={'Authorization':'Bearer '+'b'*48}
BAD={'Authorization':'Bearer '+'x'*48}
def via(ip,**headers):return {'X-Forwarded-For':ip}|headers
def buckets(app):
    with app.store.db() as db:return {r[0] for r in db.execute('SELECT bucket FROM rate_limits')}

@pytest.fixture
def served(app):
    """The app wrapped the way Waitress wraps it when run.py serves it with WAITRESS_PROXY_OPTIONS."""
    adj=Adjustments(**WAITRESS_PROXY_OPTIONS)
    app.wsgi_app=proxy_headers_middleware(app.wsgi_app,trusted_proxy=adj.trusted_proxy,trusted_proxy_count=adj.trusted_proxy_count,trusted_proxy_headers=adj.trusted_proxy_headers,clear_untrusted=adj.clear_untrusted_proxy_headers)
    return app

def test_waitress_accepts_the_proxy_options():
    adj=Adjustments(host='127.0.0.1',port=8765,**WAITRESS_PROXY_OPTIONS)
    assert adj.trusted_proxy=='127.0.0.1' and adj.trusted_proxy_count==1 and adj.trusted_proxy_headers=={'x-forwarded-for'} and adj.clear_untrusted_proxy_headers
    assert re.search(r'\bserve\(app,.*\*\*WAITRESS_PROXY_OPTIONS\)',(ROOT/'run.py').read_text(encoding='utf-8'))

def test_wait_message_rounds_up_to_whole_minutes(app,monkeypatch):
    monkeypatch.setattr(acepressure.domain,'now',lambda:1_000_000)
    with app.store.db(True) as db:db.executemany('INSERT INTO rate_limits VALUES (?,?,?)',[('zero',5,1_000_000),('half',5,1_000_030),('ninety',5,1_000_090),('login',5,1_000_900)])
    for bucket,wait in [('zero','1 minute'),('half','1 minute'),('ninety','2 minutes'),('login','15 minutes')]:
        with pytest.raises(Problem) as e:app.store.rate(bucket,5,60)
        assert (e.value.status,e.value.message)==(429,f'Too many requests. Please wait about {wait}.')

def test_each_visitor_gets_their_own_tip_limit(served):
    c=served.test_client()
    for _ in range(15):assert c.post('/api/public/tips',json={},headers=via('8.8.8.8')).status_code!=429
    r=c.post('/api/public/tips',json={},headers=via('8.8.8.8'))
    assert r.status_code==429 and 'minute' in r.json['error']
    assert r.json['error']=='Too many requests. Please wait about 10 minutes.'
    assert c.post('/api/public/tips',json={},headers=via('1.1.1.1')).status_code!=429
    assert {'public:8.8.8.8','public:1.1.1.1','public-global'}<=buckets(served)

def test_local_requests_stay_keyed_to_loopback(served):
    c=served.test_client()
    for _ in range(15):c.post('/api/public/tips',json={})
    assert c.post('/api/public/tips',json={}).status_code==429
    assert 'public:127.0.0.1' in buckets(served)

def test_forwarded_for_from_another_machine_is_ignored(served):
    c=served.test_client()
    c.post('/api/public/tips',json={},headers=via('8.8.8.8'),environ_base={'REMOTE_ADDR':'192.168.1.9'})
    assert 'public:192.168.1.9' in buckets(served) and 'public:8.8.8.8' not in buckets(served)

def test_forget_browser_has_its_own_bucket(served):
    c=served.test_client()
    codes=[c.post('/api/public/forget-browser',json={},headers=via('8.8.8.8')).status_code for _ in range(15)]
    assert codes[:10]==[200]*10 and codes[10:]==[429]*5
    assert c.post('/api/public/tips',json={},headers=via('8.8.8.8')).status_code!=429
    assert 'public:8.8.8.8' in buckets(served) and 'forget:8.8.8.8' in buckets(served)

def test_shared_safety_net_for_tip_requests(served):
    with served.store.db(True) as db:db.execute('INSERT INTO rate_limits VALUES (?,?,?)',('public-global',200,now()+600))
    c=served.test_client()
    assert c.post('/api/public/tips',json={},headers=via('8.8.8.8')).status_code==429
    assert c.post('/api/public/forget-browser',json={},headers=via('8.8.8.8')).status_code==200

def test_wrong_passwords_lock_out_only_that_visitor(served):
    c=served.test_client()
    for _ in range(8):assert c.post('/api/login',json={'password':'wrong-password'},headers=via('8.8.8.8')).status_code==401
    r=c.post('/api/login',json={'password':'wrong-password'},headers=via('8.8.8.8'))
    assert r.status_code==429 and r.json['error']=='Too many requests. Please wait about 15 minutes.'
    assert c.post('/api/login',json={'password':'test-password-123'}).status_code==200
    assert 'login-public' in buckets(served)

def test_local_lan_and_tailnet_sign_ins_skip_the_shared_bucket(served):
    c=served.test_client()
    for ip in ['192.168.1.20','100.101.102.103','fd7a:115c:a1e0::1']:c.post('/api/login',json={'password':'wrong-password'},headers=via(ip))
    c.post('/api/login',json={'password':'wrong-password'})
    assert 'login-public' not in buckets(served)
    with served.store.db(True) as db:db.execute('INSERT INTO rate_limits VALUES (?,?,?)',('login-public',40,now()+900))
    assert c.post('/api/login',json={'password':'test-password-123'},headers=via('1.1.1.1')).status_code==429
    assert c.post('/api/login',json={'password':'test-password-123'},headers=via('100.101.102.103')).status_code==200

def test_junk_cannot_block_the_paytm_phone(served):
    c=served.test_client()
    csrf={'X-CSRF-Token':c.post('/api/login',json={'password':'test-password-123'}).json['csrf']}
    token=c.post('/api/admin/paytm/config',json={'action':'rotate'},headers=csrf).json['token']
    assert c.post('/api/admin/paytm/config',json={'action':'enable'},headers=csrf).status_code==200
    codes=[c.post('/api/bridge/paytm',json={'text':'offer'},headers=via('8.8.8.8',**BAD)).status_code for _ in range(60)]
    assert codes[:30]==[401]*30 and codes[30:]==[429]*30
    phone={'Authorization':'Bearer '+token}
    assert c.post('/api/bridge/paytm',json={'text':'offer'},headers=via('8.8.8.8',**phone)).status_code==200
    assert c.post('/api/bridge/paytm',json={'text':'offer'},headers=phone).status_code==200
    assert 'paytm-bad:8.8.8.8' in buckets(served) and 'paytm-auth' in buckets(served)

def test_junk_cannot_block_the_sms_bridge(served):
    c=served.test_client()
    codes=[c.post('/api/bridge/credit',json={},headers=via('8.8.8.8',**BAD)).status_code for _ in range(60)]
    assert codes[:30]==[401]*30 and codes[30:]==[429]*30
    t=served.store.create_tip({'name':'Rahul','amount':100},True)
    d=dict(amount=t['requested_paise']/100,reference='BANK123456',received_at=now(),sender='DEMO-BANK',direction='credit')
    r=c.post('/api/bridge/credit',json=d,headers=via('8.8.8.8',**GOOD))
    assert r.status_code==200 and r.json['outcome']=='verified'
    assert 'bridge-bad:8.8.8.8' in buckets(served) and 'bridge-global' in buckets(served) and not any(b.startswith('bridge-ip:') for b in buckets(served))

def test_forwarded_host_and_proto_are_still_ignored(served):
    @served.get('/probe-host')
    def probe_host():return {'host_url':request.host_url,'remote':request.remote_addr}
    c=served.test_client()
    r=c.get('/probe-host',headers=via('8.8.8.8',**{'X-Forwarded-Host':'evil.example','X-Forwarded-Proto':'https'}))
    assert r.json=={'host_url':'http://localhost/','remote':'8.8.8.8'}
    assert c.post('/api/public/tips',json={},headers=via('8.8.8.8',**{'X-Forwarded-Host':'evil.example','Origin':'http://evil.example'})).status_code==403

def test_tunnel_is_logged_once_without_the_address(served,caplog):
    c=served.test_client()
    with caplog.at_level(logging.INFO):
        c.get('/health');c.get('/health',headers=via('8.8.8.8'));c.get('/health',headers=via('1.1.1.1'))
    found=[r for r in caplog.records if 'X-Forwarded-For' in r.getMessage()]
    assert [(r.levelno,r.getMessage()) for r in found]==[(logging.INFO,'Visitor addresses come from the tunnel (X-Forwarded-For): per-visitor rate limits are active.')]
    assert '8.8.8.8' not in caplog.text and '1.1.1.1' not in caplog.text
