"""Weekly team recap — ranking, grouping, and what counts.

Pure logic plus a fake cursor; no Postgres, no SMTP. Matches this repo's test
convention (see tests/test_pipeline_board.py).

Run: python -m pytest tests/test_weekly_recap.py -v
"""
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import weekly_recap as wr


_USERS = {
    'thomas_ellison': {'display': 'Thomas Ellison', 'role': 'admin',
                       'tier': 'owner', 'email': 'thomas@pps.com'},
    'tony_cumella': {'display': 'Tony Cumella', 'role': 'consultant',
                     'tier': 'leadership', 'email': 'tony@pps.com'},
    'andy_potts': {'display': 'Andy Potts', 'role': 'consultant',
                   'tier': 'team', 'email': 'andy@pps.com'},
    'adam_cupito': {'display': 'Adam Cupito', 'role': 'consultant',
                    'tier': 'team', 'email': 'adam@pps.com'},
    'ben_ramsey': {'display': 'Ben Ramsey', 'role': 'pm',
                   'tier': 'team', 'email': 'ben@pps.com'},
    'phil_miller': {'display': 'Phil Miller', 'role': 'pm',
                    'tier': 'team', 'email': 'phil@pps.com'},
    'stephanie_whetstone': {'display': 'Stephanie Whetstone', 'role': 'office_manager',
                            'tier': 'leadership', 'email': 'steph@pps.com'},
}


# --- Week boundaries --------------------------------------------------------

def test_last_week_bounds_is_the_monday_that_just_ended():
    # Monday 2026-08-24 → the week of Mon 8/17 through Sun 8/23.
    start, end = wr.last_week_bounds(today=date(2026, 8, 24))
    assert start.date() == date(2026, 8, 17)
    assert (end - start).days == 7


def test_last_week_bounds_from_midweek_still_looks_back_a_full_week():
    """A Trigger Run on a Wednesday must not report a half-finished week."""
    start, end = wr.last_week_bounds(today=date(2026, 8, 26))
    assert start.date() == date(2026, 8, 17)
    assert (end - start).days == 7


def test_last_week_bounds_are_eastern_midnight_expressed_as_naive_utc():
    """Naive, because every timestamp column in the Hub is naive UTC — an aware
    datetime raises the moment it's compared against one. Eastern midnight in
    August (EDT, -4) is 04:00 UTC."""
    start, end = wr.last_week_bounds(today=date(2026, 8, 24))
    assert start.tzinfo is None and end.tzinfo is None
    assert start.hour == 4
    assert end.hour == 4


def test_dst_week_is_not_exactly_168_hours():
    """US DST ends Sun Nov 1 2026, so the week of Mon Oct 26 runs 169 hours.

    Deriving the end as start + 7 days would place the boundary an hour early
    and drop anything logged in that hour. Both ends come from a real Eastern
    midnight instead.
    """
    start, end = wr.last_week_bounds(today=date(2026, 11, 2))
    assert start.date() == date(2026, 10, 26)
    assert (end - start) == timedelta(hours=169)
    # Spring forward, Sun Mar 8 2026 → the week of Mon Mar 2 runs 167 hours.
    start, end = wr.last_week_bounds(today=date(2026, 3, 9))
    assert start.date() == date(2026, 3, 2)
    assert (end - start) == timedelta(hours=167)


def test_rolling_window_is_twelve_whole_weeks_ending_where_the_week_ends():
    """Shares its end with the weekly window, so the rolling figure includes
    the week being reported rather than stopping just short of it."""
    w_start, w_end = wr.last_week_bounds(today=date(2026, 8, 24))
    r_start, r_end = wr.rolling_bounds(today=date(2026, 8, 24))
    assert r_end == w_end
    assert r_start < w_start
    assert (r_end - r_start).days == 7 * wr.ROLLING_WEEKS


def test_rolling_window_survives_a_dst_boundary():
    """Twelve weeks crosses a DST change about half the year; deriving it as
    end - timedelta(weeks=12) would land an hour off."""
    r_start, r_end = wr.rolling_bounds(today=date(2026, 12, 7))
    assert r_start.tzinfo is None and r_end.tzinfo is None
    # Not exactly 12*7*24 hours, because one of those weeks gained an hour.
    assert (r_end - r_start) == timedelta(days=84, hours=1)


def test_week_label_handles_month_boundaries():
    assert wr.week_label(datetime(2026, 8, 17)) == 'Aug 17–23'
    assert wr.week_label(datetime(2026, 8, 31)) == 'Aug 31 – Sep 6'


