"""Naive-UTC columns rendered in Eastern.

Run: python -m pytest tests/test_hub_time.py -v

The Hub stores every timestamp as naive UTC and used to render it with a
bare `.strftime` in the template, which showed UTC to people in Ohio. On the
feedback inbox — the one format with a clock time in it — that was four or
five hours out. On the date-only ones it was subtler and worse: anything
logged after 8pm Eastern appeared under tomorrow's date.

The last test in this file is the one that matters longest: it fails if a
new `.strftime` on a database timestamp appears in any template.
"""
import os
import re
import sys
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hub_time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UTC = timezone.utc


def test_the_bug_summer():
    """Feedback submitted 00:30 UTC on the 26th is 8:30pm on the 25th here."""
    submitted = datetime(2026, 8, 26, 0, 30)  # naive UTC, as stored
    assert hub_time.fmt(submitted, '%b %d, %Y at %-I:%M %p') == 'Aug 25, 2026 at 8:30 PM'


def test_the_bug_winter():
    """EST, not EDT — five hours, not four."""
    submitted = datetime(2026, 1, 15, 2, 15)
    assert hub_time.fmt(submitted, '%b %d, %Y at %-I:%M %p') == 'Jan 14, 2026 at 9:15 PM'


def test_the_date_only_case_is_the_subtle_one():
    """No clock shown, so nothing looks wrong — the row is just filed under
    the wrong day. Everything logged after 8pm Eastern did this."""
    assert hub_time.date_label(datetime(2026, 8, 26, 1, 0)) == 'Aug 25, 2026'
    assert hub_time.date_label(datetime(2026, 8, 26, 5, 0)) == 'Aug 26, 2026'


def test_dst_boundaries():
    """Second Sunday in March, first Sunday in November. Getting this from
    ZoneInfo rather than a hardcoded offset is the whole point — a fixed -4
    was a real bug in weekly_recap.eastern_now on 2026-08-21."""
    # 2026-03-08 06:59 UTC is still EST (1:59am), 07:00 UTC is EDT (3:00am)
    assert hub_time.fmt(datetime(2026, 3, 8, 6, 59), '%-I:%M %p') == '1:59 AM'
    assert hub_time.fmt(datetime(2026, 3, 8, 7, 0), '%-I:%M %p') == '3:00 AM'
    # 2026-11-01 05:59 UTC is EDT (1:59am), 06:00 UTC is EST (1:00am again)
    assert hub_time.fmt(datetime(2026, 11, 1, 5, 59), '%-I:%M %p') == '1:59 AM'
    assert hub_time.fmt(datetime(2026, 11, 1, 6, 0), '%-I:%M %p') == '1:00 AM'


def test_an_aware_datetime_is_converted_not_assumed():
    aware = datetime(2026, 8, 26, 0, 30, tzinfo=UTC)
    assert hub_time.fmt(aware, '%-I:%M %p') == '8:30 PM'
    already_et = datetime(2026, 8, 25, 20, 30, tzinfo=ZoneInfo('America/New_York'))
    assert hub_time.fmt(already_et, '%-I:%M %p') == '8:30 PM', 'not shifted twice'


def test_none_renders_as_nothing():
    """The `{% if x %}` guards around the old .strftime calls existed because
    .strftime on None raises. The filters make them optional, so they must
    genuinely be safe."""
    assert hub_time.fmt(None) == ''
    assert hub_time.date_label(None) == ''
    assert hub_time.datetime_label(None) == ''
    assert hub_time.to_eastern(None) is None


def test_junk_renders_as_nothing_rather_than_exploding():
    """A template is the worst place to raise: half a page and a 500."""
    assert hub_time.fmt('not a datetime') == ''
    assert hub_time.fmt(12345) == ''
    assert hub_time.fmt({}) == ''


def test_a_plain_date_is_not_shifted():
    """A date has no time to convert, and moving it would change the day —
    midnight in one zone is the previous evening in another."""
    d = date(2026, 8, 26)
    assert hub_time.to_eastern(d) is d
    assert hub_time.date_label(d) == 'Aug 26, 2026'


def test_filters_are_registered_under_the_expected_names():
    from flask import Flask

    app = Flask(__name__)
    hub_time.register(app)
    for name in ('et', 'et_at', 'et_long', 'et_fmt'):
        assert name in app.jinja_env.filters, name
    render = app.jinja_env.from_string(
        "{{ d | et }}|{{ d | et_long }}|{{ d | et_fmt('%-I:%M %p') }}|{{ none | et }}"
    ).render(d=datetime(2026, 8, 26, 0, 30), none=None)
    assert render == 'Aug 25, 2026|August 25, 2026|8:30 PM|'


def test_system_state_still_labels_with_ET():
    """The jobs table was the one place that already did this correctly; it
    now delegates here but must keep its explicit ET suffix."""
    import system_state

    assert system_state._eastern_label(datetime(2026, 8, 26, 0, 30)) == 'Aug 25, 8:30PM ET'
    assert system_state._eastern_label(None) is None


# ── the guard that matters longest ──────────────────────────────────────────

def test_no_template_formats_a_timestamp_by_hand():
    """`.strftime` in a template means a naive UTC value rendered as-is.

    That is the bug, and it came back for a year because nothing stopped it.
    Use `| et`, `| et_at`, `| et_long` or `| et_fmt('...')` instead — they
    convert, and they cope with None so the surrounding `{% if %}` is
    optional.
    """
    offenders = []
    tpl_dir = os.path.join(ROOT, 'templates')
    for name in sorted(os.listdir(tpl_dir)):
        if not name.endswith('.html'):
            continue
        body = open(os.path.join(tpl_dir, name), encoding='utf-8').read()
        for m in re.finditer(r'\.strftime\(', body):
            line = body[:m.start()].count('\n') + 1
            offenders.append(f'{name}:{line}')
    assert not offenders, (
        'templates formatting a timestamp by hand (use | et / | et_at / '
        '| et_fmt): ' + ', '.join(offenders))
