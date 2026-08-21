"""One-time shared-password retirement.

Fake cursor/conn, no Postgres and no SMTP — this repo's test convention.
Run: python -m pytest tests/test_password_campaign.py -v
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import password_campaign as pc


_USERS = {
    'thomas_ellison': {'display': 'Thomas Ellison', 'email': 'thomas@pps.com'},
    'andy_potts': {'display': 'Andy Potts', 'email': 'andy@pps.com'},
    'ben_ramsey': {'display': 'Ben Ramsey', 'email': 'ben@pps.com'},
    'no_email': {'display': 'No Email', 'email': ''},
}


class _Cursor:
    def __init__(self, conn):
        self._conn = conn
        self.rowcount = 1
        self._rows = []

    def execute(self, sql, args=None):
        q = ' '.join(sql.split())
        self._conn.statements.append((q, args))
        if 'COALESCE(password_epoch, 0) = 0' in q:
            # Mirrors the real query: candidates still at epoch 0.
            self._rows = [(k,) for k in args[0] if self._conn.epochs.get(k, 0) == 0]

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class _Conn:
    """One fake database. `epochs` maps user_key -> password_epoch; anyone
    absent is treated as 0, i.e. not yet processed."""

    def __init__(self, epochs=None, statements=None):
        self.epochs = epochs if epochs is not None else {}
        self.statements = statements if statements is not None else []

    def cursor(self, *a, **k):
        return _Cursor(self)

    def commit(self):
        pass

    def close(self):
        pass


def _hash(pw):
    return f'hashed:{pw}'


def _runner(conn, sender, users=None, exclude=('thomas_ellison',)):
    tokens = []

    def make_token(user_key, ttl):
        tokens.append((user_key, ttl))
        return f'tok-{user_key}'

    result = pc.run_campaign(
        lambda: conn,
        users if users is not None else _USERS,
        sender,
        make_token,
        lambda t: f'https://hub.example/reset-password/{t}',
        _hash,
        exclude=exclude,
    )
    return result, tokens


# --- Never email the same person twice --------------------------------------

def _pending_conn(epochs):
    return _Conn(epochs=epochs)


def test_pending_skips_anyone_already_processed():
    """password_epoch is the guard. The first run died mid-flight without a
    ledger, so who-was-emailed has to be derived from state."""
    conn = _pending_conn({'andy_potts': 1, 'ben_ramsey': 0, 'thomas_ellison': 2})
    pending = pc.pending_user_keys(lambda: conn, _USERS)
    assert pending == ['ben_ramsey']


def test_pending_skips_people_with_no_email():
    conn = _pending_conn({'andy_potts': 0, 'ben_ramsey': 0, 'thomas_ellison': 0})
    pending = pc.pending_user_keys(lambda: conn, _USERS)
    assert 'no_email' not in pending


def test_pending_honours_exclude():
    conn = _pending_conn({'andy_potts': 0, 'ben_ramsey': 0, 'thomas_ellison': 0})
    pending = pc.pending_user_keys(lambda: conn, _USERS, exclude={'thomas_ellison'})
    assert 'thomas_ellison' not in pending


def test_pending_returns_nothing_when_the_database_is_unreachable():
    """Emailing nobody is always the safe direction; emailing twice is not."""
    assert pc.pending_user_keys(lambda: None, _USERS) == []


def test_a_completed_campaign_is_a_no_op_on_a_second_run():
    """Everyone at epoch >= 1 -> nothing sent, nothing changed."""
    conn = _pending_conn({k: 1 for k in _USERS})
    sent = []
    result = pc.run_campaign(
        lambda: conn, _USERS, lambda *a: sent.append(a) or True,
        lambda k, t: f'tok-{k}', lambda t: f'u/{t}', _hash,
    )
    assert sent == []
    assert result['emailed'] == []
    assert result['pending_at_start'] == 0


# --- Bounded by wall clock, not row count -----------------------------------

def test_time_budget_stops_the_batch_and_reports_the_remainder():
    """The COI vision-pass lesson: a row limit does not bound wall time, and
    anything past gunicorn's 120s gets SIGKILLed mid-flight."""
    import time as _t
    conn = _pending_conn({'andy_potts': 0, 'ben_ramsey': 0, 'thomas_ellison': 0})

    def slow(*a):
        _t.sleep(0.05)
        return True

    result = pc.run_campaign(
        lambda: conn, _USERS, slow, lambda k, t: f'tok-{k}', lambda t: f'u/{t}',
        _hash, time_budget_seconds=0.0,
    )
    # Budget already spent before the first send — nothing goes out, all remain.
    assert result['emailed'] == []
    assert result['remaining'] == result['pending_at_start'] > 0


# --- Email first, invalidate second -----------------------------------------

