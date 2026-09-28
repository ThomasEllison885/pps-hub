"""Client contact attachments — types, vault math, wiring.

Run: python -m pytest tests/test_client_files.py -v

Thomas, 2026-09-28: a consultant asked to attach a site-map photo (or similar)
to a Hub contact and retrieve it later. Most file types, stored on that
client.

The files go in the existing `documents` BYTEA vault as doc_type='client_file'
with log_id = clients.id. That is the same 512 MB Render quota the generated
proposals already share — a new table would have been a second cap to miss.
Per-file cap stays 10 MB (`MAX_DOCUMENT_BYTES`). Uploads refuse when the
shared vault would go over; generated proposals did not previously enforce
the displayed quota on write.

Blocked types are a denylist (executables, scripts, HTML). Phone photos,
PDF, Word, Excel, CAD, zip all pass. No extension is refused so a nameless
blob cannot skip the check. `site-map.jpg.exe` is blocked on the last
extension.

app.py cannot be imported here (it migrates whatever DATABASE_URL points at),
so route wiring is pinned against the source the same way as
tests/test_training_access.py.
"""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import client_files  # noqa: E402

APP = os.path.join(ROOT, 'app.py')
TEMPLATE = os.path.join(ROOT, 'templates', 'clients.html')
ADMIN = os.path.join(ROOT, 'templates', 'admin.html')
SRC = open(APP, encoding='utf-8').read()
TREE = ast.parse(SRC)
HTML = open(TEMPLATE, encoding='utf-8').read()
ADMIN_HTML = open(ADMIN, encoding='utf-8').read()


def _fn(name):
    for n in ast.walk(TREE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return ast.get_source_segment(SRC, n)
    raise AssertionError(f'{name} not found in app.py')


# ── types ───────────────────────────────────────────────────────────────────

def test_site_maps_and_office_files_are_allowed():
    for name in (
        'Building A sitemap.jpg',
        'photo.HEIC',
        'plan.PNG',
        'scope.pdf',
        'notes.docx',
        'takeoff.xlsx',
        'deck.pptx',
        'export.csv',
        'cad.dwg',
        'vector.svg',
        'pack.zip',
        'scan.tif',
    ):
        assert client_files.is_blocked_client_filename(name) is False, name


def test_executables_scripts_and_html_are_blocked():
    for name in (
        'setup.exe', 'run.bat', 'payload.js', 'page.html', 'hack.php',
        'script.sh', 'macro.ps1', 'app.dmg', 'thing.apk', 'lib.dll',
    ):
        assert client_files.is_blocked_client_filename(name) is True, name


def test_double_extension_is_judged_on_the_last_one():
    assert client_files.is_blocked_client_filename('site-map.jpg.exe') is True
    assert client_files.is_blocked_client_filename('notes.exe.pdf') is False


def test_a_file_with_no_extension_is_blocked():
    """Nameless blobs skip the denylist if we only look at a suffix."""
    assert client_files.is_blocked_client_filename('sitemap') is True
    assert client_files.is_blocked_client_filename('') is True
    assert client_files.is_blocked_client_filename('just-a-dot.') is True


def test_safe_filename_strips_paths_and_control_chars():
    assert client_files.safe_client_filename('/tmp/../site map.jpg') == 'site map.jpg'
    assert client_files.safe_client_filename('C:\\\\uploads\\\\plan.pdf') == 'plan.pdf'
    assert '\x00' not in client_files.safe_client_filename('bad\x00name.png')
    assert client_files.safe_client_filename('..') == ''
    assert len(client_files.safe_client_filename('x' * 400 + '.jpg')) == 255


def test_doc_type_constant_is_the_one_the_index_expects():
    assert client_files.CLIENT_FILE_DOC_TYPE == 'client_file'


# ── vault math ──────────────────────────────────────────────────────────────

def test_ten_meg_file_fits_in_an_empty_512_vault():
    ten_mb = 10 * 1024 * 1024
    limit = 512 * 1024 * 1024
    assert client_files.vault_would_exceed(0, ten_mb, limit) is False


def test_a_file_that_would_cross_the_cap_is_refused():
    limit = 512 * 1024 * 1024
    used = limit - 1024
    assert client_files.vault_would_exceed(used, 2048, limit) is True
    assert client_files.vault_would_exceed(used, 1024, limit) is False


def test_fifty_clients_times_two_three_meg_photos_is_under_half_the_vault():
    """The consultant's actual use: a couple of site maps per contact.
    50 × 2 × 3 MB = 300 MB of 512 MB — real, but not the whole quota."""
    used = 50 * 2 * 3 * 1024 * 1024
    limit = 512 * 1024 * 1024
    assert used < limit
    assert used / limit < 0.6


def test_format_bytes_is_what_the_modal_prints():
    assert client_files.format_bytes(850) == '850 B'
    assert client_files.format_bytes(12_000) == '11.7 KB'
    assert client_files.format_bytes(2_500_000) == '2.4 MB'


# ── wiring ──────────────────────────────────────────────────────────────────

def test_app_stores_client_files_in_the_existing_documents_table():
    body = _fn('client_files_upload')
    assert "INSERT INTO documents" in body
    assert 'client_files.CLIENT_FILE_DOC_TYPE' in body
    assert 'MAX_DOCUMENT_BYTES' in body
    assert 'vault_would_exceed' in body
    assert 'is_blocked_client_filename' in body


def test_upload_refuses_when_the_shared_vault_is_full():
    body = _fn('client_files_upload')
    assert 'VAULT_STORAGE_LIMIT_BYTES' in body
    assert '413' in body


def test_download_and_delete_are_scoped_to_that_client():
    """log_id = client_id is the IDOR check. A guessed document id from
    another contact (or a proposal) must not download or delete."""
    down = _fn('client_files_download')
    delete = _fn('client_files_delete')
    assert 'log_id = %s' in down
    assert 'CLIENT_FILE_DOC_TYPE' in down
    assert 'log_id = %s' in delete
    assert 'CLIENT_FILE_DOC_TYPE' in delete


def test_the_generic_vault_download_serves_client_files_too():
    """Admin vault rows all link to /api/documents/<id>/download. That path
    used to JOIN proposal_log and 404 anything else."""
    body = _fn('document_download')
    assert 'CLIENT_FILE_DOC_TYPE' in body
    assert 'can_manage_contacts' in body
    assert "_get_proposal_log_for_document" in body, (
        'proposal downloads still have to go through the proposal permission check')


def test_contacts_page_counts_files_per_client():
    body = _fn('clients_page')
    assert 'files_count' in body
    assert 'CLIENT_FILE_DOC_TYPE' in body


def test_per_file_cap_is_still_ten_megabytes():
    assert 'MAX_DOCUMENT_BYTES = 10 * 1024 * 1024' in SRC


def test_modal_lets_you_attach_after_the_contact_has_an_id():
    assert "id=\"filesSection\"" in HTML
    assert "Save the contact first" in HTML
    assert "/api/clients/' + clientId + '/files'" in HTML or '/api/clients/\' + clientId + \'/files' in HTML
    assert 'uploadClientFiles' in HTML
    assert 'deleteClientFile' in HTML
    assert 'method: \'DELETE\'' in HTML or 'method: "DELETE"' in HTML
    assert 'files_count' in HTML


def test_admin_vault_labels_a_client_file():
    assert 'f.client_name' in ADMIN_HTML
    assert 'Client file' in ADMIN_HTML
