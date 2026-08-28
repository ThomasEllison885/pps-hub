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

# Mirrors app.USERS after the 2026-08-21 tier rework: display / role / tier.
# `proposal_access`, `ppm_access`, `team_view` and `team_view_scope` are gone.
# The retired shared 'admin' login is deliberately ABSENT — removal means
# removal from the roster, and that absence is what the guard test asserts on.
_USERS = {
    'andy_potts': {'display': 'Andy Potts', 'role': 'consultant', 'tier': 'team'},
    'ben_ramsey': {'display': 'Ben Ramsey', 'role': 'pm', 'tier': 'team'},
    'rachel_farler': {'display': 'Rachel Farler', 'role': 'consultant', 'tier': 'team'},
    'adam_cupito': {'display': 'Adam Cupito', 'role': 'consultant', 'tier': 'team'},
    'james_boling': {'display': 'James Boling', 'role': 'pm', 'tier': 'team'},
    'jordan_allen': {'display': 'Jordan Allen', 'role': 'pm', 'tier': 'team'},
    'nick_triplett': {'display': 'Nick Triplett', 'role': 'pm', 'tier': 'team'},
    'tony_cumella': {'display': 'Tony Cumella', 'role': 'consultant', 'tier': 'leadership'},
    'trey_hollmeyer': {'display': 'Trey Hollmeyer', 'role': 'pm', 'tier': 'leadership'},
    'phil_miller': {'display': 'Phil Miller', 'role': 'pm', 'tier': 'team'},
    'stephanie_whetstone': {'display': 'Stephanie Whetstone', 'role': 'office_manager',
                            'tier': 'leadership'},
    'thomas_ellison': {'display': 'Thomas Ellison', 'role': 'admin', 'tier': 'owner'},
}


def test_get_pair_key_consultant_uses_own_key():
    assert pb.get_pair_key(_USERS, 'andy_potts') == 'andy_potts'
    assert pb.get_pair_key(_USERS, 'rachel_farler') == 'rachel_farler'
    assert pb.get_pair_key(_USERS, 'adam_cupito') == 'adam_cupito'
    assert pb.get_pair_key(_USERS, 'tony_cumella') == 'tony_cumella'


def test_get_pair_key_primary_pm_lands_on_their_consultant():
    assert pb.get_pair_key(_USERS, 'ben_ramsey') == 'andy_potts'
    assert pb.get_pair_key(_USERS, 'jordan_allen') == 'adam_cupito'
    assert pb.get_pair_key(_USERS, 'nick_triplett') == 'tony_cumella'


def test_get_pair_key_owner_has_no_pair_of_their_own():
    # Thomas picks a board via ?pair=; he is nobody's working pair.
    assert pb.get_pair_key(_USERS, 'thomas_ellison') is None


def test_get_pair_key_oversight_defaults_to_first_board():
    # Trey / Stephanie can open every board; default is BOARD_CONSULTANTS[0]
    # (Andy) so /pipeline-board without ?pair= still lands somewhere.
    assert pb.get_pair_key(_USERS, 'trey_hollmeyer') == 'andy_potts'
    assert pb.get_pair_key(_USERS, 'stephanie_whetstone') == 'andy_potts'


def test_assignment_is_not_permission():
    """Phil has no working-pair assignment and still opens every board.

    This is the whole point of the 2026-08-21 split. Before it, "who is this
    consultant's PM" and "who may open this board" were tangled together in
    overlapping rosters, and the fix for each new gap was another list. Now
    assignment only decides where you LAND — Phil, having none, falls through
    to the first board rather than being locked out of all of them.
    """
    assert pb.get_pair_key(_USERS, 'phil_miller') == pb.BOARD_CONSULTANTS[0]
    for ck in pb.BOARD_CONSULTANTS:
        assert pb.can_access_board(_USERS, 'phil_miller', ck) is True, ck
        assert pb.can_access_board(_USERS, 'jordan_allen', ck) is True, ck


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
    assert pb.can_access_board(_USERS, 'rachel_farler', 'rachel_farler') is True


