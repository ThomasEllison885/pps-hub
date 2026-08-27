"""Naive UTC in the database, Eastern on the screen.

── The bug this exists to fix ──────────────────────────────────────────────

Every timestamp column in the Hub is **naive UTC** — `TIMESTAMP DEFAULT
NOW()` on a Postgres running in UTC, and the Python that writes them uses
`datetime.now(timezone.utc).replace(tzinfo=None)`. Templates then rendered
them with a bare `{{ item.submitted_at.strftime(...) }}`, which formats
those UTC numbers unchanged. So every date and time in the Hub was shown in
UTC while everyone reading it is in Ohio.

Thomas noticed it on the feedback inbox (2026-08-25), where the format
includes a clock time and it is off by four or five hours depending on the
season. The date-only sites were wrong less often but more confusingly:
anything created after 8pm Eastern renders under *tomorrow's* date.

The pattern already existed and was correct in exactly one place —
`system_state._eastern_label`, used for the jobs table. It was never applied
anywhere else. This module is that function, promoted somewhere every
template can reach it.

── Using it ────────────────────────────────────────────────────────────────

In a template, replace

    {{ item.submitted_at.strftime('%B %d, %Y at %I:%M %p') }}

with

    {{ item.submitted_at | et_at }}

`et` is the date, `et_at` the date and time, and `et_fmt` takes a strftime
string for anything else. All three take None and hand back an empty string,
so the `{% if %}` guards around the old calls are no longer load-bearing
(they were there because `.strftime` on None raises).

**Do not call `.strftime` directly on a database timestamp in a template.**
That is the bug. `tests/test_hub_time.py` fails if a new one appears.

── What it does not do ─────────────────────────────────────────────────────

It does not touch anything the crons compute. `weekly_recap` and
`daily_digest` already convert properly for their windows — that work is
about *which rows fall in a period* and is far more delicate than
formatting (see the DST notes in `weekly_recap.last_week_bounds`). They
keep their own `ET` and their own bounds helpers. This is display only.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')

# Formats used across the Hub, named so a change lands everywhere at once.
DATE = '%b %d, %Y'
DATE_LONG = '%B %d, %Y'
DATE_SHORT = '%b %d'
DATE_TIME = '%b %d, %Y at %-I:%M %p'
DATE_TIME_LONG = '%B %d, %Y at %-I:%M %p'
TIME_ONLY = '%-I:%M %p'


def to_eastern(value):
    """Naive-UTC (or aware) datetime → aware Eastern. None passes through.

    A `date` with no time has no timezone to convert — midnight in one zone
    is the previous evening in another, and shifting it would move the day.
    It comes back unchanged.
    """
    if value is None:
        return None
    if isinstance(value, str):
        # Some modules hand templates `created_at.isoformat()` rather than the
        # datetime — office_ops does it for everything it stores. Those were
        # being sliced by hand (`[:16].replace('T',' ')`), which renders raw
        # UTC. Parse it here so `| et_at` works on either shape; anything that
        # is not a timestamp comes back untouched and formats as ''.
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return value
    if isinstance(value, datetime):
        try:
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(ET)
        except Exception:
            return value
    return value


def fmt(value, pattern=DATE):
    """Format a Hub timestamp in Eastern. '' for anything unformattable.

    Deliberately total: a template is the worst place to raise. A None, a
    string that came back from a driver that did not parse, an odd type from
    a sparse old row — all render as nothing, which is what the `{% if %}`
    around the old `.strftime` calls was doing by hand.
    """
    local = to_eastern(value)
    if local is None:
        return ''
    if not hasattr(local, 'strftime'):
        return ''
    try:
        return local.strftime(pattern)
    except Exception:
        # %-I is glibc; every platform this runs on has it, but a fallback
        # costs nothing and beats a blank page.
        try:
            return local.strftime(pattern.replace('%-I', '%I').replace('%-d', '%d'))
        except Exception:
            return ''


def date_label(value):
    return fmt(value, DATE)


def datetime_label(value):
    return fmt(value, DATE_TIME)


def now():
    """Eastern now. Same as weekly_recap.eastern_now, for display code."""
    return datetime.now(ET)


# One source of truth, so a test harness rendering a template gets exactly
# the filters the app has. Adding one here reaches both.
FILTERS = {
    'et': date_label,
    'et_at': datetime_label,
    'et_long': lambda v: fmt(v, DATE_LONG),
    'et_fmt': fmt,
}


def register(app):
    """Install the `et*` Jinja filters on a Flask app."""
    app.jinja_env.filters.update(FILTERS)
    return app
