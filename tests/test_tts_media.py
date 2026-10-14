import io,json,shutil,subprocess,wave
from pathlib import Path
import pytest
from acepressure import tts_service
from acepressure.domain import Problem

def wav_bytes():
    b=io.BytesIO()
    with wave.open(b,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(b'\0\0'*2400)
    return b.getvalue()

def test_azure_escapes_text_and_caches(tmp_path,monkeypatch):
    calls=[]
    def fake(path,body=None):calls.append((path,body));return wav_bytes()
    monkeypatch.setattr(tts_service,'azure_request',fake)
    path=tts_service.synthesize(tmp_path,'Hello <voice> & GG','en-IN-TestNeural','azure')
    assert path.read_bytes()==wav_bytes()
    assert b'&lt;voice&gt; &amp; GG' in calls[0][1]
    assert tts_service.synthesize(tmp_path,'Hello <voice> & GG','en-IN-TestNeural','azure')==path
    assert len(calls)==1
    with pytest.raises(Problem):tts_service.synthesize(tmp_path,'hi','bad"voice','azure')

def test_catalog_selection_preview_and_no_secret(app,admin,monkeypatch):
    c,h=admin
    monkeypatch.setattr(tts_service,'catalog',lambda engine,directory=None:[{'id':'Installed Male','label':'Male · English','gender':'Male','locale':'en-IN'},{'id':'Installed Female','label':'Female · English','gender':'Female','locale':'en-IN'}])
    r=c.post('/api/admin/tts/configure',json={'engine':'windows','voices':['Installed Male','Installed Female']},headers=h)
    assert r.status_code==200
    config=c.get('/api/public/config').json
    assert config['voice_labels']['Installed Female'].startswith('Female')
    assert 'AZURE_SPEECH_KEY' not in str(config)
    assert c.post('/api/admin/tts/configure',json={'engine':'windows','voices':['Absent']},headers=h).status_code==400
    calls=[]
    def fake(directory,text,voice,engine):
        calls.append(text);p=directory/'test.wav';p.write_bytes(wav_bytes());return p
    monkeypatch.setattr(tts_service,'synthesize',fake)
    r=c.get('/api/public/voice-preview?voice=Installed%20Male&text=ATTACK')
    assert r.status_code==200 and 'ATTACK' not in calls[-1]
    assert app.test_client().post('/api/admin/tts/preview',json={'voice':'Installed Male'}).status_code==401
    assert c.post('/api/admin/tts/preview',json={'voice':'Installed Male','text':'GG bhai'},headers=h).status_code==200
    r=c.post('/api/overlay/tts-status',json={'code':'voice_missing'},headers={'X-Overlay-Token':'o'*48})
    assert r.status_code==200
    assert c.get('/api/admin/tts/health').json['last']['code']=='voice_missing'

def test_short_video_is_reencoded_silent(app,admin,tmp_path):
    if not shutil.which('ffmpeg'):pytest.skip('FFmpeg is optional on host')
    src=tmp_path/'clip.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=red:s=160x120:d=1','-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-y',str(src)],check=True)
    c,h=admin;r=c.post('/api/admin/visual-assets',data={'file':(io.BytesIO(src.read_bytes()),'clip.mp4')},headers=h)
    assert r.status_code==200,r.json
    filename=r.json['name'];assert filename.endswith('.webm')
    path=app.store.path/'media'/filename
    info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(path)]))
    assert [s['codec_type'] for s in info['streams']]==['video']
    assert c.post('/api/admin/visuals',json={'alert_image':filename,'alert_sound':'chime'},headers=h).status_code==200
    assert c.post('/api/admin/visuals',json={'logo':filename},headers=h).status_code==400
    assert c.post('/api/admin/visual-assets',data={'file':(io.BytesIO(b'bad'),'clip.mp4')},headers=h).status_code==400
