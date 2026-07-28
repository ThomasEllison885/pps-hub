"""Ask PPS — closed-book internal knowledge assistant."""

import json
import os
import random
import re
import time
from datetime import date, datetime
from functools import wraps

from flask import jsonify, redirect, render_template, request, session, url_for
from psycopg2.extras import RealDictCursor

from estimators.pricing_defaults import SYSTEM_DEFAULTS, get_pricing_defaults
from production_board_reference import production_board_ask_pps_entries
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
    r'\b(schedul|trade partner|subcontractor|subs?\b|crew|mobiliz|field|production|'
    r'ppm|site visit|punch list|close-?out|pm\b|building access|48.hour)\b',
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
- PPS VOICE: Use the terminology below in every answer — naturally, in your own words.
  Just use the right PPS word (apartment community, Trade Partners, residents, etc.).
  Do not lecture about wording or call out what the asker said wrong; answer normally
  with the correct term and move on.

PPS TERMINOLOGY:
{voice_terminology}

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
        # Immutable first submission (team wording) — never overwrite on curator edit
        cur.execute(
            "ALTER TABLE knowledge_entries ADD COLUMN IF NOT EXISTS original_content TEXT"
        )
        cur.execute(
            '''UPDATE knowledge_entries
               SET original_content = content
               WHERE original_content IS NULL AND content IS NOT NULL'''
        )
        # Prefer raw prompt answer text when we still have the link
        cur.execute(
            '''UPDATE knowledge_entries k
               SET original_content = a.answer
               FROM knowledge_prompt_answers a
               WHERE a.entry_id = k.id
                 AND a.answer IS NOT NULL
                 AND a.answer <> ''
                 AND (
                   k.original_content IS NULL
                   OR k.original_content = k.content
                 )
                 AND k.source_type = 'prompt_response'
                 AND length(a.answer) < length(coalesce(k.content, ''))'''
        )
        cur.execute('''
            CREATE TABLE IF NOT EXISTS knowledge_prompts (
                id SERIAL PRIMARY KEY,
                question TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'general',
                target_role TEXT NOT NULL DEFAULT 'any',
                target_user_key TEXT,
                perspective TEXT NOT NULL DEFAULT 'field',
                source_type TEXT NOT NULL DEFAULT 'curator',
                source_gap_id INTEGER,
                status TEXT NOT NULL DEFAULT 'open',
                priority INTEGER NOT NULL DEFAULT 0,
                created_by TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS knowledge_prompt_answers (
                id SERIAL PRIMARY KEY,
                prompt_id INTEGER NOT NULL REFERENCES knowledge_prompts(id),
                user_key TEXT NOT NULL,
                answer TEXT NOT NULL,
                entry_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(prompt_id, user_key)
            )
        ''')
        cur.execute(
            'CREATE INDEX IF NOT EXISTS idx_knowledge_prompts_status ON knowledge_prompts(status)'
        )
        cur.execute(
            'CREATE INDEX IF NOT EXISTS idx_knowledge_prompts_gap ON knowledge_prompts(source_gap_id)'
        )
        cur.execute(
            "ALTER TABLE knowledge_prompts ADD COLUMN IF NOT EXISTS source_ref TEXT"
        )
        cur.execute(
            'CREATE INDEX IF NOT EXISTS idx_knowledge_prompts_ref ON knowledge_prompts(source_ref)'
        )
        cur.execute('''
            CREATE TABLE IF NOT EXISTS knowledge_prompt_skips (
                prompt_id INTEGER NOT NULL REFERENCES knowledge_prompts(id),
                user_key TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (prompt_id, user_key)
            )
        ''')
        # In-app thank-yous for Ask PPS (submit + approve) — shown until dismissed / next logins
        cur.execute('''
            CREATE TABLE IF NOT EXISTS hub_user_notifications (
                id SERIAL PRIMARY KEY,
                user_key TEXT NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                related_entry_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                read_at TIMESTAMP
            )
        ''')
        cur.execute(
            '''CREATE INDEX IF NOT EXISTS idx_hub_user_notifications_unread
               ON hub_user_notifications(user_key, created_at DESC)
               WHERE read_at IS NULL'''
        )
    except Exception:
        pass


def create_user_notification(get_db_fn, user_key, kind, title, body, related_entry_id=None,
                             dedupe=True):
    """Persist an in-app notification for the user (survives until they dismiss it).

    When dedupe=True and related_entry_id is set, skip insert if the same user/kind/entry
    already has a notification (blocks double-click / network retry spam).
    """
    if not user_key or not title:
        return None
    conn = get_db_fn()
    if not conn:
        return None
    try:
        cur = conn.cursor()
        if dedupe and related_entry_id is not None:
            cur.execute(
                '''SELECT id FROM hub_user_notifications
                   WHERE user_key = %s AND kind = %s AND related_entry_id = %s
                   LIMIT 1''',
                (user_key, kind, related_entry_id),
            )
            existing = cur.fetchone()
            if existing:
                cur.close()
                return existing[0]
        cur.execute(
            '''INSERT INTO hub_user_notifications
               (user_key, kind, title, body, related_entry_id)
               VALUES (%s, %s, %s, %s, %s)
               RETURNING id''',
            (user_key, kind, title[:200], (body or '')[:2000], related_entry_id),
        )
        row = cur.fetchone()
        conn.commit()
        cur.close()
        return row[0] if row else None
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f'create_user_notification error: {e}')
        return None
    finally:
        conn.close()


def get_unread_notifications(get_db_fn, user_key, limit=20):
    if not user_key:
        return []
    conn = get_db_fn()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            '''SELECT id, kind, title, body, related_entry_id, created_at
               FROM hub_user_notifications
               WHERE user_key = %s AND read_at IS NULL
               ORDER BY created_at DESC
               LIMIT %s''',
            (user_key, limit),
        )
        rows = cur.fetchall() or []
        cur.close()
        return rows
    except Exception as e:
        print(f'get_unread_notifications error: {e}')
        return []
    finally:
        conn.close()


def mark_notification_read(get_db_fn, user_key, notification_id):
    if not user_key or not notification_id:
        return False
    conn = get_db_fn()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute(
            '''UPDATE hub_user_notifications
               SET read_at = NOW()
               WHERE id = %s AND user_key = %s AND read_at IS NULL''',
            (notification_id, user_key),
        )
        conn.commit()
        ok = cur.rowcount > 0
        cur.close()
        return ok
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f'mark_notification_read error: {e}')
        return False
    finally:
        conn.close()


def notify_ask_pps_submitted(get_db_fn, user_key, display_name, question, entry_id=None):
    short_q = (question or 'your question').strip()
    if len(short_q) > 100:
        short_q = short_q[:97] + '…'
    first = (display_name or 'there').split()[0]
    create_user_notification(
        get_db_fn,
        user_key,
        kind='ask_pps_submitted',
        title=f'Thank you, {first}',
        body=(
            f'We received your Ask PPS answer about “{short_q}”. '
            'It is saved under your name for review. Thanks for helping document how PPS works.'
        ),
        related_entry_id=entry_id,
    )


def notify_ask_pps_approved(get_db_fn, user_key, display_name, title_or_question, entry_id=None):
    if not user_key:
        return
    label = (title_or_question or 'your answer').strip()
    # Titles often look like "Name: question…" — strip leading "Name: "
    if ': ' in label:
        label = label.split(': ', 1)[-1]
    if len(label) > 100:
        label = label[:97] + '…'
    first = (display_name or 'there').split()[0]
    create_user_notification(
        get_db_fn,
        user_key,
        kind='ask_pps_approved',
        title=f'Thank you, {first} — your answer is live',
        body=(
            f'Your Ask PPS contribution about “{label}” was approved and added to the knowledge base. '
            'Thank you for taking the time to share how we work.'
        ),
        related_entry_id=entry_id,
    )


def _tsv_sql():
    return "to_tsvector('english', coalesce(title,'') || ' ' || coalesce(content,''))"


def _insert_entry(cur, category, title, content, source_type, author_key=None, status='active',
                  original_content=None):
    """Insert knowledge row. original_content freezes the first submission (defaults to content)."""
    orig = original_content if original_content is not None else content
    cur.execute(
        '''INSERT INTO knowledge_entries
           (category, title, content, source_type, author_key, status, original_content, search_tsv)
           VALUES (%s, %s, %s, %s, %s, %s, %s,
                   to_tsvector('english', coalesce(%s, '') || ' ' || coalesce(%s, '')))''',
        (category, title, content, source_type, author_key, status, orig, title, content),
    )


def _entry_exists(cur, title):
    cur.execute(
        "SELECT id FROM knowledge_entries WHERE title = %s AND status != 'archived' LIMIT 1",
        (title,),
    )
    return cur.fetchone() is not None


_VOICE_TERMINOLOGY_CACHE = None

_VOICE_TERMINOLOGY_FALLBACK = (
    'ALWAYS / NEVER:\n'
    '"residents" not "tenants" | "apartment community" not "complex"\n'
    '"ownership" or "ownership/management" not "the owner"\n'
    '"Trade Partners" not "subcontractors" or "subs"\n'
    '"investment" not "cost/price" for totals\n'
    '"homeowners" not "tenants" in condo/HOA context\n'
    '"T&M" not "hourly" | "concealed conditions" not "hidden damage"\n'
    '"Trade Partner Scope" not "sub scope" | "punch list" not "final items"\n'
    'Property context: apartments → residents; condos/HOAs → homeowners; '
    'hospitality → guests; commercial → tenants OK.'
)


