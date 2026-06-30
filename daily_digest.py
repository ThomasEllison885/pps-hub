"""Nightly Eastern-time activity digest for hub administrators."""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timedelta, time, timezone
from html import escape
from zoneinfo import ZoneInfo

from psc_training_data import PSC_TRAINING_META, get_training_curriculum

ET = ZoneInfo('America/New_York')


def _digest_enabled():
    return os.environ.get('DAILY_DIGEST_ENABLED', 'true').strip().lower() in ('1', 'true', 'yes')


def _digest_exclude_keys():
    raw = os.environ.get('DAILY_DIGEST_EXCLUDE', 'thomas_ellison').strip()
    return {k.strip() for k in raw.split(',') if k.strip()}


def digest_recipients():
    raw = (
        os.environ.get('DAILY_DIGEST_EMAIL', '').strip()
        or os.environ.get('HUB_NOTIFY_EMAIL', 'thomas@purepropsolutions.com')
    )
    return [e.strip() for e in raw.split(',') if e.strip()]


def eastern_now():
    return datetime.now(ET)


def should_run_scheduled():
    """True during midnight–1am US/Eastern (hourly UTC cron; 1am allows one retry)."""
    return eastern_now().hour in (0, 1)


def report_date_for_run(force=False, date_override=None):
    """Calendar day (Eastern) the digest summarizes — the day that just ended."""
    if date_override:
        return date_override
    return (eastern_now() - timedelta(days=1)).date()


def eastern_day_bounds_utc_naive(day_date):
    """Return naive UTC timestamps for a full Eastern calendar day."""
    start = datetime.combine(day_date, time.min, tzinfo=ET)
    end = start + timedelta(days=1)
    return (
        start.astimezone(timezone.utc).replace(tzinfo=None),
        end.astimezone(timezone.utc).replace(tzinfo=None),
    )


def _display_name(users, user_key, fallback=''):
    user = users.get(user_key, {})
    return user.get('display') or fallback or user_key.replace('_', ' ').title()


def _time_label(dt):
    if not dt or not hasattr(dt, 'strftime'):
        return ''
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone(ET)
    except Exception:
        local = dt
    return local.strftime('%I:%M %p').lstrip('0')


def _week_label(week_num):
    if week_num is None:
        return ''
    if week_num == 0:
        onboarding, _, _, _, _ = get_training_curriculum()
        return onboarding.get('title', 'Week 0')
    _, weeks, _, _, _ = get_training_curriculum()
    for w in weeks:
        if w.get('week') == week_num:
            return f"Week {week_num} · {w.get('topic', '')}"
    return f'Week {week_num}'


def _load_sent_date(get_db):
    try:
        conn = get_db()
        if not conn:
            return None
        cur = conn.cursor()
        cur.execute("SELECT value FROM hub_settings WHERE key = 'daily_digest_sent'")
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return None
        val = row[0]
        if isinstance(val, dict):
            return val.get('date')
        if isinstance(val, str):
            import json
            try:
                return json.loads(val).get('date')
            except Exception:
                return val
        return None
    except Exception:
        return None


def _load_last_run(get_db):
    try:
        conn = get_db()
        if not conn:
            return None
        cur = conn.cursor()
        cur.execute("SELECT value FROM hub_settings WHERE key = 'daily_digest_last_run'")
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return None
        val = row[0]
        if isinstance(val, dict):
            return val
        if isinstance(val, str):
            import json
            try:
                return json.loads(val)
            except Exception:
                return {'raw': val}
        return None
    except Exception:
        return None


