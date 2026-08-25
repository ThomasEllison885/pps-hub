"""dashboard_summary against a real Postgres.

Run: TEST_DATABASE_URL=postgresql://... python -m pytest tests/test_dashboard_summary_db.py -v

Skipped unless TEST_DATABASE_URL is set, so the normal suite still runs
anywhere. Worth having because the two queries in dashboard_summary are the
only part of it that unit tests cannot reach, and both use syntax that is
easy to get subtly wrong:

  * `<> ALL(%s)` with a Python list — psycopg2 has to adapt the list to a
    Postgres ARRAY, and getting this wrong yields a syntax error at runtime
    on somebody's dashboard rather than at import.
  * a GROUP BY over hub_usage_events that must return nothing at all, rather
    than raise, when the table has never been created.

It creates its own schema in a throwaway database. Point it at a scratch
Postgres, never at production.
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

    import dashboard_summary as ds
    import hub_usage
    import pipeline_board


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _connect():
    return psycopg2.connect(DSN)


@pytest.fixture
def db():
    conn = _connect()
    cur = conn.cursor()
    cur.execute('DROP TABLE IF EXISTS pipeline_board_entries CASCADE')
    cur.execute('DROP TABLE IF EXISTS hub_usage_events CASCADE')
    pipeline_board.init_tables(cur)
    hub_usage.init_tables(cur)
    conn.commit()
    cur.close()
    conn.close()
    yield _connect


def _add_row(status, archived=False, pair='andy_potts'):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO pipeline_board_entries (pair_key, property_name, status, archived) '
        'VALUES (%s, %s, %s, %s)',
        (pair, 'Cedar Ridge', status, archived),
    )
    conn.commit()
    cur.close()
    conn.close()


def test_counts_only_the_rows_the_board_highlights(db):
    """COMPLETED_STATUSES is sent, awarded, cancelled. The number on the
    dashboard has to equal the number of highlighted rows on the board, so a
    person can check it by eye."""
    for status in ('new', 'needs_scope', 'draft', 'sent', 'awarded',
                   'cancelled', 'on_hold', 'declined'):
        _add_row(status)
    n = ds.pipeline_in_progress(db, 'andy_potts', pipeline_board.COMPLETED_STATUSES)
    assert n == 5, 'new, needs_scope, draft, on_hold, declined'


def test_archived_rows_are_not_counted(db):
    _add_row('new')
    _add_row('new', archived=True)
    assert ds.pipeline_in_progress(db, 'andy_potts',
                                   pipeline_board.COMPLETED_STATUSES) == 1


def test_only_this_persons_board(db):
    _add_row('new', pair='andy_potts')
    _add_row('new', pair='rachel_farler')
    _add_row('new', pair='rachel_farler')
    assert ds.pipeline_in_progress(db, 'andy_potts',
                                   pipeline_board.COMPLETED_STATUSES) == 1


def test_no_pair_key_asks_nothing(db):
    assert ds.pipeline_in_progress(db, None,
                                   pipeline_board.COMPLETED_STATUSES) is None


def test_an_empty_board_is_zero_not_none(db):
    """Zero is a real answer here; None means the read failed. build_pills
    drops both, but conflating them would hide a broken query."""
    assert ds.pipeline_in_progress(db, 'andy_potts',
                                   pipeline_board.COMPLETED_STATUSES) == 0


def test_a_missing_table_returns_none_rather_than_raising(db):
    conn = _connect()
    cur = conn.cursor()
    cur.execute('DROP TABLE pipeline_board_entries')
    conn.commit()
    cur.close()
    conn.close()
    assert ds.pipeline_in_progress(db, 'andy_potts',
                                   pipeline_board.COMPLETED_STATUSES) is None


def test_usage_features_returns_the_latest_per_feature(db):
    now = _utcnow()
    conn = _connect()
    cur = conn.cursor()
    for feature, when in (('pipeline', now - timedelta(days=3)),
                          ('pipeline', now - timedelta(hours=1)),
                          ('office_ops', now - timedelta(days=2))):
        cur.execute(
            'INSERT INTO hub_usage_events (user_key, feature, action, created_at) '
            'VALUES (%s, %s, %s, %s)', ('andy_potts', feature, 'open', when))
    cur.execute(
        'INSERT INTO hub_usage_events (user_key, feature, action, created_at) '
        'VALUES (%s, %s, %s, %s)', ('rachel_farler', 'compliance', 'open', now))
    conn.commit()
    cur.close()
    conn.close()

    rows = dict(ds.recent_usage_features(db, 'andy_potts'))
    assert set(rows) == {'pipeline', 'office_ops'}, 'never another user'
    assert rows['pipeline'] > rows['office_ops']


def test_usage_features_respects_the_window(db):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO hub_usage_events (user_key, feature, action, created_at) '
        'VALUES (%s, %s, %s, %s)',
        ('andy_potts', 'pipeline', 'open', _utcnow() - timedelta(days=400)))
    conn.commit()
    cur.close()
    conn.close()
    assert ds.recent_usage_features(db, 'andy_potts', days=60) == []


def test_usage_features_on_a_hub_that_never_created_the_table(db):
    """It is a read. A dashboard load must not create a table, and a missing
    one must produce no cards rather than a 500."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute('DROP TABLE hub_usage_events')
    conn.commit()
    cur.close()
    conn.close()
    assert ds.recent_usage_features(db, 'andy_potts') == []

    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT to_regclass('hub_usage_events')")
    assert cur.fetchone()[0] is None, 'the read must not have created it'
    cur.close()
    conn.close()
