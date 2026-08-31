"""Where a Field Guide contents link actually lands you.

Run: python -m pytest tests/test_guide_anchors.py -v

Thomas, 2026-08-31: "On the field guide when you press the table of contents
links it goes too far down. Have it show the header too. Not directly to the
text."

`.pps-header` is `position: sticky; top: 0`, so the top of the viewport is
covered by 64px of navy on desktop. `.g-section` had `scroll-margin-top: 16px`,
which parked the section 16px below the viewport top — i.e. **behind** the
header. You arrived mid-paragraph with no title telling you which section you
had opened.

── Measured in Chromium, 21-section guide, clicking contents item #5 ───────

                        before                       after
  desktop / tablet      heading 27px behind header   fully clear
  phone                 heading 15px behind header   fully clear

Both entry paths were wrong and both are fixed by the one rule: clicking a
contents link (browser-native anchor scroll) and opening `/guide#pipeline`
from elsewhere in the Hub (`scrollIntoView()` in the page script, which
honours `scroll-margin` the same way).

── Why `calc(var(--header-h) + 16px)` and not a number ─────────────────────

`--header-h` is 64px, 52px and 48px across the three breakpoints. A hardcoded
80px would leave a phone user staring at a gap the size of a third of their
screen. Tying the offset to the same variable the header's own height comes
from means the two cannot drift apart.

The one hazard that buys is that `calc()` with an **undefined** custom property
is invalid at computed-value time — `scroll-margin-top` would fall back to 0,
which is worse than the 16px this replaced, and it would fail silently. So one
test below checks the stylesheet that defines `--header-h` is actually loaded
by this page.
"""
import os
import re
import sys

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import hub_guide  # noqa: E402
import pipeline_board  # noqa: E402
import weekly_recap  # noqa: E402

CTX = {
    'tier': 'team',
    'role': 'consultant',
    'user_key': 'andy_potts',
    'pipeline_boards': [{'key': 'andy_potts',
                         'consultant_display': 'Andy Potts',
                         'pm_display': 'Ben Cole'}],
}


@pytest.fixture(scope='module')
def html():
    values = hub_guide.facts(
        session_days=30,
        statuses=pipeline_board.STATUSES,
        completed_statuses=pipeline_board.COMPLETED_STATUSES,
        rolling_weeks=weekly_recap.ROLLING_WEEKS,
        activity_cap=weekly_recap.ACTIVITY_CAP_PER_WEEK,
        recap_day='Monday',
        recap_hour='7am Eastern',
    )
    env = Environment(loader=FileSystemLoader(os.path.join(ROOT, 'templates')),
                      undefined=StrictUndefined)
    return env.get_template('guide.html').render(
        sections=hub_guide.sections_for(CTX, values, show_all=True),
        hidden=hub_guide.hidden_count(CTX),
        show_all=True,
    )


@pytest.fixture(scope='module')
def global_css():
    with open(os.path.join(ROOT, 'static', 'pps-global.css')) as fh:
        return fh.read()


# ── the offset clears the header ────────────────────────────────────────────

def test_sections_are_offset_by_the_header_height(html):
    assert re.search(r'\.g-section\s*\{[^}]*scroll-margin-top:\s*calc\(\s*var\(--header-h\)',
                     html), (
        'a contents link lands the section heading under the sticky header')


def test_the_offset_is_not_a_hardcoded_pixel_value(html):
    """The whole reason to use the variable: the header is 64 / 52 / 48px."""
    m = re.search(r'\.g-section\s*\{[^}]*scroll-margin-top:\s*([^;]+);', html)
    assert m, '.g-section lost its scroll-margin-top'
    assert 'var(--header-h)' in m.group(1), f'hardcoded offset: {m.group(1).strip()}'


def test_there_is_breathing_room_below_the_header(html):
    """Flush against the header reads as clipped. The heading should sit
    clear of it, not touch it."""
    m = re.search(r'scroll-margin-top:\s*calc\(\s*var\(--header-h\)\s*\+\s*(\d+)px', html)
    assert m, 'the offset is exactly the header height, with no gap'
    assert 4 <= int(m.group(1)) <= 40, f'{m.group(1)}px of padding is not a gap'


# ── the pieces the calc depends on ──────────────────────────────────────────

def test_the_page_loads_the_stylesheet_that_defines_the_variable(html):
    """`calc()` with an undefined custom property is invalid at computed-value
    time, so scroll-margin-top would silently become 0 — worse than the 16px
    this replaced, and invisible until someone clicks a contents link."""
    assert '/static/pps-global.css' in html


def test_the_variable_is_defined_at_the_root(global_css):
    assert re.search(r':root\s*\{[^}]*--header-h:', global_css), (
        '--header-h moved off :root, so the guide\'s calc() resolves to nothing')


def test_the_header_really_is_sticky(global_css):
    """If it ever stops being sticky the offset becomes dead weight — a gap
    above every section for no reason. Then this rule should go, not grow."""
    header = global_css.split('.pps-header {', 1)[1].split('}', 1)[0]
    assert 'position: sticky' in header
    assert 'top: 0' in header
    assert 'height: var(--header-h)' in header, (
        'the header height is no longer --header-h, so the guide is offsetting '
        'by a number that has nothing to do with what is covering the page')


# ── the anchors themselves ──────────────────────────────────────────────────

def test_every_contents_link_points_at_a_section_that_exists(html):
    """A dead anchor does not scroll at all, which reads as the same bug."""
    targets = set(re.findall(r'<section class="g-section[^"]*" id="([^"]+)"', html))
    links = re.findall(r'<li><a href="#([^"]+)"', html)
    assert links, 'the contents list is empty'
    assert not (set(links) - targets), f'contents links with no section: {set(links) - targets}'


def test_the_anchor_is_on_the_section_not_on_the_body(html):
    """The id has to sit on the element that *contains* the <h2>. Moving it to
    the first paragraph would reintroduce the bug at a different layer, and
    the scroll-margin rule would not save it."""
    assert re.search(r'<section class="g-section[^"]*" id="[^"]+">\s*<h2>', html), (
        'the section id is no longer immediately followed by the heading')


def test_the_deep_link_path_still_scrolls_itself(html):
    """`/guide#pipeline` from elsewhere in the Hub is resolved by the browser
    before the page script runs, so the script re-scrolls on load.
    `scrollIntoView()` honours scroll-margin, so it gets the fix for free —
    but only while it stays a plain call. `scrollIntoView({block: 'start'})`
    with a manual offset would double up."""
    assert 'target.scrollIntoView();' in html
