import csv, hashlib, hmac, io, ipaddress, json, os, re, secrets, threading, time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode, urlparse
import mimetypes
import qrcode
from flask import Flask, request, jsonify, session, send_file, render_template, abort
from werkzeug.security import check_password_hash
from werkzeug.exceptions import HTTPException
from .domain import Store, Problem, clean, now, uid, rows, money, PERIODS, DEFAULTS, STORED_SOUND, SOUND_ID, SOUND_MAX_MS, BUILTIN_SOUNDS, known_uploads, display_label, volume_percent, IST
from .text_filters import normalize_pronunciations
from .parsers import parse_receipt
from .readiness import readiness
from .video import validate_or_fix_audio, sanitize_original_name, sound_labels
ROOT=Path(__file__).resolve().parent.parent

# v1.5.8 — server-side gender heuristic for voice IDs. Mirrors the client-side regex in public.js
# so public_config can backfill voice_genders for admins who upgraded from <1.5.4 without re-saving.
# Pattern: name preceded by non-letter (or start) and NOT followed by a lowercase letter.
# This matches 'Ava' in 'en-US-AvaMultilingualNeural' (CamelCase boundary) but NOT in 'Avanti'.
# Case-sensitive so 'ava' in a random lowercase string doesn't false-match 'Ava'.
_VOICE_MALE_RE = re.compile(r'(?:^|[^A-Za-z])(Andrew|Brian|William|Guy|Davis|Jason|Tony|Christopher|Eric|Jacob|Ethan|Roger|Steffan|Drew|Madhur|Prabhat|Florian|Remy|Giuseppe|Hyunsu|Mark|David|Thomas|Liam|Henri|Diego|Ryan|Noah|Kai|Lucas|Alonso|Rehaan|Arnav|Ravi|Niwat|Bashkar|Ibrahim|Hamed|Mohan|Male)(?![a-z])')
_VOICE_FEMALE_RE = re.compile(r'(?:^|[^A-Za-z])(Ava|Emma|Jenny|Aria|Sara|Nancy|Michelle|Monica|Zira|Hazel|Catherine|Claire|Elvira|Swara|Neerja|Seraphina|Vivienne|Thalita|Natasha|Clara|Fiona|Freya|Isabella|Luna|Nova|Sofia|Ananya|Kavya|Pooja|Priya|Anju|Lekha|Shruti|Pallavi|Heera|Aditi|Kalpana|Female)(?![a-z])')

def _guess_gender_from_voice_id(voice_id):
    if not isinstance(voice_id, str): return 'Any'
    if _VOICE_MALE_RE.search(voice_id): return 'Male'
    if _VOICE_FEMALE_RE.search(voice_id): return 'Female'
    return 'Any'



