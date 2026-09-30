"""Monday → Hub contact mirror — parsing, the Monday client, and wiring.

Run: python -m pytest tests/test_crm_contact_sync.py -v

The database behaviour (identity, archiving, the lock) is in
tests/test_crm_contact_sync_db.py and needs TEST_DATABASE_URL. This file needs
nothing: pure functions, monday_client with its HTTP call replaced, and the
app/template wiring pinned against source the same way test_client_files.py
does it, because app.py cannot be imported in a test.
"""
import ast
import json
import os
import re
import sys
import urllib.error

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import crm_contact_sync as sync  # noqa: E402
import monday_client  # noqa: E402
import hub_usage  # noqa: E402
import weekly_recap  # noqa: E402

APP = open(os.path.join(ROOT, 'app.py'), encoding='utf-8').read()
TREE = ast.parse(APP)
HTML = open(os.path.join(ROOT, 'templates', 'clients.html'), encoding='utf-8').read()
RENDER = open(os.path.join(ROOT, 'render.yaml'), encoding='utf-8').read()


def _fn(name):
    for n in ast.walk(TREE):
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return ast.get_source_segment(APP, n)
    raise AssertionError(f'{name} not found in app.py')


def _routes():
    out = {}
    for n in ast.walk(TREE):
        if isinstance(n, ast.FunctionDef):
            for d in n.decorator_list:
                if (isinstance(d, ast.Call) and getattr(d.func, 'attr', '') == 'route'
                        and d.args and isinstance(d.args[0], ast.Constant)):
                    out.setdefault(d.args[0].value, []).append(n.name)
    return out


def item(iid, name, email='', phone='', title='', companies=(), owners=(), group='Active Contacts'):
    return {
        'id': str(iid), 'name': name, 'group': {'title': group},
        'column_values': [
            {'id': 'contact_email', 'text': email},
            {'id': 'contact_phone', 'text': phone},
            {'id': 'title5', 'text': title},
            {'id': 'contact_account', 'text': None,
             'display_value': ', '.join(n for _, n in companies),
             'linked_item_ids': [str(c) for c, _ in companies]},
            {'id': 'people_mkm1m3s6',
             'value': json.dumps({'personsAndTeams': [{'id': int(o), 'kind': 'person'} for o in owners]})},
        ],
    }


HUB = {'andy_potts': {'display': 'Andy Potts', 'email': 'Andy@PurePropSolutions.com'}}


# ── parsing ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('raw,out', [
    ('9376702068', '(937) 670-2068'),
    ('+1 937 670 2068', '(937) 670-2068'),
    ('937-670-2068', '(937) 670-2068'),
    ('', ''),
    (None, ''),
    ('+44 20 7946 0958', '+44 20 7946 0958'),
    ('ext 12', 'ext 12'),
])
def test_phone_formats_us_numbers_and_leaves_the_rest(raw, out):
    assert sync.format_phone(raw) == out


def test_owner_lookup_matches_hub_users_by_email_ignoring_case():
    lookup = sync.build_owner_lookup({'72666701': 'andy@purepropsolutions.com',
                                      '76225206': 'mandy@gmail.com'}, HUB)
    assert lookup['72666701'] == ('andy_potts', 'Andy Potts')
    assert lookup['76225206'] == (None, 'mandy')


def test_parse_keeps_every_company_and_every_owner():
    lookup = sync.build_owner_lookup({'72666701': 'andy@purepropsolutions.com'}, HUB)
    p = sync.parse_contact(item(5, ' Lee Park ', 'lee@x.com', '5132802276', 'Condos, CEO',
                                [(1, 'Acme'), (2, 'Park HOA')], ['72666701', '15316889', '999']), lookup)
    assert p['monday_item_id'] == 5 and p['name'] == 'Lee Park'
    assert p['company'] == 'Acme, Park HOA' and p['company_monday_ids'] == [1, 2]
    assert p['owner_user_keys'] == ['andy_potts']
    assert p['owner_names'] == ['Andy Potts', 'Jeremy Bailey (former)', 'Unknown Monday user 999']
    assert p['title'] == 'Condos, CEO' and p['monday_group'] == 'Active Contacts'
    assert not p['placeholder']


