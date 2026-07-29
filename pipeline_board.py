"""Pipeline Board — live shared Consultant/PM proposal-tracking sheet.

Replaces the ad hoc shared Google Sheets each Consultant/PM pair has been keeping
(e.g. "who's waiting on sub pricing", "did I log every proposal I sent"). One
board per pair, live-updated for everyone viewing it via Socket.IO.

Pilot (2026-07-29): Andy Potts <-> Ben Ramsey, Rachel Farler <-> Derek Kidney.
A pair's board is keyed by the *consultant's* user_key (`pair_key`) since the
consultant owns the client relationship; the paired PM writes to the same board.

Status values were chosen by reviewing two real exported sheets (Rachel Farler's
and another consultant's) rather than guessed — see chat history 2026-07-29.
Do NOT add an "IC" status: in the sample data every "IC" row was actually an
"Indian Creek" property tag left in the wrong column, not a real status.
"""

from datetime import datetime

from flask_socketio import emit, join_room, leave_room
from psycopg2.extras import RealDictCursor

PILOT_PAIR_CONSULTANTS = frozenset({'andy_potts', 'rachel_farler'})

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
MAX_NOTES = 4000

_EDITABLE_TEXT_FIELDS = ('proposal_number', 'property_name', 'address', 'project',
                         'trade_partner', 'client_contact', 'notes')
_EDITABLE_NUMERIC_FIELDS = ('amount', 'sub_pay')

# In-memory presence: pair_key -> {sid: {'user_key', 'display', 'field'}}
_presence = {}
# sid -> pair_key, so disconnect can find which room to clean up
_sid_pair = {}


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


def create_entry(get_db_fn, pair_key, user_key):
    conn = get_db_fn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('''
            INSERT INTO pipeline_board_entries
                (pair_key, status, row_order, created_by, updated_by)
            VALUES (%s, 'draft',
                COALESCE((SELECT MAX(row_order) + 1 FROM pipeline_board_entries WHERE pair_key = %s), 0),
                %s, %s)
            RETURNING *
        ''', (pair_key, pair_key, user_key, user_key))
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


def register_routes(app, socketio, get_db_fn, users, require_login):
    from flask import jsonify, render_template, request, session, redirect, url_for

    def _current_pair(fallback_query_override_for_admin=True):
        """Resolve the pair_key this request should operate on."""
        user_key = session['user_key']
        pair_key = get_pair_key(users, user_key)
        if fallback_query_override_for_admin and users.get(user_key, {}).get('role') == 'admin':
            override = (request.args.get('pair') or (request.get_json(silent=True) or {}).get('pair'))
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
            return jsonify({'entries': list_entries(get_db_fn, pair_key), 'pair_key': pair_key})
        entry = create_entry(get_db_fn, pair_key, user_key)
        if not entry:
            return jsonify({'error': 'Could not create row'}), 500
        socketio.emit('entry_created', entry, room=f'pipeline_{pair_key}')
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
        socketio.emit('entry_updated', entry, room=f'pipeline_{pair_key}')
        return jsonify({'success': True, 'entry': entry})

    @app.route('/api/pipeline-board/entries/<int:entry_id>/archive', methods=['POST'])
    @require_login
    def pipeline_board_archive_api(entry_id):
        user_key, pair_key = _current_pair()
        if not pair_key or not can_access_board(users, user_key, pair_key):
            return jsonify({'error': 'Not authorized'}), 403
        ok = archive_entry(get_db_fn, entry_id, pair_key)
        if not ok:
            return jsonify({'error': 'Could not remove row'}), 500
        socketio.emit('entry_archived', {'id': entry_id}, room=f'pipeline_{pair_key}')
        return jsonify({'success': True})

    # --- Socket.IO: presence only. All writes go through the REST API above
    # and broadcast from there, so DB access always happens on the normal
    # request path (see pipeline_board.py module docstring). ---

    @socketio.on('join_pipeline_board')
    def _on_join(data):
        user_key = session.get('user_key')
        if not user_key:
            return
        pair_key = (data or {}).get('pair_key')
        if not pair_key or not can_access_board(users, user_key, pair_key):
            return
        room = f'pipeline_{pair_key}'
        join_room(room)
        _sid_pair[request.sid] = (room, pair_key)
        _presence.setdefault(pair_key, {})[request.sid] = {
            'user_key': user_key, 'display': _display(users, user_key), 'field': None,
        }
        emit('presence_state', list(_presence[pair_key].values()), room=room)

    @socketio.on('cell_focus')
    def _on_cell_focus(data):
        entry = _sid_pair.get(request.sid)
        if not entry:
            return
        room, pair_key = entry
        field = (data or {}).get('field')
        if request.sid in _presence.get(pair_key, {}):
            _presence[pair_key][request.sid]['field'] = field
        emit('presence_state', list(_presence.get(pair_key, {}).values()), room=room)

    @socketio.on('disconnect')
    def _on_disconnect():
        entry = _sid_pair.pop(request.sid, None)
        if not entry:
            return
        room, pair_key = entry
        _presence.get(pair_key, {}).pop(request.sid, None)
        leave_room(room)
        emit('presence_state', list(_presence.get(pair_key, {}).values()), room=room)
