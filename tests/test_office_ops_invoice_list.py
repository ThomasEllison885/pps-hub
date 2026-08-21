"""Invoice List parser — QB 2026 report redesign.

No Postgres. Builds tiny xlsx fixtures in memory.
Run: python -m pytest tests/test_office_ops_invoice_list.py -v
"""
import io
import os
import sys
from datetime import date, datetime

import openpyxl
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import office_ops as oo
from office_ops_generate import _parse_invoice_date, aggregate_sales_from_invoice_list


def _xlsx(rows, sheet='Sheet1'):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


OLD_STYLE = [
    ['PPSOH LLC'],
    ['Invoice List by Date'],
    ['January 1 - August 13, 2026'],
    [],
    [None, 'Date', 'Transaction Type', 'Num', 'Name', 'Memo/Description', 'Due Date', 'Amount', 'Open Balance', 'Sales Rep'],
    ['Adam / Andy'],
    [None, '01/08/2026', 'Invoice', 6561, 'Morgan Properties', None, '02/07/2026', 42394.6, 0.0, 'Adam / Andy'],
    [None, '08/10/2026', 'Invoice', 7201, 'Connor Group', None, '09/09/2026', 5000.0, 5000.0, 'Tony'],
]


# QB 2026: no Sales Rep column — groups invoices under a section header.
GROUPED_BY_REP = [
    ['PPSOH LLC'],
    ['Invoice List by Date'],
    ['January 1-August 13, 2026'],
    [],
    [None, 'Date', 'Transaction Type', 'Num', 'Name', 'Memo/Description', 'Due Date', 'Amount', 'Open Balance'],
    ['Adam / Andy'],
    [None, '01/08/2026', 'Invoice', 6561, 'Morgan Properties', None, '02/07/2026', 42394.6, 0.0],
    [None, '01/08/2026', 'Invoice', 6568, 'Morgan Properties', None, '02/07/2026', 2000.0, 0.0],
    ['Total for Adam / Andy', None, None, None, None, None, None, 44394.6, 0.0],
    ['Tony'],
    [None, '08/10/2026', 'Invoice', 7201, 'Connor Group', None, '09/09/2026', 5000.0, 5000.0],
    ['Total for Tony', None, None, None, None, None, None, 5000.0, 5000.0],
]


# Stephanie's manual flatten: headers on row 1, group labels still in the sheet.
MANUAL_EXCEL = [
    ['Date', 'Transaction Type', 'Num', 'Name', 'Amount', 'Open Balance'],
    ['Adam / Andy'],
    ['01/08/2026', 'Invoice', 6561, 'Morgan Properties', 42394.6, 0.0],
    ['Tony Cumella'],
    ['08/10/2026', 'Invoice', 7201, 'Connor Group', 5000.0, 5000.0],
]


NEW_NO_SALES = [
    ['PPSOH LLC'],
    ['Invoice List by Date'],
    ['January 1-August 13, 2026'],
    [],
    [None, 'Transaction date', 'Transaction type', 'Num', 'Customer', 'Due date', 'Amount', 'Open balance'],
    [None, datetime(2026, 1, 8), 'Invoice', '6561', 'Morgan Properties', datetime(2026, 2, 7), 42394.6, 0.0],
    [None, date(2026, 8, 10), 'Invoice', '7201', 'Connor Group', date(2026, 9, 9), 5000.0, 5000.0],
]


SALES_BY_TYPE = [
    ['PPSOH LLC'],
    ['Sales by Customer Type Detail'],
    ['January 1-August 12, 2026'],
    [],
    [None, 'Transaction date', 'Transaction type', 'Num', 'Product/Service full name', 'Description', 'Quantity', 'Sales price', 'Amount', 'Balance'],
    ['Apartment'],
    [None, '05/06/2026', 'Invoice', '6871', 'Exterior Renovations', 'Red Bank', 1.0, 575.0, 575.0, 575.0],
    ['Total for Apartment', None, None, None, None, None, 1.0, None, 575.0],
]


AGING_DETAIL = [
    ['PPSOH LLC'],
    ['A/R Aging Detail Report'],
    ['As of Aug 12, 2026'],
    [],
    [None, 'Date', 'Transaction type', 'Num', 'Customer full name', 'Due date', 'Amount', 'Open balance'],
    ['91 or more days past due'],
    [None, '06/16/2022', 'Invoice', '3827', 'Bridges of Pine Creek:BOPC Pebble Phase 3', '07/16/2022', 80397.05, 80397.05],
]