def test_blank_fields_are_null_not_empty_strings():
    p = sync.parse_contact(item(6, 'Only Name'), {})
    assert p['email'] is None and p['phone'] is None and p['title'] is None and p['company'] is None
    assert p['company_monday_ids'] == [] and p['owner_names'] == []


def test_company_ids_fall_back_to_the_value_json():
    it = item(7, 'X')
    cv = it['column_values'][3]
    cv['linked_item_ids'] = []
    cv['value'] = json.dumps({'linkedPulseIds': [{'linkedPulseId': 42}]})
    assert sync.parse_contact(it, {})['company_monday_ids'] == [42]


@pytest.mark.parametrize('name', ['New Contact', 'new contact', '', '   '])
def test_placeholders_are_flagged(name):
    assert sync.parse_contact(item(8, name), {})['placeholder']


def test_duplicate_report_groups_by_email_case_insensitively():
    parsed = [sync.parse_contact(i, {}) for i in (
        item(1, 'A', 'x@y.com'), item(2, 'B', 'X@Y.com '), item(3, 'C', 'z@y.com'), item(4, 'D'))]
    rep = sync.duplicate_email_report(parsed)
    assert [(d['email'], [i['monday_item_id'] for i in d['items']]) for d in rep] == [('x@y.com', [1, 2])]
    assert rep[0]['items'][0]['url'].endswith('/boards/7902650879/pulses/1')


# ── identity is the Monday item ID and nothing else ─────────────────────────

def test_upsert_conflicts_on_monday_item_id_only():
    sql = sync.UPSERT_SQL
    assert 'ON CONFLICT (monday_item_id)' in sql
    assert sql.count('ON CONFLICT') == 1


def test_no_statement_matches_contacts_on_name_email_or_phone():
    # The one email comparison allowed is moving an old contact's FILES.
    for name in ('UPSERT_SQL', 'INACTIVATE_SQL', 'ARCHIVE_LEGACY_SQL', 'STAMP_SYNCED_SQL'):
        sql = getattr(sync, name)
        where = sql.split('WHERE', 1)[1] if 'WHERE' in sql else ''
        where = where.split('IS DISTINCT FROM')[0]  # the change detector reads fields, it does not match on them
        for col in ('email =', 'name =', 'phone =', 'LOWER(email)', 'LOWER(name)'):
            assert col not in where.replace('clients.', ''), (name, col)
    assert 'LOWER(TRIM(COALESCE(email' in sync.MONDAY_BY_EMAIL_SQL


def test_the_unique_index_is_part_of_the_schema():
    joined = '\n'.join(sync.SCHEMA_STATEMENTS)
    assert 'CREATE UNIQUE INDEX IF NOT EXISTS uq_clients_monday_item_id ON clients(monday_item_id)' in joined
    assert all('IF NOT EXISTS' in s for s in sync.SCHEMA_STATEMENTS)
    assert not any(s.strip().upper().startswith(('DROP', 'DELETE')) for s in sync.SCHEMA_STATEMENTS)


def test_nothing_in_the_module_deletes_a_contact():
    src = open(os.path.join(ROOT, 'crm_contact_sync.py'), encoding='utf-8').read()
    assert not re.search(r'DELETE\s+FROM\s+clients', src, re.I)


def test_ignored_columns_are_not_requested():
    for col in ('status5', 'long_text4'):
        assert col not in monday_client._CONTACTS_COLUMN_IDS


# ── monday_client ───────────────────────────────────────────────────────────

def test_an_invisible_board_is_an_access_error_not_an_empty_board(monkeypatch):
    monkeypatch.setattr(monday_client, 'monday_graphql', lambda *a, **k: {'boards': []})
    with pytest.raises(monday_client.MondayAccessError) as e:
        monday_client.fetch_contacts_board()
    assert 'regenerate' in str(e.value)


