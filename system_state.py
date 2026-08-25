"""What the Hub is actually doing right now — for the owner, in one place.

Built 2026-08-21, at the end of a day that made the case for it. Over a few
hours Thomas had to ask, and could not find out from the Hub itself: which
commit is live, whether the password campaign had run, who it had emailed, who
still had not set a password, and whether Monday's recap would fire. Every one
of those answers existed — in a Render log, in a cancelled deploy's output, or
in someone's head. None were in the product.

`/health` is deliberately thin (public, no PII — see the note in CLAUDE.md about
it returning counts rather than email lists). This is the other end: owner-only,
and specific enough to act on.

Three questions it answers:

1. **What is running?** Commit, boot time, database, which integrations are
   configured. Enough to tell "the deploy landed" from "the deploy is stuck",
   which on 2026-08-21 took a Render log to work out.

2. **Where is everyone?** Per person: last active, and whether they have set
   their own password or are still sitting on a reset. That is the question the
   password campaign left open and could not answer — `_apply` bumps
   `password_epoch` whether the email sent or not, so "processed" never meant
   "done", and the only way to find a straggler was to wait for them to text.

3. **Did the scheduled jobs run?** Each cron records its own last run through
   `record_job_run`, so a job that silently stopped firing is visible instead of
   being noticed weeks later. The daily digest already did this under its own
   key; this generalises the same idea rather than inventing a second mechanism.

Everything is read-only and degrades to "unknown" rather than raising — a status
page that 500s when something is wrong is worse than no status page.
"""

from __future__ import annotations

import json
import hub_time
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')

# Result keys copied into the last-run payload. Lists become counts.
_DETAIL_KEYS = (
    'skipped', 'reason', 'sent', 'failed', 'email_failed',
    'remaining', 'total_actions', 'error', 'week_label',
    'assignment_emails_sent', 'reminder_emails_sent',
    'checked', 'new_assignments', 'completed', 'item_count',
)

# Jobs to show, in the order they appear. Key is the slug passed to
# record_job_run(); the schedule text is the human-readable cron in render.yaml.
KNOWN_JOBS = [
    ('daily_digest', 'Daily digest', 'Nightly, ~midnight–3am ET'),
    ('weekly_recap', 'Weekly team recap', 'Mondays ~7am ET'),
    ('weekly_tp_compliance', 'Trade Partner compliance', 'Mondays ~7am ET'),
    ('weekly_crm_sync', 'CRM contact sync', 'Sundays ~11pm ET'),
    ('daily_estimate_check', 'Estimate assignments', 'Daily ~7am ET'),
]

JOB_KEY_PREFIX = 'job_last_run:'

# Password states, derived from hub_users. See password_campaign.py for why
# password_epoch is the marker rather than anything more explicit.
PW_SET = 'set'              # they have chosen their own password
PW_PENDING = 'pending'      # reset issued, not yet used
PW_UNTOUCHED = 'untouched'  # never went through the campaign
PW_UNKNOWN = 'unknown'      # no hub_users row, or DB unreadable


