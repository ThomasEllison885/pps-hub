"""Training curriculum overlay — merge rules and the enrolment-date behaviour.

Fake cursor/conn, no Postgres — this repo's test convention.
Run: python -m pytest tests/test_training_overlay.py -v
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psc_training_data as psc
import training_overlay as ov


ENROLLED = datetime(2026, 6, 1, 9, 0)
BEFORE = ENROLLED - timedelta(days=30)
AFTER = ENROLLED + timedelta(days=30)


def _curriculum():
    """A private copy, as `apply` requires."""
    return psc.get_training_curriculum()


def _addition(item_id='psc_x_test_1', week=5, container='videos',
              payload=None, published_at=BEFORE, sort_order=0):
    return {
        'item_id': item_id,
        'target': {'kind': 'week', 'week': week, 'container': container},
        'payload': payload or {'title': 'Extra painting video', 'url': 'https://x/y'},
        'sort_order': sort_order,
        'published_at': published_at,
    }


def _week(curriculum, n):
    _onboarding, weeks, _cv, _st, _co = curriculum
    return next(w for w in weeks if w['week'] == n)


# --- The empty case is the one that must never break ------------------------

def test_an_empty_overlay_changes_absolutely_nothing():
    """Phase 2 ships with no data in these tables. If an empty overlay is not a
    perfect no-op, every trainee's page changed the day it deployed."""
    merged, added = ov.apply(_curriculum(), {'edits': {}, 'items': []})
    assert added == []
    assert merged == _curriculum()


def test_a_missing_or_malformed_overlay_is_also_a_no_op():
    for empty in (None, {}, {'edits': None, 'items': None}):
        merged, added = ov.apply(_curriculum(), empty)
        assert added == []
        assert merged == _curriculum()


# --- Additions and the enrolment date ---------------------------------------

def test_an_item_published_before_you_enrolled_sits_in_its_week():
    merged, added = ov.apply(_curriculum(), {'items': [_addition(published_at=BEFORE)]},
                             enrolled_at=ENROLLED)
    assert added == [], 'nothing should be deferred'
    ids = [v['id'] for v in _week(merged, 5)['videos']]
    assert ids[-1] == 'psc_x_test_1'


def test_an_item_published_after_you_enrolled_is_deferred_not_inserted():
    """The whole point of the design. Andy is in Week 7; Tony improves Week 5.
    Andy's Week 5 must not reopen."""
    before_count = len(_week(_curriculum(), 5)['videos'])
    merged, added = ov.apply(_curriculum(), {'items': [_addition(published_at=AFTER)]},
                             enrolled_at=ENROLLED)
    assert [i['id'] for i in added] == ['psc_x_test_1']
    assert len(_week(merged, 5)['videos']) == before_count, (
        'a later addition leaked into the week and would reopen it')


def test_a_new_hire_gets_the_same_item_in_its_proper_week():
    """Same row, later enrolment — placement is what differs per person, not
    content."""
    later_hire = AFTER + timedelta(days=1)
    merged, added = ov.apply(_curriculum(), {'items': [_addition(published_at=AFTER)]},
                             enrolled_at=later_hire)
    assert added == []
    assert _week(merged, 5)['videos'][-1]['id'] == 'psc_x_test_1'


def test_no_enrolment_date_means_show_the_programme_as_authored():
    """An unenrolled viewer, a manager previewing, and the editor itself."""
    merged, added = ov.apply(_curriculum(), {'items': [_addition(published_at=AFTER)]},
                             enrolled_at=None)
    assert added == []
    assert _week(merged, 5)['videos'][-1]['id'] == 'psc_x_test_1'


def test_the_deferred_bucket_is_not_part_of_the_percentage_denominator():
    """`get_all_item_ids()` is what week and overall percentages divide by. A
    deferred item appearing there would drop everyone's number — the exact
    thing Thomas ruled out on 2026-08-23."""
    _merged, added = ov.apply(_curriculum(), {'items': [_addition(published_at=AFTER)]},
                              enrolled_at=ENROLLED)
    deferred = ov.added_since_item_ids(added)
    assert deferred == ['psc_x_test_1']
    assert not set(deferred) & set(psc.get_all_item_ids())


# --- Edits ------------------------------------------------------------------

def test_an_edit_reaches_everyone_immediately_and_keeps_the_id():
    """Edits are not deferred: the ID does not move, so no progress row moves,
    and deferring would leave people reading superseded wording."""
    target = _week(_curriculum(), 1)['videos'][0]['id']
    merged, _added = ov.apply(
        _curriculum(),
        {'edits': {target: {'fields': {'title': 'Corrected title'}, 'hidden': False}}},
        enrolled_at=ENROLLED)
    edited = _week(merged, 1)['videos'][0]
    assert edited['title'] == 'Corrected title'
    assert edited['id'] == target, 'editing an item must never move its ID'