def test_successful_send_invalidates_the_old_password():
    conn = _Conn()
    result, _ = _runner(conn, lambda *a: True)
    assert set(result['emailed']) == {'andy_potts', 'ben_ramsey'}
    assert result['email_failed'] == []
    updates = [s for s, _ in conn.statements if 'password_hash' in s]
    assert len(updates) == 2
    for sql in updates:
        assert 'must_change_password = TRUE' in sql
        assert 'password_epoch = COALESCE(password_epoch, 0) + 1' in sql


def test_failed_send_never_locks_anyone_out():
    """The reason the email goes first.

    Invalidate-then-email turns one SMTP hiccup into a locked-out employee.
    A failed send leaves the existing password alone and falls back to forcing
    a change at next sign-in.
    """
    conn = _Conn()
    result, _ = _runner(conn, lambda *a: False)
    assert result['emailed'] == []
    assert set(result['email_failed']) == {'andy_potts', 'ben_ramsey'}
    assert not [s for s, _ in conn.statements if 'password_hash' in s]
    forced = [s for s, _ in conn.statements if 'must_change_password = TRUE' in s]
    assert len(forced) == 2


def test_sessions_are_evicted_even_when_the_email_fails():
    """Bumping password_epoch is the half that matters for a shared secret —
    it applies whether or not the mail got through."""
    conn = _Conn()
    _runner(conn, lambda *a: False)
    bumped = [s for s, _ in conn.statements
              if 'password_epoch = COALESCE(password_epoch, 0) + 1' in s]
    assert len(bumped) == 2


def test_a_raising_sender_is_treated_as_a_failure_not_a_crash():
    def boom(*a):
        raise RuntimeError('smtp exploded')

    conn = _Conn()
    result, _ = _runner(conn, boom)
    assert set(result['email_failed']) == {'andy_potts', 'ben_ramsey'}
    assert not [s for s, _ in conn.statements if 'password_hash' in s]


def test_one_persons_failure_does_not_stop_the_rest():
    calls = []

    def flaky(subject, text, html, recipients):
        calls.append(recipients[0])
        return recipients[0] != 'andy@pps.com'

    conn = _Conn()
    result, _ = _runner(conn, flaky)
    assert result['emailed'] == ['ben_ramsey']
    assert result['email_failed'] == ['andy_potts']


# --- Who is included --------------------------------------------------------

def test_excluded_user_is_untouched():
    """Thomas keeps his password so there is always a way in."""
    conn = _Conn()
    result, _ = _runner(conn, lambda *a: True)
    assert 'thomas_ellison' in result['skipped']
    assert 'thomas_ellison' not in result['emailed']
    assert not [a for s, a in conn.statements
                if a and 'thomas_ellison' in (a or ())]


def test_user_without_an_email_is_skipped_not_invalidated():
    """No inbox means no way back in — leave that password working and let
    Thomas handle it, rather than stranding them."""
    conn = _Conn()
    result, _ = _runner(conn, lambda *a: True)
    assert 'no_email' in result['skipped']
    assert not [a for s, a in conn.statements if a and 'no_email' in (a or ())]


def test_reset_links_get_the_long_ttl_not_the_one_hour_default():
    """An hour suits someone who just clicked "I forgot". Unprompted mail may
    be read the next morning."""
    conn = _Conn()
    _result, tokens = _runner(conn, lambda *a: True)
    assert tokens
    assert all(ttl == pc.RESET_TTL_HOURS for _key, ttl in tokens)
    assert pc.RESET_TTL_HOURS >= 48


def test_invalidated_password_is_a_real_hash_of_a_secret_nobody_holds():
    captured = {}

    def sender(*a):
        return True

    conn = _Conn()
    _runner(conn, sender)
    updates = [a for s, a in conn.statements if 'password_hash' in s]
    for args in updates:
        stored = args[0]
        assert stored.startswith('hashed:'), 'must go through the hasher'
        assert len(stored) > 40, 'and hash a long random secret'
    # No two people end up with the same replacement.
    assert len({a[0] for a in updates}) == len(updates)


# --- Email copy -------------------------------------------------------------

def test_email_does_not_mention_why_the_timing_is_what_it_is():
    """This lands in a dozen inboxes at once. The staffing reason behind the
    timing is not company-wide news."""
    _subject, text, html = pc.build_email('Andy Potts', 'https://hub.example/r/tok')
    body = (text + html).lower()
    for leak in ('fired', 'terminated', 'let go', 'leaving', 'departure',
                 'security', 'breach', 'compromised'):
        assert leak not in body, leak


def test_email_carries_the_link_and_says_what_to_do_when_it_expires():
    _subject, text, html = pc.build_email('Andy Potts', 'https://hub.example/r/tok')
    for body in (text, html):
        assert 'https://hub.example/r/tok' in body
        assert 'Forgot Password' in body
        assert '72 hours' in body


def test_email_greets_by_first_name_and_survives_a_blank_one():
    _s, text, _h = pc.build_email('Andy Potts', 'u')
    assert 'Hi Andy,' in text
    _s, text, _h = pc.build_email('', 'u')
    assert 'Hi there,' in text
