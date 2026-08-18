"""Pure-logic tests for pipeline_board.py -- no live Postgres required.

Scope is deliberately narrow: status validation, auto-numbering, the
explicit board-access roster, and the import column-mapping fallback --
the parts most likely to silently regress, cheap to check without a
database. Run with:

    cd pps-hub && python -m pytest tests/test_pipeline_board.py -v
"""
import io
import os
import sys

import openpyxl

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pipeline_board as pb


# --- Status set integrity -----------------------------------------------

def test_completed_statuses_is_subset_of_status_values():
    assert pb.COMPLETED_STATUSES <= pb.STATUS_VALUES


def test_completed_statuses_excludes_pre_draft_and_active_statuses():
    # Locks in the highlight-eligibility logic (mirrors the JS isInProgress()
    # helper in templates/pipeline_board.html) against silent drift.
    assert pb.COMPLETED_STATUSES == {'sent', 'awarded', 'cancelled'}
    for still_open in ('new', 'needs_scope', 'scoped', 'draft', 'on_hold', 'declined'):
        assert still_open not in pb.COMPLETED_STATUSES


# --- Import status-keyword mapping ---------------------------------------

def test_normalize_status_value_keyword_mapping():
    cases = [
        ('Scheduled', 'awarded'),
        ('scheduled', 'awarded'),
        ('Complete', 'awarded'),
        ('On Hold', 'on_hold'),
        ('cancelled', 'cancelled'),
        ('not doing', 'cancelled'),
        ('n/a', 'draft'),
        ('', 'draft'),
    ]
    for raw, expected_status in cases:
        status, raw_text = pb._normalize_status_value(raw)
        assert status == expected_status, f'{raw!r} -> {status!r}, expected {expected_status!r}'
        assert raw_text == raw.strip()


def test_normalize_status_value_unrecognized_falls_back_to_draft_but_keeps_raw_text():
    status, raw_text = pb._normalize_status_value("waiting on Desirae")
    assert status == 'draft'
    assert raw_text == "waiting on Desirae"


def test_normalize_status_value_never_produces_pre_draft_stages():
    # Regression guard for the deliberate 2026-08-04 decision (see CLAUDE.md,
    # "Design decisions that look like bugs but aren't"): import must never
    # reach 'new' / 'needs_scope' / 'scoped', since those describe
    # nobody's-looked-at-it-yet stages a historical spreadsheet row can't
    # truthfully claim. If this ever fails, someone edited _STATUS_KEYWORDS
    # to add such a mapping -- that's a decision to revisit deliberately,
    # not something that should slide through unreviewed.
    pre_draft = {'new', 'needs_scope', 'scoped'}
    for keywords in pb._STATUS_KEYWORDS.values():
        for word in keywords:
            status, _ = pb._normalize_status_value(word)
            assert status not in pre_draft, f'{word!r} resolved to {status!r}'


# --- Proposal auto-numbering ---------------------------------------------

def test_prefix_from_pair_key():
    assert pb._prefix_from_pair_key('andy_potts') == 'AP'
    assert pb._prefix_from_pair_key('rachel_farler') == 'RF'
    # A single-token key (no underscore) has only one part to take an
    # initial from -- 'O', not a 2-letter prefix. The 'PB' fallback is for
    # when there's no usable part at all (empty/all-underscore key).
    assert pb._prefix_from_pair_key('onename') == 'O'
    assert pb._prefix_from_pair_key('') == 'PB'
    assert pb._prefix_from_pair_key('___') == 'PB'


class _FakeNumberingCursor:
    """Just enough of a cursor for _next_proposal_number: one SELECT, rows
    shaped like RealDictCursor would return them."""
    def __init__(self, rows):
        self._rows = rows
    def execute(self, sql, params=None):
        pass
    def fetchall(self):
        return self._rows


def test_next_proposal_number_continues_max_not_count():
    import datetime
    yy = f'{datetime.datetime.now().year % 100:02d}'
    # A gap (005 -> 007) proves this is MAX+1, not COUNT+1 (which would say 003).
    cur = _FakeNumberingCursor([
        {'proposal_number': f'AP{yy}005'},
        {'proposal_number': f'AP{yy}007'},
    ])
    assert pb._next_proposal_number(cur, 'andy_potts') == f'AP{yy}008'


