"""Material quantity calculations for siding estimates."""
import math


def _scale(val, qty):
    if val is None:
        return 0
    return float(val) * max(int(qty or 1), 1)


def calculate_quantities(measurements, inputs, qty=1):
    """Compute material quantities for one building (multiplied by qty)."""
    qty = max(int(qty or 1), 1)
    waste_pct = inputs.get('waste_pct', 14) / 100
    exposure = inputs.get('exposure_in', 4.5)
    post_len = inputs.get('post_length', 12)
    stories = inputs.get('stories', 2)
    siding_type = inputs.get('siding_type', 'Vinyl Lap')

    wall_one = float(measurements.get('wall_area_net', 0) or 0)
    wall_net = _scale(wall_one, qty)
    wall_gross = _scale(measurements.get('wall_area_gross', 0) or 0, qty)
    if not wall_gross and wall_net:
        wall_gross = wall_net
    wd_perim = _scale(measurements.get('window_door_perimeter', 0) or 0, qty)
    wd_count = _scale(measurements.get('window_door_count', 0) or 0, qty)
    inside_ft = _scale(measurements.get('inside_corners', 0) or 0, qty)
    outside_ft = _scale(measurements.get('outside_corners', 0) or 0, qty)
    fascia_ft = _scale(measurements.get('fascia', 0) or 0, qty)
    soffit_ft = _scale(measurements.get('soffit', 0) or 0, qty)

    siding_area_with_waste = wall_net * (1 + waste_pct)
    siding_squares_net = wall_net / 100
    siding_squares = siding_area_with_waste / 100  # order qty incl. material waste

    avg_story_ht = 9
    est_perimeter = wall_gross / (avg_story_ht * stories) if stories else wall_gross / 9
    starter_lin_ft = est_perimeter
    starter_pieces = math.ceil(starter_lin_ft / 10)

    jchannel_lin_ft = wd_perim
    jchannel_pieces = math.ceil(jchannel_lin_ft / 12) if jchannel_lin_ft else 0

    inside_pieces = math.ceil(inside_ft / post_len) if inside_ft else 0
    outside_pieces = math.ceil(outside_ft / post_len) if outside_ft else 0

    fascia_pieces = math.ceil(fascia_ft / 12) if fascia_ft else 0
    soffit_pieces = math.ceil(soffit_ft / 12) if soffit_ft else 0

    utility_lin_ft = wd_perim
    utility_pieces = math.ceil(utility_lin_ft / 12) if utility_lin_ft else 0

    housewrap_sqft = wall_gross
    housewrap_rolls = math.ceil(wall_gross / 900) if wall_gross else 0
    fanfold_squares = math.ceil(siding_squares) if siding_squares else 0

    return {
        'qty': qty,
        'siding_type': siding_type,
        'wall_area_net': round(wall_net, 1),
        'wall_area_gross': round(wall_gross, 1),
        'siding_area_with_waste': round(siding_area_with_waste, 1),
        'siding_squares_net_one': round(wall_one / 100, 2),
        'siding_squares_net': round(siding_squares_net, 2),
        'siding_squares': round(siding_squares, 2),
        'waste_pct': inputs.get('waste_pct', 14),
        'exposure_in': exposure,
        'post_length': post_len,
        'stories': stories,
        'starter_lin_ft': round(starter_lin_ft, 1),
        'starter_pieces': starter_pieces,
        'jchannel_lin_ft': round(jchannel_lin_ft, 1),
        'jchannel_pieces': jchannel_pieces,
        'inside_corners_lin_ft': round(inside_ft, 1),
        'inside_corner_pieces': inside_pieces,
        'outside_corners_lin_ft': round(outside_ft, 1),
        'outside_corner_pieces': outside_pieces,
        'fascia_lin_ft': round(fascia_ft, 1),
        'fascia_pieces': fascia_pieces,
        'soffit_lin_ft': round(soffit_ft, 1),
        'soffit_pieces': soffit_pieces,
        'utility_lin_ft': round(utility_lin_ft, 1),
        'utility_pieces': utility_pieces,
        'housewrap_sqft': round(housewrap_sqft, 0),
        'housewrap_rolls': housewrap_rolls,
        'fanfold_squares': fanfold_squares,
        'wd_count': int(wd_count) if wd_count else 0,
    }


