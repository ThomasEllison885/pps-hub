"""Thomas's answers to the PSC training gaps, and the prompts they retire.

Thomas, 2026-11-09, answered six `[TO DOCUMENT]` SOP bullets in his own words
ahead of Harrison Hollon's start. Two things must hold afterwards:

1. The ten gaps still open sit at the SAME list positions as before. An Ask
   PPS prompt minted from a gap is keyed `psc:<module>:<index>`; move a gap and
   its open prompt starts asking a different question. If this test fails
   after an edit, put the new lines below the last gap instead of updating
   the expected set.
2. Prompts for the answered bullets get dismissed, so the team stops being
   asked what the training already says.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import ask_pps  # noqa: E402

STILL_OPEN = {
    'psc:ops_project_evaluation:5',
    'psc:ops_trade_partners:0',
    'psc:ops_trade_partners:11',
    'psc:ops_client_comms:6',
    'psc:ops_callbacks:3',
    'psc:ops_common_mistakes:0',
    'psc:ops_common_mistakes:1',
    'psc:ops_common_mistakes:2',
    'psc:ops_common_mistakes:3',
    'psc:ops_common_mistakes:4',
    'psc:ops_common_mistakes:5',
}

ANSWERED = [
    'psc:ops_partner_projects:4',
    'psc:ops_monday:4',
    'psc:ops_lifecycle:7',
    'psc:ops_estimating:6',
    'psc:ops_decision_ownership:5',
]


def test_remaining_gaps_have_not_moved():
    assert ask_pps.live_psc_gap_refs() == STILL_OPEN


class _Cur:
    def __init__(self, rows):
        self.rows = rows
        self.updated = None

    def execute(self, sql, params=None):
        if sql.lstrip().upper().startswith('UPDATE'):
            self.updated = list(params[0])

    def fetchall(self):
        return self.rows


def test_answered_gaps_retire_their_prompts_and_open_ones_stay():
    rows = [(i, ref) for i, ref in enumerate(ANSWERED, start=1)]
    rows.append((99, 'psc:ops_common_mistakes:0'))
    cur = _Cur(rows)
    assert ask_pps.retire_documented_psc_prompts(cur) == len(ANSWERED)
    assert cur.updated == [1, 2, 3, 4, 5]


def test_dict_rows_work_too():
    cur = _Cur([{'id': 7, 'source_ref': 'psc:ops_monday:4'}])
    assert ask_pps.retire_documented_psc_prompts(cur) == 1
    assert cur.updated == [7]


def test_nothing_open_to_retire_writes_nothing():
    cur = _Cur([(1, 'psc:ops_callbacks:3')])
    assert ask_pps.retire_documented_psc_prompts(cur) == 0
    assert cur.updated is None


def test_empty_curriculum_never_reads_as_everything_answered(monkeypatch):
    monkeypatch.setattr(ask_pps, 'live_psc_gap_refs', lambda: set())
    cur = _Cur([(1, 'psc:ops_monday:4')])
    assert ask_pps.retire_documented_psc_prompts(cur) == 0
    assert cur.updated is None
