"""The alias map, translated into SQL, and the call site that forgot to use it.

Run: python -m pytest tests/test_user_aliases_sql.py -v

Two things are being pinned here.

**One map, four consumers.** `user_aliases` exists because the same mapping
lived in two repositories under two names, got applied to two different fields,
and Rachel's proposals vanished. Two consumers now need the mapping *inside*
Postgres — the `init_db` last_login backfill, which joins the log tables
against `hub_users` in a single statement, and the one-time normalising
migration beside it. Writing those pairs out by hand would recreate the exact
problem the module was built to end, one repository later. So the SQL is
generated, and these tests fail if the generator and the dict disagree.

**`_touch_last_active` resolves.** Four of its callers hand it
`data.get('generated_by')` off a `/log-proposal` payload — the short key
whenever the proposal tool was opened from a bookmark. Its UPDATE matches
`user_key` exactly, so those calls updated nothing and the roster went on
reporting people as unseen while their work sat in the log. The fix is inside
the function rather than at the four call sites, because a fifth call site is
going to be written by someone who has never read this file.
"""
import ast
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import user_aliases  # noqa: E402


# ── sql_resolve mirrors resolve ─────────────────────────────────────────────

def test_every_alias_in_the_map_appears_in_the_sql():
    """Adding a consultant to the dict must not leave the SQL behind."""
    sql = user_aliases.sql_resolve('generated_by')
    for short, full in user_aliases.CONSULTANT_ALIASES.items():
        assert f"WHEN '{short}' THEN '{full}'" in sql, (
            f'{short} is in the map but not in the generated SQL')


def test_the_sql_translates_nothing_the_python_does_not():
    """The other direction — a WHEN with no matching dict entry would be a
    rule that exists only in the database."""
    sql = user_aliases.sql_resolve('generated_by')
    pairs = re.findall(r"WHEN '([^']+)' THEN '([^']+)'", sql)
    assert dict(pairs) == user_aliases.CONSULTANT_ALIASES
    assert len(pairs) == len(user_aliases.CONSULTANT_ALIASES)


def test_unrecognised_values_fall_through_untouched():
    """`resolve` does not guess, and neither may the SQL. 'unknown' has to
    survive as 'unknown' — inventing an owner for unattributed work is worse
    than admitting nobody knows who did it."""
    sql = user_aliases.sql_resolve('generated_by')
    assert sql.strip().endswith('ELSE generated_by END')
    assert 'unknown' not in sql


def test_the_column_name_is_honoured():
    """office_ops_packs names the column created_by, not generated_by."""
    sql = user_aliases.sql_resolve('created_by')
    assert sql.startswith('CASE created_by ')
    assert sql.endswith('ELSE created_by END')
    assert 'generated_by' not in sql


def test_the_in_list_covers_exactly_the_short_forms():
    in_list = user_aliases.sql_alias_in_list()
    found = set(re.findall(r"'([^']+)'", in_list))
    assert found == set(user_aliases.CONSULTANT_ALIASES)
    assert in_list.startswith('(') and in_list.endswith(')')


# ── the guard on inlining ───────────────────────────────────────────────────

def test_a_key_that_is_not_a_plain_identifier_is_refused(monkeypatch):
    """These values are code, never user input — but they are inlined into a
    statement, and the next person to edit the dict should hit an exception
    rather than build broken SQL that runs."""
    monkeypatch.setitem(user_aliases.CONSULTANT_ALIASES, "o'brien", 'x_obrien')
    with pytest.raises(ValueError):
        user_aliases.sql_resolve('generated_by')


@pytest.mark.parametrize('bad', ["a'b", 'a b', 'a;b', 'a-b', '', None])
def test_the_literal_guard_rejects_it(bad):
    with pytest.raises(ValueError):
        user_aliases._sql_literal(bad)


# ── _touch_last_active resolves, and does it in one place ───────────────────

def _touch_last_active_source():
    with open(os.path.join(ROOT, 'app.py')) as fh:
        tree = ast.parse(fh.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == '_touch_last_active':
            return node
    pytest.fail('_touch_last_active is gone from app.py')


def test_touch_last_active_resolves_its_key():
    """The whole fix, asserted structurally rather than by grepping prose:
    somewhere in the body, `user_aliases.resolve` is called."""
    calls = [n for n in ast.walk(_touch_last_active_source())
             if isinstance(n, ast.Call)]
    resolved = [
        c for c in calls
        if isinstance(c.func, ast.Attribute) and c.func.attr == 'resolve'
        and isinstance(c.func.value, ast.Name) and c.func.value.id == 'user_aliases'
    ]
    assert resolved, (
        '_touch_last_active does not resolve its key, so work logged under a '
        'short consultant key will not move last_login')


def test_it_resolves_before_it_decides_the_key_is_empty():
    """`resolve` turns None into '', so the emptiness check has to come after
    it — otherwise the ordering works by luck rather than by design."""
    fn = _touch_last_active_source()
    body = [n for n in fn.body if not isinstance(n, ast.Expr)]  # skip docstring
    first = body[0]
    assert isinstance(first, ast.Assign), (
        'the first statement is no longer the resolve assignment')
    assert 'resolve' in ast.dump(first.value)


def test_the_call_sites_do_not_each_resolve_separately():
    """Four callers pass an unresolved key today. Resolving at the call sites
    instead would fix those four and leave the fifth to be written wrong, so
    this asserts the fix stayed in the function."""
    with open(os.path.join(ROOT, 'app.py')) as fh:
        source = fh.read()
    doubled = re.findall(
        r'_touch_last_active\(\s*user_aliases\.resolve\(', source)
    assert not doubled, (
        'a call site is resolving too — harmless but it means someone thought '
        'the function does not, which is how the next call site gets it wrong')
