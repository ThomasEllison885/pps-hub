"""Detect and parse roofing measurement PDFs (EagleView or Roofr)."""
import re

from estimators.siding.pdf_extract import extract_pdf_text

from .eagleview_bid import parse_eagleview_bid
from .eagleview_premium import parse_eagleview_premium
from .roofr import parse_roofr_report


def _detect_type(text):
    low = text.lower()
    if 'bid perfect' in low:
        return 'bid_perfect'
    if 'roofr.com' in low or 'prepared by roofr' in low:
        return 'roofr'
    if 'premium report' in low:
        return 'premium'
    if 'total roof area' in low and 'ridges' in low and 'eaves' in low:
        return 'premium'
    if 'roof total area' in low and 'squares' in low:
        return 'bid_perfect'
    return 'unknown'


def parse_roof_report(pdf_bytes):
    """
    Parse uploaded roof report PDF.
    Returns (measurements dict, warnings list).
    """
    text = extract_pdf_text(pdf_bytes)
    report_type = _detect_type(text)
    warnings = []

    if report_type == 'bid_perfect':
        m, w = parse_eagleview_bid(text)
    elif report_type == 'roofr':
        m, w = parse_roofr_report(text)
    elif report_type == 'premium':
        m, w = parse_eagleview_premium(text)
    else:
        m, w = {}, [f'Unrecognized report format — expected EagleView or Roofr.']

    m['report_type'] = report_type
    warnings = list(warnings) + list(w)

    if report_type == 'bid_perfect':
        warnings.append(
            'Bid Perfect report: generating a quick bid estimate only. '
            'Upload a Premium EagleView or Roofr report for a full GAF material list.'
        )
    elif report_type == 'unknown':
        pass
    elif not m.get('roof_area_sqft') and not m.get('structures'):
        warnings.append('Could not parse roof area — verify the PDF or enter measurements manually.')

    return m, warnings