"""The connection pool, with no database.

Run: python -m pytest tests/test_db_pool.py -v

These use a fake connection so they run anywhere. The parts that only a real
Postgres can prove — that a savepoint really does rescue an aborted
transaction, that a returned connection is genuinely reusable — are in
tests/test_db_layer_db.py, which skips unless TEST_DATABASE_URL is set.

The load-bearing test here is the one about psycopg2's own pool. This module
exists *because* `psycopg2.pool` closes returned connections beyond
`minconn`, which is surprising enough that the claim needs pinning rather
than believing.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db_pool
from psycopg2 import extensions as pg_ext


class FakeConn:
    """Enough of a psycopg2 connection for the pool to make decisions about."""

    def __init__(self, status=pg_ext.TRANSACTION_STATUS_IDLE, alive=True):
        self.closed = 0
        self._status = status
        self.alive = alive
        self.rollbacks = 0
        self.selects = 0

    # psycopg2 exposes transaction_status via conn.info
    class _Info:
        def __init__(self, outer):
            self._outer = outer

        @property
        def transaction_status(self):
            return self._outer._status

    @property
    def info(self):
        return FakeConn._Info(self)

    def set_status(self, status):
        self._status = status

    def rollback(self):
        self.rollbacks += 1
        self._status = pg_ext.TRANSACTION_STATUS_IDLE

    def cursor(self):
        conn = self

        class Cur:
            def execute(self, sql, params=None):
                if not conn.alive:
                    raise RuntimeError('server closed the connection')
                conn.selects += 1

            def fetchone(self):
                return (1,)

            def close(self):
                pass

        return Cur()

    def close(self):
        self.closed = 1


@pytest.fixture(autouse=True)
def _clean():
    db_pool.reset()
    yield
    db_pool.reset()


def _pool(max_size=3, conns=None):
    made = conns if conns is not None else []

    def connect():
        c = FakeConn()
        made.append(c)
        return c

    p = db_pool.Pool(connect, max_size)
    p.made = made
    return p


# ── the reason this module is hand-rolled ───────────────────────────────────

def test_psycopg2_pool_discards_returned_connections():
    """psycopg2's pool keeps a returned connection only while the idle list is
    shorter than *minconn* — otherwise `_putconn` calls `conn.close()`.

    So ThreadedConnectionPool(1, 10) keeps exactly one connection and closes
    every other one handed back, which on a page that checks out nine at once
    means eight are destroyed on return and reopened next load. That is the
    behaviour db_pool.py exists to avoid, and this pins it: if a future
    psycopg2 changes it, this test fails and the custom pool can be retired.
    """
    import inspect

    from psycopg2 import pool as pg_pool

    src = inspect.getsource(pg_pool.AbstractConnectionPool._putconn)
    assert 'len(self._pool) < self.minconn' in src
    assert 'conn.close()' in src


# ── acquire / release ───────────────────────────────────────────────────────

def test_a_returned_connection_is_reused():
    p = _pool()
    a = p.acquire()
    p.release(a)
    b = p.acquire()
    assert b is a
    assert p.created == 1 and p.reused == 1


def test_connections_are_created_up_to_the_cap():
    p = _pool(max_size=3)
    held = [p.acquire() for _ in range(3)]
    assert len({id(c) for c in held}) == 3
    assert p.created == 3


def test_exhaustion_returns_none_rather_than_raising():
    """Invariant 2. get_db() then opens a direct connection, which is exactly
    what it did before pooling existed. A busy moment must not become an
    exception, and must not become a queue behind gunicorn's 120s timeout."""
    p = _pool(max_size=2)
    p.acquire()
    p.acquire()
    assert p.acquire() is None
    assert p.stats()['overflow'] == 1


def test_releasing_frees_the_slot():
    p = _pool(max_size=1)
    a = p.acquire()
    assert p.acquire() is None
    p.release(a)
    assert p.acquire() is not None


