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
    'ops_decision_ownership': 'company_operations',
    'ops_trade_partners': 'production_process',
    'ops_client_comms': 'sales_process',
    'ops_callbacks': 'production_process',
    'ops_common_mistakes': 'training_core_values',
}

PSC_MODULE_FIELD_ROLE = {
    'ops_partner_projects': 'consultant',
    'ops_monday': 'consultant',
    'ops_lifecycle': 'pm',
    'ops_project_evaluation': 'consultant',
    'ops_estimating': 'consultant',
    'ops_decision_ownership': 'consultant',
    'ops_trade_partners': 'pm',
    'ops_client_comms': 'consultant',
    'ops_callbacks': 'pm',
    'ops_common_mistakes': 'consultant',
}

KNOWLEDGE_AUDIT_GAPS = [
    (
        'audit:ppm',
        'production_process',
        'pm',
        'How does the Pre-Project Meeting (PPM) actually run — who attends, the agenda, '
        'and what must be confirmed before mobilization?',
    ),
    (
        'audit:change_orders',
        'production_process',
        'pm',
        'Walk through a change order from discovery to approval — who documents it, '
        'who signs off, and how the client hears about it?',
    ),
    (
        'audit:closeout',
        'production_process',
        'pm',
        'What is the punch list and close-out handoff — who walks with whom, and what '
        'must be documented before the job is done?',
    ),
    (
        'audit:proposal_review',
        'sales_process',
        'consultant',
        'Before a proposal goes to a client, what review steps happen — who reads it, '
        'what gets checked, and what is never sent cold?',
    ),
    (
        'audit:warranty',
        'trades',
        'consultant',
        'How do we explain roofing (or trade) warranty language to clients — PPS labor vs '
        'manufacturer, and what qualifies?',
    ),
]

