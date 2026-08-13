"""Weekly Trade Partner (sub) insurance compliance digest.

Pulls the Sub Info board from Monday.com, downloads each sub's most recent
Certificate of Insurance PDF, and extracts real policy expiration dates
instead of trusting the board's manually-typed date columns (which go
stale — see CLAUDE.md / Office Ops notes on this). Sends one internal-only
email to Stephanie + Thomas. No board writes, no sub-facing email — that is
an explicit later iteration (2026-08 decision).

send_email_fn(subject, text_body, html_body, recipients) -> bool
"""

from __future__ import annotations

import difflib
import os
import re
import subprocess
import tempfile
from datetime import date, datetime
from html import escape

import monday_client
from estimators.siding.pdf_extract import extract_pdf_text

EXPIRING_SOON_DAYS = 30
EXPIRING_LATER_DAYS = 60
NEW_SUB_WINDOW_DAYS = 30

_DATE_RE = re.compile(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})')

# Photo COIs (phone shots of a paper certificate) are common on this board
# and have no PDF text layer. The Hub shows them as images so Stephanie /
# Thomas can read the date and type the override. PDF extract is skipped.
_IMAGE_EXTS = frozenset({
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic', '.heif',
    '.tif', '.tiff', '.bmp',
})
_PDF_EXTS = frozenset({'.pdf'})
_IMAGE_CONTENT_TYPES = {
    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
    '.gif': 'image/gif', '.webp': 'image/webp', '.heic': 'image/heic',
    '.heif': 'image/heif', '.tif': 'image/tiff', '.tiff': 'image/tiff',
    '.bmp': 'image/bmp',
}


