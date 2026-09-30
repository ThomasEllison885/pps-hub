"""Hub contacts are a read-only mirror of the Monday CRM Contacts board.

Thomas, 2026-09-30: Monday is the CRM and the source of truth. The Hub only
needs contacts so people can build proposals faster. So the Hub never edits a
contact — Monday overwrites the synced fields on every run — and new contacts
are added in Monday, not here.

── The one rule that matters: identity is the Monday item ID ───────────────

Every contact carries `clients.monday_item_id` under a UNIQUE index, and the
sync upserts on that and nothing else. A new ID creates a contact; a known ID
updates it. **Name, email and phone are never used to match** — fixing a
typo'd email in Monday, changing a title, or two people sharing an inbox
must not create or merge Hub contacts. The first version of this module
(2026-08-10) matched on email-then-name, and that is exactly the behaviour
this replaces.

The unique index allows NULLs on purpose: contacts created in the Hub before
this existed have no Monday ID. They are archived, never deleted (see below),
and Postgres treats NULLs as distinct, so the constraint still guarantees one
Hub row per Monday item.

── What gets archived, never deleted ───────────────────────────────────────

  * A Monday item that disappears from the board → `is_active = FALSE`,
    `archived_reason = 'removed_from_monday'`. If it comes back, the next
    sync reactivates the same row.
  * Every pre-Monday Hub contact (source 'hub') → archived with reason
    'replaced_by_monday' on the first applied sync. Nothing foreign-keys
    to `clients`, and proposals copy name/email/company as text, so old
    proposals never break. The one by-ID reference is client file
    attachments (`documents.log_id`); before archiving, each old contact's
    files move to the Monday contact with the SAME email — exact match, and
    only when exactly one active Monday contact has it. That is the only
    place email is used, it only moves files, and every move and every
    file left behind is listed in the report.

── The first applied sync is gated ─────────────────────────────────────────

Until the owner applies the first sync (after a preview), a normal sync —
the button or the weekly cron — refuses with reason 'awaiting_first_sync'.
The cron sends the preview to Thomas instead. Reason: the first run is the
one that archives every existing Hub contact; it should happen once, on
purpose, with the numbers seen first.

── Safety stop ─────────────────────────────────────────────────────────────

A pull that returns zero contacts aborts before writing anything. A pull that
returns fewer than half the currently active contacts still upserts what it
got but skips inactivation, and says so. A partial Monday response must never
be able to switch the company's contact list off.

── One run at a time ───────────────────────────────────────────────────────

`pg_try_advisory_xact_lock`. Gunicorn runs two workers, so an in-process flag
would not see the other one. The lock is transaction-scoped: it releases on
commit, rollback, or a dropped connection, so a crashed run can never leave
the button stuck. A second request while one is running returns
`skipped: already_running` and does nothing.

send_email_fn(subject, text_body, html_body, recipients) -> bool
"""

from __future__ import annotations

import html as _html
import json
import re
from collections import defaultdict
from datetime import datetime, timezone

import monday_client

# Arbitrary but fixed; the Contacts board ID is memorable and fits a bigint.
LOCK_KEY = 7902650879

SETTINGS_LAST = 'crm_sync_last'
SETTINGS_INITIALIZED = 'crm_sync_initialized'

DEFAULT_GROUP = 'Active Contacts'

# Monday users who have been removed from the account. Their IDs still sit in
# the Consultant column, but `users` no longer returns them, so the API
# cannot supply a name. Identified 2026-09-30 from the board's activity log
# ("Salesman" set to Jeremy Bailey). Reassign their contacts in Monday; this
# label is only what the Hub shows until someone does.
FORMER_MONDAY_USERS = {
    '15316889': 'Jeremy Bailey',
}

INACTIVATION_FLOOR = 0.5

SOURCE_MONDAY = 'monday'
SOURCE_HUB = 'hub'
REASON_REMOVED = 'removed_from_monday'
REASON_REPLACED = 'replaced_by_monday'

CLIENT_FILE_DOC_TYPE = 'client_file'  # mirrors client_files.CLIENT_FILE_DOC_TYPE