# --- What counts ------------------------------------------------------------

def test_page_opens_are_never_scored():
    """The single most important line in this file.

    A leaderboard that counts opens teaches people to open things. Opens are
    still recorded via hub_usage.record_usage — they feed Thomas's diagnostic
    view, not this ranking.
    """
    assert 'open' not in wr.SCORED_USAGE_ACTIONS


def test_scored_sources_have_no_duplicate_tables():
    """A table listed twice would silently double every point from it."""
    tables = [src[2] for src in wr.SCORED_SOURCES]
    assert len(tables) == len(set(tables))


# --- Deliverables vs capped activity ----------------------------------------

def test_deliverables_are_never_capped():
    b = {'proposal': 9, 'ppm': 4, 'tps': 3}
    assert wr.score_total(b) == 16


def test_activity_is_capped_per_week():
    """Ten quick cell edits must not outrank a proposal."""
    b = {'pipeline_touch': 40, 'pipeline_new': 10, 'hub_actions': 20}
    assert wr.score_total(b) == wr.ACTIVITY_CAP_PER_WEEK


def test_a_deliverable_week_beats_a_pipeline_only_week():
    """The behaviour Thomas asked for: pipeline should matter, but less."""
    pipeline_only = wr.score_total({'pipeline_touch': 60})
    six_proposals = wr.score_total({'proposal': 6})
    assert six_proposals > pipeline_only


def test_activity_still_adds_on_top_of_deliverables():
    assert wr.score_total({'proposal': 3, 'pipeline_touch': 30}) == 3 + wr.ACTIVITY_CAP_PER_WEEK


def test_the_cap_scales_with_the_window():
    """A weekly ceiling applied to twelve weeks would crush the rolling column
    and could put it below the week inside it."""
    b = {'pipeline_touch': 500}
    assert wr.score_total(b, weeks=1) == wr.ACTIVITY_CAP_PER_WEEK
    assert wr.score_total(b, weeks=wr.ROLLING_WEEKS) == wr.ACTIVITY_CAP_PER_WEEK * wr.ROLLING_WEEKS


def test_capping_cannot_put_rolling_below_the_week():
    """Andy's 109-vs-84 symptom must stay impossible under the cap too."""
    week = {'andy_potts': {'pipeline_touch': 100, 'proposal': 2}}
    roll = {'andy_potts': {'pipeline_touch': 400, 'proposal': 9}}
    groups = wr.build_groups(_USERS, week, rolling=roll)
    row = [r for g in groups for r in g['rows'] if r['user_key'] == 'andy_potts'][0]
    assert row['rolling'] >= row['total']


def test_breakdown_line_still_shows_the_true_counts():
    """Only the ranked score is bounded. Rachel's real board work stays visible."""
    line = wr.breakdown_line({'pipeline_touch': 18, 'proposal': 3})
    assert '18 pipeline rows updated' in line


# --- Ranking -------------------------------------------------------------

def test_groups_rank_within_role_not_across_the_company():
    """Stephanie generates two Office Ops packs a week; Andy generates five
    proposals. On one flat list the office sits at the bottom permanently, for
    reasons that have nothing to do with effort — which is exactly how a
    scoreboard loses its authority. Groups keep the comparison honest.
    """
    scores = {
        'andy_potts': {'proposal': 5},
        'adam_cupito': {'proposal': 2},
        'stephanie_whetstone': {'office_ops': 2},
        'ben_ramsey': {'ppm': 3},
    }
    groups = wr.build_groups(_USERS, scores)
    by_name = {g['name']: g for g in groups}
    assert list(by_name) == ['Consultants', 'Project Managers', 'Office']

    consultants = {r['user_key']: r for r in by_name['Consultants']['rows']}
    assert consultants['andy_potts']['rank'] == 1
    assert consultants['adam_cupito']['rank'] == 2

    # Stephanie tops her own group on 2 points; on a flat list she'd be last.
    office = by_name['Office']['rows']
    assert office[0]['user_key'] == 'stephanie_whetstone'
    assert office[0]['rank'] == 1


def test_everyone_appears_including_a_zero_week():
    """A visible 0 is the point of what was asked for. An omitted name reads
    as an oversight and lets people assume they were simply missed."""
    groups = wr.build_groups(_USERS, {'andy_potts': {'proposal': 1}})
    rows = {r['user_key']: r for g in groups for r in g['rows']}
    assert set(rows) == set(_USERS)
    assert rows['phil_miller']['total'] == 0


