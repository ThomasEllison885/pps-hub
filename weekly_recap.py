"""Weekly team recap — the Hub's first email that goes TO the team.

Built 2026-08-21. Everything else the Hub sends points at Thomas: the nightly
digest has exactly one recipient, so the whole notification apparatus was an
owner's report on the team rather than anything the team ever received. This is
the other direction — every Monday morning, everyone gets last week's scoreboard.

Thomas's ask, verbatim: "a recap sent out to everyone, just not as detailed as
the one I get, but it would help everyone know who is crushing the hub and who
is not." So this is a real ranked leaderboard, names included, not a gentle
summary. Two design decisions carry most of the weight:

**What counts is completed work, never clicks.** SCORED_SOURCES below is the
entire definition, in one place, so anyone who disagrees with their number can
be shown exactly how it was computed. Page opens, logins, presence heartbeats
and polls are deliberately excluded — a leaderboard that counts opens is a
machine for teaching people to open things. (Opens ARE recorded, via
hub_usage.record_usage, but they feed Thomas's diagnostic view, not this.)

**Ranking is within role groups, not one flat list.** Consultants generate
proposals; PMs generate PPMs and scopes; Stephanie generates two Office Ops
packs a week and Phil is on no pipeline board. On a single list the office and
the unpaired PM sit at the bottom forever, for reasons that have nothing to do
with effort, and the first person who works that out stops believing the email.
Groups keep the comparison between people whose weeks are actually comparable.

F-04 is the finding behind the whole thing. See CLAUDE.md, "Hub review
(2026-08-21)" — the original write-up is not in this repo.
"""

from __future__ import annotations

import os
import user_aliases
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')

# ── What counts ─────────────────────────────────────────────────────────────
#
# (kind, label, table, user_column, timestamp_column). One row in one of these
# tables in the reporting week = one point. Nothing is weighted: a proposal and
# a gutter estimate both count 1. Weighting invites an argument about the
# exchange rate that no scoreboard survives.
#
# Adding a feature? Add a line here, or — if it only writes hub_usage_events —
# nothing at all: non-'open' usage events are counted generically below.

SCORED_SOURCES = [
    ('proposal',   'Proposals',        'proposal_log',           'generated_by', 'generated_at'),
    ('ppm',        'PPMs',             'ppm_log',                'generated_by', 'generated_at'),
    ('tps',        'TPS scopes',       'subscope_log',           'generated_by', 'generated_at'),
    ('site_visit', 'Site visits',      'site_visit_log',         'generated_by', 'generated_at'),
    ('siding',     'Siding estimates', 'siding_estimate_log',    'generated_by', 'generated_at'),
    ('roofing',    'Roofing estimates', 'roofing_estimate_log',  'generated_by', 'generated_at'),
    ('gutter',     'Gutter estimates', 'gutter_estimate_log',    'generated_by', 'generated_at'),
    ('painting',   'Painting estimates', 'painting_estimate_log', 'generated_by', 'generated_at'),
    ('office_ops', 'Office Ops packs', 'office_ops_packs',       'created_by',   'created_at'),
]

# ── Deliverables vs activity ────────────────────────────────────────────────
#
# Not everything countable is the same kind of act. Generating a proposal
# produces a document that goes to a client; updating a pipeline row is a few
# seconds in a shared sheet. Counting both at 1 made the board rank whoever
# edited the Pipeline Board most — Andy's 109 for a week was overwhelmingly
# pipeline touches, and Rachel's 25 was 22 pipeline against 3 proposals. Left
# alone, it teaches people that ten quick cell edits beat a proposal.
#
# The fix is a cap rather than per-kind weights. Weights mean inventing an
# exchange rate for every pair of activities and defending all of them; a cap
# answers the one question actually being asked — how much can activity move
# your rank — with a single number. Thomas set it at 5/week (2026-08-22).
#
# ACTIVITY_KINDS still appear in the breakdown line at their true counts. Only
# their contribution to the ranked score is bounded, so the board reflects
# output while the Pipeline Board's real daily use stays visible.

ACTIVITY_KINDS = ('pipeline_new', 'pipeline_touch', 'hub_actions')

ACTIVITY_CAP_PER_WEEK = 5


