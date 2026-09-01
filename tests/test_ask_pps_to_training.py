"""An approved Ask PPS answer, filed as a training draft.

Run: python -m pytest tests/test_ask_pps_to_training.py -v

Thomas, 2026-08-31: "My idea was for those answers to be incorporated into the
PSC (or PM) training. But the questions aren't that good and when they are
answered the process for adding them (I would need to review / edit them
first)."

Two findings behind this change.

**The review step already existed.** `/admin/ask-pps` has had Edit / Approve /
Reject side by side, with the team's original answer frozen and shown beside
the curator's edit. Answers land `pending` and are invisible to the assistant
until approved. What was missing was the hop *after* that.

**And the link needed to automate the hop was already in the data, unread.** A
prompt minted from a `[TO DOCUMENT]` marker in the curriculum carries
`source_ref = 'psc:<module_id>:<index>'` — so an approved answer to one of
those prompts knows exactly which module it fills. `discover_psc_training_gaps`
has been writing that; nothing read it. Until now the only route from an
approved answer into the curriculum was a person hand-editing
`psc_training_data.py`, and there is a PM training item in that file whose
text says in as many words: "This came directly from the team via Ask PPS."

── Why it files a DRAFT ────────────────────────────────────────────────────

`training_overlay.create_item` leaves `published_at` NULL, so the item waits
in the training editor. That is the whole reason this is safe to automate:
**"is this true" and "is this how we teach it" are different questions**, and
a colleague's answer can pass the first without passing the second. Approving
publishes it to the knowledge base immediately and to nobody's training
programme at all. Two reviews, on purpose.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import ask_pps  # noqa: E402
import training_overlay  # noqa: E402


# ── the link that was being thrown away ─────────────────────────────────────

def test_a_curriculum_gap_prompt_knows_which_module_it_fills():
    module, target = ask_pps.training_target_for_source_ref('psc:ops_monday:2')
    assert module == 'psc'
    assert target == {'kind': 'section', 'section': 'company_operations',
                      'group_id': 'ops_monday'}


def test_the_resolved_target_is_one_the_overlay_can_actually_place():
    """A target the overlay cannot resolve is not an error — `apply` drops the
    item into the "added since you started" bucket instead, where it looks
    like a filing mistake rather than a bug. So the shape is checked against
    the real curriculum."""
    _module, target = ask_pps.training_target_for_source_ref('psc:ops_monday:0')
    curriculum = ask_pps.get_training_curriculum()
    container = training_overlay._target_container(curriculum, target)
    assert container is not None, (
        'the target resolves to no container — the item would be orphaned')
    assert isinstance(container, list)


@pytest.mark.parametrize('ref', ['audit:x', 'pscfb:x', 'pmfb:x', 'user:andy:1',
                                 '', None, 'psc', 'psc:'])
def test_anything_that_does_not_name_a_module_resolves_to_nothing(ref):
    """The other prompt sources are questions about the company rather than
    about a module, so the curator picks the destination. Guessing would file
    a good answer under a heading nobody reads, which is worse than asking."""
    assert ask_pps.training_target_for_source_ref(ref) == (None, None)


# ── the picker for everything else ──────────────────────────────────────────

def test_the_destination_list_comes_from_the_live_curriculum():
    """Read rather than kept as a list here, so a module renamed in
    psc_training_data.py cannot leave the dropdown offering a destination the
    overlay will refuse."""
    modules = ask_pps.company_operations_modules()
    assert modules, 'no destinations offered at all'
    curriculum = ask_pps.get_training_curriculum()
    for mid, title in modules:
        assert mid and title
        target = {'kind': 'section', 'section': 'company_operations',
                  'group_id': mid}
        assert training_overlay._target_container(curriculum, target) is not None, (
            f'{mid} is offered but cannot be placed')


def test_every_psc_gap_prompt_source_lands_somewhere_real():
    """The generator mints one prompt per [TO DOCUMENT] marker. If a module
    ever gains markers but changes id, this catches it before an approved
    answer disappears into the appended bucket."""
    curriculum = ask_pps.get_training_curriculum()
    known = {mid for mid, _t in ask_pps.company_operations_modules()}
    for mid in known:
        _m, target = ask_pps.training_target_for_source_ref(f'psc:{mid}:0')
        assert training_overlay._target_container(curriculum, target) is not None


# ── it drafts, it does not publish ──────────────────────────────────────────

def test_the_route_files_a_draft_and_never_publishes():
    """`create_item` leaves published_at NULL. If this ever called `publish`,
    a colleague's wording would reach a new hire's programme untouched."""
    source = open(os.path.join(ROOT, 'ask_pps.py')).read()
    route = source.split('def admin_ask_pps_to_training', 1)[1].split('\n    @app.route', 1)[0]
    assert 'training_overlay.create_item(' in route
    assert 'training_overlay.publish(' not in route, (
        'the training hop is publishing straight into the curriculum')


def test_the_draft_is_filed_before_the_answer_is_approved():
    """The other order loses the answer's place in the pending queue if the
    overlay write fails, and a curator has no way of noticing."""
    source = open(os.path.join(ROOT, 'ask_pps.py')).read()
    route = source.split('def admin_ask_pps_to_training', 1)[1].split('\n    @app.route', 1)[0]
    assert route.index('create_item(') < route.index("status = 'active'")


def test_the_prompt_wins_over_the_dropdown():
    """When the question came from a [TO DOCUMENT] marker, that marker names
    the right module better than any default a picker could offer."""
    source = open(os.path.join(ROOT, 'ask_pps.py')).read()
    route = source.split('def admin_ask_pps_to_training', 1)[1].split('\n    @app.route', 1)[0]
    assert route.index('training_target_for_source_ref(') < route.index('elif group_id:')


def test_it_refuses_rather_than_guessing_when_there_is_no_target():
    source = open(os.path.join(ROOT, 'ask_pps.py')).read()
    route = source.split('def admin_ask_pps_to_training', 1)[1].split('\n    @app.route', 1)[0]
    assert 'if not target:' in route


def test_the_curation_page_offers_the_hop():
    with open(os.path.join(ROOT, 'templates', 'admin_ask_pps.html')) as fh:
        html = fh.read()
    assert 'admin_ask_pps_to_training' in html
    assert 'training_modules' in html, 'no destination picker for unlinked prompts'


def test_the_page_is_given_what_it_needs_to_render_that():
    source = open(os.path.join(ROOT, 'ask_pps.py')).read()
    assert "'training_modules': company_operations_modules()," in source
    assert 'p.source_ref AS prompt_source_ref' in source, (
        'the curation page cannot tell which answers have a module already')


# ── the payload reads as curriculum, not as a form submission ───────────────

def test_the_question_becomes_the_heading_and_the_answer_the_body():
    source = open(os.path.join(ROOT, 'ask_pps.py')).read()
    route = source.split('def admin_ask_pps_to_training', 1)[1].split('\n    @app.route', 1)[0]
    assert "'title': question" in route
    assert "'text': (entry.get('content')" in route


def test_the_draft_says_it_needs_rewording():
    """It arrives in the training editor next to authored curriculum. Without
    a marker, a draft that reads plausibly is the one most likely to be
    published unedited."""
    source = open(os.path.join(ROOT, 'ask_pps.py')).read()
    assert 'reword before publishing' in source.lower()


def test_the_fields_it_sets_are_ones_the_overlay_accepts():
    """`_clean_payload` whitelists, so a field named wrongly is dropped in
    silence and the draft arrives blank."""
    for field in ('title', 'text', 'topic_summary'):
        assert field in training_overlay.EDITABLE_FIELDS
