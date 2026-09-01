"""dashboard.html — the structure the 2026-08-25 rework depends on.

Run: python -m pytest tests/test_dashboard_template.py -v

These render the real template with StrictUndefined, so a context key the
route stops passing fails here rather than blanking a block on someone's
phone. They guard four things that are easy to break without noticing:

  * an empty strip renders no element, not an empty bar;
  * the fold script is called a second time BELOW Ask PPS and the feedback
    box — the first call cannot see them, because at that point in the
    document they have not been parsed;
  * every id the Ask PPS and feedback scripts look up survived those blocks
    becoming <details>;
  * the folds are folds, not hidden content — the tool cards are still in
    the DOM whether a lane starts open or closed.
"""
import os
import re
import sys
from datetime import datetime, timedelta

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import dashboard_summary as ds
import hub_time

NOW = datetime(2026, 8, 21, 14, 0)


class Row(dict):
    """A log row missing a column reads as empty, as sparse real rows do."""

    def __missing__(self, key):
        return ''


def _env():
    env = Environment(loader=FileSystemLoader(os.path.join(ROOT, 'templates')),
                      undefined=StrictUndefined)
    # Registered on the app, which this harness does not build.
    env.filters['template_label'] = lambda v: (v or 'Standard').title()
    # The Eastern-time filters, from the same dict app.py installs — so a new
    # one reaches this harness without anyone remembering to add it here.
    env.filters.update(hub_time.FILTERS)
    return env


def _ctx(**over):
    ctx = dict(
        summary_pills=ds.build_pills(week_score=9, pipeline_open=6,
                                     pipeline_url='/pipeline-board?pair=andy_potts',
                                     psc_pct=58),
        dashboard_recent_tools=ds.recent_tools(
            {'proposal': [{'generated_at': NOW}]},
            proposal_url='https://tool.example.com',
            allowed={'proposal'},
        ),
        user={'display': 'Andy Potts', 'role': 'consultant'},
        user_key='andy_potts',
        user_role='consultant',
        real_role='consultant',
        real_is_admin=False,
        ask_pps_prompt={'id': 4, 'perspective': 'field', 'question': 'How?'},
        ask_pps_prompt_queue=2,
        user_notifications=[],
        sales_lane_open=True,
        production_lane_open=True,
        admin_lane_open=False,
        team_view=True,
        consultants={'andy_potts': 'Andy Potts'},
        recent_proposals=[Row({'id': 3, 'property_name': 'Cedar Ridge',
                               'generated_at': NOW, 'document_id': 9})],
        recent_ppms=[Row({'id': 5, 'client_name': 'Cedar HOA',
                          'generated_at': NOW - timedelta(days=3)})],
        recent_tpscopes=[],
        recent_feed=[],
        date_events=[],
        psc_training_stats={'pct': 58},
        psc_training_enrolled=True,
        psc_training_oversight=False,
        pm_training_stats={'pct': 0},
        pm_training_oversight=False,
        pm_training_open=True,
        pipeline_board_access=True,
        pipeline_board_pair_key='andy_potts',
        pipeline_boards=[{'key': 'andy_potts', 'consultant_display': 'Andy Potts',
                          'pm_display': 'Ben Cole'}],
        office_ops_access=False,
        unread_feedback=0,
        unread_diffs=0,
        can_edit_pricing=False,
        pricing_summary=None,
        proposal_url='https://tool.example.com',
        session={"role": "consultant", "user_key": "andy_potts"},
        lane_order={"sales": 0, "production": 1, "admin": 2},
    )
    ctx.update(over)
    return ctx


@pytest.fixture(scope='module')
def full():
    return _env().get_template('dashboard.html').render(**_ctx())


@pytest.fixture(scope='module')
def bare():
    """A first-morning hire: no score, no history, nothing to jump back to."""
    return _env().get_template('dashboard.html').render(
        **_ctx(summary_pills=[], dashboard_recent_tools=[],
               recent_proposals=[], recent_ppms=[], recent_feed=[],
               psc_training_enrolled=False, psc_training_stats={'pct': 0}))


def test_it_renders_at_all(full):
    assert '<title>PPS Hub · Dashboard</title>' in full


