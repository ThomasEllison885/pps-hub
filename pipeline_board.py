"""Pipeline Board — live shared Consultant/PM proposal-tracking sheet.

Replaces the ad hoc shared Google Sheets each Consultant/PM pair has been keeping
(e.g. "who's waiting on sub pricing", "did I log every proposal I sent"). One
board per pair, kept current for everyone viewing it via short client polling.

Deliberately NOT Socket.IO/WebSockets (was, briefly, on 2026-07-29): that
required the whole Hub to run on a single gevent worker, and any one
non-cooperative blocking call anywhere in the app (Claude API, docx/xlsx
generation) then stalled *every* request, not just this module -- a global
Hub slowdown traced back to this module. Plain polling against the existing
REST endpoints needs no special worker class, no monkey-patching, and cannot
regress the rest of the Hub's performance again by construction: this module
now has zero effect on how gunicorn runs.

Pilot (2026-07-29): Andy Potts <-> Ben Ramsey, Rachel Farler <-> Derek Kidney.
A pair's board is keyed by the *consultant's* user_key (`pair_key`) since the
consultant owns the client relationship; the paired PM writes to the same board.

Status values were chosen by reviewing two real exported sheets (Rachel Farler's
and another consultant's) rather than guessed — see chat history 2026-07-29.
Do NOT add an "IC" status: in the sample data every "IC" row was actually an
"Indian Creek" property tag left in the wrong column, not a real status.
"""

import re
import time
from datetime import datetime, date

import openpyxl
from psycopg2.extras import RealDictCursor

PILOT_PAIR_CONSULTANTS = frozenset({'andy_potts', 'rachel_farler'})
PRESENCE_TTL_SECONDS = 12  # no explicit "disconnect" under polling; just expire

STATUSES = [
    {'value': 'draft', 'label': 'Draft'},
    {'value': 'sent', 'label': 'Sent'},
    {'value': 'awarded', 'label': 'Awarded'},
    {'value': 'on_hold', 'label': 'On Hold'},
    {'value': 'declined', 'label': 'Declined'},
    {'value': 'cancelled', 'label': 'Cancelled'},
]
STATUS_VALUES = frozenset(s['value'] for s in STATUSES)
STATUS_LABELS = {s['value']: s['label'] for s in STATUSES}

MAX_TEXT = 500
MAX_NOTES = 10000

_EDITABLE_TEXT_FIELDS = ('proposal_number', 'property_name', 'address', 'project',
                         'trade_partner', 'client_contact', 'notes')
_EDITABLE_NUMERIC_FIELDS = ('amount', 'sub_pay')

# In-memory presence, refreshed by a heartbeat call every poll cycle rather
# than a socket connection: pair_key -> {user_key: {'display', 'field', 'ts'}}.
# Entries older than PRESENCE_TTL_SECONDS are treated as gone -- the only way
# to detect someone closed their tab without an explicit disconnect event.
_presence = {}


def _touch_presence(pair_key, user_key, display, field):
    bucket = _presence.setdefault(pair_key, {})
    if field:
        bucket[user_key] = {'display': display, 'field': field, 'ts': time.time()}
    else:
        bucket.pop(user_key, None)


def _live_presence(pair_key, exclude_user_key=None):
    bucket = _presence.get(pair_key, {})
    now = time.time()
    stale = [k for k, v in bucket.items() if now - v['ts'] > PRESENCE_TTL_SECONDS]
    for k in stale:
        bucket.pop(k, None)
    return [
        {'user_key': k, 'display': v['display'], 'field': v['field']}
        for k, v in bucket.items() if k != exclude_user_key
    ]


