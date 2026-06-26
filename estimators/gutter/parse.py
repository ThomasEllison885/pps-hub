"""Extract gutter-relevant measurements from roof report PDFs."""

from estimators.roofing.parse import parse_roof_report

from .calculator import DEFAULTS, _suggest_downspouts


def _estimate_gutter_lf_from_sqft(sqft):
    """Industry rule of thumb: home sq ft ÷ 10 ≈ gutter linear feet."""
    if not sqft:
        return None
    return round(float(sqft) / 10, 1)


def parse_gutter_measurements(pdf_bytes):
    """
    Parse roof PDF for gutter takeoff fields.
    Returns (measurements dict, warnings list).
    """
    warnings = []
    try:
        roof, roof_warnings = parse_roof_report(pdf_bytes)
    except Exception as exc:
        return {}, [str(exc)]

    warnings.extend(roof_warnings)
    report_type = roof.get('report_type', 'unknown')

    eaves_ft = roof.get('eaves_ft')
    gutter_lf = eaves_ft

    if not gutter_lf and roof.get('roof_area_sqft'):
        est = _estimate_gutter_lf_from_sqft(roof['roof_area_sqft'])
        if est:
            gutter_lf = est
            warnings.append(
                f'No eaves length in report — estimated gutter run as roof sq ft ÷ 10 ({est} LF). Verify on site.'
            )

    if report_type == 'bid_perfect' and not eaves_ft:
        sq = roof.get('roof_area_squares') or 0
        if sq:
            gutter_lf = round(sq * 10, 1)  # squares × 10 ≈ LF for multi-structure bid reports
            warnings.append(
                f'Bid Perfect has no eaves — rough gutter estimate from {sq} squares × 10 = {gutter_lf} LF.'
            )

    gutter_lf = gutter_lf or 0
    spacing = DEFAULTS['downspout_spacing_ft']
    ds_each = DEFAULTS['downspout_lf_each']
    suggested_ds = _suggest_downspouts(gutter_lf, spacing) if gutter_lf else 2

    measurements = {
        'report_type': report_type,
        'report_number': roof.get('report_number', ''),
        'report_date': roof.get('report_date', ''),
        'property_address': roof.get('property_address', ''),
        'roof_area_sqft': roof.get('roof_area_sqft'),
        'roof_area_squares': roof.get('roof_area_squares'),
        'eaves_ft': eaves_ft,
        'rakes_ft': roof.get('rakes_ft'),
        'gutter_lf': gutter_lf,
        'suggested_downspout_count': suggested_ds,
        'suggested_downspout_lf': round(suggested_ds * ds_each, 1),
        'structures': roof.get('structures') or [],
    }

    if gutter_lf and not eaves_ft:
        warnings.append(
            f'Suggested {suggested_ds} downspouts ({suggested_ds * ds_each} LF vertical) '
            f'from {gutter_lf} LF gutter run — verify on site.'
        )
    elif gutter_lf:
        warnings.append(
            f'Suggested {suggested_ds} downspouts at 1 per {spacing:.0f} LF of gutter — editable below.'
        )

    if not measurements['gutter_lf']:
        warnings.append('Could not determine gutter run — enter linear feet manually.')

    return measurements, warnings