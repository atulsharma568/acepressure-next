"""Setup_Tailscale_URL.bat writes .env only after Tailscale confirms Funnel, and points the phone at the Paytm bridge first."""
import importlib.util, json, subprocess
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('setup_tailscale_funnel',ROOT/'scripts'/'setup_tailscale_funnel.py')
ts=importlib.util.module_from_spec(spec);spec.loader.exec_module(ts)

HOST='atul.tail34d209.ts.net'
STATUS={'BackendState':'Running','Self':{'DNSName':'Atul.tail34d209.ts.net.','HostName':'Atul-PC'}}
FUNNEL_ON=f'# Funnel on:\n#     - https://{HOST}\n\nhttps://{HOST} (Funnel on)\n|-- / proxy http://127.0.0.1:8765\n\n'
TAILNET_ONLY=f'https://{HOST} (tailnet only)\n|-- / proxy http://127.0.0.1:8765\n\n'
ENV=b'APP_SECRET=keep-me\nPUBLIC_BASE_URL=http://localhost:8765\nCOOKIE_SECURE=false\n'

class FakeTailscale:
    """Stands in for subprocess.run and answers the tailscale commands the script runs."""
    def __init__(self,funnel_status,code=0,status=STATUS):
        self.funnel_status,self.code,self.status,self.calls=funnel_status,code,status,[]
    def __call__(self,args,**kw):
        self.calls.append((args,kw))
        if args[1:]==['funnel','status']:return subprocess.CompletedProcess(args,self.code,self.funnel_status,'')
        return subprocess.CompletedProcess(args,0,json.dumps(self.status) if args[1:]==['status','--json'] else '','')

@pytest.fixture
def cli(monkeypatch,tmp_path):
    env=tmp_path/'.env';env.write_bytes(ENV);probes=[]
    monkeypatch.setattr(ts,'have',lambda cmd:True)
    monkeypatch.setattr(ts,'running_instance',lambda host,port,timeout=1.0:probes.append((host,port)) or None)
    def go(fake,*argv):
        monkeypatch.setattr(subprocess,'run',fake)
        return ts.main(['--port','18765',*argv],env_path=env)
    return env,go,probes

def test_public_url_uses_the_canonical_dns_name():
    assert ts.public_url_from_status({'BackendState':'Running','Self':{'DNSName':'Atul.tail34d209.ts.net.'}})=='https://atul.tail34d209.ts.net'
    assert ts.public_url_from_status({'BackendState':'Running','Self':{'HostName':'atul-pc'}})==''
    assert ts.public_url_from_status({})==''

def test_funnel_confirmation():
    assert ts.funnel_confirmed(FUNNEL_ON,HOST) and ts.funnel_confirmed(FUNNEL_ON.upper(),HOST)
    assert ts.funnel_confirmed(FUNNEL_ON,HOST.upper())
    for output in ['No serve config\n','',None,TAILNET_ONLY,FUNNEL_ON.replace(HOST,'other-pc.tail34d209.ts.net')]:assert not ts.funnel_confirmed(output,HOST)
    assert not ts.funnel_confirmed(FUNNEL_ON,'')

def test_next_steps_put_the_paytm_bridge_first():
    text=ts.next_steps('https://'+HOST,8765,False)
    for part in ['/api/bridge/paytm','Bearer','Start.bat','/admin/paytm','UPI ID','test tip']:assert part in text
    assert text.index('Start.bat')<text.index('UPI ID')<text.index('/admin/paytm')<text.index('/api/bridge/paytm')<text.index('/api/bridge/credit')
    assert 'OLD address' not in text
    running=ts.next_steps('https://'+HOST,8765,True)
    assert 'AcePressure is running with the OLD address right now. Do step 1 now.' in running
    assert running.index('OLD address')<running.index('1. Restart AcePressure')
    assert 'Start_Demo.bat' in ts.next_steps('https://'+HOST,8766,False)

@pytest.mark.parametrize('output,code',[(TAILNET_ONLY,0),('No serve config\n',0),(FUNNEL_ON,1)],ids=['tailnet-only','no-serve-config','status-failed'])
def test_unconfirmed_funnel_leaves_env_untouched(cli,capsys,output,code):
    env,go,_=cli
    with pytest.raises(SystemExit) as e:go(FakeTailscale(output,code))
    assert e.value.code==2 and env.read_bytes()==ENV
    assert f'Tailscale did not confirm that Funnel is on for {HOST}. If a login.tailscale.com link appeared above' in capsys.readouterr().out
    assert not (env.parent/'configuration-backups').exists()

def test_missing_dns_name_leaves_env_untouched(cli):
    env,go,_=cli
    with pytest.raises(SystemExit) as e:go(FakeTailscale(FUNNEL_ON,status={'BackendState':'Running','Self':{'HostName':'Atul-PC'}}))
    assert e.value.code==2 and env.read_bytes()==ENV

def test_confirmed_funnel_writes_env_and_prints_next_steps(cli,capsys):
    env,go,probes=cli;fake=FakeTailscale(FUNNEL_ON)
    assert go(fake) is None
    assert env.read_text(encoding='utf-8')=='APP_SECRET=keep-me\nPUBLIC_BASE_URL=https://atul.tail34d209.ts.net\nCOOKIE_SECURE=true\n'
    backups=list((env.parent/'configuration-backups').glob('*/.env'))
    assert len(backups)==1 and backups[0].read_text(encoding='utf-8')==ENV.decode()  # text: Windows writes CRLF
    out=capsys.readouterr().out
    assert 'login.tailscale.com' in out and out.index('/api/bridge/paytm')<out.index('/api/bridge/credit') and 'OLD address' not in out
    assert probes==[('127.0.0.1',18765)]
    assert [kw for args,kw in fake.calls if args[1:3]==['funnel','--bg']]==[{'check':False}]  # streamed to the console, not captured
    assert not any(args[1:2]==['up'] for args,kw in fake.calls)

def test_running_server_is_told_to_restart(cli,monkeypatch,capsys):
    env,go,_=cli
    monkeypatch.setattr(ts,'running_instance',lambda host,port,timeout=1.0:'acepressure')
    go(FakeTailscale(FUNNEL_ON))
    out=capsys.readouterr().out
    assert out.index('AcePressure is running with the OLD address right now. Do step 1 now.')<out.index('1. Restart AcePressure')

def test_login_check_uses_backend_state(cli):
    env,go,_=cli;fake=FakeTailscale(FUNNEL_ON,status=STATUS|{'BackendState':'NeedsLogin'})
    go(fake)
    assert (['tailscale','up'],{'check':True}) in fake.calls
