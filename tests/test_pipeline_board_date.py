"""The Date column on the Pipeline Board (2026-11-23).

Run: python -m pytest tests/test_pipeline_board_date.py -v

Thomas asked for a date column, second on the board, because the proposal
number stays the first thing people read. It is `proposal_date`, a plain
DATE people can change; new rows start on today's Eastern date.
"""
import os
import re
import sys
from datetime import date, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pipeline_board as pb
from test_pipeline_board_history import _db, T0  # noqa: E402


def test_clean_date_accepts_the_date_input_value_and_blanks_junk():
    assert pb._clean_date('2026-11-23') == date(2026, 11, 23)
    assert pb._clean_date(datetime(2026, 11, 23, 9, 30)) == date(2026, 11, 23)
    assert pb._clean_date('') is None
    assert pb._clean_date(None) is None
    assert pb._clean_date('next week') is None
    assert pb._clean_date('2026-02-30') is None


def test_new_row_starts_on_todays_eastern_date():
    store, get_db = _db()
    row = pb.create_entry(get_db, 'rachel_farler', 'rachel_farler')
    assert row['proposal_date'] == pb._today_eastern().isoformat()


def test_date_is_editable_and_clearable():
    store, get_db = _db()
    row = pb.create_entry(get_db, 'rachel_farler', 'rachel_farler')
    updated, err = pb.update_entry(
        get_db, row['id'], 'rachel_farler', 'rachel_farler', {'proposal_date': '2026-10-01'})
    assert err is None
    assert store.entries[row['id']]['proposal_date'] == date(2026, 10, 1)
    pb.update_entry(get_db, row['id'], 'rachel_farler', 'rachel_farler', {'proposal_date': ''})
    assert store.entries[row['id']]['proposal_date'] is None


def test_row_to_dict_sends_the_date_as_iso_text():
    """Snapshots json.dumps these rows; a raw date object would break backups."""
    d = pb._row_to_dict({'id': 1, 'proposal_date': date(2026, 11, 23),
                         'amount': None, 'sub_pay': None})
    assert d['proposal_date'] == '2026-11-23'


def test_restoring_a_backup_from_before_the_column_keeps_todays_dates():
    store, get_db = _db()
    entry = store.add_entry('rachel_farler', 'draft', T0)
    entry['proposal_date'] = date(2026, 11, 2)
    store.backups.append({
        'id': 1, 'pair_key': 'rachel_farler', 'reason': 'manual',
        'created_by': 'thomas_ellison', 'created_at': T0, 'entry_count': 1,
        'payload': [
            {'id': entry['id'], 'status': 'draft', 'archived': False,
             'proposal_number': None, 'property_name': 'Old', 'address': None,
             'project': None, 'amount': None, 'sub_pay': None, 'trade_partner': None,
             'client_contact': None, 'notes': None, 'row_order': 1},
        ],
    })
    _, err = pb.restore_from_backup(get_db, 'rachel_farler', 1, 'thomas_ellison')
    assert err is None
    assert store.entries[entry['id']]['proposal_date'] == date(2026, 11, 2)


def test_import_reads_a_date_column():
    assert pb._HEADER_ALIASES['date'] == 'proposal_date'
    assert pb._HEADER_ALIASES['proposal date'] == 'proposal_date'


def test_backfill_only_runs_when_the_column_is_new_and_skips_imports():
    class Cur:
        def __init__(self, exists):
            self.exists, self.sql = exists, []

        def execute(self, sql, params=None):
            self.sql.append(' '.join(sql.split()))

        def fetchone(self):
            return (1,) if self.exists else None

    already = Cur(exists=True)
    pb._ensure_proposal_date_column(already)
    assert not any('UPDATE' in s or 'ALTER' in s for s in already.sql)

    fresh = Cur(exists=False)
    pb._ensure_proposal_date_column(fresh)
    joined = '\n'.join(fresh.sql)
    assert 'ADD COLUMN proposal_date DATE' in joined
    backfill = next(s for s in fresh.sql if s.startswith('UPDATE pipeline_board_entries'))
    assert "America/New_York" in backfill
    assert "event = 'imported'" in backfill


def test_date_is_the_second_column_on_the_page():
    html = open(os.path.join(ROOT, 'templates', 'pipeline_board.html')).read()
    cols = re.findall(r'<col data-col="([a-z_]+)"', html)
    heads = re.findall(r'<th data-col="([a-z_]+)"', html)
    assert cols[:2] == ['proposal_number', 'proposal_date']
    assert heads[:2] == ['proposal_number', 'proposal_date']
    cells = re.findall(r"tr\.appendChild\(cell\('([a-z_]+)'", html)
    assert cells[:2] == ['proposal_number', 'proposal_date']
    assert 'data-field="proposal_date" type="date"' in html
    # Empty-state rows span every column.
    assert all(n == str(len(cols)) for n in re.findall(r'colspan="(\d+)"', html))
