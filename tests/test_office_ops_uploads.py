"""What is in the drop box.

Run: python -m pytest tests/test_office_ops_uploads.py -v

Thomas, 2026-08-27: "When a file is uploaded there needs to be a place holder
or something that shows the file was uploaded in that box. It just disappears
and if I don't remember I put a file in there there is no way of knowing."

The upload worked, the page reloaded, and the box came back looking exactly
as it had before. The only record was one mixed list of twelve files at the
bottom of the page, which answers "what has been uploaded lately" rather than
"is this box done".

The property worth pinning is not "the filename appears" — it is that a file
from *before this week* is not allowed to read as done. This is a weekly
workflow; a March invoice list sitting in the box is worse than an empty box,
because an empty box does not claim to be finished.
"""
import os
import sys
from datetime import datetime, timedelta

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import hub_time
import office_ops

# A Wednesday. The week it belongs to starts Monday 2026-08-24 00:00 ET.
NOW = datetime(2026, 8, 26, 14, 0, tzinfo=hub_time.ET)
THIS_WEEK = datetime(2026, 8, 25, 18, 14)      # Tue 2:14pm ET, naive UTC
LAST_WEEK = datetime(2026, 8, 20, 18, 14)      # the Thursday before


def _row(**over):
    row = {'id': 7, 'kind': 'invoice_list', 'filename': 'Rep Sales YTD.xlsx',
           'size_bytes': 41231, 'uploaded_by': 'stephanie_whetstone',
           'uploaded_at': THIS_WEEK}
    row.update(over)
    return row


# ── the week boundary ───────────────────────────────────────────────────────

def test_the_week_starts_at_eastern_midnight_on_monday():
    start = office_ops.week_start_eastern(NOW)
    assert start == datetime(2026, 8, 24, 4, 0), 'midnight EDT is 04:00 UTC'
    assert office_ops.week_start_eastern(
        datetime(2026, 8, 24, 0, 30, tzinfo=hub_time.ET)) == start, \
        'a Monday belongs to its own week'


def test_the_boundary_holds_across_a_dst_change():
    """Subtracting days from a UTC timestamp lands an hour off twice a year.
    November 2026: EST is UTC-5, so Monday midnight is 05:00 UTC."""
    november = datetime(2026, 11, 12, 9, 0, tzinfo=hub_time.ET)
    assert office_ops.week_start_eastern(november) == datetime(2026, 11, 9, 5, 0)


def test_a_file_uploaded_this_week_is_not_stale():
    assert office_ops.describe_upload(_row(), now=NOW)['stale'] is False


def test_last_weeks_file_is_stale():
    """The whole point. It is still in the box, it still has a name, and it
    is not this week's."""
    d = office_ops.describe_upload(_row(uploaded_at=LAST_WEEK), now=NOW)
    assert d['stale'] is True
    assert d['filename'] == 'Rep Sales YTD.xlsx'


def test_a_file_from_monday_morning_counts_as_this_week():
    monday = datetime(2026, 8, 24, 13, 0)   # 9am ET Monday, naive UTC
    assert office_ops.describe_upload(_row(uploaded_at=monday),
                                      now=NOW)['stale'] is False


def test_sunday_night_belongs_to_the_week_that_just_ended():
    sunday = datetime(2026, 8, 24, 1, 0)    # 9pm ET Sunday, naive UTC
    assert office_ops.describe_upload(_row(uploaded_at=sunday),
                                      now=NOW)['stale'] is True


# ── what the box says ───────────────────────────────────────────────────────

def test_nothing_uploaded_stays_nothing():
    assert office_ops.describe_upload(None, now=NOW) is None


def test_the_time_is_eastern_not_utc():
    """18:14 UTC is 2:14pm in Ohio, not 6:14pm."""
    d = office_ops.describe_upload(_row(), now=NOW)
    assert d['when'] == 'Aug 25 at 2:14 PM'


