"""Money and time are integer paise and UTC epoch seconds. Periods use Asia/Kolkata."""
import csv, hashlib, hmac, io, json, logging, math, re, secrets, sqlite3, time
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo
from .text_filters import first_part, hide_links, name_filter, speech_text, tidy_message, word_filter

IST = ZoneInfo('Asia/Kolkata')
DEFAULTS = dict(creator='AcePressure', welcome='Good games. Better company. Thanks for supporting the stream.',
    upi_id='', payee_name='', minimum=20, maximum=10000, expiry_minutes=10,
    bridge_enabled=False, bank_sender='', parser='disabled', tts_enabled=True, tts_minimum=50,
    tts_limit=180, banned_words=['fuck','shit'], muted=False, skip_version=0,
    tts_engine='browser', voices=['en-IN','hi-IN'], sounds=['chime','pulse','none'],
    allow_sound_choice=True, tiers=[1,50,200,500], alert_seconds=9,
    avatar='', accepting_tips=True,
    # 1.6.2: voice volume in %, links hidden on stream, the voice skips emoji and long repeats, Admin -> TTS pronunciations.
    tts_volume=100, hide_links=True, tts_cleanup=True, pronunciations=[],
    # 1.6.3: "Read whole messages" (Admin -> TTS and the Live activity panel). Off: the voice reads only the first
    # tts_short_limit characters, while the alert card still shows the whole message.
    tts_read_full=True, tts_short_limit=100,
    # 1.6.4: OBS going live starts a stream session; tips of tts_full_from rupees or more are read in full (0: off); the
    # offline voice that reads when the voice service fails ('' stays silent, else 'piper:<id>' or 'windows:<name>');
    # filtered words match whole words only (a database from before 1.6.4 keeps matching inside words until switched on).
    auto_session=True, tts_full_from=0, tts_backup='', filter_whole_words=True)
UPGRADE_VALUES=dict(filter_whole_words=False)  # what a new setting starts as in a database that already has settings
ANONYMOUS='Anonymous supporter'  # a blocked supporter on the boards viewers see (1.6.4)
# Sound library (1.6.0): every uploaded sound is a soundboards row; settings.default_sound plays when a viewer doesn't pick.
BUILTIN_SOUNDS = ('chime', 'pulse', 'none')
STORED_SOUND = r'[A-Za-z0-9_-]+\.(wav|mp3|ogg)'
SOUND_ID = r'[A-Za-z0-9_-]{3,80}'
SOUND_MAX_MS = 30000  # every library sound; the overlay's file watchdog is 31 s
_AUDIO_EXT = re.compile(r'\.(mp3|ogg|oga|opus|wav|m4a|aac|flac|webm|wma|aiff?)$', re.I)
def display_label(original_name): return clean(_AUDIO_EXT.sub('', original_name or ''), 80)
def known_uploads(settings):
    """Stored names of alert sounds uploaded through the admin page, whether or not viewers are offered them."""
    names = set((settings.get('media_labels') or {}).keys()) | set(settings.get('media_auto_fixed') or [])
    return {n for n in names if re.fullmatch(STORED_SOUND, n)}
# Starter rows that come with an original sound effect made for AcePressure (CC0, see starter_sounds/README.txt), in seed order.
STARTER_AUDIO = {'Vine Boom': 'vine-boom.mp3', 'Air Horn': 'air-horn.mp3', 'Cash Register': 'cash-register.mp3', 'Victory Fanfare': 'victory-fanfare.mp3',
                 'Clap': 'clap.mp3', 'Game Over': 'game-over.mp3', 'Ba Dum Tss': 'ba-dum-tss.mp3', 'Sad Trombone': 'sad-trombone.mp3'}
STARTER_DIR = Path(__file__).resolve().parent/'starter_sounds'
PERIODS=['stream','today','yesterday','week','last_week','month','last_month','year','lifetime','custom']
class Problem(Exception):
    def __init__(self, message, status=400): self.message, self.status=message,status

def now(): return int(time.time())
def uid(): return secrets.token_urlsafe(12)
def money(value):
    try:
        d=Decimal(str(value))
        if not d.is_finite() or d<0 or d>10000000 or d.as_tuple().exponent < -2: raise ValueError()
        return int(d*100)
    except (InvalidOperation,ValueError,TypeError): raise Problem('Invalid amount; use at most two decimal places.')
def clean(value, limit):
    return re.sub(r'[\x00-\x1f\x7f<>]', '', str(value or '')).strip()[:limit]
def rows(cur): return [dict(r) for r in cur.fetchall()]
def volume_percent(value):
    """A stored volume (sound library row or settings.tts_volume) as 10-100; anything else plays as uploaded (100)."""
    return value if isinstance(value,int) and not isinstance(value,bool) and 10<=value<=100 else 100