def aggregate_building_quantities(building_results):
    """Sum numeric quantity fields across buildings for job-level preview."""
    totals = {
        'building_count': len(building_results),
        'total_qty': sum(b.get('qty', 1) for b in building_results),
        'wall_area_net': 0.0,
        'siding_squares_net': 0.0,
        'siding_squares': 0.0,
        'starter_pieces': 0,
        'jchannel_pieces': 0,
        'inside_corner_pieces': 0,
        'outside_corner_pieces': 0,
        'fascia_pieces': 0,
        'soffit_pieces': 0,
    }
    for item in building_results:
        q = item['quantities']
        totals['wall_area_net'] += q.get('wall_area_net', 0) or 0
        totals['siding_squares_net'] += q.get('siding_squares_net', 0) or 0
        totals['siding_squares'] += q.get('siding_squares', 0) or 0
        totals['starter_pieces'] += q.get('starter_pieces', 0) or 0
        totals['jchannel_pieces'] += q.get('jchannel_pieces', 0) or 0
        totals['inside_corner_pieces'] += q.get('inside_corner_pieces', 0) or 0
        totals['outside_corner_pieces'] += q.get('outside_corner_pieces', 0) or 0
        totals['fascia_pieces'] += q.get('fascia_pieces', 0) or 0
        totals['soffit_pieces'] += q.get('soffit_pieces', 0) or 0
    totals['wall_area_net'] = round(totals['wall_area_net'], 1)
    totals['siding_squares_net'] = round(totals['siding_squares_net'], 2)
    totals['siding_squares'] = round(totals['siding_squares'], 2)
    return totals


def _money(n):
    return round(float(n or 0), 2)


def compute_price_stack(buildings, inputs):
    """Trey's stack: Cost + Markup $ + Overhead $ = Invoice; Margin % = Markup / Invoice.

    Cost here is labor + haul + delivery. Material unit prices are optional
    and live in the workbook — we do not invent them. Labor uses *one*
    building's net squares × type count (same as his sheet), not the
    already-expanded quantity field.
    """
    inputs = inputs or {}
    labor_rate = float(inputs.get('labor_per_sq') or 0)
    haul_rate = float(inputs.get('haul_per_sq') or 0)
    delivery = float(inputs.get('delivery') or 0)
    markup = float(inputs.get('markup') or 0)
    overhead = float(inputs.get('overhead') or 0)

    types = []
    labor = 0.0
    haul = 0.0
    total_qty = 0
    job_net_squares = 0.0
    for b in buildings or []:
        qty = max(int(b.get('qty') or 1), 1)
        m = b.get('measurements') or {}
        sq_one = float(m.get('wall_area_net') or 0) / 100.0
        labor_one = labor_rate * sq_one
        haul_one = haul_rate * sq_one
        labor += labor_one * qty
        haul += haul_one * qty
        total_qty += qty
        job_net_squares += sq_one * qty
        letter = (b.get('building_type') or '').strip() or 'A'
        types.append({
            'letter': letter,
            'label': b.get('label') or f'Type {letter}',
            'qty': qty,
            'squares_one': round(sq_one, 2),
            'labor_one': _money(labor_one),
            'labor_expanded': _money(labor_one * qty),
        })

    cost = labor + haul + delivery
    invoice = cost + markup + overhead
    margin_pct = (markup / invoice) if invoice else 0.0
    return {
        'labor': _money(labor),
        'haul': _money(haul),
        'delivery': _money(delivery),
        'cost': _money(cost),
        'markup': _money(markup),
        'overhead': _money(overhead),
        'invoice': _money(invoice),
        'margin_pct': round(margin_pct, 4),
        'total_qty': total_qty,
        'type_count': len(buildings or []),
        'job_net_squares': round(job_net_squares, 2),
        'types': types,
        'cost_note': 'Labor + haul + delivery. Material unit prices stay in the workbook.',
    }