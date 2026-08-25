"""Schema statements that cannot take the rest of the transaction with them.

── The bug this exists to kill ─────────────────────────────────────────────

`init_db` and the various `init_tables` functions are written like this:

    try:
        cur.execute('ALTER TABLE siding_estimate_log ADD COLUMN ...')
    except: pass

which reads as "this might not apply, carry on". In Postgres it does not
mean that. **A failed statement aborts the whole transaction**, and every
statement after it fails with "current transaction is aborted, commands
ignored until end of transaction block" — so `except: pass` does not
recover, it just makes the cascade silent. One skipped ALTER takes out every
CREATE TABLE that follows it, and the caller sees a single "DB init error".

Found on 2026-08-25 while smoke-testing the dashboard against a virgin
Postgres. Four ALTER statements in `init_db` target the estimate log tables
*before* those tables are created further down the same function, so on a
database that has never run the estimators, `init_db` half-completes. It has
never bitten production, where those tables have existed since an early
deploy — which is exactly why it survived this long. `ask_pps.init_tables`
has the same shape around nineteen statements in one `try`, and
`pipeline_board.init_tables` around one.

── The fix, and why it is a savepoint and not a rollback ───────────────────

Each schema statement runs inside its own `SAVEPOINT`. If it fails, only
that savepoint is rolled back; the transaction survives and the next
statement runs normally. `conn.rollback()` in the except would also clear
the aborted state — and would throw away every table `init_db` had already
created in that transaction, which is worse than the bug.

── Why only schema statements ──────────────────────────────────────────────

`checkpointed()` wraps ALTER / CREATE / DROP / COMMENT and passes everything
else straight through untouched. That line is deliberate. Schema statements
are idempotent-ish and genuinely skippable — "the column is already there"
is not a problem. An INSERT that seeds a user or a SELECT whose rows the
next line calls `fetchone()` on is neither, and quietly swallowing one would
turn this from a fix into a much better-hidden version of the same bug. DML
raises exactly as it does today.

Every skip is printed with the statement and the error, so a schema
statement that starts failing is louder now than the single opaque line it
used to produce.
"""

from __future__ import annotations

import re

_DDL_FIRST_WORD = re.compile(r'^\s*(?:--[^\n]*\n|/\*.*?\*/|\s)*([a-zA-Z]+)', re.S)
_SCHEMA_VERBS = frozenset({'ALTER', 'CREATE', 'DROP', 'COMMENT'})

SAVEPOINT_NAME = 'hub_ddl'


def is_schema_statement(sql):
    m = _DDL_FIRST_WORD.match(sql or '')
    return bool(m) and m.group(1).upper() in _SCHEMA_VERBS


def _short(sql, n=90):
    return ' '.join((sql or '').split())[:n]


def safe_ddl(cur, statement, params=None, label=''):
    """Run one schema statement inside a savepoint. True if it applied.

    Never raises. A failure is logged and skipped, and — the whole point —
    the surrounding transaction is left usable.
    """
    return run_checkpointed(cur, statement, params, label)


def optional_step(cur, statement, params=None, label=''):
    """A one-off backfill or cleanup that is allowed not to apply.

    Same machinery as `safe_ddl`, different meaning, which is why it has its
    own name: this is for the handful of DML statements in the `init_*`
    functions that migrate old rows or tidy up a retired account. They are
    genuinely best-effort — a backfill against a table that does not exist
    yet on a fresh database should be skipped, not fatal — but they were
    written as `try: ... except Exception: pass`, which in Postgres leaves
    the transaction aborted and every later statement failing.

    Found on a virgin database: `ask_pps.init_tables` backfills
    `knowledge_entries.original_content` from `knowledge_prompt_answers`
    before that table exists. The UPDATE failed, `except: pass` hid it, and
    the final `conn.commit()` on an aborted transaction became a rollback —
    so a run that printed one line of error discarded **every table it had
    just created**. One table survived, out of about forty.

    Use this ONLY for statements that are genuinely fine to skip. Ordinary
    DML — the INSERT that seeds a user row — must keep raising, and
    `checkpointed()` deliberately leaves it alone.
    """
    return run_checkpointed(cur, statement, params, label)


def run_checkpointed(cur, statement, params=None, label=''):
    try:
        cur.execute(f'SAVEPOINT {SAVEPOINT_NAME}')
    except Exception as e:
        # No transaction to take a savepoint in — an autocommit connection,
        # most likely. There is nothing to protect, so just run it.
        return _bare(cur, statement, params, label, note=f'no savepoint ({e})')

    try:
        cur.execute(statement, params) if params else cur.execute(statement)
    except Exception as e:
        try:
            cur.execute(f'ROLLBACK TO SAVEPOINT {SAVEPOINT_NAME}')
            cur.execute(f'RELEASE SAVEPOINT {SAVEPOINT_NAME}')
        except Exception:
            pass
        print(f'schema: skipped {label or _short(statement)} '
              f'-- {str(e).strip().splitlines()[0][:160]}')
        return False

    try:
        cur.execute(f'RELEASE SAVEPOINT {SAVEPOINT_NAME}')
    except Exception:
        pass
    return True


def _bare(cur, statement, params, label, note=''):
    try:
        cur.execute(statement, params) if params else cur.execute(statement)
        return True
    except Exception as e:
        print(f'schema: skipped {label or _short(statement)} '
              f'-- {str(e).strip().splitlines()[0][:160]}'
              + (f' [{note}]' if note else ''))
        return False


class CheckpointedCursor:
    """A cursor whose schema statements each get their own savepoint.

    Everything that is not a schema statement — every SELECT, INSERT, UPDATE
    — is handed to the real cursor untouched and raises exactly as before,
    and every attribute other than `execute` (`fetchone`, `fetchall`,
    `rowcount`, `close`, …) is the real cursor's. That is what lets an
    existing `init_tables` adopt this by changing one line at the top rather
    than being rewritten.
    """

    __slots__ = ('_cur',)

    def __init__(self, cur):
        object.__setattr__(self, '_cur', cur)

    @property
    def raw(self):
        return self._cur

    def execute(self, statement, params=None):
        if is_schema_statement(statement):
            return safe_ddl(self._cur, statement, params)
        if params is not None:
            return self._cur.execute(statement, params)
        return self._cur.execute(statement)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, '_cur'), name)

    def __setattr__(self, name, value):
        setattr(self._cur, name, value)

    def __iter__(self):
        return iter(self._cur)

    def __enter__(self):
        self._cur.__enter__()
        return self

    def __exit__(self, *a):
        return self._cur.__exit__(*a)


def checkpointed(cur):
    """Wrap a cursor so schema statements cannot poison the transaction.

    Idempotent: wrapping an already-wrapped cursor returns it unchanged, so
    a function that does this at the top is safe to call with either.
    """
    if isinstance(cur, CheckpointedCursor):
        return cur
    return CheckpointedCursor(cur)