def score_total(breakdown, weeks=1):
    """Ranked score: every deliverable, plus activity capped per week.

    `weeks` scales the cap with the window — the 12-week column allows
    12 x the weekly cap, or the rolling figure would be crushed against a
    ceiling meant for seven days and could read lower than the week inside it.
    """
    breakdown = breakdown or {}
    deliverables = sum(n for k, n in breakdown.items() if k not in ACTIVITY_KINDS)
    activity = sum(n for k, n in breakdown.items() if k in ACTIVITY_KINDS)
    return deliverables + min(activity, ACTIVITY_CAP_PER_WEEK * max(1, weeks))


# Usage events worth a point. 'open' is absent on purpose and must stay absent.
SCORED_USAGE_ACTIONS = ('import', 'refresh', 'vision', 'override', 'upload', 'generate', 'notes')

# Role → group. Groups are ordered as they appear in the email.
ROLE_GROUPS = [
    ('Consultants', ('consultant',)),
    ('Project Managers', ('pm',)),
    ('Office', ('office_manager', 'admin')),
]

RECAP_ENABLED_DEFAULT = 'true'


def _enabled():
    return os.environ.get('WEEKLY_RECAP_ENABLED', RECAP_ENABLED_DEFAULT).lower() == 'true'


def _excluded_keys():
    """Who is left out of the ranking entirely.

    Empty by default — Thomas appears alongside everyone else. He is excluded
    from his own nightly digest (DAILY_DIGEST_EXCLUDE) so his clicks don't
    drown out the team's, but on a scoreboard the owner opting himself out
    reads exactly the way you'd expect it to.
    """
    raw = os.environ.get('WEEKLY_RECAP_EXCLUDE', '')
    return {k.strip() for k in raw.split(',') if k.strip()}


# ── Week boundaries ─────────────────────────────────────────────────────────

def eastern_now():
    """Real US/Eastern, DST included — same ZoneInfo daily_digest.py uses."""
    return datetime.now(ET)


def should_run_scheduled(now=None):
    """True only on a Monday morning, Eastern. Mirrors daily_digest's guard.

    Without this, Render's "Trigger Run" button — the obvious way anyone tests
    a cron job — emails the entire company on the spot. A test button whose
    side effect lands in thirteen inboxes is a trap, and the person most likely
    to spring it is whoever is checking the cron works at all.

    So the endpoint is now safe to press on any day but Monday: it reports
    `skipped: not_scheduled` and sends nothing. WEEKLY_RECAP_FORCE=true still
    overrides, for a deliberate off-schedule send.

    The window is the whole Monday morning rather than the cron's exact hour,
    so a Render retry after a failed 7am attempt still lands.
    """
    now = now or eastern_now()
    return now.weekday() == 0 and now.hour < 12


def last_week_bounds(today=None):
    """(start, end) for the Monday–Sunday week that just ended, in UTC-naive.

    Called on a Monday, returns the previous Mon 00:00 ET through this Mon 00:00
    ET. Returned NAIVE UTC because every timestamp column in the Hub is naive
    UTC — handing an aware datetime to those comparisons raises.

    Both ends are converted from a real Eastern midnight rather than derived by
    adding hours, which matters twice a year: the fall-back week is 169 hours
    long and the spring-forward week is 167, so `start + timedelta(days=7)`
    would put the boundary an hour off and miscount anything logged in that
    hour. Mirrors daily_digest.eastern_day_bounds_utc_naive().
    """
    today = today or eastern_now().date()
    this_monday = today - timedelta(days=today.weekday())
    last_monday = this_monday - timedelta(days=7)
    start_et = datetime.combine(last_monday, time.min, tzinfo=ET)
    end_et = datetime.combine(this_monday, time.min, tzinfo=ET)
    return (
        start_et.astimezone(timezone.utc).replace(tzinfo=None),
        end_et.astimezone(timezone.utc).replace(tzinfo=None),
    )