def test_old_invoice_list_still_parses():
    raw = _xlsx(OLD_STYLE)
    assert oo.detect_ar_report_type('PPSOH LLC_Invoice List by Date.xlsx', raw) == 'invoice_list'
    out = oo.parse_ar_aging_bytes('PPSOH LLC_Invoice List by Date.xlsx', raw, expect='invoice_list')
    assert out['invoice_list_count'] == 2
    assert out['salesman_field_present'] is True
    assert out['invoice_list'][0]['sales_reps'] == ['Adam Cupito', 'Andy Potts']
    assert out['invoice_list'][1]['sales_reps'] == ['Tony Cumella']


def test_grouped_by_sales_rep_without_column():
    """QB dropped the Sales Rep column and groups rows under the rep name."""
    raw = _xlsx(GROUPED_BY_REP)
    out = oo.parse_ar_aging_bytes('Invoice List by Date.xlsx', raw, expect='invoice_list')
    assert out['invoice_list_count'] == 3
    assert out['salesman_field_present'] is True
    assert out['invoice_list'][0]['sales_reps'] == ['Adam Cupito', 'Andy Potts']
    assert out['invoice_list'][1]['sales_reps'] == ['Adam Cupito', 'Andy Potts']
    assert out['invoice_list'][2]['sales_reps'] == ['Tony Cumella']
    sales = aggregate_sales_from_invoice_list(out['invoice_list'], year=2026)
    # 50/50 on the Adam/Andy pair
    assert sales['by_rep_month']['Adam Cupito'][1] == pytest.approx((42394.6 + 2000.0) / 2)
    assert sales['by_rep_month']['Tony Cumella'][8] == pytest.approx(5000.0)
    assert '(unassigned)' not in sales['by_rep_month']


def test_manual_excel_with_group_headers_still_reads():
    raw = _xlsx(MANUAL_EXCEL)
    out = oo.parse_ar_aging_bytes('invoices_fixed.xlsx', raw, expect='invoice_list')
    assert out['invoice_list_count'] == 2
    assert out['invoice_list'][0]['sales_reps'] == ['Adam Cupito', 'Andy Potts']
    assert out['invoice_list'][1]['sales_reps'] == ['Tony Cumella']


def test_new_qb_invoice_list_without_sales_rep():
    raw = _xlsx(NEW_NO_SALES)
    assert oo.detect_ar_report_type('PPSOH LLC_Invoice List by Date.xlsx', raw) == 'invoice_list'
    out = oo.parse_ar_aging_bytes('InvoiceList.xlsx', raw, expect='invoice_list')
    assert out['invoice_list_count'] == 2
    assert out['salesman_field_present'] is False
    assert out['invoice_list'][0]['date'] == '2026-01-08'
    assert out['invoice_list'][1]['date'] == '2026-08-10'
    assert out['invoice_list'][0]['customer'] == 'Morgan Properties'
    sales = aggregate_sales_from_invoice_list(out['invoice_list'], year=2026)
    assert sales['team_month'][1] == pytest.approx(42394.6)
    assert sales['team_month'][8] == pytest.approx(5000.0)
    assert '(unassigned)' in sales['by_rep_month']


def test_new_list_not_misread_as_aging_detail():
    raw = _xlsx(NEW_NO_SALES)
    # Filename stripped of "invoice list" — title still wins
    assert oo.detect_ar_report_type('QB_export.xlsx', raw) == 'invoice_list'


def test_sales_by_customer_type_is_rejected_with_clear_error():
    raw = _xlsx(SALES_BY_TYPE)
    assert oo.detect_ar_report_type('PPSOH LLC_Sales by Customer Type Detail.xlsx', raw) is None
    with pytest.raises(ValueError, match='Sales by Customer Type Detail'):
        oo.parse_ar_aging_bytes(
            'PPSOH LLC_Sales by Customer Type Detail.xlsx', raw, expect='invoice_list',
        )


def test_aging_detail_still_detected_as_detail():
    raw = _xlsx(AGING_DETAIL)
    assert oo.detect_ar_report_type('PPSOH LLC_A_R Aging Detail Report.xlsx', raw) == 'detail'


def test_parse_invoice_date_accepts_date_objects_and_long_names():
    assert _parse_invoice_date(date(2026, 8, 10)).date() == date(2026, 8, 10)
    assert _parse_invoice_date(datetime(2026, 1, 8, 0, 0)).date() == date(2026, 1, 8)
    assert _parse_invoice_date('August 10, 2026').date() == date(2026, 8, 10)
    assert _parse_invoice_date('2026-08-10').date() == date(2026, 8, 10)


