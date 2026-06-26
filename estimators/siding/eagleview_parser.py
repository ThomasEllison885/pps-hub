"""EagleView Walls Only report parser."""
import re

from .pdf_extract import extract_pdf_text


def _num(s):
    try:
        return float(s.replace(',', '').strip())
    except Exception:
        return None


def parse_eagleview_walls(pdf_bytes):
    """
    Parse an EagleView Walls Only report PDF.
    Returns (measurements dict, warnings list).
    """
    text = extract_pdf_text(pdf_bytes)
    m = {}
    warnings = []

    def find(pattern, flags=re.IGNORECASE):
        return re.search(pattern, text, flags)

    r = find(r'Report:\s*(\w+)')
    m['report_number'] = r.group(1) if r else ''

    r = find(
        r'(\d+[^\n]+(?:IN|OH|KY|TN|IL|MI|WI|MN|IA|MO|KS|NE|SD|ND|MT|WY|CO|NM|AZ|UT|NV|ID|WA|OR|CA|AK|HI|TX|OK|AR|LA|MS|AL|GA|FL|SC|NC|VA|WV|MD|DE|NJ|NY|CT|RI|MA|VT|NH|ME|PA)[\s,]+\d{5})'
    )
    m['property_address'] = r.group(1).strip() if r else ''

    r = find(
        r'((?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d+,\s*\d{4})'
    )
    m['report_date'] = r.group(1).strip() if r else ''

    r = find(r'Wall Area\s*=\s*([\d,]+\.?\d*)\s*sq ft')
    m['wall_area_net'] = _num(r.group(1)) if r else None

    r = find(r'Wall Area with Windows and Doors\s*=\s*([\d,]+\.?\d*)\s*sq ft')
    m['wall_area_gross'] = _num(r.group(1)) if r else None

    r = find(r'Window and Door Area\s*=\s*([\d,]+\.?\d*)\s*sq ft')
    m['window_door_area'] = _num(r.group(1)) if r else None

    r = find(r'Window and Door Perimeter\s*=\s*([\d,]+\.?\d*)\s*ft')
    m['window_door_perimeter'] = _num(r.group(1)) if r else None

    r = find(r'Total Windows and Doors\s*=\s*(\d+)')
    m['window_door_count'] = int(r.group(1)) if r else None

    r = find(r'Total Wall Facets\s*=\s*(\d+)')
    m['wall_facets'] = int(r.group(1)) if r else None

    r = find(r'Inside Corners\s*=\s*([\d,]+\.?\d*)\s*ft')
    m['inside_corners'] = _num(r.group(1)) if r else None

    r = find(r'Outside Corners\s*=\s*([\d,]+\.?\d*)\s*ft')
    m['outside_corners'] = _num(r.group(1)) if r else None

    r = find(r'Fascia\s*(?:\(Eaves\s*\+\s*Rake\))?\s*=\s*([\d,]+\.?\d*)\s*ft')
    m['fascia'] = _num(r.group(1)) if r else None

    r = find(r'Soffit\s*=\s*([\d,]+\.?\d*)\s*ft')
    m['soffit'] = _num(r.group(1)) if r else None

    waste_table = {}
    pcts_match = re.search(
        r'Waste\s*%\s+0%\s+(\d+)%\s+(\d+)%\s+(\d+)%\s+(\d+)%\s+(\d+)%\s+(\d+)%\s+(\d+)%',
        text,
    )
    area_match = re.search(
        r'Area.*?(5[,\d]+\.?\d*)\s+(5[,\d]+\.?\d*)\s+(5[,\d]+\.?\d*)\s+(5[,\d]+\.?\d*)\s+(5[,\d]+\.?\d*)\s+(5[,\d]+\.?\d*)\s+(5[,\d]+\.?\d*)\s+(6[,\d]+\.?\d*)',
        text,
        re.DOTALL,
    )
    if pcts_match and area_match:
        pcts_list = [0] + [int(pcts_match.group(i)) for i in range(1, 8)]
        areas_list = [_num(area_match.group(i)) for i in range(1, 9)]
        for p, a in zip(pcts_list, areas_list):
            waste_table[p] = a
    m['waste_table'] = waste_table

    dir_section = re.search(
        r'North\s+East\s+South\s+West.*?([\d,]+\.\d+)\s+sq\s+ft\s+([\d,]+\.\d+)\s+sq\s+ft\s+([\d,]+\.\d+)\s+sq\s+ft\s+([\d,]+\.\d+)\s+sq\s+ft',
        text,
        re.DOTALL,
    )
    if dir_section:
        m['wall_north'] = _num(dir_section.group(1))
        m['wall_east'] = _num(dir_section.group(2))
        m['wall_south'] = _num(dir_section.group(3))
        m['wall_west'] = _num(dir_section.group(4))
    else:
        m['wall_north'] = m['wall_east'] = m['wall_south'] = m['wall_west'] = None

    required = {
        'wall_area_net': 'Net Wall Area (sq ft)',
        'wall_area_gross': 'Gross Wall Area with Openings (sq ft)',
        'window_door_area': 'Window & Door Area (sq ft)',
        'window_door_perimeter': 'Window & Door Perimeter (lin ft)',
        'window_door_count': 'Window & Door Count',
        'inside_corners': 'Inside Corners (lin ft)',
        'outside_corners': 'Outside Corners (lin ft)',
        'fascia': 'Fascia / Eaves + Rake (lin ft)',
    }
    for key, label in required.items():
        if m.get(key) is None:
            warnings.append(f'Could not parse: {label} — please enter manually')

    return m, warnings