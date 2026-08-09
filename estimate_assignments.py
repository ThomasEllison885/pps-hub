"""Estimates board: new-assignment notification + daily reminder.

Standalone feature reading Monday's Estimates board directly — deliberately
NOT a Pipeline Board change (Thomas, 2026-08-10: keep Pipeline Board's
existing behavior untouched). "Sales Lead" = PSC, "Production Lead" = PM.

Three things happen on every run:
  1. Assignment notification — a person gets emailed the first time we see
     an item that already has them assigned (assigned-at-creation, per
     Thomas's definition — not a later reassignment-change event).
  2. Daily reminder — everyone with at least one currently-open item, or
     an item completed since yesterday, gets ONE email today covering
     both — a "Completed" section (praise) above a "Still open" section.
     Completion praise is intentionally folded into this single daily
     email, not a separate notification per finished task (Thomas,
     2026-08-10).
  3. Each assignment/reminder email CCs the counterpart (PSC sees PM's
     email and vice versa, per item) and closes with a short rotating
     stoic/work-related line.

Recipients are resolved directly from Monday's own `users` email field
(monday_client.fetch_monday_users) — no cross-reference against Hub's
USERS dict, avoiding a second stale-mapping problem. `_send_smtp_email`
has no separate CC header, so "CC" here means the counterpart's email is
simply added to the same `recipients` list — same practical outcome
(both people see the email and each other on it).

send_email_fn(subject, text_body, html_body, recipients) -> bool
"""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import date, datetime

import monday_client

STOIC_QUOTES = [
    "You have power over your mind — not outside events. Realize this, and you will find strength.",
    "Waste no more time arguing what a good task looks like. Be one.",
    "The impediment to action advances action. What stands in the way becomes the way.",
    "First say to yourself what you would be; and then do what you have to do.",
    "It is not that we have a short time to live, but that we waste a lot of it.",
    "Well-being is realized by small steps, but is truly no small thing.",
    "How long are you going to wait before you demand the best for yourself?",
    "We suffer more often in imagination than in reality.",
    "The obstacle on the path becomes the path.",
    "Confine yourself to the present.",
    "No man is free who is not master of himself.",
    "Difficulties strengthen the mind, as labor does the body.",
    "He who fears death will never do anything worthy of a living man.",
    "Begin at once to live, and count each separate day as a separate life.",
    "Man conquers the world by conquering himself.",
    "The best revenge is to be unlike him who performed the injury.",
    "Don't explain your philosophy. Embody it.",
    "It's not what happens to you, but how you react to it that matters.",
    "Every new beginning comes from some other beginning's end.",
    "Associate with people who are likely to improve you.",
    "The whole future lies in uncertainty: live immediately.",
    "Luck is what happens when preparation meets opportunity.",
    "He suffers more than necessary who suffers before it is necessary.",
    "What we do now echoes in the work still to come.",
    "Discipline equals freedom.",
]


def init_tables(cur):
    cur.execute('''
        CREATE TABLE IF NOT EXISTS estimate_assignment_snapshot (
            monday_item_id VARCHAR(50) PRIMARY KEY,
            name VARCHAR(255),
            group_name VARCHAR(100),
            sales_lead_ids TEXT,
            production_lead_ids TEXT,
            due_by DATE,
            priority VARCHAR(100),
            first_seen_at TIMESTAMP DEFAULT NOW(),
            last_seen_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    ''')


def _col_value(column_values, col_id):
    for cv in column_values or []:
        if cv.get('id') == col_id:
            return cv
    return None


def _parse_monday_date(text_val):
    """Estimates' Due By column often carries a time suffix ("2026-02-24
    09:00") even though we only care about the date — confirmed live
    2026-08-10, every populated Due By on the real board had one. A
    date-only column can also come back bare, so try both."""
    if not text_val:
        return None
    text_val = text_val.strip()
    for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(text_val, fmt).date()
        except ValueError:
            continue
    return None


def _ids_to_text(ids):
    return ','.join(ids) if ids else ''