def test_rolling_total_rides_alongside_without_changing_the_ranking():
    """Ranked on the week. The 12-week figure is context for reading it —
    ranking on the rolling total would make the board nearly static and stop
    rewarding a good week."""
    week = {'andy_potts': {'proposal': 5}, 'adam_cupito': {'proposal': 2}}
    rolling = {'andy_potts': {'proposal': 6}, 'adam_cupito': {'proposal': 90}}
    groups = wr.build_groups(_USERS, week, rolling=rolling)
    rows = {r['user_key']: r for g in groups for r in g['rows']}
    assert rows['andy_potts']['rank'] == 1      # won the week
    assert rows['adam_cupito']['rank'] == 2     # despite a far bigger quarter
    assert rows['adam_cupito']['rolling'] == 90
    assert rows['andy_potts']['rolling'] == 6


class _PipelineDB:
    """Fake pipeline_board_entries. Rows are (created_by, created_at, updated_by, updated_at)."""

    def __init__(self, rows):
        self.rows = rows

    def cursor(self, *a, **k):
        db = self

        class C:
            def execute(s, sql, args=None):
                q = ' '.join(sql.split())
                start, end = args[0], args[1]
                if 'SELECT created_by' in q:
                    hits = [r for r in db.rows if start <= r[1] < end]
                    idx = 0
                else:
                    # Honour what the QUERY says rather than reimplementing the
                    # rule here — otherwise this fake bakes in the fix and the
                    # test can never fail, which is exactly what happened on the
                    # first attempt at writing it.
                    same_person_only = 'created_by = updated_by' in q
                    def excluded(r):
                        if not (start <= r[1] < end):
                            return False
                        return (r[0] == r[2]) if same_person_only else True
                    hits = [r for r in db.rows
                            if start <= r[3] < end and not excluded(r)]
                    idx = 2
                counts = {}
                for r in hits:
                    counts[r[idx]] = counts.get(r[idx], 0) + 1
                s._rows = list(counts.items())

            def fetchall(s): return s._rows
            def close(s): pass
        return C()

    def rollback(self): pass


def test_a_row_you_updated_but_did_not_create_still_counts_in_both_windows():
    """The 2026-08-22 bug: Andy read 109 for the week and 84 for twelve weeks.

    The touched query excluded every row created inside the window, whoever
    created it. A row Rachel created three weeks ago and Andy updated this week
    scored as a touch for Andy weekly — but in the 12-week window the creation
    fell inside the range, so it went to Rachel as pipeline_new and Andy's touch
    disappeared. Rolling ended up below the week it contains.
    """
    from collections import defaultdict
    week_start, week_end = wr.last_week_bounds(today=date(2026, 8, 24))
    roll_start, roll_end = wr.rolling_bounds(today=date(2026, 8, 24))
    three_weeks_ago = week_start - timedelta(days=21)
    in_week = week_start + timedelta(days=2)

    db = _PipelineDB([
        # Rachel created it 3 weeks ago; Andy updated it during the week.
        ('rachel_farler', three_weeks_ago, 'andy_potts', in_week),
        # Andy both created and updated one during the week — must score once.
        ('andy_potts', in_week, 'andy_potts', in_week),
    ])
    users = dict(_USERS, rachel_farler={'display': 'Rachel', 'role': 'consultant',
                                        'tier': 'team', 'email': 'r@x'})

    weekly = defaultdict(lambda: defaultdict(int))
    rolling = defaultdict(lambda: defaultdict(int))
    wr._collect_pipeline(db, users, week_start, week_end, weekly)
    wr._collect_pipeline(db, users, roll_start, roll_end, rolling)

    andy_week = sum(weekly['andy_potts'].values())
    andy_roll = sum(rolling['andy_potts'].values())
    assert andy_week == 2, 'touch on Rachel\'s row + his own new row'
    assert andy_roll >= andy_week, f'rolling {andy_roll} must not fall below week {andy_week}'
    # Rachel's creation only shows up in the wider window.
    assert sum(rolling['rachel_farler'].values()) == 1
    assert sum(weekly['rachel_farler'].values()) == 0