def record_job_run(get_db_fn, job, result=None, now=None):
    """Stamp a job's last run into hub_settings. Best-effort, never raises.

    Keyed rather than tabled because hub_settings already exists and the daily
    digest already stores its run this way — a second mechanism for the same
    idea is how you end up with two sources of truth that disagree.
    """
    conn = None
    try:
        conn = get_db_fn()
        if not conn:
            return
        payload = {
            'at': (now or datetime.now(timezone.utc)).isoformat(),
            'ok': bool((result or {}).get('ok', True)) if result else True,
        }
        if isinstance(result, dict):
            for k in _DETAIL_KEYS:
                if k in result:
                    v = result[k]
                    payload[k] = len(v) if isinstance(v, (list, tuple)) else v
        cur = conn.cursor()
        cur.execute(
            '''INSERT INTO hub_settings (key, value, updated_at, updated_by)
               VALUES (%s, %s::jsonb, NOW(), 'cron')
               ON CONFLICT (key) DO UPDATE
               SET value = EXCLUDED.value, updated_at = NOW(), updated_by = 'cron' ''',
            (JOB_KEY_PREFIX + job, json.dumps(payload)),
        )
        conn.commit()
        cur.close()
    except Exception as e:
        print(f'record_job_run({job}) failed: {e}')
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def load_job_runs(get_db_fn):
    """{job_slug: {...}} for every job that has ever recorded a run."""
    out = {}
    conn = None
    try:
        conn = get_db_fn()
        if not conn:
            return out
        cur = conn.cursor()
        cur.execute(
            "SELECT key, value, updated_at FROM hub_settings WHERE key LIKE %s",
            (JOB_KEY_PREFIX + '%',),
        )
        for key, value, updated_at in cur.fetchall():
            slug = key[len(JOB_KEY_PREFIX):]
            data = _json_object(value)
            data['updated_at'] = updated_at
            out[slug] = data
        cur.close()
        # The daily digest predates this and stores under its own key. Read it
        # rather than migrating: it is load-bearing for /health, and two writers
        # for one fact is exactly what this module is trying to avoid.
        cur = conn.cursor()
        cur.execute("SELECT value, updated_at FROM hub_settings WHERE key = 'daily_digest_last_run'")
        row = cur.fetchone()
        if row and 'daily_digest' not in out:
            data = _json_object(row[0])
            data['updated_at'] = row[1]
            out['daily_digest'] = data
        cur.close()
    except Exception as e:
        print(f'load_job_runs failed: {e}')
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    return out


def _json_object(value):
    """hub_settings.value is jsonb — psycopg2 may return a dict or a string."""
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _eastern_label(dt):
    """Naive Hub timestamps are UTC. Show them in Eastern, labeled.

    This was the only place in the Hub that got this right, and on
    2026-08-25 it became `hub_time.fmt` so every template could use it too.
    Kept as a function because the jobs table calls it and because it adds
    the explicit "ET" suffix, which the generic filters do not.
    """
    if dt is None:
        return None
    label = hub_time.fmt(dt, '%b %d, %-I:%M%p')
    return f'{label} ET' if label else None


def format_job_detail(run):
    """One line for the jobs table — handles bools, counts, and digest shapes."""
    if not run:
        return ''
    if run.get('error'):
        return 'error'
    if run.get('skipped'):
        reason = (run.get('reason') or '').strip()
        return f'skipped — {reason}' if reason else 'skipped'
    parts = []
    sent = run.get('sent')
    email_failed = run.get('email_failed')
    if isinstance(sent, bool):
        if sent:
            parts.append('sent')
        elif email_failed:
            parts.append('email failed')
        else:
            parts.append('not sent')
    elif isinstance(sent, (int, float)):
        parts.append(f'sent {int(sent)}')
    failed = run.get('failed')
    if isinstance(failed, bool) and failed:
        parts.append('failed')
    elif isinstance(failed, (int, float)) and failed:
        parts.append(f'{int(failed)} failed')
    if email_failed and not isinstance(sent, bool):
        if email_failed is True:
            parts.append('email failed')
        elif isinstance(email_failed, (int, float)) and email_failed:
            parts.append(f'{int(email_failed)} email failed')
    for key, tmpl in (
        ('assignment_emails_sent', '{n} assignments mailed'),
        ('reminder_emails_sent', '{n} reminders mailed'),
        ('checked', 'checked {n}'),
        ('new_assignments', '{n} new'),
        ('item_count', '{n} items'),
    ):
        v = run.get(key)
        if isinstance(v, (int, float)) and v:
            parts.append(tmpl.format(n=int(v)))
    return ' · '.join(parts)


def job_rows(get_db_fn):
    runs = load_job_runs(get_db_fn)
    rows = []
    for slug, label, schedule in KNOWN_JOBS:
        run = runs.get(slug)
        last = (run or {}).get('updated_at')
        rows.append({
            'slug': slug,
            'label': label,
            'schedule': schedule,
            'last_run': last,
            'last_run_label': _eastern_label(last),
            'detail': run or None,
            'detail_label': format_job_detail(run) if run else '',
            'ever_ran': bool(run),
        })
    return rows


