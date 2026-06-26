"""Roofing material quantity and bid calculations."""
import math

from .material_catalog import GAF_DEFAULTS


def _waste_mult(waste_pct):
    return 1 + (waste_pct or 12) / 100


def _apply_waste(val, waste_pct):
    if not val:
        return 0
    return val * _waste_mult(waste_pct)


def _ice_water_lf(measurements):
    eaves = measurements.get('eaves_ft') or 0
    valleys = measurements.get('valleys_ft') or 0
    wall = measurements.get('wall_flashing_ft') or 0
    step = measurements.get('step_flashing_ft') or 0
    return eaves + valleys + wall + step


def _starter_lf(measurements):
    eaves = measurements.get('eaves_ft') or 0
    rakes = measurements.get('rakes_ft') or 0
    return eaves + rakes


def _ridge_cap_lf(measurements):
    ridges = measurements.get('ridges_ft') or 0
    hips = measurements.get('hips_ft') or 0
    return ridges + hips


def _drip_lf(measurements):
    if measurements.get('drip_edge_ft'):
        return measurements['drip_edge_ft']
    return _starter_lf(measurements)


def calculate_materials(measurements, inputs=None):
    """Compute GAF material quantities for a full material estimate."""
    inputs = inputs or {}
    waste_pct = inputs.get('waste_pct', 12)
    gaf = {**GAF_DEFAULTS, **(inputs.get('gaf_coverage') or {})}
    pipe_boots = max(int(inputs.get('pipe_boots') or 0), 0)

    sqft = measurements.get('roof_area_sqft') or 0
    if not sqft and measurements.get('roof_area_squares'):
        sqft = measurements['roof_area_squares'] * 100

    sqft_waste = _apply_waste(sqft, waste_pct)
    order_squares = math.ceil(sqft_waste / 100 * 10) / 10  # 1 decimal

    starter_lf = _apply_waste(_starter_lf(measurements), waste_pct)
    ice_lf = _apply_waste(_ice_water_lf(measurements), waste_pct)
    ridge_lf = _apply_waste(_ridge_cap_lf(measurements), waste_pct)
    drip_lf = _apply_waste(_drip_lf(measurements), waste_pct)
    valleys_ft = measurements.get('valleys_ft') or 0
    step_ft = measurements.get('step_flashing_ft') or 0

    bundles = math.ceil(sqft_waste / 100 * gaf['bundles_per_square'])
    pro_start = math.ceil(starter_lf / gaf['pro_start_lf_per_bundle']) if starter_lf else 0
    ice_rolls = math.ceil(ice_lf / gaf['weatherwatch_lf_per_roll']) if ice_lf else 0
    synthetic = math.ceil(sqft_waste / gaf['synthetic_sqft_per_roll']) if sqft_waste else 0
    ridge_bundles = math.ceil(ridge_lf / gaf['seal_a_ridge_lf_per_bundle']) if ridge_lf else 0
    valley_pcs = math.ceil(valleys_ft / gaf['valley_piece_ft']) if valleys_ft else 0
    drip_pcs = math.ceil(drip_lf / gaf['drip_edge_piece_ft']) if drip_lf else 0
    nail_boxes = max(1, math.ceil(sqft_waste / gaf['coil_nails_sqft_per_box'])) if sqft_waste else 0
    cap_pails = max(1, math.ceil(sqft_waste / gaf['cap_nails_sqft_per_pail'])) if sqft_waste else 0
    step_bundles = math.ceil(step_ft / 100) if step_ft else 0

    return {
        'waste_pct': waste_pct,
        'roof_area_sqft': round(sqft, 1),
        'roof_area_squares': round(sqft / 100, 2) if sqft else 0,
        'order_squares': order_squares,
        'sqft_with_waste': round(sqft_waste, 1),
        'starter_lf': round(starter_lf, 1),
        'ice_water_lf': round(ice_lf, 1),
        'ridge_cap_lf': round(ridge_lf, 1),
        'drip_edge_lf': round(drip_lf, 1),
        'timberline_bundles': bundles,
        'pro_start_bundles': pro_start,
        'weatherwatch_rolls': ice_rolls,
        'pro_guard_rolls': synthetic,
        'seal_a_ridge_bundles': ridge_bundles,
        'valley_metal_pcs': valley_pcs,
        'drip_edge_pcs': drip_pcs,
        'pipe_boots': pipe_boots,
        'coil_nails_boxes': nail_boxes,
        'cap_nails_pails': cap_pails,
        'step_flashing_bundles': step_bundles,
    }


def calculate_bid_summary(measurements, inputs=None):
    """Quick bid for Bid Perfect (squares-only) reports."""
    inputs = inputs or {}
    waste_pct = inputs.get('waste_pct', 12)

    squares = measurements.get('roof_area_squares') or 0
    if not squares and measurements.get('roof_area_sqft'):
        squares = measurements['roof_area_sqft'] / 100

    order_squares = math.ceil(squares * _waste_mult(waste_pct) * 10) / 10

    mat_per_sq = inputs.get('material_per_sq', 65)
    labor_per_sq = inputs.get('labor_per_sq', 60)
    dump_divisor = inputs.get('dump_divisor', 45)
    dump_cost = inputs.get('dump_cost', 200)
    tax_pct = inputs.get('tax_pct', 7.5)
    margin_pct = inputs.get('margin_pct', 25)

    material = order_squares * mat_per_sq
    labor = order_squares * labor_per_sq
    dump_loads = math.ceil(order_squares / dump_divisor) if dump_divisor else 0
    dump = dump_loads * dump_cost
    subtotal = material + labor + dump
    tax = subtotal * (tax_pct / 100)
    cost = subtotal + tax
    grand_total = cost / (1 - margin_pct / 100) if margin_pct < 100 else cost

    structures = measurements.get('structures') or []
    per_structure = []
    for s in structures:
        sq = s.get('squares') or 0
        osq = math.ceil(sq * _waste_mult(waste_pct) * 10) / 10
        per_structure.append({
            'label': s.get('label', 'Structure'),
            'squares': sq,
            'order_squares': osq,
        })

    return {
        'waste_pct': waste_pct,
        'roof_area_squares': round(squares, 2),
        'order_squares': order_squares,
        'material_cost': round(material, 2),
        'labor_cost': round(labor, 2),
        'dump_cost': round(dump, 2),
        'dump_loads': dump_loads,
        'tax': round(tax, 2),
        'cost_before_margin': round(cost, 2),
        'margin_pct': margin_pct,
        'grand_total': round(grand_total, 2),
        'structures': per_structure,
    }