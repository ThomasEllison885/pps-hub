"""The field guide as a page in the Hub.

Run: python -m pytest tests/test_hub_guide.py -v

Thomas sent this round as a PDF on 2026-08-27. A PDF drifts — one line in it
("the last-updated line is Eastern time") was already wrong when it landed —
and it lives in an email rather than one tap from the thing it explains.

Two properties are worth pinning, and they are the two a PDF cannot have:

  * **Sections are filtered to what you can open.** A consultant should not
    read two pages about Office Ops. `?all=1` shows everything, because none
    of it is secret; it is just noise when it is not yours.
  * **The numbers are derived from the code, not retyped.** If someone
    changes the session length, the guide has to change with it. The tests
    below prove that by moving the source values and checking the prose
    follows.
"""
import os
import re
import sys

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import hub_guide
import hub_time
import pipeline_board
import weekly_recap

FACTS = dict(
    session_days=30, statuses=pipeline_board.STATUSES,
    completed_statuses=pipeline_board.COMPLETED_STATUSES,
    rolling_weeks=weekly_recap.ROLLING_WEEKS,
    activity_cap=weekly_recap.ACTIVITY_CAP_PER_WEEK,
    recap_day='Monday', recap_hour='7am Eastern',
)

FIELD_CONSULTANT = {
    'consultants': {'andy_potts': 'Andy Potts'},
    'is_leadership': False, 'is_owner': False,
    'psc_training_enrolled': False, 'psc_training_oversight': False,
    'pipeline_boards': [{'key': 'andy_potts'}],
}
LEADER = dict(FIELD_CONSULTANT, is_leadership=True)
NEW_HIRE = {'consultants': {}, 'is_leadership': False, 'is_owner': False,
            'psc_training_enrolled': True, 'psc_training_oversight': False,
            'pipeline_boards': []}


def _sections(ctx, **over):
    return hub_guide.sections_for(ctx, hub_guide.facts(**{**FACTS, **over}))


def _text(sections):
    out = []
    for s in sections:
        for kind, content in s['body']:
            if kind == 'ul':
                out.extend(content)
            elif kind == 'dl':
                out.extend(d for _t, d in content)
            else:
                out.append(content)
    return '\n'.join(out)


# ── derived, not retyped ────────────────────────────────────────────────────

def test_session_length_follows_the_config():
    """The guide says "sessions last N days". Change the config and the
    sentence has to change, or we have shipped another PDF."""
    assert '30 days of idle time' in _text(_sections(FIELD_CONSULTANT))
    moved = _text(_sections(FIELD_CONSULTANT, session_days=14))
    assert '14 days of idle time' in moved
    assert '30 days' not in moved


def test_pipeline_statuses_come_from_the_board():
    """"Yellow means in-progress" is only true if the guide lists the same
    statuses the board highlights. Both read COMPLETED_STATUSES."""
    text = _text(_sections(FIELD_CONSULTANT))
    for status in pipeline_board.STATUSES:
        if status['value'] in pipeline_board.COMPLETED_STATUSES:
            continue
        assert status['label'] in text, f'{status["label"]} missing from the guide'


def test_a_new_status_reaches_the_guide_without_an_edit():
    fake = list(pipeline_board.STATUSES) + [{'value': 'permitting',
                                             'label': 'Awaiting permit'}]
    text = _text(_sections(FIELD_CONSULTANT, statuses=fake))
    assert 'Awaiting permit' in text


def test_the_recap_window_and_cap_are_derived():
    text = _text(_sections(FIELD_CONSULTANT))
    assert f'rolling {weekly_recap.ROLLING_WEEKS}' in text
    assert f'capped at {weekly_recap.ACTIVITY_CAP_PER_WEEK} a week' in text
    moved = _text(_sections(FIELD_CONSULTANT, activity_cap=9, rolling_weeks=6))
    assert 'capped at 9 a week' in moved and 'rolling 6' in moved


