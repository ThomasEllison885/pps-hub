"""Kind-sniffing for COI files, and the vision-pass batch — no Monday / DB required."""
import os
import sys
from datetime import date

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


def test_parse_date_string_accepts_iso_and_slash_and_match():
    assert ic._parse_date_string('2027-03-01') == date(2027, 3, 1)
    assert ic._parse_date_string('03/01/2027') == date(2027, 3, 1)
    assert ic._parse_date_string('3/1/27') == date(2027, 3, 1)
    assert ic._parse_date_string('null') is None
    assert ic._parse_date_string('') is None
    m = ic._DATE_RE.search('exp 03/15/2026 something')
    assert ic._parse_date_string(m) == date(2026, 3, 15)


# --- vision pass (2026-08-13) -----------------------------------------------
# Claude vision auto-reads photo COIs that have no PDF text layer, filling
# the same insurance_expires_extracted/extract_confidence columns the PDF
# path already uses. Not automatic — an admin-triggered batch over whatever
# is currently in "needs manual entry". See CLAUDE.md for the full writeup.

def test_extract_coi_fields_vision_rejects_unsupported_type_without_calling_api():
    # HEIC sniffs as 'image' for the Hub's <img> viewer, but Claude's vision
    # API only takes jpeg/png/gif/webp. Passing a bogus key/model here proves
    # no network call is attempted -- an exception would mean it tried.
    result = ic._extract_coi_fields_vision(
        b'not-really-an-image', 'image/heic', api_key='bogus', model='bogus-model',
    )
    assert result == {
        'gl_exp': None, 'wc_exp': None, 'additional_insured': None,
        'confidence': 'unsupported_image_type',
    }


class _FakeVisionCursor:
    def __init__(self):
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql.strip(), params))


class _FakeVisionConn:
    def __init__(self):
        self.cur = _FakeVisionCursor()
        self.committed = False
        self.closed = False

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def _needs_manual_row(item_id='item-1', name='Test Sub', coi_kind='image'):
    return {
        'item_id': item_id, 'name': name, 'group': 'Sub contractors - Compliant',
        'manual_ins': None, 'manual_wc': None, 'extracted_ins': None,
        'confidence': 'image_file', 'additional_insured': None,
        'override_ins': None, 'override_by': None, 'effective_ins': None,
        'effective_source': None, 'is_new': False, 'coi_name': 'photo.jpg',
        'coi_asset_id': '999', 'coi_kind': coi_kind, 'has_viewable_coi': True,
        'needs_manual_review': True,
    }


def test_run_vision_pass_no_api_key_returns_error_without_touching_db(monkeypatch):
    def get_db_fn_should_not_be_called():
        raise AssertionError('run_vision_pass should fail fast on a missing API key')
    result = ic.run_vision_pass(get_db_fn_should_not_be_called, api_key='', model='claude-x')
    assert result == {'error': 'Claude API key not configured on hub (CLAUDE_API_KEY).'}


def test_is_vision_target_photos_and_scanned_pdfs_not_empty_rows():
    photo = _needs_manual_row(coi_kind='image')
    scanned = _needs_manual_row(coi_kind='pdf')
    scanned['confidence'] = 'no_dates_found'
    empty = _needs_manual_row(coi_kind=None)
    empty['coi_name'] = None
    empty['has_viewable_coi'] = False
    assert ic.is_vision_target(photo) is True
    assert ic.is_vision_target(scanned) is True
    assert ic.is_vision_target(empty) is False


def test_run_vision_pass_includes_scanned_pdfs(monkeypatch):
    row = _needs_manual_row(coi_kind='pdf')
    row['confidence'] = 'no_dates_found'
    row['coi_name'] = 'scan.pdf'
    monkeypatch.setattr(ic, 'get_latest_snapshot_rows', lambda get_db_fn: ([row], None))
    monkeypatch.setattr(ic, 'load_coi_asset',
                         lambda get_db_fn, item_id: (b'%PDF-fake', 'scan.pdf', 'application/pdf', None))
    monkeypatch.setattr(ic, '_pdf_first_page_jpeg', lambda data: b'jpeg-bytes')
    monkeypatch.setattr(ic, '_extract_coi_fields_vision',
                         lambda data, content_type, api_key, model: {
                             'gl_exp': date(2027, 6, 1), 'wc_exp': None,
                             'additional_insured': None, 'confidence': 'vision_extracted',
                         })
    conn = _FakeVisionConn()
    result = ic.run_vision_pass(lambda: conn, api_key='k', model='m')
    assert result['dated'] == 1
    assert result['attempted'] == 1