def test_rep_sales_ytd_filename_is_invoice_list():
    assert oo._name_says_invoice_list('PPSOH+LLC_Rep+Sales+YTD.xlsx')
    assert oo._name_says_invoice_list('Rep Sales YTD')
    assert oo._name_says_invoice_list('PPSOH LLC_Invoice List by Date.xlsx')
    assert not oo._name_says_invoice_list('PPSOH LLC_Sales by Customer Type Detail.xlsx')


def test_stephanies_rep_sales_ytd_export():
    path = os.path.join(os.path.dirname(__file__), 'fixtures', 'PPSOH_LLC_Rep_Sales_YTD.xlsx')
    raw = open(path, 'rb').read()
    assert oo.detect_ar_report_type('PPSOH+LLC_Rep+Sales+YTD.xlsx', raw) == 'invoice_list'
    out = oo.parse_ar_aging_bytes('PPSOH+LLC_Rep+Sales+YTD.xlsx', raw, expect='invoice_list')
    assert out['invoice_list_count'] >= 600
    assert out['salesman_field_present'] is True
    assert out['split_invoice_count'] >= 1
    unassigned = [i for i in out['invoice_list'] if not i['sales_reps']]
    assert unassigned == []
    sales = aggregate_sales_from_invoice_list(out['invoice_list'], year=2026)
    assert sum(sales['team_month'].values()) > 7_000_000
    assert 'Adam Cupito' in sales['by_rep_month']
    assert 'Tony Cumella' in sales['by_rep_month']
    assert '(unassigned)' not in sales['by_rep_month']


def test_real_aug4_file_still_parses():
    path = os.path.join(
        os.path.dirname(__file__),
        '..', '..', 'business-intel', 'qb_reports', 'source_files',
        'PPSOH_LLC_Invoice_List_by_Date_2026-08-04.xlsx',
    )
    if not os.path.isfile(path):
        pytest.skip('checked-in Aug 4 Invoice List not on disk')
    raw = open(path, 'rb').read()
    out = oo.parse_ar_aging_bytes(os.path.basename(path), raw, expect='invoice_list')
    assert out['invoice_list_count'] >= 500
    assert out['salesman_field_present'] is True


# Mirrors app.USERS after the 2026-08-21 tier rework.
_USERS = {
    'thomas_ellison': {'role': 'admin', 'tier': 'owner'},
    'stephanie_whetstone': {'role': 'office_manager', 'tier': 'leadership'},
    'tony_cumella': {'role': 'consultant', 'tier': 'leadership'},
    'trey_hollmeyer': {'role': 'pm', 'tier': 'leadership'},
    'phil_miller': {'role': 'pm', 'tier': 'team'},
    'andy_potts': {'role': 'consultant', 'tier': 'team'},
}


def test_office_ops_is_leadership_tier():
    """Office Ops is AR aging and rep sales dollars — Leadership and above.

    Tony and Trey were added 2026-08-21 by explicit decision. Worth knowing
    that Trey once picked this up by accident, as a side effect bundled into an
    unrelated feature commit (ea1e9c9), and it was reverted within the week
    (c61e43d). The grant is the same; what changed is that it was made
    deliberately and on its own commit.
    """
    assert oo.can_access_office_ops(_USERS, 'thomas_ellison') is True
    assert oo.can_access_office_ops(_USERS, 'stephanie_whetstone') is True
    assert oo.can_access_office_ops(_USERS, 'tony_cumella') is True
    assert oo.can_access_office_ops(_USERS, 'trey_hollmeyer') is True


def test_office_ops_closed_to_team_tier():
    """Team tier is unrestricted everywhere EXCEPT here. Financials stop at
    Leadership — the one line the 'everyone sees everything' rework holds."""
    assert oo.can_access_office_ops(_USERS, 'phil_miller') is False
    assert oo.can_access_office_ops(_USERS, 'andy_potts') is False
    # Off the roster entirely, and malformed input, both fail closed.
    assert oo.can_access_office_ops(_USERS, 'former_employee') is False
    assert oo.can_access_office_ops(_USERS, '') is False
    assert oo.can_access_office_ops(_USERS, None) is False


def test_retired_shared_admin_login_has_no_office_ops():
    """The shared 'admin' picker login was removed 2026-08-21 (F-01).

    It held Office Ops from 2026-08-18. A stale 'admin' key must not reach AR
    data — and a tier it does not recognise must fail closed, not default open.
    """
    assert oo.can_access_office_ops(_USERS, 'admin') is False
    stale = dict(_USERS, admin={'role': 'pm'})           # no tier at all
    assert oo.can_access_office_ops(stale, 'admin') is False
    typo = dict(_USERS, admin={'role': 'pm', 'tier': 'leadershp'})  # typo'd tier
    assert oo.can_access_office_ops(typo, 'admin') is False
