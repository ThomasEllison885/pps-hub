"""The nightly digest, once fifteen more pages started logging opens.

Run: python -m pytest tests/test_daily_digest_opens.py -v

F-03 (2026-08-26) instrumented the pages that keep no log of their own, so
`hub_usage_events` went from three features to twenty. The digest reads that
table automatically, which is the point of the design — and also the risk:
a line per page opened would have turned a readable email into a scroll.
The digest has exactly one recipient, and making it tiring is how it stops
being read.

So opens roll into one line per person, and — the part worth pinning —
**they are not activity**. The headline count, AT A GLANCE, and QUIET TODAY
all still mean work produced. Someone who only looked at the Hub is still
listed as quiet, with a line above saying they at least looked.
"""
import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import daily_digest as dd

USERS = {
    'andy_potts': {'display': 'Andy Potts', 'role': 'consultant'},
    'ben_cole': {'display': 'Ben Cole', 'role': 'pm'},
    'phil_miller': {'display': 'Phil Miller', 'role': 'pm'},
    'thomas_ellison': {'display': 'Thomas Ellison', 'role': 'admin'},
}
AT = datetime(2026, 8, 26, 14, 30)


def _did(user_key, name, kind='proposal', label='Proposal', title='Cedar Ridge'):
    return dd._item(user_key, name, kind, label, title, '', AT)


def _seen(user_key, name, pages):
    return dd._item(user_key, name, dd.SEEN_KIND, 'Looked at', ', '.join(pages),
                    '', AT, f'{len(pages)} pages')


def _email(items, counts=None):
    return dd.build_digest_email(
        date(2026, 8, 26), items, counts or {}, USERS, {'thomas_ellison'})


def test_opens_do_not_count_as_activity():
    """Andy generated one proposal and looked at four pages. That is one
    activity, not five."""
    subject, text, html = _email([
        _did('andy_potts', 'Andy Potts'),
        _seen('andy_potts', 'Andy Potts', ['Clients', 'Team View',
                                           'Proposal History', 'Ask PPS']),
    ])
    assert '(1 activity)' in subject
    assert '1 items from 1 people' in text


def test_a_person_who_only_looked_is_still_quiet():
    """QUIET TODAY has always meant "produced nothing". Opening a page must
    not rescue you from it — the "Looked at" line is what says you were
    here."""
    _, text, _ = _email([
        _did('andy_potts', 'Andy Potts'),
        _seen('ben_cole', 'Ben Cole', ['Pipeline', 'Clients']),
    ])
    quiet = text.split('QUIET TODAY')[1].split('\n')[1]
    assert 'Ben Cole' in quiet, 'looked but produced nothing — still quiet'
    assert 'Phil Miller' in quiet, 'did not appear at all'
    assert 'Andy Potts' not in quiet
    assert 'Looked at: Pipeline, Clients' in text, 'but his looking is visible'


def test_the_per_person_count_excludes_opens():
    _, text, _ = _email([
        _did('andy_potts', 'Andy Potts'),
        _did('andy_potts', 'Andy Potts', title='Maple Court'),
        _seen('andy_potts', 'Andy Potts', ['Clients', 'Team View']),
    ])
    assert 'Andy Potts (2)' in text


def test_at_a_glance_does_not_gain_a_seen_row():
    """The totals block lists work produced. `seen` would otherwise appear
    there automatically, because unknown kinds are passed through."""
    _, text, _ = _email(
        [_seen('andy_potts', 'Andy Potts', ['Clients'])],
        counts={'proposal': 2, dd.SEEN_KIND: 7},
    )
    glance = text.split('AT A GLANCE')[1].split('BY PERSON')[0]
    assert 'Proposals: 2' in glance
    assert 'Seen' not in glance and '7' not in glance


def test_the_looked_at_line_sorts_last_for_a_person():
    """It is context, not the headline. Read the work first."""
    _, text, _ = _email([
        _seen('andy_potts', 'Andy Potts', ['Clients']),
        _did('andy_potts', 'Andy Potts'),
    ])
    block = text.split('Andy Potts (1)')[1]
    assert block.index('Proposal') < block.index('Looked at')


def test_a_day_of_only_opens_reads_as_no_activity():
    """Everyone browsed, nobody produced. The email should say so plainly
    rather than claiming a busy day."""
    subject, text, _ = _email([
        _seen('andy_potts', 'Andy Potts', ['Clients']),
        _seen('ben_cole', 'Ben Cole', ['Pipeline']),
    ])
    assert 'no team activity' in subject
    assert 'No team activity recorded yesterday' in text
    assert 'Looked at: Clients' in text, 'still visible, just not counted'


