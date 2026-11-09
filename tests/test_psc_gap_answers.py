"""Thomas's answers to the PSC training gaps, and the prompts they retire.

Thomas, 2026-11-09, answered `[TO DOCUMENT]` SOP bullets in his own words
ahead of Harrison Hollon's start. Afterwards:

1. The gaps still open sit where the test expects. An Ask PPS prompt minted
   from a gap is keyed `psc:<module>:<index>`; if this fails after an edit,
   put new lines below the last gap instead of updating the expected set.
2. Prompts for answered bullets are dismissed, so the team stops being asked
   what the training already says.
3. A prompt whose gap merely MOVED is re-pointed, not dismissed. The rows in
   the last tests are the real production rows from 2026-11-09.
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


def test_remaining_gaps_have_not_moved():
    assert ask_pps.live_psc_gap_refs() == STILL_OPEN


class _Cur:
    def __init__(self, rows):
        self.rows = rows
        self.dismissed = None
        self.moved = []

    def execute(self, sql, params=None):
        if 'SET source_ref' in sql:
            self.moved.append(params)
        elif sql.lstrip().upper().startswith('UPDATE'):
            self.dismissed = list(params[0])

    def fetchall(self):
        return self.rows


# Open psc: prompts in production on 2026-11-09 (id, source_ref, question).
LIVE_ROWS = [
    (5, 'psc:ops_monday:4', 'How do we name properties, contacts, and deals in Monday?'),
    (16, 'psc:ops_trade_partners:0', 'How do we find and recruit new Trade Partners?'),
    (17, 'psc:ops_trade_partners:1', 'What must a Trade Partner have before we use them (insurance, quality, etc.)?'),
    (37, 'psc:ops_partner_projects:4', 'When is a new PSC ready for solo client work?'),
    (38, 'psc:ops_lifecycle:6', 'At close-out, how do callbacks and warranty hand off?'),
    (39, 'psc:ops_project_evaluation:5', 'PSC Training gap — Project Evaluation & Scope Development: '
         'Standard site-visit checklist by trade? (Document for onboarding; field reality may differ.)'),
    (40, 'psc:ops_estimating:6', 'Where do we look up typical unit costs by trade?'),
    (41, 'psc:ops_decision_ownership:5', 'PSC Training gap — Decision-Making & Who Owns What: '
         'After-hours and urgent site escalation path?'),
    (42, 'psc:ops_trade_partners:6', 'Preferred Trade Partners by trade — who and specialty?'),
    (43, 'psc:ops_client_comms:5', 'Sample client update for one phase (award, delay, or close-out)?'),
    (44, 'psc:ops_callbacks:3', 'Callback from first call to closed — what are the steps?'),
    (68, 'psc:ops_lifecycle:7', 'At close-out, how do callbacks and warranty hand off?'),
    (69, 'psc:ops_trade_partners:11', 'Preferred Trade Partners by trade — who and specialty?'),
]


def test_a_moved_gap_keeps_its_answered_prompt():
    cur = _Cur(LIVE_ROWS)
    ask_pps.retire_documented_psc_prompts(cur)
    # "Sample client update" was answered twice at :5; it is at :6 now.
    assert cur.moved == [('psc:ops_client_comms:6', 43)]


def test_answered_and_duplicate_prompts_are_dismissed():
    cur = _Cur(LIVE_ROWS)
    n = ask_pps.retire_documented_psc_prompts(cur)
    # 42 duplicates 69, which already holds the live position.
    assert cur.dismissed == [5, 17, 37, 38, 40, 41, 42, 68]
    assert n == 8


def test_prompts_on_live_gaps_are_left_alone():
    cur = _Cur([r for r in LIVE_ROWS if r[1] in STILL_OPEN])
    assert ask_pps.retire_documented_psc_prompts(cur) == 0
    assert cur.dismissed is None and cur.moved == []


def test_dict_rows_work_too():
    cur = _Cur([{'id': 7, 'source_ref': 'psc:ops_monday:4', 'question': 'x'}])
    assert ask_pps.retire_documented_psc_prompts(cur) == 1
    assert cur.dismissed == [7]


def test_empty_curriculum_never_reads_as_everything_answered(monkeypatch):
    monkeypatch.setattr(ask_pps, '_live_psc_gap_topics', lambda: {})
    cur = _Cur([(1, 'psc:ops_monday:4', 'x')])
    assert ask_pps.retire_documented_psc_prompts(cur) == 0
    assert cur.dismissed is None
