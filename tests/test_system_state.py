"""Admin system-state panel.

Fake cursor/conn, no Postgres — this repo's test convention.
Run: python -m pytest tests/test_system_state.py -v
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import system_state as ss


NOW = datetime(2026, 8, 21, 17, 0)

_USERS = {
    'thomas_ellison': {'display': 'Thomas Ellison', 'role': 'admin', 'tier': 'owner'},
    'andy_potts': {'display': 'Andy Potts', 'role': 'consultant', 'tier': 'team'},
    'ben_ramsey': {'display': 'Ben Ramsey', 'role': 'pm', 'tier': 'team'},
    'phil_miller': {'display': 'Phil Miller', 'role': 'pm', 'tier': 'team'},
}


class _Conn:
    def __init__(self, hub_users=(), tokens=(), jobs=(), digest=None):
        self.hub_users, self.tokens, self.jobs, self.digest = hub_users, tokens, jobs, digest
        self.statements = []

    def cursor(self, *a, **k):
        conn = self

        class C:
            def __init__(s):
                s._rows = []

            def execute(s, sql, args=None):
                q = ' '.join(sql.split())
                conn.statements.append((q, args))
                if 'FROM hub_users' in q:
                    s._rows = list(conn.hub_users)
                elif 'password_reset_tokens' in q:
                    s._rows = list(conn.tokens)
                elif 'key LIKE' in q:
                    s._rows = list(conn.jobs)
                elif 'daily_digest_last_run' in q:
                    s._rows = [conn.digest] if conn.digest else []
                else:
                    s._rows = []

            def fetchall(s):
                return s._rows

            def fetchone(s):
                return s._rows[0] if s._rows else None

            def close(s):
                pass

        return C()

    def commit(self):
        pass

    def close(self):
        pass


# --- Password state ---------------------------------------------------------

def test_password_states_map_to_the_question_being_asked():
    """The column that matters is who still cannot sign in.

    'pending' is someone a reset was issued for who has not used it — they are
    locked out until they do, and before this page the only way to find them
    was to wait for them to say so.
    """
    conn = _Conn(hub_users=[
        ('thomas_ellison', NOW, 2, False),           # chose their own
        ('andy_potts', NOW - timedelta(days=3), 1, True),   # reset unused
        ('ben_ramsey', None, 0, False),              # campaign never reached them
    ])
    rows = {r['user_key']: r for r in ss.people_rows(lambda: conn, _USERS)}
    assert rows['thomas_ellison']['pw_state'] == ss.PW_SET
    assert rows['andy_potts']['pw_state'] == ss.PW_PENDING
    assert rows['ben_ramsey']['pw_state'] == ss.PW_UNTOUCHED
    # In USERS but with no hub_users row at all.
    assert rows['phil_miller']['pw_state'] == ss.PW_UNKNOWN


def test_everyone_on_the_roster_appears_even_with_no_db_row():
    conn = _Conn(hub_users=[])
    rows = ss.people_rows(lambda: conn, _USERS)
    assert {r['user_key'] for r in rows} == set(_USERS)


def test_open_reset_link_is_surfaced_with_its_expiry():
    expires = NOW + timedelta(hours=68)
    conn = _Conn(hub_users=[('andy_potts', NOW, 1, True)],
                 tokens=[('andy_potts', 1, expires)])
    rows = {r['user_key']: r for r in ss.people_rows(lambda: conn, _USERS)}
    assert rows['andy_potts']['open_reset']['expires_at'] == expires
    assert rows['ben_ramsey']['open_reset'] is None


def test_summary_counts_separate_pending_from_broken():
    people = [
        {'pw_state': ss.PW_SET, 'last_login': NOW},
        {'pw_state': ss.PW_PENDING, 'last_login': None},
        {'pw_state': ss.PW_UNTOUCHED, 'last_login': NOW},
        {'pw_state': ss.PW_UNKNOWN, 'last_login': None},
    ]
    s = ss.summarize(people)
    assert s == {'total': 4, 'pw_set': 1, 'pw_pending': 1,
                 'pw_problem': 2, 'never_signed_in': 2}


# --- Jobs -------------------------------------------------------------------

def test_every_known_job_is_listed_even_if_it_has_never_run():
    """A job that never fired is the interesting case — usually its cron
    service does not exist in Render. Omitting it would hide exactly that."""
    conn = _Conn(jobs=[])
    rows = ss.job_rows(lambda: conn)
    assert len(rows) == len(ss.KNOWN_JOBS)
    assert all(r['ever_ran'] is False and r['last_run'] is None for r in rows)


def test_recorded_run_is_matched_to_its_job():
    conn = _Conn(jobs=[('job_last_run:weekly_recap', {'ok': True, 'sent': 13}, NOW)])
    rows = {r['slug']: r for r in ss.job_rows(lambda: conn)}
    assert rows['weekly_recap']['ever_ran'] is True
    assert rows['weekly_recap']['last_run'] == NOW
    assert rows['weekly_recap']['detail']['sent'] == 13
    assert rows['daily_digest']['ever_ran'] is False


def test_daily_digest_is_read_from_its_own_pre_existing_key():
    """It stored its last run before this module existed. Read that rather than
    migrating — it is load-bearing for /health, and two writers for one fact is
    what this page exists to avoid."""
    conn = _Conn(jobs=[], digest=({'skipped': True, 'reason': 'already_sent'}, NOW))
    rows = {r['slug']: r for r in ss.job_rows(lambda: conn)}
    assert rows['daily_digest']['ever_ran'] is True
    assert rows['daily_digest']['detail']['reason'] == 'already_sent'


def test_record_job_run_writes_a_single_upserted_key():
    conn = _Conn()
    ss.record_job_run(lambda: conn, 'weekly_recap', {'ok': True, 'sent': ['a', 'b']}, now=NOW)
    sql, args = conn.statements[-1]
    assert 'INSERT INTO hub_settings' in sql and 'ON CONFLICT' in sql
    assert args[0] == 'job_last_run:weekly_recap'
    assert '"sent": 2' in args[1], 'lists are stored as counts, not payloads'


# --- Degradation ------------------------------------------------------------

def test_nothing_raises_when_the_database_is_unreachable():
    """A status page that 500s when something is wrong is worse than none."""
    assert ss.people_rows(lambda: None, _USERS)          # rows, all 'unknown'
    assert len(ss.job_rows(lambda: None)) == len(ss.KNOWN_JOBS)
    assert ss.load_job_runs(lambda: None) == {}
    ss.record_job_run(lambda: None, 'weekly_recap', {'ok': True})


def test_retired_secrets_are_reported_present_when_set(monkeypatch):
    """DEFAULT_PASSWORD used to seed every account. Absence should be visible."""
    monkeypatch.delenv('DEFAULT_PASSWORD', raising=False)
    monkeypatch.delenv('MASTER_PASSWORD', raising=False)
    assert dict(ss.service_rows()['retired_secrets']) == {'DEFAULT_PASSWORD': False}
    monkeypatch.setenv('DEFAULT_PASSWORD', 'oops')
    assert dict(ss.service_rows()['retired_secrets'])['DEFAULT_PASSWORD'] is True


def test_job_payload_string_jsonb_is_parsed():
    """psycopg2 sometimes returns hub_settings.value as a str, not a dict."""
    conn = _Conn(jobs=[
        ('job_last_run:weekly_recap', '{"ok": true, "sent": 13}', NOW),
    ])
    rows = {r['slug']: r for r in ss.job_rows(lambda: conn)}
    assert rows['weekly_recap']['detail']['sent'] == 13
    assert rows['weekly_recap']['detail_label'] == 'sent 13'


def test_job_last_run_is_labeled_eastern():
    """updated_at is naive UTC. 17:00 UTC in August is 1:00 PM ET."""
    conn = _Conn(jobs=[('job_last_run:weekly_recap', {'ok': True, 'sent': 1}, NOW)])
    rows = {r['slug']: r for r in ss.job_rows(lambda: conn)}
    assert rows['weekly_recap']['last_run_label'] == 'Aug 21, 1:00PM ET'


def test_bool_sent_and_digest_email_failed_read_as_words_not_True():
    assert ss.format_job_detail({'sent': True}) == 'sent'
    assert ss.format_job_detail({'sent': False, 'email_failed': True}) == 'email failed'
    assert ss.format_job_detail({'skipped': True, 'reason': 'already_sent'}) == (
        'skipped — already_sent')
    assert ss.format_job_detail({
        'checked': 4, 'assignment_emails_sent': 2, 'reminder_emails_sent': 1,
    }) == '2 assignments mailed · 1 reminders mailed · checked 4'


# ── The deployed commit (2026-08-26) ────────────────────────────────────────
#
# The panel had been reading "unknown" even though Render's docs say
# RENDER_GIT_COMMIT is set automatically at runtime and needs no declaration.
# Rather than depend on one variable that demonstrably has not been arriving,
# resolve through several sources — including a file the build command writes,
# which pins the value into the image and cannot be affected by the runtime
# environment at all.

def test_env_var_is_preferred(monkeypatch):
    monkeypatch.setenv('RENDER_GIT_COMMIT', 'abc1234def5678')
    commit, source = ss.deployed_commit()
    assert commit == 'abc1234def5678'
    assert source == 'RENDER_GIT_COMMIT'


def test_alternative_env_names(monkeypatch):
    monkeypatch.delenv('RENDER_GIT_COMMIT', raising=False)
    monkeypatch.setenv('SOURCE_VERSION', 'deadbeef')
    commit, source = ss.deployed_commit()
    assert (commit, source) == ('deadbeef', 'SOURCE_VERSION')


def test_the_build_time_file_is_the_fallback(monkeypatch, tmp_path):
    """This is the path that does not care what the runtime env carries."""
    for name in ('RENDER_GIT_COMMIT', 'RENDER_GIT_COMMIT_SHA', 'GIT_COMMIT',
                 'SOURCE_VERSION'):
        monkeypatch.delenv(name, raising=False)
    written = tmp_path / ss.COMMIT_FILE
    written.write_text('  f31c35c9  \n')
    monkeypatch.setattr(ss.os.path, 'abspath',
                        lambda _p: str(tmp_path / 'ss.py'))
    commit, source = ss.deployed_commit()
    assert commit == 'f31c35c9', 'whitespace stripped'
    assert source == ss.COMMIT_FILE


def test_nothing_at_all_reports_no_source(monkeypatch):
    """Empty commit AND empty source — the source is what makes a blank row
    debuggable instead of just blank."""
    for name in ('RENDER_GIT_COMMIT', 'RENDER_GIT_COMMIT_SHA', 'GIT_COMMIT',
                 'SOURCE_VERSION'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(ss, 'COMMIT_FILE', 'definitely-not-here')
    assert ss.deployed_commit() == ('', '')


def test_an_empty_env_var_does_not_win(monkeypatch):
    """Render setting the variable to '' is the failure mode being fixed; it
    must fall through rather than count as an answer."""
    monkeypatch.setenv('RENDER_GIT_COMMIT', '   ')
    monkeypatch.setenv('GIT_COMMIT', 'realsha1')
    assert ss.deployed_commit()[0] == 'realsha1'


def test_service_rows_exposes_the_source(monkeypatch):
    monkeypatch.setenv('RENDER_GIT_COMMIT', 'abcdef1234567')
    rows = ss.service_rows()
    assert rows['commit'] == 'abcdef1'
    assert rows['commit_full'] == 'abcdef1234567'
    assert rows['commit_source'] == 'RENDER_GIT_COMMIT'
