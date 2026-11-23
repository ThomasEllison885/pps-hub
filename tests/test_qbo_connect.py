"""QuickBooks connect: OAuth, encrypted token storage, owner-only page.

No network and no Postgres. Run: python -m pytest tests/test_qbo_connect.py -v
"""
import os
import sys
from datetime import datetime, timezone
from functools import wraps
from urllib.parse import parse_qs, urlparse

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import qbo_connect as qbo
from cryptography.fernet import Fernet

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PLAIN_ACCESS = 'access-token-plain'
PLAIN_REFRESH = 'refresh-token-plain'


@pytest.fixture
def fernet_env(monkeypatch):
    monkeypatch.setenv('QBO_CLIENT_ID', 'client-id')
    monkeypatch.setenv('QBO_CLIENT_SECRET', 'client-secret')
    monkeypatch.setenv('QBO_TOKEN_KEY', Fernet.generate_key().decode('ascii'))
    monkeypatch.setenv('QBO_ENVIRONMENT', 'sandbox')
    monkeypatch.setenv('QBO_REDIRECT_URI', 'https://hub.purepropsolutions.com/qbo/callback')


def test_environment_defaults_to_sandbox(monkeypatch):
    monkeypatch.delenv('QBO_ENVIRONMENT', raising=False)
    assert qbo.environment() == 'sandbox'
    monkeypatch.setenv('QBO_ENVIRONMENT', 'prod')
    assert qbo.environment() == 'sandbox'
    monkeypatch.setenv('QBO_ENVIRONMENT', 'production')
    assert qbo.environment() == 'production'


def test_api_host_follows_the_stored_environment_not_the_env_var(monkeypatch):
    monkeypatch.setenv('QBO_ENVIRONMENT', 'production')
    assert qbo.api_base_for('sandbox') == qbo.SANDBOX_API_BASE
    monkeypatch.setenv('QBO_ENVIRONMENT', 'sandbox')
    assert qbo.api_base_for('production') == qbo.PRODUCTION_API_BASE


def test_missing_settings_names_the_variable_and_not_the_value(monkeypatch):
    monkeypatch.delenv('QBO_CLIENT_ID', raising=False)
    monkeypatch.delenv('QBO_CLIENT_SECRET', raising=False)
    monkeypatch.delenv('QBO_TOKEN_KEY', raising=False)
    monkeypatch.setenv('QBO_REDIRECT_URI', 'https://hub.purepropsolutions.com/qbo/callback')
    missing = qbo.missing_settings()
    assert missing == ['QBO_CLIENT_ID', 'QBO_CLIENT_SECRET', 'QBO_TOKEN_KEY']
    assert 'client-secret' not in ' '.join(missing)


def test_a_bad_fernet_key_is_the_same_missing_setting(monkeypatch):
    monkeypatch.setenv('QBO_CLIENT_ID', 'client-id')
    monkeypatch.setenv('QBO_CLIENT_SECRET', 'client-secret')
    monkeypatch.setenv('QBO_TOKEN_KEY', 'not-a-key')
    monkeypatch.setenv('QBO_REDIRECT_URI', 'https://hub.purepropsolutions.com/qbo/callback')
    assert qbo.missing_settings() == ['QBO_TOKEN_KEY']


def test_redirect_uri_must_be_https_or_localhost(monkeypatch):
    monkeypatch.setenv('QBO_CLIENT_ID', 'client-id')
    monkeypatch.setenv('QBO_CLIENT_SECRET', 'client-secret')
    monkeypatch.setenv('QBO_TOKEN_KEY', Fernet.generate_key().decode('ascii'))
    monkeypatch.setenv('QBO_REDIRECT_URI', 'http://evil.example/qbo/callback')
    assert 'QBO_REDIRECT_URI' in qbo.missing_settings()
    monkeypatch.setenv('QBO_REDIRECT_URI', 'http://localhost:5000/qbo/callback')
    assert qbo.missing_settings() == []


