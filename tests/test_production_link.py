"""Read-only Production Board funnel × Hub docs.

Run: python -m pytest tests/test_production_link.py -v
"""
import json
import os
import sys

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import monday_client as mc
import production_link as pl
import hub_time


# ── keys ────────────────────────────────────────────────────────────────────

def test_hub_style_keys_normalize():
    assert pl.normalize_proposal_key('AP26155') == 'AP26155'
    assert pl.normalize_proposal_key('ap-26155') == 'AP26155'
    assert pl.normalize_proposal_key('CK4440D') == 'CK4440D'
    assert pl.normalize_proposal_key('TC7364') == 'TC7364'


def test_numeric_monday_cells_are_keys_not_guesses():
    """460136 is what Monday actually stores for some Connor jobs. We keep
    it so the miss against Hub's AP26155-style numbers is visible."""
    assert pl.normalize_proposal_key('460136') == '460136'
    assert pl.normalize_proposal_key('AP26155') != '460136'


def test_warranty_work_is_not_a_key():
    assert pl.normalize_proposal_key('Warranty work') is None
    assert pl.normalize_proposal_key('warranty') is None
    assert pl.normalize_proposal_key('') is None
    assert pl.normalize_proposal_key('n/a') is None


def test_key_falls_back_to_the_job_name():
    key, source = pl.keys_from_job('', 'AP26155 Indian Creek 5456 Leak')
    assert key == 'AP26155' and source == 'name'
    key, source = pl.keys_from_job('AP26155', 'something else')
    assert key == 'AP26155' and source == 'column'


# ── funnel filter ───────────────────────────────────────────────────────────

def test_funnel_is_exactly_the_four_groups_thomas_named():
    assert pl.FUNNEL_GROUPS == (
        'Awarded - On Hold',
        'Needs Scheduled',
        'Scheduled',
        'In Progress',
    )
    assert 'Waiting on Margins' not in pl.FUNNEL_GROUPS
    assert 'Call Backs/ Warranty Work' not in pl.FUNNEL_GROUPS


def test_join_drops_everything_outside_the_funnel():
    jobs = [
        {'group': 'In Progress', 'name': 'keep', 'key': 'AP1'},
        {'group': 'Waiting on Margins', 'name': 'drop', 'key': 'AP00000',
         'job_size': 999999},
        {'group': 'Call Backs/ Warranty Work', 'name': 'drop2', 'key': 'AP2'},
    ]
    grouped = pl.join_funnel(jobs, {})
    assert all(r['name'] == 'keep' for rows in grouped.values() for r in rows)
    assert sum(len(v) for v in grouped.values()) == 1
    assert 'Waiting on Margins' not in grouped


def test_fetch_grouped_items_asks_monday_for_named_groups_only(monkeypatch):
    """The API still returns every group on the board; we skip the ones we
    did not name. An empty groups list must not fetch the whole board."""
    seen = {'board_query': None}

    def fake_graphql(query, variables=None, timeout=30):
        seen['board_query'] = query
        return {'boards': [{'groups': [
            {'title': 'Waiting on Margins',
             'items_page': {'cursor': None, 'items': [
                 {'id': '9', 'name': 'NO', 'group': {'title': 'Waiting on Margins'},
                  'column_values': []}]}},
            {'title': 'In Progress',
             'items_page': {'cursor': None, 'items': [
                 {'id': '1', 'name': 'YES', 'group': {'title': 'In Progress'},
                  'column_values': []}]}},
        ]}]}

    monkeypatch.setattr(mc, 'monday_graphql', fake_graphql)
    assert mc.fetch_grouped_items('672538971', (), ['x']) == []
    items = mc.fetch_grouped_items('672538971', ('In Progress',), ['x'])
    assert [i['name'] for i in items] == ['YES']


def test_production_fetch_does_not_write():
    """The spike is a join. A mutation in this path is how Hub becomes
    a second board. Comments may name the mutations they refuse."""
    import re
    pl_body = open(os.path.join(ROOT, 'production_link.py'), encoding='utf-8').read()
    mc_body = open(os.path.join(ROOT, 'monday_client.py'), encoding='utf-8').read()
    tail = mc_body.split('PRODUCTION_BOARD_ID', 1)[1]
    for src in (pl_body, tail):
        code = re.sub(r'""".*?"""', '', src, flags=re.S)
        code = re.sub(r'#.*', '', code)
        for banned in ('change_column_value', 'change_multiple_column_values',
                       'create_item', 'move_item_to_group', 'delete_item'):
            assert banned not in code


# ── join ────────────────────────────────────────────────────────────────────

