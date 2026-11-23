#!/usr/bin/env python3
"""Render cron entrypoint: POST to the Hub's nightly QuickBooks sync.

Fires at 04:05 and 05:05 UTC. The Hub runs the sync only when the Eastern
hour is 0, so exactly one of the two lands on midnight whether or not
daylight saving is on. Trigger Run at any other hour is a safe no-op unless
QBO_SYNC_FORCE=true is set on this cron.

This service holds no QuickBooks credentials. The pull happens on the web
service, which has the tokens.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

READ_TIMEOUT = int(os.environ.get('QBO_SYNC_TIMEOUT', '180'))
WAKE_TIMEOUT = int(os.environ.get('QBO_SYNC_WAKE_TIMEOUT', '90'))


def _wake_hub(base):
    try:
        with urllib.request.urlopen(base + '/health', timeout=WAKE_TIMEOUT) as resp:
            resp.read()
        print('pps-hub is responding.')
    except Exception as e:
        print(f'Wake ping: {e} (will still try the sync)')


def _post(url, api_key):
    req = urllib.request.Request(url, data=b'', headers={'X-API-Key': api_key}, method='POST')
    with urllib.request.urlopen(req, timeout=READ_TIMEOUT) as resp:
        body = resp.read().decode('utf-8', errors='replace')
        print(f'HTTP {resp.status}')
        print(body)
        return resp.status, body


def main():
    api_key = (os.environ.get('INTERNAL_API_KEY') or '').strip()
    if not api_key:
        print('ERROR: INTERNAL_API_KEY is not set on this cron job.')
        return 1
    base = (os.environ.get('HUB_PUBLIC_URL') or 'https://hub.purepropsolutions.com').rstrip('/')
    url = base + '/api/cron/qbo-sync'
    if (os.environ.get('QBO_SYNC_FORCE') or '').strip().lower() in ('1', 'true', 'yes'):
        url += '?force=1'

    _wake_hub(base)
    time.sleep(3)

    # One retry for a cold start. The sync itself is safe to repeat: every
    # run replaces the year's totals.
    for attempt in (1, 2):
        try:
            status, body = _post(url, api_key)
            break
        except urllib.error.HTTPError as e:
            print(f'HTTP {e.code}')
            if e.code == 401:
                print('ERROR: INTERNAL_API_KEY does not match pps-hub.')
                return 1
            if attempt == 2:
                return 1
        except Exception as e:
            print(f'Attempt {attempt} failed: {e}')
            if attempt == 2:
                return 1
        time.sleep(10)

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return 0 if 200 <= status < 300 else 1
    if data.get('skipped'):
        print(f"OK (skipped): {data.get('reason')}")
        return 0
    if data.get('ok'):
        print('OK: QuickBooks totals updated')
        return 0
    print('ERROR: sync did not finish. The Hub kept the last good numbers and emailed Thomas.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
