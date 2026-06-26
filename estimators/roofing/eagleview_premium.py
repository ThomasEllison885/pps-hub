"""EagleView Premium Roof report parser."""
import re


def _num(s):
    if s is None:
        return None
    try:
        return float(str(s).replace(',', '').strip())
    except ValueError:
        return None


def _find(pattern, text, flags=re.IGNORECASE):
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def parse_eagleview_premium(text):
    m = {'structures': []}
    warnings = []

    m['report_number'] = _find(r'Report:\s*(\w+)', text) or ''
    m['report_date'] = _find(
        r'((?:January|February|March|April|May|June|July|August|September|October|November|December|'
        r'Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d+,\s*\d{4})',
        text,
    ) or ''
    addr = _find(
        r'(\d+[^\n]+(?:OH|IN|KY|TN|IL|MI|WI|MN|IA|MO|KS|NE|TX|FL|GA|NC|SC|VA|PA|NY|CA)[\s,]+\d{5}(?:-\d{4})?)',
        text,
    )
    m['property_address'] = addr or ''

    m['roof_area_sqft'] = _num(_find(r'Total Roof Area\s*=\s*([\d,]+\.?\d*)\s*sq ft', text))
    m['facets'] = _num(_find(r'Total Roof Facets\s*=\s*(\d+)', text))
    pitch = _find(r'Predominant Pitch\s*=\s*(\d+/\d+)', text)
    m['predominant_pitch'] = pitch or ''

    m['ridges_ft'] = _num(_find(r'Ridges\s*=\s*([\d,]+\.?\d*)\s*ft', text))
    m['hips_ft'] = _num(_find(r'Hips\s*=\s*([\d,]+\.?\d*)\s*ft', text))
    m['valleys_ft'] = _num(_find(r'Valleys\s*=\s*([\d,]+\.?\d*)\s*ft', text))
    m['rakes_ft'] = _num(_find(r'Rakes[^\n=]*=\s*([\d,]+\.?\d*)\s*ft', text))
    m['eaves_ft'] = _num(_find(r'Eaves/Starter[^\n=]*=\s*([\d,]+\.?\d*)\s*ft', text))
    if m['eaves_ft'] is None:
        m['eaves_ft'] = _num(_find(r'Eaves\s*=\s*([\d,]+\.?\d*)\s*ft', text))
    m['step_flashing_ft'] = _num(_find(r'Step flashing\s*=\s*([\d,]+\.?\d*)\s*ft', text))
    m['wall_flashing_ft'] = _num(_find(r'Flashing\s*=\s*([\d,]+\.?\d*)\s*ft', text))
    m['drip_edge_ft'] = _num(_find(r'Drip Edge[^\n=]*=\s*([\d,]+\.?\d*)\s*ft', text))

    if m['roof_area_sqft']:
        m['roof_area_squares'] = round(m['roof_area_sqft'] / 100, 2)

    # Waste table: Squares * 80.33 81.00 85.00 ...
    waste_match = re.search(
        r'Waste\s*%\s+([\d%\s]+)\nArea\s*\(Sq ft\)\s+([\d\s]+)\nSquares\s*\*\s+([\d.\s]+)',
        text,
        re.IGNORECASE,
    )
    m['waste_table'] = {}
    if waste_match:
        pcts = [int(x) for x in re.findall(r'(\d+)%', waste_match.group(1))]
        squares = [_num(x) for x in waste_match.group(3).split()]
        for pct, sq in zip(pcts, squares):
            if pct is not None and sq is not None:
                m['waste_table'][pct] = sq

    required = [
        ('roof_area_sqft', 'Total roof area'),
        ('eaves_ft', 'Eaves length'),
        ('rakes_ft', 'Rakes length'),
    ]
    for key, label in required:
        if m.get(key) is None:
            warnings.append(f'Could not parse: {label}')

    return m, warnings