def test_run_vision_pass_writes_extracted_date_on_confident_read(monkeypatch):
    row = _needs_manual_row()
    monkeypatch.setattr(ic, 'get_latest_snapshot_rows', lambda get_db_fn: ([row], None))
    monkeypatch.setattr(ic, 'load_coi_asset',
                         lambda get_db_fn, item_id: (b'fake-bytes', 'photo.jpg', 'image/jpeg', None))
    monkeypatch.setattr(ic, '_extract_coi_fields_vision',
                         lambda data, content_type, api_key, model: {
                             'gl_exp': date(2027, 3, 1), 'wc_exp': None,
                             'additional_insured': None, 'confidence': 'vision_extracted',
                         })

    conn = _FakeVisionConn()
    result = ic.run_vision_pass(lambda: conn, api_key='k', model='m')

    assert result == {'attempted': 1, 'dated': 1, 'uncertain': 0, 'errors': 0, 'remaining': 0,
                       'details': [{'name': 'Test Sub', 'outcome': 'read 2027-03-01'}]}
    assert conn.committed is True
    sql, params = conn.cur.executed[0]
    assert 'UPDATE office_ops_tp_snapshot' in sql
    assert params == (date(2027, 3, 1), 'vision_extracted', 'item-1')


def test_run_vision_pass_uncertain_read_leaves_date_null_but_records_confidence(monkeypatch):
    row = _needs_manual_row()
    monkeypatch.setattr(ic, 'get_latest_snapshot_rows', lambda get_db_fn: ([row], None))
    monkeypatch.setattr(ic, 'load_coi_asset',
                         lambda get_db_fn, item_id: (b'fake-bytes', 'photo.jpg', 'image/jpeg', None))
    monkeypatch.setattr(ic, '_extract_coi_fields_vision',
                         lambda data, content_type, api_key, model: {
                             'gl_exp': None, 'wc_exp': None,
                             'additional_insured': None, 'confidence': 'vision_uncertain',
                         })

    conn = _FakeVisionConn()
    result = ic.run_vision_pass(lambda: conn, api_key='k', model='m')

    assert result['dated'] == 0
    assert result['uncertain'] == 1
    sql, params = conn.cur.executed[0]
    assert params == (None, 'vision_uncertain', 'item-1')


def test_run_vision_pass_fetch_failure_counts_as_error_and_skips_update(monkeypatch):
    row = _needs_manual_row()
    monkeypatch.setattr(ic, 'get_latest_snapshot_rows', lambda get_db_fn: ([row], None))
    monkeypatch.setattr(ic, 'load_coi_asset',
                         lambda get_db_fn, item_id: (None, None, None, 'Could not get a download URL from Monday'))

    conn = _FakeVisionConn()
    result = ic.run_vision_pass(lambda: conn, api_key='k', model='m')

    assert result['errors'] == 1
    assert result['attempted'] == 1
    assert conn.cur.executed == []  # never reached the UPDATE


def test_run_vision_pass_limit_caps_batch_and_reports_remaining(monkeypatch):
    # 5 rows, limit=2 -- a big board must not run as one long request that
    # can outlast gunicorn's worker timeout (render.yaml: --timeout 120).
    rows = [_needs_manual_row(item_id=f'item-{i}', name=f'Sub {i}') for i in range(5)]
    monkeypatch.setattr(ic, 'get_latest_snapshot_rows', lambda get_db_fn: (rows, None))
    monkeypatch.setattr(ic, 'load_coi_asset',
                         lambda get_db_fn, item_id: (b'fake-bytes', 'photo.jpg', 'image/jpeg', None))
    monkeypatch.setattr(ic, '_extract_coi_fields_vision',
                         lambda data, content_type, api_key, model: {
                             'gl_exp': date(2027, 1, 1), 'wc_exp': None,
                             'additional_insured': None, 'confidence': 'vision_extracted',
                         })

    conn = _FakeVisionConn()
    result = ic.run_vision_pass(lambda: conn, api_key='k', model='m', limit=2)

    assert result['attempted'] == 2
    assert result['dated'] == 2
    assert result['remaining'] == 3
    assert len(conn.cur.executed) == 2


def test_run_vision_pass_no_limit_processes_everything_with_zero_remaining(monkeypatch):
    rows = [_needs_manual_row(item_id=f'item-{i}', name=f'Sub {i}') for i in range(3)]
    monkeypatch.setattr(ic, 'get_latest_snapshot_rows', lambda get_db_fn: (rows, None))
    monkeypatch.setattr(ic, 'load_coi_asset',
                         lambda get_db_fn, item_id: (b'fake-bytes', 'photo.jpg', 'image/jpeg', None))
    monkeypatch.setattr(ic, '_extract_coi_fields_vision',
                         lambda data, content_type, api_key, model: {
                             'gl_exp': date(2027, 1, 1), 'wc_exp': None,
                             'additional_insured': None, 'confidence': 'vision_extracted',
                         })

    conn = _FakeVisionConn()
    result = ic.run_vision_pass(lambda: conn, api_key='k', model='m')

    assert result['attempted'] == 3
    assert result['remaining'] == 0
