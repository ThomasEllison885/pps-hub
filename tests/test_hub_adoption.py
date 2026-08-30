"""The adoption view — who is actually using the Hub.

Run: python -m pytest tests/test_hub_adoption.py -v

Thomas ranked this first on 2026-08-29. Usage events had been recording since
2026-08-26 and nothing read them company-wide, so "did the field guide land"
and "which of these twenty tools has nobody opened" could not be asked.

Most of what these tests pin is honesty rather than arithmetic, because the
ways this page can be wrong are all ways of implying something it does not
know:

  * **Opens are not work.** The recap excludes `'open'` from scoring on
    purpose. Three separate columns here, never summed — a PM who produces
    through the proposal tool but rarely browses is not the same person as
    one who has stopped, and one merged "activity" number reads them alike.
  * **It has five days of history, not a year.** Instrumentation covers all
    twenty features only from 2026-08-26. A trend chart that draws the five
    weeks before that shows five columns of zero, which reads as a collapse
    rather than as no data.
  * **Absence is the finding.** A tool with no opens and a person with no
    events both have to appear, or the page hides the thing worth seeing.
  * **No causal claim about the guide.** It shipped alongside four other
    changes to a team of twelve. "Readers did more" off that would be a
    coincidence wearing a finding's clothes.
"""
import os
import re
import sys
from datetime import date, datetime, timedelta

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import hub_adoption as ha
import hub_time
import hub_usage
import weekly_recap

NOW = datetime(2026, 8, 29, 21, 0)          # 5pm ET Saturday

USERS = {
    'thomas_ellison': {'display': 'Thomas Ellison', 'role': 'admin', 'tier': 'owner'},
    'andy_potts': {'display': 'Andy Potts', 'role': 'consultant', 'tier': 'team'},
    'phil_miller': {'display': 'Phil Miller', 'role': 'pm', 'tier': 'team'},
}


def _row(user, feature, action='open', when=None):
    return {'user_key': user, 'feature': feature, 'action': action,
            'created_at': when or datetime(2026, 8, 28, 14, 0)}


ROWS = [
    _row('andy_potts', 'pipeline'),
    _row('andy_potts', 'pipeline', when=datetime(2026, 8, 29, 13, 0)),
    _row('andy_potts', 'guide', when=datetime(2026, 8, 27, 15, 0)),
    _row('thomas_ellison', 'siding', action='generate',
         when=datetime(2026, 8, 26, 17, 0)),
]


# ── opens, actions and work stay apart ──────────────────────────────────────

def test_opens_and_actions_are_counted_separately():
    by_feature = {f['feature']: f for f in ha.by_feature(ROWS)}
    assert by_feature['pipeline']['opens'] == 2
    assert by_feature['pipeline']['actions'] == 0
    assert by_feature['siding']['opens'] == 0
    assert by_feature['siding']['actions'] == 1


def test_a_person_row_keeps_the_three_quantities_apart():
    """One merged number would read a quiet producer and a stopped person
    identically."""
    produced = {'phil_miller': datetime(2026, 8, 28, 12, 0)}
    people = {p['user_key']: p for p in ha.by_person(ROWS, USERS,
                                                     produced=produced, now=NOW)}
    andy = people['andy_potts']
    assert (andy['opens'], andy['actions'], andy['last_produced']) == (3, 0, None)
    phil = people['phil_miller']
    assert phil['opens'] == 0 and phil['last_produced'] is not None
    assert phil['state'] == 'active', 'producing counts as being here'


