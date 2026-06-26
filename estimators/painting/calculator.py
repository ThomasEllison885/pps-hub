"""Exterior painting labor, material, and bid calculations."""
from collections import defaultdict

from .production_rates import RATE_CATALOG, get_rate

DEFAULTS = {
    'labor_per_hour': 38,
    'margin_one_coat_pct': 42,
    'margin_two_coat_pct': 38,
    'two_coat_multiplier': 1.6,
}


def _calc_line(category, measured, inputs):
    meta = get_rate(category)
    if not meta or not measured:
        return None

    production = float(inputs.get(f'rate_{category}', meta['production_rate']) or meta['production_rate'])
    paint_cov = float(inputs.get(f'coverage_{category}', meta['paint_coverage']) or meta['paint_coverage'])
    paint_cost = float(inputs.get(f'paint_cost_{category}', meta['paint_cost']) or meta['paint_cost'])
    labor_hr = float(inputs.get('labor_per_hour', DEFAULTS['labor_per_hour']))

    measured = float(measured)
    hours = measured / production if production else 0
    labor_cost = hours * labor_hr
    paint_gal = measured / paint_cov if paint_cov else 0
    paint_material = paint_gal * paint_cost

    return {
        'exterior_type': meta['exterior_type'],
        'category': category,
        'unit': meta['unit'],
        'measured': round(measured, 2),
        'production_rate': production,
        'paint_coverage': paint_cov,
        'paint_cost_per_gal': paint_cost,
        'hours': round(hours, 2),
        'labor_cost': round(labor_cost, 2),
        'paint_gallons': round(paint_gal, 2),
        'paint_cost': round(paint_material, 2),
        'subtotal': round(labor_cost + paint_material, 2),
    }


def calculate_painting_estimate(line_items, inputs=None):
    """
    line_items: list of {category, measured} or {exterior_type, category, measured}
    """
    inputs = {**DEFAULTS, **(inputs or {})}
    lines = []
    for item in line_items or []:
        cat = item.get('category')
        measured = item.get('measured')
        if not cat or measured in (None, '', 0):
            continue
        row = _calc_line(cat, measured, inputs)
        if row:
            lines.append(row)

    by_type = defaultdict(lambda: {'labor': 0.0, 'material': 0.0, 'hours': 0.0})
    total_labor = 0.0
    total_material = 0.0
    total_hours = 0.0
    for row in lines:
        et = row['exterior_type']
        by_type[et]['labor'] += row['labor_cost']
        by_type[et]['material'] += row['paint_cost']
        by_type[et]['hours'] += row['hours']
        total_labor += row['labor_cost']
        total_material += row['paint_cost']
        total_hours += row['hours']

    one_coat_cost = total_labor + total_material
    two_mult = float(inputs.get('two_coat_multiplier', DEFAULTS['two_coat_multiplier']))
    margin_one = float(inputs.get('margin_one_coat_pct', DEFAULTS['margin_one_coat_pct']))
    margin_two = float(inputs.get('margin_two_coat_pct', DEFAULTS['margin_two_coat_pct']))

    two_coat_cost = one_coat_cost * two_mult
    one_coat_bid = one_coat_cost / (1 - margin_one / 100) if margin_one < 100 else one_coat_cost
    two_coat_bid = two_coat_cost / (1 - margin_two / 100) if margin_two < 100 else two_coat_cost

    type_summary = []
    for et in ('Doors', 'PowerWash', 'Siding', 'Soffit', 'Trim'):
        if et in by_type:
            type_summary.append({
                'exterior_type': et,
                'material': round(by_type[et]['material'], 2),
                'labor': round(by_type[et]['labor'], 2),
                'hours': round(by_type[et]['hours'], 2),
                'total': round(by_type[et]['material'] + by_type[et]['labor'], 2),
            })

    return {
        'lines': lines,
        'line_count': len(lines),
        'by_type': type_summary,
        'total_hours': round(total_hours, 2),
        'total_labor': round(total_labor, 2),
        'total_material': round(total_material, 2),
        'one_coat_cost': round(one_coat_cost, 2),
        'two_coat_cost': round(two_coat_cost, 2),
        'one_coat_bid': round(one_coat_bid, 2),
        'two_coat_bid': round(two_coat_bid, 2),
        'one_coat_profit': round(one_coat_bid - one_coat_cost, 2),
        'two_coat_profit': round(two_coat_bid - two_coat_cost, 2),
        'margin_one_coat_pct': margin_one,
        'margin_two_coat_pct': margin_two,
        'two_coat_multiplier': two_mult,
        'labor_per_hour': float(inputs.get('labor_per_hour', DEFAULTS['labor_per_hour'])),
    }