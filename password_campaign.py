"""One-time retirement of the shared Hub password.

Built 2026-08-21. Until now every account opened with the same password, so it
was never really thirteen logins — it was one login with thirteen names on it.
That is fine right up until someone who knows it stops working here, at which
point the shared secret opens *every* account, not just theirs. Removing a
person from ``USERS`` closes their own login and their live session, but it does
nothing about a password that still works on everyone else's.

So this runs once, on deploy, and does three things per person:

1. Emails them a password-reset link.
2. Replaces their password hash with random bytes nobody holds, so the old
   shared password stops working immediately rather than person by person.
3. Bumps ``password_epoch``, which evicts any session they have open anywhere.

## Two safety properties worth not breaking

**It claims the run atomically, so it cannot fire twice.** Render redeploys on
every push and gunicorn imports the app in each worker, so "run once on deploy"
has to mean once *ever*, across processes and across all future deploys — not
once per boot. The claim is an INSERT ... ON CONFLICT DO NOTHING on a campaign
id; only the worker whose insert reports a row proceeds. Without this, every
subsequent push would silently re-randomize everyone's password.

**A failed email never locks anyone out.** The email goes first, and the
password is only invalidated if it actually sent. If the send fails, that person
keeps their existing password and is merely flagged ``must_change_password``, so
their next sign-in still forces a personal one. They land in the result's
``email_failed`` list for Thomas to reset by hand from /admin. The alternative —
invalidate first, email second — turns one SMTP hiccup into a locked-out
employee, which is a worse Friday than a slightly longer exposure window.

Reset links get a longer TTL than the normal forgot-password flow (72h vs 1h).
An hour is right when someone just clicked "I forgot"; it is wrong for mail
arriving unprompted, possibly overnight or on a day off. An expired link is
recoverable anyway — Forgot Password issues a fresh one.
"""

from __future__ import annotations

import secrets

# Bump this string to run a NEW campaign. Never reuse a spent id, and never
# edit a spent one in place — the id is the only thing standing between a
# routine deploy and re-randomizing everyone's password.
CAMPAIGN_ID = '2026-08-21-retire-shared-password'

RESET_TTL_HOURS = 72


def init_tables(cur):
    cur.execute('''
        CREATE TABLE IF NOT EXISTS password_campaigns (
            campaign_id VARCHAR(120) PRIMARY KEY,
            claimed_at TIMESTAMP DEFAULT NOW(),
            finished_at TIMESTAMP,
            result TEXT
        )
    ''')


def claim(cur, campaign_id=CAMPAIGN_ID):
    """True for exactly one caller, ever. False for everyone after.

    Relies on the primary key, not on a SELECT-then-INSERT, so two workers
    booting simultaneously cannot both win.
    """
    cur.execute(
        'INSERT INTO password_campaigns (campaign_id) VALUES (%s) '
        'ON CONFLICT (campaign_id) DO NOTHING',
        (campaign_id,),
    )
    return cur.rowcount == 1


def _finish(get_db_fn, campaign_id, result):
    try:
        conn = get_db_fn()
        if not conn:
            return
        cur = conn.cursor()
        cur.execute(
            'UPDATE password_campaigns SET finished_at = NOW(), result = %s '
            'WHERE campaign_id = %s',
            (str(result)[:4000], campaign_id),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f'password campaign: could not record result ({e})')


