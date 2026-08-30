"""The dashboard summary strip and Jump back in.

Run: python -m pytest tests/test_dashboard_summary.py -v

The rule most of these guard is "nothing renders at zero" — a dashboard that
greets thirteen people with a 0 is worse than one that greets them with
nothing. The other half guard the two places where a plausible-looking
implementation would be wrong: ranking recent tools by count instead of
recency (the source lists are LIMIT 5, so counts are bounded and lie), and
treating a failed database read as an empty week.
"""
import os
import sys
from datetime import date, datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dashboard_summary as ds
import weekly_recap


# ── build_pills ─────────────────────────────────────────────────────────────

def _keys(pills):
    return [p['key'] for p in pills]


def test_empty_person_gets_an_empty_strip():
    """A new hire on a quiet Monday. No pills at all is the correct output."""
    assert ds.build_pills() == []


def test_zero_week_score_produces_no_week_pill():
    assert _keys(ds.build_pills(week_score=0)) == []


def test_zero_pipeline_produces_no_pipeline_pill():
    assert _keys(ds.build_pills(pipeline_open=0)) == []


def test_none_pipeline_is_not_confused_with_zero():
    """A failed count and an empty board both render nothing, but only
    because both are dropped — not because None was coerced to 0 somewhere."""
    assert _keys(ds.build_pills(pipeline_open=None)) == []


def test_a_normal_consultant_week():
    pills = ds.build_pills(week_score=7, pipeline_open=4,
                           pipeline_url='/pipeline-board?pair=andy_potts')
    assert _keys(pills) == ['week', 'pipeline']
    assert pills[0]['value'] == '7'
    assert pills[0]['url'] == '/team-view'
    assert pills[1]['value'] == '4'
    assert pills[1]['url'] == '/pipeline-board?pair=andy_potts'


def test_finished_training_stops_nagging():
    """100% drops off. The pill exists to close a loop, not to congratulate."""
    assert _keys(ds.build_pills(psc_pct=100)) == []
    assert _keys(ds.build_pills(psc_pct=99)) == ['psc']


def test_unstarted_training_stays_quiet():
    assert _keys(ds.build_pills(psc_pct=0)) == []


def test_both_training_pills_can_appear():
    pills = ds.build_pills(psc_pct=40, pm_pct=10)
    assert _keys(pills) == ['psc', 'pm']
    assert pills[0]['value'] == '40%'


def test_owner_inbox_pills_are_owner_only():
    """Everyone's dashboard reads unread_feedback from the same context; the
    gate has to be here, not on the caller remembering to pass 0."""
    assert _keys(ds.build_pills(unread_feedback=3, unread_diffs=2,
                                is_owner=False)) == []
    assert _keys(ds.build_pills(unread_feedback=3, unread_diffs=2,
                                is_owner=True)) == ['feedback', 'diffs']


def test_show_week_false_hides_only_the_week_pill():
    """The one switch that is a call about people rather than data. Turning
    it off must not take the rest of the strip with it."""
    pills = ds.build_pills(week_score=9, pipeline_open=3, show_week=False)
    assert _keys(pills) == ['pipeline']


def test_full_strip_is_not_silently_truncated():
    """Five real numbers render as five pills. Capping the list to protect a
    single line would hide a number the strip exists to show."""
    pills = ds.build_pills(week_score=12, pipeline_open=6, psc_pct=50,
                           pm_pct=25, unread_feedback=1, unread_diffs=1,
                           is_owner=True)
    assert _keys(pills) == ['week', 'pipeline', 'psc', 'pm',
                            'feedback', 'diffs']


# ── recent_tools ────────────────────────────────────────────────────────────

def _rows(*stamps):
    return [{'generated_at': s} for s in stamps]


NOW = datetime(2026, 8, 21, 14, 0)


def test_ranks_by_recency_not_count():
    """The dashboard route fetches these lists with LIMIT 5 per kind, so a
    count taken from them is capped at 5 and cannot see the twenty proposals
    behind it. Five estimates from last month must not outrank one proposal
    from this morning."""
    sources = {
        'estimate': _rows(*[NOW - timedelta(days=30 + i) for i in range(5)]),
        'proposal': _rows(NOW - timedelta(hours=2)),
    }
    tools = ds.recent_tools(sources, limit=3)
    assert [t['key'] for t in tools] == ['proposal', 'estimate']


def test_limit_is_respected():
    sources = {
        'proposal': _rows(NOW - timedelta(days=1)),
        'ppm': _rows(NOW - timedelta(days=2)),
        'tps': _rows(NOW - timedelta(days=3)),
        'estimate': _rows(NOW - timedelta(days=4)),
    }
    assert len(ds.recent_tools(sources, limit=3)) == 3