def _record_last_run(get_db, result):
    import json
    try:
        conn = get_db()
        if not conn:
            return
        cur = conn.cursor()
        payload = {
            'at': eastern_now().isoformat(),
            'report_date': result.get('report_date'),
            'skipped': result.get('skipped'),
            'reason': result.get('reason'),
            'sent': result.get('sent'),
            'email_failed': result.get('email_failed'),
            'item_count': result.get('item_count', 0),
            'recipients': result.get('recipients'),
            'warning': result.get('warning'),
            'error': result.get('error'),
        }
        cur.execute(
            '''INSERT INTO hub_settings (key, value, updated_at, updated_by)
               VALUES ('daily_digest_last_run', %s::jsonb, NOW(), 'cron')
               ON CONFLICT (key) DO UPDATE
               SET value = EXCLUDED.value, updated_at = NOW(), updated_by = 'cron' ''',
            (json.dumps(payload),),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f'Daily digest record last run error: {e}')


def _mark_sent(get_db, report_date):
    import json
    try:
        conn = get_db()
        if not conn:
            return
        cur = conn.cursor()
        cur.execute(
            '''INSERT INTO hub_settings (key, value, updated_at, updated_by)
               VALUES ('daily_digest_sent', %s::jsonb, NOW(), 'cron')
               ON CONFLICT (key) DO UPDATE
               SET value = EXCLUDED.value, updated_at = NOW(), updated_by = 'cron' ''',
            (json.dumps({'date': report_date.isoformat()}),),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f'Daily digest mark sent error: {e}')


def _item(user_key, display_name, kind, kind_label, title, meta, at, extra=''):
    return {
        'user_key': user_key,
        'display_name': display_name,
        'kind': kind,
        'kind_label': kind_label,
        'title': title or 'Unnamed',
        'meta': meta or '',
        'extra': extra or '',
        'at': at,
        'time_str': _time_label(at),
    }