# Run by app.init_db through db_ddl.checkpointed, so each one is its own
# savepoint and an already-applied statement costs nothing.
SCHEMA_STATEMENTS = [
    'ALTER TABLE clients ADD COLUMN IF NOT EXISTS monday_item_id BIGINT',
    'CREATE UNIQUE INDEX IF NOT EXISTS uq_clients_monday_item_id ON clients(monday_item_id)',
    'ALTER TABLE clients ADD COLUMN IF NOT EXISTS phone VARCHAR(64)',
    'ALTER TABLE clients ADD COLUMN IF NOT EXISTS title TEXT',
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS company_monday_ids BIGINT[] NOT NULL DEFAULT '{}'",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS owner_monday_ids TEXT[] NOT NULL DEFAULT '{}'",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS owner_user_keys TEXT[] NOT NULL DEFAULT '{}'",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS owner_names TEXT[] NOT NULL DEFAULT '{}'",
    'ALTER TABLE clients ADD COLUMN IF NOT EXISTS monday_group VARCHAR(255)',
    'ALTER TABLE clients ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE',
    f"ALTER TABLE clients ADD COLUMN IF NOT EXISTS source VARCHAR(20) NOT NULL DEFAULT '{SOURCE_HUB}'",
    'ALTER TABLE clients ADD COLUMN IF NOT EXISTS synced_at TIMESTAMP',
    'ALTER TABLE clients ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP',
    'ALTER TABLE clients ADD COLUMN IF NOT EXISTS archived_reason VARCHAR(40)',
    'CREATE INDEX IF NOT EXISTS idx_clients_active ON clients(is_active)',
]


# ── parsing ─────────────────────────────────────────────────────────────────

def format_phone(raw):
    """(937) 670-2068 for a US number; anything else exactly as Monday has it."""
    text = (raw or '').strip()
    if not text:
        return ''
    digits = re.sub(r'\D', '', text)
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    if len(digits) == 10:
        return f'({digits[:3]}) {digits[3:6]}-{digits[6:]}'
    return text


def _column(item, col_id):
    for cv in item.get('column_values') or []:
        if cv.get('id') == col_id:
            return cv
    return {}


def _json(raw):
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) or {}
    except (TypeError, ValueError):
        return {}


def _company(cv):
    """(display text, [linked Companies-board item IDs])."""
    ids = []
    for x in cv.get('linked_item_ids') or []:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            pass
    if not ids:
        # Older API shapes carry the links only in `value`.
        for link in _json(cv.get('value')).get('linkedPulseIds') or []:
            try:
                ids.append(int(link.get('linkedPulseId')))
            except (TypeError, ValueError, AttributeError):
                pass
    name = (cv.get('display_value') or cv.get('text') or '').strip()
    return name[:255], ids


def _owner_ids(cv):
    return [
        str(p.get('id')) for p in (_json(cv.get('value')).get('personsAndTeams') or [])
        if p.get('kind') == 'person' and p.get('id') is not None
    ]


def build_owner_lookup(monday_users, hub_users):
    """{monday_user_id: (hub_user_key or None, display name)}.

    monday_users: {monday_id: email} from monday_client.fetch_monday_users().
    Matched to the Hub roster by email, case-insensitively. All thirteen Hub
    users matched on 2026-09-30, so no hand-kept mapping table exists.
    """
    by_email = {}
    for key, u in (hub_users or {}).items():
        email = (u.get('email') or '').strip().lower()
        if email:
            by_email[email] = (key, u.get('display') or key)
    lookup = {}
    for mid, email in (monday_users or {}).items():
        hit = by_email.get((email or '').strip().lower())
        if hit:
            lookup[str(mid)] = hit
        else:
            lookup[str(mid)] = (None, (email or '').split('@')[0] or f'Monday user {mid}')
    return lookup


def _owner_label(mid, lookup):
    if mid in lookup:
        return lookup[mid]
    if mid in FORMER_MONDAY_USERS:
        return (None, f'{FORMER_MONDAY_USERS[mid]} (former)')
    return (None, f'Unknown Monday user {mid}')


