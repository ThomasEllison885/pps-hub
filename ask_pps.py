"""Ask PPS — closed-book internal knowledge assistant."""

import json
import os
import re
import time
from datetime import date, datetime
from functools import wraps

from flask import jsonify, redirect, render_template, request, session, url_for
from psycopg2.extras import RealDictCursor

from estimators.pricing_defaults import SYSTEM_DEFAULTS, get_pricing_defaults
from psc_training_data import (
    PSC_CORE_VALUES,
    PSC_COMPANY_OPERATIONS,
    get_training_curriculum,
)

CURATORS = frozenset({'thomas_ellison', 'tony_cumella', 'trey_hollmeyer'})

CATEGORIES = [
    'voice_language',
    'sales_process',
    'production_process',
    'trades',
    'training_core_values',
    'company_operations',
    'team_directory',
    'pricing',
    'general',
]

DAILY_LIMIT = 30
MAX_QUESTION_LEN = 500
MAX_SUGGEST_LEN = 5000
MAX_CONTEXT_CHARS = 6000
MAX_TOKENS = 700

PROPOSAL_VOICE_PATH = os.path.join(
    os.path.dirname(__file__), 'knowledge_sources', 'pps_proposal_voice.txt',
)

PRODUCTION_KEYWORDS = re.compile(
    r'\b(schedul|trade partner|crew|mobiliz|field|production|ppm|site visit|'
    r'punch list|close-?out|pm\b|building access|48.hour)\b',
    re.I,
)
SALES_KEYWORDS = re.compile(
    r'\b(proposal|client|consultant|pricing|sell|scope|voice|condo|apartment|'
    r'board|investment|award|bid)\b',
    re.I,
)

SYSTEM_PROMPT = """You are Ask PPS, the internal knowledge assistant for Pure Property Solutions (PPS),
an Ohio multi-family and commercial property contractor. You answer questions from
PPS team members using ONLY the documented knowledge entries provided below.

HARD RULES:
- Closed book. If the provided entries do not contain the answer, do not improvise,
  do not use general knowledge about construction or business, do not guess company
  policy. Instead set "answered" to false and route the person (see routing).
- Cite sources: reference the entry titles you drew from.
- Keep answers short and practical — a few sentences to a short paragraph. This is
  a busy team on phones.
- PRICING questions: if pricing entries are provided, you may share the documented
  default, but ALWAYS (a) ask what project/context they are pricing for, and
  (b) state that final pricing depends on the project and is confirmed with Tony
  or through the estimators. Never present a price as final or quotable.
- ROUTING when not documented: sales, proposals, clients, consultant questions → Tony
  Cumella (VP of Sales, Tony@purepropsolutions.com). Production, scheduling, Trade
  Partners, field questions → Trey Hollmeyer (Production Manager, trey@purepropsolutions.com).
  Everything else → Thomas Ellison (President, thomas@purepropsolutions.com).
- Use PPS language in your own words: "residents" not "tenants", "apartment
  community" not "complex", "Trade Partners" not "subcontractors".

Respond ONLY with JSON, no markdown fences:
{
  "answered": true|false,
  "answer": "...",
  "sources": ["entry title", ...],
  "gap_summary": "..."
}

KNOWLEDGE ENTRIES:
{entries}
"""


def is_curator(user_key):
    return user_key in CURATORS


