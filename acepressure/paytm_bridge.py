"""Persistent authenticated notification bridge; evidence is not bank-signed."""
import hashlib,hmac,json,secrets,re
from flask import request,render_template
from .domain import Problem,now,rows,clean
from .paytm_match import parse_event
from .readiness import readiness

def ingest(store,text,clock,demo=False):
    event=parse_event(text,clock)
    identity=event['identity'] if event else 'unsupported|'+' '.join(text.split())
    fingerprint=hmac.new(store.secret.encode(),identity.encode(),hashlib.sha256).hexdigest()
    with store.db(True) as db:
        old=db.execute('SELECT * FROM paytm_inbox WHERE fingerprint=?',(fingerprint,)).fetchone()
        if old:
            db.execute('UPDATE paytm_inbox SET repeats=repeats+1 WHERE id=?',(old['id'],))
            return {'outcome':'duplicate_notification','id':old['id'],'alert_created':False,'bank_verified':False}
        config=db.execute('SELECT * FROM paytm_bridge WHERE id=1').fetchone()
        store.expire(db,clock)
        candidates=[];tip=None;reason='unsupported_format';status='REVIEW';alert=False
        recipient_ok=not config['recipient_hash'] or (event and hmac.compare_digest(hmac.new(store.secret.encode(),event['recipient'].encode(),hashlib.sha256).hexdigest(),config['recipient_hash']))
        if event and not recipient_ok:reason='recipient_mismatch'
        if event and recipient_ok:
            # Include expired tips for human reconciliation. Never auto-approve them.
            candidates=rows(db.execute("SELECT * FROM tips WHERE requested_paise=? AND created>=? AND status IN ('PENDING','EXPIRED') ORDER BY created DESC",(event['amount'],clock-86400)))
            timely=[t for t in candidates if event['minute']+59>=t['created'] and event['minute']<t['expires']]
            if len(timely)==1:tip=timely[0]
            elif not timely and len(candidates)==1:tip=candidates[0]
            reason='unmatched_amount' if not candidates else 'ambiguous_match'
            if tip:
                stamp=event['minute'];active=store.active(db)
                if stamp>clock or clock-stamp>600:reason='delayed_or_future_notification'
                elif tip['status']!='PENDING' or tip['expires']<=clock:reason='expired_tip'
                elif stamp<tip['created'] or stamp+60>tip['expires']:reason='minute_precision_review'
                elif not active or active['id']!=tip['session_id']:reason='inactive_session'
                elif db.execute('SELECT blocked FROM supporters WHERE id=?',(tip['supporter_id'],)).fetchone()[0]:reason='blocked_supporter'
                elif not config['auto_match']:reason='manual_review_mode'
                else:
                    status='MATCHED';reason='notification_match'
                    source='demo-paytm-notification' if demo else 'paytm-notification'
                    db.execute("UPDATE tips SET status='VERIFIED',actual_paise=?,verified=?,verification_source=?,note='Notification evidence only; no bank transaction reference' WHERE id=?",(event['amount'],stamp,source,tip['id']))
                    tip['verification_source']=source;store.alert(db,tip,test=demo);alert=True
        ids=[t['id'] for t in candidates]
        cur=db.execute('INSERT INTO paytm_inbox(fingerprint,received,payment_minute,amount,status,reason,tip_id,candidates) VALUES(?,?,?,?,?,?,?,?)',(fingerprint,clock,event['minute'] if event else None,event['amount'] if event else None,status,reason,tip['id'] if tip else None,json.dumps(ids)))
        db.execute('UPDATE paytm_bridge SET last_seen=? WHERE id=1',(clock,))
        store.audit(db,'paytm_'+status.lower(),str(cur.lastrowid),{'reason':reason,'tip_id':tip['id'] if tip else None})
        return {'id':cur.lastrowid,'outcome':reason,'status':status,'alert_created':alert,'bank_verified':False}

