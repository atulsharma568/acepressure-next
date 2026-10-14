import json,sqlite3,time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from acepressure.domain import now,IST,Problem,money

def tip(app,**kwargs):return app.store.create_tip(dict(amount=100,name='Rahul',message='Nice shot',tts=True,voice='en-IN',sound='chime',**kwargs),True)
def receipt(t,ref='BANK123456',**kwargs):return dict(amount=t['requested_paise']/100,reference=ref,received_at=now(),**kwargs)
def start(admin):c,h=admin;return c.post('/api/admin/sessions',json={'action':'start','title':'Ranked'},headers=h)
def overlay(app,path,body):return app.test_client().post('/api/overlay/'+path,json=body,headers={'X-Overlay-Token':'o'*48})

def test_payment_pending_never_counts(app):
    t=tip(app)
    with app.store.db() as db:
        assert app.store.summary(db)['total']==0
        assert db.execute('SELECT count(*) FROM alerts').fetchone()[0]==0
    assert t['requested_paise']>t['display_paise']

def test_exact_received_separate_and_session_alerts(app,admin):
    start(admin);t=tip(app);r=app.store.verify(receipt(t))
    assert r['outcome']=='verified'
    with app.store.db() as db:
        s=app.store.summary(db,'stream');assert s['total']==10000;assert s['actual']==t['requested_paise']
        assert db.execute('SELECT count(*) FROM deliveries').fetchone()[0]==2

def test_family_transfer_ignored(app):
    t=tip(app);r=app.store.verify(dict(amount=100,reference='FAMILY123',received_at=now()))
    assert r['outcome']=='unmatched'
    with app.store.db() as db:assert app.store.summary(db)['count']==0

def test_duplicate_reference_is_idempotent(app):
    t=tip(app);one=app.store.verify(receipt(t));two=app.store.verify(receipt(t));assert one['tip_id']==two['tip_id'];assert two['duplicate']
    with app.store.db() as db:assert app.store.summary(db)['count']==1

def test_concurrent_duplicate(app):
    t=tip(app)
    with ThreadPoolExecutor(max_workers=5) as pool:out=list(pool.map(lambda _:app.store.verify(receipt(t)),range(5)))
    assert sum(not r.get('duplicate',False) for r in out)==1

def test_concurrent_amounts_unique(app):
    with ThreadPoolExecutor(max_workers=8) as pool:ts=list(pool.map(lambda _:tip(app),range(15)))
    assert len({t['requested_paise'] for t in ts})==15

def test_expired_receipt_does_not_alert(app,admin):
    start(admin);t=tip(app)
    with app.store.db(True) as db:db.execute('UPDATE tips SET expires=? WHERE id=?',(now()-1,t['id']))
    assert app.store.verify(receipt(t))['outcome']=='unmatched'
    with app.store.db() as db:assert db.execute('SELECT count(*) FROM alerts').fetchone()[0]==0

def test_amount_quarantine(app):
    t=tip(app)
    with app.store.db(True) as db:db.execute("UPDATE tips SET status='EXPIRED' WHERE id=?",(t['id'],))
    assert all(tip(app)['requested_paise']!=t['requested_paise'] for _ in range(10))

def test_pool_exhaustion_fails_safely(app):
    with app.store.db(True) as db:db.executemany('INSERT INTO amount_leases VALUES (?,?)',[(10000+i,now()+86400) for i in range(1,100)])
    try:tip(app);assert False
    except Problem as e:assert e.status==409

def test_old_session_never_alerts_new(app,admin):
    c,h=admin;start(admin);t=tip(app);c.post('/api/admin/sessions',json={'action':'end'},headers=h);start(admin)
    assert app.store.verify(receipt(t))['outcome']=='verified'
    with app.store.db() as db:assert db.execute('SELECT count(*) FROM alerts').fetchone()[0]==0;assert app.store.summary(db,'stream')['count']==0