def current_week_bounds(today=None):
    """(start, end) for the week IN PROGRESS — this Monday 00:00 ET to next.

    The recap emails `last_week_bounds`; the dashboard's activity pill uses
    this one. That difference is deliberate and worth keeping straight: an
    email sent on Monday morning reports a finished week, while a dashboard
    opened on Thursday has to be about the week the person is actually in.
    Showing them the completed-week figure would be a number that does not
    move for seven days and does not include anything they did today.

    The end is next Monday's Eastern midnight rather than "now", so the
    window is a whole week and the caller never has to reason about whether
    a row written a second ago falls inside it. Nothing is logged in the
    future, so the wide end is harmless — and keeping the shape identical to
    the other two helpers is what makes the dashboard's number the same
    arithmetic as the email's.

    Built from real Eastern midnights for the same DST reason as
    `last_week_bounds` — see that docstring.
    """
    today = today or eastern_now().date()
    this_monday = today - timedelta(days=today.weekday())
    next_monday = this_monday + timedelta(days=7)
    start_et = datetime.combine(this_monday, time.min, tzinfo=ET)
    end_et = datetime.combine(next_monday, time.min, tzinfo=ET)
    return (
        start_et.astimezone(timezone.utc).replace(tzinfo=None),
        end_et.astimezone(timezone.utc).replace(tzinfo=None),
    )


ROLLING_WEEKS = 12


def rolling_bounds(today=None, weeks=ROLLING_WEEKS):
    """(start, end) for the N whole weeks ending where last week ended.

    Shares its end with last_week_bounds(), so the rolling figure always
    includes the week being reported rather than stopping just short of it.
    Built from real Eastern midnights for the same reason as the weekly window
    — over twelve weeks the span crosses a DST boundary about half the year,
    and `end - timedelta(weeks=12)` would quietly land an hour off.
    """
    today = today or eastern_now().date()
    this_monday = today - timedelta(days=today.weekday())
    first_monday = this_monday - timedelta(days=7 * weeks)
    start_et = datetime.combine(first_monday, time.min, tzinfo=ET)
    end_et = datetime.combine(this_monday, time.min, tzinfo=ET)
    return (
        start_et.astimezone(timezone.utc).replace(tzinfo=None),
        end_et.astimezone(timezone.utc).replace(tzinfo=None),
    )


def week_label(start):
    end_day = start + timedelta(days=6)
    if start.month == end_day.month:
        return f'{start.strftime("%b %-d")}–{end_day.strftime("%-d")}'
    return f'{start.strftime("%b %-d")} – {end_day.strftime("%b %-d")}'


# ── Send-once guard ─────────────────────────────────────────────────────────
#
# `cron_weekly_recap.py` retries a failed POST three times. Sending thirteen
# emails can outlast gunicorn's 120s worker timeout, so the server can finish
# sending and *then* have the connection killed — the client sees a failure and
# retries, and everyone gets the recap again. That is not hypothetical: it is
# what happened on 2026-08-22.
#
# A retry has to be safe, so the send is recorded per week and refused if that
# week has already gone out. Same shape as daily_digest's `daily_digest_sent`
# marker. `force` still overrides, for a deliberate re-send.

SENT_KEY = 'weekly_recap_last_sent_week'


def already_sent_for(get_db_fn, week_start):
    """True when this week's recap has already gone out. False on any DB error —
    a broken read must not silently block the real Monday send."""
    conn = None
    try:
        conn = get_db_fn()
        if not conn:
            return False
        cur = conn.cursor()
        cur.execute('SELECT value FROM hub_settings WHERE key = %s', (SENT_KEY,))
        row = cur.fetchone()
        cur.close()
        if not row or not row[0]:
            return False
        value = row[0]
        if isinstance(value, str):
            import json as _json
            try:
                value = _json.loads(value)
            except (TypeError, ValueError):
                return False
        return (value or {}).get('week') == week_start.date().isoformat()
    except Exception as e:
        print(f'weekly recap sent-check failed: {e}')
        return False
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def mark_sent(get_db_fn, week_start):
    import json
    conn = None
    try:
        conn = get_db_fn()
        if not conn:
            return
        cur = conn.cursor()
        cur.execute(
            '''INSERT INTO hub_settings (key, value, updated_at, updated_by)
               VALUES (%s, %s::jsonb, NOW(), 'cron')
               ON CONFLICT (key) DO UPDATE
               SET value = EXCLUDED.value, updated_at = NOW(), updated_by = 'cron' ''',
            (SENT_KEY, json.dumps({'week': week_start.date().isoformat()})),
        )
        conn.commit()
        cur.close()
    except Exception as e:
        print(f'weekly recap mark-sent failed: {e}')
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


# ── Scoring ─────────────────────────────────────────────────────────────────

