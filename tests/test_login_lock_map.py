"""Bulk lockout lookup for the Admin roster.

Run: python -m pytest tests/test_login_lock_map.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auth_helpers
from auth_helpers import login_lock_map, MAX_LOGIN_FAILURES


class _Conn:
    """Counts connections, because that is the thing under test."""

    opened = 0

    def __init__(self, rows=(), raises=False):
        self.rows, self.raises = list(rows), raises
        self.queries = []
        self.closed = False
        _Conn.opened += 1

    def cursor(self, *a, **k):
        conn = self

        class C:
            def execute(s, sql, args=None):
                conn.queries.append(' '.join(sql.split()))
                if conn.raises:
                    raise RuntimeError('relation "login_attempts" does not exist')

            def fetchall(s):
                return conn.rows

            def close(s):
                pass

        return C()

    def close(self):
        self.closed = True


def _factory(conn):
    return lambda: conn


def test_the_whole_roster_costs_one_connection():
    """This is the entire reason the function exists. is_login_locked opens its
    own connection, and the Admin page called it once per person inside a loop —
    fourteen Postgres connections and fourteen TLS handshakes to render a table.
    """
    _Conn.opened = 0
    conn = _Conn(rows=[('andy_potts', MAX_LOGIN_FAILURES, 12.0)])
    login_lock_map(_factory(conn))
    assert _Conn.opened == 1
    assert len(conn.queries) == 1
    assert 'GROUP BY user_key' in conn.queries[0]


def test_only_people_with_recent_failures_appear():
    """Callers read a missing key as 'not locked'. Storing a row for everyone
    clean would make the map thirteen entries of nothing."""
    conn = _Conn(rows=[('andy_potts', 2, None)])
    m = login_lock_map(_factory(conn))
    assert set(m) == {'andy_potts'}
    assert m['andy_potts'] == (False, 2, None), 'two failures is not a lockout'


def test_lockout_threshold_and_minutes_left():
    conn = _Conn(rows=[
        ('andy_potts', MAX_LOGIN_FAILURES, 12.2),
        ('ben_ramsey', MAX_LOGIN_FAILURES - 1, 9.0),
    ])
    m = login_lock_map(_factory(conn))
    locked, fails, mins = m['andy_potts']
    assert locked is True and fails == MAX_LOGIN_FAILURES
    assert mins == 13, 'partial minutes round up — 12.2 left means 13, not 12'
    assert m['ben_ramsey'][0] is False
    assert m['ben_ramsey'][2] is None, 'no countdown for someone who is not locked'


def test_a_lock_with_no_expiry_reported_still_reads_as_locked():
    """Better to show the lock and let Thomas press Unlock than to hide it
    because the interval arithmetic returned NULL."""
    conn = _Conn(rows=[('andy_potts', MAX_LOGIN_FAILURES, None)])
    locked, fails, mins = login_lock_map(_factory(conn))['andy_potts']
    assert locked is True and mins is None


def test_database_down_reads_as_nobody_locked_out():
    """Same failure direction is_login_locked already chose. A column that
    wrongly says 'locked' sends Thomas chasing a problem that does not exist;
    a missed lock costs one confused message."""
    assert login_lock_map(lambda: None) == {}


def test_a_query_error_does_not_take_the_admin_page_down():
    conn = _Conn(raises=True)
    assert login_lock_map(_factory(conn)) == {}
    assert conn.closed, 'the connection is released even on the error path'


def test_connection_is_closed_on_the_happy_path_too():
    conn = _Conn(rows=[])
    login_lock_map(_factory(conn))
    assert conn.closed


def test_it_agrees_with_is_login_locked_on_the_same_counts():
    """Two implementations of one rule is how they drift. Pin them together."""
    for count in (0, 1, MAX_LOGIN_FAILURES - 1, MAX_LOGIN_FAILURES, MAX_LOGIN_FAILURES + 3):
        bulk = login_lock_map(_factory(_Conn(rows=[('andy_potts', count, 5.0)])))
        single_locked = count >= MAX_LOGIN_FAILURES
        assert bulk.get('andy_potts', (False, 0, None))[0] is single_locked
