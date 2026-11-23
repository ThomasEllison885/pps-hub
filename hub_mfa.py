"""Sign-in code for the owner. A second step after the password.

Thomas, 2026-11-23: "Do 1 and 2." Two meant this. The owner account is
the one that can connect and disconnect QuickBooks, reset everyone's
password, and open the admin pages, so it is the one worth a second
factor. The team stays on passwords; getting them to open the Hub at all
is still the harder problem.

How it works:

- After a correct password, the owner is emailed a 6-digit code and sent
  to ``/login/verify``. Nothing about the session says signed in until the
  code is right.
- "Remember this device" (on by default) sets an HttpOnly cookie for 90
  days, so the code is asked on a new phone or browser, not every visit.
  Only a hash of that cookie is stored. A password reset bumps
  ``password_epoch``, and a device remembered under an older epoch stops
  counting, so a reset also forgets every remembered device.
- A code lasts 10 minutes and allows 5 tries. After that it is dead and the
  owner starts over with the password. Asking for a new code waits 30
  seconds between sends.
- Only hashes of codes are stored, in Postgres, never in the session
  cookie: Flask's cookie is signed, not encrypted, and a six-digit hash in
  it could be guessed offline.

Emergency switch: if email stops working, the owner cannot get a code. Set
``HUB_OWNER_SIGNIN_CODE=off`` on Render and the step is skipped until it is
removed. Nothing else turns it off.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from psycopg2.extras import RealDictCursor

CODE_TTL = timedelta(minutes=10)
MAX_TRIES = 5
RESEND_WAIT = timedelta(seconds=30)
# Each new code resets the five tries, so the number of codes per password
# entry is capped too. Past it, the owner types the password again.
MAX_SENDS = 4
DEVICE_TTL = timedelta(days=90)
DEVICE_COOKIE = 'pps_device'

SESSION_USER = 'mfa_user'
SESSION_NONCE = 'mfa_nonce'
SESSION_REMEMBER = 'mfa_remember'
SESSION_SENDS = 'mfa_sends'


def enabled():
    return (os.environ.get('HUB_OWNER_SIGNIN_CODE') or '').strip().lower() not in ('off', 'false', '0', 'no')


def init_tables(cur):
    cur.execute('''
        CREATE TABLE IF NOT EXISTS hub_signin_codes (
            user_key VARCHAR(100) PRIMARY KEY,
            nonce VARCHAR(64) NOT NULL,
            code_hash VARCHAR(64) NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            attempts SMALLINT NOT NULL DEFAULT 0
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS hub_trusted_devices (
            token_hash VARCHAR(64) PRIMARY KEY,
            user_key VARCHAR(100) NOT NULL,
            password_epoch INTEGER NOT NULL DEFAULT 0,
            label VARCHAR(200),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL
        )
    ''')


# ── Pure helpers ────────────────────────────────────────────────────────────


def new_code():
    return f'{secrets.randbelow(1_000_000):06d}'


def hash_code(nonce, code):
    return hashlib.sha256(f'{nonce}:{code}'.encode('utf-8')).hexdigest()


def hash_token(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def clean_code(raw):
    """Digits only, so '123 456' and '123-456' from a phone still work."""
    return ''.join(ch for ch in str(raw or '') if ch.isdigit())


def mask_email(email):
    email = (email or '').strip()
    if '@' not in email:
        return 'your email'
    name, domain = email.split('@', 1)
    return (name[:1] + '•' * max(1, len(name) - 1)) + '@' + domain


def _now():
    return datetime.now(timezone.utc)


def _aware(value):
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


# ── DB ──────────────────────────────────────────────────────────────────────


def _run(get_db_fn, fn):
    conn = get_db_fn()
    if conn is None:
        raise RuntimeError('database unavailable')
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        out = fn(cur)
        conn.commit()
        return out
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


def device_is_trusted(get_db_fn, user_key, token, password_epoch):
    """True when this browser's cookie was remembered for this user and password."""
    if not token or len(token) > 200:
        return False

    def fn(cur):
        cur.execute(
            '''UPDATE hub_trusted_devices SET last_used_at = NOW()
               WHERE token_hash = %s AND user_key = %s AND password_epoch = %s
                 AND expires_at > NOW()
               RETURNING token_hash''',
            (hash_token(token), user_key, int(password_epoch or 0)),
        )
        return cur.fetchone() is not None

    try:
        return _run(get_db_fn, fn)
    except Exception as exc:
        print(f'mfa device check failed: {type(exc).__name__}')
        return False


