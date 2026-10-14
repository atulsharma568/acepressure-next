"""Fail-closed bank adapters. No permissive catch-all amount regex."""
import re
from .domain import Problem

def parse_receipt(data, settings, demo=False):
    if not settings['bridge_enabled'] and not demo: raise Problem('Verification bridge is disabled.',503)
    if demo and data.get('sender')=='DEMO-BANK': return fields(data)
    if not settings['bank_sender'] or data.get('sender')!=settings['bank_sender']: raise Problem('Sender rejected.',422)
    if settings['parser']=='structured-v1': return fields(data)
    # Add a bank-specific parser here only after testing real redacted credit/debit samples.
    if settings['parser']=='example-credit-v1':
        text=data.get('sms','')
        m=re.fullmatch(r'Credit INR (?P<amount>\d+\.\d{2}) via UPI Ref (?P<reference>[A-Z0-9]{6,30})',text)
        if not m: raise Problem('SMS did not match configured CREDIT format.',422)
        return {**m.groupdict(),'received_at':data.get('received_at')}
    raise Problem('A tested bank parser is required.',422)

def fields(data):
    if data.get('direction')!='credit': raise Problem('Only credit receipts are accepted.',422)
    if any(k not in data for k in ['amount','received_at','reference']): raise Problem('Incomplete receipt.',422)
    return {k:data[k] for k in ['amount','received_at','reference']}
