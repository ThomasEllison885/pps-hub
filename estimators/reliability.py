"""Takeoff reliability / confidence metadata for estimating tools."""

HIGH = 'high'
MEDIUM = 'medium'
LOW = 'low'
MANUAL = 'manual'
MISSING = 'missing'

_LEVEL_RANK = {HIGH: 4, MEDIUM: 3, LOW: 2, MANUAL: 2, MISSING: 0}

SOURCE_LABELS = {
    'eagleview_eaves': 'EagleView eaves',
    'eagleview_premium': 'EagleView Premium report',
    'eagleview_bid': 'EagleView Bid Perfect',
    'eagleview_walls': 'EagleView Walls report',
    'roofr_report': 'Roofr report',
    'sqft_formula': 'Estimated (sq ft ÷ 10)',
    'squares_formula': 'Estimated (squares × 10)',
    'spacing_formula': 'Estimated (downspout spacing)',
    'default_value': 'Default assumption',
    'user_entry': 'Manual entry',
    'field_measure': 'Field measurements',
    'generic_aerial': 'Generic aerial parse',
    'pricing_upload': 'Supplier pricing file',
    'pricing_form': 'Form defaults',
    'not_applicable': 'Not included',
}

OVERALL_COPY = {
    HIGH: {
        'title': 'High confidence',
        'headline': 'Most takeoff data came directly from the report.',
        'detail': 'Safe to generate; confirm estimated fields on site before final bid.',
        'css': 'high',
    },
    MEDIUM: {
        'title': 'Partial takeoff',
        'headline': 'Some quantities are from the report; others are estimated.',
        'detail': 'Review amber fields before bidding.',
        'css': 'medium',
    },
    LOW: {
        'title': 'Low confidence',
        'headline': 'This takeoff relies on formulas or manual entry.',
        'detail': 'Verify on site or upload a fuller EagleView report before bidding.',
        'css': 'low',
    },
}


def _field(key, label, value, reliability, source, note=None, critical=False, display=None):
    return {
        'key': key,
        'label': label,
        'value': value,
        'display': display if display is not None else _format_display(value),
        'reliability': reliability,
        'source': source,
        'source_label': SOURCE_LABELS.get(source, source.replace('_', ' ').title()),
        'note': note,
        'critical': critical,
    }


def _format_display(value):
    if value is None or value == '':
        return '—'
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    if isinstance(value, (int, float)):
        return f'{value:,.1f}'.rstrip('0').rstrip('.')
    return str(value)


def _count_levels(fields):
    counts = {HIGH: 0, MEDIUM: 0, LOW: 0, MANUAL: 0, MISSING: 0}
    for f in fields:
        rel = f.get('reliability', MISSING)
        if rel in counts:
            counts[rel] += 1
    return counts


def _overall_from_fields(fields, rules_fn):
    """rules_fn(fields) -> high|medium|low"""
    return rules_fn(fields)


def _package(fields, overall, report_label=None):
    counts = _count_levels(fields)
    from_report = counts[HIGH] + counts[MEDIUM]
    estimated = counts[LOW]
    manual = counts[MANUAL]
    missing = counts[MISSING]
    copy = OVERALL_COPY[overall]
    parts = []
    if from_report:
        parts.append(f'{from_report} from report')
    if estimated:
        parts.append(f'{estimated} estimated')
    if manual:
        parts.append(f'{manual} manual')
    if missing:
        parts.append(f'{missing} missing')
    summary_line = ' · '.join(parts) if parts else 'No takeoff data yet'
    confirm = None
    if overall == LOW:
        confirm = (
            'This takeoff has low confidence — quantities rely on formulas or manual entry. '
            'Verify on site before bidding. Continue anyway?'
        )
    elif overall == MEDIUM:
        confirm = (
            'Some takeoff fields are estimated. Review flagged items before bidding. '
            'Continue?'
        )
    return {
        'overall': overall,
        'title': copy['title'],
        'headline': copy['headline'],
        'detail': copy['detail'],
        'css': copy['css'],
        'summary_line': summary_line,
        'report_label': report_label,
        'counts': {
            'from_report': from_report,
            'estimated': estimated,
            'manual': manual,
            'missing': missing,
        },
        'fields': fields,
        'confirm_message': confirm,
    }