def run_daily_estimate_check(get_db_fn, send_email_fn):
    today = date.today()
    conn = get_db_fn()
    try:
        cur = conn.cursor()
        init_tables(cur)
        conn.commit()

        fetch_groups = monday_client.ESTIMATES_OPEN_GROUPS + (monday_client.ESTIMATES_COMPLETED_GROUP,)
        items = monday_client.fetch_estimates_items(groups=fetch_groups)
        person_emails = monday_client.fetch_monday_users()

        # person_id -> list of open items assigned to them (for the daily reminder)
        open_items_by_person = defaultdict(list)
        # person_id -> list of items newly assigned to them this run
        new_assignments_by_person = defaultdict(list)
        # person_id -> list of items completed since yesterday
        completed_by_person = defaultdict(list)
        # item_id -> set of counterpart person_ids, keyed by "the other role" —
        # built alongside so email CC lists can be assembled per recipient
        item_assignees = {}

        completed_ids_to_remove = []

        for it in items:
            col = it.get('column_values') or []
            item_id = it['id']
            name = it.get('name') or ''
            group_name = (it.get('group') or {}).get('title') or ''

            sales_cv = _col_value(col, monday_client.ESTIMATES_COL_SALES_LEAD)
            prod_cv = _col_value(col, monday_client.ESTIMATES_COL_PRODUCTION_LEAD)
            due_cv = _col_value(col, monday_client.ESTIMATES_COL_DUE_BY)
            priority_cv = _col_value(col, monday_client.ESTIMATES_COL_PRIORITY)

            sales_lead_ids = monday_client.parse_people_column(sales_cv) if sales_cv else []
            production_lead_ids = monday_client.parse_people_column(prod_cv) if prod_cv else []
            due_by = _parse_monday_date(due_cv['text'] if due_cv else None)
            priority = (priority_cv['text'] if priority_cv else '') or ''

            item_assignees[item_id] = {'sales': set(sales_lead_ids), 'production': set(production_lead_ids)}
            item_summary = {
                'item_id': item_id, 'name': name, 'group': group_name,
                'due_by': due_by, 'priority': priority,
            }

            cur.execute(
                'SELECT group_name FROM estimate_assignment_snapshot WHERE monday_item_id = %s',
                (item_id,),
            )
            row = cur.fetchone()
            prev_group = row[0] if row else None
            is_new = row is None
            all_assignees = set(sales_lead_ids) | set(production_lead_ids)

            if group_name == monday_client.ESTIMATES_COMPLETED_GROUP:
                if prev_group in monday_client.ESTIMATES_OPEN_GROUPS:
                    for pid in all_assignees:
                        completed_by_person[pid].append(item_summary)
                completed_ids_to_remove.append(item_id)
                continue

            # Still an open item.
            for pid in all_assignees:
                open_items_by_person[pid].append(item_summary)
            if is_new and all_assignees:
                for pid in all_assignees:
                    new_assignments_by_person[pid].append(item_summary)

            cur.execute('''
                INSERT INTO estimate_assignment_snapshot
                    (monday_item_id, name, group_name, sales_lead_ids, production_lead_ids,
                     due_by, priority, last_seen_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                ON CONFLICT (monday_item_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    group_name = EXCLUDED.group_name,
                    sales_lead_ids = EXCLUDED.sales_lead_ids,
                    production_lead_ids = EXCLUDED.production_lead_ids,
                    due_by = EXCLUDED.due_by,
                    priority = EXCLUDED.priority,
                    last_seen_at = NOW(),
                    updated_at = NOW()
            ''', (item_id, name, group_name, _ids_to_text(sales_lead_ids),
                  _ids_to_text(production_lead_ids), due_by, priority))

        # Prune snapshot rows for items no longer fetched at all (archived or
        # removed from the board) — same self-cleaning pattern as the TP
        # compliance snapshot. Guarded on a non-empty fetch.
        if items:
            current_ids = tuple(str(it['id']) for it in items)
            cur.execute(
                'DELETE FROM estimate_assignment_snapshot WHERE monday_item_id NOT IN %s',
                (current_ids,),
            )
        # Completed items are done being tracked once credited — remove them
        # explicitly so they don't linger and can't be double-credited.
        if completed_ids_to_remove:
            cur.execute(
                'DELETE FROM estimate_assignment_snapshot WHERE monday_item_id = ANY(%s)',
                (completed_ids_to_remove,),
            )

        conn.commit()
        cur.close()

        def _counterparts_for(items_list, person_id):
            counterpart_ids = set()
            for it in items_list:
                assignees = item_assignees.get(it['item_id'], {'sales': set(), 'production': set()})
                if person_id in assignees['sales']:
                    counterpart_ids |= assignees['production']
                if person_id in assignees['production']:
                    counterpart_ids |= assignees['sales']
            counterpart_ids.discard(person_id)
            return [person_emails[pid] for pid in counterpart_ids if person_emails.get(pid)]

        assignment_emails_sent = 0
        for pid, new_items in new_assignments_by_person.items():
            email = person_emails.get(pid)
            if not email:
                continue
            recipients = [email] + [e for e in _counterparts_for(new_items, pid) if e != email]
            subject, text_body, html_body = _build_assignment_email(new_items)
            if send_email_fn(subject, text_body, html_body, recipients):
                assignment_emails_sent += 1

        reminder_emails_sent = 0
        all_reminder_people = set(open_items_by_person) | set(completed_by_person)
        for pid in all_reminder_people:
            email = person_emails.get(pid)
            if not email:
                continue
            open_items = open_items_by_person.get(pid, [])
            completed_items = completed_by_person.get(pid, [])
            recipients = [email] + [
                e for e in _counterparts_for(open_items + completed_items, pid) if e != email
            ]
            subject, text_body, html_body = _build_reminder_email(open_items, completed_items, today)
            if send_email_fn(subject, text_body, html_body, recipients):
                reminder_emails_sent += 1

        return {
            'ok': True,
            'checked': len(items),
            'new_assignments': sum(len(v) for v in new_assignments_by_person.values()),
            'completed': sum(len(v) for v in completed_by_person.values()),
            'assignment_emails_sent': assignment_emails_sent,
            'reminder_emails_sent': reminder_emails_sent,
        }
    finally:
        conn.close()