def _load_voice_terminology():
    """Always-on PPS word choices from proposal voice guide (SECTION 1 + property context)."""
    global _VOICE_TERMINOLOGY_CACHE
    if _VOICE_TERMINOLOGY_CACHE is not None:
        return _VOICE_TERMINOLOGY_CACHE

    if not os.path.exists(PROPOSAL_VOICE_PATH):
        _VOICE_TERMINOLOGY_CACHE = _VOICE_TERMINOLOGY_FALLBACK
        return _VOICE_TERMINOLOGY_CACHE

    with open(PROPOSAL_VOICE_PATH, encoding='utf-8') as f:
        text = f.read()

    section1 = ''
    m1 = re.search(
        r'SECTION\s+1\s*[—–-]\s*UNIVERSAL LANGUAGE RULES\s*\n━+\s*\n'
        r'(.*?)(?=\n━+\s*\nSECTION\s+2)',
        text,
        re.DOTALL | re.I,
    )
    if m1:
        section1 = m1.group(1).strip()

    property_lines = []
    m3 = re.search(
        r'SECTION\s+3\s*[—–-]\s*PROPERTY TYPE GUIDANCE\s*\n━+\s*\n'
        r'(.*?)(?=\n━+\s*\nSECTION\s+4)',
        text,
        re.DOTALL | re.I,
    )
    if m3:
        for line in m3.group(1).split('\n'):
            line = line.strip()
            if line.startswith('LANGUAGE:'):
                property_lines.append(line.replace('LANGUAGE:', 'Property language:').strip())
            elif '"guests"' in line.lower() or 'acceptable in commercial' in line.lower():
                property_lines.append(line)

    parts = [p for p in (section1, '\n'.join(property_lines)) if p]
    _VOICE_TERMINOLOGY_CACHE = '\n\n'.join(parts) if parts else _VOICE_TERMINOLOGY_FALLBACK
    return _VOICE_TERMINOLOGY_CACHE


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
    entries.append({
        'category': 'production_process',
        'title': 'Scheduling work with Trade Partners',
        'content': (
            'We say Trade Partners — not subs or subcontractors. The PM typically schedules '
            'the project with the Trade Partner. Production oversight and field scheduling '
            'questions go to Trey Hollmeyer (Production Manager). Consultants do not promise '
            'crew dates without PM or production sign-off.'
        ),
    })
    entries.extend(_team_directory_entries(users))
    entries.extend(_training_seed_entries())
    entries.extend(production_board_ask_pps_entries())
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


PROMPT_TARGET_ROLES = ('any', 'pm', 'consultant', 'office_manager', 'curator')
PROMPT_PERSPECTIVES = ('field', 'policy')
THIN_CATEGORY_THRESHOLD = 3
THIN_CATEGORY_SKIP = frozenset({'team_directory', 'voice_language'})

PSC_MODULE_CATEGORY = {
    'ops_partner_projects': 'training_core_values',
    'ops_monday': 'company_operations',
    'ops_lifecycle': 'production_process',
    'ops_project_evaluation': 'sales_process',
    'ops_estimating': 'sales_process',
    'ops_proposal_generator': 'sales_process',
    'ops_decision_ownership': 'company_operations',
    'ops_trade_partners': 'production_process',
    'ops_client_comms': 'sales_process',
    'ops_callbacks': 'production_process',
    'ops_common_mistakes': 'training_core_values',
    'ops_market_expansion': 'company_operations',
}

PSC_MODULE_FIELD_ROLE = {
    'ops_partner_projects': 'consultant',
    'ops_monday': 'consultant',
    'ops_lifecycle': 'pm',
    'ops_project_evaluation': 'consultant',
    'ops_estimating': 'consultant',
    'ops_proposal_generator': 'consultant',
    'ops_decision_ownership': 'consultant',
    'ops_trade_partners': 'pm',
    'ops_client_comms': 'consultant',
    'ops_callbacks': 'pm',
    'ops_common_mistakes': 'consultant',
    'ops_market_expansion': 'consultant',
}

# Short field prompts — keep under ~120 chars. Roles: consultant = PSC/sales, pm = production.
# PSC training may include production overlap; PM training stays production-first (little/no sales).
KNOWLEDGE_AUDIT_GAPS = [
    ('audit:ppm', 'production_process', 'pm',
     'PPM: who attends, what gets confirmed, and when is it required?'),
    ('audit:change_orders', 'production_process', 'pm',
     'Change order: who documents, who approves, who tells the client?'),
    ('audit:closeout', 'production_process', 'pm',
     'Punch / close-out: who walks, what must be done before the job is done?'),
    ('audit:proposal_review', 'sales_process', 'consultant',
     'Before a proposal goes out — who reviews it, and what is never sent cold?'),
    ('audit:warranty', 'trades', 'consultant',
     'How do you explain warranty to a client (PPS labor vs manufacturer)?'),
    ('audit:fixed_vs_tm', 'production_process', 'pm',
     'When is fixed-price required vs T&M / hourly? What goes wrong with open-ended hourly?'),
    ('audit:takeoff_save', 'production_process', 'any',
     'What takeoff details must be saved so production can run the job if we win later?'),
    ('audit:include_exclude', 'sales_process', 'consultant',
     'What belongs in Included vs Excluded on a proposal (production uses this to sell the job)?'),
]

# PSC curriculum themes (Rachel + ops). Short prompts for team capture.
PSC_FEEDBACK_GAPS = [
    ('pscfb:partner_mentor', 'training_core_values', 'consultant',
     'Who picks a mentor for a new PSC, and what makes a good partner project?'),
    ('pscfb:partner_progressive', 'training_core_values', 'consultant',
     'How does a new PSC move from observe → participate → lead? Real example.'),
    ('pscfb:partner_debrief', 'training_core_values', 'consultant',
     'After a partner project, what does the debrief cover — and who runs it?'),
    ('pscfb:comm_standards', 'sales_process', 'consultant',
     'Client touchpoints by phase — list them from site visit through close-out.'),
    ('pscfb:difficult_convos', 'sales_process', 'consultant',
     'Schedule delay with a property manager — what do you say first?'),
    ('pscfb:eval_checklist', 'sales_process', 'consultant',
     'Site visit before scoping: what do you always capture?'),
    ('pscfb:ownership_guide', 'company_operations', 'consultant',
     'Pricing, callbacks, change orders, concealed conditions — who owns each?'),
    ('pscfb:pricing_inputs', 'sales_process', 'consultant',
     'What must a PSC gather so a PM can price the job accurately?'),
    ('pscfb:tp_reference', 'production_process', 'pm',
     'Go-to Trade Partners by trade — who, and how do you choose?'),
    ('pscfb:callback_intake', 'production_process', 'pm',
     'Callback intake: who logs it, who calls the client, how does it close?'),
    ('pscfb:graduation_ready', 'training_core_values', 'consultant',
     'Signs a new PSC is ready for solo client work (not just weeks completed).'),
]

# PM training gaps (production only — no sales process).
PM_TRAINING_GAPS = [
    ('pmfb:contacts', 'production_process', 'pm',
     'Where do you find preferred Trade Partner and vendor contacts?'),
    ('pmfb:route', 'production_process', 'pm',
     'How do you build a weekly route (site vs desk time)?'),
    ('pmfb:tp_scripts', 'production_process', 'pm',
     'Trade Partner call/text examples: award, mid-job, punch.'),
    ('pmfb:expectations', 'production_process', 'pm',
     'PM non-negotiables: response time, photos, board hygiene, escalation.'),
    ('pmfb:time_budget', 'production_process', 'pm',
     'Sample week: how do you split site time vs estimating/email/Updates?'),
]


def _gap_topic_to_category(gap_topic):
    return {
        'production': 'production_process',
        'sales': 'sales_process',
    }.get(gap_topic, 'general')


def _gap_topic_to_field_role(gap_topic):
    return {
        'production': 'pm',
        'sales': 'consultant',
    }.get(gap_topic, 'any')


def _user_matches_prompt(user_key, user_role, prompt):
    if prompt.get('target_user_key'):
        return user_key == prompt['target_user_key']
    target = prompt.get('target_role') or 'any'
    if target == 'any':
        return True
    if target == 'curator':
        return is_curator(user_key)
    # Admin / office can answer any open field prompt (team capture sessions)
    if user_role in ('admin', 'office_manager') and target in (
        'consultant', 'pm', 'office_manager', 'any',
    ):
        return True
    return user_role == target


def _prompt_role_weight(user_key, user_role, prompt):
    """Higher weight = more likely to appear first for this user.

    PSC → consultant questions near the top; PM → pm questions; others equal random.
    """
    if prompt.get('target_user_key') == user_key:
        return 100.0
    target = prompt.get('target_role') or 'any'
    if user_role == 'consultant':
        if target == 'consultant':
            return 10.0
        if target == 'any':
            return 3.5
        if target == 'pm':
            return 0.6
        return 0.4
    if user_role == 'pm':
        if target == 'pm':
            return 10.0
        if target == 'any':
            return 3.5
        if target == 'consultant':
            return 0.6
        return 0.4
    # admin, office_manager, etc. — true equal random across the pool they can see
    return 1.0