def parse_contact(item, owner_lookup):
    name = (item.get('name') or '').strip()
    email = (_column(item, monday_client.CONTACTS_COL_EMAIL).get('text') or '').strip()
    phone = (_column(item, monday_client.CONTACTS_COL_PHONE).get('text') or '').strip()
    title = (_column(item, monday_client.CONTACTS_COL_TITLE).get('text') or '').strip()
    company, company_ids = _company(_column(item, monday_client.CONTACTS_COL_COMPANY))
    owner_ids = _owner_ids(_column(item, monday_client.CONTACTS_COL_OWNER))
    owners = [_owner_label(mid, owner_lookup) for mid in owner_ids]
    return {
        'monday_item_id': int(item['id']),
        'name': name[:255],
        'email': email[:255] or None,
        'phone': phone[:64] or None,
        'title': title or None,
        'company': company or None,
        'company_monday_ids': company_ids,
        'owner_monday_ids': owner_ids,
        'owner_user_keys': [k for k, _ in owners if k],
        'owner_names': [n for _, n in owners],
        'monday_group': ((item.get('group') or {}).get('title') or '').strip() or None,
        'placeholder': (not name) or name.lower() in monday_client.PLACEHOLDER_CONTACT_NAMES,
    }


def duplicate_email_report(parsed):
    """Monday items that share an email — report only, never merged."""
    groups = defaultdict(list)
    for p in parsed:
        if p.get('email'):
            groups[p['email'].strip().lower()].append(p)
    out = []
    for email in sorted(groups):
        rows = groups[email]
        if len(rows) < 2:
            continue
        out.append({
            'email': email,
            'items': [{
                'monday_item_id': r['monday_item_id'],
                'name': r['name'] or '(no name)',
                'group': r['monday_group'] or '',
                'placeholder': r['placeholder'],
                'url': monday_client.contact_item_url(r['monday_item_id']),
            } for r in sorted(rows, key=lambda r: r['monday_item_id'])],
        })
    return out


# ── SQL ─────────────────────────────────────────────────────────────────────

_SYNCED = ('name', 'email', 'phone', 'title', 'company', 'company_monday_ids',
           'owner_monday_ids', 'owner_user_keys', 'owner_names', 'monday_group')

UPSERT_SQL = f'''
    INSERT INTO clients (
        monday_item_id, name, email, phone, title, company, company_monday_ids,
        owner_monday_ids, owner_user_keys, owner_names, monday_group,
        source, is_active, added_by, synced_at, updated_at, created_at
    ) VALUES (
        %(monday_item_id)s, %(name)s, %(email)s, %(phone)s, %(title)s, %(company)s,
        %(company_monday_ids)s::bigint[], %(owner_monday_ids)s::text[],
        %(owner_user_keys)s::text[], %(owner_names)s::text[], %(monday_group)s,
        '{SOURCE_MONDAY}', TRUE, 'monday_crm_sync', NOW(), NOW(), NOW()
    )
    ON CONFLICT (monday_item_id) DO UPDATE SET
        {', '.join(f'{c} = EXCLUDED.{c}' for c in _SYNCED)},
        source = '{SOURCE_MONDAY}', is_active = TRUE,
        archived_at = NULL, archived_reason = NULL, updated_at = NOW()
    WHERE ({', '.join(f'clients.{c}' for c in _SYNCED)}, clients.is_active, clients.source)
          IS DISTINCT FROM
          ({', '.join(f'EXCLUDED.{c}' for c in _SYNCED)}, TRUE, '{SOURCE_MONDAY}')
    RETURNING (xmax = 0) AS inserted, is_active
'''

STAMP_SYNCED_SQL = 'UPDATE clients SET synced_at = NOW() WHERE monday_item_id = ANY(%s::bigint[])'

INACTIVATE_SQL = f'''
    UPDATE clients
       SET is_active = FALSE, archived_at = NOW(),
           archived_reason = '{REASON_REMOVED}', updated_at = NOW()
     WHERE source = '{SOURCE_MONDAY}' AND is_active
       AND NOT (monday_item_id = ANY(%s::bigint[]))
    RETURNING id, name, monday_item_id
'''

