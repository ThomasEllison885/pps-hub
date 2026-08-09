"""Minimal Monday.com GraphQL client — stdlib urllib, no new HTTP dependency.

Board/column IDs confirmed live 2026-08-09 against the Sub Info board
(672547511): Certificates/Contract is a native `file` column (id `files`),
Date Insurance Expires is `date`, Date Workers Comp Expires is `date8`.
Asset downloads use `assets(ids: [...]) { public_url }` — a pre-signed S3 URL
good for ~1 hour, no Authorization header needed on the download itself.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

MONDAY_API_URL = 'https://api.monday.com/v2'

SUB_INFO_BOARD_ID = os.environ.get('MONDAY_SUB_INFO_BOARD_ID', '672547511')

COL_STATUS = 'status'
COL_DATE_INSURANCE = 'date'
COL_DATE_WORKERS_COMP = 'date8'
COL_FILES = 'files'
COL_DATE_FOUND = 'date4'

# Groups actually worth a weekly nudge, confirmed live against the board
# 2026-08-09 and narrowed 2026-08-10 per Thomas: "Insurance Out of Date NOT
# COMPLIANT" is mostly subs from years ago that PPS doesn't use and has no
# plan to use again — it was drowning the digest in ancient "expired since
# 2021" noise for dead relationships, not real work. Dropped from
# monitoring; existing snapshot rows for that group get pruned on the next
# run (see run_weekly_compliance_check). "ON HOLD - Waiting on updated
# insurnace" is spelled that way on the board itself — do not "fix" the
# typo here, it must match exactly for the GraphQL group-title filter to
# work. Potential Subs (not yet vetted) and No Longer Active stay excluded
# — no current compliance expectation either way.
ACTIVE_GROUPS = (
    'Sub contractors - Compliant',
    'ON HOLD - Waiting on updated insurnace',
)


def _token():
    tok = (os.environ.get('MONDAY_API_TOKEN') or '').strip()
    if not tok:
        raise RuntimeError('MONDAY_API_TOKEN is not set')
    return tok


def monday_graphql(query, variables=None, timeout=30):
    body = {'query': query}
    if variables:
        body['variables'] = variables
    req = urllib.request.Request(
        MONDAY_API_URL,
        data=json.dumps(body).encode('utf-8'),
        headers={
            'Authorization': _token(),
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    if data.get('errors'):
        raise RuntimeError(f"Monday API error: {data['errors']}")
    return data.get('data') or {}


_COLUMN_IDS = '["status", "date", "date8", "files", "date4"]'

_NEXT_PAGE_QUERY = f'''
query($cursor: String!) {{
  next_items_page(cursor: $cursor, limit: 50) {{
    cursor
    items {{
      id
      name
      group {{ title }}
      column_values(ids: {_COLUMN_IDS}) {{
        id
        text
        value
      }}
    }}
  }}
}}
'''


def fetch_sub_info_items(board_id=None, groups=ACTIVE_GROUPS):
    """Return raw items (name, group title, column_values) from the active
    compliance groups on the Sub Info board. Follows next_items_page cursors
    per group — the "Sub contractors - Compliant" group alone has 50+ items,
    confirmed live 2026-08-09 (first page came back with a non-null cursor)."""
    board_id = board_id or SUB_INFO_BOARD_ID
    items = []
    query = f'''
    query($boardId: [ID!]) {{
      boards(ids: $boardId) {{
        groups {{
          title
          items_page(limit: 50) {{
            cursor
            items {{
              id
              name
              group {{ title }}
              column_values(ids: {_COLUMN_IDS}) {{
                id
                text
                value
              }}
            }}
          }}
        }}
      }}
    }}
    '''
    boards = monday_graphql(query, {'boardId': [board_id]}).get('boards') or []
    for board in boards:
        for group in board.get('groups') or []:
            if groups and group.get('title') not in groups:
                continue
            page = group.get('items_page') or {}
            for it in page.get('items') or []:
                items.append(it)

            cursor = page.get('cursor')
            while cursor:
                next_page = monday_graphql(_NEXT_PAGE_QUERY, {'cursor': cursor}).get('next_items_page') or {}
                for it in next_page.get('items') or []:
                    # next_items_page items don't carry `group`, since the
                    # cursor is already scoped to one group's continuation.
                    it.setdefault('group', {'title': group.get('title')})
                    items.append(it)
                cursor = next_page.get('cursor')
    return items


# Pay Request board — cross-referenced against Sub Info compliance status
# (Thomas, 2026-08-10). The board's own "Sub Info" connect-column
# (board_relation_mm0m3act) exists but is empty on every item checked live —
# not populated in practice, so matching has to go by name (see
# insurance_compliance._match_sub_name), not a board relation.
PAY_REQUEST_BOARD_ID = os.environ.get('MONDAY_PAY_REQUEST_BOARD_ID', '2358228368')

PAY_REQUEST_COL_STATUS = 'status__1'      # "Insurance Compliance" — manually set, not COI-verified
PAY_REQUEST_COL_DATE = 'date4'            # "Date"
PAY_REQUEST_COL_AMOUNT = 'numbers'        # "Requested Amount"
PAY_REQUEST_COL_JOB_NAME = 'text8'        # "Job Name"

# Only the active pipeline — money not yet out the door. "Paid Out" holds the
# bulk of this board's 5,206 items and is after-the-fact, not needed for a
# forward-looking warning.
PAY_REQUEST_ACTIVE_GROUPS = ('In Request', 'On Hold')

_PAY_REQUEST_COLUMN_IDS = '["status__1", "date4", "numbers", "text8"]'

_PAY_REQUEST_NEXT_PAGE_QUERY = f'''
query($cursor: String!) {{
  next_items_page(cursor: $cursor, limit: 50) {{
    cursor
    items {{
      id
      name
      group {{ title }}
      column_values(ids: {_PAY_REQUEST_COLUMN_IDS}) {{
        id
        text
        value
      }}
    }}
  }}
}}
'''


def fetch_pay_request_items(board_id=None, groups=PAY_REQUEST_ACTIVE_GROUPS):
    """Return raw items from the active Pay Request groups (In Request, On
    Hold). Same items_page/next_items_page pagination shape as
    fetch_sub_info_items."""
    board_id = board_id or PAY_REQUEST_BOARD_ID
    items = []
    query = f'''
    query($boardId: [ID!]) {{
      boards(ids: $boardId) {{
        groups {{
          title
          items_page(limit: 50) {{
            cursor
            items {{
              id
              name
              group {{ title }}
              column_values(ids: {_PAY_REQUEST_COLUMN_IDS}) {{
                id
                text
                value
              }}
            }}
          }}
        }}
      }}
    }}
    '''
    boards = monday_graphql(query, {'boardId': [board_id]}).get('boards') or []
    for board in boards:
        for group in board.get('groups') or []:
            if groups and group.get('title') not in groups:
                continue
            page = group.get('items_page') or {}
            for it in page.get('items') or []:
                items.append(it)

            cursor = page.get('cursor')
            while cursor:
                next_page = monday_graphql(_PAY_REQUEST_NEXT_PAGE_QUERY, {'cursor': cursor}).get('next_items_page') or {}
                for it in next_page.get('items') or []:
                    it.setdefault('group', {'title': group.get('title')})
                    items.append(it)
                cursor = next_page.get('cursor')
    return items


# CRM Contacts board — synced weekly into the Hub's /clients picker (Thomas,
# 2026-08-10). The board's own "Company" connect-column (contact_account) is
# empty on every item checked live — same unused-connect-column pattern as
# every other board this session — so company isn't pulled from here.
CONTACTS_BOARD_ID = os.environ.get('MONDAY_CONTACTS_BOARD_ID', '7902650879')

CONTACTS_COL_EMAIL = 'contact_email'
CONTACTS_COL_PHONE = 'contact_phone'

# Default placeholder title Monday gives a freshly-created contact before
# anyone renames it — confirmed live in real data, not hypothetical.
PLACEHOLDER_CONTACT_NAMES = {'new contact'}

_CONTACTS_COLUMN_IDS = '["contact_email", "contact_phone"]'

_CONTACTS_NEXT_PAGE_QUERY = f'''
query($cursor: String!) {{
  next_items_page(cursor: $cursor, limit: 50) {{
    cursor
    items {{
      id
      name
      column_values(ids: {_CONTACTS_COLUMN_IDS}) {{
        id
        text
        value
      }}
    }}
  }}
}}
'''


def fetch_contacts_items(board_id=None):
    """Return all items from the Contacts board (no group filter — unlike
    Sub Info/Pay Request, this board isn't organized into meaningful
    groups for this purpose). Same items_page/next_items_page pagination
    shape used elsewhere in this module."""
    board_id = board_id or CONTACTS_BOARD_ID
    items = []
    query = f'''
    query($boardId: [ID!]) {{
      boards(ids: $boardId) {{
        items_page(limit: 50) {{
          cursor
          items {{
            id
            name
            column_values(ids: {_CONTACTS_COLUMN_IDS}) {{
              id
              text
              value
            }}
          }}
        }}
      }}
    }}
    '''
    boards = monday_graphql(query, {'boardId': [board_id]}).get('boards') or []
    for board in boards:
        page = board.get('items_page') or {}
        for it in page.get('items') or []:
            items.append(it)

        cursor = page.get('cursor')
        while cursor:
            next_page = monday_graphql(_CONTACTS_NEXT_PAGE_QUERY, {'cursor': cursor}).get('next_items_page') or {}
            for it in next_page.get('items') or []:
                items.append(it)
            cursor = next_page.get('cursor')
    return items


def resolve_asset_urls(asset_ids):
    """Return {asset_id: public_url} for a batch of Monday file asset IDs."""
    if not asset_ids:
        return {}
    query = '''
    query($ids: [ID!]) {
      assets(ids: $ids) {
        id
        name
        public_url
        created_at
      }
    }
    '''
    data = monday_graphql(query, {'ids': [str(a) for a in asset_ids]})
    out = {}
    for asset in data.get('assets') or []:
        out[str(asset['id'])] = asset
    return out


def download_asset(public_url, timeout=30):
    req = urllib.request.Request(public_url, method='GET')
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def parse_files_column(column_value):
    """column_value is the raw `value` JSON string from the `files` column —
    returns a list of {name, assetId, createdAt} dicts, newest-looking last
    (Monday returns them in upload order, which is usually chronological)."""
    raw = column_value.get('value') if isinstance(column_value, dict) else column_value
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return parsed.get('files') or []


# Estimates board — new-assignment notification + daily reminder (Thomas,
# 2026-08-10). Deliberately a standalone feature, not a Pipeline Board
# change. "Sales Lead" = PSC, "Production Lead" = PM (confirmed with
# Thomas). Note: the board has TWO groups both literally titled "Estimates
# needed" (different group IDs — a board-editing artifact, not a naming
# convention). Title-matching them together is safe only because both get
# identical (open-work) treatment here; don't assume title-matching is
# generally safe on this board if a future feature needs to tell them apart.
ESTIMATES_BOARD_ID = os.environ.get('MONDAY_ESTIMATES_BOARD_ID', '8374265997')

ESTIMATES_COL_SALES_LEAD = 'person'
ESTIMATES_COL_PRODUCTION_LEAD = 'dup__of_sales_lead_mkmq33ap'
ESTIMATES_COL_DUE_BY = 'date_1_mkn89y42'
ESTIMATES_COL_PRIORITY = 'priority_mkmq448f'

ESTIMATES_OPEN_GROUPS = ('Estimates needed', 'New Requests (Sales)', 'Estimate in Progress (PM)')

_ESTIMATES_COLUMN_IDS = '["person", "dup__of_sales_lead_mkmq33ap", "date_1_mkn89y42", "priority_mkmq448f"]'

_ESTIMATES_NEXT_PAGE_QUERY = f'''
query($cursor: String!) {{
  next_items_page(cursor: $cursor, limit: 50) {{
    cursor
    items {{
      id
      name
      group {{ title }}
      column_values(ids: {_ESTIMATES_COLUMN_IDS}) {{
        id
        text
        value
      }}
    }}
  }}
}}
'''


def fetch_estimates_items(board_id=None, groups=ESTIMATES_OPEN_GROUPS):
    """Return raw items from the open Estimates groups (excludes Completed/
    Archive). Same items_page/next_items_page pagination shape used
    elsewhere in this module."""
    board_id = board_id or ESTIMATES_BOARD_ID
    items = []
    query = f'''
    query($boardId: [ID!]) {{
      boards(ids: $boardId) {{
        groups {{
          title
          items_page(limit: 50) {{
            cursor
            items {{
              id
              name
              group {{ title }}
              column_values(ids: {_ESTIMATES_COLUMN_IDS}) {{
                id
                text
                value
              }}
            }}
          }}
        }}
      }}
    }}
    '''
    boards = monday_graphql(query, {'boardId': [board_id]}).get('boards') or []
    for board in boards:
        for group in board.get('groups') or []:
            if groups and group.get('title') not in groups:
                continue
            page = group.get('items_page') or {}
            for it in page.get('items') or []:
                items.append(it)

            cursor = page.get('cursor')
            while cursor:
                next_page = monday_graphql(_ESTIMATES_NEXT_PAGE_QUERY, {'cursor': cursor}).get('next_items_page') or {}
                for it in next_page.get('items') or []:
                    it.setdefault('group', {'title': group.get('title')})
                    items.append(it)
                cursor = next_page.get('cursor')
    return items


def fetch_monday_users():
    """Return {person_id: email} for everyone on the Monday account —
    resolving a `people` column's assigned person to a real email needs
    this, since the people column itself only carries id + name."""
    query = '{ users { id name email } }'
    data = monday_graphql(query)
    return {str(u['id']): u.get('email') for u in (data.get('users') or []) if u.get('email')}


def parse_people_column(column_value):
    """column_value is the raw `value` JSON string from a `people` column —
    returns a list of person ID strings (kind == 'person', not 'team')."""
    raw = column_value.get('value') if isinstance(column_value, dict) else column_value
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    return [
        str(p['id']) for p in (parsed.get('personsAndTeams') or [])
        if p.get('kind') == 'person'
    ]