def remember_device(get_db_fn, user_key, password_epoch, label):
    token = secrets.token_urlsafe(32)

    def fn(cur):
        cur.execute(
            '''INSERT INTO hub_trusted_devices
                   (token_hash, user_key, password_epoch, label, expires_at)
               VALUES (%s, %s, %s, %s, %s)''',
            (hash_token(token), user_key, int(password_epoch or 0), (label or '')[:200], _now() + DEVICE_TTL),
        )
        cur.execute('DELETE FROM hub_trusted_devices WHERE expires_at < NOW()')

    _run(get_db_fn, fn)
    return token


def forget_devices(get_db_fn, user_key):
    _run(get_db_fn, lambda cur: cur.execute('DELETE FROM hub_trusted_devices WHERE user_key = %s', (user_key,)))


def issue_code(get_db_fn, user_key, nonce):
    """Store a fresh code for this user, replacing any earlier one. Returns the code."""
    code = new_code()

    def fn(cur):
        cur.execute(
            '''INSERT INTO hub_signin_codes (user_key, nonce, code_hash, expires_at, sent_at, attempts)
               VALUES (%s, %s, %s, %s, NOW(), 0)
               ON CONFLICT (user_key) DO UPDATE SET
                   nonce = EXCLUDED.nonce,
                   code_hash = EXCLUDED.code_hash,
                   expires_at = EXCLUDED.expires_at,
                   sent_at = NOW(),
                   attempts = 0''',
            (user_key, nonce, hash_code(nonce, code), _now() + CODE_TTL),
        )

    _run(get_db_fn, fn)
    return code


def last_sent_at(get_db_fn, user_key, nonce):
    def fn(cur):
        cur.execute('SELECT sent_at FROM hub_signin_codes WHERE user_key = %s AND nonce = %s', (user_key, nonce))
        row = cur.fetchone()
        return _aware(row['sent_at']) if row else None

    return _run(get_db_fn, fn)


def check_code(get_db_fn, user_key, nonce, code):
    """'ok', 'wrong', 'expired', or 'gone'. A right code is used up at once."""
    code = clean_code(code)

    def fn(cur):
        cur.execute(
            'SELECT nonce, code_hash, expires_at, attempts FROM hub_signin_codes WHERE user_key = %s FOR UPDATE',
            (user_key,),
        )
        row = cur.fetchone()
        if not row or not hmac.compare_digest(row['nonce'], nonce or ''):
            return 'gone'
        if _aware(row['expires_at']) <= _now() or row['attempts'] >= MAX_TRIES:
            cur.execute('DELETE FROM hub_signin_codes WHERE user_key = %s', (user_key,))
            return 'expired'
        if len(code) == 6 and hmac.compare_digest(row['code_hash'], hash_code(nonce, code)):
            cur.execute('DELETE FROM hub_signin_codes WHERE user_key = %s', (user_key,))
            return 'ok'
        cur.execute('UPDATE hub_signin_codes SET attempts = attempts + 1 WHERE user_key = %s', (user_key,))
        if row['attempts'] + 1 >= MAX_TRIES:
            cur.execute('DELETE FROM hub_signin_codes WHERE user_key = %s', (user_key,))
            return 'expired'
        return 'wrong'

    return _run(get_db_fn, fn)


# ── Email ───────────────────────────────────────────────────────────────────


def send_code_email(send_email_fn, email, code, ip, agent):
    subject = 'Your PPS Hub sign-in code'
    where = ', '.join(x for x in ((ip or '').strip(), (agent or '').strip()[:120]) if x)
    text = (
        f'Your PPS Hub sign-in code is {code}\n\n'
        'It works for 10 minutes.\n'
        + (f'Requested from: {where}\n' if where else '')
        + '\nIf you did not just sign in, someone has your Hub password. Change it now.\n'
    )
    html = (
        '<p>Your PPS Hub sign-in code is</p>'
        f'<p style="font-size:28px;font-weight:700;letter-spacing:4px;">{code}</p>'
        '<p>It works for 10 minutes.</p>'
        + (f'<p style="color:#888;font-size:13px;">Requested from: {_esc(where)}</p>' if where else '')
        + '<p>If you did not just sign in, someone has your Hub password. Change it now.</p>'
    )
    try:
        return bool(send_email_fn(subject, text, html, [email]))
    except Exception as exc:
        print(f'mfa code email failed: {type(exc).__name__}')
        return False


