"""Access tiers — the one permission axis in the Hub.

Rewritten 2026-08-21 (Thomas). There used to be nine independent access
mechanisms spread across four files; answering "can Ben see this?" meant
checking up to four of them. See the long note in ``app.py``'s USERS block for
the full history and the two symptoms that made the case (a dead ``ppm_access``
field set on all thirteen people and read nowhere, and ``proposal_access``
drifting so far from its name that Pipeline Board built a second roster rather
than read it).

Three tiers:

    owner       Thomas. /admin, password resets, feedback inbox, vault
                delete, proposal diffs.
    leadership  Stephanie, Tony, Trey. Office Ops (Numbers + Compliance),
                PSC + PM training oversight, Ask PPS curation, estimator
                pricing defaults.
    team        Everyone else. Every tool, every pipeline board, all history,
                Team View.

This module lives on its own, with no imports from the rest of the Hub, so that
``app.py``, ``office_ops.py``, ``ask_pps.py``, and ``pipeline_board.py`` can all
agree on one definition instead of each keeping a copy that drifts. That drift
is the failure mode this whole rework exists to fix — do not re-inline these
constants into a feature module.

A tier is what you may SEE. It is separate from ASSIGNMENT — which pipeline
board opens by default, whose name prefills on a proposal. Assignment grants
nothing. Most of the nine old mechanisms were assignment wearing a permission
costume.
"""

from __future__ import annotations

TIER_OWNER = 'owner'
TIER_LEADERSHIP = 'leadership'
TIER_TEAM = 'team'

DEFAULT_TIER = TIER_TEAM

# Ordered least- to most-privileged. Anything unrecognized sorts to 0 on read
# and to "impossible" on the requirement side, so a typo'd tier fails closed.
_TIER_RANK = {TIER_TEAM: 0, TIER_LEADERSHIP: 1, TIER_OWNER: 2}


def user_tier(users, user_key):
    """This person's tier. Unknown key → the most restrictive answer."""
    return ((users or {}).get(user_key) or {}).get('tier', DEFAULT_TIER)


def has_tier(users, user_key, minimum):
    """True when this person is at ``minimum`` tier or above.

    Fails closed twice over: an unknown user_key is False, and an unrecognized
    ``minimum`` gets rank 99 so no real tier can satisfy it.
    """
    if not user_key or not users or user_key not in users:
        return False
    return _TIER_RANK.get(user_tier(users, user_key), 0) >= _TIER_RANK.get(minimum, 99)


def is_owner(users, user_key):
    return has_tier(users, user_key, TIER_OWNER)


def is_leadership(users, user_key):
    """Leadership *or* owner — tiers are cumulative, not exclusive."""
    return has_tier(users, user_key, TIER_LEADERSHIP)


def can_edit_pricing_defaults(users, user_key):
    """Company-wide estimator rates. Leadership and up (2026-08-27).

    Used to be owner-only. Thomas opened it so Tony, Trey and Stephanie can
    keep siding / roofing / gutter / painting defaults current without
    waiting on him. Team still cannot; a field override on one job is
    different from changing what every new estimate pre-fills.
    """
    return is_leadership(users, user_key)


def tier_label(tier):
    """Human-readable, for admin screens and the weekly recap."""
    return {
        TIER_OWNER: 'Owner',
        TIER_LEADERSHIP: 'Leadership',
        TIER_TEAM: 'Team',
    }.get(tier, 'Team')
