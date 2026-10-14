"""1.6.8: comma amounts in Paytm notifications, and UPI app links that carry the amount."""
import base64, json
from datetime import datetime
from urllib.parse import parse_qs, urlsplit
import pytest
from acepressure.domain import now, IST
from acepressure.paytm_bridge import ingest
from acepressure.paytm_capture import parse_amount
from acepressure.paytm_match import parse_event
from acepressure import upi_links
from test_paytm_bridge import enable

LINE='Received ₹{} from Test Sender Deposited in your Example Bank - 0000 on 10 October at 11:00 AM'


@pytest.mark.parametrize('shown,paise', [('20.76', 2076), ('1,000.37', 100037), ('10,000.05', 1000005), ('1,00,000', 10000000), ('999', 99900)])
def test_paytm_amounts_with_indian_grouping(shown, paise):
    assert parse_event(LINE.format(shown), now())['amount'] == paise
    assert parse_amount(LINE.format(shown)) == paise


@pytest.mark.parametrize('shown', ['1,0000.37', '1,00.37', ',100.37', '1,000.375', '1,000,000'])
def test_paytm_amounts_with_odd_grouping_are_not_parsed(shown):
    assert parse_event(LINE.format(shown), now()) is None


def test_thousand_rupee_tip_matches_automatically(app, admin):
    enable(admin, True)
    stamp=now()//60*60; clock=stamp+30
    with app.store.db(True) as db: db.execute('INSERT INTO sessions VALUES(?,?,?,NULL)', ('s', 'test', stamp-120))
    tip=app.store.create_tip({'name': 'Big fan', 'amount': 1500}, True)
    with app.store.db(True) as db: db.execute('UPDATE tips SET created=?,expires=? WHERE id=?', (stamp-60, stamp+600, tip['id']))
    dt=datetime.fromtimestamp(stamp, IST); rupees, paise=divmod(tip['requested_paise'], 100)
    text=f"Received ₹{rupees//1000},{rupees%1000:03d}.{paise:02d} from Test Sender Deposited in your Example Bank - 0000 on {dt.day} {dt.strftime('%B')} at {dt.strftime('%I:%M %p')}"
    r=ingest(app.store, text, clock, True)
    assert r['outcome'] == 'notification_match' and r['alert_created']


def test_app_links_carry_the_exact_amount():
    links={a['app']: a for a in upi_links.app_links('ace.pressure@ptyes', 'Ace Pressure', 2076, 'AcePressure T1')}
    assert list(links) == ['gpay', 'phonepe', 'paytm', 'upi']
    for app in ['gpay', 'paytm', 'upi']:
        href=links[app]['href']; q=parse_qs(urlsplit(href).query)
        assert q['am'] == ['20.76'] and q['pa'] == ['ace.pressure@ptyes'] and q['pn'] == ['Ace Pressure'] and q['cu'] == ['INR']
        assert '+' not in href and 'tr' not in q and 'mc' not in q
    assert links['gpay']['href'].startswith('gpay://upi/pay?')
    assert links['paytm']['href'].startswith('paytmmp://cash_wallet?') and parse_qs(urlsplit(links['paytm']['href']).query)['featuretype'] == ['money_transfer']
    phonepe=urlsplit(links['phonepe']['href']); q=parse_qs(phonepe.query)
    assert links['phonepe']['href'].startswith('phonepe://native?') and q['id'] == ['p2ppayment']
    payload=json.loads(base64.b64decode(q['data'][0]))
    assert payload['p2pPaymentCheckoutParams']['initialAmount'] == 2076 and payload['contact']['vpa'] == 'ace.pressure@ptyes'


def test_standard_link_keeps_reference_and_uses_percent_spaces():
    uri=upi_links.standard('ace.pressure@ptyes', 'Ace Pressure', 2076, 'AcePressure T1', 'T1')
    q=parse_qs(urlsplit(uri).query)
    assert uri.startswith('upi://pay?') and '+' not in uri and q['tr'] == ['T1'] and q['am'] == ['20.76']


def test_live_checkout_returns_app_links(app, admin):
    app.config['DEMO_MODE']=False; app.config['PUBLIC_BASE_URL']='https://tips.example.test'
    with app.store.db(True) as db:
        for k, v in [('upi_id', 'example@upi'), ('payee_name', 'Example')]: db.execute('UPDATE settings SET value=? WHERE key=?', (json.dumps(v), k))
    client, _=admin
    r=client.post('/api/public/tips', json={'name': 'Viewer', 'amount': 100}, headers={'Origin': 'https://tips.example.test'})
    assert r.status_code == 201 and [a['app'] for a in r.json['upi_apps']] == ['gpay', 'phonepe', 'paytm', 'upi']
    assert all(f"am={r.json['requested_paise']/100:.2f}" in a['href'] for a in r.json['upi_apps'] if a['app'] != 'phonepe')


def test_demo_checkout_has_no_app_links(app):
    r=app.test_client().post('/api/public/tips', json={'name': 'Viewer', 'amount': 100})
    assert r.status_code == 201 and r.json['upi_apps'] == [] and r.json['upi_uri'] is None


def test_version_and_docs():
    root=__import__('pathlib').Path(__file__).resolve().parents[1]
    assert tuple(int(x) for x in (root / 'VERSION').read_text(encoding='utf-8').strip().split('.')) >= (1, 6, 8)
    readme=(root / 'README.md').read_text(encoding='utf-8')
    assert '**Version 1.6.8 — ' in readme and '(docs/UPDATE_1.6.8.md)' in readme
    changelog=(root / 'docs' / 'CHANGELOG.md').read_text(encoding='utf-8')
    assert ('\n' + changelog).count('\n# 1.6.8 — ') == 1 and changelog.index('# 1.6.8 — ') < changelog.index('\n# 1.6.7 — ')
    assert 'tests\\test_release_168.py' in (root / 'docs' / 'UPDATE_1.6.8.md').read_text(encoding='utf-8')


def test_web_scripts_build_and_use_call():
    root=__import__('pathlib').Path(__file__).resolve().parents[1]
    for name in ['Install_Web.bat', 'Start_Next.bat', 'Start_Web.bat']:
        raw=(root / name).read_bytes()
        assert raw.isascii() and raw.count(b'\r\n') == raw.count(b'\n')
        assert not any(line.strip().startswith('npm ') for line in raw.decode().splitlines())  # without CALL the script ends there
    assert 'call npm run build' in (root / 'Install_Web.bat').read_text() and 'web\\.next\\BUILD_ID' in (root / 'Start_Next.bat').read_text()
