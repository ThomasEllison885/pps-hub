"""Enter moves to the next cell on the Pipeline Board.

Run: python -m pytest tests/test_pipeline_board_enter.py -v

Thomas, 2026-08-31, straight after the tab fix: "Can you make it to where you
hit enter and it goes to the next cell too?"

Enter did nothing at all before. There is no `<form>` on this page, so it was
a keystroke that looks like it should commit a cell and silently didn't —
which is worse than it sounds on a board people fill in from a phone, where
the on-screen keyboard's big blue key is Return, not Tab.

**Enter is Tab. Shift+Enter is Shift+Tab.** Moving focus fires the existing
`onblur`, so the cell saves on the way out exactly as it always has. This adds
a way to move, not a second way to save — worth stating because "make Enter
save the row" would have been a plausible reading of the same request, and it
would have produced a board with two save paths to keep in agreement.

── Measured in Chromium, seeded two-row board ──────────────────────────────

  Enter from proposal_number         → property_name
  Shift+Enter                        → back to proposal_number
  type, then Enter                   → saved, and focus lands on the next cell
  Enter in Notes                     → newline, focus unmoved
  Ctrl/Cmd+Enter in Notes            → next cell
  Enter from the last cell of a row  → first cell of the next row (✕ skipped)
  arriving in a cell                 → its text is selected, as with Tab
  with a search running              → filtered-out rows are not entered

That third line only holds because of `3086552`: moving focus fires the save,
the save patches the row, and the patch used to throw focus back to `<body>`.
Enter-to-move built on the old code would have been a feature that looked
broken on every use.

── The carve-out ───────────────────────────────────────────────────────────

**Textareas keep their newline.** Project and Notes are deliberately
multi-line and auto-grow, and taking Enter away from them to save a keystroke
in the single-line fields would be a straight downgrade for the two boxes
people write most in. Ctrl+Enter / Cmd+Enter moves on from those, which is the
convention anywhere a multi-line box sits inside a form.

Two things this deliberately does not do, both of which look like omissions:

  * **It does not go down a column, spreadsheet-style.** The ask was to make
    Enter behave like Tab, and a board row reads left to right.
  * **It does not stop at the end of a row.** Walking a flat list of cells in
    DOM order means the last cell of one row leads into the first of the next,
    which is what filling in a board actually looks like.

Template assertions, same as `test_pipeline_board_scroll.py` and
`test_pipeline_board_focus.py`: they pin the shape, and the behaviour above
was verified in a real browser.
"""
import os
import re
import sys

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pipeline_board  # noqa: E402


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


@pytest.fixture(scope='module')
def handler(html):
    # Explicit rather than letting the split throw an IndexError: a fixture
    # that errors reads as a broken test, and a broken test gets deleted
    # instead of investigated.
    assert 'function cellKeydown' in html, (
        'cellKeydown is gone from the board — Enter no longer moves anywhere')
    return html.split('function cellKeydown', 1)[1].split('\nfunction ', 1)[0]


# ── it moves, in both directions ────────────────────────────────────────────

def test_enter_is_wired_on_every_cell(html):
    assert 'cellKeydown(ev, el)' in html
    body = html.split('function wireCellEvents', 1)[1].split('\nfunction ', 1)[0]
    assert 'el.onkeydown = (ev) =>' in body, 'the handler is not attached to cells'


def test_shift_enter_goes_backwards(handler):
    assert 'ev.shiftKey' in handler
    assert re.search(r'here \+ \(ev\.shiftKey[^)]*\? -1 : 1\)', handler), (
        'Enter and Shift+Enter no longer move opposite ways')


def test_it_only_acts_on_enter(handler):
    assert re.search(r"if \(ev\.key !== 'Enter'\) return;", handler), (
        'this handler is now intercepting other keys')


# ── the carve-out for multi-line fields ─────────────────────────────────────

def test_a_plain_enter_in_a_textarea_still_makes_a_newline(handler):
    """Project and Notes auto-grow and are meant to hold more than one line.
    Losing Enter there would cost more than it saves."""
    assert re.search(r'isTextarea && !withModifier\) return;', handler), (
        'Enter in Notes no longer inserts a newline')


def test_a_modifier_gets_you_out_of_a_textarea(handler):
    assert 'ev.ctrlKey || ev.metaKey' in handler, (
        'no way to leave Notes from the keyboard except Tab')


def test_shift_enter_in_a_textarea_is_still_a_newline(handler):
    """Shift+Enter means "newline" in every chat box on earth, and in a
    textarea it already did. It must not become "go backwards" here."""
    assert 'ev.shiftKey && !isTextarea' in handler


# ── what it must not fight with ─────────────────────────────────────────────

def test_the_client_contact_suggestions_still_own_enter(html):
    """`handleSuggestKey` takes Enter when a suggestion is highlighted and
    calls preventDefault. Without the defaultPrevented check, one Enter would
    both pick a suggestion and jump a cell."""
    body = html.split('function wireCellEvents', 1)[1].split('\nfunction ', 1)[0]
    order_suggest = body.index('handleSuggestKey(ev, el)')
    order_cell = body.index('cellKeydown(ev, el)')
    assert order_suggest < order_cell, 'the cell jump runs before the suggestion list'
    assert 'if (!ev.defaultPrevented) cellKeydown(ev, el);' in body


def test_an_ime_candidate_is_not_a_cell_jump(handler):
    """Enter during composition commits the candidate. Chrome reports it as
    keyCode 229; `isComposing` covers the rest."""
    assert 'ev.isComposing' in handler and 'ev.keyCode === 229' in handler


# ── which cells are reachable ───────────────────────────────────────────────

def test_hidden_rows_are_skipped(html):
    """`.row-filtered` is `display: none` during a search. Focusing a cell in
    one does nothing at all, so Enter would look broken while searching."""
    fn = html.split('function boardCells', 1)[1].split('\nfunction ', 1)[0]
    assert 'offsetParent !== null' in fn


def test_the_remove_button_is_not_in_the_path(html):
    """The ✕ carries no `data-field`, so selecting on that attribute steps
    over it — which is the difference between Enter and Tab here, and the
    reason Enter is the nicer key for filling a board in."""
    fn = html.split('function boardCells', 1)[1].split('\nfunction ', 1)[0]
    assert "querySelectorAll('[data-field]')" in fn
    assert 'data-archive' not in fn


def test_it_walks_the_board_in_document_order(html):
    """A flat list, so the end of one row runs into the start of the next."""
    fn = html.split('function boardCells', 1)[1].split('\nfunction ', 1)[0]
    assert "getElementById('board-body')" in fn
    assert 'Array.from(' in fn


# ── arriving feels the same as arriving by Tab ──────────────────────────────

def test_the_text_is_selected_on_arrival(handler):
    """Tab into a text field selects its contents. If Enter does not, the two
    keys land you in the same box feeling different."""
    assert 'next.select()' in handler
    assert re.search(r'try \{[^}]*select\(\)[^}]*\} catch', handler, re.S), (
        'select() is unguarded — it throws on some input types')


def test_running_off_the_end_of_the_board_does_nothing(handler):
    assert 'if (!next) return;' in handler


# ── it adds a way to move, not a second way to save ─────────────────────────

def test_enter_does_not_save_by_itself(handler):
    """Moving focus fires the existing onblur, which saves. A save call here
    as well would mean two POSTs per cell and two code paths to keep in
    agreement about what a save is."""
    assert 'saveField' not in handler, (
        'Enter is now saving directly as well as through blur')