def _calls_in(module='hub_adoption.py'):
    """Every function name called in the module, from the AST.

    Matching source text would match the prose: this file's docstrings
    deliberately name the things it does not do.
    """
    import ast
    tree = ast.parse(open(os.path.join(ROOT, module), encoding='utf-8').read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            names.add(getattr(fn, 'id', None) or getattr(fn, 'attr', None))
    return names - {None}


def test_nothing_sums_the_three_into_one_score():
    """A single number here would quietly become a second, competing
    leaderboard beside the recap's."""
    assert 'score_total' not in _calls_in()
    assert 'collect_scores' not in _calls_in(), (
        'this page reports what happened, it does not rank people'
    )


# ── absence is the finding ──────────────────────────────────────────────────

def test_every_known_tool_appears_even_with_nothing():
    features = ha.by_feature(ROWS)
    assert len(features) == len(hub_usage.KNOWN_FEATURES)
    labels = {f['label'] for f in features}
    assert 'Roofing Estimator' in labels, 'an unopened tool must still be listed'


def test_untouched_tools_are_called_out():
    untouched = {f['feature'] for f in ha.untouched_features(ha.by_feature(ROWS))}
    assert 'roofing' in untouched
    assert 'pipeline' not in untouched


def test_everyone_on_the_roster_appears():
    """An omitted name reads as an oversight — same rule as the recap's
    visible zero."""
    people = ha.by_person(ROWS, USERS, now=NOW)
    assert {p['user_key'] for p in people} == set(USERS)


def test_the_quietest_person_is_first():
    people = ha.by_person(ROWS, USERS, now=NOW)
    assert people[0]['user_key'] == 'phil_miller'
    assert people[0]['state'] == 'never'


def test_states_use_the_named_thresholds():
    old = datetime(2026, 8, 29, 21, 0) - timedelta(days=ha.DORMANT_DAYS + 1)
    mid = datetime(2026, 8, 29, 21, 0) - timedelta(days=ha.QUIET_DAYS + 1)
    rows = [_row('andy_potts', 'pipeline', when=old),
            _row('thomas_ellison', 'pipeline', when=mid)]
    people = {p['user_key']: p for p in ha.by_person(rows, USERS, now=NOW)}
    assert people['andy_potts']['state'] == 'dormant'
    assert people['thomas_ellison']['state'] == 'quiet'


# ── it has five days of history, not a year ─────────────────────────────────

def test_the_trend_never_draws_weeks_before_instrumentation():
    """Five columns of zero ahead of the real ones read as a collapse, which
    is the opposite of the truth."""
    weeks = ha.by_week(ROWS, now=NOW, weeks=6)
    assert weeks, 'the current week should always be there'
    earliest = min(w['start'] for w in weeks)
    assert earliest >= ha._week_start(ha.instrumented_from())
    assert len(weeks) < 6, 'there is not six weeks of data to draw yet'


def test_the_current_week_is_marked_partial():
    weeks = ha.by_week(ROWS, now=NOW, weeks=6)
    assert weeks[-1]['partial'] is True
    assert all(not w['partial'] for w in weeks[:-1])


def test_the_start_date_is_not_shifted_by_a_day():
    """`INSTRUMENTED_SINCE` is an Eastern date. Combining it with UTC midnight
    and displaying it in Eastern printed August 25 for an August 26 constant —
    the exact bug this page's own timestamps were fixed for."""
    built = ha.INSTRUMENTED_SINCE.strftime('%B %-d, %Y')
    assert built == 'August 26, 2026'
    assert hub_time.to_eastern(ha.instrumented_from()).date() == ha.INSTRUMENTED_SINCE


def test_the_window_starts_at_an_eastern_midnight():
    assert ha.instrumented_from() == datetime(2026, 8, 26, 4, 0), 'EDT is UTC-4'


def test_weeks_are_eastern_mondays():
    # 03:59 UTC Monday is still Sunday evening in Ohio.
    sunday_night = datetime(2026, 8, 31, 3, 59)
    monday_morning = datetime(2026, 8, 31, 13, 0)
    assert ha._week_start(sunday_night) != ha._week_start(monday_morning)


def test_the_week_boundary_holds_across_a_dst_change():
    """November: EST is UTC-5, so Monday midnight is 05:00 UTC. Subtracting
    days from a UTC timestamp lands an hour out twice a year."""
    november = datetime(2026, 11, 12, 14, 0)
    assert ha._week_start(november) == datetime(2026, 11, 9, 5, 0)


# ── wording ─────────────────────────────────────────────────────────────────

def test_recent_days_are_words_not_zero_d_ago():
    assert ha.ago_label(0) == 'today'
    assert ha.ago_label(1) == 'yesterday'
    assert ha.ago_label(9) == '9 days ago'
    assert ha.ago_label(None) == 'nothing yet'


# ── the guide, without a causal claim ───────────────────────────────────────

def test_guide_readers_splits_the_roster():
    guide = ha.guide_readers(ROWS, USERS)
    assert guide['read_count'] == 1
    assert guide['roster'] == len(USERS)
    assert {m['user_key'] for m in guide['missing']} == {'thomas_ellison', 'phil_miller'}


def test_the_guide_section_makes_no_before_and_after_claim():
    """It shipped alongside four other changes to a team of twelve."""
    src = open(os.path.join(ROOT, 'hub_adoption.py'), encoding='utf-8').read()
    body = src.split('def guide_readers', 1)[1].split('\ndef ', 1)[0]
    for banned in ("'before'", "'after'", 'uplift', 'lift'):
        assert banned not in body, f'{banned} — that is a causal claim'


# ── failure ─────────────────────────────────────────────────────────────────

def test_an_unreachable_database_gives_an_empty_page_not_a_500():
    """A diagnostic page that dies when something is wrong is the page you
    needed."""
    assert ha.fetch_usage(lambda: None) == []
    assert ha.last_produced(lambda: None, USERS) == {}


def test_reading_does_not_create_the_table():
    """The digest and the dashboard both read this table and deliberately do
    not call `ensure_tables` — a read must not create a table."""
    called = _calls_in()
    assert 'ensure_tables' not in called
    assert 'init_tables' not in called


def test_produced_work_reuses_the_recaps_source_list():
    """Two definitions of "did work" that have to agree is how they stop
    agreeing — and this page sits beside the Monday email."""
    src = open(os.path.join(ROOT, 'hub_adoption.py'), encoding='utf-8').read()
    assert 'weekly_recap.SCORED_SOURCES' in src
    for _kind, _label, table, _u, _t in weekly_recap.SCORED_SOURCES:
        assert f"'{table}'" not in src, f'{table} is listed a second time here'


# ── access ──────────────────────────────────────────────────────────────────

APP = open(os.path.join(ROOT, 'app.py'), encoding='utf-8').read()


def test_the_route_is_leadership_not_owner_only():
    """Tony, Trey and Stephanie manage the people this shows, and it is the
    same tier as Office Ops and the training oversight pages."""
    body = APP.split('def admin_adoption', 1)[1].split('\n@app.route', 1)[0]
    assert 'is_leadership(user_key)' in body
    assert "redirect(url_for('dashboard'))" in body
    assert 'require_admin' not in APP.split("@app.route('/admin/adoption')", 1)[1][:200]


def test_it_is_not_open_to_everyone():
    """The recap already gives the whole team a ranked board. "Who has not
    opened anything in three weeks" is a conversation to have with someone,
    not to publish at them."""
    body = APP.split('def admin_adoption', 1)[1].split('\n@app.route', 1)[0]
    assert 'if not is_leadership' in body


def test_the_page_records_its_own_opens_like_every_other():
    assert "@logs_open('adoption')" in APP
    assert hub_usage.FEATURE_LABELS.get('adoption')


def test_leadership_finds_it_from_team_view():
    """Team View is the page about who did what; that is where someone will
    look for this rather than hunting the owner-only Admin menu."""
    tpl = open(os.path.join(ROOT, 'templates', 'team_view.html'),
               encoding='utf-8').read()
    assert 'can_see_adoption' in tpl and '/admin/adoption' in tpl
    body = APP.split('def team_view', 1)[1].split('\n@app.route', 1)[0]
    assert 'can_see_adoption=is_leadership(user_key)' in body


# ── the page ────────────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def html():
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    env = Environment(loader=FileSystemLoader(os.path.join(ROOT, 'templates')),
                      undefined=StrictUndefined)
    env.filters.update(hub_time.FILTERS)
    ctx = ha.build(lambda: None, USERS, now=NOW)   # no database: empty sections
    ctx.update(user_display='Thomas Ellison', is_admin=True)
    return env.get_template('admin_adoption.html').render(**ctx)


def test_the_page_renders_with_no_data_at_all(html):
    assert 'Who is actually using the Hub' in html
    assert 'Every tool has been opened at least once' not in html, (
        'with no events, every tool is untouched'
    )


def test_the_caveat_is_on_the_page_not_in_a_footnote(html):
    assert 'August 26, 2026' in html
    assert 'not ever' in html, 'the page must say what "nobody has opened" means'


def test_the_page_says_what_it_cannot_see(html):
    """A tool with no `@logs_open` cannot appear, and a reader would otherwise
    read its absence as "nobody uses it"."""
    assert 'is missing a' in html and 'logs_open' in html
