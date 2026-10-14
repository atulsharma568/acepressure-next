"""Optional Windows SAPI rendering. Viewer text is JSON stdin, never executable code."""
import hashlib,json,os,subprocess,threading
from pathlib import Path
from .domain import Problem
LOCK=threading.Lock()
def render_speech(directory,text,voice):
    if os.name!='nt': raise Problem('Windows TTS requires Windows; choose browser voices on other hosts.',503)
    folder=directory/'speech'; folder.mkdir(exist_ok=True)
    key=hashlib.sha256((voice+'\0'+text).encode()).hexdigest(); path=folder/(key+'.wav')
    with LOCK:
        if path.exists(): return path
        script=Path(__file__).resolve().parent.parent/'scripts'/'Speak.ps1'
        payload=json.dumps({'text':text,'voice':voice,'output':str(path)})
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script)],input=payload,encoding='utf-8',capture_output=True,timeout=40)
        if result.returncode or not path.exists():
            path.unlink(missing_ok=True)
            raise Problem('Windows voice unavailable. Check installed SAPI voices in the TTS guide.',503)
    return path
