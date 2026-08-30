"""The adoption view's two queries, against a real Postgres.

Run: TEST_DATABASE_URL=postgresql://... python -m pytest tests/test_hub_adoption_db.py -v

The rollups are pure and covered next door. These are the parts unit tests
cannot reach, and both have a failure mode that is quiet rather than loud:

  * `fetch_usage` reads a table it must never create. If it started calling
    `ensure_tables` the page would work perfectly and a Hub where nobody had
    opened anything would silently gain a table.
  * `last_produced` walks every table in `weekly_recap.SCORED_SOURCES`, and
    several of those are created lazily — a Hub that has never generated a
    painting estimate genuinely has no `painting_estimate_log`. Postgres puts
    the whole connection into a failed state after an error, so without the
    rollback in the loop the first missing table would silently zero out
    every table after it.
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

    import hub_adoption as ha
    import hub_usage

USERS = {
    'andy_potts': {'display': 'Andy Potts', 'role': 'consultant', 'tier': 'team'},
    'phil_miller': {'display': 'Phil Miller', 'role': 'pm', 'tier': 'team'},
}


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def db():
    conn = psycopg2.connect(DSN)
    cur = conn.cursor()
    cur.execute('DROP TABLE IF EXISTS hub_usage_events CASCADE')
    cur.execute('DROP TABLE IF EXISTS proposal_log CASCADE')
    conn.commit()
    cur.close()
    conn.close()
    yield lambda: psycopg2.connect(DSN)


def _make_usage(get_db):
    conn = get_db()
    cur = conn.cursor()
    hub_usage.init_tables(cur)
    conn.commit()
    cur.close()
    conn.close()


def _event(get_db, user, feature, action='open', when=None):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO hub_usage_events (user_key, feature, action, created_at) '
        'VALUES (%s, %s, %s, %s)',
        (user, feature, action, when or _utcnow()))
    conn.commit()
    cur.close()
    conn.close()


# ── fetch_usage ─────────────────────────────────────────────────────────────

def test_a_missing_table_reads_as_empty_and_stays_missing(db):
    """Not an error, and — the important half — not a new table either."""
    assert ha.fetch_usage(db) == []
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT to_regclass('public.hub_usage_events')")
    assert cur.fetchone()[0] is None, 'reading the page created the table'
    cur.close()
    conn.close()


def test_events_come_back_oldest_first(db):
    _make_usage(db)
    now = _utcnow()
    _event(db, 'andy_potts', 'pipeline', when=now - timedelta(hours=2))
    _event(db, 'phil_miller', 'guide', when=now - timedelta(hours=1))
    rows = ha.fetch_usage(db, since=now - timedelta(days=1))
    assert [r['feature'] for r in rows] == ['pipeline', 'guide']
    assert rows[0]['user_key'] == 'andy_potts'
    assert rows[0]['action'] == 'open'


def test_the_window_is_honoured(db):
    _make_usage(db)
    now = _utcnow()
    _event(db, 'andy_potts', 'pipeline', when=now - timedelta(days=40))
    _event(db, 'andy_potts', 'guide', when=now - timedelta(hours=1))
    rows = ha.fetch_usage(db, since=now - timedelta(days=7))
    assert [r['feature'] for r in rows] == ['guide'], 'the old event leaked in'


def test_events_before_instrumentation_are_not_counted(db):
    """Three features recorded before 2026-08-26 and seventeen did not, so
    reaching back past it mixes two different worlds."""
    _make_usage(db)
    _event(db, 'andy_potts', 'pipeline',
           when=ha.instrumented_from() - timedelta(hours=1))
    _event(db, 'andy_potts', 'guide', when=ha.instrumented_from() + timedelta(hours=1))
    rows = ha.fetch_usage(db)
    assert [r['feature'] for r in rows] == ['guide']


# ── last_produced ───────────────────────────────────────────────────────────

def test_missing_deliverable_tables_do_not_zero_out_the_rest(db):
    """The rollback in the loop is what makes this true. Without it the first
    lazily-created table that does not exist yet takes every later one with
    it, and the page reports that nobody has produced anything."""
    conn = db()
    cur = conn.cursor()
    cur.execute('''CREATE TABLE proposal_log (
        id SERIAL PRIMARY KEY, generated_by VARCHAR(100),
        generated_at TIMESTAMP)''')
    newest = _utcnow() - timedelta(days=1)
    cur.execute('INSERT INTO proposal_log (generated_by, generated_at) '
                'VALUES (%s, %s), (%s, %s)',
                ('andy_potts', newest - timedelta(days=5),
                 'andy_potts', newest))
    conn.commit()
    cur.close()
    conn.close()

    produced, unmatched = ha.last_produced(db, USERS)
    assert 'andy_potts' in produced, (
        'a missing table earlier in SCORED_SOURCES swallowed the one that exists')
    assert produced['andy_potts'] == newest, 'should be the newest, not the first'
    assert 'phil_miller' not in produced
    assert unmatched == {}


def test_people_outside_the_roster_are_reported_not_silently_dropped(db):
    """A departed employee's rows stay in the tables and should not appear as
    a person on a page about the current team — but they must be *counted*.

    Filtering them away silently is what hid Rachel: her proposals were
    written under 'rachel' rather than 'rachel_farler', matched no roster key,
    and disappeared. The page now shows anything it could not attribute, so
    the next time a live person falls off the roster match it says so instead
    of reporting that they did nothing.
    """
    conn = db()
    cur = conn.cursor()
    cur.execute('''CREATE TABLE proposal_log (
        id SERIAL PRIMARY KEY, generated_by VARCHAR(100),
        generated_at TIMESTAMP)''')
    cur.execute('INSERT INTO proposal_log (generated_by, generated_at) '
                'VALUES (%s, %s), (%s, %s)',
                ('derek_kidney', _utcnow(), 'rachel', _utcnow()))
    conn.commit()
    cur.close()
    conn.close()
    produced, unmatched = ha.last_produced(db, USERS)
    assert produced == {}, 'neither is on this two-person roster'
    assert unmatched == {'derek_kidney': 1, 'rachel': 1}


def test_a_short_consultant_key_finds_its_person(db):
    """The bug itself, end to end against a real table."""
    conn = db()
    cur = conn.cursor()
    cur.execute('''CREATE TABLE proposal_log (
        id SERIAL PRIMARY KEY, generated_by VARCHAR(100),
        generated_at TIMESTAMP)''')
    cur.execute('INSERT INTO proposal_log (generated_by, generated_at) '
                'VALUES (%s, %s)', ('rachel', _utcnow()))
    conn.commit()
    cur.close()
    conn.close()
    roster = dict(USERS, rachel_farler={'display': 'Rachel Farler',
                                        'role': 'consultant', 'tier': 'team'})
    produced, unmatched = ha.last_produced(db, roster)
    assert 'rachel_farler' in produced, 'the alias never reached the person'
    assert unmatched == {}


# ── the whole payload ───────────────────────────────────────────────────────

def test_build_survives_a_database_with_nothing_in_it(db):
    payload = ha.build(db, USERS)
    assert payload['events'] == 0
    assert len(payload['people']) == len(USERS)
    assert payload['untouched'] and len(payload['untouched']) == len(payload['features'])
    assert payload['guide']['read_count'] == 0
    assert payload['weeks'], 'the current week is always drawn'