def init_tables(cur):
    cur.execute('''
        CREATE TABLE IF NOT EXISTS pipeline_board_entries (
            id SERIAL PRIMARY KEY,
            pair_key VARCHAR(100) NOT NULL,
            proposal_number VARCHAR(100),
            property_name VARCHAR(255),
            address VARCHAR(255),
            project TEXT,
            status VARCHAR(30) NOT NULL DEFAULT 'draft',
            amount NUMERIC(12, 2),
            sub_pay NUMERIC(12, 2),
            trade_partner VARCHAR(255),
            client_contact VARCHAR(255),
            notes TEXT,
            row_order INTEGER NOT NULL DEFAULT 0,
            archived BOOLEAN NOT NULL DEFAULT FALSE,
            created_by VARCHAR(100),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_by VARCHAR(100),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_pipeline_board_pair ON pipeline_board_entries(pair_key, archived)"
    )


# Segment prefixes import_workbook used to fold into Notes (see below) --
# decided 2026-07-30 this just clutters the board and the field should
# start blank for people to write real notes into. import_workbook no
# longer generates these; this only cleans up rows imported before that.
_JUNK_NOTE_PREFIXES = ('Imported status:', 'Sent:')


def _strip_junk_notes(notes):
    if not notes:
        return None
    parts = [p.strip() for p in notes.split(' | ')]
    kept = [p for p in parts if not any(p.startswith(prefix) for prefix in _JUNK_NOTE_PREFIXES)]
    return ' | '.join(kept).strip() or None


def cleanup_legacy_import_notes(cur):
    """One-time cleanup of the auto-generated 'Imported status: ...' /
    'Sent: ...' text that earlier imports folded into Notes. Safe to run on
    every startup: it only rewrites rows whose stripped text actually
    differs, and since import_workbook stopped generating this text, there's
    nothing left for it to touch after the first successful pass -- it
    isn't a standing filter on notes people type in later."""
    cur.execute(
        "SELECT id, notes FROM pipeline_board_entries "
        "WHERE notes LIKE %s OR notes LIKE %s",
        ('%Imported status:%', '%Sent: 20%'),
    )
    for row in cur.fetchall():
        entry_id = row['id'] if isinstance(row, dict) else row[0]
        notes = row['notes'] if isinstance(row, dict) else row[1]
        cleaned = _strip_junk_notes(notes)
        if cleaned != notes:
            cur.execute(
                'UPDATE pipeline_board_entries SET notes = %s WHERE id = %s',
                (cleaned, entry_id),
            )


def get_pair_key(users, user_key):
    """Resolve which pair board a user belongs to. Consultants use their own
    key; PMs resolve to the consultant listed in their proposal_access."""
    user = users.get(user_key, {})
    role = user.get('role')
    if role == 'consultant':
        return user_key
    if role == 'pm':
        access = user.get('proposal_access') or []
        return access[0] if access else None
    return None


def can_access_board(users, user_key, pair_key):
    """Pilot members of that specific pair, or admin (preview)."""
    if pair_key not in PILOT_PAIR_CONSULTANTS:
        return False
    user = users.get(user_key, {})
    if user.get('role') == 'admin':
        return True
    return get_pair_key(users, user_key) == pair_key


def _display(users, user_key):
    return users.get(user_key, {}).get('display', user_key)


def _row_to_dict(row):
    d = dict(row)
    for k in ('amount', 'sub_pay'):
        if d.get(k) is not None:
            d[k] = float(d[k])
    for k in ('created_at', 'updated_at'):
        if d.get(k):
            d[k] = d[k].isoformat()
    return d


def list_entries(get_db_fn, pair_key):
    conn = get_db_fn()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('''
            SELECT * FROM pipeline_board_entries
            WHERE pair_key = %s AND archived = FALSE
            ORDER BY row_order ASC, id ASC
        ''', (pair_key,))
        rows = [_row_to_dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        print(f'Pipeline board list error: {e}')
        return []


def _prefix_from_pair_key(pair_key):
    """'andy_potts' -> 'AP', 'rachel_farler' -> 'RF' -- matches the real
    consultant-initials + 2-digit-year + 3-digit-sequence scheme already
    used in both source spreadsheets (AP26001, RF26102) and elsewhere in
    the Hub (TE26xxx for Thomas). Derived from the key, not a lookup table,
    so it keeps working for future pairs with no extra config."""
    parts = [p for p in pair_key.split('_') if p]
    prefix = ''.join(p[0] for p in parts[:2]).upper()
    return prefix or 'PB'


def _next_proposal_number(cur, pair_key):
    """Next number in THIS pair's own sequence (independent of the Hub's
    Proposal Generator numbering, per owner direction 2026-07-29) --
    <prefix><year>NNN, continuing from whatever's already on the board
    (including imported rows) rather than restarting at 001."""
    prefix = _prefix_from_pair_key(pair_key)
    year = f'{datetime.now().year % 100:02d}'
    stem = f'{prefix}{year}'
    cur.execute(
        'SELECT proposal_number FROM pipeline_board_entries '
        'WHERE pair_key = %s AND proposal_number IS NOT NULL',
        (pair_key,),
    )
    pattern = re.compile(rf'^{re.escape(stem)}(\d+)$', re.IGNORECASE)
    max_seq = 0
    for row in cur.fetchall():
        po = (row['proposal_number'] if isinstance(row, dict) else row[0]) or ''
        m = pattern.match(po.strip())
        if m:
            max_seq = max(max_seq, int(m.group(1)))
    return f'{stem}{max_seq + 1:03d}'


def create_entry(get_db_fn, pair_key, user_key):
    conn = get_db_fn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        proposal_number = _next_proposal_number(cur, pair_key)
        cur.execute('''
            INSERT INTO pipeline_board_entries
                (pair_key, proposal_number, status, row_order, created_by, updated_by)
            VALUES (%s, %s, 'draft',
                COALESCE((SELECT MAX(row_order) + 1 FROM pipeline_board_entries WHERE pair_key = %s), 0),
                %s, %s)
            RETURNING *
        ''', (pair_key, proposal_number, pair_key, user_key, user_key))
        row = _row_to_dict(cur.fetchone())
        conn.commit()
        cur.close()
        conn.close()
        return row
    except Exception as e:
        print(f'Pipeline board create error: {e}')
        return None


def _clean_text(value, max_len):
    if value is None:
        return None
    value = str(value).strip()[:max_len]
    return value or None


def _clean_numeric(value):
    if value in (None, ''):
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def update_entry(get_db_fn, entry_id, pair_key, user_key, fields):
    """Update whitelisted fields on one entry. Returns the updated row or None."""
    sets, params = [], []

    if 'status' in fields:
        status = fields['status']
        if status not in STATUS_VALUES:
            return None, 'Invalid status'
        sets.append('status = %s')
        params.append(status)

    for f in _EDITABLE_TEXT_FIELDS:
        if f in fields:
            sets.append(f'{f} = %s')
            params.append(_clean_text(fields[f], MAX_NOTES if f == 'notes' else MAX_TEXT))

    for f in _EDITABLE_NUMERIC_FIELDS:
        if f in fields:
            sets.append(f'{f} = %s')
            params.append(_clean_numeric(fields[f]))

    if not sets:
        return None, 'No editable fields provided'

    sets.append('updated_by = %s')
    sets.append('updated_at = NOW()')
    params.append(user_key)
    params.extend([entry_id, pair_key])

    conn = get_db_fn()
    if not conn:
        return None, 'Database unavailable'
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(f'''
            UPDATE pipeline_board_entries SET {", ".join(sets)}
            WHERE id = %s AND pair_key = %s AND archived = FALSE
            RETURNING *
        ''', params)
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if not row:
            return None, 'Entry not found'
        return _row_to_dict(row), None
    except Exception as e:
        print(f'Pipeline board update error: {e}')
        return None, 'Could not save'


def _normalize_header(h):
    if h is None:
        return ''
    text = str(h).strip().lower()
    text = text.replace('$', ' ').replace('?', ' ').replace('#', ' ')
    text = re.sub(r'[^a-z0-9 ]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


# Built directly from the two real sheets reviewed 2026-07-29 (Rachel Farler's
# and another consultant's "2026 PO / Proposals" + its "Bath Tubs Simms" tab),
# not guessed. 'notes:Label' means "keep it, just fold into Notes with this
# label" -- used for real columns (Material Cost, Splits, batch-job dates)
# that don't have their own schema field. Any header NOT in this map at all
# still isn't dropped: see _map_sheet's unmapped-column fallback below.
_HEADER_ALIASES = {
    'po': 'proposal_number',
    'po number': 'proposal_number',
    'proposal number': 'proposal_number',
    'proposal': 'proposal_number',
    'property': 'property_name',
    'address': 'address',
    'project': 'project',
    'job status': 'status',
    'status': 'status',
    'sent': 'sent_or_status',  # value-type sniffed: datetime -> note, text -> status
    'amount': 'amount',
    'cost': 'sub_pay',
    'sub pay': 'sub_pay',
    'material cost': 'notes:Material cost',
    'sub': 'trade_partner',
    'trade partner': 'trade_partner',
    'manager': 'client_contact',  # the *client's* property manager, confirmed from real data
    'company': 'client_contact',
    'client contact': 'client_contact',
    'splits': 'notes:Splits',
    'how many': 'notes:Qty',
    'date start': 'notes:Date start',
    'date end': 'notes:Date end',
    'started': 'notes:Started',
    'done': 'notes:Done',
    'paid out': 'notes:Paid out',
}

# Every real status value seen across both sheets, grouped. Deliberately no
# "IC" entry -- in the sample data every "IC" row was an "Indian Creek"
# property tag left in the wrong column, not a status (verified by checking
# every such row was for that one property). Anything not listed here still
# isn't lost: _normalize_status_value always preserves the raw text in Notes.
_STATUS_KEYWORDS = {
    'sent': {'yes', 'sent', 'proposed', 'propsed', 'verbal so far', 'online forms', 'email', 'work order'},
    'awarded': {'complete', 'completed', 'awarded', 'scheduled'},
    'on_hold': {'on hold', 'delayed'},
    'cancelled': {'cancelled', 'canceled', 'not doing', 'punt', 'duplicate'},
    'draft': {'no', 'none', 'na', 'n/a', '', '.....'},
}


def _normalize_status_value(raw):
    """Best-guess enum mapping, but ALWAYS returns the original text too --
    never silently collapse a real note ('waiting to hear from Desirae')
    into a clean-looking status without keeping what was actually written."""
    text = ('' if raw is None else str(raw)).strip()
    status = 'draft'
    for candidate, keywords in _STATUS_KEYWORDS.items():
        if text.lower() in keywords:
            status = candidate
            break
    return status, text


def _map_sheet(ws):
    """Map one worksheet's header row (row 1) to schema fields.
    Returns {col_index: target}; target is a schema field name, 'status',
    'sent_or_status', or 'notes:<label>'."""
    header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
    col_map = {}
    unmapped = []
    for i, raw_header in enumerate(header_row):
        norm = _normalize_header(raw_header)
        if not norm:
            continue
        if norm in _HEADER_ALIASES:
            col_map[i] = _HEADER_ALIASES[norm]
        elif i == 0:
            # An unrecognized first column is a job title/description in both
            # real sample sheets (e.g. "9456 Bainwoods - Soffitt / Roof
            # Repair") -- keep it visible as Project rather than Notes.
            col_map[i] = 'project'
        else:
            col_map[i] = f'notes:{raw_header}'
            unmapped.append(str(raw_header))
    return col_map, unmapped


def import_workbook(get_db_fn, file_obj, pair_key, user_key):
    """Import every sheet of an uploaded .xlsx into one pair's board.
    Never silently drops a column — anything not recognized lands in Notes,
    labeled with its original header, instead of being discarded."""
    try:
        wb = openpyxl.load_workbook(file_obj, data_only=True)
    except Exception as e:
        return {'success': False, 'error': f'Could not read that file as an Excel workbook: {e}'}

    conn = get_db_fn()
    if not conn:
        return {'success': False, 'error': 'Database unavailable'}

    imported = 0
    skipped = 0
    duplicates_skipped = 0
    warnings = []

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            'SELECT COALESCE(MAX(row_order), -1) + 1 AS next_order '
            'FROM pipeline_board_entries WHERE pair_key = %s',
            (pair_key,),
        )
        row_order = cur.fetchone()['next_order']

        # Dedup set for "skip if this PO already exists" -- checked against
        # every entry ever created for this pair (archived or not, so a
        # re-import can't resurrect a duplicate of something removed), and
        # updated as we go so two identical rows within the same file (or
        # sheet) are also caught, not just repeats across separate imports.
        cur.execute(
            'SELECT proposal_number FROM pipeline_board_entries '
            'WHERE pair_key = %s AND proposal_number IS NOT NULL',
            (pair_key,),
        )
        existing_pos = {
            r['proposal_number'].strip().upper()
            for r in cur.fetchall() if r['proposal_number']
        }

        # Only the first sheet is treated as real tracking data. Extra tabs in
        # these workbooks have turned out to be ad hoc scratch space (e.g. a
        # "doodle" tab someone used to track one side project with a totally
        # different, inconsistent shape — confirmed 2026-07-29) rather than
        # more of the same table, so importing them blindly does more harm
        # than good. Note it rather than silently ignore it.
        ws = wb.worksheets[0]
        if len(wb.worksheets) > 1:
            skipped_titles = [s.title for s in wb.worksheets[1:]]
            warnings.append(
                f'Only imported the first sheet ("{ws.title}"). '
                f'Additional tab(s) ignored: {", ".join(skipped_titles)}.'
            )

        col_map, unmapped = _map_sheet(ws)
        if unmapped:
            warnings.append(
                f'Columns not recognized, kept in Notes: {", ".join(unmapped)}'
            )
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row is None or all(v in (None, '') for v in row):
                continue
            fields = {}
            notes_parts = []
            has_content = False
            for i, value in enumerate(row):
                if value is None or value == '' or i not in col_map:
                    continue
                target = col_map[i]
                if target == 'sent_or_status' and isinstance(value, (datetime, date)):
                    # A sent-date value counts as real data even though (per
                    # owner direction 2026-07-30) it no longer gets written
                    # into Notes -- that bookkeeping cluttered the board and
                    # the field should start clean for people to write real
                    # notes into. The date itself is a genuine loss on
                    # import; if it turns out to matter, add a real
                    # sent_date column instead of reviving the notes hack.
                    has_content = True
                elif target in ('status', 'sent_or_status'):
                    status, raw_text = _normalize_status_value(value)
                    fields['status'] = status
                    has_content = True
                elif target.startswith('notes:'):
                    notes_parts.append(f'{target.split(":", 1)[1]}: {value}')
                    has_content = True
                elif target in _EDITABLE_NUMERIC_FIELDS:
                    cleaned = _clean_numeric(value)
                    if cleaned is not None:
                        fields[target] = cleaned
                        has_content = True
                else:
                    cleaned = _clean_text(value, MAX_TEXT)
                    if cleaned:
                        fields[target] = cleaned
                        has_content = True

            if not has_content:
                skipped += 1
                continue

            if notes_parts:
                fields['notes'] = _clean_text(' | '.join(notes_parts), MAX_NOTES)

            po_key = (fields.get('proposal_number') or '').strip().upper()
            if po_key and po_key in existing_pos:
                duplicates_skipped += 1
                continue
            if po_key:
                existing_pos.add(po_key)

            cur.execute('''
                INSERT INTO pipeline_board_entries
                    (pair_key, proposal_number, property_name, address, project, status,
                     amount, sub_pay, trade_partner, client_contact, notes, row_order,
                     created_by, updated_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                pair_key, fields.get('proposal_number'), fields.get('property_name'),
                fields.get('address'), fields.get('project'), fields.get('status', 'draft'),
                fields.get('amount'), fields.get('sub_pay'), fields.get('trade_partner'),
                fields.get('client_contact'), fields.get('notes'), row_order,
                user_key, user_key,
            ))
            row_order += 1
            imported += 1
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f'Pipeline board import error: {e}')
        return {'success': False, 'error': 'Could not import that file — no rows were added.'}

    return {
        'success': True, 'imported': imported, 'skipped': skipped,
        'duplicates_skipped': duplicates_skipped, 'warnings': warnings,
    }


