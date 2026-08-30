"""Merged Admin activity feed.

Run: python -m pytest tests/test_admin_feed.py -v
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from admin_feed import merge_activity


def _p(id, when, **kw):
    row = {'id': id, 'generated_at': when, 'generated_by': 'trey_hollmeyer',
           'property_name': f'Prop {id}', 'consultant_name': 'Andy Potts',
           'document_id': None}
    row.update(kw)
    return row


def _ppm(id, when, **kw):
    row = {'id': id, 'generated_at': when, 'generated_by': 'ben_ramsey',
           'client_name': f'Client {id}', 'pm_name': 'Phil Miller', 'proj_type': 'Roof'}
    row.update(kw)
    return row


def _tps(id, when, **kw):
    row = {'id': id, 'generated_at': when, 'generated_by': 'nick_triplett',
           'property_name': f'Site {id}', 'consultant_name': 'Tony Cumella',
           'language': 'spanish', 'po_number': None}
    row.update(kw)
    return row


# --- Ordering ---------------------------------------------------------------

def test_the_three_logs_interleave_by_time():
    """The whole point. Three lists side by side made 'what happened Tuesday'
    a manual merge."""
    feed = merge_activity(
        [_p(1, datetime(2026, 8, 20, 9))],
        [_ppm(2, datetime(2026, 8, 21, 15))],
        [_tps(3, datetime(2026, 8, 21, 8))],
    )
    assert [i['kind'] for i in feed] == ['ppm', 'tps', 'proposal']


def test_untimed_rows_sort_last_rather_than_first():
    """generated_at is nullable in all three tables, so this is reachable. A row
    with no timestamp is the least informative thing on the page; floating it to
    the top would push out real activity."""
    feed = merge_activity(
        [_p(1, None), _p(2, datetime(2026, 8, 21, 9))],
        [_ppm(3, None)],
        [],
    )
    assert feed[0]['id'] == 2, 'the only timed row leads'
    assert {i['id'] for i in feed[1:]} == {1, 3}


def test_a_mix_of_timed_and_untimed_rows_does_not_raise():
    """Sorting None against datetime is a TypeError, and this runs inside the
    Admin route — an exception here is a 500 on the page, not a missing row."""
    merge_activity([_p(1, None)], [_ppm(2, datetime(2026, 8, 21))], [])


def test_limit_applies_after_the_merge_not_per_source():
    """Slicing each log to N first would let a quiet week of proposals hold
    slots that a busy week of PPMs should have taken."""
    ppms = [_ppm(i, datetime(2026, 8, 21, 0, i)) for i in range(1, 21)]
    feed = merge_activity([_p(99, datetime(2026, 8, 1))], ppms, [], limit=5)
    assert len(feed) == 5
    assert all(i['kind'] == 'ppm' for i in feed), 'the older proposal should be cut'


# --- Attribution ------------------------------------------------------------

def test_credit_reads_generated_by_and_the_book_is_context_only():
    """2026-08-21 (Thomas): a PM writing a proposal under a consultant's name
    gets the credit; the consultant is still shown, as context."""
    feed = merge_activity([_p(1, datetime(2026, 8, 21))], [], [])
    assert feed[0]['who'] == 'Trey Hollmeyer'
    assert feed[0]['user_key'] == 'trey_hollmeyer'
    assert feed[0]['context'] == 'Andy Potts'


def test_missing_names_degrade_to_a_dash_not_an_exception():
    feed = merge_activity([_p(1, datetime(2026, 8, 21), generated_by=None,
                              property_name=None, client_name=None)], [], [])
    assert feed[0]['who'] == '—'
    assert feed[0]['title'] == 'Unnamed'


# --- Row shape --------------------------------------------------------------

def test_tps_extra_line_joins_only_the_parts_that_exist():
    with_po = merge_activity([], [], [_tps(1, datetime(2026, 8, 21), po_number='4471')])
    assert with_po[0]['extra'] == 'Spanish · PO 4471'
    no_po = merge_activity([], [], [_tps(2, datetime(2026, 8, 21), language=None)])
    assert no_po[0]['extra'] == ''


def test_only_proposals_carry_a_document_to_download():
    feed = merge_activity(
        [_p(1, datetime(2026, 8, 21), document_id=77)],
        [_ppm(2, datetime(2026, 8, 20))],
        [_tps(3, datetime(2026, 8, 19))],
    )
    by_kind = {i['kind']: i for i in feed}
    assert by_kind['proposal']['document_id'] == 77
    assert by_kind['ppm']['document_id'] is None
    assert by_kind['tps']['document_id'] is None


def test_empty_and_none_inputs_are_both_fine():
    assert merge_activity([], [], []) == []
    assert merge_activity(None, None, None) == []


# --- Attribution ------------------------------------------------------------
#
# The fourth read site of the alias bug (093244f, 6adb7e8, d6cc921, 44a33db).
# All three tables merged here carry `generated_by`, which is the short
# consultant key on anything logged before 093244f or through a bookmarked
# proposal tool — and `_pretty_key` used to `.title()` it straight onto the
# page, so `'rachel'` became a perfectly convincing "Rachel" sitting next to
# "Rachel Farler". Nothing was dropped and nothing looked broken, which is
# exactly why this survived three earlier passes at the same bug.

def test_a_short_consultant_key_shows_the_persons_real_name():
    feed = merge_activity([_p(1, datetime(2026, 8, 21), generated_by='rachel')],
                          [], [])
    assert feed[0]['who'] == 'Rachel Farler', 'the feed grew a second Rachel'
    assert feed[0]['user_key'] == 'rachel_farler'


def test_the_two_spellings_are_one_person_to_anything_filtering_the_feed():
    """`user_key` is what the Admin page filters and links on, so it has to
    agree with the name shown beside it."""
    feed = merge_activity(
        [_p(1, datetime(2026, 8, 21), generated_by='rachel'),
         _p(2, datetime(2026, 8, 20), generated_by='rachel_farler')], [], [])
    assert {i['user_key'] for i in feed} == {'rachel_farler'}


def test_every_log_resolves_not_just_proposals():
    feed = merge_activity([_p(1, datetime(2026, 8, 21), generated_by='rachel')],
                          [_ppm(2, datetime(2026, 8, 20), generated_by='tony')],
                          [_tps(3, datetime(2026, 8, 19), generated_by='adam')])
    assert [i['who'] for i in feed] == ['Rachel Farler', 'Tony Cumella', 'Adam Cupito']


def test_a_key_belonging_to_nobody_is_still_prettified():
    """The fallback stays — a departed employee's rows keep arriving and
    "Derek Kidney" reads better than a bare key. The change is that it now
    only fires when there really is nobody behind the key."""
    feed = merge_activity([_p(1, datetime(2026, 8, 21),
                              generated_by='derek_kidney')], [], [])
    assert feed[0]['who'] == 'Derek Kidney'
    assert feed[0]['user_key'] == 'derek_kidney'


def test_a_missing_author_still_renders_the_dash():
    feed = merge_activity([_p(1, datetime(2026, 8, 21), generated_by=None)], [], [])
    assert feed[0]['who'] == '—', 'resolve() must not break the empty case'