def _prompt_diversity_bucket(prompt):
    """Fine-grained topic id (module / keyword / category)."""
    ref = (prompt.get('source_ref') or '').strip()
    if ref.startswith('psc:'):
        parts = ref.split(':')
        if len(parts) >= 2 and parts[1]:
            return f'psc:{parts[1]}'  # training module id (ops_monday, ops_lifecycle, …)
    if ref.startswith('pscfb:'):
        parts = ref.split(':')
        return f'pscfb:{parts[1]}' if len(parts) >= 2 else 'pscfb'
    if ref.startswith('pmfb:'):
        parts = ref.split(':')
        return f'pmfb:{parts[1]}' if len(parts) >= 2 else 'pmfb'
    if ref.startswith('audit:'):
        parts = ref.split(':')
        return f'audit:{parts[1]}' if len(parts) >= 2 else 'audit'
    if ref.startswith('user:'):
        return 'user_recommend'

    q = (prompt.get('question') or '').lower()
    if 'monday' in q or 'production board' in q:
        return 'kw:monday'
    if 'trade partner' in q or 'subcontractor' in q or re.search(r'\bsubs?\b', q):
        return 'kw:trade_partner'
    if 'ppm' in q or 'pre-project' in q or 'mobiliz' in q:
        return 'kw:ppm'
    if 'callback' in q or 'warranty' in q:
        return 'kw:callback'
    if 'proposal' in q:
        return 'kw:proposal'
    if 'site visit' in q or 'takeoff' in q:
        return 'kw:site_visit'
    if 'change order' in q or 't&m' in q or 'hourly' in q:
        return 'kw:change_order'
    cat = (prompt.get('category') or 'general').strip() or 'general'
    return f'cat:{cat}'


def _prompt_topic_family(prompt):
    """Coarse family for interleave — Monday.com / Production Board is one family.

    Fine buckets alone still let ops_monday + kw:monday + 'production board'
    questions clump as different buckets. Family groups those together.
    """
    bucket = _prompt_diversity_bucket(prompt)
    ref = (prompt.get('source_ref') or '').strip().lower()
    q = (prompt.get('question') or '').lower()
    title = (prompt.get('title') or '').lower()
    blob = f'{q} {title} {ref} {bucket}'

    if (
        'monday' in blob
        or 'production board' in blob
        or bucket == 'kw:monday'
        or bucket == 'psc:ops_monday'
        or ref.startswith('psc:ops_monday')
    ):
        return 'family:monday'

    # Module-level family for other PSC training chunks
    if bucket.startswith('psc:'):
        return bucket
    if bucket.startswith('pscfb:') or bucket.startswith('pmfb:'):
        return bucket
    if bucket.startswith('audit:'):
        return bucket
    if bucket.startswith('kw:'):
        return bucket
    return bucket


def _weighted_shuffle_prompts(prompts, user_key, user_role):
    """Role-weighted deck: break topic families into piles, shuffle each, interleave.

    Rules:
    - Re-randomize every call (page open / next question).
    - Monday.com + Production Board share family:monday — at most ONE in the first 3.
    - Opening slot prefers a non-monday family when any exists.
    - No two consecutive from the same family when alternatives remain.
    - Role weights still bias which family wins a free slot.
    """
    if not prompts:
        return []

    # Entropy per page open (not deterministic by user)
    random.shuffle(list(range(3)))  # burn a little RNG if anything else seeded

    items = []
    for p in prompts:
        w = _prompt_role_weight(user_key, user_role, p)
        if w <= 0:
            continue
        items.append({
            'p': p,
            'w': float(w),
            'family': _prompt_topic_family(p),
            'bucket': _prompt_diversity_bucket(p),
        })
    if not items:
        return []

    # Split into family piles; shuffle within each pile
    piles = {}
    for item in items:
        piles.setdefault(item['family'], []).append(item)
    for fam in piles:
        random.shuffle(piles[fam])

    result = []
    recent_families = []
    monday_in_opening = 0
    OPENING = 3

    def _eligible_families(pos, relax=False):
        out = []
        for fam, pile in piles.items():
            if not pile:
                continue
            if not relax:
                # Hard: only one monday-family item in first OPENING slots
                if pos < OPENING and fam == 'family:monday' and monday_in_opening >= 1:
                    continue
                # Hard: never open the deck with monday if anything else exists
                if pos == 0 and fam == 'family:monday':
                    non_monday = any(
                        f != 'family:monday' and piles[f]
                        for f in piles
                    )
                    if non_monday:
                        continue
                # Hard: no back-to-back same family when other piles have cards
                if recent_families and fam == recent_families[-1]:
                    others = any(f != fam and piles[f] for f in piles)
                    if others:
                        continue
            out.append(fam)
        return out

    while any(piles[f] for f in piles):
        pos = len(result)
        families = _eligible_families(pos, relax=False)
        if not families:
            families = _eligible_families(pos, relax=True)
        if not families:
            break

        best_fam = None
        best_score = -1.0
        for fam in families:
            head = piles[fam][0]
            score = head['w'] * (0.25 + random.random())
            # Soft: family used in last 2 picks
            if fam in recent_families[-2:]:
                score *= 0.2
            elif fam in recent_families[-4:]:
                score *= 0.5
            # Soft: slightly prefer less-represented families still holding cards
            remaining_in_fam = len(piles[fam])
            score *= 1.0 + 0.05 * min(remaining_in_fam, 6)
            if score > best_score:
                best_score = score
                best_fam = fam

        chosen = piles[best_fam].pop(0)
        result.append(chosen['p'])
        recent_families.append(best_fam)
        if len(recent_families) > 10:
            recent_families = recent_families[-10:]
        if pos < OPENING and best_fam == 'family:monday':
            monday_in_opening += 1

    return result


def _perspective_label(perspective):
    return 'How we actually do it (field)' if perspective == 'field' else 'Leadership intent (policy)'


def _prompt_entry_title(question, display_name, max_len=120):
    """Title = question first; append submitter name only if it fits."""
    q = (question or '').strip()
    name = (display_name or '').strip()
    if not q:
        return (name or 'Answer')[:max_len]
    if name:
        sep = ' — '
        if len(q) + len(sep) + len(name) <= max_len:
            return f'{q}{sep}{name}'
    if len(q) <= max_len:
        return q
    return q[: max_len - 1] + '…'


def _is_stamped_prompt_content(text):
    t = (text or '').strip()
    return t.startswith('Submitted by:') or t.startswith('Submitted at:')


def _extract_answer_body(content, original_content=None, prompt_raw=None):
    """Return only the team answer text (strip legacy stamp header / Prompt trailer)."""
    for candidate in (prompt_raw, original_content):
        if not candidate:
            continue
        c = str(candidate).strip()
        if not c or _is_stamped_prompt_content(c):
            continue
        if c.startswith('Prompt:'):
            continue
        # raw answer should not end with the prompt block
        if '\n\nPrompt:' in c:
            c = c.split('\n\nPrompt:')[0].strip()
        return c

    text = (content or '').strip()
    if not text:
        return ''

    if _is_stamped_prompt_content(text):
        if '\n\nPrompt:' in text:
            text = text.split('\n\nPrompt:')[0].strip()
        lines = text.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith('Submitted by:') or line.startswith('Submitted at:'):
                i += 1
                continue
            if line in (
                'How we actually do it (field)',
                'Leadership intent (policy)',
            ):
                i += 1
                while i < len(lines) and not lines[i].strip():
                    i += 1
                break
            if not line:
                i += 1
                continue
            break
        return '\n'.join(lines[i:]).strip()

    if '\n\nPrompt:' in text:
        return text.split('\n\nPrompt:')[0].strip()
    return text


def _question_from_legacy_title(title, author_display=None):
    """If title is old 'Name: question' form, return the question part."""
    t = (title or '').strip()
    if not t:
        return ''
    name = (author_display or '').strip()
    if name and t.startswith(name + ': '):
        return t[len(name) + 2 :].strip()
    # Common display-name prefix before first ': '
    if ': ' in t and not t.lower().startswith('http'):
        left, right = t.split(': ', 1)
        # Only treat as legacy name prefix when left side looks like a short person name
        if left and len(left) <= 40 and '?' not in left and not left.startswith('Q'):
            # Prefer when author matches; otherwise if right looks like a question
            if (name and left == name) or right.strip().endswith('?') or len(right) > len(left):
                if name and left != name and not right.strip().endswith('?'):
                    return ''
                return right.strip()
    return ''


def _display_question_for_entry(row):
    """Best-effort question text for review UI."""
    q = (row.get('prompt_question') or '').strip()
    if q:
        return q
    q = _question_from_legacy_title(row.get('title'), row.get('author_display'))
    if q:
        return q
    # New titles are already question-first (optional " — Name")
    t = (row.get('title') or '').strip()
    if ' — ' in t:
        # last segment might be name
        left, right = t.rsplit(' — ', 1)
        if right and len(right) <= 40 and '?' not in right:
            return left.strip()
    return t


def _normalize_pending_prompt_entry(cur, row, users):
    """
    Rewrite pending prompt_response rows that still use stamp body / Name: title
    into question-first title + answer-only content. Leave already-clean rows alone.
    """
    if (row.get('source_type') or '') != 'prompt_response':
        return row
    content = (row.get('content') or '').strip()
    title = (row.get('title') or '').strip()
    author = row.get('author_display') or _display(users, row.get('author_key'))
    body = _extract_answer_body(
        content,
        original_content=row.get('original_content'),
        prompt_raw=row.get('prompt_raw_answer'),
    )
    question = _display_question_for_entry(row)
    new_title = _prompt_entry_title(question, author) if question else title
    needs_content = body and body != content
    needs_title = new_title and new_title != title
    needs_original = body and not (row.get('original_content') or '').strip()
    if not (needs_content or needs_title or needs_original):
        return row
    try:
        cur.execute(
            '''UPDATE knowledge_entries
               SET content = %s,
                   title = %s,
                   original_content = COALESCE(NULLIF(original_content, ''), %s),
                   updated_at = NOW(),
                   search_tsv = to_tsvector('english',
                       coalesce(%s, '') || ' ' || coalesce(%s, ''))
               WHERE id = %s AND status = 'pending' ''',
            (
                body if needs_content else content,
                new_title if needs_title else title,
                body,
                new_title if needs_title else title,
                body if needs_content else content,
                row['id'],
            ),
        )
        if needs_content:
            row['content'] = body
        if needs_title:
            row['title'] = new_title
        if needs_original:
            row['original_content'] = body
    except Exception as e:
        print(f'normalize pending prompt entry error: {e}')
    return row


