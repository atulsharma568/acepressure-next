import inspect,re
from pathlib import Path
from acepressure.domain import now,Store
from acepressure.paytm_bridge import ingest
ROOT=Path(__file__).resolve().parents[1]

def tip(app,**kw):return app.store.create_tip({'amount':100,'name':'Rahul','message':'Nice shot','tts':True,**kw},True)
def start(admin):c,h=admin;assert c.post('/api/admin/sessions',json={'action':'start','title':'Ranked'},headers=h).status_code==200
def pay(admin,t):c,h=admin;assert c.post('/api/admin/simulate/'+t['id'],json={},headers=h).json['outcome']=='verified'
def recent(admin):c,h=admin;return {r['id']:r for r in c.get('/api/admin/state').json['recent']}
def overlay(app,path,body):return app.test_client().post('/api/overlay/'+path,json=body,headers={'X-Overlay-Token':'o'*48})
def inbox(app,received,n):
    with app.store.db(True) as db:db.execute("INSERT INTO paytm_inbox(fingerprint,received,amount,status,reason) VALUES(?,?,100,'REVIEW','unmatched_amount')",('f'+str(n),received))

def test_review_count_covers_the_last_day(app,admin):
    c,h=admin;t=now()
    assert c.get('/api/admin/state').json['health']['review_count']==0
    inbox(app,t-60,1);inbox(app,t-2*86400,2)
    with app.store.db(True) as db:db.execute("INSERT INTO paytm_inbox(fingerprint,received,amount,status,reason) VALUES('f3',?,100,'IGNORED','checked')",(t,))
    health=c.get('/api/admin/state').json['health']
    assert health['review_count']==1 and health['oldest_review_at']==t-60
    assert c.get('/api/admin/paytm').json['health']['review_count']==1

def test_alert_state_follows_the_overlay(app,admin):
    early=tip(app);pay(admin,early)  # verified while no session runs: no alert at all
    assert recent(admin)[early['id']]['alert_state'] is None and recent(admin)[early['id']]['session_id'] is None
    start(admin);t=tip(app,name='Priya');pay(admin,t)
    row=recent(admin)[t['id']];assert row['alert_state']=='queued' and row['session_id']
    claim=overlay(app,'claim',{'channel':'horizontal','owner':'obs-test'}).json['alert'];assert claim['id']==t['id']
    assert recent(admin)[t['id']]['alert_state']=='playing'
    assert overlay(app,'ack',{'event_id':claim['event_id'],'channel':'horizontal','owner':'obs-test'}).status_code==200
    assert recent(admin)[t['id']]['alert_state']=='done'
    late=tip(app,name='Late');pay(admin,late)
    with app.store.db(True) as db:db.execute('UPDATE alerts SET expires=? WHERE tip_id=?',(now()-1,late['id']))
    assert recent(admin)[late['id']]['alert_state']=='expired'  # a queued alert past its window can no longer play
    c,h=admin;assert c.post('/api/admin/alerts',json={'action':'replay','id':late['id']},headers=h).status_code==200
    assert recent(admin)[late['id']]['alert_state']=='queued'  # the newest alert wins

def test_tip_status_says_whether_an_alert_is_coming(app,admin,client):
    def status(t):return client.get('/api/public/tips/'+t['id'],headers={'X-Tip-Token':t['token']}).json
    t=tip(app);pay(admin,t);d=status(t)
    assert d['status']=='VERIFIED' and d['alert_queued'] is False and d['needs_review'] is False
    start(admin);t=tip(app);assert status(t)['alert_queued'] is False
    pay(admin,t);assert status(t)['alert_queued'] is True

def test_paytm_state_reports_sessions(app,admin):
    c,h=admin;t=tip(app);d=c.get('/api/admin/paytm').json
    assert d['active_session_id'] is None and d['pending'][0]['session_id'] is None
    start(admin);t=tip(app,name='Second');d=c.get('/api/admin/paytm').json
    assert d['active_session_id'] and {p['id']:p for p in d['pending']}[t['id']]['session_id']==d['active_session_id']
    assert 'health' in d and 'public_base_url' in d and 'config' in d

def test_paytm_page_explains_every_review_reason(app):
    src=inspect.getsource(ingest)
    found={x for pair in re.findall(r"reason='([a-z_]+)'(?: if [^:\n]+? else '([a-z_]+)')?",src) for x in pair if x}
    review=found-{'notification_match'}
    assert len(review)==10 and 'ambiguous_match' in review and 'inactive_session' in review
    js=(ROOT/'acepressure/static/paytm_bridge.js').read_text(encoding='utf-8')
    keys=set(re.findall(r"(\w+):'",re.search(r'const REASONS=\{(.*?)\};',js).group(1)))
    assert found<=keys
    assert re.search(r'setInterval\(.{0,200}?,10000\)',js) and 'AcePressure payments' in js and 'active_session_id' in js
    assert 'Play alert on stream (only works while this tip’s stream session is running)' in js
    admin=(ROOT/'acepressure/static/admin.js').read_text(encoding='utf-8')
    assert 'No stream session running' in admin and ' your review (oldest ' in admin and 'Missed – use Replay' in admin
    public=(ROOT/'acepressure/static/public.js').read_text(encoding='utf-8')
    assert 'support is on its way to the stream. Watch for your alert!' in public and 'support is on the stream.' not in public

def test_browser_checks_match_the_thank_you_heading():
    for name in ['browser_smoke.py','launch_browser_check.py']:
        text=(ROOT/'tests'/name).read_text(encoding='utf-8')
        assert 'You made a difference.' not in text and "re.compile(r'^Thank you,')" in text,name
    assert "'Thank you, '" in (ROOT/'acepressure/static/public.js').read_text(encoding='utf-8')

def test_alert_tip_index_migration_is_idempotent(app,tmp_path):
    Store(str(tmp_path),'s'*48);Store(str(tmp_path),'s'*48)  # migrations re-run on every start
    with app.store.db() as db:assert db.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='alerts_tip'").fetchone()