def test_next_proposal_number_empty_board():
    cur = _FakeNumberingCursor([])
    import datetime
    yy = f'{datetime.datetime.now().year % 100:02d}'
    assert pb._next_proposal_number(cur, 'rachel_farler') == f'RF{yy}001'


def test_next_proposal_number_ignores_other_pairs_and_other_years():
    import datetime
    yy = f'{datetime.datetime.now().year % 100:02d}'
    cur = _FakeNumberingCursor([
        {'proposal_number': f'AP{yy}099'},   # different prefix (Andy's), ignored for Rachel
        {'proposal_number': 'RF20050'},       # same prefix, different/old year, ignored
    ])
    assert pb._next_proposal_number(cur, 'rachel_farler') == f'RF{yy}001'


# --- update_entry validation ----------------------------------------------

def test_update_entry_rejects_invalid_status_before_touching_db():
    def get_db_fn_should_not_be_called():
        raise AssertionError('update_entry should fail fast on an invalid status '
                              'without ever opening a DB connection')
    entry, err = pb.update_entry(
        get_db_fn_should_not_be_called, entry_id=1, pair_key='andy_potts',
        user_key='andy_potts', fields={'status': 'not_a_real_status'},
    )
    assert entry is None
    assert err == 'Invalid status'


def test_update_entry_rejects_empty_fields_before_touching_db():
    def get_db_fn_should_not_be_called():
        raise AssertionError('update_entry should fail fast on no editable fields')
    entry, err = pb.update_entry(
        get_db_fn_should_not_be_called, entry_id=1, pair_key='andy_potts',
        user_key='andy_potts', fields={'not_a_real_field': 'x'},
    )
    assert entry is None
    assert err == 'No editable fields provided'


# --- Presence (DB-backed, moved off the in-process dict 2026-08-04) --------

class _FakePresenceCursor:
    """Records every execute() call so tests can assert on the SQL shape
    without a live Postgres connection."""
    def __init__(self, select_rows=None):
        self.executed = []
        self._select_rows = select_rows or []

    def execute(self, sql, params=None):
        self.executed.append((sql.strip(), params))

    def fetchall(self):
        return self._select_rows

    def close(self):
        pass


class _FakePresenceConn:
    def __init__(self, select_rows=None):
        self.cur = _FakePresenceCursor(select_rows)
        self.committed = False
        self.closed = False

    def cursor(self, cursor_factory=None):
        return self.cur

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


def test_touch_presence_upserts_when_field_present():
    conn = _FakePresenceConn()
    pb._touch_presence(lambda: conn, 'andy_potts', 'ben_ramsey', 'Ben Ramsey', 'row5:notes')
    assert conn.committed
    sql, params = conn.cur.executed[0]
    assert sql.startswith('INSERT INTO pipeline_board_presence')
    assert 'ON CONFLICT' in sql
    assert params == ('andy_potts', 'ben_ramsey', 'Ben Ramsey', 'row5:notes')


def test_touch_presence_deletes_when_field_falsy():
    # A blur event (empty field) should clear the row, not upsert an empty one.
    conn = _FakePresenceConn()
    pb._touch_presence(lambda: conn, 'andy_potts', 'ben_ramsey', 'Ben Ramsey', None)
    sql, params = conn.cur.executed[0]
    assert sql.startswith('DELETE FROM pipeline_board_presence')
    assert params == ('andy_potts', 'ben_ramsey')


def test_touch_presence_no_conn_does_not_raise():
    pb._touch_presence(lambda: None, 'andy_potts', 'ben_ramsey', 'Ben Ramsey', 'row5:notes')


def test_live_presence_expires_stale_rows_before_selecting():
    # Regression guard for the fix itself: expiry has to happen server-side
    # in SQL now (no more Python dict iterating timestamps), so the DELETE
    # must run before the SELECT on every read.
    conn = _FakePresenceConn(select_rows=[
        {'user_key': 'ben_ramsey', 'display': 'Ben Ramsey', 'field': 'row5:notes'},
    ])
    result = pb._live_presence(lambda: conn, 'andy_potts', exclude_user_key='andy_potts')
    delete_sql, _ = conn.cur.executed[0]
    select_sql, select_params = conn.cur.executed[1]
    assert delete_sql.startswith('DELETE FROM pipeline_board_presence WHERE ts')
    assert select_sql.startswith('SELECT user_key, display, field FROM pipeline_board_presence')
    assert select_params == ('andy_potts', 'andy_potts')
    assert result == [{'user_key': 'ben_ramsey', 'display': 'Ben Ramsey', 'field': 'row5:notes'}]
    assert conn.committed


