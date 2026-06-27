#!/usr/bin/env python3
"""Render cron entrypoint — POST to hub daily digest API."""

import json
import os
import sys
import urllib.error
import urllib.request


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

    req = urllib.request.Request(
        url,
        data=b'',
        headers={'X-API-Key': api_key},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode('utf-8', errors='replace')
            print(f'HTTP {resp.status}')
            print(body)
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                return 0 if 200 <= resp.status < 300 else 1
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
    except Exception as e:
        print(f'ERROR: {e}')
        return 1


if __name__ == '__main__':
    sys.exit(main())