"""Monday → Hub contact mirror, against a real Postgres.

Run: TEST_DATABASE_URL=postgresql://... python -m pytest tests/test_crm_contact_sync_db.py -v

Thomas, 2026-09-30: "Duplicate prevention (most important)." Every test here
is about identity and about what survives — the parts a fake cursor cannot
prove, because they live in ON CONFLICT, IS DISTINCT FROM, the unique index
and the advisory lock.
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DSN = os.environ.get('TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not DSN, reason='TEST_DATABASE_URL not set')

if DSN:
    import psycopg2

import crm_contact_sync as sync  # noqa: E402
import monday_client  # noqa: E402

HUB_USERS = {
    'andy_potts': {'display': 'Andy Potts', 'email': 'Andy@purepropsolutions.com'},
    'rachel_farler': {'display': 'Rachel Farler', 'email': 'rachel@purepropsolutions.com'},
}
MONDAY_USERS = {'72666701': 'andy@purepropsolutions.com',
                '97764484': 'rachel@purepropsolutions.com'}


def item(iid, name, email='', phone='', title='', companies=(), owners=(), group='Active Contacts'):
    return {
        'id': str(iid), 'name': name, 'group': {'id': 'g', 'title': group},
        'column_values': [
            {'id': 'contact_email', 'text': email, 'value': None},
            {'id': 'contact_phone', 'text': phone, 'value': None},
            {'id': 'title5', 'text': title, 'value': None},
            {'id': 'contact_account', 'text': None, 'value': None,
             'display_value': ', '.join(n for _, n in companies),
             'linked_item_ids': [str(c) for c, _ in companies]},
            {'id': 'people_mkm1m3s6', 'text': '',
             'value': json.dumps({'personsAndTeams': [{'id': int(o), 'kind': 'person'} for o in owners]})},
        ],
    }


BASE = [
    item(101, 'Dana Reed', 'dana@acme.com', '9376702068', 'Community Manager',
         [(9001, 'Acme Mgmt')], ['72666701']),
    item(102, 'Lee Park', 'lee@acme.com', '', 'Condos, Regional Manager',
         [(9001, 'Acme Mgmt'), (9002, 'Park HOA')], ['72666701', '97764484']),
    item(103, 'Sam Old', 'sam@old.com', owners=['15316889']),
    item(104, 'Troy Roberts', 'troy@bh.com'),
    item(105, 'Troy Roberts', 'troy@bh.com'),
    item(106, 'New Contact', 'troy@bh.com'),
    item(107, 'Pat Inactive', 'pat@x.com', group='Inactive Contacts'),
]


@pytest.fixture
def get_db():
    conn = psycopg2.connect(DSN)
    cur = conn.cursor()
    for t in ('clients', 'documents', 'hub_settings'):
        cur.execute(f'DROP TABLE IF EXISTS {t} CASCADE')
    # The real shapes, from app.init_db.
    cur.execute('''CREATE TABLE clients (
        id SERIAL PRIMARY KEY, name VARCHAR(255) NOT NULL, email VARCHAR(255),
        company VARCHAR(255), property_name VARCHAR(255), address TEXT, notes TEXT,
        added_by VARCHAR(100), updated_at TIMESTAMP DEFAULT NOW(),
        created_at TIMESTAMP DEFAULT NOW())''')
    cur.execute('''CREATE TABLE documents (
        id SERIAL PRIMARY KEY, doc_type VARCHAR(40), log_id INTEGER, filename TEXT)''')
    cur.execute('''CREATE TABLE hub_settings (
        key VARCHAR(100) PRIMARY KEY, value JSONB NOT NULL,
        updated_at TIMESTAMP DEFAULT NOW(), updated_by VARCHAR(100))''')
    # Pre-Monday Hub contacts, as they exist today — added before the
    # migration columns, so they must come out as source 'hub'.
    cur.execute("""INSERT INTO clients (name, email, company, property_name, added_by) VALUES
        ('Dana Reed', 'DANA@acme.com ', 'Acme', 'Vantage Point', 'tony_cumella'),
        ('Troy R', 'troy@bh.com', '', '', 'monday_crm_sync'),
        ('Nobody', 'nobody@x.com', '', '', 'adam_cupito'),
        ('No Email', '', '', '', 'adam_cupito')""")
    for stmt in sync.SCHEMA_STATEMENTS:
        cur.execute(stmt)
    cur.execute("""INSERT INTO documents (doc_type, log_id, filename) VALUES
        ('client_file', 1, 'site-map.jpg'),
        ('client_file', 2, 'troy.pdf'),
        ('client_file', 3, 'nobody.pdf'),
        ('client_file', 4, 'noemail.pdf'),
        ('proposal', 1, 'not-a-client-file.docx')""")
    conn.commit()
    cur.close()
    conn.close()
    yield lambda: psycopg2.connect(DSN)


def run(get_db, items, **kw):
    kw.setdefault('initial', True)
    return sync.run_sync(get_db, HUB_USERS, kw.pop('by', 'thomas_ellison'),
                         fetch_items=lambda: items, fetch_users=lambda: MONDAY_USERS, **kw)


def q(get_db, sql, params=None):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    return rows


# ── the first sync ──────────────────────────────────────────────────────────

def test_preview_writes_nothing_but_reports_real_numbers(get_db):
    r = run(get_db, BASE, apply=False)
    assert r['ok'] and not r['applied']
    assert r['created'] == 6  # 7 items minus the placeholder
    assert r['legacy_archived'] == 4
    assert q(get_db, "SELECT COUNT(*) FROM clients")[0][0] == 4
    assert q(get_db, "SELECT COUNT(*) FROM clients WHERE is_active")[0][0] == 4
    assert q(get_db, "SELECT log_id FROM documents WHERE filename='site-map.jpg'")[0][0] == 1
    assert q(get_db, "SELECT COUNT(*) FROM hub_settings")[0][0] == 0


def test_normal_sync_refuses_until_the_first_one_is_applied(get_db):
    r = run(get_db, BASE, initial=False)
    assert r['skipped'] and r['reason'] == 'awaiting_first_sync'
    assert q(get_db, "SELECT COUNT(*) FROM clients WHERE source='monday'")[0][0] == 0


def test_first_apply_archives_old_contacts_and_never_deletes_them(get_db):
    r = run(get_db, BASE)
    assert r['ok'] and r['applied'] and r['first_sync']
    rows = q(get_db, "SELECT name, is_active, archived_reason FROM clients WHERE source='hub' ORDER BY id")
    assert [x[0] for x in rows] == ['Dana Reed', 'Troy R', 'Nobody', 'No Email']
    assert all(not x[1] and x[2] == sync.REASON_REPLACED for x in rows)
    assert sync.is_initialized(get_db)


def test_files_follow_an_exact_unique_email_and_nothing_else(get_db):
    r = run(get_db, BASE)
    dana = q(get_db, "SELECT id FROM clients WHERE monday_item_id=101")[0][0]
    # 'DANA@acme.com ' matched dana@acme.com: case and whitespace only.
    assert q(get_db, "SELECT log_id FROM documents WHERE filename='site-map.jpg'")[0][0] == dana
    left = {f['filename']: f['why'] for f in r['files_left']}
    assert left['troy.pdf'] == '2 Monday contacts share that email'
    assert left['nobody.pdf'] == 'no Monday contact has that email'
    assert left['noemail.pdf'] == 'old contact has no email'
    # Files left behind stay on the archived row, which still exists.
    assert q(get_db, "SELECT log_id FROM documents WHERE filename='troy.pdf'")[0][0] == 2
    # A proposal document with a colliding log_id is never touched.
    assert q(get_db, "SELECT log_id FROM documents WHERE doc_type='proposal'")[0][0] == 1


def test_placeholders_are_left_out_and_reported(get_db):
    r = run(get_db, BASE)
    assert q(get_db, "SELECT COUNT(*) FROM clients WHERE monday_item_id=106")[0][0] == 0
    assert [p['monday_item_id'] for p in r['placeholders']] == [106]


def test_duplicate_report_includes_the_placeholder_twin(get_db):
    r = run(get_db, BASE)
    dup = {d['email']: [i['monday_item_id'] for i in d['items']] for d in r['duplicates']}
    assert dup == {'troy@bh.com': [104, 105, 106]}


def test_synced_fields_land_as_monday_has_them(get_db):
    run(get_db, BASE)
    row = q(get_db, """SELECT name, email, phone, title, company, company_monday_ids,
                              owner_user_keys, owner_names, monday_group, source
                       FROM clients WHERE monday_item_id=102""")[0]
    assert row == ('Lee Park', 'lee@acme.com', None, 'Condos, Regional Manager',
                   'Acme Mgmt, Park HOA', [9001, 9002], ['andy_potts', 'rachel_farler'],
                   ['Andy Potts', 'Rachel Farler'], 'Active Contacts', 'monday')
    former = q(get_db, "SELECT owner_user_keys, owner_names FROM clients WHERE monday_item_id=103")[0]
    assert former == ([], ['Jeremy Bailey (former)'])
    # Every group is synced; the picker defaults to Active Contacts, it does not filter here.
    assert q(get_db, "SELECT monday_group FROM clients WHERE monday_item_id=107")[0][0] == 'Inactive Contacts'


# ── identity: the whole point ───────────────────────────────────────────────

def test_second_identical_sync_changes_nothing(get_db):
    run(get_db, BASE)
    r = run(get_db, BASE, initial=False)
    assert (r['created'], r['updated'], r['inactivated'], r['unchanged']) == (0, 0, 0, 6)
    assert not r['first_sync']


def test_editing_email_title_and_phone_in_monday_updates_the_same_row(get_db):
    run(get_db, BASE)
    before = q(get_db, "SELECT id FROM clients WHERE monday_item_id=101")[0][0]
    edited = [item(101, 'Dana Reed-Smith', 'dana.new@acme.com', '5132802276', 'Regional Manager',
                   [(9001, 'Acme Mgmt')], ['97764484'])] + BASE[1:]
    r = run(get_db, edited, initial=False)
    assert (r['created'], r['updated']) == (0, 1)
    rows = q(get_db, "SELECT id, name, email, phone, owner_user_keys FROM clients WHERE monday_item_id=101")
    assert rows == [(before, 'Dana Reed-Smith', 'dana.new@acme.com', '5132802276', ['rachel_farler'])]
    assert q(get_db, "SELECT COUNT(*) FROM clients WHERE source='monday'")[0][0] == 6


def test_two_monday_items_with_the_same_name_and_email_stay_two_contacts(get_db):
    run(get_db, BASE)
    assert q(get_db, "SELECT COUNT(*) FROM clients WHERE email='troy@bh.com' AND source='monday'")[0][0] == 2


def test_the_database_itself_refuses_a_second_row_for_one_monday_item(get_db):
    run(get_db, BASE)
    conn = get_db()
    cur = conn.cursor()
    with pytest.raises(psycopg2.errors.UniqueViolation):
        cur.execute("INSERT INTO clients (name, monday_item_id) VALUES ('dup', 101)")
    conn.close()


def test_a_removed_item_is_inactivated_and_comes_back_as_the_same_row(get_db):
    run(get_db, BASE)
    rid = q(get_db, "SELECT id FROM clients WHERE monday_item_id=103")[0][0]
    r = run(get_db, [i for i in BASE if i['id'] != '103'], initial=False)
    assert r['inactivated'] == 1 and r['inactivated_names'] == ['Sam Old']
    assert q(get_db, "SELECT is_active, archived_reason FROM clients WHERE id=%s", (rid,))[0] == \
        (False, sync.REASON_REMOVED)
    r = run(get_db, BASE, initial=False)
    assert (r['created'], r['updated']) == (0, 1)
    assert q(get_db, "SELECT id, is_active, archived_reason FROM clients WHERE monday_item_id=103")[0] == \
        (rid, True, None)


# ── safety ──────────────────────────────────────────────────────────────────

def test_a_partial_pull_skips_inactivation(get_db):
    run(get_db, BASE)
    r = run(get_db, BASE[:2], initial=False)
    assert r['ok'] and r['inactivated'] == 0 and r['skipped_inactivation']
    assert q(get_db, "SELECT COUNT(*) FROM clients WHERE source='monday' AND is_active")[0][0] == 6


def test_an_empty_pull_changes_nothing_at_all(get_db):
    run(get_db, BASE)
    r = run(get_db, [item(200, 'New Contact')], initial=False)
    assert not r['ok'] and r['error'] == 'empty_board'
    assert q(get_db, "SELECT COUNT(*) FROM clients WHERE source='monday' AND is_active")[0][0] == 6


def test_a_permissions_failure_is_reported_and_writes_nothing(get_db):
    def denied():
        raise monday_client.MondayAccessError('cannot see board 7902650879')
    r = sync.run_sync(get_db, HUB_USERS, 'x', initial=True,
                      fetch_items=denied, fetch_users=lambda: {})
    assert not r['ok'] and r['error'] == 'monday_access'
    assert 'cannot see board' in r['message']
    assert q(get_db, "SELECT COUNT(*) FROM clients WHERE is_active")[0][0] == 4


def test_a_second_run_while_one_is_running_is_ignored(get_db):
    holder = get_db()
    hcur = holder.cursor()
    hcur.execute('SELECT pg_try_advisory_xact_lock(%s)', (sync.LOCK_KEY,))
    assert hcur.fetchone()[0]
    r = run(get_db, BASE)
    assert r['skipped'] and r['reason'] == 'already_running'
    assert q(get_db, "SELECT COUNT(*) FROM clients WHERE source='monday'")[0][0] == 0
    holder.rollback()  # releases it — a crashed run cannot leave the button stuck
    holder.close()
    assert run(get_db, BASE)['ok']


def test_last_sync_is_stored_with_who_and_counts(get_db):
    run(get_db, BASE, by='tony_cumella')
    last = sync.load_last_sync(get_db)
    assert last['by'] == 'tony_cumella' and last['created'] == 6
    assert last['duplicates'][0]['email'] == 'troy@bh.com'
    assert sync.by_label(last['by'], {'tony_cumella': {'display': 'Tony Cumella'}}) == 'Tony Cumella'


def test_schema_statements_are_safe_to_run_again(get_db):
    conn = get_db()
    cur = conn.cursor()
    for stmt in sync.SCHEMA_STATEMENTS:
        cur.execute(stmt)
    conn.commit()
    conn.close()
