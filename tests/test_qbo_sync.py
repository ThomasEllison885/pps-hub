"""QuickBooks nightly pull: tally, split, matching, paging, refresh, failure.

No network and no Postgres. Run: python -m pytest tests/test_qbo_sync.py -v
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import qbo_connect
import qbo_sync as sync

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

USERS = {
    'adam_cupito': {'display': 'Adam Cupito'},
    'rachel_farler': {'display': 'Rachel Farler'},
    'andy_potts': {'display': 'Andy Potts'},
    'andy_baur': {'display': 'Andy Baur'},
    'harrison_hollon': {'display': 'Harrison Hollon'},
}


def inv(inv_id, txn_date, total, consultant=None, city=None, tax=None):
    fields = []
    if consultant is not None:
        fields.append({'DefinitionId': '1', 'Name': 'Consultant', 'Type': 'StringType', 'StringValue': consultant})
    fields.append({'DefinitionId': '2', 'Name': 'Customer Code', 'Type': 'StringType', 'StringValue': 'Fath'})
    if city is not None:
        fields.append({'DefinitionId': '3', 'Name': 'City', 'Type': 'StringType', 'StringValue': city})
    out = {'Id': str(inv_id), 'TxnDate': txn_date, 'TotalAmt': total, 'CustomField': fields}
    if tax is not None:
        out['TxnTaxDetail'] = {'TotalTax': tax}
    return out


# ── tally ────────────────────────────────────────────────────────────────


def test_shared_invoice_splits_evenly_and_company_counts_it_once():
    rows, facts = sync.tally([inv(1, '2026-03-04', 1000, 'Adam / Rachel', 'Dayton')], 2026)
    assert rows[(3, 'Adam', 'Dayton')] == [Decimal('500'), Decimal('0.5')]
    assert rows[(3, 'Rachel', 'Dayton')] == [Decimal('500'), Decimal('0.5')]
    assert facts['company_total'] == Decimal('1000')
    assert facts['invoice_count'] == 1


def test_split_accepts_ampersand_and_the_word_and():
    assert sync.split_consultants('Adam & Andy') == ['Adam', 'Andy']
    assert sync.split_consultants('Adam and Rachel') == ['Adam', 'Rachel']
    assert sync.split_consultants('  Andy   Potts ') == ['Andy Potts']
    assert sync.split_consultants('Adam / adam') == ['Adam']
    assert sync.split_consultants('') == []


def test_sales_tax_is_not_sales():
    rows, facts = sync.tally([inv(1, '2026-01-10', '1070.00', 'Andy Potts', tax='70.00')], 2026)
    assert facts['company_total'] == Decimal('1000.00')


def test_voided_invoice_counts_zero_and_blank_consultant_goes_to_company_only():
    rows, facts = sync.tally([
        inv(1, '2026-02-01', 0, 'Andy Potts'),
        inv(2, '2026-02-02', 250, ''),
    ], 2026)
    assert facts['company_total'] == Decimal('250')
    assert facts['no_consultant_count'] == 1
    assert facts['no_consultant_total'] == Decimal('250')
    assert rows[(2, '', '')][0] == Decimal('250')


def test_consultant_field_seen_is_false_when_quickbooks_omits_it():
    _, facts = sync.tally([inv(1, '2026-02-01', 100)], 2026)
    assert facts['consultant_field_seen'] is False
    _, facts = sync.tally([inv(1, '2026-02-01', 100, '')], 2026)
    assert facts['consultant_field_seen'] is True


def test_other_years_and_duplicate_ids_are_dropped():
    rows, facts = sync.tally([
        inv(1, '2025-12-31', 999, 'Andy Potts'),
        inv(2, '2026-05-05', 100, 'Andy Potts'),
        inv(2, '2026-05-05', 100, 'Andy Potts'),
    ], 2026)
    assert facts['invoice_count'] == 1
    assert facts['skipped_other_year'] == 1
    assert facts['company_total'] == Decimal('100')


def test_custom_field_names_are_matched_without_case():
    invoice = {'Id': '1', 'TxnDate': '2026-06-01', 'TotalAmt': 10,
               'CustomField': [{'Name': 'CONSULTANT', 'StringValue': 'Andy Potts'}]}
    rows, _ = sync.tally([invoice], 2026)
    assert (6, 'Andy Potts', '') in rows


# ── matching ─────────────────────────────────────────────────────────────


def test_full_name_matches_without_a_saved_match():
    assert sync.resolve_consultant('andy potts', USERS, {}) == 'andy_potts'


def test_unique_first_name_matches_and_an_ambiguous_one_does_not():
    assert sync.resolve_consultant('Rachel', USERS, {}) == 'rachel_farler'
    assert sync.resolve_consultant('Andy', USERS, {}) is None


def test_saved_match_wins_and_a_departed_person_does_not_resolve():
    assert sync.resolve_consultant('Andy', USERS, {'andy': 'andy_potts'}) == 'andy_potts'
    assert sync.resolve_consultant('Tony Cumella', USERS, {}) is None
    assert sync.resolve_consultant('Tony Cumella', USERS, {'tony cumella': 'tony_cumella'}) is None


# ── query and paging ─────────────────────────────────────────────────────


def test_query_is_one_calendar_year_and_paged():
    q = sync.invoice_query(2026, 1001)
    assert q.startswith('SELECT * FROM Invoice WHERE ')
    assert "TxnDate >= '2026-01-01'" in q
    assert "TxnDate <= '2026-12-31'" in q
    assert q.endswith('STARTPOSITION 1001 MAXRESULTS 1000')


class Resp:
    def __init__(self, status, invoices=None):
        self.status_code = status
        self._invoices = invoices or []

    def json(self):
        return {'QueryResponse': {'Invoice': self._invoices}}


def _tokens(expires_in=timedelta(hours=1)):
    return {
        'realm_id': '123', 'environment': 'sandbox',
        'access_token': 'a1', 'refresh_token': 'r1',
        'access_expires_at': datetime.now(timezone.utc) + expires_in,
    }


def test_pulls_until_a_short_page(monkeypatch):
    calls = []
    monkeypatch.setattr(sync, 'PAGE_SIZE', 2)
    monkeypatch.setattr(qbo_connect, 'load_tokens', lambda g: _tokens())

    def fake_get(env, realm, path, params=None, headers=None):
        calls.append(params['query'])
        n = len(calls)
        return Resp(200, [{'Id': str(n * 10 + i)} for i in range(2 if n < 3 else 1)])

    monkeypatch.setattr(qbo_connect, 'accounting_get', fake_get)
    out = sync.pull_year(None, 2026)
    assert len(out) == 5
    assert [q.split('STARTPOSITION ')[1].split()[0] for q in calls] == ['1', '3', '5']


def test_expired_access_token_is_refreshed_and_stored_before_the_query(monkeypatch):
    order = []
    monkeypatch.setattr(qbo_connect, 'load_tokens', lambda g: _tokens(timedelta(minutes=-1)))
    monkeypatch.setattr(qbo_connect, 'refresh_tokens',
                        lambda r: order.append(('refresh', r)) or {'access_token': 'a2', 'refresh_token': 'r2'})
    monkeypatch.setattr(qbo_connect, 'replace_tokens', lambda g, p: order.append(('store', p['refresh_token'])))

    def fake_get(env, realm, path, params=None, headers=None):
        order.append(('get', headers['Authorization']))
        return Resp(200, [])

    monkeypatch.setattr(qbo_connect, 'accounting_get', fake_get)
    sync.pull_year(None, 2026)
    assert order == [('refresh', 'r1'), ('store', 'r2'), ('get', 'Bearer a2')]


def test_a_401_refreshes_once_then_retries(monkeypatch):
    seen = []
    monkeypatch.setattr(qbo_connect, 'load_tokens', lambda g: _tokens())
    monkeypatch.setattr(qbo_connect, 'refresh_tokens', lambda r: {'access_token': 'a2', 'refresh_token': 'r2'})
    monkeypatch.setattr(qbo_connect, 'replace_tokens', lambda g, p: None)

    def fake_get(env, realm, path, params=None, headers=None):
        seen.append(headers['Authorization'])
        return Resp(401) if len(seen) == 1 else Resp(200, [])

    monkeypatch.setattr(qbo_connect, 'accounting_get', fake_get)
    sync.pull_year(None, 2026)
    assert seen == ['Bearer a1', 'Bearer a2']


def test_refused_refresh_is_a_visible_failure_and_nothing_is_stored(monkeypatch):
    recorded = {}
    monkeypatch.setattr(qbo_connect, 'load_tokens', lambda g: _tokens(timedelta(minutes=-1)))

    def refused(r):
        raise qbo_connect.QboAuthError('QuickBooks refused the connection (invalid_grant).')

    monkeypatch.setattr(qbo_connect, 'refresh_tokens', refused)
    monkeypatch.setattr(sync, '_record_connection_error', lambda g, m: recorded.setdefault('conn', m))
    monkeypatch.setattr(sync, 'record_failure', lambda g, m, by: recorded.setdefault('sync', m))
    monkeypatch.setattr(sync, 'store', lambda *a, **k: pytest.fail('must not store after a failure'))
    result = sync.run_sync(None, run_by='nightly', year=2026)
    assert result['ok'] is False
    assert 'reconnected' in result['error']
    assert 'invalid_grant' in recorded['conn']
    assert recorded['sync'] == result['error']


def test_a_failed_page_keeps_the_last_good_numbers(monkeypatch):
    monkeypatch.setattr(qbo_connect, 'load_tokens', lambda g: _tokens())
    monkeypatch.setattr(qbo_connect, 'accounting_get', lambda *a, **k: Resp(500))
    monkeypatch.setattr(sync, 'record_failure', lambda g, m, by: None)
    monkeypatch.setattr(sync, 'store', lambda *a, **k: pytest.fail('must not store after a failure'))
    result = sync.run_sync(None, year=2026)
    assert result == {'ok': False, 'error': 'QuickBooks answered 500 to the invoice query.'}


def test_successful_run_result_has_no_token(monkeypatch):
    monkeypatch.setattr(qbo_connect, 'load_tokens', lambda g: _tokens())
    monkeypatch.setattr(qbo_connect, 'accounting_get',
                        lambda *a, **k: Resp(200, [inv(1, '2026-04-01', 10, 'Andy Potts')]))
    stored = {}
    monkeypatch.setattr(sync, 'store', lambda g, y, rows, facts, by: stored.update(rows=rows))
    result = sync.run_sync(None, year=2026)
    assert result['ok'] is True and result['invoices'] == 1
    assert 'a1' not in str(result) and 'r1' not in str(result)
    assert (4, 'Andy Potts', '') in stored['rows']


# ── read only, schedule ──────────────────────────────────────────────────


def test_sync_module_never_calls_intuit_itself():
    text = open(os.path.join(ROOT, 'qbo_sync.py'), encoding='utf-8').read()
    assert 'httpx' not in text
    assert 'requests' not in text.replace('# ', '')
    assert 'intuit.com' not in text
    assert 'CreditMemo' not in text


def test_runs_only_at_midnight_eastern():
    assert sync.is_midnight_eastern(datetime(2026, 11, 24, 0, 5, tzinfo=sync.ET))
    assert not sync.is_midnight_eastern(datetime(2026, 11, 24, 1, 5, tzinfo=sync.ET))
    assert not sync.is_midnight_eastern(datetime(2026, 11, 23, 23, 59, tzinfo=sync.ET))


def test_cron_endpoint_needs_the_key_and_skips_outside_midnight(monkeypatch):
    from flask import Flask
    app = Flask(__name__)
    app.secret_key = 'x'
    key_ok = {'v': False}
    ran = []
    monkeypatch.setattr(sync, 'run_sync', lambda g, run_by='nightly': ran.append(run_by) or {'ok': True})
    monkeypatch.setattr(sync, 'is_midnight_eastern', lambda now=None: False)

    def require_admin(f):
        return f

    @app.route('/admin/quickbooks')
    def admin_quickbooks():
        return ''

    sync.register_routes(app, lambda: None, require_admin, USERS, lambda: key_ok['v'], None, lambda: [])
    client = app.test_client()
    assert client.post('/api/cron/qbo-sync').status_code == 401
    key_ok['v'] = True
    assert client.post('/api/cron/qbo-sync').get_json()['skipped'] is True
    assert ran == []
    assert client.post('/api/cron/qbo-sync?force=1').get_json()['ok'] is True
    assert ran == ['nightly']


def test_mapping_refuses_someone_not_on_the_roster(monkeypatch):
    from flask import Flask
    app = Flask(__name__)
    app.secret_key = 'x'
    saved = []
    monkeypatch.setattr(sync, 'save_mapping', lambda g, n, k, by: saved.append((n, k)))

    @app.route('/admin/quickbooks')
    def admin_quickbooks():
        return ''

    sync.register_routes(app, lambda: None, lambda f: f, USERS, lambda: False, None, lambda: [])
    client = app.test_client()
    r = client.post('/admin/quickbooks/map', data={'qb_name': 'Andy', 'user_key': 'nobody'})
    assert 'map_bad' in r.headers['Location']
    client.post('/admin/quickbooks/map', data={'qb_name': 'Andy', 'user_key': 'andy_potts'})
    assert saved == [('Andy', 'andy_potts')]


def test_admin_page_renders_with_the_sync_section():
    import hub_time
    from flask import Flask
    app = Flask(__name__, template_folder=os.path.join(ROOT, 'templates'))
    hub_time.register(app)
    status = qbo_connect._empty_status()
    status.update(connected=True, realm_id='123')
    summary = {
        'year': 2026,
        'by_name': [
            {'name': 'Andy Potts', 'amount': Decimal('1000.6'), 'invoices': Decimal('2'), 'user_key': 'andy_potts'},
            {'name': 'Tony', 'amount': Decimal('300'), 'invoices': Decimal('0.5'), 'user_key': None},
            {'name': '', 'amount': Decimal('50'), 'invoices': Decimal('1'), 'user_key': None},
        ],
        'by_person': [{'user_key': 'andy_potts', 'display': 'Andy Potts', 'amount': Decimal('1000.6')}],
        'by_city': [('Dayton', Decimal('1350.6'))],
        'company_total': Decimal('1350.6'),
    }
    sync_row = {
        'year': 2026, 'last_synced_at': datetime(2026, 11, 24, 5, 5, tzinfo=timezone.utc),
        'invoice_count': 3, 'no_consultant_count': 1, 'no_consultant_total': Decimal('50'),
        'consultant_field_seen': True, 'last_run_by': 'nightly', 'last_error': None, 'last_error_at': None,
    }
    with app.test_request_context():
        from flask import render_template
        html = render_template(
            'admin_quickbooks.html', status=status, notice='', notice_ok=False, ready=True,
            sync=sync_row, summary=summary, unmatched_count=1, saved_map={},
            people=[('andy_potts', 'Andy Potts')],
        )
    assert '$1,351' in html
    assert 'Sync now' in html
    assert '1 name did not match' in html
    assert 'Company total only' in html
    assert 'Dayton $1,351' in html
