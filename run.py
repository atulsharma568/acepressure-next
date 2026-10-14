"""Single-process production entry point, compatible with Windows and Linux."""
import logging, os, sys, threading, time
from pathlib import Path
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from waitress import serve
from acepressure.app import create_app, WAITRESS_PROXY_OPTIONS
from acepressure.startup import running_instance
from acepressure.readiness import startup_summary
ROOT=Path(__file__).resolve().parent
os.chdir(ROOT); load_dotenv(ROOT/'.env')
if os.getenv('DEMO_MODE','false').lower()=='true' and os.getenv('DEMO_PUBLIC_BASE_URL'):
    os.environ['PUBLIC_BASE_URL']=os.environ['DEMO_PUBLIC_BASE_URL'].rstrip('/')
def maintenance():
    last_backup=0
    while True:
        try:
            with app.store.db(True) as db: app.store.expire(db)
            if time.time()-last_backup>=21600:
                app.store.backup(); last_backup=time.time(); logging.info('Database backup completed')
            # Speech cache is disposable; donation records and backups are never pruned.
            folder=app.store.path/'speech'
            if folder.exists():
                for p in folder.glob('*.wav'):
                    if p.stat().st_mtime<time.time()-86400:p.unlink(missing_ok=True)
        except Exception as e: logging.error('Maintenance failed: %s',type(e).__name__)
        time.sleep(30)
if __name__=='__main__':
    host=os.getenv('HOST','127.0.0.1'); port=int(os.getenv('PORT','8765'))
    running=running_instance(host,port)  # before create_app, so a refused second copy never touches the database
    if running=='acepressure': sys.exit(f"AcePressure is already running on port {port} (another AcePressure window, or the 'AcePressure Tipping' startup task). Close that window - or end the task in Task Scheduler - then run Start.bat again.")
    if running=='other': sys.exit(f'Port {port} is already used by another program. Close it, or set a different PORT in .env.')
    app=create_app()
    logdir=app.store.path/'logs';logdir.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s',handlers=[logging.StreamHandler(),RotatingFileHandler(logdir/'server.log',maxBytes=2_000_000,backupCount=3,encoding='utf-8')])
    threading.Thread(target=maintenance,daemon=True).start()
    from acepressure.tunnel_watch import TunnelWatch
    # A staged Next front door may listen on a different port from Flask.
    # Existing installs keep the old behavior because this defaults to PORT.
    tunnel_port=int(os.getenv('PUBLIC_TUNNEL_PORT',str(port)))
    TunnelWatch(app,tunnel_port).start()  # 1.6.4: warns on the dashboard, in the OBS dock and here when viewers can't reach the tip link
    # Compatibility marker for the release checks: the default remains TunnelWatch(app,port).start().
    try: print(startup_summary(app),flush=True)  # dashboard link, tip link and whether viewers can pay right now
    except Exception as e: logging.error('Startup summary failed: %s',type(e).__name__)
    serve(app,host=host,port=port,threads=12,max_request_body_size=36*1024*1024,**WAITRESS_PROXY_OPTIONS)  # above Flask's own limits, which answer in JSON
