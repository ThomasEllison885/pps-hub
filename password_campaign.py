"""One-time retirement of the shared Hub password.

Built 2026-08-21. Until now every account opened with the same password, so it
was never really thirteen logins — it was one login with thirteen names on it.
That is fine right up until someone who knows it stops working here, at which
point the shared secret opens *every* account, not just theirs. Removing a
person from ``USERS`` closes their own login and their live session, but it does
nothing about a password that still works on everyone else's.

It does three things per person:

1. Emails them a password-reset link.
2. Replaces their password hash with random bytes nobody holds, so the old
   shared password stops working immediately rather than person by person.
3. Bumps ``password_epoch``, which evicts any session they have open anywhere.

## Three safety properties worth not breaking

**It never emails the same person twice.** The set of people still to process is
derived from ``password_epoch = 0`` rather than from a ledger — see
``pending_user_keys``. That matters because the first attempt died mid-run
without leaving one, and a duplicate "set your password" email is both confusing
and, if it re-randomized an account someone had already fixed, destructive.

**It is bounded by wall clock and never runs at import.** The first attempt
called this from the bottom of app.py, so gunicorn was still importing the
module while it worked through thirteen SMTP sends; Render's port scan timed out
first and the deploy was cancelled with "No open ports detected". It is now a
manual, owner-only endpoint that processes what it can inside a time budget and
reports ``remaining``. Same shape as the COI vision pass, for the same reason.

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
import time

# Labels the run in logs and in the summary email. It is NOT the idempotency
# guard any more — password_epoch is (see pending_user_keys).
CAMPAIGN_ID = '2026-08-21-retire-shared-password'

RESET_TTL_HOURS = 72


def pending_user_keys(get_db_fn, users, exclude=()):
    """Who has NOT been processed yet. The guard against duplicate emails.

    Idempotency is derived from state rather than tracked in a ledger, because
    the first run (2026-08-21) died mid-flight without leaving one: gunicorn was
    still importing app.py when Render's port scan timed out, so the deploy was
    cancelled with an unknown number of people already emailed.

    ``password_epoch`` is the marker. The column was added the same day and
    defaults to 0, and the only things that bump it are this campaign, a
    password change, and a reset. So epoch = 0 means *nothing has touched this
    account*, which is exactly the set that still needs an email. Anyone at 1 or
    above either already got theirs or has since set a password — and must not
    be mailed again, still less have a working password re-randomized.

    Returns [] on any DB failure. Sending nobody an email is always the safe
    direction here; sending a second one is not.
    """
    conn = None
    try:
        conn = get_db_fn()
        if not conn:
            return []
        exclude = set(exclude or ())
        candidates = [
            k for k, u in users.items()
            if k not in exclude and (u.get('email') or '').strip()
        ]
        if not candidates:
            return []
        cur = conn.cursor()
        cur.execute(
            'SELECT user_key FROM hub_users '
            'WHERE user_key = ANY(%s) AND COALESCE(password_epoch, 0) = 0',
            (candidates,),
        )
        pending = {row[0] for row in cur.fetchall()}
        cur.close()
        return [k for k in candidates if k in pending]
    except Exception as e:
        print(f'password campaign: could not read pending users ({e})')
        return []
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


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
    time_budget_seconds=60,
):
    """Email the people who have not been emailed yet, and retire their password.

    Resumable and safe to call repeatedly: it only touches accounts still at
    ``password_epoch = 0``, so a second call after a complete run does nothing
    at all, and a call after a partial run finishes exactly the remainder.

    Bounded by wall clock, not row count. This is the repo's hard-won lesson
    from the COI vision pass (see CLAUDE.md): a row limit does not bound time,
    and anything slower than gunicorn's 120s timeout gets SIGKILLed mid-flight.
    Thirteen SMTP sends at up to 30s each is well past that, which is exactly
    how the first attempt took the whole deploy down. Returns ``remaining`` so
    the caller can run it again rather than being cut off.

    Dependencies are passed in rather than imported so this module stays
    testable without Flask, Postgres, or SMTP.
    """
    started = time.monotonic()
    exclude = set(exclude or ())
    pending = pending_user_keys(get_db_fn, users, exclude)
    # Everyone not in play this run: excluded, no inbox, or already processed.
    skipped = [k for k in users if k not in pending]
    emailed, email_failed = [], []
    remaining = 0

    for i, user_key in enumerate(pending):
        # Checked BEFORE starting a send, so a slow one cannot overrun the
        # budget it was admitted under.
        if time.monotonic() - started > time_budget_seconds:
            remaining = len(pending) - i
            break

        user = users.get(user_key) or {}
        email = (user.get('email') or '').strip()

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
        #    Either branch bumps password_epoch, so this person drops out of
        #    pending_user_keys and can never be emailed a second time.
        if _apply(get_db_fn, user_key, hash_password, invalidate=bool(sent)):
            (emailed if sent else email_failed).append(user_key)
        else:
            email_failed.append(user_key)

    result = {
        'campaign_id': campaign_id,
        'emailed': emailed,
        'email_failed': email_failed,
        'remaining': remaining,
        'pending_at_start': len(pending),
        'skipped': skipped,
    }
    if email_failed:
        print(f'password campaign: MANUAL RESET NEEDED for {", ".join(email_failed)}')
    print(f'password campaign: {len(emailed)} emailed, {len(email_failed)} need attention, '
          f'{remaining} still pending')
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