def _format_prompt_entry_content(question, answer, perspective, display_name, hub_role,
                                 user_key=None, email=None):
    """Legacy helper — new submissions store answer text only. Kept for any old callers."""
    return (answer or '').strip()


def _prompt_exists_for_gap(cur, gap_id, perspective):
    cur.execute(
        '''SELECT id FROM knowledge_prompts
           WHERE source_gap_id = %s AND perspective = %s AND status != 'dismissed'
           LIMIT 1''',
        (gap_id, perspective),
    )
    return cur.fetchone() is not None


def _prompt_exists_by_ref(cur, source_ref):
    if not source_ref:
        return False
    cur.execute(
        '''SELECT id FROM knowledge_prompts
           WHERE source_ref = %s AND status != 'dismissed' LIMIT 1''',
        (source_ref,),
    )
    return cur.fetchone() is not None


def _topic_documented(cur, topic):
    """True if active/pending knowledge already covers this topic (FTS or keyword)."""
    topic = (topic or '').strip()
    if len(topic) < 4:
        return False
    try:
        cur.execute(
            '''SELECT id FROM knowledge_entries
               WHERE status IN ('active', 'pending')
                 AND search_tsv @@ plainto_tsquery('english', %s)
               LIMIT 1''',
            (topic,),
        )
        if cur.fetchone():
            return True
    except Exception:
        pass
    words = [w for w in re.findall(r'[a-zA-Z]{4,}', topic.lower()) if w not in ('document', 'with', 'what', 'when', 'who', 'how')]
    if len(words) < 2:
        words = re.findall(r'[a-zA-Z]{3,}', topic.lower())[:4]
    if not words:
        return False
    pattern = '%' + '%'.join(words[:3]) + '%'
    cur.execute(
        '''SELECT id FROM knowledge_entries
           WHERE status IN ('active', 'pending')
             AND lower(title || ' ' || content) LIKE %s
           LIMIT 1''',
        (pattern,),
    )
    return cur.fetchone() is not None


def _prompt_question_from_topic(topic):
    """Turn a [TO DOCUMENT] topic into a short dashboard prompt."""
    t = (topic or '').strip()
    t = re.sub(r'\s+', ' ', t)
    if not t:
        return t
    if t.endswith('?'):
        return t
    # Already a full prompt without ?
    if t[:1].isupper() and any(t.lower().startswith(w) for w in (
        'how ', 'what ', 'when ', 'who ', 'where ', 'why ', 'list ', 'walk ',
        'signs ', 'give ', 'name ',
    )):
        return t if t.endswith('?') else t + '?'
    return f'{t}?'


def discover_psc_training_gaps(get_db_fn):
    """PSC Company Operations [TO DOCUMENT] bullets not yet in the knowledge base."""
    _, _, _, _, company_operations = get_training_curriculum()
    conn = get_db_fn()
    if not conn:
        return []
    gaps = []
    try:
        cur = conn.cursor()
        for module in company_operations.get('modules', []):
            module_id = module.get('id', '')
            module_title = module.get('title', 'Company Operations')
            category = PSC_MODULE_CATEGORY.get(module_id, 'company_operations')
            field_role = PSC_MODULE_FIELD_ROLE.get(module_id, 'any')
            for i, sop in enumerate(module.get('sop_placeholders', [])):
                if '[TO DOCUMENT]' not in sop:
                    continue
                topic = re.sub(r'^\[TO DOCUMENT\]\s*', '', sop).strip()
                # Drop parenthetical clutter from training SOPs
                topic = re.sub(r'\s*\([^)]*templates? in progress\)\s*', '', topic, flags=re.I)
                topic = topic.strip(' .')
                if _topic_documented(cur, topic):
                    continue
                ref = f'psc:{module_id}:{i}'
                gaps.append({
                    'source_ref': ref,
                    'question': _prompt_question_from_topic(topic),
                    'category': category,
                    'field_role': field_role,
                    'module_title': module_title,
                    'topic': topic,
                })
        cur.close()
    except Exception as e:
        print(f'Ask PPS discover PSC gaps error: {e}')
    finally:
        conn.close()
    return gaps


def group_psc_gaps_for_display(gaps):
    """Group PSC gap dicts by module_title for curator browse UI."""
    modules = []
    by_module = {}
    order = []
    for gap in gaps:
        title = gap.get('module_title') or 'Company Operations'
        if title not in by_module:
            by_module[title] = {
                'module_title': title,
                'field_role': gap.get('field_role'),
                'topics': [],
            }
            order.append(title)
        by_module[title]['topics'].append({
            'topic': gap.get('topic', ''),
            'field_role': gap.get('field_role'),
            'source_ref': gap.get('source_ref'),
        })
    for title in order:
        modules.append(by_module[title])
    return modules


def count_open_assigned_prompts(get_db_fn, user_key):
    conn = get_db_fn()
    if not conn:
        return 0
    try:
        cur = conn.cursor()
        cur.execute(
            '''SELECT COUNT(*) FROM knowledge_prompts
               WHERE status = 'open' AND target_user_key = %s''',
            (user_key,),
        )
        n = cur.fetchone()[0]
        cur.close()
        return n or 0
    except Exception as e:
        print(f'Ask PPS assigned prompt count error: {e}')
        return 0
    finally:
        conn.close()


def discover_psc_feedback_gaps(get_db_fn):
    """Gap questions from PSC training feedback themes (not already in knowledge base)."""
    conn = get_db_fn()
    if not conn:
        return []
    gaps = []
    try:
        cur = conn.cursor()
        for ref, category, field_role, question in PSC_FEEDBACK_GAPS:
            if _topic_documented(cur, question):
                continue
            gaps.append({
                'source_ref': ref,
                'question': question.strip(),
                'category': category,
                'field_role': field_role,
                'topic': question,
            })
        cur.close()
    except Exception as e:
        print(f'Ask PPS discover PSC feedback gaps error: {e}')
    finally:
        conn.close()
    return gaps


def discover_knowledge_audit_gaps(get_db_fn):
    """Cross-cutting operations questions when the KB has no matching entry."""
    conn = get_db_fn()
    if not conn:
        return []
    gaps = []
    try:
        cur = conn.cursor()
        for ref, category, field_role, question in KNOWLEDGE_AUDIT_GAPS:
            if _topic_documented(cur, question):
                continue
            gaps.append({
                'source_ref': ref,
                'question': question.strip(),
                'category': category,
                'field_role': field_role,
            })
        cur.close()
    except Exception as e:
        print(f'Ask PPS discover audit gaps error: {e}')
    finally:
        conn.close()
    return gaps


def discover_pm_training_gaps(get_db_fn):
    """PM training capture prompts (production-only)."""
    conn = get_db_fn()
    if not conn:
        return []
    gaps = []
    try:
        cur = conn.cursor()
        for ref, category, field_role, question in PM_TRAINING_GAPS:
            if _topic_documented(cur, question):
                continue
            gaps.append({
                'source_ref': ref,
                'question': question.strip(),
                'category': category,
                'field_role': field_role,
                'topic': question,
            })
        cur.close()
    except Exception as e:
        print(f'Ask PPS discover PM training gaps error: {e}')
    finally:
        conn.close()
    return gaps