def test_live_presence_no_conn_returns_empty_list():
    assert pb._live_presence(lambda: None, 'andy_potts') == []


# --- Access gating ----------------------------------------------------------

_USERS = {
    'andy_potts': {'display': 'Andy Potts', 'role': 'consultant'},
    'ben_ramsey': {'display': 'Ben Ramsey', 'role': 'pm'},
    'rachel_farler': {'display': 'Rachel Farler', 'role': 'consultant'},
    'derek_kidney': {'display': 'Derek Kidney', 'role': 'pm'},
    'adam_cupito': {'display': 'Adam Cupito', 'role': 'consultant'},
    'james_boling': {'display': 'James Boling', 'role': 'pm'},
    'jordan_allen': {'display': 'Jordan Allen', 'role': 'pm', 'proposal_access': 'all'},
    'nick_triplett': {'display': 'Nick Triplett', 'role': 'pm'},
    'tony_cumella': {'display': 'Tony Cumella', 'role': 'consultant'},
    'trey_hollmeyer': {'display': 'Trey Hollmeyer', 'role': 'pm', 'proposal_access': 'all'},
    'phil_miller': {'display': 'Phil Miller', 'role': 'pm', 'proposal_access': 'all'},
    'stephanie_whetstone': {'display': 'Stephanie Whetstone', 'role': 'office_manager'},
    'thomas_ellison': {'display': 'Thomas Ellison', 'role': 'admin'},
    'rj': {'display': 'RJ', 'role': 'pm', 'proposal_access': 'all'},
}


def test_get_pair_key_consultant_uses_own_key():
    assert pb.get_pair_key(_USERS, 'andy_potts') == 'andy_potts'
    assert pb.get_pair_key(_USERS, 'rachel_farler') == 'rachel_farler'
    assert pb.get_pair_key(_USERS, 'adam_cupito') == 'adam_cupito'
    assert pb.get_pair_key(_USERS, 'tony_cumella') == 'tony_cumella'


def test_get_pair_key_primary_pm_lands_on_their_consultant():
    assert pb.get_pair_key(_USERS, 'ben_ramsey') == 'andy_potts'
    assert pb.get_pair_key(_USERS, 'derek_kidney') == 'rachel_farler'
    assert pb.get_pair_key(_USERS, 'jordan_allen') == 'adam_cupito'
    assert pb.get_pair_key(_USERS, 'nick_triplett') == 'tony_cumella'


def test_get_pair_key_admin_has_no_pair_of_their_own():
    assert pb.get_pair_key(_USERS, 'thomas_ellison') is None


def test_get_pair_key_oversight_defaults_to_first_board():
    # Trey / Stephanie can open every board; default is BOARD_CONSULTANTS[0]
    # (Andy) so /pipeline-board without ?pair= still lands somewhere.
    assert pb.get_pair_key(_USERS, 'trey_hollmeyer') == 'andy_potts'
    assert pb.get_pair_key(_USERS, 'stephanie_whetstone') == 'andy_potts'
    assert pb.get_pair_key(_USERS, 'rj') == 'andy_potts'


def test_get_pair_key_ignores_proposal_access_all():
    # Jordan and Phil both carry proposal_access 'all' in Hub. Pipeline
    # access is the explicit roster — Phil is on no board, Jordan is on
    # Adam (primary) + Andy, not Tony/Rachel.
    assert pb.get_pair_key(_USERS, 'phil_miller') is None
    assert pb.can_access_board(_USERS, 'phil_miller', 'andy_potts') is False
    assert pb.can_access_board(_USERS, 'jordan_allen', 'tony_cumella') is False