def collect_scores(get_db, users, start, end):
    """Return {user_key: {kind: count}} for the window. Never raises.

    A missing table is skipped rather than failing the whole run — several of
    these are created lazily on first use, so a Hub that has never generated a
    painting estimate genuinely has no painting_estimate_log yet.
    """
    scores = defaultdict(lambda: defaultdict(int))
    conn = None
    try:
        conn = get_db()
        if not conn:
            return {}
        for kind, _label, table, user_col, ts_col in SCORED_SOURCES:
            try:
                cur = conn.cursor()
                cur.execute(
                    f'SELECT {user_col}, COUNT(*) FROM {table} '
                    f'WHERE {ts_col} >= %s AND {ts_col} < %s '
                    f'GROUP BY 1',
                    (start, end),
                )
                for user_key, n in cur.fetchall():
                    # `generated_by` can hold a short consultant key when the
                    # proposal tool had no SSO session — 'rachel' rather than
                    # 'rachel_farler'. Those rows used to fall through this
                    # guard and vanish from the leaderboard entirely.
                    owner = user_aliases.resolve_for(user_key, users)
                    if owner:
                        scores[owner][kind] += int(n or 0)
                cur.close()
            except Exception as e:
                # Roll back the aborted statement so the next query can run —
                # Postgres puts the whole connection in a failed state after an
                # error, and without this every remaining source would also fail.
                conn.rollback()
                print(f'weekly recap: skipped {table} ({e})')

        _collect_pipeline(conn, users, start, end, scores)
        _collect_usage(conn, users, start, end, scores)
        _collect_training(conn, users, start, end, scores)
    except Exception as e:
        print(f'weekly recap collect error: {e}')
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    return {k: dict(v) for k, v in scores.items()}


def _collect_pipeline(conn, users, start, end, scores):
    """Rows created and rows touched. Counted per row, not per keystroke.

    updated_at moves on every cell edit, so this is "rows you worked on this
    week", which is the honest unit — counting edits would rank whoever retypes
    a note the most.

    The touched query excludes a row only when the SAME person created it inside
    the window, which is the actual double-count worth avoiding (add a row, edit
    it, score twice). Excluding every in-window creation regardless of who did
    it was a real bug: a row Rachel created three weeks ago and Andy updated
    this week counted as a touch for Andy in the weekly window, but in the
    12-week window the creation fell inside the range, so the row went to Rachel
    as `pipeline_new` and Andy's touch vanished. That made a rolling total
    *lower* than the week inside it — impossible on its face, and how it was
    caught: Andy read 109 for the week against 84 for twelve weeks (2026-08-22).
    """
    try:
        cur = conn.cursor()
        cur.execute(
            'SELECT created_by, COUNT(*) FROM pipeline_board_entries '
            'WHERE created_at >= %s AND created_at < %s GROUP BY 1',
            (start, end),
        )
        for user_key, n in cur.fetchall():
            owner = user_aliases.resolve_for(user_key, users)
            if owner:
                scores[owner]['pipeline_new'] += int(n or 0)
        cur.execute(
            'SELECT updated_by, COUNT(*) FROM pipeline_board_entries '
            'WHERE updated_at >= %s AND updated_at < %s '
            '  AND NOT (created_at >= %s AND created_at < %s '
            '           AND created_by = updated_by) '
            'GROUP BY 1',
            (start, end, start, end),
        )
        for user_key, n in cur.fetchall():
            owner = user_aliases.resolve_for(user_key, users)
            if owner:
                scores[owner]['pipeline_touch'] += int(n or 0)
        cur.close()
    except Exception as e:
        conn.rollback()
        print(f'weekly recap: skipped pipeline ({e})')


def _collect_usage(conn, users, start, end, scores):
    """Generic hub_usage_events, minus opens.

    Mirrors the daily digest's arrangement deliberately: a new module that calls
    record_usage shows up here with no edit to this file, exactly as it shows up
    in the nightly email with no edit to daily_digest.py.
    """
    try:
        cur = conn.cursor()
        cur.execute(
            'SELECT user_key, COUNT(*) FROM hub_usage_events '
            'WHERE created_at >= %s AND created_at < %s AND action IN %s '
            'GROUP BY 1',
            (start, end, tuple(SCORED_USAGE_ACTIONS)),
        )
        for user_key, n in cur.fetchall():
            owner = user_aliases.resolve_for(user_key, users)
            if owner:
                scores[owner]['hub_actions'] += int(n or 0)
        cur.close()
    except Exception as e:
        conn.rollback()
        print(f'weekly recap: skipped usage events ({e})')