def test_offline_tip_is_saved_without_live_alert(app):
    t=tip(app);app.store.verify(receipt(t))
    with app.store.db() as db:assert db.execute('SELECT count(*) FROM alerts').fetchone()[0]==0;assert app.store.summary(db)['count']==1

def test_bridge_auth_and_direction(app,client):
    assert client.post('/api/bridge/credit',json={}).status_code==401
    assert client.post('/api/bridge/credit',json={'sender':'DEMO-BANK','direction':'debit'},headers={'Authorization':'Bearer '+'b'*48}).status_code==422

def test_bridge_full_flow(app,client):
    t=tip(app);d=receipt(t)|dict(sender='DEMO-BANK',direction='credit')
    r=client.post('/api/bridge/credit',json=d,headers={'Authorization':'Bearer '+'b'*48});assert r.json['outcome']=='verified'

def test_live_disabled_fail_closed(app,client):
    app.config['DEMO_MODE']=False
    assert client.post('/api/public/tips',json={'name':'A','amount':100}).status_code==503
    assert client.post('/api/bridge/credit',json={},headers={'Authorization':'Bearer '+'b'*48}).status_code==503

def test_live_structured_sender_and_credit(app,admin):
    c,h=admin
    r=c.post('/api/admin/settings',headers=h,json=dict(upi_id='example@bank',payee_name='Example',bank_sender='VM-TEST',parser='structured-v1',bridge_enabled=True));assert r.status_code==200
    app.config['DEMO_MODE']=False;t=app.store.create_tip({'name':'A','amount':100})
    d=receipt(t)|dict(sender='VM-OTHER',direction='credit');headers={'Authorization':'Bearer '+'b'*48}
    assert c.post('/api/bridge/credit',json=d,headers=headers).status_code==422
    d['sender']='VM-TEST';assert c.post('/api/bridge/credit',json=d,headers=headers).json['outcome']=='verified'

def test_live_simulation_disabled(app,admin):
    c,h=admin;t=tip(app);app.config['DEMO_MODE']=False
    assert c.post('/api/admin/simulate/'+t['id'],json={},headers=h).status_code==403

def test_admin_and_csrf(client,admin):
    c,h=admin
    assert c.post('/api/admin/sessions',json={'action':'start'}).status_code==403
    c.post('/api/admin/logout',json={},headers=h)
    assert c.get('/api/admin/state').status_code==401

def test_cross_origin(client):
    assert client.post('/api/public/tips',json={},headers={'Origin':'https://evil.example'}).status_code==403

def test_private_fields_not_exposed(app,client):
    t=tip(app,email='secret@example.com');app.store.verify(receipt(t))
    top=client.get('/api/public/top').json;assert 'secret@example.com' not in str(top);assert 'BANK123456' not in str(top)
    assert client.get('/api/public/tips/'+t['id']).status_code==404
    public=client.get('/api/public/tips/'+t['id'],headers={'X-Tip-Token':t['token']}).json
    assert 'reference' not in public and 'email' not in public
    overlaystate=client.get('/api/overlay/state?key='+'o'*48).json
    assert 'secret@example.com' not in str(overlaystate)

def test_email_groups_but_names_do_not(app):
    t1=tip(app,email='same@example.com');t2=app.store.create_tip(dict(name='New name',amount=100,email='SAME@example.com'),True)
    assert t1['supporter_id']==t2['supporter_id'];assert tip(app)['supporter_id']!=tip(app)['supporter_id']

def test_blocked_supporter_cannot_create(app,admin):
    c,h=admin;t=tip(app,email='b@example.com');c.post('/api/admin/supporters/'+t['supporter_id'],json={'blocked':True,'muted':True},headers=h)
    try:tip(app,email='b@example.com');assert False
    except Problem as e:assert e.status==403

def test_test_alert_no_money(app,admin):
    c,h=admin;assert c.post('/api/admin/alerts',json={'action':'test'},headers=h).status_code==200
    with app.store.db() as db:assert app.store.summary(db)['count']==0

