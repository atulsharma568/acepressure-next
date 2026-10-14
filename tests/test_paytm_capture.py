import pytest
from acepressure.paytm_capture import parse_amount

TEXT='Received ₹11 from Test Sender\nDeposited in your Example Bank - 0000 on 10 October at 12:29 AM'

def start(admin):
    client, headers = admin
    response=client.post('/api/admin/paytm-test/start',json={},headers=headers)
    assert response.status_code==200
    return client, {'Authorization':'Bearer '+response.json['token']}

def test_capture_never_verifies_or_alerts(app,admin):
    client,headers=start(admin)
    tip=app.store.create_tip({'name':'Tester','amount':100},True)
    text=TEXT.replace('₹11',f"₹{tip['requested_paise']/100:.2f}")
    for i in range(2):
        r=client.post('/api/bridge/paytm-test',json={'text':text},headers=headers)
        assert r.status_code==200
        assert r.json['duplicate_input']==bool(i)
        assert r.json['verified'] is False and r.json['alert_created'] is False
    with app.store.db() as db:
        assert db.execute('SELECT status FROM tips WHERE id=?',(tip['id'],)).fetchone()[0]=='PENDING'
        assert db.execute('SELECT count(*) FROM alerts').fetchone()[0]==0
        assert db.execute('SELECT count(*) FROM receipts').fetchone()[0]==0
        row=dict(db.execute('SELECT * FROM paytm_captures').fetchone())
        assert row['repeats']==1 and row['amount_paise']==tip['requested_paise']
        assert 'Test Sender' not in str(row) and '0000' not in str(row)

def test_auth_and_stop(admin):
    client,headers=start(admin)
    assert client.post('/api/bridge/paytm-test',json={'text':TEXT}).status_code==401
    assert client.post('/api/admin/paytm-test/start',json={}).status_code==403
    assert client.get('/admin/paytm-test').status_code==200
    client.post('/api/admin/paytm-test/stop',json={},headers=admin[1])
    assert client.post('/api/bridge/paytm-test',json={'text':TEXT},headers=headers).status_code==401

def test_disabled_on_live(app,admin):
    client,headers=start(admin)
    app.config['DEMO_MODE']=False
    assert client.post('/api/bridge/paytm-test',json={'text':TEXT},headers=headers).status_code==404
    assert client.get('/admin/paytm-test').status_code==404

def test_token_rotation_and_expiry(admin,monkeypatch):
    client,old=start(admin)
    _,new=start(admin)
    assert client.post('/api/bridge/paytm-test',json={'text':TEXT},headers=old).status_code==401
    from acepressure.domain import now
    future=now()+1801
    monkeypatch.setattr('acepressure.paytm_capture.now',lambda:future)
    assert client.post('/api/bridge/paytm-test',json={'text':TEXT},headers=new).status_code==401

def test_invalid_and_unrecognized(admin):
    client,headers=start(admin)
    assert client.post('/api/bridge/paytm-test',json={'text':'x'*5000},headers=headers).status_code==413
    assert client.post('/api/bridge/paytm-test',json={'text':TEXT,'amount':50000},headers=headers).status_code==400
    r=client.post('/api/bridge/paytm-test',json={'text':'Cashback ₹50000!'},headers=headers)
    assert r.json['amount_paise'] is None and r.json['outcome']=='unrecognized_text'

@pytest.mark.parametrize('amount,expected',[('11',1100),('11.37',1137),('1,000.05',100005)])
def test_amount_parser(amount,expected):
    assert parse_amount(TEXT.replace('₹11','₹'+amount))==expected

@pytest.mark.parametrize('text',['Sent ₹11 to Someone','Received ₹0 from X\nDeposited in your Bank','Received ₹11.123 from X\nDeposited in your Bank','Received ₹11 from X','<script>alert(1)</script>'])
def test_parser_fails_closed(text):
    assert parse_amount(text) is None

def test_unauthenticated_admin(client):
    assert client.get('/api/admin/paytm-test').status_code==401
    assert client.get('/admin/paytm-test').status_code==401

def test_rate_limit(admin):
    client,headers=start(admin)
    for _ in range(60):
        assert client.post('/api/bridge/paytm-test',json={'text':TEXT},headers=headers).status_code==200
    assert client.post('/api/bridge/paytm-test',json={'text':TEXT},headers=headers).status_code==429