def init_tables(cur):
    cur.execute('''
        CREATE TABLE IF NOT EXISTS office_ops_tp_snapshot (
            monday_item_id VARCHAR(50) PRIMARY KEY,
            name VARCHAR(255),
            group_name VARCHAR(100),
            insurance_expires_manual DATE,
            wc_expires_manual DATE,
            insurance_expires_extracted DATE,
            extract_confidence TEXT,
            additional_insured_present BOOLEAN,
            coi_asset_name VARCHAR(255),
            first_seen_at TIMESTAMP DEFAULT NOW(),
            last_seen_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    # Hub-side manual correction — a human looked at the real COI (or knows
    # the true date some other way) and typed it in directly. Outranks the
    # Monday board's manual column (the thing that goes stale) but still
    # loses to a COI we can actually read, since that's ground truth.
    cur.execute('''
        ALTER TABLE office_ops_tp_snapshot
        ADD COLUMN IF NOT EXISTS insurance_expires_override DATE
    ''')
    cur.execute('''
        ALTER TABLE office_ops_tp_snapshot
        ADD COLUMN IF NOT EXISTS override_by VARCHAR(100)
    ''')
    cur.execute('''
        ALTER TABLE office_ops_tp_snapshot
        ADD COLUMN IF NOT EXISTS override_at TIMESTAMP
    ''')
    # Widen extract_confidence on tables created before this fix (2026-08-09) —
    # fetch_error values embed the exception message, which routinely runs
    # past 50 chars ("value too long for type character varying(50)").
    cur.execute('''
        ALTER TABLE office_ops_tp_snapshot
        ALTER COLUMN extract_confidence TYPE TEXT
    ''')
    # Monday's own "Date Found" column — the real signal for "new sub."
    # first_seen_at (this table's insert time) is NOT usable for that: this
    # table didn't exist before 2026-08-09, so every sub already on the
    # board got first_seen_at = that day, making every veteran sub look
    # "new" for 30 days after launch. date_found fixes that (2026-08-10).
    cur.execute('''
        ALTER TABLE office_ops_tp_snapshot
        ADD COLUMN IF NOT EXISTS date_found DATE
    ''')
    # Monday asset id for the COI we last looked at — needed to proxy the
    # file in the Hub viewer (public_url expires in ~1 hour, so we cannot
    # store the URL). Filename alone is not enough to re-fetch.
    cur.execute('''
        ALTER TABLE office_ops_tp_snapshot
        ADD COLUMN IF NOT EXISTS coi_asset_id VARCHAR(50)
    ''')
    cur.execute('''
        ALTER TABLE office_ops_tp_snapshot
        ADD COLUMN IF NOT EXISTS coi_kind VARCHAR(20)
    ''')


def save_override(get_db_fn, monday_item_id, override_date, user_key):
    conn = get_db_fn()
    try:
        cur = conn.cursor()
        init_tables(cur)
        cur.execute('''
            UPDATE office_ops_tp_snapshot
            SET insurance_expires_override = %s, override_by = %s, override_at = NOW(), updated_at = NOW()
            WHERE monday_item_id = %s
        ''', (override_date, user_key, monday_item_id))
        updated = cur.rowcount
        conn.commit()
        cur.close()
        return updated > 0
    finally:
        conn.close()


def _parse_monday_date(text_val):
    if not text_val:
        return None
    try:
        return datetime.strptime(text_val.strip(), '%Y-%m-%d').date()
    except (ValueError, AttributeError):
        return None


def _parse_date_token(m):
    mo, day, yr = int(m.group(1)), int(m.group(2)), m.group(3)
    yr = int(yr)
    if yr < 100:
        yr += 2000
    try:
        return date(yr, mo, day)
    except ValueError:
        return None


def _parse_date_string(val):
    """Accept a regex match (PDF text path) or a '03/01/2027' / '2027-03-01'
    string (Claude vision JSON). The vision pass used to call
    _parse_date_token on the raw string — that crashes on .group() and
    every photo read came back as vision_error."""
    if val is None or val == '':
        return None
    if hasattr(val, 'group'):
        return _parse_date_token(val)
    text = str(val).strip()
    if not text or text.lower() in ('null', 'none', 'n/a'):
        return None
    try:
        return datetime.strptime(text[:10], '%Y-%m-%d').date()
    except ValueError:
        pass
    m = _DATE_RE.search(text)
    return _parse_date_token(m) if m else None


def _ext(name):
    name = (name or '').strip()
    dot = name.rfind('.')
    if dot < 0:
        return ''
    return name[dot:].lower()


def sniff_coi_kind(filename, data=None):
    """'pdf', 'image', or 'other'. Prefer magic bytes when we have them —
    a phone photo uploaded as 'COI.pdf' should still display as an image."""
    if data:
        head = data[:16]
        if head.startswith(b'%PDF'):
            return 'pdf'
        if head.startswith(b'\xff\xd8\xff'):
            return 'image'
        if head.startswith(b'\x89PNG\r\n\x1a\n'):
            return 'image'
        if head.startswith(b'GIF8'):
            return 'image'
        if head[0:4] == b'RIFF' and data[8:12] == b'WEBP':
            return 'image'
        if b'ftyp' in head[4:12]:
            # HEIC/HEIF container
            return 'image'
    ext = _ext(filename)
    if ext in _PDF_EXTS:
        return 'pdf'
    if ext in _IMAGE_EXTS:
        return 'image'
    return 'other'


def content_type_for_coi(kind, filename):
    if kind == 'pdf':
        return 'application/pdf'
    ext = _ext(filename)
    return _IMAGE_CONTENT_TYPES.get(ext, 'application/octet-stream')


def _extract_coi_fields(pdf_bytes):
    """Best-effort extraction from a COI PDF's text layer.

    Real-world COIs vary by carrier/agent template, so this is a heuristic,
    not a guarantee — matches Office Ops' philosophy elsewhere (chase list,
    import status mapping) of a calibrated-honest best guess over a
    confident wrong one. Flag confidence so low-confidence rows get a human
    look rather than being silently trusted.
    """
    try:
        text = extract_pdf_text(pdf_bytes)
    except Exception:
        return {'gl_exp': None, 'wc_exp': None, 'additional_insured': None, 'confidence': 'unreadable'}

    upper = text.upper()
    gl_exp = None
    wc_exp = None

    # General Liability: look for the block between "GENERAL LIABILITY" and
    # the next coverage section, take the second date on the first
    # EFF/EXP-looking date pair (ACORD 25 lists EFF then EXP).
    gl_idx = upper.find('GENERAL LIABILITY')
    if gl_idx != -1:
        window = text[gl_idx:gl_idx + 600]
        dates = [(m, _parse_date_token(m)) for m in _DATE_RE.finditer(window)]
        dates = [(m, d) for m, d in dates if d]
        if len(dates) >= 2:
            gl_exp = dates[1][1]
        elif len(dates) == 1:
            gl_exp = dates[0][1]

    # Workers Comp: same approach, scoped to its own section if present.
    wc_idx = upper.find('WORKERS COMPENSATION')
    if wc_idx != -1:
        window = text[wc_idx:wc_idx + 600]
        dates = [(m, _parse_date_token(m)) for m in _DATE_RE.finditer(window)]
        dates = [(m, d) for m, d in dates if d]
        if len(dates) >= 2:
            wc_exp = dates[1][1]
        elif len(dates) == 1:
            wc_exp = dates[0][1]

    # Additional insured: text-layer checkbox state is unreliable (checkbox
    # marks are often graphics, not extractable characters) — only assert
    # True/False when the surrounding text gives an unambiguous signal,
    # otherwise leave None (unknown) rather than guess.
    additional_insured = None
    ai_idx = upper.find('ADDITIONAL INSURED')
    if ai_idx != -1:
        nearby = upper[max(0, ai_idx - 5):ai_idx + 5]
        if re.search(r'[XY]\s*ADDITIONAL INSURED|ADDITIONAL INSURED\s*[XY]', upper[max(0, ai_idx - 10):ai_idx + 30]):
            additional_insured = True
        # else: leave None — presence of the label alone isn't a checked box

    confidence = 'text_extracted' if (gl_exp or wc_exp) else 'no_dates_found'
    return {
        'gl_exp': gl_exp,
        'wc_exp': wc_exp,
        'additional_insured': additional_insured,
        'confidence': confidence,
    }


# Claude's vision input only accepts these four image types. HEIC/HEIF and
# TIFF/BMP sniff as 'image' for display purposes (Grok's viewer proxies them
# straight to the browser via <img>, which does render some of these
# depending on client), but a vision API call needs one of the four below.
_VISION_SUPPORTED_TYPES = frozenset({'image/jpeg', 'image/png', 'image/gif', 'image/webp'})


def _strip_json_fences(raw):
    text = (raw or '').strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[-1]
        if text.endswith('```'):
            text = text.rsplit('```', 1)[0]
        text = text.strip()
        if text.lower().startswith('json'):
            text = text[4:].strip()
    return text


def _extract_coi_fields_vision(image_bytes, content_type, api_key, model, timeout=45.0):
    """Same job as _extract_coi_fields, for a COI that's a photo instead of
    a PDF with a text layer — reads the certificate visually with Claude.

    Same calibrated-honest posture as the text path: a low-confidence or
    unreadable read comes back with gl_exp=None rather than a guess, so it
    stays in 'needs manual entry' instead of silently posing as verified.
    """
    if content_type not in _VISION_SUPPORTED_TYPES:
        return {'gl_exp': None, 'wc_exp': None, 'additional_insured': None,
                'confidence': 'unsupported_image_type'}

    import base64
    import json
    import time
    import anthropic

    b64 = base64.standard_b64encode(image_bytes).decode('ascii')
    prompt = (
        "This is a photo of a Certificate of Insurance (ACORD 25 or similar). "
        "Find the General Liability expiration date and the Workers Compensation "
        "expiration date (the EXP/expiration date, not the effective date — COIs "
        "usually list both). Reply with ONLY this JSON, no other text:\n"
        '{"gl_exp": "MM/DD/YYYY or null", "wc_exp": "MM/DD/YYYY or null", '
        '"confident": true or false}\n'
        "Set confident to false if the photo is blurry, cropped, glare-obscured, "
        "or you are not sure you are reading the right field."
    )
    cl = anthropic.Anthropic(api_key=api_key, timeout=timeout)
    last_err = None
    for attempt in range(2):
        try:
            msg = cl.messages.create(
                model=model,
                max_tokens=300,
                messages=[{
                    'role': 'user',
                    'content': [
                        {'type': 'image', 'source': {'type': 'base64', 'media_type': content_type, 'data': b64}},
                        {'type': 'text', 'text': prompt},
                    ],
                }],
            )
            raw = msg.content[0].text
            parsed = json.loads(_strip_json_fences(raw))
            gl_exp = _parse_date_string(parsed.get('gl_exp'))
            wc_exp = _parse_date_string(parsed.get('wc_exp'))
            confident = bool(parsed.get('confident'))
            if not confident or (not gl_exp and not wc_exp):
                return {'gl_exp': None, 'wc_exp': None, 'additional_insured': None,
                        'confidence': 'vision_uncertain'}
            return {'gl_exp': gl_exp, 'wc_exp': wc_exp, 'additional_insured': None,
                    'confidence': 'vision_extracted'}
        except Exception as e:
            last_err = e
            err_name = type(e).__name__
            transient = err_name in (
                'APITimeoutError', 'APIConnectionError', 'RateLimitError', 'InternalServerError',
            ) or 'timeout' in str(e).lower() or 'overloaded' in str(e).lower()
            if attempt == 0 and transient:
                time.sleep(1.5)
                continue
            print(f"COI vision extract error ({err_name}): {e}")
    return {'gl_exp': None, 'wc_exp': None, 'additional_insured': None,
            'confidence': f'vision_error: {last_err}'[:300]}


_SCANNED_PDF_CONFIDENCE = frozenset({'no_dates_found', 'unreadable', 'image_file'})


def is_vision_target(row):
    """Photos always. PDFs only when the text layer already failed —
    those are scans/photos saved as .pdf. Skip rows with no file at all."""
    if not row.get('has_viewable_coi') and not row.get('coi_name'):
        return False
    kind = row.get('coi_kind')
    if kind == 'image':
        return True
    if kind == 'pdf' and (row.get('confidence') or '') in _SCANNED_PDF_CONFIDENCE:
        return True
    return False


def _pdf_first_page_jpeg(pdf_bytes):
    """Render page 1 of a scanned PDF so Claude vision can read it.
    Uses pdftoppm from poppler-utils (already in Aptfile for estimators)."""
    if not pdf_bytes:
        return None
    try:
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, 'coi.pdf')
            with open(src, 'wb') as f:
                f.write(pdf_bytes)
            dest = os.path.join(tmp, 'page')
            subprocess.run(
                ['pdftoppm', '-jpeg', '-f', '1', '-l', '1', '-r', '150', src, dest],
                check=True, capture_output=True, timeout=30,
            )
            out = dest + '-1.jpg'
            if os.path.exists(out):
                with open(out, 'rb') as f:
                    return f.read()
    except Exception as e:
        print(f'pdftoppm COI render failed: {e}')
    return None


def _vision_ready_image(data, filename, content_type):
    """Turn whatever we downloaded into jpeg/png/gif/webp bytes, or
    return (None, reason) if Claude cannot see this file."""
    kind = sniff_coi_kind(filename, data)
    if kind == 'pdf' or (content_type or '').startswith('application/pdf') or (
        data and data.startswith(b'%PDF')
    ):
        jpeg = _pdf_first_page_jpeg(data)
        if not jpeg:
            return None, None, 'could not render PDF page'
        return jpeg, 'image/jpeg', None
    media = content_type if content_type in _VISION_SUPPORTED_TYPES else content_type_for_coi(kind, filename)
    if media in _VISION_SUPPORTED_TYPES:
        return data, media, None
    return None, content_type, f"{content_type or filename or 'file type'} not supported for vision (iPhone HEIC is the usual case)"


def run_vision_pass(get_db_fn, api_key, model):
    """On-demand batch: try Claude vision on every 'needs manual entry'
    COI we can actually look at — photos, and PDFs whose text layer was
    empty (scans). Not run automatically; Thomas/Stephanie trigger it
    from the Compliance page. Writes into the same extracted/confidence
    columns the PDF text path uses.

    A row that comes back uncertain still gets its confidence recorded
    but its date stays NULL rather than posting a guess.
    """
    if not api_key:
        return {'error': 'Claude API key not configured on hub (CLAUDE_API_KEY).'}

    rows, _ = get_latest_snapshot_rows(get_db_fn)
    targets = [r for r in categorize_rows(rows, date.today())['needs_manual']
               if is_vision_target(r)]

    result = {'attempted': len(targets), 'dated': 0, 'uncertain': 0, 'errors': 0, 'details': []}
    if not targets:
        return result

    conn = get_db_fn()
    try:
        cur = conn.cursor()
        for r in targets:
            item_id = r['item_id']
            try:
                data, filename, content_type, err = load_coi_asset(get_db_fn, item_id)
                if err:
                    result['errors'] += 1
                    result['details'].append({'name': r['name'], 'outcome': f'fetch failed: {err}'})
                    continue
                image_bytes, media, prep_err = _vision_ready_image(data, filename, content_type)
                if prep_err:
                    result['errors'] += 1
                    result['details'].append({'name': r['name'], 'outcome': prep_err})
                    continue
                extracted = _extract_coi_fields_vision(image_bytes, media, api_key, model)
            except Exception as e:
                result['errors'] += 1
                result['details'].append({'name': r['name'], 'outcome': f'error: {e}'})
                continue

            cur.execute(
                'UPDATE office_ops_tp_snapshot '
                'SET insurance_expires_extracted = %s, extract_confidence = %s, updated_at = NOW() '
                'WHERE monday_item_id = %s',
                (extracted['gl_exp'], extracted['confidence'], item_id),
            )
            if extracted['gl_exp']:
                result['dated'] += 1
                result['details'].append({'name': r['name'], 'outcome': f"read {extracted['gl_exp']}"})
            elif extracted['confidence'] == 'unsupported_image_type':
                result['errors'] += 1
                result['details'].append({'name': r['name'], 'outcome': f"{content_type or 'file type'} not supported for vision"})
            else:
                result['uncertain'] += 1
                result['details'].append({'name': r['name'], 'outcome': 'photo unclear, still needs a human look'})
        conn.commit()
    finally:
        conn.close()

    return result


def _pick_latest_coi_file(files):
    """Files are usually in upload order; prefer names with a recent-looking
    year range (e.g. '25-26') and otherwise fall back to the last uploaded."""
    if not files:
        return None
    year_re = re.compile(r'(\d{2})[\-\/](\d{2})(?!\d)')
    best = None
    best_year = -1
    for f in files:
        m = year_re.search(f.get('name') or '')
        if m:
            yr = int(m.group(2))
            if yr > best_year:
                best_year = yr
                best = f
    return best or files[-1]


def _col_value(column_values, col_id):
    for cv in column_values or []:
        if cv.get('id') == col_id:
            return cv
    return None


def _bucket_label(exp_date, today):
    if exp_date is None:
        return None
    delta = (exp_date - today).days
    if delta < 0:
        return 'expired'
    if delta <= EXPIRING_SOON_DAYS:
        return 'expiring_soon'
    if delta <= EXPIRING_LATER_DAYS:
        return 'expiring_later'
    return None


FUZZY_MATCH_THRESHOLD = 0.75


def _match_sub_name(name, snapshot_names, threshold=FUZZY_MATCH_THRESHOLD):
    """Match a Pay Request item's name against known Sub Info names.

    Two-tier: cheap substring match first (same pattern as office_ops.py's
    past-due customer matching), then a difflib fallback so real typos and
    misspellings ("Grey Sky" vs "Gray Sky", transposed letters) still match
    instead of silently falling through to "unmatched." Returns
    (matched_name, 'exact'|'fuzzy') or (None, None) if nothing clears the
    threshold — a miss is safer than a wrong guess between two subs with
    genuinely similar names.
    """
    key = (name or '').lower().strip()
    if not key:
        return None, None
    for candidate in snapshot_names:
        cand_norm = candidate.lower().strip()
        if key == cand_norm or key in cand_norm or cand_norm in key:
            return candidate, 'exact'
    best_name, best_score = None, 0.0
    for candidate in snapshot_names:
        score = difflib.SequenceMatcher(None, key, candidate.lower().strip()).ratio()
        if score > best_score:
            best_name, best_score = candidate, score
    if best_name and best_score >= threshold:
        return best_name, 'fuzzy'
    return None, None


def check_pay_requests(get_db_fn):
    """Cross-reference the Pay Request board's active pipeline (In Request,
    On Hold) against current sub compliance status — flags a recent pay
    request to a sub whose insurance is expired/expiring, which is the
    exact failure mode this whole feature exists to catch (paying/continuing
    to use someone whose insurance lapsed). Read-only against Monday; never
    writes to the unused Sub Info connect-column or the manual "Insurance
    Compliance" status on Pay Request — those stay human-owned.
    """
    today = date.today()
    rows, _ = get_latest_snapshot_rows(get_db_fn)
    name_lookup = {r['name']: r for r in rows}
    snapshot_names = list(name_lookup.keys())

    pay_items = monday_client.fetch_pay_request_items()

    flagged = []
    unmatched = []
    for it in pay_items:
        col = it.get('column_values') or []
        pr_name = it.get('name') or ''
        group_name = (it.get('group') or {}).get('title') or ''

        status_cv = _col_value(col, monday_client.PAY_REQUEST_COL_STATUS)
        date_cv = _col_value(col, monday_client.PAY_REQUEST_COL_DATE)
        amount_cv = _col_value(col, monday_client.PAY_REQUEST_COL_AMOUNT)
        job_cv = _col_value(col, monday_client.PAY_REQUEST_COL_JOB_NAME)

        monday_status = (status_cv['text'] if status_cv else '') or None
        request_date = _parse_monday_date(date_cv['text'] if date_cv else None)
        try:
            amount = float(amount_cv['text']) if amount_cv and amount_cv.get('text') else None
        except (TypeError, ValueError):
            amount = None
        job_name = (job_cv['text'] if job_cv else '') or None

        matched_name, confidence = _match_sub_name(pr_name, snapshot_names)
        if not matched_name:
            unmatched.append({
                'pay_request_name': pr_name,
                'amount': amount,
                'date': request_date,
                'group': group_name,
            })
            continue

        sub_row = name_lookup[matched_name]
        bucket = _bucket_label(sub_row['effective_ins'], today)
        if bucket in ('expired', 'expiring_soon'):
            monday_says_compliant = bool(monday_status and monday_status.lower().strip() == 'compliant')
            flagged.append({
                'pay_request_name': pr_name,
                'matched_sub': matched_name,
                'match_confidence': confidence,
                'amount': amount,
                'date': request_date,
                'group': group_name,
                'job_name': job_name,
                'our_status': bucket,
                'effective_ins': sub_row['effective_ins'],
                'monday_status': monday_status,
                'status_disagreement': monday_says_compliant,
            })

    flagged.sort(key=lambda f: -(f['amount'] or 0))
    return {'flagged': flagged, 'unmatched': unmatched}


def categorize_rows(rows, today):
    """Single shared definition of the digest's categories — used by both
    the weekly email and the Office Ops compliance page, so the two never
    silently drift apart on what counts as 'expiring soon'."""
    expired, soon, later, new_subs, mismatches, needs_manual = [], [], [], [], [], []
    for r in rows:
        bucket = _bucket_label(r['effective_ins'], today)
        if bucket == 'expired':
            expired.append(r)
        elif bucket == 'expiring_soon':
            soon.append(r)
        elif bucket == 'expiring_later':
            later.append(r)
        if r['is_new']:
            new_subs.append(r)
        if r['manual_ins'] and r['extracted_ins'] and r['manual_ins'] != r['extracted_ins']:
            mismatches.append(r)
        if r['needs_manual_review']:
            needs_manual.append(r)

    expired.sort(key=lambda r: r['effective_ins'] or date.min)
    soon.sort(key=lambda r: r['effective_ins'] or date.min)
    later.sort(key=lambda r: r['effective_ins'] or date.min)

    return {
        'expired': expired,
        'soon': soon,
        'later': later,
        'new_subs': new_subs,
        'mismatches': mismatches,
        'needs_manual': needs_manual,
    }


def get_latest_snapshot_rows(get_db_fn):
    """Read office_ops_tp_snapshot back out in the same row-shape
    run_weekly_compliance_check builds, for the Office Ops compliance page.
    Returns (rows, last_run_at) — last_run_at is None if never run."""
    conn = get_db_fn()
    try:
        cur = conn.cursor()
        init_tables(cur)
        conn.commit()
        cur.execute('''
            SELECT monday_item_id, name, group_name, insurance_expires_manual,
                   wc_expires_manual, insurance_expires_extracted, extract_confidence,
                   additional_insured_present, coi_asset_name, insurance_expires_override,
                   override_by, date_found, updated_at, coi_asset_id, coi_kind
            FROM office_ops_tp_snapshot
            ORDER BY name
        ''')
        db_rows = cur.fetchall()
        cur.close()

        today = date.today()
        rows = []
        last_run_at = None
        for (item_id, name, group_name, manual_ins, manual_wc, extracted_ins,
             confidence, additional_insured, coi_name, override_ins, override_by,
             date_found, updated_at, coi_asset_id, coi_kind) in db_rows:
            if updated_at and (last_run_at is None or updated_at > last_run_at):
                last_run_at = updated_at

            if extracted_ins:
                src = 'coi_vision' if (confidence or '').startswith('vision') else 'coi_pdf'
                effective_ins, effective_source = extracted_ins, src
            elif override_ins:
                effective_ins, effective_source = override_ins, 'override'
            elif manual_ins:
                effective_ins, effective_source = manual_ins, 'manual'
            else:
                effective_ins, effective_source = None, None

            # Same "new" definition as run_weekly_compliance_check — Monday's
            # own Date Found column, not our table's insert time.
            is_new = bool(date_found and (today - date_found).days <= NEW_SUB_WINDOW_DAYS)
            needs_manual_review = (not extracted_ins) and (not override_ins)

            rows.append({
                'item_id': item_id,
                'name': name,
                'group': group_name,
                'manual_ins': manual_ins,
                'manual_wc': manual_wc,
                'extracted_ins': extracted_ins,
                'confidence': confidence,
                'additional_insured': additional_insured,
                'override_ins': override_ins,
                'override_by': override_by,
                'effective_ins': effective_ins,
                'effective_source': effective_source,
                'is_new': is_new,
                'coi_name': coi_name,
                'coi_asset_id': coi_asset_id,
                'coi_kind': coi_kind or sniff_coi_kind(coi_name),
                'has_viewable_coi': bool(coi_name or coi_asset_id),
                'needs_manual_review': needs_manual_review,
            })
        return rows, last_run_at
    finally:
        conn.close()


def load_coi_asset(get_db_fn, item_id):
    """Fetch the COI bytes for one sub so the Hub can display it.

    Returns (data, filename, content_type, error). Monday's public_url
    expires in about an hour, so this always re-resolves the asset id
    rather than serving a stored URL.
    """
    item_id = (item_id or '').strip()
    if not item_id:
        return None, None, None, 'Missing item'
    asset_id, filename = None, None
    conn = get_db_fn()
    try:
        cur = conn.cursor()
        init_tables(cur)
        conn.commit()
        cur.execute(
            'SELECT coi_asset_id, coi_asset_name FROM office_ops_tp_snapshot '
            'WHERE monday_item_id = %s',
            (item_id,),
        )
        row = cur.fetchone()
        cur.close()
        if row:
            asset_id, filename = row[0], row[1]
    finally:
        conn.close()

    if not asset_id:
        files = monday_client.fetch_item_files(item_id)
        picked = _pick_latest_coi_file(files)
        if not picked:
            return None, None, None, 'No COI file on this Monday item'
        asset_id = picked.get('assetId')
        filename = picked.get('name') or filename or 'coi'

    asset_map = monday_client.resolve_asset_urls([asset_id])
    asset = asset_map.get(str(asset_id))
    if not asset or not asset.get('public_url'):
        return None, None, None, 'Could not get a download URL from Monday'
    data = monday_client.download_asset(asset['public_url'])
    kind = sniff_coi_kind(filename, data)
    return data, filename or 'coi', content_type_for_coi(kind, filename), None


def run_weekly_compliance_check(get_db_fn, send_email_fn, recipients):
    today = date.today()
    conn = get_db_fn()
    try:
        cur = conn.cursor()
        init_tables(cur)
        conn.commit()

        items = monday_client.fetch_sub_info_items()

        rows = []
        for it in items:
            col = it.get('column_values') or []
            item_id = it['id']
            name = it.get('name') or ''
            group_name = (it.get('group') or {}).get('title') or ''

            ins_cv = _col_value(col, monday_client.COL_DATE_INSURANCE)
            wc_cv = _col_value(col, monday_client.COL_DATE_WORKERS_COMP)
            found_cv = _col_value(col, monday_client.COL_DATE_FOUND)
            manual_ins = _parse_monday_date(ins_cv['text'] if ins_cv else None)
            manual_wc = _parse_monday_date(wc_cv['text'] if wc_cv else None)
            date_found = _parse_monday_date(found_cv['text'] if found_cv else None)

            files_col = _col_value(col, monday_client.COL_FILES)
            files = monday_client.parse_files_column(files_col) if files_col else []
            coi_file = _pick_latest_coi_file(files)

            extracted = {'gl_exp': None, 'wc_exp': None, 'additional_insured': None, 'confidence': 'no_file'}
            coi_name = None
            coi_asset_id = None
            coi_kind = None
            if coi_file:
                coi_name = coi_file.get('name')
                coi_asset_id = str(coi_file.get('assetId') or '') or None
                try:
                    asset_map = monday_client.resolve_asset_urls([coi_file['assetId']])
                    asset = asset_map.get(str(coi_file['assetId']))
                    if asset and asset.get('public_url'):
                        file_bytes = monday_client.download_asset(asset['public_url'])
                        coi_kind = sniff_coi_kind(coi_name, file_bytes)
                        if coi_kind == 'pdf':
                            extracted = _extract_coi_fields(file_bytes)
                        elif coi_kind == 'image':
                            extracted = {
                                'gl_exp': None, 'wc_exp': None,
                                'additional_insured': None, 'confidence': 'image_file',
                            }
                        else:
                            extracted = {
                                'gl_exp': None, 'wc_exp': None,
                                'additional_insured': None, 'confidence': 'unsupported_file',
                            }
                    else:
                        coi_kind = sniff_coi_kind(coi_name)
                except Exception as e:
                    extracted = {'gl_exp': None, 'wc_exp': None, 'additional_insured': None,
                                 'confidence': f'fetch_error: {e}'[:300]}
                    coi_kind = sniff_coi_kind(coi_name)

            cur.execute(
                'SELECT first_seen_at, insurance_expires_override, override_by '
                'FROM office_ops_tp_snapshot WHERE monday_item_id = %s',
                (item_id,),
            )
            existing = cur.fetchone()
            override_ins = existing[1] if existing else None
            override_by = existing[2] if existing else None
            # "New" means Monday's own Date Found is recent — NOT whether
            # this is the first time our table has seen the item (that
            # conflates "new to us" with "new to the business").
            is_new = bool(date_found and (today - date_found).days <= NEW_SUB_WINDOW_DAYS)

            # Priority: a COI we can actually read > a human-typed Hub
            # override (someone looked at the real file) > the Monday
            # board's manual column, which is what goes stale in practice.
            effective_ins = extracted['gl_exp'] or override_ins or manual_ins
            if extracted['gl_exp']:
                effective_source = 'coi_pdf'
            elif override_ins:
                effective_source = 'override'
            elif manual_ins:
                effective_source = 'manual'
            else:
                effective_source = None
            needs_manual_review = (not extracted['gl_exp']) and (not override_ins)

            cur.execute('''
                INSERT INTO office_ops_tp_snapshot
                    (monday_item_id, name, group_name, insurance_expires_manual,
                     wc_expires_manual, insurance_expires_extracted, extract_confidence,
                     additional_insured_present, coi_asset_name, date_found,
                     coi_asset_id, coi_kind, last_seen_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                ON CONFLICT (monday_item_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    group_name = EXCLUDED.group_name,
                    insurance_expires_manual = EXCLUDED.insurance_expires_manual,
                    wc_expires_manual = EXCLUDED.wc_expires_manual,
                    insurance_expires_extracted = EXCLUDED.insurance_expires_extracted,
                    extract_confidence = EXCLUDED.extract_confidence,
                    additional_insured_present = EXCLUDED.additional_insured_present,
                    coi_asset_name = EXCLUDED.coi_asset_name,
                    date_found = EXCLUDED.date_found,
                    coi_asset_id = EXCLUDED.coi_asset_id,
                    coi_kind = EXCLUDED.coi_kind,
                    last_seen_at = NOW(),
                    updated_at = NOW()
            ''', (item_id, name, group_name, manual_ins, manual_wc,
                  extracted['gl_exp'], extracted['confidence'],
                  extracted['additional_insured'], coi_name, date_found,
                  coi_asset_id, coi_kind))
            # Note: override_* columns are untouched by this upsert (not in
            # the SET clause) — a manual correction survives every future
            # weekly run until a real COI is read and beats it.

            rows.append({
                'item_id': item_id,
                'name': name,
                'group': group_name,
                'manual_ins': manual_ins,
                'manual_wc': manual_wc,
                'extracted_ins': extracted['gl_exp'],
                'extracted_wc': extracted['wc_exp'],
                'confidence': extracted['confidence'],
                'additional_insured': extracted['additional_insured'],
                'override_ins': override_ins,
                'override_by': override_by,
                'effective_ins': effective_ins,
                'effective_source': effective_source,
                'is_new': is_new,
                'coi_name': coi_name,
                'coi_asset_id': coi_asset_id,
                'coi_kind': coi_kind,
                'has_viewable_coi': bool(coi_name or coi_asset_id),
                'needs_manual_review': needs_manual_review,
            })

        # Prune rows for subs no longer in a monitored group — e.g. dropped
        # from ACTIVE_GROUPS (like "Insurance Out of Date NOT COMPLIANT",
        # 2026-08-10), moved to No Longer Active, or removed from the board
        # entirely. Guarded on a non-empty fetch so a Monday API hiccup
        # can't wipe the whole table.
        if items:
            current_ids = tuple(str(it['id']) for it in items)
            cur.execute(
                'DELETE FROM office_ops_tp_snapshot WHERE monday_item_id NOT IN %s',
                (current_ids,),
            )

        conn.commit()
        cur.close()

        try:
            pay_request_result = check_pay_requests(get_db_fn)
        except Exception as e:
            print(f'Pay Request cross-check failed (continuing without it): {e}')
            pay_request_result = {'flagged': [], 'unmatched': []}

        subject, text_body, html_body = _build_digest(rows, today, pay_request_result)
        sent = send_email_fn(subject, text_body, html_body, recipients)
        return {'ok': True, 'sent': sent, 'checked': len(rows), 'pay_requests_flagged': len(pay_request_result['flagged'])}
    finally:
        conn.close()


def _fmt_date(d):
    return d.strftime('%m/%d/%Y') if d else '—'


def _needs_manual_message(r):
    if r.get('coi_kind') == 'image' or (r.get('confidence') == 'image_file'):
        base = f"{r['name']} — \"{r.get('coi_name') or 'photo'}\" is an image; open in Hub to read the date"
    elif r['coi_name']:
        base = f"{r['name']} — \"{r['coi_name']}\" looks like a scan/photo, no text to read"
    else:
        base = f"{r['name']} — no COI on file to read"
    if r['manual_ins']:
        return f"{base}; using board date ({_fmt_date(r['manual_ins'])}) for now"
    return f"{base}, and no board date entered either"


def _pay_request_message(f):
    amt = f'${f["amount"]:,.0f}' if f['amount'] is not None else '$?'
    when = _fmt_date(f['date'])
    match_note = '' if f['match_confidence'] == 'exact' else f" (fuzzy match to \"{f['matched_sub']}\")"
    status_note = (
        f" — Monday board says compliant, we say {f['our_status'].replace('_', ' ')}"
        if f['status_disagreement'] else f" ({f['our_status'].replace('_', ' ')})"
    )
    return f"{f['pay_request_name']}{match_note} — {amt} requested {when}, sub expires {_fmt_date(f['effective_ins'])}{status_note}"


def _build_digest(rows, today, pay_request_result=None):
    cats = categorize_rows(rows, today)
    expired, soon, later = cats['expired'], cats['soon'], cats['later']
    new_subs, mismatches, needs_manual = cats['new_subs'], cats['mismatches'], cats['needs_manual']
    pay_flagged = (pay_request_result or {}).get('flagged') or []

    lines = [f'PPS Trade Partner Compliance — {today.strftime("%A, %B %d, %Y")}', '']

    def _section(title, items, fmt):
        if not items:
            return
        lines.append(f'{title} ({len(items)})')
        for it in items:
            lines.append(f'  - {fmt(it)}')
        lines.append('')

    _section('PAY REQUESTS TO NON-COMPLIANT SUBS', pay_flagged, _pay_request_message)
    _section('EXPIRED', expired, lambda r: f"{r['name']} — expired {_fmt_date(r['effective_ins'])} [{r['effective_source']}]")
    _section(f'EXPIRING ≤{EXPIRING_SOON_DAYS} DAYS', soon, lambda r: f"{r['name']} — expires {_fmt_date(r['effective_ins'])} [{r['effective_source']}]")
    _section(f'EXPIRING {EXPIRING_SOON_DAYS+1}-{EXPIRING_LATER_DAYS} DAYS', later, lambda r: f"{r['name']} — expires {_fmt_date(r['effective_ins'])} [{r['effective_source']}]")
    _section(f'NEW SUBS (last {NEW_SUB_WINDOW_DAYS} days)', new_subs, lambda r: f"{r['name']} ({r['group']})")
    _section('MANUAL VS COI-EXTRACTED DATE MISMATCH', mismatches,
              lambda r: f"{r['name']} — board says {_fmt_date(r['manual_ins'])}, COI PDF says {_fmt_date(r['extracted_ins'])}")
    _section('NEEDS MANUAL ENTRY', needs_manual, _needs_manual_message)

    if not (pay_flagged or expired or soon or later or new_subs or mismatches):
        lines.append('Nothing flagged this week — all checked subs are current.')
        lines.append('')

    lines.append(f'Checked {len(rows)} subs across Compliant + On Hold groups.')
    lines.append('Source: Monday.com Sub Info board + COI PDF text extraction (best-effort — spot-check low-confidence rows).')

    text_body = '\n'.join(lines)

    html_parts = [f'<h2>PPS Trade Partner Compliance — {escape(today.strftime("%A, %B %d, %Y"))}</h2>']

    def _html_section(title, items, fmt, color):
        if not items:
            return
        html_parts.append(f'<h3 style="color:{color};margin:18px 0 6px;">{escape(title)} ({len(items)})</h3><ul>')
        for it in items:
            html_parts.append(f'<li>{escape(fmt(it))}</li>')
        html_parts.append('</ul>')

    _html_section('Pay requests to non-compliant subs', pay_flagged, _pay_request_message, '#9d174d')
    _html_section('Expired', expired, lambda r: f"{r['name']} — expired {_fmt_date(r['effective_ins'])} [{r['effective_source']}]", '#b91c1c')
    _html_section(f'Expiring ≤{EXPIRING_SOON_DAYS} days', soon, lambda r: f"{r['name']} — expires {_fmt_date(r['effective_ins'])} [{r['effective_source']}]", '#c2410c')
    _html_section(f'Expiring {EXPIRING_SOON_DAYS+1}-{EXPIRING_LATER_DAYS} days', later, lambda r: f"{r['name']} — expires {_fmt_date(r['effective_ins'])} [{r['effective_source']}]", '#a16207')
    _html_section('New subs', new_subs, lambda r: f"{r['name']} ({r['group']})", '#166534')
    _html_section('Manual vs COI-extracted mismatch', mismatches,
                   lambda r: f"{r['name']} — board says {_fmt_date(r['manual_ins'])}, COI PDF says {_fmt_date(r['extracted_ins'])}", '#4338ca')
    _html_section('Needs manual entry', needs_manual, _needs_manual_message, '#78716c')

    if not (pay_flagged or expired or soon or later or new_subs or mismatches):
        html_parts.append('<p>Nothing flagged this week — all checked subs are current.</p>')

    html_parts.append(f'<p style="color:#64748b;font-size:12px;">Checked {len(rows)} subs. Source: Monday.com Sub Info + COI PDF extraction (best-effort).</p>')
    html_body = '\n'.join(html_parts)

    subject = 'PPS Trade Partner Compliance'
    if pay_flagged:
        subject += f' — {len(pay_flagged)} PAY REQUEST(S) TO NON-COMPLIANT SUBS'
    elif expired:
        subject += f' — {len(expired)} EXPIRED'
    elif soon:
        subject += f' — {len(soon)} expiring soon'

    return subject, text_body, html_body