def require_ask_pps_curator(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_key') or not is_curator(session['user_key']):
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


def init_tables(cur):
    cur.execute('''
        CREATE TABLE IF NOT EXISTS knowledge_entries (
            id SERIAL PRIMARY KEY,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            source_type TEXT NOT NULL,
            author_key TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            search_tsv TSVECTOR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS ask_pps_questions (
            id SERIAL PRIMARY KEY,
            user_key TEXT NOT NULL,
            question TEXT NOT NULL,
            answer TEXT,
            sources TEXT,
            answered BOOLEAN NOT NULL,
            gap_status TEXT DEFAULT NULL,
            gap_topic TEXT DEFAULT NULL,
            gap_summary TEXT DEFAULT NULL,
            resolved_entry_id INTEGER,
            flagged BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS ask_pps_daily_usage (
            user_key TEXT NOT NULL,
            usage_date DATE NOT NULL DEFAULT CURRENT_DATE,
            question_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_key, usage_date)
        )
    ''')
    try:
        cur.execute(
            'CREATE INDEX IF NOT EXISTS idx_knowledge_tsv ON knowledge_entries USING GIN(search_tsv)'
        )
        cur.execute(
            'CREATE INDEX IF NOT EXISTS idx_knowledge_status ON knowledge_entries(status)'
        )
        cur.execute(
            'CREATE INDEX IF NOT EXISTS idx_ask_pps_questions_user ON ask_pps_questions(user_key)'
        )
        cur.execute(
            'CREATE INDEX IF NOT EXISTS idx_ask_pps_questions_gap ON ask_pps_questions(gap_status)'
        )
        cur.execute(
            "ALTER TABLE ask_pps_questions ADD COLUMN IF NOT EXISTS gap_topic TEXT"
        )
        cur.execute(
            "ALTER TABLE ask_pps_questions ADD COLUMN IF NOT EXISTS gap_summary TEXT"
        )
    except Exception:
        pass


def _tsv_sql():
    return "to_tsvector('english', coalesce(title,'') || ' ' || coalesce(content,''))"


def _insert_entry(cur, category, title, content, source_type, author_key=None, status='active'):
    cur.execute(
        '''INSERT INTO knowledge_entries
           (category, title, content, source_type, author_key, status, search_tsv)
           VALUES (%s, %s, %s, %s, %s, %s,
                   to_tsvector('english', coalesce(%s, '') || ' ' || coalesce(%s, '')))''',
        (category, title, content, source_type, author_key, status, title, content),
    )


def _entry_exists(cur, title):
    cur.execute(
        "SELECT id FROM knowledge_entries WHERE title = %s AND status != 'archived' LIMIT 1",
        (title,),
    )
    return cur.fetchone() is not None


def _parse_voice_sections(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        text = f.read()
    parts = re.split(r'━+\s*\nSECTION\s+(\d+)\s*[—–-]\s*([^\n]+)\s*\n━+', text)
    entries = []
    if len(parts) < 2:
        return entries
    for i in range(1, len(parts), 3):
        if i + 2 > len(parts):
            break
        sec_num = parts[i].strip()
        sec_title = parts[i + 1].strip()
        body = parts[i + 2].strip()
        if not body or sec_title.upper().startswith('CONSULTANT NOTES'):
            continue
        if len(body) > 2200:
            body = body[:2200] + '…'
        entries.append({
            'category': 'voice_language',
            'title': f'Proposal voice — {sec_title}',
            'content': body,
        })
    return entries


def _team_directory_entries(users):
    blurbs = {
        'thomas_ellison': (
            'Thomas Ellison — President. Owns company systems, hub tools, and escalations '
            'that are not sales or production. Ask PPS curation and general policy gaps.'
        ),
        'tony_cumella': (
            'Tony Cumella — VP of Sales. Owns consultants, sales process, proposals, '
            'client relationships, and proposal sign-off. Route sales and proposal questions here.'
        ),
        'trey_hollmeyer': (
            'Trey Hollmeyer — Production Manager. Owns production, scheduling, Trade Partners, '
            'field execution, and PM coordination. Route production and field questions here.'
        ),
    }
    rows = []
    for key, user in users.items():
        display = user.get('display', key)
        title = user.get('title', '')
        email = user.get('email', '')
        role = user.get('role', '')
        extra = blurbs.get(key, '')
        content = f'{display} — {title}. Email: {email}. Hub role: {role}.'
        if extra:
            content += f' {extra}'
        rows.append({
            'category': 'team_directory',
            'title': f'Team — {display}',
            'content': content,
        })
    return rows


def _training_seed_entries():
    entries = []
    for section in PSC_CORE_VALUES.get('sections', []):
        acts = section.get('activities', [])
        act_lines = '\n'.join(f'- {a["title"]}: {a["text"][:120]}…' if len(a.get('text', '')) > 120
                              else f'- {a["title"]}: {a.get("text", "")}' for a in acts[:3])
        content = section.get('content', '')
        if act_lines:
            content = f'{content}\n\nKey activities:\n{act_lines}'
        entries.append({
            'category': 'training_core_values',
            'title': f'PSC training — {section["title"]}',
            'content': content[:1800],
        })

    _, weeks, _, sales_training, company_operations = get_training_curriculum()

    for module in sales_training.get('modules', [])[:5]:
        items = module.get('items', [])
        bullets = '\n'.join(f'- {it["title"]}' for it in items[:4])
        entries.append({
            'category': 'sales_process',
            'title': f'Sales training — {module["title"]}',
            'content': f'{module.get("summary", "")}\n\nTopics:\n{bullets}'[:1600],
        })

    ops_ids = {'ops_lifecycle', 'ops_trade_partners', 'ops_estimating', 'ops_client_comms'}
    for module in company_operations.get('modules', []):
        if module.get('id') not in ops_ids and module.get('assigned_week', 99) > 2:
            continue
        sop = '\n'.join(f'- {s}' for s in module.get('sop_placeholders', [])[:5])
        entries.append({
            'category': 'company_operations' if module['id'].startswith('ops_') else 'production_process',
            'title': f'Company ops — {module["title"]}',
            'content': f'{module.get("summary", "")}\n\nSOP highlights:\n{sop}\n\n'
                       f'Manager 1:1: {module.get("manager_1on1", "")[:400]}'[:1700],
        })

    for week in weeks[:4]:
        focus = week.get('pps_focus', [])
        if not focus:
            continue
        lines = '\n'.join(
            f'- {f.get("title", "Focus")}: {f.get("text", "")[:200]}' for f in focus[:3]
        )
        wk = week.get('week') or week.get('week_num', '?')
        topic = week.get('topic') or week.get('segment', 'Trade focus')
        entries.append({
            'category': 'trades',
            'title': f'PSC Week {wk} — {topic}',
            'content': lines[:1500],
        })

    return entries


def _pricing_seed_entries(get_db_fn):
    entries = []
    defaults = get_pricing_defaults(get_db_fn)
    for trade, fields in SYSTEM_DEFAULTS.items():
        stored = (defaults or {}).get(trade, {})
        merged = {**fields, **{k: v for k, v in (stored or {}).items() if v is not None and v != ''}}
        parts = ', '.join(f'{k}: {v}' for k, v in merged.items() if not str(k).startswith('_'))
        entries.append({
            'category': 'pricing',
            'title': f'Estimator defaults — {trade.title()}',
            'content': (
                f'Hub baseline estimator defaults for {trade} (starting points only): {parts}. '
                'Final job pricing depends on size/volume, property type (apartment vs condo), '
                'complexity (e.g. roof pitch), and client. Confirm with Tony or run the estimator.'
            ),
        })
    entries.append({
        'category': 'pricing',
        'title': 'Pricing nuance — when defaults are not enough',
        'content': (
            'Estimator defaults are starting points, not quotes. Volume, phasing, property type '
            '(apartment community vs condo/HOA), pitch/complexity, access, and client relationship '
            'all move the number. For "what are we charging per square right now?" — share the '
            'relevant trade default, ask what project/context they are pricing, and route final '
            'numbers through Tony or the trade estimator. Never treat hub defaults as a client quote.'
        ),
    })
    return entries


def build_seed_entries(users, get_db_fn):
    entries = []
    entries.extend(_parse_voice_sections(PROPOSAL_VOICE_PATH))
    entries.append({
        'category': 'production_process',
        'title': 'PPS standard field process',
        'content': (
            'Pre-Project Meeting before every mobilization. Minimum 48 hours notice before work '
            'begins at any building or area. Photo documentation at key milestones. Daily cleanup '
            'on every job. All scope changes documented and approved before work proceeds. '
            'Walkthrough close-out at project end.'
        ),
    })
    entries.extend(_team_directory_entries(users))
    entries.extend(_training_seed_entries())
    entries.extend(_pricing_seed_entries(get_db_fn))
    return entries


def run_seed(get_db_fn, users):
    conn = get_db_fn()
    if not conn:
        return {'ok': False, 'error': 'Database unavailable'}
    created = 0
    skipped = 0
    try:
        cur = conn.cursor()
        for row in build_seed_entries(users, get_db_fn):
            if _entry_exists(cur, row['title']):
                skipped += 1
                continue
            _insert_entry(
                cur, row['category'], row['title'], row['content'],
                'seed', author_key='seed',
            )
            created += 1
        conn.commit()
        cur.close()
    except Exception as e:
        conn.rollback()
        print(f'Ask PPS seed error: {e}')
        return {'ok': False, 'error': str(e)}
    finally:
        conn.close()
    return {'ok': True, 'created': created, 'skipped': skipped}


def _usage_today(get_db_fn, user_key):
    conn = get_db_fn()
    if not conn:
        return 0
    try:
        cur = conn.cursor()
        cur.execute(
            '''SELECT question_count FROM ask_pps_daily_usage
               WHERE user_key = %s AND usage_date = CURRENT_DATE''',
            (user_key,),
        )
        row = cur.fetchone()
        cur.close()
        return row[0] if row else 0
    except Exception as e:
        print(f'Ask PPS usage read error: {e}')
        return 0
    finally:
        conn.close()


def _increment_usage(get_db_fn, user_key):
    conn = get_db_fn()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute(
            '''INSERT INTO ask_pps_daily_usage (user_key, usage_date, question_count)
               VALUES (%s, CURRENT_DATE, 1)
               ON CONFLICT (user_key, usage_date)
               DO UPDATE SET question_count = ask_pps_daily_usage.question_count + 1''',
            (user_key,),
        )
        conn.commit()
        cur.close()
    except Exception as e:
        print(f'Ask PPS usage increment error: {e}')
    finally:
        conn.close()


def _infer_gap_topic(question, user_role):
    if PRODUCTION_KEYWORDS.search(question) or user_role == 'pm':
        return 'production'
    if SALES_KEYWORDS.search(question) or user_role in ('consultant', 'office_manager'):
        return 'sales'
    return 'general'


def _retrieve_entries(get_db_fn, question):
    conn = get_db_fn()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        ranked = []
        try:
            cur.execute(
                '''SELECT id, category, title, content,
                          ts_rank(search_tsv, plainto_tsquery('english', %s)) AS rank
                   FROM knowledge_entries
                   WHERE status = 'active'
                     AND search_tsv @@ plainto_tsquery('english', %s)
                   ORDER BY rank DESC
                   LIMIT 8''',
                (question, question),
            )
            ranked = cur.fetchall()
        except Exception as fts_err:
            print(f'Ask PPS FTS query fallback: {fts_err}')
        cur.execute(
            '''SELECT id, category, title, content
               FROM knowledge_entries
               WHERE status = 'active' AND category = 'team_directory'
               ORDER BY title'''
        )
        directory = cur.fetchall()
        cur.execute(
            '''SELECT id, category, title, content
               FROM knowledge_entries
               WHERE status = 'active' AND category = 'voice_language'
               ORDER BY id
               LIMIT 5'''
        )
        voice = cur.fetchall()
        cur.close()

        seen = set()
        merged = []
        for row in directory + voice + ranked:
            if row['id'] in seen:
                continue
            seen.add(row['id'])
            merged.append(row)
        return merged
    except Exception as e:
        print(f'Ask PPS retrieve error: {e}')
        return []
    finally:
        conn.close()


def _format_entries_for_prompt(entries):
    parts = []
    total = 0
    for e in entries:
        block = f'[{e["category"]}] {e["title"]}\n{e["content"]}'
        if total + len(block) > MAX_CONTEXT_CHARS:
            break
        parts.append(block)
        total += len(block) + 2
    return '\n\n'.join(parts)


def _strip_json_fences(raw):
    text = (raw or '').strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[-1]
        if text.endswith('```'):
            text = text.rsplit('```', 1)[0]
        text = text.strip()
        if text.lower().startswith('json'):
            text = text[4:].strip()
    return text


def _claude_ask_call(api_key, model, system_prompt, question, timeout=60.0):
    import anthropic
    cl = anthropic.Anthropic(api_key=api_key, timeout=timeout)
    last_err = None
    for attempt in range(2):
        try:
            msg = cl.messages.create(
                model=model,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                messages=[{'role': 'user', 'content': question}],
            )
            return msg.content[0].text.strip()
        except Exception as e:
            last_err = e
            err_name = type(e).__name__
            transient = err_name in (
                'APITimeoutError', 'APIConnectionError', 'RateLimitError', 'InternalServerError',
            ) or 'timeout' in str(e).lower() or 'overloaded' in str(e).lower()
            if attempt == 0 and transient:
                time.sleep(1.5)
                continue
            print(f'Ask PPS Claude error ({err_name}): {e}')
            raise last_err


def _parse_answer(raw):
    parsed = json.loads(_strip_json_fences(raw))
    if not isinstance(parsed, dict):
        raise ValueError('not a dict')
    answered = bool(parsed.get('answered'))
    answer = (parsed.get('answer') or '').strip()
    sources = parsed.get('sources') or []
    if not isinstance(sources, list):
        sources = []
    gap_summary = (parsed.get('gap_summary') or '').strip()
    return answered, answer, [str(s) for s in sources], gap_summary


def ask_question(get_db_fn, user_key, user_role, question, api_key, model):
    question = (question or '').strip()
    if len(question) < 3:
        return {'success': False, 'error': 'Question must be at least 3 characters.'}, 400
    if len(question) > MAX_QUESTION_LEN:
        return {'success': False, 'error': f'Question must be {MAX_QUESTION_LEN} characters or fewer.'}, 400
    if not api_key:
        return {'success': False, 'error': 'Ask PPS is not configured. Contact Thomas.'}, 503

    if not is_curator(user_key):
        used = _usage_today(get_db_fn, user_key)
        if used >= DAILY_LIMIT:
            return {
                'success': False,
                'error': f'Daily limit reached ({DAILY_LIMIT} questions). Try again tomorrow.',
            }, 429

    entries = _retrieve_entries(get_db_fn, question)
    prompt_entries = _format_entries_for_prompt(entries)
    system = SYSTEM_PROMPT.format(entries=prompt_entries or '(no entries retrieved)')
    role_hint = ''
    if user_role == 'pm':
        role_hint = ' The asker is production/PM — bias routing to Trey for undocumented production topics.'
    elif user_role in ('consultant', 'office_manager'):
        role_hint = ' The asker is sales/consulting — bias routing to Tony for undocumented sales topics.'
    full_question = question + role_hint

    try:
        raw = _claude_ask_call(api_key, model, system, full_question)
        answered, answer, sources, gap_summary = _parse_answer(raw)
    except json.JSONDecodeError:
        try:
            raw = _claude_ask_call(api_key, model, system, full_question)
            answered, answer, sources, gap_summary = _parse_answer(raw)
        except Exception as e:
            print(f'Ask PPS parse error: {e}')
            return {'success': False, 'error': 'Could not process the answer. Please try again.'}, 500
    except Exception as e:
        print(f'Ask PPS ask error: {e}')
        return {'success': False, 'error': 'Ask PPS is temporarily unavailable. Try again shortly.'}, 500

    gap_topic = None
    gap_status = None
    if not answered:
        gap_topic = _infer_gap_topic(question, user_role)
        gap_status = 'open'

    conn = get_db_fn()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute(
                '''INSERT INTO ask_pps_questions
                   (user_key, question, answer, sources, answered, gap_status, gap_topic, gap_summary)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''',
                (
                    user_key, question, answer,
                    json.dumps(sources), answered, gap_status, gap_topic, gap_summary,
                ),
            )
            conn.commit()
            cur.close()
        except Exception as e:
            print(f'Ask PPS log error: {e}')
        finally:
            conn.close()

    if not is_curator(user_key):
        _increment_usage(get_db_fn, user_key)

    return {
        'success': True,
        'answered': answered,
        'answer': answer,
        'sources': sources,
    }, 200


def get_recent_questions(get_db_fn, user_key, limit=10):
    conn = get_db_fn()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            '''SELECT question, answer, sources, answered, created_at
               FROM ask_pps_questions WHERE user_key = %s
               ORDER BY created_at DESC LIMIT %s''',
            (user_key, limit),
        )
        rows = cur.fetchall()
        cur.close()
        for r in rows:
            try:
                r['sources'] = json.loads(r['sources'] or '[]')
            except Exception:
                r['sources'] = []
        return rows
    except Exception as e:
        print(f'Ask PPS recent error: {e}')
        return []
    finally:
        conn.close()


def _display(users, user_key):
    return users.get(user_key, {}).get('display', user_key or 'Unknown')


def get_admin_data(get_db_fn, users):
    conn = get_db_fn()
    if not conn:
        return {}
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            '''SELECT * FROM ask_pps_questions
               WHERE gap_status = 'open'
               ORDER BY created_at DESC LIMIT 100'''
        )
        gaps = cur.fetchall()
        for g in gaps:
            g['display_name'] = _display(users, g['user_key'])

        cur.execute(
            '''SELECT k.*, u.display_name AS author_display
               FROM knowledge_entries k
               LEFT JOIN hub_users u ON u.user_key = k.author_key
               WHERE k.status = 'pending'
               ORDER BY k.created_at DESC'''
        )
        pending = cur.fetchall()
        for p in pending:
            if not p.get('author_display'):
                p['author_display'] = _display(users, p.get('author_key'))

        cur.execute(
            '''SELECT * FROM ask_pps_questions ORDER BY created_at DESC LIMIT 200'''
        )
        log = cur.fetchall()
        for row in log:
            row['display_name'] = _display(users, row['user_key'])

        cur.execute(
            '''SELECT k.*, u.display_name AS author_display
               FROM knowledge_entries k
               LEFT JOIN hub_users u ON u.user_key = k.author_key
               WHERE k.status != 'archived'
               ORDER BY k.category, k.title'''
        )
        knowledge = cur.fetchall()

        cur.execute(
            '''SELECT user_key, COUNT(*) AS cnt
               FROM ask_pps_questions
               WHERE created_at >= date_trunc('week', CURRENT_DATE)
               GROUP BY user_key ORDER BY cnt DESC'''
        )
        week_counts = [
            {'user_key': r['user_key'], 'cnt': r['cnt'],
             'display_name': _display(users, r['user_key'])}
            for r in cur.fetchall()
        ]

        cur.execute("SELECT COUNT(*) AS cnt FROM ask_pps_questions WHERE gap_status = 'open'")
        open_gaps = cur.fetchone()['cnt']
        cur.execute("SELECT COUNT(*) AS cnt FROM knowledge_entries WHERE status = 'pending'")
        pending_cnt = cur.fetchone()['cnt']

        cur.close()
        return {
            'gaps': gaps,
            'pending': pending,
            'log': log,
            'knowledge': knowledge,
            'week_counts': week_counts,
            'open_gaps': open_gaps,
            'pending_cnt': pending_cnt,
        }
    except Exception as e:
        print(f'Ask PPS admin data error: {e}')
        return {}
    finally:
        conn.close()