def _gutter_overall(fields):
    by_key = {f['key']: f for f in fields}
    gutter = by_key.get('gutter_lf', {})
    gutter_rel = gutter.get('reliability', MISSING)
    if gutter_rel == MISSING or not gutter.get('value'):
        return LOW
    if gutter_rel == HIGH:
        return MEDIUM  # downspouts are still estimated
    if gutter_rel == MEDIUM:
        return MEDIUM
    return LOW


def build_gutter_reliability(measurements, inputs=None, user_overrides=None):
    inputs = inputs or {}
    user_overrides = user_overrides or {}
    report_type = measurements.get('report_type', 'unknown')
    report_labels = {
        'premium': 'EagleView Premium',
        'bid_perfect': 'EagleView Bid Perfect',
        'roofr': 'Roofr',
        'unknown': 'Unknown report',
    }
    report_label = report_labels.get(report_type, report_type)

    eaves_ft = measurements.get('eaves_ft')
    gutter_lf = measurements.get('gutter_lf') or user_overrides.get('gutter_lf')
    gutter_source = 'user_entry'
    gutter_rel = MANUAL
    gutter_note = None

    if user_overrides.get('gutter_lf_manual'):
        gutter_source = 'user_entry'
        gutter_rel = MANUAL
        gutter_note = 'Overridden after PDF parse'
    elif eaves_ft:
        gutter_source = 'eagleview_eaves'
        gutter_rel = HIGH if report_type in ('premium', 'roofr') else MEDIUM
    elif gutter_lf and report_type == 'bid_perfect':
        gutter_source = 'squares_formula'
        gutter_rel = LOW
        gutter_note = 'Bid Perfect has no eaves length'
    elif gutter_lf:
        gutter_source = 'sqft_formula'
        gutter_rel = LOW
        gutter_note = 'No eaves in report — rule of thumb'

    ds_count = inputs.get('downspout_count')
    if ds_count is None or ds_count == '':
        ds_count = measurements.get('suggested_downspout_count')
    ds_manual = user_overrides.get('downspout_manual')
    ds_rel = MANUAL if ds_manual else LOW
    ds_source = 'user_entry' if ds_manual else 'spacing_formula'

    ds_height = inputs.get('downspout_lf_each', 10)
    include_guards = bool(inputs.get('include_guards'))

    fields = [
        _field('gutter_lf', 'Gutter run', gutter_lf, gutter_rel, gutter_source, gutter_note, critical=True,
               display=f'{_format_display(gutter_lf)} ft' if gutter_lf else '—'),
        _field('downspout_count', 'Downspouts', ds_count, ds_rel, ds_source,
               'Count from spacing rule — confirm on site', critical=True),
        _field('downspout_height', 'Downspout height', ds_height, LOW if ds_height == 10 else MANUAL,
               'default_value' if ds_height == 10 else 'user_entry', 'Per-vertical run'),
        _field('guards', 'Gutter guards', include_guards, MANUAL if include_guards else MISSING,
               'user_entry' if include_guards else 'not_applicable'),
        _field('pricing', 'Pricing rates', True, MANUAL, 'pricing_form', 'Editable in form and Excel'),
    ]
    overall = _gutter_overall(fields)
    return _package(fields, overall, report_label)


def _roofing_overall(fields):
    by_key = {f['key']: f for f in fields}
    area = by_key.get('roof_area', {})
    if area.get('reliability') == MISSING:
        return LOW
    if area.get('reliability') == LOW:
        return LOW
    critical = [f for f in fields if f.get('critical')]
    lows = sum(1 for f in critical if f['reliability'] in (LOW, MISSING))
    if lows >= 2:
        return LOW
    if lows == 1 or area.get('reliability') == MEDIUM:
        return MEDIUM
    highs = sum(1 for f in critical if f['reliability'] == HIGH)
    if highs >= 3:
        return HIGH
    return MEDIUM