def test_can_access_board_still_fails_closed_on_bad_input():
    """Open to everyone means everyone who works here — not anyone at all."""
    # Not a real board.
    assert pb.can_access_board(_USERS, 'phil_miller', 'nobody_at_all') is False
    assert pb.can_access_board(_USERS, 'phil_miller', '') is False
    # Not on the roster — this is what makes removing someone from USERS
    # actually revoke their boards.
    assert pb.can_access_board(_USERS, 'former_employee', 'andy_potts') is False
    assert pb.can_access_board(_USERS, '', 'andy_potts') is False
    assert pb.can_access_board(_USERS, None, 'andy_potts') is False


def test_can_access_board_oversight_all_boards():
    for user_key in ('thomas_ellison', 'trey_hollmeyer', 'stephanie_whetstone'):
        for ck in pb.BOARD_CONSULTANTS:
            assert pb.can_access_board(_USERS, user_key, ck) is True, (user_key, ck)


def test_retired_shared_admin_login_has_no_boards():
    """The shared 'admin' picker login was removed 2026-08-21 (F-01).

    Now that every board is open to everyone on the roster, the roster IS the
    boundary — so this asserts the removal all the way through: 'admin' is not
    in _USERS, and therefore opens nothing and gets no default board. If anyone
    re-adds that key to USERS, this test goes green again and should be read as
    a deliberate decision, not an accident.
    """
    assert 'admin' not in _USERS
    assert pb.get_pair_key(_USERS, 'admin') is None
    assert pb.list_accessible_boards(_USERS, 'admin') == []
    for ck in pb.BOARD_CONSULTANTS:
        assert pb.can_access_board(_USERS, 'admin', ck) is False, ck


def test_list_accessible_boards_is_every_board_for_everyone():
    """Every roster member gets the full switcher (2026-08-21)."""
    for user_key in _USERS:
        keys = [b['key'] for b in pb.list_accessible_boards(_USERS, user_key)]
        assert keys == list(pb.BOARD_CONSULTANTS), user_key


def test_list_accessible_boards_labels_the_working_pair():
    """Assignment survives as a label even though it gates nothing."""
    boards = {b['key']: b for b in pb.list_accessible_boards(_USERS, 'phil_miller')}
    assert boards['andy_potts']['pm_display'] == 'Ben Ramsey'
    assert boards['andy_potts']['consultant_display'] == 'Andy Potts'
    assert boards['andy_potts']['board_label'] == 'Andy Potts / Ben Ramsey'
    assert boards['rachel_farler']['pm_display'] == ''
    assert boards['rachel_farler']['board_label'] == 'Rachel'


def test_derek_kidney_is_gone_from_the_live_roster_source():
    """The pipeline _USERS mirror can drift from app.py. This reads the
    source: a USERS / TEAM_DATES entry is `'derek_kidney': {`. Comments and
    the init_db DELETE name the key without that shape, so they still pass.
    """
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    body = open(os.path.join(root, 'app.py')).read()
    assert "'derek_kidney': {" not in body
    assert "derek_kidney" in body, 'the cleanup DELETE should still name him'
    assert "DELETE FROM hub_users WHERE user_key IN ('admin', 'derek_kidney')" in body


def test_retired_derek_kidney_has_no_boards():
    """Derek Kidney was removed from USERS 2026-08-28.

    Same shape as the retired shared-admin test: absence from the roster is
    what revokes him. Re-adding 'derek_kidney' to _USERS (or to app.USERS)
    makes this fail, and that failure is the point.
    """
    assert 'derek_kidney' not in _USERS
    assert pb.get_pair_key(_USERS, 'derek_kidney') is None
    assert pb.list_accessible_boards(_USERS, 'derek_kidney') == []
    for ck in pb.BOARD_CONSULTANTS:
        assert pb.can_access_board(_USERS, 'derek_kidney', ck) is False, ck


def test_unpaired_board_is_just_first_name():
    """Rachel has no PM after Derek left. The board is hers, labelled Rachel.

    Do not fall back to 'Just Rachel', 'PM', or a leftover user_key — those
    would show in the header and the dashboard cards.
    """
    assert 'rachel_farler' not in pb.PRIMARY_PM_FOR_CONSULTANT
    assert pb.board_label(_USERS, 'rachel_farler') == 'Rachel'
    assert pb.board_label(_USERS, 'andy_potts') == 'Andy Potts / Ben Ramsey'


