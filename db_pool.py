"""One Postgres connection pool per gunicorn worker.

── Why this exists ─────────────────────────────────────────────────────────

`get_db()` opened a brand new connection every time it was called, and the
dashboard route calls it — directly and through about fifteen helpers —
**twenty-one times per page load**. Measured 2026-08-25 against a local
Postgres over a UNIX socket: 61ms to render, of which 44ms (72%) was nothing
but connection setup, at 2.1ms a handshake. On Render the database is over
the network with TLS, where a handshake costs several times that, so the
real figure there is worse. Peak concurrency during one dashboard render was
nine connections open at once, and seven were never explicitly closed —
released only when Python got round to collecting them.

This is finding F-05 from the 2026-08-21 review.

── Why not psycopg2.pool ───────────────────────────────────────────────────

Because it would not have fixed it, and the reason is genuinely surprising.
`AbstractConnectionPool._putconn` keeps a returned connection only when
`len(self._pool) < self.minconn`; otherwise it calls `conn.close()`. So a
`ThreadedConnectionPool(1, 10, ...)` — the obvious spelling — keeps exactly
**one** idle connection and closes every other one handed back to it. On a
page that checks out nine at once, eight are destroyed on return and the
next load opens them all again. `minconn` there is not "the floor"; it is
"how many we bother keeping". Setting `minconn == maxconn` fixes the
discarding but then opens every connection eagerly in the constructor.

`tests/test_db_pool.py::test_psycopg2_pool_discards_returned_connections`
pins that behaviour against the installed psycopg2, so nobody has to take
this paragraph on trust — and so the day it changes, we find out.

So this is a small purpose-built pool: lazy, keeps everything healthy that
comes back, and does the two things psycopg2's does not — check a connection
is still alive before handing it out, and degrade to a plain connection
instead of raising when it runs out.

── The four invariants ─────────────────────────────────────────────────────

1. **A connection handed out is always in a clean transaction state.** It is
   rolled back on release *and* validated on acquire. Callers used to get a
   brand-new connection every time, so no caller has ever had to cope with
   inheriting somebody else's aborted transaction, and none of them will
   start now. This is the invariant that makes pooling invisible to the ~107
   call sites; if you break it you will get the `init_db` failure mode
   (a poisoned transaction silently failing every later statement) spread
   across the whole app.

2. **Exhaustion is never an error.** `acquire()` returns None when the pool
   is at its cap, and `get_db()` then opens a direct connection exactly as
   it did before this module existed. The worst case is the old behaviour,
   not a 500.

3. **A dead connection is never handed out.** Render restarts Postgres;
   pooled sockets go stale and `.closed` does not necessarily notice. Every
   acquire does a `SELECT 1`. That is a round trip — but a round trip is a
   fraction of a handshake, and the alternative is one stale connection
   being recycled forever, which is far worse than the problem being fixed.

4. **Connections are never shared across a fork.** gunicorn runs without
   `--preload`, so each worker imports the app itself, after forking, and
   builds its own pool on first use. The pid guard below is a net for the
   day someone adds `--preload`; note that it *abandons* the old
   connections rather than closing them, because closing an inherited socket
   sends a Terminate to a backend the parent is still using.
"""

from __future__ import annotations

import collections
import os
import threading

import psycopg2
from psycopg2 import extensions as _ext

DEFAULT_MAX_CONNECTIONS = 10

# Peak concurrency measured on the heaviest page (the dashboard) was 9. The
# default leaves a little room above that; two workers means at most
# 2 x DB_POOL_MAX sockets against Postgres, so raise it knowing that.
_MIN_ALLOWED = 2
_MAX_ALLOWED = 50


def max_connections():
    raw = (os.environ.get('DB_POOL_MAX') or '').strip()
    try:
        n = int(raw) if raw else DEFAULT_MAX_CONNECTIONS
    except ValueError:
        n = DEFAULT_MAX_CONNECTIONS
    return max(_MIN_ALLOWED, min(n, _MAX_ALLOWED))