def test_editing_only_touches_the_named_fields():
    target = _week(_curriculum(), 1)['videos'][0]
    merged, _ = ov.apply(_curriculum(),
                         {'edits': {target['id']: {'fields': {'title': 'New'}}}})
    after = _week(merged, 1)['videos'][0]
    assert after['url'] == target['url'], 'url was clobbered by a title-only edit'


def test_hiding_removes_it_from_view_without_deleting_history():
    target = _week(_curriculum(), 1)['videos'][0]['id']
    merged, _ = ov.apply(_curriculum(), {'edits': {target: {'hidden': True}}})
    assert target not in [v['id'] for v in _week(merged, 1)['videos']]


def test_hiding_can_only_raise_a_trainee_percentage_never_lower_it():
    """Shrinking the denominator is the only direction hiding can move someone,
    which is why hides do not need deferring either."""
    week1 = _week(_curriculum(), 1)
    before = len(week1['videos'])
    target = week1['videos'][0]['id']
    merged, _ = ov.apply(_curriculum(), {'edits': {target: {'hidden': True}}})
    assert len(_week(merged, 1)['videos']) == before - 1


def test_an_edit_applies_to_an_added_item_too():
    merged, _ = ov.apply(
        _curriculum(),
        {'items': [_addition(published_at=BEFORE)],
         'edits': {'psc_x_test_1': {'fields': {'title': 'Renamed'}}}},
        enrolled_at=ENROLLED)
    assert _week(merged, 5)['videos'][-1]['title'] == 'Renamed'


def test_hiding_an_added_item_removes_it_from_both_paths():
    for enrolled, published in ((ENROLLED, BEFORE), (ENROLLED, AFTER)):
        merged, added = ov.apply(
            _curriculum(),
            {'items': [_addition(published_at=published)],
             'edits': {'psc_x_test_1': {'hidden': True}}},
            enrolled_at=enrolled)
        assert added == []
        assert 'psc_x_test_1' not in [v['id'] for v in _week(merged, 5)['videos']]


# --- Targets ----------------------------------------------------------------

def test_it_can_add_to_each_week_container():
    for container in ('videos', 'shadowing', 'additional', 'pps_focus'):
        merged, _ = ov.apply(
            _curriculum(),
            {'items': [_addition(container=container, payload={'title': 'X', 'text': 'Y'})]})
        assert _week(merged, 5)[container][-1]['id'] == 'psc_x_test_1', container


def test_it_can_add_to_a_standalone_section():
    _o, _w, _cv, sales, _co = _curriculum()
    module_id = sales['modules'][0]['id']
    row = _addition()
    row['target'] = {'kind': 'section', 'section': 'sales_training',
                     'group_id': module_id, 'container': 'items'}
    merged, added = ov.apply(_curriculum(), {'items': [row]})
    assert added == []
    assert merged[3]['modules'][0]['items'][-1]['id'] == 'psc_x_test_1'


def test_an_item_whose_target_no_longer_exists_surfaces_rather_than_vanishing():
    """A week removed or a module renamed in the base file must not silently
    swallow somebody's addition."""
    row = _addition(week=99)
    merged, added = ov.apply(_curriculum(), {'items': [row]})
    assert [i['id'] for i in added] == ['psc_x_test_1']
    assert added[0]['_unplaceable'] is True
    assert merged == _curriculum()


def test_an_unknown_container_is_refused_rather_than_inventing_a_key():
    row = _addition(container='not_a_container')
    merged, added = ov.apply(_curriculum(), {'items': [row]})
    assert added[0]['_unplaceable'] is True
    assert 'not_a_container' not in _week(merged, 5)


# --- Minted IDs -------------------------------------------------------------

def test_a_minted_id_can_never_collide_with_an_authored_one():
    frozen = set(psc.get_all_item_ids())
    for hint in ('videos', 'w5_video_2', '', None, 'Ünïcødé and spaces!'):
        new = ov.mint_item_id('psc', hint, rand=lambda: 'deadbeef')
        assert '_x_' in new, new
        assert new not in frozen
        assert len(new) <= 100, 'item_id is VARCHAR(100) and keys progress rows'


def test_minted_ids_are_unique_across_calls():
    seen = {ov.mint_item_id('psc', 'video') for _ in range(200)}
    assert len(seen) == 200


# --- Reading from the database ---------------------------------------------

class _Conn:
    def __init__(self, edits=(), items=(), raises=False):
        self.edits, self.items, self.raises = list(edits), list(items), raises
        self.closed = False
        self.queries = []

    def cursor(self, *a, **k):
        conn = self

        class C:
            def execute(s, sql, args=None):
                q = ' '.join(sql.split())
                conn.queries.append(q)
                if conn.raises:
                    raise RuntimeError('relation "training_overlay_edits" does not exist')
                s._rows = conn.edits if 'training_overlay_edits' in q else conn.items

            def fetchall(s):
                return s._rows

            def close(s):
                pass

        return C()

    def close(self):
        self.closed = True


