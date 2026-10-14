import io
from PIL import Image

def tip(c,**kw):
    return c.post('/api/public/tips',json=dict(amount=20,name='Dinesh',**kw))
def ids(app):
    with app.store.db() as db:return [r[0] for r in db.execute('SELECT supporter_id FROM tips ORDER BY rowid')]

def test_browser_opt_in_and_forget(app,client):
    assert tip(client,remember=True).status_code==201
    assert tip(client,remember=True).status_code==201
    assert len(set(ids(app)))==1
    other=app.test_client();assert tip(other,remember=True).status_code==201
    assert len(set(ids(app)))==2
    assert client.post('/api/public/forget-browser',json={}).status_code==200
    assert tip(client,remember=True).status_code==201
    assert len(set(ids(app)))==3

def test_without_consent_never_groups(app,client):
    tip(client);tip(client)
    assert len(set(ids(app)))==2
    assert client.get_cookie('ace_demo_supporter') is None

def test_cookie_private_and_block_applies(app,client):
    response=tip(client,remember=True)
    assert 'HttpOnly' in response.headers['Set-Cookie']
    with app.store.db(True) as db:db.execute('UPDATE supporters SET blocked=1')
    assert tip(client,remember=True).status_code==403

def test_browser_alias_survives_merge(app,admin):
    c,h=admin;tip(c,remember=True)
    other=app.test_client();tip(other,remember=True)
    source,target=ids(app)
    r=c.post('/api/admin/supporters/merge',json={'source':source,'target':target,'reason':'Confirmed duplicate'},headers=h)
    assert r.status_code==200,r.json
    tip(c,remember=True)
    assert set(ids(app))=={target}

def test_visual_security_and_upload(app,admin):
    c,h=admin
    assert app.test_client().get('/api/admin/visuals').status_code==401
    assert app.test_client().get('/admin/visual-preview').status_code==401
    assert c.post('/api/admin/visuals',json={'accent':'url(evil)'},headers=h).status_code==400
    assert c.post('/api/admin/visuals',json={'alert_image':'../secret.png'},headers=h).status_code==400
    assert c.post('/api/admin/visuals',json={'radius':True},headers=h).status_code==400
    assert c.post('/api/admin/visual-assets',data={'file':(io.BytesIO(b'<svg/>'),'bad.svg')},headers=h).status_code==400
    out=io.BytesIO();Image.new('RGBA',(20,20),(255,0,0,100)).save(out,format='PNG');out.seek(0)
    r=c.post('/api/admin/visual-assets',data={'file':(out,'logo.png')},headers=h)
    assert r.status_code==200,r.json
    name=r.json['name']
    assert c.get('/media/'+name).status_code==200
    assert c.post('/api/admin/visuals',json={'logo':name,'accent':'#123456'},headers=h).status_code==200
    assert c.get('/api/admin/visuals').json['visuals']['logo']==name
    overlay=c.get('/api/overlay/state',headers={'X-Overlay-Token':'o'*48}).json
    assert overlay['visuals']['accent']=='#123456'
    assert c.get('/admin/visual-preview').status_code==200
    with app.store.db() as db:assert db.execute('SELECT COUNT(*) FROM alerts').fetchone()[0]==0
