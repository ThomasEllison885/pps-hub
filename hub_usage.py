"""Generic Hub usage events for the nightly daily-digest email.

New modules: call ``record_usage(...)`` when a person does something
worth seeing in tomorrow's email. ``daily_digest.collect_digest_items``
reads this table automatically — you do **not** add a new SELECT to the
digest when you ship a feature.

Do not log high-frequency noise (Pipeline 3s polls, presence heartbeats).
Log discrete actions: page opens, imports, Run now, View COI, Generate.

Features that already have their own activity table (proposal_log, ppm_log,
subscope_log, estimate logs, training progress) stay on those tables. This
is for everything that does not — Pipeline Board opens, Compliance, Office
Ops Numbers, and whatever ships next.
"""

from __future__ import annotations

# Every feature that may appear in hub_usage_events, and how it reads in the
# nightly digest. A feature missing from here still records and still works —
# `event_label` falls back to a title-cased slug — but it reads worse, so
# `tests/test_hub_usage.py::test_every_recorded_feature_has_a_label` fails if
# a call site uses a name that is not listed. That catches the typo that would
# otherwise create a silent second feature ('proposal_hist') nobody notices.
FEATURE_LABELS = {
    # Instrumented 2026-08 (the first three)
    'pipeline': 'Pipeline',
    'compliance': 'Compliance',
    'office_ops': 'Office Ops',
    # F-03, 2026-08-26 — the rest of the Hub
    'clients': 'Clients',
    'proposal_history': 'Proposal History',
    'ppm_history': 'PPM History',
    'tps_history': 'TPS History',
    'comparison': 'Proposal Comparison',
    'ask_pps': 'Ask PPS',
    'team_view': 'Team View',
    'estimating': 'Estimating',
    'siding': 'Siding Estimator',
    'roofing': 'Roofing Estimator',
    'gutter': 'Gutter Estimator',
    'painting': 'Painting Estimator',
    'site_visit': 'Site Visit Report',
    'psc_training': 'PSC Training',
    'pm_training': 'PM Training',
    'psc_oversight': 'PSC Accountability',
    'pm_oversight': 'PM Accountability',
    'roleplay': 'PSC Roleplay',
    'guide': 'Field Guide',
    # 2026-08-27 — opened to leadership, so who opens it is worth knowing
    'pricing_defaults': 'Estimating Defaults',
    # 2026-08-29 — the adoption view reads this table and appears in it
    'adoption': 'Adoption',
    # 2026-09-03 — read-only Monday funnel × Hub docs. Not a board.
    'production_link': 'Awarded work',
}

KNOWN_FEATURES = frozenset(FEATURE_LABELS)

ACTION_LABELS = {
    'open': 'Opened',
    'import': 'Imported',
    'refresh': 'Ran check',
    'vision': 'Read COIs',
    'view': 'Viewed COI',
    'override': 'Set expiration',
    'upload': 'Uploaded',
    'generate': 'Generated',
    'notes': 'Saved notes',
    # Ask PPS records the outcome, not just the act. A question the Hub could
    # NOT answer is the more useful of the two: it names something the company
    # has not written down yet. Both stay out of weekly_recap's
    # SCORED_USAGE_ACTIONS — asking a question is not a deliverable, and a
    # leaderboard that counted it would teach people to ask questions.
    'answered': 'Asked (answered)',
    'unanswered': 'Asked (no answer)',
}


def init_tables(cur):
    cur.execute('''
        CREATE TABLE IF NOT EXISTS hub_usage_events (
            id SERIAL PRIMARY KEY,
            user_key VARCHAR(100) NOT NULL,
            feature VARCHAR(50) NOT NULL,
            action VARCHAR(50) NOT NULL,
            title VARCHAR(255),
            meta VARCHAR(255),
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    cur.execute(
        'CREATE INDEX IF NOT EXISTS idx_hub_usage_created '
        'ON hub_usage_events(created_at DESC)'
    )
    cur.execute(
        'CREATE INDEX IF NOT EXISTS idx_hub_usage_user_time '
        'ON hub_usage_events(user_key, created_at DESC)'
    )


# ── Why the table is not created on every write (F-06, fixed 2026-08-26) ────
#
# `record_usage` used to call `init_tables` before every insert: a
# CREATE TABLE IF NOT EXISTS plus two CREATE INDEX IF NOT EXISTS, so four
# statements to log one event. They are all no-ops after the first time, but
# they are not free — each is a round trip, and CREATE INDEX IF NOT EXISTS
# takes a lock on the table it is about to not create.
#
# Now it is checked once per process. The flag is per gunicorn worker and is
# lost on restart, which is the correct amount of caching: after a deploy the
# first usage event in each worker pays for one check and every one after it
# does not. It is set only after the DDL actually succeeded, so a failed run
# is retried rather than assumed done.
#
# The daily digest and the dashboard's "Jump back in" both READ this table
# and deliberately do not call init_tables — a read must not create a table,
# and a Hub where nobody has opened the Pipeline Board should show no
# pipeline card rather than a new empty table.
_tables_ready = False


def ensure_tables(cur, force=False):
    """Create the usage table once per process. True if it is ready."""
    global _tables_ready
    if _tables_ready and not force:
        return True
    try:
        init_tables(cur)
    except Exception as e:
        print(f'hub_usage: could not create tables ({e})')
        return False
    _tables_ready = True
    return True


def reset_tables_ready():
    """Tests only — forget that the tables were checked."""
    global _tables_ready
    _tables_ready = False


def record_usage(get_db_fn, user_key, feature, action, title='', meta=''):
    """Best-effort insert. Never raises — a usage log must not break the feature."""
    if not user_key or not feature or not action:
        return
    try:
        conn = get_db_fn()
        if not conn:
            return
        cur = conn.cursor()
        ensure_tables(cur)
        cur.execute(
            '''INSERT INTO hub_usage_events
                   (user_key, feature, action, title, meta)
               VALUES (%s, %s, %s, %s, %s)''',
            (
                user_key,
                str(feature)[:50],
                str(action)[:50],
                (title or '')[:255] or None,
                (meta or '')[:255] or None,
            ),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f'hub_usage record error ({feature}/{action}): {e}')


def record_open(get_db_fn, user_key, feature, title=''):
    """Log that someone opened a page. One line per route, and the name says
    what it is — an open, not a deliverable.

    Two rules ride on the action being exactly 'open':

      * **The weekly recap must never score it.** `SCORED_USAGE_ACTIONS` in
        weekly_recap.py excludes 'open' on purpose: a leaderboard that counts
        opens is a machine for teaching people to open things. F-03 added
        opens to fifteen more places, which makes that exclusion far more
        load-bearing than it was when three features used it.
      * **The nightly digest rolls them into one line per person** rather
        than one per page, and they do not count toward its activity total or
        rescue anyone from QUIET TODAY. Seeing is not doing.

    Anything that produces something — a generate, an import, an upload —
    uses `record_usage` with its own action instead.
    """
    record_usage(get_db_fn, user_key, feature, 'open', title)


def event_label(feature, action, title='', count=1):
    """One digest line for a grouped usage event."""
    feat = FEATURE_LABELS.get(feature, (feature or '').replace('_', ' ').title() or 'Hub')
    act = ACTION_LABELS.get(action, (action or '').replace('_', ' ').title() or 'Used')
    head = f'{feat} · {act}'
    if title:
        head = f'{head} · {title}'
    extra = f'{count}×' if count and count > 1 else ''
    return feat, head, extra