def test_rows_without_a_timestamp_are_ignored_not_ranked_first():
    sources = {'proposal': [{'generated_at': None}],
               'ppm': _rows(NOW - timedelta(days=5))}
    assert [t['key'] for t in ds.recent_tools(sources)] == ['ppm']


def test_usage_events_bring_in_tools_that_keep_no_log():
    """Pipeline, Office Ops and Compliance write only hub_usage_events. If
    this path breaks, the three tools with the heaviest daily use are exactly
    the ones that never appear."""
    tools = ds.recent_tools(
        {'proposal': _rows(NOW - timedelta(days=4))},
        usage_rows=[('pipeline', NOW - timedelta(hours=1)),
                    ('office_ops', NOW - timedelta(days=9))],
    )
    assert [t['key'] for t in tools] == ['pipeline', 'proposal', 'office_ops']


def test_unknown_usage_features_are_ignored():
    tools = ds.recent_tools({}, usage_rows=[('something_new', NOW)])
    assert tools == []


def test_history_is_not_permission():
    """Someone who used Office Ops before a tier change must not be handed a
    card straight back into it."""
    sources = {'proposal': _rows(NOW)}
    usage = [('office_ops', NOW)]
    allowed = {'proposal', 'estimate'}
    keys = [t['key'] for t in ds.recent_tools(sources, usage, allowed=allowed)]
    assert keys == ['proposal']


def test_external_tools_carry_the_proposal_tool_url():
    """Proposal, PPM and TPS live in pps-proposal-tool and open through
    openTool(); the template needs both the flag and an absolute URL."""
    tools = ds.recent_tools({'proposal': _rows(NOW)},
                            proposal_url='https://tool.example.com')
    assert tools[0]['external'] is True
    assert tools[0]['url'] == 'https://tool.example.com/proposal'


def test_internal_tools_are_plain_paths():
    tools = ds.recent_tools({'estimate': _rows(NOW)},
                            proposal_url='https://tool.example.com')
    assert tools[0]['external'] is False
    assert tools[0]['url'] == '/estimating'


def test_every_tool_key_has_a_catalog_entry():
    """USAGE_FEATURE_TO_TOOL maps into TOOLS; a typo on either side would
    KeyError on somebody's dashboard rather than in a test."""
    for tool_key in ds.USAGE_FEATURE_TO_TOOL.values():
        assert tool_key in ds.TOOLS
    for key, spec in ds.TOOLS.items():
        assert spec['path'].startswith('/'), key
        assert spec['name'] and spec['icon'], key


def test_relative_day_labels():
    """Every value here is naive UTC, and the label is about Eastern days.

    `now` is 9:00 UTC on the 21st, which is 5am Friday in Ohio.
    """
    now = datetime(2026, 8, 21, 9, 0)
    # 13:00 UTC == 9am ET the same morning.
    assert ds._relative_day(datetime(2026, 8, 21, 13, 0), now) == 'Today'
    # 23:00 UTC on the 20th == 7pm ET on the 20th — yesterday evening.
    assert ds._relative_day(datetime(2026, 8, 20, 23, 0), now) == 'Yesterday'
    assert ds._relative_day(datetime(2026, 8, 18, 8, 0), now) == '3 days ago'
    assert ds._relative_day(datetime(2026, 8, 1, 8, 0), now) == 'Aug 01'
    assert ds._relative_day(None, now) == ''


def test_late_evening_work_is_yesterday_the_next_morning():
    """The bug this replaced (2026-08-29). 01:00 UTC on the 21st is 9pm ET on
    the *20th*, but it shares a UTC date with a 5am Friday, so comparing UTC
    days called it "Today" — for anything between midnight and 8pm UTC, which
    is most of the working day in Ohio."""
    now = datetime(2026, 8, 21, 9, 0)          # 5am ET Friday
    last_night = datetime(2026, 8, 21, 1, 0)   # 9pm ET Thursday
    assert ds._relative_day(last_night, now) == 'Yesterday'


def test_the_label_flips_on_the_eastern_midnight_not_the_utc_one():
    now = datetime(2026, 8, 21, 16, 0)         # noon ET Friday
    # 03:59 UTC == 11:59pm ET Thursday; 04:00 UTC == midnight ET Friday.
    assert ds._relative_day(datetime(2026, 8, 21, 3, 59), now) == 'Yesterday'
    assert ds._relative_day(datetime(2026, 8, 21, 4, 0), now) == 'Today'


def test_relative_day_survives_a_bad_value():
    """One odd row must not take the whole dashboard down."""
    assert ds._relative_day('not a datetime') == ''


# ── week_scores ─────────────────────────────────────────────────────────────

