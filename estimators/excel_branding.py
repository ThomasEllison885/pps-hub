"""PPS logo and motto on estimator Excel deliverables."""
import os

from openpyxl.drawing.image import Image

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(_PKG_ROOT, 'static')
LOGO_PATH = os.path.join(STATIC_DIR, 'logo.png')
MOTTO_PATH = os.path.join(STATIC_DIR, 'PPS_statement1_MED.jpg')


def _place_image(ws, path, anchor, width, height):
    if not os.path.isfile(path):
        return False
    img = Image(path)
    img.width = width
    img.height = height
    ws.add_image(img, anchor)
    return True


def add_header_branding(ws, logo_anchor='B1', motto_anchor='E1'):
    """Row 1: company logo + motto image (title bar stays on row 2)."""
    ws.row_dimensions[1].height = 54
    _place_image(ws, LOGO_PATH, logo_anchor, 150, 50)
    _place_image(ws, MOTTO_PATH, motto_anchor, 320, 38)


def add_footer_branding(ws, row=None, logo_anchor=None, motto_anchor=None):
    """Footer row on final tab — logo + motto."""
    row = row or max((ws.max_row or 1) + 3, 5)
    ws.row_dimensions[row].height = 46
    logo_anchor = logo_anchor or f'B{row}'
    motto_anchor = motto_anchor or f'E{row}'
    _place_image(ws, LOGO_PATH, logo_anchor, 115, 38)
    _place_image(ws, MOTTO_PATH, motto_anchor, 280, 34)
    return row


def brand_estimate_workbook(wb):
    """Header on first sheet, footer on last sheet."""
    sheets = wb.worksheets
    if not sheets:
        return
    add_header_branding(sheets[0])
    add_footer_branding(sheets[-1])