"""Read-only join: Monday Production Board funnel × Hub documents.

Thomas, 2026-09-03: not a Hub Production Board. Monday stays the operating
system. This page reads four live groups (On Hold / Needs Scheduled /
Scheduled / In Progress) and puts Hub proposals, PPMs, and TPS next to each
job, joined on proposal number. Waiting on Margins, warranty, and close-out
are out. Nothing writes back.

The join key is proposal number, not Monday's connect columns — those were
empty when this board was sampled in August, same pattern as Pay Request.
A cell that says "Warranty work" is not a key. Numeric Monday numbers
(460136) are accepted as keys and will simply miss Hub docs that use
AP26155-style numbers; that miss is the finding, not a bug to paper over.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

from tiers import is_leadership

# The four live funnel groups, in the order Thomas named them. Adding a
# fifth here is how Waiting on Margins would leak onto the page — tests
# pin this tuple as exactly these four.
FUNNEL_GROUPS = (
    'Awarded - On Hold',
    'Needs Scheduled',
    'Scheduled',
    'In Progress',
)

# Titles on the Production Board, matched case-insensitively at runtime.
# Ids are not hardcoded: they drift (`dup__of_…` on Estimates).
COLUMN_TITLES = {
    'proposal_number': ('proposal number',),
    'ppm': ('ppm',),
    'survey': ('survey',),
    'consultant': ('consultant',),
    'project_manager': ('project manager',),
    'job_size': ('job size',),
    'trade': ('trade',),
    'mgmt_company': ('mgmt company',),
    'date_awarded': ('date awarded',),
    'timeline_start': ('estimated timeline - start',),
    'timeline_end': ('estimated timeline - end',),
    'sub_assigned': ('sub assigned',),
}

# AP26155, RF26165, CK4440D, TC7364 — Hub's own numbering.
_HUB_KEY_RE = re.compile(r'\b([A-Z]{1,4}\d{4,8}[A-Z]?)\b', re.I)
# Bare numeric cells on Monday (460136). Kept as a key so we can *see* they
# do not match Hub docs; we do not invent an AP prefix.
_NUMERIC_KEY_RE = re.compile(r'^\d{4,8}$')
_REJECT_RE = re.compile(
    r'warrant|\bn/?a\b|\btbd\b|\bnone\b|\bunknown\b|\btest\b',
    re.I,
)

FIXTURE_ENV = 'PRODUCTION_LINK_FIXTURE'


def can_view(users, user_key):
    """Leadership. Same people as Office Ops today; a separate function so
    this page cannot inherit a future narrowing of Office Ops, or vice versa.
    """
    return is_leadership(users, user_key)


def normalize_proposal_key(raw):
    """A joinable proposal number, or None.

    Rejects 'Warranty work', blanks, and sentences. Accepts Hub-style
    (AP26155, CK4440D) and a whole-field numeric token (460136). Hyphens
    inside a Hub-style number are stripped so AP-26155 still matches AP26155.
    """
    text = (raw or '').strip()
    if not text or _REJECT_RE.search(text):
        return None
    if _NUMERIC_KEY_RE.match(text):
        return text
    compact = re.sub(r'[\s\-]', '', text)
    if _NUMERIC_KEY_RE.match(compact):
        return compact
    m = _HUB_KEY_RE.search(text)
    if m:
        return m.group(1).replace('-', '').upper()
    m = _HUB_KEY_RE.search(compact)
    if m:
        return m.group(1).upper()
    return None


def keys_from_job(proposal_number, name):
    """(key, source). Column wins; the job name is a fallback when the
    column is blank or rejected. source is 'column', 'name', or None."""
    key = normalize_proposal_key(proposal_number)
    if key:
        return key, 'column'
    key = normalize_proposal_key(name)
    if key:
        return key, 'name'
    return None, None


def parse_money(raw):
    if raw is None or raw == '':
        return None
    cleaned = re.sub(r'[^0-9.\-]', '', str(raw))
    if cleaned in ('', '-', '.', '-.'):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def column_map(columns):
    """field → Monday column id, from live titles."""
    by_title = {}
    for col in columns or []:
        title = (col.get('title') or '').strip().lower()
        if title and col.get('id'):
            by_title[title] = col['id']
    out = {}
    for field, titles in COLUMN_TITLES.items():
        for t in titles:
            if t in by_title:
                out[field] = by_title[t]
                break
    return out


def _col_text(item, colmap, field):
    cid = colmap.get(field)
    if not cid:
        return ''
    for cv in item.get('column_values') or []:
        if cv.get('id') == cid:
            return (cv.get('text') or '').strip()
    return ''


def parse_monday_item(raw, colmap, board_url=None):
    """One Monday item → a flat job dict, no Hub docs yet."""
    group = ''
    g = raw.get('group')
    if isinstance(g, dict):
        group = g.get('title') or ''
    elif isinstance(g, str):
        group = g
    name = (raw.get('name') or '').strip()
    proposal_raw = _col_text(raw, colmap, 'proposal_number')
    key, key_source = keys_from_job(proposal_raw, name)
    item_id = str(raw.get('id') or '')
    url = (raw.get('url') or '').strip()
    if not url and board_url and item_id:
        url = f"{board_url.rstrip('/')}/pulses/{item_id}"
    ppm_text = _col_text(raw, colmap, 'ppm')
    monday_ppm = ppm_text if ppm_text else None
    return {
        'id': item_id,
        'name': name,
        'group': group,
        'consultant': _col_text(raw, colmap, 'consultant'),
        'project_manager': _col_text(raw, colmap, 'project_manager'),
        'proposal_number_raw': proposal_raw,
        'key': key,
        'key_source': key_source,
        'job_size': parse_money(_col_text(raw, colmap, 'job_size')),
        'trade': _col_text(raw, colmap, 'trade'),
        'mgmt_company': _col_text(raw, colmap, 'mgmt_company'),
        'date_awarded': _col_text(raw, colmap, 'date_awarded'),
        'timeline_start': _col_text(raw, colmap, 'timeline_start'),
        'timeline_end': _col_text(raw, colmap, 'timeline_end'),
        'sub_assigned': _col_text(raw, colmap, 'sub_assigned'),
        'survey': _col_text(raw, colmap, 'survey'),
        'monday_ppm': monday_ppm,
        'monday_url': url,
    }


def _put_doc(index, key, kind, row):
    if not key:
        return
    slot = index.setdefault(key, {})
    prev = slot.get(kind)
    if prev is None or (row.get('generated_at') or '') > (prev.get('generated_at') or ''):
        slot[kind] = row


def _row_from_sql(r, id_key='id'):
    if not r:
        return None
    if isinstance(r, dict):
        generated = r.get('generated_at')
        return {
            'id': r.get(id_key),
            'property_name': r.get('property_name') or '',
            'generated_at': generated.isoformat() if hasattr(generated, 'isoformat') else (generated or ''),
            'document_id': r.get('document_id'),
        }
    # tuple fallback: (id, proposal_number, property_name, generated_at, document_id?)
    generated = r[3] if len(r) > 3 else None
    return {
        'id': r[0],
        'property_name': r[2] or '' if len(r) > 2 else '',
        'generated_at': generated.isoformat() if hasattr(generated, 'isoformat') else (generated or ''),
        'document_id': r[4] if len(r) > 4 else None,
    }


def index_hub_docs(proposal_rows=None, ppm_rows=None, tps_rows=None):
    """{normalized_key: {proposal, ppm, tps}} from already-fetched rows.

    Latest generated_at wins per kind. Rows whose proposal_number does not
    normalize are dropped rather than guessed at.
    """
    index = {}
    for r in proposal_rows or []:
        raw = r.get('proposal_number') if isinstance(r, dict) else (r[1] if len(r) > 1 else '')
        key = normalize_proposal_key(raw)
        _put_doc(index, key, 'proposal', _row_from_sql(r))
    for r in ppm_rows or []:
        raw = r.get('proposal_number') if isinstance(r, dict) else (r[1] if len(r) > 1 else '')
        key = normalize_proposal_key(raw)
        _put_doc(index, key, 'ppm', _row_from_sql(r))
    for r in tps_rows or []:
        if isinstance(r, dict):
            raw = r.get('proposal_number') or r.get('po_number') or ''
        else:
            raw = r[1] if len(r) > 1 else ''
        key = normalize_proposal_key(raw)
        _put_doc(index, key, 'tps', _row_from_sql(r))
    return index


def load_hub_index(get_db_fn):
    """Best-effort. A missing table or a down database returns {} so the
    Monday jobs still render, with every Hub cell empty — that is 'not
    connected', not an empty board."""
    if not get_db_fn:
        return {}
    conn = None
    try:
        conn = get_db_fn()
        if not conn:
            return {}
        cur = conn.cursor()
        proposals, ppms, tps = [], [], []
        try:
            cur.execute(
                'SELECT id, proposal_number, property_name, generated_at, document_id '
                'FROM proposal_log WHERE proposal_number IS NOT NULL'
            )
            cols = ['id', 'proposal_number', 'property_name', 'generated_at', 'document_id']
            proposals = [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception as e:
            print(f'production_link proposal_log: {e}')
            conn.rollback()
        try:
            cur.execute(
                'SELECT id, proposal_number, property_name, generated_at '
                'FROM ppm_log WHERE proposal_number IS NOT NULL'
            )
            cols = ['id', 'proposal_number', 'property_name', 'generated_at']
            ppms = [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception as e:
            print(f'production_link ppm_log: {e}')
            conn.rollback()
        try:
            cur.execute(
                'SELECT id, COALESCE(proposal_number, po_number) AS proposal_number, '
                'property_name, generated_at '
                'FROM subscope_log'
            )
            cols = ['id', 'proposal_number', 'property_name', 'generated_at']
            tps = [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception as e:
            print(f'production_link subscope_log: {e}')
            try:
                conn.rollback()
            except Exception:
                pass
            try:
                cur.execute(
                    'SELECT id, po_number, property_name, generated_at FROM subscope_log'
                )
                cols = ['id', 'proposal_number', 'property_name', 'generated_at']
                tps = [dict(zip(cols, row)) for row in cur.fetchall()]
            except Exception as e2:
                print(f'production_link subscope_log po_number: {e2}')
                try:
                    conn.rollback()
                except Exception:
                    pass
        cur.close()
        return index_hub_docs(proposals, ppms, tps)
    except Exception as e:
        print(f'production_link hub index: {e}')
        return {}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _tool_urls(proposal_url, document_id, log_id=None):
    """PPM/TPS links that open the proposal tool with this vault file.

    No document_id → no links. A Monday number is not a file, and a blank
    /ppm form is not a link worth having.
    """
    if not proposal_url or not document_id:
        return '', ''
    base = proposal_url.rstrip('/')
    try:
        doc = int(document_id)
    except (TypeError, ValueError):
        return '', ''
    ppm = f'{base}/ppm?document={doc}'
    tps = f'{base}/subscope?document={doc}'
    try:
        log = int(log_id) if log_id is not None else 0
    except (TypeError, ValueError):
        log = 0
    if log:
        tps = f'{tps}&log={log}'
    return ppm, tps


def join_funnel(jobs, hub_index, proposal_url=None):
    """Attach Hub docs. Jobs outside FUNNEL_GROUPS are dropped — that is
    the whole point of the spike, not a display filter.
    """
    hub_index = hub_index or {}
    grouped = {g: [] for g in FUNNEL_GROUPS}
    for job in jobs or []:
        group = job.get('group')
        if group not in grouped:
            continue
        key = job.get('key')
        docs = hub_index.get(key) or {} if key else {}
        row = dict(job)
        row['hub_proposal'] = docs.get('proposal')
        row['hub_ppm'] = docs.get('ppm')
        row['hub_tps'] = docs.get('tps')
        prop = row['hub_proposal'] or {}
        row['ppm_url'], row['tps_url'] = _tool_urls(
            proposal_url, prop.get('document_id'), prop.get('id'))
        monday_yes = (row.get('monday_ppm') or '').strip().lower() == 'yes'
        row['ppm_gap'] = bool(key) and not row['hub_ppm']
        row['ppm_disagrees'] = monday_yes and not row['hub_ppm']
        if row['hub_ppm'] or row['hub_proposal']:
            row['link_state'] = 'linked'
        elif key:
            row['link_state'] = 'key_only'
        else:
            row['link_state'] = 'no_key'
        grouped[group].append(row)
    return grouped


def summarize(grouped):
    """Counts for the strip at the top. Never sums opens; this is jobs."""
    totals = {
        'jobs': 0,
        'with_key': 0,
        'hub_proposal': 0,
        'hub_ppm': 0,
        'hub_tps': 0,
        'ppm_gap': 0,
        'no_key': 0,
        'job_size': 0.0,
    }
    per_group = []
    for name in FUNNEL_GROUPS:
        rows = grouped.get(name) or []
        g = {
            'name': name,
            'jobs': len(rows),
            'with_key': sum(1 for r in rows if r.get('key')),
            'hub_ppm': sum(1 for r in rows if r.get('hub_ppm')),
            'ppm_gap': sum(1 for r in rows if r.get('ppm_gap')),
            'job_size': sum((r.get('job_size') or 0) for r in rows),
        }
        per_group.append(g)
        totals['jobs'] += g['jobs']
        totals['with_key'] += g['with_key']
        totals['hub_ppm'] += g['hub_ppm']
        totals['ppm_gap'] += g['ppm_gap']
        totals['job_size'] += g['job_size']
        totals['hub_proposal'] += sum(1 for r in rows if r.get('hub_proposal'))
        totals['hub_tps'] += sum(1 for r in rows if r.get('hub_tps'))
        totals['no_key'] += sum(1 for r in rows if not r.get('key'))
    return {'totals': totals, 'groups': per_group}


def _fixture_path():
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, 'tests', 'fixtures', 'production_funnel.json')


def load_fixture_jobs():
    """Sample jobs shipped with the tests. Used only when
    PRODUCTION_LINK_FIXTURE=1 — never the production default."""
    with open(_fixture_path(), encoding='utf-8') as fh:
        data = json.load(fh)
    colmap = data.get('colmap') or {
        'proposal_number': 'proposal_number',
        'ppm': 'ppm',
        'consultant': 'consultant',
        'project_manager': 'project_manager',
        'job_size': 'job_size',
        'trade': 'trade',
    }
    jobs = [parse_monday_item(raw, colmap, data.get('board_url'))
            for raw in data.get('items') or []]
    return jobs, data.get('hub_docs') or {}


def fetch_monday_jobs():
    """(jobs, error, source). error set ⇒ jobs is None, never []. The empty
    board is how Pipeline looked wiped; we will not repeat that."""
    if (os.environ.get(FIXTURE_ENV) or '').strip() == '1':
        try:
            jobs, _hub = load_fixture_jobs()
            return jobs, None, 'fixture'
        except Exception as e:
            return None, f'fixture: {e}', None
    try:
        import monday_client as mc
        desc = mc.describe_board(mc.PRODUCTION_BOARD_ID)
        if not desc:
            return None, 'Monday returned no Production Board', None
        colmap = column_map(desc.get('columns'))
        raw = mc.fetch_grouped_items(
            mc.PRODUCTION_BOARD_ID,
            FUNNEL_GROUPS,
            list(colmap.values()),
        )
        jobs = [parse_monday_item(item, colmap, desc.get('url')) for item in raw]
        return jobs, None, 'monday'
    except Exception as e:
        return None, str(e), None


def build_view(get_db_fn, proposal_url=None):
    """What the page renders. Never raises."""
    jobs, error, source = fetch_monday_jobs()
    hub_index = {}
    if source == 'fixture':
        try:
            _jobs, fixture_hub = load_fixture_jobs()
            hub_index = index_hub_docs(
                fixture_hub.get('proposals'),
                fixture_hub.get('ppms'),
                fixture_hub.get('tps'),
            )
        except Exception:
            hub_index = {}
    db_index = load_hub_index(get_db_fn)
    # Live Hub docs overlay the fixture's sample docs so a local demo with a
    # real database shows real matches; empty db_index is a no-op.
    for key, docs in db_index.items():
        slot = hub_index.setdefault(key, {})
        slot.update(docs)
    grouped = join_funnel(jobs or [], hub_index, proposal_url=proposal_url)
    summary = summarize(grouped)
    return {
        'groups': grouped,
        'summary': summary,
        'error': error,
        'source': source,
        'funnel_groups': FUNNEL_GROUPS,
        'fetched_at': datetime.now(timezone.utc).replace(tzinfo=None),
    }


def register_routes(app, get_db_fn, users, require_login):
    from flask import redirect, render_template, session, url_for

    import hub_time
    from hub_usage import record_open

    @app.route('/production-link')
    @require_login
    def production_link_page():
        user_key = session.get('user_key')
        if not can_view(users, user_key):
            return redirect(url_for('dashboard'))
        proposal_url = os.environ.get(
            'PROPOSAL_URL', 'https://pps-proposal-tool.onrender.com')
        view = build_view(get_db_fn, proposal_url=proposal_url)
        try:
            record_open(get_db_fn, user_key, 'production_link')
        except Exception as e:
            print(f'production_link usage: {e}')
        user = users.get(user_key) or {}
        fetched = view['fetched_at']
        return render_template(
            'production_link.html',
            user_display=user.get('display', user_key),
            groups=view['groups'],
            summary=view['summary'],
            error=view['error'],
            source=view['source'],
            funnel_groups=view['funnel_groups'],
            fetched_label=hub_time.fmt(fetched, '%b %-d, %-I:%M %p') if fetched else '',
            proposal_url=proposal_url,
        )
