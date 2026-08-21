#!/usr/bin/env python3
"""Render cron entrypoint — POST to the weekly team recap API.

Mirrors cron_weekly_tp_compliance.py / cron_daily_digest.py exactly: wake the
web service first (Render can let it idle), then POST with the shared
INTERNAL_API_KEY, with retries for a cold start. All the real work happens in
weekly_recap.py behind /api/cron/weekly-recap; this file only triggers it.

Set WEEKLY_RECAP_FORCE=true and hit "Trigger Run" to send outside the schedule.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

READ_TIMEOUT = int(os.environ.get('WEEKLY_RECAP_TIMEOUT', '300'))
WAKE_TIMEOUT = int(os.environ.get('WEEKLY_RECAP_WAKE_TIMEOUT', '90'))


def _wake_hub(base):
    try:
        with urllib.request.urlopen(base + '/health', timeout=WAKE_TIMEOUT) as resp:
            resp.read()
        print('pps-hub is responding.')
    except Exception as e:
        print(f'Wake ping: {e} (will still try the recap)')


def _post(url, api_key):
    req = urllib.request.Request(
        url, data=b'', headers={'X-API-Key': api_key}, method='POST',
    )
    with urllib.request.urlopen(req, timeout=READ_TIMEOUT) as resp:
        body = resp.read().decode('utf-8', errors='replace')
        print(f'HTTP {resp.status}')
        print(body)
        return resp.status, body


def _post_with_retries(url, api_key, attempts=3):
    last_err = None
    for attempt in range(1, attempts + 1):
        try:
            return _post(url, api_key)
        except (urllib.error.HTTPError, TimeoutError, OSError) as e:
            last_err = e
            if attempt < attempts:
                wait = 5 * attempt
                print(f'Attempt {attempt} failed ({e}); retrying in {wait}s...')
                time.sleep(wait)
            else:
                raise
    raise last_err


def main():
    api_key = (os.environ.get('INTERNAL_API_KEY') or '').strip()
    if not api_key:
        print('ERROR: INTERNAL_API_KEY is not set on this cron job.')
        print('Copy the same INTERNAL_API_KEY value from the pps-hub web service.')
        return 1

    base = (os.environ.get('HUB_PUBLIC_URL') or 'https://hub.purepropsolutions.com').rstrip('/')
    url = base + '/api/cron/weekly-recap'
    if (os.environ.get('WEEKLY_RECAP_FORCE') or '').strip().lower() in ('1', 'true', 'yes'):
        url += '?force=1'

    _wake_hub(base)
    time.sleep(3)

    try:
        status, body = _post_with_retries(url, api_key)
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return 0 if 200 <= status < 300 else 1
        if data.get('skipped'):
            print(f"OK (skipped): {data.get('reason', 'unknown')}")
            return 0
        sent = data.get('sent') or []
        failed = data.get('failed') or []
        print(f"OK: recap for {data.get('week_label')} sent to {len(sent)} people "
              f"({data.get('total_actions')} actions logged)")
        if failed:
            print(f"WARNING: send failed for {', '.join(failed)} — check pps-hub SMTP logs")
        return 0
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        print(f'HTTP {e.code}')
        print(body or e.reason)
        if e.code == 401:
            print('ERROR: INTERNAL_API_KEY does not match pps-hub. Use the same key on both.')
        return 1
    except TimeoutError:
        print(f'ERROR: Request timed out after {READ_TIMEOUT}s.')
        return 1
    except Exception as e:
        print(f'ERROR: {e}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