def pooling_enabled():
    """DB_POOL_DISABLED=true restores the old connection-per-call behaviour.

    Same reasoning as SERVICE_WORKER_DISABLED: this sits under every query in
    the Hub, and if it ever misbehaves the fix has to be an env var and a
    restart, not a deploy.
    """
    return (os.environ.get('DB_POOL_DISABLED') or '').strip().lower() not in (
        '1', 'true', 'yes')


def _healthy(raw):
    """True if this connection is usable and left in a clean state."""
    try:
        if raw.closed:
            return False
        status = raw.info.transaction_status
        if status == _ext.TRANSACTION_STATUS_UNKNOWN:
            return False
        if status != _ext.TRANSACTION_STATUS_IDLE:
            raw.rollback()
        cur = raw.cursor()
        cur.execute('SELECT 1')
        cur.fetchone()
        cur.close()
        return True
    except Exception:
        return False


def _quietly_close(raw):
    try:
        raw.close()
    except Exception:
        pass


class Pool:
    """Idle connections in a deque, a count of what is checked out, a cap."""

    def __init__(self, connect, max_size):
        self._connect = connect
        self._max = max(1, int(max_size))
        self._idle = collections.deque()
        self._out = 0
        self._lock = threading.Lock()
        self.created = 0
        self.reused = 0
        self.discarded = 0
        self.overflow = 0

    # ── checkout ────────────────────────────────────────────────────────
    def acquire(self):
        """A live connection, or None meaning "make your own".

        None is returned when the pool is at its cap. It is deliberately not
        an exception and deliberately not a block-until-free: a queue in here
        would turn a busy moment into a stalled request behind gunicorn's
        120s timeout, and the caller can always do what it did before this
        module existed.
        """
        # Bounded, because every unhealthy connection costs a round trip to
        # discover. If this many in a row are dead the database is having a
        # much bigger problem than pooling.
        for _ in range(4):
            raw = None
            with self._lock:
                if self._idle:
                    raw = self._idle.popleft()
                    self._out += 1
                elif self._out < self._max:
                    self._out += 1  # claim the slot before we let go of the lock
                else:
                    self.overflow += 1
                    return None
            if raw is not None:
                # Validated outside the lock: it is a network round trip and
                # holding the lock across it would serialise every request.
                if _healthy(raw):
                    with self._lock:
                        self.reused += 1
                    return raw
                _quietly_close(raw)
                with self._lock:
                    self._out -= 1
                    self.discarded += 1
                continue
            try:
                raw = self._connect()
            except Exception:
                with self._lock:
                    self._out -= 1
                raise
            with self._lock:
                self.created += 1
            return raw
        return None

    # ── return ──────────────────────────────────────────────────────────
    def release(self, raw, broken=False):
        """Put a connection back, or drop it if it is not fit to reuse."""
        with self._lock:
            self._out = max(0, self._out - 1)

        if raw is None:
            return
        if broken:
            _quietly_close(raw)
            with self._lock:
                self.discarded += 1
            return
        try:
            if raw.closed:
                raise RuntimeError('closed')
            status = raw.info.transaction_status
            if status == _ext.TRANSACTION_STATUS_UNKNOWN:
                raise RuntimeError('unknown transaction status')
            if status != _ext.TRANSACTION_STATUS_IDLE:
                # Invariant 1. A caller that raised mid-transaction, or that
                # simply forgot to commit, must not hand the next caller an
                # aborted transaction in which every statement fails.
                raw.rollback()
        except Exception:
            _quietly_close(raw)
            with self._lock:
                self.discarded += 1
            return

        with self._lock:
            if len(self._idle) >= self._max:
                keep = False
            else:
                self._idle.append(raw)
                keep = True
        if not keep:
            _quietly_close(raw)
            with self._lock:
                self.discarded += 1

    def stats(self):
        with self._lock:
            return {
                'idle': len(self._idle),
                'in_use': self._out,
                'max': self._max,
                'created': self.created,
                'reused': self.reused,
                'discarded': self.discarded,
                'overflow': self.overflow,
            }

    def closeall(self):
        with self._lock:
            idle, self._idle = list(self._idle), collections.deque()
        for raw in idle:
            _quietly_close(raw)


