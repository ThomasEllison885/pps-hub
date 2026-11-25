"""Live roster rules — role required, retired people stay out of USERS.

Run: python -m pytest tests/test_roster.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import roster


def test_every_live_user_has_a_role_and_email():
    import app as hub
    errors = roster.validate_users(hub.USERS)
    assert errors == [], errors


def test_harrison_hollon_has_a_pipeline_with_nick():
    import app as hub
    import pipeline_board as pb
    import user_aliases
    person = hub.USERS['harrison_hollon']
    assert person['role'] == 'consultant'
    assert person['tier'] == 'team'
    assert person['email'] == 'harrison@purepropsolutions.com'
    assert person['display'] == 'Harrison Hollon'
    assert person['phone'] == '614-975-0376'
    assert hub.PROPOSAL_NUMBER_INITIALS['harrison_hollon'] == 'HH'
    assert hub.CONSULTANTS['harrison_hollon'] == 'Harrison Hollon'
    assert 'harrison_hollon' in pb.BOARD_CONSULTANTS
    assert pb.PRIMARY_PM_FOR_CONSULTANT['harrison_hollon'] == 'nick_triplett'
    assert user_aliases.CONSULTANT_ALIASES['harrison'] == 'harrison_hollon'
    assert 'harrison_hollon' not in hub.TEAM_DATES


def test_andy_baur_is_a_pm_on_the_live_roster():
    import app as hub
    person = hub.USERS['andy_baur']
    assert person['role'] == 'pm'
    assert person['email'] == 'abaur@purepropsolutions.com'
    assert person['display'] == 'Andy Baur'
    assert person.get('phone') == '937-716-3950'


def test_pm_phones_are_on_the_live_roster():
    import app as hub
    assert hub.USERS['phil_miller'].get('phone')
    assert hub.USERS['nick_triplett'].get('phone')


def test_derek_is_retired_not_live():
    import app as hub
    assert 'derek_kidney' not in hub.USERS
    assert 'derek_kidney' in roster.RETIRED_USER_KEYS


def test_tony_is_retired_not_live():
    import app as hub
    assert 'tony_cumella' not in hub.USERS
    assert 'tony_cumella' in roster.RETIRED_USER_KEYS
    assert 'tony_cumella' not in hub.CONSULTANTS
    assert 'tony_cumella' not in hub.PROPOSAL_NUMBER_INITIALS
    assert 'tony_cumella' not in hub.TEAM_DATES


def test_missing_role_is_rejected():
    bad = {
        'new_hire': {
            'display': 'New Hire',
            'tier': 'team',
            'title': 'Project Manager',
            'email': 'new@example.com',
        }
    }
    errors = roster.validate_users(bad)
    assert any('role' in e for e in errors)


def test_retired_key_cannot_be_put_back():
    bad = {
        'derek_kidney': {
            'display': 'Derek Kidney',
            'role': 'pm',
            'tier': 'team',
            'title': 'Project Manager',
            'email': 'derek@example.com',
        }
    }
    errors = roster.validate_users(bad)
    assert any('retired' in e for e in errors)


def test_demo_guest_is_a_login_and_not_a_person_on_the_roster():
    import app as hub
    person = hub.USERS['demo']
    assert person['role'] == 'guest'
    assert person['display'] == 'Demo'
    assert not person.get('phone')
    assert roster.is_guest(hub.USERS, 'demo') is True
    assert roster.is_guest(hub.USERS, 'rachel_farler') is False
    rows = roster.people_payload(hub.USERS)
    assert all(r['user_key'] != 'demo' for r in rows)
    assert 'demo' in roster.REPORT_OMIT_KEYS
    assert hub.get_user_proposal_access('demo') == []
    assert hub.guest_may_open('dashboard', '/dashboard') is True
    assert hub.guest_may_open('clients', '/clients') is False
    assert hub.guest_may_open(None, '/static/pps-global.css') is True
    client = hub.app.test_client()
    with client.session_transaction() as sess:
        sess['user_key'] = 'demo'
    blocked = client.get('/admin')
    assert blocked.status_code == 302
    assert blocked.headers['Location'].endswith('/dashboard')
    home = client.get('/dashboard')
    assert home.status_code == 200
    assert b'cannot open client' in home.data
    api = client.get('/api/proposals/next-number')
    assert api.status_code == 403


def test_people_payload_skips_nothing_in_users_and_sorts():
    users = {
        'zeta': {'display': 'Zed', 'role': 'pm', 'tier': 'team',
                 'title': 'PM', 'email': 'z@x.com'},
        'alpha': {'display': 'Ann', 'role': 'consultant', 'tier': 'team',
                  'title': 'PSC', 'email': 'a@x.com'},
    }
    rows = roster.people_payload(users)
    assert [r['user_key'] for r in rows] == ['alpha', 'zeta']
