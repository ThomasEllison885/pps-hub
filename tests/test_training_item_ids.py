"""Every training item ID, frozen 2026-08-23.

These strings are the primary keys of `psc_training_progress` and
`pm_training_progress`. A row says "andy_potts completed w5_video_2" and nothing
else records what that item was — so **an ID that changes is a completed item
that silently becomes a different one**, with no error and nothing in the logs.

**Position is the hazard.** 114 of the 246 PSC IDs and 32 of the 37 PM IDs are
built from list order — every video, shadowing task, additional item, book and
check-in (`w5_video_2`). Inserting one anywhere but the end of a list renumbers
everything after it.

The other 132 PSC items — `pps_focus` blocks, core values, sales training and
company operations — already carry an explicit `id` in the source, so their
titles can be rewritten freely. `_prepare_sales_training` and `_assign_ids` do
contain title-derived fallbacks, but no current item reaches them; those paths
would only fire for a NEW item added without an id, which is why anything the
editor creates must be given a minted id rather than left to that fallback.

If this test fails, do not update the expected list to make it pass. Find which
item moved and give it an explicit `'id'` in the source instead, keeping the old
value. Updating the list is how you orphan a trainee's progress.

Regenerate deliberately only when adding NEW items at the end of a list:
    python -c "import psc_training_data as d; print(d.get_all_item_ids())"

Run: python -m pytest tests/test_training_item_ids.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psc_training_data as psc
import pm_training_data as pm


FROZEN_PSC_IDS = (
    'cv_psc_role_stakeholders',
    'cv_psc_role_advocacy',
    'cv_psc_role_ownership',
    'cv_pure_way_map',
    'cv_pure_way_tradeoff',
    'cv_pure_way_breach',
    'cv_mission_reflect',
    'cv_mission_site',
    'cv_resource_hub',
    'cv_resource_scenario',
    'cv_resource_blocker',
    'cv_integrity_scope',
    'cv_integrity_concealed',
    'cv_integrity_promise',
    'cv_loyalty_escalation',
    'cv_loyalty_handoff',
    'cv_loyalty_habit',
    'cv_voice_generate',
    'cv_voice_rewrite',
    'cv_voice_vault',
    'cv_voice_apartment_condo',
    'cv_voice_audience',
    'cv_voice_diff',
    'ops_partner_kickoff',
    'ops_partner_log',
    'ops_partner_debrief',
    'ops_monday_read',
    'ops_monday_1on1',
    'ops_monday_practice',
    'ops_monday_award_handoff',
    'ops_lifecycle_read',
    'ops_lifecycle_1on1',
    'ops_lifecycle_map',
    'ops_eval_issue_first',
    'ops_eval_unknowns',
    'ops_eval_review',
    'ops_estimating_read',
    'ops_estimating_1on1',
    'ops_estimating_proposal',
    'ops_pg_old_vs_new',
    'ops_pg_form_map',
    'ops_pg_short_vs_full',
    'ops_pg_issue_outcome',
    'ops_pg_scope_notes',
    'ops_pg_site_obs',
    'ops_pg_pricing_modes',
    'ops_pg_generate_practice',
    'ops_pg_comparison',
    'ops_pg_production_ready',
    'ops_pg_live_review',
    'ops_pg_pure_way_check',
    'ops_ownership_card',
    'ops_ownership_scenarios',
    'ops_tp_read',
    'ops_tp_1on1',
    'ops_tp_shadow',
    'ops_tp_text_chain',
    'ops_tp_pay_point',
    'ops_comms_read',
    'ops_comms_1on1',
    'ops_comms_escalation',
    'ops_callback_role',
    'ops_callback_draft',
    'ops_mistakes_read',
    'ops_mistakes_1on1',
    'ops_mistakes_commit',
    'ops_expansion_read',
    'ops_expansion_roles',
    'ops_expansion_gates',
    'ops_expansion_1on1',
    'sales_comm_proactive',
    'sales_comm_stakeholders',
    'sales_comm_difficult',
    'sales_comm_uncertainty',
    'sales_pipe_1',
    'sales_pipe_2',
    'sales_pipe_3',
    'sales_pipe_4',
    'sales_pipe_5',
    'sales_prop_1',
    'sales_prop_2',
    'sales_prop_3',
    'sales_prop_tool_1',
    'sales_prop_tool_2',
    'sales_prop_tool_3',
    'sales_prop_tool_4',
    'sales_prop_tool_5',
    'sales_prop_tool_6',
    'sales_obj_1',
    'sales_obj_2',
    'sales_obj_3',
    'sales_obj_4',
    'sales_rel_1',
    'sales_rel_2',
    'sales_rel_3',
    'w0_shadow_intro',
    'w0_shadow_partner',
    'w0_shadow_ride',
    'w0_add_monday',
    'w0_add_hub',
    'w0_add_proposal',
    'w0_add_ppm',
    'w0_add_site_visit',
    'w0_add_crm',
    'w0_focus_partner',
    'w0_focus_ops',
    'w0_focus_core',
    'w0_focus_vocab',
    'w0_book',
    'w1_video_0',
    'w1_video_1',
    'w1_video_2',
    'w1_video_3',
    'w1_shadow_0',
    'w1_shadow_1',
    'w1_focus_ops',
    'w1_focus_proposal',
    'w1_focus_identify',
    'w1_book',
    'w2_video_0',
    'w2_video_1',
    'w2_video_2',
    'w2_video_3',
    'w2_shadow_0',
    'w2_shadow_1',
    'w2_additional_0',
    'w2_additional_1',
    'w2_additional_2',
    'w2_focus_ops',
    'w2_lifecycle_site',
    'w2_focus_tps',
    'w2_book',
    'w3_video_0',
    'w3_video_1',
    'w3_video_2',
    'w3_video_3',
    'w3_shadow_0',
    'w3_shadow_1',
    'w3_additional_0',
    'w3_focus_ops',
    'w3_lifecycle_proposal',
    'w3_focus_objections',
    'w3_book',
    'w4_video_0',
    'w4_video_1',
    'w4_video_2',
    'w4_video_3',
    'w4_video_4',
    'w4_shadow_0',
    'w4_shadow_1',
    'w4_additional_0',
    'w4_focus_ops_expansion',
    'w4_lifecycle_review',
    'w4_focus_scope_edit',
    'w4_focus_complaints',
    'w4_focus_apartment_complete',
    'w4_book',
    'w5_video_0',
    'w5_video_1',
    'w5_video_2',
    'w5_video_3',
    'w5_shadow_0',
    'w5_shadow_1',
    'w5_additional_0',
    'w5_additional_1',
    'w5_lifecycle_award',
    'w5_focus_hoa',
    'w5_book',
    'w6_video_0',
    'w6_video_1',
    'w6_video_2',
    'w6_video_3',
    'w6_shadow_0',
    'w6_shadow_1',
    'w6_additional_0',
    'w6_additional_1',
    'w6_lifecycle_ppm',
    'w6_focus_condo_proposal',
    'w6_focus_prospecting',
    'w6_book',
    'w7_video_0',
    'w7_video_1',
    'w7_video_2',
    'w7_video_3',
    'w7_video_4',
    'w7_shadow_0',
    'w7_shadow_1',
    'w7_additional_0',
    'w7_lifecycle_mobilization',
    'w7_focus_warranty',
    'w7_book',
    'w8_video_0',
    'w8_video_1',
    'w8_video_2',
    'w8_video_3',
    'w8_video_4',
    'w8_video_5',
    'w8_video_6',
    'w8_shadow_0',
    'w8_shadow_1',
    'w8_additional_0',
    'w8_additional_1',
    'w8_lifecycle_active',
    'w8_focus_condo_complete',
    'w8_book',
    'w9_video_0',
    'w9_video_1',
    'w9_video_2',
    'w9_video_3',
    'w9_shadow_0',
    'w9_shadow_1',
    'w9_additional_0',
    'w9_lifecycle_change',
    'w9_focus_permits',
    'w9_focus_4dx_start',
    'w9_book',
    'w10_video_0',
    'w10_video_1',
    'w10_video_2',
    'w10_shadow_0',
    'w10_shadow_1',
    'w10_lifecycle_concealed',
    'w10_focus_wig_draft',
    'w10_book',
    'w11_video_0',
    'w11_video_1',
    'w11_video_2',
    'w11_shadow_0',
    'w11_shadow_1',
    'w11_lifecycle_punch',
    'w11_focus_estimate_live',
    'w11_focus_scoreboard',
    'w11_focus_proposal',
    'w11_book',
    'w12_video_0',
    'w12_video_1',
    'w12_video_2',
    'w12_shadow_0',
    'w12_shadow_1',
    'w12_shadow_2',
    'w12_lifecycle_recap',
    'w12_focus_estimate_lead',
    'w12_focus_graduation',
    'w12_focus_cadence',
    'w12_focus_continuous',
    'w12_book',
)


FROZEN_PM_IDS = (
    'pm_w1_shadow_0',
    'pm_w1_shadow_1',
    'pm_w1_shadow_2',
    'pm_w1_shadow_3',
    'pm_w1_additional_0',
    'pm_w1_additional_1',
    'pm_w1_additional_2',
    'pm_w1_additional_3',
    'pm_w1_additional_4',
    'pm_w1_additional_5',
    'pm_w1_additional_6',
    'pm_w1_additional_7',
    'pm_w1_focus_trace_one_job_on_the_pro',
    'pm_w1_focus_map_your_first-week_obse',
    'pm_w1_checkin',
    'pm_w2_shadow_0',
    'pm_w2_shadow_1',
    'pm_w2_shadow_2',
    'pm_w2_additional_0',
    'pm_w2_additional_1',
    'pm_w2_additional_2',
    'pm_w2_additional_3',
    'pm_w2_focus_draft_your_week-2_operat',
    'pm_w2_checkin',
    'pm_w3_shadow_0',
    'pm_w3_shadow_1',
    'pm_w3_additional_0',
    'pm_w3_additional_1',
    'pm_w3_additional_2',
    'pm_w3_additional_3',
    'pm_w3_focus_audit_one_upcoming_jobs',
    'pm_w3_checkin',
    'pm_w4_shadow_0',
    'pm_w4_additional_0',
    'pm_w4_additional_1',
    'pm_w4_focus_service_recovery_draft',
    'pm_w4_checkin',
)


def test_no_psc_item_id_has_moved():
    assert list(psc.get_all_item_ids()) == list(FROZEN_PSC_IDS)


def test_no_pm_item_id_has_moved():
    assert list(pm.get_pm_training_item_ids()) == list(FROZEN_PM_IDS)


def test_ids_are_unique_within_each_module():
    """A duplicate ID means two items share one progress row — checking one
    ticks the other."""
    for name, got in (('PSC', psc.get_all_item_ids()), ('PM', pm.get_pm_training_item_ids())):
        dupes = {i for i in got if list(got).count(i) > 1}
        assert not dupes, f'{name} has duplicate item IDs: {sorted(dupes)}'


def test_the_counts_the_progress_bars_divide_by():
    """`compute_psc_training_stats` divides by these. If they drift, every
    trainee's percentage moves without anyone touching their record."""
    assert psc.count_trackable_items() == len(FROZEN_PSC_IDS) == 246
    assert pm.count_pm_trackable_items() == len(FROZEN_PM_IDS) == 37