def test_queue_claims_distinct_channels_and_ack(app,admin):
    c,h=admin;c.post('/api/admin/alerts',json={'action':'test'},headers=h)
    p=overlay(app,'claim',{'channel':'horizontal','owner':'one'}).json['alert'];assert p
    assert overlay(app,'claim',{'channel':'horizontal','owner':'two'}).json['alert'] is None
    assert overlay(app,'claim',{'channel':'vertical','owner':'v'}).json['alert']['event_id']==p['event_id']
    bad=overlay(app,'ack',dict(channel='horizontal',owner='two',event_id=p['event_id']));assert bad.status_code==409
    assert overlay(app,'ack',dict(channel='horizontal',owner='one',event_id=p['event_id'])).status_code==200

def test_refund_cancels_queued_alert_and_totals(app,admin):
    c,h=admin;start(admin);t=tip(app);app.store.verify(receipt(t))
    assert c.post('/api/admin/transactions/'+t['id'],json={'status':'REFUNDED','reason':'Refund sent in bank app'},headers=h).status_code==200
    assert overlay(app,'claim',{'channel':'horizontal','owner':'one'}).json['alert'] is None
    with app.store.db() as db:assert app.store.summary(db)['count']==0;assert db.execute('SELECT count(*) FROM audit').fetchone()[0]>0

def test_manual_correction_audited_no_automatic_alert(app,admin):
    c,h=admin;start(admin);t=tip(app)
    r=c.post('/api/admin/transactions/'+t['id'],json={'status':'MANUAL','reason':'Checked bank reference offline','actual_amount':'100.00'},headers=h);assert r.status_code==200
    with app.store.db() as db:assert app.store.summary(db)['actual']==10000;assert db.execute('SELECT count(*) FROM alerts').fetchone()[0]==0

def test_pending_cannot_replay(app,admin):
    c,h=admin;t=tip(app);assert c.post('/api/admin/alerts',json={'action':'replay','id':t['id']},headers=h).status_code==400

def test_goals_crud_reset_history(app,admin):
    c,h=admin;t=tip(app);app.store.verify(receipt(t))
    d=dict(title='Custom weekly',target=2000,starting=50,period='week',reset='automatic',enabled=True,design='compact',style='segments')
    r=c.post('/api/admin/goals',json=d,headers=h);assert r.status_code==200;gid=r.json['id']
    s=c.get('/api/admin/state').json;assert s['goals'][0]['current']==15000
    assert c.post('/api/admin/goals',json={'id':gid,'delete':True},headers=h).status_code==200
    with app.store.db() as db:assert app.store.summary(db)['count']==1

def test_ist_period_boundaries(app,monkeypatch):
    import acepressure.domain as domain
    fixed=int(datetime(2026,10,5,0,5,tzinfo=IST).timestamp());monkeypatch.setattr(domain,'now',lambda:fixed)
    with app.store.db() as db:
        begin,end,_=app.store.period('week',db);assert datetime.fromtimestamp(begin,IST).isoformat().startswith('2026-10-05T00:00')
        begin,end,_=app.store.period('last_month',db);assert datetime.fromtimestamp(begin,IST).day==1;assert datetime.fromtimestamp(end,IST).month==10

def test_custom_analytics(app,admin):
    c,h=admin;t=tip(app);app.store.verify(receipt(t));r=c.get('/api/admin/analytics?period=custom&start='+str(now()-10)+'&end='+str(now()+10));assert r.json['summary']['count']==1

def test_csv_formula_neutralized(app,admin):
    c,h=admin;t=app.store.create_tip({'name':'=HYPERLINK("bad")','amount':100},True)
    r=c.get('/api/admin/transactions?export=csv');assert r.status_code==200;assert "'=HYPERLINK" in r.text

def test_backup_integrity(app):
    t=tip(app);app.store.verify(receipt(t));path=app.store.backup()
    with sqlite3.connect(path) as db:assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok';assert db.execute("SELECT count(*) FROM tips WHERE status='VERIFIED'").fetchone()[0]==1