def _esc(text):
    return str(text or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


# ── Flow ────────────────────────────────────────────────────────────────────


def required_for(users, user_key, is_owner_fn):
    return enabled() and user_key in users and bool(is_owner_fn(user_key))


def register_routes(app, get_db_fn, users, send_email_fn, finish_login_fn, load_db_user_fn):
    """``finish_login_fn(user_key, db_user)`` returns the post-login response.

    ``load_db_user_fn(user_key)`` returns the hub_users row or None.
    """
    from flask import make_response, redirect, render_template, request, session, url_for

    from auth_helpers import client_ip

    def _page(error='', message=''):
        user_key = session.get(SESSION_USER)
        email = (users.get(user_key) or {}).get('email', '')
        resp = make_response(render_template(
            'login_verify.html',
            masked_email=mask_email(email),
            error=error,
            message=message,
            remember=session.get(SESSION_REMEMBER, True),
        ))
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
        return resp

    def _clear_pending():
        session.pop(SESSION_SENDS, None)
        session.pop(SESSION_USER, None)
        session.pop(SESSION_NONCE, None)
        session.pop(SESSION_REMEMBER, None)

    def _send(user_key, nonce):
        session[SESSION_SENDS] = int(session.get(SESSION_SENDS) or 0) + 1
        code = issue_code(get_db_fn, user_key, nonce)
        email = (users.get(user_key) or {}).get('email', '')
        ok = send_code_email(send_email_fn, email, code, client_ip(request), request.headers.get('User-Agent', ''))
        print(f'mfa code sent user={user_key} ok={ok}')
        return ok

    def start(user_key, db_user):
        """Called by /login after a correct password. Returns a response."""
        epoch = (db_user or {}).get('password_epoch') or 0
        if device_is_trusted(get_db_fn, user_key, request.cookies.get(DEVICE_COOKIE, ''), epoch):
            return finish_login_fn(user_key, db_user)
        nonce = secrets.token_urlsafe(24)
        session[SESSION_USER] = user_key
        session[SESSION_NONCE] = nonce
        session[SESSION_REMEMBER] = True
        session[SESSION_SENDS] = 0
        try:
            sent = _send(user_key, nonce)
        except Exception as exc:
            print(f'mfa code issue failed: {type(exc).__name__}')
            sent = False
        resp = redirect(url_for('login_verify', notsent='1' if not sent else None))
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    @app.route('/login/verify', methods=['GET', 'POST'])
    def login_verify():
        user_key = session.get(SESSION_USER)
        nonce = session.get(SESSION_NONCE)
        if not user_key or not nonce or user_key not in users:
            return redirect(url_for('login'))
        if request.method in ('GET', 'HEAD'):
            if request.args.get('notsent'):
                return _page(error='The code email did not send. Tap "Send a new code" to try again.')
            return _page()

        remember = request.form.get('remember') == '1'
        session[SESSION_REMEMBER] = remember
        try:
            result = check_code(get_db_fn, user_key, nonce, request.form.get('code'))
        except Exception as exc:
            print(f'mfa check failed: {type(exc).__name__}')
            return _page(error='Sign-in is temporarily unavailable. Try again in a moment.')
        if result == 'wrong':
            return _page(error='That code is not right. Check the newest email and try again.')
        if result in ('expired', 'gone'):
            _clear_pending()
            session['login_flash_error'] = 'That code expired. Enter your password again for a new one.'
            return redirect(url_for('login'))

        db_user = load_db_user_fn(user_key)
        _clear_pending()
        resp = finish_login_fn(user_key, db_user)
        if remember:
            try:
                token = remember_device(
                    get_db_fn, user_key, (db_user or {}).get('password_epoch') or 0,
                    request.headers.get('User-Agent', ''),
                )
                resp.set_cookie(
                    DEVICE_COOKIE, token,
                    max_age=int(DEVICE_TTL.total_seconds()),
                    secure=not app.debug, httponly=True, samesite='Lax', path='/',
                )
            except Exception as exc:
                print(f'mfa remember failed: {type(exc).__name__}')
        return resp

    @app.route('/login/verify/resend', methods=['POST'])
    def login_verify_resend():
        user_key = session.get(SESSION_USER)
        nonce = session.get(SESSION_NONCE)
        if not user_key or not nonce or user_key not in users:
            return redirect(url_for('login'))
        try:
            sent_at = last_sent_at(get_db_fn, user_key, nonce)
            if int(session.get(SESSION_SENDS) or 0) >= MAX_SENDS:
                _clear_pending()
                session['login_flash_error'] = 'Too many codes. Enter your password again for a new one.'
                return redirect(url_for('login'))
            if sent_at and _now() - sent_at < RESEND_WAIT:
                return _page(message='A code was just sent. Give it a few seconds, then check your email.')
            ok = _send(user_key, nonce)
        except Exception as exc:
            print(f'mfa resend failed: {type(exc).__name__}')
            ok = False
        if not ok:
            return _page(error='The code email did not send. Try again in a minute.')
        return _page(message='A new code is on its way. Only the newest code works.')

    return start