def _collect_training(conn, users, start, end, scores):
    """Training items actually completed — not items merely ticked and unticked.

    Filters on completed = TRUE and completed_at, rather than updated_at, so
    unchecking and rechecking a box doesn't farm points.
    """
    for table, kind in (('psc_training_progress', 'training'),
                        ('pm_training_progress', 'training')):
        try:
            cur = conn.cursor()
            cur.execute(
                f'SELECT user_key, COUNT(*) FROM {table} '
                f'WHERE completed = TRUE AND completed_at >= %s AND completed_at < %s '
                f'GROUP BY 1',
                (start, end),
            )
            for user_key, n in cur.fetchall():
                owner = user_aliases.resolve_for(user_key, users)
                if owner:
                    scores[owner][kind] += int(n or 0)
            cur.close()
        except Exception as e:
            conn.rollback()
            print(f'weekly recap: skipped {table} ({e})')


# ── Ranking ─────────────────────────────────────────────────────────────────

def build_groups(users, scores, exclude=None, rolling=None):
    """[{'name', 'rows': [{user_key, display, total, rolling, breakdown, rank}]}].

    Ranked on the WEEK, not the rolling figure. The weekly number is the one
    meant to change behaviour; the 12-week column is context for reading it —
    it separates "quiet week" from "quiet quarter", which a single number
    cannot. Ranking on the rolling total instead would make the board almost
    static and stop rewarding a good week.

    Everyone on the roster appears, including a zero week — the absence of a
    name would be read as an oversight, and a visible 0 is the entire point of
    what Thomas asked for. Ties share a rank.
    """
    exclude = exclude or set()
    rolling = rolling or {}
    groups = []
    for group_name, roles in ROLE_GROUPS:
        rows = []
        for user_key, user in users.items():
            if user_key in exclude or user.get('role') not in roles:
                continue
            breakdown = scores.get(user_key, {})
            roll_breakdown = rolling.get(user_key) or {}
            rows.append({
                'user_key': user_key,
                'display': user.get('display', user_key),
                'total': score_total(breakdown, weeks=1),
                'rolling': score_total(roll_breakdown, weeks=ROLLING_WEEKS),
                'breakdown': breakdown,
                'raw_total': sum(breakdown.values()),
            })
        rows.sort(key=lambda r: (-r['total'], -r['rolling'], r['display']))
        last_total, last_rank = None, 0
        for i, row in enumerate(rows, start=1):
            if row['total'] != last_total:
                last_rank, last_total = i, row['total']
            row['rank'] = last_rank
        if rows:
            groups.append({'name': group_name, 'rows': rows})
    return groups


# (singular, plural) written out rather than derived. Stripping a trailing 's'
# and lowercasing turned "PPMs" into "ppms" and "TPS scopes" into "tps scopes",
# which looks careless in an email people are being ranked by.
INLINE_LABELS = {
    'proposal':       ('proposal', 'proposals'),
    'ppm':            ('PPM', 'PPMs'),
    'tps':            ('TPS scope', 'TPS scopes'),
    'site_visit':     ('site visit', 'site visits'),
    'siding':         ('siding estimate', 'siding estimates'),
    'roofing':        ('roofing estimate', 'roofing estimates'),
    'gutter':         ('gutter estimate', 'gutter estimates'),
    'painting':       ('painting estimate', 'painting estimates'),
    'office_ops':     ('Office Ops pack', 'Office Ops packs'),
    'pipeline_new':   ('pipeline row added', 'pipeline rows added'),
    'pipeline_touch': ('pipeline row updated', 'pipeline rows updated'),
    'hub_actions':    ('Hub action', 'Hub actions'),
    'training':       ('training item', 'training items'),
}


def breakdown_line(breakdown):
    """'4 proposals · 2 TPS scopes · 11 pipeline rows updated'."""
    parts = []
    for key, n in sorted(breakdown.items(), key=lambda kv: (-kv[1], kv[0])):
        if not n:
            continue
        fallback = key.replace('_', ' ')
        singular, plural = INLINE_LABELS.get(key, (fallback, fallback))
        parts.append(f'{n} {singular if n == 1 else plural}')
    return ' · '.join(parts)


# ── Email ───────────────────────────────────────────────────────────────────