def test_html_body_matches_the_text_body(_=None):
    _, text, html = _email([
        _did('andy_potts', 'Andy Potts'),
        _seen('andy_potts', 'Andy Potts', ['Clients', 'Team View']),
    ])
    assert 'Andy Potts' in html
    assert 'Looked at' in html
    assert '(1)' in html, 'per-person count excludes the opens line'


def test_seen_kind_is_what_the_collector_writes():
    """One constant, used by the collector and three places in the renderer.
    A literal 'seen' anywhere would drift."""
    import re

    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'daily_digest.py'), encoding='utf-8').read()
    assert "SEEN_KIND = 'seen'" in src
    body = src.split('def build_digest_email')[1]
    assert not re.search(r"kind'\]\s*[=!]=\s*'seen'", body), \
        "compare against SEEN_KIND, not a literal"


# ── the rollup itself ───────────────────────────────────────────────────────
#
# Everything above builds items by hand, which left the function that
# actually does the rolling up untested — a mutation that listed every open
# as its own line passed the whole suite. These drive the collector.

class FakeCur:
    """Returns one canned result set for the usage-events query."""

    def __init__(self, rows):
        self.rows = rows

    def execute(self, sql, params=None):
        pass

    def fetchall(self):
        return self.rows


def _collect(rows, exclude=()):
    got = []
    dd._collect_usage_events(FakeCur(rows), USERS, sorted(exclude),
                             datetime(2026, 8, 26), datetime(2026, 8, 27),
                             got.append)
    return got


# (user_key, feature, action, title, count, last_at, meta)
def _row(user, feature, action, title='', n=1, at=AT, meta=''):
    return (user, feature, action, title, n, at, meta)


def test_many_opens_become_one_line_per_person():
    """The whole reason this exists: fifteen instrumented pages must not mean
    fifteen lines under someone's name."""
    items = _collect([
        _row('andy_potts', 'clients', 'open'),
        _row('andy_potts', 'team_view', 'open'),
        _row('andy_potts', 'proposal_history', 'open'),
        _row('andy_potts', 'ask_pps', 'open'),
    ])
    assert len(items) == 1
    assert items[0]['kind'] == dd.SEEN_KIND
    assert items[0]['title'] == 'Ask PPS, Clients, Proposal History, Team View'
    assert items[0]['extra'] == '4 pages'


def test_one_page_reads_as_one_page():
    items = _collect([_row('andy_potts', 'clients', 'open')])
    assert items[0]['extra'] == '1 page'


def test_opens_are_rolled_up_per_person_not_globally():
    items = _collect([
        _row('andy_potts', 'clients', 'open'),
        _row('ben_cole', 'pipeline', 'open', 'Andy Potts'),
    ])
    assert len(items) == 2
    assert {i['user_key'] for i in items} == {'andy_potts', 'ben_cole'}


def test_the_same_page_opened_on_two_boards_is_named_once():
    """Pipeline opens carry the board name as the title, so one person gets
    several rows for the same feature. The rolled-up line names the feature,
    not each title, or it is a list of boards again."""
    items = _collect([
        _row('ben_cole', 'pipeline', 'open', 'Andy Potts'),
        _row('ben_cole', 'pipeline', 'open', 'Rachel Farler'),
    ])
    assert len(items) == 1
    assert items[0]['title'] == 'Pipeline'


def test_real_actions_still_get_their_own_line():
    """Imports, generates and uploads are work. Only opens roll up."""
    items = _collect([
        _row('andy_potts', 'clients', 'open'),
        _row('andy_potts', 'office_ops', 'generate', 'Thursday pack'),
        _row('andy_potts', 'pipeline', 'import', "Andy's board"),
    ])
    kinds = sorted(i['kind'] for i in items)
    assert kinds == ['office_ops', 'pipeline', dd.SEEN_KIND]
    assert len(items) == 3


def test_an_unlabelled_feature_still_reads_sensibly():
    """A feature nobody added to FEATURE_LABELS is a bug the tests catch, but
    it must not render as a raw slug in Thomas's inbox meanwhile."""
    items = _collect([_row('andy_potts', 'brand_new_thing', 'open')])
    assert items[0]['title'] == 'Brand New Thing'


def test_the_rolled_up_line_carries_the_latest_timestamp():
    later = datetime(2026, 8, 26, 17, 5)
    items = _collect([
        _row('andy_potts', 'clients', 'open', at=AT),
        _row('andy_potts', 'team_view', 'open', at=later),
    ])
    assert items[0]['at'] == later


def test_a_broken_query_does_not_take_the_digest_down():
    class Boom:
        def execute(self, sql, params=None):
            raise RuntimeError('table gone')

        def fetchall(self):
            return []

    got = []
    dd._collect_usage_events(Boom(), USERS, [], datetime(2026, 8, 26),
                             datetime(2026, 8, 27), got.append)
    assert got == []
