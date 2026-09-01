"""What Ask PPS actually puts in front of the model, and whether anyone can tell.

Run: python -m pytest tests/test_ask_pps_context.py -v

Thomas, 2026-08-31: "I dont know how helpful the Ask PPS is."

That turned out to be literally unanswerable. Ask PPS was the only feature in
the Hub recording nothing — `hub_usage.FEATURE_LABELS` has had `'ask_pps'`
since F-03 and no code ever wrote a row, and `/ask-pps` was the one page of
twenty-two without instrumentation. The adoption view showed it as untouched
whether it was being used or not.

Two things are fixed here. One is that; the other is a retrieval bug that made
the answers worse than the knowledge base deserved.

── The retrieval bug ───────────────────────────────────────────────────────

`_retrieve_entries` returns three sets: the FTS matches for the question, and
then **every** `team_directory` and **every** `voice_language` entry, pulled in
whole on every question whatever was asked. `_format_entries_for_prompt` then
walked them in the order `directory + voice + ranked` and **`break`**-ed at
the first block that did not fit in MAX_CONTEXT_CHARS.

Two failures fall out of that, and both are invisible from the outside:

  * As those two always-on categories grow, they push the ranked matches out
    of the context entirely. The assistant then answers "I don't know" while
    the answer sits in an entry it was never shown — and that reply is
    indistinguishable from an honest closed-book miss, which is the whole
    point of the closed-book design.
  * Because it broke rather than skipped, one oversized entry early in the
    list dropped **everything** after it, including small entries that would
    have fitted.

The budget is now split: entries chosen *because of the question* are packed
first and may take the whole budget, the always-on framing takes what is left,
and neither pass stops early — it skips what will not fit and keeps going.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import ask_pps  # noqa: E402
import hub_usage  # noqa: E402


def _entry(category, title, size, always_on, eid=None):
    return {'id': eid if eid is not None else abs(hash((category, title))) % 10**7,
            'category': category, 'title': title,
            'content': 'x' * size, 'always_on': always_on}


def _match(title, size):
    return _entry('production_process', title, size, False)


def _framing(title, size, category='team_directory'):
    return _entry(category, title, size, True)


# ── the answer the question matched must survive ────────────────────────────

def test_a_match_is_not_starved_by_the_always_on_entries():
    """The bug, in one assertion. Directory and voice together overflow the
    budget, so under the old `break` the actual answer never reached the
    model at all."""
    out = ask_pps._format_entries_for_prompt([
        _framing('Who is who', 4000),
        _framing('Tone rules', 3000, 'voice_language'),
        _match('THE ACTUAL ANSWER', 500),
    ])
    assert 'THE ACTUAL ANSWER' in out


def test_matches_are_packed_before_the_framing():
    """Not just included — first. They are the only entries chosen because of
    the question, and the top of the context is read most carefully."""
    out = ask_pps._format_entries_for_prompt([
        _framing('Who is who', 100),
        _match('The answer', 100),
    ])
    assert out.index('The answer') < out.index('Who is who')


def test_the_framing_still_gets_in_when_there_is_room():
    """Splitting the budget must not turn into dropping the directory. Most
    questions retrieve a handful of small entries and everything fits."""
    out = ask_pps._format_entries_for_prompt([
        _framing('Who is who', 200),
        _framing('Tone rules', 200, 'voice_language'),
        _match('The answer', 200),
    ])
    for expected in ('Who is who', 'Tone rules', 'The answer'):
        assert expected in out


def test_one_oversized_entry_does_not_drop_everything_after_it():
    """`break` became `continue`. A single fat entry used to take every
    smaller one with it, whichever pass it was in."""
    out = ask_pps._format_entries_for_prompt([
        _match('Enormous', ask_pps.MAX_CONTEXT_CHARS + 10),
        _match('Small and relevant', 100),
    ])
    assert 'Small and relevant' in out
    assert 'Enormous' not in out


def test_the_budget_is_still_respected():
    out = ask_pps._format_entries_for_prompt(
        [_match(f'M{i}', 1000) for i in range(6)]
        + [_framing(f'F{i}', 1000) for i in range(6)])
    assert len(out) <= ask_pps.MAX_CONTEXT_CHARS + 200, (
        'the split budget became no budget')


def test_nothing_is_included_twice():
    e = _match('Only once', 100)
    out = ask_pps._format_entries_for_prompt([e, e])
    assert out.count('Only once') == 1


def test_no_entries_is_an_empty_block_not_a_crash():
    assert ask_pps._format_entries_for_prompt([]) == ''


def test_untagged_entries_are_treated_as_matches():
    """`always_on` is set by `_retrieve_entries`. Anything reaching this
    function without it — a caller written later, a test — should be treated
    as question-relevant rather than silently demoted to framing."""
    out = ask_pps._format_entries_for_prompt([
        {'id': 1, 'category': 'x', 'title': 'Untagged', 'content': 'y'},
    ])
    assert 'Untagged' in out


# ── it records that it was used ─────────────────────────────────────────────

def test_ask_pps_is_a_known_feature_with_labels_for_what_it_records():
    assert 'ask_pps' in hub_usage.KNOWN_FEATURES
    for action in ('answered', 'unanswered'):
        assert action in hub_usage.ACTION_LABELS, (
            f"an ask recorded as '{action}' would render as a bare word on "
            f'the adoption page')


def test_the_page_and_the_asking_are_both_recorded():
    """Opens alone would say people visit it; asks alone would miss the ones
    who open it and bounce. The gap between the two is the finding."""
    source = open(os.path.join(ROOT, 'ask_pps.py')).read()
    assert "hub_usage.record_usage(get_db_fn, user_key, 'ask_pps', 'open')" in source
    assert "'answered' if answered else 'unanswered'" in source, (
        'the ask is recorded without saying whether the Hub could answer it, '
        'which is the half that names what is undocumented')


def test_asking_a_question_is_not_scored_by_the_weekly_recap():
    """Deliberate. A leaderboard that counts questions teaches people to ask
    questions — the same reason 'open' is excluded."""
    import weekly_recap
    for action in ('answered', 'unanswered', 'open'):
        assert action not in weekly_recap.SCORED_USAGE_ACTIONS


# ── a missing knowledge source is said out loud ─────────────────────────────

def test_the_missing_voice_guide_is_reported():
    """`knowledge_sources/pps_proposal_voice.txt` has never been in this repo.
    `_load_voice_terminology` falls back to a short inline stub *silently*, so
    every answer has been shaped by a fraction of the voice rules with nothing
    saying so — and seeding contributes no voice_language entries at all."""
    if os.path.exists(ask_pps.PROPOSAL_VOICE_PATH):
        pytest.skip('the voice guide is present — nothing to warn about')
    warnings = ask_pps.knowledge_source_warnings()
    assert warnings, 'the voice guide is missing and nothing says so'
    assert 'voice' in warnings[0].lower()


def test_the_warning_reaches_the_curation_page():
    with open(os.path.join(ROOT, 'ask_pps.py')) as fh:
        assert "'source_warnings': knowledge_source_warnings()," in fh.read()
    with open(os.path.join(ROOT, 'templates', 'admin_ask_pps.html')) as fh:
        assert 'source_warnings' in fh.read(), (
            'the warning is computed and never rendered')


def test_no_warning_once_the_file_is_added(tmp_path, monkeypatch):
    real = tmp_path / 'pps_proposal_voice.txt'
    real.write_text('SECTION 1 — UNIVERSAL LANGUAGE RULES\n')
    monkeypatch.setattr(ask_pps, 'PROPOSAL_VOICE_PATH', str(real))
    assert ask_pps.knowledge_source_warnings() == []