def test_no_section_hardcodes_a_fact_we_derive():
    """A number typed into the prose is a promise nobody is keeping. This
    catches the obvious ones coming back."""
    raw = open(os.path.join(ROOT, 'hub_guide.py'), encoding='utf-8').read()
    body = raw.split('SECTIONS = [', 1)[1].split('\ndef _fill', 1)[0]
    for banned in ('30 days of idle', 'rolling twelve', 'rolling 12',
                   'capped at 5'):
        assert banned not in body, f'hardcoded: {banned!r} — derive it instead'


# ── who sees what ───────────────────────────────────────────────────────────

def _ids(sections):
    return [s['id'] for s in sections]


def test_a_consultant_does_not_read_two_pages_about_office_ops():
    ids = _ids(_sections(FIELD_CONSULTANT))
    assert 'office-ops' not in ids
    assert 'training-editor' not in ids
    assert 'pricing-defaults' not in ids
    assert 'awarded-work' not in ids
    assert 'pipeline' in ids and 'proposal' in ids


def test_awarded_work_lists_the_funnel_groups():
    """The four groups in the guide have to be the four the page reads,
    or the guide becomes another PDF."""
    import production_link
    text = _text(_sections(LEADER))
    for group in production_link.FUNNEL_GROUPS:
        assert group in text
    assert 'Waiting on Margins' in text  # named as out, not as in


def test_leadership_gets_the_leadership_sections():
    ids = _ids(_sections(LEADER))
    for section_id in ('office-ops', 'training-editor', 'pricing-defaults',
                       'awarded-work'):
        assert section_id in ids


def test_psc_training_only_shows_when_it_applies():
    assert 'psc-training' not in _ids(_sections(FIELD_CONSULTANT))
    assert 'psc-training' in _ids(_sections(NEW_HIRE))


def test_pipeline_section_needs_a_board():
    assert 'pipeline' not in _ids(_sections(NEW_HIRE))
    assert 'pipeline' in _ids(_sections(FIELD_CONSULTANT))


def test_show_all_keeps_everything_and_marks_what_is_not_yours():
    every = hub_guide.sections_for(
        FIELD_CONSULTANT, hub_guide.facts(**FACTS), show_all=True)
    assert len(every) == len(hub_guide.SECTIONS)
    not_mine = [s['id'] for s in every if not s['mine']]
    assert 'office-ops' in not_mine
    assert all(s['mine'] for s in every if s['id'] == 'dashboard')


def test_hidden_count_matches_what_was_dropped():
    shown = len(_sections(FIELD_CONSULTANT))
    assert shown + hub_guide.hidden_count(FIELD_CONSULTANT) == len(hub_guide.SECTIONS)


def test_everyone_gets_the_things_everyone_needs():
    """However narrow your access, you still get how to sign in, what the
    dashboard is, how you are scored, and what to do when it breaks.

    `what-not` was on this list until 2026-08-31, when Thomas removed that
    section — six prohibitions, most of which the Hub enforces in code rather
    than by asking people not to. Dropped from here rather than kept as a
    stub: an "essential section" nobody can reach is a failing test with no
    bug behind it.
    """
    for ctx in (FIELD_CONSULTANT, LEADER, NEW_HIRE):
        ids = _ids(_sections(ctx))
        for essential in ('start', 'dashboard', 'broken', 'recap'):
            assert essential in ids


# ── structure ───────────────────────────────────────────────────────────────

def test_every_section_is_well_formed():
    seen = set()
    for s in hub_guide.SECTIONS:
        assert s['id'] not in seen, f'duplicate id {s["id"]}'
        seen.add(s['id'])
        assert re.fullmatch(r'[a-z0-9-]+', s['id']), s['id']
        assert s['title'] and callable(s['access'])
        assert s['body'], f'{s["id"]} has no body'
        for kind, content in s['body']:
            assert kind in ('p', 'h', 'ul', 'note', 'dl'), kind
            assert content, f'{s["id"]} has an empty {kind}'


