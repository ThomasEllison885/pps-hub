"""QuickBooks Online connection for the Hub. Step 1: connect, callback, tokens.

Thomas, 2026-11-23. Live invoiced sales on the dashboard, read from our own
tables. This module is only the OAuth grant and the place the tokens live.
The nightly pull is ``qbo_sync.py``. Goals and the numbers above Jump back
in come later.

What is already decided, so the next step does not relitigate it:

- Sync once a night at midnight US/Eastern, not hourly. The cron fires at
  04:00 and 05:00 UTC and the job runs only when the Eastern hour is 0, so
  daylight saving does not slide it off midnight. Under the numbers, in
  smaller type: "Updated each night at midnight."
- The numbers sit above Jump back in on the dashboard.
- Goals wait until Thomas sends the figures. Do not seed the 2026 books.
- Sandbox first. ``QBO_ENVIRONMENT`` defaults to sandbox. Production is a
  later switch, after Intuit's questionnaire.
- Read only. Intuit's accounting scope can write, and Intuit will not
  issue a read-only one. ``accounting_get`` is the only accounting call,
  and it is GET only. The token POST goes to the token address and does
  not change a QuickBooks record. A test locks both.

Tokens are Fernet-encrypted with ``QBO_TOKEN_KEY`` before they touch
Postgres. The status page selects every column except the two ciphertext
columns, so a template cannot print a token by accident. Nothing in this
file logs a token, a client secret, or an authorization code.
"""

from __future__ import annotations

import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken
from psycopg2.extras import RealDictCursor

AUTH_URL = 'https://appcenter.intuit.com/connect/oauth2'
TOKEN_URL = 'https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer'
SCOPE = 'com.intuit.quickbooks.accounting'
SANDBOX_API_BASE = 'https://sandbox-quickbooks.api.intuit.com'
PRODUCTION_API_BASE = 'https://quickbooks.api.intuit.com'
# Pinned. Intuit retired minor versions 1–74; an unpinned request is 75.
MINOR_VERSION = 75

SESSION_STATE_KEY = 'qbo_oauth_state'

# The status dict is an allowlist. Adding a key is a decision, because this
# dict is what the template receives.
PUBLIC_STATUS_KEYS = frozenset({
    'connected',
    'environment',
    'realm_id',
    'connected_by',
    'connected_at',
    'updated_at',
    'access_expires_at',
    'refresh_expires_at',
    'last_error',
    'last_error_at',
    'problems',
    'redirect_uri',
})

NOTICES = {
    'connected': 'QuickBooks is connected. The tokens are stored on the server.',
    'disconnected': 'QuickBooks is disconnected. The stored tokens were deleted.',
    'denied': 'QuickBooks access was not granted.',
    'state': 'That connect attempt expired. Start again.',
    'token': 'QuickBooks did not return a token. Start again.',
    'config': 'QuickBooks is not configured on the server yet. The missing settings are listed below.',
    'realm': 'QuickBooks did not send a company id. Start again.',
    'save': 'The token came back, and it could not be saved. Nothing was stored. Start again.',
    'synced': 'Sync finished. The totals below are what the dashboard will read.',
    'sync_failed': 'The sync did not finish. The last good numbers were kept. The problem is listed below.',
    'mapped': 'Saved. The match applies right away, with no new sync.',
    'map_bad': 'That match could not be saved.',
}

OK_NOTICES = frozenset({'connected', 'disconnected', 'synced', 'mapped'})

_CODE_RE = re.compile(r'^[A-Za-z0-9._~-]{8,2048}$')
_REALM_RE = re.compile(r'^[0-9]{1,20}$')
_SAFE_OAUTH_ERROR = re.compile(r'^[A-Za-z0-9_]{1,40}$')


class QboConfigError(Exception):
    """A setting is missing or unusable. The message names the setting, never its value."""


class QboAuthError(Exception):
    """Intuit refused or did not answer. The message is safe to show the owner."""


class QboWriteBlocked(Exception):
    """A call would create, change, or delete a QuickBooks record."""


def environment():
    """Where new grants are stored. Anything other than production is sandbox.

    A typo must not point the Hub at the live company.
    """
    raw = (os.environ.get('QBO_ENVIRONMENT') or '').strip().lower()
    if raw == 'production':
        return 'production'
    return 'sandbox'


def api_base_for(environment_name):
    """API host for a stored connection. The env var does not override a row.

    A sandbox grant kept working after someone flips ``QBO_ENVIRONMENT`` is
    worse than a sync that refuses. Callers pass the value from the row.
    """
    if environment_name == 'production':
        return PRODUCTION_API_BASE
    return SANDBOX_API_BASE


