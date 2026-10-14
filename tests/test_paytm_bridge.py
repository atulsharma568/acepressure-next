import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from acepressure.domain import now,IST
from acepressure.paytm_bridge import ingest

def enable(admin,auto=False,recipient=''):
    client,csrf=admin
    token=client.post('/api/admin/paytm/config',json={'action':'rotate'},headers=csrf).json['token']
    r=client.post('/api/admin/paytm/config',json={'action':'enable','auto_match':auto,'acknowledge_notification_risk':auto,'recipient':recipient},headers=csrf)
    assert r.status_code==200,r.json
    return {'Authorization':'Bearer '+token}

def setup(app,offset=10):
    stamp=now()//60*60;clock=stamp+30
    with app.store.db(True) as db:db.execute('INSERT INTO sessions VALUES(?,?,?,NULL)',('s','test',stamp-120))
    tip=app.store.create_tip({'name':'Tester','amount':100},True)
    with app.store.db(True) as db:db.execute('UPDATE tips SET created=?,expires=? WHERE id=?',(stamp+offset,stamp+600,tip['id']))
    dt=datetime.fromtimestamp(stamp,IST)
    text=f"Received ₹{tip['requested_paise']/100:.2f} from Test Sender Deposited in your Example Bank - 0000 on {dt.day} {dt.strftime('%B')} at {dt.strftime('%I:%M %p')}"
    return tip,clock,text

def test_immediate_review_and_approval(app,admin):
    enable(admin,True);tip,clock,text=setup(app)
    r=ingest(app.store,text,clock,True)
    assert r['status']=='REVIEW' and not r['alert_created']
    client,csrf=admin
    body={'action':'approve','tip_id':tip['id'],'checked_bank':True,'reason':'Checked payment history','alert':True}
    res=client.post('/api/admin/paytm/review/'+str(r['id']),json=body,headers=csrf)
    assert res.status_code==200 and res.json['alert_created']
    assert client.post('/api/admin/paytm/review/'+str(r['id']),json=body,headers=csrf).status_code==409
    with app.store.db() as db:
        assert db.execute('SELECT status FROM tips').fetchone()[0]=='MANUAL'
        assert db.execute('SELECT count(*) FROM alerts').fetchone()[0]==1

def test_precise_auto_and_concurrency(app,admin):
    enable(admin,True);tip,clock,text=setup(app,-60)
    with ThreadPoolExecutor(max_workers=4) as pool:r=list(pool.map(lambda _:ingest(app.store,text,clock,True),range(4)))
    assert sum(x['alert_created'] for x in r)==1
    assert all(x['bank_verified'] is False for x in r)

def test_delayed_and_expired_review(app,admin):
    enable(admin,True);tip,clock,text=setup(app,-60)
    with app.store.db(True) as db:db.execute('UPDATE tips SET expires=?',(clock-1,))
    r=ingest(app.store,text,clock+650,True)
    assert r['status']=='REVIEW'
    assert not r['alert_created']

def test_recipient_mismatch_cannot_approve(app,admin):
    enable(admin,True,'Other Bank - 9999');tip,clock,text=setup(app,-60)
    r=ingest(app.store,text,clock,True);assert r['outcome']=='recipient_mismatch'
    client,csrf=admin
    res=client.post('/api/admin/paytm/review/'+str(r['id']),json={'action':'approve','tip_id':tip['id'],'checked_bank':True,'reason':'checked history'},headers=csrf)
    assert res.status_code==400

def test_persistent_auth_disable_rotation(app,admin):
    headers=enable(admin);client,csrf=admin
    from acepressure.app import create_app
    other=create_app(dict(app.config));c=other.test_client()
    assert c.post('/api/bridge/paytm',json={'text':'offer'},headers=headers).status_code==200
    assert c.post('/api/bridge/paytm',json={'text':'offer'}).status_code==401
    client.post('/api/admin/paytm/config',json={'action':'disable'},headers=csrf)
    assert c.post('/api/bridge/paytm',json={'text':'offer'},headers=headers).status_code==401
    enable(admin)
    assert c.post('/api/bridge/paytm',json={'text':'offer'},headers=headers).status_code==401

def test_live_configuration_gates(app,admin):
    app.config['DEMO_MODE']=False
    client,csrf=admin
    client.post('/api/admin/paytm/config',json={'action':'rotate'},headers=csrf)
    assert client.post('/api/admin/paytm/config',json={'action':'enable'},headers=csrf).status_code==400
    with app.store.db(True) as db:
        for k,v in [('upi_id','example@upi'),('payee_name','Example')]:db.execute('UPDATE settings SET value=? WHERE key=?',(json.dumps(v),k))
    assert client.post('/api/admin/paytm/config',json={'action':'enable','recipient':'Example Bank - 0000'},headers=csrf).status_code==400
    app.config['PUBLIC_BASE_URL']='https://tips.example.test'
    r=client.post('/api/admin/paytm/config',json={'action':'enable','recipient':'Example Bank - 0000'},headers=csrf)
    assert r.status_code==200
    r=client.post('/api/public/tips',json={'name':'Viewer','amount':100},headers={'Origin':'https://tips.example.test'})
    assert r.status_code==201 and r.json['upi_id']=='example@upi' and 'upi://pay?' in r.json['upi_uri']
    assert client.post('/api/public/tips',json={'name':'Bad','amount':100},headers={'Origin':'https://evil.example'}).status_code==403

def test_admin_auth_and_ack(admin):
    client,csrf=admin
    client.post('/api/admin/paytm/config',json={'action':'rotate'},headers=csrf)
    assert client.post('/api/admin/paytm/config',json={'action':'enable','auto_match':True},headers=csrf).status_code==400
    assert client.post('/api/admin/paytm/config',json={'action':'enable'}).status_code==403

def test_review_status_public(app,admin):
    enable(admin);tip,clock,text=setup(app)
    ingest(app.store,text,clock,True)
    client,_=admin
    r=client.get('/api/public/tips/'+tip['id'],headers={'X-Tip-Token':tip['token']})
    assert r.json['needs_review'] is True
    assert 'fingerprint' not in r.json

def test_expired_only_cannot_auto_alert(app,admin):
    enable(admin,True);tip,clock,text=setup(app,-60)
    with app.store.db(True) as db:db.execute('UPDATE tips SET expires=? WHERE id=?',(clock-1,tip['id']))
    r=ingest(app.store,text,clock,True)
    assert r['outcome']=='expired_tip' and not r['alert_created']
    with app.store.db() as db:
        assert db.execute('SELECT count(*) FROM alerts').fetchone()[0]==0
        assert db.execute('SELECT status FROM tips WHERE id=?',(tip['id'],)).fetchone()[0]=='EXPIRED'

def test_replay_after_manual_approval_cannot_alert(app,admin):
    enable(admin);tip,clock,text=setup(app,-60)
    r=ingest(app.store,text,clock,True);client,csrf=admin
    res=client.post('/api/admin/paytm/review/'+str(r['id']),json={'action':'approve','tip_id':tip['id'],'checked_bank':True,'reason':'Confirmed test history','alert':True},headers=csrf)
    assert res.status_code==200
    repeated=ingest(app.store,text,clock+1,True)
    assert repeated['outcome']=='duplicate_notification' and not repeated['alert_created']
    with app.store.db() as db:assert db.execute('SELECT count(*) FROM alerts').fetchone()[0]==1
