"""Gutter and downspout quantity and cost calculations."""
import math

# Defaults from PPS 2025 Roof & Gutter spreadsheet + industry norms
DEFAULTS = {
    'gutter_price_per_lf': 7.0,       # installed $/LF (gutters + downspout run combined)
    'guard_price_per_lf': 2.0,        # gutter guard $/LF
    'downspout_lf_each': 10.0,        # vertical run per downspout (~10 ft)
    'downspout_spacing_ft': 35.0,     # 1 downspout per 30–40 LF (use 35)
    'waste_pct': 10.0,                # extra LF for cuts/corners
    'hanger_spacing_ft': 2.5,         # hanger every 2–3 ft
    'elbows_per_downspout': 2,
    'end_caps_per_run': 2,
    'labor_per_lf': 0.0,              # often bundled in $7/LF; optional add-on
    'tax_pct': 7.5,
    'margin_pct': 25.0,
}


def _suggest_downspouts(gutter_lf, spacing):
    """Recommend downspout count (minimum 2 on any job)."""
    if not gutter_lf:
        return 2
    return max(2, math.ceil(float(gutter_lf) / spacing))


def calculate_gutter_estimate(measurements, inputs=None):
    inputs = {**DEFAULTS, **(inputs or {})}
    waste_pct = inputs.get('waste_pct', 10)
    gutter_lf_raw = float(measurements.get('gutter_lf') or measurements.get('eaves_ft') or 0)

    downspout_count = inputs.get('downspout_count')
    if downspout_count is None or downspout_count == '':
        downspout_count = _suggest_downspouts(gutter_lf_raw, inputs['downspout_spacing_ft'])
    else:
        downspout_count = max(int(downspout_count), 0)

    ds_lf_each = float(inputs.get('downspout_lf_each', 10))
    downspout_lf = downspout_count * ds_lf_each

    # PPS sheet: total linear = gutters + downspouts (as LF)
    total_lf_raw = gutter_lf_raw + downspout_lf
    total_lf_order = total_lf_raw * (1 + waste_pct / 100)

    include_guards = bool(inputs.get('include_guards'))
    guard_lf = gutter_lf_raw * (1 + waste_pct / 100) if include_guards else 0

    hangers = math.ceil(gutter_lf_raw / inputs['hanger_spacing_ft']) if gutter_lf_raw else 0
    elbows = downspout_count * int(inputs.get('elbows_per_downspout', 2))
    end_caps = int(inputs.get('end_caps_per_run', 2))

    gutter_cost = total_lf_order * float(inputs.get('gutter_price_per_lf', 7))
    guard_cost = guard_lf * float(inputs.get('guard_price_per_lf', 2)) if include_guards else 0
    labor = total_lf_order * float(inputs.get('labor_per_lf', 0))
    material_subtotal = gutter_cost + guard_cost + labor

    tax_pct = float(inputs.get('tax_pct', 7.5))
    margin_pct = float(inputs.get('margin_pct', 25))
    tax = material_subtotal * (tax_pct / 100)
    cost = material_subtotal + tax
    invoice = cost / (1 - margin_pct / 100) if margin_pct < 100 else cost

    return {
        'gutter_lf_raw': round(gutter_lf_raw, 1),
        'downspout_count': downspout_count,
        'downspout_lf': round(downspout_lf, 1),
        'total_lf_raw': round(total_lf_raw, 1),
        'total_lf_order': round(total_lf_order, 1),
        'guard_lf': round(guard_lf, 1),
        'waste_pct': waste_pct,
        'hangers': hangers,
        'elbows': elbows,
        'end_caps': end_caps,
        'gutter_cost': round(gutter_cost, 2),
        'guard_cost': round(guard_cost, 2),
        'labor_cost': round(labor, 2),
        'material_subtotal': round(material_subtotal, 2),
        'tax': round(tax, 2),
        'cost_before_margin': round(cost, 2),
        'margin_pct': margin_pct,
        'invoice_total': round(invoice, 2),
        'include_guards': include_guards,
    }