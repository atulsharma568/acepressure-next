"""Opt-in demo diagnostics, with separately enabled demo matching."""
import hmac
import re
import secrets
import threading
from flask import request, render_template
from .domain import Problem, money, now, rows
from .paytm_match import process_event


def parse_amount(text):
    # Observed Paytm notification wording. Do not infer a credit from arbitrary amounts.
    match = re.fullmatch(
        r'Received\s+₹\s*((?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]{1,2})?)'
        r'\s+from\s+[^\r\n]+[\r\n\s]+Deposited in your\s+[^\r\n]+(?:[\r\n][^\r\n]+)*',
        text.strip())
    if not match:
        return None
    amount = money(match[1].replace(',', ''))
    return amount if amount > 0 else None


def register_capture(app, store, admin):
    lock = threading.Lock()
    state = {'token': '', 'until': 0, 'matching':False}

    def demo_only():
        if not app.config['DEMO_MODE']:
            raise Problem('Paytm diagnostics are available only in demo mode.', 404)

    @app.get('/admin/paytm-test')
    def capture_page():
        admin()
        demo_only()
        return render_template('paytm_test.html')

    @app.post('/api/admin/paytm-test/start')
    def capture_start():
        demo_only()
        d=request.get_json(silent=True) or {}
        if not isinstance(d,dict) or not isinstance(d.get('matching',False),bool):
            raise Problem('matching must be true or false.')
        with lock:
            state.update(token=secrets.token_urlsafe(32), until=now()+1800,matching=d.get('matching',False))
            return {'token': state['token'], 'expires': state['until']}

    @app.post('/api/admin/paytm-test/stop')
    def capture_stop():
        demo_only()
        with lock:
            state.update(token='', until=0,matching=False)
        return {'ok': True}

    @app.get('/api/admin/paytm-test')
    def capture_list():
        demo_only()
        with store.db(True) as db:
            db.execute('DELETE FROM paytm_captures WHERE captured_at<?', (now()-7*86400,))
            result = rows(db.execute('SELECT id,captured_at,amount_paise,outcome,repeats FROM paytm_captures ORDER BY id DESC LIMIT 100'))
        with lock:
            active = state['until'] > now()
            matching=state['matching']
        return {'active': active, 'matching':matching, 'captures': result}

    @app.post('/api/bridge/paytm-test')
    def capture_notification():
        demo_only()
        store.rate('paytm-test-ip:'+str(request.remote_addr), 60, 60)
        with lock:
            token = state['token']
            active = state['until'] > now()
            matching=state['matching']
        supplied = request.headers.get('Authorization', '').removeprefix('Bearer ')
        if not active or not token or not hmac.compare_digest(supplied, token):
            raise Problem('Test capture inactive or token rejected.', 401)
        store.rate('paytm-test-global', 120, 60)
        request.max_content_length = 4096
        d = request.get_json(silent=True)
        if not isinstance(d, dict) or set(d) - {'text', 'notification_date'}:
            raise Problem('Send text and optional notification_date only.')
        text = d.get('text')
        date = d.get('notification_date', '')
        if not isinstance(text, str) or not text.strip() or len(text)>3000:
            raise Problem('Notification text must contain 1-3000 characters.')
        if not isinstance(date, str) or len(date)>100:
            raise Problem('Invalid notification_date.')
        amount = parse_amount(text)
        outcome = 'credit_text_detected' if amount is not None else 'unrecognized_text'
        # The matcher fingerprints normalized evidence, not a bank reference.
        # Raw text is discarded; client notification_date never changes identity.
        with store.db(True) as db:
            result,fingerprint=process_event(store,db,text,now(),matching)
            if matching or result['duplicate_input']:outcome=result['outcome']
            previous = db.execute('SELECT id FROM paytm_captures WHERE fingerprint=?', (fingerprint,)).fetchone()
            if previous:
                db.execute('UPDATE paytm_captures SET repeats=repeats+1 WHERE id=?', (previous['id'],))
            else:
                db.execute('INSERT INTO paytm_captures(fingerprint,captured_at,amount_paise,outcome) VALUES(?,?,?,?)', (fingerprint,now(),amount,outcome))
            db.execute('DELETE FROM paytm_captures WHERE captured_at<? OR id NOT IN (SELECT id FROM paytm_captures ORDER BY id DESC LIMIT 500)', (now()-7*86400,))
        return result|{'mode':'demo_matching' if matching else 'capture_only', 'verified':False,
                       'amount_paise':amount,'outcome':outcome}