class PooledConnection:
    """A connection proxy whose close() returns it to the pool.

    Every call site in the Hub does `conn = get_db()` … `conn.close()`, so
    the pool has to hide behind exactly that shape. Everything except
    `close()` is forwarded untouched, which is why `cursor(cursor_factory=…)`,
    `commit()` and `rollback()` all behave identically to before.

    `close()` is idempotent. Some routes close in both a branch and a
    `finally`, and returning the same connection to the pool twice would let
    two callers hold it at once — the one bug in a pool that produces
    genuinely baffling symptoms.
    """

    __slots__ = ('_raw', '_pool', '_released', '_on_release')

    def __init__(self, raw, pool=None, on_release=None):
        object.__setattr__(self, '_raw', raw)
        object.__setattr__(self, '_pool', pool)
        object.__setattr__(self, '_released', False)
        object.__setattr__(self, '_on_release', on_release)

    @property
    def raw(self):
        return self._raw

    def close(self):
        if self._released:
            return
        object.__setattr__(self, '_released', True)
        if self._on_release is not None:
            try:
                self._on_release(self)
            except Exception:
                pass
        if self._pool is None:
            _quietly_close(self._raw)
        else:
            self._pool.release(self._raw)

    def discard(self):
        """Return it as unusable — for a caller that knows it is broken."""
        if self._released:
            return
        object.__setattr__(self, '_released', True)
        if self._on_release is not None:
            try:
                self._on_release(self)
            except Exception:
                pass
        if self._pool is None:
            _quietly_close(self._raw)
        else:
            self._pool.release(self._raw, broken=True)

    # psycopg2's own `with conn:` means "transaction", not "close". Nothing in
    # the Hub uses it today; this keeps the meaning identical if anything
    # starts to.
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self._raw.commit()
        else:
            try:
                self._raw.rollback()
            except Exception:
                pass
        return False

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, '_raw'), name)

    def __setattr__(self, name, value):
        setattr(self._raw, name, value)

    def __repr__(self):
        return f'<PooledConnection released={self._released} raw={self._raw!r}>'


# ── one pool per process ────────────────────────────────────────────────────

_state_lock = threading.RLock()
_state = {'pool': None, 'pid': None, 'key': None}

# Connections inherited across a fork. Never closed and never collected: a
# close() on an inherited socket sends a Terminate for a backend the parent
# is still using. See invariant 4.
_abandoned = []


def get_pool(key, connect, max_size=None):
    """The pool for this process, building it on first use.

    `key` identifies the configuration (the DSN). A change rebuilds, which
    matters only in tests — the DSN does not change at runtime in production.
    """
    with _state_lock:
        pid = os.getpid()
        pool = _state['pool']
        if pool is not None and (_state['pid'] != pid or _state['key'] != key):
            if _state['pid'] != pid:
                with pool._lock:
                    _abandoned.extend(pool._idle)
                    pool._idle = collections.deque()
            else:
                pool.closeall()
            pool = None
        if pool is None:
            pool = Pool(connect, max_size or max_connections())
            _state.update(pool=pool, pid=pid, key=key)
        return pool


def current_pool():
    with _state_lock:
        return _state['pool']


def stats():
    pool = current_pool()
    if pool is None:
        return {'enabled': pooling_enabled(), 'built': False}
    out = pool.stats()
    out['enabled'] = pooling_enabled()
    out['built'] = True
    return out


def reset():
    """Drop the pool. Tests, and nothing else."""
    with _state_lock:
        pool = _state['pool']
        if pool is not None:
            pool.closeall()
        _state.update(pool=None, pid=None, key=None)


def connect_direct(url, sslmodes=('require', 'prefer', 'allow'), timeout=10):
    """One connection, trying the SSL modes managed Postgres providers use.

    Unchanged from what `get_db` always did — it is still the fallback when
    pooling is off or the pool is at its cap, so its behaviour has to stay
    identical.
    """
    last = None
    for sslmode in sslmodes:
        try:
            return psycopg2.connect(url, sslmode=sslmode, connect_timeout=timeout)
        except Exception as e:
            last = e
    if last is not None:
        raise last
    raise RuntimeError('no sslmode attempted')
