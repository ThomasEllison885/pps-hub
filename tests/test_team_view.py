"""Team View — that it agrees with the Monday email, and stays bounded.

The route is in app.py, which no test can import, so these are structural
assertions against the source plus behavioural checks on the scoring functions
Team View is now required to share with the recap.

Run: python -m pytest tests/test_team_view.py -v
"""
import ast
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import weekly_recap

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = open(os.path.join(ROOT, 'app.py')).read()
TPL = open(os.path.join(ROOT, 'templates', 'team_view.html')).read()


def _route_body():
    tree = ast.parse(SRC)
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name == 'team_view':
            return ast.get_source_segment(SRC, n)
    raise AssertionError('team_view route not found')


# --- One scoring function, not two ------------------------------------------

def test_team_view_scores_through_the_recap_not_its_own_arithmetic():
    """The bug this fixes: the page counted every row a person had ever
    generated, uncapped, while the email counted a week plus a rolling twelve
    with pipeline capped at five. Two numbers, same person's name on both."""
    body = _route_body()
    assert 'weekly_recap.collect_scores' in body
    assert 'weekly_recap.score_total' in body
    assert 'weekly_recap.last_week_bounds' in body
    assert 'weekly_recap.rolling_bounds' in body


def test_the_card_numbers_are_not_computed_from_list_lengths():
    """`{{ mdata.get('proposals', [])|length }}` was the old headline number —
    lifetime row count, no cap, no window. If that shape comes back the page
    silently disagrees with the email again."""
    assert "|length }}" not in TPL.replace("{{ members|length }}", ""), (
        'a card stat is back to counting a list length')
    assert '{{ m.week_score }}' in TPL
    assert '{{ m.rolling_score }}' in TPL


def test_the_rolling_score_uses_the_full_window_allowance():
    """`score_total(..., weeks=1)` on a twelve-week breakdown would crush the
    rolling figure against a cap meant for seven days, and it could read lower
    than the week inside it — the impossible number Andy spotted on 08-22."""
    body = _route_body()
    # Match the score_total call itself. A bare `weeks=weekly_recap.ROLLING_WEEKS`
    # substring is also satisfied by `rolling_weeks=weekly_recap.ROLLING_WEEKS`
    # on the render_template line, so the first version of this assertion could
    # not fail when the call was changed to weeks=1.
    call = re.search(r'score_total\(\s*roll_break,\s*weeks=([^)]+)\)', body)
    assert call, 'the rolling score is not built from score_total(roll_break, weeks=...)'
    assert call.group(1).strip() == 'weekly_recap.ROLLING_WEEKS', (
        f'rolling score uses weeks={call.group(1).strip()} — a twelve-week '
        f'breakdown scored against a one-week cap can read lower than the week '
        f'inside it')


def test_a_rolling_total_can_never_be_lower_than_its_own_week():
    """Belt and braces on the arithmetic Team View now shares."""
    week = {'pipeline_touch': 40, 'proposal': 2}
    rolling = {'pipeline_touch': 400, 'proposal': 20}
    w = weekly_recap.score_total(week, weeks=1)
    r = weekly_recap.score_total(rolling, weeks=weekly_recap.ROLLING_WEEKS)
    assert r >= w, f'rolling {r} < week {w}'


# --- Bounded ----------------------------------------------------------------

def test_detail_queries_are_windowed_and_capped():
    """Was three `SELECT *` per person — thirty-nine queries with no date
    filter and no LIMIT, every row ever written serialised into the page."""
    body = _route_body()
    assert 'generated_at >= %s' in body, 'detail rows are unwindowed again'
    assert 'LIMIT %s' in body, 'detail rows are uncapped again'
    assert 'TEAM_VIEW_ROW_CAP' in body


def test_the_roster_is_fetched_in_one_query_per_table_not_one_per_person():
    body = _route_body()
    assert 'generated_by = ANY(%s)' in body, (
        'back to a per-person query loop')
    # Three detail tables, three lifetime counts — not thirteen times three.
    assert body.count('cur.execute') <= 4, (
        f'{body.count("cur.execute")} execute calls — a per-person loop crept back')


def test_lifetime_totals_are_counted_not_fetched():
    """People want a lifetime number, not five hundred lifetime rows."""
    body = _route_body()
    assert re.search(r'SELECT generated_by, COUNT\(\*\)', body), (
        'lifetime totals are not a grouped count')


def test_a_missing_table_does_not_take_the_page_down():
    body = _route_body()
    assert 'conn.rollback()' in body, (
        'Postgres fails the whole connection after an error — without a '
        'rollback every later query in this route also fails')


# --- The dead `scope` branch ------------------------------------------------

def test_the_template_no_longer_branches_on_a_hardcoded_scope():
    """`scope` was pinned to 'all' in the route while the template branched on
    `scope == 'consultants'`. So the consultants branch was dead: every card
    showed PM stats, and **no consultant's proposals were ever counted or
    listed** on the page built to show them."""
    assert "scope == 'consultants'" not in TPL
    assert "scope === 'consultants'" not in TPL
    body = _route_body()
    # 'tpscopes' and 'subscope_log' both contain the substring, so match the
    # variable itself rather than the word.
    assert not re.search(r'\bscope\s*=\s*[\'"]', body), (
        'the route still assigns a scope')
    assert not re.search(r'\bscope=', body), 'the route still passes scope to the template'


def test_every_person_gets_all_three_activity_kinds():
    for kind in ('proposals', 'ppms', 'tpscopes'):
        assert f"key: '{kind}'" in TPL, f'{kind} section missing from the detail panel'
    for label in ('Proposals', 'PPMs', 'Trade Partner Scopes'):
        assert f"label: '{label}'" in TPL, label


def test_the_type_filter_offers_kinds_not_proposal_templates():
    """The old select offered short/full proposal templates because the page
    only ever showed one kind per person."""
    for value in ('proposal', 'ppm', 'tps'):
        assert f'value="{value}"' in TPL, value
    assert 'Comprehensive only' not in TPL


def test_the_detail_panel_indexes_into_the_unfiltered_list():
    """The modals read `memberData[key][kind][i]`. An index into the filtered
    copy opens a different record than the one clicked — subtle, and only
    visible once a filter is active."""
    assert 'sec.all.indexOf(r)' in TPL, (
        'detail rows index into the filtered array, not the original')


def test_somebody_with_no_activity_still_appears():
    """An omitted name reads as an oversight — the same reasoning that keeps a
    visible zero in the weekly recap."""
    assert '_filtersAreIdle()' in TPL
    assert 'No activity in the last' in TPL