def test_unpaired_pipeline_card_says_just_rachel():
    """Rachel's board after Derek left. A leftover '/ PM' or raw key would
    show on every dashboard that lists boards."""
    env = _env()
    html = env.get_template('dashboard.html').render(**_ctx(
        user_role='consultant',
        pipeline_boards=[{
            'key': 'rachel_farler',
            'consultant_display': 'Rachel Farler',
            'pm_display': '',
            'board_label': 'Rachel',
        }],
    ))
    assert 'Rachel — live shared' in html
    assert 'Just Rachel' not in html
    assert 'Derek' not in html
    assert 'Rachel Farler /' not in html
    # Owner dashboard lists every board in the Admin lane, which is itself
    # gated on pricing_summary. Same label has to survive that path too.
    owner = env.get_template('dashboard.html').render(**_ctx(
        user_role='admin', real_is_admin=True, admin_lane_open=True,
        can_edit_pricing=True,
        pricing_summary={
            'is_custom': True, 'updated_label': 'Aug 28, 2026',
            'siding_labor': 45, 'roofing_labor': 80,
            'gutter_lf': 12, 'painting_hour': 55,
        },
        pipeline_boards=[{
            'key': 'rachel_farler',
            'consultant_display': 'Rachel Farler',
            'pm_display': '',
            'board_label': 'Rachel',
        }],
    ))
    assert 'Pipeline Board — Rachel' in owner
    assert 'Just Rachel' not in owner
    assert 'Rachel Farler /' not in owner


def test_pricing_defaults_card_is_for_leadership_not_the_admin_lane():
    """Tony / Trey / Stephanie get the card next to Estimating. The Admin
    lane stays owner-only so a pricing_summary does not drag feedback/diffs
    onto a leadership dashboard."""
    env = _env()
    tpl = env.get_template('dashboard.html')
    summary = {
        'is_custom': True, 'updated_label': 'Aug 26, 2026',
        'siding_labor': 45, 'roofing_labor': 80,
        'gutter_lf': 12, 'painting_hour': 55,
    }
    leadership = tpl.render(**_ctx(
        can_edit_pricing=True, pricing_summary=summary,
        admin_lane_open=False, user_role='consultant'))
    assert 'href="/admin/pricing-defaults"' in leadership
    assert 'Estimating Pricing Defaults' in leadership
    assert 'class="dashboard-lane lane-admin"' not in leadership
    team = tpl.render(**_ctx(can_edit_pricing=False, pricing_summary=None,
                             admin_lane_open=False))
    assert 'href="/admin/pricing-defaults"' not in team
    owner = tpl.render(**_ctx(
        can_edit_pricing=True, pricing_summary=summary,
        admin_lane_open=True, user_role='admin', real_is_admin=True))
    assert 'class="dashboard-lane lane-admin"' in owner


def test_pills_render_with_value_and_label(full):
    assert 'class="dash-pill blue"><b>9</b> this week' in full
    assert 'class="dash-pill slate"><b>6</b> in progress' in full
    assert 'class="dash-pill green"><b>58%</b> PSC training' in full


def test_pill_links_go_where_the_number_came_from(full):
    assert 'href="/team-view" class="dash-pill' in full
    assert 'href="/pipeline-board?pair=andy_potts" class="dash-pill' in full


def test_an_empty_strip_renders_no_element(bare):
    """Not an empty bar with nothing in it — no element at all. Matched on
    the markup rather than the class name, which also appears in the inline
    stylesheet above it."""
    assert 'class="dash-strip"' not in bare
    assert 'class="dash-pill' not in bare


def test_an_empty_jump_row_renders_no_element(bare):
    assert 'class="jump-back"' not in bare
    assert '<div class="section-head">Jump back in</div>' not in bare
    assert 'class="jump-card"' not in bare


def test_external_jump_cards_go_through_openTool(full):
    """A plain href to the proposal tool drops the SSO hand-off; the lane
    cards below have always used this shim and these have to as well."""
    assert "openTool('https://tool.example.com/proposal')" in full


def test_every_fold_is_addressable_by_the_script(full):
    lanes = set(re.findall(r'data-lane="([a-z]+)"', full))
    assert lanes == {'sales', 'production', 'askpps', 'feedback'}


