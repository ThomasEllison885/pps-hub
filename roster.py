"""Live company roster — one source of truth for who appears on new work.

Hub ``USERS`` is the only list that may grant a login or a dropdown slot.
History tables keep whatever ``generated_by`` they already have, including
departed people. Do not rewrite those rows.

See ``docs/ROSTER.md``.
"""

from __future__ import annotations

ALLOWED_ROLES = frozenset({'admin', 'consultant', 'pm', 'office_manager'})
REQUIRED_FIELDS = ('display', 'role', 'tier', 'title', 'email')
# Dropped from USERS. Keep generating this SQL for hub_users cleanup.
# History logs are left alone.
RETIRED_USER_KEYS = ('admin', 'derek_kidney')

_SQL_SAFE = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')


def validate_users(users):
    """Human-readable errors. Empty list means the roster may boot."""
    errors = []
    users = users or {}
    for key in RETIRED_USER_KEYS:
        if key in users:
            errors.append(
                f'{key} is retired — remove them from USERS. History rows stay.'
            )
    for key, person in users.items():
        if not key or set(key) - _SQL_SAFE:
            errors.append(f'user_key {key!r} is not a plain identifier')
            continue
        if not isinstance(person, dict):
            errors.append(f'USERS[{key}] must be a dict')
            continue
        for field in REQUIRED_FIELDS:
            if not (person.get(field) or '').strip():
                errors.append(f'USERS[{key}] is missing required field {field!r}')
        role = (person.get('role') or '').strip()
        if role and role not in ALLOWED_ROLES:
            errors.append(
                f'USERS[{key}] role {role!r} is not one of {sorted(ALLOWED_ROLES)}'
            )
    return errors


def assert_users(users):
    errors = validate_users(users)
    if errors:
        raise RuntimeError('USERS roster invalid:\n- ' + '\n- '.join(errors))


def people_payload(users):
    """JSON list for /api/roster — live people only, sorted by display name."""
    rows = []
    for key, person in (users or {}).items():
        rows.append({
            'user_key': key,
            'display': person.get('display') or key,
            'role': person.get('role') or '',
            'title': person.get('title') or '',
            'email': person.get('email') or '',
            'phone': person.get('phone') or '',
        })
    rows.sort(key=lambda r: (r['display'].lower(), r['user_key']))
    return rows


def retired_sql_in_list():
    for key in RETIRED_USER_KEYS:
        if set(key) - _SQL_SAFE:
            raise ValueError(f'retired key {key!r} is not SQL-safe')
    return '(' + ', '.join(f"'{k}'" for k in RETIRED_USER_KEYS) + ')'
