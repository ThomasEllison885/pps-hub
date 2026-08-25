"""pipeline_board.html — the search added 2026-08-25.

Run: python -m pytest tests/test_pipeline_board_template.py -v

The filter itself is driven in a real browser (Chromium, both viewports)
rather than here — matching text is not the interesting part. What these pin
is the one design decision the feature hangs on:

**Non-matching rows are HIDDEN, never removed from the DOM.**

Removing them would look tidier and would break two things quietly:

  * `patchEntryInPlace` looks up `row-<id>` and *appends* when it cannot find
    one, so the 3s poll would re-add a filtered row at the bottom of the
    table, out of order;
  * `mergeEntries` refuses to overwrite a row containing
    `document.activeElement` — that is what stops a poll wiping what you are
    typing — and a row that is not in the DOM cannot contain the focus, so
    the guard would silently stop guarding.

Both were verified in the browser: with a search running, a poll that edits
a hidden row leaves the DOM at five rows, the count at "2 of 5", and the
hidden row hidden.
"""
import os
import re
import sys

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pipeline_board


@pytest.fixture(scope='module')
def html():
    env = Environment(loader=FileSystemLoader(os.path.join(ROOT, 'templates')),
                      undefined=StrictUndefined)
    return env.get_template('pipeline_board.html').render(
        pair_key='andy_potts',
        user_key='andy_potts',
        user_display='Andy Potts',
        consultant_display='Andy Potts',
        pm_display='Ben Cole',
        is_admin_preview=False,
        accessible_boards=[{'key': 'andy_potts',
                            'consultant_display': 'Andy Potts',
                            'pm_display': 'Ben Cole'}],
        statuses=pipeline_board.STATUSES,
        completed_statuses=sorted(pipeline_board.COMPLETED_STATUSES),
        can_import=True,
    )


def test_the_search_box_is_there(html):
    assert 'id="board-search-input"' in html
    assert 'id="board-search-clear"' in html
    assert 'Search this board' in html


def test_rows_are_hidden_not_removed(html):
    """`display:none` on a class, applied to a row that stays in the table."""
    assert re.search(r'tr\.row-filtered\s*\{\s*display:\s*none', html)
    assert "classList.toggle('row-filtered'" in html


def test_the_filter_is_reapplied_everywhere_a_row_is_rebuilt(html):
    """renderRow returns a clean <tr>, so anything that rebuilds one has to
    re-apply the filter or an edited row reappears mid-search."""
    for fn in ('function renderAll(', 'function patchEntryInPlace(',
               'function mergeEntries('):
        start = html.index(fn)
        end = html.index('\n}', start)
        assert 'applyFilter()' in html[start:end], f'{fn} does not re-apply the filter'


def test_the_row_count_is_not_written_directly_while_filtering(html):
    """mergeEntries used to set #row-count itself. With a search running the
    count is "N of M", and a poll must not quietly replace it with M."""
    start = html.index('function mergeEntries(')
    end = html.index('\n}', start)
    body = html[start:end]
    assert "getElementById('row-count').textContent" not in body


def test_adding_a_row_clears_the_search(html):
    """A new row is blank, so it matches nothing and would be created
    invisible."""
    start = html.index("document.getElementById('add-row-btn').onclick")
    body = html[start:start + 1200]
    assert "boardQuery = ''" in body


def test_search_covers_every_column_including_the_status_label(html):
    """People search for "walk", meaning the "Needs walk/scope" status — the
    label, which is never in the entry itself."""
    start = html.index('function entryHaystack(')
    end = html.index('\n}', start)
    body = html[start:end]
    assert 'TEXT_FIELDS' in body
    assert 'NUMERIC_FIELDS' in body
    assert 'STATUSES.find' in body


def test_every_editable_field_is_searchable(html):
    """TEXT_FIELDS/NUMERIC_FIELDS drive both the editor and the search, so a
    new column is searchable the day it is added. This pins that they are
    still the same lists the row renderer uses."""
    text = re.search(r'const TEXT_FIELDS = \[(.*?)\];', html, re.S).group(1)
    for field in ('proposal_number', 'property_name', 'address', 'project',
                  'trade_partner', 'client_contact', 'notes'):
        assert f"'{field}'" in text, field
    numeric = re.search(r'const NUMERIC_FIELDS = \[(.*?)\];', html, re.S).group(1)
    assert "'amount'" in numeric and "'sub_pay'" in numeric


def test_terms_are_ANDed_not_ORed(html):
    """"cedar gutter" should mean both words somewhere in the row, not
    either — otherwise a second word widens the results instead of
    narrowing them, which is the opposite of what typing more means."""
    start = html.index('function entryMatches(')
    end = html.index('\n}', start)
    assert 'terms.every(' in html[start:end]


def test_jump_to_open_work_respects_the_filter(html):
    """Jumping to a hidden row scrolls to nothing."""
    start = html.index('function jumpToOpenWork(')
    end = html.index('\n}', start)
    body = html[start:end]
    assert 'entryMatches(' in body


def test_the_native_search_clear_button_is_suppressed(html):
    """type="search" earns the mobile keyboard's Search key, but Chrome and
    Safari then draw their own ✕ on top of ours."""
    assert '-webkit-search-cancel-button' in html
