import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def flags(app,sid):
    with app.store.db() as db:r=db.execute('SELECT blocked,muted FROM supporters WHERE id=?',(sid,)).fetchone();return r['blocked'],r['muted']
def moderate(admin,sid,body):c,h=admin;r=c.post('/api/admin/supporters/'+sid,json=body,headers=h);assert r.status_code==200 and r.json=={'ok':True};return r

def test_muting_keeps_a_block_and_unblocking_keeps_a_mute(app,admin):
    sid=app.store.create_tip(dict(amount=100,name='Rahul'),True)['supporter_id']
    moderate(admin,sid,{'blocked':True,'muted':True});assert flags(app,sid)==(1,1)
    moderate(admin,sid,{'muted':True});assert flags(app,sid)==(1,1)  # Live activity "Mute supporter" on a blocked supporter
    moderate(admin,sid,{'blocked':False});assert flags(app,sid)==(0,1)
    moderate(admin,sid,{'muted':False});assert flags(app,sid)==(0,0)
    moderate(admin,sid,{'blocked':True});assert flags(app,sid)==(1,0)
    moderate(admin,sid,{});assert flags(app,sid)==(1,0)
    with app.store.db() as db:audit=[json.loads(r[0]) for r in db.execute("SELECT detail FROM audit WHERE action='supporter_moderation' ORDER BY id")]
    assert audit==[{'blocked':True,'muted':True},{'muted':True},{'blocked':False},{'muted':False},{'blocked':True}]

def test_dashboard_sends_only_the_flag_it_changes():
    js=(ROOT/'acepressure/static/admin.js').read_text(encoding='utf-8')
    assert "button('Mute supporter',()=>action(()=>A('supporters/'+t.supporter_id,{muted:true})))" in js
    assert 'muted:true,blocked:false' not in js and 'muted:!!x.muted' not in js and 'blocked:!!x.blocked' not in js