def test_a_connection_in_a_transaction_is_rolled_back_on_release():
    """Invariant 1. No caller has ever had to cope with inheriting somebody
    else's open transaction, and none of them will start now."""
    p = _pool()
    a = p.acquire()
    a.set_status(pg_ext.TRANSACTION_STATUS_INTRANS)
    p.release(a)
    assert a.rollbacks == 1
    assert a.closed == 0, 'still reusable, just reset'


def test_a_connection_in_an_aborted_transaction_is_rolled_back():
    p = _pool()
    a = p.acquire()
    a.set_status(pg_ext.TRANSACTION_STATUS_INERROR)
    p.release(a)
    assert a.rollbacks == 1
    assert p.acquire() is a


def test_an_unknown_status_connection_is_dropped_not_pooled():
    """UNKNOWN means the socket is gone. Handing that to the next caller
    would turn one lost connection into every subsequent request failing."""
    p = _pool()
    a = p.acquire()
    a.set_status(pg_ext.TRANSACTION_STATUS_UNKNOWN)
    p.release(a)
    assert a.closed == 1
    assert p.stats()['discarded'] == 1
    assert p.acquire() is not a


def test_a_broken_release_is_not_pooled():
    p = _pool()
    a = p.acquire()
    p.release(a, broken=True)
    assert a.closed == 1
    assert p.acquire() is not a


def test_a_dead_connection_is_not_handed_out():
    """Invariant 3. Render restarts Postgres and pooled sockets go stale
    without `.closed` noticing, so acquire proves liveness with a SELECT 1."""
    p = _pool()
    a = p.acquire()
    p.release(a)
    a.alive = False  # server went away while it sat idle
    b = p.acquire()
    assert b is not a
    assert a.closed == 1
    assert p.stats()['discarded'] == 1


def test_liveness_check_actually_queries():
    p = _pool()
    a = p.acquire()
    p.release(a)
    p.acquire()
    assert a.selects >= 1, 'a checkout that does not query cannot detect a dead socket'


def test_a_run_of_dead_connections_gives_up_rather_than_spinning():
    p = _pool(max_size=8)
    dead = []
    for _ in range(6):
        c = p.acquire()
        dead.append(c)
    for c in dead:
        p.release(c)
        c.alive = False
    # Never loops forever; either returns a fresh connection or None.
    got = p.acquire()
    assert got is None or got.alive


def test_idle_list_is_capped():
    p = _pool(max_size=2)
    held = [p.acquire(), p.acquire()]
    for c in held:
        p.release(c)
    assert p.stats()['idle'] == 2
    p.release(FakeConn())  # a stray from somewhere
    assert p.stats()['idle'] <= 2


def test_a_failed_connect_does_not_leak_the_slot():
    """If creating a connection raises, the slot it claimed has to come back
    or the pool bleeds capacity every time the database blinks."""
    calls = {'n': 0}

    def connect():
        calls['n'] += 1
        raise RuntimeError('down')

    p = db_pool.Pool(connect, 2)
    for _ in range(4):
        with pytest.raises(RuntimeError):
            p.acquire()
    assert p.stats()['in_use'] == 0
    assert calls['n'] == 4, 'still trying, not permanently exhausted'


# ── PooledConnection ────────────────────────────────────────────────────────

def test_close_returns_to_the_pool_instead_of_closing():
    p = _pool()
    raw = p.acquire()
    conn = db_pool.PooledConnection(raw, p)
    conn.close()
    assert raw.closed == 0
    assert p.stats()['idle'] == 1


def test_close_is_idempotent():
    """Several routes close in a branch and again in a `finally`. Returning
    the same connection twice would let two callers hold it at once."""
    p = _pool()
    raw = p.acquire()
    conn = db_pool.PooledConnection(raw, p)
    conn.close()
    conn.close()
    conn.close()
    assert p.stats()['idle'] == 1
    assert p.stats()['in_use'] == 0