def test_reading_the_curriculum_does_not_rewrite_it():
    """`get_training_curriculum()` shallow-copied each week, so `_assign_ids`
    wrote IDs straight back into the module-level lists. Harmless while the IDs
    were identical every time — but the overlay planned for the editor appends
    to these same lists, and an append that lands in the global accumulates on
    every page load for the life of the worker process.

    The module is reloaded first on purpose. Snapshotting the globals in an
    already-imported module compares mutated state against mutated state, and
    the assertion can never fail — which is exactly what the first version of
    this test did.
    """
    import importlib
    fresh = importlib.reload(psc)
    raw_video = fresh.PSC_TRAINING_WEEKS[0]['videos'][0]
    raw_shadow = fresh.PSC_TRAINING_WEEKS[0]['shadowing'][0]
    raw_sales = fresh.PSC_SALES_TRAINING['modules'][0]['items'][0]
    assert 'id' not in raw_video, 'source data already carries ids — check the fixture'

    fresh.get_training_curriculum()

    assert 'id' not in raw_video, (
        'get_training_curriculum() wrote an id into PSC_TRAINING_WEEKS')
    assert isinstance(raw_shadow, str), (
        'get_training_curriculum() replaced a shadowing string in the global list')
    # Sales-training items already carry explicit ids in the source, so the
    # check here is that the prepared copy is a different object — not that the
    # global lacks an id it always had.
    prepared = fresh.get_training_curriculum()[3]
    assert prepared['modules'][0]['items'][0] is not raw_sales, (
        'get_training_curriculum() handed back the module-level sales object')
    importlib.reload(psc)