def _create_prompt(cur, question, category, target_role, perspective, source_type,
                   created_by, source_gap_id=None, target_user_key=None, priority=0,
                   source_ref=None):
    cur.execute(
        '''INSERT INTO knowledge_prompts
           (question, category, target_role, target_user_key, perspective,
            source_type, source_gap_id, source_ref, created_by, priority)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
        (
            question.strip(), category, target_role, target_user_key, perspective,
            source_type, source_gap_id, source_ref, created_by, priority,
        ),
    )


def _gap_source_type(source_ref):
    if not source_ref:
        return 'curator'
    if source_ref.startswith('psc:'):
        return 'psc_gap'
    if source_ref.startswith('pscfb:'):
        return 'psc_feedback'
    if source_ref.startswith('pmfb:'):
        return 'pm_training'
    if source_ref.startswith('audit:'):
        return 'audit_gap'
    return 'curator'


def _priority_for_ref(source_ref):
    if not source_ref:
        return 5
    if source_ref.startswith('psc:'):
        return 12
    if source_ref.startswith('pscfb:') or source_ref.startswith('pmfb:'):
        return 11
    if source_ref.startswith('audit:'):
        return 10
    return 9


def sync_identified_gap_prompts(get_db_fn, created_by, assign_to=None, bank_mode=True):
    """Create/refresh prompts for identified gaps. bank_mode=True → field prompts by role.

    Re-wording: if an open prompt already exists for source_ref, updates question text
    so shorter prompts ship without wiping the bank.
    """
    conn = get_db_fn()
    if not conn:
        return {'ok': False, 'error': 'Database unavailable'}
    psc_gaps = discover_psc_training_gaps(get_db_fn)
    feedback_gaps = discover_psc_feedback_gaps(get_db_fn)
    audit_gaps = discover_knowledge_audit_gaps(get_db_fn)
    pm_gaps = discover_pm_training_gaps(get_db_fn)
    all_gaps = psc_gaps + feedback_gaps + audit_gaps + pm_gaps
    created = 0
    updated = 0
    skipped = 0
    perspective = 'field' if bank_mode and not assign_to else 'policy'
    try:
        cur = conn.cursor()
        for gap in all_gaps:
            ref = gap['source_ref']
            q = (gap.get('question') or '').strip()
            if not q:
                skipped += 1
                continue
            if _prompt_exists_by_ref(cur, ref):
                cur.execute(
                    '''UPDATE knowledge_prompts
                       SET question = %s,
                           category = %s,
                           target_role = %s,
                           updated_at = NOW()
                       WHERE source_ref = %s AND status = 'open'
                         AND question IS DISTINCT FROM %s''',
                    (q, gap['category'], gap.get('field_role', 'any'), ref, q),
                )
                if cur.rowcount:
                    updated += 1
                else:
                    skipped += 1
                continue
            _create_prompt(
                cur,
                q,
                gap['category'],
                gap.get('field_role', 'any'),
                perspective,
                _gap_source_type(ref),
                created_by,
                target_user_key=assign_to,
                priority=_priority_for_ref(ref),
                source_ref=ref,
            )
            created += 1
        conn.commit()
        cur.close()
    except Exception as e:
        conn.rollback()
        print(f'Ask PPS sync identified gaps error: {e}')
        return {'ok': False, 'error': str(e)}
    finally:
        conn.close()
    return {
        'ok': True,
        'created': created,
        'updated': updated,
        'skipped': skipped,
        'psc_candidates': len(psc_gaps),
        'feedback_candidates': len(feedback_gaps),
        'audit_candidates': len(audit_gaps),
        'pm_candidates': len(pm_gaps),
    }


def assign_prompt(get_db_fn, prompt_id, target_role, target_user_key=None, perspective=None):
    if target_role not in PROMPT_TARGET_ROLES:
        return {'ok': False, 'error': 'Invalid role.'}
    if perspective and perspective not in PROMPT_PERSPECTIVES:
        return {'ok': False, 'error': 'Invalid perspective.'}
    conn = get_db_fn()
    if not conn:
        return {'ok': False, 'error': 'Database unavailable'}
    try:
        cur = conn.cursor()
        cur.execute(
            '''UPDATE knowledge_prompts
               SET target_role = %s,
                   target_user_key = %s,
                   perspective = COALESCE(%s, perspective),
                   updated_at = NOW()
               WHERE id = %s AND status = 'open' ''',
            (target_role, target_user_key or None, perspective, prompt_id),
        )
        if cur.rowcount == 0:
            return {'ok': False, 'error': 'Prompt not found or not open.'}
        conn.commit()
        cur.close()
    except Exception as e:
        print(f'Ask PPS assign prompt error: {e}')
        return {'ok': False, 'error': str(e)}
    finally:
        conn.close()
    return {'ok': True}


def sync_prompts_from_gaps(get_db_fn, created_by, include_policy=False):
    """Turn open Q&A gaps into prompts — field team first, leadership optional."""
    conn = get_db_fn()
    if not conn:
        return {'ok': False, 'error': 'Database unavailable'}
    field_created = 0
    policy_created = 0
    skipped = 0
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            '''SELECT id, question, gap_topic, gap_summary
               FROM ask_pps_questions WHERE gap_status = 'open' ORDER BY created_at DESC'''
        )
        gaps = cur.fetchall()
        for gap in gaps:
            topic = gap.get('gap_topic') or 'general'
            category = _gap_topic_to_category(topic)
            field_role = _gap_topic_to_field_role(topic)
            if not _prompt_exists_for_gap(cur, gap['id'], 'field'):
                _create_prompt(
                    cur, gap['question'], category, field_role, 'field', 'gap',
                    created_by, source_gap_id=gap['id'], priority=10,
                )
                field_created += 1
            else:
                skipped += 1
            if include_policy and not _prompt_exists_for_gap(cur, gap['id'], 'policy'):
                _create_prompt(
                    cur, gap['question'], category, 'curator', 'policy', 'gap',
                    created_by, source_gap_id=gap['id'], priority=5,
                )
                policy_created += 1
            elif include_policy:
                skipped += 1
        conn.commit()
        cur.close()
    except Exception as e:
        conn.rollback()
        print(f'Ask PPS sync prompts error: {e}')
        return {'ok': False, 'error': str(e)}
    finally:
        conn.close()
    return {
        'ok': True,
        'field_created': field_created,
        'policy_created': policy_created,
        'skipped': skipped,
    }


def sync_thin_category_prompts(get_db_fn, created_by):
    """Prompt the field when a knowledge category has few documented entries."""
    conn = get_db_fn()
    if not conn:
        return {'ok': False, 'error': 'Database unavailable'}
    created = 0
    prompts_by_category = {
        'production_process': (
            'Typical mobilization: who does what from PPM through first day on site?',
            'pm',
        ),
        'sales_process': (
            'First contact to awarded proposal — what steps do you actually take?',
            'consultant',
        ),
        'company_operations': (
            'One habit or handoff that keeps jobs from slipping?',
            'any',
        ),
        'trades': (
            'Your main trade: what do new people get wrong most often?',
            'any',
        ),
    }
    try:
        cur = conn.cursor()
        for category in CATEGORIES:
            if category in THIN_CATEGORY_SKIP:
                continue
            cur.execute(
                '''SELECT COUNT(*) FROM knowledge_entries
                   WHERE category = %s AND status = 'active' ''',
                (category,),
            )
            count = cur.fetchone()[0]
            if count >= THIN_CATEGORY_THRESHOLD:
                continue
            if category not in prompts_by_category:
                continue
            question, target_role = prompts_by_category[category]
            cur.execute(
                '''SELECT id FROM knowledge_prompts
                   WHERE source_type = 'thin_category' AND category = %s
                     AND status = 'open' LIMIT 1''',
                (category,),
            )
            if cur.fetchone():
                continue
            _create_prompt(
                cur, question, category, target_role, 'field', 'thin_category',
                created_by, priority=3,
            )
            created += 1
        conn.commit()
        cur.close()
    except Exception as e:
        conn.rollback()
        print(f'Ask PPS thin category prompts error: {e}')
        return {'ok': False, 'error': str(e)}
    finally:
        conn.close()
    return {'ok': True, 'created': created}


def _field_role_hint_from_ref(source_ref):
    if not source_ref or not source_ref.startswith('psc:'):
        return None
    parts = source_ref.split(':')
    if len(parts) >= 2:
        return PSC_MODULE_FIELD_ROLE.get(parts[1])
    return None


def _enrich_prompt_row(row, users, user_key):
    row['field_role_hint'] = _field_role_hint_from_ref(row.get('source_ref'))
    row['target_user_display'] = _display(users, row.get('target_user_key'))
    row['can_answer'] = False  # set by caller
    return row


def ensure_field_prompt_bank(get_db_fn, created_by='system'):
    """Make sure the open prompt bank has identified-gap questions for team capture.

    Idempotent — skips refs that already exist. Safe to call from dashboard loads.
    """
    try:
        return sync_identified_gap_prompts(
            get_db_fn, created_by, assign_to=None, bank_mode=True,
        )
    except Exception as e:
        print(f'Ask PPS ensure prompt bank error: {e}')
        return {'ok': False, 'error': str(e)}


def get_prompts_for_user(get_db_fn, users, user_key, user_role, limit=None, include_all_for_curator=False):
    if limit is None:
        limit = 200
    conn = get_db_fn()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            '''SELECT p.*,
                      (SELECT COUNT(*) FROM knowledge_prompt_answers a
                       WHERE a.prompt_id = p.id) AS answer_count,
                      EXISTS (
                        SELECT 1 FROM knowledge_prompt_answers a2
                        WHERE a2.prompt_id = p.id AND a2.user_key = %s
                      ) AS answered_by_me,
                      EXISTS (
                        SELECT 1 FROM knowledge_prompt_skips s
                        WHERE s.prompt_id = p.id AND s.user_key = %s
                      ) AS skipped_by_me
               FROM knowledge_prompts p
               WHERE p.status = 'open' ''',
            (user_key, user_key),
        )
        rows = cur.fetchall()
        cur.close()
        active = []
        skipped_pool = []
        for row in rows:
            if not include_all_for_curator or not is_curator(user_key):
                if not _user_matches_prompt(user_key, user_role, row):
                    continue
            if row.get('answered_by_me'):
                continue
            _enrich_prompt_row(row, users, user_key)
            row['can_answer'] = _user_matches_prompt(user_key, user_role, row)
            if row.get('skipped_by_me'):
                skipped_pool.append(row)
            else:
                # Assigned + bank together so assigned monday items cannot pin the top
                active.append(row)

        # Full diversify shuffle every page open (not stable by priority / created_at)
        shuffled = _weighted_shuffle_prompts(active, user_key, user_role)
        # Soft-include skipped at the very end so a 30-min blitz can still cycle
        skipped = _weighted_shuffle_prompts(skipped_pool, user_key, user_role)
        matched = shuffled + skipped
        if limit:
            matched = matched[:limit]
        return matched
    except Exception as e:
        print(f'Ask PPS user prompts error: {e}')
        return []
    finally:
        conn.close()


def skip_prompt(get_db_fn, users, user_key, user_role, prompt_id):
    conn = get_db_fn()
    if not conn:
        return {'success': False, 'error': 'Database unavailable.'}, 500
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            'SELECT * FROM knowledge_prompts WHERE id = %s AND status = %s',
            (prompt_id, 'open'),
        )
        prompt = cur.fetchone()
        if not prompt:
            return {'success': False, 'error': 'Prompt not found.'}, 404
        if not _user_matches_prompt(user_key, user_role, prompt):
            return {'success': False, 'error': 'This prompt is not in your queue.'}, 403
        cur.execute(
            '''INSERT INTO knowledge_prompt_skips (prompt_id, user_key)
               VALUES (%s, %s) ON CONFLICT DO NOTHING''',
            (prompt_id, user_key),
        )
        conn.commit()
        cur.close()
    except Exception as e:
        print(f'Ask PPS skip prompt error: {e}')
        return {'success': False, 'error': 'Could not skip.'}, 500
    finally:
        conn.close()

    nxt = get_prompts_for_user(get_db_fn, users, user_key, user_role, limit=1)
    next_prompt = _serialize_prompt_for_client(nxt[0]) if nxt else None
    return {
        'success': True,
        'next_prompt': next_prompt,
        'remaining': len(get_prompts_for_user(get_db_fn, users, user_key, user_role)),
    }, 200


def get_consultant_assignees(users):
    return sorted(
        [
            {'key': k, 'display': v.get('display', k), 'title': v.get('title', '')}
            for k, v in users.items()
            if v.get('role') == 'consultant'
        ],
        key=lambda u: u['display'],
    )


def get_next_prompt_for_user(get_db_fn, users, user_key, user_role):
    prompts = get_prompts_for_user(get_db_fn, users, user_key, user_role, limit=1)
    if not prompts:
        # Seed bank from identified gaps so team capture sessions always have questions
        ensure_field_prompt_bank(get_db_fn, created_by=user_key or 'system')
        # Also thin-category prompts when KB is sparse
        try:
            sync_thin_category_prompts(get_db_fn, user_key or 'system')
        except Exception as e:
            print(f'Ask PPS thin seed on next-prompt: {e}')
        prompts = get_prompts_for_user(get_db_fn, users, user_key, user_role, limit=1)
    return prompts[0] if prompts else None


def _serialize_prompt_for_client(prompt):
    if not prompt:
        return None
    return {
        'id': prompt['id'],
        'question': prompt['question'],
        'perspective': prompt.get('perspective') or 'field',
        'field_role_hint': prompt.get('field_role_hint'),
        'target_role': prompt.get('target_role'),
    }


def submit_prompt_answer(get_db_fn, users, user_key, user_role, prompt_id, answer):
    answer = (answer or '').strip()
    if len(answer) < 10:
        return {'success': False, 'error': 'Please share at least a sentence or two.'}, 400
    if len(answer) > MAX_SUGGEST_LEN:
        return {'success': False, 'error': 'Answer is too long.'}, 400

    conn = get_db_fn()
    if not conn:
        return {'success': False, 'error': 'Database unavailable.'}, 500
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            'SELECT * FROM knowledge_prompts WHERE id = %s AND status = %s',
            (prompt_id, 'open'),
        )
        prompt = cur.fetchone()
        if not prompt:
            return {'success': False, 'error': 'Prompt not found or already closed.'}, 404
        if not _user_matches_prompt(user_key, user_role, prompt):
            return {'success': False, 'error': 'This prompt is not assigned to you.'}, 403

        display = _display(users, user_key)
        # Title: question first; name only if it fits. Content: answer body only.
        title = _prompt_entry_title(prompt['question'], display)
        content = (answer or '').strip()
        _insert_entry(
            cur, prompt['category'], title, content, 'prompt_response',
            author_key=user_key, status='pending',
            original_content=content,  # freeze raw team answer
        )
        cur.execute('SELECT id FROM knowledge_entries ORDER BY id DESC LIMIT 1')
        entry_id = cur.fetchone()['id']
        cur.execute(
            '''INSERT INTO knowledge_prompt_answers (prompt_id, user_key, answer, entry_id)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (prompt_id, user_key) DO UPDATE
               SET answer = EXCLUDED.answer, entry_id = EXCLUDED.entry_id''',
            (prompt_id, user_key, answer, entry_id),
        )
        perspective = prompt['perspective']
        prompt_question = prompt['question']
        conn.commit()
        cur.close()
    except Exception as e:
        conn.rollback()
        print(f'Ask PPS prompt answer error: {e}')
        return {'success': False, 'error': 'Could not save your answer.'}, 500
    finally:
        conn.close()

    # Persistent thank-you (shows on dashboard until dismissed / next logins)
    try:
        notify_ask_pps_submitted(
            get_db_fn, user_key, display, prompt_question, entry_id=entry_id,
        )
    except Exception as e:
        print(f'Ask PPS submit notify error: {e}')

    perspective_note = (
        'Field answers help us document how work really gets done.'
        if perspective == 'field'
        else 'Policy note saved — curators may still want field confirmation.'
    )
    nxt = get_prompts_for_user(get_db_fn, users, user_key, user_role, limit=1)
    next_prompt = _serialize_prompt_for_client(nxt[0]) if nxt else None
    first = display.split()[0] if display else 'there'
    return {
        'success': True,
        'message': (
            f'Thank you, {first}! Your answer was saved under your name for review. '
            f'{perspective_note} '
            'You’ll also see a thank-you on your dashboard until you dismiss it.'
        ),
        'submitted_by': display,
        'submitted_by_key': user_key,
        'next_prompt': next_prompt,
        'remaining': len(get_prompts_for_user(get_db_fn, users, user_key, user_role)),
    }, 200


def get_open_prompts_admin(get_db_fn, users):
    conn = get_db_fn()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            '''SELECT p.*,
                      (SELECT COUNT(*) FROM knowledge_prompt_answers a
                       WHERE a.prompt_id = p.id) AS answer_count
               FROM knowledge_prompts p
               WHERE p.status = 'open'
               ORDER BY p.priority DESC, p.created_at DESC
               LIMIT 100'''
        )
        rows = cur.fetchall()
        cur.close()
        for r in rows:
            r['created_by_display'] = _display(users, r.get('created_by'))
            r['target_user_display'] = _display(users, r.get('target_user_key'))
            r['field_role_hint'] = _field_role_hint_from_ref(r.get('source_ref'))
        return rows
    except Exception as e:
        print(f'Ask PPS open prompts error: {e}')
        return []
    finally:
        conn.close()


def get_category_coverage(get_db_fn):
    conn = get_db_fn()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            '''SELECT category, COUNT(*) AS cnt
               FROM knowledge_entries WHERE status = 'active'
               GROUP BY category ORDER BY cnt ASC, category'''
        )
        rows = cur.fetchall()
        cur.close()
        return rows
    except Exception as e:
        print(f'Ask PPS category coverage error: {e}')
        return []
    finally:
        conn.close()


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
               ORDER BY id'''
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
    # Use replace, not str.format — prompt contains literal { } in the JSON example.
    system = (
        SYSTEM_PROMPT
        .replace('{voice_terminology}', _load_voice_terminology())
        .replace('{entries}', prompt_entries or '(no entries retrieved)')
    )
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
            '''SELECT k.*, u.display_name AS author_display,
                      a.answer AS prompt_raw_answer,
                      p.question AS prompt_question
               FROM knowledge_entries k
               LEFT JOIN hub_users u ON u.user_key = k.author_key
               LEFT JOIN knowledge_prompt_answers a ON a.entry_id = k.id
               LEFT JOIN knowledge_prompts p ON p.id = a.prompt_id
               WHERE k.status = 'pending'
               ORDER BY k.created_at DESC'''
        )
        pending = cur.fetchall()
        for p in pending:
            if not p.get('author_display'):
                p['author_display'] = _display(users, p.get('author_key'))
            # Normalize legacy stamp / Name: title into clean form (pending only)
            p = _normalize_pending_prompt_entry(cur, p, users)
            body = _extract_answer_body(
                p.get('content'),
                original_content=p.get('original_content'),
                prompt_raw=p.get('prompt_raw_answer'),
            )
            original = _extract_answer_body(
                p.get('original_content') or p.get('prompt_raw_answer') or p.get('content'),
                original_content=p.get('original_content'),
                prompt_raw=p.get('prompt_raw_answer'),
            )
            p['display_question'] = _display_question_for_entry(p)
            p['display_title'] = _prompt_entry_title(
                p['display_question'], p.get('author_display')
            ) if p.get('display_question') else (p.get('title') or '')
            p['answer_body'] = body
            p['original_answer'] = original
            p['edit_body'] = body
        try:
            conn.commit()
        except Exception:
            pass

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
        cur.execute("SELECT COUNT(*) AS cnt FROM knowledge_prompts WHERE status = 'open'")
        open_prompts = cur.fetchone()['cnt']

        # Recent actives (e.g. accidental approve) — easy Return to pending
        cur.execute(
            '''SELECT k.*, u.display_name AS author_display
               FROM knowledge_entries k
               LEFT JOIN hub_users u ON u.user_key = k.author_key
               WHERE k.status = 'active'
                 AND (
                   k.source_type = 'prompt_response'
                   OR k.updated_at >= NOW() - INTERVAL '7 days'
                 )
               ORDER BY k.updated_at DESC NULLS LAST, k.id DESC
               LIMIT 12'''
        )
        recently_activated = cur.fetchall()
        for r in recently_activated:
            if not r.get('author_display'):
                r['author_display'] = _display(users, r.get('author_key'))

        cur.close()
        return {
            'gaps': gaps,
            'pending': pending,
            'log': log,
            'knowledge': knowledge,
            'recently_activated': recently_activated,
            'week_counts': week_counts,
            'open_gaps': open_gaps,
            'pending_cnt': pending_cnt,
            'open_prompts': open_prompts,
            'prompts': get_open_prompts_admin(get_db_fn, users),
            'category_coverage': get_category_coverage(get_db_fn),
            'psc_gap_preview': len(discover_psc_training_gaps(get_db_fn)),
            'feedback_gap_preview': len(discover_psc_feedback_gaps(get_db_fn)),
            'audit_gap_preview': len(discover_knowledge_audit_gaps(get_db_fn)),
        }
    except Exception as e:
        print(f'Ask PPS admin data error: {e}')
        return {}
    finally:
        conn.close()