def test_discard_drops_the_connection():
    p = _pool()
    raw = p.acquire()
    conn = db_pool.PooledConnection(raw, p)
    conn.discard()
    assert raw.closed == 1
    assert p.stats()['idle'] == 0


def test_an_unpooled_proxy_really_closes():
    """The fallback path — pooling disabled, or the pool at its cap — has to
    behave exactly like the old get_db."""
    raw = FakeConn()
    conn = db_pool.PooledConnection(raw, None)
    conn.close()
    assert raw.closed == 1


def test_attributes_are_forwarded():
    raw = FakeConn()
    conn = db_pool.PooledConnection(raw, None)
    assert conn.cursor() is not None
    conn.rollback()
    assert raw.rollbacks == 1


def test_on_release_fires_once():
    seen = []
    p = _pool()
    conn = db_pool.PooledConnection(p.acquire(), p, on_release=seen.append)
    conn.close()
    conn.close()
    assert len(seen) == 1


def test_a_throwing_on_release_still_returns_the_connection():
    """The teardown bookkeeping must never be able to strand a connection."""
    def boom(_):
        raise RuntimeError('bookkeeping broke')

    p = _pool()
    raw = p.acquire()
    conn = db_pool.PooledConnection(raw, p, on_release=boom)
    conn.close()
    assert p.stats()['idle'] == 1


# ── process-level pool ──────────────────────────────────────────────────────

def test_get_pool_is_per_process_and_stable():
    p1 = db_pool.get_pool('dsn-a', lambda: FakeConn())
    p2 = db_pool.get_pool('dsn-a', lambda: FakeConn())
    assert p1 is p2


def test_changing_the_dsn_rebuilds():
    p1 = db_pool.get_pool('dsn-a', lambda: FakeConn())
    p2 = db_pool.get_pool('dsn-b', lambda: FakeConn())
    assert p1 is not p2


def test_a_forked_pool_is_rebuilt_and_its_connections_abandoned(monkeypatch):
    """Invariant 4. Closing a connection inherited across a fork sends a
    Terminate for a backend the parent is still using, so the child rebuilds
    and leaves the old sockets alone rather than closing them."""
    p1 = db_pool.get_pool('dsn-a', lambda: FakeConn())
    raw = p1.acquire()
    p1.release(raw)
    assert p1.stats()['idle'] == 1

    fake_pid = os.getpid() + 1
    monkeypatch.setattr(db_pool.os, 'getpid', lambda: fake_pid)
    p2 = db_pool.get_pool('dsn-a', lambda: FakeConn())
    assert p2 is not p1
    assert raw.closed == 0, 'an inherited socket must not be closed'
    assert raw in db_pool._abandoned


def test_max_connections_reads_the_env(monkeypatch):
    monkeypatch.setenv('DB_POOL_MAX', '25')
    assert db_pool.max_connections() == 25
    monkeypatch.setenv('DB_POOL_MAX', 'nonsense')
    assert db_pool.max_connections() == db_pool.DEFAULT_MAX_CONNECTIONS
    monkeypatch.setenv('DB_POOL_MAX', '9999')
    assert db_pool.max_connections() == 50, 'clamped'
    monkeypatch.delenv('DB_POOL_MAX')
    assert db_pool.max_connections() == db_pool.DEFAULT_MAX_CONNECTIONS


def test_the_kill_switch(monkeypatch):
    assert db_pool.pooling_enabled() is True
    for value in ('true', 'TRUE', '1', 'yes'):
        monkeypatch.setenv('DB_POOL_DISABLED', value)
        assert db_pool.pooling_enabled() is False
    monkeypatch.setenv('DB_POOL_DISABLED', 'no')
    assert db_pool.pooling_enabled() is True


def test_stats_before_the_pool_is_built():
    assert db_pool.stats() == {'enabled': True, 'built': False}
