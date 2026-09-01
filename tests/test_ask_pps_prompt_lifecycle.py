"""A question's life: asked, unanswered, put to someone, answered, retired.

Run: TEST_DATABASE_URL=postgresql://... python -m pytest tests/test_ask_pps_prompt_lifecycle.py -v

Thomas, 2026-08-31: "the questions aren't that good."

They were about forty hardcoded questions written once — 8 general ops, 11
PSC feedback themes, 5 PM, and 16 scraped from `[TO DOCUMENT]` markers. Nobody
chose them for this week and they cannot respond to anything, so the bank runs
dry per person and never refills.

The better source was already in the database. Every question the assistant
could not answer is logged with a topic and `gap_status='open'` — real
questions, from real people, about things the company has not written down.

Two halves are added here, and together they close a loop that was open at
both ends.

── Half one: put one question to one person ────────────────────────────────

A bulk path already existed (`sync_prompts_from_gaps`): every open gap at
once, aimed at a *role* guessed by keyword regex. That is right for clearing a
backlog and wrong for the common case, which is reading a gap and knowing
exactly whose head the answer is in. A role guess sends "how do we handle a
stalled Monday board" to all five PMs and gets it answered by none of them.

So the gaps queue gains a third option beside "answer it yourself" and
"dismiss". The gap then leaves the open queue as `asked` rather than sitting
there looking undealt-with.

── Half two: retire the question once it is documented ─────────────────────

Answering a prompt never changed its status. It stayed `open` forever, so the
Hub went on asking the team a question it had already been told the answer to,
published, and could answer itself. That is the fastest way to teach people
the prompts are not worth reading.

**Closing happens on approval, not on answering**, and that distinction is the
design. `knowledge_prompt_answers` is `UNIQUE(prompt_id, user_key)` — several
people answering the same question is deliberate, and two accounts of how
something is done are useful right up until one is published. Closing on the
first answer would throw the second away.

`source_gap_id` has been a column on `knowledge_prompts`, with an index, since
the table was created; only the bulk sync ever set it. It is what carries an
approved answer back to the question that prompted it.
"""
import os
import sys
from datetime import datetime, timezone

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DSN = os.environ.get('TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not DSN, reason='TEST_DATABASE_URL not set')

if DSN:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    import ask_pps

USERS = {
    'trey_hollmeyer': {'display': 'Trey Hollmeyer', 'role': 'pm'},
    'andy_potts': {'display': 'Andy Potts', 'role': 'consultant'},
}


@pytest.fixture
def db():
    def get_db():
        return psycopg2.connect(DSN)
    conn = get_db()
    cur = conn.cursor()
    for t in ('knowledge_prompt_answers', 'knowledge_prompt_skips',
              'knowledge_prompts', 'knowledge_entries', 'ask_pps_questions',
              'hub_user_notifications', 'ask_pps_daily_usage'):
        cur.execute(f'DROP TABLE IF EXISTS {t} CASCADE')
    conn.commit()
    cur.close()
    conn.close()
    conn = get_db()
    cur = conn.cursor()
    ask_pps.init_tables(cur)
    conn.commit()
    cur.close()
    conn.close()
    return get_db


def _gap(get_db, question='How do we handle a stalled Monday board?',
         topic='production'):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO ask_pps_questions (user_key, question, answered, "
        "gap_status, gap_topic) VALUES (%s,%s,FALSE,'open',%s) RETURNING id",
        ('andy_potts', question, topic))
    gid = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return gid


def _rows(get_db, sql, args=()):
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql, args)
    out = cur.fetchall()
    cur.close()
    conn.close()
    return out


# ── half one: asking one person ─────────────────────────────────────────────

def test_a_gap_becomes_a_prompt_aimed_at_the_person_named(db):
    gid = _gap(db)
    res = ask_pps.ask_gap_of_person(db, gid, 'trey_hollmeyer', 'thomas_ellison')
    assert res['ok'], res
    prompts = _rows(db, 'SELECT * FROM knowledge_prompts')
    assert len(prompts) == 1
    p = prompts[0]
    assert p['target_user_key'] == 'trey_hollmeyer'
    assert p['question'] == 'How do we handle a stalled Monday board?'
    assert p['source_gap_id'] == gid, (
        'the prompt cannot find its way back to the question that caused it')
    assert p['status'] == 'open'


def test_the_asked_question_leaves_the_open_queue(db):
    """Otherwise it sits in the gaps list looking undealt-with, and gets
    answered by Thomas a second time."""
    gid = _gap(db)
    ask_gap = ask_pps.ask_gap_of_person(db, gid, 'trey_hollmeyer', 'thomas_ellison')
    assert ask_gap['ok']
    row = _rows(db, 'SELECT gap_status FROM ask_pps_questions WHERE id=%s', (gid,))[0]
    assert row['gap_status'] == 'asked'


def test_it_outranks_the_generated_questions(db):
    """Someone asked this out loud and got nothing back. It beats a question
    scraped from a curriculum marker in July."""
    gid = _gap(db)
    ask_pps.ask_gap_of_person(db, gid, 'trey_hollmeyer', 'thomas_ellison')
    p = _rows(db, 'SELECT priority FROM knowledge_prompts')[0]
    assert p['priority'] > 10


