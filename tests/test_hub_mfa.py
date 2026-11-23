"""Owner sign-in code. No Postgres, no email: the DB and mail calls are faked.

Run: python -m pytest tests/test_hub_mfa.py -v
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hub_mfa as mfa

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

USERS = {
    'thomas_ellison': {'display': 'Thomas Ellison', 'email': 'owner@example.com', 'tier': 'owner'},
    'andy_potts': {'display': 'Andy Potts', 'email': 'andy@example.com', 'tier': 'team'},
}


def is_owner(k):
    return USERS.get(k, {}).get('tier') == 'owner'


def test_only_the_owner_needs_a_code(monkeypatch):
    monkeypatch.delenv('HUB_OWNER_SIGNIN_CODE', raising=False)
    assert mfa.required_for(USERS, 'thomas_ellison', is_owner)
    assert not mfa.required_for(USERS, 'andy_potts', is_owner)
    assert not mfa.required_for(USERS, 'nobody', is_owner)


def test_emergency_switch_turns_it_off(monkeypatch):
    monkeypatch.setenv('HUB_OWNER_SIGNIN_CODE', 'off')
    assert not mfa.required_for(USERS, 'thomas_ellison', is_owner)


def test_codes_are_six_digits_and_hashed_with_the_nonce():
    for _ in range(50):
        c = mfa.new_code()
        assert len(c) == 6 and c.isdigit()
    assert mfa.hash_code('n1', '123456') != mfa.hash_code('n2', '123456')
    assert '123456' not in mfa.hash_code('n1', '123456')


def test_phone_formatting_is_forgiven_and_email_is_masked():
    assert mfa.clean_code('123 456') == '123456'
    assert mfa.clean_code('123-456') == '123456'
    assert mfa.mask_email('thomas@purepropsolutions.com') == 't•••••@purepropsolutions.com'


# ── flow, with the DB faked ─────────────────────────────────────────────


@pytest.fixture
def app(monkeypatch):
    from flask import Flask, redirect, session
    monkeypatch.delenv('HUB_OWNER_SIGNIN_CODE', raising=False)
    a = Flask(__name__, template_folder=os.path.join(ROOT, 'templates'))
    a.secret_key = 'test'
    state = {'codes': {}, 'sent': [], 'trusted': set(), 'finished': []}

    def issue(get_db, user_key, nonce):
        state['codes'][user_key] = {'nonce': nonce, 'code': '424242', 'tries': 0,
                                    'sent_at': datetime.now(timezone.utc) - timedelta(minutes=1)}
        return '424242'

    def check(get_db, user_key, nonce, code):
        row = state['codes'].get(user_key)
        if not row or row['nonce'] != nonce:
            return 'gone'
        if mfa.clean_code(code) == row['code']:
            del state['codes'][user_key]
            return 'ok'
        row['tries'] += 1
        if row['tries'] >= mfa.MAX_TRIES:
            del state['codes'][user_key]
            return 'expired'
        return 'wrong'

    monkeypatch.setattr(mfa, 'issue_code', issue)
    monkeypatch.setattr(mfa, 'check_code', check)
    monkeypatch.setattr(mfa, 'last_sent_at', lambda g, u, n: state['codes'].get(u, {}).get('sent_at'))
    monkeypatch.setattr(mfa, 'device_is_trusted', lambda g, u, t, e: t in state['trusted'])
    monkeypatch.setattr(mfa, 'remember_device', lambda g, u, e, l: state['trusted'].add('tok') or 'tok')
    monkeypatch.setattr(mfa, 'send_code_email',
                        lambda fn, email, code, ip, agent: state['sent'].append((email, code)) or True)

    def finish(user_key, db_user):
        session['user_key'] = user_key
        state['finished'].append(user_key)
        return redirect('/dashboard')

    start = mfa.register_routes(a, lambda: None, USERS, None, finish, lambda k: {'password_epoch': 3})

    @a.route('/login', methods=['GET', 'POST'])
    def login():
        return start('thomas_ellison', {'password_epoch': 3})

    @a.route('/dashboard')
    def dashboard():
        return 'dash'

    a.state = state
    return a


def test_password_then_code_signs_in_and_remembers_the_device(app):
    c = app.test_client()
    r = c.post('/login')
    assert r.headers['Location'].endswith('/login/verify')
    assert app.state['sent'] == [('owner@example.com', '424242')]
    with c.session_transaction() as s:
        assert 'user_key' not in s
    r = c.post('/login/verify', data={'code': '424 242', 'remember': '1'})
    assert r.headers['Location'].endswith('/dashboard')
    assert app.state['finished'] == ['thomas_ellison']
    assert 'pps_device=tok' in r.headers['Set-Cookie']
    assert 'HttpOnly' in r.headers['Set-Cookie']


def test_a_remembered_device_skips_the_code(app):
    app.state['trusted'].add('tok')
    c = app.test_client()
    c.set_cookie('pps_device', 'tok')
    r = c.post('/login')
    assert r.headers['Location'].endswith('/dashboard')
    assert app.state['sent'] == []


def test_wrong_code_does_not_sign_in_and_five_wrong_starts_over(app):
    c = app.test_client()
    c.post('/login')
    r = c.post('/login/verify', data={'code': '000000'})
    assert r.status_code == 200 and b'not right' in r.data
    for _ in range(mfa.MAX_TRIES - 1):
        r = c.post('/login/verify', data={'code': '000000'})
    assert r.headers['Location'].endswith('/login')
    assert app.state['finished'] == []
    r = c.post('/login/verify', data={'code': '424242'})
    assert r.headers['Location'].endswith('/login')
    assert app.state['finished'] == []


def test_verify_without_a_password_step_goes_back_to_login(app):
    r = app.test_client().post('/login/verify', data={'code': '424242'})
    assert r.headers['Location'].endswith('/login')


def test_not_remembering_sets_no_cookie(app):
    c = app.test_client()
    c.post('/login')
    r = c.post('/login/verify', data={'code': '424242'})
    assert 'pps_device' not in (r.headers.get('Set-Cookie') or '')


def test_new_codes_are_capped_per_password(app):
    c = app.test_client()
    c.post('/login')
    for _ in range(mfa.MAX_SENDS - 1):
        r = c.post('/login/verify/resend')
        assert r.status_code == 200
    r = c.post('/login/verify/resend')
    assert r.headers['Location'].endswith('/login')


def test_app_sends_only_the_owner_through_the_code():
    text = open(os.path.join(ROOT, 'app.py'), encoding='utf-8').read()
    assert 'hub_mfa.required_for(USERS, user_key, is_owner)' in text
    assert text.count('_establish_session(') == 2  # the def and _finish_login
