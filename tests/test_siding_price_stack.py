"""Trey worksheet: building-type rollup + Cost/Markup/Overhead/Invoice stack."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from estimators.siding.calculator import calculate_quantities, compute_price_stack
from estimators.siding.excel_builder import build_estimate_excel


def _type(letter, wall_sf, qty, **extra):
    m = {'wall_area_net': wall_sf}
    m.update(extra)
    return {
        'label': f'Type {letter}',
        'building_type': letter,
        'qty': qty,
        'source': 'field',
        'measurements': m,
    }


def test_price_stack_matches_trey_expansion():
    # Waterfront-style: Type A, 80 squares, 7 buildings, $215/sq labor.
    buildings = [_type('A', 8000, 7)]
    inputs = {'labor_per_sq': 215, 'haul_per_sq': 25, 'delivery': 15,
              'markup': 450000, 'overhead': 58000}
    stack = compute_price_stack(buildings, inputs)
    assert stack['types'][0]['squares_one'] == 80.0
    assert stack['types'][0]['labor_one'] == 17200.0          # 215 * 80
    assert stack['labor'] == 120400.0                         # 17200 * 7
    assert stack['haul'] == 14000.0                           # 25 * 80 * 7
    assert stack['cost'] == 134415.0                          # labor + haul + 15
    assert stack['invoice'] == 642415.0                       # cost + 450k + 58k
    assert abs(stack['margin_pct'] - (450000 / 642415)) < 1e-4
    assert stack['total_qty'] == 7
    assert stack['type_count'] == 1


def test_price_stack_two_types_do_not_double_count_qty():
    buildings = [_type('A', 5000, 4), _type('B', 3000, 2)]
    inputs = {'labor_per_sq': 180, 'haul_per_sq': 0, 'delivery': 0,
              'markup': 10000, 'overhead': 2000}
    stack = compute_price_stack(buildings, inputs)
    # A: 50 sq * 180 * 4 = 36,000; B: 30 sq * 180 * 2 = 10,800
    assert stack['labor'] == 46800.0
    assert stack['cost'] == 46800.0
    assert stack['invoice'] == 58800.0
    assert stack['total_qty'] == 6
    assert stack['type_count'] == 2


def test_price_stack_zero_invoice_has_zero_margin():
    stack = compute_price_stack([], {'markup': 0, 'overhead': 0})
    assert stack['invoice'] == 0
    assert stack['margin_pct'] == 0


def test_squares_net_one_is_unscaled():
    q = calculate_quantities({'wall_area_net': 8000}, {'waste_pct': 14}, qty=7)
    assert q['siding_squares_net_one'] == 80.0
    assert q['siding_squares_net'] == 560.0  # 80 * 7


def test_excel_writes_markup_overhead_and_unscaled_labor_squares():
    buildings = [_type('A', 8000, 7)]
    inputs = {'labor_per_sq': 180, 'haul_per_sq': 25, 'delivery': 15,
              'markup': 450000, 'overhead': 58000, 'waste_pct': 14,
              'siding_type': 'Vinyl Lap'}
    buf = build_estimate_excel({'property_name': 'Test'}, buildings, inputs, {})
    from openpyxl import load_workbook
    wb = load_workbook(buf)
    totals = wb['6 – Estimate Total']
    assert totals['C11'].value == 450000
    assert totals['C12'].value == 58000
    labor = wb['5 – Labor']
    # Header row 5, first type row 6: E = squares for ONE building
    assert labor['E6'].value == 80.0
    assert labor['D6'].value == 7
    assert '*E6*D6' in str(labor['F6'].value)
