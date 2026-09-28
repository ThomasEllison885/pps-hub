"""The three hardening changes from the 2026-09-28 review.

Run: python -m pytest tests/test_hub_hardening.py -v

Thomas, 2026-09-28: "Re review the code. Especially the newest changes. Make
sure they all work and recommend any changes / updates." The client-file
attachment feature (701f605) held up — auth on every route, `textContent`
rendering so a filename cannot carry script, default-deny on an unrecognised
doc_type. These are the three gaps around it.

1. ADOPTION. Upload and delete recorded no usage, so the newest feature in the
   Hub was invisible to /admin/adoption and the nightly digest — the two
   things built specifically to stop guessing what people use. Delete gets
   recorded for a second reason: contacts are shared and anyone on the roster
   can remove anyone's attachment.

2. THE REQUEST CAP. Werkzeug parses the whole body before a view function
   runs, so the 10 MB check inside client_files_upload was already too late —
   the bytes were on Render's disk by then. MAX_CONTENT_LENGTH rejects at the
   door.

   The number is not arbitrary and that is what the test below protects:
   /analyze-diff legitimately posts TWO proposals at MAX_DOCUMENT_BYTES each,
   so the cap has to clear 2x the per-file limit with room for multipart
   framing. Raise MAX_DOCUMENT_BYTES without raising this and proposal
   comparison breaks on real files — with a 413 from the web server, not a
   message the consultant can act on.

3. NOSNIFF. Every download path today passes as_attachment=True, so a
   mislabelled MIME type is not currently an XSS vector. The header is what
   keeps that true when someone adds the next download route.

app.py is not imported here — it migrates whatever DATABASE_URL points at.
Route wiring is pinned against the source, the same way as
tests/test_client_files.py.
"""
import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import hub_usage  # noqa: E402
import weekly_recap  # noqa: E402

APP = os.path.join(ROOT, 'app.py')
SRC = open(APP, encoding='utf-8').read()
TREE = ast.parse(SRC)


def _fn(name):
    for n in ast.walk(TREE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return ast.get_source_segment(SRC, n)
    raise AssertionError(f'{name} not found in app.py')


def _int_const(name):
    """Value of a module-level `NAME = <int expr>` in app.py."""
    for node in TREE.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                return eval(compile(ast.Expression(node.value), '<app>', 'eval'))
    raise AssertionError(f'{name} is no longer a module-level constant in app.py')


# ── 1. adoption ─────────────────────────────────────────────────────────────

def test_upload_records_usage():
    src = _fn('client_files_upload')
    assert '_record_client_file_usage(' in src, (
        'attaching a file records nothing, so /admin/adoption and the nightly '
        'digest cannot see the feature at all')


def test_delete_records_usage():
    src = _fn('client_files_delete')
    assert '_record_client_file_usage(' in src, (
        'anyone on the roster can delete anyone else\'s attachment — the usage '
        'row is the only record of who did')


def test_delete_returns_the_filename_it_logs():
    """Logging `row.get('filename')` from a DELETE that only RETURNS id gives
    every delete an empty title. Caught once; pinned so it stays caught."""
    src = _fn('client_files_delete')
    m = re.search(r'RETURNING\s+([^\'"]+)', src)
    assert m, 'the delete no longer uses RETURNING'
    returned = {c.strip() for c in m.group(1).split(',')}
    assert 'filename' in returned, (
        f'delete logs a filename it does not select back: RETURNING {m.group(1)!r}')


def test_usage_helper_never_breaks_the_upload():
    src = _fn('_record_client_file_usage')
    assert 'try:' in src and 'except Exception' in src, (
        'a usage log must never be the reason an attachment fails to save')


def test_both_actions_have_a_label():
    for action in ('upload', 'delete'):
        assert action in hub_usage.ACTION_LABELS, (
            f'{action!r} would show in the digest as a raw verb')


def test_clients_is_a_known_feature():
    assert 'clients' in hub_usage.KNOWN_FEATURES


def test_deleting_is_not_worth_points():
    """A leaderboard that scored deletes would be a leaderboard for deleting
    things. Uploading is real work and stays scored."""
    assert 'delete' not in weekly_recap.SCORED_USAGE_ACTIONS
    assert 'upload' in weekly_recap.SCORED_USAGE_ACTIONS


# ── 2. the request cap ──────────────────────────────────────────────────────

def test_the_app_caps_the_request_body():
    assert "app.config['MAX_CONTENT_LENGTH']" in SRC, (
        'without MAX_CONTENT_LENGTH the whole body is parsed to disk before '
        'any per-file check runs')


def test_the_cap_clears_the_two_file_route():
    """/analyze-diff posts an original AND an edited proposal, each allowed to
    be MAX_DOCUMENT_BYTES. A cap below that pair breaks real comparisons."""
    per_file = _int_const('MAX_DOCUMENT_BYTES')
    cap = _int_const('MAX_REQUEST_BYTES')
    assert cap > per_file * 2, (
        f'request cap {cap} does not clear two {per_file}-byte files — '
        f'proposal comparison would 413 on legitimate uploads')


def test_analyze_diff_really_does_take_two_files():
    """The reason the cap is 2x. If this route stops taking a pair, the
    headroom above can come back down — but somebody has to notice."""
    src = _fn('analyze_diff')
    assert "request.files.get('original')" in src
    assert "request.files.get('edited')" in src


def test_a_413_comes_back_as_json_on_the_api():
    """The attachment UI reads `result.error`. Werkzeug's own 413 is an HTML
    page, so the JSON handler is what makes the message readable."""
    src = _fn('_handle_http_exception')
    assert "request.path.startswith('/api/')" in src
    assert 'jsonify' in src


# ── 3. headers ──────────────────────────────────────────────────────────────

def test_nosniff_is_set_on_every_response():
    src = _fn('_security_headers')
    assert 'X-Content-Type-Options' in src and 'nosniff' in src


def test_headers_do_not_overwrite_a_route_that_set_its_own():
    """setdefault, not assignment — an embed or a download that deliberately
    sets its own header keeps it."""
    src = _fn('_security_headers')
    assert 'setdefault' in src
    assert re.search(r"headers\[['\"]X-Content-Type-Options", src) is None