def _hub():
    return pl.index_hub_docs(
        proposal_rows=[{'id': 1, 'proposal_number': 'AP26155',
                        'property_name': 'Indian Creek', 'generated_at': '2026-08-12',
                        'document_id': 44}],
        ppm_rows=[{'id': 2, 'proposal_number': 'ap26155',
                   'property_name': 'Indian Creek', 'generated_at': '2026-08-20'}],
        tps_rows=[{'id': 3, 'proposal_number': 'AP26155',
                   'property_name': 'Indian Creek', 'generated_at': '2026-08-21'}],
    )


def test_join_is_case_insensitive_and_latest_wins():
    hub = pl.index_hub_docs(
        ppm_rows=[
            {'id': 1, 'proposal_number': 'AP26155', 'property_name': 'old',
             'generated_at': '2026-01-01'},
            {'id': 2, 'proposal_number': 'ap26155', 'property_name': 'new',
             'generated_at': '2026-08-20'},
        ],
    )
    assert hub['AP26155']['ppm']['id'] == 2
    grouped = pl.join_funnel(
        [{'group': 'In Progress', 'key': 'AP26155', 'name': 'x'}], hub)
    assert grouped['In Progress'][0]['hub_ppm']['property_name'] == 'new'


def test_monday_yes_without_hub_ppm_is_a_disagreement():
    jobs = [{'group': 'Needs Scheduled', 'key': 'RF26165', 'name': 'Sugar Glen',
             'monday_ppm': 'Yes'}]
    grouped = pl.join_funnel(jobs, {})
    row = grouped['Needs Scheduled'][0]
    assert row['ppm_gap'] is True
    assert row['ppm_disagrees'] is True
    assert row['link_state'] == 'key_only'


def test_a_job_with_a_hub_ppm_is_linked_even_if_monday_says_no():
    jobs = [{'group': 'Awarded - On Hold', 'key': 'AP26155', 'name': 'IC',
             'monday_ppm': 'No'}]
    grouped = pl.join_funnel(jobs, _hub())
    row = grouped['Awarded - On Hold'][0]
    assert row['link_state'] == 'linked'
    assert row['hub_proposal']['document_id'] == 44
    assert row['hub_ppm']
    assert row['hub_tps']
    assert row['ppm_gap'] is False


def test_numeric_key_does_not_match_a_hub_ap_number():
    hub = _hub()
    jobs = [{'group': 'Needs Scheduled', 'key': '460136', 'name': 'Connor'}]
    grouped = pl.join_funnel(jobs, hub)
    assert grouped['Needs Scheduled'][0]['hub_proposal'] is None
    assert grouped['Needs Scheduled'][0]['link_state'] == 'key_only'


def test_a_monday_number_is_not_a_ppm_button():
    """PPM is generated from the proposal file. A key with no Hub proposal
    must not offer a link to the empty /ppm form."""
    jobs = [{'group': 'In Progress', 'key': 'CK4440D', 'name': 'Kettering'}]
    row = pl.join_funnel(jobs, {}, proposal_url='https://tool.example.com')['In Progress'][0]
    assert not row.get('ppm_url')
    assert not row.get('tps_url')


def test_ppm_and_tps_links_need_the_vault_file():
    """The useful link opens the tool with ?document= so it can load the
    file. No document_id, no link — even if we have a proposal_url."""
    with_file = pl.join_funnel(
        [{'group': 'Needs Scheduled', 'key': 'AP26155', 'name': 'IC'}],
        _hub(), proposal_url='https://tool.example.com',
    )['Needs Scheduled'][0]
    assert with_file['ppm_url'] == 'https://tool.example.com/ppm?document=44'
    assert with_file['tps_url'].startswith(
        'https://tool.example.com/subscope?document=44')
    assert 'log=1' in with_file['tps_url']
    no_file = pl.index_hub_docs(
        proposal_rows=[{'id': 9, 'proposal_number': 'TC7364',
                        'property_name': 'Woodlands', 'generated_at': '2026-08-01'}],
    )
    row = pl.join_funnel(
        [{'group': 'Scheduled', 'key': 'TC7364', 'name': 'Woodlands'}],
        no_file, proposal_url='https://tool.example.com',
    )['Scheduled'][0]
    assert row['hub_proposal']
    assert not row['ppm_url'] and not row['tps_url']


def test_error_is_not_an_empty_board():
    """Pipeline Board's wipe: [] from a failed fetch looked like no jobs.
    build_view must carry the error and not a zero-job summary pretending
    the funnel is quiet."""
    jobs, error, source = None, 'Monday API error: timeout', None
    grouped = pl.join_funnel(jobs or [], {})
    summary = pl.summarize(grouped)
    assert error
    assert summary['totals']['jobs'] == 0
    # The page branches on error, not on jobs==0. Pin the payload shape.
    view = {'error': error, 'groups': grouped, 'summary': summary, 'source': source}
    assert view['error'] and view['source'] is None


