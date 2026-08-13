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

FEATURE_LABELS = {
    'pipeline': 'Pipeline',
    'compliance': 'Compliance',
    'office_ops': 'Office Ops',
}

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


def record_usage(get_db_fn, user_key, feature, action, title='', meta=''):
    """Best-effort insert. Never raises — a usage log must not break the feature."""
    if not user_key or not feature or not action:
        return
    try:
        conn = get_db_fn()
        if not conn:
            return
        cur = conn.cursor()
        init_tables(cur)
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


def event_label(feature, action, title='', count=1):
    """One digest line for a grouped usage event."""
    feat = FEATURE_LABELS.get(feature, (feature or '').replace('_', ' ').title() or 'Hub')
    act = ACTION_LABELS.get(action, (action or '').replace('_', ' ').title() or 'Used')
    head = f'{feat} · {act}'
    if title:
        head = f'{head} · {title}'
    extra = f'{count}×' if count and count > 1 else ''
    return feat, head, extra