def get_digest_line(get_db_fn, start, end, users=None):
    """Multi-line Ask PPS block for the daily digest (prompt answers are primary)."""
    users = users or {}
    conn = get_db_fn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Team capture answers in the report window
        cur.execute(
            '''SELECT user_key, COUNT(*) AS cnt
               FROM knowledge_prompt_answers
               WHERE created_at >= %s AND created_at < %s
               GROUP BY user_key
               ORDER BY cnt DESC, user_key''',
            (start, end),
        )
        answer_rows = cur.fetchall() or []
        total_answers = sum(int(r['cnt'] or 0) for r in answer_rows)

        # Recommended questions added to the bank
        cur.execute(
            '''SELECT COUNT(*) AS cnt FROM knowledge_prompts
               WHERE source_type = 'user_recommend'
                 AND created_at >= %s AND created_at < %s''',
            (start, end),
        )
        recommended = int((cur.fetchone() or {}).get('cnt') or 0)

        # Lookups (search box) — secondary
        cur.execute(
            '''SELECT COUNT(*) AS cnt FROM ask_pps_questions
               WHERE created_at >= %s AND created_at < %s''',
            (start, end),
        )
        lookups = int((cur.fetchone() or {}).get('cnt') or 0)

        cur.execute("SELECT COUNT(*) AS cnt FROM knowledge_prompts WHERE status = 'open'")
        open_prompts = int((cur.fetchone() or {}).get('cnt') or 0)

        # Distinct people who still have unanswered open prompts they can match is heavy;
        # just report bank size.
        cur.close()

        if total_answers == 0 and recommended == 0 and lookups == 0 and open_prompts == 0:
            return None

        lines = ['ASK PPS']
        if total_answers:
            lines.append(
                f'  Prompt answers: {total_answers} '
                f'from {len(answer_rows)} person{"s" if len(answer_rows) != 1 else ""}'
            )
            for r in answer_rows:
                name = _display(users, r['user_key'])
                n = int(r['cnt'] or 0)
                lines.append(f'    · {name}: {n}')
        else:
            lines.append('  Prompt answers: 0')

        if recommended:
            lines.append(
                f'  Questions suggested by team: {recommended}'
            )
        if lookups:
            lines.append(
                f'  Knowledge lookups: {lookups}'
            )
        if open_prompts:
            lines.append(
                f'  Open prompts still in bank: {open_prompts}'
            )

        return '\n'.join(lines)
    except Exception as e:
        print(f'Ask PPS digest error: {e}')
        return None
    finally:
        conn.close()