class Store:
    def __init__(self, directory, secret):
        self.path=Path(directory).resolve(); self.path.mkdir(parents=True,exist_ok=True)
        self.dbpath=self.path/'acepressure.sqlite3'; self.secret=secret
        with self.db() as db:
            db.execute('PRAGMA journal_mode=WAL')
            for file in sorted((Path(__file__).parent/'migrations').glob('*.sql')):
                sql = file.read_text(encoding='utf-8')
                # Migrations are re-run on every startup. CREATE ... IF NOT EXISTS is
                # natively idempotent; ALTER TABLE ADD COLUMN is not. Split each file
                # into statements and skip "duplicate column name" errors so additive
                # column migrations stay replay-safe. All other errors propagate.
                for stmt in [s.strip() for s in sql.split(';') if s.strip()]:
                    try:
                        db.execute(stmt)
                    except sqlite3.OperationalError as e:
                        if 'duplicate column name' not in str(e).lower():
                            raise
            upgrade=db.execute('SELECT 1 FROM settings LIMIT 1').fetchone() is not None
            for k,v in DEFAULTS.items(): db.execute('INSERT OR IGNORE INTO settings VALUES (?,?)',(k,json.dumps(UPGRADE_VALUES.get(k,v) if upgrade else v)))
        self._migrate_sound_library()
    @contextmanager
    def db(self, write=False):
        db=sqlite3.connect(self.dbpath,timeout=20); db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON'); db.execute('PRAGMA busy_timeout=20000')
        try:
            if write: db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except Exception:
            db.rollback(); raise
        finally: db.close()
    def settings(self,db=None):
        if db is None:
            with self.db() as d: return self.settings(d)
        return {r['key']:json.loads(r['value']) for r in db.execute('SELECT * FROM settings')}
    def remember_upload(self,db,name,original_name,auto_fixed):
        """Record the uploader's filename (display only) and whether the server re-encoded the file."""
        s=self.settings(db)
        labels=dict(s.get('media_labels') or {}); fixed=[x for x in s.get('media_auto_fixed') or [] if x!=name]
        if original_name: labels[name]=original_name
        if auto_fixed: fixed.append(name)
        self._put_upload_meta(db,labels,fixed)
    def remember_visual(self,db,name,original_name):
        """1.6.7: the uploader's filename for a Design studio file (display only), so files uploaded together can be told apart.
        Kept apart from media_labels, which lists alert sounds."""
        if not original_name: return
        s=self.settings(db); labels=dict(s.get('visual_labels') if isinstance(s.get('visual_labels'),dict) else {})
        labels[name]=original_name; self._put_setting(db,'visual_labels',labels)
    def forget_upload(self,db,name):
        s=self.settings(db)
        self._put_upload_meta(db,{k:v for k,v in (s.get('media_labels') or {}).items() if k!=name},[x for x in s.get('media_auto_fixed') or [] if x!=name])
    def _put_upload_meta(self,db,labels,fixed):
        for key,value in [('media_labels',labels),('media_auto_fixed',fixed)]:
            db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(value)))
    def _put_setting(self,db,key,value):
        db.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(value)))
    def audit(self,db,action,obj='',detail=None):
        db.execute('INSERT INTO audit(at,actor,action,object_id,detail) VALUES (?,?,?,?,?)',(now(),'admin',action,obj,json.dumps(detail or {},ensure_ascii=False)))
    def expire(self,db,t=None):
        db.execute("UPDATE tips SET status='EXPIRED' WHERE status='PENDING' AND expires<=?",(t or now(),))
    def active(self,db):
        r=db.execute('SELECT * FROM sessions WHERE ended IS NULL').fetchone(); return dict(r) if r else None
    def rate(self,bucket,limit,seconds):
        with self.db(True) as db:
            t=now(); db.execute('DELETE FROM rate_limits WHERE until<?',(t,))
            r=db.execute('SELECT * FROM rate_limits WHERE bucket=?',(bucket,)).fetchone()
            if r and r['count']>=limit:
                wait=max(1,math.ceil((r['until']-t)/60)); raise Problem(f"Too many requests. Please wait about {wait} minute{'s' if wait>1 else ''}.",429)
            db.execute('INSERT INTO rate_limits VALUES (?,1,?) ON CONFLICT(bucket) DO UPDATE SET count=count+1',(bucket,t+seconds))
    def moderated(self,text,s):
        """A message as a tip stores it: line breaks made spaces and <3 a heart (1.6.4), cut to the typing limit, filtered
        words replaced (whole words only when settings.filter_whole_words is on)."""
        return word_filter(clean(tidy_message(text),int(s['tts_limit'])),s['banned_words'],s.get('filter_whole_words') is True)
    # 1.6.2: what reaches the stream (alert card, OBS boards, the tip page's top supporters) and what the voice reads.
    # Tips keep what the viewer typed, and the dashboard shows that.
    def on_stream(self,text,s):
        """A message as shown on stream and read aloud: links hidden (settings.hide_links), then filtered words."""
        return self.moderated(hide_links(text) if s.get('hide_links',True) else text,s)
    def stream_name(self,name,s):
        """A supporter's name as shown on stream: links hidden (settings.hide_links), then filtered words (1.6.4), always as
        whole words, where _, digits and capitals also split a name into words (1.6.5, text_filters.name_filter): matching
        inside names showed "Kshitij" as "K[filtered]ij" on a database from before 1.6.4. Messages follow
        settings.filter_whole_words."""
        if not isinstance(name,str): return name
        return name_filter(hide_links(name) if s.get('hide_links',True) else name,s.get('banned_words'))
    def blocked_ids(self,db): return {r[0] for r in db.execute('SELECT id FROM supporters WHERE blocked=1')}
    def board_name(self,name,supporter_id,blocked,s):
        """A name on the boards viewers see (OBS Top 3 and Recent, the tip page's Top 3): blocked supporters are
        anonymous there (1.6.4); totals, goals and the dashboard stay exact."""
        return ANONYMOUS if supporter_id in blocked else self.stream_name(name,s)
    def speech(self,text,s,amount=None,full=False):
        """The copy of an on-stream message that the voice reads: the streamer's pronunciations, then (unless
        settings.tts_cleanup is off) no emoji and no long repeats, then (when settings.tts_read_full is off, 1.6.3) only
        its first settings.tts_short_limit characters, unless reads_whole. Empty means there is nothing to say."""
        out=speech_text(text,s.get('pronunciations'),s.get('tts_cleanup',True) is not False)
        return out if self.reads_whole(s,amount,full) else first_part(out,int(s.get('tts_short_limit',100)))
    def reads_whole(self,s,amount=None,full=False):
        """Whether the voice reads a whole message: "Read whole messages" is on, the alert is a "Replay in full" (full),
        or the tip (amount, paise) reaches settings.tts_full_from rupees (1.6.4)."""
        if full is True or s.get('tts_read_full',True) is not False: return True
        t=s.get('tts_full_from')
        return isinstance(t,int) and not isinstance(t,bool) and t>0 and isinstance(amount,int) and not isinstance(amount,bool) and amount>=t*100
    def start_session(self,db,title,source='admin'):
        """Start a stream session inside the caller's transaction and return its id. Tips still waiting for payment that
        were made with no session running join it (1.6.4), so a viewer who tipped just before the stream went live still
        gets an alert when the payment arrives. source: admin or obs (OBS went live)."""
        sid=uid(); t=now()
        db.execute('INSERT INTO sessions VALUES (?,?,?,NULL)',(sid,title,t))
        joined=db.execute("UPDATE tips SET session_id=? WHERE session_id IS NULL AND status='PENDING' AND expires>?",(sid,t)).rowcount
        self.audit(db,'start_session',sid,{'source':source,'waiting_tips_joined':joined})
        return sid
    def dismiss(self,db,alert_ids):
        """Skip alert (1.6.4): OBS pages playing one of these alerts stop it (card, sound and voice) and leave; a layout
        that hasn't started it yet never will. skip_version also moves, so a page from before 1.6.4 still stops the voice."""
        ids=[i for i in alert_ids if isinstance(i,int)]
        if not ids: return
        s=self.settings(db); kept=[i for i in (s.get('dismissed_alerts') or []) if isinstance(i,int) and i not in ids]
        self._put_setting(db,'dismissed_alerts',(kept+ids)[-20:])
        db.execute(f"UPDATE deliveries SET state='cancelled' WHERE state='queued' AND alert_id IN ({','.join('?'*len(ids))})",ids)
        self._put_setting(db,'skip_version',s['skip_version']+1)
    def payment_ready(self,s,db=None):
        if db is None:
            with self.db() as conn:return self.payment_ready(s,conn)
        bridge=db.execute('SELECT enabled FROM paytm_bridge WHERE id=1').fetchone()
        return bool(s['upi_id'] and s['payee_name'] and (s['bridge_enabled'] or bridge['enabled']))
    def create_tip(self,data,demo=False,browser_token=None):
        with self.db(True) as db:
            t=now(); self.expire(db,t); s=self.settings(db)
            if not s['accepting_tips']: raise Problem('Tips are temporarily paused.',503)
            if not demo and not self.payment_ready(s,db): raise Problem('Payment verification is not ready. Please check back later.',503)
            amount=money(data.get('amount'))
            if amount%100 or not money(s['minimum'])<=amount<=money(s['maximum']): raise Problem('Choose a whole-rupee amount within the allowed range.')
            name=clean(tidy_message(data.get('name')),40)
            if not name: raise Problem('Please enter a display name.')
            email=clean(data.get('email'),254).lower()
            if email and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email): raise Problem('Enter a valid email or leave it blank.')
            # Email grouping is explicitly unverified, never authorization. Anonymous names are NOT identities.
            identity=hmac.new(self.secret.encode(),('email:'+email if email else 'anon:'+uid()).encode(),hashlib.sha256).hexdigest()
            sup=db.execute('SELECT * FROM supporters WHERE identity_hash=?',(identity,)).fetchone()
            browser_hash=hmac.new(self.secret.encode(),('browser:'+browser_token).encode(),hashlib.sha256).hexdigest() if browser_token else None
            if not email and browser_hash:
                remembered=db.execute('SELECT supporter_id FROM browser_supporters WHERE token_hash=? AND expires>?',(browser_hash,t)).fetchone()
                if remembered: sup=db.execute('SELECT * FROM supporters WHERE id=?',(remembered['supporter_id'],)).fetchone()
            if sup:
                alias=db.execute('SELECT target_id FROM supporter_aliases WHERE source_id=?',(sup['id'],)).fetchone()
                if alias:sup=db.execute('SELECT * FROM supporters WHERE id=?',(alias['target_id'],)).fetchone()
            if sup and sup['blocked']: raise Problem('This supporter is blocked.',403)
            sid=sup['id'] if sup else uid()
            if not sup: db.execute('INSERT INTO supporters(id,identity_hash,email,name) VALUES (?,?,?,?)',(sid,identity,email or None,name))
            else: db.execute('UPDATE supporters SET name=? WHERE id=?',(name,sid))
            if browser_hash:
                db.execute('DELETE FROM browser_supporters WHERE expires<?',(t,))
                db.execute('INSERT INTO browser_supporters VALUES (?,?,?) ON CONFLICT(token_hash) DO UPDATE SET supporter_id=excluded.supporter_id,expires=excluded.expires',(browser_hash,sid,t+31536000))
            db.execute('DELETE FROM amount_leases WHERE until<?',(t,))
            used={r[0] for r in db.execute('SELECT amount FROM amount_leases')}
            candidates=[amount+p for p in range(1,100) if amount+p not in used]
            if not candidates: raise Problem('This amount is temporarily busy. Choose another whole-rupee amount.',409)
            exact=secrets.choice(candidates)
            # A full-day quarantine prevents most late-payment collisions after pending expiry.
            db.execute('INSERT INTO amount_leases VALUES (?,?)',(exact,t+86400))
            session=self.active(db); tid=uid(); token=secrets.token_urlsafe(32)
            voice=data.get('voice',s['voices'][0])
            if voice not in s['voices']: raise Problem('Invalid voice.')
            sound=self.resolve_default(db,s)['sound']  # tips.sound is NOT NULL; data['sound'] is ignored
            # Optional pick from the sound library: it must exist, be offered to viewers, have a playable
            # file, and the tip must clear its minimum. Tips without one play the streamer's default.
            sb_id=data.get('soundboard_id') or None
            if sb_id is not None:
                if not isinstance(sb_id,str) or not re.fullmatch(SOUND_ID,sb_id):
                    raise Problem('Invalid soundboard id.')
                if not s['allow_sound_choice']: raise Problem('Sound picks are switched off right now. Clear your sound choice and try again.',409)
                sb=db.execute('SELECT id,enabled,min_paise,media_filename FROM soundboards WHERE id=?',(sb_id,)).fetchone()
                if not sb: raise Problem('That soundboard clip no longer exists.',404)
                if not sb['enabled']: raise Problem('That soundboard clip is disabled.',409)
                if not sb['media_filename']: raise Problem('That soundboard clip has no audio file yet.',409)
                if not self.media_ok(sb['media_filename']): raise Problem('That sound is unavailable right now. Pick another or clear your choice.',409)
                if amount<int(sb['min_paise']): raise Problem(f"Tip at least ₹{int(sb['min_paise'])//100} to play this sound.",400)
            db.execute('''INSERT INTO tips(id,token,supporter_id,name,display_paise,requested_paise,message,created,expires,session_id,status,tts,voice,sound,soundboard_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,'PENDING',?,?,?,?)''',(tid,token,sid,name,amount,exact,self.moderated(data.get('message'),s),t,t+int(s['expiry_minutes'])*60,session['id'] if session else None,int(bool(data.get('tts'))),voice,sound,sb_id))
            return dict(db.execute('SELECT * FROM tips WHERE id=?',(tid,)).fetchone())
    def alert(self,db,tip,test=False,read_full=False):
        s=self.settings(db); sup=db.execute('SELECT * FROM supporters WHERE id=?',(tip.get('supporter_id',''),)).fetchone()
        if sup and sup['blocked']: return
        payload={k:tip.get(k) for k in ['id','name','display_paise','message','voice','sound']}
        if read_full: payload['read_full']=True  # "Replay in full" (1.6.4): this alert reads the whole message
        # The overlay needs no database: the pick becomes its clip filename and `sound` is what plays without one
        # (or if the clip fails to load). sound_source is one of pick|tip|default|video; old overlays ignore it.
        try:
            sound,source=self._no_pick_sound(db,s,tip)
            sb_id=tip.get('soundboard_id')
            row=db.execute('SELECT media_filename FROM soundboards WHERE id=?',(sb_id,)).fetchone() if isinstance(sb_id,str) and re.fullmatch(SOUND_ID,sb_id) else None
            if row and self.media_ok(row['media_filename']):  # no enabled/min check: a paid pick always plays
                payload.update(soundboard_clip=row['media_filename'],soundboard_id=sb_id,sound='chime' if source=='video' else sound,sound_source='pick')
            else: payload.update(sound=sound,sound_source=source)
        except Exception:
            payload.pop('soundboard_clip',None); payload.pop('soundboard_id',None)
            payload.update(sound='chime',sound_source='default')
        payload.update(test=test,test_label=('DEMO • PAYTM NOTIFICATION MATCH' if tip.get('verification_source')=='demo-paytm-notification' else 'TEST ALERT • NO MONEY RECEIVED'),tts=bool(tip.get('tts') and s['tts_enabled'] and not s['muted'] and (not sup or not sup['muted']) and tip['display_paise']>=money(s['tts_minimum'])),tier=sum(tip['display_paise']>=money(x) for x in s['tiers']),seconds=s['alert_seconds'])
        cur=db.execute('INSERT INTO alerts(tip_id,payload,created,expires) VALUES (?,?,?,?)',(None if test else tip['id'],json.dumps(payload),now(),now()+300))
        for channel in ['horizontal','vertical']: db.execute('INSERT INTO deliveries(alert_id,channel) VALUES (?,?)',(cur.lastrowid,channel))
    def _no_pick_sound(self,db,s,tip):
        """(sound, source) for an alert without a playable pick."""
        m=s.get('sound_library_migrated') if isinstance(s.get('sound_library_migrated'),dict) else {}
        own,created=tip.get('sound'),tip.get('created')
        if m and not m.get('had_fixed_sound') and isinstance(created,int) and created<int(m.get('at') or 0) and self.playable(own):
            return own,'tip'  # made on a 1.5.9 page: keep the viewer's old choice
        d=self.resolve_default(db,s)
        if not d['problem']: return d['sound'],('video' if d['kind']=='video' else 'default')
        if self.playable(own): return own,'tip'
        return 'chime','default'
    def refresh_alert_sound(self,db,s,p):
        """Repair a queued payload at claim time (the stored payload is never rewritten) and return the per-alert
        alert_video_has_audio flag: a clip deleted or replaced since, a payload frozen by 1.5.9, a video gone silent."""
        def fallback():
            d=self.resolve_default(db,s)
            return d['sound'] if not d['problem'] and d['kind']!='video' else 'chime'
        clip=p.get('soundboard_clip')
        if clip is not None and not self.media_ok(clip):  # deleted or replaced after the alert was queued
            sid=p.get('soundboard_id')
            row=db.execute('SELECT media_filename FROM soundboards WHERE id=?',(sid,)).fetchone() if isinstance(sid,str) and re.fullmatch(SOUND_ID,sid) else None
            if row and self.media_ok(row['media_filename']): p['soundboard_clip']=row['media_filename']
            else: p.pop('soundboard_clip',None); p.pop('soundboard_id',None)
        src=p.get('sound_source')
        if p.get('soundboard_clip'): vflag=False
        elif src is None:  # payload frozen by 1.5.9 (at most 300 s across the restart)
            p['sound'],src2=self._no_pick_sound(db,s,{'sound':p.get('sound'),'created':0}); vflag=src2=='video'
        elif src=='video':
            vflag=self.video_audio_available(s)
            if not vflag: p['sound']=fallback()
        else: vflag=False
        if not vflag and not self.playable(p.get('sound')): p['sound']=fallback()
        return vflag
    def sound_volumes(self,db,s,p):
        """{file: volume %} for the files a claimed alert may play (the pick, then the no-pick sound), from their library
        rows; the pick's own row and the default's row win when one file is in several rows. Built-in sounds have no row."""
        out,d={},None
        for key in ('soundboard_clip','sound'):
            f=p.get(key)
            if not isinstance(f,str) or f in out or not re.fullmatch(STORED_SOUND,f): continue
            row=None
            if key=='soundboard_clip' and isinstance(p.get('soundboard_id'),str):
                row=db.execute('SELECT volume FROM soundboards WHERE id=? AND media_filename=?',(p['soundboard_id'],f)).fetchone()
            if row is None:
                d=d or self.resolve_default(db,s)
                if d['kind']=='item' and d['sound']==f: row=db.execute('SELECT volume FROM soundboards WHERE id=?',(d['item_id'],)).fetchone()
            if row is None: row=db.execute('SELECT volume FROM soundboards WHERE media_filename=? ORDER BY display_order,created LIMIT 1',(f,)).fetchone()
            out[f]=volume_percent(row['volume'] if row else None)
        return out
    def default_volume(self,db,s):
        """The default sound's library volume (100 for Chime, Pulse, Silent or the alert video)."""
        d=self.resolve_default(db,s)
        row=db.execute('SELECT volume FROM soundboards WHERE id=?',(d['item_id'],)).fetchone() if d['kind']=='item' and not d['problem'] else None
        return volume_percent(row['volume'] if row else None)
    def verify(self,receipt,source='sms'):
        amount=money(receipt['amount']); ref=clean(receipt['reference'],100).upper()
        if not re.fullmatch(r'[A-Z0-9-]{6,100}',ref): raise Problem('Missing or invalid bank reference.')
        try: received=int(receipt['received_at'])
        except (KeyError,ValueError,TypeError): raise Problem('received_at must be UTC Unix seconds.')
        t=now()
        if received>t+30 or received<t-86400: raise Problem('Receipt timestamp is outside the allowed window.')
        with self.db(True) as db:
            self.expire(db,t)
            previous=db.execute('SELECT outcome,tip_id FROM receipts WHERE reference=?',(ref,)).fetchone()
            if previous: return dict(previous)|{'duplicate':True}
            if db.execute('SELECT id FROM tips WHERE reference=?',(ref,)).fetchone(): return {'outcome':'duplicate_reference','duplicate':True}
            matches=rows(db.execute("SELECT * FROM tips WHERE status='PENDING' AND requested_paise=? AND created<=? AND expires>? AND expires>?",(amount,received,received,t)))
            tip=matches[0] if len(matches)==1 else None
            outcome='verified' if tip else ('ambiguous' if len(matches)>1 else 'unmatched')
            db.execute('INSERT INTO receipts VALUES (?,?,?,?,?,?)',(ref,amount,received,t,outcome,tip['id'] if tip else None))
            if tip:
                db.execute("UPDATE tips SET status='VERIFIED',actual_paise=?,verified=?,reference=?,verification_source=? WHERE id=?",(amount,received,ref,source,tip['id']))
                session=self.active(db)
                if session and tip['session_id']==session['id']: self.alert(db,tip)
            return {'outcome':outcome,'tip_id':tip['id'] if tip else None}
    def period(self,period,db,starts=None,ends=None):
        if period not in PERIODS: raise Problem('Unknown period.')
        dt=datetime.fromtimestamp(now(),IST); today=dt.replace(hour=0,minute=0,second=0,microsecond=0)
        end=None; start=None; session=None
        if period=='stream':
            active=self.active(db); session=active['id'] if active else '__no_active_session__'
        elif period=='today': start=today; end=start+timedelta(days=1)
        elif period=='yesterday': start=today-timedelta(days=1); end=today
        elif period in ['week','last_week']:
            start=today-timedelta(days=today.weekday()); end=start+timedelta(days=7)
            if period=='last_week': start-=timedelta(days=7); end-=timedelta(days=7)
        elif period in ['month','last_month']:
            start=today.replace(day=1); end=(start.replace(day=28)+timedelta(days=4)).replace(day=1)
            if period=='last_month': end=start; start=(start-timedelta(days=1)).replace(day=1)
        elif period=='year': start=today.replace(day=1,month=1); end=start.replace(year=start.year+1)
        elif period=='custom':
            if starts is None or ends is None or int(ends)<=int(starts): raise Problem('Custom range requires start < end.')
            return int(starts),int(ends),None
        return int(start.timestamp()) if start else None,int(end.timestamp()) if end else None,session
    def donations(self,db,period='lifetime',starts=None,ends=None,session_override=None):
        start,end,sid=self.period(period,db,starts,ends)
        if session_override: sid=session_override
        sql="SELECT t.* FROM tips t WHERE status IN ('VERIFIED','MANUAL')"; args=[]
        if start is not None: sql+=' AND verified>=?'; args.append(start)
        if end is not None: sql+=' AND verified<?'; args.append(end)
        if sid is not None: sql+=' AND session_id=?'; args.append(sid)
        return rows(db.execute(sql+' ORDER BY verified DESC',args))
    def summary(self,db,period='lifetime',starts=None,ends=None,session_override=None):
        tips=self.donations(db,period,starts,ends,session_override); grouped={}
        for t in tips:
            p=grouped.setdefault(t['supporter_id'],dict(id=t['supporter_id'],name=t['name'],total=0,count=0,largest=0,first=t['verified'],latest=t['verified']))
            p['total']+=t['display_paise']; p['count']+=1; p['largest']=max(p['largest'],t['display_paise']); p['first']=min(p['first'],t['verified'])
        ranked=sorted(grouped.values(),key=lambda p:(-p['total'],-p['count'],p['id']))
        total=sum(t['display_paise'] for t in tips)
        return dict(total=total,actual=sum(t['actual_paise'] or 0 for t in tips),count=len(tips),average=round(total/len(tips)) if tips else 0,highest=max([t['display_paise'] for t in tips],default=0),supporters=len(grouped),top=ranked[0] if ranked else None,frequent=max(ranked,key=lambda p:p['count']) if ranked else None,leaderboard=ranked)
    def goal_values(self,db):
        result=[]
        for g in rows(db.execute('SELECT * FROM goals ORDER BY rowid')):
            period=g['period'] if g['reset']=='automatic' else 'custom'
            start=g['starts']; end=g['ends']
            if g['reset']=='carry': start=start or 0; end=end or now()+1
            tips=self.donations(db,period,start,end,g['session_id'] if g['period']=='stream' and g['reset']=='carry' else None)
            tips=[t for t in tips if (start is None or t['verified']>=start) and (end is None or t['verified']<end)]
            total=sum(t['display_paise'] for t in tips)
            g['current']=g['starting']+total; g['percent']=min(100,round(g['current']/g['target']*100,2)); result.append(g)
        return result
    def backup(self):
        folder=self.path/'backups'; folder.mkdir(exist_ok=True)
        target=folder/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uid()+'.sqlite3')
        with self.db() as db,sqlite3.connect(target) as out: db.backup(out)
        return target
    # ---------- Sound library ----------
    # One row per uploaded sound (the soundboards table): `enabled` means viewers can pick it, `min_paise` is its price.
    # settings.default_sound is chime|pulse|none|video|<row id>; settings.sounds stays as a legacy mirror whose head is
    # the default's sound, for downgrades and pages left open across the upgrade.
    def media_ok(self,name): return isinstance(name,str) and re.fullmatch(STORED_SOUND,name) is not None and (self.path/'media'/name).is_file()
    def playable(self,name): return isinstance(name,str) and (name in BUILTIN_SOUNDS or self.media_ok(name))
    def video_audio_available(self,s):
        v=s.get('visuals') if isinstance(s.get('visuals'),dict) else {}; img=v.get('alert_image')
        return v.get('alert_video_has_audio') is True and isinstance(img,str) and re.fullmatch(r'[A-Za-z0-9_-]+\.webm',img) is not None and (self.path/'media'/img).is_file()
    def _mirror(self,db,value):
        if value in BUILTIN_SOUNDS: return value
        if value=='video': return 'none'  # the overlay plays the video element instead
        row=db.execute('SELECT media_filename FROM soundboards WHERE id=?',(value,)).fetchone() if isinstance(value,str) else None
        return row['media_filename'] if row and row['media_filename'] else 'chime'
    def _sync_mirror(self,db,value):
        head=self._mirror(db,value); s=self.settings(db); sounds=s['sounds'] if isinstance(s.get('sounds'),list) else []
        if sounds[:1]!=[head]: self._put_setting(db,'sounds',[head]+[x for x in sounds if x!=head])
    def resolve_default(self,db,s=None):
        """dict(value,kind,sound,item_id,name,problem) for the default sound. Never raises for any settings or row state;
        with a problem, alerts play Chime."""
        s=s if s is not None else self.settings(db); v=s.get('default_sound')
        base=dict(value=v,kind=None,sound='chime',item_id=None,name=None,problem=None)
        if not isinstance(v,str):  # no successful migration yet
            lst=s.get('sounds') if isinstance(s.get('sounds'),list) else []
            head=lst[0] if lst else 'chime'; ok=self.playable(head)
            return base|dict(value=head if ok else 'chime',kind='legacy',sound=head if ok else 'chime')
        if v in BUILTIN_SOUNDS: return base|dict(kind='builtin',sound=v,name={'chime':'Chime','pulse':'Pulse','none':'Silent'}[v])
        if v=='video':
            if self.video_audio_available(s): return base|dict(kind='video',sound='none',name='Alert video’s own sound')
            return base|dict(kind='video',name='Alert video’s own sound',problem='no_video_audio')
        row=db.execute('SELECT id,name,media_filename FROM soundboards WHERE id=?',(v,)).fetchone() if re.fullmatch(SOUND_ID,v) else None
        if not row or not row['media_filename']: return base|dict(kind='item',item_id=row and row['id'],name=row and row['name'],problem='missing_item')
        if not self.media_ok(row['media_filename']): return base|dict(kind='item',item_id=v,name=row['name'],problem='file_missing')
        return base|dict(kind='item',sound=row['media_filename'],item_id=v,name=row['name'])
    def put_default_sound(self,db,value,source):
        """The only writer of settings.default_sound (source: admin|upload|bundle|design_studio|delete|visuals)."""
        if value=='video' and not self.video_audio_available(self.settings(db)):
            raise Problem('Your alert visual has no sound of its own. Upload a video with sound as an alert bundle first.',409)
        if value!='video' and value not in BUILTIN_SOUNDS:
            if not isinstance(value,str) or not re.fullmatch(SOUND_ID,value): raise Problem('Choose Chime, Pulse, Silent, your alert video’s sound or one of your sounds.')
            row=db.execute('SELECT name,media_filename FROM soundboards WHERE id=?',(value,)).fetchone()
            if not row: raise Problem('That sound no longer exists.',404)
            if not row['media_filename']: raise Problem(f'Upload audio for “{row["name"]}” first.',409)
            if not self.media_ok(row['media_filename']): raise Problem(f'The audio file for “{row["name"]}” is missing. Replace its audio first.',409)
        old=self.settings(db).get('default_sound')
        self._put_setting(db,'default_sound',value); self._sync_mirror(db,value)
        if old!=value: self.audit(db,'default_sound_changed',value,{'from':old,'to':value,'source':source})
        return value
    def _insert_sound(self,db,*,name,emoji='',category='General',min_paise=0,enabled=True,media_filename=None,duration_ms=0,display_order=None,audit=True):
        """Add one library row inside the caller's transaction and return its id."""
        name=clean(name,80)
        if not name: raise Problem('Sound name is required.')
        emoji=clean(emoji,8)
        category=clean(category,40) or 'General'
        min_paise=int(min_paise or 0)
        if min_paise<0 or min_paise>10000000: raise Problem('Minimum tip must be between ₹0 and ₹100000.')
        if display_order is None: display_order=db.execute('SELECT COALESCE(MAX(display_order),0)+10 FROM soundboards').fetchone()[0]
        sb_id=uid()
        db.execute('INSERT INTO soundboards(id,name,emoji,category,min_paise,display_order,enabled,media_filename,duration_ms,created) VALUES (?,?,?,?,?,?,?,?,?,?)',
                   (sb_id,name,emoji,category,min_paise,int(display_order),int(bool(enabled)),media_filename,int(duration_ms or 0),now()))
        if audit: self.audit(db,'soundboard_created',sb_id,{'name':name,'category':category,'min_paise':min_paise})
        return sb_id
    def _set_sound_media(self,db,sb_id,media_filename,duration_ms=0):
        """Give a row a new audio file inside the caller's transaction. Settings that named the old file follow it (so
        the default's mirror stays right). Returns the old file name; pass it to _unlink_if_unused after commit."""
        r=db.execute('SELECT media_filename FROM soundboards WHERE id=?',(sb_id,)).fetchone()
        if not r: raise Problem('Soundboard entry not found.',404)
        prev=r['media_filename']
        db.execute('UPDATE soundboards SET media_filename=?,duration_ms=? WHERE id=?',(media_filename,int(duration_ms or 0),sb_id))
        if prev and prev!=media_filename and not db.execute('SELECT 1 FROM soundboards WHERE media_filename=?',(prev,)).fetchone():
            s=self.settings(db); sounds=s['sounds'] if isinstance(s.get('sounds'),list) else []
            if prev in sounds: self._put_setting(db,'sounds',[x for x in sounds if x!=prev] if media_filename in sounds else [media_filename if x==prev else x for x in sounds])
            if isinstance(s.get('visuals'),dict) and s['visuals'].get('alert_sound')==prev: self._put_setting(db,'visuals',dict(s['visuals'],alert_sound='viewer'))
            self.forget_upload(db,prev)
        if self.settings(db).get('default_sound')==sb_id: self._sync_mirror(db,sb_id)
        return prev
    def _delete_sound_row(self,db,sb_id):
        """Delete a row inside the caller's transaction. Returns (default_reset, file); unlink the file after commit."""
        r=db.execute('SELECT media_filename FROM soundboards WHERE id=?',(sb_id,)).fetchone()
        if not r: raise Problem('Soundboard entry not found.',404)
        db.execute('UPDATE tips SET soundboard_id=NULL WHERE soundboard_id=?',(sb_id,))  # FK integrity; those tips play the default
        db.execute('DELETE FROM soundboards WHERE id=?',(sb_id,))
        reset=self.settings(db).get('default_sound')==sb_id
        if reset: self.put_default_sound(db,'chime','delete')
        f=r['media_filename']
        if f and not db.execute('SELECT 1 FROM soundboards WHERE media_filename=?',(f,)).fetchone(): self._drop_file_refs(db,f)
        self.audit(db,'soundboard_deleted',sb_id)
        return reset,f
    def _drop_file_refs(self,db,name):
        """Forget a file that no row uses: settings.sounds (['chime'] if it empties), a 1.5.9 alert_sound and its upload metadata."""
        s=self.settings(db); sounds=s['sounds'] if isinstance(s.get('sounds'),list) else []
        if name in sounds: self._put_setting(db,'sounds',[x for x in sounds if x!=name] or ['chime'])
        if isinstance(s.get('visuals'),dict) and s['visuals'].get('alert_sound')==name: self._put_setting(db,'visuals',dict(s['visuals'],alert_sound='viewer'))
        self.forget_upload(db,name)
    def _media_in_use(self,name):
        with self.db() as db:
            if db.execute('SELECT 1 FROM soundboards WHERE media_filename=? LIMIT 1',(name,)).fetchone(): return True
            s=self.settings(db)
        v=s.get('visuals') if isinstance(s.get('visuals'),dict) else {}
        return (name in (s['sounds'] if isinstance(s.get('sounds'),list) else []) or name in [v.get(k) for k in ('alert_sound','alert_image','goal_image','logo')]
                or s.get('avatar')=='/media/'+name)
    def _unlink_if_unused(self,name):
        """After commit: delete a stored sound file that nothing references any more. Never raises."""
        if not isinstance(name,str) or not re.fullmatch(STORED_SOUND,name): return False
        try:
            if self._media_in_use(name): return False
            (self.path/'media'/name).unlink(missing_ok=True); return True
        except (OSError,sqlite3.Error): return False  # the change is committed; a leftover file is harmless
    def _migrate_sound_library(self):
        """1.6.0, once per database: sounds offered to viewers, other uploads and a fixed Design studio sound become library
        rows, and settings.default_sound is set. A named backup is written first; files are never touched. A failure rolls
        back, is logged to the console and is retried on the next start; the server starts either way."""
        log=logging.getLogger('acepressure.sounds')
        try:
            with self.db() as db:
                if db.execute("SELECT 1 FROM settings WHERE key='sound_library_migrated'").fetchone(): return
                s=self.settings(db); has_rows=db.execute('SELECT 1 FROM soundboards LIMIT 1').fetchone() is not None
            vis=s.get('visuals') if isinstance(s.get('visuals'),dict) else {}
            fixed=vis.get('alert_sound'); had_fixed=isinstance(fixed,str) and fixed!='viewer'
            legacy=(s.get('sounds')!=DEFAULTS['sounds'] or s.get('allow_sound_choice') is not True
                    or had_fixed or bool(known_uploads(s)) or has_rows)
            if legacy:
                target=self.path/'backups'/'before-1.6.0-sound-library.sqlite3'
                if not target.exists():  # a complete backup is never replaced
                    # Copied under a temporary name and renamed once complete: a crash or power cut mid-copy must never leave a
                    # half-written file under the real name, because that name is never written again.
                    tmp=target.with_name(target.name+'.partial'); junk=(tmp,tmp.with_name(tmp.name+'-journal')); copied=False
                    try:
                        target.parent.mkdir(exist_ok=True)
                        for f in junk: f.unlink(missing_ok=True)  # left by a crash during an earlier copy
                        src=sqlite3.connect(self.dbpath,timeout=20)
                        try:
                            out=sqlite3.connect(tmp)
                            try: src.backup(out)
                            finally: out.close()
                        finally: src.close()
                        copied=True
                        for attempt in range(10):  # both connections are closed; an antivirus or indexer may still hold the new file a moment on Windows
                            try: tmp.replace(target); break
                            except PermissionError:
                                if attempt==9: raise
                                time.sleep(0.2)
                    except Exception:
                        if copied: log.warning('Saved the backup as %s because it could not be renamed to %s; migrating.',tmp.name,target.name)  # complete: keep it
                        else:
                            for f in junk:
                                try: f.unlink(missing_ok=True)  # a half-written copy must not look like a good backup
                                except OSError: pass
                            log.warning('Could not write %s; migrating without it.',target.name)
            with self.db(True) as db:
                if db.execute("SELECT 1 FROM settings WHERE key='sound_library_migrated'").fetchone(): return  # lost a race
                s=self.settings(db); vis=s.get('visuals') if isinstance(s.get('visuals'),dict) else {}
                fixed=vis.get('alert_sound'); had_fixed=isinstance(fixed,str) and fixed!='viewer'
                sounds=[x for x in s['sounds'] if isinstance(x,str)] if isinstance(s.get('sounds'),list) else []
                labels=s.get('media_labels') if isinstance(s.get('media_labels'),dict) else {}
                allow=s.get('allow_sound_choice') is True
                live_board=db.execute('SELECT 1 FROM soundboards WHERE enabled=1 AND media_filename IS NOT NULL LIMIT 1').fetchone() is not None
                media=self.path/'media'
                cands=list(dict.fromkeys(sounds+([fixed] if had_fixed else [])+sorted(n for n in known_uploads(s) if (media/n).is_file())))
                owner,imported,linked,skipped,n={},0,0,0,0
                for f in cands:
                    if f in BUILTIN_SOUNDS or f=='viewer': continue
                    if not re.fullmatch(STORED_SOUND,f): skipped+=1; continue  # hand-typed text: never touch disk
                    row=db.execute('SELECT id FROM soundboards WHERE media_filename=? ORDER BY display_order,created LIMIT 1',(f,)).fetchone()
                    if row: owner[f]=row['id']; linked+=1; continue  # already a soundboard clip: no duplicate
                    name=display_label(labels.get(f))
                    if not name:
                        if f==fixed: name='Alert sound'
                        else: n+=1; name=f'Uploaded sound {n}'
                    owner[f]=self._insert_sound(db,name=name,min_paise=0,enabled=allow and f in sounds,media_filename=f,duration_ms=0,audit=False)  # imported even if the file is missing
                    imported+=1
                pick=lambda x: x if x in BUILTIN_SOUNDS else owner.get(x,'chime')
                if self.video_audio_available(s): default='video'  # 1.5.9 played the video's own sound for every alert
                elif had_fixed: default=pick(fixed)
                else: default=pick(sounds[0] if sounds else 'chime')
                db.execute("INSERT OR IGNORE INTO settings VALUES ('default_sound',?)",(json.dumps(default),))
                current=self.settings(db)['default_sound']; self._sync_mirror(db,current)
                if had_fixed: self._put_setting(db,'visuals',dict(vis,alert_sound='viewer'))  # every other visuals key kept, including the flag
                turned_on=not allow and live_board
                if turned_on: db.execute("UPDATE settings SET value='true' WHERE key='allow_sound_choice'")
                marker=dict(version=1,at=now(),had_fixed_sound=had_fixed,previous_alert_sound=fixed if had_fixed else None,
                            imported=imported,linked=linked,skipped=skipped,default=current,picks_turned_on=turned_on)
                db.execute("INSERT INTO settings VALUES ('sound_library_migrated',?)",(json.dumps(marker),))
                if legacy: self.audit(db,'sound_library_migrated',detail=marker)
        except Exception: log.exception('Sound library migration failed; it will be retried on the next start.')
    # ---------- Soundboard ----------
    # The sound library's rows; tippers pick one on the public page.
    # Each row owns a cached audio file under <DATA>/media/ (same folder as sounds/avatars).
    def soundboard_list(self,enabled_only=False):
        with self.db() as db:
            q='SELECT * FROM soundboards'+(' WHERE enabled=1' if enabled_only else '')+' ORDER BY display_order,created'
            return rows(db.execute(q))
    def soundboard_get(self,sb_id):
        with self.db() as db:
            r=db.execute('SELECT * FROM soundboards WHERE id=?',(sb_id,)).fetchone()
            return dict(r) if r else None
    def soundboard_create(self,name,emoji='',category='General',min_paise=5000,display_order=None,enabled=True):
        with self.db(True) as db: sb_id=self._insert_sound(db,name=name,emoji=emoji,category=category,min_paise=min_paise,display_order=display_order,enabled=enabled)
        return self.soundboard_get(sb_id)
    def soundboard_update(self,sb_id,**fields):
        allowed={'name','emoji','category','min_paise','display_order','enabled','volume'}
        bad=set(fields)-allowed
        if bad: raise Problem(f'Unknown field(s): {sorted(bad)}')
        if 'name' in fields:
            fields['name']=clean(fields['name'],80)
            if not fields['name']: raise Problem('Sound name is required.')
        if 'emoji' in fields: fields['emoji']=clean(fields['emoji'],8)
        if 'category' in fields: fields['category']=clean(fields['category'],40) or 'General'
        if 'min_paise' in fields:
            fields['min_paise']=int(fields['min_paise'] or 0)
            if fields['min_paise']<0 or fields['min_paise']>10000000: raise Problem('Minimum tip must be between ₹0 and ₹100000.')
        if 'display_order' in fields: fields['display_order']=int(fields['display_order'])
        if 'enabled' in fields: fields['enabled']=int(bool(fields['enabled']))
        if 'volume' in fields:
            v=fields['volume']
            if isinstance(v,bool) or not isinstance(v,(int,float)) or not 10<=v<=100 or v!=int(v): raise Problem('Volume must be a whole number from 10 to 100.')  # range first: NaN and Infinity fail it
            fields['volume']=int(v)
        if not fields: return self.soundboard_get(sb_id)
        with self.db(True) as db:
            if not db.execute('SELECT id FROM soundboards WHERE id=?',(sb_id,)).fetchone(): raise Problem('Soundboard entry not found.',404)
            sets=', '.join(k+'=?' for k in fields)
            db.execute('UPDATE soundboards SET '+sets+' WHERE id=?',[*fields.values(),sb_id])
            self.audit(db,'soundboard_updated',sb_id,{'fields':list(fields)})
        return self.soundboard_get(sb_id)
    def soundboard_set_media(self,sb_id,media_filename,duration_ms=0):
        with self.db(True) as db:
            prev=self._set_sound_media(db,sb_id,media_filename,duration_ms)
            self.audit(db,'soundboard_media_set',sb_id,{'filename':media_filename})
        if prev and prev!=media_filename: self._unlink_if_unused(prev)  # only after commit, and only when nothing uses it
        return self.soundboard_get(sb_id)
    def soundboard_delete(self,sb_id):
        """Returns True when the deleted row was the default sound (the default went back to Chime)."""
        with self.db(True) as db: reset,f=self._delete_sound_row(db,sb_id)
        self._unlink_if_unused(f)
        return reset
    def soundboard_reorder(self,order_map):
        """Apply a {id: display_order} map atomically."""
        if not isinstance(order_map,dict) or not order_map: raise Problem('Provide {id: order} to reorder.')
        with self.db(True) as db:
            for sb_id,order in order_map.items():
                if not isinstance(sb_id,str) or not isinstance(order,int):
                    raise Problem('Each entry must be {id: integer_order}.')
                db.execute('UPDATE soundboards SET display_order=? WHERE id=?',(order,sb_id))
            self.audit(db,'soundboard_reordered',detail={'count':len(order_map)})
    def soundboard_seed(self):
        """Populate the library with 22 starter entries: 14 well-known Indian meme slots and the 8 sound effects whose
        bundled audio seed_starter_audio adds (STARTER_AUDIO). Each entry starts with NO audio file and switched off; its
        first clip (an upload, or the bundled one) switches it on. Idempotent: re-running skips entries whose name already exists."""
        starter=[
            ('Thug Life','😎','Reactions',5000),
            ('Chai Peelo','🍵','Hindi Memes',5000),
            ('Babu Bhaiya','😱','Hindi Memes',5000),
            ('440 Volt Ka Jhatka','⚡','Hindi Memes',5000),
            ('Rasode Mein Kaun Tha','🍳','Hindi Memes',10000),
            ('Pawri Ho Rahi Hai','🎉','Hindi Memes',5000),
            ('Binod','🙃','Hindi Memes',2000),
            ('Beta Tumse Na Ho Payega','🙅','Hindi Memes',5000),
            ('Papa Kehte Hain','🎸','Hindi Memes',5000),
            ('Ye Chemical Hai','🧪','Hindi Memes',5000),
            ('Dhoondho Dhoondho','📱','Hindi Memes',5000),
            ('Mauka Mauka','🏏','Sports',5000),
            ('Hum Honge Kaamyab','🇮🇳','Patriotic',5000),
            ('Hera Pheri Laughter','😂','Hindi Memes',10000),
            ('Vine Boom','💥','SFX',2000),
            ('Air Horn','📯','SFX',2000),
            ('Cash Register','💰','SFX',2000),
            ('Victory Fanfare','🏆','SFX',5000),
            ('Clap','👏','Reactions',2000),
            ('Game Over','🎮','SFX',5000),
            ('Ba Dum Tss','🥁','SFX',2000),
            ('Sad Trombone','🎺','SFX',2000),
        ]
        created=[]
        with self.db() as db:
            existing={r['name'] for r in db.execute('SELECT name FROM soundboards')}
        for i,(name,emoji,category,min_paise) in enumerate(starter):
            if name in existing: continue
            self.soundboard_create(name=name,emoji=emoji,category=category,min_paise=min_paise,display_order=100+i*10,enabled=False)
            created.append(name)
        return created
    def seed_starter_audio(self):
        """Give each empty row named in STARTER_AUDIO its bundled clip, like an owner's first upload to that slot: a copy
        under a random name in data/media (the bundled original is never linked or moved), the row switched on and labelled
        '<Name>.mp3'. A row that already has audio is skipped (the owner's clip wins, even if its file is missing), and a
        sound that fails is logged and skipped without stopping the rest. Only the seed button calls this; it never changes
        the default sound or the picks switch. Returns the names that got audio in this call."""
        from .video import validate_or_fix_audio  # video imports domain
        log=logging.getLogger('acepressure.sounds'); media=self.path/'media'; ready=[]
        def slot(db,name):  # the first row with exactly this name, unless there is none or any of them already has audio
            found=db.execute('SELECT id,media_filename FROM soundboards WHERE name=? ORDER BY display_order,created',(name,)).fetchall()
            return found[0]['id'] if found and not any(r['media_filename'] for r in found) else None
        for name,file in STARTER_AUDIO.items():
            with self.db() as db:
                if not slot(db,name): continue
            stored=sid=prev=None
            try:
                content,ext,duration_ms,auto_fixed=validate_or_fix_audio((STARTER_DIR/file).read_bytes(),max_duration_ms=SOUND_MAX_MS)
                media.mkdir(exist_ok=True); stored=uid()+'.'+ext; (media/stored).write_bytes(content)
                with self.db(True) as db:
                    sid=slot(db,name)  # again under the write lock: a second click may have filled it meanwhile
                    if sid:
                        prev=self._set_sound_media(db,sid,stored,duration_ms)
                        db.execute('UPDATE soundboards SET enabled=1 WHERE id=?',(sid,))  # a slot's first clip makes it pickable
                        self.remember_upload(db,stored,name+'.mp3',auto_fixed)
                        self.audit(db,'starter_sound_added',sid,{'name':name,'filename':stored})
            except Exception as e:
                sid=None; log.warning('Starter sound %s was skipped: %s',name,getattr(e,'message',None) or f'{type(e).__name__}: {e}')
            if not sid:  # failed, or filled meanwhile: the copy goes
                if stored:
                    try: (media/stored).unlink(missing_ok=True)
                    except OSError: pass
                continue
            if prev: self._unlink_if_unused(prev)
            ready.append(name)
        return ready
