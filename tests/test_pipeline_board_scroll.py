"""The Pipeline Board's scrolling, and what was making it feel broken.

Run: python -m pytest tests/test_pipeline_board_scroll.py -v

Thomas, 2026-08-29: "The scroll on the Pipeline is weird. Glitchy. Also when I
click on the sub pay or amount and I try to scroll up or down it causes the
numbers to go up or down."

Three separate causes, all measured in Chromium against a seeded 60-row board
before and after:

1. **A 120ms stall on every poll.** `patchEntryInPlace` re-rendered one row
   and then called `wireCellEvents()`, which re-wired *every* cell on the
   board and re-measured *every* textarea. The 3-second poll calls that for
   each changed row, so any edit by anyone froze the main thread for an eighth
   of a second — landing mid-scroll, which is what "glitchy" was.
   Measured median: **120.1ms → 2.5ms**.

2. **Two nested scrollers.** The table's height was `100dvh - 220px`, a guess
   that was too small once the board switcher and the install hint were both
   on the page, leaving 93px of the *page* scrolling underneath the table's
   own scrolling. A wheel gesture moved the table, then handed over to the
   page part-way through. Measured page overflow: **93px → 0px**.

3. **The wheel edited the money.** A focused `<input type="number">` in
   Chrome and Safari treats a wheel as increment/decrement, so scrolling with
   the cursor over Amount or Sub Pay silently changed the number instead of
   moving the board.

These are template assertions, so they pin the *shape* of each fix rather than
its behaviour — the behaviour was verified in a real browser. What they are
good for is catching the specific regressions: re-widening the wiring scope,
going back to a hardcoded height, or dropping the wheel guard.
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


# ── 1. one row patched should touch one row ─────────────────────────────────

def test_patching_one_row_rewires_only_that_row(html):
    """The whole of cause (1). `wireCellEvents()` with no argument walks the
    entire board; the poll must not do that per changed row."""
    assert 'wireCellEvents(fresh)' in html, (
        'patchEntryInPlace is re-wiring the whole board again — that is the '
        '120ms stall')


def test_wire_cell_events_takes_a_scope(html):
    assert re.search(r'function wireCellEvents\(root\)', html)
    assert "const scope = root || document.getElementById('board-body')" in html
    assert 'scope.querySelectorAll(' in html
    assert "document.querySelectorAll('#board-body input" not in html, (
        'still reaching across the whole board regardless of the scope')


def test_textarea_sizing_is_one_layout_not_one_per_textarea(html):
    """Writing a height and then reading scrollHeight forces a layout. In a
    loop over 120 textareas that was 100ms; batched it is 8ms."""
    body = html.split('function autoGrowAll', 1)[1].split('function autoGrow(', 1)[0]
    write_all = body.index("list.forEach(el => { el.style.height = '0px'; })")
    read_all = body.index('list.map(el => el.scrollHeight)')
    write_back = body.index("heights[i] + 'px'")
    assert write_all < read_all < write_back, (
        'the writes and reads are interleaved again — that is the layout '
        'thrash this replaced')


def test_the_single_textarea_helper_still_exists(html):
    """`oninput` needs a one-element version; it just goes through the batch."""
    assert 'function autoGrow(el) { autoGrowAll([el]); }' in html
    assert 'el.oninput = () => autoGrow(el);' in html


# ── 2. one scroller, not two ────────────────────────────────────────────────

def test_the_table_height_is_measured_not_guessed(html):
    assert 'function sizeScroller()' in html
    assert 'window.innerHeight - top - below' in html, (
        'the height is back to a fixed guess')
    assert "window.addEventListener('resize', sizeScrollerSoon)" in html


def test_the_measurement_checks_its_own_answer(html):
    """Borders and sub-pixel rounding left 11px of page still scrolling, which
    is enough to feel like the board slips at the end of a gesture."""
    block = html.split('function sizeScroller()', 1)[1].split('\n}', 1)[0]
    assert 'documentElement.scrollHeight' in block
    assert 'documentElement.clientHeight' in block


def test_resizing_is_debounced(html):
    """On a phone, hiding the URL bar fires resize continuously; resizing the
    scroller on every one of those is its own jitter."""
    assert 'function sizeScrollerSoon()' in html
    assert 'clearTimeout(sizeTimer)' in html


def test_the_scroller_is_remeasured_once_the_rows_are_in(html):
    """The first sizing runs before any row exists, and fonts land later
    still."""
    assert "window.addEventListener('load', sizeScrollerSoon)" in html
    render_all = html.split('function renderAll()', 1)[1].split('\nfunction ', 1)[0]
    assert 'sizeScrollerSoon()' in render_all


def test_a_wheel_gesture_does_not_escape_to_the_page(html):
    assert 'overscroll-behavior: contain' in html


def test_dismissing_the_install_hint_gives_the_height_back(html):
    # The second occurrence is the click handler; the first is the button.
    handler = html.split("getElementById('install-hint-dismiss').onclick", 1)[1][:400]
    assert 'sizeScroller()' in handler


# ── 3. the wheel must not edit the money ────────────────────────────────────

def test_the_wheel_over_a_number_input_is_intercepted(html):
    block = html.split('stopWheelEditingNumbers', 1)[1]
    assert "el.type !== 'number'" in block, 'the guard no longer targets numbers'
    assert 'ev.preventDefault()' in block, (
        'without preventDefault Chrome still increments the value')


def test_it_is_not_a_passive_listener(html):
    """A passive wheel listener cannot preventDefault, so the guard would be
    installed and do nothing — the failure mode that looks fixed."""
    block = html.split('stopWheelEditingNumbers', 1)[1]
    assert '{ passive: false }' in block


def test_the_gesture_still_scrolls_the_board(html):
    """Prevent the default and stop there and every number cell becomes a
    dead patch where the wheel does nothing at all."""
    block = html.split('stopWheelEditingNumbers', 1)[1]
    assert 'scroller.scrollTop += ev.deltaY' in block


def test_line_and_page_wheel_modes_are_handled(html):
    """deltaMode 0 is pixels, 1 is lines, 2 is pages. Treating lines as pixels
    makes a mouse wheel scroll the board by three pixels."""
    block = html.split('stopWheelEditingNumbers', 1)[1]
    assert 'ev.deltaMode === 1' in block and 'ev.deltaMode === 2' in block


def test_text_inputs_are_left_alone(html):
    """Only number inputs have the spin behaviour; intercepting the rest would
    break normal scrolling over most of the board."""
    block = html.split('stopWheelEditingNumbers', 1)[1].split('})();', 1)[0]
    assert "el.tagName !== 'INPUT'" in block
    assert 'return;' in block


def test_only_the_two_money_columns_are_number_inputs(html):
    """If a future column becomes type=number the guard covers it too — this
    is here so that stays a deliberate choice rather than a surprise."""
    numeric = re.findall(r'data-field="(\w+)"[^>]*type="number"', html)
    assert set(numeric) == {'amount', 'sub_pay'}, numeric


# ── keeping your place ──────────────────────────────────────────────────────

def test_a_full_rerender_keeps_your_scroll_position(html):
    """`renderAll` rebuilds the whole tbody, and it runs when someone *else*
    archives a row. Being thrown to the top of the board is not something you
    did."""
    render_all = html.split('function renderAll()', 1)[1].split('\nfunction ', 1)[0]
    assert 'const keepScroll = scroller ? scroller.scrollTop : 0' in render_all
    assert 'scroller.scrollTop = Math.min(keepScroll, scroller.scrollHeight)' in render_all