def redirect_uri():
    explicit = (os.environ.get('QBO_REDIRECT_URI') or '').strip()
    if explicit:
        return explicit
    base = (os.environ.get('HUB_PUBLIC_URL') or 'https://hub.purepropsolutions.com').rstrip('/')
    return base + '/qbo/callback'


def _redirect_uri_allowed(uri):
    parts = urlparse(uri or '')
    host = (parts.hostname or '').lower()
    if parts.username or parts.password:
        return False
    if parts.scheme == 'https' and host:
        return True
    return parts.scheme == 'http' and host in ('localhost', '127.0.0.1')


def _fernet():
    raw = (os.environ.get('QBO_TOKEN_KEY') or '').strip()
    if not raw:
        raise QboConfigError('QBO_TOKEN_KEY is not set')
    try:
        return Fernet(raw.encode('ascii'))
    except (ValueError, TypeError):
        raise QboConfigError('QBO_TOKEN_KEY is not a valid Fernet key')


def missing_settings():
    """Env var names that are absent or unusable. Values are never included."""
    missing = []
    if not (os.environ.get('QBO_CLIENT_ID') or '').strip():
        missing.append('QBO_CLIENT_ID')
    if not (os.environ.get('QBO_CLIENT_SECRET') or '').strip():
        missing.append('QBO_CLIENT_SECRET')
    key = (os.environ.get('QBO_TOKEN_KEY') or '').strip()
    if not key:
        missing.append('QBO_TOKEN_KEY')
    else:
        try:
            _fernet()
        except QboConfigError:
            missing.append('QBO_TOKEN_KEY')
    if not _redirect_uri_allowed(redirect_uri()):
        missing.append('QBO_REDIRECT_URI')
    return missing


def encrypt_secret(value):
    if not isinstance(value, str) or not value:
        raise QboConfigError('refusing to store an empty token')
    return _fernet().encrypt(value.encode('utf-8')).decode('ascii')


def decrypt_secret(value):
    if not isinstance(value, str) or not value:
        raise QboConfigError('stored token is empty')
    try:
        return _fernet().decrypt(value.encode('ascii')).decode('utf-8')
    except (InvalidToken, ValueError, TypeError):
        raise QboConfigError('stored token could not be read')


def build_authorize_url(state):
    """Browser redirect. Carries the client id and the scope, never the secret."""
    if missing_settings():
        raise QboConfigError('QuickBooks settings are incomplete')
    if not state:
        raise QboConfigError('OAuth state is missing')
    client_id = (os.environ.get('QBO_CLIENT_ID') or '').strip()
    query = urlencode({
        'client_id': client_id,
        'response_type': 'code',
        'scope': SCOPE,
        'redirect_uri': redirect_uri(),
        'state': state,
    })
    return AUTH_URL + '?' + query


def _client_credentials():
    client_id = (os.environ.get('QBO_CLIENT_ID') or '').strip()
    client_secret = (os.environ.get('QBO_CLIENT_SECRET') or '').strip()
    if not client_id or not client_secret:
        raise QboConfigError('QBO_CLIENT_ID and QBO_CLIENT_SECRET are required')
    return client_id, client_secret


def _read_token_payload(body):
    if not isinstance(body, dict):
        raise QboAuthError('QuickBooks did not return a token.')
    access = body.get('access_token')
    refresh = body.get('refresh_token')
    if not isinstance(access, str) or not access:
        raise QboAuthError('QuickBooks did not return a token.')
    if refresh is not None and not isinstance(refresh, str):
        raise QboAuthError('QuickBooks did not return a token.')
    try:
        expires_in = int(body.get('expires_in') or 0)
    except (TypeError, ValueError):
        expires_in = 0
    if expires_in <= 0:
        expires_in = 3600
    raw_refresh_expires = body.get('x_refresh_token_expires_in')
    refresh_expires_in = None
    if raw_refresh_expires not in (None, ''):
        try:
            refresh_expires_in = int(raw_refresh_expires)
        except (TypeError, ValueError):
            refresh_expires_in = None
    return {
        'access_token': access,
        'refresh_token': refresh or '',
        'expires_in': expires_in,
        'refresh_expires_in': refresh_expires_in,
    }


def _oauth_error_code(resp):
    """Intuit's short error name, when it is a single safe word. Otherwise ''."""
    try:
        body = resp.json()
    except Exception:
        return ''
    if not isinstance(body, dict):
        return ''
    raw = body.get('error')
    if isinstance(raw, str) and _SAFE_OAUTH_ERROR.match(raw):
        return raw
    return ''