def test_filter_and_xss_stored_as_text(app,client):
    t=app.store.create_tip(dict(amount=100,name='<script>alert(1)</script>',message='SHIT <img onerror=alert(1)>'),True)
    assert '<' not in t['name'];assert '[filtered]' in t['message'];assert '<' not in t['message']
    assert "script-src 'self'" in client.get('/').headers['Content-Security-Policy']

def test_money_exact_and_invalid():
    assert money('100.37')==10037
    for s in ['NaN','Infinity','-1','1.234','garbage']:
        try:money(s);assert False
        except Problem:pass

def test_reject_stale_or_future_receipt(app):
    t=tip(app)
    for ts in [now()+1000,now()-90000]:
        d=receipt(t);d['received_at']=ts
        try:app.store.verify(d);assert False
        except Problem:pass

def test_missing_reference_is_not_auto_verified(app):
    t=tip(app);d=receipt(t);d['reference']=''
    try:app.store.verify(d);assert False
    except Problem:pass

def test_public_rate_limit(client):
    for _ in range(15):client.post('/api/public/tips',json={})
    assert client.post('/api/public/tips',json={}).status_code==429

def test_unknown_sender_raw_parser_rejects(app,admin):
    from acepressure.parsers import parse_receipt
    s=app.store.settings()|dict(bridge_enabled=True,bank_sender='BANK',parser='example-credit-v1')
    r=parse_receipt({'sender':'BANK','sms':'Credit INR 100.37 via UPI Ref ABC123456','received_at':now()},s);assert r['amount']=='100.37'
    for text in ['Debit INR 100.37 via UPI Ref ABC123456','Your balance INR 50000.00','Credit INR 1 via UPI Ref ABC123456']:
        try:parse_receipt({'sender':'BANK','sms':text},s);assert False
        except Problem:pass

def test_qr_live_only(app,admin):
    c,h=admin;t=tip(app);assert c.get('/api/public/tips/'+t['id']+'/qr?token='+t['token']).status_code==409
    c.post('/api/admin/settings',json={'upi_id':'example@bank','payee_name':'Example'},headers=h);app.config['DEMO_MODE']=False
    r=c.get('/api/public/tips/'+t['id']+'/qr?token='+t['token']);assert r.status_code==200 and r.data.startswith(b'\x89PNG')

def test_no_default_goal(app):
    with app.store.db() as db:assert app.store.goal_values(db)==[]

def test_manual_reference_deduplicates_bridge(app,admin):
    c,h=admin;t=tip(app)
    r=c.post('/api/admin/transactions/'+t['id'],json={'status':'MANUAL','reference':'BANKMANUAL1','reason':'Verified against bank app'},headers=h);assert r.status_code==200
    assert app.store.verify(receipt(t,'BANKMANUAL1'))['duplicate']
    t2=tip(app)
    assert c.post('/api/admin/transactions/'+t2['id'],json={'status':'MANUAL','reference':'BANKMANUAL1','reason':'Duplicate attempt'},headers=h).status_code==409

def test_campaign_dates_and_reset_do_not_delete(app,admin,monkeypatch):
    import acepressure.domain as domain
    c,h=admin;t=tip(app);app.store.verify(receipt(t))
    c.post('/api/admin/goals',json={'title':'Future campaign','target':1000,'period':'lifetime','reset':'automatic','starts':now()+100,'ends':now()+1000},headers=h)
    with app.store.db() as db:assert app.store.goal_values(db)[0]['current']==0
    c.post('/api/admin/goals',json={'title':'Weekly','target':1000,'period':'week','reset':'automatic'},headers=h)
    original=now();monkeypatch.setattr(domain,'now',lambda:original+8*86400)
    with app.store.db() as db:
        assert app.store.goal_values(db)[1]['current']==0
        assert app.store.summary(db)['count']==1

def test_invalid_api_values_are_400(app,admin):
    c,h=admin
    assert c.get('/api/admin/analytics?period=custom&start=banana&end=1').status_code==400
    assert c.post('/api/admin/settings',json={'minimum':20.5},headers=h).status_code==400