def build_recap_email(groups, start, recipient_key=None, users=None):
    """(subject, text_body, html_body) — one person's copy of the recap."""
    label = week_label(start)
    total = sum(r['total'] for g in groups for r in g['rows'])
    # Thomas, 2026-08-31. "PPS Hub — week of Aug 17–23" said when the email was
    # about, not what it was, and it lands in an inbox beside every other
    # automated Hub message. Naming the ranking in the subject is the point:
    # this is the one email that tells someone where they stand, and it should
    # be findable a month later by searching for what it does.
    subject = f'PPS Hub Activity Ranked Week of {label}'

    you = None
    for g in groups:
        for r in g['rows']:
            if r['user_key'] == recipient_key:
                you = (g, r)

    text = [f'PPS HUB — WEEK OF {label.upper()}', '']
    if you:
        g, r = you
        n_in_group = len(g['rows'])
        text.append(f"You: {r['total']} this week — #{r['rank']} of {n_in_group} in {g['name']}"
                    f"  ({r['rolling']} in the last {ROLLING_WEEKS} weeks)")
        if r['breakdown']:
            text.append(f"  {breakdown_line(r['breakdown'])}")
        else:
            text.append('  Nothing logged in the Hub last week.')
        text.append('')

    for g in groups:
        text.append(g['name'].upper())
        text.append(f"{'':>4}{'':<24}{'WEEK':>6}{'12 WK':>8}")
        for r in g['rows']:
            mark = '  <-- you' if r['user_key'] == recipient_key else ''
            name = r['display'][:24]
            text.append(f"  {r['rank']}. {name:<24}{r['total']:>6}{r['rolling']:>8}{mark}")
            detail = breakdown_line(r['breakdown'])
            if detail:
                text.append(f"        {detail}")
        text.append('')

    text.append(f'Team total: {total} this week · '
                f'{sum(r["rolling"] for g in groups for r in g["rows"])} '
                f'over {ROLLING_WEEKS} weeks')
    text.append('')
    text.append('Counts completed work — proposals, PPMs, TPS scopes, estimates, site')
    text.append('visits, Office Ops packs, training. Pipeline rows and other Hub actions')
    text.append(f'count too, up to {ACTIVITY_CAP_PER_WEEK} a week. Opening a page does not count.')
    text.append('')
    text.append(hub_url())

    html = _html_body(groups, label, total, recipient_key)
    return subject, '\n'.join(text), html


def hub_url():
    return os.environ.get('HUB_PUBLIC_URL', 'https://hub.purepropsolutions.com').rstrip('/')


def _html_body(groups, label, total, recipient_key):
    navy, ink, muted, rule = '#004C8C', '#1a1a1a', '#666', '#e3e8ef'
    out = [
        '<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;'
        f'max-width:640px;margin:0 auto;color:{ink};line-height:1.5;">',
        f'<h1 style="font-size:20px;margin:0 0 4px;color:{navy};">PPS Hub</h1>',
        f'<div style="color:{muted};font-size:14px;margin-bottom:24px;">Week of {label}</div>',
    ]
    for g in groups:
        out.append(
            f'<div style="font-size:12px;font-weight:700;letter-spacing:.08em;'
            f'text-transform:uppercase;color:{navy};margin:22px 0 8px;">{g["name"]}</div>'
        )
        out.append('<table style="width:100%;border-collapse:collapse;font-size:14px;">')
        out.append(
            f'<tr><td></td><td></td>'
            f'<td style="padding:0 8px 4px;text-align:right;font-size:10px;'
            f'letter-spacing:.08em;text-transform:uppercase;color:{muted};">Week</td>'
            f'<td style="padding:0 8px 4px;text-align:right;font-size:10px;'
            f'letter-spacing:.08em;text-transform:uppercase;color:{muted};">'
            f'{ROLLING_WEEKS} wk</td></tr>'
        )
        for r in g['rows']:
            mine = r['user_key'] == recipient_key
            bg = '#f4f8fc' if mine else 'transparent'
            weight = '700' if mine else '400'
            detail = breakdown_line(r['breakdown'])
            name = r['display'] + (' (you)' if mine else '')
            out.append(
                f'<tr style="background:{bg};">'
                f'<td style="padding:7px 8px;border-bottom:1px solid {rule};'
                f'width:28px;color:{muted};">{r["rank"]}</td>'
                f'<td style="padding:7px 8px;border-bottom:1px solid {rule};'
                f'font-weight:{weight};">{name}'
                + (f'<div style="color:{muted};font-size:12px;font-weight:400;">{detail}</div>'
                   if detail else '')
                + '</td>'
                f'<td style="padding:7px 8px;border-bottom:1px solid {rule};'
                f'text-align:right;font-weight:700;font-variant-numeric:tabular-nums;">'
                f'{r["total"]}</td>'
                f'<td style="padding:7px 8px;border-bottom:1px solid {rule};'
                f'text-align:right;color:{muted};font-variant-numeric:tabular-nums;">'
                f'{r["rolling"]}</td></tr>'
            )
        out.append('</table>')
    out.append(
        f'<div style="margin-top:24px;padding-top:14px;border-top:2px solid {navy};'
        f'font-size:14px;"><b>Team total: {total}</b> this week</div>'
    )
    out.append(
        f'<div style="color:{muted};font-size:12px;margin-top:14px;">'
        'Counts completed work — proposals, PPMs, TPS scopes, estimates, site visits, '
        'Office Ops packs, training. Pipeline rows and other Hub actions count too, up '
        f'to {ACTIVITY_CAP_PER_WEEK} a week. Opening a page does not count.'
        f'</div><div style="margin-top:18px;">'
        f'<a href="{hub_url()}" style="color:{navy};">Open the Hub</a></div></div>'
    )
    return ''.join(out)


