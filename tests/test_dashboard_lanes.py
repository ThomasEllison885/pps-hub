"""Which lane each person's dashboard leads with.

Run: python -m pytest tests/test_dashboard_lanes.py -v

Thomas set these by hand on 2026-08-31, replacing four role-based CSS rules
(`.dash-role-pm .lane-production { order: 1 }` and friends) that made the
order a property of your role. That was right often enough to survive and
wrong for the two people who do not fit their role's shape: Stephanie is the
office manager and opens the Hub to do Numbers, and Trey is a PM who spends
his day on oversight.

The assignments, in his words:

    "Stephanie can have admin show up at the top (after jump back in).
     James, Ben, Phil, Nick, and Jordan can have Production and Field up at
     the top. Everyone else can keep sales and consulting at the top."

Two of them were ambiguous and were asked about rather than guessed:

  * **Thomas himself.** "Everyone else" would have moved him off Admin-first,
    which is what the old admin CSS rule gave him. He confirmed: Sales.
  * **Trey.** A PM, but not in the list of PMs. He confirmed the omission was
    deliberate — Sales first, not Production. The test below names him
    explicitly, because the next person to read `LANE_ORDER` will assume he
    was forgotten and "fix" it.

── What this is not ────────────────────────────────────────────────────────

Order is a preference. It grants nothing and hides nothing — a lane someone
cannot see is not rendered at all, so listing `admin` first for someone
without Office Ops is a no-op rather than a leak. There is a test for that,
because a per-person dict sitting next to the roster is exactly the shape that
grows into an access mechanism nobody remembers to check. Access stays in
`tiers.py`.
"""
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import dashboard_lanes as dl  # noqa: E402

SALES_FIRST = ('thomas_ellison', 'tony_cumella', 'adam_cupito', 'rachel_farler',
               'andy_potts', 'trey_hollmeyer')
PRODUCTION_FIRST = ('james_boling', 'ben_ramsey', 'phil_miller',
                    'nick_triplett', 'jordan_allen')


# ── the assignments themselves ──────────────────────────────────────────────

def test_stephanie_opens_on_admin():
    """She opens the Hub to do Numbers and Compliance."""
    assert dl.order_for('stephanie_whetstone')[0] == 'admin'


@pytest.mark.parametrize('user_key', PRODUCTION_FIRST)
def test_the_project_managers_open_on_production(user_key):
    assert dl.order_for(user_key)[0] == 'production'


@pytest.mark.parametrize('user_key', SALES_FIRST)
def test_everyone_else_opens_on_sales(user_key):
    assert dl.order_for(user_key)[0] == 'sales'


def test_trey_is_sales_first_on_purpose_even_though_he_is_a_pm():
    """He is a PM and is deliberately not in the PM group — asked and
    answered on 2026-08-31. Without this test the next reader adds him to
    LANE_ORDER as an obvious omission."""
    assert 'trey_hollmeyer' not in dl.LANE_ORDER
    assert dl.order_for('trey_hollmeyer')[0] == 'sales'


def test_thomas_is_no_longer_admin_first():
    """The old `.dash-role-admin .lane-admin { order: 0 }` gave him Admin
    first. He chose to join "everyone else" — also asked and answered, and
    also the kind of thing that reads as a regression later."""
    assert dl.order_for('thomas_ellison')[0] == 'sales'


# ── it cannot lose a lane ───────────────────────────────────────────────────

def test_everyone_gets_every_lane_exactly_once():
    """The failure that matters: a lane left unplaced computes to CSS
    `order: 0` and floats to the TOP — the opposite of being forgotten, and it
    would look like a deliberate choice."""
    for user_key in SALES_FIRST + PRODUCTION_FIRST + ('stephanie_whetstone',):
        order = dl.order_for(user_key)
        assert sorted(order) == sorted(dl.LANES), f'{user_key}: {order}'
        assert len(set(order)) == len(order)


def test_somebody_with_no_entry_gets_the_default():
    """A new hire on their first morning, before anyone has thought about
    them."""
    assert dl.order_for('brand_new_person') == dl.DEFAULT_ORDER
    assert dl.order_for(None) == dl.DEFAULT_ORDER
    assert dl.order_for('') == dl.DEFAULT_ORDER


def test_a_typo_costs_that_person_their_preference_and_nothing_else(monkeypatch):
    """`LANE_ORDER` is a preference *over* the canonical list, not a
    replacement for it — so a misspelled lane cannot blank a dashboard."""
    monkeypatch.setitem(dl.LANE_ORDER, 'someone', ('prodcution', 'admin'))
    assert dl.order_for('someone') == ('admin', 'sales', 'production')


def test_a_partial_list_is_completed_not_truncated(monkeypatch):
    monkeypatch.setitem(dl.LANE_ORDER, 'someone', ('production',))
    assert dl.order_for('someone') == ('production', 'sales', 'admin')


def test_a_repeated_lane_is_placed_once(monkeypatch):
    monkeypatch.setitem(dl.LANE_ORDER, 'someone', ('admin', 'admin', 'sales'))
    assert dl.order_for('someone') == ('admin', 'sales', 'production')


def test_a_lane_added_to_the_hub_later_reaches_everybody(monkeypatch):
    """Nobody should have to revisit twelve entries to add a fourth lane."""
    monkeypatch.setattr(dl, 'LANES', ('sales', 'production', 'admin', 'training'))
    monkeypatch.setattr(dl, 'DEFAULT_ORDER', dl.LANES)
    assert 'training' in dl.order_for('stephanie_whetstone')
    assert dl.order_for('stephanie_whetstone')[0] == 'admin', 'her choice survived'


# ── it is a preference, not a permission ────────────────────────────────────

def test_the_order_says_nothing_about_access():
    """Listing `admin` first for someone without Office Ops is a no-op — the
    lane is not rendered for them at all. This module must never become a
    place where access is decided; that is `tiers.py`.
    """
    assert 'admin' in dl.order_for('adam_cupito'), (
        'every order names every lane, including ones the person cannot see')
    source = open(os.path.join(ROOT, 'dashboard_lanes.py')).read()
    for forbidden in ('tier', 'can_access', 'TIER_', 'role'):
        assert not re.search(rf'\b{forbidden}\w*\s*[=(]', source), (
            f'dashboard_lanes.py has started making {forbidden} decisions')


def test_css_order_is_positions_not_names():
    o = dl.css_order('stephanie_whetstone')
    assert o == {'admin': 0, 'sales': 1, 'production': 2}
    assert all(isinstance(v, int) for v in o.values())
