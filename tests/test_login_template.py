"""Login must keep Password on screen after you pick a name.

Run: python -m pytest tests/test_login_template.py -v

Andy Baur, 2026-10-02: could pick his name (and anyone else's) on a laptop
but could not enter a password. Same page on his phone signed in.

Cause: `.name-list { max-height: none }` at `min-width: 480px`. That was
intentional in July 2026 when the roster was shorter and a laptop could
show every name without an inner scroll. Thirteen names later, the list
is ~730px. Header + brand + title sit above it, so Password / Sign In
fall below the fold. Phone CSS kept `max-height: min(42vh, 320px)`, which
is why the same account worked in his pocket.

Forgot Password had the same uncap, so Send Reset Link could vanish the
same way.

The click handler must also `focus()` the password field. Picking a name
is a user gesture, so iOS allows it; without it a laptop user who only
saw names is left with no caret in the field they came for.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(ROOT, 'templates')


def _read(name):
    with open(os.path.join(TEMPLATES, name), encoding='utf-8') as fh:
        return fh.read()


def _uncap_rules(html):
    return re.findall(r'\.name-list\s*\{[^}]*max-height\s*:\s*none', html)


def test_login_does_not_uncap_the_name_list_on_desktop():
    html = _read('login.html')
    assert _uncap_rules(html) == [], (
        'Uncapping .name-list at 480px pushes Password below the fold on a '
        'laptop. Keep a max-height on every width — the phone cap is what '
        'let Andy sign in.'
    )


def test_forgot_password_does_not_uncap_the_name_list_on_desktop():
    html = _read('forgot_password.html')
    assert _uncap_rules(html) == [], (
        'Forgot Password used the same desktop uncap; Send Reset Link then '
        'sits below the fold the same way Sign In did.'
    )


def test_login_name_list_has_a_max_height():
    html = _read('login.html')
    assert re.search(r'\.name-list\s*\{[^}]*max-height\s*:', html), (
        'The name list needs a max-height so Password stays on screen.'
    )


def test_login_has_a_password_field():
    html = _read('login.html')
    assert 'id="login-password"' in html
    assert 'name="password"' in html
    assert 'autocomplete="current-password"' in html


def test_picking_a_name_focuses_the_password_field():
    html = _read('login.html')
    assert 'pw.focus()' in html, (
        'After a name tap, focus the password field so it is on screen and '
        'ready to type. That click is a user gesture, so iOS allows it.'
    )