def collect_digest_items(get_db, users, exclude, report_date, format_template_label):
    """Gather all team activity for one Eastern calendar day."""
    start, end = eastern_day_bounds_utc_naive(report_date)
    exclude_list = sorted(exclude)
    items = []
    counts = defaultdict(int)

    def add(item):
        items.append(item)
        counts[item['kind']] += 1

    try:
        conn = get_db()
        if not conn:
            return [], {}, start, end
        cur = conn.cursor()
        ex_sql = ' AND generated_by NOT IN %s' if exclude_list else ''
        ex_args = (tuple(exclude_list),) if exclude_list else ()

        cur.execute(
            f'''SELECT generated_by, consultant_name, property_name, client_name,
                      property_type, template_type, generated_at
               FROM proposal_log
               WHERE generated_at >= %s AND generated_at < %s{ex_sql}
               ORDER BY generated_at''',
            (start, end, *ex_args),
        )
        for r in cur.fetchall():
            title = r[2] or r[3] or 'Unnamed'
            meta = ' · '.join(x for x in [
                format_template_label(r[5]),
                r[4],
                r[1],
            ] if x and x != '—')
            add(_item(r[0], _display_name(users, r[0]), 'proposal', 'Proposal', title, meta, r[6]))

        cur.execute(
            f'''SELECT generated_by, client_name, property_name, proj_type, pm_name, generated_at
               FROM ppm_log
               WHERE generated_at >= %s AND generated_at < %s{ex_sql}
               ORDER BY generated_at''',
            (start, end, *ex_args),
        )
        for r in cur.fetchall():
            title = r[1] or r[2] or 'Unnamed'
            meta = ' · '.join(x for x in [r[3], r[4]] if x)
            add(_item(r[0], _display_name(users, r[0]), 'ppm', 'PPM', title, meta, r[5]))

        cur.execute(
            f'''SELECT generated_by, property_name, language, pm_name, consultant_name, generated_at
               FROM subscope_log
               WHERE generated_at >= %s AND generated_at < %s{ex_sql}
               ORDER BY generated_at''',
            (start, end, *ex_args),
        )
        for r in cur.fetchall():
            lang = (r[2] or '').title()
            meta = ' · '.join(x for x in [lang, r[4], f'PM: {r[3]}' if r[3] else ''] if x)
            add(_item(r[0], _display_name(users, r[0]), 'tps', 'TPS', r[1], meta, r[5]))

        user_ex_sql = ' AND user_key NOT IN %s' if exclude_list else ''

        cur.execute(
            f'''SELECT generated_by, display_name, property_name, visit_date, overall_status, generated_at
               FROM site_visit_log
               WHERE generated_at >= %s AND generated_at < %s{ex_sql}
               ORDER BY generated_at''',
            (start, end, *ex_args),
        )
        for r in cur.fetchall():
            meta = ' · '.join(x for x in [r[3], r[4]] if x)
            add(_item(r[0], r[1] or _display_name(users, r[0]), 'site_visit', 'Site visit', r[2], meta, r[5]))

        cur.execute(
            f'''SELECT generated_by, display_name, property_name, building_count, siding_type,
                      summary_meta, generated_at
               FROM siding_estimate_log
               WHERE generated_at >= %s AND generated_at < %s{ex_sql}
               ORDER BY generated_at''',
            (start, end, *ex_args),
        )
        for r in cur.fetchall():
            meta = r[5] or ' · '.join(x for x in [
                f"{r[3] or 1} building{'s' if (r[3] or 1) != 1 else ''}",
                r[4],
            ] if x)
            add(_item(r[0], r[1] or _display_name(users, r[0]), 'siding', 'Siding estimate', r[2], meta, r[6]))

        cur.execute(
            f'''SELECT generated_by, display_name, property_name, report_type, summary_meta, generated_at
               FROM roofing_estimate_log
               WHERE generated_at >= %s AND generated_at < %s{ex_sql}
               ORDER BY generated_at''',
            (start, end, *ex_args),
        )
        for r in cur.fetchall():
            meta = r[4] or (r[3] or 'report')
            add(_item(r[0], r[1] or _display_name(users, r[0]), 'roofing', 'Roofing estimate', r[2], meta, r[5]))

        cur.execute(
            f'''SELECT generated_by, display_name, property_name, gutter_lf, summary_meta, generated_at
               FROM gutter_estimate_log
               WHERE generated_at >= %s AND generated_at < %s{ex_sql}
               ORDER BY generated_at''',
            (start, end, *ex_args),
        )
        for r in cur.fetchall():
            meta = r[4] or (f'{float(r[3] or 0):.0f} LF' if r[3] is not None else '')
            add(_item(r[0], r[1] or _display_name(users, r[0]), 'gutter', 'Gutter estimate', r[2], meta, r[5]))

        cur.execute(
            f'''SELECT generated_by, display_name, property_name, line_count, one_coat_bid,
                      summary_meta, generated_at
               FROM painting_estimate_log
               WHERE generated_at >= %s AND generated_at < %s{ex_sql}
               ORDER BY generated_at''',
            (start, end, *ex_args),
        )
        for r in cur.fetchall():
            if r[5]:
                meta = r[5]
            else:
                parts = []
                if r[3]:
                    parts.append(f'{r[3]} lines')
                if r[4]:
                    parts.append(f'${float(r[4]):,.0f} 1-coat')
                meta = ' · '.join(parts)
            add(_item(r[0], r[1] or _display_name(users, r[0]), 'painting', 'Painting estimate', r[2], meta, r[6]))

        cur.execute(
            f'''SELECT user_key, display_name, message, submitted_at
               FROM feedback
               WHERE submitted_at >= %s AND submitted_at < %s{user_ex_sql}
               ORDER BY submitted_at''',
            (start, end, *ex_args),
        )
        for r in cur.fetchall():
            snippet = (r[2] or '').strip()
            if len(snippet) > 120:
                snippet = snippet[:117] + '…'
            add(_item(r[0], r[1] or _display_name(users, r[0]), 'feedback', 'Feedback', snippet, '', r[3]))

        cur.execute(
            f'''SELECT user_key, display_name, property_name, user_notes, submitted_at
               FROM proposal_diffs
               WHERE submitted_at >= %s AND submitted_at < %s{user_ex_sql}
               ORDER BY submitted_at''',
            (start, end, *ex_args),
        )
        for r in cur.fetchall():
            notes = (r[3] or '').strip()
            if len(notes) > 80:
                notes = notes[:77] + '…'
            add(_item(r[0], r[1] or _display_name(users, r[0]), 'comparison', 'Proposal comparison', r[2], notes, r[4]))

        cur.execute(
            f'''SELECT user_key, display_name, message, week_num, submitted_at
               FROM psc_training_feedback
               WHERE submitted_at >= %s AND submitted_at < %s{user_ex_sql}
               ORDER BY submitted_at''',
            (start, end, *ex_args),
        )
        for r in cur.fetchall():
            snippet = (r[2] or '').strip()
            if len(snippet) > 100:
                snippet = snippet[:97] + '…'
            meta = _week_label(r[3])
            add(_item(r[0], r[1] or _display_name(users, r[0]), 'psc_feedback', 'PSC feedback', snippet, meta, r[4]))

        cur.execute(
            f'''SELECT user_key, COUNT(*) AS n, MAX(completed_at) AS last_at
               FROM psc_training_progress
               WHERE completed = TRUE
                 AND completed_at >= %s AND completed_at < %s{user_ex_sql}
               GROUP BY user_key''',
            (start, end, *ex_args),
        )
        for r in cur.fetchall():
            n = r[1] or 0
            add(_item(
                r[0], _display_name(users, r[0]), 'psc_progress', 'PSC training',
                f'{n} checklist item{"s" if n != 1 else ""} completed', '', r[2],
            ))

        cur.execute(
            f'''SELECT user_key, week_num, updated_at
               FROM psc_training_notes
               WHERE updated_at >= %s AND updated_at < %s{user_ex_sql}
               ORDER BY updated_at''',
            (start, end, *ex_args),
        )
        for r in cur.fetchall():
            add(_item(
                r[0], _display_name(users, r[0]), 'psc_notes', 'PSC notes',
                f'{_week_label(r[1])} notes updated', '', r[2],
            ))

        cur.execute(
            f'''SELECT user_key, week_num, signed_by, signed_at
               FROM psc_training_manager_signoffs
               WHERE signed_at >= %s AND signed_at < %s{user_ex_sql}
               ORDER BY signed_at''',
            (start, end, *ex_args),
        )
        for r in cur.fetchall():
            signer = _display_name(users, r[2], r[2])
            add(_item(
                r[0], _display_name(users, r[0]), 'psc_signoff', 'PSC sign-off',
                f'{_week_label(r[1])} signed', f'by {signer}', r[3],
            ))

        cur.execute(
            f'''SELECT user_key, enrolled_by, enrolled_at
               FROM psc_training_enrollment
               WHERE enrolled_at >= %s AND enrolled_at < %s{user_ex_sql}
               ORDER BY enrolled_at''',
            (start, end, *ex_args),
        )
        for r in cur.fetchall():
            by = _display_name(users, r[1], r[1]) if r[1] else ''
            add(_item(
                r[0], _display_name(users, r[0]), 'psc_enrolled', 'PSC enrolled',
                PSC_TRAINING_META.get('title', 'PSC Training'), f'enrolled by {by}' if by else '', r[2],
            ))

        cur.close()
        conn.close()
    except Exception as e:
        print(f'Daily digest collect error: {e}')
        import traceback
        traceback.print_exc()

    return items, dict(counts), start, end


