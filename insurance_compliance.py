"""Weekly Trade Partner (sub) insurance compliance digest.

Pulls the Sub Info board from Monday.com, downloads each sub's most recent
Certificate of Insurance PDF, and extracts real policy expiration dates
instead of trusting the board's manually-typed date columns (which go
stale — see CLAUDE.md / Office Ops notes on this). Sends one internal-only
email to Stephanie + Thomas. No board writes, no sub-facing email — that is
an explicit later iteration (2026-08 decision).

send_email_fn(subject, text_body, html_body, recipients) -> bool
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from html import escape

import monday_client
from estimators.siding.pdf_extract import extract_pdf_text

EXPIRING_SOON_DAYS = 30
EXPIRING_LATER_DAYS = 60
NEW_SUB_WINDOW_DAYS = 30

_DATE_RE = re.compile(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})')


def init_tables(cur):
    cur.execute('''
        CREATE TABLE IF NOT EXISTS office_ops_tp_snapshot (
            monday_item_id VARCHAR(50) PRIMARY KEY,
            name VARCHAR(255),
            group_name VARCHAR(100),
            insurance_expires_manual DATE,
            wc_expires_manual DATE,
            insurance_expires_extracted DATE,
            extract_confidence TEXT,
            additional_insured_present BOOLEAN,
            coi_asset_name VARCHAR(255),
            first_seen_at TIMESTAMP DEFAULT NOW(),
            last_seen_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    # Hub-side manual correction — a human looked at the real COI (or knows
    # the true date some other way) and typed it in directly. Outranks the
    # Monday board's manual column (the thing that goes stale) but still
    # loses to a COI we can actually read, since that's ground truth.
    cur.execute('''
        ALTER TABLE office_ops_tp_snapshot
        ADD COLUMN IF NOT EXISTS insurance_expires_override DATE
    ''')
    cur.execute('''
        ALTER TABLE office_ops_tp_snapshot
        ADD COLUMN IF NOT EXISTS override_by VARCHAR(100)
    ''')
    cur.execute('''
        ALTER TABLE office_ops_tp_snapshot
        ADD COLUMN IF NOT EXISTS override_at TIMESTAMP
    ''')
    # Widen extract_confidence on tables created before this fix (2026-08-09) —
    # fetch_error values embed the exception message, which routinely runs
    # past 50 chars ("value too long for type character varying(50)").
    cur.execute('''
        ALTER TABLE office_ops_tp_snapshot
        ALTER COLUMN extract_confidence TYPE TEXT
    ''')


def save_override(get_db_fn, monday_item_id, override_date, user_key):
    conn = get_db_fn()
    try:
        cur = conn.cursor()
        init_tables(cur)
        cur.execute('''
            UPDATE office_ops_tp_snapshot
            SET insurance_expires_override = %s, override_by = %s, override_at = NOW(), updated_at = NOW()
            WHERE monday_item_id = %s
        ''', (override_date, user_key, monday_item_id))
        updated = cur.rowcount
        conn.commit()
        cur.close()
        return updated > 0
    finally:
        conn.close()


def _parse_monday_date(text_val):
    if not text_val:
        return None
    try:
        return datetime.strptime(text_val.strip(), '%Y-%m-%d').date()
    except (ValueError, AttributeError):
        return None


def _parse_date_token(m):
    mo, day, yr = int(m.group(1)), int(m.group(2)), m.group(3)
    yr = int(yr)
    if yr < 100:
        yr += 2000
    try:
        return date(yr, mo, day)
    except ValueError:
        return None


def _extract_coi_fields(pdf_bytes):
    """Best-effort extraction from a COI PDF's text layer.

    Real-world COIs vary by carrier/agent template, so this is a heuristic,
    not a guarantee — matches Office Ops' philosophy elsewhere (chase list,
    import status mapping) of a calibrated-honest best guess over a
    confident wrong one. Flag confidence so low-confidence rows get a human
    look rather than being silently trusted.
    """
    try:
        text = extract_pdf_text(pdf_bytes)
    except Exception:
        return {'gl_exp': None, 'wc_exp': None, 'additional_insured': None, 'confidence': 'unreadable'}

    upper = text.upper()
    gl_exp = None
    wc_exp = None

    # General Liability: look for the block between "GENERAL LIABILITY" and
    # the next coverage section, take the second date on the first
    # EFF/EXP-looking date pair (ACORD 25 lists EFF then EXP).
    gl_idx = upper.find('GENERAL LIABILITY')
    if gl_idx != -1:
        window = text[gl_idx:gl_idx + 600]
        dates = [(m, _parse_date_token(m)) for m in _DATE_RE.finditer(window)]
        dates = [(m, d) for m, d in dates if d]
        if len(dates) >= 2:
            gl_exp = dates[1][1]
        elif len(dates) == 1:
            gl_exp = dates[0][1]

    # Workers Comp: same approach, scoped to its own section if present.
    wc_idx = upper.find('WORKERS COMPENSATION')
    if wc_idx != -1:
        window = text[wc_idx:wc_idx + 600]
        dates = [(m, _parse_date_token(m)) for m in _DATE_RE.finditer(window)]
        dates = [(m, d) for m, d in dates if d]
        if len(dates) >= 2:
            wc_exp = dates[1][1]
        elif len(dates) == 1:
            wc_exp = dates[0][1]

    # Additional insured: text-layer checkbox state is unreliable (checkbox
    # marks are often graphics, not extractable characters) — only assert
    # True/False when the surrounding text gives an unambiguous signal,
    # otherwise leave None (unknown) rather than guess.
    additional_insured = None
    ai_idx = upper.find('ADDITIONAL INSURED')
    if ai_idx != -1:
        nearby = upper[max(0, ai_idx - 5):ai_idx + 5]
        if re.search(r'[XY]\s*ADDITIONAL INSURED|ADDITIONAL INSURED\s*[XY]', upper[max(0, ai_idx - 10):ai_idx + 30]):
            additional_insured = True
        # else: leave None — presence of the label alone isn't a checked box

    confidence = 'text_extracted' if (gl_exp or wc_exp) else 'no_dates_found'
    return {
        'gl_exp': gl_exp,
        'wc_exp': wc_exp,
        'additional_insured': additional_insured,
        'confidence': confidence,
    }


def _pick_latest_coi_file(files):
    """Files are usually in upload order; prefer names with a recent-looking
    year range (e.g. '25-26') and otherwise fall back to the last uploaded."""
    if not files:
        return None
    year_re = re.compile(r'(\d{2})[\-\/](\d{2})(?!\d)')
    best = None
    best_year = -1
    for f in files:
        m = year_re.search(f.get('name') or '')
        if m:
            yr = int(m.group(2))
            if yr > best_year:
                best_year = yr
                best = f
    return best or files[-1]


def _col_value(column_values, col_id):
    for cv in column_values or []:
        if cv.get('id') == col_id:
            return cv
    return None


def _bucket_label(exp_date, today):
    if exp_date is None:
        return None
    delta = (exp_date - today).days
    if delta < 0:
        return 'expired'
    if delta <= EXPIRING_SOON_DAYS:
        return 'expiring_soon'
    if delta <= EXPIRING_LATER_DAYS:
        return 'expiring_later'
    return None


def categorize_rows(rows, today):
    """Single shared definition of the digest's categories — used by both
    the weekly email and the Office Ops compliance page, so the two never
    silently drift apart on what counts as 'expiring soon'."""
    expired, soon, later, new_subs, mismatches, needs_manual = [], [], [], [], [], []
    for r in rows:
        bucket = _bucket_label(r['effective_ins'], today)
        if bucket == 'expired':
            expired.append(r)
        elif bucket == 'expiring_soon':
            soon.append(r)
        elif bucket == 'expiring_later':
            later.append(r)
        if r['is_new']:
            new_subs.append(r)
        if r['manual_ins'] and r['extracted_ins'] and r['manual_ins'] != r['extracted_ins']:
            mismatches.append(r)
        if r['needs_manual_review']:
            needs_manual.append(r)

    expired.sort(key=lambda r: r['effective_ins'] or date.min)
    soon.sort(key=lambda r: r['effective_ins'] or date.min)
    later.sort(key=lambda r: r['effective_ins'] or date.min)

    return {
        'expired': expired,
        'soon': soon,
        'later': later,
        'new_subs': new_subs,
        'mismatches': mismatches,
        'needs_manual': needs_manual,
    }


def get_latest_snapshot_rows(get_db_fn):
    """Read office_ops_tp_snapshot back out in the same row-shape
    run_weekly_compliance_check builds, for the Office Ops compliance page.
    Returns (rows, last_run_at) — last_run_at is None if never run."""
    conn = get_db_fn()
    try:
        cur = conn.cursor()
        init_tables(cur)
        conn.commit()
        cur.execute('''
            SELECT monday_item_id, name, group_name, insurance_expires_manual,
                   wc_expires_manual, insurance_expires_extracted, extract_confidence,
                   additional_insured_present, coi_asset_name, insurance_expires_override,
                   override_by, first_seen_at, updated_at
            FROM office_ops_tp_snapshot
            ORDER BY name
        ''')
        db_rows = cur.fetchall()
        cur.close()

        today = date.today()
        new_cutoff = today - timedelta(days=NEW_SUB_WINDOW_DAYS)
        rows = []
        last_run_at = None
        for (item_id, name, group_name, manual_ins, manual_wc, extracted_ins,
             confidence, additional_insured, coi_name, override_ins, override_by,
             first_seen_at, updated_at) in db_rows:
            if updated_at and (last_run_at is None or updated_at > last_run_at):
                last_run_at = updated_at

            if extracted_ins:
                effective_ins, effective_source = extracted_ins, 'coi_pdf'
            elif override_ins:
                effective_ins, effective_source = override_ins, 'override'
            elif manual_ins:
                effective_ins, effective_source = manual_ins, 'manual'
            else:
                effective_ins, effective_source = None, None

            is_new = bool(first_seen_at and first_seen_at.date() >= new_cutoff)
            needs_manual_review = (not extracted_ins) and (not override_ins)

            rows.append({
                'item_id': item_id,
                'name': name,
                'group': group_name,
                'manual_ins': manual_ins,
                'manual_wc': manual_wc,
                'extracted_ins': extracted_ins,
                'confidence': confidence,
                'additional_insured': additional_insured,
                'override_ins': override_ins,
                'override_by': override_by,
                'effective_ins': effective_ins,
                'effective_source': effective_source,
                'is_new': is_new,
                'coi_name': coi_name,
                'needs_manual_review': needs_manual_review,
            })
        return rows, last_run_at
    finally:
        conn.close()


def run_weekly_compliance_check(get_db_fn, send_email_fn, recipients):
    today = date.today()
    conn = get_db_fn()
    try:
        cur = conn.cursor()
        init_tables(cur)
        conn.commit()

        items = monday_client.fetch_sub_info_items()

        rows = []
        for it in items:
            col = it.get('column_values') or []
            item_id = it['id']
            name = it.get('name') or ''
            group_name = (it.get('group') or {}).get('title') or ''

            ins_cv = _col_value(col, monday_client.COL_DATE_INSURANCE)
            wc_cv = _col_value(col, monday_client.COL_DATE_WORKERS_COMP)
            manual_ins = _parse_monday_date(ins_cv['text'] if ins_cv else None)
            manual_wc = _parse_monday_date(wc_cv['text'] if wc_cv else None)

            files_col = _col_value(col, monday_client.COL_FILES)
            files = monday_client.parse_files_column(files_col) if files_col else []
            coi_file = _pick_latest_coi_file(files)

            extracted = {'gl_exp': None, 'wc_exp': None, 'additional_insured': None, 'confidence': 'no_file'}
            coi_name = None
            if coi_file:
                coi_name = coi_file.get('name')
                try:
                    asset_map = monday_client.resolve_asset_urls([coi_file['assetId']])
                    asset = asset_map.get(str(coi_file['assetId']))
                    if asset and asset.get('public_url'):
                        pdf_bytes = monday_client.download_asset(asset['public_url'])
                        extracted = _extract_coi_fields(pdf_bytes)
                except Exception as e:
                    extracted = {'gl_exp': None, 'wc_exp': None, 'additional_insured': None,
                                 'confidence': f'fetch_error: {e}'[:300]}

            cur.execute(
                'SELECT first_seen_at, insurance_expires_override, override_by '
                'FROM office_ops_tp_snapshot WHERE monday_item_id = %s',
                (item_id,),
            )
            existing = cur.fetchone()
            is_new = existing is None
            override_ins = existing[1] if existing else None
            override_by = existing[2] if existing else None

            # Priority: a COI we can actually read > a human-typed Hub
            # override (someone looked at the real file) > the Monday
            # board's manual column, which is what goes stale in practice.
            effective_ins = extracted['gl_exp'] or override_ins or manual_ins
            if extracted['gl_exp']:
                effective_source = 'coi_pdf'
            elif override_ins:
                effective_source = 'override'
            elif manual_ins:
                effective_source = 'manual'
            else:
                effective_source = None
            needs_manual_review = (not extracted['gl_exp']) and (not override_ins)

            cur.execute('''
                INSERT INTO office_ops_tp_snapshot
                    (monday_item_id, name, group_name, insurance_expires_manual,
                     wc_expires_manual, insurance_expires_extracted, extract_confidence,
                     additional_insured_present, coi_asset_name, last_seen_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                ON CONFLICT (monday_item_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    group_name = EXCLUDED.group_name,
                    insurance_expires_manual = EXCLUDED.insurance_expires_manual,
                    wc_expires_manual = EXCLUDED.wc_expires_manual,
                    insurance_expires_extracted = EXCLUDED.insurance_expires_extracted,
                    extract_confidence = EXCLUDED.extract_confidence,
                    additional_insured_present = EXCLUDED.additional_insured_present,
                    coi_asset_name = EXCLUDED.coi_asset_name,
                    last_seen_at = NOW(),
                    updated_at = NOW()
            ''', (item_id, name, group_name, manual_ins, manual_wc,
                  extracted['gl_exp'], extracted['confidence'],
                  extracted['additional_insured'], coi_name))
            # Note: override_* columns are untouched by this upsert (not in
            # the SET clause) — a manual correction survives every future
            # weekly run until a real COI is read and beats it.

            rows.append({
                'item_id': item_id,
                'name': name,
                'group': group_name,
                'manual_ins': manual_ins,
                'manual_wc': manual_wc,
                'extracted_ins': extracted['gl_exp'],
                'extracted_wc': extracted['wc_exp'],
                'confidence': extracted['confidence'],
                'additional_insured': extracted['additional_insured'],
                'override_ins': override_ins,
                'override_by': override_by,
                'effective_ins': effective_ins,
                'effective_source': effective_source,
                'is_new': is_new,
                'coi_name': coi_name,
                'needs_manual_review': needs_manual_review,
            })

        conn.commit()
        cur.close()

        subject, text_body, html_body = _build_digest(rows, today)
        sent = send_email_fn(subject, text_body, html_body, recipients)
        return {'ok': True, 'sent': sent, 'checked': len(rows)}
    finally:
        conn.close()


def _fmt_date(d):
    return d.strftime('%m/%d/%Y') if d else '—'


def _needs_manual_message(r):
    if r['coi_name']:
        base = f"{r['name']} — \"{r['coi_name']}\" looks like a scan/photo, no text to read"
    else:
        base = f"{r['name']} — no COI on file to read"
    if r['manual_ins']:
        return f"{base}; using board date ({_fmt_date(r['manual_ins'])}) for now"
    return f"{base}, and no board date entered either"


def _build_digest(rows, today):
    cats = categorize_rows(rows, today)
    expired, soon, later = cats['expired'], cats['soon'], cats['later']
    new_subs, mismatches, needs_manual = cats['new_subs'], cats['mismatches'], cats['needs_manual']

    lines = [f'PPS Trade Partner Compliance — {today.strftime("%A, %B %d, %Y")}', '']

    def _section(title, items, fmt):
        if not items:
            return
        lines.append(f'{title} ({len(items)})')
        for it in items:
            lines.append(f'  - {fmt(it)}')
        lines.append('')

    _section('EXPIRED', expired, lambda r: f"{r['name']} — expired {_fmt_date(r['effective_ins'])} [{r['effective_source']}]")
    _section(f'EXPIRING ≤{EXPIRING_SOON_DAYS} DAYS', soon, lambda r: f"{r['name']} — expires {_fmt_date(r['effective_ins'])} [{r['effective_source']}]")
    _section(f'EXPIRING {EXPIRING_SOON_DAYS+1}-{EXPIRING_LATER_DAYS} DAYS', later, lambda r: f"{r['name']} — expires {_fmt_date(r['effective_ins'])} [{r['effective_source']}]")
    _section(f'NEW SUBS (last {NEW_SUB_WINDOW_DAYS} days)', new_subs, lambda r: f"{r['name']} ({r['group']})")
    _section('MANUAL VS COI-EXTRACTED DATE MISMATCH', mismatches,
              lambda r: f"{r['name']} — board says {_fmt_date(r['manual_ins'])}, COI PDF says {_fmt_date(r['extracted_ins'])}")
    _section('NEEDS MANUAL ENTRY', needs_manual, _needs_manual_message)

    if not (expired or soon or later or new_subs or mismatches):
        lines.append('Nothing flagged this week — all checked subs are current.')
        lines.append('')

    lines.append(f'Checked {len(rows)} subs across Compliant + Insurance Out of Date groups.')
    lines.append('Source: Monday.com Sub Info board + COI PDF text extraction (best-effort — spot-check low-confidence rows).')

    text_body = '\n'.join(lines)

    html_parts = [f'<h2>PPS Trade Partner Compliance — {escape(today.strftime("%A, %B %d, %Y"))}</h2>']

    def _html_section(title, items, fmt, color):
        if not items:
            return
        html_parts.append(f'<h3 style="color:{color};margin:18px 0 6px;">{escape(title)} ({len(items)})</h3><ul>')
        for it in items:
            html_parts.append(f'<li>{escape(fmt(it))}</li>')
        html_parts.append('</ul>')

    _html_section('Expired', expired, lambda r: f"{r['name']} — expired {_fmt_date(r['effective_ins'])} [{r['effective_source']}]", '#b91c1c')
    _html_section(f'Expiring ≤{EXPIRING_SOON_DAYS} days', soon, lambda r: f"{r['name']} — expires {_fmt_date(r['effective_ins'])} [{r['effective_source']}]", '#c2410c')
    _html_section(f'Expiring {EXPIRING_SOON_DAYS+1}-{EXPIRING_LATER_DAYS} days', later, lambda r: f"{r['name']} — expires {_fmt_date(r['effective_ins'])} [{r['effective_source']}]", '#a16207')
    _html_section('New subs', new_subs, lambda r: f"{r['name']} ({r['group']})", '#166534')
    _html_section('Manual vs COI-extracted mismatch', mismatches,
                   lambda r: f"{r['name']} — board says {_fmt_date(r['manual_ins'])}, COI PDF says {_fmt_date(r['extracted_ins'])}", '#4338ca')
    _html_section('Needs manual entry', needs_manual, _needs_manual_message, '#78716c')

    if not (expired or soon or later or new_subs or mismatches):
        html_parts.append('<p>Nothing flagged this week — all checked subs are current.</p>')

    html_parts.append(f'<p style="color:#64748b;font-size:12px;">Checked {len(rows)} subs. Source: Monday.com Sub Info + COI PDF extraction (best-effort).</p>')
    html_body = '\n'.join(html_parts)

    subject = 'PPS Trade Partner Compliance'
    if expired:
        subject += f' — {len(expired)} EXPIRED'
    elif soon:
        subject += f' — {len(soon)} expiring soon'

    return subject, text_body, html_body
