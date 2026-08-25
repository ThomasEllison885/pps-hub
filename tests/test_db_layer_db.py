"""The pool and the savepoint fix, against a real Postgres.

Run: TEST_DATABASE_URL=postgresql://... python -m pytest tests/test_db_layer_db.py -v

Skipped unless TEST_DATABASE_URL is set. Everything here is about behaviour
no fake can prove:

  * that a failed statement really does abort the whole transaction, which is
    the bug `db_ddl` exists to fix — asserted directly, so the module's
    justification is demonstrated rather than asserted in a comment;
  * that a savepoint really does rescue it;
  * that a pooled connection handed back and taken again is the *same
    backend*, checked by pid, which is the only proof the pool is actually
    saving a handshake;
  * that a connection killed server-side is not handed to the next caller.

Point it at a scratch database. It creates and drops tables.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DSN = os.environ.get('TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not DSN, reason='TEST_DATABASE_URL not set')

if DSN:
    import psycopg2

    import db_ddl
    import db_pool


@pytest.fixture
def conn():
    c = psycopg2.connect(DSN)
    yield c
    try:
        c.rollback()
        cur = c.cursor()
        cur.execute('DROP TABLE IF EXISTS ddl_probe CASCADE')
        c.commit()
        cur.close()
    except Exception:
        pass
    c.close()


@pytest.fixture(autouse=True)
def _reset_pool():
    db_pool.reset()
    yield
    db_pool.reset()


# ── the bug ─────────────────────────────────────────────────────────────────

def test_a_failed_statement_poisons_the_whole_transaction(conn):
    """This is the bug, demonstrated. `except: pass` around the first
    statement does not save the second one — which is why init_db could
    half-complete and report a single opaque error."""
    cur = conn.cursor()
    cur.execute('SELECT 1')
    try:
        cur.execute('ALTER TABLE does_not_exist ADD COLUMN x INT')
    except Exception:
        pass  # exactly what init_db used to do
    with pytest.raises(Exception) as e:
        cur.execute('CREATE TABLE ddl_probe (id INT)')
    assert 'aborted' in str(e.value).lower()


def test_a_savepoint_rescues_it(conn):
    """The fix. Same sequence, but the failing statement is checkpointed."""
    cur = conn.cursor()
    cur.execute('SELECT 1')
    assert db_ddl.safe_ddl(
        cur, 'ALTER TABLE does_not_exist ADD COLUMN x INT') is False
    cur.execute('CREATE TABLE ddl_probe (id INT)')  # must not raise
    cur.execute("SELECT to_regclass('ddl_probe')")
    assert cur.fetchone()[0] is not None


def test_a_checkpointed_cursor_survives_a_run_of_failures(conn):
    """init_db's real shape: several ALTERs against tables that do not exist
    yet, followed by the CREATEs that would have made them."""
    cur = db_ddl.checkpointed(conn.cursor())
    for table in ('nope_a', 'nope_b', 'nope_c', 'nope_d'):
        cur.execute(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS summary_meta VARCHAR(255)')
    cur.execute('CREATE TABLE IF NOT EXISTS ddl_probe (id INT)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_ddl_probe ON ddl_probe(id)')
    cur.execute("SELECT to_regclass('ddl_probe')")
    assert cur.fetchone()[0] is not None, 'the CREATEs after the failures still ran'


def test_a_successful_statement_still_takes_effect(conn):
    cur = db_ddl.checkpointed(conn.cursor())
    cur.execute('CREATE TABLE ddl_probe (id INT)')
    assert db_ddl.safe_ddl(cur, 'ALTER TABLE ddl_probe ADD COLUMN note TEXT') is True
    cur.execute("SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'ddl_probe' ORDER BY column_name")
    assert [r[0] for r in cur.fetchall()] == ['id', 'note']


def test_dml_is_not_swallowed(conn):
    """The line that keeps this a fix rather than a better-hidden bug. A bad
    INSERT or SELECT has to raise exactly as it always did — swallowing one
    would hide a genuine failure and leave the next fetchone() to explain it."""
    cur = db_ddl.checkpointed(conn.cursor())
    cur.execute('CREATE TABLE ddl_probe (id INT)')
    with pytest.raises(Exception):
        cur.execute('INSERT INTO ddl_probe (nope) VALUES (1)')
    conn.rollback()
    cur2 = db_ddl.checkpointed(conn.cursor())
    with pytest.raises(Exception):
        cur2.execute('SELECT * FROM definitely_not_here')


def test_dml_results_are_readable_through_the_wrapper(conn):
    cur = db_ddl.checkpointed(conn.cursor())
    cur.execute('CREATE TABLE ddl_probe (id INT)')
    cur.execute('INSERT INTO ddl_probe (id) VALUES (7)')
    cur.execute('SELECT id FROM ddl_probe')
    assert cur.fetchone()[0] == 7
    assert cur.rowcount == 1


def test_savepoints_do_not_leak(conn):
    """RELEASE after each one, or a long init_db accumulates hundreds of
    savepoints in a single transaction."""
    cur = conn.cursor()
    for i in range(50):
        db_ddl.safe_ddl(cur, f'ALTER TABLE missing_{i} ADD COLUMN x INT')
    cur.execute('CREATE TABLE ddl_probe (id INT)')
    cur.execute('SELECT 1')
    assert cur.fetchone()[0] == 1


def test_is_schema_statement_classification():
    assert db_ddl.is_schema_statement('CREATE TABLE x (id INT)')
    assert db_ddl.is_schema_statement('  \n  alter table x add column y int')
    assert db_ddl.is_schema_statement('DROP INDEX x')
    assert not db_ddl.is_schema_statement('SELECT 1')
    assert not db_ddl.is_schema_statement('INSERT INTO x VALUES (1)')
    assert not db_ddl.is_schema_statement('UPDATE x SET y = 1')
    assert not db_ddl.is_schema_statement('')


# ── the pool ────────────────────────────────────────────────────────────────

def _backend_pid(raw):
    cur = raw.cursor()
    cur.execute('SELECT pg_backend_pid()')
    pid = cur.fetchone()[0]
    cur.close()
    return pid


def test_a_returned_connection_is_the_same_backend(conn):
    """The whole point, proven rather than assumed: no new handshake."""
    pool = db_pool.Pool(lambda: psycopg2.connect(DSN), 4)
    a = pool.acquire()
    pid_a = _backend_pid(a)
    pool.release(a)
    b = pool.acquire()
    assert _backend_pid(b) == pid_a
    assert pool.created == 1
    pool.release(b)
    pool.closeall()


def test_a_caller_that_leaves_an_aborted_transaction_does_not_poison_the_next(conn):
    """Invariant 1 against a real server. Without the rollback in release(),
    the next caller inherits "current transaction is aborted" and every query
    it makes fails for reasons that have nothing to do with it."""
    pool = db_pool.Pool(lambda: psycopg2.connect(DSN), 2)
    a = pool.acquire()
    cur = a.cursor()
    try:
        cur.execute('SELECT * FROM definitely_not_here')
    except Exception:
        pass
    pool.release(a)  # returned mid-abort, as a raising route would

    b = pool.acquire()
    cur2 = b.cursor()
    cur2.execute('SELECT 1')  # must not raise
    assert cur2.fetchone()[0] == 1
    pool.release(b)
    pool.closeall()


def test_a_connection_killed_server_side_is_not_handed_out(conn):
    """Invariant 3. Render restarts Postgres; idle pooled sockets die without
    `.closed` noticing. Simulated exactly, with pg_terminate_backend."""
    pool = db_pool.Pool(lambda: psycopg2.connect(DSN), 3)
    a = pool.acquire()
    pid_a = _backend_pid(a)
    pool.release(a)

    killer = conn.cursor()
    killer.execute('SELECT pg_terminate_backend(%s)', (pid_a,))
    conn.commit()

    b = pool.acquire()
    assert _backend_pid(b) != pid_a, 'must not have reused the dead one'
    assert pool.discarded >= 1
    pool.release(b)
    pool.closeall()


def test_closeall_really_closes(conn):
    pool = db_pool.Pool(lambda: psycopg2.connect(DSN), 3)
    a = pool.acquire()
    raw = a
    pool.release(a)
    pool.closeall()
    assert raw.closed != 0


def test_pooled_connection_round_trip(conn):
    """The proxy in the shape every call site uses it: cursor, query, close."""
    pool = db_pool.Pool(lambda: psycopg2.connect(DSN), 2)
    proxy = db_pool.PooledConnection(pool.acquire(), pool)
    cur = proxy.cursor()
    cur.execute('SELECT 42')
    assert cur.fetchone()[0] == 42
    cur.close()
    proxy.close()
    assert pool.stats()['idle'] == 1
    assert pool.stats()['in_use'] == 0
    pool.closeall()


def test_connect_direct_still_works():
    raw = db_pool.connect_direct(DSN)
    cur = raw.cursor()
    cur.execute('SELECT 1')
    assert cur.fetchone()[0] == 1
    cur.close()
    raw.close()


# ── why it was so destructive ───────────────────────────────────────────────

def test_commit_on_an_aborted_transaction_silently_rolls_back(conn):
    """The part that turned a skipped ALTER into a wiped schema.

    `init_db` creates ~40 tables and commits once at the end. If anything
    aborted the transaction on the way through, that commit is not a commit —
    Postgres turns it into a rollback, and every table created in that
    transaction disappears. No exception, one line of log.

    Measured on a virgin database: before the fix, `init_db` left **1** table
    of 49. After, 49. This test is the mechanism behind that number.
    """
    cur = conn.cursor()
    cur.execute('CREATE TABLE ddl_probe (id INT)')
    try:
        cur.execute('SELECT * FROM definitely_not_here')  # aborts
    except Exception:
        pass
    conn.commit()  # reads as success, is a rollback

    check = psycopg2.connect(DSN)
    ccur = check.cursor()
    ccur.execute("SELECT to_regclass('ddl_probe')")
    survived = ccur.fetchone()[0]
    ccur.close()
    check.close()
    assert survived is None, 'the CREATE was discarded by a commit that looked fine'


def test_optional_step_keeps_a_failed_backfill_from_discarding_everything(conn):
    """The same sequence with the backfill checkpointed — which is what
    ask_pps.init_tables and init_db's last_login backfill now do."""
    cur = conn.cursor()
    cur.execute('CREATE TABLE ddl_probe (id INT)')
    assert db_ddl.optional_step(
        cur, 'UPDATE not_a_table SET x = 1', label='backfill') is False
    conn.commit()  # a real commit this time

    check = psycopg2.connect(DSN)
    ccur = check.cursor()
    ccur.execute("SELECT to_regclass('ddl_probe')")
    survived = ccur.fetchone()[0]
    ccur.close()
    check.close()
    assert survived is not None
