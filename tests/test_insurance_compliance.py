"""Kind-sniffing for COI files — no Monday / DB required."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import insurance_compliance as ic


def test_sniff_pdf_by_extension_and_magic():
    assert ic.sniff_coi_kind('ACORD-25.pdf') == 'pdf'
    assert ic.sniff_coi_kind('scan.jpg', b'%PDF-1.4 leftover') == 'pdf'


def test_sniff_image_by_extension():
    assert ic.sniff_coi_kind('Kings of Business.JPG') == 'image'
    assert ic.sniff_coi_kind('coi.heic') == 'image'
    assert ic.sniff_coi_kind('photo.PNG') == 'image'


def test_sniff_image_by_magic_even_when_named_pdf():
    jpeg = b'\xff\xd8\xff\xe0' + b'\x00' * 20
    assert ic.sniff_coi_kind('COI.pdf', jpeg) == 'image'
    png = b'\x89PNG\r\n\x1a\n' + b'\x00' * 8
    assert ic.sniff_coi_kind('certificate.pdf', png) == 'image'


def test_sniff_unknown_stays_other():
    assert ic.sniff_coi_kind('agreement.docx') == 'other'
    assert ic.sniff_coi_kind('') == 'other'


def test_content_type_for_images_and_pdfs():
    assert ic.content_type_for_coi('pdf', 'x.pdf') == 'application/pdf'
    assert ic.content_type_for_coi('image', 'shot.jpg') == 'image/jpeg'
    assert ic.content_type_for_coi('image', 'shot.HEIC') == 'image/heic'