def test_can_access_board_owner_and_named_roster():
    assert pb.can_access_board(_USERS, 'andy_potts', 'andy_potts') is True
    assert pb.can_access_board(_USERS, 'ben_ramsey', 'andy_potts') is True
    assert pb.can_access_board(_USERS, 'adam_cupito', 'andy_potts') is True
    assert pb.can_access_board(_USERS, 'jordan_allen', 'andy_potts') is True
    assert pb.can_access_board(_USERS, 'james_boling', 'andy_potts') is True
    assert pb.can_access_board(_USERS, 'adam_cupito', 'adam_cupito') is True
    assert pb.can_access_board(_USERS, 'jordan_allen', 'adam_cupito') is True
    assert pb.can_access_board(_USERS, 'james_boling', 'adam_cupito') is True
    assert pb.can_access_board(_USERS, 'andy_potts', 'adam_cupito') is True
    assert pb.can_access_board(_USERS, 'ben_ramsey', 'adam_cupito') is True
    assert pb.can_access_board(_USERS, 'nick_triplett', 'tony_cumella') is True
    assert pb.can_access_board(_USERS, 'derek_kidney', 'rachel_farler') is True


def test_can_access_board_wrong_pair_denied():
    assert pb.can_access_board(_USERS, 'derek_kidney', 'andy_potts') is False
    assert pb.can_access_board(_USERS, 'nick_triplett', 'adam_cupito') is False
    assert pb.can_access_board(_USERS, 'rachel_farler', 'adam_cupito') is False


def test_can_access_board_oversight_all_boards():
    for user_key in ('thomas_ellison', 'trey_hollmeyer', 'stephanie_whetstone', 'rj'):
        for ck in pb.BOARD_CONSULTANTS:
            assert pb.can_access_board(_USERS, user_key, ck) is True, (user_key, ck)


def test_list_accessible_boards_for_multi_board_users():
    andy = [b['key'] for b in pb.list_accessible_boards(_USERS, 'andy_potts')]
    assert andy == ['andy_potts', 'adam_cupito']
    nick = [b['key'] for b in pb.list_accessible_boards(_USERS, 'nick_triplett')]
    assert nick == ['tony_cumella']
    trey = [b['key'] for b in pb.list_accessible_boards(_USERS, 'trey_hollmeyer')]
    assert trey == list(pb.BOARD_CONSULTANTS)
    steph = [b['key'] for b in pb.list_accessible_boards(_USERS, 'stephanie_whetstone')]
    assert steph == list(pb.BOARD_CONSULTANTS)
    rj = [b['key'] for b in pb.list_accessible_boards(_USERS, 'rj')]
    assert rj == list(pb.BOARD_CONSULTANTS)


# --- Import column mapping --------------------------------------------------

def _workbook_with_headers(headers):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    ws.append(['x'] * len(headers))
    return ws


def test_map_sheet_recognizes_known_headers():
    ws = _workbook_with_headers(['PO', 'Property', 'Job Status'])
    col_map, unmapped = pb._map_sheet(ws)
    assert col_map[0] == 'proposal_number'
    assert col_map[1] == 'property_name'
    assert col_map[2] == 'status'
    assert unmapped == []


def test_map_sheet_unmapped_column_falls_back_to_notes_not_dropped():
    # Covers the "never silently drops a column" invariant the module
    # docstring promises: an unrecognized header still shows up somewhere.
    ws = _workbook_with_headers(['PO', 'Random Column'])
    col_map, unmapped = pb._map_sheet(ws)
    assert col_map[0] == 'proposal_number'
    assert col_map[1] == 'notes:Random Column'
    assert unmapped == ['Random Column']


def test_map_sheet_unrecognized_first_column_becomes_project_not_notes():
    # Both real source sheets had an unlabeled/oddly-labeled first column
    # that was actually a job title/description -- confirmed this stays
    # visible as Project rather than getting buried in Notes.
    ws = _workbook_with_headers(['2026 PO / Proposals', 'Amount'])
    col_map, unmapped = pb._map_sheet(ws)
    assert col_map[0] == 'project'
    assert 'Amount' not in unmapped  # 'Amount' is a recognized header


# --- list_entries must not pretend "empty board" on DB failure ------------

def test_list_entries_db_unavailable_returns_none_not_empty_list():
    # Regression: when Render Postgres was suspended, list_entries returned []
    # and the client wiped every row. Failure must be distinguishable from
    # a legitimately empty board.
    rows, err = pb.list_entries(lambda: None, 'andy_potts')
    assert rows is None
    assert err
    assert 'Database' in err or 'unavailable' in err.lower()
