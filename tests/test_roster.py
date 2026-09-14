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


def test_andy_baur_is_a_pm_on_the_live_roster():
    import app as hub
    person = hub.USERS['andy_baur']
    assert person['role'] == 'pm'
    assert person['email'] == 'abaur@purepropsolutions.com'
    assert person['display'] == 'Andy Baur'


def test_derek_is_retired_not_live():
    import app as hub
    assert 'derek_kidney' not in hub.USERS
    assert 'derek_kidney' in roster.RETIRED_USER_KEYS


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


def test_people_payload_skips_nothing_in_users_and_sorts():
    users = {
        'zeta': {'display': 'Zed', 'role': 'pm', 'tier': 'team',
                 'title': 'PM', 'email': 'z@x.com'},
        'alpha': {'display': 'Ann', 'role': 'consultant', 'tier': 'team',
                  'title': 'PSC', 'email': 'a@x.com'},
    }
    rows = roster.people_payload(users)
    assert [r['user_key'] for r in rows] == ['alpha', 'zeta']
