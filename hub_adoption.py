"""Who is actually using the Hub — the payoff for F-03's instrumentation.

Thomas, 2026-08-29: "Lets do 1", after this was ranked first because usage
events have been recording since 2026-08-26 and nothing reads them
company-wide. `dashboard_summary` uses them for your own "jump back in", the
digest and the recap each read a slice; nobody could ask "did the field guide
land" or "which of these twenty tools has nobody opened".

── Three quantities, never added together ──────────────────────────────────

The recap already establishes the rule and this page keeps it:

  * **Opens** are page views. They are NOT work, which is why
    `weekly_recap.SCORED_USAGE_ACTIONS` excludes `'open'` — a leaderboard
    that counts opens teaches people to open things.
  * **Actions** are the discrete things a page records beyond arriving:
    import, generate, upload, refresh. Recorded in the same table.
  * **Produced** is deliverables — proposals, PPMs, TPS scopes, estimates,
    site visits — counted from their own tables via `weekly_recap`.

Adoption is a different question from performance, so all three are shown
side by side and none of them is summed into a single number. A PM who
produces steadily through the proposal tool and rarely browses the Hub is not
the same person as one who has stopped; a single "activity" figure would
render them identically.

── What this page must not imply ───────────────────────────────────────────

Instrumentation covers twenty features from **2026-08-26**. Before that date
three features recorded and seventeen did not, so "nobody has opened the
Roofing Estimator" is only a claim about the days since. Every figure here is
labelled with that start date. Without it the page would read as history it
does not have, and the first person to notice would stop believing the rest.

Nothing here writes. A read must not create a table (see the note in
hub_usage.py), and every query degrades to empty rather than raising — a
diagnostic page that 500s when something is wrong is the page you needed.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

import hub_time
import hub_usage
import user_aliases
import weekly_recap

# F-03 landed 2026-08-26 (commit f503244). Before it, `record_usage` covered
# Pipeline, Compliance and Office Ops only. Any "never opened" claim is a
# claim about the days since this date and the page says so out loud.
INSTRUMENTED_SINCE = date(2026, 8, 26)

# Days without opening anything or producing anything. Not a judgement — a
# prompt to go and ask. Two thresholds because "quiet for a fortnight" and
# "gone for a month" are different conversations.
QUIET_DAYS = 14
DORMANT_DAYS = 30

# How many weeks of trend to draw. Six is enough to see a direction without
# reaching back past the instrumentation date for most of the chart.
TREND_WEEKS = 6


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def instrumented_from():
    """Eastern midnight on INSTRUMENTED_SINCE, as naive UTC.

    The date is an Eastern one — that is the day people in Ohio started being
    recorded. Combining it with UTC midnight and then displaying it in Eastern
    printed "August 25" for an August 26 constant, and pulled in four hours of
    events from the evening before. The same day-shift this page exists partly
    to stop mattering.
    """
    local = datetime.combine(INSTRUMENTED_SINCE, datetime.min.time())
    return local.replace(tzinfo=hub_time.ET).astimezone(timezone.utc).replace(
        tzinfo=None)


# ── reading ─────────────────────────────────────────────────────────────────

def fetch_usage(get_db, since=None):
    """Usage events since `since` (naive UTC). [] on any failure.

    Deliberately does not call `hub_usage.ensure_tables`: a read must not
    create a table, and a Hub where nobody has opened anything should show an
    empty page rather than quietly gaining a table.
    """
    conn = None
    try:
        conn = get_db()
        if not conn:
            return []
        cur = conn.cursor()
        cur.execute(
            'SELECT user_key, feature, action, created_at '
            'FROM hub_usage_events WHERE created_at >= %s '
            'ORDER BY created_at',
            (since or instrumented_from(),),
        )
        rows = [
            {'user_key': r[0], 'feature': r[1], 'action': r[2], 'created_at': r[3]}
            for r in cur.fetchall()
        ]
        cur.close()
        return rows
    except Exception as e:
        print(f'adoption: could not read usage events ({e})')
        return []
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def last_produced(get_db, users):
    """({user_key: newest deliverable}, {unmatched_key: count}).

    Reuses `weekly_recap.SCORED_SOURCES` rather than listing the tables again.
    Two definitions of "did work" that have to agree is how they stop agreeing,
    and this page sitting beside the Monday email makes that especially easy
    to notice.

    **The second return value is the point.** This function used to filter
    `if user_key in users` and throw away everything else, which is how Rachel
    came to have produced nothing: the proposal tool writes `generated_by` as
    the short consultant key when it has no SSO session, so her rows said
    `'rachel'` and no roster key matched. Aliases now resolve
    (`user_aliases`), and anything still unmatched is *counted and reported*
    rather than dropped. A page that silently discards what it cannot explain
    is the page that told Thomas she had done nothing.
    """
    out = {}
    unmatched = defaultdict(int)
    conn = None
    try:
        conn = get_db()
        if not conn:
            # Same shape as the success path. Returning a bare {} here made the
            # failure case unpackable-into-two only when it worked, which is
            # the sort of thing that only shows up when the database is down.
            return {}, {}
        for _kind, _label, table, user_col, ts_col in weekly_recap.SCORED_SOURCES:
            try:
                cur = conn.cursor()
                cur.execute(
                    f'SELECT {user_col}, MAX({ts_col}) FROM {table} '
                    f'WHERE {user_col} IS NOT NULL GROUP BY 1'
                )
                for user_key, ts in cur.fetchall():
                    owner = user_aliases.resolve_for(user_key, users)
                    if not owner:
                        unmatched[(user_key or '(blank)')] += 1
                        continue
                    if ts and (owner not in out or ts > out[owner]):
                        out[owner] = ts
                cur.close()
            except Exception as e:
                # Postgres fails the whole connection after an error, so the
                # rollback is what lets the remaining tables still be read.
                conn.rollback()
                print(f'adoption: skipped {table} ({e})')
    except Exception as e:
        print(f'adoption: last_produced error ({e})')
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    return out, dict(unmatched)


# ── rollups (pure) ──────────────────────────────────────────────────────────

def by_feature(rows, labels=None, known=None):
    """One row per instrumented feature, busiest first.

    Every known feature appears, including the ones with nothing — a tool
    nobody has opened is the finding, and leaving it off the list hides
    exactly the thing worth seeing.
    """
    labels = labels or hub_usage.FEATURE_LABELS
    known = known or set(hub_usage.KNOWN_FEATURES)
    opens = defaultdict(int)
    actions = defaultdict(int)
    people = defaultdict(set)
    last = {}
    for row in rows:
        feature = row.get('feature')
        if not feature:
            continue
        if row.get('action') == 'open':
            opens[feature] += 1
        else:
            actions[feature] += 1
        if row.get('user_key'):
            people[feature].add(row['user_key'])
        ts = row.get('created_at')
        if ts and (feature not in last or ts > last[feature]):
            last[feature] = ts

    out = []
    for feature in sorted(set(known) | set(opens) | set(actions)):
        out.append({
            'feature': feature,
            'label': labels.get(feature, feature.replace('_', ' ').title()),
            'opens': opens.get(feature, 0),
            'actions': actions.get(feature, 0),
            'people': len(people.get(feature, ())),
            'last_used': last.get(feature),
            'untouched': not opens.get(feature) and not actions.get(feature),
        })
    out.sort(key=lambda f: (-f['people'], -f['opens'], f['label']))
    return out


def untouched_features(feature_rows):
    """The tools nobody has opened at all. The point of the page."""
    return [f for f in feature_rows if f['untouched']]


def unmatched_usage(rows, users):
    """{key: count} for usage events belonging to nobody on the roster.

    Usually a departed employee's history, which is fine and expected. Worth
    showing anyway: the alternative is a page that quietly knows about work it
    is not telling you about.
    """
    out = defaultdict(int)
    for row in rows:
        key = row.get('user_key')
        if key and not user_aliases.resolve_for(key, users):
            out[key or '(blank)'] += 1
    return dict(out)


def by_person(rows, users, produced=None, now=None):
    """One row per person on the roster, quietest first.

    Everyone appears, including people with nothing — an omitted name reads as
    an oversight, the same reason the weekly recap lists a visible zero.
    """
    now = now or _utcnow()
    produced = produced or {}
    opens = defaultdict(int)
    actions = defaultdict(int)
    features = defaultdict(set)
    last_open = {}
    for row in rows:
        key = user_aliases.resolve_for(row.get('user_key'), users)
        if not key:
            continue
        if row.get('action') == 'open':
            opens[key] += 1
        else:
            actions[key] += 1
        if row.get('feature'):
            features[key].add(row['feature'])
        ts = row.get('created_at')
        if ts and (key not in last_open or ts > last_open[key]):
            last_open[key] = ts

    out = []
    for key, info in (users or {}).items():
        seen = last_open.get(key)
        made = produced.get(key)
        newest = max([t for t in (seen, made) if t], default=None)
        out.append({
            'user_key': key,
            'display': (info or {}).get('display', key),
            'role': (info or {}).get('role', ''),
            'tier': (info or {}).get('tier', 'team'),
            'opens': opens.get(key, 0),
            'actions': actions.get(key, 0),
            'features': len(features.get(key, ())),
            'last_open': seen,
            'last_produced': made,
            'days_quiet': _days_between(newest, now),
            'ago': ago_label(_days_between(newest, now)),
            'state': _state(newest, now),
        })
    # Quietest first: the people this page exists to surface.
    out.sort(key=lambda p: (-(p['days_quiet'] if p['days_quiet'] is not None
                              else 10 ** 6), p['display']))
    return out


def _days_between(then, now):
    """Whole days between two naive-UTC stamps, or None if there is no `then`."""
    if not then:
        return None
    try:
        return max(0, (hub_time.to_eastern(now).date()
                       - hub_time.to_eastern(then).date()).days)
    except Exception:
        return None


def ago_label(days):
    """"today" / "yesterday" / "3 days ago". "0d ago" is not a thing anyone
    says, and this column is read at a glance."""
    if days is None:
        return 'nothing yet'
    if days == 0:
        return 'today'
    if days == 1:
        return 'yesterday'
    return f'{days} days ago'


def _state(newest, now):
    days = _days_between(newest, now)
    if days is None:
        return 'never'
    if days >= DORMANT_DAYS:
        return 'dormant'
    if days >= QUIET_DAYS:
        return 'quiet'
    return 'active'


def by_week(rows, now=None, weeks=TREND_WEEKS):
    """Opens, actions and distinct people per Eastern week, oldest first.

    Weeks start on the Eastern Monday, matching the recap's window, so a
    Monday morning here means the same Monday morning as the email.
    """
    now = now or _utcnow()
    this_monday = _week_start(now)
    # Never draw a week that ended before anything was being recorded. Five
    # rows of zeros ahead of the real ones do not read as "no data" — they
    # read as a collapse, which is the opposite of the truth and exactly the
    # misreading the note at the top of the page is there to prevent.
    floor = _week_start(instrumented_from())
    buckets = []
    for back in range(weeks - 1, -1, -1):
        start = this_monday - timedelta(days=7 * back)
        if start < floor:
            continue
        buckets.append({
            'start': start,
            'label': hub_time.fmt(start, '%b %-d'),
            'opens': 0, 'actions': 0, 'people': set(),
            'partial': back == 0,
        })
    for row in rows:
        ts = row.get('created_at')
        if not ts:
            continue
        start = _week_start(ts)
        for bucket in buckets:
            if bucket['start'] == start:
                if row.get('action') == 'open':
                    bucket['opens'] += 1
                else:
                    bucket['actions'] += 1
                if row.get('user_key'):
                    bucket['people'].add(row['user_key'])
                break
    for bucket in buckets:
        bucket['people'] = len(bucket['people'])
    return buckets


def _week_start(ts):
    """Eastern Monday midnight for a naive-UTC stamp, back as naive UTC."""
    local = hub_time.to_eastern(ts)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    monday = midnight - timedelta(days=midnight.weekday())
    return monday.astimezone(timezone.utc).replace(tzinfo=None)


def guide_readers(rows, users, feature='guide'):
    """Who has opened the field guide, and who has not.

    Deliberately no before/after comparison. The guide shipped on 2026-08-27
    alongside four other changes, the roster is thirteen people, and any
    "readers did more" number off that would be a coincidence dressed as a
    finding. Who has not opened it is actionable on its own: those are the
    people to hand it to directly.
    """
    read = {}
    for row in rows:
        if row.get('feature') != feature or not row.get('user_key'):
            continue
        ts = row.get('created_at')
        key = row['user_key']
        if ts and (key not in read or ts > read[key]):
            read[key] = ts
    readers, missing = [], []
    for key, info in (users or {}).items():
        entry = {'user_key': key, 'display': (info or {}).get('display', key),
                 'when': read.get(key)}
        (readers if key in read else missing).append(entry)
    readers.sort(key=lambda r: r['when'], reverse=True)
    missing.sort(key=lambda r: r['display'])
    return {'readers': readers, 'missing': missing,
            'roster': len(users or {}), 'read_count': len(readers)}


def build(get_db, users, now=None):
    """Everything the page needs. Never raises; empty sections on failure."""
    now = now or _utcnow()
    rows = fetch_usage(get_db)
    features = by_feature(rows)
    produced, orphan_work = last_produced(get_db, users)
    # Everything the page knows about but cannot pin on anybody. Kept together
    # so it is one visible line rather than several silent filters.
    unattributed = {'work': orphan_work, 'usage': unmatched_usage(rows, users)}
    return {
        'since': INSTRUMENTED_SINCE,
        # Formatted straight off the date. Running it through the timezone
        # conversion is what printed the day before.
        'since_label': INSTRUMENTED_SINCE.strftime('%B %-d, %Y'),
        # Inclusive: the first day counts as a day of data.
        'days_of_data': max(
            1, (hub_time.to_eastern(now).date() - INSTRUMENTED_SINCE).days + 1),
        'events': len(rows),
        'features': features,
        'untouched': untouched_features(features),
        'people': by_person(rows, users, produced=produced, now=now),
        'unattributed': unattributed,
        'weeks': by_week(rows, now=now),
        'guide': guide_readers(rows, users),
        'quiet_days': QUIET_DAYS,
        'dormant_days': DORMANT_DAYS,
    }