def test_authorize_url_carries_the_accounting_scope_and_not_the_secret(fernet_env):
    url = qbo.build_authorize_url('state-value')
    parts = urlparse(url)
    query = parse_qs(parts.query)
    assert parts.scheme + '://' + parts.netloc + parts.path == qbo.AUTH_URL
    assert query['scope'] == [qbo.SCOPE]
    assert 'payment' not in query['scope'][0]
    assert query['client_id'] == ['client-id']
    assert query['state'] == ['state-value']
    assert query['redirect_uri'] == ['https://hub.purepropsolutions.com/qbo/callback']
    assert 'client-secret' not in url


def test_token_request_uses_basic_auth_and_does_not_follow_redirects(fernet_env, monkeypatch):
    seen = {}

    class Resp:
        status_code = 200

        def json(self):
            return {
                'access_token': PLAIN_ACCESS,
                'refresh_token': PLAIN_REFRESH,
                'expires_in': 3600,
                'x_refresh_token_expires_in': 8000000,
                'token_type': 'bearer',
            }

    def fake_post(url, data=None, auth=None, headers=None, timeout=None, follow_redirects=None):
        seen['url'] = url
        seen['data'] = dict(data)
        seen['auth'] = auth
        seen['follow'] = follow_redirects
        return Resp()

    monkeypatch.setattr(qbo.httpx, 'post', fake_post)
    payload = qbo.exchange_code('auth-code-1')
    assert seen['url'] == qbo.TOKEN_URL
    assert seen['follow'] is False
    assert seen['auth'] == ('client-id', 'client-secret')
    assert seen['data']['grant_type'] == 'authorization_code'
    assert 'client_secret' not in seen['data']
    assert payload['access_token'] == PLAIN_ACCESS
    assert payload['refresh_token'] == PLAIN_REFRESH


def test_a_refused_token_does_not_echo_the_response_body(fernet_env, monkeypatch):
    class Resp:
        status_code = 400
        text = 'access_token=' + PLAIN_ACCESS + ' client-secret'

        def json(self):
            return {'error': 'invalid_grant', 'access_token': PLAIN_ACCESS}

    monkeypatch.setattr(qbo.httpx, 'post', lambda *a, **k: Resp())
    with pytest.raises(qbo.QboAuthError) as caught:
        qbo.exchange_code('auth-code-1')
    message = str(caught.value)
    assert 'invalid_grant' in message
    assert PLAIN_ACCESS not in message
    assert 'client-secret' not in message


def test_refresh_keeps_the_old_token_when_intuit_omits_the_new_one(fernet_env, monkeypatch):
    class Resp:
        status_code = 200

        def json(self):
            return {'access_token': 'next-access', 'expires_in': 3600}

    monkeypatch.setattr(qbo.httpx, 'post', lambda *a, **k: Resp())
    payload = qbo.refresh_tokens('previous-refresh')
    assert payload['access_token'] == 'next-access'
    assert payload['refresh_token'] == 'previous-refresh'


def test_refresh_stores_the_rotated_token(fernet_env, monkeypatch):
    class Resp:
        status_code = 200

        def json(self):
            return {
                'access_token': 'next-access',
                'refresh_token': 'rotated-refresh',
                'expires_in': 3600,
            }

    monkeypatch.setattr(qbo.httpx, 'post', lambda *a, **k: Resp())
    payload = qbo.refresh_tokens('previous-refresh')
    assert payload['refresh_token'] == 'rotated-refresh'


class _Conn:
    def __init__(self):
        self.statements = []
        self.committed = False
        self.closed = False

    def cursor(self, cursor_factory=None):
        conn = self

        class Cur:
            def execute(self, sql, args=None):
                conn.statements.append((' '.join(sql.split()), args))

            def close(self):
                pass

            rowcount = 1

        return Cur()

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        self.closed = True


def test_save_writes_ciphertext_and_closes_the_connection(fernet_env):
    conn = _Conn()
    qbo.save_connection(
        lambda: conn,
        '9341453222',
        {
            'access_token': PLAIN_ACCESS,
            'refresh_token': PLAIN_REFRESH,
            'expires_in': 3600,
            'refresh_expires_in': 8000000,
        },
        'thomas_ellison',
    )
    sql, args = conn.statements[0]
    blob = ' '.join(str(part) for part in args)
    assert 'access_token_enc' in sql
    assert PLAIN_ACCESS not in blob
    assert PLAIN_REFRESH not in blob
    assert qbo.decrypt_secret(args[2]) == PLAIN_ACCESS
    assert qbo.decrypt_secret(args[3]) == PLAIN_REFRESH
    assert args[0] == '9341453222'
    assert args[1] == 'sandbox'
    assert conn.committed and conn.closed


