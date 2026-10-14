"""Can viewers tip right now? One checklist for the dashboard, the Paytm page, the Start window and the tip page."""
import os
from pathlib import Path
from dotenv import dotenv_values
from .domain import now

def disk_env(config):
    """The .env on disk, or None when there is none or it can't be read. Setup_Tailscale_URL.bat edits it while AcePressure runs."""
    try:
        path=config.get('ENV_FILE')
        return dotenv_values(path) if path and Path(path).is_file() else None
    except Exception: return None

def readiness(store,db,config,settings=None):
    """Checks in fix order, each {key, ok, title, fix, link}, plus tip_page: 'open', 'setup', 'paused' or 'demo'.
    Never raises and never returns a secret: no token or recipient hashes and no .env value except the public address."""
    demo=bool(config.get('DEMO_MODE')); base=str(config.get('PUBLIC_BASE_URL',''))
    try:
        s=settings if settings is not None else store.settings(db)
        b=db.execute('SELECT * FROM paytm_bridge WHERE id=1').fetchone()
        paytm=dict(enabled=bool(b['enabled']),auto_match=bool(b['auto_match']),has_token=bool(b['token_hash']),has_recipient=bool(b['recipient_hash']),last_seen=b['last_seen'])
        review,oldest=db.execute("SELECT COUNT(*),MIN(received) FROM paytm_inbox WHERE status='REVIEW' AND received>=?",(now()-86400,)).fetchone()
        checks=[]; check=lambda key,ok,title,fix,link:checks.append(dict(key=key,ok=bool(ok),title=title,fix=fix,link=link))
        if not demo:
            env=disk_env(config)
            if env is not None:  # advisory: PUBLIC_BASE_URL and COOKIE_SECURE are read only at startup
                url=(env.get('PUBLIC_BASE_URL') or '').rstrip('/'); secure=(env.get('COOKIE_SECURE') or 'false').lower()=='true'
                check('restart',(not url or url==base) and secure==bool(config.get('SESSION_COOKIE_SECURE')),'Restarted after setup',f'Restart needed: .env has {url} but this server is still using {base}. Close the AcePressure window and run Start.bat again.' if url and url!=base else 'Restart needed: .env changed after AcePressure started. Close the AcePressure window and run Start.bat again.','restart')
            check('upi',s['upi_id'] and s['payee_name'],'UPI ID and payee name','Add your UPI ID and payee name in Settings → Creator & payments.','settings')
            check('https',base.startswith('https://'),'Public HTTPS address','Run Setup_Tailscale_URL.bat, then close this AcePressure window and run Start.bat again.','restart')
            check('verification',paytm['enabled'] or s['bridge_enabled'],'Payment verification','Open Paytm bridge → Generate token, then paste it into your phone automation.' if not paytm['has_token'] else 'Open Paytm bridge, enter your bank marker exactly as Paytm shows it (e.g. HDFC Bank - 1234), then click Enable bridge.' if not paytm['has_recipient'] else 'Open Paytm bridge and click Enable bridge. (Generating a new token switches the bridge off.)','/admin/paytm')
        check('accepting',s['accepting_tips'],'New tip requests','New tips are paused (Settings → Accept new tip requests).','resume')
        ok={c['key'] for c in checks if c['ok']}
        page='paused' if not s['accepting_tips'] else 'demo' if demo else 'open' if {'upi','https','verification'}<=ok else 'setup'
        return dict(checks=checks,tip_page=page,tip_url=base+'/',paytm=paytm,sms_bridge=bool(s['bridge_enabled']),review_count=review,oldest_review_at=oldest)
    except Exception:
        return dict(checks=[],tip_page='demo' if demo else 'setup',tip_url=base+'/',paytm=dict(enabled=False,auto_match=False,has_token=False,has_recipient=False,last_seen=None),sms_bridge=False,review_count=0,oldest_review_at=None)

def startup_summary(app):
    """What the Start window prints, in plain ASCII: where the dashboard is and whether viewers can pay."""
    with app.store.db() as db: h=readiness(app.store,db,app.config)
    first=next((c for c in h['checks'] if not c['ok'] and c['key']!='restart'),None)  # the restart check is advisory, never the reason
    pay={'open':'Payments: READY','demo':'DEMO MODE - no real money.'}.get(h['tip_page']) or 'Payments: PAUSED'+(' - '+first['title']+': '+first['fix'] if first else '')
    text=f"AcePressure is running.\n  Dashboard on this PC: http://localhost:{os.getenv('PORT','8765')}/admin\n  Tip page: {h['tip_url']}\n  {pay}\nKeep this window open while you stream. Closing it stops AcePressure."
    return text.replace('→','->').replace('—','-').encode('ascii','replace').decode('ascii')
