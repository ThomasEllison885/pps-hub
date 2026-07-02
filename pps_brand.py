"""
PPS document brand constants — single source for hub-generated documents.

Use for colors, fonts, and static asset paths only. Layout and structure stay in
each builder until a change is proven visually identical (byte-for-byte Word/Excel
comparison on real outputs).

PROPOSAL BUILDER POLICY (pps-proposal-tool/docx_builder.py):
  FROZEN — do not change layout or structure without side-by-side Word regression
  on real proposals (multi-option, condo, T&M, long scope). Future unification
  should import these constants only after proving visually identical output.
"""
import os

from docx.shared import RGBColor

# ── RGB (python-docx) ────────────────────────────────────────────────────────

DARK_BLUE = RGBColor(0x00, 0x4C, 0x8C)
BLUE = RGBColor(0x00, 0x96, 0xD6)
LIGHT_BG = RGBColor(0xEB, 0xF6, 0xFC)
GRAY = RGBColor(0x44, 0x44, 0x44)
MID_GRAY = RGBColor(0x88, 0x88, 0x88)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
BODY_TEXT = RGBColor(0x33, 0x33, 0x33)
LIGHT_GRAY = RGBColor(0x99, 0x99, 0x99)
BLACK = RGBColor(0x1A, 0x1A, 0x1A)

# ── Hex (openpyxl, oxml borders, inline HTML) ────────────────────────────────

DARK_BLUE_HEX = '004C8C'
BLUE_HEX = '0096D6'
LIGHT_BG_HEX = 'EBF6FC'
WHITE_HEX = 'FFFFFF'
GRAY_HDR_HEX = 'F2F7FB'
WARNING_HEX = 'FFF3CD'
BORDER_HEX = 'D0DCE8'
GRAY_HEX = 'CCCCCC'

# ── Fonts ────────────────────────────────────────────────────────────────────

FONT_BODY = 'Arial'
FONT_HEADING = 'Georgia'

# ── Copy ─────────────────────────────────────────────────────────────────────

TAGLINE = 'The Pure Way: Trust. Quality. Results.™'
EMAIL_INTERNAL_NOTICE = (
    'Internal use only — email this file to yourself (especially on mobile) or a '
    'coworker. Review before any client delivery.'
)

# ── Hub static assets ────────────────────────────────────────────────────────

HUB_ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(HUB_ROOT, 'static')
LOGO_PATH = os.path.join(STATIC_DIR, 'logo.png')
TAGLINE_PATH = os.path.join(STATIC_DIR, 'PPS_statement1_MED.jpg')