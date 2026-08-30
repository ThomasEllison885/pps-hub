"""The startup migration that rewrites short consultant keys, for real.

Run: TEST_DATABASE_URL=postgresql://... python -m pytest tests/test_key_normalisation_db.py -v

Kept in its own module because it imports `app`, which runs the startup
migrations against whatever database it is pointed at. **Point it at a scratch
database.**

── What this is for ────────────────────────────────────────────────────────

`/log-proposal` has written resolved keys since 093244f (2026-08-29). This is
about everything before that: months of proposals filed under 'rachel' because
the consultant opened the tool from a bookmark, had no SSO session, and the
form's dropdown value went into `generated_by` unmapped.

Every reader resolves aliases now, so the Hub is already correct without this
migration. What the migration buys is that it stops being five readers' job to
stay correct — the sixth one, written next month by someone who has not read
`user_aliases.py`, gets the right answer straight out of the column.

Which is exactly why the tests below check the *data*, not the readers. If the
statement silently matched nothing — a lazily-created table, a typo in a column
name, `optional_step` swallowing an error the way it is designed to — every
page on the Hub would still look right, because the readers would go on
resolving. That is a migration that quietly does nothing for months.

The other half is the last_login backfill directly beneath it, which is the
remaining half of F-03: bookmark-logged work never moved `last_login`, so the
roster reported people as unseen while their proposals sat in the log.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DSN = os.environ.get('TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not DSN, reason='TEST_DATABASE_URL not set')

if DSN:
    import psycopg2

    import user_aliases

LOG_TABLES = ('proposal_log', 'ppm_log', 'subscope_log', 'site_visit_log')


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture(scope='module')
def hub():
    os.environ['DATABASE_URL'] = DSN
    os.environ.setdefault('SECRET_KEY', 'test-secret')
    import app as A  # noqa: E402 — must follow the env vars above
    return A


@pytest.fixture
def db():
    conn = psycopg2.connect(DSN)
    cur = conn.cursor()
    for table in LOG_TABLES:
        cur.execute(f'DROP TABLE IF EXISTS {table} CASCADE')
        cur.execute(f'''CREATE TABLE {table} (
            id SERIAL PRIMARY KEY, generated_by VARCHAR(100),
            generated_at TIMESTAMP)''')
    conn.commit()
    cur.close()
    conn.close()
    yield lambda: psycopg2.connect(DSN)


def _rows(get_db, table='proposal_log'):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f'SELECT generated_by FROM {table} ORDER BY id')
    out = [r[0] for r in cur.fetchall()]
    cur.close()
    conn.close()
    return out


def _insert(get_db, table, pairs):
    conn = get_db()
    cur = conn.cursor()
    cur.executemany(
        f'INSERT INTO {table} (generated_by, generated_at) VALUES (%s, %s)',
        pairs)
    conn.commit()
    cur.close()
    conn.close()


def _last_login(get_db, user_key):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT last_login FROM hub_users WHERE user_key = %s', (user_key,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else None


# ── the rewrite ─────────────────────────────────────────────────────────────

def test_short_keys_become_roster_keys(hub, db):
    now = _utcnow()
    _insert(db, 'proposal_log', [('rachel', now), ('andy', now), ('tony', now)])
    hub.init_db()
    assert _rows(db) == ['rachel_farler', 'andy_potts', 'tony_cumella']


def test_it_runs_across_every_scored_table_not_just_proposals(hub, db):
    """The table list comes from weekly_recap.SCORED_SOURCES so a new
    deliverable log cannot be added to the Hub and quietly skipped here."""
    now = _utcnow()
    for table in LOG_TABLES:
        _insert(db, table, [('rachel', now)])
    hub.init_db()
    for table in LOG_TABLES:
        assert _rows(db, table) == ['rachel_farler'], f'{table} was not migrated'


def test_it_leaves_everything_it_does_not_recognise_alone(hub, db):
    """`resolve` does not guess and neither does this. 'unknown' is what the
    PPM and TPS loggers write when there is no session, and a departed
    employee's key is history, not a mistake — inventing owners for either
    would be worse than leaving the work unattributed."""
    now = _utcnow()
    _insert(db, 'proposal_log',
            [('unknown', now), ('derek_kidney', now), ('stephanie_shrout', now),
             ('', now)])
    hub.init_db()
    assert _rows(db) == ['unknown', 'derek_kidney', 'stephanie_shrout', '']


def test_running_it_twice_changes_nothing(hub, db):
    """It runs on every boot, in every gunicorn worker."""
    now = _utcnow()
    _insert(db, 'proposal_log', [('rachel', now), ('rachel_farler', now)])
    hub.init_db()
    first = _rows(db)
    hub.init_db()
    hub.init_db()
    assert _rows(db) == first == ['rachel_farler', 'rachel_farler']


def test_a_missing_table_does_not_stop_the_others(hub, db):
    """Four of the nine scored tables are created lazily and genuinely may not
    exist. Each rewrite is its own optional_step for that reason; if they
    shared one, the first absent table would take the rest with it."""
    conn = db()
    cur = conn.cursor()
    cur.execute('DROP TABLE IF EXISTS siding_estimate_log CASCADE')
    conn.commit()
    cur.close()
    conn.close()
    _insert(db, 'proposal_log', [('rachel', _utcnow())])
    hub.init_db()
    assert _rows(db) == ['rachel_farler']


# ── and the backfill on top of it ───────────────────────────────────────────

def test_bookmark_logged_work_now_moves_last_login(hub, db):
    """The remaining half of F-03. Before this, a consultant could file
    proposals all week and the roster would report they had not been seen —
    the backfill joined on the raw key and 'rachel' matched no hub_users row.
    """
    if 'rachel_farler' not in hub.USERS:
        pytest.skip('rachel_farler is not on the roster any more')
    recent = _utcnow() - timedelta(hours=2)
    _insert(db, 'proposal_log', [('rachel', recent)])
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE hub_users SET last_login = %s WHERE user_key = %s",
                (_utcnow() - timedelta(days=40), 'rachel_farler'))
    conn.commit()
    cur.close()
    conn.close()

    hub.init_db()
    seen = _last_login(db, 'rachel_farler')
    assert seen is not None
    assert abs((seen - recent).total_seconds()) < 5, (
        'last_login did not follow the proposal that was logged under a short key')


def test_the_backfill_does_not_drag_last_login_backwards(hub, db):
    """Somebody who signed in this morning and whose newest logged deliverable
    is from last month must not be reported as last seen last month."""
    if 'rachel_farler' not in hub.USERS:
        pytest.skip('rachel_farler is not on the roster any more')
    _insert(db, 'proposal_log', [('rachel', _utcnow() - timedelta(days=30))])
    fresh = _utcnow() - timedelta(minutes=5)
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE hub_users SET last_login = %s WHERE user_key = %s",
                (fresh, 'rachel_farler'))
    conn.commit()
    cur.close()
    conn.close()

    hub.init_db()
    assert abs((_last_login(db, 'rachel_farler') - fresh).total_seconds()) < 5


def test_the_backfill_is_independent_of_the_migration(hub, db):
    """The two are deliberately not chained. `optional_step` swallows failures
    by design, so a rewrite that could not run on one table must not silently
    take the backfill down with it — both resolve aliases on their own."""
    import ast
    with open(os.path.join(ROOT, 'app.py')) as fh:
        tree = ast.parse(fh.read())

    # The statement is built as an f-string, so "does it resolve" means: does
    # its SQL interpolate a name, and was that name assigned from sql_resolve.
    resolved_names = {
        t.id
        for node in ast.walk(tree) if isinstance(node, ast.Assign)
        for t in node.targets if isinstance(t, ast.Name)
        if isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr == 'sql_resolve'
    }
    assert resolved_names, 'nothing in app.py is built from sql_resolve'

    backfills = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and any(kw.arg == 'label'
                and getattr(kw.value, 'value', None) == 'last_login backfill'
                for kw in node.keywords)
    ]
    assert len(backfills) == 1, 'expected exactly one last_login backfill step'
    sql_arg = backfills[0].args[-1]
    interpolated = {
        n.id for n in ast.walk(sql_arg) if isinstance(n, ast.Name)
    }
    assert interpolated & resolved_names, (
        'the backfill reads generated_by raw again and is relying on the '
        'migration above having succeeded')