LEGACY_FILES_SQL = f'''
    SELECT d.id, d.filename, c.id, c.name, LOWER(TRIM(COALESCE(c.email, '')))
      FROM documents d
      JOIN clients c ON c.id = d.log_id
     WHERE d.doc_type = %s AND c.source <> '{SOURCE_MONDAY}'
     ORDER BY c.name, d.id
'''

MONDAY_BY_EMAIL_SQL = f'''
    SELECT id, name FROM clients
     WHERE source = '{SOURCE_MONDAY}' AND is_active
       AND LOWER(TRIM(COALESCE(email, ''))) = %s
'''

MOVE_FILE_SQL = 'UPDATE documents SET log_id = %s WHERE id = %s AND doc_type = %s'

ARCHIVE_LEGACY_SQL = f'''
    UPDATE clients
       SET is_active = FALSE, archived_at = COALESCE(archived_at, NOW()),
           archived_reason = '{REASON_REPLACED}', updated_at = NOW()
     WHERE source <> '{SOURCE_MONDAY}' AND is_active
'''

ACTIVE_MONDAY_COUNT_SQL = f"SELECT COUNT(*) FROM clients WHERE source = '{SOURCE_MONDAY}' AND is_active"


# ── settings (hub_settings, JSONB) ──────────────────────────────────────────

def _read_setting(cur, key):
    cur.execute('SELECT value FROM hub_settings WHERE key = %s', (key,))
    row = cur.fetchone()
    if not row:
        return None
    return _json(row[0]) if not isinstance(row[0], dict) else row[0]


def _write_setting(cur, key, value, by):
    cur.execute(
        '''INSERT INTO hub_settings (key, value, updated_at, updated_by)
           VALUES (%s, %s::jsonb, NOW(), %s)
           ON CONFLICT (key) DO UPDATE
           SET value = EXCLUDED.value, updated_at = NOW(), updated_by = EXCLUDED.updated_by''',
        (key, json.dumps(value), (by or '')[:100]),
    )


def _read_setting_standalone(get_db_fn, key):
    conn = None
    try:
        conn = get_db_fn()
        if not conn:
            return None
        cur = conn.cursor()
        value = _read_setting(cur, key)
        cur.close()
        conn.rollback()
        return value
    except Exception as e:
        print(f'crm sync: reading {key} failed: {e}')
        return None
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def is_initialized(get_db_fn):
    return _read_setting_standalone(get_db_fn, SETTINGS_INITIALIZED) is not None


def load_last_sync(get_db_fn):
    return _read_setting_standalone(get_db_fn, SETTINGS_LAST)


# ── the sync ────────────────────────────────────────────────────────────────

def _move_legacy_files(cur):
    moved, left = [], []
    cur.execute(LEGACY_FILES_SQL, (CLIENT_FILE_DOC_TYPE,))
    for doc_id, filename, old_id, old_name, email in cur.fetchall():
        entry = {'document_id': doc_id, 'filename': filename,
                 'old_contact_id': old_id, 'old_contact': old_name, 'email': email}
        if not email:
            left.append({**entry, 'why': 'old contact has no email'})
            continue
        cur.execute(MONDAY_BY_EMAIL_SQL, (email,))
        targets = cur.fetchall()
        if len(targets) != 1:
            why = ('no Monday contact has that email' if not targets
                   else f'{len(targets)} Monday contacts share that email')
            left.append({**entry, 'why': why})
            continue
        cur.execute(MOVE_FILE_SQL, (targets[0][0], doc_id, CLIENT_FILE_DOC_TYPE))
        moved.append({**entry, 'new_contact_id': targets[0][0], 'new_contact': targets[0][1]})
    return moved, left


