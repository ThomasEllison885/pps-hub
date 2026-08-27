"""Access tiers — the one permission axis (2026-08-21 rework).

Pure logic, no DB. Run: python -m pytest tests/test_tiers.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tiers as t


_USERS = {
    'thomas_ellison': {'role': 'admin', 'tier': 'owner'},
    'tony_cumella': {'role': 'consultant', 'tier': 'leadership'},
    'trey_hollmeyer': {'role': 'pm', 'tier': 'leadership'},
    'stephanie_whetstone': {'role': 'office_manager', 'tier': 'leadership'},
    'andy_potts': {'role': 'consultant', 'tier': 'team'},
    'phil_miller': {'role': 'pm', 'tier': 'team'},
}


def test_tiers_are_cumulative_not_exclusive():
    """Owner satisfies a leadership requirement. The classic bug in a tier
    system is `tier == 'leadership'`, which locks the owner out of everything
    leadership can do."""
    assert t.is_leadership(_USERS, 'thomas_ellison') is True
    assert t.is_leadership(_USERS, 'tony_cumella') is True
    assert t.is_owner(_USERS, 'tony_cumella') is False
    assert t.is_owner(_USERS, 'thomas_ellison') is True


def test_team_tier_is_the_floor():
    for key in ('andy_potts', 'phil_miller'):
        assert t.has_tier(_USERS, key, t.TIER_TEAM) is True
        assert t.is_leadership(_USERS, key) is False
        assert t.is_owner(_USERS, key) is False


def test_unknown_user_fails_closed():
    """What makes removing someone from USERS actually revoke their access."""
    for key in ('former_employee', 'admin', '', None):
        assert t.has_tier(_USERS, key, t.TIER_TEAM) is False
        assert t.is_leadership(_USERS, key) is False
        assert t.is_owner(_USERS, key) is False


def test_missing_or_typod_tier_fails_closed():
    """A user with no tier gets the floor; a typo'd tier grants nothing above it.

    The dangerous direction is a typo defaulting OPEN — 'leadershp' must not
    reach Office Ops just because it isn't recognised.
    """
    users = dict(
        _USERS,
        no_tier={'role': 'pm'},
        typo={'role': 'pm', 'tier': 'leadershp'},
    )
    assert t.user_tier(users, 'no_tier') == t.TIER_TEAM
    assert t.is_leadership(users, 'no_tier') is False
    assert t.is_leadership(users, 'typo') is False
    assert t.has_tier(users, 'typo', t.TIER_TEAM) is True


def test_unknown_requirement_is_unsatisfiable():
    """A typo on the REQUIREMENT side must also fail closed, not open."""
    assert t.has_tier(_USERS, 'thomas_ellison', 'superuser') is False
    assert t.has_tier(_USERS, 'thomas_ellison', '') is False


def test_empty_roster_grants_nothing():
    assert t.is_leadership({}, 'thomas_ellison') is False
    assert t.is_leadership(None, 'thomas_ellison') is False


def test_pricing_defaults_are_leadership_not_owner_only():
    """2026-08-27: Tony, Trey and Stephanie edit estimator company rates.
    The field team still cannot — a per-job override is not a company default."""
    assert t.can_edit_pricing_defaults(_USERS, 'thomas_ellison') is True
    for key in ('tony_cumella', 'trey_hollmeyer', 'stephanie_whetstone'):
        assert t.can_edit_pricing_defaults(_USERS, key) is True, key
    for key in ('andy_potts', 'phil_miller'):
        assert t.can_edit_pricing_defaults(_USERS, key) is False, key
    assert t.can_edit_pricing_defaults(_USERS, 'former_employee') is False
    assert t.can_edit_pricing_defaults({}, 'thomas_ellison') is False


def test_tier_label_is_human_readable():
    assert t.tier_label(t.TIER_OWNER) == 'Owner'
    assert t.tier_label(t.TIER_LEADERSHIP) == 'Leadership'
    assert t.tier_label(t.TIER_TEAM) == 'Team'
    assert t.tier_label('nonsense') == 'Team'
