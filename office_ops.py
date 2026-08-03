"""Office Ops — Stephanie + Thomas workspace for AR digests and weekly Numbers.

Owner request 2026-08-03 / build-out 2026-08:
  - Access: office_manager (Stephanie) + admin (Thomas) only.
  - Files land via Hub upload (Postgres), not a shared team vault dump.
  - v1: AR Aging Summary (QB export) → ranked chase list + Numbers draft body.
  - Later: Sub Info compliance, Outlook sheet, 50/50 split nuance, Gmail drafts.

Does NOT write to QuickBooks. Does NOT auto-send email.
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import date, datetime
from decimal import Decimal

from psycopg2.extras import RealDictCursor

# Who may open /office-ops and upload. Admin always; Stephanie by key + role.
OFFICE_OPS_USER_KEYS = frozenset({'stephanie_whetstone', 'thomas_ellison'})
OFFICE_OPS_ROLES = frozenset({'office_manager', 'admin'})

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_KINDS = frozenset({'ar_aging'})

# Customers always called out in the brief (ops judgment, not accounting).
LEGACY_CUSTOMER_HINTS = (
    'bridges of pine creek',
    'bopc',
    '3800 cornell',
)

BOPC_ALIASES = ('bridges of pine creek', 'bopc')


def can_access_office_ops(users, user_key):
    if not user_key:
        return False
    if user_key in OFFICE_OPS_USER_KEYS:
        return True
    role = (users.get(user_key) or {}).get('role')
    return role in OFFICE_OPS_ROLES


def init_tables(cur):
    cur.execute('''
        CREATE TABLE IF NOT EXISTS office_ops_files (
            id SERIAL PRIMARY KEY,
            kind VARCHAR(50) NOT NULL,
            filename VARCHAR(255) NOT NULL,
            mime_type VARCHAR(100),
            size_bytes INTEGER NOT NULL,
            file_data BYTEA NOT NULL,
            uploaded_by VARCHAR(100),
            uploaded_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    cur.execute(
        'CREATE INDEX IF NOT EXISTS idx_office_ops_files_kind_time '
        'ON office_ops_files(kind, uploaded_at DESC)'
    )
    cur.execute('''
        CREATE TABLE IF NOT EXISTS office_ops_packs (
            id SERIAL PRIMARY KEY,
            pack_date DATE NOT NULL,
            source_file_id INTEGER REFERENCES office_ops_files(id) ON DELETE SET NULL,
            kind VARCHAR(50) NOT NULL DEFAULT 'ar_aging',
            summary_json JSONB NOT NULL,
            numbers_draft_md TEXT,
            created_by VARCHAR(100),
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    cur.execute(
        'CREATE INDEX IF NOT EXISTS idx_office_ops_packs_created '
        'ON office_ops_packs(created_at DESC)'
    )


def _money(val):
    if val is None or val == '':
        return 0.0
    if isinstance(val, (int, float, Decimal)):
        return float(val)
    s = str(val).strip().replace(',', '').replace('$', '').replace('(', '-').replace(')', '')
    if not s or s == '-':
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _norm_header(h):
    if h is None:
        return ''
    return re.sub(r'\s+', ' ', str(h).strip().lower())


def _is_header_row(cells):
    joined = ' '.join(_norm_header(c) for c in cells if c is not None)
    return (
        'current' in joined
        and ('1 - 30' in joined or '1-30' in joined or '1 – 30' in joined)
        and 'total' in joined
    )


def _map_aging_cols(header_cells):
    """Map column index → bucket key from QB-style header row."""
    colmap = {}
    for i, h in enumerate(header_cells):
        n = _norm_header(h)
        if not n:
            continue
        if n in ('', 'customer', 'name') or i == 0 and 'current' not in n:
            if i == 0:
                colmap['customer'] = i
            continue
        if n == 'current':
            colmap['current'] = i
        elif '1' in n and '30' in n:
            colmap['1_30'] = i
        elif '31' in n and '60' in n:
            colmap['31_60'] = i
        elif '61' in n and '90' in n:
            colmap['61_90'] = i
        elif '91' in n or 'over' in n:
            colmap['91_and_over'] = i
        elif n == 'total':
            colmap['total'] = i
    if 'customer' not in colmap:
        colmap['customer'] = 0
    return colmap


def _row_bucket(cells, colmap):
    def g(key):
        idx = colmap.get(key)
        if idx is None or idx >= len(cells):
            return 0.0
        return _money(cells[idx])

    total = g('total')
    if total == 0.0:
        total = g('current') + g('1_30') + g('31_60') + g('61_90') + g('91_and_over')
    return {
        'current': g('current'),
        '1_30': g('1_30'),
        '31_60': g('31_60'),
        '61_90': g('61_90'),
        '91_and_over': g('91_and_over'),
        'total': total,
    }


def parse_ar_aging_bytes(filename, raw_bytes):
    """Parse QB A/R Aging Summary (xlsx) or flat CSV. Returns summary dict."""
    name = (filename or '').lower()
    if name.endswith('.csv') or name.endswith('.txt'):
        return _parse_ar_csv(raw_bytes)
    return _parse_ar_xlsx(raw_bytes)


def _parse_ar_csv(raw_bytes):
    text = raw_bytes.decode('utf-8-sig', errors='replace')
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise ValueError('CSV is empty.')
    header_idx = 0
    for i, row in enumerate(rows[:20]):
        if _is_header_row(row) or any(_norm_header(c) == 'customer' for c in row):
            header_idx = i
            break
    colmap = _map_aging_cols(rows[header_idx])
    # Flat CSV from our prior exports: customer,current,1_30,...
    if 'current' not in colmap:
        headers = [_norm_header(h) for h in rows[header_idx]]
        aliases = {
            'customer': 'customer',
            'current': 'current',
            '1_30': '1_30',
            '31_60': '31_60',
            '61_90': '61_90',
            '91_and_over': '91_and_over',
            'total': 'total',
        }
        colmap = {}
        for i, h in enumerate(headers):
            key = aliases.get(h.replace(' ', '_').replace('-', '_'))
            if key:
                colmap[key] = i
        if 'customer' not in colmap:
            colmap['customer'] = 0

    customers = []
    for row in rows[header_idx + 1:]:
        if not row or all(c in (None, '') for c in row):
            continue
        cust = str(row[colmap.get('customer', 0)] or '').strip()
        if not cust or cust.upper() == 'TOTAL':
            continue
        if cust.lower().startswith('total for '):
            cust = cust[10:].strip()
        buckets = _row_bucket(row, colmap)
        if buckets['total'] == 0 and not any(
            buckets[k] for k in ('current', '1_30', '31_60', '61_90', '91_and_over')
        ):
            continue
        customers.append({'customer': cust, **buckets})
    return _build_summary(customers, as_of_label=None, source='csv')


def _parse_ar_xlsx(raw_bytes):
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), data_only=True, read_only=True)
    ws = wb.active
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    if not rows:
        raise ValueError('Spreadsheet is empty.')

    as_of_label = None
    for row in rows[:8]:
        for cell in row:
            if cell and isinstance(cell, str) and cell.strip().lower().startswith('as of'):
                as_of_label = cell.strip()
                break

    header_idx = None
    for i, row in enumerate(rows[:25]):
        if _is_header_row(row):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError(
            'Could not find an A/R Aging header row (expected CURRENT / 1-30 / Total). '
            'Upload the QuickBooks A/R Aging Summary export.'
        )

    colmap = _map_aging_cols(rows[header_idx])
    # Prefer "Total for X" rollups (QB hierarchy); fall back to leaf rows.
    total_for = []
    leafish = []
    for row in rows[header_idx + 1:]:
        if not row or row[0] is None:
            continue
        name = str(row[0]).strip()
        if not name:
            continue
        if name.upper() == 'TOTAL' or name.upper().startswith('TOTAL '):
            # Grand total row — capture but don't list as customer
            continue
        buckets = _row_bucket(row, colmap)
        if name.lower().startswith('total for '):
            cust = name[10:].strip()
            if buckets['total'] or any(buckets[k] for k in buckets if k != 'total'):
                total_for.append({'customer': cust, **buckets})
        else:
            # Skip pure parent headers with no amounts (children follow)
            if buckets['total'] or any(
                buckets[k] for k in ('current', '1_30', '31_60', '61_90', '91_and_over')
            ):
                leafish.append({'customer': name, **buckets})

    customers = total_for if total_for else leafish
    # Dedupe by customer keeping max total (parent "Total for ACME" vs job totals)
    by_name = {}
    for c in customers:
        key = c['customer'].strip().lower()
        prev = by_name.get(key)
        if not prev or c['total'] >= prev['total']:
            by_name[key] = c
    customers = sorted(by_name.values(), key=lambda x: -x['total'])
    return _build_summary(customers, as_of_label=as_of_label, source='xlsx')


def _build_summary(customers, as_of_label, source):
    grand = {
        'current': 0.0,
        '1_30': 0.0,
        '31_60': 0.0,
        '61_90': 0.0,
        '91_and_over': 0.0,
        'total': 0.0,
    }
    for c in customers:
        for k in grand:
            grand[k] += c.get(k, 0.0)

    def _is_bopc_name(name):
        low = (name or '').lower()
        if any(a in low for a in BOPC_ALIASES):
            return True
        # QB often splits Bridges into "BOPC Turns", "BOPC Capital", etc.
        return low.startswith('bopc') or low.startswith('bridges of pine')

    # Roll up all BOPC / Bridges lines (job-level Total-for rows in QB exports).
    bopc_parts = [c for c in customers if _is_bopc_name(c['customer'])]
    bopc = None
    if bopc_parts:
        bopc = {
            'customer': 'BOPC / Bridges of Pine Creek (rolled up)',
            'parts': [p['customer'] for p in bopc_parts],
            'current': sum(p['current'] for p in bopc_parts),
            '1_30': sum(p['1_30'] for p in bopc_parts),
            '31_60': sum(p['31_60'] for p in bopc_parts),
            '61_90': sum(p['61_90'] for p in bopc_parts),
            '91_and_over': sum(p['91_and_over'] for p in bopc_parts),
            'total': sum(p['total'] for p in bopc_parts),
        }

    # Operating AR: exclude BOPC full balance (common Stephanie/Thomas view)
    operating = dict(grand)
    if bopc:
        for k in ('current', '1_30', '31_60', '61_90', '91_and_over', 'total'):
            operating[k] = max(0.0, operating[k] - bopc.get(k, 0.0))

    # Chase list: prioritize 61+ and 91+, then 31-60, then 1-30 — exclude pure current
    chase = []
    for c in customers:
        overdue = c['1_30'] + c['31_60'] + c['61_90'] + c['91_and_over']
        if overdue <= 0:
            continue
        weight = (
            c['91_and_over'] * 4
            + c['61_90'] * 3
            + c['31_60'] * 2
            + c['1_30']
        )
        is_legacy = _is_bopc_name(c['customer']) or any(
            h in c['customer'].lower() for h in LEGACY_CUSTOMER_HINTS
        )
        chase.append({
            **c,
            'overdue': overdue,
            'weight': weight,
            'is_legacy_or_bopc': is_legacy,
        })
    chase.sort(key=lambda x: (-x['weight'], -x['overdue']))

    top_by_balance = customers[:15]
    top_chase = chase[:20]

    numbers_draft = _numbers_draft_md(
        as_of_label=as_of_label,
        grand=grand,
        operating=operating,
        bopc=bopc,
        top_chase=top_chase,
    )

    return {
        'report': 'A/R Aging Summary',
        'as_of_label': as_of_label,
        'source_format': source,
        'parsed_at': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        'customer_count': len(customers),
        'grand_total': grand,
        'operating_ex_bopc': operating,
        'bopc': bopc,
        'top_customers_by_balance': top_by_balance,
        'chase_list': top_chase,
        'notes_for_humans': [
            'BOPC / Bridges is split out for operating AR — confirm with Stephanie before quoting totals externally.',
            '50/50 split jobs are not auto-detected yet — flag those in Notes when you know them; we will learn the pattern.',
            'Draft is for edit/send by Stephanie — Hub does not email this automatically.',
        ],
        'numbers_draft_md': numbers_draft,
    }


def _fmt_money(n):
    try:
        v = float(n or 0)
    except (TypeError, ValueError):
        v = 0.0
    return f'${v:,.0f}'


def _numbers_draft_md(as_of_label, grand, operating, bopc, top_chase):
    as_of = as_of_label or 'this week'
    lines = [
        f'**Numbers draft** — AR snapshot ({as_of})',
        '',
        '_Edit freely. Sales vs goal still comes from your Monthly Outlook sheet — paste that block above or below._',
        '',
        '### AR snapshot',
        f'- **Total AR (all customers):** {_fmt_money(grand["total"])}',
        f'- **Current:** {_fmt_money(grand["current"])} · **1–30:** {_fmt_money(grand["1_30"])} · '
        f'**31–60:** {_fmt_money(grand["31_60"])} · **61–90:** {_fmt_money(grand["61_90"])} · '
        f'**91+:** {_fmt_money(grand["91_and_over"])}',
    ]
    if bopc:
        lines.append(
            f'- **BOPC / Bridges (included above):** {_fmt_money(bopc["total"])} '
            f'(91+: {_fmt_money(bopc["91_and_over"])})'
        )
        lines.append(
            f'- **Operating AR (ex-BOPC, rough):** {_fmt_money(operating["total"])}'
        )
    lines.extend(['', '### Collection focus (overdue-weighted)', ''])
    if not top_chase:
        lines.append('_No overdue balances detected in this export._')
    else:
        for i, c in enumerate(top_chase[:12], 1):
            tag = ' _(legacy/BOPC — handle with care)_' if c.get('is_legacy_or_bopc') else ''
            lines.append(
                f'{i}. **{c["customer"]}** — total {_fmt_money(c["total"])}, '
                f'overdue {_fmt_money(c["overdue"])} '
                f'(91+ {_fmt_money(c["91_and_over"])}){tag}'
            )
    lines.extend([
        '',
        '### Notes / 50–50 splits',
        '- _Add any 50/50 jobs or shared AR here so totals stay honest._',
        '',
        '—',
        'Generated from Office Ops · not sent automatically',
    ])
    return '\n'.join(lines)


def save_upload(get_db_fn, kind, filename, mime_type, raw_bytes, user_key):
    if kind not in ALLOWED_KINDS:
        return {'success': False, 'error': f'Unknown upload type: {kind}'}
    if not raw_bytes:
        return {'success': False, 'error': 'Empty file.'}
    if len(raw_bytes) > MAX_UPLOAD_BYTES:
        return {'success': False, 'error': f'File too large (max {MAX_UPLOAD_BYTES // (1024*1024)}MB).'}
    conn = get_db_fn()
    if not conn:
        return {'success': False, 'error': 'Database unavailable.'}
    try:
        cur = conn.cursor()
        cur.execute(
            '''
            INSERT INTO office_ops_files
                (kind, filename, mime_type, size_bytes, file_data, uploaded_by)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, uploaded_at
            ''',
            (
                kind,
                (filename or 'upload')[:255],
                (mime_type or '')[:100],
                len(raw_bytes),
                psycopg2_binary(raw_bytes),
                user_key,
            ),
        )
        row = cur.fetchone()
        file_id = row[0]
        uploaded_at = row[1]
        conn.commit()
        cur.close()
        conn.close()
        return {
            'success': True,
            'file_id': file_id,
            'uploaded_at': uploaded_at.isoformat() if uploaded_at else None,
            'filename': filename,
            'size_bytes': len(raw_bytes),
        }
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        print(f'Office Ops upload error: {e}')
        return {'success': False, 'error': 'Could not save upload.'}


def psycopg2_binary(raw_bytes):
    """Wrap bytes for BYTEA insert without importing Binary at module top if unused."""
    from psycopg2 import Binary
    return Binary(raw_bytes)


def process_ar_file(get_db_fn, file_id, user_key):
    conn = get_db_fn()
    if not conn:
        return {'success': False, 'error': 'Database unavailable.'}
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            'SELECT id, kind, filename, file_data FROM office_ops_files WHERE id = %s',
            (file_id,),
        )
        frow = cur.fetchone()
        if not frow:
            cur.close()
            conn.close()
            return {'success': False, 'error': 'Upload not found.'}
        if frow['kind'] != 'ar_aging':
            cur.close()
            conn.close()
            return {'success': False, 'error': 'Not an AR aging file.'}

        raw = bytes(frow['file_data'])
        summary = parse_ar_aging_bytes(frow['filename'], raw)
        summary['source_filename'] = frow['filename']
        summary['source_file_id'] = file_id

        pack_date = date.today()
        cur.execute(
            '''
            INSERT INTO office_ops_packs
                (pack_date, source_file_id, kind, summary_json, numbers_draft_md, created_by)
            VALUES (%s, %s, %s, %s::jsonb, %s, %s)
            RETURNING id, created_at
            ''',
            (
                pack_date,
                file_id,
                'ar_aging',
                json.dumps(summary),
                summary.get('numbers_draft_md'),
                user_key,
            ),
        )
        prow = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return {
            'success': True,
            'pack_id': prow['id'],
            'created_at': prow['created_at'].isoformat() if prow['created_at'] else None,
            'summary': summary,
        }
    except ValueError as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {'success': False, 'error': str(e)}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        print(f'Office Ops process error: {e}')
        return {'success': False, 'error': 'Could not process that AR file. Check it is a QB Aging Summary export.'}


def get_latest_pack(get_db_fn, kind='ar_aging'):
    conn = get_db_fn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            '''
            SELECT p.id, p.pack_date, p.kind, p.summary_json, p.numbers_draft_md,
                   p.created_by, p.created_at, p.source_file_id,
                   f.filename AS source_filename
            FROM office_ops_packs p
            LEFT JOIN office_ops_files f ON f.id = p.source_file_id
            WHERE p.kind = %s
            ORDER BY p.created_at DESC
            LIMIT 1
            ''',
            (kind,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return None
        summary = row['summary_json']
        if isinstance(summary, str):
            summary = json.loads(summary)
        return {
            'id': row['id'],
            'pack_date': row['pack_date'].isoformat() if row['pack_date'] else None,
            'kind': row['kind'],
            'summary': summary,
            'numbers_draft_md': row['numbers_draft_md'] or (summary or {}).get('numbers_draft_md'),
            'created_by': row['created_by'],
            'created_at': row['created_at'].isoformat() if row['created_at'] else None,
            'source_file_id': row['source_file_id'],
            'source_filename': row['source_filename'],
        }
    except Exception as e:
        print(f'Office Ops latest pack error: {e}')
        try:
            conn.close()
        except Exception:
            pass
        return None


def list_recent_files(get_db_fn, kind='ar_aging', limit=10):
    conn = get_db_fn()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            '''
            SELECT id, kind, filename, size_bytes, uploaded_by, uploaded_at
            FROM office_ops_files
            WHERE kind = %s
            ORDER BY uploaded_at DESC
            LIMIT %s
            ''',
            (kind, limit),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        out = []
        for r in rows:
            out.append({
                'id': r['id'],
                'kind': r['kind'],
                'filename': r['filename'],
                'size_bytes': r['size_bytes'],
                'uploaded_by': r['uploaded_by'],
                'uploaded_at': r['uploaded_at'].isoformat() if r['uploaded_at'] else None,
            })
        return out
    except Exception as e:
        print(f'Office Ops list files error: {e}')
        try:
            conn.close()
        except Exception:
            pass
        return []


def register_routes(app, get_db_fn, users, require_login):
    from flask import jsonify, redirect, render_template, request, session, url_for

    def _gate():
        user_key = session.get('user_key')
        if not can_access_office_ops(users, user_key):
            return redirect(url_for('dashboard'))
        return None

    @app.route('/office-ops')
    @require_login
    def office_ops_page():
        blocked = _gate()
        if blocked:
            return blocked
        user_key = session.get('user_key')
        pack = get_latest_pack(get_db_fn)
        files = list_recent_files(get_db_fn)
        return render_template(
            'office_ops.html',
            user_key=user_key,
            user_display=(users.get(user_key) or {}).get('display', user_key),
            pack=pack,
            recent_files=files,
        )

    @app.route('/api/office-ops/upload', methods=['POST'])
    @require_login
    def office_ops_upload():
        user_key = session.get('user_key')
        if not can_access_office_ops(users, user_key):
            return jsonify({'success': False, 'error': 'Not allowed.'}), 403
        kind = (request.form.get('kind') or 'ar_aging').strip()
        f = request.files.get('file')
        if not f or not f.filename:
            return jsonify({'success': False, 'error': 'Choose a file to upload.'}), 400
        raw = f.read()
        saved = save_upload(
            get_db_fn, kind, f.filename, f.mimetype or '', raw, user_key,
        )
        if not saved.get('success'):
            return jsonify(saved), 400
        # Auto-process AR on upload
        if kind == 'ar_aging':
            result = process_ar_file(get_db_fn, saved['file_id'], user_key)
            if not result.get('success'):
                return jsonify({
                    'success': False,
                    'error': result.get('error', 'Processed save failed.'),
                    'file_id': saved['file_id'],
                }), 400
            return jsonify({
                'success': True,
                'file_id': saved['file_id'],
                'pack_id': result['pack_id'],
                'summary': result['summary'],
                'numbers_draft_md': result['summary'].get('numbers_draft_md'),
            })
        return jsonify(saved)

    @app.route('/api/office-ops/latest')
    @require_login
    def office_ops_latest():
        user_key = session.get('user_key')
        if not can_access_office_ops(users, user_key):
            return jsonify({'error': 'Not allowed.'}), 403
        pack = get_latest_pack(get_db_fn)
        if not pack:
            return jsonify({'success': True, 'pack': None})
        return jsonify({'success': True, 'pack': pack})