# ── Runner ──────────────────────────────────────────────────────────────────

def run_weekly_recap(get_db, users, send_email_fn, force=False, today=None, now=None):
    """Send each person their copy. Returns a result dict for /health and logs.

    One email per person rather than one to everyone: the recipient's own row is
    highlighted and their standing is called out at the top, which is the part
    that makes it land. Nobody is BCC'd a list they have to scan for their name.
    """
    # One reference time drives both the window check and the reporting week, so
    # a caller cannot end up asking about one week while being judged against
    # another clock. `today` still overrides the week alone, for tests that only
    # care about the date maths.
    now = now or eastern_now()
    today = today or now.date()

    if not _enabled() and not force:
        return {'skipped': True, 'reason': 'disabled'}

    # Checked after `disabled` so an explicitly switched-off recap reports that
    # rather than the day of the week — matches run_daily_digest's ordering.
    if not force and not should_run_scheduled(now):
        return {'skipped': True, 'reason': 'not_scheduled'}

    start, end = last_week_bounds(today)
    if not force and already_sent_for(get_db, start):
        return {'skipped': True, 'reason': 'already_sent', 'week_label': week_label(start)}
    # Marked BEFORE the sending loop, not after. A retry is triggered by the
    # first attempt failing *late* — often after the emails already went — so a
    # marker written at the end would never be reached in exactly the case it
    # needs to guard.
    mark_sent(get_db, start)
    roll_start, roll_end = rolling_bounds(today)
    exclude = _excluded_keys()
    scores = collect_scores(get_db, users, start, end)
    # Same queries, wider window. Runs once a week, so a second pass is cheaper
    # than keeping a running tally that could drift out of step with the source
    # tables — this is always derived from the logs, never from a stored count.
    rolling = collect_scores(get_db, users, roll_start, roll_end)
    groups = build_groups(users, scores, exclude, rolling)
    if not groups:
        return {'skipped': True, 'reason': 'no_roster'}

    sent, failed = [], []
    for user_key, user in users.items():
        if user_key in exclude:
            continue
        email = (user.get('email') or '').strip()
        if not email:
            continue
        subject, text_body, html_body = build_recap_email(groups, start, user_key, users)
        try:
            ok = send_email_fn(subject, text_body, html_body, [email])
            (sent if ok else failed).append(user_key)
        except Exception as e:
            print(f'weekly recap send failed for {user_key}: {e}')
            failed.append(user_key)

    return {
        'skipped': False,
        'week_start': start.isoformat(),
        'week_end': end.isoformat(),
        'week_label': week_label(start),
        'sent': sent,
        'failed': failed,
        'total_actions': sum(r['total'] for g in groups for r in g['rows']),
        'rolling_weeks': ROLLING_WEEKS,
        'rolling_actions': sum(r['rolling'] for g in groups for r in g['rows']),
    }