def test_rolling_can_never_be_lower_than_the_week_it_contains():
    """The week sits inside the 12-week window, so rolling < weekly is
    impossible with real data — it only happens when a caller forgets to pass
    the rolling scores, which is exactly what the admin preview did."""
    week = {'andy_potts': {'proposal': 5}}
    rolling = {'andy_potts': {'proposal': 5}}       # same week, nothing older
    groups = wr.build_groups(_USERS, week, rolling=rolling)
    row = [r for g in groups for r in g['rows'] if r['user_key'] == 'andy_potts'][0]
    assert row['rolling'] >= row['total']


def test_rolling_defaults_to_zero_when_not_supplied():
    groups = wr.build_groups(_USERS, {'andy_potts': {'proposal': 1}})
    rows = {r['user_key']: r for g in groups for r in g['rows']}
    assert rows['andy_potts']['rolling'] == 0


def test_email_shows_both_numbers():
    week = {'andy_potts': {'proposal': 5}}
    rolling = {'andy_potts': {'proposal': 41}}
    groups = wr.build_groups(_USERS, week, rolling=rolling)
    _s, text, html = wr.build_recap_email(groups, datetime(2026, 8, 17), 'andy_potts', _USERS)
    assert '41' in text and '41' in html
    assert f'{wr.ROLLING_WEEKS} weeks' in text
    assert '12 WK' in text


def test_ties_share_a_rank():
    scores = {'andy_potts': {'proposal': 3}, 'adam_cupito': {'proposal': 3},
              'tony_cumella': {'proposal': 1}}
    groups = wr.build_groups(_USERS, scores)
    rows = {r['user_key']: r for g in groups for r in g['rows']}
    assert rows['andy_potts']['rank'] == 1
    assert rows['adam_cupito']['rank'] == 1
    assert rows['tony_cumella']['rank'] == 3   # not 2 — standard competition ranking


def test_totals_sum_every_kind_not_just_the_biggest():
    scores = {'ben_ramsey': {'ppm': 2, 'tps': 3, 'pipeline_touch': 4}}
    groups = wr.build_groups(_USERS, scores)
    ben = [r for g in groups for r in g['rows'] if r['user_key'] == 'ben_ramsey'][0]
    assert ben['total'] == 9


def test_exclude_removes_someone_from_the_board_entirely():
    groups = wr.build_groups(_USERS, {}, exclude={'thomas_ellison'})
    keys = {r['user_key'] for g in groups for r in g['rows']}
    assert 'thomas_ellison' not in keys
    assert 'stephanie_whetstone' in keys


# --- Copy -------------------------------------------------------------------

def test_breakdown_line_singularizes_and_orders_by_size():
    line = wr.breakdown_line({'proposal': 1, 'ppm': 3})
    assert line == '3 PPMs · 1 proposal'


def test_breakdown_line_keeps_acronyms_upper_case():
    """Stripping an 's' and lowercasing produced "2 ppms" and "1 tps scope",
    which looks careless in an email people are being ranked by."""
    assert wr.breakdown_line({'ppm': 2}) == '2 PPMs'
    assert wr.breakdown_line({'tps': 1}) == '1 TPS scope'
    assert wr.breakdown_line({'tps': 3}) == '3 TPS scopes'
    assert wr.breakdown_line({'office_ops': 1}) == '1 Office Ops pack'


def test_every_scored_kind_has_an_inline_label():
    """A new source without a label would print a raw column name at people."""
    for kind, _label, *_rest in wr.SCORED_SOURCES:
        assert kind in wr.INLINE_LABELS, kind
    for kind in ('pipeline_new', 'pipeline_touch', 'hub_actions', 'training'):
        assert kind in wr.INLINE_LABELS, kind


def test_breakdown_line_is_empty_for_a_zero_week():
    assert wr.breakdown_line({}) == ''
    assert wr.breakdown_line({'proposal': 0}) == ''


def test_recipient_sees_their_own_standing_first():
    scores = {'andy_potts': {'proposal': 5}, 'adam_cupito': {'proposal': 9}}
    groups = wr.build_groups(_USERS, scores)
    subject, text, html = wr.build_recap_email(
        groups, datetime(2026, 8, 17), 'andy_potts', _USERS,
    )
    assert 'Aug 17' in subject
    # 3 consultants in the fixture: Tony, Andy, Adam.
    assert 'You: 5 this week — #2 of 3 in Consultants' in text
    assert 'Andy Potts (you)' in html


def test_zero_week_is_stated_plainly_not_hidden():
    groups = wr.build_groups(_USERS, {})
    _subject, text, _html = wr.build_recap_email(
        groups, datetime(2026, 8, 17), 'phil_miller', _USERS,
    )
    assert 'Nothing logged in the Hub last week.' in text


