"""Edge and Piper speak in OBS: the overlay plays audio the server makes, and Voice Studio says why when it can't."""
import re
from pathlib import Path
from werkzeug.security import generate_password_hash
import acepressure.app
from acepressure import tts_service
from acepressure.domain import Problem, now
ROOT=Path(__file__).resolve().parents[1]
KEY={'X-Overlay-Token':'o'*48}
VERSION=(ROOT/'VERSION').read_text(encoding='utf-8').strip()

def queue_test_alert(admin,engine):
    c,h=admin
    assert c.post('/api/admin/settings',json={'tts_engine':engine},headers=h).status_code==200
    assert c.post('/api/admin/alerts',json={'action':'test'},headers=h).status_code==200
def last_alert(app):
    with app.store.db() as db:return db.execute('SELECT max(id) FROM alerts').fetchone()[0]
def tts(app,event_id):return app.test_client().get(f'/api/overlay/tts/{event_id}',headers=KEY)
def report(app,code):return app.test_client().post('/api/overlay/tts-status',json={'code':code},headers=KEY)

def test_overlay_asks_the_server_for_every_server_engine():
    js=(ROOT/'acepressure'/'static'/'overlay.js').read_text(encoding='utf-8')
    engines=re.search(r"const SERVER_TTS=\[([^\]]*)\]",js)
    assert engines and set(re.findall(r"'(\w+)'",engines.group(1)))=={'windows','azure','edge','piper'}
    assert js.count('SERVER_TTS.includes(engine)')==1 and js.index('async function speak(')<js.index('SERVER_TTS.includes(engine)')
    assert "engine==='windows'||engine==='azure'" not in js
    assert 'AbortController' in js and 'signal:' in js and '20000' in js

def test_edge_audio_is_served_to_the_overlay(app,admin,monkeypatch,tmp_path):
    clip=tmp_path/'edge-test.mp3';clip.write_bytes(b'ID3'+b'\0'*600);calls=[]
    def fake(directory,text,voice,engine):calls.append((text,voice,engine));return clip
    monkeypatch.setattr(tts_service,'synthesize',fake)
    queue_test_alert(admin,'edge')
    r=tts(app,last_alert(app))
    assert r.status_code==200 and r.mimetype=='audio/mpeg' and r.data==clip.read_bytes()
    assert calls==[('This is a test alert. No money received.','en-IN','edge')]

def test_provider_error_reaches_voice_studio(app,admin,monkeypatch):
    def broken(directory,text,voice,engine):raise Problem('Edge TTS is not installed. Run Install_Edge_TTS.bat to add it to your .venv.',503)
    monkeypatch.setattr(tts_service,'synthesize',broken)
    queue_test_alert(admin,'edge')
    r=tts(app,last_alert(app))
    assert r.status_code==503 and 'Install_Edge_TTS.bat' in r.json['error']
    assert report(app,'provider_failed').status_code==200
    c,_=admin;d=c.get('/api/admin/tts/health').json
    assert d['last']['code']=='provider_failed'
    assert 'Install_Edge_TTS.bat' in d['provider_error']['message'] and d['provider_error']['engine']=='edge'

def test_provider_error_only_explains_a_recent_provider_failure(app,admin):
    c,_=admin
    def health():return c.get('/api/admin/tts/health').json
    assert health()['last'] is None and health()['provider_error'] is None
    app.extensions['ace_tts_error']={'message':'Piper produced an empty audio clip.','engine':'piper','at':now()}
    report(app,'played');assert health()['provider_error'] is None
    report(app,'provider_failed');assert health()['provider_error']['message']=='Piper produced an empty audio clip.'
    app.extensions['ace_tts_error']['at']=now()-121
    assert health()['provider_error'] is None and health()['last']['code']=='provider_failed'

def test_long_provider_messages_are_cut(app,admin,monkeypatch):
    def broken(directory,text,voice,engine):raise Problem('x'*500,503)
    monkeypatch.setattr(tts_service,'synthesize',broken)
    queue_test_alert(admin,'piper')
    assert tts(app,last_alert(app)).status_code==503
    assert app.extensions['ace_tts_error']['message']=='x'*240 and app.extensions['ace_tts_error']['engine']=='piper'

def test_muted_and_expired_alerts_still_get_404(app,admin,monkeypatch):
    c,h=admin;calls=[]
    monkeypatch.setattr(tts_service,'synthesize',lambda *a:calls.append(a))
    queue_test_alert(admin,'edge');event=last_alert(app)
    c.post('/api/admin/settings',json={'muted':True},headers=h)
    assert tts(app,event).status_code==404
    c.post('/api/admin/settings',json={'muted':False},headers=h)
    with app.store.db(True) as db:db.execute('UPDATE alerts SET expires=?',(now()-1,))
    assert tts(app,event).status_code==404
    assert calls==[] and 'ace_tts_error' not in app.extensions

def test_overlay_and_admin_pages_load_versioned_scripts(client):
    assert '/static/overlay.js?v='+VERSION in client.get('/overlay/alert').get_data(as_text=True)
    for page in ['/overlay/alert','/overlay/goal','/admin','/obs/activity']:
        assets=re.findall(r'(?:src|href)="(/static/[^"]+\.(?:js|css)[^"]*)"',client.get(page).get_data(as_text=True))
        assert assets and all(re.fullmatch(r'/static/[\w./-]+\.(js|css)\?v='+re.escape(VERSION),a) for a in assets),assets

def test_asset_version_falls_back_to_dev(monkeypatch,tmp_path):
    monkeypatch.setattr(acepressure.app,'ROOT',tmp_path)
    app=acepressure.app.create_app(dict(TESTING=True,DATA_DIR=str(tmp_path/'data'),SECRET_KEY='s'*48,BRIDGE_TOKEN='b'*48,OVERLAY_TOKEN='o'*48,ADMIN_PASSWORD_HASH=generate_password_hash('test-password-123'),DEMO_MODE=True))
    assert app.jinja_env.globals['asset_v']=='dev'
    assert '/static/overlay.js?v=dev' in app.test_client().get('/overlay/alert').get_data(as_text=True)

def test_voice_studio_and_privacy_copy():
    static=ROOT/'acepressure'/'static'
    designer=(static/'designer.js').read_text(encoding='utf-8')
    for code in ['played','voice_missing','provider_failed','playback_failed','unavailable']:assert code+':' in designer
    assert 'Last OBS readout played' in designer and 'd.provider_error' in designer and 'check();' in designer
    assert 'Messages are sent to Microsoft’s online voice service.' in (static/'admin.js').read_text(encoding='utf-8')
    assert 'Voice readout uses Microsoft’s online Edge voices, so your message is sent to Microsoft to be spoken.' in (static/'public.js').read_text(encoding='utf-8')