def test_only_published_rows_reach_a_trainee():
    """Drafts are the point of editing in waves — Tony works through Week 5 over
    a fortnight without anyone seeing half of it."""
    conn = _Conn()
    ov.load_overlay(lambda: conn, use_cache=False)
    assert all('published_at IS NOT NULL' in q for q in conn.queries), conn.queries


def test_jsonb_that_arrives_as_a_string_is_parsed():
    """psycopg2 returns jsonb as dict or str depending on version — the same
    trap system_state hit."""
    conn = _Conn(
        edits=[('psc', 'w1_video_0', '{"title": "From a string"}', False)],
        items=[('psc', 'psc_x_a', '{"kind": "week", "week": 5, "container": "videos"}',
                '{"title": "Also a string"}', 0, BEFORE)])
    data = ov.load_overlay(lambda: conn, use_cache=False)
    assert data['psc']['edits']['w1_video_0']['fields'] == {'title': 'From a string'}
    assert data['psc']['items'][0]['target']['week'] == 5
    assert data['psc']['items'][0]['payload']['title'] == 'Also a string'


def test_an_unreachable_database_shows_the_authored_curriculum():
    """A training page that 500s because an optional overlay is down is worse
    than one showing the curriculum as written."""
    for factory in (lambda: None, lambda: _Conn(raises=True)):
        data = ov.load_overlay(factory, use_cache=False)
        assert data == {'psc': {'edits': {}, 'items': []},
                        'pm': {'edits': {}, 'items': []}}
    merged, added = ov.apply(_curriculum(), ov.load_overlay(lambda: None,
                                                            use_cache=False)['psc'])
    assert added == [] and merged == _curriculum()


def test_the_connection_is_released_on_both_paths():
    ok = _Conn()
    ov.load_overlay(lambda: ok, use_cache=False)
    assert ok.closed
    bad = _Conn(raises=True)
    ov.load_overlay(lambda: bad, use_cache=False)
    assert bad.closed


def test_the_cache_holds_then_clears():
    calls = []

    def factory():
        calls.append(1)
        return _Conn()

    ov.clear_cache()
    now = datetime(2026, 8, 23, 12, 0)
    ov.load_overlay(factory, now=now)
    ov.load_overlay(factory, now=now + timedelta(seconds=ov.CACHE_TTL_SECONDS - 1))
    assert len(calls) == 1, 'cache did not hold inside the window'
    ov.load_overlay(factory, now=now + timedelta(seconds=ov.CACHE_TTL_SECONDS + 1))
    assert len(calls) == 2, 'cache did not expire'
    ov.clear_cache()
    ov.load_overlay(factory, now=now)
    assert len(calls) == 3, 'clear_cache did not force a re-read'
    ov.clear_cache()


# --- The PM shim ------------------------------------------------------------

import pm_training_data as pmd


def _pm_curriculum():
    """PM has no standalone sections, so app.py hands `apply` a five-tuple with
    empty placeholders. Pinning that shape here — if `apply` ever starts
    assuming those are populated, the PM training page breaks and nothing else
    would catch it."""
    _meta, weeks = pmd.get_pm_training_curriculum()
    return (dict(), weeks, {}, {}, {})


def test_the_pm_shape_is_a_no_op_when_empty():
    merged, added = ov.apply(_pm_curriculum(), {'edits': {}, 'items': []})
    assert added == []
    assert merged[1] == _pm_curriculum()[1]


def test_an_addition_lands_in_a_pm_week():
    row = _addition(item_id='pm_x_test_1', week=2, container='additional',
                    payload={'title': 'New PM task', 'text': 'Do the thing'})
    merged, added = ov.apply(_pm_curriculum(), {'items': [row]}, enrolled_at=ENROLLED)
    assert added == []
    week2 = next(w for w in merged[1] if w['week'] == 2)
    assert week2['additional'][-1]['id'] == 'pm_x_test_1'


def test_pm_deferral_works_the_same_way():
    row = _addition(item_id='pm_x_test_1', week=2, container='additional',
                    published_at=AFTER)
    merged, added = ov.apply(_pm_curriculum(), {'items': [row]}, enrolled_at=ENROLLED)
    assert [i['id'] for i in added] == ['pm_x_test_1']
    week2 = next(w for w in merged[1] if w['week'] == 2)
    assert 'pm_x_test_1' not in [i.get('id') for i in week2.get('additional', [])]


def test_empty_placeholder_sections_are_ignored_not_populated():
    """`apply` must not invent `sections` or `modules` keys on the empty dicts
    the PM route passes."""
    merged, _ = ov.apply(_pm_curriculum(), {'edits': {}, 'items': []})
    assert merged[2] == {} and merged[3] == {} and merged[4] == {}