def _post_token(form):
    """Token endpoint only. This trades a code for a token. It does not
    create, change, or delete a QuickBooks record."""
    if not isinstance(form, dict):
        raise QboWriteBlocked('The Hub can only read QuickBooks.')
    if form.get('grant_type') not in ('authorization_code', 'refresh_token'):
        raise QboWriteBlocked('The Hub can only read QuickBooks.')
    client_id, client_secret = _client_credentials()
    try:
        resp = httpx.post(
            TOKEN_URL,
            data=form,
            auth=(client_id, client_secret),
            headers={'Accept': 'application/json'},
            timeout=20.0,
            follow_redirects=False,
        )
    except httpx.HTTPError:
        raise QboAuthError('QuickBooks did not respond.')
    if resp.status_code != 200:
        code = _oauth_error_code(resp)
        if code:
            raise QboAuthError(f'QuickBooks refused the connection ({code}).')
        raise QboAuthError('QuickBooks refused the connection.')
    try:
        body = resp.json()
    except Exception:
        raise QboAuthError('QuickBooks did not return a token.')
    return _read_token_payload(body)


def accounting_get(environment_name, realm_id, path, *, params=None, headers=None):
    """Read one QuickBooks resource. The caller does not pass a full URL.

    POST, PUT, PATCH, and DELETE do not exist on this module. A query
    string named ``operation`` is how Intuit deletes and voids, so that
    name is refused even on a GET. ``batch`` can carry creates, so that
    path is refused too.
    """
    if environment_name not in ('sandbox', 'production'):
        raise QboWriteBlocked('The Hub can only read QuickBooks.')
    if not _valid_realm(realm_id):
        raise QboWriteBlocked('The Hub can only read QuickBooks.')
    path = '' if path is None else str(path).strip().lstrip('/')
    pieces = [p for p in path.split('/') if p != '']
    if (
        not pieces
        or any(c in path for c in '?#\\')
        or '://' in path
        or any(p in ('.', '..') for p in pieces)
    ):
        raise QboWriteBlocked('The Hub can only read QuickBooks.')
    if pieces[0].lower() == 'batch':
        raise QboWriteBlocked('The Hub can only read QuickBooks.')
    clean = {}
    if params:
        if not isinstance(params, dict):
            raise QboWriteBlocked('The Hub can only read QuickBooks.')
        for key, value in params.items():
            if str(key).lower() == 'operation':
                raise QboWriteBlocked('The Hub can only read QuickBooks.')
            clean[str(key)] = value
    clean.setdefault('minorversion', str(MINOR_VERSION))
    url = f'{api_base_for(environment_name)}/v3/company/{realm_id}/{path}'
    try:
        return httpx.get(
            url,
            params=clean,
            headers=headers or {},
            timeout=30.0,
            follow_redirects=False,
        )
    except httpx.HTTPError:
        raise QboAuthError('QuickBooks did not respond.')


def exchange_code(code):
    payload = _post_token({
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri(),
    })
    if not payload['refresh_token']:
        raise QboAuthError('QuickBooks did not return a token.')
    return payload


def refresh_tokens(refresh_token):
    """Exchange a refresh token. Intuit rotates it. A missing new one keeps the old.

    The caller must store whatever this returns before doing anything else.
    The previous refresh token dies when Intuit issues a new one.
    """
    if not isinstance(refresh_token, str) or not refresh_token:
        raise QboConfigError('refresh token is empty')
    payload = _post_token({
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
    })
    if not payload['refresh_token']:
        payload['refresh_token'] = refresh_token
    return payload


def _states_match(expected, got):
    if not isinstance(expected, str) or not isinstance(got, str):
        return False
    if not expected or len(expected) != len(got):
        return False
    return secrets.compare_digest(expected, got)


def _valid_code(code):
    return isinstance(code, str) and bool(_CODE_RE.match(code))


def _valid_realm(realm_id):
    return isinstance(realm_id, str) and bool(_REALM_RE.match(realm_id))


def init_tables(cur):
    cur.execute('''
        CREATE TABLE IF NOT EXISTS qbo_connection (
            id SMALLINT PRIMARY KEY DEFAULT 1,
            realm_id VARCHAR(32) NOT NULL,
            environment VARCHAR(20) NOT NULL,
            access_token_enc TEXT NOT NULL,
            refresh_token_enc TEXT NOT NULL,
            access_expires_at TIMESTAMPTZ NOT NULL,
            refresh_expires_at TIMESTAMPTZ,
            connected_by VARCHAR(100),
            connected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_error TEXT,
            last_error_at TIMESTAMPTZ,
            CONSTRAINT qbo_connection_singleton CHECK (id = 1)
        )
    ''')


