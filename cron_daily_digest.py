#!/usr/bin/env python3
"""Render cron entrypoint — POST to hub daily digest API."""

import json
import os
import sys
import time
import urllib.error
import urllib.request

READ_TIMEOUT = int(os.environ.get('DAILY_DIGEST_TIMEOUT', '300'))
WAKE_TIMEOUT = int(os.environ.get('DAILY_DIGEST_WAKE_TIMEOUT', '90'))


def _wake_hub(base):
    """Hit /health first so a sleeping pps-hub web instance can spin up."""
    health_url = base + '/health'
    print(f'Waking pps-hub ({health_url})...')
    try:
        with urllib.request.urlopen(health_url, timeout=WAKE_TIMEOUT) as resp:
            resp.read()
        print('pps-hub is responding.')
        return True
    except Exception as e:
        print(f'Wake ping: {e} (will still try digest)')
        return False


def _post_digest(url, api_key):
    req = urllib.request.Request(
        url,
        data=b'',
        headers={'X-API-Key': api_key},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=READ_TIMEOUT) as resp:
        body = resp.read().decode('utf-8', errors='replace')
        print(f'HTTP {resp.status}')
        print(body)
        return resp.status, body


def _post_digest_with_retries(url, api_key, attempts=3):
    last_err = None
    for attempt in range(1, attempts + 1):
        try:
            return _post_digest(url, api_key)
        except (urllib.error.HTTPError, TimeoutError, OSError) as e:
            last_err = e
            if attempt < attempts:
                wait = 5 * attempt
                print(f'Attempt {attempt} failed ({e}); retrying in {wait}s...')
                time.sleep(wait)
            else:
                raise last_err
    raise last_err


def main():
    api_key = (os.environ.get('INTERNAL_API_KEY') or '').strip()
    if not api_key:
        print('ERROR: INTERNAL_API_KEY is not set on this cron job.')
        print('Copy the same INTERNAL_API_KEY value from the pps-hub web service.')
        return 1

    base = (os.environ.get('HUB_PUBLIC_URL') or 'https://hub.purepropsolutions.com').rstrip('/')
    url = base + '/api/cron/daily-digest'
    force = (os.environ.get('DAILY_DIGEST_FORCE') or '').strip().lower() in ('1', 'true', 'yes')
    if force:
        url += '?force=1'

    _wake_hub(base)
    time.sleep(3)

    try:
        status, body = _post_digest_with_retries(url, api_key)
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return 0 if 200 <= status < 300 else 1
        if data.get('skipped'):
            print(f"OK (skipped): {data.get('reason', 'unknown')}")
            return 0
        if data.get('ok'):
            if data.get('email_failed'):
                print('WARNING: digest ran but email was not sent — check pps-hub SMTP logs')
            elif data.get('sent'):
                print('OK: digest email sent')
            return 0
        print('ERROR: digest endpoint returned ok=false')
        return 1
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        print(f'HTTP {e.code}')
        print(body or e.reason)
        if e.code == 401:
            print('ERROR: INTERNAL_API_KEY does not match pps-hub. Use the same key on both services.')
        return 1
    except TimeoutError:
        print(f'ERROR: Request timed out after {READ_TIMEOUT}s.')
        print('pps-hub may be cold-starting or SMTP is slow. Try Trigger Run again, or increase DAILY_DIGEST_TIMEOUT.')
        return 1
    except Exception as e:
        print(f'ERROR: {e}')
        return 1


if __name__ == '__main__':
    sys.exit(main())