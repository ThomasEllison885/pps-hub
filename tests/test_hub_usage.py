"""Daily-digest usage helpers — no live Postgres."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import daily_digest as dd
import hub_usage


def test_event_label_known_feature_and_count():
    feat, head, extra = hub_usage.event_label('pipeline', 'open', 'Andy Potts', 4)
    assert feat == 'Pipeline'
    assert head == 'Pipeline · Opened · Andy Potts'
    assert extra == '4×'


def test_event_label_unknown_feature_still_readable():
    feat, head, extra = hub_usage.event_label('site_visit_v2', 'export', '', 1)
    assert feat == 'Site Visit V2'
    assert 'Export' in head
    assert extra == ''


def test_record_usage_no_conn_does_not_raise():
    hub_usage.record_usage(lambda: None, 'andy_potts', 'pipeline', 'open', 'Andy')


def test_kind_totals_includes_pipeline_compliance_and_unknowns():
    lines = dd._kind_totals({
        'proposal': 2,
        'pipeline': 5,
        'compliance': 3,
        'new_gadget': 1,
        'login': 0,
    })
    labels = [label for label, _ in lines]
    assert 'Proposals' in labels
    assert 'Pipeline Board' in labels
    assert 'Compliance' in labels
    assert 'New Gadget' in labels
    assert 'Hub logins' not in labels


def test_board_title():
    users = {'andy_potts': {'display': 'Andy Potts'}}
    assert dd._board_title(users, 'andy_potts') == "Andy Potts's board"
