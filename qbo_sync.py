"""QuickBooks Online nightly pull. Step 2: invoiced sales, stored as totals.

Thomas, 2026-11-23. The dashboard shows company invoiced YTD and invoiced
YTD per Property Solutions Consultant. It reads only the tables this module
writes. It never calls QuickBooks.

What was decided, so the next step does not relitigate it:

- Gross invoiced. Invoices only. Credit memos are not read and do not
  lower anyone's number (Thomas: "Credit memos shouldn't matter then. Let's
  do gross invoice").
- The amount is the invoice total less its sales tax. Sales tax is money
  collected for the state, not sales. A voided invoice comes back with a
  total of zero, so it counts as zero. A deleted invoice does not come back.
- Every run re-reads every invoice dated this calendar year. Edits, voids,
  and deletes are always reflected, and there is no "changed since" cursor
  to drift. One run replaces the year's rows in one transaction, so the
  dashboard never sees half a sync. A failed run leaves the last good
  numbers in place and records the problem.
- A shared invoice ("Adam / Rachel") is split evenly between the names,
  the same rule Office Ops uses. The company total counts the invoice once.
- The "Consultant" custom field is free text. It is stored as written.
  Matching a name to a Hub person happens when the totals are read, so a
  fix on the admin page applies without another sync. A name that matches
  nobody is listed on the admin page.
- Everyone who signs in sees the company total and every consultant
  (Thomas, 2026-11-23). That is step 4. Former employees stay in the
  company total and drop off the per-person list.
- Runs once a night at midnight US/Eastern, plus "Sync now" on the admin
  page. The cron fires at 04:05 and 05:05 UTC and the run happens only
  when the Eastern hour is 0.
- Read only. Every QuickBooks call goes through ``qbo_connect.accounting_get``.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from psycopg2.extras import RealDictCursor

import qbo_connect

ET = ZoneInfo('America/New_York')

PAGE_SIZE = 1000
# 50,000 invoices in a year is far past anything PPS writes. The cap is a
# guard against a paging bug looping forever, not a business limit.
MAX_PAGES = 50
# Refresh a little early so a slow page does not run past the hour.
REFRESH_MARGIN = timedelta(minutes=5)

FIELD_CONSULTANT = 'consultant'
FIELD_CITY = 'city'
FIELD_CUSTOMER_CODE = 'customer code'

NO_CONSULTANT = ''
NO_CITY = ''

_SPLIT_RE = re.compile(r'\s*/\s*|\s*&\s*|\s+and\s+', re.I)
_SPACES_RE = re.compile(r'\s+')


class QboSyncError(Exception):
    """A run did not finish. The message is safe to show the owner and to email."""


# ── Tables ──────────────────────────────────────────────────────────────────


def init_tables(cur):
    cur.execute('''
        CREATE TABLE IF NOT EXISTS qbo_sales_monthly (
            year SMALLINT NOT NULL,
            month SMALLINT NOT NULL,
            consultant VARCHAR(120) NOT NULL DEFAULT '',
            city VARCHAR(120) NOT NULL DEFAULT '',
            amount NUMERIC(16, 4) NOT NULL DEFAULT 0,
            invoice_share NUMERIC(10, 4) NOT NULL DEFAULT 0,
            PRIMARY KEY (year, month, consultant, city)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS qbo_sync_status (
            id SMALLINT PRIMARY KEY DEFAULT 1,
            year SMALLINT,
            last_synced_at TIMESTAMPTZ,
            invoice_count INTEGER,
            company_total NUMERIC(16, 2),
            no_consultant_count INTEGER,
            no_consultant_total NUMERIC(16, 2),
            consultant_field_seen BOOLEAN,
            last_run_at TIMESTAMPTZ,
            last_run_by VARCHAR(100),
            last_error TEXT,
            last_error_at TIMESTAMPTZ,
            CONSTRAINT qbo_sync_status_singleton CHECK (id = 1)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS qbo_consultant_map (
            qb_name VARCHAR(120) PRIMARY KEY,
            user_key VARCHAR(100) NOT NULL,
            set_by VARCHAR(100),
            set_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    ''')


# ── Small helpers ───────────────────────────────────────────────────────────


def eastern_now():
    return datetime.now(ET)


def is_midnight_eastern(now=None):
    return (now or eastern_now()).hour == 0


def clean_name(value):
    """Trim and collapse spaces. Case is kept for display."""
    if not isinstance(value, str):
        return ''
    return _SPACES_RE.sub(' ', value).strip()[:120]


def name_key(value):
    return clean_name(value).lower()


def split_consultants(raw):
    """'Adam / Rachel' -> ['Adam', 'Rachel']. Duplicates dropped, order kept."""
    out = []
    seen = set()
    for part in _SPLIT_RE.split(raw or ''):
        name = clean_name(part)
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return out


def _money(value):
    if value in (None, ''):
        return Decimal('0')
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal('0')


def custom_fields(invoice):
    """{'consultant': 'Andy Potts', 'city': 'Dayton', ...}, names lowercased."""
    out = {}
    for field in invoice.get('CustomField') or []:
        if not isinstance(field, dict):
            continue
        label = name_key(field.get('Name'))
        if not label:
            continue
        out[label] = clean_name(field.get('StringValue'))
    return out


def invoice_amount(invoice):
    """Invoice total less sales tax."""
    total = _money(invoice.get('TotalAmt'))
    tax = _money((invoice.get('TxnTaxDetail') or {}).get('TotalTax'))
    return total - tax


def invoice_month(invoice, year):
    raw = invoice.get('TxnDate') or ''
    try:
        d = date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None
    if d.year != year:
        return None
    return d.month


def tally(invoices, year):
    """Invoices -> monthly rows and run facts. Pure, so the tests can drive it.

    Rows are keyed (month, consultant, city). A shared invoice adds an even
    share of its amount, and an even share of one invoice, to each name.
    """
    rows = {}
    facts = {
        'invoice_count': 0,
        'company_total': Decimal('0'),
        'no_consultant_count': 0,
        'no_consultant_total': Decimal('0'),
        'consultant_field_seen': False,
        'skipped_other_year': 0,
    }
    seen_ids = set()
    for inv in invoices:
        if not isinstance(inv, dict):
            continue
        inv_id = inv.get('Id')
        if inv_id is not None:
            if inv_id in seen_ids:
                continue
            seen_ids.add(inv_id)
        month = invoice_month(inv, year)
        if month is None:
            facts['skipped_other_year'] += 1
            continue
        amount = invoice_amount(inv)
        fields = custom_fields(inv)
        if FIELD_CONSULTANT in fields:
            facts['consultant_field_seen'] = True
        city = fields.get(FIELD_CITY) or NO_CITY
        names = split_consultants(fields.get(FIELD_CONSULTANT) or '')
        facts['invoice_count'] += 1
        facts['company_total'] += amount
        if not names:
            facts['no_consultant_count'] += 1
            facts['no_consultant_total'] += amount
            names = [NO_CONSULTANT]
        share_amount = amount / len(names)
        share_count = Decimal('1') / len(names)
        for name in names:
            key = (month, name, city)
            cur = rows.get(key)
            if cur is None:
                rows[key] = [share_amount, share_count]
            else:
                cur[0] += share_amount
                cur[1] += share_count
    return rows, facts


# ── Tokens ──────────────────────────────────────────────────────────────────


def _record_connection_error(get_db_fn, message):
    """Put the problem on the connection row too, so the admin page shows it."""
    def write(cur):
        cur.execute(
            'UPDATE qbo_connection SET last_error = %s, last_error_at = NOW() WHERE id = 1',
            (message,),
        )
    try:
        qbo_connect._run_write(get_db_fn, write)
    except Exception as exc:
        print(f'qbo sync could not record connection error: {type(exc).__name__}')


def _refresh(get_db_fn, tokens):
    try:
        payload = qbo_connect.refresh_tokens(tokens['refresh_token'])
    except qbo_connect.QboAuthError as exc:
        message = (
            f'{exc} QuickBooks needs to be reconnected on Admin → QuickBooks. '
            'Until then the dashboard keeps the last numbers it had.'
        )
        _record_connection_error(get_db_fn, message)
        raise QboSyncError(message)
    # Intuit has already retired the old refresh token. Store the new pair
    # before anything else can fail.
    qbo_connect.replace_tokens(get_db_fn, payload)
    tokens = dict(tokens)
    tokens['access_token'] = payload['access_token']
    tokens['refresh_token'] = payload['refresh_token']
    return tokens


def _fresh_tokens(get_db_fn):
    tokens = qbo_connect.load_tokens(get_db_fn)
    if not tokens:
        raise QboSyncError('QuickBooks is not connected, or the stored tokens could not be read.')
    expires = tokens.get('access_expires_at')
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires is None or expires - REFRESH_MARGIN <= datetime.now(timezone.utc):
        tokens = _refresh(get_db_fn, tokens)
    return tokens


# ── Pull ────────────────────────────────────────────────────────────────────


def invoice_query(year, start_position):
    return (
        f"SELECT * FROM Invoice WHERE TxnDate >= '{year:04d}-01-01' "
        f"AND TxnDate <= '{year:04d}-12-31' "
        f'STARTPOSITION {int(start_position)} MAXRESULTS {PAGE_SIZE}'
    )


def _get_page(get_db_fn, tokens, year, start_position):
    """One page of invoices. Refreshes once on a 401. Returns (tokens, invoices)."""
    for attempt in (1, 2):
        resp = qbo_connect.accounting_get(
            tokens['environment'],
            tokens['realm_id'],
            'query',
            params={'query': invoice_query(year, start_position)},
            headers={
                'Authorization': 'Bearer ' + tokens['access_token'],
                'Accept': 'application/json',
            },
        )
        # Intuit support traces a call by this id. Logged for every query,
        # and carried into any error the owner sees or is emailed.
        print(f'qbo query start={start_position} status={resp.status_code} '
              f'intuit_tid={qbo_connect.intuit_tid(resp) or "-"}')
        if resp.status_code == 401 and attempt == 1:
            tokens = _refresh(get_db_fn, tokens)
            continue
        if resp.status_code == 429:
            raise QboSyncError(qbo_connect.with_tid('QuickBooks asked the Hub to slow down. The next run will try again.', resp))
        if resp.status_code != 200:
            raise QboSyncError(qbo_connect.with_tid(f'QuickBooks answered {resp.status_code} to the invoice query.', resp))
        try:
            body = resp.json()
        except Exception:
            raise QboSyncError(qbo_connect.with_tid('QuickBooks returned something that was not JSON.', resp))
        query_response = (body or {}).get('QueryResponse')
        if not isinstance(query_response, dict):
            raise QboSyncError(qbo_connect.with_tid('QuickBooks did not return a query result.', resp))
        invoices = query_response.get('Invoice') or []
        if not isinstance(invoices, list):
            raise QboSyncError('QuickBooks did not return a list of invoices.')
        return tokens, invoices
    raise QboSyncError('QuickBooks refused the token twice.')


def pull_year(get_db_fn, year):
    tokens = _fresh_tokens(get_db_fn)
    out = []
    start = 1
    for _ in range(MAX_PAGES):
        tokens, page = _get_page(get_db_fn, tokens, year, start)
        out.extend(page)
        if len(page) < PAGE_SIZE:
            return out
        start += PAGE_SIZE
    raise QboSyncError(f'Stopped after {MAX_PAGES} pages of invoices. Nothing was saved.')


# ── Store ───────────────────────────────────────────────────────────────────


def store(get_db_fn, year, rows, facts, run_by):
    def write(cur):
        cur.execute('DELETE FROM qbo_sales_monthly WHERE year = %s', (year,))
        for (month, consultant, city), (amount, share) in sorted(rows.items()):
            cur.execute(
                '''INSERT INTO qbo_sales_monthly
                       (year, month, consultant, city, amount, invoice_share)
                   VALUES (%s, %s, %s, %s, %s, %s)''',
                (year, month, consultant, city, amount, share),
            )
        cur.execute(
            '''INSERT INTO qbo_sync_status (
                   id, year, last_synced_at, invoice_count, company_total,
                   no_consultant_count, no_consultant_total, consultant_field_seen,
                   last_run_at, last_run_by, last_error, last_error_at
               ) VALUES (1, %s, NOW(), %s, %s, %s, %s, %s, NOW(), %s, NULL, NULL)
               ON CONFLICT (id) DO UPDATE SET
                   year = EXCLUDED.year,
                   last_synced_at = EXCLUDED.last_synced_at,
                   invoice_count = EXCLUDED.invoice_count,
                   company_total = EXCLUDED.company_total,
                   no_consultant_count = EXCLUDED.no_consultant_count,
                   no_consultant_total = EXCLUDED.no_consultant_total,
                   consultant_field_seen = EXCLUDED.consultant_field_seen,
                   last_run_at = EXCLUDED.last_run_at,
                   last_run_by = EXCLUDED.last_run_by,
                   last_error = NULL,
                   last_error_at = NULL''',
            (
                year,
                facts['invoice_count'],
                facts['company_total'],
                facts['no_consultant_count'],
                facts['no_consultant_total'],
                facts['consultant_field_seen'],
                run_by,
            ),
        )

    qbo_connect._run_write(get_db_fn, write)


def record_failure(get_db_fn, message, run_by):
    """Keep the last good numbers. Note what went wrong and when."""
    def write(cur):
        cur.execute(
            '''INSERT INTO qbo_sync_status (id, last_run_at, last_run_by, last_error, last_error_at)
               VALUES (1, NOW(), %s, %s, NOW())
               ON CONFLICT (id) DO UPDATE SET
                   last_run_at = NOW(),
                   last_run_by = EXCLUDED.last_run_by,
                   last_error = EXCLUDED.last_error,
                   last_error_at = NOW()''',
            (run_by, message),
        )
    try:
        qbo_connect._run_write(get_db_fn, write)
    except Exception as exc:
        print(f'qbo sync could not record failure: {type(exc).__name__}')


# ── Run ─────────────────────────────────────────────────────────────────────


def run_sync(get_db_fn, *, run_by='nightly', year=None):
    """Pull this year's invoices and replace the stored totals.

    Returns a dict that is safe to log and to return from the cron endpoint.
    It never contains a token.
    """
    year = year or eastern_now().year
    try:
        invoices = pull_year(get_db_fn, year)
        rows, facts = tally(invoices, year)
        store(get_db_fn, year, rows, facts, run_by)
    except QboSyncError as exc:
        record_failure(get_db_fn, str(exc), run_by)
        print(f'qbo sync failed: {exc}')
        return {'ok': False, 'error': str(exc)}
    except qbo_connect.QboWriteBlocked:
        message = 'A QuickBooks call was refused because it was not a read. Nothing was saved.'
        record_failure(get_db_fn, message, run_by)
        print('qbo sync failed: write blocked')
        return {'ok': False, 'error': message}
    except (qbo_connect.QboAuthError, qbo_connect.QboConfigError) as exc:
        message = str(exc) or 'QuickBooks could not be reached.'
        record_failure(get_db_fn, message, run_by)
        print(f'qbo sync failed: {type(exc).__name__}')
        return {'ok': False, 'error': message}
    except Exception as exc:
        message = 'The sync stopped on an unexpected error. Nothing was saved.'
        record_failure(get_db_fn, message, run_by)
        print(f'qbo sync failed: {type(exc).__name__}')
        return {'ok': False, 'error': message}
    print(
        f'qbo sync ok year={year} invoices={facts["invoice_count"]} '
        f'no_consultant={facts["no_consultant_count"]} by={run_by}'
    )
    return {
        'ok': True,
        'year': year,
        'invoices': facts['invoice_count'],
        'company_total': str(facts['company_total'].quantize(Decimal('0.01'), ROUND_HALF_UP)),
        'no_consultant': facts['no_consultant_count'],
        'consultant_field_seen': facts['consultant_field_seen'],
    }


# ── Read (admin page now, dashboard in step 4) ──────────────────────────────


def _read(get_db_fn, sql, params=()):
    conn = get_db_fn()
    if conn is None:
        return []
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute(sql, params)
            return cur.fetchall()
        finally:
            cur.close()
    finally:
        try:
            conn.close()
        except Exception:
            pass


def sync_status(get_db_fn):
    try:
        rows = _read(get_db_fn, 'SELECT * FROM qbo_sync_status WHERE id = 1')
    except Exception as exc:
        print(f'qbo sync status read failed: {type(exc).__name__}')
        return None
    return rows[0] if rows else None


def consultant_map(get_db_fn):
    try:
        rows = _read(get_db_fn, 'SELECT qb_name, user_key FROM qbo_consultant_map')
    except Exception as exc:
        print(f'qbo consultant map read failed: {type(exc).__name__}')
        return {}
    return {r['qb_name']: r['user_key'] for r in rows}


def resolve_consultant(qb_name, users, saved_map):
    """QuickBooks name -> Hub user key, or None.

    Order: a match saved on the admin page, then the full display name,
    then a first name that belongs to exactly one person on the roster.
    """
    key = name_key(qb_name)
    if not key:
        return None
    saved = saved_map.get(key)
    if saved and saved in users:
        return saved
    for user_key, user in users.items():
        if name_key(user.get('display')) == key:
            return user_key
    if ' ' not in key:
        hits = [
            k for k, u in users.items()
            if name_key(u.get('display')).split(' ')[0] == key
        ]
        if len(hits) == 1:
            return hits[0]
    return None


def year_summary(get_db_fn, users, saved_map=None, year=None):
    """Totals by QuickBooks name and by Hub person, for one year.

    ``by_name`` keeps every Consultant value as written, with the person it
    resolves to (or None). ``by_person`` adds those up per Hub user.
    """
    year = year or eastern_now().year
    if saved_map is None:
        saved_map = consultant_map(get_db_fn)
    try:
        rows = _read(
            get_db_fn,
            '''SELECT consultant, city, SUM(amount) AS amount, SUM(invoice_share) AS invoices
               FROM qbo_sales_monthly WHERE year = %s
               GROUP BY consultant, city''',
            (year,),
        )
    except Exception as exc:
        print(f'qbo summary read failed: {type(exc).__name__}')
        rows = []
    by_name = {}
    by_city = {}
    for r in rows:
        amount = _money(r['amount'])
        invoices = _money(r['invoices'])
        name = r['consultant'] or NO_CONSULTANT
        entry = by_name.setdefault(name, {'name': name, 'amount': Decimal('0'), 'invoices': Decimal('0')})
        entry['amount'] += amount
        entry['invoices'] += invoices
        city = r['city'] or NO_CITY
        by_city[city] = by_city.get(city, Decimal('0')) + amount
    by_person = {}
    for entry in by_name.values():
        user_key = resolve_consultant(entry['name'], users, saved_map) if entry['name'] else None
        entry['user_key'] = user_key
        if user_key:
            person = by_person.setdefault(user_key, {
                'user_key': user_key,
                'display': users[user_key].get('display', user_key),
                'amount': Decimal('0'),
            })
            person['amount'] += entry['amount']
    return {
        'year': year,
        'by_name': sorted(by_name.values(), key=lambda e: (-e['amount'], e['name'])),
        'by_person': sorted(by_person.values(), key=lambda e: -e['amount']),
        'by_city': sorted(by_city.items(), key=lambda kv: -kv[1]),
        'company_total': sum((e['amount'] for e in by_name.values()), Decimal('0')),
    }


def save_mapping(get_db_fn, qb_name, user_key, set_by):
    key = name_key(qb_name)
    if not key:
        return

    def write(cur):
        if user_key:
            cur.execute(
                '''INSERT INTO qbo_consultant_map (qb_name, user_key, set_by, set_at)
                   VALUES (%s, %s, %s, NOW())
                   ON CONFLICT (qb_name) DO UPDATE SET
                       user_key = EXCLUDED.user_key,
                       set_by = EXCLUDED.set_by,
                       set_at = NOW()''',
                (key, user_key, set_by),
            )
        else:
            cur.execute('DELETE FROM qbo_consultant_map WHERE qb_name = %s', (key,))

    qbo_connect._run_write(get_db_fn, write)


def admin_context(get_db_fn, users):
    """What the owner page shows under Connection. No tokens are read here."""
    saved_map = consultant_map(get_db_fn)
    status = sync_status(get_db_fn)
    year = (status or {}).get('year') or eastern_now().year
    summary = year_summary(get_db_fn, users, saved_map, year=year)
    unmatched = [e for e in summary['by_name'] if e['name'] and not e['user_key']]
    people = sorted(
        ((k, u.get('display', k)) for k, u in users.items()),
        key=lambda kv: kv[1],
    )
    return {
        'sync': status,
        'summary': summary,
        'unmatched_count': len(unmatched),
        'saved_map': saved_map,
        'people': people,
    }


# ── Alert ───────────────────────────────────────────────────────────────────


def alert_owner(send_email_fn, recipients, error):
    """Email when the nightly run fails, so the numbers never go stale quietly."""
    if not send_email_fn or not recipients:
        return False
    subject = 'Hub: QuickBooks sync did not run'
    text = (
        'Last night\'s QuickBooks sync did not finish.\n\n'
        f'{error}\n\n'
        'The dashboard still shows the last numbers that synced. '
        'Open Admin → QuickBooks on the Hub to see the details or run it again.\n'
    )
    html = (
        '<p>Last night\'s QuickBooks sync did not finish.</p>'
        f'<p>{_escape(error)}</p>'
        '<p>The dashboard still shows the last numbers that synced. '
        'Open Admin → QuickBooks on the Hub to see the details or run it again.</p>'
    )
    try:
        return bool(send_email_fn(subject, text, html, recipients))
    except Exception as exc:
        print(f'qbo sync alert email failed: {type(exc).__name__}')
        return False


def _escape(text):
    return (
        str(text or '')
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
    )


# ── Routes ──────────────────────────────────────────────────────────────────


def register_routes(app, get_db_fn, require_admin, users, internal_api_ok, send_email_fn, owner_emails):
    from flask import jsonify, redirect, request, session, url_for

    @app.route('/admin/quickbooks/sync', methods=['POST'])
    @require_admin
    def admin_quickbooks_sync():
        result = run_sync(get_db_fn, run_by=session.get('user_key') or 'owner')
        return redirect(url_for('admin_quickbooks', notice='synced' if result['ok'] else 'sync_failed'))

    @app.route('/admin/quickbooks/map', methods=['POST'])
    @require_admin
    def admin_quickbooks_map():
        qb_name = request.form.get('qb_name') or ''
        user_key = (request.form.get('user_key') or '').strip()
        if user_key and user_key not in users:
            return redirect(url_for('admin_quickbooks', notice='map_bad'))
        try:
            save_mapping(get_db_fn, qb_name, user_key, session.get('user_key'))
        except Exception as exc:
            print(f'qbo map save failed: {type(exc).__name__}')
            return redirect(url_for('admin_quickbooks', notice='map_bad'))
        return redirect(url_for('admin_quickbooks', notice='mapped'))

    @app.route('/api/cron/qbo-sync', methods=['POST'])
    def cron_qbo_sync():
        if not internal_api_ok():
            return jsonify({'error': 'Unauthorized'}), 401
        force = (request.args.get('force') or '').lower() in ('1', 'true', 'yes')
        if not force and not is_midnight_eastern():
            return jsonify({'ok': True, 'skipped': True, 'reason': 'not midnight Eastern'}), 200
        result = run_sync(get_db_fn, run_by='nightly')
        if not result['ok']:
            result['alerted'] = alert_owner(send_email_fn, owner_emails(), result['error'])
        return jsonify(result), 200