def build_roofing_reliability(measurements, inputs=None):
    inputs = inputs or {}
    report_type = measurements.get('report_type', 'unknown')
    report_labels = {
        'premium': 'EagleView Premium',
        'bid_perfect': 'EagleView Bid Perfect',
        'roofr': 'Roofr',
        'unknown': 'Unknown report',
    }
    report_label = report_labels.get(report_type, report_type)
    is_quick = report_type == 'bid_perfect'

    sq = measurements.get('roof_area_squares')
    sqft = measurements.get('roof_area_sqft')
    area_val = sq or sqft
    if sq:
        area_display = f'{_format_display(sq)} sq'
    elif sqft:
        area_display = f'{_format_display(sqft)} sq ft'
    else:
        area_display = '—'

    if report_type in ('premium', 'roofr') and sqft:
        area_rel, area_src = HIGH, 'eagleview_premium' if report_type == 'premium' else 'roofr_report'
    elif report_type == 'bid_perfect' and sq:
        area_rel, area_src = MEDIUM, 'eagleview_bid'
    elif area_val:
        area_rel, area_src = LOW, 'user_entry'
    else:
        area_rel, area_src = MISSING, 'user_entry'

    def _meas(key, label, unit='ft', critical=False):
        val = measurements.get(key)
        if val is not None and report_type in ('premium', 'roofr'):
            return _field(key, label, val, HIGH,
                            'eagleview_premium' if report_type == 'premium' else 'roofr_report',
                            critical=critical, display=f'{_format_display(val)} {unit}')
        if val is not None:
            return _field(key, label, val, MEDIUM, 'user_entry', critical=critical,
                            display=f'{_format_display(val)} {unit}')
        return _field(key, label, None, MISSING, 'user_entry', f'Not on {report_label}',
                       critical=critical)

    pipe_boots = inputs.get('pipe_boots', 0)
    fields = [
        _field('roof_area', 'Roof area', area_val, area_rel, area_src, critical=True, display=area_display),
        _field('pitch', 'Predominant pitch', measurements.get('predominant_pitch') or None,
               HIGH if measurements.get('predominant_pitch') and report_type in ('premium', 'roofr') else MISSING,
               'eagleview_premium' if report_type == 'premium' else 'roofr_report' if report_type == 'roofr' else 'user_entry',
               critical=False),
        _meas('eaves_ft', 'Eaves', critical=not is_quick),
        _meas('rakes_ft', 'Rakes', critical=not is_quick),
        _meas('valleys_ft', 'Valleys'),
        _meas('ridges_ft', 'Ridges'),
        _field('pipe_boots', 'Pipe boots', pipe_boots, MANUAL, 'user_entry',
               'Never on EagleView — count from site photos', critical=True,
               display=str(pipe_boots)),
        _field('material_list', 'Material takeoff', not is_quick,
               HIGH if not is_quick and report_type in ('premium', 'roofr') else LOW,
               'eagleview_premium' if report_type == 'premium' else 'roofr_report' if not is_quick else 'eagleview_bid',
               'Bid Perfect → quick bid only' if is_quick else 'Full GAF material list',
               critical=True, display='Quick bid' if is_quick else 'Full GAF list'),
        _field('pricing', 'Pricing rates', True, MANUAL, 'pricing_form', 'Editable in form and Excel'),
    ]
    overall = _roofing_overall(fields)
    return _package(fields, overall, report_label)


def _siding_overall(fields):
    by_key = {f['key']: f for f in fields}
    wall = by_key.get('wall_area_net', {})
    if wall.get('reliability') == HIGH:
        missing_crit = sum(
            1 for f in fields
            if f.get('critical') and f['reliability'] in (MISSING, LOW)
        )
        if missing_crit == 0:
            return HIGH
        if missing_crit <= 2:
            return MEDIUM
    if wall.get('reliability') == MEDIUM:
        return MEDIUM
    return LOW


def build_siding_reliability(measurements, source='eagleview', pricing_loaded=0):
    is_eagleview = source == 'eagleview'
    is_field = source == 'field'
    is_aerial = source == 'aerial_other'

    def _wall_field(key, label, critical=False):
        val = measurements.get(key)
        if val is not None and is_eagleview:
            rel, src = HIGH, 'eagleview_walls'
        elif val is not None and is_field:
            rel, src = MANUAL, 'field_measure'
        elif val is not None:
            rel, src = LOW, 'generic_aerial'
        else:
            rel, src = MISSING, 'field_measure' if is_field else 'eagleview_walls' if is_eagleview else 'generic_aerial'
        unit = 'sq ft' if 'area' in key else 'lin ft' if key != 'window_door_count' else 'ea'
        disp = f'{_format_display(val)} {unit}' if val is not None and key != 'window_door_count' else (
            _format_display(val) if val is not None else '—'
        )
        return _field(key, label, val, rel, src, critical=critical, display=disp)

    source_labels = {
        'eagleview': 'EagleView Walls',
        'field': 'Field measurements',
        'aerial_other': 'Other aerial report',
    }
    fields = [
        _field('data_source', 'Data source', source_labels.get(source, source),
               HIGH if is_eagleview else MANUAL if is_field else LOW,
               'eagleview_walls' if is_eagleview else 'field_measure' if is_field else 'generic_aerial',
               critical=True),
        _wall_field('wall_area_net', 'Net wall area', critical=True),
        _wall_field('wall_area_gross', 'Gross wall area', critical=True),
        _wall_field('window_door_perimeter', 'W&D perimeter', critical=True),
        _wall_field('inside_corners', 'Inside corners'),
        _wall_field('outside_corners', 'Outside corners'),
        _wall_field('fascia', 'Fascia'),
        _field('pricing', 'Material pricing', pricing_loaded > 0, 
               HIGH if pricing_loaded >= 5 else MANUAL if pricing_loaded else LOW,
               'pricing_upload' if pricing_loaded else 'pricing_form',
               f'{pricing_loaded} prices loaded' if pricing_loaded else 'Upload CSV or edit Excel',
               critical=True, display=f'{pricing_loaded} items' if pricing_loaded else 'Not uploaded'),
    ]
    overall = _siding_overall(fields)
    return _package(fields, overall, source_labels.get(source, source))


