"""Generate Monday Numbers Excel from QB exports + frozen 2026 goals template.

Owner decisions 2026-08-04:
  - Goals stay from Monthly Outlook template (update for 2027 later).
  - Sales = invoice send date × Amount; Sales Rep 50/50 on multi-rep.
  - Draws/downpayments count here (in QB); bonuses are separate (closed jobs).
  - No A/R-by-rep; company AR + Bridges breakdown when possible.
  - Output Excel + email path; Stephanie notes via past-due prompt.
"""

from __future__ import annotations

import io
import os
import re
from collections import defaultdict
from calendar import month_abbr
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.formatting.rule import CellIsRule

from office_ops import _parse_sales_reps

TEMPLATE_PATH = Path(__file__).resolve().parent / 'static' / 'office_ops' / 'monthly_outlook_goals_template_2026.xlsx'

# Monthly Sales: label → Actual $ row
SALES_ACTUAL_ROWS = {
    'thomas ellison': 4,
    'thomas': 4,
    'tony cumella': 10,
    'tony': 10,
    'adam cupito': 16,
    'adam': 16,
    'andy potts': 22,
    'andy': 22,
    'rachel farler': 28,
    'rachel': 28,
}
SALES_SHARED_ROWS = {
    'thomas ellison': 34,
    'tony cumella': 35,
    'adam cupito': 36,
    'andy potts': 37,
    'rachel farler': 38,
}

FILL_POS = PatternFill(start_color='FFC6EFCE', end_color='FFC6EFCE', fill_type='solid')
FILL_NEG = PatternFill(start_color='FFFFC7CE', end_color='FFFFC7CE', fill_type='solid')
FILL_POS_CF = PatternFill(start_color='FFB7E1CD', end_color='FFB7E1CD', fill_type='solid')
FILL_NEG_CF = PatternFill(start_color='FFF4C7C3', end_color='FFF4C7C3', fill_type='solid')
FONT_POS = Font(color='FF006100')
FONT_NEG = Font(color='FF9C0006')
FILL_YELLOW = PatternFill(start_color='FFFFF2CC', end_color='FFFFF2CC', fill_type='solid')
FILL_HEADER = PatternFill(start_color='FF1A5276', end_color='FF1A5276', fill_type='solid')
FONT_HEADER = Font(color='FFFFFFFF', bold=True, name='Calibri', size=12)
FONT_BODY = Font(name='Calibri', size=11)
FONT_BOLD = Font(name='Calibri', size=11, bold=True)

MONTH_COLS = {1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7, 7: 8, 8: 9, 9: 10, 10: 11, 11: 12, 12: 13}


