"""Each estimating tool produces a real Excel workbook from field numbers.

Run: python -m pytest tests/test_estimator_smoke.py -v

These do not call Claude. They are the math + xlsx path a demo hits after
a takeoff is typed or parsed.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _xlsx(buf):
    raw = buf.getvalue() if hasattr(buf, 'getvalue') else buf
    assert raw[:2] == b'PK', 'not a zip/xlsx'
    assert len(raw) > 2000
    return raw


def test_siding_estimator_builds_xlsx():
    from estimators.siding.excel_builder import build_estimate_excel
    buildings = [{
        'label': 'Building A',
        'building_type': 'A',
        'qty': 2,
        'source': 'field',
        'measurements': {'wall_area_net': 8000, 'window_door_perimeter': 400},
    }]
    buf = build_estimate_excel(
        {'property_name': 'Sample Community', 'address': '100 Main'},
        buildings,
        {'waste_pct': 14, 'siding_type': 'Vinyl Lap', 'labor_per_sq': 215},
        {},
    )
    _xlsx(buf)


def test_roofing_estimator_builds_xlsx():
    from estimators.roofing.calculator import calculate_materials
    from estimators.roofing.excel_builder import build_estimate_excel
    measurements = {
        'roof_area_sqft': 24000,
        'eaves_ft': 400,
        'rakes_ft': 180,
        'ridges_ft': 80,
        'valleys_ft': 40,
    }
    qty = calculate_materials(measurements, {'waste_pct': 12})
    assert qty['order_squares'] > 0
    buf = build_estimate_excel(
        {'property_name': 'Sample Community'},
        measurements,
        {'waste_pct': 12},
    )
    _xlsx(buf)


def test_gutter_estimator_builds_xlsx():
    from estimators.gutter.calculator import calculate_gutter_estimate
    from estimators.gutter.excel_builder import build_estimate_excel
    measurements = {'gutter_lf': 420, 'eaves_ft': 420}
    summary = calculate_gutter_estimate(measurements, {})
    assert summary['invoice_total'] > 0
    buf = build_estimate_excel(
        {'property_name': 'Sample Community'},
        measurements,
        {},
    )
    _xlsx(buf)


def test_painting_estimator_builds_xlsx():
    from estimators.painting.calculator import calculate_painting_estimate
    from estimators.painting.excel_builder import build_estimate_excel
    lines = [{'category': 'Airless', 'measured': 12000}]
    result = calculate_painting_estimate(lines, {})
    assert result['lines']
    assert result['one_coat_bid'] > 0
    buf = build_estimate_excel(
        {'property_name': 'Sample Community'},
        lines,
        {},
    )
    _xlsx(buf)