def build_siding_job_reliability(buildings, pricing_loaded=0):
    """Aggregate confidence across buildings (weakest link sets overall)."""
    if not buildings:
        return _package([], LOW, 'No buildings')
    confidences = []
    for b in buildings:
        confidences.append(
            build_siding_reliability(
                b.get('measurements') or {},
                b.get('source') or 'eagleview',
                pricing_loaded,
            )
        )
    overall = min((c['overall'] for c in confidences), key=lambda x: _LEVEL_RANK[x])
    merged_fields = []
    for i, c in enumerate(confidences):
        label = (buildings[i].get('label') or f'Building {i + 1}')
        for f in c['fields']:
            if f['key'] == 'data_source':
                merged_fields.append({
                    **f,
                    'label': f'{label} — source',
                    'display': f.get('display'),
                })
            elif f.get('critical'):
                merged_fields.append({
                    **f,
                    'label': f'{label} — {f["label"]}',
                })
    if pricing_loaded:
        merged_fields.append(
            _field('pricing', 'Material pricing', pricing_loaded, HIGH, 'pricing_upload',
                   f'{pricing_loaded} prices loaded', critical=True,
                   display=f'{pricing_loaded} items')
        )
    else:
        merged_fields.append(
            _field('pricing', 'Material pricing', 0, LOW, 'pricing_form',
                   'Upload CSV or edit Excel', critical=True, display='Not uploaded')
        )
    report_label = f'{len(buildings)} building{"s" if len(buildings) != 1 else ""}'
    base = _package(merged_fields, overall, report_label)
    base['buildings'] = confidences
    return base


def build_painting_reliability(measurements, line_items, user_overrides=None):
    line_items = line_items or []
    active = [li for li in line_items if li.get('measured')]

    fields = [
        _field(
            'data_source',
            'Data source',
            'Field takeoff',
            MANUAL,
            'field_measure',
            'Exterior painting uses site measurements, not aerial reports',
            critical=True,
        ),
        _field(
            'line_items',
            'Takeoff lines',
            len(active),
            HIGH if len(active) >= 5 else MEDIUM if len(active) >= 2 else MISSING,
            'user_entry' if active else 'field_measure',
            f'{len(active)} categories with quantities' if active else 'Enter measured quantities',
            critical=True,
            display=f'{len(active)} lines',
        ),
    ]

    types = {li.get('exterior_type') for li in active if li.get('exterior_type')}
    if types:
        fields.append(_field(
            'categories',
            'Exterior types',
            len(types),
            MEDIUM if len(types) >= 2 else MANUAL,
            'user_entry',
            ', '.join(sorted(types)),
            display=', '.join(sorted(types)),
        ))

    if not active:
        overall = MISSING
    elif len(active) >= 5:
        overall = MEDIUM
    elif len(active) >= 2:
        overall = MANUAL
    else:
        overall = LOW

    return _package(fields, overall, 'Exterior painting takeoff')


def reliability_excel_lines(confidence):
    """Short lines for Job Summary tab in Excel."""
    if not confidence:
        return []
    lines = [
        ('Takeoff confidence:', confidence.get('title', '')),
        ('Data summary:', confidence.get('summary_line', '')),
    ]
    for f in confidence.get('fields', [])[:6]:
        if f.get('critical'):
            badge = f.get('source_label', '')
            lines.append((f'{f["label"]}:', f'{f.get("display", "")} ({badge})'))
    return lines