def test_asking_twice_does_not_ask_twice(db):
    """A double-click must not put the same question in front of someone
    twice — they would answer it once and see it again."""
    gid = _gap(db)
    ask_pps.ask_gap_of_person(db, gid, 'trey_hollmeyer', 'thomas_ellison')
    second = ask_pps.ask_gap_of_person(db, gid, 'trey_hollmeyer', 'thomas_ellison')
    assert second['ok'] and second.get('already')
    assert len(_rows(db, 'SELECT id FROM knowledge_prompts')) == 1


def test_a_gap_that_does_not_exist_is_refused(db):
    assert not ask_pps.ask_gap_of_person(db, 99999, 'trey_hollmeyer', 'x')['ok']


def test_the_person_it_was_aimed_at_is_the_one_who_sees_it(db):
    """`target_user_key` beats every other weighting in the deck — the whole
    point of naming someone."""
    gid = _gap(db)
    ask_pps.ask_gap_of_person(db, gid, 'trey_hollmeyer', 'thomas_ellison')
    for_trey = ask_pps.get_prompts_for_user(db, USERS, 'trey_hollmeyer', 'pm')
    assert any(p['question'].startswith('How do we handle') for p in for_trey)


# ── half two: retiring it once documented ───────────────────────────────────

def _answer_and_approve(get_db, prompt_id, user_key='trey_hollmeyer'):
    body, _status = ask_pps.submit_prompt_answer(
        get_db, USERS, user_key, USERS[user_key]['role'], prompt_id,
        'You reassign the card and note it in the weekly.')
    assert body.get('success'), body
    entry = _rows(get_db,
                  "SELECT id FROM knowledge_entries WHERE status='pending' "
                  "ORDER BY id DESC LIMIT 1")[0]
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("UPDATE knowledge_entries SET status='active' WHERE id=%s",
                (entry['id'],))
    ask_pps.close_prompt_for_entry(cur, entry['id'])
    conn.commit()
    cur.close()
    conn.close()
    return entry['id']


def test_answering_alone_does_not_close_the_prompt(db):
    """Several people answering one question is deliberate — two accounts are
    useful right up until one is published."""
    gid = _gap(db)
    ask_pps.ask_gap_of_person(db, gid, 'trey_hollmeyer', 'thomas_ellison')
    pid = _rows(db, 'SELECT id FROM knowledge_prompts')[0]['id']
    ask_pps.submit_prompt_answer(db, USERS, 'trey_hollmeyer', 'pm', pid,
                                 'An answer that has not been approved yet.')
    assert _rows(db, 'SELECT status FROM knowledge_prompts')[0]['status'] == 'open'


def test_approving_the_answer_retires_the_question(db):
    gid = _gap(db)
    ask_pps.ask_gap_of_person(db, gid, 'trey_hollmeyer', 'thomas_ellison')
    pid = _rows(db, 'SELECT id FROM knowledge_prompts')[0]['id']
    _answer_and_approve(db, pid)
    assert _rows(db, 'SELECT status FROM knowledge_prompts')[0]['status'] == 'answered'


def test_a_retired_question_stops_being_served(db):
    """The symptom that matters: the Hub asking the team something it has been
    told, has published, and can now answer itself."""
    gid = _gap(db)
    ask_pps.ask_gap_of_person(db, gid, 'trey_hollmeyer', 'thomas_ellison',
                              target_role='any')
    pid = _rows(db, 'SELECT id FROM knowledge_prompts')[0]['id']
    _answer_and_approve(db, pid)
    for who, role in (('andy_potts', 'consultant'), ('trey_hollmeyer', 'pm')):
        served = ask_pps.get_prompts_for_user(db, USERS, who, role)
        assert not any(p['id'] == pid for p in served), (
            f'{who} is still being asked a documented question')


def test_approving_resolves_the_gap_it_came_from(db):
    """The loop closing: a real question someone asked is marked answered when
    the answer is published, and points at the entry that answers it."""
    gid = _gap(db)
    ask_pps.ask_gap_of_person(db, gid, 'trey_hollmeyer', 'thomas_ellison')
    pid = _rows(db, 'SELECT id FROM knowledge_prompts')[0]['id']
    entry_id = _answer_and_approve(db, pid)
    gap = _rows(db, 'SELECT gap_status, resolved_entry_id FROM ask_pps_questions '
                    'WHERE id=%s', (gid,))[0]
    assert gap['gap_status'] == 'resolved'
    assert gap['resolved_entry_id'] == entry_id


def test_closing_a_prompt_with_no_gap_behind_it_is_fine(db):
    """Most prompts are generated and have no source_gap_id. Approving one of
    those must not error looking for a gap to resolve."""
    conn = db()
    cur = conn.cursor()
    ask_pps._create_prompt(cur, 'A generated question?', 'general', 'any',
                           'field', 'audit_gap', 'thomas_ellison',
                           source_ref='audit:1')
    conn.commit()
    cur.close()
    conn.close()
    pid = _rows(db, 'SELECT id FROM knowledge_prompts')[0]['id']
    _answer_and_approve(db, pid)
    assert _rows(db, 'SELECT status FROM knowledge_prompts')[0]['status'] == 'answered'


def test_an_entry_with_no_prompt_behind_it_is_fine(db):
    """Curators add entries directly. Approving one must not go looking for a
    prompt that never existed."""
    conn = db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("INSERT INTO knowledge_entries "
                "(category, title, content, status, source_type) "
                "VALUES ('general','T','C','pending','admin') RETURNING id")
    eid = cur.fetchone()['id']
    assert ask_pps.close_prompt_for_entry(cur, eid) is None
    conn.commit()
    cur.close()
    conn.close()