def _parse_invoice_date(val):
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    s = str(val).strip()
    for fmt in ('%m/%d/%Y', '%Y-%m-%d', '%m/%d/%y', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    return None


def aggregate_sales_from_invoice_list(invoice_list, year=2026):
    """invoice_list items: date, amount, sales_reps[], is_50_50_style.

    Returns:
      by_rep_month: {rep_full_name: {month: dollars}}
      by_rep_shared_month: multi-rep only share by rep/month
      team_month: {month: dollars}
      meta
    """
    by_rep = defaultdict(lambda: defaultdict(float))
    by_shared = defaultdict(lambda: defaultdict(float))
    team = defaultdict(float)
    count = 0
    split_count = 0
    for inv in invoice_list or []:
        dt = _parse_invoice_date(inv.get('date'))
        if not dt or dt.year != year:
            continue
        # Count full invoice amount for sales (draws count for this report)
        amt = float(inv.get('amount') or 0)
        if amt == 0:
            continue
        reps = inv.get('sales_reps') or _parse_sales_reps(inv.get('sales_rep_raw') or inv.get('salesman'))
        if not reps:
            reps = ['(unassigned)']
        share = amt / len(reps)
        m = dt.month
        team[m] += amt
        count += 1
        multi = len(reps) >= 2
        if multi:
            split_count += 1
        for r in reps:
            by_rep[r][m] += share
            if multi:
                by_shared[r][m] += share
    return {
        'by_rep_month': {k: dict(v) for k, v in by_rep.items()},
        'by_shared_month': {k: dict(v) for k, v in by_shared.items()},
        'team_month': dict(team),
        'invoice_count': count,
        'split_invoice_count': split_count,
        'year': year,
    }


def _bridges_ar_breakdown(customers):
    """Split Bridges/BOPC customers into Old / Pine-Meadow / Pebble when possible."""
    buckets = {
        'Bridges — Pebble': 0.0,
        'Bridges — Pine/Meadow': 0.0,
        'Bridges — old / other': 0.0,
    }
    parts = []
    for c in customers or []:
        name = (c.get('customer') or '')
        low = name.lower()
        if not any(x in low for x in ('bopc', 'bridges', 'pine creek', 'pebble', 'meadow')):
            continue
        total = float(c.get('total') or 0)
        parts.append(name)
        if 'pebble' in low:
            buckets['Bridges — Pebble'] += total
        elif 'pine' in low or 'meadow' in low or '2701' in low:
            buckets['Bridges — Pine/Meadow'] += total
        else:
            buckets['Bridges — old / other'] += total
    # Drop zero lines
    lines = [{'label': k, 'total': v} for k, v in buckets.items() if abs(v) > 0.5]
    if not lines and parts:
        lines = [{'label': 'Bridges / BOPC (rolled up)', 'total': sum(buckets.values())}]
    return lines, parts


def _fill_sales_sheet(ws, sales_agg):
    """Write Actual $ and Shared rows from invoice aggregation; keep Goal/Historial."""
    by_rep = sales_agg['by_rep_month']
    by_shared = sales_agg['by_shared_month']

    # Clear Shared first
    for row in SALES_SHARED_ROWS.values():
        for col in MONTH_COLS.values():
            cell = ws.cell(row, col)
            cell.value = 0
            cell.number_format = '"$"#,##0.00'
            cell.fill = FILL_YELLOW

    # Map rep names in agg to rows
    def row_for(rep_name):
        low = (rep_name or '').lower()
        if low in SALES_ACTUAL_ROWS:
            return SALES_ACTUAL_ROWS[low]
        for k, r in SALES_ACTUAL_ROWS.items():
            if k in low or low in k:
                return r
        return None

    # Zero all actual months then fill
    for rep, months in by_rep.items():
        r = row_for(rep)
        if not r:
            continue
        for m in range(1, 13):
            col = MONTH_COLS[m]
            cell = ws.cell(r, col)
            val = months.get(m, 0.0)
            cell.value = round(val, 2) if val else 0
            cell.number_format = '"$"#,##0.00'
            cell.fill = FILL_YELLOW
        # Full year col N = 14 if used
        if ws.cell(r, 14).value is not None or True:
            total = sum(months.get(m, 0) for m in range(1, 13))
            ws.cell(r, 14).value = round(total, 2)
            ws.cell(r, 14).number_format = '"$"#,##0.00'

    for rep, months in by_shared.items():
        r = SALES_SHARED_ROWS.get(rep) or SALES_SHARED_ROWS.get(
            next((k for k in SALES_SHARED_ROWS if k.split()[0].lower() in rep.lower()), None)
        )
        # direct map
        low = rep.lower()
        r = None
        for k, row in SALES_SHARED_ROWS.items():
            if k in low or low in k or k.split()[0] == low.split()[0]:
                r = row
                break
        if not r:
            continue
        for m, val in months.items():
            col = MONTH_COLS.get(m)
            if not col:
                continue
            cell = ws.cell(r, col)
            cell.value = round(val, 2)
            cell.number_format = '"$"#,##0.00'


def _fill_team_sheet(ws, sales_agg):
    """2026 Actual $ row 13 from team_month; leave 2025 and goals alone."""
    team = sales_agg['team_month']
    # 2026 block starts row 9; Actual $ is row 13
    for m in range(1, 13):
        col = MONTH_COLS[m]
        cell = ws.cell(13, col)
        val = team.get(m, 0.0)
        cell.value = round(val, 2) if val else None
        if val:
            cell.number_format = '"$"#,##0.00'
            cell.fill = FILL_YELLOW
    # Full year sum formula
    ws.cell(13, 14).value = '=SUM(B13:M13)'
    ws.cell(13, 14).number_format = '"$"#,##0.00'


def _build_insights(sales_agg, ar_summary, notes_by_customer=None):
    lines = []
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    lines.append(f'Office Ops · Monday Numbers insights · generated {now}')
    lines.append('')
    lines.append(
        '_Sales = invoiced amount by invoice date (includes draws/downpayments for this '
        'report). Quarterly bonuses still use closed/completed jobs — not changed here._'
    )
    lines.append('')

    team = sales_agg.get('team_month') or {}
    if team:
        months = sorted(team.keys())
        latest = months[-1] if months else None
        ytd = sum(team.values())
        lines.append('## Team invoiced (from Invoice List)')
        lines.append(f'- **YTD invoiced:** ${_money(ytd)}')
        if latest:
            lines.append(
                f'- **Latest month ({month_abbr[latest]}):** ${_money(team[latest])}'
            )
        lines.append(
            f'- Invoices counted: {sales_agg.get("invoice_count", 0)} · '
            f'50/50-style splits: {sales_agg.get("split_invoice_count", 0)}'
        )
        lines.append('')

    by_rep = sales_agg.get('by_rep_month') or {}
    if by_rep:
        lines.append('## By sales rep (YTD invoiced; multi-rep = equal 50/50 share)')
        ranked = sorted(
            ((r, sum(m.values())) for r, m in by_rep.items()),
            key=lambda x: -x[1],
        )
        for r, tot in ranked:
            if r == '(unassigned)':
                continue
            lines.append(f'- **{r}:** ${_money(tot)}')
        lines.append('')

    lines.append('## A/R (company total — Stephanie owns collections)')
    if ar_summary and ar_summary.get('grand_total'):
        g = ar_summary['grand_total']
        lines.append(f'- **Total AR:** ${_money(g.get("total"))}')
        lines.append(
            f'- Current ${_money(g.get("current"))} · 1–30 ${_money(g.get("1_30"))} · '
            f'31–60 ${_money(g.get("31_60"))} · 61–90 ${_money(g.get("61_90"))} · '
            f'91+ ${_money(g.get("91_and_over"))}'
        )
        bridges = ar_summary.get('bridges_lines') or []
        if bridges:
            for b in bridges:
                lines.append(f'- **{b["label"]}:** ${_money(b["total"])}')
        elif ar_summary.get('bopc'):
            lines.append(
                f'- **Bridges / BOPC (rolled up):** ${_money(ar_summary["bopc"].get("total"))}'
            )
    else:
        lines.append('- _Upload A/R Aging Summary to fill totals._')
    lines.append('')

    if notes_by_customer:
        lines.append('## Past-due updates (Stephanie)')
        for cust, note in notes_by_customer.items():
            if note and str(note).strip():
                lines.append(f'- **{cust}:** {note.strip()}')
        lines.append('')

    lines.append('—')
    lines.append('Thursday pack · goals from 2026 Outlook template · actuals from QB Invoice List')
    return '\n'.join(lines)


def _money(n):
    try:
        return f'{float(n or 0):,.0f}'
    except (TypeError, ValueError):
        return '0'


def generate_from_qb(invoice_list, ar_summary=None, notes_by_customer=None, year=2026, template_path=None):
    """Build Monday Excel bytes from Invoice List + AR pack + optional past-due notes."""
    path = Path(template_path or TEMPLATE_PATH)
    if not path.exists():
        raise FileNotFoundError(f'Goals template missing: {path}')

    sales_agg = aggregate_sales_from_invoice_list(invoice_list, year=year)

    # Enrich AR summary with bridges breakdown
    ar = dict(ar_summary or {})
    if ar.get('top_customers_by_balance') or ar.get('chase_list'):
        customers = ar.get('top_customers_by_balance') or []
        # also use all customers if present
        if ar.get('chase_list'):
            # chase is subset; prefer full list if we stored it
            pass
        lines, parts = _bridges_ar_breakdown(
            ar.get('all_customers') or ar.get('top_customers_by_balance') or ar.get('chase_list')
        )
        ar['bridges_lines'] = lines
        ar['bridges_source_names'] = parts

    wb = load_workbook(path)

    # Drop Profit and Margin unless we later merge P&L
    if 'Profit and Margin' in wb.sheetnames:
        del wb['Profit and Margin']

    if 'Monthly Sales' in wb.sheetnames:
        _fill_sales_sheet(wb['Monthly Sales'], sales_agg)
        _ensure_cf(wb['Monthly Sales'], 'B5:M6', le=True)
        _ensure_cf(wb['Monthly Sales'], 'B11:M12', le=True)
        _ensure_cf(wb['Monthly Sales'], 'B17:M18', le=True)
        _ensure_cf(wb['Monthly Sales'], 'B23:M24', le=True)
        _ensure_cf(wb['Monthly Sales'], 'C29:M30', le=True)

    if 'Monthly Team' in wb.sheetnames:
        _fill_team_sheet(wb['Monthly Team'], sales_agg)
        _ensure_cf(wb['Monthly Team'], 'B6:M7')
        _ensure_cf(wb['Monthly Team'], 'B14:M15', le=True)

    if 'Quarterly Breakdowns' in wb.sheetnames:
        _ensure_cf(wb['Quarterly Breakdowns'], 'B4:E5')
        _ensure_cf(wb['Quarterly Breakdowns'], 'D8:D19')
        _ensure_cf(wb['Quarterly Breakdowns'], 'I8:I19')

    # Re-open data_only won't work without Excel cache for new values —
    # paint Difference rows by computing from filled Actual vs Goal where possible
    _paint_computed_diffs(wb)

    insights = _build_insights(sales_agg, ar, notes_by_customer=notes_by_customer)

    if 'Insights' in wb.sheetnames:
        del wb['Insights']
    ws_i = wb.create_sheet('Insights', 0)
    ws_i['A1'] = 'Monday Numbers · Insights'
    ws_i['A1'].font = FONT_HEADER
    ws_i['A1'].fill = FILL_HEADER
    ws_i.merge_cells('A1:B1')
    ws_i.column_dimensions['A'].width = 110
    for i, line in enumerate(insights.splitlines(), start=3):
        cell = ws_i.cell(i, 1, line)
        cell.font = Font(name='Calibri', size=12, bold=True, color='FF1A5276') if line.startswith('## ') else FONT_BODY

    if 'AR Totals' in wb.sheetnames:
        del wb['AR Totals']
    ws_ar = wb.create_sheet('AR Totals', 1)
    ws_ar['A1'] = 'Company A/R — Stephanie owns collections (not by rep)'
    ws_ar['A1'].font = FONT_HEADER
    ws_ar['A1'].fill = FILL_HEADER
    ws_ar.merge_cells('A1:C1')
    ws_ar['A3'] = 'Bucket'
    ws_ar['B3'] = 'Amount'
    ws_ar['A3'].fill = FILL_YELLOW
    ws_ar['B3'].fill = FILL_YELLOW
    if ar.get('grand_total'):
        g = ar['grand_total']
        rows = [
            ('Current', g.get('current')),
            ('1–30', g.get('1_30')),
            ('31–60', g.get('31_60')),
            ('61–90', g.get('61_90')),
            ('91+', g.get('91_and_over')),
            ('TOTAL AR', g.get('total')),
        ]
        for i, (lab, amt) in enumerate(rows, 4):
            ws_ar.cell(i, 1, lab)
            c = ws_ar.cell(i, 2, float(amt or 0))
            c.number_format = '"$"#,##0'
            if lab == 'TOTAL AR':
                ws_ar.cell(i, 1).font = FONT_BOLD
                c.font = FONT_BOLD
        r = 11
        for b in ar.get('bridges_lines') or []:
            ws_ar.cell(r, 1, b['label'])
            c = ws_ar.cell(r, 2, float(b['total'] or 0))
            c.number_format = '"$"#,##0'
            r += 1
        if notes_by_customer:
            r += 1
            ws_ar.cell(r, 1, 'Past-due notes')
            ws_ar.cell(r, 1).font = FONT_BOLD
            r += 1
            for cust, note in notes_by_customer.items():
                if note and str(note).strip():
                    ws_ar.cell(r, 1, cust)
                    ws_ar.cell(r, 2, str(note).strip())
                    r += 1
    else:
        ws_ar['A4'] = 'Upload A/R Aging Summary to populate.'
    ws_ar.column_dimensions['A'].width = 40
    ws_ar.column_dimensions['B'].width = 48

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue(), insights, {
        'sales_agg': {
            'invoice_count': sales_agg['invoice_count'],
            'split_invoice_count': sales_agg['split_invoice_count'],
            'team_ytd': sum(sales_agg['team_month'].values()),
            'by_rep_ytd': {r: sum(m.values()) for r, m in sales_agg['by_rep_month'].items()},
        },
        'generated_at': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
    }


def _paint_computed_diffs(wb):
    """After writing Actual values, compute Difference/% hit cells as values with colors."""
    if 'Monthly Sales' not in wb.sheetnames:
        return
    ws = wb['Monthly Sales']
    # For each rep block: Actual row R, Goal R-1, Diff R+1, Pct R+2
    blocks = [(4, 3, 5, 6), (10, 9, 11, 12), (16, 15, 17, 18), (22, 21, 23, 24), (28, 27, 29, 30)]
    for actual_r, goal_r, diff_r, pct_r in blocks:
        for m, col in MONTH_COLS.items():
            try:
                actual = float(ws.cell(actual_r, col).value or 0)
            except (TypeError, ValueError):
                actual = 0.0
            goal_raw = ws.cell(goal_r, col).value
            try:
                if isinstance(goal_raw, str) and goal_raw.startswith('='):
                    # leave formula for goal; read cached or skip paint for formula-only
                    goal = None
                else:
                    goal = float(goal_raw or 0) if goal_raw not in ('$ -', '', None) else 0.0
            except (TypeError, ValueError):
                goal = 0.0
            if goal is None:
                continue
            diff = actual - goal
            dcell = ws.cell(diff_r, col, round(diff, 2))
            dcell.number_format = '"$"#,##0.00'
            if diff > 0:
                dcell.fill = FILL_POS
                dcell.font = Font(color='FF006100', name='Calibri', size=11)
            elif diff < 0:
                dcell.fill = FILL_NEG
                dcell.font = Font(color='FF9C0006', name='Calibri', size=11)
            if goal:
                pct = diff / goal
                pcell = ws.cell(pct_r, col, pct)
                pcell.number_format = '0%'
                if pct > 0:
                    pcell.fill = FILL_POS
                    pcell.font = Font(color='FF006100', name='Calibri', size=11)
                elif pct < 0:
                    pcell.fill = FILL_NEG
                    pcell.font = Font(color='FF9C0006', name='Calibri', size=11)

    if 'Monthly Team' in wb.sheetnames:
        ws = wb['Monthly Team']
        # 2026 Actual row 13, Goal row 11 (formulas from %), Diff 14, Pct 15
        for m, col in MONTH_COLS.items():
            actual = ws.cell(13, col).value
            if actual is None:
                continue
            try:
                actual = float(actual)
            except (TypeError, ValueError):
                continue
            # Goal $ may be formula — use Goal % * 10M from N11
            try:
                annual = float(ws.cell(11, 14).value or 10000000)
            except (TypeError, ValueError):
                annual = 10000000.0
            goal_pct = ws.cell(10, col).value
            try:
                goal = float(goal_pct) * annual if goal_pct is not None else 0.0
            except (TypeError, ValueError):
                goal = 0.0
            diff = actual - goal
            dcell = ws.cell(14, col, round(diff, 2))
            dcell.number_format = '"$"#,##0.00'
            if diff > 0:
                dcell.fill = FILL_POS
                dcell.font = Font(color='FF006100', name='Calibri', size=11)
            elif diff < 0:
                dcell.fill = FILL_NEG
                dcell.font = Font(color='FF9C0006', name='Calibri', size=11)
            if goal:
                pct = diff / goal
                pcell = ws.cell(15, col, pct)
                pcell.number_format = '0%'
                if pct > 0:
                    pcell.fill = FILL_POS
                    pcell.font = Font(color='FF006100', name='Calibri', size=11)
                elif pct < 0:
                    pcell.fill = FILL_NEG
                    pcell.font = Font(color='FF9C0006', name='Calibri', size=11)


def _ensure_cf(ws, rng, le=False):
    ws.conditional_formatting.add(
        rng,
        CellIsRule(operator='greaterThan', formula=['0'], fill=FILL_POS_CF, font=FONT_POS),
    )
    op = 'lessThanOrEqual' if le else 'lessThan'
    ws.conditional_formatting.add(
        rng,
        CellIsRule(operator=op, formula=['0'], fill=FILL_NEG_CF, font=FONT_NEG),
    )