class _FakeRecap:
    """Stands in for weekly_recap so these tests need no database."""

    def __init__(self, raw, bounds=None):
        self.raw = raw
        self.calls = 0
        self._bounds = bounds or (datetime(2026, 8, 17), datetime(2026, 8, 24))

    def current_week_bounds(self, today=None):
        return self._bounds

    def collect_scores(self, get_db, users, start, end):
        self.calls += 1
        if isinstance(self.raw, Exception):
            raise self.raw
        return self.raw

    def score_total(self, breakdown, weeks=1):
        return weekly_recap.score_total(breakdown, weeks=weeks)


@pytest.fixture(autouse=True)
def _clean_cache():
    ds.clear_cache()
    yield
    ds.clear_cache()


def test_week_scores_uses_the_recaps_arithmetic(monkeypatch):
    """Not a reimplementation: the number on the dashboard has to be the
    number in Monday's email, or nobody believes either one."""
    fake = _FakeRecap({'andy_potts': {'proposal': 3, 'pipeline_touch': 40}})
    monkeypatch.setattr(ds, 'weekly_recap', fake)
    scores = ds.week_scores(None, {}, use_cache=False)
    # 3 deliverables + activity capped at ACTIVITY_CAP_PER_WEEK, not 43.
    assert scores == {'andy_potts': 3 + weekly_recap.ACTIVITY_CAP_PER_WEEK}


def test_a_failed_read_is_not_cached(monkeypatch):
    """collect_scores returns {} for both an empty week and a broken
    database. Caching that would blank the strip for five minutes after one
    hiccup, so the empty case must re-query."""
    fake = _FakeRecap({})
    monkeypatch.setattr(ds, 'weekly_recap', fake)
    ds.week_scores(None, {})
    ds.week_scores(None, {})
    assert fake.calls == 2


def test_a_real_result_is_cached(monkeypatch):
    fake = _FakeRecap({'andy_potts': {'proposal': 1}})
    monkeypatch.setattr(ds, 'weekly_recap', fake)
    assert ds.week_scores(None, {}) == {'andy_potts': 1}
    assert ds.week_scores(None, {}) == {'andy_potts': 1}
    assert fake.calls == 1


def test_cache_expires(monkeypatch):
    fake = _FakeRecap({'andy_potts': {'proposal': 1}})
    monkeypatch.setattr(ds, 'weekly_recap', fake)
    clock = [1000.0]
    monkeypatch.setattr(ds, '_now_monotonic', lambda: clock[0])
    ds.week_scores(None, {})
    clock[0] += ds.CACHE_TTL_SECONDS + 1
    ds.week_scores(None, {})
    assert fake.calls == 2


def test_a_new_week_invalidates_the_cache(monkeypatch):
    """Otherwise the first person to load a dashboard on Monday keeps last
    week's number until the worker restarts."""
    fake = _FakeRecap({'andy_potts': {'proposal': 5}})
    monkeypatch.setattr(ds, 'weekly_recap', fake)
    ds.week_scores(None, {})
    fake._bounds = (datetime(2026, 8, 24), datetime(2026, 8, 31))
    fake.raw = {'andy_potts': {'proposal': 1}}
    assert ds.week_scores(None, {}) == {'andy_potts': 1}
    assert fake.calls == 2


def test_an_exception_returns_an_empty_map(monkeypatch):
    fake = _FakeRecap(RuntimeError('db gone'))
    monkeypatch.setattr(ds, 'weekly_recap', fake)
    assert ds.week_scores(None, {}) == {}


# ── current_week_bounds ─────────────────────────────────────────────────────

def test_current_week_starts_on_monday():
    # Friday 2026-08-21 -> week beginning Monday 2026-08-17 ET.
    start, end = weekly_recap.current_week_bounds(today=date(2026, 8, 21))
    last_start, last_end = weekly_recap.last_week_bounds(today=date(2026, 8, 21))
    assert start == last_end, 'this week must begin where last week ended'
    assert end > start


def test_current_week_is_not_last_week():
    """The pill would otherwise sit unchanged for seven days and match
    nothing the person did today."""
    cur = weekly_recap.current_week_bounds(today=date(2026, 8, 21))
    last = weekly_recap.last_week_bounds(today=date(2026, 8, 21))
    assert cur != last


def test_current_week_handles_the_dst_weeks():
    """A week containing a clock change is 167 or 169 hours, so deriving the
    end by adding seven days would land the boundary an hour off — the same
    bug that was fixed in last_week_bounds on 2026-08-21."""
    start, end = weekly_recap.current_week_bounds(today=date(2026, 11, 1))
    assert (end - start) == timedelta(hours=169)
    start, end = weekly_recap.current_week_bounds(today=date(2026, 3, 8))
    assert (end - start) == timedelta(hours=167)