def register_routes(app, get_db_fn, users, claude_api_key, claude_model, require_login):
    @app.route('/ask-pps')
    @require_login
    def ask_pps_page():
        """Field-facing Ask PPS only (same experience for everyone, including curators)."""
        user_key = session['user_key']
        user_role = session.get('role', '')
        q = (request.args.get('q') or '').strip()
        recent = get_recent_questions(get_db_fn, user_key)
        # Same queue rules as dashboard — no curator “see everything / assign” UI.
        prompts = get_prompts_for_user(
            get_db_fn, users, user_key, user_role,
            include_all_for_curator=False,
        )
        # Only show prompts this user can answer
        prompts = [p for p in prompts if p.get('can_answer')]
        return render_template(
            'ask_pps.html',
            initial_question=q,
            recent=recent,
            categories=CATEGORIES,
            prompts=prompts,
        )

    @app.route('/api/ask-pps/recommend-question', methods=['POST'])
    @require_login
    def api_ask_pps_recommend_question():
        """Anyone can suggest a short question for the team capture bank."""
        user_key = session['user_key']
        data = request.get_json(silent=True) or {}
        question = (data.get('question') or '').strip()
        if len(question) < 8:
            return jsonify({'success': False, 'error': 'Write a short question (a few words).'}), 400
        if len(question) > 400:
            return jsonify({'success': False, 'error': 'Keep it under 400 characters.'}), 400
        if not question.endswith('?'):
            question = question.rstrip('. ') + '?'
        display = _display(users, user_key)
        conn = get_db_fn()
        if not conn:
            return jsonify({'success': False, 'error': 'Database unavailable.'}), 500
        try:
            cur = conn.cursor()
            # Open prompt for the bank (anyone can answer) + pending note for review trail
            _create_prompt(
                cur,
                question,
                'general',
                'any',
                'field',
                'user_recommend',
                user_key,
                priority=8,
                source_ref=f'user:{user_key}:{int(time.time())}',
            )
            _insert_entry(
                cur,
                'general',
                f'Recommended question — {display}',
                (
                    f'Suggested by: {display} ({user_key})\n'
                    f'Question: {question}\n\n'
                    'Added to the open prompt bank for the team to answer.'
                ),
                'team_contribution',
                author_key=user_key,
                status='pending',
            )
            conn.commit()
            cur.close()
        except Exception as e:
            conn.rollback()
            print(f'Ask PPS recommend question error: {e}')
            return jsonify({'success': False, 'error': 'Could not save question.'}), 500
        finally:
            conn.close()
        return jsonify({
            'success': True,
            'message': 'Thanks — added for the team to answer.',
        })

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

    @app.route('/api/ask-pps/load-identified-gaps', methods=['POST'])
    @require_login
    def api_ask_pps_load_identified_gaps():
        user_key = session['user_key']
        if not is_curator(user_key):
            return jsonify({'success': False, 'error': 'Curators only.'}), 403
        data = request.get_json(silent=True) or {}
        assign_to = (data.get('assign_to') or '').strip() or None
        bank_mode = data.get('bank_mode', True) if assign_to is None else False
        result = sync_identified_gap_prompts(
            get_db_fn, user_key, assign_to=assign_to, bank_mode=bank_mode,
        )
        if not result.get('ok'):
            return jsonify({'success': False, 'error': result.get('error', 'Failed.')}), 500
        return jsonify({'success': True, **result})

    @app.route('/api/ask-pps/prompt-skip', methods=['POST'])
    @require_login
    def api_ask_pps_prompt_skip():
        user_key = session['user_key']
        user_role = session.get('role', '')
        data = request.get_json(silent=True) or {}
        try:
            prompt_id = int(data.get('prompt_id'))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'Invalid prompt.'}), 400
        payload, status = skip_prompt(get_db_fn, users, user_key, user_role, prompt_id)
        return jsonify(payload), status

    @app.route('/api/ask-pps/prompt-assign', methods=['POST'])
    @require_login
    def api_ask_pps_prompt_assign():
        user_key = session['user_key']
        if not is_curator(user_key):
            return jsonify({'success': False, 'error': 'Curators only.'}), 403
        data = request.get_json(silent=True) or {}
        try:
            prompt_id = int(data.get('prompt_id'))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'Invalid prompt.'}), 400
        target_user_key = (data.get('target_user_key') or '').strip() or None
        target_role = (data.get('target_role') or 'consultant').strip()
        perspective = (data.get('perspective') or 'field').strip()
        result = assign_prompt(get_db_fn, prompt_id, target_role, target_user_key, perspective)
        if not result.get('ok'):
            return jsonify({'success': False, 'error': result.get('error', 'Failed.')}), 400
        return jsonify({'success': True})

    @app.route('/api/ask-pps/prompt-answer', methods=['POST'])
    @require_login
    def api_ask_pps_prompt_answer():
        user_key = session['user_key']
        user_role = session.get('role', '')
        data = request.get_json(silent=True) or {}
        prompt_id = data.get('prompt_id')
        answer = (data.get('answer') or '').strip()
        try:
            prompt_id = int(prompt_id)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': 'Invalid prompt.'}), 400
        payload, status = submit_prompt_answer(
            get_db_fn, users, user_key, user_role, prompt_id, answer,
        )
        return jsonify(payload), status

    @app.route('/api/notifications/<int:notification_id>/dismiss', methods=['POST'])
    @require_login
    def api_dismiss_notification(notification_id):
        user_key = session['user_key']
        ok = mark_notification_read(get_db_fn, user_key, notification_id)
        return jsonify({'success': bool(ok)})

    @app.route('/admin/ask-pps/prompts/sync-gaps', methods=['POST'])
    @require_login
    @require_ask_pps_curator
    def admin_ask_pps_sync_gap_prompts():
        include_policy = request.form.get('include_policy') == '1' or (
            (request.get_json(silent=True) or {}).get('include_policy')
        )
        result = sync_prompts_from_gaps(
            get_db_fn, session['user_key'], include_policy=bool(include_policy),
        )
        if not result.get('ok'):
            return jsonify(result), 500
        return jsonify(result)

    @app.route('/admin/ask-pps/prompts/sync-thin', methods=['POST'])
    @require_login
    @require_ask_pps_curator
    def admin_ask_pps_sync_thin_prompts():
        result = sync_thin_category_prompts(get_db_fn, session['user_key'])
        if not result.get('ok'):
            return jsonify(result), 500
        return jsonify(result)

    @app.route('/admin/ask-pps/prompts/sync-identified', methods=['POST'])
    @require_login
    @require_ask_pps_curator
    def admin_ask_pps_sync_identified_prompts():
        data = request.get_json(silent=True) or {}
        bank_mode = bool(data.get('bank_mode', False))
        assign_to = (data.get('assign_to') or '').strip() or None
        if not bank_mode and not assign_to:
            assign_to = session.get('user_key') or 'thomas_ellison'
        result = sync_identified_gap_prompts(
            get_db_fn, session['user_key'], assign_to=assign_to, bank_mode=bank_mode,
        )
        if not result.get('ok'):
            return jsonify(result), 500
        return jsonify(result)

    @app.route('/admin/ask-pps/prompts/<int:prompt_id>/assign', methods=['POST'])
    @require_login
    @require_ask_pps_curator
    def admin_ask_pps_assign_prompt(prompt_id):
        target_role = (request.form.get('target_role') or 'any').strip()
        target_user_key = (request.form.get('target_user_key') or '').strip() or None
        perspective = (request.form.get('perspective') or '').strip() or None
        result = assign_prompt(get_db_fn, prompt_id, target_role, target_user_key, perspective)
        if not result.get('ok'):
            return jsonify(result), 400
        if request.headers.get('Accept', '').find('application/json') >= 0:
            return jsonify(result)
        return redirect(url_for('admin_ask_pps'))

    @app.route('/admin/ask-pps/prompts/create', methods=['POST'])
    @require_login
    @require_ask_pps_curator
    def admin_ask_pps_create_prompt():
        category = (request.form.get('category') or 'general').strip()
        question = (request.form.get('question') or '').strip()
        target_role = (request.form.get('target_role') or 'any').strip()
        perspective = (request.form.get('perspective') or 'field').strip()
        target_user_key = (request.form.get('target_user_key') or '').strip() or None
        if category not in CATEGORIES or target_role not in PROMPT_TARGET_ROLES:
            return redirect(url_for('admin_ask_pps'))
        if perspective not in PROMPT_PERSPECTIVES or len(question) < 8:
            return redirect(url_for('admin_ask_pps'))
        conn = get_db_fn()
        if conn:
            try:
                cur = conn.cursor()
                _create_prompt(
                    cur, question, category, target_role, perspective, 'curator',
                    session['user_key'], target_user_key=target_user_key,
                )
                conn.commit()
                cur.close()
            except Exception as e:
                print(f'Ask PPS create prompt error: {e}')
            finally:
                conn.close()
        return redirect(url_for('admin_ask_pps'))

    @app.route('/admin/ask-pps/prompts/<int:prompt_id>/dismiss', methods=['POST'])
    @require_login
    @require_ask_pps_curator
    def admin_ask_pps_dismiss_prompt(prompt_id):
        conn = get_db_fn()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute(
                    '''UPDATE knowledge_prompts SET status = 'dismissed', updated_at = NOW()
                       WHERE id = %s''',
                    (prompt_id,),
                )
                conn.commit()
                cur.close()
            except Exception as e:
                print(f'Ask PPS dismiss prompt error: {e}')
            finally:
                conn.close()
        return redirect(url_for('admin_ask_pps'))

    def _render_ask_pps_admin():
        """Curation UI — admin/curator only. Field Ask PPS stays at /ask-pps for everyone."""
        data = get_admin_data(get_db_fn, users)
        assignable_users = sorted(
            [
                {
                    'key': k,
                    'display': v.get('display', k),
                    'role': v.get('role', ''),
                    'title': v.get('title', ''),
                }
                for k, v in users.items()
            ],
            key=lambda u: u['display'],
        )
        return render_template(
            'admin_ask_pps.html',
            categories=CATEGORIES,
            curators=CURATORS,
            assignable_users=assignable_users,
            prompt_target_roles=PROMPT_TARGET_ROLES,
            **data,
        )

    @app.route('/admin/ask-pps')
    @require_login
    @require_ask_pps_curator
    def admin_ask_pps():
        """Knowledge curation (pending answers, gaps, prompts). Not the field Ask PPS UI."""
        return _render_ask_pps_admin()

    @app.route('/admin/ask-pps/_legacy')
    @require_login
    @require_ask_pps_curator
    def admin_ask_pps_legacy():
        """Old bookmark → same curation page."""
        return redirect(url_for('admin_ask_pps'))

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
        """Publish pending → active once. Double-submit does not re-notify."""
        conn = get_db_fn()
        transitioned = None  # row only when status was pending
        if conn:
            try:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                cur.execute(
                    '''UPDATE knowledge_entries
                       SET status = 'active', updated_at = NOW(),
                           search_tsv = to_tsvector('english',
                               coalesce(title, '') || ' ' || coalesce(content, ''))
                       WHERE id = %s AND status = 'pending'
                       RETURNING author_key, title''',
                    (entry_id,),
                )
                transitioned = cur.fetchone()
                conn.commit()
                cur.close()
            except Exception as e:
                print(f'Ask PPS approve error: {e}')
            finally:
                conn.close()
        if transitioned and transitioned.get('author_key'):
            try:
                notify_ask_pps_approved(
                    get_db_fn,
                    transitioned['author_key'],
                    _display(users, transitioned['author_key']),
                    transitioned.get('title'),
                    entry_id=entry_id,
                )
            except Exception as e:
                print(f'Ask PPS approve notify error: {e}')
        return redirect(url_for('admin_ask_pps') + '#pending-contributions')

    @app.route('/admin/ask-pps/pending/<int:entry_id>/reject', methods=['POST'])
    @require_login
    @require_ask_pps_curator
    def admin_ask_pps_reject(entry_id):
        conn = get_db_fn()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute(
                    '''UPDATE knowledge_entries
                       SET status = 'archived', updated_at = NOW()
                       WHERE id = %s AND status = 'pending' ''',
                    (entry_id,),
                )
                conn.commit()
                cur.close()
            except Exception as e:
                print(f'Ask PPS reject error: {e}')
            finally:
                conn.close()
        return redirect(url_for('admin_ask_pps') + '#pending-contributions')

    @app.route('/admin/ask-pps/pending/<int:entry_id>/edit', methods=['POST'])
    @require_login
    @require_ask_pps_curator
    def admin_ask_pps_edit_pending(entry_id):
        """Save answer body (+ optional category). Stays pending — does not publish.
        Never overwrites original_content (first team submission)."""
        category = (request.form.get('category') or 'general').strip()
        content = _extract_answer_body((request.form.get('content') or '').strip())
        if category not in CATEGORIES or len(content) < 3:
            return redirect(url_for('admin_ask_pps') + f'#pending-{entry_id}')
        conn = get_db_fn()
        if conn:
            try:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                cur.execute(
                    '''SELECT k.title, k.author_key, k.original_content, k.content,
                              a.answer AS prompt_raw_answer, p.question AS prompt_question
                       FROM knowledge_entries k
                       LEFT JOIN knowledge_prompt_answers a ON a.entry_id = k.id
                       LEFT JOIN knowledge_prompts p ON p.id = a.prompt_id
                       WHERE k.id = %s''',
                    (entry_id,),
                )
                row = cur.fetchone() or {}
                author = _display(users, row.get('author_key'))
                question = (row.get('prompt_question') or '').strip() or _question_from_legacy_title(
                    row.get('title'), author
                ) or _display_question_for_entry({
                    'title': row.get('title'),
                    'author_display': author,
                    'prompt_question': row.get('prompt_question'),
                })
                title = _prompt_entry_title(question, author) if question else (row.get('title') or 'Answer')
                # Freeze pre-edit body as original if missing
                prior_body = _extract_answer_body(
                    row.get('content'),
                    original_content=row.get('original_content'),
                    prompt_raw=row.get('prompt_raw_answer'),
                )
                cur.execute(
                    '''UPDATE knowledge_entries
                       SET category = %s,
                           title = %s,
                           content = %s,
                           status = 'pending',
                           original_content = COALESCE(NULLIF(original_content, ''), %s),
                           updated_at = NOW(),
                           search_tsv = to_tsvector('english',
                               coalesce(%s, '') || ' ' || coalesce(%s, ''))
                       WHERE id = %s AND status = 'pending' ''',
                    (category, title, content, prior_body or content, title, content, entry_id),
                )
                conn.commit()
                cur.close()
            except Exception as e:
                print(f'Ask PPS edit pending error: {e}')
            finally:
                conn.close()
        return redirect(url_for('admin_ask_pps') + f'#pending-{entry_id}')

    @app.route('/admin/ask-pps/entry/<int:entry_id>/return-pending', methods=['POST'])
    @require_login
    @require_ask_pps_curator
    def admin_ask_pps_return_pending(entry_id):
        """Move an active (or archived) entry back to pending for re-review."""
        conn = get_db_fn()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute(
                    '''UPDATE knowledge_entries
                       SET status = 'pending', updated_at = NOW()
                       WHERE id = %s''',
                    (entry_id,),
                )
                conn.commit()
                cur.close()
            except Exception as e:
                print(f'Ask PPS return-pending error: {e}')
            finally:
                conn.close()
        return redirect(url_for('admin_ask_pps') + '#pending-contributions')

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