def test_a_permission_message_is_an_access_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("Monday API error: [{'message': 'User unauthorized to perform action'}]")
    monkeypatch.setattr(monday_client, 'monday_graphql', boom)
    with pytest.raises(monday_client.MondayAccessError):
        monday_client.fetch_contacts_board()


def test_http_403_is_an_access_error(monkeypatch):
    def boom(*a, **k):
        raise urllib.error.HTTPError('u', 403, 'Forbidden', {}, None)
    monkeypatch.setattr(monday_client, 'monday_graphql', boom)
    with pytest.raises(monday_client.MondayAccessError):
        monday_client.fetch_contacts_board()


def test_other_api_errors_are_not_disguised_as_access_errors(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError('Monday API error: complexity budget exhausted')
    monkeypatch.setattr(monday_client, 'monday_graphql', boom)
    with pytest.raises(RuntimeError) as e:
        monday_client.fetch_contacts_board()
    assert not isinstance(e.value, monday_client.MondayAccessError)


def test_pages_with_cursors_500_at_a_time(monkeypatch):
    calls = []

    def fake(query, variables=None, timeout=30):
        calls.append(variables)
        if 'boardId' in variables:
            return {'boards': [{'items_page': {'cursor': 'c1', 'items': [{'id': '1'}]}}]}
        if variables['cursor'] == 'c1':
            return {'next_items_page': {'cursor': 'c2', 'items': [{'id': '2'}]}}
        return {'next_items_page': {'cursor': None, 'items': [{'id': '3'}]}}
    monkeypatch.setattr(monday_client, 'monday_graphql', fake)
    assert [i['id'] for i in monday_client.fetch_contacts_board()] == ['1', '2', '3']
    assert all(v['limit'] == 500 for v in calls) and len(calls) == 3


def test_compliance_board_code_is_untouched():
    # Thomas: do not change the compliance board's behaviour in this work.
    assert monday_client.ACTIVE_GROUPS == (
        'Sub contractors - Compliant', 'ON HOLD - Waiting on updated insurnace')
    assert monday_client._COLUMN_IDS == '["status", "date", "date8", "files", "date4"]'
    assert 'api_version' not in open(os.path.join(ROOT, 'monday_client.py')).read().split('def monday_graphql')[1].split('\ndef ')[0]


# ── the email ───────────────────────────────────────────────────────────────

def test_summary_email_lists_duplicates_placeholders_and_the_safety_stop():
    r = {'ok': True, 'applied': True, 'first_sync': False, 'checked': 10, 'contacts': 9,
         'created': 1, 'updated': 2, 'unchanged': 6, 'inactivated': 0,
         'skipped_inactivation': 'looks partial', 'owners_unmatched': ['Jeremy Bailey (former)'],
         'duplicates': [{'email': 'a@b.com', 'items': [{'name': 'A', 'monday_item_id': 1},
                                                        {'name': 'B', 'monday_item_id': 2}]}],
         'placeholders': [{'url': 'https://m/1', 'email': 'a@b.com'}]}
    subject, text, html = sync.build_summary_email(r)
    assert '1 new, 2 updated, 0 inactivated' in subject
    assert 'SAFETY STOP' in text and 'a@b.com: A (1); B (2)' in text
    assert 'https://m/1' in text and 'Jeremy Bailey' in text


def test_preview_email_says_nothing_was_written():
    r = {'ok': True, 'applied': False, 'first_sync': True, 'checked': 1, 'contacts': 1,
         'created': 1, 'updated': 0, 'unchanged': 0, 'inactivated': 0, 'legacy_archived': 3,
         'files_moved': [], 'files_left': [], 'duplicates': [], 'placeholders': []}
    subject, text, _ = sync.build_summary_email(r)
    assert 'preview' in subject and 'nothing was written' in text


def test_weekly_cron_previews_until_the_first_sync_is_applied(monkeypatch):
    seen = {}
    monkeypatch.setattr(sync, 'is_initialized', lambda g: False)

    def fake_run(get_db, users, by, apply=True, initial=False, **kw):
        seen.update(apply=apply, initial=initial, by=by)
        return {'ok': True, 'applied': apply, 'first_sync': True, 'checked': 0, 'contacts': 0,
                'created': 0, 'updated': 0, 'unchanged': 0, 'inactivated': 0, 'legacy_archived': 0,
                'files_moved': [], 'files_left': [], 'duplicates': [], 'placeholders': []}
    monkeypatch.setattr(sync, 'run_sync', fake_run)
    out = sync.run_weekly_crm_sync(lambda: None, lambda *a: True, ['t@x'], HUB)
    assert seen == {'apply': False, 'initial': True, 'by': 'schedule'} and out['sent']


# ── usage and scoring ───────────────────────────────────────────────────────

def test_sync_is_labelled_and_never_scored():
    assert 'sync' in hub_usage.ACTION_LABELS
    assert 'sync' not in weekly_recap.SCORED_USAGE_ACTIONS


# ── app wiring ──────────────────────────────────────────────────────────────

def test_the_add_edit_and_seed_routes_are_gone():
    routes = _routes()
    for gone in ('/api/clients/save', '/api/clients/seed', '/admin/seed-clients'):
        assert gone not in routes, gone
    assert not os.path.exists(os.path.join(ROOT, 'templates', 'seed_clients.html')), \
        'seed_clients.html carries real client names and emails; git rm it'
    assert 'INSERT INTO clients' not in APP and 'UPDATE clients SET name' not in APP


def test_sync_routes_exist_and_first_sync_is_owner_only():
    routes = _routes()
    assert routes['/api/clients/sync'] == ['clients_sync_now']
    assert routes['/api/clients/sync/first'] == ['clients_sync_first']
    now = _fn('clients_sync_now')
    assert '_contacts_api_user()' in now and 'is_owner' not in now  # anyone on the roster
    first = _fn('clients_sync_first')
    assert 'is_owner(user_key)' in first and 'initial=True' in first


def test_the_cron_endpoint_uses_the_internal_key_and_records_its_run():
    body = _fn('cron_weekly_crm_sync')
    assert '_internal_api_ok()' in body
    assert "record_job_run(get_db, 'weekly_crm_sync'" in body
    assert 'USERS' in body


def test_search_hides_inactive_puts_mine_first_and_defaults_to_active_contacts():
    body = _fn('clients_search')
    assert 'WHERE is_active' in body
    assert 'ANY(owner_user_keys)' in body
    assert body.index('ANY(owner_user_keys), FALSE) DESC') < body.index('LIMIT 10')
    assert 'crm_contact_sync.DEFAULT_GROUP' in body
    # The proxy's user_key is trusted only alongside the internal key.
    assert "request.args.get('user_key') if internal_ok" in body
    # Old callers read these five; they must survive.
    for col in ('id', 'name', 'email', 'company', 'property_name', 'address'):
        assert re.search(rf'\b{col}\b', body.split('FROM clients')[0]), col


def test_page_is_read_only_with_the_monday_link_and_the_toggles():
    assert '/api/clients/save' not in HTML and 'saveClient' not in HTML
    assert '{{ monday_board_url }}' in HTML and 'Add contact in Monday' in HTML
    assert 'Mine first' in HTML and 'All A–Z' in HTML
    assert 'Last synced' in HTML and 'id="syncBtn"' in HTML
    assert 'use sparingly' not in HTML.lower()
    body = _fn('clients_page')
    assert 'WHERE c.is_active' in body and "default_group" in body


def test_page_builds_rows_with_text_nodes_not_markup():
    # Names and companies come from Monday; nothing from a row may be parsed as HTML.
    script = HTML.split('<script>')[1]
    assert 'innerHTML = \'\'' in script
    for bad in ('innerHTML = r.', 'innerHTML = `', 'innerHTML += '):
        assert bad not in script


def test_render_yaml_still_declares_the_cron():
    assert 'name: pps-hub-weekly-crm-sync' in RENDER
    assert 'startCommand: python cron_weekly_crm_sync.py' in RENDER