def people_rows(get_db_fn, users):
    """Per-person password and activity state, in roster order.

    The column that matters is `pw_state`: who is still sitting on a reset they
    have not used. On 2026-08-21 the only way to find those people was to wait
    for one of them to say so in a group text.
    """
    rows = []
    by_key = {}
    conn = None
    try:
        conn = get_db_fn()
        if conn:
            cur = conn.cursor()
            cur.execute(
                'SELECT user_key, last_login, COALESCE(password_epoch, 0), '
                '       COALESCE(must_change_password, FALSE) '
                'FROM hub_users'
            )
            for key, last_login, epoch, must_change in cur.fetchall():
                by_key[key] = {
                    'last_login': last_login,
                    'epoch': int(epoch or 0),
                    'must_change': bool(must_change),
                }
            cur.close()
            cur = conn.cursor()
            cur.execute(
                'SELECT user_key, COUNT(*), MAX(expires_at) FROM password_reset_tokens '
                'WHERE used = FALSE AND expires_at > NOW() GROUP BY user_key'
            )
            for key, count, expires in cur.fetchall():
                if key in by_key:
                    by_key[key]['open_reset'] = {'count': int(count), 'expires_at': expires}
            cur.close()
    except Exception as e:
        print(f'people_rows failed: {e}')
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    for key, user in users.items():
        db = by_key.get(key)
        if db is None:
            state = PW_UNKNOWN
        elif db['must_change']:
            state = PW_PENDING
        elif db['epoch'] >= 1:
            state = PW_SET
        else:
            state = PW_UNTOUCHED
        rows.append({
            'user_key': key,
            'display': user.get('display', key),
            'role': user.get('role', ''),
            'tier': user.get('tier', 'team'),
            'email': user.get('email', ''),
            'last_login': (db or {}).get('last_login'),
            'pw_state': state,
            'open_reset': (db or {}).get('open_reset'),
        })
    return rows


def service_rows():
    """What is running, and which integrations are wired.

    Render exposes the deployed commit as RENDER_GIT_COMMIT. Without it there is
    no way from inside the process to answer "did my push actually land", which
    cost real time on 2026-08-21.
    """
    commit = (os.environ.get('RENDER_GIT_COMMIT') or '').strip()
    return {
        'commit': commit[:7] if commit else '',
        'commit_full': commit,
        'branch': os.environ.get('RENDER_GIT_BRANCH', ''),
        'service': os.environ.get('RENDER_SERVICE_NAME', ''),
        'integrations': [
            ('Database', bool((os.environ.get('DATABASE_URL') or '').strip())),
            ('Claude API', bool((os.environ.get('CLAUDE_API_KEY') or '').strip())),
            ('SMTP', bool((os.environ.get('SMTP_HOST') or '').strip())),
            ('Resend', bool((os.environ.get('RESEND_API_KEY') or '').strip())),
            ('Internal API key', bool((os.environ.get('INTERNAL_API_KEY') or '').strip())),
            ('Monday.com', bool((os.environ.get('MONDAY_API_TOKEN') or '').strip())),
            ('Weekly recap enabled',
             (os.environ.get('WEEKLY_RECAP_ENABLED', 'true') or '').lower() == 'true'),
        ],
        # Retired 2026-08-21. Code ignores it; the row is here so a
        # reappearance is loud.
        'retired_secrets': [
            ('DEFAULT_PASSWORD', bool((os.environ.get('DEFAULT_PASSWORD') or '').strip())),
        ],
    }


def summarize(people):
    """Headline counts for the top of the page."""
    return {
        'total': len(people),
        'pw_set': sum(1 for p in people if p['pw_state'] == PW_SET),
        'pw_pending': sum(1 for p in people if p['pw_state'] == PW_PENDING),
        'pw_problem': sum(1 for p in people
                          if p['pw_state'] in (PW_UNTOUCHED, PW_UNKNOWN)),
        'never_signed_in': sum(1 for p in people if not p['last_login']),
    }
