"""EagleView Bid Perfect report parser."""
import re


def _num(s):
    if s is None:
        return None
    try:
        return float(str(s).replace(',', '').strip())
    except ValueError:
        return None


def parse_eagleview_bid(text):
    m = {'structures': []}
    warnings = []

    m['report_number'] = ''
    rep = re.search(r'Report:\s*(\d+)', text, re.I)
    if rep:
        m['report_number'] = rep.group(1)

    date_m = re.search(
        r'((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d+,\s*\d{4})',
        text,
        re.I,
    )
    m['report_date'] = date_m.group(1) if date_m else ''

    addr = re.search(
        r'(\d+[^\n]+(?:OH|IN|KY|TN|IL|MI)[\s,]+\d{5})',
        text,
    )
    m['property_address'] = addr.group(1).strip() if addr else ''

    total_squares = 0.0
    for sm in re.finditer(r'#\s*(\d+)\s+([\d.]+)\s+squares', text, re.I):
        sq = float(sm.group(2))
        total_squares += sq
        m['structures'].append({
            'label': f"Structure #{sm.group(1)}",
            'squares': sq,
        })

    if total_squares:
        m['roof_area_squares'] = round(total_squares, 2)
        m['roof_area_sqft'] = round(total_squares * 100, 1)

    if not m['structures']:
        warnings.append('Could not parse structure squares from Bid Perfect report.')

    return m, warnings