def test_the_fold_script_runs_again_below_the_bottom_two_blocks(full):
    """The subtle one. The first __ppsApplyFolds() call sits right after the
    lanes so they never paint expanded, but Ask PPS and the feedback box are
    further down the document and do not exist yet at that point. Without the
    second call they stay open on every phone — which is exactly what
    happened the first time this was built."""
    calls = [m.start() for m in re.finditer(r'__ppsApplyFolds\(\)', full)]
    assert len(calls) == 2, 'expected one call after the lanes and one at the end'
    askpps = full.index('data-lane="askpps"')
    feedback = full.index('data-lane="feedback"')
    assert calls[0] < askpps, 'the first call should sit with the lanes'
    assert calls[1] > feedback, 'the second call must come after both blocks'


def test_ask_pps_ids_survived_becoming_a_details(full):
    """ask_pps's dashboard script looks all of these up by id. The wrapper
    changed from <div> to <details>; nothing inside it may have."""
    for element_id in ('dashPromptBlock', 'dashPromptQ', 'dashPromptAnswer',
                       'dashPromptSubmit', 'dashPromptSkip', 'dashPromptMsg',
                       'dashPromptEmpty', 'dashPromptTag', 'dashPromptIntro',
                       'askPpsWidget'):
        assert f'id="{element_id}"' in full, element_id


def test_feedback_ids_survived_the_fold(full):
    for element_id in ('feedbackText', 'feedbackSuccess'):
        assert f'id="{element_id}"' in full


def test_the_ask_pps_summary_carries_the_queue_count(full):
    """A folded block has to say whether it is worth opening."""
    assert 'Help document PPS · 2 waiting' in full


def test_no_queue_means_no_count_in_the_summary():
    html = _env().get_template('dashboard.html').render(
        **_ctx(ask_pps_prompt=None, ask_pps_prompt_queue=0))
    assert 'Help document PPS<' in html
    assert 'waiting' not in html


def test_folding_hides_nothing_the_server_sent(full):
    """A closed lane is closed, not filtered. Every tool card the server
    decided to render is in the DOM regardless of fold state — if that ever
    stops being true, the fold script has quietly become an access control
    and the tier system is no longer the only place access is decided."""
    assert full.count('pps-tool-card') >= 8
    assert 'Proposal Generator' in full
    assert 'Site Visit Report' in full


def test_the_greeting_no_longer_promises_open_lanes(full):
    """It used to read "both sections open so you can reach either lane",
    which stopped being true when the lanes started folded on phones."""
    assert 'both sections open' not in full


# --- The Admin lane (2026-08-31) ---------------------------------------------
#
# Thomas: "Put office ops in its own section. Call it admin."
#
# Office Ops used to be a card in Production & Field for leadership, and a
# second copy of the same card inside the owner-only "Admin & Company
# Settings" lane. It is now in one place: a lane called Admin, which
# leadership can see for the first time.
#
# The shape worth protecting is that ONE lane is called Admin and who sees
# which card inside it is decided per card. The obvious alternative — a second
# leadership lane also called Admin — gives you a dashboard where "the Admin
# section" means something different depending on who is looking at it.
#
# The gate is deliberately two conditions rather than one tier check: Office
# Ops is leadership, the company settings are owner-only, and they are
# separate questions that happen to share a lane. Collapsing them is how a
# leadership user ends up looking at the feedback inbox.

OWNER_PRICING = {'is_custom': True, 'updated_label': 'today',
                 'updated_by_name': 'Thomas', 'siding_labor': 1,
                 'roofing_labor': 2, 'gutter_lf': 3, 'painting_hour': 4}


def _render(**over):
    return _env().get_template('dashboard.html').render(**_ctx(**over))


def _lane(html, name):
    if f'data-lane="{name}"' not in html:
        return None
    return html.split(f'data-lane="{name}"', 1)[1].split('</details>', 1)[0]


def _cards(block):
    return re.findall(r'pps-tool-name">([^<]+)', block or '')


def test_office_ops_has_left_production_and_field():
    """The move, from the side people will notice."""
    for role in ('consultant', 'pm', 'office_manager', 'admin'):
        html = _render(user_role=role, office_ops_access=True,
                       pricing_summary=OWNER_PRICING)
        assert 'office-ops' not in _lane(html, 'production'), (
            f'Office Ops is still in Production & Field for {role}')


def test_leadership_gets_an_admin_lane_with_office_ops_in_it():
    html = _render(user_role='consultant', office_ops_access=True)
    admin = _lane(html, 'admin')
    assert admin is not None, 'leadership cannot see the Admin lane'
    assert _cards(admin) == ['Office Ops'], (
        'leadership sees more than Office Ops in the Admin lane')