for _ext,_type in {'.js':'text/javascript','.mjs':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.json':'application/json','.png':'image/png','.webp':'image/webp','.gif':'image/gif','.mp3':'audio/mpeg','.ogg':'audio/ogg','.wav':'audio/wav','.webm':'video/webm','.mp4':'video/mp4','.woff2':'font/woff2'}.items():
    mimetypes.add_type(_type,_ext)  # Windows registry entries (e.g. .js -> text/plain) would otherwise win, and nosniff then blocks the file

_STORED_SOUND=STORED_SOUND; _known_uploads=known_uploads
TEST_MESSAGE='This is a test alert. No money received.'
# 1.6.4: while "Read whole messages" is off, Test alert sends a long message, so the cut can be heard in OBS.
TEST_LONG_MESSAGE=('This is a test alert. No money received. Bhai kya clutch tha, aaj ka stream bahut mast tha! '
                   'Main roz stream dekhta hoon, keep it up and see you in the next match.')

# Tailscale Funnel, cloudflared and ngrok connect from 127.0.0.1 and pass the visitor's address in X-Forwarded-For.
# Only that hop is trusted, so each visitor gets their own rate limits; X-Forwarded-Host/Proto are still cleared.
WAITRESS_PROXY_OPTIONS=dict(trusted_proxy='127.0.0.1',trusted_proxy_count=1,trusted_proxy_headers={'x-forwarded-for'},clear_untrusted_proxy_headers=True)

class OverlayClients:
    """Alert overlays seen in the last 15 s, in memory only: (channel, owner) -> {client, seen, standby}. Owner ids never leave it."""
    def __init__(self,clock=time.monotonic): self.clock=clock; self.lock=threading.Lock(); self.seen={}
    def _prune(self):
        # An overlay doesn't poll while it plays an alert, so it stays listed until its 180 s lease ends or it polls again.
        t=self.clock(); self.seen={k:v for k,v in self.seen.items() if t-v['seen']<=15 or t<v.get('busy',t)}; return t
    def record(self,channel,owner,client):
        """Notes a claim or ack. True means standby: a browser tab while an OBS page polled this channel in the last 5 s or is playing its alert."""
        with self.lock:
            t=self._prune(); standby=client=='browser' and any(c==channel and o!=owner and v['client']=='obs' and (t-v['seen']<=5 or t<v.get('busy',t)) for (c,o),v in self.seen.items())
            self.seen[(channel,owner)]=dict(client=client,seen=t,standby=standby); return standby
    def playing(self,channel,owner):
        with self.lock:
            t=self._prune()
            if (channel,owner) in self.seen: self.seen[(channel,owner)]['busy']=t+180
    def summary(self):
        with self.lock:
            t=self._prune(); out={'horizontal':[],'vertical':[]}
            for (channel,_),v in self.seen.items(): out[channel].append(dict(client=v['client'],age=round(t-v['seen'],1),standby=v['standby']))
            return out

def create_app(config=None):
    app=Flask(__name__)
    try: asset_v=(ROOT/'VERSION').read_text(encoding='utf-8').strip()
    except (OSError,ValueError): asset_v=''
    app.jinja_env.globals['asset_v']=asset_v or 'dev'  # ?v= makes OBS load the new overlay scripts after an upgrade
    app.config.update(SECRET_KEY=os.getenv('APP_SECRET',''),DATA_DIR=os.getenv('DATA_DIR','data'),ADMIN_PASSWORD_HASH=os.getenv('ADMIN_PASSWORD_HASH',''),BRIDGE_TOKEN=os.getenv('BRIDGE_TOKEN',''),OVERLAY_TOKEN=os.getenv('OVERLAY_TOKEN',''),DEMO_MODE=os.getenv('DEMO_MODE','false').lower()=='true',PUBLIC_BASE_URL=os.getenv('PUBLIC_BASE_URL','http://localhost:8765').rstrip('/'),TRUST_CLOUDFLARE=os.getenv('TRUST_CLOUDFLARE','false').lower()=='true',ENV_FILE=str(ROOT/'.env'),SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE','false').lower()=='true',PERMANENT_SESSION_LIFETIME=timedelta(hours=12),MAX_CONTENT_LENGTH=26*1024*1024,TESTING=False)
    if config: app.config.update(config)
    for key in ['SECRET_KEY','BRIDGE_TOKEN','OVERLAY_TOKEN']:
        if len(app.config[key])<32: raise RuntimeError(f'{key} must be generated by setup.py (at least 32 characters).')
    if not app.config['ADMIN_PASSWORD_HASH']: raise RuntimeError('Run setup.py to set an administrator password.')
    app.config['SESSION_COOKIE_NAME']='ace_demo_session' if app.config['DEMO_MODE'] else 'ace_session'
    store=Store(app.config['DATA_DIR'],os.getenv('IDENTITY_SECRET') or app.config['SECRET_KEY']); app.store=store
    clients=app.extensions['ace_overlay_clients']=OverlayClients()
    from .paytm_capture import register_capture
    def admin():
        if not session.get('admin'): raise Problem('Please sign in.',401)
        if request.method not in ['GET','HEAD','OPTIONS']:
            if not hmac.compare_digest(request.headers.get('X-CSRF-Token',''),session.get('csrf','--')): raise Problem('Invalid CSRF token. Reload the dashboard.',403)
    def overlay():
        token=request.headers.get('X-Overlay-Token') or request.args.get('key','')
        if not hmac.compare_digest(token,app.config['OVERLAY_TOKEN']): raise Problem('Overlay key rejected.',401)
    def data():
        d=request.get_json(silent=True)
        if not isinstance(d,dict): raise Problem('Expected a JSON object.')
        return d
    def client_ip():
        if app.config['TRUST_CLOUDFLARE'] and request.remote_addr in ['127.0.0.1','::1']: return request.headers.get('CF-Connecting-IP',request.remote_addr)
        return request.remote_addr or 'unknown'
    def client_kind(d):  # overlay scripts from before 1.6.0 send no client field
        return d['client'] if d.get('client') in ['obs','browser','forced'] else 'obs' if 'OBS/' in request.headers.get('User-Agent','') else 'unknown'
    register_capture(app,store,admin)
    from .visuals import register_visuals
    register_visuals(app,store,admin)
    from .tts_service import register_tts
    register_tts(app,store)
    from .paytm_bridge import register_bridge
    register_bridge(app,store,admin,client_ip)
    tunnel=threading.Lock()  # taken once, by the first request that arrives through a tunnel, and never released
    @app.before_request
    def guard():
        if request.headers.get('X-Forwarded-For') and tunnel.acquire(False): app.logger.info('Visitor addresses come from the tunnel (X-Forwarded-For): per-visitor rate limits are active.')
        if request.path.startswith('/api/admin/'): admin()
        if request.path.startswith('/api/overlay/'): overlay()
        if request.path.startswith('/api/') and request.method not in ['GET','HEAD']:
            origin=request.headers.get('Origin')
            allowed={app.config['PUBLIC_BASE_URL'],request.host_url.rstrip('/')}
            if origin and origin not in allowed: raise Problem('Cross-origin request rejected.',403)
        if request.path.startswith('/api/public/') and request.method=='POST':
            if request.path=='/api/public/forget-browser': store.rate('forget:'+client_ip(),10,600)
            else: store.rate('public:'+client_ip(),15,600); store.rate('public-global',200,600)
    @app.after_request
    def headers(res):
        res.headers['X-Content-Type-Options']='nosniff'; res.headers['Referrer-Policy']='no-referrer'
        res.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'; form-action 'self'"
        if request.path.startswith('/api/') or request.path.startswith('/admin'): res.headers['Cache-Control']='no-store'
        return res
    @app.errorhandler(Problem)
    def problem(e): return jsonify(error=e.message),e.status
    @app.errorhandler(HTTPException)
    def http_error(e):
        if e.code==413: return jsonify(error='That file is too large. Sounds and images can be up to 8 MB, videos up to 24 MB.'),413
        return jsonify(error=e.name),e.code
    @app.errorhandler(ValueError)
    @app.errorhandler(TypeError)
    def bad_value(e): return jsonify(error='Invalid value or field type.'),400
    @app.errorhandler(Exception)
    def unexpected(e):
        # Do not log request bodies, bank messages, tokens or private supporter data.
        app.logger.error('Unhandled error type=%s path=%s',type(e).__name__,request.path)
        if app.config['TESTING']: raise e
        return jsonify(error='Unexpected server error. Check local service health.'),500
    @app.get('/')
    @app.get('/tip/acepressure')
    def public_page(): return render_template('public.html')
    @app.get('/admin')
    @app.get('/obs/activity')
    def admin_page(): return render_template('admin.html',dock=request.path.startswith('/obs/'))
    @app.get('/overlay/<kind>')
    def overlay_page(kind):
        if kind not in ['alert','goal','top3','recent']: abort(404)
        return render_template('overlay.html',kind=kind)
    @app.get('/health')
    def health():
        with store.db() as db: db.execute('SELECT 1').fetchone()
        return {'ok':True,'demo':app.config['DEMO_MODE']}
    @app.get('/api/public/config')
    def public_config():
        with store.db() as db: s=store.settings(db); d=store.resolve_default(db,s)
        keys=['creator','welcome','minimum','maximum','voices','sounds','allow_sound_choice','tts_minimum','tts_limit','avatar','accepting_tips','tiers','tts_read_full','tts_short_limit','tts_full_from']
        # v1.5.8 — auto-backfill voice_genders from current engine if legacy settings missing it.
        # Users who upgraded from <1.5.4 may not have voice_genders yet; this derives it on-the-fly
        # (name-token heuristics only — never calls out to Edge/Azure network catalog here).
        vg = dict(s.get('voice_genders', {}) or {})
        missing = [v for v in s.get('voices', []) if v not in vg or vg[v] not in ('Male', 'Female')]
        if missing:
            for v in missing:
                vg[v] = _guess_gender_from_voice_id(v)
        with store.db() as db:  # live checkout also needs the HTTPS address (new_tip answers 503 without it)
            ready=app.config['DEMO_MODE'] or (store.payment_ready(s,db) and app.config['PUBLIC_BASE_URL'].startswith('https://')); page=readiness(store,db,app.config,s)['tip_page']
            default_volume=store.default_volume(db,s)
        # Since 1.6.0 viewers pick from /api/public/soundboard; `sounds` is only the default, so a 1.5.9 tip page left open hides its chips.
        return {k:s[k] for k in keys}|{'sounds':[d['sound']],'allow_sound_choice':False,'demo':app.config['DEMO_MODE'],'ready':ready,'availability':page,'voice_labels':s.get('voice_labels',{}),'voice_genders':vg,'sound_labels':{d['sound']:d['name']} if d['kind']=='item' and not d['problem'] else {},'tts_engine':s['tts_engine'],'tts_enabled':s['tts_enabled'],
                                         'tts_volume':volume_percent(s.get('tts_volume')),'default_volume':default_volume}
    def payment(tip):
        s=store.settings(); demo=app.config['DEMO_MODE']
        uri=None if demo else 'upi://pay?'+urlencode(dict(pa=s['upi_id'],pn=s['payee_name'],am=f"{tip['requested_paise']/100:.2f}",cu='INR',tn='AcePressure '+tip['id'],tr=tip['id']))
        with store.db() as db:
            review,queued=db.execute("SELECT EXISTS(SELECT 1 FROM paytm_inbox WHERE tip_id=? AND status='REVIEW'),EXISTS(SELECT 1 FROM alerts WHERE tip_id=?)",(tip['id'],)*2).fetchone()
        return {k:tip[k] for k in ['id','token','name','display_paise','requested_paise','status','expires']}|{'upi_uri':uri,'demo':demo,'upi_id':s['upi_id'] if not demo else '', 'payee_name':s['payee_name'] if not demo else '', 'needs_review':bool(review),'alert_queued':bool(queued)}
    @app.post('/api/public/tips')
    def new_tip():
        if not app.config['DEMO_MODE'] and not app.config['PUBLIC_BASE_URL'].startswith('https://'):
            raise Problem('Public HTTPS checkout is not configured.',503)
        d=data(); remember=d.get('remember',False)
        if not isinstance(remember,bool): raise Problem('Invalid remember choice.')
        cookie='ace_demo_supporter' if app.config['DEMO_MODE'] else 'ace_supporter'
        token=request.cookies.get(cookie,'')
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}',token): token=secrets.token_urlsafe(32)
        response=jsonify(payment(store.create_tip(d,app.config['DEMO_MODE'],token if remember else None)))
        if remember: response.set_cookie(cookie,token,max_age=31536000,httponly=True,secure=app.config['SESSION_COOKIE_SECURE'],samesite='Lax')
        else: response.delete_cookie(cookie)
        return response,201
    @app.post('/api/public/forget-browser')
    def forget_browser():
        cookie='ace_demo_supporter' if app.config['DEMO_MODE'] else 'ace_supporter'
        token=request.cookies.get(cookie,'')
        hashed=hmac.new(store.secret.encode(),('browser:'+token).encode(),hashlib.sha256).hexdigest()
        with store.db(True) as db: db.execute('DELETE FROM browser_supporters WHERE token_hash=?',(hashed,))
        response=jsonify(ok=True); response.delete_cookie(cookie); return response
    def find_public(tid):
        token=request.headers.get('X-Tip-Token') or request.args.get('token','')
        with store.db(True) as db:
            store.expire(db)
            r=db.execute('SELECT * FROM tips WHERE id=? AND token=?',(tid,token)).fetchone()
        if not r: raise Problem('Tip not found.',404)
        return dict(r)
    @app.get('/api/public/tips/<tid>')
    def status(tid): return payment(find_public(tid))
    @app.get('/api/public/tips/<tid>/qr')
    def qr(tid):
        t=find_public(tid); uri=payment(t)['upi_uri']
        if not uri or t['status']!='PENDING': raise Problem('No active payment QR.',409)
        out=io.BytesIO(); qrcode.make(uri).save(out,format='PNG'); out.seek(0)
        return send_file(out,mimetype='image/png',max_age=0)
    @app.get('/api/public/top')
    def public_top():
        with store.db() as db: board=store.summary(db,'lifetime')['leaderboard'][:3]; blocked=store.blocked_ids(db); s=store.settings(db)
        return {'supporters':[{'name':store.board_name(p['name'],p['id'],blocked,s),'total':p['total'],'count':p['count']} for p in board]}
    @app.post('/api/bridge/credit')
    def credit():
        token=request.headers.get('Authorization','').removeprefix('Bearer ')
        # Token first: junk posts get their own per-address bucket and can never use up the phone's.
        if not hmac.compare_digest(token,app.config['BRIDGE_TOKEN']): store.rate('bridge-bad:'+client_ip(),30,60); raise Problem('Unauthorized bridge.',401)
        store.rate('bridge-global',120,60)
        d=data()
        if len(json.dumps(d))>4096: raise Problem('Receipt too large.',413)
        receipt=parse_receipt(d,store.settings(),app.config['DEMO_MODE'])
        return store.verify(receipt,'demo' if app.config['DEMO_MODE'] else 'iphone-sms')
    @app.post('/api/login')
    def login():
        ip=client_ip(); store.rate('login:'+ip,8,900)
        try: public=ipaddress.ip_address(ip).is_global
        except ValueError: public=False
        if public: store.rate('login-public',40,900)  # sign-ins from this PC, the LAN or the tailnet (100.64/10) never touch it
        d=data()
        if not check_password_hash(app.config['ADMIN_PASSWORD_HASH'],str(d.get('password',''))): raise Problem('Incorrect password.',401)
        session.clear(); session['admin']=True; session['csrf']=secrets.token_urlsafe(32); session.permanent=True
        return {'csrf':session['csrf']}
    @app.get('/api/admin/state')
    def state():
        from .tts_service import voice_report
        with store.db(True) as db:
            store.expire(db); s=store.settings(db); active=store.active(db)
            # alert_state: the newest horizontal delivery for each tip; a queued alert past its 5 minutes can no longer play.
            recent=rows(db.execute("SELECT id,name,display_paise,message,status,verified,alert_shown,tts_played,tts,supporter_id,session_id,(SELECT CASE WHEN d.state='queued' AND a.expires<? THEN 'expired' ELSE d.state END FROM alerts a JOIN deliveries d ON d.alert_id=a.id WHERE a.tip_id=tips.id AND d.channel='horizontal' ORDER BY a.id DESC LIMIT 1) AS alert_state FROM tips WHERE status IN ('VERIFIED','MANUAL') ORDER BY verified DESC LIMIT 20",(now(),)))
            for t in recent:  # 1.6.4: cut means the voice reads only part of it now ("Replay in full"); voice_missed: shown on stream, voice never finished
                try:
                    shown=store.on_stream(t['message'],s); said=store.speech(shown,s,t['display_paise'])
                    t['cut']=bool(said) and said!=store.speech(shown,s,full=True)
                    t['voice_missed']=t['alert_state']=='done' and bool(t['tts']) and not t['tts_played'] and bool(said) and t['display_paise']>=money(s['tts_minimum'])
                except Exception: t['cut']=t['voice_missed']=False
            voice=voice_report(app,db,active['started'] if active else now()-10800)
            tunnel=app.extensions.get('ace_tunnel')
            return dict(csrf=session['csrf'],settings=s,active_session=active,goals=store.goal_values(db),demo=app.config['DEMO_MODE'],stats={p:store.summary(db,p) for p in PERIODS if p!='custom'},health=readiness(store,db,app.config,s),overlays=clients.summary(),recent=recent,voice=voice,
                        tunnel=tunnel if isinstance(tunnel,dict) and now()-tunnel.get('checked',0)<=300 else None,now=now())
    @app.post('/api/admin/logout')
    def logout(): session.clear(); return {'ok':True}
    @app.get('/api/admin/transactions')
    def transactions():
        with store.db(True) as db:
            store.expire(db); sql='SELECT t.*,s.email FROM tips t JOIN supporters s ON t.supporter_id=s.id WHERE 1=1'; args=[]
            if request.args.get('status'): sql+=' AND t.status=?'; args.append(request.args['status'])
            if request.args.get('q'): sql+=' AND (t.name LIKE ? OR t.id LIKE ? OR t.reference LIKE ?)'; args += ['%'+request.args['q']+'%']*3
            if request.args.get('supporter'): sql+=' AND supporter_id=?'; args.append(request.args['supporter'])
            if request.args.get('start'): sql+=' AND coalesce(verified,created)>=?'; args.append(int(request.args['start']))
            if request.args.get('end'): sql+=' AND coalesce(verified,created)<?'; args.append(int(request.args['end']))
            out=rows(db.execute(sql+' ORDER BY created DESC',args))
        for t in out: t.pop('token',None)
        if request.args.get('export')=='csv':
            sio=io.StringIO(); fields=list(out[0]) if out else ['id','name','display_paise','actual_paise','status']
            writer=csv.DictWriter(sio,fieldnames=fields); writer.writeheader()
            for t in out:
                writer.writerow({k:("'"+str(v) if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@','\t','\r')) else v) for k,v in t.items()})
            return send_file(io.BytesIO(('\ufeff'+sio.getvalue()).encode()),mimetype='text/csv',download_name='AcePressure-transactions.csv',as_attachment=True)
        return {'transactions':out[:2000],'total':len(out)}
    @app.post('/api/admin/transactions/<tid>')
    def correct(tid):
        d=data(); reason=clean(d.get('reason'),300)
        if len(reason)<5: raise Problem('An audit reason of at least 5 characters is required.')
        with store.db(True) as db:
            r=db.execute('SELECT * FROM tips WHERE id=?',(tid,)).fetchone()
            if not r: abort(404)
            before=dict(r); status=d.get('status',r['status'])
            if status not in ['EXPIRED','REFUNDED','MANUAL','REJECTED']: raise Problem('Use MANUAL for a bank-checked correction, never VERIFIED.')
            if r['status']=='REFUNDED' and status!='REFUNDED': raise Problem('Refunded records cannot be reactivated.')
            actual=money(d.get('actual_amount',r['actual_paise']/100 if r['actual_paise'] is not None else r['requested_paise']/100))
            display=money(d.get('display_amount',r['display_paise']/100))
            if display<=0 or (status=='MANUAL' and actual<=0): raise Problem('Amounts must be positive.')
            reference=clean(d.get('reference',r['reference'] or ''),100).upper() or None
            if reference and not re.fullmatch(r'[A-Z0-9-]{6,100}',reference): raise Problem('Invalid bank reference.')
            if r['reference'] and reference!=r['reference']: raise Problem('An existing bank reference is immutable.')
            if reference:
                used=db.execute('SELECT id FROM tips WHERE reference=? AND id<>?',(reference,tid)).fetchone()
                receipt=db.execute('SELECT tip_id FROM receipts WHERE reference=?',(reference,)).fetchone()
                if used or (receipt and receipt['tip_id'] and receipt['tip_id']!=tid): raise Problem('Bank reference already belongs to another tip.',409)
                if status=='MANUAL':
                    db.execute('INSERT INTO receipts VALUES (?,?,?,?,?,?) ON CONFLICT(reference) DO UPDATE SET tip_id=excluded.tip_id,outcome=excluded.outcome',(reference,actual,now(),now(),'manual',tid))
            # Corrections must never enter a live alert automatically.
            db.execute('UPDATE tips SET status=?,actual_paise=?,display_paise=?,reference=?,verified=coalesce(verified,?),note=?,verification_source=? WHERE id=?',(status,actual,display,reference,now(),reason,'manual-admin',tid))
            db.execute("UPDATE deliveries SET state='cancelled' WHERE alert_id IN (SELECT id FROM alerts WHERE tip_id=?) AND state!='done'",(tid,))
            store.audit(db,'correct_transaction',tid,dict(before={k:before[k] for k in ['status','display_paise','actual_paise','reference']},after=dict(status=status,display_paise=display,actual_paise=actual,reference=reference),reason=reason))
        return {'ok':True}
    @app.get('/api/admin/supporters')
    def supporters():
        with store.db() as db:
            allsup=rows(db.execute('SELECT id,name,email,blocked,muted FROM supporters WHERE id NOT IN (SELECT source_id FROM supporter_aliases)'))
            history=store.summary(db)['leaderboard']; stats={p['id']:p for p in history}
        return {'supporters':[p|stats.get(p['id'],dict(total=0,count=0,largest=0,first=None,latest=None)) for p in allsup]}
    @app.post('/api/admin/supporters/merge')
    def merge_supporters():
        d=data();source=d.get('source');target=d.get('target');reason=clean(d.get('reason'),300)
        if not isinstance(source,str) or not isinstance(target,str) or source==target or len(reason)<5:
            raise Problem('Choose two different profiles and give a reason of at least five characters.')
        with store.db(True) as db:
            records=rows(db.execute('SELECT * FROM supporters WHERE id IN (?,?)',(source,target)))
            if len(records)!=2:raise Problem('Supporter not found.',404)
            if db.execute('SELECT 1 FROM supporter_aliases WHERE source_id IN (?,?)',(source,target)).fetchone():
                raise Problem('Profile already merged. Refresh the supporters page.',409)
            moved=[r[0] for r in db.execute('SELECT id FROM tips WHERE supporter_id=?',(source,))]
            db.execute('UPDATE tips SET supporter_id=? WHERE supporter_id=?',(target,source))
            db.execute('UPDATE supporter_aliases SET target_id=? WHERE target_id=?',(target,source))
            db.execute('INSERT INTO supporter_aliases VALUES(?,?)',(source,target))
            db.execute('UPDATE supporters SET blocked=?,muted=? WHERE id=?',(max(r['blocked'] for r in records),max(r['muted'] for r in records),target))
            store.audit(db,'merge_supporters',target,{'source':source,'target':target,'tip_ids':moved,'reason':reason})
        return {'ok':True,'moved_tips':len(moved)}
    @app.post('/api/admin/supporters/<sid>')
    def supporter_action(sid):
        d=data(); flags={k:int(bool(d[k])) for k in ['blocked','muted'] if k in d}  # only the flags sent: muting must never unblock
        with store.db(True) as db:
            if flags: db.execute('UPDATE supporters SET '+','.join(k+'=?' for k in flags)+' WHERE id=?',(*flags.values(),sid)); store.audit(db,'supporter_moderation',sid,{k:bool(v) for k,v in flags.items()})
            # 1.6.4: Block also stops their alert on screen and drops any still waiting; Mute stops their voice now.
            mine="SELECT a.id FROM alerts a JOIN tips t ON t.id=a.tip_id WHERE t.supporter_id=?"
            playing=[r[0] for r in db.execute(f"SELECT DISTINCT alert_id FROM deliveries WHERE state='playing' AND alert_id IN ({mine})",(sid,))]
            if flags.get('blocked'):
                db.execute(f"UPDATE deliveries SET state='cancelled' WHERE state='queued' AND alert_id IN ({mine})",(sid,))
                store.dismiss(db,playing)
            elif flags.get('muted') and playing:
                store._put_setting(db,'skip_version',store.settings(db)['skip_version']+1)
        return {'ok':True}
    @app.post('/api/admin/sessions')
    def sessions_action():
        d=data()
        with store.db(True) as db:
            active=store.active(db)
            if d.get('action')=='start':
                if active: raise Problem('A stream session is already active.',409)
                store.start_session(db,clean(d.get('title'),80) or 'Live stream')
            elif d.get('action')=='end':
                if active:
                    db.execute('UPDATE sessions SET ended=? WHERE id=?',(now(),active['id']))
                    db.execute("UPDATE deliveries SET state='cancelled' WHERE state IN ('queued','playing')")
                    s=store.settings(db); db.execute("UPDATE settings SET value=? WHERE key='skip_version'",(json.dumps(s['skip_version']+1),))
                    store.audit(db,'end_session',active['id'])
            else: raise Problem('Unknown session action.')
        return {'ok':True}
    @app.get('/api/admin/sessions')
    def sessions_list():
        with store.db() as db: return {'sessions':[s|{'stats':store.summary(db,session_override=s['id'])} for s in rows(db.execute('SELECT * FROM sessions ORDER BY started DESC'))]}
    @app.get('/api/admin/analytics')
    def analytics():
        period=request.args.get('period','month'); starts=request.args.get('start'); ends=request.args.get('end')
        with store.db() as db:
            ts=store.donations(db,period,starts,ends); summary=store.summary(db,period,starts,ends)
            start,end,_=store.period(period,db,starts,ends)
        from datetime import datetime
        from .domain import IST
        buckets={}; gran=request.args.get('group','day')
        key=lambda dt:(dt-timedelta(days=dt.weekday())).strftime('%Y-%m-%d') if gran=='week' else dt.strftime('%Y-%m' if gran=='month' else '%Y-%m-%d')
        if start is not None:  # quiet days/weeks/months up to today still get a (zero) bar
            day,last=datetime.fromtimestamp(start,IST),datetime.fromtimestamp(max(start,min(end or now(),now())-1),IST)
            for _ in range(400):
                if day>last: break
                buckets[key(day)]=0; day+=timedelta(days=1)
        for t in ts:
            k=key(datetime.fromtimestamp(t['verified'],IST)); buckets[k]=buckets.get(k,0)+t['display_paise']
        return {'summary':summary,'series':[{'date':k,'total':v} for k,v in sorted(buckets.items())]}
    @app.post('/api/admin/goals')
    def goal_save():
        d=data(); gid=d.get('id') or uid()
        with store.db(True) as db:
            if d.get('delete'):
                db.execute('DELETE FROM goals WHERE id=?',(gid,)); store.audit(db,'delete_goal',gid); return {'ok':True}
            period=d.get('period','week'); reset=d.get('reset','automatic')
            if period not in ['stream','today','week','month','lifetime','custom'] or reset not in ['automatic','carry']: raise Problem('Invalid goal period/reset.')
            target=money(d.get('target')); starting=money(d.get('starting',0)); title=clean(d.get('title'),70)
            if not title or target<=0: raise Problem('Goal needs a title and a positive target.')
            starts=int(d['starts']) if d.get('starts') else None; ends=int(d['ends']) if d.get('ends') else None
            if period=='custom' and (starts is None or ends is None or ends<=starts): raise Problem('Custom goals require start < end.')
            if ends and starts and ends<=starts: raise Problem('End must follow start.')
            if reset=='carry' and not starts: starts=now()
            design=d.get('design','compact'); style=d.get('style','bar')
            if design not in ['compact','large'] or style not in ['bar','segments']: raise Problem('Invalid goal design.')
            active=store.active(db)
            values=(gid,title,target,starting,period,reset,starts,ends,int(bool(d.get('enabled',True))),design,style,active['id'] if active and period=='stream' and reset=='carry' else None)
            db.execute('''INSERT INTO goals VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,target=excluded.target,starting=excluded.starting,period=excluded.period,reset=excluded.reset,starts=excluded.starts,ends=excluded.ends,enabled=excluded.enabled,design=excluded.design,style=excluded.style,session_id=excluded.session_id''',values)
            store.audit(db,'save_goal',gid,{k:d[k] for k in d if k!='delete'})
        return {'ok':True,'id':gid}
    @app.post('/api/admin/settings')
    def save_settings():
        d=data(); allowed=set(DEFAULTS)-{'skip_version','avatar'}
        if set(d)-allowed: raise Problem('Unknown setting.')
        if 'sounds' in d: raise Problem('Sound choices moved to the Sound library in 1.6.0. Reload the dashboard.',409)
        merged=store.settings()|d
        for key in ['minimum','maximum','tts_minimum']:
            money(merged[key])
        if merged['minimum']<1 or merged['maximum']<merged['minimum'] or merged['maximum']>1000000: raise Problem('Invalid amount limits.')
        if money(merged['minimum'])%100 or money(merged['maximum'])%100: raise Problem('Minimum and maximum must be whole rupees.')
        for key,lo,hi,what in [('expiry_minutes',1,30,'Pending expiry (minutes)'),('tts_limit',1,500,'Longest message viewers can type'),
                               ('alert_seconds',3,30,'Minimum display duration (seconds)'),('tts_short_limit',20,500,'“Read up to” characters'),
                               ('tts_full_from',0,1000000,'“Always read whole messages from” (₹, 0 = off)')]:
            if not isinstance(merged[key],int) or isinstance(merged[key],bool) or not lo<=merged[key]<=hi: raise Problem(f'{what} must be a whole number from {lo} to {hi}.')
        if volume_percent(merged['tts_volume'])!=merged['tts_volume']: raise Problem('Voice volume must be a whole number from 10 to 100.')
        try: merged['pronunciations']=normalize_pronunciations(merged['pronunciations'])
        except ValueError as e: raise Problem(str(e))
        for key in ['tts_enabled','muted','accepting_tips','bridge_enabled','allow_sound_choice','hide_links','tts_cleanup','tts_read_full','auto_session','filter_whole_words']:
            if not isinstance(merged[key],bool): raise Problem('Invalid '+key)
        if merged['upi_id'] and not re.fullmatch(r'[A-Za-z0-9._-]{2,100}@[A-Za-z0-9.-]{2,80}',merged['upi_id']): raise Problem('Invalid UPI ID.')
        if merged['parser'] not in ['disabled','structured-v1','example-credit-v1']: raise Problem('Unknown parser.')
        if merged['bridge_enabled'] and (not merged['bank_sender'] or merged['parser']=='disabled'): raise Problem('Configure sender and parser first.')
        if merged['tts_engine'] not in ['browser','windows','edge','piper','azure','off']: raise Problem('Invalid TTS engine.')
        if not isinstance(merged['tts_backup'],str) or (merged['tts_backup'] and not re.fullmatch(r'(piper|windows):[^\x00-\x1f]{1,120}',merged['tts_backup'])): raise Problem('Choose the backup voice from the list in Admin → TTS.')
        for key in ['voices','banned_words','tiers']:
            if not isinstance(merged[key],list) or len(merged[key])>100: raise Problem('Invalid list: '+key)
        if not merged['voices']: raise Problem('Keep at least one voice.')
        if any(not isinstance(x,str) or len(x)>80 for x in merged['voices']+merged['banned_words']): raise Problem('Invalid list value.')
        if not 1<=len(merged['tiers'])<=8 or any(not isinstance(x,(int,float)) or x<0 for x in merged['tiers']) or sorted(set(merged['tiers']))!=merged['tiers']: raise Problem('Tiers must be ascending unique amounts.')
        for key in ['creator','welcome','payee_name','bank_sender']: merged[key]=clean(merged[key],250)
        with store.db(True) as db:
            for k in d: db.execute('UPDATE settings SET value=? WHERE key=?',(json.dumps(merged[k]),k))
            store.audit(db,'settings_changed',detail={'keys':list(d)})
        return {'ok':True}
    @app.post('/api/admin/alerts')
    def alerts_action():
        d=data()
        with store.db(True) as db:
            action=d.get('action')
            detail=None
            if action=='skip':
                s=store.settings(db); db.execute("UPDATE settings SET value=? WHERE key='skip_version'",(json.dumps(s['skip_version']+1),))
            elif action=='dismiss':  # Skip alert (1.6.4): the alerts on screen stop, card, sound and voice
                playing=[r[0] for r in db.execute("SELECT DISTINCT alert_id FROM deliveries WHERE state='playing' AND lease>=?",(now(),))]
                if not playing: raise Problem('No alert is playing right now.',409)
                store.dismiss(db,playing); detail={'alerts':playing}
            elif action=='test':
                # Sounds like a real tip where the viewer picked nothing (the default), or like a pick of one library sound.
                # 1.6.4: Voice Studio sends its sample as the message; with "Read whole messages" off the built-in one is long.
                s=store.settings(db); message=d.get('message')
                if message is not None:
                    if not isinstance(message,str) or not store.moderated(message,s).strip(): raise Problem('Type a sample message first.')
                    message=store.moderated(message,s)
                else: message=TEST_MESSAGE if s.get('tts_read_full',True) is not False else TEST_LONG_MESSAGE
                tip=dict(id='test-'+uid(),name='Test supporter',display_paise=money(d.get('amount',100)),message=message,tts=True,voice=s['voices'][0],sound=store.resolve_default(db,s)['sound'])
                sb=d.get('soundboard_id')
                if sb is not None:
                    if not isinstance(sb,str) or not re.fullmatch(SOUND_ID,sb): raise Problem('Invalid sound choice.')
                    row=db.execute('SELECT media_filename FROM soundboards WHERE id=?',(sb,)).fetchone()
                    if not row: raise Problem('That sound was removed.',404)
                    if not store.media_ok(row['media_filename']): raise Problem('Upload audio for this sound first.',409)
                    tip['soundboard_id']=sb
                store.alert(db,tip,True)
            elif action=='replay':
                tip=db.execute("SELECT * FROM tips WHERE id=? AND status IN ('VERIFIED','MANUAL')",(d.get('id'),)).fetchone()
                if not tip: raise Problem('Only verified or manually reconciled tips may be replayed.')
                full=d.get('full') is True  # "Replay in full" (1.6.4)
                store.alert(db,dict(tip),read_full=full)
                if full: detail={'full':True}
            else: raise Problem('Unknown alert action.')
            store.audit(db,'alert_'+action,d.get('id',''),detail)
        return {'ok':True,'overlays':clients.summary()} if action=='test' else {'ok':True}
    @app.get('/api/admin/obs')
    def obs_links():
        # OBS on this PC needs no tunnel: loopback, unless HOST names one specific address (Waitress binds IPv6 sockets IPv6-only).
        host=os.getenv('HOST','127.0.0.1').strip().strip('[]')
        host='127.0.0.1' if host in ('','0.0.0.0','localhost') else '[::1]' if host in ('::','::1') else '['+host+']' if ':' in host else host
        return {'key':app.config['OVERLAY_TOKEN'],'base':app.config['PUBLIC_BASE_URL'],'local_base':'http://'+host+':'+os.getenv('PORT','8765')}
    @app.get('/api/admin/audit')
    def audit_list():
        with store.db() as db: return {'audit':rows(db.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 500')),'receipts':rows(db.execute('SELECT * FROM receipts ORDER BY ingested DESC LIMIT 100'))}
    @app.post('/api/admin/backup')
    def backup():
        target=store.backup()
        return send_file(target,mimetype='application/octet-stream',download_name=target.name,as_attachment=True)
    @app.post('/api/admin/simulate/<tid>')
    def simulate(tid):
        if not app.config['DEMO_MODE']: raise Problem('Simulator is disabled in live mode.',403)
        with store.db() as db: tip=db.execute('SELECT * FROM tips WHERE id=?',(tid,)).fetchone()
        if not tip: abort(404)
        return store.verify(dict(amount=f"{tip['requested_paise']/100:.2f}",reference='DEMO-'+uid().replace('_','A').replace('-','B').upper(),received_at=now()),'demo')
    @app.get('/api/overlay/state')
    def overlay_state():
        period=request.args.get('period','week')
        if period not in PERIODS or period=='custom': period='week'
        with store.db() as db:
            s=store.settings(db); summary=store.summary(db,period); blocked=store.blocked_ids(db)
            recent=[dict(name=store.board_name(r['name'],r['supporter_id'],blocked,s),display_paise=r['display_paise'],message='' if r['supporter_id'] in blocked else store.on_stream(r['message'],s))
                    for r in rows(db.execute("SELECT name,display_paise,message,supporter_id FROM tips WHERE status IN ('VERIFIED','MANUAL') ORDER BY verified DESC LIMIT 5"))]
            # 1.6.4: alert pages read session_active and auto_session (OBS going live starts a session) and dismissed (Skip alert).
            return dict(goals=[g for g in store.goal_values(db) if g['enabled']],top=[{'name':store.board_name(p['name'],p['id'],blocked,s),'total':p['total'],'count':p['count']} for p in summary['leaderboard'][:3]],recent=recent,muted=s['muted'],skip_version=s['skip_version'],tts_engine=s['tts_engine'],visuals=s.get('visuals',{}),
                        session_active=store.active(db) is not None,auto_session=s.get('auto_session',True) is True,dismissed=[i for i in (s.get('dismissed_alerts') or []) if isinstance(i,int)])
    @app.post('/api/overlay/live')
    def obs_live():
        """1.6.4: an OBS alert page says OBS started (or stopped) streaming. Starting opens a stream session unless one is
        running or Admin -> OBS switched it off; the overlay key can never end one. reason 'load': the page found OBS
        already live when it loaded (a refresh, or OBS went live before the page was ready), so a session the streamer
        ended in the last 2 hours stays ended."""
        d=data(); streaming=d.get('streaming'); reason=d.get('reason','event')
        if not isinstance(streaming,bool) or reason not in ('event','load'): raise Problem('Invalid live status.')
        store.rate('overlay-live',30,60)
        with store.db(True) as db:
            t=now(); s=store.settings(db); active=store.active(db); started=None
            store._put_setting(db,'obs_live',{'streaming':streaming,'at':t})
            if streaming and not active and s.get('auto_session',True) is True:
                if reason=='event' or not db.execute('SELECT 1 FROM sessions WHERE ended>?',(t-7200,)).fetchone():
                    day=datetime.fromtimestamp(t,IST)
                    started=store.start_session(db,f"Live stream · {day.day} {day.strftime('%b')}",'obs')
                    store._put_setting(db,'session_auto',{'session_id':started,'at':t})
        return {'ok':True,'session_started':started is not None,'session_active':active is not None or started is not None}
    @app.post('/api/overlay/claim')
    def claim():
        d=data(); channel=d.get('channel'); owner=clean(d.get('owner'),80)
        if channel not in ['horizontal','vertical'] or not owner: raise Problem('Invalid channel/client.')
        if clients.record(channel,owner,client_kind(d)): return {'alert':None,'standby':True}  # OBS gets the alerts, not a forgotten browser tab
        with store.db(True) as db:
            # A channel plays at most one alert; a crashed browser can retry after its lease. 1.6.4: not one that was skipped.
            gone=[i for i in (store.settings(db).get('dismissed_alerts') or []) if isinstance(i,int)]
            if gone: db.execute(f"UPDATE deliveries SET state='skipped' WHERE state='playing' AND lease<? AND alert_id IN ({','.join('?'*len(gone))})",(now(),*gone))
            db.execute("UPDATE deliveries SET state='queued',owner=NULL WHERE state='playing' AND lease<?",(now(),))
            # 1.6.4: only an alert still waiting can expire. One that is playing keeps its lease (it used to be marked missed mid-play).
            db.execute("UPDATE deliveries SET state='expired' WHERE state='queued' AND alert_id IN (SELECT id FROM alerts WHERE expires<?)",(now(),))
            if db.execute("SELECT 1 FROM deliveries WHERE channel=? AND state='playing'",(channel,)).fetchone(): return {'alert':None}
            r=db.execute("SELECT a.* FROM alerts a JOIN deliveries d ON a.id=d.alert_id WHERE d.channel=? AND d.state='queued' ORDER BY a.id LIMIT 1",(channel,)).fetchone()
            if not r: return {'alert':None}
            db.execute("UPDATE deliveries SET state='playing',owner=?,lease=? WHERE alert_id=? AND channel=?",(owner,now()+180,r['id'],channel))
            # While a layout keeps playing, the alerts queued behind it don't run out of time (many approvals released after a
            # match) and this one's voice can still be made.
            db.execute("UPDATE alerts SET expires=max(expires,?) WHERE id IN (SELECT alert_id FROM deliveries WHERE channel=? AND state IN ('queued','playing'))",(now()+180,channel))
            p=json.loads(r['payload'])
            if r['tip_id']:
                sup=db.execute('SELECT s.blocked,s.muted,t.status FROM supporters s JOIN tips t ON s.id=t.supporter_id WHERE t.id=?',(r['tip_id'],)).fetchone()
                if not sup or sup['blocked'] or sup['status'] not in ['VERIFIED','MANUAL']:
                    db.execute("UPDATE deliveries SET state='cancelled' WHERE alert_id=?",(r['id'],)); return {'alert':None}
                if sup['muted']: p['tts']=False
            s=store.settings(db)
            try: vflag=store.refresh_alert_sound(db,s,p)
            except Exception: app.logger.exception('alert sound refresh failed'); vflag=False
            if s['muted'] or not s['tts_enabled']: p['tts']=False
            p['message']=store.on_stream(p['message'],s); p['name']=store.stream_name(p.get('name'),s)
            # 1.6.2, ignored by a 1.6.1 overlay: the copy the voice reads, what a Hindi voice reads (so the browser engine
            # matches the server voices) and each sound file's volume. A failure here must never stop the alert.
            try:
                from .tts_service import hindi_speech
                p['speech']=store.speech(p['message'],s,p.get('display_paise'),p.get('read_full') is True)
                if not p['speech']: p['tts']=False  # only emoji or skipped words: nothing to say
                p['speech_hi'],p['hinglish']=hindi_speech(p['speech'])
                p['volumes']=store.sound_volumes(db,s,p)
            except Exception:
                app.logger.exception('alert speech/volume preparation failed')
                for k in ('speech','speech_hi','hinglish','volumes'): p.pop(k,None)
            clients.playing(channel,owner)
            # Per alert: an overlay that OBS kept open since 1.5.9 then plays the pick, the default or the video correctly.
            visuals=dict(s.get('visuals') or {}); visuals.update(alert_sound='viewer',alert_video_has_audio=vflag)
            return {'alert':dict(event_id=r['id'],**p),'tts_engine':s['tts_engine'],'tts_volume':volume_percent(s.get('tts_volume')),'visuals':visuals}
    @app.post('/api/overlay/ack')
    def ack():
        d=data(); channel=d.get('channel'); owner=clean(d.get('owner'),80)
        if channel in ['horizontal','vertical'] and owner: clients.record(channel,owner,client_kind(d))  # before 'done', so OBS is fresh the moment the channel frees up
        with store.db(True) as db:
            r=db.execute('SELECT a.tip_id,d.state FROM alerts a JOIN deliveries d ON a.id=d.alert_id WHERE a.id=? AND d.channel=? AND d.owner=?',(d.get('event_id'),d.get('channel'),d.get('owner'))).fetchone()
            if not r or r['state']!='playing': raise Problem('Alert lease no longer belongs to this client.',409)
            db.execute("UPDATE deliveries SET state=? WHERE alert_id=? AND channel=?",('skipped' if d.get('skipped') is True else 'done',d['event_id'],d['channel']))  # skipped: Skip alert (1.6.4)
            if r['tip_id']: db.execute('UPDATE tips SET alert_shown=1,tts_played=max(tts_played,?) WHERE id=?',(int(bool(d.get('tts_played'))),r['tip_id']))
        return {'ok':True}
    @app.post('/api/admin/media')
    def upload_media():
        file=request.files.get('file'); kind=request.form.get('kind','sound')
        if not file: raise Problem('Choose a file.')
        content=file.read()
        if len(content)>8*1024*1024:raise Problem('Sound/avatar limit is 8 MB.')
        media=store.path/'media'; media.mkdir(exist_ok=True)
        if kind=='avatar':
            from PIL import Image
            try:
                img=Image.open(io.BytesIO(content)); img.thumbnail((600,600)); out=io.BytesIO(); img.convert('RGB').save(out,format='JPEG'); content=out.getvalue()
            except Exception: raise Problem('Invalid image.')
            name=uid()+'.jpg'
            (media/name).write_bytes(content)
            with store.db(True) as db:
                db.execute("UPDATE settings SET value=? WHERE key='avatar'",(json.dumps('/media/'+name),))
                store.audit(db,'upload_media',name)
            return {'ok':True,'name':name}
        # A sound-library upload, stored under a random name (never the uploader's); the original is kept for display only.
        # The 30 s cap matches the overlay's 31000 ms playback watchdog. Form fields are checked before any work is done.
        form=request.form; original_name=sanitize_original_name(file.filename)
        try: min_paise=int(form.get('min_paise') or 0)
        except ValueError: min_paise=-1
        if not 0<=min_paise<=10000000: raise Problem('Minimum tip must be between ₹0 and ₹100000.')
        label=clean(form.get('name'),80); emoji=clean(form.get('emoji'),8); category=clean(form.get('category'),40) or 'General'
        offered=form.get('offered','1')!='0'; make_default=form.get('make_default','0')!='0'
        content,ext,duration_ms,auto_fixed=validate_or_fix_audio(content,max_duration_ms=SOUND_MAX_MS)
        name=uid()+'.'+ext
        (media/name).write_bytes(content)
        try:
            with store.db(True) as db:
                sid=store._insert_sound(db,name=label or display_label(original_name) or 'Uploaded sound',emoji=emoji,category=category,min_paise=min_paise,enabled=offered,media_filename=name,duration_ms=duration_ms)
                store.remember_upload(db,name,original_name,auto_fixed)
                if make_default: store.put_default_sound(db,sid,'upload')
                store.audit(db,'upload_media',name,{'original_name':original_name,'auto_fixed':auto_fixed})
                entry=dict(db.execute('SELECT * FROM soundboards WHERE id=?',(sid,)).fetchone())
        except Exception:
            (media/name).unlink(missing_ok=True); raise
        return {'ok':True,'name':name,'original_name':original_name,'auto_fixed':auto_fixed,'entry':entry|{'url':'/media/'+name}}
    @app.get('/media/<name>')
    def media_file(name):
        if not re.fullmatch(r'[A-Za-z0-9_-]+\.(wav|jpg|png|webp|gif|webm|mp3|ogg)',name): abort(404)
        return send_file(store.path/'media'/name)

    sound_probes = {}  # (path, size, mtime_ns) -> ffprobe result, so reopening Sound library doesn't re-probe every file
    @app.get('/api/admin/sounds/list')
    def admin_sounds_list():
        """v1.5.7 — scan every uploaded sound (not chime/pulse/none) with ffprobe and report
        codec, duration, and whether a browser can actually decode it. Lets the admin spot the
        legacy broken uploads that cause 'no supported source' errors on the tipping page.
        1.6.0: library files first, in library order (id, offered, default), then older settings.sounds entries."""
        from .video import probe_audio_file
        with store.db() as db:
            settings = store.settings(db); d = store.resolve_default(db, settings)
            library = rows(db.execute('SELECT id,enabled,media_filename FROM soundboards WHERE media_filename IS NOT NULL ORDER BY display_order,created'))
        owners = {}
        for e in library: owners.setdefault(e['media_filename'], e)
        default_file = next((e['media_filename'] for e in library if e['id'] == d['item_id']), None) if d['kind'] == 'item' else d['sound'] if d['kind'] == 'legacy' else None
        listed = [x for x in settings.get('sounds', []) if x not in BUILTIN_SOUNDS]
        # Uploads the admin stopped offering to viewers stay visible here so they can be re-offered or deleted.
        unlisted = _known_uploads(settings) - set(listed) - set(owners)
        names = list(dict.fromkeys(list(owners) + listed + sorted(n for n in unlisted if (store.path / 'media' / n).is_file())))
        labels = sound_labels(settings | {'sounds': names})
        auto_fixed = set(settings.get('media_auto_fixed') or [])
        ffprobe = probe_audio_file(b'', '.mp3')['valid'] is not None
        out = []
        for name in names:
            path = store.path / 'media' / name; e = owners.get(name)
            base = {'name': name, 'display_name': labels.get(name) or name, 'listed': bool(e['enabled']) if e else name in listed,
                    'id': e['id'] if e else None, 'offered': bool(e['enabled']) if e else None, 'default': name == default_file,
                    'auto_fixed': name in auto_fixed, 'missing': False, 'codec': None, 'duration_ms': None, 'size_bytes': 0}
            if not path.is_file():
                out.append(base | {'playable': False, 'missing': True, 'reason': 'File missing from the media folder (data/media).'})
                continue
            try:
                st = path.stat(); key = (str(path), st.st_size, st.st_mtime_ns)
                probe = sound_probes.get(key) if ffprobe else None
                if probe is None:
                    ext = ('.' + name.rsplit('.', 1)[-1]).lower() if '.' in name else ''
                    probe = probe_audio_file(path.read_bytes(), ext) if ext in ['.wav', '.mp3', '.ogg'] else {'valid': None, 'codec': None, 'duration_ms': None, 'reason': 'Unknown extension'}
                    if ffprobe and probe['valid'] is not None:
                        if len(sound_probes) > 512: sound_probes.clear()
                        sound_probes[key] = probe
            except Exception as ex:
                out.append(base | {'playable': False, 'reason': f'Could not read file: {type(ex).__name__}'})
                continue
            out.append(base | {
                'playable': probe['valid'],  # None = not checked (FFmpeg/ffprobe not installed)
                'codec': probe.get('codec'),
                'duration_ms': probe.get('duration_ms'),
                'reason': probe.get('reason') if probe['valid'] is False else None,
                'size_bytes': st.st_size,
            })
        return {'items': out, 'ffprobe_available': ffprobe}

    @app.delete('/api/admin/sounds/<name>')
    def admin_sounds_delete(name):
        """Remove a sound everywhere: every library row that plays it, the settings.sounds mirror and its upload
        metadata; after commit the file itself, unless something else still uses it."""
        safe = re.fullmatch(_STORED_SOUND, name) is not None
        if name in BUILTIN_SOUNDS: raise Problem('Cannot delete built-in sound.')
        with store.db(True) as db:
            s = store.settings(db)
            sounds = s.get('sounds', [])
            owners = [r['id'] for r in db.execute('SELECT id FROM soundboards WHERE media_filename=? ORDER BY display_order,created', (name,))] if safe else []
            if not owners and name not in sounds and not (safe and name in _known_uploads(s)):
                if not safe: raise Problem('Invalid filename.')
                raise Problem('Sound is not in the allowlist.', 404)
            # A hand-typed entry that was never a file (older builds allowed any text) is only unlisted.
            reset = False
            for sid in owners: reset = store._delete_sound_row(db, sid)[0] or reset
            store._drop_file_refs(db, name)
            store.audit(db, 'sound_deleted', name)
        if safe: store._unlink_if_unused(name)
        return {'ok': True, 'name': name, 'default_reset': reset}
    # ---------- Soundboard (admin CRUD + public gallery) ----------
    @app.get('/api/public/soundboard')
    def public_soundboard():
        """Return the library sounds viewers can pick, with their /media/ URL. Empty while viewer picks are
        switched off; hides sounds that aren't offered and sounds without a playable file."""
        if store.settings().get('allow_sound_choice') is not True: return {'items':[]}
        items=[]
        for e in store.soundboard_list(enabled_only=True):
            if not store.media_ok(e.get('media_filename')): continue
            items.append({
                'id':e['id'],
                'name':e['name'],
                'emoji':e.get('emoji') or '',
                'category':e.get('category') or 'General',
                'min_paise':int(e.get('min_paise') or 0),
                'duration_ms':int(e.get('duration_ms') or 0),
                'url':'/media/'+e['media_filename'],
                'volume':volume_percent(e.get('volume')),
            })
        return {'items':items}
    @app.get('/api/admin/soundboard')
    def admin_soundboard_list():
        with store.db() as db:
            s=store.settings(db); d=store.resolve_default(db,s); items=rows(db.execute('SELECT * FROM soundboards ORDER BY display_order,created'))
        labels=s.get('media_labels') if isinstance(s.get('media_labels'),dict) else {}; fixed=set(s.get('media_auto_fixed') or [])
        is_default=lambda e:(d['kind']=='item' and e['id']==d['item_id']) or (d['kind']=='legacy' and e['media_filename']==d['sound'])
        return {'items':[{**e,'url':('/media/'+e['media_filename']) if e['media_filename'] else None,'missing':bool(e['media_filename']) and not store.media_ok(e['media_filename']),
                          'original_name':labels.get(e['media_filename']) or '','auto_fixed':e['media_filename'] in fixed,'is_default':is_default(e)} for e in items],
                'default':d['value'],'default_kind':d['kind'],'default_name':d['name'],'default_problem':d['problem'],
                'video_audio_available':store.video_audio_available(s),'picks_on':s.get('allow_sound_choice') is True}
    @app.post('/api/admin/soundboard/default')
    def admin_soundboard_default():
        value=data().get('value')
        with store.db(True) as db: v=store.put_default_sound(db,value,'admin')
        return {'ok':True,'default':v}
    @app.post('/api/admin/soundboard')
    def admin_soundboard_create():
        d=data()
        entry=store.soundboard_create(
            name=d.get('name',''),
            emoji=d.get('emoji',''),
            category=d.get('category','General'),
            min_paise=int(d.get('min_paise',5000)),
            enabled=bool(d.get('enabled',False)),  # start disabled until audio uploaded
        )
        return {'ok':True,'entry':entry},201
    @app.post('/api/admin/soundboard/<sb_id>')
    def admin_soundboard_update(sb_id):
        d=data()
        if not re.fullmatch(r'[A-Za-z0-9_-]{3,80}',sb_id): raise Problem('Invalid id.')
        return {'ok':True,'entry':store.soundboard_update(sb_id,**d)}
    @app.post('/api/admin/soundboard/reorder')
    def admin_soundboard_reorder():
        d=data()
        store.soundboard_reorder(d.get('order',{}))
        return {'ok':True}
    @app.post('/api/admin/soundboard/seed')
    def admin_soundboard_seed():
        # `created` keeps its 1.5.9 meaning (the new rows); `ready` names the starter sounds that just got their bundled audio.
        created=store.soundboard_seed(); ready=store.seed_starter_audio()
        return {'ok':True,'created':created,'ready':ready}
    @app.delete('/api/admin/soundboard/<sb_id>')
    def admin_soundboard_delete(sb_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]{3,80}',sb_id): raise Problem('Invalid id.')
        return {'ok':True,'default_reset':store.soundboard_delete(sb_id)}
    @app.post('/api/admin/soundboard/<sb_id>/media')
    def admin_soundboard_upload(sb_id):
        """Upload / replace the audio clip for a soundboard entry: WAV, MP3 or OGG, at most 8 MB
        and 30 s. Files a browser couldn't play are re-encoded to MP3 (see validate_or_fix_audio).
        The entry's own name is what admins and viewers see, so the upload filename isn't stored.
        A slot's first clip switches it on (the seed message promises this); replacing a clip keeps
        whatever on/off choice the admin made."""
        if not re.fullmatch(r'[A-Za-z0-9_-]{3,80}',sb_id): raise Problem('Invalid id.')
        before=store.soundboard_get(sb_id)
        if not before: raise Problem('Soundboard entry not found.',404)
        file=request.files.get('file')
        if not file: raise Problem('Choose a .wav, .mp3, or .ogg file.')
        content=file.read()
        if len(content)>8*1024*1024: raise Problem('Clip limit is 8 MB.')
        content,ext,duration_ms,auto_fixed=validate_or_fix_audio(content,max_duration_ms=SOUND_MAX_MS)
        media=store.path/'media'; media.mkdir(exist_ok=True)
        name=uid()+'.'+ext
        (media/name).write_bytes(content)
        try: entry=store.soundboard_set_media(sb_id,name,duration_ms)
        except Exception: (media/name).unlink(missing_ok=True); raise
        if not before.get('media_filename') and not entry.get('enabled'): entry=store.soundboard_update(sb_id,enabled=True)
        return {'ok':True,'entry':entry|{'url':'/media/'+name},'original_name':sanitize_original_name(file.filename),'auto_fixed':auto_fixed}

    @app.get('/api/overlay/tts/<int:event_id>')
    def tts_file(event_id):
        from .tts_service import synthesize_alert, _mimetype_for
        with store.db() as db:
            event=db.execute('SELECT * FROM alerts WHERE id=? AND expires>?',(event_id,now())).fetchone()
            s=store.settings(db)
        if not event or not json.loads(event['payload'])['tts'] or s['muted']: abort(404)
        p=json.loads(event['payload'])
        text=store.speech(store.on_stream(p['message'],s),s,p.get('display_paise'),p.get('read_full') is True)
        if not text: abort(404)  # only emoji or skipped words; 1.6.2 overlays don't ask
        path,_=synthesize_alert(app,store,text,p['voice'],s)  # a failure is saved for the dashboard and Voice Studio
        return send_file(path,mimetype=_mimetype_for(path),max_age=0)
    return app
