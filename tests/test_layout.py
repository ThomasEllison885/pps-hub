"""One content column, defined once.

Run: python -m pytest tests/test_layout.py -v

Thomas, 2026-09-01, after the palette: "What would be the next step to tidy
the site up?"

Measured rather than guessed. `.main` — the wrapper every page's content sits
in — had **31 distinct definitions across 48 templates**, and thirteen
different widths:

    1100px  admin, my_proposals, my_ppms, my_tpscopes …
    1000px  dashboard, team_view, admin_training …
     900px  admin_breakdown, admin_diffs, proposal_diff …
     860px  psc_training, pm_training
     820px  guide
     720px  ask_pps, the four estimator results
     640px  site_visit

So clicking Dashboard → My Proposals → Ask PPS moved the content column
1000 → 1100 → 720. Each page was internally coherent; no two agreed.

**1100px**, because it was already the most common and suits the table- and
card-heavy pages that are most of the Hub.

── Narrow is a decision, not a leftover ────────────────────────────────────

Some pages have a real reason to be narrower and keep their own `max-width`:
long-form reading (the guide, the two training courses, Ask PPS), a form
filled on a phone in the field (site visit), printed estimator output, and the
Pipeline Board, which is deliberately full-bleed. `NARROW` below is that list
with the reason attached, so the next person can tell a decision from an
oversight — the same shape as the Office Ops exemption in the palette work.

── What this changed that is worth knowing ─────────────────────────────────

Six pages had **no** `.main` rule at all and ran full-bleed: `clients`,
`estimating`, and the four estimator entry pages. They are now capped at
1100px like everything else. That is the intended tidy-up rather than a side
effect — content stretched across a 2,560px monitor was never deliberate — but
it is a real change to those six and is recorded here rather than buried.

── A note on how this was verified ─────────────────────────────────────────

The screenshot harness renders each template's CSS against fixed markup that
always contains a `.main`. That is right for colour changes and **misleading
for structural rules**: it reported 28 pages changing when only six really do,
because it injects a `.main` into templates that never had one. The reliable
check for a change like this is the markup one — which templates actually use
`class="main"` — and that is what the six came from.
"""
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(ROOT, 'templates')
GLOBAL_CSS = os.path.join(ROOT, 'static', 'pps-global.css')

CANONICAL = '1100px'

# Pages that keep their own width, and why. Adding to this list is a design
# decision and should read like one in the diff.
NARROW = {
    'guide.html': 'long-form reading — line length',
    'ask_pps.html': 'question and answer, reads like prose',
    'psc_training.html': 'course material, read start to finish',
    'pm_training.html': 'course material, read start to finish',
    'psc_roleplay.html': 'scripted dialogue, reads as prose',
    'site_visit.html': 'a form, filled on a phone in the field',
    'gutter_result.html': 'estimator output, printed',
    'painting_result.html': 'estimator output, printed',
    'roofing_result.html': 'estimator output, printed',
    'siding_result.html': 'estimator output, printed',
    'gutter_preview.html': 'estimator form, narrow by design',
    'painting_preview.html': 'estimator form, narrow by design',
    'roofing_preview.html': 'estimator form, narrow by design',
    'siding_preview.html': 'estimator form, narrow by design',
    'pipeline_board.html': 'full-bleed board, sets its own width',
}


def _templates():
    return [f for f in sorted(os.listdir(TEMPLATES)) if f.endswith('.html')]


def _css(name):
    with open(os.path.join(TEMPLATES, name), encoding='utf-8') as fh:
        s = fh.read()
    return '\n'.join(re.findall(r'<style[^>]*>(.*?)</style>', s, re.S))


def _main_width(name):
    """The max-width this template sets on .main, if any."""
    css = re.sub(r'/\*.*?\*/', '', _css(name), flags=re.S)
    for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', css):
        if ' '.join(m.group(1).split()) != '.main':
            continue
        w = re.search(r'max-width\s*:\s*([^;]+)', m.group(2))
        if w:
            return w.group(1).strip()
    return None


# ── the rule ────────────────────────────────────────────────────────────────

def test_the_global_stylesheet_owns_the_content_width():
    with open(GLOBAL_CSS, encoding='utf-8') as fh:
        css = fh.read()
    m = re.search(r'\.main\s*\{([^}]*)\}', css)
    assert m, 'pps-global.css no longer defines .main'
    assert CANONICAL in m.group(1), f'the canonical width is no longer {CANONICAL}'


def test_no_page_sets_its_own_width_without_a_reason():
    """The whole point. A page-level max-width wins the cascade — it comes
    after the stylesheet link — so a stray one is invisible until you notice
    the column jumping as you move around."""
    offenders = [f'{n} ({_main_width(n)})' for n in _templates()
                 if n not in NARROW and _main_width(n)]
    assert not offenders, (
        'these set their own content width and are not on the NARROW list, '
        f'which is how thirteen widths happened: {offenders}')


def test_every_narrow_page_actually_is_narrow():
    """A stale exemption is worse than none — it hides a page that should have
    been converted. If a page on this list no longer sets its own width, it is
    getting the canonical one and the entry is a lie."""
    stale = []
    for name in sorted(NARROW):
        if not os.path.exists(os.path.join(TEMPLATES, name)):
            stale.append(f'{name} (gone)')
            continue
        if name == 'pipeline_board.html':
            continue          # full-bleed: its width comes from the scroller
        if not _main_width(name):
            stale.append(f'{name} (no longer narrow)')
    assert not stale, f'NARROW is out of date: {stale}'


def test_narrow_means_narrower():
    """Guards the direction. An exemption that is WIDER than canonical is not
    an exemption, it is someone reintroducing the problem with a note."""
    canonical = int(CANONICAL.rstrip('px'))
    wide = []
    for name in NARROW:
        w = _main_width(name) if os.path.exists(os.path.join(TEMPLATES, name)) else None
        if w and w.endswith('px') and int(w.rstrip('px')) > canonical:
            wide.append(f'{name}={w}')
    assert not wide, f'wider than canonical while claiming to be narrow: {wide}'


def test_every_reason_is_a_real_sentence():
    """The list is only useful if the reasons are. A blank one is a decision
    nobody recorded."""
    thin = [n for n, why in NARROW.items() if len(why.split()) < 3]
    assert not thin, f'these exemptions have no stated reason: {thin}'


def test_the_pages_that_had_no_width_now_get_one():
    """Six pages ran full-bleed and are now capped. Named so the change is
    findable if anyone asks why Clients looks different on a big monitor."""
    newly = {'clients.html', 'estimating.html', 'gutter_estimator.html',
             'painting_estimator.html', 'roofing_estimator.html',
             'siding_estimator.html'}
    for name in sorted(newly):
        assert os.path.exists(os.path.join(TEMPLATES, name)), name
        assert not _main_width(name), (
            f'{name} has grown its own width again — it should take the '
            f'canonical one')
        with open(os.path.join(TEMPLATES, name), encoding='utf-8') as fh:
            body = re.sub(r'<style[^>]*>.*?</style>', '', fh.read(), flags=re.S)
        assert re.search(r'class="[^"]*\bmain\b', body), (
            f'{name} no longer uses .main, so it is uncapped again')