def _kind_totals(counts):
    labels = [
        ('proposal', 'Proposals'),
        ('ppm', 'PPMs'),
        ('tps', 'TPS Scopes'),
        ('site_visit', 'Site visits'),
        ('siding', 'Siding estimates'),
        ('roofing', 'Roofing estimates'),
        ('gutter', 'Gutter estimates'),
        ('painting', 'Painting estimates'),
        ('feedback', 'Feedback'),
        ('comparison', 'Comparisons'),
        ('psc_feedback', 'PSC feedback'),
        ('psc_progress', 'PSC progress'),
        ('psc_notes', 'PSC notes'),
        ('psc_signoff', 'PSC sign-offs'),
        ('psc_enrolled', 'PSC enrollments'),
    ]
    lines = []
    for key, label in labels:
        n = counts.get(key, 0)
        if n:
            lines.append((label, n))
    return lines


def build_digest_email(report_date, items, counts, users, exclude):
    """Return (subject, text_body, html_body)."""
    people = defaultdict(list)
    for it in items:
        people[it['display_name']].append(it)

    day_label = report_date.strftime('%A, %b %d, %Y')
    total = len(items)
    person_count = len(people)
    if total == 0:
        subject = f'PPS Hub Daily Digest — {day_label} (no team activity)'
    else:
        subject = f'PPS Hub Daily Digest — {day_label} ({total} activit{"y" if total == 1 else "ies"})'

    lines = [
        'PPS Hub · Daily Team Activity',
        day_label,
    ]
    if total == 0:
        lines.append('No team activity recorded yesterday (your own activity is excluded).')
    else:
        lines.append(f'{total} items from {person_count} people (excluding your activity)')
    lines.extend(['', 'AT A GLANCE'])
    kind_totals = _kind_totals(counts)
    if kind_totals:
        for label, n in kind_totals:
            lines.append(f'  {label}: {n}')
    else:
        lines.append('  (none)')
    lines.extend(['', 'BY PERSON'])
    if not people:
        lines.append('  (no activity)')

    for name in sorted(people.keys()):
        person_items = people[name]
        lines.append(f'{name} ({len(person_items)})')
        for it in person_items:
            meta = f' · {it["meta"]}' if it['meta'] else ''
            extra = f' · {it["extra"]}' if it['extra'] else ''
            ts = f' · {it["time_str"]}' if it['time_str'] else ''
            if it['kind'] in ('feedback', 'psc_feedback'):
                lines.append(f'  {it["kind_label"]}: {it["title"]}{meta}{ts}')
            else:
                lines.append(f'  {it["kind_label"]} · {it["title"]}{meta}{extra}{ts}')
        lines.append('')

    active_keys = {it['user_key'] for it in items}
    quiet = []
    for key, user in sorted(users.items(), key=lambda x: x[1].get('display', x[0])):
        if key in exclude or key in active_keys:
            continue
        quiet.append(user.get('display') or key.replace('_', ' ').title())
    if quiet:
        lines.append('QUIET TODAY')
        lines.append(', '.join(quiet))
        lines.append('')

    lines.append('Sent automatically at midnight US/Eastern. Reply not monitored.')

    text_body = '\n'.join(lines)

    # HTML
    glance_rows = ''.join(
        f'<tr><td style="padding:4px 12px 4px 0;color:#64748b;">{escape(label)}</td>'
        f'<td style="padding:4px 0;font-weight:600;color:#004C8C;">{n}</td></tr>'
        for label, n in _kind_totals(counts)
    )
    person_blocks = []
    for name in sorted(people.keys()):
        person_items = people[name]
        item_lis = []
        for it in person_items:
            meta = f' <span style="color:#64748b;">· {escape(it["meta"])}</span>' if it['meta'] else ''
            extra = f' <span style="color:#64748b;">· {escape(it["extra"])}</span>' if it['extra'] else ''
            ts = f' <span style="color:#94a3b8;">· {escape(it["time_str"])}</span>' if it['time_str'] else ''
            if it['kind'] in ('feedback', 'psc_feedback'):
                item_lis.append(
                    f'<li style="margin-bottom:6px;"><strong>{escape(it["kind_label"])}:</strong> '
                    f'{escape(it["title"])}{meta}{ts}</li>'
                )
            else:
                item_lis.append(
                    f'<li style="margin-bottom:6px;"><strong>{escape(it["kind_label"])}</strong> · '
                    f'{escape(it["title"])}{meta}{extra}{ts}</li>'
                )
        person_blocks.append(
            f'<div style="margin-bottom:18px;">'
            f'<p style="margin:0 0 8px;font-weight:700;color:#004C8C;">{escape(name)} '
            f'<span style="font-weight:400;color:#64748b;">({len(person_items)})</span></p>'
            f'<ul style="margin:0;padding-left:20px;color:#334155;font-size:14px;line-height:1.5;">'
            f'{"".join(item_lis)}</ul></div>'
        )

    quiet_html = ''
    if quiet:
        quiet_html = (
            '<div style="margin-top:20px;padding-top:16px;border-top:1px solid #e2e8f0;">'
            '<p style="margin:0 0 6px;font-size:11px;font-weight:600;color:#004C8C;'
            'text-transform:uppercase;letter-spacing:0.06em;">Quiet today</p>'
            f'<p style="margin:0;color:#64748b;font-size:13px;">{escape(", ".join(quiet))}</p></div>'
        )

    html_body = f'''
    <div style="font-family:Arial,sans-serif;max-width:620px;margin:0 auto;">
      <div style="background:#004C8C;padding:20px 24px;border-radius:8px 8px 0 0;">
        <p style="color:white;font-size:18px;font-weight:600;margin:0;">PPS Hub · Daily Team Activity</p>
        <p style="color:rgba(255,255,255,0.85);font-size:13px;margin:6px 0 0;">{escape(day_label)} · {"no team activity" if total == 0 else f"{total} items from {person_count} people"}</p>
      </div>
      <div style="background:#f8fafc;padding:24px;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;">
        <p style="margin:0 0 10px;font-size:11px;font-weight:600;color:#004C8C;text-transform:uppercase;letter-spacing:0.06em;">At a glance</p>
        <table style="font-size:14px;margin-bottom:20px;">{glance_rows}</table>
        <p style="margin:0 0 12px;font-size:11px;font-weight:600;color:#004C8C;text-transform:uppercase;letter-spacing:0.06em;">By person</p>
        {"".join(person_blocks)}
        {quiet_html}
        <p style="margin:20px 0 0;color:#94a3b8;font-size:11px;">Sent automatically at midnight US/Eastern.</p>
      </div>
    </div>
    '''

    return subject, text_body, html_body


