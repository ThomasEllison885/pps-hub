"""Who can run the training modules.

The routes live in app.py, which no test can import, so these are structural
assertions against the source plus tier-logic checks against the real roster.

Run: python -m pytest tests/test_training_access.py -v
"""
import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tiers

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = open(os.path.join(ROOT, 'app.py')).read()
TREE = ast.parse(SRC)

# The three people Thomas named on 2026-08-23, plus the owner.
_USERS = {
    'thomas_ellison': {'display': 'Thomas Ellison', 'role': 'admin', 'tier': 'owner'},
    'tony_cumella': {'display': 'Tony Cumella', 'role': 'consultant', 'tier': 'leadership'},
    'trey_hollmeyer': {'display': 'Trey Hollmeyer', 'role': 'pm', 'tier': 'leadership'},
    'stephanie_whetstone': {'display': 'Stephanie Whetstone', 'role': 'office_manager',
                            'tier': 'leadership'},
    'andy_potts': {'display': 'Andy Potts', 'role': 'consultant', 'tier': 'team'},
    'ben_ramsey': {'display': 'Ben Ramsey', 'role': 'pm', 'tier': 'team'},
}


def _fn(name):
    for n in ast.walk(TREE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return ast.get_source_segment(SRC, n)
    raise AssertionError(f'{name} not found in app.py')


def _decorators(name):
    for n in ast.walk(TREE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return [ast.get_source_segment(SRC, d) for d in n.decorator_list]
    raise AssertionError(f'{name} not found in app.py')


# --- The three named people all resolve to leadership ------------------------

def test_the_three_thomas_named_are_all_leadership():
    """Tony, Trey and Stephanie. Because tiers are the only access axis, gating
    a route at leadership grants all three at once — there is no per-person
    list to keep in sync, which is the whole point of the 2026-08-21 rework."""
    for key in ('tony_cumella', 'trey_hollmeyer', 'stephanie_whetstone'):
        assert tiers.is_leadership(_USERS, key) is True, key
    assert tiers.is_leadership(_USERS, 'thomas_ellison') is True


def test_the_field_team_is_not_swept_in():
    for key in ('andy_potts', 'ben_ramsey'):
        assert tiers.is_leadership(_USERS, key) is False, key


# --- PSC enrolment moved off owner-only --------------------------------------

def test_estimator_pricing_defaults_are_no_longer_owner_only():
    """Was `@require_admin`. 2026-08-27 Thomas opened it to leadership so
    Tony / Trey / Stephanie can keep company rates current."""
    decos = _decorators('admin_pricing_defaults')
    assert not any('require_admin' in (d or '') for d in decos), (
        'estimator pricing defaults are back to owner-only')
    body = _fn('admin_pricing_defaults')
    assert 'can_edit_pricing_defaults' in body, (
        'pricing defaults lost its tier check — that is worse, not better')
    assert 'require_login' in ''.join(decos or []), (
        'pricing defaults must still sit behind a session')


def test_psc_enrolment_is_no_longer_owner_only():
    """Was `@require_admin`, which left Tony unable to enrol the hire he was
    already allowed to sign off every week for. 2026-08-23, Thomas."""
    decos = _decorators('psc_training_enroll_api')
    assert not any('require_admin' in (d or '') for d in decos), (
        'PSC enrolment is back to owner-only')
    assert 'can_psc_training_oversight' in _fn('psc_training_enroll_api'), (
        'PSC enrolment lost its tier check entirely — that is worse, not better')


def test_psc_and_pm_enrolment_now_agree():
    """The asymmetry was the bug: PM enrolment has always been leadership."""
    psc, pm = _fn('psc_training_enroll_api'), _fn('pm_training_enroll_api')
    assert 'can_psc_training_oversight' in psc
    assert 'can_pm_training_oversight' in pm


def test_revoking_a_signoff_stays_owner_only():
    """Deliberately NOT widened. Enrolling is a roster decision; erasing a
    completed sign-off is an audit one, and it stays with Thomas."""
    body = _fn('psc_training_signoff_api')
    assert "if action == 'revoke':" in body
    revoke = body[body.index("if action == 'revoke':"):]
    assert "session.get('role') != 'admin'" in revoke.split('ok =')[0], (
        'revoke lost its owner-only guard')


# --- Redirects guard the same thing their destination guards -----------------

def test_both_training_redirects_check_what_their_target_checks():
    """`/admin/psc-training` used to be `@require_admin` while the page it
    redirects to is leadership — a locked door to an open room. A redirect that
    guards differently from its destination is wrong in one direction or the
    other; these now match."""
    assert 'can_psc_training_oversight' in _fn('admin_psc_training')
    assert 'can_pm_training_oversight' in _fn('admin_pm_training')
    for name in ('admin_psc_training', 'admin_pm_training'):
        assert not any('require_admin' in (d or '') for d in _decorators(name)), name


# --- The oversight page must not gate enrolment on `is_admin` ----------------

def test_the_oversight_page_is_handed_a_tier_flag_not_an_admin_flag():
    """The route can allow enrolment while the template still hides the form
    behind `is_admin`, which would look like the change did nothing."""
    tpl = os.path.join(ROOT, 'templates', 'psc_training_oversight.html')
    html = open(tpl).read()
    assert 'can_enroll' in _fn('psc_training_oversight'), (
        'route does not pass can_enroll')
    assert '{% if can_enroll %}' in html
    for marker in ('Enroll in PSC Training', 'unenrollTrainee', 'graduateTrainee'):
        assert marker in html, marker
    # `is_admin` may survive only for the back-link, never around enrolment.
    for line in html.split('\n'):
        if 'is_admin' in line and not line.strip().startswith(('{#', 'PSC onboarding')):
            assert 'pps-btn-header' in line, f'is_admin still gating: {line.strip()[:80]}'