def test_save_refuses_without_a_key_and_does_not_touch_the_database(monkeypatch):
    monkeypatch.delenv('QBO_TOKEN_KEY', raising=False)
    conn = _Conn()
    with pytest.raises(qbo.QboConfigError):
        qbo.save_connection(
            lambda: conn,
            '9341453222',
            {'access_token': PLAIN_ACCESS, 'refresh_token': PLAIN_REFRESH, 'expires_in': 3600},
            'thomas_ellison',
        )
    assert conn.statements == []


def test_replace_tokens_updates_the_pair_and_not_the_company(fernet_env):
    conn = _Conn()
    qbo.replace_tokens(lambda: conn, {
        'access_token': 'next-access',
        'refresh_token': 'rotated-refresh',
        'expires_in': 3600,
        'refresh_expires_in': None,
    })
    sql, args = conn.statements[0]
    assert sql.startswith('UPDATE qbo_connection')
    assert 'realm_id' not in sql
    assert 'connected_at' not in sql
    assert qbo.decrypt_secret(args[0]) == 'next-access'
    assert qbo.decrypt_secret(args[1]) == 'rotated-refresh'


def test_public_status_does_not_select_the_token_columns(fernet_env):
    class Conn:
        def __init__(self):
            self.sql = ''
            self.closed = False

        def cursor(self, cursor_factory=None):
            outer = self

            class C:
                def execute(self, sql, args=None):
                    outer.sql = ' '.join(sql.split())

                def fetchone(self):
                    return None

                def close(self):
                    pass

            return C()

        def close(self):
            self.closed = True

    conn = Conn()
    status = qbo.public_status(lambda: conn)
    assert 'token_enc' not in conn.sql
    assert set(status) == qbo.PUBLIC_STATUS_KEYS
    assert status['connected'] is False
    joined = ' '.join(str(v) for v in status.values())
    assert PLAIN_ACCESS not in joined
    assert conn.closed


def test_load_tokens_decrypts_and_public_status_cannot_see_them(fernet_env):
    access_enc = qbo.encrypt_secret(PLAIN_ACCESS)
    refresh_enc = qbo.encrypt_secret(PLAIN_REFRESH)
    row = {
        'realm_id': '9341453222',
        'environment': 'sandbox',
        'access_token_enc': access_enc,
        'refresh_token_enc': refresh_enc,
        'access_expires_at': datetime(2026, 11, 23, tzinfo=timezone.utc),
        'refresh_expires_at': None,
        'connected_by': 'thomas_ellison',
        'connected_at': None,
        'updated_at': None,
        'last_error': None,
        'last_error_at': None,
    }

    class Conn:
        def __init__(self, columns):
            self.columns = columns
            self.closed = False

        def cursor(self, cursor_factory=None):
            outer = self

            class C:
                def execute(self, sql, args=None):
                    self.sql = sql

                def fetchone(self):
                    return {key: row[key] for key in outer.columns}

                def close(self):
                    pass

            return C()

        def close(self):
            self.closed = True

    loaded = qbo.load_tokens(lambda: Conn([
        'realm_id', 'environment', 'access_token_enc', 'refresh_token_enc', 'access_expires_at',
    ]))
    assert loaded['access_token'] == PLAIN_ACCESS
    assert loaded['refresh_token'] == PLAIN_REFRESH

    status = qbo.public_status(lambda: Conn([
        'realm_id', 'environment', 'access_expires_at', 'refresh_expires_at',
        'connected_by', 'connected_at', 'updated_at', 'last_error', 'last_error_at',
    ]))
    assert status['connected'] is True
    assert status['realm_id'] == '9341453222'
    assert 'access_token' not in status
    assert PLAIN_ACCESS not in ' '.join(str(v) for v in status.values())