def run_sync(get_db_fn, hub_users, triggered_by, apply=True, initial=False,
             fetch_items=None, fetch_users=None, now=None):
    """Mirror the Monday Contacts board into `clients`.

    apply=False is a preview: every statement runs for real inside the
    transaction, so the counts are exactly what an apply would produce, then
    it rolls back. initial=True allows the first run (archive old Hub
    contacts); after that it is a no-op and normal runs do it anyway.

    Returns a dict. `ok` False with `error` for a failure the caller should
    show; `skipped` True with `reason` for a run that deliberately did nothing.
    """
    fetch_items = fetch_items or monday_client.fetch_contacts_board
    fetch_users = fetch_users or monday_client.fetch_monday_users
    now = now or datetime.now(timezone.utc)

    conn = get_db_fn()
    if not conn:
        return {'ok': False, 'error': 'database_unavailable',
                'message': 'The Hub database is not reachable right now.'}
    committed = False
    try:
        cur = conn.cursor()
        cur.execute('SELECT pg_try_advisory_xact_lock(%s)', (LOCK_KEY,))
        if not cur.fetchone()[0]:
            return {'ok': True, 'skipped': True, 'reason': 'already_running',
                    'message': 'A sync is already running. This one was ignored.'}

        initialized = _read_setting(cur, SETTINGS_INITIALIZED) is not None
        if not initialized and not initial:
            return {'ok': False, 'skipped': True, 'reason': 'awaiting_first_sync',
                    'message': 'The first Monday sync has not been applied yet. '
                               'Thomas previews and applies it from the Clients page.'}

        try:
            items = fetch_items()
            monday_users = fetch_users()
        except monday_client.MondayAccessError as e:
            return {'ok': False, 'error': 'monday_access', 'message': str(e)}

        lookup = build_owner_lookup(monday_users, hub_users)
        parsed = [parse_contact(it, lookup) for it in items]
        placeholders = [p for p in parsed if p['placeholder']]
        contacts = [p for p in parsed if not p['placeholder']]

        if not contacts:
            return {'ok': False, 'error': 'empty_board',
                    'message': f'Monday returned {len(items)} items and no real '
                               f'contacts. Nothing was changed.'}

        cur.execute(ACTIVE_MONDAY_COUNT_SQL)
        active_before = cur.fetchone()[0] or 0

        created = updated = unchanged = 0
        for c in contacts:
            params = {k: c[k] for k in ('monday_item_id',) + _SYNCED}
            cur.execute(UPSERT_SQL, params)
            row = cur.fetchone()
            if row is None:
                unchanged += 1
            elif row[0]:
                created += 1
            else:
                updated += 1
        ids = [c['monday_item_id'] for c in contacts]
        cur.execute(STAMP_SYNCED_SQL, (ids,))

        inactivated, skipped_inactivation = [], None
        if active_before and len(contacts) < active_before * INACTIVATION_FLOOR:
            skipped_inactivation = (
                f'Monday returned {len(contacts)} contacts but the Hub has '
                f'{active_before} active. That looks like a partial pull, so no '
                f'contact was marked inactive this run.')
        else:
            cur.execute(INACTIVATE_SQL, (ids,))
            inactivated = [{'id': r[0], 'name': r[1], 'monday_item_id': r[2]}
                           for r in cur.fetchall()]

        files_moved, files_left = _move_legacy_files(cur)
        cur.execute(ARCHIVE_LEGACY_SQL)
        legacy_archived = max(cur.rowcount or 0, 0)

        duplicates = duplicate_email_report(parsed)
        by = triggered_by or 'schedule'
        result = {
            'ok': True,
            'applied': bool(apply),
            'first_sync': not initialized,
            'at': now.isoformat(),
            'by': by,
            'checked': len(items),
            'contacts': len(contacts),
            'created': created,
            'updated': updated,
            'unchanged': unchanged,
            'inactivated': len(inactivated),
            'inactivated_names': [r['name'] for r in inactivated][:50],
            'skipped_inactivation': skipped_inactivation,
            'placeholders': [{'monday_item_id': p['monday_item_id'],
                              'email': p['email'] or '',
                              'url': monday_client.contact_item_url(p['monday_item_id'])}
                             for p in placeholders],
            'duplicates': duplicates,
            'legacy_archived': legacy_archived,
            'files_moved': files_moved,
            'files_left': files_left,
            'owners_unmatched': sorted({n for c in contacts for n in c['owner_names']
                                        if n.endswith('(former)') or n.startswith('Unknown')}),
        }

        if apply:
            _write_setting(cur, SETTINGS_LAST, result, by)
            if not initialized:
                _write_setting(cur, SETTINGS_INITIALIZED,
                               {'at': now.isoformat(), 'by': by,
                                'legacy_archived': legacy_archived,
                                'files_moved': len(files_moved),
                                'files_left': len(files_left)}, by)
            conn.commit()
            committed = True
        return result
    finally:
        if not committed:
            try:
                conn.rollback()  # preview, refusal, or error: nothing persists
            except Exception:
                pass
        try:
            conn.close()
        except Exception:
            pass


