#!/usr/bin/env python3
"""Render cron entrypoint — POST to hub weekly CRM contact sync API."""

import json
import os
import sys
import time
import urllib.error
import urllib.request

READ_TIMEOUT = int(os.environ.get('CRM_SYNC_TIMEOUT', '300'))
WAKE_TIMEOUT = int(os.environ.get('CRM_SYNC_WAKE_TIMEOUT', '90'))


def _wake_hub(base):
    health_url = base + '/health'
    print(f'Waking pps-hub ({health_url})...')
    try:
        with urllib.request.urlopen(health_url, timeout=WAKE_TIMEOUT) as resp:
            resp.read()
        print('pps-hub is responding.')
        return True
    except Exception as e:
        print(f'Wake ping: {e} (will still try sync)')
        return False


def _post(url, api_key):
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
                raise last_err
    raise last_err


def main():
    api_key = (os.environ.get('INTERNAL_API_KEY') or '').strip()
    if not api_key:
        print('ERROR: INTERNAL_API_KEY is not set on this cron job.')
        print('Copy the same INTERNAL_API_KEY value from the pps-hub web service.')
        return 1

    base = (os.environ.get('HUB_PUBLIC_URL') or 'https://hub.purepropsolutions.com').rstrip('/')
    url = base + '/api/cron/weekly-crm-sync'

    _wake_hub(base)
    time.sleep(3)

    try:
        status, body = _post_with_retries(url, api_key)
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return 0 if 200 <= status < 300 else 1
        if data.get('ok'):
            print(f"OK: checked {data.get('checked', '?')} contacts, added={data.get('added')}, sent={data.get('sent')}")
            return 0
        print('ERROR: CRM sync endpoint returned ok=false')
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
        return 1
    except Exception as e:
        print(f'ERROR: {e}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
