"""One palette, defined once.

Run: python -m pytest tests/test_palette.py -v

Thomas, 2026-09-01: "I don't think one matters over the other. I see they are
different but lets pick one and make it consistent. The only color I care
about is the blue in the company logo."

── What was actually wrong ─────────────────────────────────────────────────

Twenty-four templates carried their own `:root` block redefining the palette,
and twenty-seven drew it from `pps-global.css`. The two had drifted, so **the
Hub rendered in two palettes depending on which page you were on**:

    --border    #D8E8F2  (24 pages)   vs  #D0DCE8  (27 pages)
    --gray      #444                  vs  #3A3A3A
    --shadow    0 2px 16px …0.08      vs  0 3px 16px …0.10
    --green     #27AE60               vs  #1E8449
    --amber     #E67E22               vs  #D68910
    --red       #E74C3C               vs  #C0392B

Not one template was a pure duplicate — every single one disagreed on at least
one value. So there was no "delete the redundant copies" tidy-up available;
choosing was the prerequisite, and it was Thomas's call to make, not a
refactor.

Global won on two counts beyond being a coin flip. It was already the majority
and already loaded by every page, so adopting it *deletes* blocks rather than
moving them. And it is measurably more legible — the inline green and red
**fail** WCAG AA contrast on white (2.87 and 3.82); the global ones pass (4.72
and 5.44). Those are the status pills people read on a phone outdoors.

── The brand is untouched, which was the one hard requirement ──────────────

`--blue` (#0096D6) and `--dark-blue` (#004C8C) were **already identical**
everywhere they were defined — they were never part of the drift, and nothing
here changed them. White is likewise unaffected: cards are plain white in both
palettes. Verified by screenshot: 20 pages changed, 0 changed layout, and the
header blue is pixel-identical.

── What is deliberately exempt ─────────────────────────────────────────────

Office Ops runs a warm navy/gold/cream palette across its three pages, and the
offline page has its own lighter blues for a disconnected state. Those are
design decisions and are allowlisted below rather than silently skipped, so
the next person can tell the difference between "exempt" and "missed".
"""
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(ROOT, 'templates')
GLOBAL_CSS = os.path.join(ROOT, 'static', 'pps-global.css')

# Pages with a deliberate palette of their own. Adding to this list is a design
# decision; it should be rare and it should be obvious in the diff.
OWN_PALETTE = {
    'office_ops.html',
    'office_ops_compliance.html',
    'office_ops_landing.html',
    'offline.html',
}


def _global_vars():
    with open(GLOBAL_CSS, encoding='utf-8') as fh:
        return set(re.findall(r'^\s*(--[\w-]+)\s*:', fh.read(), re.M))


def _templates():
    return [f for f in sorted(os.listdir(TEMPLATES)) if f.endswith('.html')]


def _read(name):
    with open(os.path.join(TEMPLATES, name), encoding='utf-8') as fh:
        return fh.read()


def _declared_in(name):
    """Custom properties this template defines for itself."""
    out = {}
    for block in re.findall(r'<style[^>]*>(.*?)</style>', _read(name), re.S):
        for m in re.finditer(r':root\s*\{([^}]*)\}', block):
            out.update(dict(re.findall(r'(--[\w-]+)\s*:\s*([^;]+);', m.group(1))))
    return out


# ── the rule ────────────────────────────────────────────────────────────────

def test_no_template_redefines_a_variable_the_global_stylesheet_owns():
    """The whole point. A template that redefines `--border` wins the cascade
    — it comes after the stylesheet link — so the drift is invisible until you
    put two pages side by side, which nobody does."""
    gvars = _global_vars()
    offenders = []
    for name in _templates():
        if name in OWN_PALETTE:
            continue
        for var in _declared_in(name):
            if var in gvars:
                offenders.append(f'{name}:{var}')
    assert not offenders, (
        'these redefine variables pps-global.css already owns, which is how '
        f'the Hub ended up with two palettes: {offenders}')


def test_a_template_may_still_define_variables_of_its_own():
    """Not a ban on `:root`. admin_training needs --draft/--edit/--live and
    admin_system_state needs --ok/--warn/--bad; those exist nowhere else and
    belong with the page that uses them."""
    gvars = _global_vars()
    local = {n: [v for v in _declared_in(n) if v not in gvars]
             for n in _templates() if n not in OWN_PALETTE}
    assert any(v for v in local.values()), (
        'no template defines a local variable any more — if that is because '
        'they were all pushed into the global stylesheet, that file is now '
        'carrying page-specific colours')


def test_every_variable_used_still_resolves():
    """The failure that would have made this change break pages rather than
    recolour them: deleting a declaration that something still reads. An
    unresolvable `var()` is not an error, it is an invalid property — the
    style silently does not apply."""
    gvars = _global_vars()
    broken = []
    for name in _templates():
        # `var(--x)` only. The two-argument form — `var(--bg, #F2F7FB)` on the
        # login pages, `var(--gold, #B8922A)` on Ask PPS — carries its own
        # fallback and is fine by construction; flagging those sent me looking
        # at four templates that were never broken.
        used = set(re.findall(r'var\(\s*(--[\w-]+)\s*\)', _read(name)))
        available = gvars | set(_declared_in(name))
        for var in sorted(used - available):
            broken.append(f'{name}:{var}')
    assert not broken, f'used with no fallback and defined nowhere: {broken}'


# ── the brand, which is the part Thomas cares about ─────────────────────────

@pytest.mark.parametrize('var,value', [('--blue', '#0096D6'),
                                       ('--dark-blue', '#004C8C')])
def test_the_company_blues_are_what_they_are(var, value):
    """Thomas: "The only color I care about is the blue in the company logo.
    It is kind of our own blue." These two are it — #0096D6 is the mark in the
    app icon, #004C8C the navy behind it and the Hub header."""
    with open(GLOBAL_CSS, encoding='utf-8') as fh:
        css = fh.read()
    assert re.search(rf'{var}\s*:\s*{value}\s*;', css, re.I), (
        f'{var} is no longer {value}')


def test_nothing_overrides_the_company_blues():
    """Office Ops and the offline page are allowed their own palette, and both
    do change --blue. Every other page must not."""
    offenders = []
    for name in _templates():
        if name in OWN_PALETTE:
            continue
        declared = _declared_in(name)
        for var in ('--blue', '--dark-blue'):
            if var in declared:
                offenders.append(f'{name}:{var}={declared[var].strip()}')
    assert not offenders, f'the brand blue is being overridden: {offenders}'


def test_the_exempt_pages_really_are_exempt():
    """An allowlist that has gone stale is worse than none — it hides a page
    that should have been converted. Each entry must actually define a palette
    of its own, or it does not belong here."""
    gvars = _global_vars()
    for name in sorted(OWN_PALETTE):
        assert os.path.exists(os.path.join(TEMPLATES, name)), (
            f'{name} is allowlisted and does not exist')
        own = [v for v in _declared_in(name) if v not in gvars]
        assert own, (
            f'{name} is on the own-palette list but defines no variables of '
            f'its own — it should be converted, not exempt')
