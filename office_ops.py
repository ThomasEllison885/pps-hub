"""Office Ops — Stephanie + Thomas workspace for AR digests and weekly Numbers.

Owner request 2026-08-03 / build-out 2026-08:
  - Access: office_manager (Stephanie) + admin (Thomas) only.
  - Files land via Hub upload (Postgres), not a shared team vault dump.
  - AR Aging Summary → totals / chase list / Numbers draft skeleton.
  - AR Aging Detail → open invoices by age bucket (invoice-level chase).
  - Later: sticky notes, salesman/50-50 from invoice custom field, Sub Info,
    Outlook sheet, Gmail drafts.

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
# ar_aging kept for early uploads; new kinds are explicit.
ALLOWED_KINDS = frozenset({
    'ar_aging',
    'ar_aging_summary',
    'ar_aging_detail',
})
KIND_SUMMARY = 'ar_aging_summary'
KIND_DETAIL = 'ar_aging_detail'
PACK_KIND = 'ar_aging'  # combined pack stored after either upload

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


def _is_summary_header_row(cells):
    """QB A/R Aging Summary: CURRENT | 1-30 | … | Total (customer in col 0)."""
    joined = ' '.join(_norm_header(c) for c in cells if c is not None)
    has_current = 'current' in joined
    has_1_30 = bool(re.search(r'1\s*[-–—]\s*30', joined) or '1-30' in joined)
    has_total = 'total' in joined
    # Some exports use "Not yet due" instead of CURRENT
    has_not_yet = 'not yet due' in joined
    return (has_current or has_not_yet) and has_1_30 and has_total


def _is_detail_header_row(cells):
    """QB A/R Aging Detail: Date | Transaction type | Num | Customer full name | …"""
    joined = ' '.join(_norm_header(c) for c in cells if c is not None)
    return (
        'transaction type' in joined
        or ('date' in joined and 'customer' in joined and 'open balance' in joined)
        or ('customer full name' in joined and 'open balance' in joined)
    )


# Back-compat name used by older call sites
def _is_header_row(cells):
    return _is_summary_header_row(cells)


def detect_ar_report_type(filename, raw_bytes):
    """Return 'summary' | 'detail' | None from filename + content peek."""
    name = (filename or '').lower()
    if 'detail' in name:
        return 'detail'
    if 'summary' in name:
        return 'summary'

    # Peek rows without full parse
    rows = _load_tabular_rows(filename, raw_bytes, max_rows=30)
    for row in rows:
        if _is_detail_header_row(row):
            return 'detail'
        if _is_summary_header_row(row):
            return 'summary'
    # Title rows
    for row in rows[:5]:
        joined = ' '.join(str(c) for c in row if c).lower()
        if 'aging detail' in joined:
            return 'detail'
        if 'aging summary' in joined:
            return 'summary'
    return None


def _load_tabular_rows(filename, raw_bytes, max_rows=None):
    name = (filename or '').lower()
    if name.endswith('.csv') or name.endswith('.txt'):
        text = raw_bytes.decode('utf-8-sig', errors='replace')
        reader = csv.reader(io.StringIO(text))
        rows = []
        for i, row in enumerate(reader):
            rows.append(row)
            if max_rows and i + 1 >= max_rows:
                break
        return rows
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), data_only=True, read_only=True)
    ws = wb.active
    rows = []
    for i, row in enumerate(ws.iter_rows(values_only=True), 1):
        rows.append(list(row))
        if max_rows and i >= max_rows:
            break
    wb.close()
    return rows


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


def parse_ar_aging_bytes(filename, raw_bytes, expect=None):
    """Parse AR export. expect: 'summary' | 'detail' | None (auto-detect).

    Returns a summary-shaped dict; detail also includes 'invoices' and report type.
    """
    detected = detect_ar_report_type(filename, raw_bytes)
    kind = expect or detected
    if expect and detected and expect != detected:
        raise ValueError(
            f'This file looks like an A/R Aging {detected.title()} export, '
            f'but it was uploaded as {expect.title()}. '
            f'Use the matching drop zone (or upload again — we will auto-detect).'
        )
    if kind == 'detail':
        return _parse_ar_detail(filename, raw_bytes)
    if kind == 'summary':
        name = (filename or '').lower()
        if name.endswith('.csv') or name.endswith('.txt'):
            return _parse_ar_csv(raw_bytes)
        return _parse_ar_xlsx(raw_bytes)
    # Unknown
    raise ValueError(
        'Could not tell Summary from Detail. Export from QuickBooks:\n'
        '• A/R Aging Summary — columns CURRENT / 1-30 / … / Total\n'
        '• A/R Aging Detail — columns Date / Transaction type / Customer / Open balance\n'
        'Then use the matching upload box on Office Ops.'
    )


def _parse_ar_csv(raw_bytes):
    text = raw_bytes.decode('utf-8-sig', errors='replace')
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise ValueError('CSV is empty.')
    header_idx = 0
    for i, row in enumerate(rows[:20]):
        if _is_summary_header_row(row) or any(_norm_header(c) == 'customer' for c in row):
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
        if _is_summary_header_row(row):
            header_idx = i
            break
    if header_idx is None:
        # Common mistake: Detail file in Summary slot
        for row in rows[:15]:
            if _is_detail_header_row(row):
                raise ValueError(
                    'This is an A/R Aging Detail export, not Summary. '
                    'Use the “Aging Detail” upload box (invoice-level), '
                    'or export Reports → A/R Aging Summary for totals.'
                )
        raise ValueError(
            'Could not find an A/R Aging Summary header row '
            '(expected CURRENT / 1-30 / Total). '
            'In QuickBooks: Reports → Who owes you → A/R Aging Summary → Export to Excel.'
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
    out = _build_summary(customers, as_of_label=as_of_label, source='xlsx')
    out['report'] = 'A/R Aging Summary'
    out['report_kind'] = 'summary'
    return out


def _bucket_from_section_label(label):
    n = _norm_header(label)
    if not n:
        return None
    if n.startswith('total for'):
        return None
    if '91' in n or 'or more' in n:
        return '91_and_over'
    if re.search(r'61\s*[-–—]\s*90', n):
        return '61_90'
    if re.search(r'31\s*[-–—]\s*60', n):
        return '31_60'
    if re.search(r'1\s*[-–—]\s*30', n):
        return '1_30'
    if n == 'current' or 'not yet due' in n:
        return 'current'
    return None


def _parse_ar_detail(filename, raw_bytes):
    """Parse QB A/R Aging Detail into customer rollup + invoice list."""
    rows = _load_tabular_rows(filename, raw_bytes)
    if not rows:
        raise ValueError('Detail spreadsheet is empty.')

    as_of_label = None
    for row in rows[:8]:
        for cell in row:
            if cell and isinstance(cell, str) and cell.strip().lower().startswith('as of'):
                as_of_label = cell.strip()
                break

    header_idx = None
    for i, row in enumerate(rows[:25]):
        if _is_detail_header_row(row):
            header_idx = i
            break
    if header_idx is None:
        for row in rows[:15]:
            if _is_summary_header_row(row):
                raise ValueError(
                    'This is an A/R Aging Summary export, not Detail. '
                    'Use the “Aging Summary” upload box for totals.'
                )
        raise ValueError(
            'Could not find an A/R Aging Detail header '
            '(expected Date / Transaction type / Customer / Open balance). '
            'In QuickBooks: Reports → Who owes you → A/R Aging Detail → Export to Excel.'
        )

    header = rows[header_idx]
    # Map columns (Detail often has a blank leading column)
    col = {}
    for i, h in enumerate(header):
        n = _norm_header(h)
        if not n:
            continue
        if n == 'date' or n.endswith(' date') and 'due' not in n:
            col.setdefault('date', i)
        elif 'transaction' in n or n == 'type':
            col['type'] = i
        elif n in ('num', 'no.', 'number', '#') or n == 'num':
            col['num'] = i
        elif 'customer' in n:
            col['customer'] = i
        elif 'due' in n:
            col['due'] = i
        elif n == 'amount':
            col['amount'] = i
        elif 'open' in n and 'balance' in n:
            col['open'] = i
        elif 'sales' in n or 'rep' in n or n in ('salesman', 'salesperson', 'sales rep'):
            col['salesman'] = i
        elif 'memo' in n or 'description' in n or 'product' in n or 'service' in n:
            col.setdefault('memo', i)

    if 'customer' not in col:
        raise ValueError('Detail export missing Customer column.')
    if 'open' not in col and 'amount' not in col:
        raise ValueError('Detail export missing Open balance / Amount column.')

    def cell(row, key):
        idx = col.get(key)
        if idx is None or idx >= len(row):
            return None
        return row[idx]

    current_bucket = 'current'
    invoices = []
    by_customer = {}

    for row in rows[header_idx + 1:]:
        if not row or all(v in (None, '') for v in row):
            continue
        # Section labels live in first non-empty cell
        first = next((str(v).strip() for v in row if v not in (None, '')), '')
        if first.upper() == 'TOTAL' or first.lower().startswith('total for'):
            # Prefer TOTAL open-balance if present
            continue
        bucket_hit = _bucket_from_section_label(first)
        if bucket_hit and cell(row, 'type') in (None, ''):
            current_bucket = bucket_hit
            continue

        txn = cell(row, 'type')
        if txn is None:
            continue
        txn_s = str(txn).strip()
        if txn_s.lower() not in ('invoice', 'credit memo', 'payment', 'journal entry', 'deposit', 'cheque', 'check', 'sales receipt'):
            # Still allow rows that look like invoices via open balance + customer
            if not cell(row, 'customer'):
                continue
        cust_raw = cell(row, 'customer')
        if not cust_raw:
            continue
        cust = str(cust_raw).strip()
        open_bal = _money(cell(row, 'open') if col.get('open') is not None else cell(row, 'amount'))
        if open_bal == 0 and str(txn_s).lower() != 'invoice':
            continue
        # Credit memos reduce AR
        if str(txn_s).lower() == 'credit memo' and open_bal > 0:
            open_bal = -open_bal

        inv = {
            'date': str(cell(row, 'date') or ''),
            'type': txn_s,
            'num': str(cell(row, 'num') or ''),
            'customer': cust,
            'due_date': str(cell(row, 'due') or ''),
            'amount': _money(cell(row, 'amount')),
            'open_balance': open_bal,
            'age_bucket': current_bucket,
            'salesman': str(cell(row, 'salesman') or '').strip() or None,
            'memo': str(cell(row, 'memo') or '').strip() or None,
        }
        # Heuristic: salesman on a free-text line (e.g. "Sales: Andy / Adam")
        if not inv['salesman'] and inv['memo']:
            m = re.search(
                r'(?:sales(?:man|person| rep)?|psc|consultant)\s*[:\-]\s*(.+)$',
                inv['memo'],
                re.I,
            )
            if m:
                inv['salesman'] = m.group(1).strip()[:120]

        if str(txn_s).lower() != 'invoice' and open_bal == 0:
            continue
        invoices.append(inv)

        # Parent customer before ":" for rollups
        parent = cust.split(':', 1)[0].strip()
        slot = by_customer.setdefault(parent, {
            'customer': parent,
            'current': 0.0,
            '1_30': 0.0,
            '31_60': 0.0,
            '61_90': 0.0,
            '91_and_over': 0.0,
            'total': 0.0,
            'invoice_count': 0,
        })
        b = current_bucket if current_bucket in slot else 'current'
        slot[b] = slot.get(b, 0.0) + open_bal
        slot['total'] += open_bal
        slot['invoice_count'] += 1

    customers = sorted(by_customer.values(), key=lambda x: -x['total'])
    out = _build_summary(customers, as_of_label=as_of_label, source='detail_xlsx')
    out['report'] = 'A/R Aging Detail'
    out['report_kind'] = 'detail'
    out['invoices'] = invoices[:500]  # cap payload
    out['invoice_count'] = len(invoices)
    out['invoices_truncated'] = max(0, len(invoices) - 500)
    # Salesman coverage
    with_sales = sum(1 for i in invoices if i.get('salesman'))
    out['salesman_field_present'] = with_sales > 0
    out['salesman_invoice_count'] = with_sales
    if with_sales == 0:
        out['notes_for_humans'] = list(out.get('notes_for_humans') or []) + [
            'No salesman/rep column found on this Detail export. '
            'If salesmen are stored as a custom field or invoice line in QB, '
            'export that field (or we parse a “Sales: Name” description line once the export includes it).',
        ]
    return out


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


def _merge_pack_payload(existing, incoming):
    """Combine summary totals with detail invoices when both have been uploaded."""
    if not existing:
        return incoming
    if not incoming:
        return existing
    # Prefer Summary for money buckets; always prefer newer of same kind
    out = dict(existing)
    inc_kind = incoming.get('report_kind')
    if inc_kind == 'summary' or (incoming.get('report') or '').lower().find('summary') >= 0:
        for k in (
            'grand_total', 'operating_ex_bopc', 'bopc', 'top_customers_by_balance',
            'chase_list', 'customer_count', 'as_of_label', 'numbers_draft_md',
            'notes_for_humans', 'source_format', 'report',
        ):
            if k in incoming:
                out[k] = incoming[k]
        out['report_kind'] = 'summary'
        out['summary_source_filename'] = incoming.get('source_filename')
        out['summary_source_file_id'] = incoming.get('source_file_id')
    if inc_kind == 'detail' or incoming.get('invoices') is not None:
        out['invoices'] = incoming.get('invoices') or []
        out['invoice_count'] = incoming.get('invoice_count', len(out['invoices']))
        out['invoices_truncated'] = incoming.get('invoices_truncated', 0)
        out['salesman_field_present'] = incoming.get('salesman_field_present', False)
        out['salesman_invoice_count'] = incoming.get('salesman_invoice_count', 0)
        out['detail_source_filename'] = incoming.get('source_filename')
        out['detail_source_file_id'] = incoming.get('source_file_id')
        out['detail_as_of_label'] = incoming.get('as_of_label')
        # If we only have detail so far, use its rollup as the pack
        if not out.get('grand_total'):
            for k in (
                'grand_total', 'operating_ex_bopc', 'bopc', 'top_customers_by_balance',
                'chase_list', 'customer_count', 'as_of_label', 'numbers_draft_md',
                'notes_for_humans', 'report',
            ):
                if k in incoming:
                    out[k] = incoming[k]
            out['report_kind'] = 'detail'
        # Attach sample open invoices onto chase rows (match parent or job name)
        inv_by_key = {}
        for inv in out.get('invoices') or []:
            full = (inv.get('customer') or '').strip()
            parent = full.split(':', 1)[0].strip()
            job = full.split(':', 1)[1].strip() if ':' in full else ''
            for key in filter(None, (full.lower(), parent.lower(), job.lower())):
                inv_by_key.setdefault(key, []).append(inv)
        for c in out.get('chase_list') or []:
            key = (c.get('customer') or '').strip().lower()
            samples = inv_by_key.get(key, [])[:5]
            if not samples:
                # soft match: any invoice whose full name contains chase name
                samples = [
                    i for i in (out.get('invoices') or [])
                    if key and key in (i.get('customer') or '').lower()
                ][:5]
            c['sample_invoices'] = [
                {
                    'num': i.get('num'),
                    'open_balance': i.get('open_balance'),
                    'age_bucket': i.get('age_bucket'),
                    'due_date': i.get('due_date'),
                    'salesman': i.get('salesman'),
                }
                for i in samples
            ]
        # Rebuild numbers draft if we have totals
        if out.get('grand_total'):
            out['numbers_draft_md'] = _numbers_draft_md(
                as_of_label=out.get('as_of_label'),
                grand=out['grand_total'],
                operating=out.get('operating_ex_bopc') or out['grand_total'],
                bopc=out.get('bopc'),
                top_chase=out.get('chase_list') or [],
            )
    out['parsed_at'] = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    out['sources'] = {
        'summary': out.get('summary_source_filename'),
        'detail': out.get('detail_source_filename'),
    }
    return out


def process_ar_file(get_db_fn, file_id, user_key, expect=None):
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
        if frow['kind'] not in ALLOWED_KINDS:
            cur.close()
            conn.close()
            return {'success': False, 'error': 'Not an AR aging file.'}

        # Prefer explicit kind from upload slot
        kind_hint = frow['kind']
        if expect is None:
            if kind_hint == KIND_DETAIL:
                expect = 'detail'
            elif kind_hint in (KIND_SUMMARY, 'ar_aging'):
                expect = 'summary'

        raw = bytes(frow['file_data'])
        # Auto-correct kind if content disagrees (user used wrong box)
        detected = detect_ar_report_type(frow['filename'], raw)
        if detected and expect and detected != expect:
            expect = detected  # trust content; still process successfully

        parsed = parse_ar_aging_bytes(frow['filename'], raw, expect=expect)
        parsed['source_filename'] = frow['filename']
        parsed['source_file_id'] = file_id

        # Merge with latest combined pack if present
        cur.execute(
            '''
            SELECT summary_json FROM office_ops_packs
            WHERE kind = %s
            ORDER BY created_at DESC LIMIT 1
            ''',
            (PACK_KIND,),
        )
        prev = cur.fetchone()
        existing = None
        if prev and prev.get('summary_json'):
            existing = prev['summary_json']
            if isinstance(existing, str):
                existing = json.loads(existing)
        merged = _merge_pack_payload(existing, parsed)

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
                PACK_KIND,
                json.dumps(merged),
                merged.get('numbers_draft_md'),
                user_key,
            ),
        )
        prow = cur.fetchone()
        # Fix stored file kind if auto-detected differently
        if detected:
            fixed = KIND_DETAIL if detected == 'detail' else KIND_SUMMARY
            if frow['kind'] != fixed:
                cur.execute(
                    'UPDATE office_ops_files SET kind = %s WHERE id = %s',
                    (fixed, file_id),
                )
        conn.commit()
        cur.close()
        conn.close()
        return {
            'success': True,
            'pack_id': prow['id'],
            'created_at': prow['created_at'].isoformat() if prow['created_at'] else None,
            'summary': merged,
            'detected': detected or expect,
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
        return {
            'success': False,
            'error': (
                'Could not process that AR file. '
                'Use A/R Aging Summary for totals and A/R Aging Detail for invoices.'
            ),
        }


def get_latest_pack(get_db_fn, kind=None):
    kind = kind or PACK_KIND
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


def list_recent_files(get_db_fn, kind=None, limit=12):
    conn = get_db_fn()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if kind:
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
        else:
            cur.execute(
                '''
                SELECT id, kind, filename, size_bytes, uploaded_by, uploaded_at
                FROM office_ops_files
                WHERE kind IN %s
                ORDER BY uploaded_at DESC
                LIMIT %s
                ''',
                (tuple(ALLOWED_KINDS), limit),
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
        kind = (request.form.get('kind') or KIND_SUMMARY).strip()
        # Map UI kinds
        if kind in ('summary', 'ar_summary'):
            kind = KIND_SUMMARY
        elif kind in ('detail', 'ar_detail'):
            kind = KIND_DETAIL
        f = request.files.get('file')
        if not f or not f.filename:
            return jsonify({'success': False, 'error': 'Choose a file to upload.'}), 400
        raw = f.read()
        # Content wins over wrong drop-zone label
        detected = detect_ar_report_type(f.filename, raw)
        if detected == 'detail':
            kind = KIND_DETAIL
        elif detected == 'summary':
            kind = KIND_SUMMARY
        saved = save_upload(
            get_db_fn, kind, f.filename, f.mimetype or '', raw, user_key,
        )
        if not saved.get('success'):
            return jsonify(saved), 400
        expect = 'detail' if kind == KIND_DETAIL else 'summary'
        result = process_ar_file(get_db_fn, saved['file_id'], user_key, expect=expect)
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
            'detected': result.get('detected') or expect,
            'summary': result['summary'],
            'numbers_draft_md': result['summary'].get('numbers_draft_md'),
        })

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
