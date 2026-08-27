"""Who can change what every future estimate starts from.

Run: python -m pytest tests/test_pricing_access.py -v

`tiers.can_edit_pricing_defaults` is the decision and `tests/test_tiers.py`
pins it. This file pins the *wiring* around it, which is where an access
change usually leaks:

  * the route enforces it (tests/test_training_access.py),
  * every page that offers the link asks the same question, and
  * the dashboard actually computes the summary for the people who can now
    edit — not just for the owner it used to be gated on.

That last one is the interesting one. The old dashboard read

    if is_admin:
        unread_feedback, unread_diffs = _admin_inbox_counts()
        pricing_summary = _pricing_summary_for_dashboard()

so widening the route without splitting that block gives leadership a card
with no rates on it, or no card at all. The two questions are not the same
question any more.
"""
import ast
import os
import sys

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import hub_time  # noqa: E402
import hub_usage  # noqa: E402

SRC = open(os.path.join(ROOT, 'app.py'), encoding='utf-8').read()
TREE = ast.parse(SRC)


def _fn(name):
    for n in ast.walk(TREE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return ast.get_source_segment(SRC, n)
    raise AssertionError(f'{name} not found in app.py')


# ── the pages that offer the link ───────────────────────────────────────────

def test_the_estimating_page_asks_the_tier_question():
    """The card next to the four estimators is the one leadership will
    actually find. It has to be gated on the same predicate as the route, not
    on a role string."""
    body = _fn('estimating_hub')
    assert 'can_edit_pricing=can_edit_pricing_defaults(user_key)' in body, (
        'the estimating page must pass the tier answer, not assume it')


def test_the_dashboard_asks_the_tier_question():
    body = _fn('dashboard')
    assert 'can_edit_pricing_defaults(user_key)' in body
    assert 'can_edit_pricing=' in body, 'the template needs the answer'


def _blocks_guarded_by(fn_name, guard):
    """Source of every `if <guard>:` body inside a function, via the AST so a
    reformat does not break the assertion."""
    src = _fn(fn_name)
    tree = ast.parse(src)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and ast.get_source_segment(src, node.test) == guard:
            out.extend(ast.get_source_segment(src, stmt) or '' for stmt in node.body)
    return '\n'.join(out)


def test_the_pricing_summary_is_computed_for_everyone_who_can_edit():
    """The mutation this catches: leaving `pricing_summary` inside the
    `if is_admin:` block that also fetches the owner's inbox counts. The card
    then renders for Tony with no rates in it."""
    body = _fn('dashboard')
    assert '_pricing_summary_for_dashboard()' in body
    assert '_pricing_summary_for_dashboard' not in _blocks_guarded_by(
        'dashboard', 'is_admin'), (
        'pricing_summary is still gated on is_admin; leadership gets an '
        'empty card')
    assert '_pricing_summary_for_dashboard' in _blocks_guarded_by(
        'dashboard', 'edit_pricing'), (
        'the summary should be fetched exactly when someone can edit it')


def test_feedback_counts_did_not_ride_along():
    """Widening pricing must not widen the feedback inbox. Those counts are
    the owner's and stay behind is_admin."""
    assert '_admin_inbox_counts' in _blocks_guarded_by('dashboard', 'is_admin'), (
        'the feedback and diff counts left the owner-only block')


def test_opening_the_editor_is_recorded_like_every_other_page():
    """F-03: if it is a page in the Hub, we know it was opened. A new
    `@logs_open` feature with no label shows up in the digest as a raw key."""
    assert "@logs_open('pricing_defaults')" in SRC
    assert hub_usage.FEATURE_LABELS.get('pricing_defaults')


# ── the two cards ───────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def env():
    e = Environment(loader=FileSystemLoader(os.path.join(ROOT, 'templates')),
                    undefined=StrictUndefined)
    e.filters.update(hub_time.FILTERS)
    return e


def _estimating(env, can_edit):
    return env.get_template('estimating.html').render(
        recent_siding=[], recent_roofing=[], recent_gutters=[],
        recent_painting=[], can_edit_pricing=can_edit,
    )


def test_estimating_shows_the_card_only_to_the_people_who_can_edit(env):
    allowed = _estimating(env, True)
    assert '/admin/pricing-defaults' in allowed
    denied = _estimating(env, False)
    assert '/admin/pricing-defaults' not in denied, (
        'a link that redirects you back to the dashboard is worse than no '
        'link')


def test_the_estimating_card_says_an_override_is_still_yours(env):
    """The distinction Thomas drew: change the default, or change one job.
    Estimators keep the second and the card should not imply otherwise."""
    allowed = _estimating(env, True)
    assert 'override' in allowed.lower()


# ── who moved the rate ──────────────────────────────────────────────────────

def test_the_summary_label_is_eastern_not_raw_utc():
    """`_pricing_summary_for_dashboard` formatted a naive-UTC timestamp with a
    bare `.strftime`, so an edit made after 8pm Eastern showed tomorrow's
    date. Same bug as the templates, one layer up — hub_time.fmt converts."""
    body = _fn('_pricing_summary_for_dashboard')
    assert '.strftime(' not in body, (
        'formatting a database timestamp by hand renders UTC; use hub_time')
    assert 'hub_time.fmt(' in body


def _dashboard(**over):
    """Context and filters both borrowed from tests/test_dashboard_template.py
    — the dashboard needs more of each than this file is about."""
    from test_dashboard_template import _ctx, _env
    return _env().get_template('dashboard.html').render(**_ctx(**over))


def test_the_card_names_who_moved_the_rate():
    """One person editing company rates needed no byline. Four do."""
    summary = {'is_custom': True, 'updated_label': 'Aug 26, 2026',
               'updated_by_name': 'Tony Cumella', 'siding_labor': 45,
               'roofing_labor': 80, 'gutter_lf': 12, 'painting_hour': 55}
    html = _dashboard(can_edit_pricing=True, pricing_summary=summary,
                      admin_lane_open=False, user_role='consultant')
    assert 'Updated Aug 26, 2026 by Tony Cumella' in html


def test_a_summary_without_a_name_still_renders():
    """StrictUndefined here would 500 the whole dashboard over a byline."""
    summary = {'is_custom': True, 'updated_label': 'Aug 26, 2026',
               'siding_labor': 45, 'roofing_labor': 80,
               'gutter_lf': 12, 'painting_hour': 55}
    html = _dashboard(can_edit_pricing=True, pricing_summary=summary,
                      admin_lane_open=False, user_role='consultant')
    assert 'Updated Aug 26, 2026' in html
