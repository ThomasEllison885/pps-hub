"""One time-ordered activity feed for the Admin page.

The Admin page used to render proposals, PPMs and trade partner scopes as three
parallel lists of twenty. Three lists answer "what are the last twenty
proposals" — a question nobody was asking — while the question actually being
asked, "what happened in the Hub this week", meant reading three columns and
merging them by eye.

Lives outside ``app.py`` so it can be tested: no test in this repo imports
``app.py``, and a display rule with an ordering bug in it is exactly the kind of
thing that should have a test. Same reason ``tiers.py``, ``weekly_recap.py`` and
``system_state.py`` are their own modules.
"""

from __future__ import annotations

from datetime import datetime

import user_aliases


ACTIVITY_KIND_LABELS = {
    'proposal': 'Proposal',
    'ppm': 'PPM',
    'tps': 'TPS',
}


def _pretty_key(user_key):
    """A readable name from a roster key.

    Resolves first, for the same reason `daily_digest._display_name` does: all
    three tables this feed merges carry `generated_by`, which is the short
    consultant key on anything logged before 093244f or through a bookmarked
    proposal tool. Without the resolve, `'rachel'` prettifies into a perfectly
    convincing **"Rachel"**, and the Admin feed shows two people who are one
    person — the same symptom as the nightly digest, on the page Thomas is
    most likely to be looking at when he wonders who did something.

    No roster is consulted here on purpose: this module stays free of `app.py`
    so it can be tested, so it prettifies rather than looks up. That is also
    why the fix is `resolve` and not `resolve_for` — the job is to make a key
    readable, not to decide whether it belongs to anyone.
    """
    return user_aliases.resolve(user_key).replace('_', ' ').title() or '—'


def merge_activity(proposals, ppms, subscopes, limit=30):
    """One time-ordered feed out of the three activity logs.

    The Admin page used to render these as three parallel lists of twenty. Three
    lists answer "what are the last twenty proposals" — a question nobody was
    asking — while the question actually being asked, "what happened in the Hub
    this week", required reading three columns and merging them by eye.

    Rows with no timestamp sort last rather than crashing the comparison. They
    exist: ``generated_at`` is nullable in all three tables, and a NULL sorting
    first would put the least informative rows at the top of the page.
    """
    items = []

    for p in proposals or []:
        items.append({
            'kind': 'proposal',
            'id': p.get('id'),
            'title': p.get('property_name') or p.get('client_name') or 'Unnamed',
            'who': _pretty_key(p.get('generated_by')),
            'user_key': user_aliases.resolve(p.get('generated_by')),
            'context': p.get('consultant_name') or '',
            'extra': '',
            'when': p.get('generated_at'),
            'document_id': p.get('document_id'),
        })

    for p in ppms or []:
        items.append({
            'kind': 'ppm',
            'id': p.get('id'),
            'title': p.get('client_name') or p.get('property_name') or 'Unnamed',
            'who': _pretty_key(p.get('generated_by')),
            'user_key': user_aliases.resolve(p.get('generated_by')),
            'context': p.get('pm_name') or '',
            'extra': p.get('proj_type') or '',
            'when': p.get('generated_at'),
            'document_id': None,
        })

    for s in subscopes or []:
        bits = [b for b in (
            (s.get('language') or '').title(),
            f"PO {s['po_number']}" if s.get('po_number') else '',
        ) if b]
        items.append({
            'kind': 'tps',
            'id': s.get('id'),
            'title': s.get('property_name') or 'Unnamed',
            'who': _pretty_key(s.get('generated_by')),
            'user_key': user_aliases.resolve(s.get('generated_by')),
            'context': s.get('consultant_name') or '',
            'extra': ' · '.join(bits),
            'when': s.get('generated_at'),
            'document_id': None,
        })

    # `or floor` rather than sorting on `when` directly: sorting a mix of None
    # and datetime raises TypeError, which would take the Admin page down. The
    # floor puts untimed rows last, which is also where they belong — a row with
    # no timestamp is the least informative thing on the page. `generated_at` is
    # nullable in all three tables, so this is reachable, not defensive.
    floor = datetime.min
    items.sort(key=lambda i: i['when'] or floor, reverse=True)
    return items[:limit]