def test_pm_curriculum_is_also_read_only():
    import importlib
    fresh = importlib.reload(pm)
    raw = fresh.PM_TRAINING_WEEKS[0]
    raw_shadow = raw['shadowing'][0] if raw.get('shadowing') else None
    fresh.get_pm_training_curriculum()
    if raw_shadow is not None and isinstance(raw_shadow, str):
        assert isinstance(raw['shadowing'][0], str), (
            'get_pm_training_curriculum() replaced a shadowing string in the global')
    for focus in raw.get('pps_focus', []):
        assert 'id' not in focus or focus.get('id', '').startswith('pm_'), (
            'unexpected id shape in PM source')
    importlib.reload(pm)


def test_repeated_reads_cannot_accumulate_items():
    """The failure this whole phase exists to prevent: an overlay appending to
    a module-level list would grow it on every page load, so the item count
    would drift upward for the life of the worker process."""
    import importlib
    fresh = importlib.reload(psc)
    counts = [len(fresh.get_all_item_ids()) for _ in range(5)]
    assert len(set(counts)) == 1, f'item count drifted across reads: {counts}'
    assert counts[0] == len(FROZEN_PSC_IDS)
    importlib.reload(psc)


# --- The cache the overlay will have to invalidate ---------------------------

def test_get_training_curriculum_hands_out_copies_not_the_cache():
    """Two callers must not be able to see each other's edits, and neither may
    reach the shared prepared structure."""
    a = psc.get_training_curriculum()
    b = psc.get_training_curriculum()
    assert a[1] is not b[1], 'two callers received the same weeks list'
    assert a[1] is not psc.read_curriculum()[1], 'a caller was handed the cache'
    a[1][0]['topic'] = 'MUTATED BY A CALLER'
    assert psc.read_curriculum()[1][0]['topic'] != 'MUTATED BY A CALLER'
    assert psc.get_training_curriculum()[1][0]['topic'] != 'MUTATED BY A CALLER'


def test_read_curriculum_is_the_cache_so_it_stays_cheap():
    """`compute_psc_training_stats` walks this three times per dashboard load.
    If it ever starts deep-copying, that is ~2.5ms of pure waste on the page
    every employee opens first."""
    assert psc.read_curriculum() is psc.read_curriculum()


def test_the_cache_can_be_cleared():
    """Phase 2 of the training editor publishes changes by clearing this. If the
    cache stops being clearable, published edits will not appear until Render
    restarts the workers — which looks exactly like 'the save button is broken'.
    """
    assert hasattr(psc._prepared_curriculum, 'cache_clear')
    assert hasattr(pm._prepared_pm_curriculum, 'cache_clear')
    first = psc.read_curriculum()
    psc._prepared_curriculum.cache_clear()
    assert psc.read_curriculum() is not first, 'cache_clear did not rebuild'
    assert list(psc.get_all_item_ids()) == list(FROZEN_PSC_IDS), (
        'rebuilding after a clear produced different IDs')
