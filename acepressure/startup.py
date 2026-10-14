"""Single-instance guard. Waitress binds with SO_REUSEADDR, so on Windows a second server could share the port instead of failing."""
import json,socket,urllib.request

def running_instance(host,port,timeout=1.0):
    """None when nothing answers on the port, 'acepressure' when an AcePressure /health answers, 'other' for any other program. Never raises."""
    try:
        probe='127.0.0.1' if host in ('','0.0.0.0','localhost','127.0.0.1') else '::1' if host=='::' else host
        socket.create_connection((probe,port),timeout).close()
    except Exception: return None  # refused, timed out or unexpected: nothing is in the way
    try:
        # No proxies: a Windows system proxy must never answer for this PC.
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(f"http://{'['+probe+']' if ':' in probe else probe}:{port}/health",timeout=2) as r:
            return 'acepressure' if json.loads(r.read(65536)).get('ok') is True else 'other'
    except Exception: return 'other'
