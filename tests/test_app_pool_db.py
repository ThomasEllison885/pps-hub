"""The real app gives its connections back. Against a real Postgres.

Run: TEST_DATABASE_URL=postgresql://... python -m pytest tests/test_app_pool_db.py -v

Skipped unless TEST_DATABASE_URL is set, and kept in its own module because
it imports `app`, which runs the startup migrations on whatever database it
is pointed at. **Point it at a scratch database.**

Why it is worth the trouble: the pool's own tests prove that a connection
handed back is reused. They cannot prove that the Hub hands them back. Seven
of the twenty-one connections a dashboard load took were never closed by
their caller, and rather than audit 107 call sites the request that took them
returns them at teardown. If that hook stops firing, the pool drains to its
cap and every checkout after that silently falls back to a direct connection
— measured, with the hook disabled: `in_use` pinned at 10, `idle` 0, and 227
overflows across twelve loads. The app keeps working, which is exactly why
nobody would notice.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DSN = os.environ.get('TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not DSN, reason='TEST_DATABASE_URL not set')


@pytest.fixture(scope='module')
def hub():
    os.environ['DATABASE_URL'] = DSN
    os.environ.setdefault('SECRET_KEY', 'test-secret')
    import app as A  # noqa: E402  — must follow the env vars above
    import db_pool

    # Flask 3 refuses to register a route once the app has served a request,
    # so the two probe routes below are added here, before anything runs.
    @A.app.route('/__test_explode')
    def _explode():
        conn = A.get_db()
        cur = conn.cursor()
        cur.execute('SELECT 1')
        raise RuntimeError('boom')  # deliberately never closes conn

    @A.app.route('/__test_forget')
    def _forget():
        for _ in range(4):
            conn = A.get_db()
            cur = conn.cursor()
            cur.execute('SELECT 1')
            cur.fetchone()
            cur.close()
            # deliberately no conn.close() — seven per dashboard load did this
        return 'ok'

    A.app.config['PROPAGATE_EXCEPTIONS'] = False
    return A, db_pool


def _signed_in(A):
    c = A.app.test_client()
    with c.session_transaction() as s:
        s['user_key'] = 'andy_potts'
        s['role'] = 'consultant'
        s['password_epoch'] = 0
        s['epoch_checked_at'] = 9e18
    return c


def test_startup_does_not_hold_a_connection(hub):
    """`init_db` runs outside a request, so nothing can clean up after it.
    It used to end with three bare lines that an exception anywhere in the
    several hundred statements above would skip, pinning `in_use` at 1 from
    process start for the life of the worker."""
    A, db_pool = hub
    _signed_in(A).get('/dashboard')  # make sure the pool exists
    assert db_pool.stats()['in_use'] == 0


def test_a_request_returns_every_connection_it_took(hub):
    A, db_pool = hub
    c = _signed_in(A)
    c.get('/dashboard')
    before = db_pool.stats()
    for _ in range(6):
        c.get('/dashboard')
    after = db_pool.stats()
    assert after['in_use'] == 0
    assert after['created'] == before['created'], 'no new handshakes once warm'
    assert after['reused'] > before['reused']


def test_the_dashboard_stops_opening_connections_once_warm(hub):
    """The headline. It was twenty-one per load."""
    A, db_pool = hub
    c = _signed_in(A)
    c.get('/dashboard')
    created_before = db_pool.stats()['created']
    for _ in range(5):
        assert c.get('/dashboard').status_code == 200
    assert db_pool.stats()['created'] == created_before


def test_a_route_that_raises_still_gives_its_connection_back(hub):
    """teardown_request runs on the error path too — and discards rather than
    pools, because a connection whose request exploded is in a state nobody
    can vouch for."""
    A, db_pool = hub
    c = _signed_in(A)
    before = db_pool.stats()['in_use']
    resp = c.get('/__test_explode')
    assert resp.status_code == 500
    assert db_pool.stats()['in_use'] == before, 'the connection came back'


def test_a_caller_that_forgets_to_close_does_not_strand_it(hub):
    A, db_pool = hub
    c = _signed_in(A)
    assert c.get('/__test_forget').data == b'ok'
    assert db_pool.stats()['in_use'] == 0


def test_get_db_still_returns_something_cursor_shaped(hub):
    """The contract every one of the ~107 call sites relies on."""
    A, db_pool = hub
    with A.app.test_request_context('/'):
        conn = A.get_db()
        assert conn is not None
        cur = conn.cursor()
        cur.execute('SELECT 1')
        assert cur.fetchone()[0] == 1
        cur.close()
        conn.close()
        conn.close()  # idempotent, as several routes do


def test_the_kill_switch_bypasses_the_pool(hub, monkeypatch):
    """DB_POOL_DISABLED=true has to give back exactly the old behaviour: a
    real connection that really closes, and no pool involvement."""
    A, db_pool = hub
    monkeypatch.setenv('DB_POOL_DISABLED', 'true')
    before = db_pool.stats()
    with A.app.test_request_context('/'):
        conn = A.get_db()
        cur = conn.cursor()
        cur.execute('SELECT 1')
        cur.close()
        conn.close()
        assert conn.closed != 0, 'unpooled connections really close'
    after = db_pool.stats()
    assert after['reused'] == before['reused']
    assert after['in_use'] == before['in_use']