# ── The Pipeline Board's URL ────────────────────────────────────────────────
#
# Reported by Thomas 2026-08-26: the Pipeline Board card in Jump back in did
# nothing. `/pipeline-board` with no ?pair= asks the route to pick your
# default board, and `pipeline_board.get_pair_key` returns None for the owner
# on purpose — he can open every board and has no "his". The route then
# redirects to the dashboard, so the card bounced him back to where he
# already was. Every other tool has a URL that works for everyone; this is
# the one that does not.

BOARDS = [
    {'key': 'andy_potts', 'consultant_display': 'Andy Potts', 'pm_display': 'Ben Cole'},
    {'key': 'adam_cupito', 'consultant_display': 'Adam Cupito', 'pm_display': 'James Reid'},
    {'key': 'rachel_farler', 'consultant_display': 'Rachel Farler', 'pm_display': 'Ben Cole'},
]


def test_the_bug_no_bare_pipeline_url_anywhere():
    """The catalog path is still bare, and that is fine — every caller has to
    override it. This pins that nothing renders the bare path by accident."""
    assert ds.TOOLS['pipeline']['path'] == '/pipeline-board'
    url = ds.pipeline_url_for(None, BOARDS, None)
    assert url and 'pair=' in url, 'a pipeline URL must always carry a board'


def test_it_returns_you_to_the_board_you_were_last_on():
    """The point of the block. Every pipeline open writes a usage row whose
    title is the board's display name, so the board is recoverable."""
    assert ds.pipeline_url_for('Rachel Farler', BOARDS, 'andy_potts') == \
        '/pipeline-board?pair=rachel_farler'


def test_matching_the_board_name_is_case_and_space_insensitive():
    assert ds.pipeline_url_for('  adam cupito ', BOARDS, None) == \
        '/pipeline-board?pair=adam_cupito'


def test_rachel_matches_the_unpaired_board_label():
    boards = [
        {'key': 'andy_potts', 'consultant_display': 'Andy Potts',
         'pm_display': 'Ben Ramsey', 'board_label': 'Andy Potts / Ben Ramsey'},
        {'key': 'rachel_farler', 'consultant_display': 'Rachel Farler',
         'pm_display': '', 'board_label': 'Rachel'},
    ]
    assert ds.pipeline_url_for('Rachel', boards, 'andy_potts') == \
        '/pipeline-board?pair=rachel_farler'


def test_no_history_falls_back_to_your_default_board():
    assert ds.pipeline_url_for(None, BOARDS, 'andy_potts') == \
        '/pipeline-board?pair=andy_potts'


def test_the_owner_has_no_default_and_still_gets_a_working_link():
    """get_pair_key returns None for the owner. Before this fix that produced
    `/pipeline-board`, which redirects him straight back to the dashboard."""
    url = ds.pipeline_url_for(None, BOARDS, None)
    assert url == '/pipeline-board?pair=andy_potts'


def test_an_unrecognised_board_name_degrades_to_the_default():
    """Matching on display name means a rename misses. That should cost you
    the *right* board, not a working link."""
    assert ds.pipeline_url_for('Someone Renamed', BOARDS, 'adam_cupito') == \
        '/pipeline-board?pair=adam_cupito'


def test_no_boards_at_all_means_no_link():
    """The caller then leaves the card out entirely — a card that redirects
    is worse than no card."""
    assert ds.pipeline_url_for('Andy Potts', [], 'andy_potts') is None
    assert ds.pipeline_url_for(None, None, None) is None


def test_url_overrides_replace_the_catalog_url():
    tools = ds.recent_tools(
        {}, usage_rows=[('pipeline', NOW, 'Andy Potts')],
        allowed={'pipeline'},
        url_overrides={'pipeline': '/pipeline-board?pair=andy_potts'},
    )
    assert [t['url'] for t in tools] == ['/pipeline-board?pair=andy_potts']


def test_a_three_column_usage_row_still_ranks_correctly():
    """recent_usage_features grew a title column; recent_tools reads the
    first two and must not trip over the third."""
    tools = ds.recent_tools(
        {'proposal': [{'generated_at': NOW - timedelta(days=2)}]},
        usage_rows=[('pipeline', NOW, 'Andy Potts'),
                    ('office_ops', NOW - timedelta(days=9), 'Numbers page')],
        allowed={'pipeline', 'proposal', 'office_ops'},
    )
    assert [t['key'] for t in tools] == ['pipeline', 'proposal', 'office_ops']


def test_two_column_usage_rows_still_work():
    """The older shape, so nothing that still passes pairs breaks."""
    tools = ds.recent_tools({}, usage_rows=[('pipeline', NOW)],
                            allowed={'pipeline'})
    assert [t['key'] for t in tools] == ['pipeline']
