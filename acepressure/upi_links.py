"""UPI payment links: the standard upi:// link for the QR, plus one link per payment app.

On iPhone, opening an app with only `gpay://`, `phonepe://` or `paytmmp://` in front of the
standard query lands on the app's home screen for PhonePe and Paytm: they read the amount
only from their own link formats. Values are encoded with %20 (never +) because some apps
show a + literally. App links leave out `tr`/`mc`, which mark a merchant payment, since the
payee is a personal UPI ID. The app formats are not public vendor contracts: test them on a
real phone after any app update, and keep the QR and copy controls as the fallback.
"""
import base64, json
from urllib.parse import quote, urlencode


def _query(params):
    return urlencode(params, quote_via=quote)


def standard(upi_id, payee, paise, note, reference):
    return 'upi://pay?'+_query(dict(pa=upi_id, pn=payee, am=f'{paise/100:.2f}', cu='INR', tn=note, tr=reference))


def app_links(upi_id, payee, paise, note):
    amount=f'{paise/100:.2f}'
    personal=_query(dict(pa=upi_id, pn=payee, am=amount, cu='INR', tn=note))
    # PhonePe reads a base64 JSON payload; initialAmount is in paise.
    phonepe=json.dumps({'p2pPaymentCheckoutParams': {'checkoutType': 'COLLECT', 'initialAmount': paise,
                                                     'note': {'type': 'text', 'message': note}, 'supportedInstruments': -1},
                        'contact': {'type': 'EXTERNAL_MERCHANT', 'name': payee, 'vpa': upi_id}}, separators=(',', ':'))
    return [
        {'app': 'gpay', 'name': 'Google Pay', 'href': 'gpay://upi/pay?'+personal},
        {'app': 'phonepe', 'name': 'PhonePe', 'href': 'phonepe://native?'+_query(dict(data=base64.b64encode(phonepe.encode()).decode(), id='p2ppayment'))},
        {'app': 'paytm', 'name': 'Paytm', 'href': 'paytmmp://cash_wallet?'+personal+'&featuretype=money_transfer'},
        {'app': 'upi', 'name': 'Other UPI app', 'href': 'upi://pay?'+personal},
    ]