def archive_entry(get_db_fn, entry_id, pair_key):
    conn = get_db_fn()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute('''
            UPDATE pipeline_board_entries SET archived = TRUE, updated_at = NOW()
            WHERE id = %s AND pair_key = %s
        ''', (entry_id, pair_key))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f'Pipeline board archive error: {e}')
        return False


def register_routes(app, get_db_fn, users, require_login):
    from flask import jsonify, render_template, request, session, redirect, url_for

    def _current_pair(fallback_query_override_for_admin=True):
        """Resolve the pair_key this request should operate on."""
        user_key = session['user_key']
        pair_key = get_pair_key(users, user_key)
        if fallback_query_override_for_admin and users.get(user_key, {}).get('role') == 'admin':
            override = (request.args.get('pair')
                        or request.form.get('pair')
                        or (request.get_json(silent=True) or {}).get('pair'))
            if override:
                pair_key = override
        return user_key, pair_key

    @app.route('/pipeline-board')
    @require_login
    def pipeline_board_page():
        user_key, pair_key = _current_pair()
        if not pair_key or not can_access_board(users, user_key, pair_key):
            return redirect(url_for('dashboard'))
        pm_key = None
        for k, u in users.items():
            if u.get('role') == 'pm' and pair_key in (u.get('proposal_access') or []):
                pm_key = k
                break
        return render_template(
            'pipeline_board.html',
            pair_key=pair_key,
            consultant_display=_display(users, pair_key),
            pm_display=_display(users, pm_key) if pm_key else 'PM',
            statuses=STATUSES,
            user_key=user_key,
            user_display=_display(users, user_key),
            is_admin_preview=(users.get(user_key, {}).get('role') == 'admin'
                              and get_pair_key(users, user_key) != pair_key),
        )

    @app.route('/api/pipeline-board/entries', methods=['GET', 'POST'])
    @require_login
    def pipeline_board_entries_api():
        user_key, pair_key = _current_pair()
        if not pair_key or not can_access_board(users, user_key, pair_key):
            return jsonify({'error': 'Not authorized'}), 403
        if request.method == 'GET':
            return jsonify({
                'entries': list_entries(get_db_fn, pair_key),
                'presence': _live_presence(pair_key, exclude_user_key=user_key),
                'pair_key': pair_key,
            })
        entry = create_entry(get_db_fn, pair_key, user_key)
        if not entry:
            return jsonify({'error': 'Could not create row'}), 500
        return jsonify({'success': True, 'entry': entry})

    @app.route('/api/pipeline-board/entries/<int:entry_id>', methods=['POST'])
    @require_login
    def pipeline_board_update_api(entry_id):
        user_key, pair_key = _current_pair()
        if not pair_key or not can_access_board(users, user_key, pair_key):
            return jsonify({'error': 'Not authorized'}), 403
        data = request.get_json(silent=True) or {}
        fields = {k: v for k, v in data.items() if k in
                  _EDITABLE_TEXT_FIELDS + _EDITABLE_NUMERIC_FIELDS + ('status',)}
        entry, err = update_entry(get_db_fn, entry_id, pair_key, user_key, fields)
        if err:
            return jsonify({'error': err}), 400
        return jsonify({'success': True, 'entry': entry})

    @app.route('/api/pipeline-board/import', methods=['POST'])
    @require_login
    def pipeline_board_import_api():
        user_key, pair_key = _current_pair()
        if not pair_key or not can_access_board(users, user_key, pair_key):
            return jsonify({'error': 'Not authorized'}), 403
        file = request.files.get('file')
        if not file or not file.filename:
            return jsonify({'error': 'No file selected'}), 400
        if not file.filename.lower().endswith(('.xlsx', '.xlsm')):
            return jsonify({'error': 'Please upload an .xlsx (Excel) file'}), 400
        result = import_workbook(get_db_fn, file, pair_key, user_key)
        if not result.get('success'):
            return jsonify(result), 400
        return jsonify(result)

    @app.route('/api/pipeline-board/entries/<int:entry_id>/archive', methods=['POST'])
    @require_login
    def pipeline_board_archive_api(entry_id):
        user_key, pair_key = _current_pair()
        if not pair_key or not can_access_board(users, user_key, pair_key):
            return jsonify({'error': 'Not authorized'}), 403
        ok = archive_entry(get_db_fn, entry_id, pair_key)
        if not ok:
            return jsonify({'error': 'Could not remove row'}), 500
        return jsonify({'success': True})

    @app.route('/api/pipeline-board/presence', methods=['POST'])
    @require_login
    def pipeline_board_presence_api():
        """Heartbeat: 'I'm here, and here's what I'm editing (or nothing)'.
        Called on focus/blur and on a timer while a cell stays focused, from
        the poll loop in pipeline_board.html — replaces the old Socket.IO
        join/cell_focus/disconnect events with plain polling (see module
        docstring for why)."""
        user_key, pair_key = _current_pair()
        if not pair_key or not can_access_board(users, user_key, pair_key):
            return jsonify({'error': 'Not authorized'}), 403
        data = request.get_json(silent=True) or {}
        field = (data.get('field') or '').strip()[:100] or None
        _touch_presence(pair_key, user_key, _display(users, user_key), field)
        return jsonify({'success': True, 'presence': _live_presence(pair_key, exclude_user_key=user_key)})
