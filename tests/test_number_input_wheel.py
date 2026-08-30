"""A scroll must never edit a number — everywhere, not just the Pipeline.

Run: python -m pytest tests/test_number_input_wheel.py -v

Thomas found this on the Pipeline Board (2026-08-29): "when I click on the sub
pay or amount and I try to scroll up or down it causes the numbers to go up or
down." Chrome and Safari treat a wheel over a focused `<input type="number">`
as increment/decrement.

The Pipeline was the least of it. Counting the number inputs in the Hub:

    admin_pricing_defaults.html   24
    siding_estimator.html         10
    gutter_estimator.html          9
    roofing_estimator.html         7
    painting_estimator.html        5
    pipeline_board.html            2
    site_visit.html                1

and the `step` values on those pages are not small — Labor $/sq steps by 5,
Markup and Overhead by 100. One notch of an accidental scroll is $100 on a
bid, or $5/square on what every future siding estimate starts from, with
nothing on screen to say it happened. Pricing defaults is the worst of the
three: it is company-wide and forward-looking.

So the guard lives in `_pwa_head.html`, which every form page in the Hub
includes. The Pipeline Board keeps its own copy — it does not include that
partial, and it forwards the scroll to its table rather than to the page.

`test_no_page_ships_a_number_input_without_the_guard` is the one that matters
long-term: it is a property of the whole templates directory, so a new page
with a money field cannot quietly arrive without cover.
"""
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TEMPLATES = os.path.join(ROOT, 'templates')
SHARED_HEAD = '_pwa_head.html'
INCLUDE = "{% include '_pwa_head.html' %}"


def _read(name):
    with open(os.path.join(TEMPLATES, name), encoding='utf-8') as fh:
        return fh.read()


def _templates():
    return sorted(n for n in os.listdir(TEMPLATES) if n.endswith('.html'))


def _number_input_count(body):
    return len(re.findall(r'type="number"', body))


def _has_own_guard(body):
    """A page carrying its own wheel handler for number inputs."""
    return bool(re.search(r"type !== 'number'", body))


# ── the shared guard ────────────────────────────────────────────────────────

def test_the_shared_head_carries_the_guard():
    head = _read(SHARED_HEAD)
    assert "el.type !== 'number'" in head
    assert 'ev.preventDefault()' in head, (
        'without preventDefault the browser still spins the value')


def test_the_shared_guard_is_not_passive():
    """A passive wheel listener cannot preventDefault. The guard would be
    installed, run, and do nothing — the failure mode that looks fixed."""
    head = _read(SHARED_HEAD)
    assert 'passive: false' in head


def test_the_gesture_still_scrolls_something():
    """Prevent the default and stop there and every money field becomes a
    dead patch where the wheel does nothing at all."""
    head = _read(SHARED_HEAD)
    assert 'scrollableAncestor' in head
    assert 'window.scrollBy(0, amount)' in head, (
        'nothing scrolls when the field is not inside its own scroller')


def test_line_and_page_wheel_modes_are_handled():
    head = _read(SHARED_HEAD)
    assert 'ev.deltaMode === 1' in head and 'ev.deltaMode === 2' in head


def test_disabled_and_readonly_fields_are_skipped():
    """They cannot spin, so intercepting them only breaks scrolling."""
    head = _read(SHARED_HEAD)
    assert 'el.disabled || el.readOnly' in head


def test_the_guard_cannot_take_the_page_down_with_it():
    """This partial runs on every page in the Hub, and the file's own comment
    says an uncaught throw here kills whatever inline script follows."""
    head = _read(SHARED_HEAD)
    block = head.split('scrollableAncestor', 1)[1]
    assert 'try {' in block and 'catch (e)' in block


def test_it_only_touches_number_inputs():
    head = _read(SHARED_HEAD)
    assert "el.tagName !== 'INPUT'" in head, (
        'intercepting the wheel over every element would break the Hub')


# ── the property that keeps holding ─────────────────────────────────────────

def test_no_page_ships_a_number_input_without_the_guard():
    """Every template with a number field either includes the shared head or
    carries its own handler. A new page with a money field cannot arrive
    without cover."""
    unguarded = []
    for name in _templates():
        if name == SHARED_HEAD:
            continue
        body = _read(name)
        if not _number_input_count(body):
            continue
        if INCLUDE in body or _has_own_guard(body):
            continue
        unguarded.append(f'{name} ({_number_input_count(body)} number inputs)')
    assert not unguarded, (
        'a scroll can edit numbers on: ' + ', '.join(unguarded))


def test_the_pages_we_know_about_are_still_covered():
    """Named, so that deleting the include from one of them fails here with
    the page's name rather than as a generic count."""
    for name in ('admin_pricing_defaults.html', 'siding_estimator.html',
                 'roofing_estimator.html', 'gutter_estimator.html',
                 'painting_estimator.html', 'site_visit.html'):
        body = _read(name)
        assert _number_input_count(body), f'{name} lost its number inputs?'
        assert INCLUDE in body, f'{name} no longer includes the shared head'


def test_the_pipeline_board_has_its_own_because_it_has_its_own_scroller():
    body = _read('pipeline_board.html')
    assert INCLUDE not in body, (
        'if the Pipeline now includes the shared head, drop its private copy '
        'rather than running two wheel handlers')
    assert _has_own_guard(body)
    assert 'scroller.scrollTop += ev.deltaY' in body


# ── the money at stake, so the next reader knows why this exists ────────────

def test_the_step_values_are_still_large_enough_to_care_about():
    """If these ever became step="0.01" the guard would matter less. They are
    not: one notch is $5 a square, or $100 of markup."""
    pricing = _read('admin_pricing_defaults.html')
    assert re.search(r'name="siding_labor_per_sq"[^>]*step="5"', pricing)
    siding = _read('siding_estimator.html')
    assert re.search(r'id="markupAmt"[^>]*step="100"', siding)