def test_callback_rejects_a_mismatched_state_without_calling_intuit(fernet_env, monkeypatch):
    def explode(*a, **k):
        raise AssertionError('Intuit was called')

    monkeypatch.setattr(qbo.httpx, 'post', explode)
    notice = qbo.callback_notice(
        {'code': 'auth-code-1', 'state': 'other', 'realmId': '9341453222'},
        'expected-state-value',
        'thomas_ellison',
        lambda: _Conn(),
    )
    assert notice == 'state'


def test_callback_saves_a_matching_grant(fernet_env, monkeypatch):
    monkeypatch.setattr(qbo, 'exchange_code', lambda code: {
        'access_token': PLAIN_ACCESS,
        'refresh_token': PLAIN_REFRESH,
        'expires_in': 3600,
        'refresh_expires_in': 8000000,
    })
    conn = _Conn()
    notice = qbo.callback_notice(
        {'code': 'auth-code-1', 'state': 'expected-state', 'realmId': '9341453222'},
        'expected-state',
        'thomas_ellison',
        lambda: conn,
    )
    assert notice == 'connected'
    assert conn.statements[0][1][0] == '9341453222'
    assert PLAIN_ACCESS not in ' '.join(str(p) for p in conn.statements[0][1])


def test_module_posts_only_to_the_token_endpoint():
    """The accounting scope can write. One POST, and it is the token address.

    The one GET is accounting_get. Nothing else in this repo calls Intuit.
    """
    text = open(os.path.join(ROOT, 'qbo_connect.py'), encoding='utf-8').read()
    assert text.count('httpx.post') == 1
    assert text.count('httpx.get') == 1
    assert 'httpx.put' not in text
    assert 'httpx.patch' not in text
    assert 'httpx.delete' not in text
    assert 'httpx.request' not in text
    assert 'httpx.Client' not in text
    assert qbo.TOKEN_URL in text
    skip = {'.git', '.venv', 'venv', '__pycache__', 'tests'}
    for dirpath, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in skip and not d.startswith('.')]
        for name in files:
            if not name.endswith('.py') or name == 'qbo_connect.py':
                continue
            body = open(os.path.join(dirpath, name), encoding='utf-8').read()
            assert 'quickbooks.api.intuit.com' not in body, name
            assert 'oauth.platform.intuit.com' not in body, name


def test_accounting_get_is_a_get_against_the_company(monkeypatch):
    seen = {}

    class Resp:
        status_code = 200

    def fake_get(url, **kwargs):
        seen['url'] = url
        seen['params'] = kwargs.get('params')
        seen['follow'] = kwargs.get('follow_redirects')
        return Resp()

    monkeypatch.setattr(qbo.httpx, 'get', fake_get)
    monkeypatch.setattr(qbo.httpx, 'post', lambda *a, **k: (_ for _ in ()).throw(AssertionError('post')))
    resp = qbo.accounting_get(
        'sandbox', '9341453222', 'query',
        params={'query': "SELECT * FROM Invoice"},
        headers={'Authorization': 'Bearer secret-token'},
    )
    assert resp.status_code == 200
    assert seen['url'] == 'https://sandbox-quickbooks.api.intuit.com/v3/company/9341453222/query'
    assert seen['params']['query'].startswith('SELECT')
    assert seen['params']['minorversion'] == str(qbo.MINOR_VERSION)
    assert seen['follow'] is False
    assert 'secret-token' not in seen['url']


def test_accounting_calls_that_write_are_refused(monkeypatch):
    def explode(*a, **k):
        raise AssertionError('Intuit was called')

    monkeypatch.setattr(qbo.httpx, 'get', explode)
    monkeypatch.setattr(qbo.httpx, 'post', explode)
    blocked = (
        ('sandbox', '12', 'batch'),
        ('sandbox', '12', 'invoice/9?operation=delete'),
        ('sandbox', 'not-a-realm', 'invoice/9'),
        ('elsewhere', '12', 'invoice/9'),
        ('sandbox', '12', 'https://quickbooks.api.intuit.com/v3/company/12/invoice'),
        ('sandbox', '12', '../invoice'),
    )
    for env, realm, path in blocked:
        try:
            qbo.accounting_get(env, realm, path)
        except qbo.QboWriteBlocked:
            continue
        raise AssertionError(f'allowed {env} {realm} {path}')
    try:
        qbo.accounting_get('sandbox', '12', 'invoice/9', params={'operation': 'delete'})
    except qbo.QboWriteBlocked:
        pass
    else:
        raise AssertionError('operation=delete was allowed')
    try:
        qbo._post_token({'grant_type': 'client_credentials'})
    except qbo.QboWriteBlocked:
        pass
    else:
        raise AssertionError('a third grant type was allowed')


