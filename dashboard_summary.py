"""What a person should see before fifteen tool cards.

The dashboard has always been a launcher: a greeting, then every tool the
Hub owns, in lanes, expanded. Measured on a 390px phone it was 3,446px —
4.1 screens — with the first tool link 258px down and nothing above it but
"Good morning". Whatever the person came to check, they scrolled for it.

This module supplies the two blocks that go above the lanes. Both are built
from data the Hub already has; neither adds a table.

  * **Pills** — a single line of small facts, each one a link. Your activity
    this week, in-progress rows on your board, training that isn't finished,
    and (for the owner) an unread count worth acting on.

  * **Jump back in** — the three tools this person most recently used,
    derived from the same logs the Recent Activity feed at the bottom of the
    page is already reading, plus `hub_usage_events` for the features that
    have no log of their own.

── The rule that shapes all of it ──────────────────────────────────────────

**Nothing renders at zero.** A pill with a 0 in it is not information, it is
a reproach, and thirteen people opening a dashboard that tells them they
have done nothing is a good way to make them stop opening it. A quiet week
produces a short strip, or no strip at all, and the page simply starts at
Jump back in. Every builder here returns a list that can legitimately be
empty and the template handles that.

── Why the week number is the recap's number ───────────────────────────────

`week_scores` does not invent an arithmetic. It calls
`weekly_recap.collect_scores` and `weekly_recap.score_total` — the same two
functions that produce Monday's email — over the current week to date. That
is deliberate and load-bearing: people argue with their number, and the only
defensible answer is "it is the same count, from the same tables, as the
email you already get". If the recap's definition of a point changes, this
changes with it and cannot drift. Do not add a source here that the recap
does not score, and in particular do not start counting page opens — see the
note above SCORED_USAGE_ACTIONS in weekly_recap.py for why that stays out.

── Why it is cached, and why the cache holds everyone ──────────────────────

`collect_scores` is roughly a dozen GROUP BY queries. There is still no
connection pool (review F-05), so running that per dashboard load would be
the most expensive thing on the page by a wide margin. It is cached for
CACHE_TTL_SECONDS.

The cache holds the whole `{user_key: ...}` map rather than one person's
row, because `collect_scores` computes everyone in the same dozen queries —
scoping it to one user would cost the same and then have to be repeated for
the next person to load their dashboard. One cold computation per gunicorn
worker per five minutes serves the entire company.

The key includes the week start, so the Monday rollover invalidates it
without anyone remembering to. A DB failure caches nothing, so the next
request retries rather than serving an empty strip for five minutes.
"""

from __future__ import annotations

import time as _time
from datetime import datetime, timedelta, timezone

import weekly_recap

CACHE_TTL_SECONDS = 300

# ── The one setting here that is a call about people, not about data ────────
#
# True: everyone sees their own week-to-date activity count on their own
# dashboard. False: only the owner does.
#
# Set True on 2026-08-25. The reasoning, so it can be reversed knowingly
# rather than by taste: this number is already public inside PPS. The weekly
# recap emails a ranked leaderboard with everyone's name on it to the whole
# company every Monday, and Team View is open to every tier. Showing a person
# their own figure on their own page tells them nothing the rest of the team
# is not already being told about them, and it lets them see a bad week on
# Wednesday instead of finding out on Monday.
#
# The argument the other way is real and is why this is a named constant
# rather than a hardcoded True: a number on your own dashboard reads as being
# kept on you in a way a group email does not. If it starts feeling like a
# scoreboard, flip this — the rest of the strip is unaffected, and
# `tests/test_dashboard_summary.py::test_show_week_false_hides_only_the_week_pill`
# pins that.
SHOW_WEEK_SCORE_TO_EVERYONE = True