def test_the_lane_is_called_admin_and_nothing_longer():
    """"Call it admin" — not "Admin & Company Settings", which is what it was
    when only Thomas could see it."""
    html = _render(user_role='consultant', office_ops_access=True)
    assert '<div class="lane-title">Admin</div>' in html


def test_there_is_only_ever_one_lane_called_admin():
    for role, over in (('consultant', {}), ('office_manager', {}),
                       ('admin', {'pricing_summary': OWNER_PRICING})):
        html = _render(user_role=role, office_ops_access=True, **over)
        assert html.count('data-lane="admin"') == 1, f'{role} sees two Admin lanes'


def test_the_owner_keeps_every_card_he_had():
    html = _render(user_role='admin', office_ops_access=True,
                   pricing_summary=OWNER_PRICING, unread_feedback=2)
    cards = _cards(_lane(html, 'admin'))
    for expected in ('Office Ops', 'Estimating Pricing Defaults', 'Feedback Inbox',
                     'Proposal Comparisons', 'Team View', 'Admin Hub'):
        assert expected in cards, f'{expected} fell out of the Admin lane'


def test_leadership_does_not_get_the_owners_cards():
    """The reason the gate is per card. Tony has Office Ops; he does not have
    the feedback inbox, the diffs, or the Admin Hub."""
    html = _render(user_role='consultant', office_ops_access=True,
                   unread_feedback=3, unread_diffs=2)
    admin = _lane(html, 'admin')
    for owner_only in ('Feedback Inbox', 'Proposal Comparisons', 'Admin Hub'):
        assert owner_only not in admin
    assert '/admin/feedback' not in admin, 'the feedback lane-link leaked'
    assert '3 feedback' not in html, 'the unread count leaked to leadership'


def test_someone_without_office_ops_sees_no_admin_lane_at_all():
    html = _render(user_role='consultant', office_ops_access=False)
    assert _lane(html, 'admin') is None
    assert 'office-ops' not in html


def test_office_ops_is_the_first_card_in_the_lane():
    """For leadership it is the only one; for Thomas it is the one with
    something new in it most days."""
    html = _render(user_role='admin', office_ops_access=True,
                   pricing_summary=OWNER_PRICING)
    assert _cards(_lane(html, 'admin'))[0] == 'Office Ops'


def test_admin_does_not_float_above_the_lane_someone_leads_with():
    """Same guarantee as the CSS rule this replaced, through the mechanism
    that replaced it. Flex `order` defaults to 0, so a lane nobody placed
    sorts FIRST — which is why `order_for` returns every lane rather than
    only the ones someone expressed a preference about. Tony has Office Ops
    and leads with Sales; Admin must not jump him."""
    import dashboard_lanes as dl
    order = dl.css_order('tony_cumella')
    assert order['admin'] > order['sales'], 'Office Ops sits above his proposals'
    html = _render(user_role='consultant', office_ops_access=True,
                   lane_order=order)
    assert f'data-lane="admin" style="order: {order["admin"]}"' in html


def test_each_lane_carries_the_order_the_server_decided():
    """The order arrives as an inline style per lane. It used to be four
    role-based CSS rules; both mechanisms at once is how they disagree."""
    import dashboard_lanes as dl
    html = _render(user_role='office_manager', office_ops_access=True,
                   lane_order=dl.css_order('stephanie_whetstone'))
    for lane, pos in (('sales', 1), ('production', 2), ('admin', 0)):
        assert re.search(rf'data-lane="{lane}" style="order: {pos}"', html), (
            f'{lane} is not carrying order {pos}')


def test_the_role_based_order_rules_are_gone():
    html = _render()
    for dead in ('.dash-role-pm .lane-production', '.dash-role-consultant .lane-sales',
                 '.dash-role-admin .lane-admin'):
        # The selector is named in a comment explaining what it replaced, so
        # match the rule — selector followed by an `order` declaration.
        assert not re.search(re.escape(dead) + r'\s*\{\s*order:', html), (
            f'{dead} is back and fighting the server')


def test_a_missing_lane_order_still_renders_in_document_order():
    """Every lane computes to 0, which is document order — sales, production,
    admin. A blank dashboard would be a much worse failure than a default
    one."""
    html = _render(lane_order={})
    assert html.count('style="order: 0"') >= 2
    assert 'data-lane="sales"' in html and 'data-lane="production"' in html