def _app():
    from flask import Flask, session
    import hub_time

    app = Flask(__name__, template_folder=os.path.join(ROOT, 'templates'))
    app.secret_key = 'test'

    def require_admin(fn):
        @wraps(fn)
        def inner(*args, **kwargs):
            if session.get('user_key') != 'thomas_ellison':
                return 'forbidden', 403
            return fn(*args, **kwargs)
        return inner

    qbo.register_routes(app, lambda: None, require_admin)
    hub_time.register(app)
    return app


def _signed_in(app, owner=True):
    client = app.test_client()
    if owner:
        with client.session_transaction() as sess:
            sess['user_key'] = 'thomas_ellison'
    return client


def test_the_page_is_owner_only_and_renders_no_token(fernet_env):
    app = _app()
    assert _signed_in(app, owner=False).get('/admin/quickbooks').status_code == 403
    page = _signed_in(app).get('/admin/quickbooks')
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert 'Connect QuickBooks' in body
    assert 'https://hub.purepropsolutions.com/qbo/callback' in body
    assert 'access_token' not in body
    assert 'refresh_token' not in body
    assert 'client-secret' not in body
    assert page.headers['Cache-Control'] == 'no-store'


def test_connect_redirects_to_intuit_and_remembers_the_state(fernet_env):
    app = _app()
    client = _signed_in(app)
    resp = client.get('/admin/quickbooks/connect')
    assert resp.status_code == 302
    location = resp.headers['Location']
    assert location.startswith(qbo.AUTH_URL)
    assert 'client-secret' not in location
    with client.session_transaction() as sess:
        state = sess[qbo.SESSION_STATE_KEY]
    assert parse_qs(urlparse(location).query)['state'] == [state]


def test_callback_clears_the_state_and_a_mismatch_does_not_save(fernet_env, monkeypatch):
    monkeypatch.setattr(qbo.httpx, 'post', lambda *a, **k: (_ for _ in ()).throw(AssertionError('called')))
    app = _app()
    client = _signed_in(app)
    with client.session_transaction() as sess:
        sess[qbo.SESSION_STATE_KEY] = 'expected-state'
    resp = client.get('/qbo/callback?code=auth-code-1&state=nope&realmId=9341453222')
    assert resp.status_code == 302
    assert 'notice=state' in resp.headers['Location']
    with client.session_transaction() as sess:
        assert qbo.SESSION_STATE_KEY not in sess


def test_disconnect_is_owner_only(fernet_env, monkeypatch):
    called = {}
    monkeypatch.setattr(qbo, 'delete_connection', lambda get_db: called.setdefault('yes', True))
    app = _app()
    stranger = _signed_in(app, owner=False)
    assert stranger.post('/admin/quickbooks/disconnect').status_code == 403
    assert called == {}
    owner = _signed_in(app)
    resp = owner.post('/admin/quickbooks/disconnect')
    assert resp.status_code == 302
    assert 'notice=disconnected' in resp.headers['Location']
    assert called == {'yes': True}


def test_routes_on_the_real_app_are_owner_gated():
    """Importing app runs migrations, so this reads the source instead."""
    text = open(os.path.join(ROOT, 'qbo_connect.py'), encoding='utf-8').read()
    app_text = open(os.path.join(ROOT, 'app.py'), encoding='utf-8').read()
    for route in ('/admin/quickbooks', '/admin/quickbooks/connect', '/qbo/callback',
                  '/admin/quickbooks/disconnect'):
        assert route in text
    assert text.count('@require_admin') == 4
    assert 'qbo_connect.register_routes(app, get_db, require_admin)' in app_text
    assert 'qbo_connect.init_tables(cur)' in app_text