def register_bridge(app,store,admin,client_ip):
    @app.get('/admin/paytm')
    def bridge_page():
        admin();return render_template('paytm_bridge.html')

    @app.get('/api/admin/paytm')
    def bridge_state():
        with store.db() as db:
            c=dict(db.execute('SELECT * FROM paytm_bridge WHERE id=1').fetchone());c['has_token']=bool(c.pop('token_hash'));c['has_recipient']=bool(c.pop('recipient_hash'))
            inbox=rows(db.execute('SELECT id,received,payment_minute,amount,status,reason,tip_id,candidates,repeats FROM paytm_inbox ORDER BY id DESC LIMIT 100'))
            pending=rows(db.execute("SELECT id,name,requested_paise,status,created,session_id,message,tts FROM tips WHERE status IN ('PENDING','EXPIRED') AND created>=? ORDER BY created DESC LIMIT 300",(now()-86400,)))
            s=store.settings(db)
            for t in pending:t['message']=store.on_stream(t['message'],s);t['tts']=bool(t['tts'])  # 1.6.4: read it before you approve, as it will look on stream
            active=store.active(db);health=readiness(store,db,app.config)
        return {'config':c,'inbox':inbox,'pending':pending,'demo':app.config['DEMO_MODE'],'public_base_url':app.config['PUBLIC_BASE_URL'],'active_session_id':active['id'] if active else None,'health':health}

    @app.post('/api/admin/paytm/config')
    def bridge_config():
        d=request.get_json(silent=True)
        if not isinstance(d,dict):raise Problem('Expected settings.')
        action=d.get('action')
        with store.db(True) as db:
            if action=='rotate':
                token=secrets.token_urlsafe(48)
                db.execute('UPDATE paytm_bridge SET token_hash=?,enabled=0 WHERE id=1',(hashlib.sha256(token.encode()).hexdigest(),))
                store.audit(db,'rotate_paytm_token');return {'token':token,'enabled':False}
            if action=='disable':
                db.execute('UPDATE paytm_bridge SET enabled=0 WHERE id=1');store.audit(db,'disable_paytm');return {'ok':True}
            if action!='enable':raise Problem('Unknown action.')
            c=db.execute('SELECT * FROM paytm_bridge WHERE id=1').fetchone();s=store.settings(db)
            if not c['token_hash']:raise Problem('Generate the bridge token first.')
            recipient=d.get('recipient','')
            if not isinstance(recipient,str) or len(recipient)>150:raise Problem('Invalid recipient marker.')
            if recipient.strip():
                m=re.fullmatch(r'(.+?)\s*-\s*([0-9]{4})',recipient.strip())
                if not m:raise Problem('Enter bank name - last four digits exactly as Paytm shows it.')
                canonical=' '.join(m[1].split()).casefold()+'|'+m[2]
                db.execute('UPDATE paytm_bridge SET recipient_hash=? WHERE id=1',(hmac.new(store.secret.encode(),canonical.encode(),hashlib.sha256).hexdigest(),))
            if not app.config['DEMO_MODE']:
                if not recipient.strip() and not c['recipient_hash']:raise Problem('Configure the receiving bank marker first.')
                if not s['upi_id'] or not s['payee_name']:raise Problem('Set your UPI ID and payee name in Settings first.')
                if not app.config['PUBLIC_BASE_URL'].startswith('https://'):raise Problem('This server is still using PUBLIC_BASE_URL='+app.config['PUBLIC_BASE_URL']+'. Run Setup_Tailscale_URL.bat, then close the AcePressure window and run Start.bat again.')
            auto=d.get('auto_match',False)
            if not isinstance(auto,bool):raise Problem('Invalid auto_match.')
            if auto and d.get('acknowledge_notification_risk') is not True:raise Problem('Acknowledge notification-only matching before enabling automatic matches.')
            db.execute('UPDATE paytm_bridge SET enabled=1,auto_match=? WHERE id=1',(int(auto),));store.audit(db,'enable_paytm',detail={'auto_match':auto})
        return {'ok':True}

    @app.post('/api/bridge/paytm')
    def bridge_receive():
        token=request.headers.get('Authorization','').removeprefix('Bearer ')
        with store.db() as db:c=db.execute('SELECT * FROM paytm_bridge WHERE id=1').fetchone()
        # Token first: junk posts get their own per-address bucket and can never use up the phone's.
        if not c['enabled'] or not c['token_hash'] or not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(),c['token_hash']):store.rate('paytm-bad:'+client_ip(),30,60);raise Problem('Paytm bridge disabled or token rejected.',401)
        store.rate('paytm-auth',120,60)
        request.max_content_length=4096
        d=request.get_json(silent=True)
        if not isinstance(d,dict) or set(d)-{'text','notification_date'} or not isinstance(d.get('text'),str) or not 1<=len(d['text'])<=3000:raise Problem('Expected notification text only (1-3000 characters).')
        return ingest(store,d['text'],now(),app.config['DEMO_MODE'])

    @app.post('/api/admin/paytm/review/<int:rid>')
    def bridge_review(rid):
        d=request.get_json(silent=True) or {};reason=clean(d.get('reason'),300)
        if len(reason)<5:raise Problem('Give an audit reason of at least five characters.')
        with store.db(True) as db:
            r=db.execute('SELECT * FROM paytm_inbox WHERE id=?',(rid,)).fetchone()
            if not r or r['status']!='REVIEW':raise Problem('This item is not awaiting review.',409)
            if d.get('action')=='ignore':
                db.execute("UPDATE paytm_inbox SET status='IGNORED',reason=? WHERE id=?",(reason,rid));store.audit(db,'ignore_paytm',str(rid),{'reason':reason});return {'ok':True}
            if d.get('action')!='approve' or d.get('checked_bank') is not True:raise Problem('Check the payment in your own Paytm/bank history before approving.')
            tip=db.execute('SELECT * FROM tips WHERE id=?',(d.get('tip_id'),)).fetchone()
            if not tip or tip['status'] not in ['PENDING','EXPIRED']:raise Problem('Select an unpaid pending or expired tip.',409)
            tip=dict(tip)
            if r['reason']=='recipient_mismatch':raise Problem('This notification is for a different configured recipient. Ignore it and investigate separately.')
            if r['amount'] is None or r['amount']!=tip['requested_paise']:raise Problem('The received amount must match the requested amount.')
            if db.execute('SELECT blocked FROM supporters WHERE id=?',(tip['supporter_id'],)).fetchone()[0]:raise Problem('Supporter is blocked. Review the block separately.')
            stamp=r['payment_minute'] or now()
            if stamp>now():raise Problem('Payment timestamp is in the future.')
            source='demo-paytm-notification' if app.config['DEMO_MODE'] else 'manual-paytm-review'
            db.execute("UPDATE tips SET status='MANUAL',actual_paise=?,verified=?,verification_source=?,note=? WHERE id=?",(r['amount'],stamp,source,reason,tip['id']))
            db.execute("UPDATE paytm_inbox SET status='APPROVED',tip_id=?,reason=? WHERE id=?",(tip['id'],reason,rid))
            active=store.active(db);alert=False
            if d.get('alert') is True and active and active['id']==tip['session_id']:
                tip['verification_source']=source;store.alert(db,tip,test=app.config['DEMO_MODE']);alert=True
            store.audit(db,'approve_paytm',str(rid),{'reason':reason,'tip_id':tip['id'],'alert':alert,'evidence':'admin_checked'})
        return {'ok':True,'alert_created':alert}