def test_a_missing_fact_leaves_the_text_alone_rather_than_raising():
    """A guide that 500s is worse than one with a stray brace."""
    assert hub_guide._fill('literal {not_a_fact} here', {}) == \
        'literal {not_a_fact} here'
    assert hub_guide._fill('{session_days} days', {'session_days': 7}) == '7 days'


# ── the page ────────────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def env():
    e = Environment(loader=FileSystemLoader(os.path.join(ROOT, 'templates')),
                    undefined=StrictUndefined)
    e.filters.update(hub_time.FILTERS)
    return e


def _render(env, ctx, show_all=False):
    return env.get_template('guide.html').render(
        sections=hub_guide.sections_for(ctx, hub_guide.facts(**FACTS),
                                        show_all=show_all),
        hidden=hub_guide.hidden_count(ctx),
        show_all=show_all,
    )


def test_the_page_renders(env):
    html = _render(env, FIELD_CONSULTANT)
    assert '<title>PPS Hub · Field Guide</title>' in html
    assert 'Contents' in html


def test_every_contents_link_has_a_section_to_land_on(env):
    """A contents list that scrolls nowhere is worse than none."""
    html = _render(env, LEADER)
    anchors = set(re.findall(r'<a href="#([a-z0-9-]+)">', html))
    ids = set(re.findall(r'<section class="g-section[^"]*" id="([a-z0-9-]+)">', html))
    assert anchors and anchors == ids


def test_the_page_offers_the_sections_it_hid(env):
    """Filtering is only defensible if you can see what was filtered."""
    html = _render(env, FIELD_CONSULTANT)
    assert '/guide?all=1' in html
    assert 'cover tools you don’t have' in html


def test_show_all_offers_the_way_back(env):
    html = _render(env, FIELD_CONSULTANT, show_all=True)
    assert 'Show only my sections' in html
    assert 'not-mine' in html


def test_search_hides_sections_rather_than_removing_them(env):
    """Same reason as the Pipeline Board, plus one of its own: a removed
    section breaks the #anchor that got you here from the contents."""
    html = _render(env, FIELD_CONSULTANT)
    # Sections are toggled, never detached. (The no-match banner does get
    # removed, which is why this checks for section removal specifically
    # rather than for the word "remove" anywhere in the script.)
    assert "el.style.display = hit ? '' : 'none'" in html
    assert 'el.remove(' not in html
    assert 'removeChild' not in html


# ── redundancy (2026-08-27) ─────────────────────────────────────────────────
#
# Thomas: "Probably doesn't need a 'how to get in' section since they have to
# be in to view it. Get rid of other redundancies like that."

def test_there_is_no_how_to_get_in_section():
    """You are reading this signed in. A section on signing in is telling you
    something you have just done."""
    assert 'getting-in' not in [s['id'] for s in hub_guide.SECTIONS]
    text = _text(_sections(FIELD_CONSULTANT))
    assert 'Forgot Password' not in text
    assert 'Pick your name' not in text


def test_the_phone_tip_survived_the_cut():
    """Add to Home Screen was the one part of that section that was not about
    getting in — it is about getting back in fast, which is still worth
    saying."""
    text = _text(_sections(FIELD_CONSULTANT))
    assert 'Add to Home Screen' in text
    assert 'days of idle time' in text, 'and why you are not logged out daily'


def test_each_rule_is_stated_once():
    """"Opens do not score" was in three sections and the feedback box in
    three more. A guide that repeats itself is a guide people skim."""
    text = _text(_sections(LEADER)).lower()
    assert text.count('opening pages does not') + text.count('opens do not') <= 1, \
        'the scoring rule is restated'
    assert text.count('feedback box') <= 1, 'the feedback box is explained twice'


def test_the_tour_is_not_given_twice():
    """"Start here" and "What it is for" both explained what the Hub is."""
    ids = [s['id'] for s in hub_guide.SECTIONS]
    assert 'what-for' not in ids
    starts = [s for s in hub_guide.SECTIONS if s['id'] == 'start']
    assert len(starts) == 1
