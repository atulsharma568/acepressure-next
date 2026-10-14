import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import pytest
from acepressure.domain import now,IST
from acepressure.paytm_match import parse_event,process_event

def setup_tip(app):
    clock=now();stamp=clock//60*60
    with app.store.db(True) as db:db.execute('INSERT INTO sessions VALUES(?,?,?,NULL)',('session','test',clock-120))
    tip=app.store.create_tip({'name':'Demo','amount':100},True)
    with app.store.db(True) as db:db.execute('UPDATE tips SET created=?,expires=? WHERE id=?',(stamp-60,stamp+600,tip['id']))
    return tip,clock,stamp

def notification(tip,stamp):
    dt=datetime.fromtimestamp(stamp,IST)
    return f"Received ₹{tip['requested_paise']/100:.2f} from Test Sender\nDeposited in your Example Bank - 0000 on {dt.day} {dt.strftime('%B')} at {dt.strftime('%I:%M %p')}"

def run(app,text,clock,matching=True):
    with app.store.db(True) as db:return process_event(app.store,db,text,clock,matching)[0]

def test_exact_match_only_once(app):
    tip,clock,stamp=setup_tip(app);text=notification(tip,stamp)
    first=run(app,text,clock);second=run(app,text.replace('\n','  '),clock)
    assert first['outcome']=='demo_matched' and first['alert_created']
    assert second['duplicate_input'] and not second['alert_created']
    with app.store.db() as db:
        t=dict(db.execute('SELECT * FROM tips WHERE id=?',(tip['id'],)).fetchone())
        assert t['actual_paise']==tip['requested_paise'] and t['reference'] is None
        assert t['verification_source']=='demo-paytm-notification'
        alerts=db.execute('SELECT payload FROM alerts').fetchall()
        assert len(alerts)==1 and json.loads(alerts[0][0])['test'] is True
        assert db.execute('SELECT count(*) FROM receipts').fetchone()[0]==0

@pytest.mark.parametrize('case,expected',[('round','unmatched_amount'),('expired','unmatched_amount'),('old','stale_or_future_notification'),('future','stale_or_future_notification'),('same_minute','payment_time_before_or_ambiguous'),('ended','inactive_stream_session'),('blocked','blocked_supporter'),('near_expiry','payment_time_near_expiry'),('bad_format','unsupported_payment_format')])
def test_fail_closed(app,case,expected):
    tip,clock,stamp=setup_tip(app)
    if case=='near_expiry':clock=stamp+10
    with app.store.db(True) as db:
        if case=='expired':db.execute('UPDATE tips SET expires=?',(clock-1,))
        if case=='same_minute':db.execute('UPDATE tips SET created=?',(stamp+1,))
        if case=='ended':db.execute('UPDATE sessions SET ended=?',(clock,))
        if case=='blocked':db.execute('UPDATE supporters SET blocked=1')
        if case=='near_expiry':db.execute('UPDATE tips SET expires=?',(clock+1,))
    if case=='round':tip['requested_paise']=10000
    text=notification(tip,stamp-660 if case=='old' else stamp+120 if case=='future' else stamp)
    if case=='bad_format':text='Cashback received ₹100'
    r=run(app,text,clock)
    assert r['outcome']==expected and not r['alert_created']
    with app.store.db() as db:assert db.execute('SELECT count(*) FROM alerts').fetchone()[0]==0

def test_capture_cannot_be_replayed_after_enable(app):
    tip,clock,stamp=setup_tip(app);text=notification(tip,stamp)
    assert run(app,text,clock,False)['outcome']=='capture_only'
    assert run(app,text,clock,True)['outcome']=='duplicate_notification'

def test_concurrent_retries(app):
    tip,clock,stamp=setup_tip(app);text=notification(tip,stamp)
    with ThreadPoolExecutor(max_workers=5) as pool:results=list(pool.map(lambda _:run(app,text,clock),range(5)))
    assert sum(r['alert_created'] for r in results)==1

def test_api_mode_and_date_replay(app,admin):
    tip,clock,stamp=setup_tip(app);client,csrf=admin
    token=client.post('/api/admin/paytm-test/start',json={'matching':True},headers=csrf).json['token']
    headers={'Authorization':'Bearer '+token}
    for date,dup in [('one',False),('two',True)]:
        r=client.post('/api/bridge/paytm-test',json={'text':notification(tip,stamp),'notification_date':date},headers=headers)
        assert r.status_code==200 and r.json['mode']=='demo_matching'
        assert r.json['duplicate_input']==dup and r.json['verified'] is False

def test_timestamp_year_boundary():
    clock=int(datetime(2027,1,1,0,1,tzinfo=IST).timestamp())
    e=parse_event('Received ₹1.37 from Test Sender Deposited in your Bank - 0000 on 31 December at 11:59 PM',clock)
    assert clock-e['minute']==120

def test_duplicate_survives_store_reopen(app):
    from acepressure.domain import Store
    tip,clock,stamp=setup_tip(app);text=notification(tip,stamp)
    assert run(app,text,clock)['alert_created']
    app.store=Store(app.store.path,app.store.secret)
    assert run(app,text,clock)['duplicate_input']

def test_ambiguous_amount(app):
    tip,clock,stamp=setup_tip(app)
    other=app.store.create_tip({'name':'Other','amount':100},True)
    with app.store.db(True) as db:
        db.execute('UPDATE tips SET requested_paise=?,created=? WHERE id=?',(tip['requested_paise'],stamp-60,other['id']))
    assert run(app,notification(tip,stamp),clock)['outcome']=='ambiguous_amount'
