"""Estimates board: new-assignment notification + daily reminder.

Standalone feature reading Monday's Estimates board directly — deliberately
NOT a Pipeline Board change (Thomas, 2026-08-10: keep Pipeline Board's
existing behavior untouched). "Sales Lead" = PSC, "Production Lead" = PM.

Two things happen on every run:
  1. Assignment notification — a person gets emailed the first time we see
     an item that already has them assigned (assigned-at-creation, per
     Thomas's definition — not a later reassignment-change event).
  2. Daily reminder — everyone with at least one currently-open item gets
     one email listing all of them, every day the cron runs.

Recipients are resolved directly from Monday's own `users` email field
(monday_client.fetch_monday_users) — no cross-reference against Hub's
USERS dict, avoiding a second stale-mapping problem.

send_email_fn(subject, text_body, html_body, recipients) -> bool
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

import monday_client


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
    if not text_val:
        return None
    try:
        return datetime.strptime(text_val.strip(), '%Y-%m-%d').date()
    except (ValueError, AttributeError):
        return None


def _ids_to_text(ids):
    return ','.join(ids) if ids else ''


def _text_to_ids(text):
    return [x for x in (text or '').split(',') if x]


def run_daily_estimate_check(get_db_fn, send_email_fn):
    today = date.today()
    conn = get_db_fn()
    try:
        cur = conn.cursor()
        init_tables(cur)
        conn.commit()

        items = monday_client.fetch_estimates_items()
        person_emails = monday_client.fetch_monday_users()

        # person_id -> list of open items assigned to them (for the daily reminder)
        open_items_by_person = defaultdict(list)
        # person_id -> list of items newly assigned to them this run
        new_assignments_by_person = defaultdict(list)

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

            all_assignees = set(sales_lead_ids) | set(production_lead_ids)
            for pid in all_assignees:
                open_items_by_person[pid].append({
                    'name': name, 'group': group_name, 'due_by': due_by, 'priority': priority,
                })

            cur.execute(
                'SELECT monday_item_id FROM estimate_assignment_snapshot WHERE monday_item_id = %s',
                (item_id,),
            )
            is_new = cur.fetchone() is None
            if is_new and all_assignees:
                for pid in all_assignees:
                    new_assignments_by_person[pid].append({
                        'name': name, 'group': group_name, 'due_by': due_by, 'priority': priority,
                    })

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

        # Prune snapshot rows for items no longer in an open group (completed/
        # archived/removed) — same self-cleaning pattern as the TP compliance
        # snapshot. Guarded on a non-empty fetch.
        if items:
            current_ids = tuple(str(it['id']) for it in items)
            cur.execute(
                'DELETE FROM estimate_assignment_snapshot WHERE monday_item_id NOT IN %s',
                (current_ids,),
            )

        conn.commit()
        cur.close()

        assignment_emails_sent = 0
        for pid, new_items in new_assignments_by_person.items():
            email = person_emails.get(pid)
            if not email:
                continue
            subject, text_body, html_body = _build_assignment_email(new_items)
            if send_email_fn(subject, text_body, html_body, [email]):
                assignment_emails_sent += 1

        reminder_emails_sent = 0
        for pid, open_items in open_items_by_person.items():
            email = person_emails.get(pid)
            if not email:
                continue
            subject, text_body, html_body = _build_reminder_email(open_items, today)
            if send_email_fn(subject, text_body, html_body, [email]):
                reminder_emails_sent += 1

        return {
            'ok': True,
            'checked': len(items),
            'new_assignments': sum(len(v) for v in new_assignments_by_person.values()),
            'assignment_emails_sent': assignment_emails_sent,
            'reminder_emails_sent': reminder_emails_sent,
        }
    finally:
        conn.close()


def _fmt_date(d):
    return d.strftime('%m/%d/%Y') if d else 'no due date'


def _build_assignment_email(new_items):
    subject = f"You've been assigned {len(new_items)} new estimate task(s)"
    lines = [f"- {it['name']} ({it['group']}) — due {_fmt_date(it['due_by'])}, priority {it['priority'] or 'unset'}"
              for it in new_items]
    text_body = subject + '\n\n' + '\n'.join(lines)
    html_body = f'<p>{subject}</p><ul>' + ''.join(f'<li>{l[2:]}</li>' for l in lines) + '</ul>'
    return subject, text_body, html_body


def _build_reminder_email(open_items, today):
    open_items = sorted(open_items, key=lambda it: it['due_by'] or date.max)
    subject = f"Estimates on your plate — {today.strftime('%A, %B %d')} ({len(open_items)} open)"
    lines = [f"- {it['name']} ({it['group']}) — due {_fmt_date(it['due_by'])}, priority {it['priority'] or 'unset'}"
              for it in open_items]
    text_body = subject + '\n\n' + '\n'.join(lines)
    html_body = f'<p>{subject}</p><ul>' + ''.join(f'<li>{l[2:]}</li>' for l in lines) + '</ul>'
    return subject, text_body, html_body
