"""Conservative notification matching for the demo database only."""
import hashlib, hmac, re
from datetime import datetime
from .domain import IST, money

MONTHS={m:i+1 for i,m in enumerate(['January','February','March','April','May','June','July','August','September','October','November','December'])}
# Paytm groups thousands the Indian way (₹1,000.37, ₹10,000.05, ₹1,00,000); any other grouping is not parsed.
AMOUNT=r'(?:[0-9]{1,3}(?:,[0-9]{2})*,[0-9]{3}|[0-9]+)(?:\.[0-9]{1,2})?'
PATTERN=re.compile(r'Received ₹\s*(?P<amount>'+AMOUNT+r') from (?P<sender>.+?) Deposited in your (?P<bank>.+?) - (?P<suffix>[0-9]{4}) on (?P<day>[0-9]{1,2}) (?P<month>[A-Za-z]+) at (?P<hour>[0-9]{1,2}):(?P<minute>[0-9]{2}) (?P<ampm>AM|PM)')

def parse_event(text, clock):
    normalized=' '.join(text.split())
    match=PATTERN.fullmatch(normalized)
    if not match:return None
    d=match.groupdict()
    if d['month'] not in MONTHS or not 1<=int(d['hour'])<=12 or int(d['minute'])>59:return None
    hour=int(d['hour'])%12+(12 if d['ampm']=='PM' else 0)
    dates=[]
    for year in range(datetime.fromtimestamp(clock,IST).year-1,datetime.fromtimestamp(clock,IST).year+2):
        try:dates.append(int(datetime(year,MONTHS[d['month']],int(d['day']),hour,int(d['minute']),tzinfo=IST).timestamp()))
        except ValueError:pass
    if not dates:return None
    minute=min(dates,key=lambda x:abs(x-clock))
    amount=money(d['amount'].replace(',',''))
    if amount<=0:return None
    # Ignore optional client-supplied dates. A retry must not gain a new identity.
    identity='|'.join([str(amount),d['sender'].casefold(),d['bank'].casefold(),d['suffix'],str(minute)])
    return {'amount':amount,'minute':minute,'identity':identity,'recipient':d['bank'].casefold()+'|'+d['suffix']}

def process_event(store,db,text,clock,matching):
    event=parse_event(text,clock)
    identity=event['identity'] if event else 'unsupported|'+' '.join(text.split())
    fingerprint=hmac.new(store.secret.encode(),identity.encode(),hashlib.sha256).hexdigest()
    previous=db.execute('SELECT * FROM paytm_events WHERE fingerprint=?',(fingerprint,)).fetchone()
    if previous:
        db.execute('UPDATE paytm_events SET repeats=repeats+1 WHERE fingerprint=?',(fingerprint,))
        return {'outcome':'duplicate_notification','tip_id':previous['tip_id'],'duplicate_input':True,'alert_created':False},fingerprint
    outcome='capture_only';tid=None;alert=False
    if matching:
        outcome='unsupported_payment_format'
        if event:
            stamp=event['minute']
            if stamp>clock or clock-stamp>600:outcome='stale_or_future_notification'
            else:
                store.expire(db,clock)
                candidates=db.execute("SELECT * FROM tips WHERE status='PENDING' AND requested_paise=? AND expires>?",(event['amount'],clock)).fetchall()
                outcome='unmatched_amount'
                if len(candidates)>1:outcome='ambiguous_amount'
                elif len(candidates)==1:
                    tip=dict(candidates[0]);active=store.active(db)
                    if stamp<tip['created']:
                        outcome='payment_time_before_or_ambiguous'
                    elif stamp+60>tip['expires']:outcome='payment_time_near_expiry'
                    elif not active or active['id']!=tip['session_id']:outcome='inactive_stream_session'
                    elif db.execute('SELECT blocked FROM supporters WHERE id=?',(tip['supporter_id'],)).fetchone()[0]:outcome='blocked_supporter'
                    else:
                        tid=tip['id'];outcome='demo_matched'
                        db.execute("UPDATE tips SET status='VERIFIED',actual_paise=?,verified=?,verification_source='demo-paytm-notification',note='DEMO notification match; no bank reference; not bank verification' WHERE id=?",(event['amount'],stamp,tid))
                        # Tests are labelled test=true and never presented as real receipts.
                        tip['verification_source']='demo-paytm-notification'
                        store.alert(db,tip,test=True);alert=True
                        store.audit(db,'demo_paytm_match',tid,{'evidence':'notification_only','amount_paise':event['amount']})
    db.execute('INSERT INTO paytm_events(fingerprint,ingested,amount_paise,outcome,tip_id) VALUES(?,?,?,?,?)',(fingerprint,clock,event['amount'] if event else None,outcome,tid))
    return {'outcome':outcome,'tip_id':tid,'duplicate_input':False,'alert_created':alert},fingerprint
