"""PSC training alerts for the manager and the trainer.

Thomas, 2026-11-09: "when there is a meaningful update or usage on the
training it goes to Adam and I." Adam Cupito trains Harrison Hollon; Thomas
holds check-ins and sign-offs.

**What counts as meaningful, and why it is one email a day.** A trainee ticks
dozens of boxes a week. An email per tick would train both readers to ignore
the sender by Wednesday — the Estimates board notifications learned the same
lesson (one email per person per day, not a flood). So:

* **Daily summary**, sent with the nightly digest run, only on a day the
  trainee did something: items checked off (grouped, by title), week notes
  written, Practice Arena role-plays with their score, feedback sent.
* **Week ready for check-in** is the headline when every item in a week is
  done and the week is not signed off yet. Once per week, ever.
* **Gone quiet**: no training activity for three weekdays. Once per quiet
  stretch, keyed on the date of the last activity, so a trainee who stays
  idle does not get reported every night.

Sign-offs, feedback and enrolment still email straight away from `app.py`;
they are rare and someone may need to act the same day. All of these go to
the same people: Thomas, the training manager, and the trainer
(`PSC_TRAINING_MENTOR`) — never the trainee, and never anyone twice.

Everything is deduplicated in `psc_training_notifications` (the table the
sign-off email already uses), so the five hourly cron calls inside the
midnight window send at most one email per trainee per day.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from html import escape

QUIET_WEEKDAYS = 3

# notification_type values in psc_training_notifications. `week_num` holds a
# week for WEEK_READY and a yyyymmdd integer for the two day-keyed kinds.
DAILY = 'daily_summary'
WEEK_READY = 'week_ready'
QUIET = 'quiet'


def day_key(d: date) -> int:
    return d.year * 10000 + d.month * 100 + d.day


def weekdays_between(after: date, through: date) -> int:
    """Weekdays strictly after `after`, up to and including `through`."""
    n = 0
    d = after + timedelta(days=1)
    while d <= through:
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return n


def item_titles(curriculum):
    """{item_id: (where, title)} for every trackable item in the curriculum."""
    onboarding, weeks, core_values, sales_training, company_operations = curriculum
    out = {}

    def week_items(w):
        where = f"Week {w.get('week', 0)}"
        for key in ('videos', 'shadowing', 'additional', 'pps_focus'):
            for it in w.get(key, []) or []:
                if isinstance(it, dict) and it.get('id'):
                    out[it['id']] = (where, (it.get('title') or it.get('text') or it['id']).strip())
        if w.get('book_id'):
            out[w['book_id']] = (where, f"Reading: {w.get('book') or 'assigned chapters'}")

    week_items(onboarding)
    for w in weeks:
        week_items(w)
    for section in core_values.get('sections', []):
        for act in section.get('activities', []):
            out[act['id']] = ('Mission & Values', act.get('title') or act['id'])
    for module in sales_training.get('modules', []):
        for it in module.get('items', []):
            out[it['id']] = ('Sales Training', it.get('title') or it['id'])
    for module in company_operations.get('modules', []):
        for it in module.get('items', []):
            out[it['id']] = (module.get('title') or 'Company Operations', it.get('title') or it['id'])
    return out


def _eastern_date(value):
    """Calendar day in Eastern for a naive-UTC timestamp (or a date, unchanged)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        import hub_time
        return hub_time.to_eastern(value).date()
    return value


def _rows(cur, sql, params):
    cur.execute(sql, params)
    return cur.fetchall() or []