def test_email_explains_what_counts():
    """People will argue with their number; the email should pre-empt it."""
    groups = wr.build_groups(_USERS, {'andy_potts': {'proposal': 1}})
    _s, text, html = wr.build_recap_email(groups, datetime(2026, 8, 17), 'andy_potts', _USERS)
    for body in (text, html):
        assert 'Opening a page does not count' in body or \
               'does not count' in body


# --- Runner -----------------------------------------------------------------

class _FakeCursor:
    def __init__(self, rows_by_call):
        self._rows = list(rows_by_call)
        self._current = []

    def execute(self, sql, args=None):
        self._current = self._rows.pop(0) if self._rows else []

    def fetchall(self):
        return self._current

    def close(self):
        pass


class _FakeConn:
    def __init__(self, rows_by_call):
        self._cursor = _FakeCursor(rows_by_call)
        self.rolled_back = 0

    def cursor(self, *a, **k):
        return self._cursor

    def rollback(self):
        self.rolled_back += 1

    def close(self):
        pass


def test_collect_scores_ignores_rows_for_people_not_on_the_roster():
    """Stale user_keys (a departed employee, the retired shared login) still
    have rows in these tables. They must not appear on the board."""
    rows = [[('andy_potts', 3), ('admin', 99)]] + [[] for _ in range(20)]
    conn = _FakeConn(rows)
    scores = wr.collect_scores(lambda: conn, _USERS, datetime(2026, 8, 17), datetime(2026, 8, 24))
    assert scores.get('andy_potts', {}).get('proposal') == 3
    assert 'admin' not in scores


def test_run_weekly_recap_sends_one_email_per_person():
    sent = []

    def fake_send(subject, text, html, recipients):
        sent.append((subject, recipients))
        return True

    conn = _FakeConn([[] for _ in range(30)])
    result = wr.run_weekly_recap(
        lambda: conn, _USERS, fake_send, force=True, today=date(2026, 8, 24),
    )
    assert result['skipped'] is False
    assert len(sent) == len(_USERS)
    # One recipient each — nobody is BCC'd a list to scan for their own name.
    assert all(len(r) == 1 for _s, r in sent)
    assert set(result['sent']) == set(_USERS)


def test_run_weekly_recap_skips_people_with_no_email():
    sent = []
    users = dict(_USERS, no_email={'display': 'No Email', 'role': 'pm',
                                   'tier': 'team', 'email': ''})
    conn = _FakeConn([[] for _ in range(30)])
    result = wr.run_weekly_recap(
        lambda: conn, users, lambda *a: sent.append(a) or True,
        force=True, today=date(2026, 8, 24),
    )
    assert 'no_email' not in result['sent']
    # ...but they still appear on everyone else's scoreboard.
    _s, text, _h = wr.build_recap_email(
        wr.build_groups(users, {}), datetime(2026, 8, 17), 'ben_ramsey', users,
    )
    assert 'No Email' in text


def test_run_weekly_recap_reports_send_failures_rather_than_raising():
    def failing_send(*a):
        raise RuntimeError('smtp down')

    conn = _FakeConn([[] for _ in range(30)])
    result = wr.run_weekly_recap(
        lambda: conn, _USERS, failing_send, force=True, today=date(2026, 8, 24),
    )
    assert result['sent'] == []
    assert set(result['failed']) == set(_USERS)


def test_a_retry_does_not_send_the_recap_twice():
    """cron_weekly_recap.py retries three times. Sending thirteen emails can
    outlast gunicorn's timeout, so the server can finish sending and then have
    the connection killed — the retry would send to everyone again."""
    sent = []
    marked = {}

    class C:
        def cursor(s, *a, **k): return s
        def execute(s, sql, args=None):
            q = ' '.join(sql.split())
            if 'SELECT value FROM hub_settings' in q:
                s._row = (marked.get('v'),)
            elif 'INSERT INTO hub_settings' in q:
                import json as _j
                marked['v'] = _j.loads(args[1])
                s._row = None
            else:
                s._row = None
        def fetchone(s): return getattr(s, '_row', None)
        def fetchall(s): return []
        def close(s): pass
        def commit(s): pass
        def rollback(s): pass

    monday = datetime(2026, 8, 24, 7, 0, tzinfo=wr.ET)
    for _attempt in range(3):
        wr.run_weekly_recap(lambda: C(), _USERS,
                            lambda *a: sent.append(a) or True, now=monday)
    assert len(sent) == len(_USERS), 'only the first attempt should have sent'


