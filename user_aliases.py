"""Short consultant keys → roster keys, in one place.

── The bug this exists to fix (2026-08-29) ─────────────────────────────────

Thomas: "I know Rachel has generated proposals but she shows no activity."

The proposal tool sends `generated_by` when it logs a proposal to the Hub:

    'generated_by': user_key or consultant_key

`user_key` is the SSO session — set when someone reaches the tool by clicking
through from the Hub. Reach it by bookmark instead and there is no session, so
it falls back to `consultant_key`, which is the value of the consultant
dropdown on the form: **`'rachel'`, not `'rachel_farler'`**.

Note the line right below it in that same payload:

    'consultant_key': CONSULTANT_KEY_MAP.get(consultant_key, consultant_key)

The mapping was applied to `consultant_key` and not to `generated_by`. One
line apart.

Every consumer then filters `if user_key in users` — `weekly_recap`,
`hub_adoption`, Team View — and `'rachel'` is not a roster key, so the row was
**silently dropped**. Not mis-attributed. Dropped. Which is why Rachel showed
no activity, and why her proposals have not been counted in the Monday recap
either. That email is the company-wide leaderboard.

── Why the map lives here ──────────────────────────────────────────────────

It already existed twice: `_CONSULTANT_KEY_ALIASES` in `app.py` and
`CONSULTANT_KEY_MAP` in the proposal tool's `app.py`. Two copies of a mapping
that must agree, in two repositories, is how they stop agreeing — and this bug
is what that looks like when the two copies are applied to different fields.

One copy, imported by everything on this side. The proposal tool keeps its own
(different repo, no shared import) but now sends an already-resolved key, so
the Hub's copy is a safety net rather than the only thing standing between a
proposal and the person who wrote it.

── The rule ────────────────────────────────────────────────────────────────

`resolve` maps a known alias to a roster key and **leaves everything else
alone**. It does not guess. `'unknown'` — what the PPM and TPS loggers write
when there is no session — stays `'unknown'` and shows up as unattributed
work, because inventing an owner for it would be worse than admitting nobody
knows.
"""

from __future__ import annotations

# Short form → roster key. Mirrors CONSULTANT_KEY_MAP in the proposal tool.
# Consultants only: these are the values the proposal form's dropdown emits.
CONSULTANT_ALIASES = {
    'thomas': 'thomas_ellison',
    'tony': 'tony_cumella',
    'adam': 'adam_cupito',
    'rachel': 'rachel_farler',
    'andy': 'andy_potts',
}

# What the PPM and TPS loggers write when there is no SSO session. Kept as a
# name rather than a bare string so the places that check for it are findable.
UNATTRIBUTED = 'unknown'


def resolve(key):
    """Alias → roster key. Anything unrecognised comes back untouched."""
    cleaned = (key or '').strip()
    return CONSULTANT_ALIASES.get(cleaned, cleaned)


def resolve_for(key, users):
    """Resolve, then confirm the result is somebody. None if it is not.

    Callers that were written as `if key in users` become
    `if resolve_for(key, users)`, which is the same guard with the aliases
    understood — and returning None rather than a falsy string keeps the
    "we could not attribute this" case explicit at every call site.
    """
    resolved = resolve(key)
    return resolved if resolved in (users or {}) else None


# ── the same map, for SQL that cannot call resolve() ─────────────────────────
#
# Two places need to translate keys inside the database rather than in Python:
# the `init_db` last_login backfill (it joins log tables against `hub_users`
# in one statement) and the one-time normalising migration. Writing the pairs
# out by hand in either of them would put a third and fourth copy of this map
# in the tree, which is the exact failure this module was created to end —
# `_CONSULTANT_KEY_ALIASES` and `CONSULTANT_KEY_MAP` disagreeing is how
# Rachel's proposals went missing in the first place.
#
# The values below are code-controlled literals, never user input, but a future
# edit adding a key with a quote in it would build broken SQL silently, so the
# guard is here rather than in the reviewer's head.

_SQL_SAFE = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')


def _sql_literal(value):
    if not value or set(value) - _SQL_SAFE:
        raise ValueError(
            f'consultant alias {value!r} is not a plain identifier and cannot '
            f'be inlined into SQL — see user_aliases._sql_literal')
    return f"'{value}'"


def sql_resolve(column):
    """A CASE expression that does what `resolve` does, inside Postgres.

    Unrecognised values fall through the ELSE untouched, exactly as `resolve`
    leaves them alone. `tests/test_user_aliases_sql.py` asserts the expression
    covers every entry in CONSULTANT_ALIASES, so adding a consultant to the map
    cannot leave the SQL behind.
    """
    whens = ' '.join(
        f'WHEN {_sql_literal(short)} THEN {_sql_literal(full)}'
        for short, full in sorted(CONSULTANT_ALIASES.items()))
    return f'CASE {column} {whens} ELSE {column} END'


def sql_alias_keys():
    """The short forms, as a tuple, for `WHERE col IN %s` parameters."""
    return tuple(sorted(CONSULTANT_ALIASES))


def sql_alias_in_list():
    """`('adam', 'andy', …)` — the short forms as a literal SQL IN list.

    For statements that cannot take parameters because they are built as text
    and handed to `db_ddl.optional_step`. Same guard as `sql_resolve`.
    """
    return '(' + ', '.join(_sql_literal(k) for k in sorted(CONSULTANT_ALIASES)) + ')'
