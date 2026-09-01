"""Which dashboard lane each person sees first.

── Why this is a per-person setting and not a per-role rule ────────────────

It used to be CSS: `.dash-role-pm .lane-production { order: 1 }` and three
rules like it, so the order followed your role and nothing else. That put
Production first for every PM and Sales first for every consultant, which was
right often enough to survive but wrong for the people who do not fit their
role's shape — Stephanie is the office manager and opens the Hub to do
Numbers, and Trey is a PM who spends his day on oversight rather than jobs.

Thomas set these by hand on 2026-08-31. **`LANE_ORDER` below is the whole
configuration**; the CSS rules it replaced are gone, because two mechanisms
deciding the same thing is how they end up disagreeing.

── Not a permission ────────────────────────────────────────────────────────

Order is a preference. It grants nothing and hides nothing: a lane a person
cannot see is not rendered at all, so listing `admin` first for someone
without Office Ops is a no-op rather than a leak. Access still comes from
`tiers.py`, and it must stay that way — see the "assignment is not permission"
note in CLAUDE.md, which is about exactly this kind of per-person dict growing
into an access mechanism nobody remembers to check.

── Failure mode this is built around ───────────────────────────────────────

A typo in a person's list must not blank their dashboard. `order_for` treats
`LANE_ORDER` as a *preference over* the canonical list rather than a
replacement for it: anything unknown is dropped, anything missing is appended
in default order. So a mangled entry costs that person their preferred order
and nothing else, and a lane added to the Hub later shows up for everybody
without this file being touched.
"""

from __future__ import annotations

# Every lane, in the order they appear in the template. Also the fallback for
# anyone with no entry below, which is why Sales leads: it is what the largest
# group — the consultants — should open to.
LANES = ('sales', 'production', 'admin')

DEFAULT_ORDER = LANES

# user_key → the lanes they care about most, first. Partial lists are fine;
# whatever is left over follows in DEFAULT_ORDER.
#
# Thomas, 2026-08-31, deciding these one by one:
#   * Stephanie opens the Hub to do Numbers and Compliance, so Admin leads.
#   * The five project managers lead with Production & Field.
#   * "Everyone else can keep sales and consulting at the top" — which he
#     confirmed includes himself, so the owner no longer leads with Admin.
#   * Trey is a PM and is deliberately NOT in the Production group. He was
#     asked about directly and the answer was Sales first: he is leadership
#     oversight rather than a jobs PM. Left as a comment because the next
#     person to read this list will assume he was forgotten.
LANE_ORDER = {
    'stephanie_whetstone': ('admin',),

    'james_boling': ('production',),
    'ben_ramsey': ('production',),
    'phil_miller': ('production',),
    'nick_triplett': ('production',),
    'jordan_allen': ('production',),
}


def order_for(user_key):
    """The full lane order for one person, always every lane, no duplicates.

    Returns a tuple in the order they should appear. Unknown names in
    `LANE_ORDER` are dropped and unlisted lanes are appended, so this cannot
    return a list that leaves a lane unplaced — which would give it CSS
    `order: 0` and float it to the top, the opposite of being forgotten.
    """
    preferred = LANE_ORDER.get(user_key) or ()
    out = []
    for lane in preferred:
        if lane in LANES and lane not in out:
            out.append(lane)
    for lane in DEFAULT_ORDER:
        if lane not in out:
            out.append(lane)
    return tuple(out)


def css_order(user_key):
    """{lane: index} — what the template puts in each lane's `style`.

    Inline rather than a stylesheet rule per person: the order is a property
    of who is signed in, and the page is already rendered per person. A CSS
    file that grew a rule per employee would be a second roster to keep in
    step with the first.
    """
    return {lane: i for i, lane in enumerate(order_for(user_key))}
