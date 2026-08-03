"""Authentication helpers for PPS Hub."""
import os
import secrets
import urllib.parse
from datetime import datetime, timedelta

HUB_PUBLIC_URL = os.environ.get('HUB_PUBLIC_URL', 'https://hub.purepropsolutions.com').rstrip('/')
PROPOSAL_URL = os.environ.get('PROPOSAL_URL', 'https://pps-proposal-tool.onrender.com').rstrip('/')
# PROFILE_URL retired 2026-08-03 (personal tool archived off Hub). Do not re-add
# without an explicit owner request — see ~/PPS Proposal/personal-storage/README.md.

MAX_LOGIN_FAILURES = 5
LOGIN_LOCKOUT_MINUTES = 15
SSO_CODE_TTL_MINUTES = 2
RESET_TOKEN_TTL_HOURS = 1


def allowed_redirect_bases():
    bases = {HUB_PUBLIC_URL, PROPOSAL_URL}
    return {b for b in bases if b}


# Paths that must never be used as post-login "next" destinations — they cause
# Safari "too many redirects" loops (login → next=login → login → …).
_AUTH_LOOP_PATHS = (
    '/login',
    '/logout',
    '/change-password',
    '/forgot-password',
    '/reset-password',
)


def safe_next_url(url):
    if not url:
        return None
    url = url.strip()
    # Relative path on this hub
    if url.startswith('/') and not url.startswith('//'):
        path = url.split('?', 1)[0]
        if path == '/' or any(path == p or path.startswith(p + '/') for p in _AUTH_LOOP_PATHS):
            return None
        return url
    for base in allowed_redirect_bases():
        if url == base or url.startswith(base + '/'):
            path = urllib.parse.urlparse(url).path or '/'
            if path == '/' or any(path == p or path.startswith(p + '/') for p in _AUTH_LOOP_PATHS):
                return None
            return url
    return None


def client_ip(request):
    forwarded = (request.headers.get('X-Forwarded-For') or '').split(',')[0].strip()
    return forwarded or (request.remote_addr or '')


def record_login_attempt(get_db, user_key, success, ip_address):
    try:
        conn = get_db()
        if not conn:
            return
        cur = conn.cursor()
        cur.execute(
            'INSERT INTO login_attempts (user_key, success, ip_address) VALUES (%s, %s, %s)',
            (user_key or 'unknown', success, ip_address),
        )
        # Successful login clears recent failures so a fixed password works immediately.
        if success and user_key:
            cur.execute(
                '''DELETE FROM login_attempts
                   WHERE user_key = %s AND success = FALSE
                     AND attempted_at > NOW() - make_interval(mins => %s)''',
                (user_key, LOGIN_LOCKOUT_MINUTES * 4),
            )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f'login_attempt log error: {e}')


def clear_login_failures(get_db, user_key):
    """Admin/password-reset helper — lift lockout for this account."""
    if not user_key:
        return
    try:
        conn = get_db()
        if not conn:
            return
        cur = conn.cursor()
        cur.execute(
            'DELETE FROM login_attempts WHERE user_key = %s AND success = FALSE',
            (user_key,),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f'clear_login_failures error: {e}')


def is_login_locked(get_db, user_key):
    """Return (locked: bool, failures: int, minutes_left: int|None)."""
    if not user_key:
        return False, 0, None
    try:
        conn = get_db()
        if not conn:
            return False, 0, None
        cur = conn.cursor()
        cur.execute(
            '''SELECT COUNT(*),
                      EXTRACT(EPOCH FROM (MAX(attempted_at) + make_interval(mins => %s) - NOW())) / 60.0
               FROM login_attempts
               WHERE user_key = %s AND success = FALSE
                 AND attempted_at > NOW() - make_interval(mins => %s)''',
            (LOGIN_LOCKOUT_MINUTES, user_key, LOGIN_LOCKOUT_MINUTES),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        count = int(row[0] or 0) if row else 0
        mins_left = None
        if row and row[1] is not None and count >= MAX_LOGIN_FAILURES:
            mins_left = max(1, int(float(row[1]) + 0.999))
        return count >= MAX_LOGIN_FAILURES, count, mins_left
    except Exception as e:
        print(f'login lock check error: {e}')
        return False, 0, None


def generate_sso_code(get_db, user_key, display_name, role):
    code = secrets.token_urlsafe(32)
    try:
        conn = get_db()
        if not conn:
            return None
        cur = conn.cursor()
        cur.execute("DELETE FROM auth_codes WHERE expires_at < NOW()")
        cur.execute(
            '''INSERT INTO auth_codes (code, user_key, display_name, role, expires_at)
               VALUES (%s, %s, %s, %s, NOW() + make_interval(mins => %s))''',
            (code, user_key, display_name, role, SSO_CODE_TTL_MINUTES),
        )
        conn.commit()
        cur.close()
        conn.close()
        return code
    except Exception as e:
        print(f'generate_sso_code error: {e}')
        return None


def exchange_sso_code(get_db, code):
    if not code:
        return None
    try:
        conn = get_db()
        if not conn:
            return None
        cur = conn.cursor()
        cur.execute(
            '''SELECT user_key, display_name, role FROM auth_codes
               WHERE code = %s AND used = FALSE AND expires_at > NOW()''',
            (code,),
        )
        row = cur.fetchone()
        if not row:
            cur.close()
            conn.close()
            return None
        cur.execute('UPDATE auth_codes SET used = TRUE WHERE code = %s', (code,))
        conn.commit()
        cur.close()
        conn.close()
        return {'user_key': row[0], 'display_name': row[1], 'role': row[2]}
    except Exception as e:
        print(f'exchange_sso_code error: {e}')
        return None


def create_password_reset_token(get_db, user_key):
    token = secrets.token_urlsafe(32)
    try:
        conn = get_db()
        if not conn:
            return None
        cur = conn.cursor()
        cur.execute("DELETE FROM password_reset_tokens WHERE expires_at < NOW()")
        cur.execute(
            '''INSERT INTO password_reset_tokens (token, user_key, expires_at)
               VALUES (%s, %s, NOW() + make_interval(hours => %s))''',
            (token, user_key, RESET_TOKEN_TTL_HOURS),
        )
        conn.commit()
        cur.close()
        conn.close()
        return token
    except Exception as e:
        print(f'password reset token error: {e}')
        return None


def peek_password_reset_token(get_db, token):
    if not token:
        return None
    try:
        conn = get_db()
        if not conn:
            return None
        cur = conn.cursor()
        cur.execute(
            '''SELECT user_key FROM password_reset_tokens
               WHERE token = %s AND used = FALSE AND expires_at > NOW()''',
            (token,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        print(f'peek reset token error: {e}')
        return None


def consume_password_reset_token(get_db, token):
    user_key = peek_password_reset_token(get_db, token)
    if not user_key:
        return None
    try:
        conn = get_db()
        if not conn:
            return None
        cur = conn.cursor()
        cur.execute('UPDATE password_reset_tokens SET used = TRUE WHERE token = %s', (token,))
        conn.commit()
        cur.close()
        conn.close()
        return user_key
    except Exception as e:
        print(f'consume reset token error: {e}')
        return None


def reset_url_for_token(token):
    return f'{HUB_PUBLIC_URL}/reset-password/{token}'