def test_the_uploader_is_named_when_we_know_them():
    d = office_ops.describe_upload(
        _row(), now=NOW, display_names={'stephanie_whetstone': 'Stephanie Whetstone'})
    assert d['by'] == 'Stephanie Whetstone'
    plain = office_ops.describe_upload(_row(), now=NOW)
    assert plain['by'] == 'stephanie_whetstone', 'an unknown key beats a blank'


# ── the page ────────────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def env():
    e = Environment(loader=FileSystemLoader(os.path.join(ROOT, 'templates')),
                    undefined=StrictUndefined)
    e.filters.update(hub_time.FILTERS)
    return e


def _render(env, box_uploads):
    return env.get_template('office_ops.html').render(
        user_key='stephanie_whetstone', user_display='Stephanie Whetstone',
        pack=None, monday=None, recent_files=[], past_due=[], ar_notes={},
        box_uploads=box_uploads,
    )


def test_an_empty_box_says_so(env):
    html = _render(env, {})
    assert 'Nothing uploaded yet' in html
    for kind in ('invoice_list', 'ar_aging_summary', 'profit_loss'):
        assert 'has-file' not in _box_class(html, kind), kind


def test_a_filled_box_shows_the_file(env):
    html = _render(env, {'invoice_list': office_ops.describe_upload(_row(), now=NOW)})
    assert 'Rep Sales YTD.xlsx' in html
    assert 'Aug 25 at 2:14 PM' in html
    assert 'has-file' in html


def _box_class(html, kind):
    """The class actually on the box, not the one in the stylesheet above it."""
    import re
    m = re.search(r'<div class="(drop[^"]*)" data-kind="%s"' % kind, html)
    assert m, f'no {kind} box in the page'
    return m.group(1)


def test_a_stale_box_is_flagged_rather_than_looking_done(env):
    d = office_ops.describe_upload(_row(uploaded_at=LAST_WEEK), now=NOW)
    html = _render(env, {'invoice_list': d})
    assert 'before this week' in html
    assert 'is-stale' in _box_class(html, 'invoice_list'), (
        'the box carries no stale styling — matching the stylesheet is not '
        'the same as matching the box')


def test_a_fresh_box_is_not_flagged(env):
    html = _render(env, {'invoice_list': office_ops.describe_upload(_row(), now=NOW)})
    cls = _box_class(html, 'invoice_list')
    assert 'has-file' in cls and 'is-stale' not in cls


def test_each_of_the_four_boxes_can_show_its_own_file(env):
    kinds = ('invoice_list', 'ar_aging_summary', 'ar_aging_detail', 'profit_loss')
    uploads = {k: office_ops.describe_upload(_row(kind=k, filename=f'{k}.xlsx'),
                                             now=NOW) for k in kinds}
    html = _render(env, uploads)
    for k in kinds:
        assert f'{k}.xlsx' in html, f'{k} box does not show its file'


# ── the timestamps around it ────────────────────────────────────────────────

def test_stored_isoformat_strings_render_eastern_too():
    """office_ops hands templates `created_at.isoformat()`, and the page used
    to slice the string by hand — which renders UTC. `| et_at` now parses it."""
    assert hub_time.datetime_label('2026-08-26T18:14:00') == 'Aug 26, 2026 at 2:14 PM'
    assert hub_time.date_label('2026-08-26T18:14:00') == 'Aug 26, 2026'


def test_a_string_that_is_not_a_timestamp_is_still_harmless():
    assert hub_time.datetime_label('not a date') == ''
    assert hub_time.to_eastern('not a date') == 'not a date'


def test_the_page_no_longer_slices_a_timestamp_by_hand():
    body = open(os.path.join(ROOT, 'templates', 'office_ops.html'),
                encoding='utf-8').read()
    assert "replace('T',' ')" not in body, (
        'a hand-sliced ISO string is the UTC bug in string form')


def test_the_button_offers_to_replace_what_is_already_there(env):
    """"Upload Invoice List" beside a file that is already uploaded reads as
    "this box is not done"."""
    filled = _render(env, {'invoice_list': office_ops.describe_upload(_row(), now=NOW)})
    assert 'Replace Invoice List' in filled
    empty = _render(env, {})
    assert 'Upload Invoice List' in empty
    assert 'Replace Invoice List' not in empty