# --- Client contact last-used (Rachel 2026-08: client's manager, not PPS PM)

def test_last_used_client_contact_prefers_newest_same_property():
    entries = [
        {'id': 1, 'property_name': 'Macaulay', 'client_contact': 'Old Mgr',
         'updated_at': '2026-01-01T00:00:00'},
        {'id': 2, 'property_name': 'Macaulay', 'client_contact': 'New Mgr',
         'updated_at': '2026-08-01T00:00:00'},
        {'id': 3, 'property_name': 'Drexel', 'client_contact': 'Someone Else',
         'updated_at': '2026-08-20T00:00:00'},
    ]
    assert pb.last_used_client_contact(entries, 'macaulay') == 'New Mgr'
    assert pb.last_used_client_contact(entries, '  Macaulay  ') == 'New Mgr'


def test_last_used_client_contact_skips_empty_and_the_row_being_edited():
    entries = [
        {'id': 1, 'property_name': 'Macaulay', 'client_contact': 'Keep',
         'updated_at': '2026-01-01T00:00:00'},
        {'id': 2, 'property_name': 'Macaulay', 'client_contact': '   ',
         'updated_at': '2026-08-01T00:00:00'},
        {'id': 3, 'property_name': 'Macaulay', 'client_contact': 'Self',
         'updated_at': '2026-08-20T00:00:00'},
    ]
    assert pb.last_used_client_contact(entries, 'Macaulay', exclude_id=3) == 'Keep'
    assert pb.last_used_client_contact(entries, '') == ''
    assert pb.last_used_client_contact([], 'Macaulay') == ''


def test_last_used_client_contact_is_the_client_not_a_pps_pm():
    # Guard: this helper only reads client_contact. A PPS PM name on the
    # board title must not leak in just because the board used to be Rachel/Derek.
    entries = [
        {'id': 1, 'property_name': 'Sugar Glenn', 'client_contact': 'Lisa',
         'updated_at': '2026-08-01T00:00:00'},
    ]
    assert pb.last_used_client_contact(entries, 'Sugar Glenn') == 'Lisa'
    assert 'Derek' not in pb.last_used_client_contact(entries, 'Sugar Glenn')


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


# --- Bulk import gating (2026-08-23) ----------------------------------------

def test_importing_is_leadership_but_editing_stays_open_to_everyone():
    """The board is a shared sheet — that is the point, and it is why editing
    and archiving stay open to the whole roster. Import is different in kind:
    it rewrites a board wholesale rather than moving one row, and its remaining
    purpose is seeding a board when one is created.

    Thomas, 2026-08-23: "a one time feature that was needed to kick off the
    pipeline board... they shouldn't need to do it again."
    """
    for key in ('james_boling', 'andy_potts', 'ben_ramsey', 'rachel_farler'):
        assert pb.can_access_board(_USERS, key, 'andy_potts') is True, key
        assert pb.can_import_to_board(_USERS, key, 'andy_potts') is False, key


def test_leadership_and_owner_can_still_seed_any_board():
    """A new consultant arrives with a spreadsheet — that need does not go
    away, so the control is narrowed rather than deleted."""
    for key in ('thomas_ellison', 'tony_cumella', 'trey_hollmeyer',
                'stephanie_whetstone'):
        assert pb.can_import_to_board(_USERS, key, 'andy_potts') is True, key


def test_import_still_fails_closed_on_a_board_that_does_not_exist():
    """Tier is checked in addition to board access, never instead of it —
    otherwise leadership would bypass the pair_key validation entirely."""
    assert pb.can_import_to_board(_USERS, 'thomas_ellison', 'not_a_board') is False
    assert pb.can_import_to_board(_USERS, 'tony_cumella', '') is False


def test_a_stale_key_off_the_roster_cannot_import_even_at_leadership():
    """Removal from USERS has to revoke everything, including this."""
    assert pb.can_import_to_board(_USERS, 'admin', 'andy_potts') is False
    assert pb.can_import_to_board(_USERS, '', 'andy_potts') is False
    assert pb.can_import_to_board({}, 'tony_cumella', 'andy_potts') is False