# ── labels and email ────────────────────────────────────────────────────────

def by_label(by, hub_users):
    if not by or by == 'schedule':
        return 'the weekly schedule'
    u = (hub_users or {}).get(by) or {}
    return u.get('display') or by


def counts_line(r):
    return (f"{r.get('created', 0)} new · {r.get('updated', 0)} updated · "
            f"{r.get('inactivated', 0)} inactivated · {r.get('unchanged', 0)} unchanged")


def build_summary_email(result, hub_users=None):
    preview = not result.get('applied')
    if result.get('skipped') or not result.get('ok'):
        subject = 'PPS CRM Contact Sync — did not run'
        text = result.get('message') or result.get('reason') or result.get('error') or 'Unknown'
        return subject, text, _html.escape(text)
    head = 'PREVIEW — nothing was written' if preview else 'Applied'
    subject = (f"PPS CRM Contact Sync — {'preview, ' if preview else ''}"
               f"{result['created']} new, {result['updated']} updated, "
               f"{result['inactivated']} inactivated")
    lines = [head, '',
             f"Checked {result['checked']} Monday items ({result['contacts']} contacts).",
             counts_line(result)]
    if result.get('skipped_inactivation'):
        lines += ['', 'SAFETY STOP: ' + result['skipped_inactivation']]
    if result.get('first_sync'):
        lines += ['', f"Old Hub contacts archived: {result['legacy_archived']}",
                  f"Attachments moved to the matching Monday contact: {len(result['files_moved'])}",
                  f"Attachments left on archived contacts: {len(result['files_left'])}"]
        for f in result['files_left']:
            lines.append(f"  - {f['filename']} on {f['old_contact']} ({f['why']})")
    if result.get('owners_unmatched'):
        lines += ['', 'Owners the Hub cannot match to a person: '
                  + ', '.join(result['owners_unmatched'])]
    dups = result.get('duplicates') or []
    lines += ['', f'Possible duplicates in Monday (same email): {len(dups)}']
    for d in dups:
        names = '; '.join(f"{i['name']} ({i['monday_item_id']})" for i in d['items'])
        lines.append(f"  - {d['email']}: {names}")
    ph = result.get('placeholders') or []
    lines += ['', f'"New Contact" placeholders left out of the Hub: {len(ph)}']
    for p in ph:
        lines.append(f"  - {p['url']}" + (f" ({p['email']})" if p['email'] else ''))
    text = '\n'.join(lines)
    return subject, text, '<br>'.join(_html.escape(line) for line in lines)


def run_weekly_crm_sync(get_db_fn, send_email_fn, recipients, hub_users):
    """The cron path. Before the first sync is applied, it previews and emails
    that preview instead of applying — the first apply is Thomas's call."""
    if not is_initialized(get_db_fn):
        result = run_sync(get_db_fn, hub_users, 'schedule', apply=False, initial=True)
        if result.get('ok'):
            result['note'] = 'First sync not applied yet — this is a preview.'
    else:
        result = run_sync(get_db_fn, hub_users, 'schedule', apply=True)
    if result.get('skipped') and result.get('reason') == 'already_running':
        return {**result, 'sent': False}
    subject, text_body, html_body = build_summary_email(result, hub_users)
    sent = send_email_fn(subject, text_body, html_body, recipients)
    return {**result, 'sent': sent}
