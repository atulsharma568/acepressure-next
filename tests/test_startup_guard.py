"""A second AcePressure must refuse to start instead of sharing the port (Waitress binds with SO_REUSEADDR on Windows)."""
import os, socket, subprocess, sys, threading, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import pytest
from acepressure.startup import running_instance
ROOT=Path(__file__).resolve().parents[1]

def free_port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]

@pytest.fixture
def stub():
    """Start a tiny local HTTP server that answers every GET with the given body; returns its port."""
    servers=[]
    def start(body,kind='text/plain'):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);servers.append(server)
        threading.Thread(target=server.serve_forever,kwargs={'poll_interval':0.05},daemon=True).start()
        return server.server_address[1]
    yield start
    for server in servers:server.shutdown();server.server_close()

def test_free_port_means_nothing_is_running():
    assert running_instance('127.0.0.1',free_port()) is None

def test_acepressure_health_is_recognised(stub):
    port=stub(b'{"ok":true,"demo":false}','application/json')
    for host in ['127.0.0.1','0.0.0.0','','localhost']:assert running_instance(host,port)=='acepressure',host

def test_any_other_answer_is_another_program(stub):
    assert running_instance('127.0.0.1',stub(b'hello'))=='other'
    assert running_instance('127.0.0.1',stub(b'{"ok":false}','application/json'))=='other'
    assert running_instance('127.0.0.1',stub(b'[true]','application/json'))=='other'

def test_system_proxy_is_never_asked(stub,monkeypatch):
    for key in ['no_proxy','NO_PROXY']:monkeypatch.delenv(key,raising=False)
    monkeypatch.setenv('http_proxy','http://127.0.0.1:'+str(free_port()))
    monkeypatch.setattr(urllib.request,'_opener',None)  # urlopen() caches the proxies it saw first
    assert running_instance('127.0.0.1',stub(b'{"ok":true}','application/json'))=='acepressure'

def test_never_raises():
    assert running_instance(12345,free_port()) is None
    assert running_instance('127.0.0.1',object()) is None

@pytest.mark.parametrize('body,message',[(b'{"ok":true}',"AcePressure is already running on port {port} (another AcePressure window, or the 'AcePressure Tipping' startup task). Close that window - or end the task in Task Scheduler - then run Start.bat again."),
                                         (b'hello','Port {port} is already used by another program. Close it, or set a different PORT in .env.')],ids=['acepressure','other'])
def test_run_py_refuses_before_creating_the_app(stub,tmp_path,body,message):
    port=stub(body);data=tmp_path/'data'
    env=os.environ|{'HOST':'127.0.0.1','PORT':str(port),'DATA_DIR':str(data),'APP_SECRET':'s'*48,'BRIDGE_TOKEN':'b'*48,'OVERLAY_TOKEN':'o'*48,'ADMIN_PASSWORD_HASH':'unused','DEMO_MODE':'true','PYTHONUTF8':'1'}
    r=subprocess.run([sys.executable,str(ROOT/'run.py')],env=env,capture_output=True,text=True,timeout=60)
    expected=message.format(port=port)
    assert r.returncode==1 and expected in r.stdout+r.stderr, r.stdout+r.stderr
    assert expected.isascii()
    assert not data.exists()  # create_app (which creates DATA_DIR) never ran
