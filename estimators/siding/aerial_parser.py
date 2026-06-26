"""Best-effort parser for non-EagleView aerial measurement PDFs."""
import re

from .eagleview_parser import _num
from .pdf_extract import extract_pdf_text


def _find_num(text, patterns):
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            val = _num(match.group(1))
            if val is not None:
                return val
    return None


def parse_aerial_report(pdf_bytes):
    """
    Try common measurement labels used across aerial report vendors.
    Returns (measurements dict, warnings list).
    """
    text = extract_pdf_text(pdf_bytes)
    m = {}
    warnings = ['Parsed as generic aerial report — review all values before generating.']

    m['report_number'] = ''
    addr = re.search(
        r'(\d+[^\n]{5,80}(?:IN|OH|KY|TN|IL|MI|WI|MN|IA|MO|KS|NE|SD|ND|MT|WY|CO|NM|AZ|UT|NV|ID|WA|OR|CA|AK|HI|TX|OK|AR|LA|MS|AL|GA|FL|SC|NC|VA|WV|MD|DE|NJ|NY|CT|RI|MA|VT|NH|ME|PA)[\s,]+\d{5})',
        text,
        re.IGNORECASE,
    )
    m['property_address'] = addr.group(1).strip() if addr else ''
    m['report_date'] = ''

    m['wall_area_net'] = _find_num(text, [
        r'Wall Area\s*[=:]\s*([\d,]+\.?\d*)\s*sq\.?\s*ft',
        r'Net Wall(?:\s+Area)?\s*[=:]\s*([\d,]+\.?\d*)\s*sq\.?\s*ft',
        r'Total Wall Area\s*[=:]\s*([\d,]+\.?\d*)\s*sq\.?\s*ft',
    ])
    m['wall_area_gross'] = _find_num(text, [
        r'Wall Area with Windows and Doors\s*[=:]\s*([\d,]+\.?\d*)\s*sq\.?\s*ft',
        r'Gross Wall(?:\s+Area)?\s*[=:]\s*([\d,]+\.?\d*)\s*sq\.?\s*ft',
    ])
    if m['wall_area_gross'] is None and m['wall_area_net']:
        m['wall_area_gross'] = m['wall_area_net']

    m['window_door_area'] = _find_num(text, [
        r'Window and Door Area\s*[=:]\s*([\d,]+\.?\d*)\s*sq\.?\s*ft',
        r'Opening(?:\s+Area)?\s*[=:]\s*([\d,]+\.?\d*)\s*sq\.?\s*ft',
    ])
    m['window_door_perimeter'] = _find_num(text, [
        r'Window and Door Perimeter\s*[=:]\s*([\d,]+\.?\d*)\s*ft',
        r'Opening Perimeter\s*[=:]\s*([\d,]+\.?\d*)\s*ft',
    ])
    wd_count = re.search(r'(?:Total )?Windows and Doors\s*[=:]\s*(\d+)', text, re.IGNORECASE)
    m['window_door_count'] = int(wd_count.group(1)) if wd_count else None

    m['inside_corners'] = _find_num(text, [
        r'Inside Corners?\s*[=:]\s*([\d,]+\.?\d*)\s*ft',
    ])
    m['outside_corners'] = _find_num(text, [
        r'Outside Corners?\s*[=:]\s*([\d,]+\.?\d*)\s*ft',
    ])
    m['fascia'] = _find_num(text, [
        r'Fascia(?:\s*\(Eaves\s*\+\s*Rake\))?\s*[=:]\s*([\d,]+\.?\d*)\s*ft',
        r'Eaves\s*\+\s*Rake\s*[=:]\s*([\d,]+\.?\d*)\s*ft',
    ])
    m['soffit'] = _find_num(text, [
        r'Soffit\s*[=:]\s*([\d,]+\.?\d*)\s*ft',
    ])

    m['wall_facets'] = None
    m['waste_table'] = {}
    m['wall_north'] = m['wall_east'] = m['wall_south'] = m['wall_west'] = None

    required = {
        'wall_area_net': 'Net Wall Area (sq ft)',
        'wall_area_gross': 'Gross Wall Area with Openings (sq ft)',
        'window_door_perimeter': 'Window & Door Perimeter (lin ft)',
        'inside_corners': 'Inside Corners (lin ft)',
        'outside_corners': 'Outside Corners (lin ft)',
    }
    for key, label in required.items():
        if m.get(key) is None:
            warnings.append(f'Could not parse: {label} — enter manually or use field measurements')

    return m, warnings