def _expires_at(seconds):
    if not seconds:
        return None
    return datetime.now(timezone.utc) + timedelta(seconds=int(seconds))


def _run_write(get_db_fn, fn):
    conn = get_db_fn()
    if conn is None:
        raise QboConfigError('database unavailable')
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        result = fn(cur)
        conn.commit()
        return result
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


def save_connection(get_db_fn, realm_id, payload, connected_by):
    """Store a new grant. Replaces the previous company, if there was one."""
    if not _valid_realm(realm_id):
        raise QboConfigError('realm id is not valid')
    access_enc = encrypt_secret(payload['access_token'])
    refresh_enc = encrypt_secret(payload['refresh_token'])
    environment_name = environment()

    def write(cur):
        cur.execute(
            '''INSERT INTO qbo_connection (
                   id, realm_id, environment,
                   access_token_enc, refresh_token_enc,
                   access_expires_at, refresh_expires_at,
                   connected_by, connected_at, updated_at,
                   last_error, last_error_at
               ) VALUES (
                   1, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), NULL, NULL
               )
               ON CONFLICT (id) DO UPDATE SET
                   realm_id = EXCLUDED.realm_id,
                   environment = EXCLUDED.environment,
                   access_token_enc = EXCLUDED.access_token_enc,
                   refresh_token_enc = EXCLUDED.refresh_token_enc,
                   access_expires_at = EXCLUDED.access_expires_at,
                   refresh_expires_at = EXCLUDED.refresh_expires_at,
                   connected_by = EXCLUDED.connected_by,
                   connected_at = NOW(),
                   updated_at = NOW(),
                   last_error = NULL,
                   last_error_at = NULL''',
            (
                realm_id,
                environment_name,
                access_enc,
                refresh_enc,
                _expires_at(payload.get('expires_in') or 3600),
                _expires_at(payload.get('refresh_expires_in')),
                connected_by,
            ),
        )

    _run_write(get_db_fn, write)
    print(f'qbo connected realm={realm_id} env={environment_name} by={connected_by}')


def replace_tokens(get_db_fn, payload):
    """Store a rotated pair. Keeps the company, the environment, and who connected.

    Call this in the same step as a successful refresh, before anything else.
    """
    access_enc = encrypt_secret(payload['access_token'])
    refresh_enc = encrypt_secret(payload['refresh_token'])

    def write(cur):
        cur.execute(
            '''UPDATE qbo_connection SET
                   access_token_enc = %s,
                   refresh_token_enc = %s,
                   access_expires_at = %s,
                   refresh_expires_at = %s,
                   updated_at = NOW(),
                   last_error = NULL,
                   last_error_at = NULL
               WHERE id = 1''',
            (
                access_enc,
                refresh_enc,
                _expires_at(payload.get('expires_in') or 3600),
                _expires_at(payload.get('refresh_expires_in')),
            ),
        )
        return cur.rowcount

    updated = _run_write(get_db_fn, write)
    if not updated:
        raise QboConfigError('QuickBooks is not connected')


def delete_connection(get_db_fn):
    def write(cur):
        cur.execute('DELETE FROM qbo_connection WHERE id = 1')

    _run_write(get_db_fn, write)
    print('qbo disconnected')


def _empty_status():
    return {
        'connected': False,
        'environment': environment(),
        'realm_id': '',
        'connected_by': '',
        'connected_at': None,
        'updated_at': None,
        'access_expires_at': None,
        'refresh_expires_at': None,
        'last_error': None,
        'last_error_at': None,
        'problems': [],
        'redirect_uri': redirect_uri(),
    }


def public_status(get_db_fn):
    """What the owner page may render. The SELECT lists its columns on purpose.

    ``access_token_enc`` and ``refresh_token_enc`` are not in that list.
    """
    status = _empty_status()
    status['problems'] = missing_settings()
    conn = None
    try:
        conn = get_db_fn()
        if conn is None:
            status['last_error'] = 'The database is not available.'
            return status
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute(
                '''SELECT realm_id, environment, access_expires_at, refresh_expires_at,
                          connected_by, connected_at, updated_at, last_error, last_error_at
                   FROM qbo_connection WHERE id = 1'''
            )
            row = cur.fetchone()
        finally:
            cur.close()
    except Exception as exc:
        print(f'qbo status read failed: {type(exc).__name__}')
        status['last_error'] = 'The connection status could not be read.'
        return status
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
    if not row:
        return status
    status['connected'] = True
    status['environment'] = row.get('environment') or status['environment']
    status['realm_id'] = row.get('realm_id') or ''
    status['connected_by'] = row.get('connected_by') or ''
    status['connected_at'] = row.get('connected_at')
    status['updated_at'] = row.get('updated_at')
    status['access_expires_at'] = row.get('access_expires_at')
    status['refresh_expires_at'] = row.get('refresh_expires_at')
    status['last_error'] = row.get('last_error')
    status['last_error_at'] = row.get('last_error_at')
    return status