def _utcnow():
    """Naive UTC. `datetime.utcnow()` was cleared repo-wide on 2026-08-21 --
    see CLAUDE.md -- and the columns this is compared against are all naive
    UTC, so the tzinfo has to come straight back off."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

# {week_start: (monotonic_stamp, {user_key: score})}
_score_cache: dict = {}


def _now_monotonic():
    return _time.monotonic()


def week_scores(get_db, users, today=None, use_cache=True):
    """{user_key: int} — this week's recap score, week-to-date.

    Never raises and never returns None: a database that is down produces an
    empty dict, which the pill builder reads as "no pill", not as "zero".
    """
    start, end = weekly_recap.current_week_bounds(today=today)
    if use_cache:
        hit = _score_cache.get(start)
        if hit and (_now_monotonic() - hit[0]) < CACHE_TTL_SECONDS:
            return hit[1]

    try:
        raw = weekly_recap.collect_scores(get_db, users, start, end)
    except Exception as e:  # collect_scores swallows its own, but be certain
        print(f'dashboard summary: score collection failed ({e})')
        return {}

    if not raw:
        # Either a genuinely empty week or a failed read — collect_scores
        # returns {} for both. Not cached, so a broken database costs one
        # retry per request rather than five minutes of a blank strip.
        return {}

    scores = {
        key: weekly_recap.score_total(breakdown, weeks=1)
        for key, breakdown in raw.items()
    }
    if use_cache:
        _score_cache.clear()  # only ever one live week
        _score_cache[start] = (_now_monotonic(), scores)
    return scores


def clear_cache():
    _score_cache.clear()


def pipeline_in_progress(get_db, pair_key, completed_statuses):
    """Rows on this person's default board that the board itself highlights.

    `completed_statuses` is passed in rather than imported so this module
    does not depend on pipeline_board — but it must be
    `pipeline_board.COMPLETED_STATUSES`. The point of using the board's own
    constant is that the number here equals the number of highlighted rows
    the person sees when they open the board, which makes it checkable by
    eye. If the board's definition of "still in progress" changes, this
    follows it. Do not substitute a nicer-sounding rule (e.g. excluding
    declined rows) here alone — that would put two different answers to the
    same question on two pages.

    Returns None on any failure, which the pill builder treats as "say
    nothing" rather than "zero".
    """
    if not pair_key:
        return None
    statuses = list(completed_statuses or ())
    conn = None
    try:
        conn = get_db()
        if not conn:
            return None
        cur = conn.cursor()
        if statuses:
            cur.execute(
                'SELECT COUNT(*) FROM pipeline_board_entries '
                'WHERE pair_key = %s AND archived = FALSE '
                'AND COALESCE(status, %s) <> ALL(%s)',
                (pair_key, 'new', statuses),
            )
        else:
            cur.execute(
                'SELECT COUNT(*) FROM pipeline_board_entries '
                'WHERE pair_key = %s AND archived = FALSE',
                (pair_key,),
            )
        row = cur.fetchone()
        cur.close()
        return int(row[0]) if row else None
    except Exception as e:
        print(f'dashboard summary: pipeline count failed ({e})')
        return None
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def build_pills(
    week_score=None,
    pipeline_open=None,
    pipeline_url=None,
    psc_pct=None,
    pm_pct=None,
    unread_feedback=0,
    unread_diffs=0,
    is_owner=False,
    show_week=True,
):
    """The strip, in display order. Empty list is a valid, expected result.

    Every argument is optional and every zero, None or 100%-complete value
    drops its pill. See the module docstring: nothing renders at zero.

    `show_week` exists so the activity pill can be switched off for everyone
    but the owner without touching the template — the one thing here that is
    a judgement call about people rather than about data.
    """
    pills = []

    if show_week and week_score:
        pills.append({
            'key': 'week',
            'value': str(week_score),
            'label': 'this week',
            'url': '/team-view',
            'tone': 'blue',
        })

    if pipeline_open:
        pills.append({
            'key': 'pipeline',
            'value': str(pipeline_open),
            'label': 'in progress',
            'url': pipeline_url or '/pipeline-board',
            'tone': 'slate',
        })

    # Training pills exist to close a loop, so a finished programme is not a
    # standing reminder. 100% drops off; so does an un-enrolled person, and
    # so does 0% — someone who has not started does not need the dashboard
    # opening with a zero.
    if psc_pct and 0 < psc_pct < 100:
        pills.append({
            'key': 'psc',
            'value': f'{psc_pct}%',
            'label': 'PSC training',
            'url': '/psc-training',
            'tone': 'green',
        })
    if pm_pct and 0 < pm_pct < 100:
        pills.append({
            'key': 'pm',
            'value': f'{pm_pct}%',
            'label': 'PM training',
            'url': '/pm-training',
            'tone': 'green',
        })

    if is_owner and unread_feedback:
        pills.append({
            'key': 'feedback',
            'value': str(unread_feedback),
            'label': 'feedback',
            'url': '/admin/feedback',
            'tone': 'amber',
        })
    if is_owner and unread_diffs:
        pills.append({
            'key': 'diffs',
            'value': str(unread_diffs),
            'label': 'comparisons',
            'url': '/admin/diffs',
            'tone': 'amber',
        })

    # Deliberately uncapped. Five pills wrap to a second short line on a
    # phone; dropping the fifth would silently hide a real number to protect
    # a layout, which is the wrong trade for a strip whose entire job is to
    # be the honest summary.
    return pills


# ── Jump back in ────────────────────────────────────────────────────────────
#
# `external` marks the tools that live in pps-proposal-tool and are opened
# through the dashboard's existing openTool() shim rather than a plain link;
# the template needs to know which is which.

TOOLS = {
    'proposal':     {'icon': '✍️',  'name': 'Proposal Generator', 'path': '/proposal',  'external': True},
    'ppm':          {'icon': '📋',  'name': 'PPM Checklist',      'path': '/ppm',       'external': True},
    'tps':          {'icon': '📝',  'name': 'Trade Partner Scope', 'path': '/subscope', 'external': True},
    'estimate':     {'icon': '📊',  'name': 'Estimating',         'path': '/estimating'},
    'site_visit':   {'icon': '🏗️', 'name': 'Site Visit Report',  'path': '/site-visit'},
    'pipeline':     {'icon': '🗂️', 'name': 'Pipeline Board',     'path': '/pipeline-board'},
    'office_ops':   {'icon': '📥',  'name': 'Office Ops',         'path': '/office-ops'},
    'compliance':   {'icon': '🛡️', 'name': 'Compliance',         'path': '/office-ops/compliance'},
    'psc_training': {'icon': '🎓',  'name': 'PSC Training',       'path': '/psc-training'},
    'pm_training':  {'icon': '🔧',  'name': 'PM Training',        'path': '/pm-training'},
}

# hub_usage_events.feature -> tool key. Only the features that map to a place
# worth returning to; anything unrecognised is ignored rather than guessed at.
USAGE_FEATURE_TO_TOOL = {
    'pipeline': 'pipeline',
    'office_ops': 'office_ops',
    'compliance': 'compliance',
}


def _latest(seq, field='generated_at'):
    best = None
    for row in seq or []:
        try:
            ts = row.get(field)
        except AttributeError:
            ts = None
        if ts is None:
            continue
        if best is None or ts > best:
            best = ts
    return best


def recent_tools(
    sources,
    usage_rows=None,
    proposal_url='',
    allowed=None,
    limit=3,
):
    """The tools this person actually returns to, most recent first.

    `sources` is {tool_key: rows} where each row carries a `generated_at` —
    exactly the lists the dashboard route already fetched to build Recent
    Activity at the bottom of the page. This block asks a different question
    of the same data: not "what did you make" but "where were you".

    Ranking is by **most recent use, not frequency**. Those lists are capped
    at LIMIT 5 per kind by the route, so a count taken from them is bounded
    and would rank a burst of five estimates above the twenty proposals it
    could not see. A max timestamp is exact regardless of how many rows came
    back, which is why it is the only thing this reads.

    `usage_rows` is [(feature, last_used)] from hub_usage_events, covering
    Pipeline, Office Ops and Compliance — the features that write no log of
    their own.

    `allowed`, when given, is the set of tool keys this person may still
    open. History is not permission: someone who used Office Ops before a
    tier change must not be handed a card back to it. Omitted means no
    filtering, which is only correct in tests.
    """
    stamps = {}

    for key, rows in (sources or {}).items():
        if key not in TOOLS:
            continue
        ts = _latest(rows)
        if ts is not None:
            stamps[key] = max(stamps.get(key, ts), ts)

    for row in usage_rows or []:
        try:
            feature, ts = row[0], row[1]
        except (TypeError, IndexError, KeyError):
            continue
        key = USAGE_FEATURE_TO_TOOL.get(feature)
        if not key or ts is None:
            continue
        stamps[key] = max(stamps.get(key, ts), ts)

    if allowed is not None:
        stamps = {k: v for k, v in stamps.items() if k in allowed}

    ordered = sorted(stamps.items(), key=lambda kv: kv[1], reverse=True)[:limit]

    out = []
    for key, ts in ordered:
        spec = TOOLS[key]
        external = bool(spec.get('external'))
        out.append({
            'key': key,
            'icon': spec['icon'],
            'name': spec['name'],
            'url': (proposal_url or '') + spec['path'] if external else spec['path'],
            'external': external,
            'when': _relative_day(ts),
        })
    return out


def _relative_day(ts, now=None):
    """'Today' / 'Yesterday' / 'Aug 12'. Empty string if it cannot be read.

    Both sides are naive UTC — every timestamp column in the Hub is — so this
    compares like with like and does not convert to Eastern. The result is a
    soft recency hint on a card, not a figure anyone reconciles against
    anything, and a page that throws because one row had an odd type would be
    a much worse outcome than "Aug 12" being "Aug 11" for a few late-evening
    hours.
    """
    if ts is None:
        return ''
    try:
        now = now or _utcnow()
        delta = now.date() - ts.date()
    except Exception:
        return ''
    if delta <= timedelta(0):
        return 'Today'
    if delta == timedelta(days=1):
        return 'Yesterday'
    if delta < timedelta(days=7):
        return f'{delta.days} days ago'
    try:
        return ts.strftime('%b %d')
    except Exception:
        return ''


def recent_usage_features(get_db, user_key, days=60):
    """[(feature, last_used)] for one person. [] on any failure.

    One grouped query on the (user_key, created_at DESC) index that
    hub_usage.init_tables already creates. It is not wrapped in
    init_tables — this is a read, and a Hub where nobody has ever opened the
    Pipeline Board should show no pipeline card, not create a table on a
    dashboard load. A missing table lands in the except and returns [].
    """
    if not user_key:
        return []
    conn = None
    try:
        conn = get_db()
        if not conn:
            return []
        cur = conn.cursor()
        cur.execute(
            'SELECT feature, MAX(created_at) FROM hub_usage_events '
            'WHERE user_key = %s AND created_at >= %s '
            'GROUP BY feature',
            (user_key, _utcnow() - timedelta(days=days)),
        )
        rows = [(r[0], r[1]) for r in cur.fetchall()]
        cur.close()
        return rows
    except Exception as e:
        print(f'dashboard summary: usage read failed ({e})')
        return []
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