def build_email(display_name, reset_url):
    """Deliberately says nothing about why the shared password is going away.

    This lands in thirteen inboxes at once. The staffing reason behind the
    timing is not company-wide news, and an email that hints at it would be
    both indiscreet and, to the person reading it, alarming for no reason.
    "The Hub now uses individual passwords" is true, sufficient, and boring.
    """
    subject = 'Set your PPS Hub password'
    first = (display_name or '').split(' ')[0] or 'there'
    text = f"""Hi {first},

The PPS Hub now uses individual passwords instead of the shared one. Please set
yours using the link below — it takes about a minute.

{reset_url}

This link works for 72 hours. If it has expired by the time you get to it, go to
the Hub, click "Forgot Password" and it will email you a fresh one.

You will stay signed in for 30 days at a time from now on, so this should be the
last time you need to do this for a while.

Thomas
"""
    html = f"""<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;
max-width:560px;margin:0 auto;color:#1a1a1a;line-height:1.55;">
<h1 style="font-size:19px;color:#004C8C;margin:0 0 16px;">Set your PPS Hub password</h1>
<p>Hi {first},</p>
<p>The PPS Hub now uses individual passwords instead of the shared one. Please set
yours using the button below — it takes about a minute.</p>
<p style="margin:26px 0;">
  <a href="{reset_url}" style="background:#004C8C;color:#fff;text-decoration:none;
     padding:12px 22px;border-radius:4px;display:inline-block;font-weight:600;">
    Set my password</a>
</p>
<p style="color:#666;font-size:14px;">This link works for 72 hours. If it has expired
by the time you get to it, go to the Hub, click <b>Forgot Password</b>, and it will
email you a fresh one.</p>
<p style="color:#666;font-size:14px;">You will stay signed in for 30 days at a time
from now on, so this should be the last time you need to do this for a while.</p>
<p>Thomas</p></div>"""
    return subject, text, html


def run_campaign(
    get_db_fn,
    users,
    send_email_fn,
    make_reset_token,
    reset_url_for_token,
    hash_password,
    exclude=(),
    campaign_id=CAMPAIGN_ID,
):
    """Email everyone a reset link and retire the shared password.

    Dependencies are passed in rather than imported so this module stays
    testable without Flask, Postgres, or SMTP — same convention as the rest of
    the Hub's non-route modules.
    """
    exclude = set(exclude or ())
    emailed, email_failed, skipped = [], [], []

    for user_key, user in users.items():
        if user_key in exclude:
            skipped.append(user_key)
            continue
        email = (user.get('email') or '').strip()
        if not email:
            skipped.append(user_key)
            continue

        # 1. Token + email FIRST. Nothing is invalidated until this succeeds.
        try:
            token = make_reset_token(user_key, RESET_TTL_HOURS)
            if not token:
                raise RuntimeError('token not created')
            subject, text, html = build_email(user.get('display', ''), reset_url_for_token(token))
            sent = send_email_fn(subject, text, html, [email])
        except Exception as e:
            print(f'password campaign: email error for {user_key} ({e})')
            sent = False

        # 2. Only now retire the old password — and only for people who can
        #    actually get back in. A failed send falls back to forcing a change
        #    at next sign-in, which is weaker but never locks anyone out.
        if _apply(get_db_fn, user_key, hash_password, invalidate=bool(sent)):
            (emailed if sent else email_failed).append(user_key)
        else:
            email_failed.append(user_key)

    result = {
        'campaign_id': campaign_id,
        'emailed': emailed,
        'email_failed': email_failed,
        'skipped': skipped,
    }
    _finish(get_db_fn, campaign_id, result)
    if email_failed:
        print(f'password campaign: MANUAL RESET NEEDED for {", ".join(email_failed)}')
    print(f'password campaign: {len(emailed)} emailed, {len(email_failed)} need attention')
    return result


def _apply(get_db_fn, user_key, hash_password, invalidate):
    """Force a password change, and optionally kill the current password.

    ``password_epoch`` is bumped either way so open sessions on other devices
    are evicted — that is the half that matters for a shared secret, whether or
    not the email got through.

    The replacement is a real hash of random bytes, not the random bytes
    themselves. A malformed value in ``password_hash`` would also deny login
    (``_safe_check_password`` catches the ValueError), but only as a side
    effect of being broken; storing a well-formed hash of a secret nobody holds
    denies it on purpose, and keeps the column's invariant intact for anything
    that reads it later.
    """
    conn = None
    try:
        conn = get_db_fn()
        if not conn:
            return False
        cur = conn.cursor()
        if invalidate:
            unusable = hash_password(secrets.token_urlsafe(48))
            cur.execute(
                'UPDATE hub_users SET password_hash = %s, must_change_password = TRUE, '
                'password_epoch = COALESCE(password_epoch, 0) + 1 WHERE user_key = %s',
                (unusable, user_key),
            )
        else:
            cur.execute(
                'UPDATE hub_users SET must_change_password = TRUE, '
                'password_epoch = COALESCE(password_epoch, 0) + 1 WHERE user_key = %s',
                (user_key,),
            )
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        print(f'password campaign: could not update {user_key} ({e})')
        return False
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