def _fmt_date(d):
    return d.strftime('%m/%d/%Y') if d else 'no due date'


def _quote():
    return random.choice(STOIC_QUOTES)


def _item_line(it):
    return f"{it['name']} ({it['group']}) — due {_fmt_date(it['due_by'])}, priority {it['priority'] or 'unset'}"


def _build_assignment_email(new_items):
    subject = f"You've been assigned {len(new_items)} new estimate task(s)"
    lines = [_item_line(it) for it in new_items]
    quote = _quote()
    text_body = subject + '\n\n' + '\n'.join(f'- {l}' for l in lines) + f'\n\n"{quote}"'
    html_body = (
        f'<p>{subject}</p><ul>' + ''.join(f'<li>{l}</li>' for l in lines) + '</ul>'
        f'<p style="color:#64748b;font-style:italic;">"{quote}"</p>'
    )
    return subject, text_body, html_body


def _build_reminder_email(open_items, completed_items, today):
    open_items = sorted(open_items, key=lambda it: it['due_by'] or date.max)
    subject_bits = []
    if completed_items:
        subject_bits.append(f'{len(completed_items)} completed')
    if open_items:
        subject_bits.append(f'{len(open_items)} open')
    subject = f"Estimates update — {today.strftime('%A, %B %d')} ({', '.join(subject_bits) or 'nothing pending'})"

    quote = _quote()
    text_parts = [subject, '']
    html_parts = [f'<p>{subject}</p>']

    if completed_items:
        text_parts.append(f'COMPLETED ({len(completed_items)}) — nice work:')
        text_parts.extend(f'- {_item_line(it)}' for it in completed_items)
        text_parts.append('')
        html_parts.append(f'<h3 style="color:#166534;">Completed ({len(completed_items)}) — nice work</h3><ul>')
        html_parts.extend(f'<li>{_item_line(it)}</li>' for it in completed_items)
        html_parts.append('</ul>')

    if open_items:
        text_parts.append(f'STILL OPEN ({len(open_items)}):')
        text_parts.extend(f'- {_item_line(it)}' for it in open_items)
        html_parts.append(f'<h3>Still open ({len(open_items)})</h3><ul>')
        html_parts.extend(f'<li>{_item_line(it)}</li>' for it in open_items)
        html_parts.append('</ul>')

    text_parts.append('')
    text_parts.append(f'"{quote}"')
    html_parts.append(f'<p style="color:#64748b;font-style:italic;">"{quote}"</p>')

    return subject, '\n'.join(text_parts), '\n'.join(html_parts)
