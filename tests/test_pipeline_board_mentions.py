"""@ tagging in Pipeline Board Notes (2026-11-25).

Run: python -m pytest tests/test_pipeline_board_mentions.py -v

Thomas: a way to tag someone that emails them. Type @ in Notes, pick a
person, and when the note saves anyone NEWLY tagged gets one email.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pipeline_board as pb
from test_pipeline_board_history import _db  # noqa: E402

USERS = {
    'thomas_ellison': {'display': 'Thomas Ellison', 'role': 'admin',
                       'email': 'thomas@purepropsolutions.com'},
    'adam_cupito': {'display': 'Adam Cupito', 'role': 'consultant',
                    'email': 'adam@purepropsolutions.com'},
    'andy_potts': {'display': 'Andy Potts', 'role': 'consultant',
                   'email': 'andy@purepropsolutions.com'},
    'andy_baur': {'display': 'Andy Baur', 'role': 'pm',
                  'email': 'abaur@purepropsolutions.com'},
    'rachel_farler': {'display': 'Rachel Farler', 'role': 'consultant',
                      'email': 'rachel@purepropsolutions.com'},
    'demo': {'display': 'Demo', 'role': 'guest', 'email': 'demo@purepropsolutions.com'},
}


def test_full_names_match():
    assert pb.find_mentions('call @Andy Potts today', USERS) == {'andy_potts'}
    assert pb.find_mentions('@andy baur check this', USERS) == {'andy_baur'}


def test_unique_first_name_matches_shared_one_does_not():
    assert pb.find_mentions('@Adam can you look', USERS) == {'adam_cupito'}
    assert pb.find_mentions('@Andy can you look', USERS) == set()


def test_email_addresses_and_longer_words_are_not_tags():
    assert pb.find_mentions('sent to adam@purepropsolutions.com', USERS) == set()
    assert pb.find_mentions('@Adamson Property', USERS) == set()


def test_guest_cannot_be_tagged():
    assert pb.find_mentions('@Demo', USERS) == set()
    assert all(p['key'] != 'demo' for p in pb.mention_people(USERS))


def test_only_new_tags_count_and_never_the_author():
    old = 'Waiting on @Adam Cupito'
    new = 'Waiting on @Adam Cupito, and @Rachel Farler and @Thomas Ellison'
    assert pb.new_mentions(old, new, USERS, 'thomas_ellison') == ['rachel_farler']
    assert pb.new_mentions(new, new, USERS, 'thomas_ellison') == []


def _entry(notes):
    return {'id': 42, 'proposal_number': 'AC26014', 'property_name': 'Cedar Ridge',
            'project': 'Roof repair', 'notes': notes}


def test_notify_sends_one_email_per_new_tag():
    sent = []
    names = pb.notify_mentions(
        lambda subj, text, html, to: sent.append((subj, text, html, to)) or True,
        USERS, 'thomas_ellison', 'adam_cupito',
        _entry('@Adam Cupito and @Rachel Farler please look <b>now</b>'),
        'old note', 'https://hub.purepropsolutions.com/',
        run=lambda fn: fn(),
    )
    assert names == ['Adam Cupito', 'Rachel Farler']
    assert [s[3] for s in sent] == [['adam@purepropsolutions.com'],
                                    ['rachel@purepropsolutions.com']]
    subj, text, html, _ = sent[0]
    assert 'Thomas Ellison tagged you' in subj and 'AC26014' in subj
    assert 'https://hub.purepropsolutions.com/pipeline-board?pair=adam_cupito#row-42' in text
    assert '<b>now</b>' not in html and '&lt;b&gt;now&lt;/b&gt;' in html


def test_notify_does_nothing_without_new_tags_or_mailer():
    calls = []
    run = lambda fn: calls.append(fn)
    assert pb.notify_mentions(lambda *a: True, USERS, 'thomas_ellison', 'adam_cupito',
                              _entry('@Adam'), '@Adam', 'x', run=run) == []
    assert pb.notify_mentions(None, USERS, 'thomas_ellison', 'adam_cupito',
                              _entry('@Adam'), '', 'x', run=run) == []
    assert calls == []


def test_update_entry_hands_back_the_notes_before_the_save():
    store, get_db = _db()
    row = pb.create_entry(get_db, 'rachel_farler', 'rachel_farler')
    pb.update_entry(get_db, row['id'], 'rachel_farler', 'rachel_farler', {'notes': 'first'})
    old = {}
    pb.update_entry(get_db, row['id'], 'rachel_farler', 'rachel_farler',
                    {'notes': 'second @Adam'}, old_out=old)
    assert old == {'notes': 'first'}


def test_save_route_accepts_the_date_and_notes():
    """The Date column shipped with proposal_date missing from this list."""
    src = open(os.path.join(ROOT, 'pipeline_board.py')).read()
    route = src.split('def pipeline_board_update_api', 1)[1].split('@app.route', 1)[0]
    assert '_EDITABLE_DATE_FIELDS' in route
    assert 'notify_mentions' in route


def test_page_wires_the_tag_list_and_the_row_link():
    html = open(os.path.join(ROOT, 'templates', 'pipeline_board.html')).read()
    assert 'MENTION_PEOPLE = {{ mention_people|default([])|tojson }}' in html
    assert re.search(r"field'\) === 'notes'\) handleMentionKey", html)
    assert 'focusRowFromHash();' in html