def run_daily_digest(get_db, users, format_template_label, send_email_fn, force=False, date_override=None):
    """
    Build and optionally send the digest.
    send_email_fn(subject, text_body, html_body, recipients) -> bool
    Returns result dict.
    """
    def _finish(result):
        _record_last_run(get_db, result)
        return result

    if not _digest_enabled():
        return _finish({'ok': True, 'skipped': True, 'reason': 'disabled'})

    if not force and not should_run_scheduled():
        return _finish({'ok': True, 'skipped': True, 'reason': 'not_midnight_eastern'})

    exclude = _digest_exclude_keys()
    report_date = report_date_for_run(force=force, date_override=date_override)
    sent_key = report_date.isoformat()
    if not force and _load_sent_date(get_db) == sent_key:
        return _finish({'ok': True, 'skipped': True, 'reason': 'already_sent', 'report_date': sent_key})

    recipients = digest_recipients()
    if not recipients:
        return _finish({
            'ok': True,
            'skipped': True,
            'reason': 'no_recipients',
            'report_date': sent_key,
        })

    items, counts, start, end = collect_digest_items(
        get_db, users, exclude, report_date, format_template_label,
    )

    subject, text_body, html_body = build_digest_email(report_date, items, counts, users, exclude)
    sent = send_email_fn(subject, text_body, html_body, recipients)
    if sent:
        _mark_sent(get_db, report_date)
    result = {
        'ok': True,
        'skipped': False,
        'sent': sent,
        'report_date': sent_key,
        'item_count': len(items),
        'people_count': len({it['user_key'] for it in items}),
        'counts': counts,
        'recipients': recipients,
        'window_utc': [start.isoformat(), end.isoformat()],
    }
    if not items:
        result['no_activity'] = True
    if not sent:
        result['email_failed'] = True
        result['warning'] = 'Digest built but SMTP send failed — check pps-hub logs'
    return _finish(result)