def test_trigger_run_on_a_normal_day_sends_nothing():
    """The whole point of the guard.

    Render's "Trigger Run" is how anyone tests a cron. Before this, pressing it
    on a Tuesday emailed all thirteen people immediately.
    """
    sent = []
    conn = _FakeConn([[] for _ in range(30)])
    result = wr.run_weekly_recap(
        lambda: conn, _USERS, lambda *a: sent.append(a) or True,
        now=datetime(2026, 8, 25, 7, 0, tzinfo=wr.ET),   # a Tuesday
    )
    assert result['skipped'] is True
    assert result['reason'] == 'not_scheduled'
    assert sent == []


def test_force_still_overrides_the_window():
    """WEEKLY_RECAP_FORCE=true remains a deliberate off-schedule send."""
    sent = []
    conn = _FakeConn([[] for _ in range(30)])
    result = wr.run_weekly_recap(
        lambda: conn, _USERS, lambda *a: sent.append(a) or True,
        force=True, now=datetime(2026, 8, 25, 7, 0, tzinfo=wr.ET),
    )
    assert result['skipped'] is False
    assert len(sent) == len(_USERS)


def test_the_window_is_monday_morning_eastern():
    from datetime import datetime as _dt
    monday_7am = _dt(2026, 8, 24, 7, 0, tzinfo=wr.ET)
    assert wr.should_run_scheduled(monday_7am) is True
    # A retry later the same morning still lands.
    assert wr.should_run_scheduled(_dt(2026, 8, 24, 11, 30, tzinfo=wr.ET)) is True
    # Monday afternoon, and every other day, do not.
    assert wr.should_run_scheduled(_dt(2026, 8, 24, 13, 0, tzinfo=wr.ET)) is False
    assert wr.should_run_scheduled(_dt(2026, 8, 25, 7, 0, tzinfo=wr.ET)) is False
    assert wr.should_run_scheduled(_dt(2026, 8, 23, 7, 0, tzinfo=wr.ET)) is False


def test_disabled_beats_not_scheduled_in_the_reason():
    """An explicitly switched-off recap should say so, not blame the weekday."""
    os.environ['WEEKLY_RECAP_ENABLED'] = 'false'
    try:
        result = wr.run_weekly_recap(lambda: None, _USERS, lambda *a: True,
                                     now=datetime(2026, 8, 25, 7, 0, tzinfo=wr.ET))
        assert result['reason'] == 'disabled'
    finally:
        os.environ.pop('WEEKLY_RECAP_ENABLED', None)


def test_disabled_recap_sends_nothing():
    os.environ['WEEKLY_RECAP_ENABLED'] = 'false'
    try:
        result = wr.run_weekly_recap(lambda: None, _USERS, lambda *a: True,
                                     today=date(2026, 8, 24))
        assert result['skipped'] is True
        assert result['reason'] == 'disabled'
    finally:
        os.environ.pop('WEEKLY_RECAP_ENABLED', None)


# --- Subject line -----------------------------------------------------------
#
# Thomas, 2026-08-31. The old subject — "PPS Hub — week of Aug 17–23" — said
# when the email was about, not what it was, and it arrives beside every other
# automated Hub message. This is the one email that tells someone where they
# stand, so the subject says so.

def test_the_subject_names_what_the_email_is():
    subject, _text, _html = wr.build_recap_email(
        wr.build_groups(_USERS, {'andy_potts': {'proposal': 5}}),
        datetime(2026, 8, 17), 'andy_potts', _USERS,
    )
    assert subject.startswith('PPS Hub Activity Ranked Week of ')


def test_the_subject_still_says_which_week():
    """The reason a person can find last month's copy. Losing the date while
    renaming the subject would be a quiet regression — every week's email
    would have an identical subject line."""
    subject, _text, _html = wr.build_recap_email(
        wr.build_groups(_USERS, {}), datetime(2026, 8, 17), 'andy_potts', _USERS,
    )
    assert subject == 'PPS Hub Activity Ranked Week of Aug 17–23'


def test_a_week_spanning_two_months_still_reads_properly():
    subject, _text, _html = wr.build_recap_email(
        wr.build_groups(_USERS, {}), datetime(2026, 8, 31), 'andy_potts', _USERS,
    )
    assert subject == 'PPS Hub Activity Ranked Week of Aug 31 – Sep 6'