def collect_day(cur, user_key, start, end):
    """What the trainee did between start and end (naive UTC)."""
    items = [r[0] for r in _rows(cur, '''
        SELECT item_id FROM psc_training_progress
         WHERE user_key = %s AND completed = TRUE
           AND completed_at >= %s AND completed_at < %s
         ORDER BY completed_at''', (user_key, start, end))]
    notes = [(r[0], r[1] or '') for r in _rows(cur, '''
        SELECT week_num, notes FROM psc_training_notes
         WHERE user_key = %s AND updated_at >= %s AND updated_at < %s
           AND COALESCE(TRIM(notes), '') <> ''
         ORDER BY week_num''', (user_key, start, end))]
    roleplays = [(r[0], r[1], r[2]) for r in _rows(cur, '''
        SELECT scenario_id, overall, result FROM psc_roleplay_sessions
         WHERE user_key = %s AND created_at >= %s AND created_at < %s
         ORDER BY created_at''', (user_key, start, end))]
    feedback = [(r[0], r[1] or '') for r in _rows(cur, '''
        SELECT week_num, message FROM psc_training_feedback
         WHERE user_key = %s AND submitted_at >= %s AND submitted_at < %s
         ORDER BY submitted_at''', (user_key, start, end))]
    return {'items': items, 'notes': notes, 'roleplays': roleplays, 'feedback': feedback}


def last_activity(cur, user_key):
    rows = _rows(cur, '''
        SELECT GREATEST(
            (SELECT MAX(completed_at) FROM psc_training_progress WHERE user_key = %s AND completed = TRUE),
            (SELECT MAX(updated_at) FROM psc_training_notes WHERE user_key = %s),
            (SELECT MAX(created_at) FROM psc_roleplay_sessions WHERE user_key = %s),
            (SELECT MAX(submitted_at) FROM psc_training_feedback WHERE user_key = %s)
        )''', (user_key,) * 4)
    return rows[0][0] if rows else None


def _already(cur, user_key, kind, num):
    return bool(_rows(cur, '''
        SELECT 1 FROM psc_training_notifications
         WHERE user_key = %s AND notification_type = %s AND week_num = %s''',
        (user_key, kind, num)))


def _record(cur, user_key, kind, num):
    cur.execute('''
        INSERT INTO psc_training_notifications (user_key, notification_type, week_num)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_key, notification_type, week_num) DO NOTHING''',
        (user_key, kind, num))


