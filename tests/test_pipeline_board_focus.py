"""Tabbing between Pipeline cells, and why the caret kept falling out.

Run: python -m pytest tests/test_pipeline_board_focus.py -v

Rachel, 2026-08-31: "This feels nitpicky but when I'm working in the pipeline
and I try to tab over to the next section, I still have to click in the box to
start typing. Said differently, the cursor isn't automatic when you use tab to
navigate to the next input field."

Not nitpicky, and not a tab-order problem — the Tab key worked correctly. What
happened is a race with the save:

  1. Tabbing out of a cell fires `onblur` → `saveField`, which POSTs.
  2. The browser moves focus to the next cell. The caret is there, correctly.
  3. A few hundred milliseconds later the POST returns and
     `patchEntryInPlace` calls `old.replaceWith(fresh)` — replacing the whole
     row, *including the element she is sitting in*. Focus falls back to
     `<body>`.
  4. She clicks the box, because there is nothing else to do.

It presents as flaky rather than broken because it is a race: type slowly, or
on a fast connection, and the patch lands before you reach for the keyboard.
That is why it arrived as an apology rather than a bug report — and it is a
good argument for taking "this feels nitpicky" reports seriously, because the
ones that are hard to describe are often the ones with a race behind them.

── Measured in Chromium, seeded two-row board, 250ms save latency ──────────

                                          before          after
  focus right after Tab                   next cell       next cell
  focus once the save lands               **<body>**      next cell
  caret position in a textarea            **reset to 0**  preserved
  focus after tabbing off a number field  **<body>**      next cell
  a value typed during the round trip     preserved       preserved
  server-derived client_contact           lands           lands

**No data was being lost** — the typed value survived either way, because the
replacement itself triggers a blur that saves it. This was only ever the
cursor. Worth stating plainly so nobody reads the fix as more urgent than it
was, or goes looking for corrupted rows.

── Why the fix is not the one already in the file ──────────────────────────

The 3-second poll has guarded against exactly this hazard for some time:
"Never stomp a row while the local user has a field in it focused". Nobody
gave the save path the same protection.

But the poll's answer — skip the patch — is wrong here. The save response is
how the server's derived values arrive: blurring `property_name` fills
`client_contact` from the Hub, and that only reaches the page through this
patch. Skipping it would trade a lost caret for a lost auto-fill.

So the caret is carried across the replacement rather than the replacement
being avoided. The one judgement call inside that is whose value wins for the
focused field, and `defaultValue` answers it with no bookkeeping: it holds
what `renderRow` wrote into the markup, so `value !== defaultValue` means "she
has typed here since this row was drawn". Her keystrokes win if she has; the
server's value wins if she has not — which is what lets an auto-filled
`client_contact` still appear in a field she has merely tabbed into.

These are template assertions, in the same spirit as
`test_pipeline_board_scroll.py`: they pin the *shape* of the fix so the
specific regression is caught. The behaviour was verified in a real browser,
in both directions, and the numbers above are from that run.
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


# ── the patch has to notice, and put it back ────────────────────────────────

def test_the_row_patch_captures_focus_before_replacing_the_row(html):
    body = html.split('function patchEntryInPlace', 1)[1].split('\nfunction ', 1)[0]
    capture = body.index('captureCellFocus(old)')
    replace = body.index('old.replaceWith(fresh)')
    assert capture < replace, (
        'focus is captured after the element holding it has already gone')


def test_it_is_restored_after_the_handlers_are_back_on(html):
    """Order matters the other way round too: restoring focus before
    `wireCellEvents` would fire `onfocus` on an element with no handler, so
    the presence ping and the client-contact suggestions would not run."""
    body = html.split('function patchEntryInPlace', 1)[1].split('\nfunction ', 1)[0]
    assert body.index('wireCellEvents(fresh)') < body.index('restoreCellFocus(fresh, held)')


def test_a_patch_to_another_row_leaves_the_caret_alone(html):
    """`captureCellFocus` returns null unless the focus is inside the row
    being replaced — otherwise every patch anywhere on the board would drag
    the cursor to it."""
    fn = html.split('function captureCellFocus', 1)[1].split('\nfunction ', 1)[0]
    assert 'rowEl.contains(el)' in fn
    assert 'return null' in fn


# ── whose value wins ────────────────────────────────────────────────────────

def test_typing_beats_the_server_for_the_field_she_is_in(html):
    fn = html.split('function captureCellFocus', 1)[1].split('\nfunction ', 1)[0]
    assert 'el.value !== el.defaultValue' in fn, (
        'the dirty check is gone — either her keystrokes get overwritten by '
        'the server, or the auto-filled client_contact never appears')


def test_a_field_she_only_tabbed_into_still_takes_the_servers_value(html):
    """The other half of the same rule, and the reason it is not simply
    "always keep what is on screen": blurring property_name fills
    client_contact from the Hub, and she is usually sitting in a field of that
    row when the answer comes back."""
    fn = html.split('function restoreCellFocus', 1)[1].split('\nfunction ', 1)[0]
    assert 'if (held.dirty) el.value = held.value;' in fn, (
        'the restore is unconditional — a server-derived value would be '
        'clobbered by whatever was on screen before it arrived')


def test_a_select_is_never_treated_as_dirty(html):
    """`defaultValue` means nothing on a <select>; status would look dirty
    forever and pin itself to whatever was showing."""
    fn = html.split('function captureCellFocus', 1)[1].split('\nfunction ', 1)[0]
    assert "el.tagName !== 'SELECT'" in fn


# ── the two browser quirks this has to survive ──────────────────────────────

def test_reading_the_caret_is_guarded(html):
    """Chrome throws InvalidStateError reading `selectionStart` on
    `<input type="number">`, which is exactly what Amount and Sub Pay are —
    the two fields most likely to be tabbed through in a row of money."""
    fn = html.split('function captureCellFocus', 1)[1].split('\nfunction ', 1)[0]
    assert re.search(r'try \{[^}]*selectionStart[^}]*\} catch', fn, re.S), (
        'an unguarded selectionStart read will throw on Amount and Sub Pay '
        'and abandon the patch half-done')


def test_setting_the_caret_back_is_guarded_too(html):
    fn = html.split('function restoreCellFocus', 1)[1].split('\nfunction ', 1)[0]
    assert re.search(r'try \{[^}]*setSelectionRange[^}]*\} catch', fn, re.S)


def test_restoring_focus_does_not_move_the_board(html):
    """The board scrolls sideways. Focusing an element scrolls it into view by
    default, so a save landing while she has scrolled away would yank the
    viewport back — reintroducing the jumpiness beebb0e removed."""
    fn = html.split('function restoreCellFocus', 1)[1].split('\nfunction ', 1)[0]
    assert 'focus({preventScroll: true})' in fn


def test_a_grown_textarea_is_re_measured_after_its_value_is_put_back(html):
    """Project and Notes auto-size. Restoring a taller value without
    re-measuring leaves the box one line high with text hidden in it."""
    fn = html.split('function restoreCellFocus', 1)[1].split('\nfunction ', 1)[0]
    assert "el.tagName === 'TEXTAREA'" in fn and 'autoGrow(el)' in fn


# ── what must not have been undone ──────────────────────────────────────────

def test_the_poll_still_refuses_to_stomp_a_focused_row(html):
    """Different path, different answer, both still needed. The poll has
    nothing to show that the local page does not already have, so skipping is
    right there; the save response does, so it patches and carries the caret."""
    assert 'if (rowEl && rowEl.contains(document.activeElement)) return;' in html


def test_only_the_one_row_is_still_re_rendered(html):
    """The focus work sits inside `patchEntryInPlace`, which is also where the
    120ms → 2.5ms fix lives. Widening it back to the whole board would undo
    both at once."""
    assert 'wireCellEvents(fresh)' in html
