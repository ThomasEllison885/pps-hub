"""Weekly sync: new Monday CRM contacts into the Hub's /clients picker.

Insert-only, never updates an existing row — that's what makes "leave
Hub-only contacts untouched" a hard guarantee rather than best-effort.
A Monday contact is skipped whenever it matches an existing clients row
by email (case-insensitive) or, lacking an email, by name.

send_email_fn(subject, text_body, html_body, recipients) -> bool
"""

from __future__ import annotations

import monday_client


def _col_value(column_values, col_id):
    for cv in column_values or []:
        if cv.get('id') == col_id:
            return cv
    return None


def sync_new_contacts(get_db_fn):
    items = monday_client.fetch_contacts_items()

    conn = get_db_fn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT LOWER(email) FROM clients WHERE email IS NOT NULL AND email != ''")
        existing_emails = {r[0] for r in cur.fetchall()}
        cur.execute('SELECT LOWER(name) FROM clients')
        existing_names = {r[0] for r in cur.fetchall()}

        added = 0
        skipped_existing = 0
        skipped_placeholder = 0
        added_names = []

        for it in items:
            name = (it.get('name') or '').strip()
            name_key = name.lower()

            if not name or name_key in monday_client.PLACEHOLDER_CONTACT_NAMES:
                skipped_placeholder += 1
                continue

            col = it.get('column_values') or []
            email_cv = _col_value(col, monday_client.CONTACTS_COL_EMAIL)
            phone_cv = _col_value(col, monday_client.CONTACTS_COL_PHONE)
            email = ((email_cv or {}).get('text') or '').strip()
            phone = ((phone_cv or {}).get('text') or '').strip()

            if email:
                if email.lower() in existing_emails:
                    skipped_existing += 1
                    continue
            elif name_key in existing_names:
                skipped_existing += 1
                continue

            notes = f'Phone: {phone} (synced from Monday CRM)' if phone else 'Synced from Monday CRM'
            cur.execute('''
                INSERT INTO clients (name, email, company, property_name, address, notes, added_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (name, email, '', '', '', notes, 'monday_crm_sync'))
            added += 1
            added_names.append(name)

            if email:
                existing_emails.add(email.lower())
            existing_names.add(name_key)

        conn.commit()
        cur.close()
        return {
            'added': added,
            'skipped_existing': skipped_existing,
            'skipped_placeholder': skipped_placeholder,
            'checked': len(items),
            'added_names': added_names,
        }
    finally:
        conn.close()


def _build_summary_email(result):
    subject = f"PPS CRM Contact Sync — {result['added']} new contact(s)"
    lines = [
        f"Checked {result['checked']} Monday CRM contacts.",
        f"Added: {result['added']}",
        f"Already in Hub (skipped): {result['skipped_existing']}",
        f"Placeholder-named (skipped): {result['skipped_placeholder']}",
    ]
    if result['added_names']:
        lines.append('')
        lines.append('New contacts added:')
        lines.extend(f'  - {n}' for n in result['added_names'])
    text_body = '\n'.join(lines)
    html_body = '<br>'.join(lines)
    return subject, text_body, html_body


def run_weekly_crm_sync(get_db_fn, send_email_fn, recipients):
    result = sync_new_contacts(get_db_fn)
    subject, text_body, html_body = _build_summary_email(result)
    sent = send_email_fn(subject, text_body, html_body, recipients)
    return {'ok': True, 'sent': sent, **result}