# PSC curriculum feedback (Rachel Farler, 2026) — themes beyond [TO DOCUMENT] bullets
PSC_FEEDBACK_GAPS = [
    (
        'pscfb:partner_mentor',
        'training_core_values',
        'consultant',
        'How is a mentor consultant chosen for partner-project onboarding, and what makes a good partner project for a new PSC?',
    ),
    (
        'pscfb:partner_progressive',
        'training_core_values',
        'consultant',
        'How does responsibility actually shift from observe → participate → lead on partner projects? Give a real example.',
    ),
    (
        'pscfb:partner_debrief',
        'training_core_values',
        'consultant',
        'What should a post-project debrief cover after a partner project milestone — and who runs it?',
    ),
    (
        'pscfb:comm_standards',
        'sales_process',
        'consultant',
        'What are the standard client communication touchpoints by project phase (site visit through close-out)?',
    ),
    (
        'pscfb:difficult_convos',
        'sales_process',
        'consultant',
        'How should a PSC handle a schedule delay conversation with a property manager — what do you say first?',
    ),
    (
        'pscfb:eval_checklist',
        'sales_process',
        'consultant',
        'What do you always capture on a site visit before scoping (photos, measurements, unknowns, access, phasing)?',
    ),
    (
        'pscfb:ownership_guide',
        'company_operations',
        'consultant',
        'For pricing support, callbacks, change orders, and concealed conditions — who owns the decision vs. who gets looped in?',
    ),
    (
        'pscfb:pricing_inputs',
        'sales_process',
        'consultant',
        'What information must a PSC gather so a PM can build an accurate production price (not just hub defaults)?',
    ),
    (
        'pscfb:tp_reference',
        'production_process',
        'pm',
        'Who are our go-to Trade Partners by trade, and how do you decide which partner to use on a job?',
    ),
    (
        'pscfb:callback_intake',
        'production_process',
        'pm',
        'Walk through callback/warranty intake — who logs it, who talks to the client, and how it gets resolved.',
    ),
    (
        'pscfb:graduation_ready',
        'training_core_values',
        'consultant',
        'What tells you a new PSC is ready for independent client-facing work — concrete signs, not just weeks completed?',
    ),
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
    return user_role == target


def _perspective_label(perspective):
    return 'How we actually do it (field)' if perspective == 'field' else 'Leadership intent (policy)'


def _format_prompt_entry_content(question, answer, perspective, display_name, hub_role):
    header = _perspective_label(perspective)
    role_note = f'{display_name}'
    if hub_role:
        role_note += f', {hub_role}'
    return (
        f'{header} — {role_note}:\n{answer.strip()}\n\n'
        f'Prompt: {question.strip()}'
    )


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
                if _topic_documented(cur, topic):
                    continue
                ref = f'psc:{module_id}:{i}'
                gaps.append({
                    'source_ref': ref,
                    'question': (
                        f'PSC Training gap — {module_title}: {topic}? '
                        f'(Document for onboarding; field reality may differ from leadership intent.)'
                    ),
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
                'question': f'PSC feedback gap: {question}',
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
                'question': f'Knowledge gap: {question}',
                'category': category,
                'field_role': field_role,
            })
        cur.close()
    except Exception as e:
        print(f'Ask PPS discover audit gaps error: {e}')
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
    if source_ref.startswith('audit:'):
        return 'audit_gap'
    return 'curator'


def sync_identified_gap_prompts(get_db_fn, created_by, assign_to=None, bank_mode=True):
    """Create prompts for all identified gaps. bank_mode=True → field prompts by role (assign PSCs later)."""
    conn = get_db_fn()
    if not conn:
        return {'ok': False, 'error': 'Database unavailable'}
    psc_gaps = discover_psc_training_gaps(get_db_fn)
    feedback_gaps = discover_psc_feedback_gaps(get_db_fn)
    audit_gaps = discover_knowledge_audit_gaps(get_db_fn)
    all_gaps = psc_gaps + feedback_gaps + audit_gaps
    created = 0
    skipped = 0
    perspective = 'field' if bank_mode and not assign_to else 'policy'
    try:
        cur = conn.cursor()
        for gap in all_gaps:
            ref = gap['source_ref']
            if _prompt_exists_by_ref(cur, ref):
                skipped += 1
                continue
            priority = 12 if ref.startswith('psc:') else (11 if ref.startswith('pscfb:') else 9)
            _create_prompt(
                cur,
                gap['question'],
                gap['category'],
                gap.get('field_role', 'any'),
                perspective,
                _gap_source_type(ref),
                created_by,
                target_user_key=assign_to,
                priority=priority,
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
        'skipped': skipped,
        'psc_candidates': len(psc_gaps),
        'feedback_candidates': len(feedback_gaps),
        'audit_candidates': len(audit_gaps),
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
            'Walk us through a typical mobilization — who does what from PPM through '
            'first day on site?',
            'pm',
        ),
        'sales_process': (
            'From first client contact to awarded proposal — what are the real steps '
            'you follow today?',
            'consultant',
        ),
        'company_operations': (
            'What is one operations habit or handoff that keeps jobs from slipping?',
            'any',
        ),
        'trades': (
            'For your main trade focus — what do new PMs or consultants get wrong most often?',
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
               WHERE p.status = 'open'
               ORDER BY
                 CASE WHEN EXISTS (
                   SELECT 1 FROM knowledge_prompt_skips s
                   WHERE s.prompt_id = p.id AND s.user_key = %s
                 ) THEN 1 ELSE 0 END,
                 CASE WHEN p.target_user_key = %s THEN 0 ELSE 1 END,
                 p.priority DESC,
                 p.created_at ASC''',
            (user_key, user_key, user_key, user_key),
        )
        rows = cur.fetchall()
        cur.close()
        matched = []
        for row in rows:
            if not include_all_for_curator or not is_curator(user_key):
                if not _user_matches_prompt(user_key, user_role, row):
                    continue
            if row.get('answered_by_me'):
                continue
            _enrich_prompt_row(row, users, user_key)
            row['can_answer'] = _user_matches_prompt(user_key, user_role, row)
            matched.append(row)
            if limit and len(matched) >= limit:
                break
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
    next_prompt = None
    if nxt:
        p = nxt[0]
        next_prompt = {
            'id': p['id'],
            'question': p['question'],
            'perspective': p['perspective'],
            'field_role_hint': p.get('field_role_hint'),
        }
    return {'success': True, 'next_prompt': next_prompt}, 200


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
    return prompts[0] if prompts else None


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
        hub_role = users.get(user_key, {}).get('title', user_role)
        title = prompt['question'][:120]
        if len(prompt['question']) > 120:
            title += '…'
        content = _format_prompt_entry_content(
            prompt['question'], answer, prompt['perspective'], display, hub_role,
        )
        _insert_entry(
            cur, prompt['category'], title, content, 'prompt_response',
            author_key=user_key, status='pending',
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
        conn.commit()
        cur.close()
    except Exception as e:
        conn.rollback()
        print(f'Ask PPS prompt answer error: {e}')
        return {'success': False, 'error': 'Could not save your answer.'}, 500
    finally:
        conn.close()

    perspective_note = (
        'Field answers help us document how work really gets done.'
        if perspective == 'field'
        else 'Policy note saved — curators may still want field confirmation.'
    )
    return {
        'success': True,
        'message': f'Thanks — sent for curator review. {perspective_note}',
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
        cur.execute("SELECT COUNT(*) AS cnt FROM knowledge_prompts WHERE status = 'open'")
        open_prompts = cur.fetchone()['cnt']

        cur.close()
        return {
            'gaps': gaps,
            'pending': pending,
            'log': log,
            'knowledge': knowledge,
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
        cur.execute("SELECT COUNT(*) FROM knowledge_prompts WHERE status = 'open'")
        open_prompts = cur.fetchone()[0]
        cur.close()
        if questions == 0 and open_gaps == 0 and open_prompts == 0:
            return None
        parts = [f'{questions} question{"s" if questions != 1 else ""} yesterday']
        if open_gaps:
            parts.append(f'{open_gaps} open gap{"s" if open_gaps != 1 else ""}')
        if open_prompts:
            parts.append(f'{open_prompts} open prompt{"s" if open_prompts != 1 else ""}')
        return 'Ask PPS: ' + ', '.join(parts) + '.'
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
        user_role = session.get('role', '')
        q = (request.args.get('q') or '').strip()
        recent = get_recent_questions(get_db_fn, user_key)
        curator = is_curator(user_key)
        psc_gaps = []
        feedback_gaps = []
        audit_gaps = []
        psc_gap_modules = []
        try:
            psc_gaps = discover_psc_training_gaps(get_db_fn)
            feedback_gaps = discover_psc_feedback_gaps(get_db_fn)
            audit_gaps = discover_knowledge_audit_gaps(get_db_fn)
            if curator:
                psc_gap_modules = group_psc_gaps_for_display(psc_gaps)
        except Exception as e:
            print(f'Ask PPS page gap discovery error: {e}')
        prompts = get_prompts_for_user(
            get_db_fn, users, user_key, user_role,
            include_all_for_curator=curator,
        )
        open_prompt_count = 0
        try:
            conn_cnt = get_db_fn()
            if conn_cnt:
                cur_cnt = conn_cnt.cursor()
                cur_cnt.execute("SELECT COUNT(*) FROM knowledge_prompts WHERE status = 'open'")
                open_prompt_count = cur_cnt.fetchone()[0]
                cur_cnt.close()
                conn_cnt.close()
        except Exception:
            pass
        return render_template(
            'ask_pps.html',
            initial_question=q,
            recent=recent,
            categories=CATEGORIES,
            prompts=prompts,
            prompt_target_roles=PROMPT_TARGET_ROLES,
            prompt_perspectives=PROMPT_PERSPECTIVES,
            is_curator=curator,
            psc_gap_preview=len(psc_gaps),
            feedback_gap_preview=len(feedback_gaps),
            audit_gap_preview=len(audit_gaps),
            identified_gap_total=len(psc_gaps) + len(feedback_gaps) + len(audit_gaps),
            psc_gap_modules=psc_gap_modules,
            feedback_gaps=feedback_gaps,
            audit_gaps=audit_gaps,
            consultant_assignees=get_consultant_assignees(users),
            open_prompt_count=open_prompt_count,
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

    @app.route('/admin/ask-pps')
    @require_login
    @require_ask_pps_curator
    def admin_ask_pps():
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