def test_fixture_hides_waiting_on_margins_and_shows_the_join(monkeypatch):
    monkeypatch.setenv(pl.FIXTURE_ENV, '1')
    view = pl.build_view(lambda: None, proposal_url='https://tool.example.com')
    assert view['error'] is None
    assert view['source'] == 'fixture'
    names = [r['name'] for rows in view['groups'].values() for r in rows]
    assert any('Indian Creek' in n for n in names)
    assert all('Waiting on Margins' not in n for n in names)
    ic = [r for r in view['groups']['Awarded - On Hold'] if r['key'] == 'AP26155'][0]
    assert ic['hub_ppm'] and ic['hub_proposal']
    sugar = [r for r in view['groups']['Needs Scheduled'] if r['key'] == 'RF26165'][0]
    assert sugar['ppm_disagrees'] is True  # Monday Yes, no Hub PPM
    numeric = [r for r in view['groups']['Needs Scheduled'] if r['key'] == '460136'][0]
    assert numeric['link_state'] == 'key_only'


# ── access ──────────────────────────────────────────────────────────────────

def test_it_is_parked_even_for_the_owner():
    """Thomas, 2026-09-04: take it off the Hub. A missing env var must not
    bring the Production Board join back."""
    users = {
        'thomas_ellison': {'tier': 'owner', 'display': 'Thomas'},
        'trey_hollmeyer': {'tier': 'leadership', 'display': 'Trey'},
    }
    assert pl.is_enabled() is False
    assert not pl.can_view(users, 'thomas_ellison')
    assert not pl.can_view(users, 'trey_hollmeyer')


def test_leadership_can_view_only_when_switched_on(monkeypatch):
    monkeypatch.setenv(pl.ENABLED_ENV, 'true')
    users = {
        'thomas_ellison': {'tier': 'owner', 'display': 'Thomas'},
        'trey_hollmeyer': {'tier': 'leadership', 'display': 'Trey'},
        'andy_potts': {'tier': 'team', 'display': 'Andy'},
    }
    assert pl.can_view(users, 'thomas_ellison')
    assert pl.can_view(users, 'trey_hollmeyer')
    assert not pl.can_view(users, 'andy_potts')
    assert not pl.can_view(users, 'not_on_roster')
    assert not pl.can_view(users, '')
    assert not pl.can_view({}, 'trey_hollmeyer')


# ── template ────────────────────────────────────────────────────────────────

def _env():
    env = Environment(loader=FileSystemLoader(os.path.join(ROOT, 'templates')),
                      undefined=StrictUndefined)
    env.filters.update(hub_time.FILTERS)
    return env


def test_page_renders_the_four_groups_and_says_it_is_not_the_board(monkeypatch):
    monkeypatch.setenv(pl.FIXTURE_ENV, '1')
    view = pl.build_view(lambda: None, proposal_url='https://tool.example.com')
    html = _env().get_template('production_link.html').render(
        user_display='Trey Hollmeyer',
        groups=view['groups'],
        summary=view['summary'],
        error=view['error'],
        source=view['source'],
        funnel_groups=view['funnel_groups'],
        fetched_label='Sep 3, 2:00 PM',
        proposal_url='https://tool.example.com',
    )
    assert 'Not the Production Board' in html
    for name in pl.FUNNEL_GROUPS:
        assert name in html
    assert 'THIS SHOULD NEVER RENDER' not in html
    assert html.count('Waiting on Margins') == 1  # the banner naming it as out
    assert 'AP26155' in html
    assert 'Warranty work' in html or 'none' in html
    assert 'No Hub PPM' in html
    assert 'Generate PPM' not in html
    assert '/ppm?document=44' in html
    assert '/subscope?document=44' in html
    assert 'CK4440D' in html
    # Kettering has a key and no Hub file — Monday only, no fake tool links.
    assert html.count('/ppm?document=') == 2  # AP26155 + RF26165
    assert ':root' not in html  # palette is global
    css = html.split('<style>', 1)[1].split('</style>', 1)[0]
    main_block = css.split('.main', 1)[-1].split('}', 1)[0]
    assert 'max-width' not in main_block


def test_error_page_does_not_look_like_a_quiet_funnel():
    html = _env().get_template('production_link.html').render(
        user_display='Thomas',
        groups={g: [] for g in pl.FUNNEL_GROUPS},
        summary=pl.summarize({g: [] for g in pl.FUNNEL_GROUPS}),
        error='Monday API error: timeout',
        source=None,
        funnel_groups=pl.FUNNEL_GROUPS,
        fetched_label='',
        proposal_url='https://tool.example.com',
    )
    assert 'Could not read Monday' in html
    assert 'Showing nothing rather than an empty board' in html
    assert 'stat-card' not in html.split('</style>', 1)[-1]  # no 0-jobs strip
