"""Roofr measurement report parser."""
import re


def _num(s):
    if s is None:
        return None
    try:
        return float(str(s).replace(',', '').strip())
    except ValueError:
        return None


def _ft_in_to_decimal(text):
    """Parse '167ft 3in' or '133ft 0in' to decimal feet."""
    if not text:
        return None
    m = re.search(r'(\d+)\s*ft\s*(\d+)\s*in', str(text), re.I)
    if m:
        return int(m.group(1)) + int(m.group(2)) / 12.0
    m2 = re.search(r'([\d.]+)\s*ft', str(text), re.I)
    return _num(m2.group(1)) if m2 else None


def parse_roofr_report(text):
    m = {'structures': []}
    warnings = []

    addr = re.search(r'(\d+[^\n]+,\s*OH\s*\d{5})', text, re.I)
    m['property_address'] = addr.group(1).strip() if addr else ''

    m['roof_area_sqft'] = _num(re.search(r'Total roof area[:\s]+(\d[\d,]*)\s*sqft', text, re.I))
    if m['roof_area_sqft'] is None:
        m['roof_area_sqft'] = _num(re.search(r'Total roof area\s+(\d[\d,]*)\s*sqft', text, re.I))

    facets = re.search(r'(\d+)\s*facets', text, re.I)
    m['facets'] = int(facets.group(1)) if facets else None

    pitch = re.search(r'Predominant pitch\s+(\d+/\d+)', text, re.I)
    m['predominant_pitch'] = pitch.group(1) if pitch else ''

    if m['roof_area_sqft']:
        m['roof_area_squares'] = round(m['roof_area_sqft'] / 100, 1)

    # Summary section measurements
    def _summary_ft(label):
        pat = rf'Total {label}\s+(\d+ft\s*\d+in|\d+ft)'
        hit = re.search(pat, text, re.I)
        return _ft_in_to_decimal(hit.group(1)) if hit else None

    m['eaves_ft'] = _summary_ft('eaves')
    m['rakes_ft'] = _summary_ft('rakes')
    m['valleys_ft'] = _summary_ft('valleys')
    m['ridges_ft'] = _summary_ft('ridges')
    m['hips_ft'] = _summary_ft('hips') or 0
    m['step_flashing_ft'] = _summary_ft('step flashing')
    m['wall_flashing_ft'] = _summary_ft('wall flashing')

    er = re.search(r'Total eaves \+ rakes\s+(\d+ft\s*\d+in|\d+ft)', text, re.I)
    m['drip_edge_ft'] = _ft_in_to_decimal(er.group(1)) if er else None
    if m['drip_edge_ft'] is None and m.get('eaves_ft') and m.get('rakes_ft'):
        m['drip_edge_ft'] = m['eaves_ft'] + m['rakes_ft']

    hr = re.search(r'Total hips \+ ridges\s+(\d+ft\s*\d+in|\d+ft)', text, re.I)
    if hr:
        m['ridges_ft'] = _ft_in_to_decimal(hr.group(1))

    # Roofr waste table row
    waste_row = re.search(
        r'Waste\s*%\s+0%\s+10%\s+12%\s+13%.*?\nSquares\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)',
        text,
        re.I | re.DOTALL,
    )
    m['waste_table'] = {}
    if waste_row:
        for pct, val in zip((0, 10, 12, 13), waste_row.groups()):
            m['waste_table'][pct] = _num(val)

    if not m.get('roof_area_sqft'):
        warnings.append('Could not parse total roof area from Roofr report.')

    return m, warnings