def load_tokens(get_db_fn):
    """Decrypted tokens for the sync job. Do not put this in a template or a response."""
    conn = get_db_fn()
    if conn is None:
        return None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute(
                '''SELECT realm_id, environment, access_token_enc, refresh_token_enc,
                          access_expires_at
                   FROM qbo_connection WHERE id = 1'''
            )
            row = cur.fetchone()
        finally:
            cur.close()
    finally:
        try:
            conn.close()
        except Exception:
            pass
    if not row:
        return None
    try:
        access = decrypt_secret(row['access_token_enc'])
        refresh = decrypt_secret(row['refresh_token_enc'])
    except QboConfigError as exc:
        print(f'qbo token decrypt failed: {type(exc).__name__}')
        return None
    return {
        'realm_id': row['realm_id'],
        'environment': row['environment'],
        'access_token': access,
        'refresh_token': refresh,
        'access_expires_at': row['access_expires_at'],
    }


def callback_notice(query, expected_state, connected_by, get_db_fn):
    """Finish the grant. Returns a notice code from ``NOTICES``.

    The authorization code is exchanged only after the state matches and the
    server can actually store the result. A failure here does not include
    Intuit's response body.
    """
    err = (query.get('error') or '').strip()
    if err:
        return 'denied' if err == 'access_denied' else 'token'
    if not _states_match(expected_state, query.get('state') or ''):
        return 'state'
    if not _valid_code(query.get('code') or ''):
        return 'token'
    realm_id = query.get('realmId') or ''
    if not _valid_realm(realm_id):
        return 'realm'
    if missing_settings():
        return 'config'
    try:
        payload = exchange_code(query.get('code'))
    except (QboAuthError, QboConfigError) as exc:
        print(f'qbo token exchange failed: {type(exc).__name__}')
        return 'token'
    try:
        save_connection(get_db_fn, realm_id, payload, connected_by)
    except Exception as exc:
        print(f'qbo save failed: {type(exc).__name__}')
        return 'save'
    return 'connected'


def register_routes(app, get_db_fn, require_admin, extra_context=None):
    """``extra_context`` is a no-argument callable that adds the sync section.

    It comes from ``qbo_sync`` and must never return a token. It reads only
    the stored totals, the sync status row, and the name matches.
    """
    from flask import make_response, redirect, render_template, request, session, url_for

    def _page(notice_code):
        status = public_status(get_db_fn)
        # The allowlist is the point of public_status. Fail closed if a
        # future edit puts a token-shaped key on the dict the template sees.
        if set(status) != PUBLIC_STATUS_KEYS:
            raise RuntimeError('qbo status dict drifted')
        extra = {}
        if extra_context is not None:
            try:
                extra = extra_context() or {}
            except Exception as exc:
                print(f'qbo sync section failed: {type(exc).__name__}')
                extra = {}
        resp = make_response(render_template(
            'admin_quickbooks.html',
            status=status,
            notice=NOTICES.get(notice_code or '', ''),
            notice_ok=notice_code in OK_NOTICES,
            ready=not status['problems'],
            **extra,
        ))
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    @app.route('/admin/quickbooks')
    @require_admin
    def admin_quickbooks():
        return _page(request.args.get('notice') or '')

    @app.route('/admin/quickbooks/connect')
    @require_admin
    def admin_quickbooks_connect():
        if missing_settings():
            return redirect(url_for('admin_quickbooks', notice='config'))
        state = secrets.token_urlsafe(32)
        session[SESSION_STATE_KEY] = state
        return redirect(build_authorize_url(state))

    @app.route('/qbo/callback')
    @require_admin
    def qbo_oauth_callback():
        expected = session.pop(SESSION_STATE_KEY, None)
        notice = callback_notice(
            request.args,
            expected,
            session.get('user_key'),
            get_db_fn,
        )
        return redirect(url_for('admin_quickbooks', notice=notice))

    @app.route('/admin/quickbooks/disconnect', methods=['POST'])
    @require_admin
    def admin_quickbooks_disconnect():
        try:
            delete_connection(get_db_fn)
        except Exception as exc:
            print(f'qbo disconnect failed: {type(exc).__name__}')
            return redirect(url_for('admin_quickbooks', notice='save'))
        return redirect(url_for('admin_quickbooks', notice='disconnected'))