def get_digest_line(get_db_fn, start, end):
    conn = get_db_fn()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            '''SELECT COUNT(*) FROM ask_pps_questions
               WHERE created_at >= %s AND created_at < %s''',
            (start, end),
        )
        questions = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM ask_pps_questions WHERE gap_status = 'open'")
        open_gaps = cur.fetchone()[0]
        cur.close()
        if questions == 0 and open_gaps == 0:
            return None
        return f'Ask PPS: {questions} question{"s" if questions != 1 else ""} yesterday, {open_gaps} open gap{"s" if open_gaps != 1 else ""}.'
    except Exception as e:
        print(f'Ask PPS digest error: {e}')
        return None
    finally:
        conn.close()


def register_routes(app, get_db_fn, users, claude_api_key, claude_model, require_login):
    @app.route('/ask-pps')
    @require_login
    def ask_pps_page():
        user_key = session['user_key']
        q = (request.args.get('q') or '').strip()
        recent = get_recent_questions(get_db_fn, user_key)
        return render_template(
            'ask_pps.html',
            initial_question=q,
            recent=recent,
            categories=CATEGORIES,
        )

    @app.route('/api/ask-pps/ask', methods=['POST'])
    @require_login
    def api_ask_pps_ask():
        user_key = session['user_key']
        user_role = session.get('role', '')
        data = request.get_json(silent=True) or {}
        question = (data.get('question') or '').strip()
        payload, status = ask_question(
            get_db_fn, user_key, user_role, question, claude_api_key, claude_model,
        )
        return jsonify(payload), status

    @app.route('/api/ask-pps/suggest', methods=['POST'])
    @require_login
    def api_ask_pps_suggest():
        user_key = session['user_key']
        data = request.get_json(silent=True) or {}
        category = (data.get('category') or 'general').strip()
        title = (data.get('title') or '').strip()
        content = (data.get('content') or '').strip()
        if category not in CATEGORIES:
            return jsonify({'success': False, 'error': 'Invalid category.'}), 400
        if len(title) < 3 or len(content) < 10:
            return jsonify({'success': False, 'error': 'Title and content are required.'}), 400
        if len(content) > MAX_SUGGEST_LEN:
            return jsonify({'success': False, 'error': 'Content is too long.'}), 400
        conn = get_db_fn()
        if not conn:
            return jsonify({'success': False, 'error': 'Database unavailable.'}), 500
        try:
            cur = conn.cursor()
            _insert_entry(
                cur, category, title, content, 'team_contribution',
                author_key=user_key, status='pending',
            )
            conn.commit()
            cur.close()
        except Exception as e:
            print(f'Ask PPS suggest error: {e}')
            return jsonify({'success': False, 'error': 'Could not save suggestion.'}), 500
        finally:
            conn.close()
        return jsonify({'success': True})

    @app.route('/admin/ask-pps')
    @require_login
    @require_ask_pps_curator
    def admin_ask_pps():
        data = get_admin_data(get_db_fn, users)
        return render_template(
            'admin_ask_pps.html',
            categories=CATEGORIES,
            curators=CURATORS,
            **data,
        )

    @app.route('/admin/ask-pps/seed', methods=['POST'])
    @require_login
    @require_ask_pps_curator
    def admin_ask_pps_seed():
        result = run_seed(get_db_fn, users)
        if not result.get('ok'):
            return jsonify(result), 500
        return jsonify(result)

    def _publish_entry(cur, category, title, content, author_key, status='active'):
        _insert_entry(cur, category, title, content, 'admin', author_key=author_key, status=status)

    @app.route('/admin/ask-pps/gap/<int:gap_id>/resolve', methods=['POST'])
    @require_login
    @require_ask_pps_curator
    def admin_ask_pps_resolve_gap(gap_id):
        category = (request.form.get('category') or 'general').strip()
        title = (request.form.get('title') or '').strip()
        content = (request.form.get('content') or '').strip()
        if category not in CATEGORIES or len(title) < 3 or len(content) < 10:
            return redirect(url_for('admin_ask_pps'))
        conn = get_db_fn()
        if not conn:
            return redirect(url_for('admin_ask_pps'))
        try:
            cur = conn.cursor()
            _publish_entry(cur, category, title, content, session['user_key'])
            cur.execute('SELECT id FROM knowledge_entries ORDER BY id DESC LIMIT 1')
            entry_id = cur.fetchone()[0]
            cur.execute(
                '''UPDATE ask_pps_questions
                   SET gap_status = 'resolved', resolved_entry_id = %s
                   WHERE id = %s''',
                (entry_id, gap_id),
            )
            conn.commit()
            cur.close()
        except Exception as e:
            print(f'Ask PPS resolve gap error: {e}')
        finally:
            conn.close()
        return redirect(url_for('admin_ask_pps'))

    @app.route('/admin/ask-pps/gap/<int:gap_id>/dismiss', methods=['POST'])
    @require_login
    @require_ask_pps_curator
    def admin_ask_pps_dismiss_gap(gap_id):
        conn = get_db_fn()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE ask_pps_questions SET gap_status = 'dismissed' WHERE id = %s",
                    (gap_id,),
                )
                conn.commit()
                cur.close()
            except Exception as e:
                print(f'Ask PPS dismiss error: {e}')
            finally:
                conn.close()
        return redirect(url_for('admin_ask_pps'))

    @app.route('/admin/ask-pps/pending/<int:entry_id>/approve', methods=['POST'])
    @require_login
    @require_ask_pps_curator
    def admin_ask_pps_approve(entry_id):
        conn = get_db_fn()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute(
                    '''UPDATE knowledge_entries
                       SET status = 'active', updated_at = NOW(),
                           search_tsv = to_tsvector('english',
                               coalesce(title, '') || ' ' || coalesce(content, ''))
                       WHERE id = %s''',
                    (entry_id,),
                )
                conn.commit()
                cur.close()
            except Exception as e:
                print(f'Ask PPS approve error: {e}')
            finally:
                conn.close()
        return redirect(url_for('admin_ask_pps'))

    @app.route('/admin/ask-pps/pending/<int:entry_id>/reject', methods=['POST'])
    @require_login
    @require_ask_pps_curator
    def admin_ask_pps_reject(entry_id):
        conn = get_db_fn()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE knowledge_entries SET status = 'archived', updated_at = NOW() WHERE id = %s",
                    (entry_id,),
                )
                conn.commit()
                cur.close()
            except Exception as e:
                print(f'Ask PPS reject error: {e}')
            finally:
                conn.close()
        return redirect(url_for('admin_ask_pps'))

    @app.route('/admin/ask-pps/pending/<int:entry_id>/edit-approve', methods=['POST'])
    @require_login
    @require_ask_pps_curator
    def admin_ask_pps_edit_approve(entry_id):
        category = (request.form.get('category') or 'general').strip()
        title = (request.form.get('title') or '').strip()
        content = (request.form.get('content') or '').strip()
        if category not in CATEGORIES:
            return redirect(url_for('admin_ask_pps'))
        conn = get_db_fn()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute(
                    '''UPDATE knowledge_entries
                       SET category = %s, title = %s, content = %s, status = 'active',
                           updated_at = NOW(),
                           search_tsv = to_tsvector('english',
                               coalesce(%s, '') || ' ' || coalesce(%s, ''))
                       WHERE id = %s''',
                    (category, title, content, title, content, entry_id),
                )
                conn.commit()
                cur.close()
            except Exception as e:
                print(f'Ask PPS edit approve error: {e}')
            finally:
                conn.close()
        return redirect(url_for('admin_ask_pps'))

    @app.route('/admin/ask-pps/entry', methods=['POST'])
    @require_login
    @require_ask_pps_curator
    def admin_ask_pps_add_entry():
        category = (request.form.get('category') or 'general').strip()
        title = (request.form.get('title') or '').strip()
        content = (request.form.get('content') or '').strip()
        conn = get_db_fn()
        if conn and category in CATEGORIES and len(title) >= 3 and len(content) >= 10:
            try:
                cur = conn.cursor()
                _publish_entry(cur, category, title, content, session['user_key'])
                conn.commit()
                cur.close()
            except Exception as e:
                print(f'Ask PPS add entry error: {e}')
            finally:
                conn.close()
        return redirect(url_for('admin_ask_pps'))

    @app.route('/admin/ask-pps/entry/<int:entry_id>/edit', methods=['POST'])
    @require_login
    @require_ask_pps_curator
    def admin_ask_pps_edit_entry(entry_id):
        category = (request.form.get('category') or 'general').strip()
        title = (request.form.get('title') or '').strip()
        content = (request.form.get('content') or '').strip()
        conn = get_db_fn()
        if conn and category in CATEGORIES:
            try:
                cur = conn.cursor()
                cur.execute(
                    '''UPDATE knowledge_entries
                       SET category = %s, title = %s, content = %s, updated_at = NOW(),
                           search_tsv = to_tsvector('english',
                               coalesce(%s, '') || ' ' || coalesce(%s, ''))
                       WHERE id = %s''',
                    (category, title, content, title, content, entry_id),
                )
                conn.commit()
                cur.close()
            except Exception as e:
                print(f'Ask PPS edit entry error: {e}')
            finally:
                conn.close()
        return redirect(url_for('admin_ask_pps'))

    @app.route('/admin/ask-pps/entry/<int:entry_id>/archive', methods=['POST'])
    @require_login
    @require_ask_pps_curator
    def admin_ask_pps_archive_entry(entry_id):
        conn = get_db_fn()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE knowledge_entries SET status = 'archived', updated_at = NOW() WHERE id = %s",
                    (entry_id,),
                )
                conn.commit()
                cur.close()
            except Exception as e:
                print(f'Ask PPS archive error: {e}')
            finally:
                conn.close()
        return redirect(url_for('admin_ask_pps'))

    @app.route('/admin/ask-pps/flag/<int:q_id>', methods=['POST'])
    @require_login
    @require_ask_pps_curator
    def admin_ask_pps_flag(q_id):
        conn = get_db_fn()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute(
                    'UPDATE ask_pps_questions SET flagged = TRUE WHERE id = %s',
                    (q_id,),
                )
                conn.commit()
                cur.close()
            except Exception as e:
                print(f'Ask PPS flag error: {e}')
            finally:
                conn.close()
        return redirect(url_for('admin_ask_pps', flag=q_id))