import pytest
from acepressure.domain import Problem

def test_merge_preserves_money_and_email_alias(app,admin):
    c,h=admin
    a=app.store.create_tip({'name':'Dinesh','amount':20,'email':'one@example.test'},True)
    b=app.store.create_tip({'name':'Dinesh','amount':20,'email':'two@example.test'},True)
    with app.store.db(True) as db:
        db.execute("UPDATE tips SET status='VERIFIED',verified=created,actual_paise=requested_paise")
        before=app.store.summary(db)
    r=c.post('/api/admin/supporters/merge',json={'source':a['supporter_id'],'target':b['supporter_id'],'reason':'Confirmed same person'},headers=h)
    assert r.status_code==200
    with app.store.db() as db:
        after=app.store.summary(db)
        assert after['total']==before['total']==4000
        assert after['actual']==before['actual']
        assert len(after['leaderboard'])==1 and after['leaderboard'][0]['count']==2
        assert db.execute('SELECT count(*) FROM tips').fetchone()[0]==2
    assert len(c.get('/api/admin/supporters').json['supporters'])==1
    t=app.store.create_tip({'name':'New name','amount':20,'email':'one@example.test'},True)
    assert t['supporter_id']==b['supporter_id']
    assert c.post('/api/admin/supporters/merge',json={'source':a['supporter_id'],'target':b['supporter_id'],'reason':'repeat merge'},headers=h).status_code==409

def test_merge_auth_and_blocks(app,admin):
    c,h=admin;a=app.store.create_tip({'name':'Dinesh','amount':20,'email':'a@example.test'},True);b=app.store.create_tip({'name':'Dinesh','amount':20},True)
    d={'source':a['supporter_id'],'target':b['supporter_id'],'reason':'Confirmed duplicate'}
    assert c.post('/api/admin/supporters/merge',json=d).status_code==403
    with app.store.db(True) as db:db.execute('UPDATE supporters SET blocked=1 WHERE id=?',(a['supporter_id'],))
    assert c.post('/api/admin/supporters/merge',json=d,headers=h).status_code==200
    with pytest.raises(Problem):app.store.create_tip({'name':'Dinesh','amount':20,'email':'a@example.test'},True)
