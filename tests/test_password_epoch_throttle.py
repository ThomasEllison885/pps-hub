"""How often a live session re-checks its password, and why it is 60 seconds.

Run: python -m pytest tests/test_password_epoch_throttle.py -v

── Why a value has a test ──────────────────────────────────────────────────

`PASSWORD_EPOCH_RECHECK_SECONDS` is the window between a password reset and
that person's *other* devices being signed out. It was 15 minutes because
there was no connection pool, so a SELECT per request meant a fresh Postgres
connect per request. Pooling landed 2026-08-25 (`db_pool.py`) and the comment
above the constant went on citing its absence for six days — a stale
justification is exactly how a number that was once right survives past the
reason for it.

Two ways it can drift back, and both look reasonable at the time:

  * **Up**, because someone is worried about load and 15 minutes is the
    number they remember. That silently widens the eviction window on the one
    control that makes a 30-day session tolerable.
  * **To zero**, because "there's a pool now, so just check every request" is
    a one-line change with an obvious-sounding argument. It is also wrong:
    this check runs on *every* request, which includes Pipeline Board's
    three-second poll and every static asset. Per-request buys the last 59
    seconds of eviction latency for a permanent per-hit tax on the busiest
    path in the app.

So the value is pinned here rather than defended by a paragraph nobody reads
before editing. Changing it means changing this file, which means saying why.

Thomas, 2026-08-31: "60 seconds is the decision."
"""
import ast
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _app_source():
    with open(os.path.join(ROOT, 'app.py')) as fh:
        return fh.read()


def _value(node):
    """Fold a literal, or simple arithmetic over literals.

    `15 * 60` is how this constant was written for most of its life, and it is
    how the next person will write `5 * 60` if they raise it. `literal_eval`
    refuses a BinOp, so reading it that way would make these tests *error*
    rather than fail — which reads as a broken test rather than a rejected
    change, and is how a guard gets deleted instead of argued with.
    """
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        pass
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mult, ast.Add)):
        left, right = _value(node.left), _value(node.right)
        return left * right if isinstance(node.op, ast.Mult) else left + right
    pytest.fail(f'cannot read the value of {ast.dump(node)}')


def _constant(name):
    """Read the value out of app.py without importing it.

    No test in this repo imports `app` except the two that need a real
    database — importing it runs the startup migrations against whatever
    DATABASE_URL happens to be set, which is not something a unit test about
    a number should be able to do.
    """
    for node in ast.walk(ast.parse(_app_source())):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return _value(node.value)
    pytest.fail(f'{name} is gone from app.py')


# ── the value ───────────────────────────────────────────────────────────────

def test_the_recheck_window_is_sixty_seconds():
    assert _constant('PASSWORD_EPOCH_RECHECK_SECONDS') == 60


def test_it_is_not_per_request():
    """Zero would mean a SELECT on every static asset and every three-second
    Pipeline poll. If someone wants this, it needs an argument, not an edit."""
    assert _constant('PASSWORD_EPOCH_RECHECK_SECONDS') > 0


def test_eviction_cannot_quietly_go_back_to_fifteen_minutes():
    """The upper bound is the point of the whole control: a 30-day idle
    session is only tolerable because a password reset evicts other devices
    reasonably promptly."""
    assert _constant('PASSWORD_EPOCH_RECHECK_SECONDS') <= 120, (
        'the eviction window widened — see the sessions entry in CLAUDE.md')


# ── the reasons written next to it ──────────────────────────────────────────

def test_nothing_still_claims_there_is_no_connection_pool():
    """`db_pool.py` shipped 2026-08-25. Two comments went on citing its
    absence — one of them as the reason for this very constant. A stale
    justification is worse than none: it answers the question a reader was
    about to ask, wrongly."""
    offenders = []
    for name in ('app.py', 'dashboard_summary.py', 'weekly_recap.py',
                 'hub_adoption.py', 'daily_digest.py'):
        path = os.path.join(ROOT, name)
        if not os.path.exists(path):
            continue
        with open(path) as fh:
            text = fh.read()
        for match in re.finditer(r'no connection pool', text, re.I):
            line = text[:match.start()].count('\n') + 1
            # A line describing the *history* is fine; one asserting the
            # present tense is not.
            context = text[max(0, match.start() - 120):match.end() + 60]
            if not re.search(r'used to|stopped being true|was\b|until|before',
                             context, re.I):
                offenders.append(f'{name}:{line}')
    assert not offenders, f'still claiming there is no pool: {offenders}'


def test_the_reasoning_here_is_not_outsourced_to_a_missing_file():
    """The old comment on this constant cited `docs/HUB_REVIEW_2026-08-21.md`,
    which is not in the repo — so the stated reason was both wrong and
    unreadable. `tests/test_doc_pointers.py` covers the other citations."""
    block = _app_source().split('PASSWORD_EPOCH_RECHECK_SECONDS')[0][-1400:]
    assert 'docs/HUB_REVIEW' not in block


def test_the_epoch_check_still_fails_open():
    """Not about the throttle, but it shares the function and is the thing
    that must not be lost while tuning it: an unreachable database must not
    sign the whole company out. The roster check fails closed; this one does
    not, on purpose."""
    source = _app_source()
    body = source.split('def _session_password_stale(')[1].split('\ndef ')[0]
    tail = body.split('except')[-1]
    assert 'return False' in tail, (
        '_session_password_stale no longer fails open on DB trouble')