def build_email(display, report_date, day, ready_weeks, quiet_since, titles,
                week_labels, checkins, scenario_title, stats, oversight_url, trainer):
    """Subject, text and HTML for one trainee's day. Pure; tested directly."""
    day_label = report_date.strftime('%a %b %-d')
    if ready_weeks:
        headline = f"{display} finished {', '.join(week_labels.get(w, f'Week {w}') for w in ready_weeks)} — ready for check-in"
    elif quiet_since:
        headline = f"{display}: no training activity since {quiet_since.strftime('%a %b %-d')}"
    else:
        headline = f"{display}: training activity {day_label}"
    subject = f'PSC Training — {headline}'

    lines, html = [], []

    def section(title, rows):
        if not rows:
            return
        lines.append(title)
        lines.extend(f'  - {r}' for r in rows)
        lines.append('')
        html.append(f'<p style="margin:14px 0 4px;color:#004C8C;font-weight:600;">{escape(title)}</p>'
                    '<ul style="margin:0;padding-left:20px;color:#334155;">'
                    + ''.join(f'<li>{escape(r)}</li>' for r in rows) + '</ul>')

    for w in ready_weeks:
        q = checkins.get(w, '')
        section(f"{week_labels.get(w, f'Week {w}')} is complete — check-in question",
                [q] if q else ['Every item checked off. Ready for the manager check-in and sign-off.'])
    if quiet_since:
        section('Gone quiet', [
            f"Last training activity was {quiet_since.strftime('%A %b %-d')} — "
            f"{QUIET_WEEKDAYS}+ weekdays ago. Worth a check-in with {trainer or 'the trainer'}."])

    grouped = {}
    for item_id in day['items']:
        where, title = titles.get(item_id, ('Other', item_id))
        grouped.setdefault(where, []).append(title)
    if grouped:
        section(f"Checked off ({len(day['items'])})",
                [f"{where}: {'; '.join(ts)}" for where, ts in grouped.items()])
    if day['notes']:
        section('Week notes written', [
            f"{week_labels.get(w, f'Week {w}')}: {n.strip()[:280]}{'…' if len(n.strip()) > 280 else ''}"
            for w, n in day['notes']])
    if day['roleplays']:
        section('Practice Arena', [
            f"{scenario_title(s)} — {overall:.1f}/10, {result}" if overall is not None else scenario_title(s)
            for s, overall, result in day['roleplays']])
    if day['feedback']:
        section('Feedback on the training', [m.strip()[:400] for _, m in day['feedback']])

    progress = f"Overall: {stats['pct']}% ({stats['done']} / {stats['total']} items), {stats.get('signed_weeks', 0)} weeks signed off."
    lines.append(progress)
    lines.append(f'Accountability dashboard: {oversight_url}')
    text = f'{headline}\n\n' + '\n'.join(lines)
    body = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
      <div style="background:#004C8C;padding:18px 22px;border-radius:8px 8px 0 0;">
        <p style="color:white;font-size:17px;font-weight:600;margin:0;">{escape(headline)}</p>
      </div>
      <div style="background:#f8fafc;padding:18px 22px;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;font-size:14px;line-height:1.5;">
        {''.join(html)}
        <p style="margin:16px 0 6px;color:#64748b;">{escape(progress)}</p>
        <p style="margin:0;"><a href="{oversight_url}" style="color:#004C8C;font-weight:600;">Open PSC Accountability dashboard →</a></p>
      </div>
    </div>"""
    return subject, text, body


def run(get_db, trainees, report_date, start, end, *, titles, week_labels, checkins,
        scenario_title, stats_fn, recipients_fn, send_fn, oversight_url, trainer,
        today=None, force=False):
    """One email per active trainee with something meaningful. Returns a result dict.

    `trainees` is [(user_key, display, enrolled_at)]. `force` ignores the
    dedupe (used for a manual preview) and records nothing.
    """
    today = today or report_date + timedelta(days=1)
    conn = get_db()
    if not conn:
        return {'ok': False, 'error': 'Database unavailable'}
    sent, skipped = [], []
    try:
        cur = conn.cursor()
        for user_key, display, enrolled_at in trainees:
            day = collect_day(cur, user_key, start, end)
            stats = stats_fn(user_key)
            ready = [w['week'] for w in stats.get('week_pcts', [])
                     if w.get('ready_for_signoff') and (force or not _already(cur, user_key, WEEK_READY, w['week']))]

            quiet_since = None
            last = last_activity(cur, user_key) or enrolled_at
            if last is not None:
                # DB stamps are naive UTC; 9pm Eastern is tomorrow in UTC.
                last_d = _eastern_date(last)
                started = _eastern_date(enrolled_at) or last_d
                if (weekdays_between(last_d, report_date) >= QUIET_WEEKDAYS
                        and weekdays_between(started, report_date) >= QUIET_WEEKDAYS
                        and (force or not _already(cur, user_key, QUIET, day_key(last_d)))):
                    quiet_since = last_d

            did_something = any(day[k] for k in ('items', 'notes', 'roleplays', 'feedback'))
            if not (did_something or ready or quiet_since):
                skipped.append(user_key)
                continue
            if not force and did_something and _already(cur, user_key, DAILY, day_key(report_date)):
                skipped.append(user_key)
                continue

            recipients = recipients_fn(user_key)
            subject, text, html = build_email(
                display, report_date, day, ready, quiet_since, titles, week_labels,
                checkins, scenario_title, stats, oversight_url, trainer)
            if not send_fn(subject, text, html, recipients):
                skipped.append(user_key)
                continue
            sent.append({'user_key': user_key, 'subject': subject, 'recipients': recipients})
            if force:
                continue
            if did_something:
                _record(cur, user_key, DAILY, day_key(report_date))
            for w in ready:
                _record(cur, user_key, WEEK_READY, w)
            if quiet_since:
                _record(cur, user_key, QUIET, day_key(quiet_since))
            conn.commit()
        cur.close()
    except Exception as e:
        conn.rollback()
        print(f'PSC training alerts error: {e}')
        return {'ok': False, 'error': str(e), 'sent': sent}
    finally:
        conn.close()
    return {'ok': True, 'report_date': report_date.isoformat(), 'sent': sent, 'skipped': skipped}
