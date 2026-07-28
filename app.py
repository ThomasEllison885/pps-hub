import os
import re
import json
import threading
import base64
from io import BytesIO
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file, send_from_directory, make_response
from werkzeug.exceptions import HTTPException
from psc_training_data import (
    PSC_TRAINING_META, PSC_TRAINING_MANAGER, get_training_curriculum,
    get_all_item_ids, count_trackable_items,
    PSC_ROLEPLAY_SCENARIOS, PSC_ROLEPLAY_GRADER_RULES,
    get_roleplay_scenario, get_roleplay_week_links, get_roleplay_sales_links,
    get_suggested_roleplay_ids, segment_color,
    ROLEPLAY_DAILY_GRADE_LIMIT, ROLEPLAY_DAILY_TURN_LIMIT,
)
from pm_training_data import (
    PM_TRAINING_META, PM_TRAINING_MANAGER, get_pm_training_curriculum,
    get_pm_training_item_ids, count_pm_trackable_items, get_pm_week_item_ids,
    get_pm_week_checkin_questions,
)
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor
from auth_helpers import (
    HUB_PUBLIC_URL, PROPOSAL_URL, PROFILE_URL, LOGIN_LOCKOUT_MINUTES, MAX_LOGIN_FAILURES,
    safe_next_url, client_ip, record_login_attempt, is_login_locked, clear_login_failures,
    generate_sso_code, exchange_sso_code,
    create_password_reset_token, peek_password_reset_token,
    consume_password_reset_token, reset_url_for_token,
)
import ask_pps
from runway_game_data import (
    RUNWAY_OWNER,
    RUNWAY_MAPBOX_TOKEN,
    RUNWAY_PUBLIC_ACCESS,
    RUNWAY_SHARE_TOKEN,
    get_runway_bootstrap,
)


def _load_dotenv():
    """Load .env into os.environ (keys already set in the environment win)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if not os.path.isfile(path):
        return
    with open(path, encoding='utf-8') as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, val = line.partition('=')
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


_load_dotenv()

app = Flask(__name__)
_secret = os.environ.get('SECRET_KEY', '').strip()
if not _secret:
    print(
        'WARNING: SECRET_KEY is not set — hub will run but you should add SECRET_KEY '
        'in Render Environment (generate a random 32+ char string).'
    )
    _secret = 'pps-hub-unset-secret-key'
app.secret_key = _secret

INTERNAL_API_KEY = os.environ.get('INTERNAL_API_KEY', '').strip()
CLAUDE_API_KEY = os.environ.get('CLAUDE_API_KEY', '').strip()
CLAUDE_MODEL = 'claude-sonnet-4-6'
if not INTERNAL_API_KEY:
    print(
        'WARNING: INTERNAL_API_KEY is not set — proposal/profile SSO and internal APIs '
        'will not work until you add the same key on hub, proposal, and profile services.'
    )
MASTER_PASSWORD = os.environ.get('MASTER_PASSWORD', '').strip()

DATABASE_URL = os.environ.get('DATABASE_URL', '')
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024  # 10 MB per file
VAULT_STORAGE_LIMIT_BYTES = int(os.environ.get('VAULT_STORAGE_LIMIT_MB', '512')) * 1024 * 1024

_IS_DEBUG = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')
app.config.update(
    SESSION_COOKIE_SECURE=not _IS_DEBUG,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)

GENERIC_API_ERROR = 'Something went wrong. Please try again or contact Thomas.'
GENERIC_DOWNLOAD_ERROR = 'Could not generate the file. Please try again or contact Thomas.'


def _log_exception(exc, context=''):
    import traceback
    label = f' ({context})' if context else ''
    print(f'Error{label}: {exc}')
    traceback.print_exc()


def _api_error(exc, status=500, **extra):
    _log_exception(exc)
    payload = {'error': GENERIC_API_ERROR}
    payload.update(extra)
    return jsonify(payload), status


_JSON_API_PATHS = frozenset({
    '/analyze-diff',
    '/submit-diff',
})


def _wants_json_response():
    if request.path.startswith('/api/') or request.path in _JSON_API_PATHS:
        return True
    if request.is_json:
        return True
    accept = request.accept_mimetypes.best_match(['application/json', 'text/html'])
    return accept == 'application/json'


# ── USER DEFINITIONS ────────────────────────────────────────────────────────────

USERS = {
    'thomas_ellison': {
        'display': 'Thomas Ellison',
        'role': 'admin',
        'proposal_access': 'all',
        'ppm_access': True,
        'team_view': False,
        'team_view_scope': None,
        'title': 'President',
        'email': 'thomas@purepropsolutions.com',
    },
    'tony_cumella': {
        'display': 'Tony Cumella',
        'role': 'consultant',
        'proposal_access': ['tony_cumella'],
        'ppm_access': True,
        'team_view': True,
        'team_view_scope': 'consultants',
        'title': 'VP of Sales',
        'email': 'Tony@purepropsolutions.com',
    },
    'adam_cupito': {
        'display': 'Adam Cupito',
        'role': 'consultant',
        'proposal_access': ['adam_cupito'],
        'ppm_access': True,
        'team_view': False,
        'team_view_scope': None,
        'title': 'Property Solutions Consultant',
        'email': 'Adam@purepropsolutions.com',
    },
    'rachel_farler': {
        'display': 'Rachel Farler',
        'role': 'consultant',
        'proposal_access': ['rachel_farler'],
        'ppm_access': True,
        'team_view': False,
        'team_view_scope': None,
        'title': 'Property Solutions Consultant',
        'email': 'Rachel@purepropsolutions.com',
    },
    'andy_potts': {
        'display': 'Andy Potts',
        'role': 'consultant',
        'proposal_access': ['andy_potts'],
        'ppm_access': True,
        'team_view': False,
        'team_view_scope': None,
        'title': 'Property Solutions Consultant',
        'email': 'Andy@purepropsolutions.com',
    },
    'phil_miller': {
        'display': 'Phil Miller',
        'role': 'pm',
        'proposal_access': 'all',
        'ppm_access': True,
        'team_view': False,
        'team_view_scope': None,
        'title': 'Project Manager',
        'email': 'phil@purepropsolutions.com',
    },
    'derek_kidney': {
        'display': 'Derek Kidney',
        'role': 'pm',
        'proposal_access': ['rachel_farler'],
        'ppm_access': True,
        'team_view': False,
        'team_view_scope': None,
        'title': 'Project Manager',
        'email': 'Derek@purepropsolutions.com',
    },
    'nick_triplett': {
        'display': 'Nick Triplett',
        'role': 'pm',
        'proposal_access': ['tony_cumella'],
        'ppm_access': True,
        'team_view': False,
        'team_view_scope': None,
        'title': 'Project Manager',
        'email': 'nick@purepropsolutions.com',
    },
    'trey_hollmeyer': {
        'display': 'Trey Hollmeyer',
        'role': 'pm',
        'proposal_access': 'all',
        'ppm_access': True,
        'team_view': True,
        'team_view_scope': 'pms',
        'title': 'Production Manager',
        'email': 'trey@purepropsolutions.com',
    },
    'james_boling': {
        'display': 'James Boling',
        'role': 'pm',
        'proposal_access': ['andy_potts', 'adam_cupito'],
        'ppm_access': True,
        'team_view': False,
        'team_view_scope': None,
        'title': 'Project Manager',
        'email': 'James@purepropsolutions.com',
    },
    'jordan_allen': {
        'display': 'Jordan Allen',
        'role': 'pm',
        'proposal_access': 'all',
        'ppm_access': True,
        'team_view': False,
        'team_view_scope': None,
        'title': 'Project Manager',
        'email': 'jordan@purepropsolutions.com',
    },
    'ben_ramsey': {
        'display': 'Ben Ramsey',
        'role': 'pm',
        'proposal_access': ['andy_potts'],
        'ppm_access': True,
        'team_view': False,
        'team_view_scope': None,
        'title': 'Project Manager',
        'email': 'ben@purepropsolutions.com',
    },
    'stephanie_whetstone': {
        'display': 'Stephanie Whetstone',
        'role': 'office_manager',
        'proposal_access': [],
        'ppm_access': True,
        'team_view': False,
        'team_view_scope': None,
        'title': 'Office Manager',
        'email': 'Stephanie@purepropsolutions.com',
    },
}

# Proposal numbers: {INITIALS}{YY}{XXX} — e.g. TE26001 (Thomas Ellison, 2026, #1)
PROPOSAL_NUMBER_SEQ_DIGITS = 3
PROPOSAL_NUMBER_INITIALS = {
    'thomas_ellison': 'TE',
    'tony_cumella': 'TC',
    'adam_cupito': 'AC',
    'rachel_farler': 'RF',
    'andy_potts': 'AP',
}

_CONSULTANT_KEY_ALIASES = {
    'thomas': 'thomas_ellison',
    'tony': 'tony_cumella',
    'adam': 'adam_cupito',
    'rachel': 'rachel_farler',
    'andy': 'andy_potts',
}


def _normalize_consultant_key(consultant_key):
    key = (consultant_key or '').strip()
    return _CONSULTANT_KEY_ALIASES.get(key, key)


def _proposal_initials(consultant_key):
    key = _normalize_consultant_key(consultant_key)
    initials = PROPOSAL_NUMBER_INITIALS.get(key)
    if initials:
        return initials
    user = USERS.get(key, {})
    display = user.get('display', '')
    parts = display.split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    if display:
        return display[:2].upper()
    return 'PP'


def _proposal_seq_suffix_len_ok(suffix_len):
    """Current format uses 3 digits; legacy hub entries may use 4."""
    return suffix_len in (PROPOSAL_NUMBER_SEQ_DIGITS, PROPOSAL_NUMBER_SEQ_DIGITS + 1)


def _parse_proposal_seq(raw, prefix):
    if not raw.startswith(prefix):
        return None
    suffix = raw[len(prefix):]
    if not suffix.isdigit() or not _proposal_seq_suffix_len_ok(len(suffix)):
        return None
    return int(suffix)


def _format_proposal_number(prefix, seq):
    return f"{prefix}{seq:0{PROPOSAL_NUMBER_SEQ_DIGITS}d}"


def _max_proposal_seq_from_log(cur, consultant_key, prefix):
    """Highest sequence suffix already used in proposal_log for this consultant/year."""
    cur.execute(
        '''
        SELECT proposal_number FROM proposal_log
        WHERE consultant_key = %s AND proposal_number IS NOT NULL
          AND UPPER(proposal_number) LIKE %s
        ''',
        (consultant_key, prefix + '%'),
    )
    max_seq = 0
    for row in cur.fetchall():
        num = re.sub(r'[^A-Z0-9]', '', (row[0] or '').strip().upper())
        seq = _parse_proposal_seq(num, prefix)
        if seq is not None:
            max_seq = max(max_seq, seq)
    return max_seq


def peek_next_proposal_number(consultant_key, year=None):
    """
    Suggest the next proposal number (INITIALS + 2-digit year + 3-digit seq) without
    reserving it. The sequence counter advances only on save via
    sync_proposal_number_sequence(), so edits before generate are respected.
    """
    key = _normalize_consultant_key(consultant_key)
    if key not in PROPOSAL_NUMBER_INITIALS and key not in USERS:
        return None, 'Unknown consultant'
    yr = year or datetime.now().year
    yy = yr % 100
    prefix = f"{_proposal_initials(key)}{yy:02d}"
    try:
        conn = get_db()
        if not conn:
            return None, 'Database unavailable'
        cur = conn.cursor()
        cur.execute(
            '''
            INSERT INTO proposal_number_sequence (consultant_key, seq_year, last_seq)
            VALUES (%s, %s, 0)
            ON CONFLICT (consultant_key, seq_year) DO NOTHING
            ''',
            (key, yr),
        )
        max_log = _max_proposal_seq_from_log(cur, key, prefix)
        if max_log:
            cur.execute(
                '''
                UPDATE proposal_number_sequence
                SET last_seq = GREATEST(last_seq, %s)
                WHERE consultant_key = %s AND seq_year = %s AND last_seq < %s
                ''',
                (max_log, key, yr, max_log),
            )
        cur.execute(
            '''
            SELECT last_seq FROM proposal_number_sequence
            WHERE consultant_key = %s AND seq_year = %s
            ''',
            (key, yr),
        )
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if not row:
            return None, 'Could not read proposal number sequence'
        number = _format_proposal_number(prefix, row[0] + 1)
        return number, None
    except Exception as e:
        print(f"Proposal number peek error: {e}")
        return None, 'Could not read next proposal number'


def sync_proposal_number_sequence(consultant_key, proposal_number, year=None):
    """Advance the per-consultant sequence to the saved proposal number (never backward)."""
    key = _normalize_consultant_key(consultant_key)
    raw = re.sub(r'[^A-Z0-9]', '', (proposal_number or '').upper())
    if not raw:
        return
    yr = year or datetime.now().year
    yy = yr % 100
    expected_initials = _proposal_initials(key)
    prefix = f"{expected_initials}{yy:02d}"
    seq = _parse_proposal_seq(raw, prefix)
    if seq is None:
        return
    try:
        conn = get_db()
        if not conn:
            return
        cur = conn.cursor()
        cur.execute(
            '''
            INSERT INTO proposal_number_sequence (consultant_key, seq_year, last_seq)
            VALUES (%s, %s, %s)
            ON CONFLICT (consultant_key, seq_year) DO UPDATE SET
                last_seq = GREATEST(proposal_number_sequence.last_seq, EXCLUDED.last_seq)
            ''',
            (key, yr, seq),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Proposal number sync error: {e}")


# ── BIRTHDAYS & HIRE DATES ──────────────────────────────────────────────────
TEAM_DATES = {
    'thomas_ellison': {'birthday': (10, 8),  'hire': (5, 21, 2017)},
    'tony_cumella':   {'birthday': (8, 21),  'hire': (6, 17, 2019)},
    'phil_miller':    {'birthday': (3, 2),   'hire': (2, 24, 2020)},
    'trey_hollmeyer': {'birthday': (10, 3),  'hire': (5, 14, 2018)},
    'stephanie_whetstone': {'birthday': (5, 5), 'hire': (5, 7, 2017)},
    'derek_kidney':   {'birthday': (4, 15),  'hire': (4, 26, 2021)},
    'jordan_allen':   {'birthday': (6, 26),  'hire': (9, 13, 2021)},
    'adam_cupito':    {'birthday': (6, 18),  'hire': (2, 28, 2022)},
    'ben_ramsey':     {'birthday': (8, 6),   'hire': (7, 10, 2023)},
    'andy_potts':     {'birthday': (12, 31), 'hire': (2, 24, 2025)},
    'james_boling':   {'birthday': (3, 31),  'hire': (5, 5,  2025)},
    'rachel_farler':  {'birthday': (5, 15),  'hire': (1, 5,  2026)},
    'nick_triplett':  {'birthday': (12, 23), 'hire': (5, 4,  2026)},
}

MONTH_NAMES = ['January','February','March','April','May','June',
               'July','August','September','October','November','December']

def get_date_events(user_key, is_admin=False):
    """Returns upcoming birthday/anniversary events within 3 days for this user,
    plus team events if admin."""
    from datetime import date, timedelta
    today = date.today()
    events = []

    def days_until(month, day):
        this_year = date(today.year, month, day)
        if this_year < today:
            this_year = date(today.year + 1, month, day)
        return (this_year - today).days

    def event_label(days):
        if days == 0: return 'today'
        if days == 1: return 'tomorrow'
        return f'in {days} days'

    if is_admin:
        # Admin sees everyone's upcoming events
        for key, dates in TEAM_DATES.items():
            user = USERS.get(key, {})
            first_name = user.get('display', '').split()[0]
            bday_days = days_until(*dates['birthday'])
            hire_month, hire_day, hire_year = dates['hire']
            hire_days = days_until(hire_month, hire_day)
            years = today.year - hire_year
            if bday_days <= 3:
                events.append({
                    'type': 'birthday',
                    'name': first_name,
                    'full_name': user.get('display', ''),
                    'days': bday_days,
                    'label': event_label(bday_days),
                    'date_str': f"{MONTH_NAMES[dates['birthday'][0]-1]} {dates['birthday'][1]}",
                    'message': f"🎂 Heads up — {first_name}'s birthday is {event_label(bday_days)}, {MONTH_NAMES[dates['birthday'][0]-1]} {dates['birthday'][1]}. A good excuse to say something.",
                })
            if hire_days <= 3 and years >= 1:
                events.append({
                    'type': 'anniversary',
                    'name': first_name,
                    'full_name': user.get('display', ''),
                    'days': hire_days,
                    'label': event_label(hire_days),
                    'date_str': f"{MONTH_NAMES[hire_month-1]} {hire_day}",
                    'message': f"🏆 {first_name} is hitting {years} year{'s' if years > 1 else ''} with PPS {event_label(hire_days)}. Worth acknowledging.",
                })
    else:
        # User sees their own events (must include 'days' for sort below)
        dates = TEAM_DATES.get(user_key)
        if dates:
            user = USERS.get(user_key, {})
            first_name = user.get('display', '').split()[0]
            bday_days = days_until(*dates['birthday'])
            hire_month, hire_day, hire_year = dates['hire']
            hire_days = days_until(hire_month, hire_day)
            years = today.year - hire_year
            if bday_days <= 3:
                events.append({
                    'type': 'birthday',
                    'name': first_name,
                    'full_name': user.get('display', ''),
                    'days': bday_days,
                    'label': event_label(bday_days),
                    'date_str': f"{MONTH_NAMES[dates['birthday'][0]-1]} {dates['birthday'][1]}",
                    'message': f"🎂 Your birthday is {event_label(bday_days)} — {MONTH_NAMES[dates['birthday'][0]-1]} {dates['birthday'][1]}. Hope it's a good one.",
                })
            if hire_days <= 3 and years >= 1:
                events.append({
                    'type': 'anniversary',
                    'name': first_name,
                    'full_name': user.get('display', ''),
                    'days': hire_days,
                    'label': event_label(hire_days),
                    'date_str': f"{MONTH_NAMES[hire_month-1]} {hire_day}",
                    'message': f"🏆 {years} year{'s' if years > 1 else ''} at PPS {event_label(hire_days)}. That's worth something.",
                })

    events.sort(key=lambda x: x.get('days', 999))
    return events

CONSULTANTS = {
    'tony_cumella': 'Tony Cumella',
    'adam_cupito': 'Adam Cupito',
    'rachel_farler': 'Rachel Farler',
    'andy_potts': 'Andy Potts',
}

# ── DATABASE ────────────────────────────────────────────────────────────────────

def _database_url():
    """Normalize Render/Heroku-style postgres:// URLs for psycopg2."""
    url = (DATABASE_URL or '').strip()
    if not url:
        return ''
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    # Strip query sslmode so we can control it explicitly (avoids double-setting).
    if '?' in url:
        base, qs = url.split('?', 1)
        parts = [p for p in qs.split('&') if p and not p.lower().startswith('sslmode=')]
        url = base + (('?' + '&'.join(parts)) if parts else '')
    return url


# Last connect failure (sanitized) — for /health diagnostics, not shown to end users.
_DB_LAST_ERROR = ''


def get_db():
    """Open a short-lived Postgres connection. Returns None if unavailable."""
    global _DB_LAST_ERROR
    url = _database_url()
    if not url:
        _DB_LAST_ERROR = 'DATABASE_URL not set'
        return None
    # Try common SSL modes used by Render / managed Postgres.
    last_err = None
    for sslmode in ('require', 'prefer', 'allow'):
        try:
            conn = psycopg2.connect(url, sslmode=sslmode, connect_timeout=10)
            _DB_LAST_ERROR = ''
            return conn
        except Exception as e:
            last_err = e
            continue
    msg = str(last_err) if last_err else 'unknown connect failure'
    # Never log credentials; psycopg2 errors usually omit the password.
    _DB_LAST_ERROR = msg[:240]
    print(f'get_db connect error: {_DB_LAST_ERROR}')
    return None


def init_db():
    conn = get_db()
    if not conn:
        return
    cur = conn.cursor()

    # Users table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS hub_users (
            id SERIAL PRIMARY KEY,
            user_key VARCHAR(100) UNIQUE NOT NULL,
            display_name VARCHAR(255) NOT NULL,
            password_hash VARCHAR(500) NOT NULL,
            role VARCHAR(50) NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            last_login TIMESTAMP
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS proposal_number_sequence (
            consultant_key VARCHAR(100) NOT NULL,
            seq_year INTEGER NOT NULL,
            last_seq INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (consultant_key, seq_year)
        )
    ''')

    # Proposal activity log
    cur.execute('''
        CREATE TABLE IF NOT EXISTS proposal_log (
            id SERIAL PRIMARY KEY,
            generated_by VARCHAR(100) NOT NULL,
            consultant_key VARCHAR(100) NOT NULL,
            consultant_name VARCHAR(255) NOT NULL,
            client_name VARCHAR(255),
            property_name VARCHAR(255),
            property_address VARCHAR(255),
            property_type VARCHAR(100),
            template_type VARCHAR(100),
            proposal_number VARCHAR(100),
            existing_issue TEXT,
            intended_outcome TEXT,
            scopes_selected TEXT,
            scope_notes TEXT,
            generated_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    # Add new columns if they don't exist (for existing databases)
    for col in [
        "ALTER TABLE proposal_log ADD COLUMN IF NOT EXISTS property_address VARCHAR(255)",
        "ALTER TABLE proposal_log ADD COLUMN IF NOT EXISTS proposal_number VARCHAR(100)",
        "ALTER TABLE proposal_log ADD COLUMN IF NOT EXISTS existing_issue TEXT",
        "ALTER TABLE proposal_log ADD COLUMN IF NOT EXISTS intended_outcome TEXT",
        "ALTER TABLE proposal_log ADD COLUMN IF NOT EXISTS scopes_selected TEXT",
        "ALTER TABLE proposal_log ADD COLUMN IF NOT EXISTS scope_notes TEXT",
        "ALTER TABLE proposal_log ADD COLUMN IF NOT EXISTS document_id INTEGER",
        "ALTER TABLE proposal_log ADD COLUMN IF NOT EXISTS contact_name VARCHAR(255)",
        "ALTER TABLE proposal_log ADD COLUMN IF NOT EXISTS contact_email VARCHAR(255)",
        "ALTER TABLE proposal_log ADD COLUMN IF NOT EXISTS company VARCHAR(255)",
        "ALTER TABLE proposal_log ADD COLUMN IF NOT EXISTS scope_details TEXT",
        "ALTER TABLE proposal_log ADD COLUMN IF NOT EXISTS other_scope TEXT",
        "ALTER TABLE proposal_log ADD COLUMN IF NOT EXISTS pricing_json TEXT",
        "ALTER TABLE proposal_log ADD COLUMN IF NOT EXISTS warranty_pps VARCHAR(100)",
        "ALTER TABLE proposal_log ADD COLUMN IF NOT EXISTS warranty_mfg VARCHAR(100)",
        "ALTER TABLE proposal_log ADD COLUMN IF NOT EXISTS proposal_date VARCHAR(50)",
        "ALTER TABLE proposal_log ADD COLUMN IF NOT EXISTS expiry_date VARCHAR(50)",
        "ALTER TABLE proposal_log ADD COLUMN IF NOT EXISTS contract_total VARCHAR(100)",
        "ALTER TABLE proposal_log ADD COLUMN IF NOT EXISTS scope_style VARCHAR(50)",
        "ALTER TABLE siding_estimate_log ADD COLUMN IF NOT EXISTS summary_meta VARCHAR(255)",
        "ALTER TABLE roofing_estimate_log ADD COLUMN IF NOT EXISTS summary_meta VARCHAR(255)",
        "ALTER TABLE gutter_estimate_log ADD COLUMN IF NOT EXISTS summary_meta VARCHAR(255)",
        "ALTER TABLE painting_estimate_log ADD COLUMN IF NOT EXISTS summary_meta VARCHAR(255)",
    ]:
        try:
            cur.execute(col)
        except: pass

    # Document vault — persistent file storage
    cur.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id SERIAL PRIMARY KEY,
            doc_type VARCHAR(50) NOT NULL,
            log_id INTEGER,
            user_key VARCHAR(100) NOT NULL,
            filename VARCHAR(255) NOT NULL,
            mime_type VARCHAR(100) NOT NULL,
            size_bytes INTEGER NOT NULL,
            file_data BYTEA NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_log ON documents(doc_type, log_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(user_key)")
    except: pass

    # PPM activity log
    cur.execute('''
        CREATE TABLE IF NOT EXISTS ppm_log (
            id SERIAL PRIMARY KEY,
            generated_by VARCHAR(100) NOT NULL,
            property_name VARCHAR(255),
            generated_at TIMESTAMP DEFAULT NOW()
        )
    ''')

    # Subscope log table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS subscope_log (
            id SERIAL PRIMARY KEY,
            generated_by VARCHAR(100) NOT NULL,
            property_name VARCHAR(255),
            pm_name VARCHAR(255),
            consultant_name VARCHAR(255),
            language VARCHAR(50),
            generated_at TIMESTAMP DEFAULT NOW()
        )
    ''')

    # SSO auth tokens table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS auth_tokens (
            token VARCHAR(64) PRIMARY KEY,
            user_key VARCHAR(100) NOT NULL,
            display_name VARCHAR(255) NOT NULL,
            role VARCHAR(50),
            created_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP NOT NULL,
            used BOOLEAN DEFAULT FALSE
        )
    ''')


    # Feedback table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            id SERIAL PRIMARY KEY,
            user_key VARCHAR(100) NOT NULL,
            display_name VARCHAR(255) NOT NULL,
            message TEXT NOT NULL,
            feedback_type VARCHAR(50) DEFAULT 'general',
            submitted_at TIMESTAMP DEFAULT NOW(),
            read_by_admin BOOLEAN DEFAULT FALSE
        )
    ''')

    # Proposal diffs table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS proposal_diffs (
            id SERIAL PRIMARY KEY,
            user_key VARCHAR(100) NOT NULL,
            display_name VARCHAR(255) NOT NULL,
            property_name VARCHAR(255),
            diff_analysis TEXT,
            user_notes TEXT,
            voice_recommendations TEXT,
            submitted_at TIMESTAMP DEFAULT NOW(),
            reviewed_by_admin BOOLEAN DEFAULT FALSE
        )
    ''')

    cur.execute(
        'ALTER TABLE proposal_diffs ADD COLUMN IF NOT EXISTS comparison_prompt TEXT'
    )

    # Migrate ppm_log / subscope_log metadata columns
    for col in [
        "ALTER TABLE ppm_log ADD COLUMN IF NOT EXISTS pm_key VARCHAR(100)",
        "ALTER TABLE ppm_log ADD COLUMN IF NOT EXISTS pm_name VARCHAR(255)",
        "ALTER TABLE ppm_log ADD COLUMN IF NOT EXISTS property_address VARCHAR(255)",
        "ALTER TABLE ppm_log ADD COLUMN IF NOT EXISTS client_name VARCHAR(255)",
        "ALTER TABLE ppm_log ADD COLUMN IF NOT EXISTS proposal_number VARCHAR(100)",
        "ALTER TABLE ppm_log ADD COLUMN IF NOT EXISTS total_value VARCHAR(100)",
        "ALTER TABLE ppm_log ADD COLUMN IF NOT EXISTS proposal_date VARCHAR(100)",
        "ALTER TABLE ppm_log ADD COLUMN IF NOT EXISTS proj_type VARCHAR(100)",
        "ALTER TABLE ppm_log ADD COLUMN IF NOT EXISTS scale VARCHAR(100)",
        "ALTER TABLE ppm_log ADD COLUMN IF NOT EXISTS client_type VARCHAR(100)",
        "ALTER TABLE ppm_log ADD COLUMN IF NOT EXISTS occupied VARCHAR(100)",
        "ALTER TABLE subscope_log ADD COLUMN IF NOT EXISTS property_address VARCHAR(255)",
        "ALTER TABLE subscope_log ADD COLUMN IF NOT EXISTS po_number VARCHAR(100)",
        "ALTER TABLE subscope_log ADD COLUMN IF NOT EXISTS consultant_key VARCHAR(100)",
        "ALTER TABLE subscope_log ADD COLUMN IF NOT EXISTS pm_key VARCHAR(100)",
        "ALTER TABLE subscope_log ADD COLUMN IF NOT EXISTS material_provider VARCHAR(50)",
        "ALTER TABLE subscope_log ADD COLUMN IF NOT EXISTS proposal_filename VARCHAR(255)",
        "ALTER TABLE feedback ADD COLUMN IF NOT EXISTS feedback_type VARCHAR(50) DEFAULT 'general'",
    ]:
        try:
            cur.execute(col)
        except: pass

    # Client / contact database
    cur.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255),
            company VARCHAR(255),
            property_name VARCHAR(255),
            address TEXT,
            notes TEXT,
            added_by VARCHAR(100),
            updated_at TIMESTAMP DEFAULT NOW(),
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_clients_name ON clients(LOWER(name))")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_clients_company ON clients(LOWER(company))")
    except: pass

    # Site visit log
    cur.execute('''
        CREATE TABLE IF NOT EXISTS site_visit_log (
            id SERIAL PRIMARY KEY,
            generated_by VARCHAR(100) NOT NULL,
            display_name VARCHAR(255) NOT NULL,
            property_name VARCHAR(255),
            property_address VARCHAR(255),
            visit_date VARCHAR(100),
            visit_time VARCHAR(100),
            po_number VARCHAR(100),
            trade_partner_present VARCHAR(10),
            trade_partner_company VARCHAR(255),
            crew_lead VARCHAR(255),
            crew_count VARCHAR(50),
            met_with_staff VARCHAR(10),
            staff_contact VARCHAR(255),
            topics_discussed TEXT,
            complaints_received VARCHAR(10),
            complaint_details TEXT,
            checklist JSONB,
            overall_status VARCHAR(50),
            quality_status VARCHAR(50),
            schedule_status VARCHAR(50),
            observations TEXT,
            photos_taken BOOLEAN DEFAULT FALSE,
            next_visit_date VARCHAR(100),
            generated_at TIMESTAMP DEFAULT NOW()
        )
    ''')

    # Siding estimate log
    cur.execute('''
        CREATE TABLE IF NOT EXISTS siding_estimate_log (
            id SERIAL PRIMARY KEY,
            generated_by VARCHAR(100) NOT NULL,
            display_name VARCHAR(255),
            property_name VARCHAR(255),
            property_address VARCHAR(255),
            building_count INTEGER DEFAULT 1,
            siding_type VARCHAR(100),
            job_data JSONB NOT NULL,
            generated_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    try:
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_siding_estimate_user ON siding_estimate_log(generated_by, generated_at DESC)"
        )
    except Exception:
        pass

    cur.execute('''
        CREATE TABLE IF NOT EXISTS roofing_estimate_log (
            id SERIAL PRIMARY KEY,
            generated_by VARCHAR(100) NOT NULL,
            display_name VARCHAR(255),
            property_name VARCHAR(255),
            property_address VARCHAR(255),
            report_type VARCHAR(50),
            job_data JSONB NOT NULL,
            generated_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    try:
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_roofing_estimate_user ON roofing_estimate_log(generated_by, generated_at DESC)"
        )
    except Exception:
        pass

    cur.execute('''
        CREATE TABLE IF NOT EXISTS gutter_estimate_log (
            id SERIAL PRIMARY KEY,
            generated_by VARCHAR(100) NOT NULL,
            display_name VARCHAR(255),
            property_name VARCHAR(255),
            property_address VARCHAR(255),
            gutter_lf NUMERIC,
            job_data JSONB NOT NULL,
            generated_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    try:
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_gutter_estimate_user ON gutter_estimate_log(generated_by, generated_at DESC)"
        )
    except Exception:
        pass

    cur.execute('''
        CREATE TABLE IF NOT EXISTS painting_estimate_log (
            id SERIAL PRIMARY KEY,
            generated_by VARCHAR(100) NOT NULL,
            display_name VARCHAR(255),
            property_name VARCHAR(255),
            property_address VARCHAR(255),
            line_count INTEGER,
            one_coat_bid NUMERIC,
            two_coat_bid NUMERIC,
            job_data JSONB NOT NULL,
            generated_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    try:
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_painting_estimate_user ON painting_estimate_log(generated_by, generated_at DESC)"
        )
    except Exception:
        pass

    cur.execute('''
        CREATE TABLE IF NOT EXISTS hub_settings (
            key VARCHAR(100) PRIMARY KEY,
            value JSONB NOT NULL,
            updated_at TIMESTAMP DEFAULT NOW(),
            updated_by VARCHAR(100)
        )
    ''')

    # Auth support tables
    cur.execute('''
        CREATE TABLE IF NOT EXISTS auth_codes (
            code VARCHAR(64) PRIMARY KEY,
            user_key VARCHAR(100) NOT NULL,
            display_name VARCHAR(255) NOT NULL,
            role VARCHAR(50),
            created_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP NOT NULL,
            used BOOLEAN DEFAULT FALSE
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS login_attempts (
            id SERIAL PRIMARY KEY,
            user_key VARCHAR(100) NOT NULL,
            success BOOLEAN NOT NULL,
            ip_address VARCHAR(45),
            attempted_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            token VARCHAR(64) PRIMARY KEY,
            user_key VARCHAR(100) NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP NOT NULL,
            used BOOLEAN DEFAULT FALSE
        )
    ''')
    try:
        cur.execute('ALTER TABLE hub_users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN DEFAULT FALSE')
    except Exception:
        pass
    try:
        cur.execute('ALTER TABLE hub_users ALTER COLUMN password_hash TYPE TEXT')
    except Exception:
        pass

    cur.execute('''
        CREATE TABLE IF NOT EXISTS psc_training_progress (
            id SERIAL PRIMARY KEY,
            user_key VARCHAR(100) NOT NULL,
            item_id VARCHAR(100) NOT NULL,
            completed BOOLEAN DEFAULT FALSE,
            completed_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(user_key, item_id)
        )
    ''')
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_psc_training_user ON psc_training_progress(user_key)")
    except Exception:
        pass

    cur.execute('''
        CREATE TABLE IF NOT EXISTS psc_training_notes (
            id SERIAL PRIMARY KEY,
            user_key VARCHAR(100) NOT NULL,
            week_num INTEGER NOT NULL,
            notes TEXT,
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(user_key, week_num)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS psc_training_feedback (
            id SERIAL PRIMARY KEY,
            user_key VARCHAR(100) NOT NULL,
            display_name VARCHAR(255) NOT NULL,
            week_num INTEGER,
            message TEXT NOT NULL,
            feedback_type VARCHAR(50) DEFAULT 'improvement',
            submitted_at TIMESTAMP DEFAULT NOW(),
            read_by_admin BOOLEAN DEFAULT FALSE
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS psc_training_enrollment (
            user_key VARCHAR(100) PRIMARY KEY,
            enrolled_at TIMESTAMP DEFAULT NOW(),
            enrolled_by VARCHAR(100),
            manager_key VARCHAR(100) NOT NULL DEFAULT 'tony_cumella',
            target_weeks INTEGER DEFAULT 12,
            last_activity_at TIMESTAMP,
            graduated_at TIMESTAMP,
            active BOOLEAN DEFAULT TRUE
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS psc_training_notifications (
            user_key VARCHAR(100) NOT NULL,
            notification_type VARCHAR(50) NOT NULL,
            week_num INTEGER NOT NULL DEFAULT -1,
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (user_key, notification_type, week_num)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS psc_training_manager_signoffs (
            user_key VARCHAR(100) NOT NULL,
            week_num INTEGER NOT NULL,
            signed_by VARCHAR(100) NOT NULL,
            signed_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (user_key, week_num)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS psc_roleplay_sessions (
            id SERIAL PRIMARY KEY,
            user_key VARCHAR(100) NOT NULL,
            scenario_id VARCHAR(100) NOT NULL,
            transcript TEXT NOT NULL,
            feedback TEXT NOT NULL,
            overall REAL NOT NULL,
            result VARCHAR(32) NOT NULL,
            turn_count INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS psc_roleplay_daily_usage (
            user_key VARCHAR(100) NOT NULL,
            usage_date DATE NOT NULL DEFAULT CURRENT_DATE,
            turn_count INTEGER NOT NULL DEFAULT 0,
            grade_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_key, usage_date)
        )
    ''')
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_roleplay_sessions_user ON psc_roleplay_sessions(user_key)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_roleplay_sessions_created ON psc_roleplay_sessions(created_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_psc_training_notes_user ON psc_training_notes(user_key)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_psc_training_feedback_time ON psc_training_feedback(submitted_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_psc_training_enrollment_active ON psc_training_enrollment(active)")
    except Exception:
        pass

    # PM training (mirror of PSC — separate item-id namespace)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS pm_training_progress (
            id SERIAL PRIMARY KEY,
            user_key VARCHAR(100) NOT NULL,
            item_id VARCHAR(100) NOT NULL,
            completed BOOLEAN DEFAULT FALSE,
            completed_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(user_key, item_id)
        )
    ''')
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pm_training_user ON pm_training_progress(user_key)")
    except Exception:
        pass
    cur.execute('''
        CREATE TABLE IF NOT EXISTS pm_training_notes (
            id SERIAL PRIMARY KEY,
            user_key VARCHAR(100) NOT NULL,
            week_num INTEGER NOT NULL,
            notes TEXT,
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(user_key, week_num)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS pm_training_feedback (
            id SERIAL PRIMARY KEY,
            user_key VARCHAR(100) NOT NULL,
            display_name VARCHAR(255) NOT NULL,
            week_num INTEGER,
            message TEXT NOT NULL,
            feedback_type VARCHAR(50) DEFAULT 'improvement',
            submitted_at TIMESTAMP DEFAULT NOW(),
            read_by_admin BOOLEAN DEFAULT FALSE
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS pm_training_enrollment (
            user_key VARCHAR(100) PRIMARY KEY,
            enrolled_at TIMESTAMP DEFAULT NOW(),
            enrolled_by VARCHAR(100),
            manager_key VARCHAR(100) NOT NULL DEFAULT 'trey_hollmeyer',
            target_weeks INTEGER DEFAULT 4,
            last_activity_at TIMESTAMP,
            graduated_at TIMESTAMP,
            active BOOLEAN DEFAULT TRUE
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS pm_training_manager_signoffs (
            user_key VARCHAR(100) NOT NULL,
            week_num INTEGER NOT NULL,
            signed_by VARCHAR(100) NOT NULL,
            signed_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (user_key, week_num)
        )
    ''')

    ask_pps.init_tables(cur)

    # Seed users with default password if configured
    default_password = os.environ.get('DEFAULT_PASSWORD', '').strip()
    if default_password:
        for key, user in USERS.items():
            cur.execute('SELECT id FROM hub_users WHERE user_key = %s', (key,))
            if not cur.fetchone():
                hashed = generate_password_hash(default_password)
                cur.execute(
                    '''INSERT INTO hub_users
                       (user_key, display_name, password_hash, role, must_change_password)
                       VALUES (%s, %s, %s, %s, TRUE)''',
                    (key, user['display'], hashed, user['role'])
                )

    # Backfill last_login from tool activity where logs are more recent
    try:
        cur.execute('''
            UPDATE hub_users u
            SET last_login = activity.last_seen
            FROM (
                SELECT user_key, MAX(last_seen) AS last_seen
                FROM (
                    SELECT generated_by AS user_key, MAX(generated_at) AS last_seen
                    FROM proposal_log GROUP BY generated_by
                    UNION ALL
                    SELECT generated_by, MAX(generated_at) FROM ppm_log GROUP BY generated_by
                    UNION ALL
                    SELECT generated_by, MAX(generated_at) FROM subscope_log GROUP BY generated_by
                    UNION ALL
                    SELECT generated_by, MAX(generated_at) FROM site_visit_log GROUP BY generated_by
                ) combined
                GROUP BY user_key
            ) activity
            WHERE u.user_key = activity.user_key
              AND (u.last_login IS NULL OR u.last_login < activity.last_seen)
        ''')
    except Exception as e:
        print(f"last_login backfill skipped: {e}")

    conn.commit()
    cur.close()
    conn.close()


_db_startup_lock = threading.Lock()
_db_startup_done = False


def _run_db_startup():
    """Run migrations once — gunicorn imports app in every worker."""
    global _db_startup_done
    with _db_startup_lock:
        if _db_startup_done:
            return
        try:
            init_db()
        except Exception as e:
            print(f"DB init error: {e}")
        try:
            _conn = get_db()
            if _conn:
                _cur = _conn.cursor()
                _cur.execute('''
                    CREATE TABLE IF NOT EXISTS auth_tokens (
                        token VARCHAR(64) PRIMARY KEY,
                        user_key VARCHAR(100) NOT NULL,
                        display_name VARCHAR(255) NOT NULL,
                        role VARCHAR(50),
                        created_at TIMESTAMP DEFAULT NOW(),
                        expires_at TIMESTAMP NOT NULL,
                        used BOOLEAN DEFAULT FALSE
                    )
                ''')
                _conn.commit()
                _cur.close()
                _conn.close()
                print("auth_tokens table ready")
        except Exception as _e:
            print(f"auth_tokens migration error: {_e}")
        _db_startup_done = True


_run_db_startup()


# ── HELPERS ─────────────────────────────────────────────────────────────────────

def get_current_user():
    return session.get('user_key')


def require_login(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_key'):
            # Prefer a clean relative next so mobile Safari doesn't loop on full
            # auth URLs (login?next=login?next=…).
            nxt = safe_next_url(request.full_path if request.query_string else request.path)
            if nxt:
                return redirect(url_for('login', next=nxt))
            return redirect(url_for('login'))
        if session.get('must_change_password') and request.endpoint not in ('change_password', 'logout'):
            return redirect(url_for('change_password'))
        return f(*args, **kwargs)
    return decorated


def require_admin(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_key') or session.get('role') != 'admin':
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


def _runway_share_access_granted():
    """Optional guest link — only when both SHARE token and PUBLIC flag are on.

    Route Lab is a private experiment for the owner (not Hub teammates like Ben).
    Guest links are opt-in via env, not the default.
    """
    if not RUNWAY_PUBLIC_ACCESS or not RUNWAY_SHARE_TOKEN:
        return False
    token = (request.args.get('access') or '').strip()
    if token and token == RUNWAY_SHARE_TOKEN:
        session['runway_guest'] = True
        return True
    return bool(session.get('runway_guest'))


def require_runway_access(f):
    """Route Lab: owner only (or explicit public/share env for solo testing)."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        # Owner always wins when logged in
        if session.get('user_key') == RUNWAY_OWNER:
            return f(*args, **kwargs)
        # Optional solo public / share — never grant other Hub users
        if RUNWAY_PUBLIC_ACCESS and _runway_share_access_granted():
            return f(*args, **kwargs)
        if RUNWAY_PUBLIC_ACCESS and not RUNWAY_SHARE_TOKEN:
            # Fully public only when intentionally enabled without a token
            return f(*args, **kwargs)
        if not session.get('user_key'):
            return redirect(url_for('login', next=request.url))
        # Logged-in Hub users who are not the owner (e.g. Ben) → dashboard only
        return redirect(url_for('dashboard'))
    return decorated


# Back-compat alias
require_runway_owner = require_runway_access


def get_user_proposal_access(user_key):
    user = USERS.get(user_key, {})
    access = user.get('proposal_access', [])
    if access == 'all':
        return list(CONSULTANTS.keys())
    return access


def get_recent_proposals(user_key, limit=5):
    try:
        conn = get_db()
        if not conn:
            return []
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('''
            SELECT * FROM proposal_log
            WHERE generated_by = %s
            ORDER BY generated_at DESC LIMIT %s
        ''', (user_key, limit))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except:
        return []


def get_recent_ppms(user_key, limit=5):
    try:
        conn = get_db()
        if not conn:
            return []
        user_def = USERS.get(user_key, {})
        cur = conn.cursor(cursor_factory=RealDictCursor)
        if user_def.get('role') in ('pm', 'admin'):
            cur.execute('''
                SELECT * FROM ppm_log
                WHERE generated_by = %s OR pm_key = %s
                ORDER BY generated_at DESC LIMIT %s
            ''', (user_key, user_key, limit))
        else:
            cur.execute('''
                SELECT * FROM ppm_log
                WHERE generated_by = %s
                ORDER BY generated_at DESC LIMIT %s
            ''', (user_key, limit))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except:
        return []


def get_profile_result(user_key):
    user = USERS.get(user_key, {})
    display_name = user.get('display', '')
    try:
        conn = get_db()
        if not conn:
            return None
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('''
            SELECT * FROM profile_results
            WHERE LOWER(name) = LOWER(%s)
            ORDER BY taken_date DESC LIMIT 1
        ''', (display_name,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row
    except:
        return None


def get_psc_training_progress(user_key):
    """Return {item_id: True} for completed training items."""
    progress = {}
    try:
        conn = get_db()
        if not conn:
            return progress
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            'SELECT item_id FROM psc_training_progress WHERE user_key = %s AND completed = TRUE',
            (user_key,),
        )
        for row in cur.fetchall():
            progress[row['item_id']] = True
        cur.close()
        conn.close()
    except Exception as e:
        print(f"PSC training progress read error: {e}")
    return progress


def _psc_accountability_recipients():
    """President and PSC training manager — accountability email recipients."""
    recipients = []
    for key in ('thomas_ellison', PSC_TRAINING_MANAGER):
        email = (USERS.get(key, {}).get('email') or '').strip()
        if email and email.lower() not in {r.lower() for r in recipients}:
            recipients.append(email)
    return recipients


def _send_psc_accountability_email(subject, text_body, html_body=None):
    """Email President and training manager about PSC onboarding events."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    recipients = _psc_accountability_recipients()
    if not recipients:
        print(f"PSC accountability (no recipients): {subject}\n{text_body}")
        return False

    smtp_host = os.environ.get('SMTP_HOST', '')
    smtp_user = os.environ.get('SMTP_USER', '')
    smtp_pass = os.environ.get('SMTP_PASS', '')
    if not smtp_host:
        print(f"PSC accountability email:\nSubject: {subject}\nTo: {', '.join(recipients)}\n{text_body}")
        return False

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = smtp_user
        msg['To'] = ', '.join(recipients)
        msg.attach(MIMEText(text_body, 'plain'))
        if html_body:
            msg.attach(MIMEText(html_body, 'html'))
        with smtplib.SMTP_SSL(smtp_host, 465, timeout=30) as s:
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
        return True
    except Exception as e:
        print(f"PSC accountability email failed: {e}")
        return False


def _psc_week_labels():
    onboarding, weeks, _, _, _ = get_training_curriculum()
    labels = {0: onboarding.get('title', 'Week 0 · PPS Foundations')}
    for w in weeks:
        labels[w['week']] = f"Week {w['week']} · {w['topic']}"
    return labels


def _psc_week_trainee_complete(progress, week_map):
    """Return {week_num: bool} for whether the trainee finished every item in that week."""
    status = {}
    for week_num, ids in week_map.items():
        if not ids:
            status[week_num] = False
            continue
        done = sum(1 for item_id in ids if progress.get(item_id))
        status[week_num] = done == len(ids)
    return status


def get_psc_manager_signoffs(user_key):
    """Return {week_num: {signed_by, signed_at, signed_by_display}}."""
    signoffs = {}
    try:
        conn = get_db()
        if not conn:
            return signoffs
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            'SELECT week_num, signed_by, signed_at FROM psc_training_manager_signoffs WHERE user_key = %s',
            (user_key,),
        )
        for row in cur.fetchall():
            signer = row['signed_by']
            signoffs[row['week_num']] = {
                'signed_by': signer,
                'signed_at': row['signed_at'],
                'signed_by_display': USERS.get(signer, {}).get('display', signer),
            }
        cur.close()
        conn.close()
    except Exception as e:
        print(f"PSC manager signoffs read error: {e}")
    return signoffs


def _psc_week_checkin_questions():
    onboarding, weeks, _, _, _ = get_training_curriculum()
    questions = {}
    if onboarding.get('manager_checkin'):
        questions[0] = onboarding['manager_checkin']
    for w in weeks:
        if w.get('manager_checkin'):
            questions[w['week']] = w['manager_checkin']
    return questions


def manager_signoff_psc_week(trainee_key, week_num, signed_by):
    """Manager verifies a week after the trainee completes all items."""
    week_map = _psc_week_item_ids()
    week_num = int(week_num)
    if week_num not in week_map:
        return False, 'Invalid week'
    progress = get_psc_training_progress(trainee_key)
    if not _psc_week_trainee_complete(progress, week_map).get(week_num):
        return False, 'Trainee has not completed all items for this week yet'
    if not is_psc_training_enrolled(trainee_key):
        return False, 'Trainee is not actively enrolled'
    try:
        conn = get_db()
        if not conn:
            return False, 'Database unavailable'
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO psc_training_manager_signoffs (user_key, week_num, signed_by, signed_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (user_key, week_num)
            DO UPDATE SET signed_by = EXCLUDED.signed_by, signed_at = NOW()
        ''', (trainee_key, week_num, signed_by))
        conn.commit()
        cur.close()
        conn.close()
        touch_psc_training_activity(trainee_key)
        _notify_psc_week_signed_off(trainee_key, week_num, signed_by)
        return True, None
    except Exception as e:
        print(f"PSC manager signoff error: {e}")
        return False, str(e)


def revoke_psc_manager_signoff(trainee_key, week_num):
    try:
        conn = get_db()
        if not conn:
            return False
        cur = conn.cursor()
        cur.execute(
            'DELETE FROM psc_training_manager_signoffs WHERE user_key = %s AND week_num = %s',
            (trainee_key, int(week_num)),
        )
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"PSC signoff revoke error: {e}")
        return False


def _psc_week_notification_sent(user_key, week_num):
    try:
        conn = get_db()
        if not conn:
            return False
        cur = conn.cursor()
        cur.execute('''
            SELECT 1 FROM psc_training_notifications
            WHERE user_key = %s AND notification_type = %s AND week_num = %s
        ''', (user_key, 'week_complete', week_num))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return bool(row)
    except Exception:
        return False


def _record_psc_week_notification(user_key, week_num):
    try:
        conn = get_db()
        if not conn:
            return False
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO psc_training_notifications (user_key, notification_type, week_num)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_key, notification_type, week_num) DO NOTHING
        ''', (user_key, 'week_complete', week_num))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"PSC week notification record error: {e}")
        return False


def _notify_psc_week_signed_off(trainee_key, week_num, signed_by):
    """Email accountability owners when a manager officially signs off a week."""
    from html import escape

    if _psc_week_notification_sent(trainee_key, week_num):
        return
    labels = _psc_week_labels()
    checkins = _psc_week_checkin_questions()
    display = USERS.get(trainee_key, {}).get('display', trainee_key)
    signer = USERS.get(signed_by, {}).get('display', signed_by)
    stats = compute_psc_training_stats(trainee_key)
    oversight_url = f"{HUB_PUBLIC_URL.rstrip('/')}/psc-training/oversight"
    label = labels.get(week_num, f'Week {week_num}')
    checkin = checkins.get(week_num, '')
    subject = f'PSC Training — {display} completed {label} (manager sign-off)'
    text_body = (
        f'{signer} signed off {label} for {display}.\n\n'
        f'Manager check-in: {checkin}\n\n'
        f'Overall progress: {stats["pct"]}% ({stats["done"]} / {stats["total"]} items)\n\n'
        f'Review progress: {oversight_url}'
    )
    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;">
      <div style="background:#004C8C;padding:18px 22px;border-radius:8px 8px 0 0;">
        <p style="color:white;font-size:17px;font-weight:600;margin:0;">PSC Training — Week Signed Off</p>
      </div>
      <div style="background:#f8fafc;padding:22px;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;">
        <p style="color:#334155;font-size:15px;margin:0 0 12px;">
          <strong>{signer}</strong> signed off <strong>{label}</strong> for <strong>{display}</strong>.
        </p>
        <p style="color:#64748b;font-size:14px;margin:0 0 12px;"><strong>Check-in covered:</strong> {escape(checkin)}</p>
        <p style="color:#64748b;font-size:14px;margin:0 0 16px;">
          Overall progress: {stats['pct']}% ({stats['done']} / {stats['total']} items)
        </p>
        <p style="margin:0;">
          <a href="{oversight_url}" style="color:#004C8C;font-weight:600;">Open PSC Accountability dashboard →</a>
        </p>
      </div>
    </div>
    """
    if _send_psc_accountability_email(subject, text_body, html_body):
        _record_psc_week_notification(trainee_key, week_num)


def _notify_psc_training_feedback(user_key, display_name, message, week_num=None):
    """Email accountability owners when a trainee submits module feedback."""
    from html import escape

    labels = _psc_week_labels()
    if week_num is None or week_num == '':
        week_label = 'General — whole module'
    else:
        week_label = labels.get(int(week_num), f'Week {week_num}')
    oversight_url = f"{HUB_PUBLIC_URL.rstrip('/')}/psc-training/oversight"
    subject = f'PSC Training Feedback — {display_name}'
    text_body = (
        f'New PSC training feedback from {display_name}\n'
        f'Week: {week_label}\n\n'
        f'{message.strip()}\n\n'
        f'Review in hub: {oversight_url}'
    )
    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;">
      <div style="background:#004C8C;padding:18px 22px;border-radius:8px 8px 0 0;">
        <p style="color:white;font-size:17px;font-weight:600;margin:0;">PSC Training Feedback</p>
      </div>
      <div style="background:#f8fafc;padding:22px;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;">
        <p style="color:#334155;font-size:14px;margin:0 0 8px;"><strong>From:</strong> {display_name}</p>
        <p style="color:#334155;font-size:14px;margin:0 0 16px;"><strong>Week:</strong> {week_label}</p>
        <div style="background:white;border:1px solid #e2e8f0;border-radius:8px;padding:14px;color:#334155;font-size:14px;line-height:1.55;white-space:pre-wrap;">{escape(message.strip())}</div>
        <p style="margin:16px 0 0;">
          <a href="{oversight_url}" style="color:#004C8C;font-weight:600;">Open PSC Accountability dashboard →</a>
        </p>
      </div>
    </div>
    """
    _send_psc_accountability_email(subject, text_body, html_body)


def save_psc_training_progress(user_key, progress_dict):
    """Upsert completion state for training items."""
    if not progress_dict or not isinstance(progress_dict, dict):
        return False
    valid_ids = set(get_all_item_ids())
    try:
        conn = get_db()
        if not conn:
            return False
        cur = conn.cursor()
        for item_id, completed in progress_dict.items():
            if item_id not in valid_ids:
                continue
            if completed:
                cur.execute('''
                    INSERT INTO psc_training_progress (user_key, item_id, completed, completed_at, updated_at)
                    VALUES (%s, %s, TRUE, NOW(), NOW())
                    ON CONFLICT (user_key, item_id)
                    DO UPDATE SET completed = TRUE, completed_at = NOW(), updated_at = NOW()
                ''', (user_key, item_id))
            else:
                cur.execute('''
                    INSERT INTO psc_training_progress (user_key, item_id, completed, completed_at, updated_at)
                    VALUES (%s, %s, FALSE, NULL, NOW())
                    ON CONFLICT (user_key, item_id)
                    DO UPDATE SET completed = FALSE, completed_at = NULL, updated_at = NOW()
                ''', (user_key, item_id))
        conn.commit()
        cur.close()
        conn.close()
        touch_psc_training_activity(user_key)
        return True
    except Exception as e:
        print(f"PSC training progress save error: {e}")
        return False


def can_psc_training_oversight(user_key):
    """President (admin) and VP Sales track enrolled trainee progress."""
    user = USERS.get(user_key, {})
    if user.get('role') == 'admin':
        return True
    return user_key == PSC_TRAINING_MANAGER


def is_psc_training_enrolled(user_key):
    """Active enrollment — enrolled consultants (and admin self-preview) see the training module."""
    role = USERS.get(user_key, {}).get('role')
    if role not in ('consultant', 'admin'):
        return False
    try:
        conn = get_db()
        if not conn:
            return False
        cur = conn.cursor()
        cur.execute(
            'SELECT 1 FROM psc_training_enrollment WHERE user_key = %s AND active = TRUE AND graduated_at IS NULL',
            (user_key,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return bool(row)
    except Exception as e:
        print(f"PSC enrollment check error: {e}")
        return False


def get_psc_enrollment(user_key):
    try:
        conn = get_db()
        if not conn:
            return None
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('SELECT * FROM psc_training_enrollment WHERE user_key = %s', (user_key,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row
    except Exception:
        return None


def list_psc_enrolled_trainees():
    rows = []
    try:
        conn = get_db()
        if not conn:
            return rows
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('''
            SELECT * FROM psc_training_enrollment
            WHERE active = TRUE AND graduated_at IS NULL
            ORDER BY enrolled_at DESC
        ''')
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"PSC enrollment list error: {e}")
    result = []
    for row in rows:
        key = row['user_key']
        u = USERS.get(key, {})
        result.append({
            **dict(row),
            'display': u.get('display', row.get('display_name') or key),
        })
    return result


def enroll_psc_trainee(user_key, enrolled_by, manager_key=None):
    user = USERS.get(user_key, {})
    role = user.get('role')
    if role == 'consultant':
        pass
    elif role == 'admin' and user_key == enrolled_by:
        pass  # President previewing the trainee experience
    else:
        return False, 'User cannot be enrolled in PSC training'
    mgr = manager_key or PSC_TRAINING_MANAGER
    try:
        conn = get_db()
        if not conn:
            return False, 'Database unavailable'
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO psc_training_enrollment
            (user_key, enrolled_by, manager_key, enrolled_at, active, graduated_at, last_activity_at)
            VALUES (%s, %s, %s, NOW(), TRUE, NULL, NOW())
            ON CONFLICT (user_key) DO UPDATE SET
                enrolled_by = EXCLUDED.enrolled_by,
                manager_key = EXCLUDED.manager_key,
                enrolled_at = NOW(),
                active = TRUE,
                graduated_at = NULL,
                last_activity_at = NOW()
        ''', (user_key, enrolled_by, mgr))
        conn.commit()
        cur.close()
        conn.close()
        return True, None
    except Exception as e:
        print(f"PSC enroll error: {e}")
        return False, str(e)


def graduate_psc_trainee(user_key):
    try:
        conn = get_db()
        if not conn:
            return False
        cur = conn.cursor()
        cur.execute('''
            UPDATE psc_training_enrollment
            SET graduated_at = NOW(), active = FALSE, last_activity_at = NOW()
            WHERE user_key = %s
        ''', (user_key,))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"PSC graduate error: {e}")
        return False


def unenroll_psc_trainee(user_key):
    try:
        conn = get_db()
        if not conn:
            return False
        cur = conn.cursor()
        cur.execute(
            'UPDATE psc_training_enrollment SET active = FALSE WHERE user_key = %s',
            (user_key,),
        )
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"PSC unenroll error: {e}")
        return False


def touch_psc_training_activity(user_key):
    try:
        conn = get_db()
        if not conn:
            return
        cur = conn.cursor()
        cur.execute(
            'UPDATE psc_training_enrollment SET last_activity_at = NOW() WHERE user_key = %s AND active = TRUE',
            (user_key,),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass


def get_psc_training_notes(user_key):
    """Return {week_num: notes_text} for a trainee."""
    notes = {}
    try:
        conn = get_db()
        if not conn:
            return notes
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            'SELECT week_num, notes FROM psc_training_notes WHERE user_key = %s',
            (user_key,),
        )
        for row in cur.fetchall():
            notes[row['week_num']] = row['notes'] or ''
        cur.close()
        conn.close()
    except Exception as e:
        print(f"PSC training notes read error: {e}")
    return notes


def save_psc_training_notes(user_key, week_num, notes_text):
    try:
        conn = get_db()
        if not conn:
            return False
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO psc_training_notes (user_key, week_num, notes, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (user_key, week_num)
            DO UPDATE SET notes = EXCLUDED.notes, updated_at = NOW()
        ''', (user_key, int(week_num), notes_text or ''))
        conn.commit()
        cur.close()
        conn.close()
        touch_psc_training_activity(user_key)
        return True
    except Exception as e:
        print(f"PSC training notes save error: {e}")
        return False


def submit_psc_training_feedback(user_key, display_name, message, week_num=None, feedback_type='improvement'):
    if not message or not message.strip():
        return False
    try:
        conn = get_db()
        if not conn:
            return False
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO psc_training_feedback
            (user_key, display_name, week_num, message, feedback_type)
            VALUES (%s, %s, %s, %s, %s)
        ''', (user_key, display_name, week_num, message.strip(), feedback_type))
        conn.commit()
        cur.close()
        conn.close()
        _notify_psc_training_feedback(user_key, display_name, message, week_num)
        return True
    except Exception as e:
        print(f"PSC training feedback error: {e}")
        return False


def _psc_week_item_ids():
    """Map week number -> list of trainee item IDs for that week."""
    onboarding, weeks, core_values, sales_training, company_operations = get_training_curriculum()
    result = {0: []}

    def collect(week_data):
        ids = []
        for v in week_data.get('videos', []):
            ids.append(v['id'])
        for s in week_data.get('shadowing', []):
            ids.append(s['id'] if isinstance(s, dict) else s)
        for a in week_data.get('additional', []):
            ids.append(a['id'])
        for f in week_data.get('pps_focus', []):
            ids.append(f['id'])
        if week_data.get('book_id'):
            ids.append(week_data['book_id'])
        return ids

    ops_by_week = {}
    for module in company_operations['modules']:
        week_num = module.get('assigned_week', 0)
        ops_by_week.setdefault(week_num, []).extend(item['id'] for item in module['items'])

    result[0] = collect(onboarding) + ops_by_week.get(0, [])
    for section in core_values['sections']:
        for act in section.get('activities', []):
            result[0].append(act['id'])
    for module in sales_training['modules']:
        for item in module['items']:
            result[0].append(item['id'])
    for w in weeks:
        week_num = w['week']
        result[week_num] = collect(w) + ops_by_week.get(week_num, [])
    return result


def compute_psc_training_stats(user_key):
    """Overall and per-week completion stats."""
    progress = get_psc_training_progress(user_key)
    week_map = _psc_week_item_ids()
    signoffs = get_psc_manager_signoffs(user_key)
    checkins = _psc_week_checkin_questions()
    total = count_trackable_items()
    done = sum(1 for i in get_all_item_ids() if progress.get(i))
    week_pcts = []
    for week_num in sorted(week_map.keys()):
        ids = week_map[week_num]
        w_done = sum(1 for i in ids if progress.get(i))
        w_total = len(ids)
        trainee_pct = round((w_done / w_total) * 100) if w_total else 0
        manager_signed = week_num in signoffs
        entry = {
            'week': week_num,
            'done': w_done,
            'total': w_total,
            'trainee_pct': trainee_pct,
            'manager_signed': manager_signed,
            'ready_for_signoff': trainee_pct == 100 and not manager_signed,
            'pct': 100 if manager_signed and trainee_pct == 100 else trainee_pct,
            'checkin': checkins.get(week_num, ''),
        }
        if manager_signed:
            entry['signed_by_display'] = signoffs[week_num]['signed_by_display']
            entry['signed_at'] = signoffs[week_num]['signed_at']
        week_pcts.append(entry)
    pct = round((done / total) * 100) if total else 0
    signed_weeks = sum(1 for w in week_pcts if w['manager_signed'] and w['trainee_pct'] == 100)
    return {
        'done': done,
        'total': total,
        'pct': pct,
        'week_pcts': week_pcts,
        'signed_weeks': signed_weeks,
        'total_weeks': len(week_map),
    }


def get_pm_training_progress(user_key):
    """Return {item_id: True} for completed PM training items."""
    progress = {}
    try:
        conn = get_db()
        if not conn:
            return progress
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            'SELECT item_id FROM pm_training_progress WHERE user_key = %s AND completed = TRUE',
            (user_key,),
        )
        for row in cur.fetchall():
            progress[row['item_id']] = True
        cur.close()
        conn.close()
    except Exception as e:
        print(f"PM training progress read error: {e}")
    return progress


def save_pm_training_progress(user_key, progress_dict):
    """Upsert completed flags. Open to all logged-in users (under-construction rollout)."""
    if not isinstance(progress_dict, dict):
        return False
    try:
        conn = get_db()
        if not conn:
            return False
        cur = conn.cursor()
        for item_id, completed in progress_dict.items():
            item_id = str(item_id)[:100]
            done = bool(completed)
            cur.execute('''
                INSERT INTO pm_training_progress (user_key, item_id, completed, completed_at, updated_at)
                VALUES (%s, %s, %s, CASE WHEN %s THEN NOW() ELSE NULL END, NOW())
                ON CONFLICT (user_key, item_id)
                DO UPDATE SET
                    completed = EXCLUDED.completed,
                    completed_at = CASE WHEN EXCLUDED.completed THEN COALESCE(pm_training_progress.completed_at, NOW()) ELSE NULL END,
                    updated_at = NOW()
            ''', (user_key, item_id, done, done))
        conn.commit()
        cur.close()
        conn.close()
        touch_pm_training_activity(user_key)
        return True
    except Exception as e:
        print(f"PM training progress save error: {e}")
        return False


def can_pm_training_oversight(user_key):
    """Admin and Production Manager (Trey) track PM training progress."""
    user = USERS.get(user_key, {})
    if user.get('role') == 'admin':
        return True
    return user_key == PM_TRAINING_MANAGER


def is_pm_training_enrolled(user_key):
    """Optional formal enrollment. Module is open to everyone; enrollment is for accountability tracking."""
    try:
        conn = get_db()
        if not conn:
            return False
        cur = conn.cursor()
        cur.execute(
            'SELECT 1 FROM pm_training_enrollment WHERE user_key = %s AND active = TRUE AND graduated_at IS NULL',
            (user_key,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return bool(row)
    except Exception as e:
        print(f"PM enrollment check error: {e}")
        return False


def get_pm_enrollment(user_key):
    try:
        conn = get_db()
        if not conn:
            return None
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('SELECT * FROM pm_training_enrollment WHERE user_key = %s', (user_key,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row
    except Exception:
        return None


def list_pm_enrolled_trainees():
    rows = []
    try:
        conn = get_db()
        if not conn:
            return rows
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('''
            SELECT * FROM pm_training_enrollment
            WHERE active = TRUE AND graduated_at IS NULL
            ORDER BY enrolled_at DESC
        ''')
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"PM enrollment list error: {e}")
    result = []
    for row in rows:
        key = row['user_key']
        u = USERS.get(key, {})
        result.append({
            **dict(row),
            'display': u.get('display', row.get('display_name') or key),
        })
    return result


def enroll_pm_trainee(user_key, enrolled_by, manager_key=None):
    if user_key not in USERS:
        return False, 'Unknown user'
    mgr = manager_key or PM_TRAINING_MANAGER
    try:
        conn = get_db()
        if not conn:
            return False, 'Database unavailable'
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO pm_training_enrollment
            (user_key, enrolled_by, manager_key, enrolled_at, active, graduated_at, last_activity_at, target_weeks)
            VALUES (%s, %s, %s, NOW(), TRUE, NULL, NOW(), 4)
            ON CONFLICT (user_key) DO UPDATE SET
                enrolled_by = EXCLUDED.enrolled_by,
                manager_key = EXCLUDED.manager_key,
                enrolled_at = NOW(),
                active = TRUE,
                graduated_at = NULL,
                last_activity_at = NOW(),
                target_weeks = 4
        ''', (user_key, enrolled_by, mgr))
        conn.commit()
        cur.close()
        conn.close()
        return True, None
    except Exception as e:
        print(f"PM enroll error: {e}")
        return False, str(e)


def graduate_pm_trainee(user_key):
    try:
        conn = get_db()
        if not conn:
            return False
        cur = conn.cursor()
        cur.execute('''
            UPDATE pm_training_enrollment
            SET graduated_at = NOW(), active = FALSE, last_activity_at = NOW()
            WHERE user_key = %s
        ''', (user_key,))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"PM graduate error: {e}")
        return False


def unenroll_pm_trainee(user_key):
    try:
        conn = get_db()
        if not conn:
            return False
        cur = conn.cursor()
        cur.execute(
            'UPDATE pm_training_enrollment SET active = FALSE WHERE user_key = %s',
            (user_key,),
        )
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"PM unenroll error: {e}")
        return False


def touch_pm_training_activity(user_key):
    try:
        conn = get_db()
        if not conn:
            return
        cur = conn.cursor()
        cur.execute(
            'UPDATE pm_training_enrollment SET last_activity_at = NOW() WHERE user_key = %s AND active = TRUE',
            (user_key,),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        pass


def get_pm_training_notes(user_key):
    notes = {}
    try:
        conn = get_db()
        if not conn:
            return notes
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            'SELECT week_num, notes FROM pm_training_notes WHERE user_key = %s',
            (user_key,),
        )
        for row in cur.fetchall():
            notes[row['week_num']] = row['notes'] or ''
        cur.close()
        conn.close()
    except Exception as e:
        print(f"PM training notes read error: {e}")
    return notes


def save_pm_training_notes(user_key, week_num, notes_text):
    try:
        conn = get_db()
        if not conn:
            return False
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO pm_training_notes (user_key, week_num, notes, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (user_key, week_num)
            DO UPDATE SET notes = EXCLUDED.notes, updated_at = NOW()
        ''', (user_key, int(week_num), notes_text or ''))
        conn.commit()
        cur.close()
        conn.close()
        touch_pm_training_activity(user_key)
        return True
    except Exception as e:
        print(f"PM training notes save error: {e}")
        return False


def submit_pm_training_feedback(user_key, display_name, message, week_num=None, feedback_type='improvement'):
    if not message or not message.strip():
        return False
    try:
        conn = get_db()
        if not conn:
            return False
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO pm_training_feedback
            (user_key, display_name, week_num, message, feedback_type)
            VALUES (%s, %s, %s, %s, %s)
        ''', (user_key, display_name, week_num, message.strip(), feedback_type))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"PM training feedback error: {e}")
        return False


def get_pm_manager_signoffs(user_key):
    signoffs = {}
    try:
        conn = get_db()
        if not conn:
            return signoffs
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            'SELECT week_num, signed_by, signed_at FROM pm_training_manager_signoffs WHERE user_key = %s',
            (user_key,),
        )
        for row in cur.fetchall():
            signer = row['signed_by']
            signoffs[row['week_num']] = {
                'signed_by': signer,
                'signed_at': row['signed_at'],
                'signed_by_display': USERS.get(signer, {}).get('display', signer),
            }
        cur.close()
        conn.close()
    except Exception as e:
        print(f"PM manager signoffs read error: {e}")
    return signoffs


def compute_pm_training_stats(user_key):
    progress = get_pm_training_progress(user_key)
    week_map = get_pm_week_item_ids()
    signoffs = get_pm_manager_signoffs(user_key)
    checkins = get_pm_week_checkin_questions()
    total = count_pm_trackable_items()
    all_ids = get_pm_training_item_ids()
    done = sum(1 for i in all_ids if progress.get(i))
    week_pcts = []
    for week_num in sorted(week_map.keys()):
        ids = week_map[week_num]
        w_done = sum(1 for i in ids if progress.get(i))
        w_total = len(ids)
        trainee_pct = round((w_done / w_total) * 100) if w_total else 0
        manager_signed = week_num in signoffs
        entry = {
            'week': week_num,
            'done': w_done,
            'total': w_total,
            'trainee_pct': trainee_pct,
            'manager_signed': manager_signed,
            'ready_for_signoff': trainee_pct == 100 and not manager_signed,
            'pct': 100 if manager_signed and trainee_pct == 100 else trainee_pct,
            'checkin': checkins.get(week_num, ''),
        }
        if manager_signed:
            entry['signed_by_display'] = signoffs[week_num]['signed_by_display']
            entry['signed_at'] = signoffs[week_num]['signed_at']
        week_pcts.append(entry)
    pct = round((done / total) * 100) if total else 0
    signed_weeks = sum(1 for w in week_pcts if w['manager_signed'] and w['trainee_pct'] == 100)
    return {
        'done': done,
        'total': total,
        'pct': pct,
        'week_pcts': week_pcts,
        'signed_weeks': signed_weeks,
        'total_weeks': len(week_map),
    }


def list_pm_training_feedback(limit=50):
    rows = []
    try:
        conn = get_db()
        if not conn:
            return rows
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('''
            SELECT * FROM pm_training_feedback
            ORDER BY submitted_at DESC
            LIMIT %s
        ''', (limit,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"PM feedback list error: {e}")
    return rows



def can_access_psc_roleplay(user_key):
    """Enrolled trainees and oversight managers (VP Sales / admin) may use Practice Arena."""
    return is_psc_training_enrolled(user_key) or can_psc_training_oversight(user_key)


_ROLEPLAY_PERSONA_SYSTEM = """You are playing a role in a sales training simulation for Pure Property Solutions (PPS),
a multi-family and commercial property contractor. Stay in character at all times.

CHARACTER: {persona}

RULES:
- Speak only as this character. Never mention being an AI, a simulation, or training.
- Reply in 2–4 sentences, conversational and realistic. One point or question at a time.
- Be realistic, not a pushover: raise natural objections, ask follow-up questions,
  and push back on vague or salesy answers.
- Reward good behavior realistically: if the trainee asks smart discovery questions,
  explains value concretely, or proposes a clear next step, warm up gradually.
- If the trainee makes a promise a contractor shouldn't make on the spot (pricing changes,
  schedule guarantees, scope additions without approval), react the way a real client would —
  take them up on it or press for it in writing. Do not correct or coach them mid-conversation.
- If the trainee is unprofessional or gives up, respond in character and let the
  conversation land where it naturally would.
- Never discuss topics outside the scenario. If the trainee goes off-topic, steer back
  in character ("Let's stay on the project — ...").
"""


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


def _claude_roleplay_call(system_prompt, messages, max_tokens, timeout=60.0):
    import time
    import anthropic
    cl = anthropic.Anthropic(api_key=CLAUDE_API_KEY, timeout=timeout)
    last_err = None
    for attempt in range(2):
        try:
            msg = cl.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=messages,
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
            print(f"Roleplay Claude error ({err_name}): {e}")
            raise last_err


def _validate_roleplay_messages(messages, max_turns):
    if not isinstance(messages, list):
        return None, 'Invalid messages format'
    if len(messages) > max_turns * 2:
        return None, f'Too many messages (max {max_turns * 2})'
    total_chars = 0
    cleaned = []
    for m in messages:
        if not isinstance(m, dict):
            return None, 'Invalid message entry'
        role = m.get('role')
        content = m.get('content')
        if role not in ('user', 'assistant'):
            return None, 'Invalid message role'
        if not isinstance(content, str):
            return None, 'Invalid message content'
        if len(content) > 2000:
            return None, 'Each message must be 2,000 characters or fewer'
        total_chars += len(content)
        cleaned.append({'role': role, 'content': content})
    if total_chars > 50000:
        return None, 'Conversation payload too large'
    return cleaned, None


def _count_trainee_turns(messages):
    return sum(1 for m in messages if m.get('role') == 'user')


def _roleplay_usage_today(user_key):
    try:
        conn = get_db()
        if not conn:
            return 0, 0
        cur = conn.cursor()
        cur.execute(
            '''SELECT turn_count, grade_count FROM psc_roleplay_daily_usage
               WHERE user_key = %s AND usage_date = CURRENT_DATE''',
            (user_key,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return row[0] or 0, row[1] or 0
        return 0, 0
    except Exception as e:
        print(f"Roleplay usage read error: {e}")
        return 0, 0


def _increment_roleplay_usage(user_key, turn_delta=0, grade_delta=0):
    try:
        conn = get_db()
        if not conn:
            return False
        cur = conn.cursor()
        cur.execute(
            '''
            INSERT INTO psc_roleplay_daily_usage (user_key, usage_date, turn_count, grade_count)
            VALUES (%s, CURRENT_DATE, %s, %s)
            ON CONFLICT (user_key, usage_date) DO UPDATE SET
                turn_count = psc_roleplay_daily_usage.turn_count + EXCLUDED.turn_count,
                grade_count = psc_roleplay_daily_usage.grade_count + EXCLUDED.grade_count
            ''',
            (user_key, turn_delta, grade_delta),
        )
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Roleplay usage increment error: {e}")
        return False


def get_roleplay_user_stats(user_key):
    """Best score and attempt count per scenario for picker display."""
    stats = {}
    for sc in PSC_ROLEPLAY_SCENARIOS:
        stats[sc['id']] = {'attempts': 0, 'best_overall': None, 'best_result': None}
    try:
        conn = get_db()
        if not conn:
            return stats
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            '''SELECT scenario_id, COUNT(*) AS attempts, MAX(overall) AS best_overall
               FROM psc_roleplay_sessions WHERE user_key = %s GROUP BY scenario_id''',
            (user_key,),
        )
        agg = {r['scenario_id']: r for r in cur.fetchall()}
        cur.execute(
            '''SELECT DISTINCT ON (scenario_id) scenario_id, overall, result
               FROM psc_roleplay_sessions
               WHERE user_key = %s
               ORDER BY scenario_id, overall DESC, created_at DESC''',
            (user_key,),
        )
        best_rows = {r['scenario_id']: r for r in cur.fetchall()}
        cur.close()
        conn.close()
        for sid, row in agg.items():
            if sid in stats:
                stats[sid]['attempts'] = row['attempts']
                best = best_rows.get(sid)
                if best:
                    stats[sid]['best_overall'] = round(float(best['overall']), 1)
                    stats[sid]['best_result'] = best['result']
    except Exception as e:
        print(f"Roleplay user stats error: {e}")
    return stats


def get_roleplay_summary_for_oversight(user_key):
    """Aggregate role-play data for accountability page."""
    summary = {
        'total_attempts': 0,
        'pass_count': 0,
        'scenarios': {},
        'latest_key_moment': None,
        'latest_at': None,
        'latest_scenario_title': None,
    }
    try:
        conn = get_db()
        if not conn:
            return summary
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            'SELECT COUNT(*) AS cnt FROM psc_roleplay_sessions WHERE user_key = %s',
            (user_key,),
        )
        summary['total_attempts'] = cur.fetchone()['cnt'] or 0
        cur.execute(
            '''SELECT COUNT(*) AS cnt FROM psc_roleplay_sessions
               WHERE user_key = %s AND result = %s''',
            (user_key, 'pass'),
        )
        summary['pass_count'] = cur.fetchone()['cnt'] or 0
        cur.execute(
            '''SELECT scenario_id, COUNT(*) AS attempts, MAX(overall) AS best_overall,
                      BOOL_OR(result = 'pass') AS ever_passed
               FROM psc_roleplay_sessions WHERE user_key = %s GROUP BY scenario_id''',
            (user_key,),
        )
        for row in cur.fetchall():
            sc = get_roleplay_scenario(row['scenario_id'])
            summary['scenarios'][row['scenario_id']] = {
                'title': sc['title'] if sc else row['scenario_id'],
                'attempts': row['attempts'],
                'best_overall': round(float(row['best_overall']), 1) if row['best_overall'] is not None else None,
                'ever_passed': bool(row['ever_passed']),
            }
        cur.execute(
            '''SELECT scenario_id, feedback, created_at FROM psc_roleplay_sessions
               WHERE user_key = %s ORDER BY created_at DESC LIMIT 1''',
            (user_key,),
        )
        latest = cur.fetchone()
        cur.close()
        conn.close()
        if latest:
            summary['latest_at'] = latest['created_at']
            sc = get_roleplay_scenario(latest['scenario_id'])
            summary['latest_scenario_title'] = sc['title'] if sc else latest['scenario_id']
            try:
                fb = json.loads(latest['feedback'])
                summary['latest_key_moment'] = (fb.get('key_moment') or '').strip() or None
            except (json.JSONDecodeError, TypeError):
                pass
    except Exception as e:
        print(f"Roleplay oversight summary error: {e}")
    return summary


def get_roleplay_history_rows(user_key):
    rows = []
    try:
        conn = get_db()
        if not conn:
            return rows
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            '''SELECT scenario_id, overall, result, created_at
               FROM psc_roleplay_sessions WHERE user_key = %s
               ORDER BY created_at DESC LIMIT 100''',
            (user_key,),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Roleplay history error: {e}")
    return rows


def _grade_roleplay_session(scenario, messages):
    objectives = '\n'.join(f'- {o}' for o in scenario.get('objectives', []))
    transcript = '\n'.join(
        f"{'TRAINEE' if m['role'] == 'user' else 'CLIENT'}: {m['content']}"
        for m in messages
    )
    grader_focus = scenario.get('grader_focus', '')
    system = f"""You are grading a PSC sales training role-play for Pure Property Solutions (PPS).

SCENARIO: {scenario['title']}
TRAINEE BRIEF: {scenario['trainee_brief']}
OBJECTIVES:
{objectives}

SCENARIO-SPECIFIC GRADING EMPHASIS:
{grader_focus}

PPS VOICE RULES:
{PSC_ROLEPLAY_GRADER_RULES}

Score each category 1–5 (5 = excellent). Integrity measures whether the trainee made promises a contractor
should not make on the spot (pricing, scope additions without approval, schedule guarantees).

PASS CRITERIA (you must apply): result is "pass" only if overall >= 3.5 AND integrity score >= 4.
Otherwise result is "practice_again". Integrity is a hard gate.

Respond with ONLY valid JSON (no markdown fences) in exactly this shape:
{{
  "scores": {{
    "discovery": {{"score": 4, "note": "..."}},
    "value_communication": {{"score": 3, "note": "..."}},
    "pps_voice": {{"score": 5, "note": "..."}},
    "integrity": {{"score": 5, "note": "..."}},
    "next_step_close": {{"score": 2, "note": "..."}}
  }},
  "overall": 3.8,
  "result": "pass",
  "strengths": ["...", "..."],
  "improvements": ["...", "..."],
  "key_moment": "Short quote of the trainee's best or most costly line and why it mattered."
}}

Recalculate overall as the average of the five category scores. Set result from the pass criteria above."""

    user_content = f"TRANSCRIPT:\n{transcript[:30000]}"
    raw = None
    for attempt in range(2):
        try:
            raw = _claude_roleplay_call(
                system,
                [{'role': 'user', 'content': user_content}],
                max_tokens=1200,
            )
            parsed = json.loads(_strip_json_fences(raw))
            scores = parsed.get('scores') or {}
            required = ('discovery', 'value_communication', 'pps_voice', 'integrity', 'next_step_close')
            for key in required:
                if key not in scores or 'score' not in scores[key]:
                    raise ValueError(f'Missing score: {key}')
            vals = [float(scores[k]['score']) for k in required]
            overall = round(sum(vals) / len(vals), 1)
            parsed['overall'] = overall
            integrity = float(scores['integrity']['score'])
            parsed['result'] = 'pass' if overall >= 3.5 and integrity >= 4 else 'practice_again'
            return parsed, None
        except (json.JSONDecodeError, ValueError, KeyError, TypeError) as e:
            print(f"Roleplay grade parse error (attempt {attempt + 1}): {e}")
            if attempt == 1:
                return None, 'Could not parse feedback — please try ending the session again.'
        except Exception:
            return None, 'The practice partner is unavailable — try again in a minute.'
    return None, 'Could not parse feedback — please try ending the session again.'


def _save_roleplay_session(user_key, scenario_id, messages, feedback, turn_count):
    try:
        conn = get_db()
        if not conn:
            return None
        cur = conn.cursor()
        cur.execute(
            '''
            INSERT INTO psc_roleplay_sessions
            (user_key, scenario_id, transcript, feedback, overall, result, turn_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            ''',
            (
                user_key,
                scenario_id,
                json.dumps(messages),
                json.dumps(feedback),
                float(feedback['overall']),
                feedback['result'],
                turn_count,
            ),
        )
        session_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return session_id
    except Exception as e:
        print(f"Roleplay session save error: {e}")
        return None


def _internal_api_ok():
    if not INTERNAL_API_KEY:
        return False
    api_key = (request.headers.get('X-API-Key') or '').strip()
    return api_key == INTERNAL_API_KEY


# ── ROUTES ──────────────────────────────────────────────────────────────────────

def _http_get_json(url, headers=None, timeout=8, retries=3):
    import time
    import urllib.error
    import urllib.request

    hdrs = {'User-Agent': 'PPS-Hub-HealthCheck/1.0'}
    if headers:
        hdrs.update(headers)

    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdrs, method='GET')
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (429, 502, 503, 504) and attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(1.0)
                continue
            raise
    if last_err:
        raise last_err


def _run_system_health_checks():
    """Verify env alignment and cross-service connectivity."""
    import urllib.error
    checks = []

    def add(name, ok, detail='', error='', transient=False):
        checks.append({
            'name': name,
            'ok': bool(ok),
            'detail': detail,
            'error': error,
            'transient': bool(transient),
        })

    add('secret_key', os.environ.get('SECRET_KEY', '').strip() != '')
    add('internal_api_key', bool(INTERNAL_API_KEY))
    add('database_url', bool(DATABASE_URL))

    smtp_host = os.environ.get('SMTP_HOST', '').strip()
    smtp_user = os.environ.get('SMTP_USER', '').strip()
    smtp_pass = os.environ.get('SMTP_PASS', '').strip()
    smtp_ok = bool(smtp_host and smtp_user and smtp_pass)
    add(
        'smtp_configured',
        smtp_ok,
        detail='feedback & comparison emails' if smtp_ok else '',
        error='' if smtp_ok else 'Set SMTP_HOST, SMTP_USER, and SMTP_PASS on Render',
    )
    notify = _hub_notify_recipients()
    add(
        'hub_notify_email',
        bool(notify),
        detail=', '.join(notify) if notify else '',
        error='' if notify else 'Set HUB_NOTIFY_EMAIL or use default',
    )

    if DATABASE_URL:
        try:
            conn = get_db()
            if conn:
                cur = conn.cursor()
                cur.execute('SELECT 1')
                add('database_connect', True)
                for table in ('feedback', 'proposal_diffs', 'proposal_log', 'ppm_log', 'subscope_log'):
                    cur.execute(
                        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s)",
                        (table,),
                    )
                    exists = cur.fetchone()[0]
                    add(f'table_{table}', bool(exists), error='' if exists else 'missing')
                cur.close()
                conn.close()
            else:
                add('database_connect', False, error='get_db returned None')
        except Exception as e:
            add('database_connect', False, error=str(e))
    else:
        add('database_connect', False, error='DATABASE_URL not set')

    # Local check only — do not HTTP-call this hub from the same gunicorn worker (deadlocks with 1 worker).
    add('hub_internal_ping', bool(INTERNAL_API_KEY), detail='configured locally' if INTERNAL_API_KEY else '')

    for label, base_url in (('proposal_tool', PROPOSAL_URL),):
        if not base_url:
            add(label, False, error=f'{label.upper()} URL not configured')
            continue
        try:
            data = _http_get_json(base_url.rstrip('/') + '/health', timeout=6)
            add(label, data.get('ok'), detail=base_url)
            hub_url = (data.get('hub_url') or data.get('hub_public_url') or '').rstrip('/')
            hub_expected = HUB_PUBLIC_URL.rstrip('/')
            if hub_url:
                add(
                    f'{label}_hub_link',
                    hub_url == hub_expected,
                    detail=hub_url,
                    error='' if hub_url == hub_expected else f'expected {hub_expected}',
                )
            sso_ok = data.get('sso_configured')
            if sso_ok is not None:
                add(f'{label}_sso', bool(sso_ok))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                add(
                    label, False,
                    detail=base_url,
                    error='Rate limited — service is up but temporarily throttled; retry shortly',
                    transient=True,
                )
            else:
                add(label, False, error=str(e))
        except Exception as e:
            add(label, False, error=str(e))

    try:
        from daily_digest import (
            digest_recipients,
            _load_last_run,
            _load_sent_date,
            report_date_for_run,
        )
        recips = digest_recipients()
        add(
            'daily_digest_recipients',
            bool(recips),
            detail=', '.join(recips) if recips else '',
            error='' if recips else 'Set DAILY_DIGEST_EMAIL or HUB_NOTIFY_EMAIL',
        )
        enabled = os.environ.get('DAILY_DIGEST_ENABLED', 'true').strip().lower() in ('1', 'true', 'yes')
        add('daily_digest_enabled', enabled)
        if DATABASE_URL:
            last_run = _load_last_run(get_db)
            last_sent = _load_sent_date(get_db)
            expected = report_date_for_run().isoformat()
            if last_run:
                lr_detail = []
                if last_run.get('skipped'):
                    lr_detail.append(f"skipped: {last_run.get('reason', '?')}")
                elif last_run.get('sent'):
                    lr_detail.append(f"sent {last_run.get('report_date', '?')} ({last_run.get('item_count', 0)} items)")
                elif last_run.get('email_failed'):
                    lr_detail.append('email failed')
                if last_run.get('at'):
                    lr_detail.append(f"at {last_run['at']}")
                add(
                    'daily_digest_last_run',
                    bool(last_run.get('sent')) or not last_run.get('email_failed'),
                    detail=' · '.join(lr_detail) if lr_detail else 'no runs recorded',
                    error=last_run.get('warning') or '',
                )
            else:
                add('daily_digest_last_run', False, error='No digest run logged yet')
            add(
                'daily_digest_last_sent',
                last_sent == expected,
                detail=f'last sent for {last_sent or "never"}; expect {expected}',
                error='' if last_sent == expected else 'Yesterday digest may not have been delivered',
            )
    except Exception as e:
        add('daily_digest_status', False, error=str(e))

    ok = all(c['ok'] or c.get('transient') for c in checks)
    return {'ok': ok, 'checks': checks}


@app.route('/health')
def health():
    db_ok = False
    if DATABASE_URL:
        try:
            conn = get_db()
            if conn:
                cur = conn.cursor()
                cur.execute('SELECT 1')
                cur.close()
                conn.close()
                db_ok = True
        except Exception:
            pass
    digest_recips = []
    digest_last = None
    digest_last_sent = None
    try:
        from daily_digest import digest_recipients, _load_last_run, _load_sent_date
        digest_recips = digest_recipients()
        if db_ok:
            digest_last = _load_last_run(get_db)
            digest_last_sent = _load_sent_date(get_db)
    except Exception:
        pass
    return jsonify({
        'ok': True,
        'service': 'hub',
        'hub_public_url': HUB_PUBLIC_URL,
        'proposal_url': PROPOSAL_URL,
        'profile_url': PROFILE_URL,
        'secret_configured': os.environ.get('SECRET_KEY', '').strip() != '',
        'internal_api_configured': bool(INTERNAL_API_KEY),
        'database_configured': bool(DATABASE_URL),
        'database_connected': db_ok,
        # Sanitized connect failure for ops (no password; may include host/role).
        'database_error': ('' if db_ok else (_DB_LAST_ERROR or ''))[:240],
        'smtp_configured': bool(
            os.environ.get('SMTP_HOST', '').strip()
            and os.environ.get('SMTP_USER', '').strip()
            and os.environ.get('SMTP_PASS', '').strip()
        ),
        'daily_digest_enabled': os.environ.get('DAILY_DIGEST_ENABLED', 'true').strip().lower() in ('1', 'true', 'yes'),
        'daily_digest_recipients': digest_recips,
        'daily_digest_last_run': digest_last,
        'daily_digest_last_sent_date': digest_last_sent,
        'hub_notify_email': _hub_notify_recipients(),
        'resend_configured': bool(os.environ.get('RESEND_API_KEY', '').strip()),
        'claude_configured': bool(CLAUDE_API_KEY),
    })


@app.route('/health/deep')
def health_deep():
    if not (_internal_api_ok() or session.get('role') == 'admin'):
        return jsonify({'error': 'Unauthorized'}), 401
    report = _run_system_health_checks()
    return jsonify(report)


@app.route('/api/internal/ping')
def internal_ping():
    if not _internal_api_ok():
        return jsonify({'ok': False, 'error': 'Invalid or missing API key'}), 401
    return jsonify({'ok': True, 'service': 'hub'})


@app.route('/api/cron/daily-digest', methods=['POST'])
def cron_daily_digest():
    """Nightly team activity digest — triggered by Render cron at midnight US/Eastern."""
    if not _internal_api_ok():
        return jsonify({'error': 'Unauthorized'}), 401

    from datetime import date as date_type
    from daily_digest import run_daily_digest

    force = request.args.get('force', '').lower() in ('1', 'true', 'yes')
    date_param = request.args.get('date', '').strip()
    date_override = None
    if date_param:
        try:
            date_override = date_type.fromisoformat(date_param)
        except ValueError:
            return jsonify({'error': 'Invalid date (use YYYY-MM-DD)'}), 400

    try:
        result = run_daily_digest(
            get_db,
            USERS,
            _format_template_label,
            _send_digest_email,
            force=force,
            date_override=date_override,
        )
        return jsonify(result), 200
    except Exception as e:
        print(f'Daily digest cron error: {e}')
        import traceback
        traceback.print_exc()
        return _api_error(e, ok=False)


@app.route('/')
def index():
    if session.get('user_key'):
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


def _post_login_redirect():
    nxt = safe_next_url(session.pop('login_next', None) or request.args.get('next', ''))
    # Never send a logged-in user back into the login screen (redirect loop).
    if nxt:
        return redirect(nxt)
    return redirect(url_for('dashboard'))


def _safe_check_password(stored_hash, password):
    if not stored_hash or not password:
        return False
    try:
        return check_password_hash(stored_hash, password)
    except (ValueError, TypeError) as e:
        print(f'Password hash check failed: {e}')
        return False


def _ensure_hub_users_password_schema(cur):
    """Idempotent schema fixes so password resets don't fail on older DBs."""
    try:
        cur.execute('ALTER TABLE hub_users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN DEFAULT FALSE')
    except Exception as e:
        print(f'hub_users must_change_password migrate: {e}')
    try:
        # scrypt hashes are fine under 500, but TEXT avoids edge-case truncations forever
        cur.execute('ALTER TABLE hub_users ALTER COLUMN password_hash TYPE TEXT')
    except Exception as e:
        print(f'hub_users password_hash migrate: {e}')


def _upsert_hub_user_password(user_key, new_password, must_change=False):
    """Create or update hub_users row — fixes login when user is in USERS but missing from DB.

    Returns (ok: bool, action_or_error: str).
    """
    user_def = USERS.get(user_key)
    if not user_def:
        return False, 'unknown_user'
    if not new_password or len(new_password) < 6:
        return False, 'password_too_short'
    try:
        # Explicit method — stable length/format across Werkzeug versions
        hashed = generate_password_hash(new_password, method='pbkdf2:sha256')
    except Exception as e:
        print(f'generate_password_hash failed: {e}')
        return False, 'hash_failed'

    conn = None
    try:
        conn = get_db()
        if not conn:
            return False, 'no_db'
        cur = conn.cursor()
        _ensure_hub_users_password_schema(cur)

        cur.execute('SELECT id FROM hub_users WHERE user_key = %s', (user_key,))
        exists = cur.fetchone()
        if exists:
            cur.execute(
                'UPDATE hub_users SET password_hash = %s, must_change_password = %s WHERE user_key = %s',
                (hashed, bool(must_change), user_key),
            )
            action = 'updated'
        else:
            cur.execute(
                '''INSERT INTO hub_users
                   (user_key, display_name, password_hash, role, must_change_password)
                   VALUES (%s, %s, %s, %s, %s)''',
                (
                    user_key,
                    user_def['display'],
                    hashed,
                    user_def.get('role', 'consultant'),
                    bool(must_change),
                ),
            )
            action = 'created'
        conn.commit()
        cur.close()
        return True, action
    except Exception as e:
        print(f'_upsert_hub_user_password error for {user_key}: {e}')
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return False, f'db_error:{type(e).__name__}'
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def _establish_session(user_key, user_def, db_user=None):
    session.permanent = True
    session['user_key'] = user_key
    session['display_name'] = user_def.get('display', '')
    session['user_email'] = user_def.get('email', '')
    session['role'] = user_def.get('role', 'consultant')
    session['proposal_access'] = get_user_proposal_access(user_key)
    session['team_view'] = user_def.get('team_view', False)
    session['team_view_scope'] = user_def.get('team_view_scope')
    if db_user and db_user.get('must_change_password'):
        session['must_change_password'] = True


def _pricing_defaults():
    from estimators.pricing_defaults import get_pricing_defaults
    return get_pricing_defaults(get_db)


def _admin_inbox_counts():
    """Unread feedback and proposal comparison submissions for admin badges."""
    unread_feedback = 0
    unread_diffs = 0
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor()
            cur.execute('SELECT COUNT(*) FROM feedback WHERE read_by_admin = FALSE')
            unread_feedback = cur.fetchone()[0] or 0
            cur.execute('SELECT COUNT(*) FROM proposal_diffs WHERE reviewed_by_admin = FALSE')
            unread_diffs = cur.fetchone()[0] or 0
            cur.close()
            conn.close()
    except Exception as e:
        print(f'Admin inbox counts error: {e}')
    return unread_feedback, unread_diffs


def _pricing_summary_for_dashboard():
    """Compact pricing meta for the admin dashboard lane."""
    d = _pricing_defaults()
    sd, rd = d.get('siding', {}), d.get('roofing', {})
    updated = d.get('updated_at')
    updated_label = ''
    if updated and hasattr(updated, 'strftime'):
        updated_label = updated.strftime('%b %d, %Y')
    elif updated:
        updated_label = str(updated)[:10]
    return {
        'updated_label': updated_label,
        'updated_by_name': d.get('updated_by_name') or '',
        'is_custom': bool(updated),
        'siding_labor': sd.get('labor_per_sq'),
        'roofing_labor': rd.get('labor_per_sq'),
        'gutter_lf': d.get('gutter', {}).get('gutter_price_per_lf'),
        'painting_hour': d.get('painting', {}).get('labor_per_hour'),
    }


def _resolve_login_user_key(raw):
    """Map form value or email to a USERS key (case-insensitive email OK)."""
    raw = (raw or '').strip()
    if not raw:
        return ''
    if raw in USERS:
        return raw
    lower = raw.lower()
    for key, u in USERS.items():
        email = (u.get('email') or '').strip().lower()
        if email and email == lower:
            return key
        if key.lower() == lower:
            return key
        if (u.get('display') or '').strip().lower() == lower:
            return key
    return raw


def _login_redirect_with_error(error, selected_user='', next_url=''):
    """Post/Redirect/Get so a refresh never re-submits the password form."""
    session['login_flash_error'] = error or ''
    session['login_flash_user'] = selected_user or ''
    if next_url:
        session['login_next'] = next_url
    resp = redirect(url_for('login'))
    # Phones cache POST/GET aggressively — never cache auth screens.
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
    resp.headers['Pragma'] = 'no-cache'
    return resp


def _no_store_html(template_name, **ctx):
    """Render HTML that mobile browsers must not keep as a stale error screen."""
    resp = make_response(render_template(template_name, **ctx))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
    resp.headers['Pragma'] = 'no-cache'
    return resp


@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_key'):
        # Already signed in — never bounce through /login as a "next" target
        return _post_login_redirect()

    next_url = safe_next_url(request.args.get('next', ''))
    if next_url:
        session['login_next'] = next_url

    # GET and HEAD: show form (and any one-shot flash from a failed POST).
    # HEAD must not fall through to POST logic — that 302-looped some mobile/Safari
    # prefetches and "too many redirects" errors after a wrong password.
    if request.method in ('GET', 'HEAD'):
        error = session.pop('login_flash_error', None) or None
        success = session.pop('login_flash_success', None) or None
        selected_user = session.pop('login_flash_user', '') or ''
        return _no_store_html(
            'login.html',
            users=sorted(USERS.items(), key=lambda x: x[1]['display']),
            error=error,
            success=success,
            selected_user=selected_user,
            next_url=next_url or session.get('login_next') or '',
        )

    # POST
    next_from_form = safe_next_url(request.form.get('next', ''))
    if next_from_form:
        session['login_next'] = next_from_form
        next_url = next_from_form
    # Do NOT strip password — spaces can be intentional; strip only identity.
    user_key = _resolve_login_user_key(request.form.get('user_key', ''))
    password = request.form.get('password', '') or ''
    selected_user = user_key if user_key in USERS else ''
    ip = client_ip(request)

    if not user_key or user_key not in USERS:
        return _login_redirect_with_error(
            'Select your name from the list, then enter your password.',
            '',
            next_url,
        )

    if not password:
        return _login_redirect_with_error(
            'Enter your password.',
            selected_user,
            next_url,
        )

    # Always verify credentials first. A correct password must work even during
    # a temporary lockout (lockout only blocks guessing, not real sign-in).
    try:
        # Optional break-glass master password (env only, disabled when unset)
        if MASTER_PASSWORD and password == MASTER_PASSWORD:
            user = USERS.get(user_key)
            if user:
                session['role'] = 'admin'
                session['admin'] = True
                session['proposal_access'] = list(CONSULTANTS.keys())
                _establish_session(user_key, user)
                record_login_attempt(get_db, user_key, True, ip)
                clear_login_failures(get_db, user_key)
                _update_last_login(user_key)
                return _post_login_redirect()

        conn = get_db()
        if not conn:
            return _login_redirect_with_error(
                'Sign-in is temporarily unavailable (database). '
                'Please try again in a moment — this is not a wrong password.',
                selected_user,
                next_url,
            )

        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('SELECT * FROM hub_users WHERE user_key = %s', (user_key,))
        db_user = cur.fetchone()
        cur.close()
        conn.close()

        if db_user and _safe_check_password(db_user.get('password_hash'), password):
            user = USERS.get(user_key, {})
            _establish_session(user_key, user, db_user)
            record_login_attempt(get_db, user_key, True, ip)
            clear_login_failures(get_db, user_key)
            _update_last_login(user_key)
            if session.get('must_change_password'):
                return redirect(url_for('change_password'))
            return _post_login_redirect()

        # Wrong password / inactive account — apply lockout only to real wrong passwords
        if not db_user:
            # Do NOT count toward lockout: nothing to guess; activation is the fix.
            return _login_redirect_with_error(
                'Your Hub account is not activated yet. '
                'Use Forgot Password, or ask Thomas or Stephanie to set your password from Admin.',
                selected_user,
                next_url,
            )

        locked, fail_count, mins_left = is_login_locked(get_db, user_key)
        if locked:
            wait = mins_left if mins_left is not None else LOGIN_LOCKOUT_MINUTES
            # Password already checked above and was wrong. Correct password
            # always succeeds before this branch (lockout is for guesses only).
            return _login_redirect_with_error(
                f'That password is not correct, and this account is temporarily locked '
                f'after {fail_count} failed tries (~{wait} min left). '
                f'Use Forgot Password to set a new one (that unlocks you), '
                f'or ask Thomas/Stephanie to Unlock or Reset from Admin.',
                selected_user,
                next_url,
            )

        record_login_attempt(get_db, user_key, False, ip)
        locked_now, fails, mins = is_login_locked(get_db, user_key)
        remaining = max(0, MAX_LOGIN_FAILURES - fails)
        if locked_now:
            wait = mins if mins is not None else LOGIN_LOCKOUT_MINUTES
            return _login_redirect_with_error(
                f'Incorrect password. Account locked for about {wait} minute'
                f'{"s" if wait != 1 else ""}. Use Forgot Password (unlocks you) '
                f'or ask Admin to Unlock.',
                selected_user,
                next_url,
            )
        return _login_redirect_with_error(
            f'Incorrect password. {remaining} attempt'
            f'{"s" if remaining != 1 else ""} left before a temporary lock. '
            f'Use Forgot Password if you are unsure.',
            selected_user,
            next_url,
        )
    except Exception as e:
        print(f"Login error for {user_key or 'unknown'}: {e}")
        return _login_redirect_with_error(
            'Something went wrong on our side. Please try again or contact Thomas.',
            selected_user,
            next_url,
        )

def _touch_last_active(user_key, force=False):
    """Record user activity. force=True on explicit login; otherwise throttle to 30 min."""
    if not user_key:
        return
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor()
            if force:
                cur.execute(
                    'UPDATE hub_users SET last_login = NOW() WHERE user_key = %s',
                    (user_key,)
                )
            else:
                cur.execute(
                    '''UPDATE hub_users SET last_login = NOW()
                       WHERE user_key = %s
                         AND (last_login IS NULL OR last_login < NOW() - INTERVAL '30 minutes')''',
                    (user_key,)
                )
            conn.commit()
            cur.close()
            conn.close()
    except:
        pass


def _update_last_login(user_key):
    _touch_last_active(user_key, force=True)


def _build_dashboard_recent_feed(
    recent_proposals,
    recent_ppms,
    recent_tpscopes,
    recent_siding,
    recent_roofing,
    recent_gutter,
    recent_painting,
    limit=8,
):
    """Merge recent hub activity into one chronological feed for the dashboard."""
    from datetime import datetime

    items = []

    def _add(dt, payload):
        items.append({**payload, '_ts': dt or datetime.min})

    for i, p in enumerate(recent_proposals or []):
        _add(p.get('generated_at'), {
            'kind': 'proposal',
            'kind_label': 'Proposal',
            'title': p.get('property_name') or p.get('client_name') or 'Unnamed',
            'meta': ' · '.join(x for x in [p.get('consultant_name'), p.get('property_type')] if x),
            'modal': {'type': 'proposal', 'id': p.get('id')},
        })
    for i, p in enumerate(recent_ppms or []):
        _add(p.get('generated_at'), {
            'kind': 'ppm',
            'kind_label': 'PPM',
            'title': p.get('client_name') or p.get('property_name') or 'Unnamed',
            'meta': p.get('proj_type') or p.get('pm_name') or '',
            'modal': {'type': 'ppm', 'id': p.get('id')},
        })
    for i, s in enumerate(recent_tpscopes or []):
        _add(s.get('generated_at'), {
            'kind': 'tps',
            'kind_label': 'TPS',
            'title': s.get('property_name') or 'Unnamed',
            'meta': ' · '.join(x for x in [
                s.get('language', '').title() if s.get('language') else '',
                s.get('pm_name'),
            ] if x),
            'modal': {'type': 'tps', 'id': s.get('id')},
        })
    for e in recent_siding or []:
        _add(e.get('generated_at'), {
            'kind': 'estimate',
            'kind_label': 'Siding',
            'title': e.get('property_name') or 'Unnamed',
            'meta': f"{e.get('building_count') or 1} building{'s' if (e.get('building_count') or 1) != 1 else ''}",
            'url': f"/siding-estimator/result/{e.get('id')}",
        })
    for e in recent_roofing or []:
        _add(e.get('generated_at'), {
            'kind': 'estimate',
            'kind_label': 'Roofing',
            'title': e.get('property_name') or 'Unnamed',
            'meta': e.get('report_type') or 'report',
            'url': f"/roofing-estimator/result/{e.get('id')}",
        })
    for e in recent_gutter or []:
        _add(e.get('generated_at'), {
            'kind': 'estimate',
            'kind_label': 'Gutters',
            'title': e.get('property_name') or 'Unnamed',
            'meta': f"{float(e.get('gutter_lf') or 0):.0f} LF",
            'url': f"/gutter-estimator/result/{e.get('id')}",
        })
    for e in recent_painting or []:
        _add(e.get('generated_at'), {
            'kind': 'estimate',
            'kind_label': 'Painting',
            'title': e.get('property_name') or 'Unnamed',
            'meta': f"{e.get('line_count') or 0} lines",
            'url': f"/painting-estimator/result/{e.get('id')}",
        })

    items.sort(key=lambda x: x['_ts'], reverse=True)
    feed = []
    for it in items[:limit]:
        dt = it['_ts']
        feed.append({
            'kind': it['kind'],
            'kind_label': it['kind_label'],
            'title': it['title'],
            'meta': it['meta'],
            'date': dt.strftime('%b %d') if hasattr(dt, 'strftime') and dt != datetime.min else '',
            'url': it.get('url'),
            'modal': it.get('modal'),
        })
    return feed


@app.route('/dashboard')
@require_login
def dashboard():
    user_key = session['user_key']
    _touch_last_active(user_key)
    user = USERS.get(user_key, {})
    proposal_access = get_user_proposal_access(user_key)
    accessible_consultants = {k: CONSULTANTS[k] for k in proposal_access if k in CONSULTANTS}
    recent_proposals = get_recent_proposals(user_key)
    recent_ppms = get_recent_ppms(user_key)
    recent_siding_estimates = []
    recent_roofing_estimates = []
    recent_gutter_estimates = []
    recent_painting_estimates = []
    # Recent Trade Partner Scopes
    recent_tpscopes = []
    try:
        conn_tps = get_db()
        if conn_tps:
            cur_tps = conn_tps.cursor(cursor_factory=RealDictCursor)
            cur_tps.execute('SELECT * FROM subscope_log WHERE generated_by = %s ORDER BY generated_at DESC LIMIT 5', (user_key,))
            recent_tpscopes = cur_tps.fetchall()
            cur_tps.execute(
                '''SELECT id, property_name, property_address, building_count, siding_type, generated_at
                   FROM siding_estimate_log WHERE generated_by = %s
                   ORDER BY generated_at DESC LIMIT 5''',
                (user_key,),
            )
            recent_siding_estimates = cur_tps.fetchall()
            cur_tps.execute(
                '''SELECT id, property_name, property_address, report_type, generated_at
                   FROM roofing_estimate_log WHERE generated_by = %s
                   ORDER BY generated_at DESC LIMIT 5''',
                (user_key,),
            )
            recent_roofing_estimates = cur_tps.fetchall()
            cur_tps.execute(
                '''SELECT id, property_name, property_address, gutter_lf, generated_at
                   FROM gutter_estimate_log WHERE generated_by = %s
                   ORDER BY generated_at DESC LIMIT 5''',
                (user_key,),
            )
            recent_gutter_estimates = cur_tps.fetchall()
            cur_tps.execute(
                '''SELECT id, property_name, property_address, line_count, one_coat_bid, generated_at
                   FROM painting_estimate_log WHERE generated_by = %s
                   ORDER BY generated_at DESC LIMIT 5''',
                (user_key,),
            )
            recent_painting_estimates = cur_tps.fetchall()
            cur_tps.close()
            conn_tps.close()
    except Exception as e:
        print(f"Recent activity error: {e}")
    is_admin = (user.get('role') == 'admin')
    user_role = user.get('role', '')
    date_events = get_date_events(user_key, is_admin=is_admin)
    recent_feed = _build_dashboard_recent_feed(
        recent_proposals,
        recent_ppms,
        recent_tpscopes,
        recent_siding_estimates,
        recent_roofing_estimates,
        recent_gutter_estimates,
        recent_painting_estimates,
    )
    sales_lane_open = user_role in ('consultant', 'office_manager', 'admin')
    production_lane_open = user_role in ('pm', 'office_manager', 'admin')
    team_view = user.get('team_view', False)
    team_view_scope = user.get('team_view_scope')
    psc_training_stats = None
    psc_training_enrolled = is_psc_training_enrolled(user_key)
    if psc_training_enrolled:
        psc_training_stats = compute_psc_training_stats(user_key)
    psc_training_oversight = can_psc_training_oversight(user_key)
    # PM training: open to everyone (under construction); progress optional
    pm_training_stats = compute_pm_training_stats(user_key)
    pm_training_oversight = can_pm_training_oversight(user_key)
    pm_training_open = True
    unread_feedback = 0
    unread_diffs = 0
    pricing_summary = None
    if is_admin:
        unread_feedback, unread_diffs = _admin_inbox_counts()
        pricing_summary = _pricing_summary_for_dashboard()
    # Field Ask PPS only on dashboard — same queue rules for everyone (no curator admin UI).
    ask_pps_prompt = ask_pps.get_next_prompt_for_user(get_db, USERS, user_key, user_role)
    ask_pps_prompt_queue = len(
        ask_pps.get_prompts_for_user(
            get_db, USERS, user_key, user_role, include_all_for_curator=False,
        )
    )
    user_notifications = ask_pps.get_unread_notifications(get_db, user_key)
    return render_template(
        'dashboard.html',
        user=user,
        user_key=user_key,
        user_role=user_role,
        ask_pps_prompt=ask_pps_prompt,
        ask_pps_prompt_queue=ask_pps_prompt_queue,
        user_notifications=user_notifications,
        sales_lane_open=sales_lane_open,
        production_lane_open=production_lane_open,
        admin_lane_open=is_admin,
        team_view=team_view,
        team_view_scope=team_view_scope,
        consultants=accessible_consultants,
        recent_proposals=recent_proposals,
        recent_ppms=recent_ppms,
        recent_tpscopes=recent_tpscopes,
        recent_feed=recent_feed,
        date_events=date_events,
        psc_training_stats=psc_training_stats,
        psc_training_enrolled=psc_training_enrolled,
        psc_training_oversight=psc_training_oversight,
        pm_training_stats=pm_training_stats,
        pm_training_oversight=pm_training_oversight,
        pm_training_open=pm_training_open,
        unread_feedback=unread_feedback,
        unread_diffs=unread_diffs,
        pricing_summary=pricing_summary,
        proposal_url=os.environ.get('PROPOSAL_URL', 'https://pps-proposal-tool.onrender.com'),
        runway_available=(user_key == RUNWAY_OWNER),
    )


@app.route('/routelab/logos')
def routelab_logo_gallery():
    """RouteLab logo concept gallery — static assets, no login required."""
    return send_from_directory(
        os.path.join(app.root_path, 'static', 'routelab'),
        'index.html',
    )


@app.route('/runway')
@app.route('/airline')
@require_runway_access
def runway_game():
    """Airline startup sim — public when RUNWAY_PUBLIC_ACCESS or share token is set."""
    return render_template(
        'runway.html',
        bootstrap_json=json.dumps(get_runway_bootstrap()),
        mapbox_token=RUNWAY_MAPBOX_TOKEN,
    )


@app.route('/estimating/property-lookup')
@require_login
def estimating_property_lookup():
    """Search hub clients and past jobs by address — not external measurement APIs."""
    q = (request.args.get('q') or '').strip()
    try:
        from estimators.property_lookup import lookup_property_by_address
        return jsonify(lookup_property_by_address(get_db, q))
    except Exception as e:
        import traceback
        traceback.print_exc()
        return _api_error(e, results=[])


@app.route('/estimating/confidence', methods=['POST'])
@require_login
def estimating_confidence():
    """Return takeoff reliability metadata for gutter, roofing, or siding."""
    data = request.get_json(silent=True) or {}
    tool = (data.get('tool') or '').strip()
    try:
        from estimators.reliability import (
            build_gutter_reliability,
            build_painting_reliability,
            build_roofing_reliability,
            build_siding_job_reliability,
            build_siding_reliability,
        )
        if tool == 'gutter':
            confidence = build_gutter_reliability(
                data.get('measurements') or {},
                data.get('inputs') or {},
                data.get('user_overrides') or {},
            )
        elif tool == 'roofing':
            confidence = build_roofing_reliability(
                data.get('measurements') or {},
                data.get('inputs') or {},
            )
        elif tool == 'siding':
            buildings = data.get('buildings') or []
            if buildings:
                confidence = build_siding_job_reliability(
                    buildings,
                    int(data.get('pricing_loaded') or 0),
                )
            else:
                confidence = build_siding_reliability(
                    data.get('measurements') or {},
                    data.get('source') or 'eagleview',
                    int(data.get('pricing_loaded') or 0),
                )
        elif tool == 'painting':
            confidence = build_painting_reliability(
                data.get('measurements') or {},
                data.get('line_items') or [],
                data.get('user_overrides') or {},
            )
        else:
            return jsonify({'error': 'Unknown tool'}), 400
        return jsonify({'confidence': confidence})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return _api_error(e)


@app.route('/estimating')
@require_login
def estimating_hub():
    user_key = session['user_key']
    recent_siding = []
    recent_roofing = []
    recent_gutters = []
    recent_painting = []
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                '''SELECT id, property_name, building_count, generated_at
                   FROM siding_estimate_log WHERE generated_by = %s
                   ORDER BY generated_at DESC LIMIT 5''',
                (user_key,),
            )
            recent_siding = cur.fetchall()
            cur.execute(
                '''SELECT id, property_name, report_type, generated_at
                   FROM roofing_estimate_log WHERE generated_by = %s
                   ORDER BY generated_at DESC LIMIT 5''',
                (user_key,),
            )
            recent_roofing = cur.fetchall()
            cur.execute(
                '''SELECT id, property_name, gutter_lf, generated_at
                   FROM gutter_estimate_log WHERE generated_by = %s
                   ORDER BY generated_at DESC LIMIT 5''',
                (user_key,),
            )
            recent_gutters = cur.fetchall()
            cur.execute(
                '''SELECT id, property_name, line_count, one_coat_bid, two_coat_bid, generated_at
                   FROM painting_estimate_log WHERE generated_by = %s
                   ORDER BY generated_at DESC LIMIT 5''',
                (user_key,),
            )
            recent_painting = cur.fetchall()
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Estimating hub error: {e}")
    return render_template(
        'estimating.html',
        recent_siding=recent_siding,
        recent_roofing=recent_roofing,
        recent_gutters=recent_gutters,
        recent_painting=recent_painting,
    )


@app.route('/log-proposal', methods=['POST'])
def log_proposal():
    """Called by proposal tool after successful generation."""
    data = request.get_json()
    api_key = request.headers.get('X-API-Key', '')
    if api_key != INTERNAL_API_KEY:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO proposal_log
                (generated_by, consultant_key, consultant_name, client_name,
                 property_name, property_address, property_type, template_type,
                 proposal_number, existing_issue, intended_outcome, scopes_selected, scope_notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                data.get('generated_by'),
                data.get('consultant_key'),
                data.get('consultant_name'),
                data.get('client_name'),
                data.get('property_name'),
                data.get('property_address', ''),
                data.get('property_type'),
                data.get('template_type'),
                data.get('proposal_number', ''),
                data.get('existing_issue', ''),
                data.get('intended_outcome', ''),
                data.get('scopes_selected', ''),
                data.get('scope_notes', ''),
            ))
            conn.commit()
            cur.close()
            conn.close()
            sync_proposal_number_sequence(
                data.get('consultant_key') or '',
                data.get('proposal_number') or '',
            )
            _touch_last_active(data.get('generated_by'))
        return jsonify({'success': True})
    except Exception as e:
        print(f"Log proposal error: {e}")
        return _api_error(e)


def _get_proposal_log_for_document(cur, document_id):
    cur.execute('''
        SELECT pl.*, d.filename, d.mime_type, d.size_bytes, d.user_key AS doc_user_key
        FROM documents d
        JOIN proposal_log pl ON pl.id = d.log_id
        WHERE d.id = %s AND d.doc_type = 'proposal'
    ''', (document_id,))
    return cur.fetchone()


def _user_can_download_proposal(user_key, role, row):
    if not row:
        return False
    if role == 'admin':
        return True
    if row.get('generated_by') == user_key:
        return True
    # Consultants with shared proposal access may download team proposals they generated
    return row.get('doc_user_key') == user_key


def _user_can_access_proposal_log(user_key, role, row):
    if not row:
        return False
    if role == 'admin':
        return True
    return row.get('generated_by') == user_key


@app.route('/api/proposals/next-number')
def proposal_next_number():
    """Suggest the next proposal number for a consultant (INITIALS + YY + XXX); does not reserve."""
    if not _internal_api_ok():
        return jsonify({'error': 'Unauthorized'}), 401
    consultant_key = _normalize_consultant_key(request.args.get('consultant_key', ''))
    if not consultant_key:
        return jsonify({'error': 'consultant_key required'}), 400
    number, err = peek_next_proposal_number(consultant_key)
    if err:
        return jsonify({'error': err}), 400
    return jsonify({
        'success': True,
        'proposal_number': number,
        'consultant_key': consultant_key,
        'format': 'INITIALS + 2-digit year + 3-digit sequence (e.g. TE26001)',
    })


@app.route('/api/proposals/<int:log_id>/prefill')
def proposal_prefill(log_id):
    """Return saved proposal metadata for regenerating in the proposal tool."""
    user_key = session.get('user_key')
    role = session.get('role', '')
    if _internal_api_ok():
        user_key = user_key or request.args.get('user_key', '').strip()
        if user_key:
            role = USERS.get(user_key, {}).get('role', role)
    if not user_key:
        return jsonify({'error': 'Not authenticated'}), 401

    try:
        conn = get_db()
        if not conn:
            return jsonify({'error': 'Database unavailable'}), 503
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('SELECT * FROM proposal_log WHERE id = %s', (log_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return jsonify({'error': 'Proposal not found'}), 404
        if not _user_can_access_proposal_log(user_key, role, row):
            return jsonify({'error': 'Permission denied'}), 403

        scopes = []
        if row.get('scopes_selected'):
            scopes = [s.strip() for s in row['scopes_selected'].split(',') if s.strip()]

        scope_details = []
        if row.get('scope_details'):
            try:
                parsed = json.loads(row['scope_details'])
                if isinstance(parsed, list):
                    scope_details = parsed
            except Exception:
                scope_details = [s.strip() for s in row['scope_details'].split(',') if s.strip()]

        pricing_lines = []
        if row.get('pricing_json'):
            try:
                parsed = json.loads(row['pricing_json'])
                if isinstance(parsed, list):
                    pricing_lines = parsed
            except Exception:
                pass

        return jsonify({
            'success': True,
            'consultant_key': row.get('consultant_key') or '',
            'client_name': row.get('client_name') or row.get('property_name') or '',
            'contact_name': row.get('contact_name') or '',
            'contact_email': row.get('contact_email') or '',
            'company': row.get('company') or '',
            'address': row.get('property_address') or '',
            'property_type': row.get('property_type') or '',
            'template_type': row.get('template_type') or 'short',
            'scope_style': row.get('scope_style') or 'bullets',
            'proposal_number': row.get('proposal_number') or '',
            'proposal_date': row.get('proposal_date') or '',
            'expiry_date': row.get('expiry_date') or '',
            'existing_issue': row.get('existing_issue') or '',
            'intended_outcome': row.get('intended_outcome') or '',
            'scopes': scopes,
            'scope_details': scope_details,
            'other_scope': row.get('other_scope') or '',
            'scope_notes': row.get('scope_notes') or '',
            'pricing_lines': pricing_lines,
            'warranty_pps': row.get('warranty_pps') or '',
            'warranty_mfg': row.get('warranty_mfg') or '',
            'contract_total': row.get('contract_total') or '',
            'has_file': bool(row.get('document_id')),
            'document_id': row.get('document_id'),
        })
    except Exception as e:
        print(f"Proposal prefill error: {e}")
        return _api_error(e)


@app.route('/api/vault/proposals', methods=['POST'])
def vault_store_proposal():
    """Store a generated proposal file and metadata atomically."""
    if not _internal_api_ok():
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json() or {}
    user_key = (data.get('user_key') or '').strip()
    if not user_key:
        return jsonify({'error': 'user_key required'}), 400

    filename = (data.get('filename') or 'PPS_Proposal.docx').strip()
    file_b64 = data.get('file_base64') or ''
    if not file_b64:
        return jsonify({'error': 'file_base64 required'}), 400

    try:
        file_bytes = base64.b64decode(file_b64)
    except Exception:
        return jsonify({'error': 'Invalid file_base64 payload'}), 400

    if len(file_bytes) > MAX_DOCUMENT_BYTES:
        return jsonify({'error': f'File exceeds {MAX_DOCUMENT_BYTES // (1024*1024)} MB limit'}), 413
    if len(file_bytes) < 100:
        return jsonify({'error': 'File too small or empty'}), 400

    mime_type = data.get('mime_type') or 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

    try:
        conn = get_db()
        if not conn:
            return jsonify({'error': 'Database unavailable'}), 503
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO proposal_log
            (generated_by, consultant_key, consultant_name, client_name,
             property_name, property_address, property_type, template_type, scope_style,
             proposal_number, existing_issue, intended_outcome, scopes_selected, scope_notes,
             contact_name, contact_email, company, scope_details, other_scope,
             pricing_json, warranty_pps, warranty_mfg, proposal_date, expiry_date, contract_total)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            data.get('generated_by') or user_key,
            data.get('consultant_key'),
            data.get('consultant_name'),
            data.get('client_name'),
            data.get('property_name'),
            data.get('property_address', ''),
            data.get('property_type'),
            data.get('template_type'),
            data.get('scope_style', 'bullets'),
            data.get('proposal_number', ''),
            data.get('existing_issue', ''),
            data.get('intended_outcome', ''),
            data.get('scopes_selected', ''),
            data.get('scope_notes', ''),
            data.get('contact_name', ''),
            data.get('contact_email', ''),
            data.get('company', ''),
            data.get('scope_details', ''),
            data.get('other_scope', ''),
            data.get('pricing_json', ''),
            data.get('warranty_pps', ''),
            data.get('warranty_mfg', ''),
            data.get('proposal_date', ''),
            data.get('expiry_date', ''),
            data.get('contract_total', ''),
        ))
        log_id = cur.fetchone()[0]

        cur.execute('''
            INSERT INTO documents
            (doc_type, log_id, user_key, filename, mime_type, size_bytes, file_data)
            VALUES ('proposal', %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (log_id, user_key, filename, mime_type, len(file_bytes), psycopg2.Binary(file_bytes)))
        document_id = cur.fetchone()[0]

        cur.execute('UPDATE proposal_log SET document_id = %s WHERE id = %s', (document_id, log_id))
        conn.commit()
        cur.close()
        conn.close()
        sync_proposal_number_sequence(
            data.get('consultant_key') or '',
            data.get('proposal_number') or '',
        )
        _touch_last_active(data.get('generated_by') or user_key)
        return jsonify({'success': True, 'log_id': log_id, 'document_id': document_id})
    except Exception as e:
        print(f"Vault store error: {e}")
        return _api_error(e)


@app.route('/api/documents/<int:document_id>/download')
def document_download(document_id):
    """Download a vaulted document — hub session or internal API proxy."""
    user_key = session.get('user_key')
    role = session.get('role', '')
    internal = _internal_api_ok()
    if internal:
        user_key = request.args.get('user_key', user_key)
        role = USERS.get(user_key, {}).get('role', role)

    if not user_key:
        return jsonify({'error': 'Not authenticated'}), 401

    try:
        conn = get_db()
        if not conn:
            return jsonify({'error': 'Database unavailable'}), 503
        cur = conn.cursor(cursor_factory=RealDictCursor)
        row = _get_proposal_log_for_document(cur, document_id)
        if not row:
            cur.close()
            conn.close()
            return jsonify({'error': 'Document not found'}), 404
        if not _user_can_download_proposal(user_key, role, row):
            cur.close()
            conn.close()
            return jsonify({'error': 'Permission denied'}), 403

        cur.execute(
            'SELECT filename, mime_type, file_data FROM documents WHERE id = %s',
            (document_id,)
        )
        doc = cur.fetchone()
        cur.close()
        conn.close()
        if not doc or not doc.get('file_data'):
            return jsonify({'error': 'File data missing'}), 404

        return send_file(
            BytesIO(bytes(doc['file_data'])),
            as_attachment=True,
            download_name=doc['filename'],
            mimetype=doc['mime_type'],
        )
    except Exception as e:
        print(f"Document download error: {e}")
        return _api_error(e)


@app.route('/log-ppm', methods=['POST'])
def log_ppm():
    """Called by PPM tool after generation."""
    data = request.get_json()
    api_key = request.headers.get('X-API-Key', '')
    if api_key != INTERNAL_API_KEY:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor()
            cur.execute(
                '''INSERT INTO ppm_log
                   (generated_by, property_name, pm_key, pm_name,
                    property_address, client_name, proposal_number, total_value,
                    proposal_date, proj_type, scale, client_type, occupied)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                (
                    data.get('generated_by'),
                    data.get('property_name'),
                    data.get('pm_key', ''),
                    data.get('pm_name', ''),
                    data.get('property_address', ''),
                    data.get('client_name', ''),
                    data.get('proposal_number', ''),
                    data.get('total_value', ''),
                    data.get('proposal_date', ''),
                    data.get('proj_type', ''),
                    data.get('scale', ''),
                    data.get('client_type', ''),
                    data.get('occupied', ''),
                )
            )
            conn.commit()
            cur.close()
            conn.close()
            _touch_last_active(data.get('generated_by'))
        return jsonify({'success': True})
    except Exception as e:
        return _api_error(e)


@app.route('/session-info')
def session_info():
    """Called by proposal/profile tools to get current user session."""
    user_key = session.get('user_key')
    if not user_key:
        return jsonify({'authenticated': False})
    user = USERS.get(user_key, {})
    return jsonify({
        'authenticated': True,
        'user_key': user_key,
        'display_name': session.get('display_name'),
        'role': session.get('role'),
        'proposal_access': get_user_proposal_access(user_key),
    })


def _fetch_admin_breakdown(cur):
    """Trade/template activity breakdown for admin dashboard."""
    breakdown = {}
    queries = {
        'property_types': '''
            SELECT COALESCE(NULLIF(TRIM(property_type), ''), 'Unknown') AS label, COUNT(*) AS cnt
            FROM proposal_log GROUP BY 1 ORDER BY cnt DESC LIMIT 14
        ''',
        'templates': '''
            SELECT COALESCE(NULLIF(TRIM(template_type), ''), 'Unknown') AS label, COUNT(*) AS cnt
            FROM proposal_log GROUP BY 1 ORDER BY cnt DESC LIMIT 14
        ''',
        'ppm_types': '''
            SELECT COALESCE(NULLIF(TRIM(proj_type), ''), 'Unknown') AS label, COUNT(*) AS cnt
            FROM ppm_log GROUP BY 1 ORDER BY cnt DESC LIMIT 14
        ''',
        'tps_languages': '''
            SELECT COALESCE(NULLIF(TRIM(language), ''), 'Unknown') AS label, COUNT(*) AS cnt
            FROM subscope_log GROUP BY 1 ORDER BY cnt DESC LIMIT 14
        ''',
    }
    for key, sql in queries.items():
        try:
            cur.execute(sql)
            breakdown[key] = cur.fetchall()
        except Exception:
            breakdown[key] = []
    return breakdown


def _fetch_vault_summary(cur):
    """Vault storage stats and file list (no binary payload)."""
    vault = {
        'files': [],
        'file_count': 0,
        'total_bytes': 0,
        'proposals_with_file': 0,
        'proposals_total': 0,
    }
    try:
        cur.execute('SELECT COUNT(*) AS c, COALESCE(SUM(size_bytes), 0) AS b FROM documents')
        row = cur.fetchone()
        vault['file_count'] = row['c'] or 0
        vault['total_bytes'] = row['b'] or 0
        cur.execute('SELECT COUNT(*) AS c FROM proposal_log')
        vault['proposals_total'] = cur.fetchone()['c'] or 0
        cur.execute('SELECT COUNT(*) AS c FROM proposal_log WHERE document_id IS NOT NULL')
        vault['proposals_with_file'] = cur.fetchone()['c'] or 0
        vault['proposals_missing_file'] = max(0, vault['proposals_total'] - vault['proposals_with_file'])
        cur.execute(
            """SELECT COUNT(*) AS c FROM proposal_log
               WHERE document_id IS NULL AND generated_at >= NOW() - INTERVAL '7 days'"""
        )
        vault['recent_missing_file'] = cur.fetchone()['c'] or 0
        cur.execute('''
            SELECT d.id, d.doc_type, d.filename, d.size_bytes, d.created_at, d.user_key, d.log_id,
                   pl.property_name, pl.consultant_name, pl.generated_by
            FROM documents d
            LEFT JOIN proposal_log pl ON pl.id = d.log_id AND d.doc_type = 'proposal'
            ORDER BY d.created_at DESC
            LIMIT 100
        ''')
        vault['files'] = cur.fetchall()

        limit = VAULT_STORAGE_LIMIT_BYTES
        used = vault['total_bytes'] or 0
        used_pct = min(100, round(used / limit * 100)) if limit else 0
        vault['storage_limit_bytes'] = limit
        vault['storage_used_bytes'] = used
        vault['storage_used_pct'] = used_pct
        vault['storage_remaining_pct'] = max(0, 100 - used_pct)
        vault['storage_used_mb'] = round(used / (1024 * 1024), 1)
        vault['storage_limit_mb'] = int(limit / (1024 * 1024))
        vault['storage_remaining_mb'] = round(max(0, limit - used) / (1024 * 1024), 1)
    except Exception as e:
        print(f"Vault summary error: {e}")
    return vault


def _serialize_dt(val):
    if not val:
        return ''
    return val.strftime('%Y-%m-%d') if hasattr(val, 'strftime') else str(val)


def _format_activity_date(val):
    if not val:
        return '—'
    if hasattr(val, 'strftime'):
        return val.strftime('%B %d, %Y')
    return str(val)


def _format_activity_by(user_key):
    if not user_key:
        return '—'
    return str(user_key).replace('_', ' ').title()


def _format_template_label(val):
    if not val:
        return '—'
    v = str(val).strip().lower()
    if v in ('short', 'standard'):
        return 'Standard'
    if v in ('full', 'long', 'comprehensive'):
        return 'Comprehensive'
    return str(val)


@app.template_filter('template_label')
def _template_label_filter(val):
    return _format_template_label(val)


def _can_view_activity_row(user_key, role, activity_type, row):
    if role == 'admin':
        return True
    if row.get('generated_by') == user_key:
        return True
    if activity_type == 'ppm' and row.get('pm_key') == user_key:
        return True
    return False


def _activity_detail_row(label, value):
    val = value if value not in (None, '') else '—'
    return {'label': label, 'value': val}


def _activity_detail_payload(activity_type, row):
    """Normalize a DB row into a JSON payload for activity detail modals."""
    if activity_type == 'proposal':
        return {
            'type': 'proposal',
            'title': row.get('property_name') or row.get('client_name') or 'Unnamed',
            'rows': [
                _activity_detail_row('Proposal #', row.get('proposal_number')),
                _activity_detail_row('Address', row.get('property_address')),
                _activity_detail_row('Consultant', row.get('consultant_name')),
                _activity_detail_row('Generated By', _format_activity_by(row.get('generated_by'))),
                _activity_detail_row('Property Type', row.get('property_type')),
                _activity_detail_row('Template', _format_template_label(row.get('template_type'))),
                _activity_detail_row('Scopes', row.get('scopes_selected')),
                _activity_detail_row('Date', _format_activity_date(row.get('generated_at'))),
            ],
            'issue': row.get('existing_issue') or '',
            'outcome': row.get('intended_outcome') or '',
            'notes': row.get('scope_notes') or '',
            'document_id': row.get('document_id'),
            'log_id': row.get('id'),
        }
    if activity_type == 'ppm':
        details = ' · '.join(x for x in [
            row.get('scale'),
            row.get('client_type'),
            row.get('occupied'),
            row.get('total_value'),
        ] if x and x != '—') or '—'
        prop_date = row.get('proposal_date')
        generated = _format_activity_date(row.get('generated_at'))
        date_val = f"{prop_date} (generated {generated})" if prop_date and prop_date != '—' else generated
        return {
            'type': 'ppm',
            'title': row.get('property_name') or row.get('client_name') or 'Unnamed',
            'rows': [
                _activity_detail_row('Proposal #', row.get('proposal_number')),
                _activity_detail_row('Address', row.get('property_address')),
                _activity_detail_row('Client', row.get('client_name')),
                _activity_detail_row('Project Manager', row.get('pm_name')),
                _activity_detail_row('Project Type', row.get('proj_type')),
                _activity_detail_row('Details', details),
                _activity_detail_row('Generated By', _format_activity_by(row.get('generated_by'))),
                _activity_detail_row('Date', date_val),
            ],
        }
    if activity_type == 'tps':
        lang = (row.get('language') or '').title() or '—'
        mat = row.get('material_provider')
        mat_label = 'TP materials' if mat == 'tp' else 'PPS materials' if mat == 'pps' else (mat or '—')
        return {
            'type': 'tps',
            'title': row.get('property_name') or 'Unnamed',
            'rows': [
                _activity_detail_row('PO #', row.get('po_number')),
                _activity_detail_row('Address', row.get('property_address')),
                _activity_detail_row('Consultant', row.get('consultant_name')),
                _activity_detail_row('Project Manager', row.get('pm_name')),
                _activity_detail_row('Details', ' · '.join(x for x in [lang, mat_label] if x and x != '—') or '—'),
                _activity_detail_row('Generated By', _format_activity_by(row.get('generated_by'))),
                _activity_detail_row('Date', _format_activity_date(row.get('generated_at'))),
            ],
            'notes': (
                f"Source proposal: {row.get('proposal_filename')}"
                if row.get('proposal_filename') and row.get('proposal_filename') != '—'
                else ''
            ),
        }
    if activity_type == 'site_visit':
        rows_out = [
            _activity_detail_row('Address', row.get('property_address')),
            _activity_detail_row('Visit Date', row.get('visit_date')),
            _activity_detail_row('Time', row.get('visit_time')),
            _activity_detail_row('Visited By', row.get('display_name')),
            _activity_detail_row('PO / Proposal #', row.get('po_number')),
        ]
        if row.get('trade_partner_company'):
            rows_out.append(_activity_detail_row('Trade Partner', row.get('trade_partner_company')))
        if row.get('crew_lead'):
            rows_out.append(_activity_detail_row('Crew Lead', row.get('crew_lead')))
        if row.get('staff_contact'):
            rows_out.append(_activity_detail_row('Onsite Contact', row.get('staff_contact')))
        if row.get('topics_discussed'):
            rows_out.append(_activity_detail_row('Topics', row.get('topics_discussed')))
        if row.get('complaints_received') == 'yes' and row.get('complaint_details'):
            rows_out.append(_activity_detail_row('Complaint', row.get('complaint_details')))
        rows_out.append(_activity_detail_row('Submitted', _format_activity_date(row.get('generated_at'))))
        checklist = row.get('checklist')
        if isinstance(checklist, str):
            try:
                checklist = json.loads(checklist)
            except Exception:
                checklist = []
        return {
            'type': 'site_visit',
            'title': row.get('property_name') or 'Unnamed',
            'rows': rows_out,
            'observations': row.get('observations') or '',
            'checklist': checklist or [],
            'download_url': f"/site-visit/download/{row.get('id')}",
        }
    return None


ACTIVITY_DETAIL_TABLES = {
    'proposal': 'proposal_log',
    'ppm': 'ppm_log',
    'tps': 'subscope_log',
    'site_visit': 'site_visit_log',
}


@app.route('/api/activity-detail/<activity_type>/<int:record_id>')
@require_login
def activity_detail(activity_type, record_id):
    table = ACTIVITY_DETAIL_TABLES.get(activity_type)
    if not table:
        return jsonify({'error': 'Unknown activity type'}), 400
    user_key = session.get('user_key')
    role = session.get('role')
    try:
        conn = get_db()
        if not conn:
            return jsonify({'error': 'Database unavailable'}), 503
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(f'SELECT * FROM {table} WHERE id = %s', (record_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return jsonify({'error': 'Not found'}), 404
        if not _can_view_activity_row(user_key, role, activity_type, row):
            return jsonify({'error': 'Forbidden'}), 403
        payload = _activity_detail_payload(activity_type, row)
        if not payload:
            return jsonify({'error': 'Unsupported activity type'}), 400
        return jsonify(payload)
    except Exception as e:
        print(f"Activity detail error: {e}")
        return _api_error(e)


def _admin_search(cur, query, limit=50):
    """Search proposals, PPMs, TPS, site visits, and clients."""
    q = (query or '').strip()
    if len(q) < 2:
        return []
    pattern = f'%{q}%'
    per_type = max(6, limit // 5)
    results = []

    def _add(result_type, row, title, meta, date_val, link='', document_id=None):
        results.append({
            'type': result_type,
            'id': row.get('id'),
            'title': title or 'Unnamed',
            'meta': meta,
            'date': _serialize_dt(date_val),
            'link': link,
            'document_id': document_id,
        })

    try:
        cur.execute('''
            SELECT id, property_name, client_name, property_address, consultant_name,
                   proposal_number, generated_by, generated_at, document_id
            FROM proposal_log
            WHERE property_name ILIKE %s OR client_name ILIKE %s OR property_address ILIKE %s
               OR proposal_number ILIKE %s OR consultant_name ILIKE %s OR scopes_selected ILIKE %s
               OR COALESCE(generated_by, '') ILIKE %s
            ORDER BY generated_at DESC LIMIT %s
        ''', (pattern,) * 7 + (per_type,))
        for r in cur.fetchall():
            _add(
                'proposal',
                r,
                r.get('property_name') or r.get('client_name'),
                ' · '.join(filter(None, [
                    r.get('consultant_name'),
                    r.get('proposal_number'),
                    (r.get('generated_by') or '').replace('_', ' ').title(),
                ])),
                r.get('generated_at'),
                '/admin/proposals',
                r.get('document_id'),
            )
    except Exception as e:
        print(f"Search proposals error: {e}")

    try:
        cur.execute('''
            SELECT id, property_name, property_address, client_name, proposal_number,
                   pm_name, proj_type, generated_by, generated_at
            FROM ppm_log
            WHERE property_name ILIKE %s OR property_address ILIKE %s OR client_name ILIKE %s
               OR proposal_number ILIKE %s OR pm_name ILIKE %s OR proj_type ILIKE %s
               OR COALESCE(generated_by, '') ILIKE %s
            ORDER BY generated_at DESC LIMIT %s
        ''', (pattern,) * 7 + (per_type,))
        for r in cur.fetchall():
            _add(
                'ppm',
                r,
                r.get('property_name'),
                ' · '.join(filter(None, [r.get('pm_name'), r.get('proj_type'), (r.get('generated_by') or '').replace('_', ' ').title()])),
                r.get('generated_at'),
            )
    except Exception as e:
        print(f"Search PPM error: {e}")

    try:
        cur.execute('''
            SELECT id, property_name, property_address, consultant_name, pm_name,
                   po_number, language, generated_by, generated_at
            FROM subscope_log
            WHERE property_name ILIKE %s OR property_address ILIKE %s OR consultant_name ILIKE %s
               OR pm_name ILIKE %s OR po_number ILIKE %s OR language ILIKE %s
               OR COALESCE(generated_by, '') ILIKE %s
            ORDER BY generated_at DESC LIMIT %s
        ''', (pattern,) * 7 + (per_type,))
        for r in cur.fetchall():
            _add(
                'tps',
                r,
                r.get('property_name'),
                ' · '.join(filter(None, [
                    r.get('consultant_name'),
                    r.get('language', '').title() if r.get('language') else '',
                    f"PO {r['po_number']}" if r.get('po_number') else '',
                ])),
                r.get('generated_at'),
                '/admin/tpscopes',
            )
    except Exception as e:
        print(f"Search TPS error: {e}")

    try:
        cur.execute('''
            SELECT id, property_name, property_address, display_name, po_number, generated_by, generated_at
            FROM site_visit_log
            WHERE property_name ILIKE %s OR property_address ILIKE %s OR display_name ILIKE %s
               OR po_number ILIKE %s OR COALESCE(generated_by, '') ILIKE %s
               OR COALESCE(observations, '') ILIKE %s
            ORDER BY generated_at DESC LIMIT %s
        ''', (pattern,) * 6 + (per_type,))
        for r in cur.fetchall():
            _add(
                'site_visit',
                r,
                r.get('property_name'),
                ' · '.join(filter(None, [r.get('display_name'), r.get('po_number')])),
                r.get('generated_at'),
                '/admin/site-visits',
            )
    except Exception as e:
        print(f"Search site visit error: {e}")

    try:
        cur.execute('''
            SELECT id, name, company, property_name, address, email, added_by, updated_at
            FROM clients
            WHERE name ILIKE %s OR company ILIKE %s OR property_name ILIKE %s
               OR address ILIKE %s OR email ILIKE %s OR COALESCE(added_by, '') ILIKE %s
            ORDER BY updated_at DESC LIMIT %s
        ''', (pattern,) * 6 + (per_type,))
        for r in cur.fetchall():
            _add(
                'client',
                r,
                r.get('name') or r.get('property_name'),
                ' · '.join(filter(None, [r.get('company'), r.get('email'), (r.get('added_by') or '').replace('_', ' ').title()])),
                r.get('updated_at'),
                '/clients',
            )
    except Exception as e:
        print(f"Search clients error: {e}")

    return results[:limit]


@app.route('/admin')
@require_admin
def admin():
    rows = []
    all_proposals = []
    all_ppms = []
    all_subscopes = []
    unread_feedback, _ = _admin_inbox_counts()
    client_count = 0
    proposals_30d = ppms_30d = subscopes_30d = 0
    breakdown = {}
    vault = {
        'files': [], 'file_count': 0, 'total_bytes': 0,
        'proposals_with_file': 0, 'proposals_total': 0,
        'proposals_missing_file': 0, 'recent_missing_file': 0,
        'storage_limit_bytes': VAULT_STORAGE_LIMIT_BYTES,
        'storage_used_bytes': 0, 'storage_used_pct': 0,
        'storage_remaining_pct': 100, 'storage_used_mb': 0,
        'storage_limit_mb': int(VAULT_STORAGE_LIMIT_BYTES / (1024 * 1024)),
        'storage_remaining_mb': int(VAULT_STORAGE_LIMIT_BYTES / (1024 * 1024)),
    }
    system_health = {'ok': False, 'checks': []}
    ask_pps_pending_cnt = 0
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('SELECT * FROM hub_users ORDER BY display_name')
            rows = cur.fetchall()
            cur.execute('SELECT * FROM proposal_log ORDER BY generated_at DESC LIMIT 50')
            all_proposals = cur.fetchall()
            cur.execute('SELECT * FROM ppm_log ORDER BY generated_at DESC LIMIT 50')
            all_ppms = cur.fetchall()
            cur.execute('SELECT * FROM subscope_log ORDER BY generated_at DESC LIMIT 50')
            all_subscopes = cur.fetchall()
            cur.execute("SELECT COUNT(*) AS c FROM proposal_log WHERE generated_at >= NOW() - INTERVAL '30 days'")
            proposals_30d = cur.fetchone()['c'] or 0
            cur.execute("SELECT COUNT(*) AS c FROM ppm_log WHERE generated_at >= NOW() - INTERVAL '30 days'")
            ppms_30d = cur.fetchone()['c'] or 0
            cur.execute("SELECT COUNT(*) AS c FROM subscope_log WHERE generated_at >= NOW() - INTERVAL '30 days'")
            subscopes_30d = cur.fetchone()['c'] or 0
            breakdown = _fetch_admin_breakdown(cur)
            vault = _fetch_vault_summary(cur)
            try:
                cur.execute('SELECT COUNT(*) as cnt FROM clients')
                client_count = cur.fetchone()['cnt']
            except Exception:
                pass
            try:
                cur.execute(
                    "SELECT COUNT(*) AS c FROM knowledge_entries WHERE status = 'pending'"
                )
                ask_pps_pending_cnt = cur.fetchone()['c'] or 0
            except Exception:
                ask_pps_pending_cnt = 0
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Admin error: {e}")

    # Annotate lockouts so admin can unlock stuck teammates at a glance.
    annotated = []
    for row in rows:
        item = dict(row)
        try:
            locked, fails, mins = is_login_locked(get_db, item.get('user_key'))
            item['login_locked'] = locked
            item['login_failures'] = fails
            item['login_mins_left'] = mins
        except Exception:
            item['login_locked'] = False
            item['login_failures'] = 0
            item['login_mins_left'] = None
        item['missing_hub_row'] = False
        annotated.append(item)
    rows = annotated

    # Ensure every USERS profile appears even if hub_users row is missing (can't log in).
    present = {r.get('user_key') for r in rows}
    for key, udef in USERS.items():
        if key in present:
            continue
        locked, fails, mins = is_login_locked(get_db, key)
        rows.append({
            'user_key': key,
            'display_name': udef.get('display', key),
            'role': udef.get('role', ''),
            'last_login': None,
            'must_change_password': False,
            'missing_hub_row': True,
            'login_locked': locked,
            'login_failures': fails,
            'login_mins_left': mins,
        })
    rows = sorted(rows, key=lambda r: (r.get('display_name') or '').lower())

    return render_template('admin.html', users=rows, all_proposals=all_proposals,
                           all_ppms=all_ppms, all_subscopes=all_subscopes,
                           unread_feedback=unread_feedback,
                           ask_pps_pending_cnt=ask_pps_pending_cnt,
                           client_count=client_count,
                           proposals_30d=proposals_30d, ppms_30d=ppms_30d, subscopes_30d=subscopes_30d,
                           breakdown=breakdown, vault=vault,
                           user_definitions=USERS,
                           runway_available=(session.get('user_key') == RUNWAY_OWNER))


@app.route('/admin/pricing-defaults', methods=['GET', 'POST'])
@require_admin
def admin_pricing_defaults():
    from estimators.pricing_defaults import save_pricing_defaults, SYSTEM_DEFAULTS

    defaults = _pricing_defaults()
    message = None
    error = None
    if request.method == 'POST':
        try:
            trades = {
                'siding': {
                    'labor_per_sq': request.form.get('siding_labor_per_sq'),
                    'haul_per_sq': request.form.get('siding_haul_per_sq'),
                    'tax_pct': request.form.get('siding_tax_pct'),
                    'delivery': request.form.get('siding_delivery'),
                    'waste_pct': request.form.get('siding_waste_pct'),
                },
                'roofing': {
                    'labor_per_sq': request.form.get('roofing_labor_per_sq'),
                    'material_per_sq': request.form.get('roofing_material_per_sq'),
                    'tax_pct': request.form.get('roofing_tax_pct'),
                    'margin_pct': request.form.get('roofing_margin_pct'),
                    'waste_pct': request.form.get('roofing_waste_pct'),
                    'dump_divisor': request.form.get('roofing_dump_divisor'),
                    'dump_cost': request.form.get('roofing_dump_cost'),
                },
                'gutter': {
                    'gutter_price_per_lf': request.form.get('gutter_price_per_lf'),
                    'guard_price_per_lf': request.form.get('gutter_guard_per_lf'),
                    'labor_per_lf': request.form.get('gutter_labor_per_lf'),
                    'tax_pct': request.form.get('gutter_tax_pct'),
                    'margin_pct': request.form.get('gutter_margin_pct'),
                    'waste_pct': request.form.get('gutter_waste_pct'),
                    'downspout_lf_each': request.form.get('gutter_ds_height'),
                    'downspout_spacing_ft': request.form.get('gutter_ds_spacing'),
                },
                'painting': {
                    'labor_per_hour': request.form.get('painting_labor_per_hour'),
                    'margin_one_coat_pct': request.form.get('painting_margin_one_coat_pct'),
                    'margin_two_coat_pct': request.form.get('painting_margin_two_coat_pct'),
                    'two_coat_multiplier': request.form.get('painting_two_coat_multiplier'),
                },
            }
            defaults = save_pricing_defaults(
                get_db,
                trades,
                session['user_key'],
                session.get('display_name', ''),
            )
            message = 'Pricing defaults saved. New estimates will use these values.'
        except Exception as e:
            error = str(e)

    return render_template(
        'admin_pricing_defaults.html',
        defaults=defaults,
        system_defaults=SYSTEM_DEFAULTS,
        message=message,
        error=error,
    )


@app.route('/admin/system-health')
@require_admin
def admin_system_health():
    """Load system health async — avoids blocking /admin on outbound HTTP (single-worker deadlock)."""
    try:
        return jsonify(_run_system_health_checks())
    except Exception as e:
        print(f"System health error: {e}")
        return jsonify({
            'ok': False,
            'checks': [{'name': 'health_check', 'ok': False, 'error': str(e)}],
        })


@app.route('/admin/daily-digest-test', methods=['POST'])
@require_admin
def admin_daily_digest_test():
    """Send yesterday's digest now (admin smoke test)."""
    from daily_digest import run_daily_digest

    try:
        result = run_daily_digest(
            get_db,
            USERS,
            _format_template_label,
            _send_digest_email,
            force=True,
        )
        status = 200 if result.get('ok') else 500
        return jsonify(result), status
    except Exception as e:
        print(f'Admin digest test error: {e}')
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/admin/search')
@require_admin
def admin_search():
    q = request.args.get('q', '').strip()
    results = []
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            results = _admin_search(cur, q)
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Admin search error: {e}")
        return _api_error(e)
    return jsonify({'query': q, 'results': results, 'count': len(results)})


@app.route('/admin/vault/delete', methods=['POST'])
@require_admin
def admin_vault_delete():
    data = request.get_json(silent=True) or {}
    doc_id = data.get('document_id') or request.form.get('document_id')
    try:
        doc_id = int(doc_id)
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid document_id'}), 400
    try:
        conn = get_db()
        if not conn:
            return jsonify({'error': 'Database unavailable'}), 503
        cur = conn.cursor()
        cur.execute('SELECT id, filename FROM documents WHERE id = %s', (doc_id,))
        row = cur.fetchone()
        if not row:
            cur.close()
            conn.close()
            return jsonify({'error': 'Document not found'}), 404
        cur.execute('UPDATE proposal_log SET document_id = NULL WHERE document_id = %s', (doc_id,))
        cur.execute('DELETE FROM documents WHERE id = %s', (doc_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True, 'deleted_id': doc_id})
    except Exception as e:
        print(f"Vault delete error: {e}")
        return _api_error(e)


@app.route('/admin/reset-password', methods=['POST'])
@require_admin
def admin_reset_password():
    user_key = (request.form.get('user_key') or '').strip()
    new_password = request.form.get('new_password', '')  # do not strip — match login
    if not user_key:
        return jsonify({'error': 'No team member selected. Close and open Reset again.'}), 400
    if not new_password or len(new_password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters.'}), 400
    if user_key not in USERS:
        return jsonify({'error': f'Unknown user “{user_key}”.'}), 400
    try:
        ok, action = _upsert_hub_user_password(user_key, new_password, must_change=False)
        if not ok:
            reason = action or 'unknown'
            friendly = {
                'no_db': (
                    'Cannot reach the database right now. '
                    'Check Admin → System Health (database_connect), then try again in a minute.'
                ),
                'password_too_short': 'Password must be at least 6 characters.',
                'unknown_user': 'Unknown user.',
                'hash_failed': 'Could not encrypt password. Try a different password.',
            }.get(reason)
            if not friendly and reason.startswith('db_error:'):
                friendly = (
                    f'Database rejected the password save ({reason.split(":", 1)[-1]}). '
                    'Try again; if it keeps failing, check System Health.'
                )
            return jsonify({
                'error': friendly or 'Could not save password.',
                'reason': reason,
            }), 503 if reason in ('no_db',) or str(reason).startswith('db_error:') else 400
        # Unlock is best-effort — password is already saved
        unlocked = True
        try:
            clear_login_failures(get_db, user_key)
        except Exception as unlock_err:
            print(f'clear_login_failures after reset failed for {user_key}: {unlock_err}')
            unlocked = False
        return jsonify({
            'success': True,
            'action': action,
            'unlocked': unlocked,
            'user_key': user_key,
            'display': USERS[user_key].get('display'),
        })
    except Exception as e:
        _log_exception(e, 'admin_reset_password')
        return jsonify({
            'error': f'Password reset failed ({type(e).__name__}). Check System Health / database.',
        }), 500


@app.route('/admin/unlock-login', methods=['POST'])
@require_admin
def admin_unlock_login():
    """Clear failed login attempts so a teammate can sign in immediately."""
    user_key = (request.form.get('user_key') or '').strip()
    if not user_key or user_key not in USERS:
        return jsonify({'error': 'Unknown user'}), 400
    try:
        clear_login_failures(get_db, user_key)
        return jsonify({'success': True, 'user_key': user_key})
    except Exception as e:
        return _api_error(e)


@app.route('/api/internal/unlock-login', methods=['POST'])
def internal_unlock_login():
    """Ops helper: clear lockout without an admin browser session."""
    if not _internal_api_ok():
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json(silent=True) or {}
    user_key = (request.form.get('user_key') or data.get('user_key') or '').strip()
    if not user_key or user_key not in USERS:
        return jsonify({'error': 'Unknown user'}), 400
    try:
        clear_login_failures(get_db, user_key)
        return jsonify({
            'success': True,
            'user_key': user_key,
            'display': USERS[user_key].get('display'),
        })
    except Exception as e:
        return _api_error(e)


@app.route('/log-subscope', methods=['POST'])
def log_subscope():
    data = request.get_json()
    api_key = request.headers.get('X-API-Key', '')
    if api_key != INTERNAL_API_KEY:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor()
            cur.execute(
                '''INSERT INTO subscope_log
                   (generated_by, property_name, pm_name, consultant_name, language,
                    property_address, po_number, consultant_key, pm_key,
                    material_provider, proposal_filename)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                (
                    data.get('generated_by'),
                    data.get('property_name'),
                    data.get('pm_name'),
                    data.get('consultant_name'),
                    data.get('language'),
                    data.get('property_address', ''),
                    data.get('po_number', ''),
                    data.get('consultant_key', ''),
                    data.get('pm_key', ''),
                    data.get('material_provider', ''),
                    data.get('proposal_filename', ''),
                )
            )
            conn.commit()
            cur.close()
            conn.close()
            _touch_last_active(data.get('generated_by'))
        return jsonify({'success': True})
    except Exception as e:
        return _api_error(e)


@app.route('/feedback', methods=['POST'])
def submit_feedback():
    if not session.get('user_key'):
        return jsonify({'error': 'Not authenticated'}), 401
    message = request.form.get('message', '').strip()
    if not message:
        return jsonify({'error': 'Message is required'}), 400
    user_key = session['user_key']
    display_name = session.get('display_name', '')
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor()
            cur.execute(
                'INSERT INTO feedback (user_key, display_name, message) VALUES (%s, %s, %s)',
                (user_key, display_name, message)
            )
            conn.commit()
            cur.close()
            conn.close()
        # Send email
        _send_feedback_email(display_name, message)
        return jsonify({'success': True})
    except Exception as e:
        return _api_error(e)


def _hub_notify_recipients():
    """Primary inbox(es) for hub feedback and proposal comparison submissions."""
    raw = os.environ.get('HUB_NOTIFY_EMAIL', 'thomas@purepropsolutions.com')
    return [e.strip() for e in raw.split(',') if e.strip()]


def _send_smtp_email(subject, text_body, html_body=None, recipients=None):
    """Send email via SMTP to the given recipient list."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    if not recipients:
        print(f"SMTP email (no recipients): {subject}\n{text_body}")
        return False

    smtp_host = os.environ.get('SMTP_HOST', '')
    smtp_user = os.environ.get('SMTP_USER', '')
    smtp_pass = os.environ.get('SMTP_PASS', '')
    if not smtp_host:
        print(f"SMTP email:\nSubject: {subject}\nTo: {', '.join(recipients)}\n{text_body}")
        return False

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = smtp_user
        msg['To'] = ', '.join(recipients)
        msg.attach(MIMEText(text_body, 'plain'))
        if html_body:
            msg.attach(MIMEText(html_body, 'html'))
        with smtplib.SMTP_SSL(smtp_host, 465, timeout=30) as s:
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
        return True
    except Exception as e:
        print(f"SMTP email failed: {e}")
        return False


def _send_digest_email(subject, text_body, html_body, recipients):
    """Nightly digest — SMTP first, Resend fallback (password reset uses Resend)."""
    if not recipients:
        return False
    if _send_smtp_email(subject, text_body, html_body, recipients):
        print(f'Daily digest sent via SMTP to {", ".join(recipients)}')
        return True
    if not os.environ.get('RESEND_API_KEY', '').strip():
        print('Daily digest: SMTP failed and Resend is not configured')
        return False
    print(f'Daily digest: SMTP failed, trying Resend for {", ".join(recipients)}')
    ok_all = True
    for addr in recipients:
        ok, detail = _send_resend_email(addr, subject, html_body or '', text_body)
        if ok:
            print(f'Daily digest sent via Resend to {addr} ({detail})')
        else:
            print(f'Daily digest Resend failed for {addr}: {detail}')
            ok_all = False
    return ok_all


def _send_hub_notify_email(subject, text_body, html_body=None):
    """Email hub admin when users submit feedback or voice comparisons."""
    return _send_smtp_email(subject, text_body, html_body, _hub_notify_recipients())


def _send_feedback_email(name, message):
    from html import escape

    admin_url = f"{HUB_PUBLIC_URL.rstrip('/')}/admin/feedback"
    subject = f'PPS Hub Feedback — {name}'
    text_body = f"Feedback from {name}:\n\n{message.strip()}\n\nReview in hub: {admin_url}"
    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;">
      <div style="background:#004C8C;padding:18px 22px;border-radius:8px 8px 0 0;">
        <p style="color:white;font-size:17px;font-weight:600;margin:0;">PPS Hub Feedback</p>
      </div>
      <div style="background:#f8fafc;padding:22px;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;">
        <p style="color:#334155;font-size:14px;margin:0 0 16px;"><strong>From:</strong> {escape(name)}</p>
        <div style="background:white;border:1px solid #e2e8f0;border-radius:8px;padding:14px;color:#334155;font-size:14px;line-height:1.55;white-space:pre-wrap;">{escape(message.strip())}</div>
        <p style="margin:16px 0 0;">
          <a href="{admin_url}" style="color:#004C8C;font-weight:600;">Open feedback in Admin →</a>
        </p>
      </div>
    </div>
    """
    _send_hub_notify_email(subject, text_body, html_body)


def _save_proposal_diff(user_key, display_name, diff_analysis, voice_recommendations,
                        user_notes='', comparison_prompt=''):
    """Persist a proposal comparison submission; returns new row id or None."""
    try:
        conn = get_db()
        if not conn:
            return None
        cur = conn.cursor()
        cur.execute(
            '''INSERT INTO proposal_diffs
               (user_key, display_name, property_name, diff_analysis, user_notes,
                voice_recommendations, comparison_prompt)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               RETURNING id''',
            (user_key, display_name, '', diff_analysis, user_notes,
             voice_recommendations, comparison_prompt),
        )
        diff_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return diff_id
    except Exception as e:
        print(f'Save proposal diff error: {e}')
        return None


def _notify_proposal_diff_email(name, user_notes, diff_analysis, voice_recommendations,
                                comparison_prompt=''):
    """Send comparison notification without blocking the HTTP response."""
    import threading

    def _send():
        try:
            _send_proposal_diff_email(
                name, user_notes, diff_analysis, voice_recommendations,
                comparison_prompt=comparison_prompt,
            )
        except Exception as e:
            _log_exception(e, 'proposal-diff-email')

    threading.Thread(target=_send, daemon=True).start()


def _send_proposal_diff_email(name, user_notes, diff_analysis, voice_recommendations,
                              comparison_prompt=''):
    from html import escape

    admin_url = f"{HUB_PUBLIC_URL.rstrip('/')}/admin/diffs"
    subject = f'Proposal Comparison — {name}'
    analysis_text = (diff_analysis or '').strip()
    voice_text = (voice_recommendations or '').strip()
    prompt_text = (comparison_prompt or '').strip()
    prompt_block = f"\n\nComparison prompt:\n{prompt_text}" if prompt_text else ''
    notes_block = f"\n\nConsultant notes:\n{user_notes.strip()}" if user_notes else ''
    text_body = (
        f"New proposal comparison from {name}\n"
        f"{prompt_block}{notes_block}\n\n"
        f"What Changed:\n{analysis_text}\n\n"
        f"Voice Guide Recommendations:\n{voice_text}\n\n"
        f"Review in hub: {admin_url}"
    )
    prompt_html = ''
    if prompt_text:
        prompt_html = (
            '<div style="margin-bottom:14px;">'
            '<p style="font-size:12px;font-weight:600;color:#004C8C;text-transform:uppercase;margin:0 0 6px;">Comparison Prompt</p>'
            f'<div style="background:#FFF9E6;border:1px solid #FFE082;border-radius:8px;padding:14px;color:#334155;font-size:14px;line-height:1.55;white-space:pre-wrap;">{escape(prompt_text)}</div>'
            '</div>'
        )
    notes_html = ''
    if user_notes:
        notes_html = (
            '<div style="margin-bottom:14px;">'
            '<p style="font-size:12px;font-weight:600;color:#004C8C;text-transform:uppercase;margin:0 0 6px;">Consultant Notes</p>'
            f'<div style="background:white;border:1px solid #e2e8f0;border-radius:8px;padding:14px;color:#334155;font-size:14px;line-height:1.55;white-space:pre-wrap;">{escape(user_notes.strip())}</div>'
            '</div>'
        )
    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto;">
      <div style="background:#004C8C;padding:18px 22px;border-radius:8px 8px 0 0;">
        <p style="color:white;font-size:17px;font-weight:600;margin:0;">Proposal Comparison</p>
      </div>
      <div style="background:#f8fafc;padding:22px;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;">
        <p style="color:#334155;font-size:14px;margin:0 0 16px;"><strong>From:</strong> {escape(name)}</p>
        {prompt_html}
        {notes_html}
        <div style="margin-bottom:14px;">
          <p style="font-size:12px;font-weight:600;color:#004C8C;text-transform:uppercase;margin:0 0 6px;">What Changed</p>
          <div style="background:white;border:1px solid #e2e8f0;border-radius:8px;padding:14px;color:#334155;font-size:14px;line-height:1.55;white-space:pre-wrap;">{escape(analysis_text)}</div>
        </div>
        <div style="margin-bottom:14px;">
          <p style="font-size:12px;font-weight:600;color:#004C8C;text-transform:uppercase;margin:0 0 6px;">Voice Guide Recommendations</p>
          <div style="background:#FFF9E6;border:1px solid #FFE082;border-radius:8px;padding:14px;color:#334155;font-size:14px;line-height:1.55;white-space:pre-wrap;">{escape(voice_text)}</div>
        </div>
        <p style="margin:0;">
          <a href="{admin_url}" style="color:#004C8C;font-weight:600;">Open comparisons in Admin →</a>
        </p>
      </div>
    </div>
    """
    _send_hub_notify_email(subject, text_body, html_body)


@app.route('/admin/delete-activity', methods=['POST'])
def delete_activity():
    # Allow any authenticated user to delete their own entries
    # Only admin can delete anyone's entries
    if not session.get('user_key'):
        return jsonify({'error': 'Unauthorized'}), 401
    item_type = request.form.get('type')
    item_id   = request.form.get('id')
    user_key  = request.form.get('user_key')
    # Must be deleting own record OR be admin
    if user_key != session.get('user_key') and session.get('role') != 'admin':
        return jsonify({'error': 'Can only delete your own entries'}), 403
    table_map = {'proposal': 'proposal_log', 'ppm': 'ppm_log', 'subscope': 'subscope_log'}
    table = table_map.get(item_type)
    if not table:
        return jsonify({'error': 'Invalid type'}), 400
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor()
            cur.execute(f'DELETE FROM {table} WHERE id = %s AND generated_by = %s',
                        (item_id, user_key))
            conn.commit()
            cur.close()
            conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return _api_error(e)


@app.route('/admin/clear-my-data', methods=['POST'])
def clear_my_data():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor()
            for table in ['proposal_log', 'ppm_log', 'subscope_log']:
                cur.execute(f"DELETE FROM {table} WHERE generated_by = 'thomas_ellison'")
            conn.commit()
            cur.close()
            conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return _api_error(e)


@app.route('/admin/clear-my-profile', methods=['POST'])
def clear_my_profile():
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM profile_results WHERE LOWER(name) = LOWER('Thomas Ellison')")
            conn.commit()
            cur.close()
            conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return _api_error(e)


@app.route('/admin/member/<user_key>')
def admin_member(user_key):
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    user_def = USERS.get(user_key)
    if not user_def:
        return redirect(url_for('admin'))
    proposals, ppms, subscopes, feedback_items = [], [], [], []
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('SELECT * FROM proposal_log WHERE generated_by = %s ORDER BY generated_at DESC', (user_key,))
            proposals = cur.fetchall()
            cur.execute('SELECT * FROM ppm_log WHERE generated_by = %s ORDER BY generated_at DESC', (user_key,))
            ppms = cur.fetchall()
            cur.execute('SELECT * FROM subscope_log WHERE generated_by = %s ORDER BY generated_at DESC', (user_key,))
            subscopes = cur.fetchall()
            cur.execute('SELECT * FROM feedback WHERE user_key = %s ORDER BY submitted_at DESC', (user_key,))
            feedback_items = cur.fetchall()
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Member detail error: {e}")
    return render_template('admin_member.html',
                           user=user_def, user_key=user_key,
                           proposals=proposals, ppms=ppms,
                           subscopes=subscopes,
                           feedback_items=feedback_items)


@app.route('/admin/feedback')
def admin_feedback():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    items = []
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('SELECT * FROM feedback ORDER BY submitted_at DESC')
            items = cur.fetchall()
            # Mark all as read
            cur.execute('UPDATE feedback SET read_by_admin = TRUE')
            conn.commit()
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Feedback error: {e}")
    return render_template('admin_feedback.html', items=items)


def _serialize_log_rows(rows):
    """Convert DB rows to JSON-safe dicts for templates."""
    out = []
    for row in rows or []:
        d = dict(row)
        for k, v in d.items():
            if hasattr(v, 'isoformat'):
                d[k] = v.isoformat()
        out.append(d)
    return out


@app.route('/my-proposals')
@require_login
def my_proposals():
    user_key = session['user_key']
    user = USERS.get(user_key, {})
    if user.get('role') not in ('consultant', 'admin'):
        return redirect(url_for('dashboard'))

    rows = []
    stats = {'total': 0, 'last_30': 0, 'with_file': 0}
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                'SELECT * FROM proposal_log WHERE generated_by = %s ORDER BY generated_at DESC',
                (user_key,)
            )
            rows = cur.fetchall()
            stats['total'] = len(rows)
            stats['with_file'] = sum(1 for r in rows if r.get('document_id'))
            cur.execute(
                '''SELECT COUNT(*) AS c FROM proposal_log
                   WHERE generated_by = %s AND generated_at >= NOW() - INTERVAL '30 days' ''',
                (user_key,)
            )
            stats['last_30'] = cur.fetchone()['c'] or 0
            cur.close()
            conn.close()
    except Exception as e:
        print(f"My proposals error: {e}")

    return render_template(
        'my_proposals.html',
        user=user,
        user_key=user_key,
        rows=rows,
        stats=stats,
        proposal_url=os.environ.get('PROPOSAL_URL', 'https://pps-proposal-tool.onrender.com'),
    )


@app.route('/my-ppms')
@require_login
def my_ppms():
    user_key = session['user_key']
    user = USERS.get(user_key, {})
    if user.get('role') not in ('pm', 'admin'):
        return redirect(url_for('dashboard'))

    rows = []
    stats = {'total': 0, 'last_30': 0, 'as_pm': 0}
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                '''SELECT * FROM ppm_log
                   WHERE generated_by = %s OR pm_key = %s
                   ORDER BY generated_at DESC''',
                (user_key, user_key)
            )
            rows = cur.fetchall()
            stats['total'] = len(rows)
            stats['as_pm'] = sum(1 for r in rows if r.get('pm_key') == user_key)
            cur.execute(
                '''SELECT COUNT(*) AS c FROM ppm_log
                   WHERE (generated_by = %s OR pm_key = %s)
                   AND generated_at >= NOW() - INTERVAL '30 days' ''',
                (user_key, user_key)
            )
            stats['last_30'] = cur.fetchone()['c'] or 0
            cur.close()
            conn.close()
    except Exception as e:
        print(f"My PPMs error: {e}")

    return render_template(
        'my_ppms.html',
        user=user,
        user_key=user_key,
        rows=rows,
        stats=stats,
        proposal_url=os.environ.get('PROPOSAL_URL', 'https://pps-proposal-tool.onrender.com'),
    )


@app.route('/admin/proposals')
def admin_proposals():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    from datetime import datetime as _dt, timedelta
    consultant_filter = request.args.get('consultant', '')
    period = request.args.get('period', 'all')
    rows = []
    counts = {}
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            # Get all proposals filtered by consultant_key (for)
            if consultant_filter:
                cur.execute(
                    'SELECT * FROM proposal_log WHERE consultant_key = %s ORDER BY generated_at DESC',
                    (consultant_filter,)
                )
            else:
                cur.execute('SELECT * FROM proposal_log ORDER BY generated_at DESC')
            rows = cur.fetchall()
            # Get counts per consultant
            cur.execute('''
                SELECT consultant_key, consultant_name,
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE generated_at >= NOW() - INTERVAL '30 days') as last_30
                FROM proposal_log GROUP BY consultant_key, consultant_name ORDER BY consultant_name
            ''')
            counts = {r['consultant_key']: r for r in cur.fetchall()}
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Admin proposals error: {e}")
    return render_template('admin_proposals.html',
                           rows=rows, counts=counts,
                           consultant_filter=consultant_filter,
                           consultants=CONSULTANTS)


@app.route('/admin/stats')
def admin_stats():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    from datetime import datetime as _dt
    stats = {}
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            for table, key in [
                ('proposal_log', 'proposals'),
                ('ppm_log', 'ppms'),
                ('subscope_log', 'subscopes'),
                ('profile_results', 'profiles'),
            ]:
                try:
                    cur.execute(f'''
                        SELECT COUNT(*) as total,
                        COUNT(*) FILTER (WHERE generated_at >= NOW() - INTERVAL '30 days') as last_30
                        FROM {table}
                    ''')
                    stats[key] = cur.fetchone()
                except:
                    stats[key] = {'total': 0, 'last_30': 0}
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Stats error: {e}")
    return jsonify(stats)


@app.route('/generate-code', methods=['POST'])
@require_login
def generate_code():
    """Called by hub dashboard JS — returns a one-time SSO code for satellite tools."""
    user_key = session['user_key']
    code = generate_sso_code(get_db, user_key, session.get('display_name', ''), session.get('role', 'user'))
    if not code:
        return jsonify({'error': 'Could not create sign-in code. Check database connection.'}), 500
    return jsonify({'code': code})


@app.route('/generate-token', methods=['POST'])
@require_login
def generate_token():
    """Legacy alias — returns a code (not a long-lived token)."""
    user_key = session['user_key']
    code = generate_sso_code(get_db, user_key, session.get('display_name', ''), session.get('role', 'user'))
    if not code:
        return jsonify({'error': 'Could not create sign-in code.'}), 500
    return jsonify({'code': code, 'token': code})


@app.route('/exchange-code', methods=['POST'])
def exchange_code_route():
    """Server-to-server: satellite tools exchange a one-time code for user info."""
    api_key = request.headers.get('X-API-Key', '')
    if api_key != INTERNAL_API_KEY:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json(silent=True) or {}
    code = (data.get('code') or '').strip()
    if not code:
        return jsonify({'valid': False, 'reason': 'code required'}), 400
    row = exchange_sso_code(get_db, code)
    if not row:
        return jsonify({'valid': False, 'reason': 'Code invalid or expired'})
    _touch_last_active(row['user_key'], force=True)
    return jsonify({'valid': True, **row})


@app.route('/validate-token', methods=['POST'])
def validate_token():
    """Legacy token validation — deprecated; use /exchange-code."""
    api_key = request.headers.get('X-API-Key', '')
    if api_key != INTERNAL_API_KEY:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json(silent=True) or {}
    token = (data.get('token') or '').strip()
    if not token:
        return jsonify({'valid': False}), 400
    row = exchange_sso_code(get_db, token)
    if row:
        _touch_last_active(row['user_key'], force=True)
        return jsonify({'valid': True, **row})
    return jsonify({'valid': False, 'reason': 'Token invalid or expired'})


def _upload_size_bytes(file_storage):
    pos = file_storage.tell()
    file_storage.seek(0, os.SEEK_END)
    size = file_storage.tell()
    file_storage.seek(pos)
    return size


def _extract_upload_text(file_storage, label='file'):
    """Extract plain text from an uploaded proposal (.docx, .txt; .pdf if pdftotext available)."""
    if not file_storage or not file_storage.filename:
        raise ValueError(f'Missing {label}')
    size = _upload_size_bytes(file_storage)
    if size > MAX_DOCUMENT_BYTES:
        limit_mb = MAX_DOCUMENT_BYTES // (1024 * 1024)
        raise ValueError(f'{label} exceeds {limit_mb} MB — use a smaller file.')
    filename = file_storage.filename.lower()
    if filename.endswith('.docx'):
        from docx import Document as DocxDoc
        data = file_storage.read()
        doc = DocxDoc(BytesIO(data))
        parts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    t = cell.text.strip()
                    if t:
                        parts.append(t)
        return '\n'.join(parts)
    if filename.endswith('.txt'):
        return file_storage.read().decode('utf-8', errors='ignore')
    if filename.endswith('.pdf'):
        import subprocess
        import tempfile
        data = file_storage.read()
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            result = subprocess.run(
                ['pdftotext', tmp_path, '-'],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise ValueError('Could not extract text from PDF — upload a Word (.docx) or text file instead.')
    raise ValueError('Unsupported file type — use .docx or .txt')


@app.route('/analyze-diff', methods=['POST'])
def analyze_diff():
    """Compare original vs edited proposal; return Claude analysis for voice guide updates."""
    if not session.get('user_key'):
        return jsonify({'error': 'Not authenticated'}), 401
    if not CLAUDE_API_KEY:
        return jsonify({'error': 'Claude API key not configured on hub (CLAUDE_API_KEY).'}), 503

    original_file = request.files.get('original')
    edited_file = request.files.get('edited')

    try:
        original_text = _extract_upload_text(original_file, 'original proposal')
        edited_text = _extract_upload_text(edited_file, 'edited proposal')
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        _log_exception(e, 'analyze-diff')
        return jsonify({'success': False, 'error': 'Could not read one or both files.'}), 400

    if not original_text.strip() or not edited_text.strip():
        return jsonify({'success': False, 'error': 'Could not extract text from one or both files.'}), 400

    comparison_prompt = (request.form.get('comparison_prompt') or '').strip()[:2000]

    prompt = f"""You are helping improve the PPS (Pure Property Solutions) construction proposal voice guide.

A consultant generated a proposal with AI, then edited it before sending to the client.
Compare the ORIGINAL and EDITED versions. Focus on meaningful changes to tone, structure,
wording, scope language, and client-facing phrasing — not trivial formatting."""

    if comparison_prompt:
        prompt += f"""

ADDITIONAL INSTRUCTIONS FROM THE CONSULTANT (apply on top of the standard comparison above — do not ignore the base task):
{comparison_prompt}"""

    prompt += f"""

ORIGINAL (AI-generated):
{original_text[:14000]}

EDITED (consultant's final version):
{edited_text[:14000]}

Respond with ONLY valid JSON (no markdown fences) using exactly these keys:
{{
  "diff_analysis": "Bullet-style summary of what changed and why it matters for client-facing proposals",
  "voice_recommendations": "Specific, actionable updates to recommend for pps_voice.txt — phrasing rules, tone shifts, trade language, or sections to add"
}}"""

    try:
        raw = _claude_roleplay_call(
            'You compare proposal drafts and return strict JSON only.',
            [{'role': 'user', 'content': prompt}],
            max_tokens=2500,
            timeout=90.0,
        )
        if raw.startswith('```'):
            raw = raw.split('\n', 1)[-1]
            if raw.endswith('```'):
                raw = raw.rsplit('```', 1)[0]
            raw = raw.strip()
        parsed = json.loads(raw)
        diff_analysis = (parsed.get('diff_analysis') or '').strip()
        voice_recommendations = (parsed.get('voice_recommendations') or '').strip()
        if not diff_analysis and not voice_recommendations:
            return jsonify({'success': False, 'error': 'Claude returned an empty analysis.'}), 500

        user_key = session['user_key']
        display_name = session.get('display_name', '')
        diff_id = _save_proposal_diff(
            user_key, display_name, diff_analysis, voice_recommendations,
            comparison_prompt=comparison_prompt,
        )
        _notify_proposal_diff_email(
            display_name, '', diff_analysis, voice_recommendations,
            comparison_prompt=comparison_prompt,
        )

        return jsonify({
            'success': True,
            'diff_analysis': diff_analysis,
            'voice_recommendations': voice_recommendations,
            'diff_id': diff_id,
            'shared_with_admin': bool(diff_id),
        })
    except json.JSONDecodeError:
        return jsonify({'success': False, 'error': 'Could not parse Claude response. Try again.'}), 500
    except Exception as e:
        _log_exception(e, 'analyze-diff')
        err_name = type(e).__name__
        if err_name in ('APITimeoutError', 'TimeoutError') or 'timeout' in str(e).lower():
            return jsonify({
                'success': False,
                'error': 'Analysis timed out. Try again with smaller files or a shorter comparison prompt.',
            }), 504
        return jsonify({'success': False, 'error': 'Analysis failed. Please try again.'}), 500


@app.route('/submit-diff', methods=['POST'])
def submit_diff():
    """Optional follow-up: attach consultant notes to an existing comparison."""
    if not session.get('user_key'):
        return jsonify({'error': 'Not authenticated'}), 401
    diff_id = request.form.get('diff_id', '').strip()
    user_notes = request.form.get('user_notes', '').strip()
    if not user_notes:
        return jsonify({'success': False, 'error': 'No notes to save.'}), 400
    user_key = session['user_key']
    display_name = session.get('display_name', '')
    try:
        conn = get_db()
        if not conn:
            return jsonify({'error': 'Database unavailable'}), 500
        cur = conn.cursor(cursor_factory=RealDictCursor)
        comparison_prompt = ''
        if diff_id:
            cur.execute(
                '''SELECT id, diff_analysis, voice_recommendations, comparison_prompt
                   FROM proposal_diffs WHERE id = %s AND user_key = %s''',
                (diff_id, user_key),
            )
            row = cur.fetchone()
            if not row:
                cur.close()
                conn.close()
                return jsonify({'error': 'Comparison not found.'}), 404
            cur.execute(
                'UPDATE proposal_diffs SET user_notes = %s WHERE id = %s',
                (user_notes, diff_id),
            )
            diff_analysis = row.get('diff_analysis') or ''
            voice_recommendations = row.get('voice_recommendations') or ''
            comparison_prompt = row.get('comparison_prompt') or ''
        else:
            diff_analysis = request.form.get('diff_analysis', '').strip()
            voice_recommendations = request.form.get('voice_recommendations', '').strip()
            cur.execute(
                '''INSERT INTO proposal_diffs
                   (user_key, display_name, property_name, diff_analysis, user_notes, voice_recommendations)
                   VALUES (%s, %s, %s, %s, %s, %s)''',
                (user_key, display_name, '', diff_analysis, user_notes, voice_recommendations),
            )
        conn.commit()
        cur.close()
        conn.close()
        _notify_proposal_diff_email(
            display_name, user_notes, diff_analysis, voice_recommendations,
            comparison_prompt=comparison_prompt,
        )
        return jsonify({'success': True})
    except Exception as e:
        return _api_error(e)


@app.route('/admin/diffs')
def admin_diffs():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    rows = []
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('SELECT * FROM proposal_diffs ORDER BY submitted_at DESC')
            rows = cur.fetchall()
            cur.execute('UPDATE proposal_diffs SET reviewed_by_admin = TRUE')
            conn.commit()
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Admin diffs error: {e}")
    return render_template('admin_diffs.html', rows=rows)


@app.route('/my-diffs')
def my_diffs():
    if not session.get('user_key'):
        return redirect(url_for('login'))
    rows = []
    user_key = session['user_key']
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            if session.get('role') == 'admin':
                cur.execute('SELECT * FROM proposal_diffs ORDER BY submitted_at DESC')
            else:
                cur.execute(
                    'SELECT * FROM proposal_diffs WHERE user_key = %s ORDER BY submitted_at DESC',
                    (user_key,)
                )
            rows = cur.fetchall()
            cur.close()
            conn.close()
    except Exception as e:
        print(f"My diffs error: {e}")
    return render_template('proposal_diff.html', rows=rows,
                           is_admin=session.get('role') == 'admin')


@app.route('/team-view')
def team_view():
    if not session.get('user_key'):
        return redirect(url_for('login'))
    user_key = session['user_key']
    user = USERS.get(user_key, {})
    if not user.get('team_view') and session.get('role') != 'admin':
        return redirect(url_for('dashboard'))

    scope = user.get('team_view_scope')
    members = []
    member_data = {}

    # Build member list based on scope
    if scope == 'consultants':
        member_keys = ['tony_cumella','adam_cupito','rachel_farler','andy_potts','thomas_ellison']
    elif scope == 'pms':
        member_keys = ['phil_miller','derek_kidney','nick_triplett','trey_hollmeyer',
                       'james_boling','jordan_allen','ben_ramsey']
    else:
        member_keys = list(USERS.keys())

    for key in member_keys:
        u = USERS.get(key, {})
        if u:
            members.append({'key': key, 'display': u['display'], 'title': u.get('title',''), 'role': u['role']})

    try:
        conn = get_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            for key in member_keys:
                udata = {}
                if scope == 'consultants':
                    cur.execute(
                        'SELECT * FROM proposal_log WHERE consultant_key = %s ORDER BY generated_at DESC',
                        (key,)
                    )
                    udata['proposals'] = _serialize_log_rows(cur.fetchall())
                elif scope == 'pms':
                    cur.execute(
                        'SELECT * FROM ppm_log WHERE generated_by = %s OR pm_key = %s ORDER BY generated_at DESC',
                        (key, key)
                    )
                    udata['ppms'] = _serialize_log_rows(cur.fetchall())
                    cur.execute(
                        'SELECT * FROM subscope_log WHERE generated_by = %s ORDER BY generated_at DESC',
                        (key,)
                    )
                    udata['tpscopes'] = _serialize_log_rows(cur.fetchall())
                member_data[key] = udata
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Team view error: {e}")

    return render_template(
        'team_view.html',
        user=user,
        user_key=user_key,
        scope=scope,
        members=members,
        member_data=member_data,
        is_admin=session.get('role') == 'admin',
        proposal_url=os.environ.get('PROPOSAL_URL', 'https://pps-proposal-tool.onrender.com'),
    )


@app.route('/admin/tpscopes')
def admin_tpscopes():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    rows = []
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('SELECT * FROM subscope_log ORDER BY generated_at DESC')
            rows = cur.fetchall()
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Admin TPS error: {e}")
    return render_template('admin_tpscopes.html', rows=rows)


@app.route('/admin/reset-team-view', methods=['POST'])
def reset_team_view():
    """Toggle team_view for a user — admin only."""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized'}), 401
    user_key = request.form.get('user_key')
    enabled = request.form.get('enabled') == 'true'
    scope = request.form.get('scope', '')
    if user_key in USERS:
        USERS[user_key]['team_view'] = enabled
        if scope:
            USERS[user_key]['team_view_scope'] = scope
        return jsonify({'success': True, 'team_view': USERS[user_key]['team_view']})
    return jsonify({'error': 'User not found'}), 404


@app.route('/site-visit')
def site_visit():
    if not session.get('user_key'):
        return redirect(url_for('login'))
    user_key = session['user_key']
    return render_template(
        'site_visit.html',
        user_key=user_key,
        display_name=session.get('display_name', ''),
        user_email=USERS.get(user_key, {}).get('email', session.get('user_email', '')),
    )


@app.route('/site-visit/generate', methods=['POST'])
def site_visit_generate():
    if not session.get('user_key'):
        return jsonify({'error': 'Not authenticated'}), 401

    import json as _json
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data received'}), 400

    user_key     = session['user_key']
    display_name = session.get('display_name', '')
    data['visited_by'] = data.get('visited_by') or display_name

    action = data.get('action', 'both')  # 'download', 'save', 'both'

    # Save to DB if requested
    saved_id = None
    if action in ('save', 'both'):
        try:
            conn = get_db()
            if conn:
                cur = conn.cursor()
                cur.execute('''
                    INSERT INTO site_visit_log (
                        generated_by, display_name, property_name, property_address,
                        visit_date, visit_time, po_number,
                        trade_partner_present, trade_partner_company, crew_lead, crew_count,
                        met_with_staff, staff_contact, topics_discussed,
                        complaints_received, complaint_details,
                        checklist, overall_status, quality_status, schedule_status,
                        observations, photos_taken, next_visit_date
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id
                ''', (
                    user_key, display_name,
                    data.get('property_name'), data.get('property_address'),
                    data.get('visit_date'), data.get('visit_time'), data.get('po_number'),
                    data.get('trade_partner_present'), data.get('trade_partner_company'),
                    data.get('crew_lead'), data.get('crew_count'),
                    data.get('met_with_staff'), data.get('staff_contact'),
                    data.get('topics_discussed'), data.get('complaints_received'),
                    data.get('complaint_details'),
                    _json.dumps(data.get('checklist', [])),
                    data.get('overall_status'), data.get('quality_status'),
                    data.get('schedule_status'), data.get('observations'),
                    bool(data.get('photos_taken')), data.get('next_visit_date'),
                ))
                saved_id = cur.fetchone()[0]
                conn.commit()
                cur.close()
                conn.close()
        except Exception as e:
            print(f"Site visit save error: {e}")

    if action == 'save':
        return jsonify({'success': True, 'saved_id': saved_id})

    # Generate Word doc
    try:
        import sys, os
        sys.path.insert(0, os.path.dirname(__file__))
        from site_visit_builder import build_site_visit
        buf = build_site_visit(data)
        from flask import send_file
        prop = data.get('property_name', 'Site_Visit').replace(' ', '_')
        date = data.get('visit_date', '').replace('/', '-').replace(' ', '_')
        filename = f"PPS_Site_Visit_{prop}_{date}.docx"
        buf.seek(0)
        return send_file(
            buf,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
    except Exception as e:
        import traceback; traceback.print_exc()
        return _api_error(e)


@app.route('/site-visit/download/<int:visit_id>')
def site_visit_download(visit_id):
    user_key = session.get('user_key')
    if not user_key:
        return redirect(url_for('login'))
    role = session.get('role', '')
    row = None
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('SELECT * FROM site_visit_log WHERE id = %s', (visit_id,))
            row = cur.fetchone()
            cur.close(); conn.close()
        if not row:
            return "Not found", 404
        if not _can_view_activity_row(user_key, role, 'site_visit', row):
            return "Forbidden", 403
        import json as _json, sys, os
        data = dict(row)
        if isinstance(data.get('checklist'), str):
            data['checklist'] = _json.loads(data['checklist'])
        sys.path.insert(0, os.path.dirname(__file__))
        from site_visit_builder import build_site_visit
        buf = build_site_visit(data)
        from flask import send_file
        prop = (data.get('property_name') or 'Site_Visit').replace(' ','_')
        filename = f"PPS_Site_Visit_{prop}.docx"
        return send_file(buf, as_attachment=True, download_name=filename,
                        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    except Exception as e:
        _log_exception(e)
        return GENERIC_DOWNLOAD_ERROR, 500


@app.route('/admin/site-visits')
def admin_site_visits():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    rows = []
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('SELECT * FROM site_visit_log ORDER BY generated_at DESC')
            rows = cur.fetchall()
            cur.close(); conn.close()
    except Exception as e:
        print(f"Admin site visits error: {e}")
    return render_template('admin_site_visits.html', rows=rows)


@app.route('/pm-training')
@require_login
def pm_training():
    """PM onboarding module — open to all logged-in users while under construction."""
    user_key = session['user_key']
    user = USERS.get(user_key, {})
    enrollment = get_pm_enrollment(user_key) or {}
    manager = USERS.get(enrollment.get('manager_key') or PM_TRAINING_MANAGER, {})
    meta, weeks = get_pm_training_curriculum()
    progress = get_pm_training_progress(user_key)
    notes = get_pm_training_notes(user_key)
    stats = compute_pm_training_stats(user_key)
    week_status = {wp['week']: wp for wp in stats['week_pcts']}
    return render_template(
        'pm_training.html',
        meta=meta,
        weeks=weeks,
        total_items=count_pm_trackable_items(),
        progress_json=json.dumps(progress),
        notes_json=json.dumps(notes),
        enrollment=enrollment,
        manager=manager,
        stats=stats,
        week_status=week_status,
        user=user,
        under_construction=True,
    )


@app.route('/api/pm-training/progress', methods=['GET', 'POST'])
@require_login
def pm_training_progress_api():
    user_key = session['user_key']
    if request.method == 'GET':
        return jsonify({'progress': get_pm_training_progress(user_key)})
    data = request.get_json(silent=True) or {}
    progress = data.get('progress', {})
    if not isinstance(progress, dict):
        return jsonify({'error': 'Invalid progress data'}), 400
    ok = save_pm_training_progress(user_key, progress)
    if not ok:
        return jsonify({'error': 'Could not save progress'}), 500
    return jsonify({'success': True, 'stats': compute_pm_training_stats(user_key)})


@app.route('/api/pm-training/notes', methods=['GET', 'POST'])
@require_login
def pm_training_notes_api():
    user_key = session['user_key']
    if request.method == 'GET':
        return jsonify({'notes': get_pm_training_notes(user_key)})
    data = request.get_json(silent=True) or {}
    week_num = data.get('week')
    if week_num is None:
        return jsonify({'error': 'week required'}), 400
    notes_text = data.get('notes', '')
    ok = save_pm_training_notes(user_key, week_num, notes_text)
    if not ok:
        return jsonify({'error': 'Could not save notes'}), 500
    return jsonify({'success': True})


@app.route('/api/pm-training/feedback', methods=['POST'])
@require_login
def pm_training_feedback_api():
    user_key = session['user_key']
    user = USERS.get(user_key, {})
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'error': 'Message required'}), 400
    week_num = data.get('week')
    if week_num is not None and week_num != '':
        try:
            week_num = int(week_num)
        except (TypeError, ValueError):
            week_num = None
    else:
        week_num = None
    feedback_type = (data.get('type') or 'improvement').strip()[:50]
    ok = submit_pm_training_feedback(
        user_key,
        user.get('display', user_key),
        message,
        week_num=week_num,
        feedback_type=feedback_type,
    )
    if not ok:
        return jsonify({'error': 'Could not submit feedback'}), 500
    return jsonify({'success': True})


@app.route('/pm-training/oversight')
@require_login
def pm_training_oversight():
    user_key = session['user_key']
    if not can_pm_training_oversight(user_key):
        return redirect(url_for('dashboard'))
    trainees = list_pm_enrolled_trainees()
    trainee_rows = []
    for t in trainees:
        key = t['user_key']
        stats = compute_pm_training_stats(key)
        trainee_rows.append({**t, 'stats': stats})
    # Everyone can open the module; also list recent progress users not formally enrolled
    enrollable = sorted(
        [{'key': k, 'display': v.get('display', k), 'role': v.get('role', '')}
         for k, v in USERS.items()],
        key=lambda u: u['display'],
    )
    return render_template(
        'pm_training_oversight.html',
        trainees=trainee_rows,
        enrollable=enrollable,
        feedback=list_pm_training_feedback(),
        manager_name=USERS.get(PM_TRAINING_MANAGER, {}).get('display', 'Production Manager'),
        is_admin=(USERS.get(user_key, {}).get('role') == 'admin'),
        under_construction=True,
    )


@app.route('/admin/pm-training')
@require_login
def admin_pm_training():
    return redirect(url_for('pm_training_oversight'))


@app.route('/api/pm-training/signoff', methods=['POST'])
@require_login
def pm_training_signoff_api():
    user_key = session['user_key']
    if not can_pm_training_oversight(user_key):
        return jsonify({'error': 'Not authorized'}), 403
    data = request.get_json(silent=True) or {}
    trainee_key = (data.get('user_key') or '').strip()
    try:
        week_num = int(data.get('week'))
    except (TypeError, ValueError):
        return jsonify({'error': 'week required'}), 400
    if not trainee_key:
        return jsonify({'error': 'user_key required'}), 400
    try:
        conn = get_db()
        if not conn:
            return jsonify({'error': 'Database unavailable'}), 500
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO pm_training_manager_signoffs (user_key, week_num, signed_by, signed_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (user_key, week_num)
            DO UPDATE SET signed_by = EXCLUDED.signed_by, signed_at = NOW()
        ''', (trainee_key, week_num, user_key))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"PM signoff error: {e}")
        return jsonify({'error': 'Could not sign off'}), 500
    return jsonify({'success': True, 'stats': compute_pm_training_stats(trainee_key)})


@app.route('/api/pm-training/enroll', methods=['POST'])
@require_login
def pm_training_enroll_api():
    user_key = session['user_key']
    if not can_pm_training_oversight(user_key):
        return jsonify({'error': 'Not authorized'}), 403
    data = request.get_json(silent=True) or {}
    target_key = (data.get('user_key') or '').strip()
    action = (data.get('action') or 'enroll').strip()
    if not target_key:
        return jsonify({'error': 'user_key required'}), 400
    if action == 'unenroll':
        ok = unenroll_pm_trainee(target_key)
        return jsonify({'success': bool(ok)})
    if action == 'graduate':
        ok = graduate_pm_trainee(target_key)
        return jsonify({'success': bool(ok)})
    ok, err = enroll_pm_trainee(target_key, user_key, data.get('manager_key'))
    if not ok:
        return jsonify({'error': err or 'Could not enroll'}), 400
    return jsonify({'success': True})



@app.route('/psc-training')
@require_login
def psc_training():
    user_key = session['user_key']
    if not is_psc_training_enrolled(user_key):
        return redirect(url_for('dashboard'))
    user = USERS.get(user_key, {})
    enrollment = get_psc_enrollment(user_key) or {}
    manager = USERS.get(enrollment.get('manager_key') or PSC_TRAINING_MANAGER, {})
    onboarding, weeks, core_values, sales_training, company_operations = get_training_curriculum()
    progress = get_psc_training_progress(user_key)
    notes = get_psc_training_notes(user_key)
    stats = compute_psc_training_stats(user_key)
    week_status = {wp['week']: wp for wp in stats['week_pcts']}
    return render_template(
        'psc_training.html',
        meta=PSC_TRAINING_META,
        onboarding=onboarding,
        weeks=weeks,
        core_values=core_values,
        sales_training=sales_training,
        company_operations=company_operations,
        total_items=count_trackable_items(),
        progress_json=json.dumps(progress),
        notes_json=json.dumps(notes),
        enrollment=enrollment,
        manager=manager,
        stats=stats,
        week_status=week_status,
        user=user,
        roleplay_by_week=get_roleplay_week_links(),
        roleplay_sales_links=get_roleplay_sales_links(),
    )


@app.route('/api/psc-training/progress', methods=['GET', 'POST'])
@require_login
def psc_training_progress_api():
    user_key = session['user_key']
    if not is_psc_training_enrolled(user_key):
        return jsonify({'error': 'Not enrolled in PSC training'}), 403
    if request.method == 'GET':
        return jsonify({'progress': get_psc_training_progress(user_key)})
    data = request.get_json(silent=True) or {}
    progress = data.get('progress', {})
    if not isinstance(progress, dict):
        return jsonify({'error': 'Invalid progress data'}), 400
    ok = save_psc_training_progress(user_key, progress)
    if not ok:
        return jsonify({'error': 'Could not save progress'}), 500
    return jsonify({'success': True, 'stats': compute_psc_training_stats(user_key)})


@app.route('/api/psc-training/notes', methods=['GET', 'POST'])
@require_login
def psc_training_notes_api():
    user_key = session['user_key']
    if not is_psc_training_enrolled(user_key):
        return jsonify({'error': 'Not enrolled in PSC training'}), 403
    if request.method == 'GET':
        return jsonify({'notes': get_psc_training_notes(user_key)})
    data = request.get_json(silent=True) or {}
    week_num = data.get('week')
    if week_num is None:
        return jsonify({'error': 'week required'}), 400
    notes_text = data.get('notes', '')
    ok = save_psc_training_notes(user_key, week_num, notes_text)
    if not ok:
        return jsonify({'error': 'Could not save notes'}), 500
    return jsonify({'success': True})


@app.route('/api/psc-training/feedback', methods=['POST'])
@require_login
def psc_training_feedback_api():
    user_key = session['user_key']
    if not is_psc_training_enrolled(user_key):
        return jsonify({'error': 'Not enrolled in PSC training'}), 403
    user = USERS.get(user_key, {})
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({'error': 'Message required'}), 400
    week_num = data.get('week')
    if week_num is not None and week_num != '':
        try:
            week_num = int(week_num)
        except (TypeError, ValueError):
            week_num = None
    else:
        week_num = None
    feedback_type = (data.get('type') or 'improvement').strip()[:50]
    ok = submit_psc_training_feedback(
        user_key,
        user.get('display', user_key),
        message,
        week_num=week_num,
        feedback_type=feedback_type,
    )
    if not ok:
        return jsonify({'error': 'Could not submit feedback'}), 500
    return jsonify({'success': True})


@app.route('/psc-training/roleplay')
@require_login
def psc_roleplay_page():
    user_key = session['user_key']
    if not can_access_psc_roleplay(user_key):
        return redirect(url_for('dashboard'))
    user = USERS.get(user_key, {})
    stats = compute_psc_training_stats(user_key) if is_psc_training_enrolled(user_key) else None
    week_pcts = stats['week_pcts'] if stats else []
    suggested_ids = get_suggested_roleplay_ids(week_pcts)
    user_stats = get_roleplay_user_stats(user_key)
    scenarios = []
    for sc in PSC_ROLEPLAY_SCENARIOS:
        st = user_stats.get(sc['id'], {})
        scenarios.append({
            'id': sc['id'],
            'title': sc['title'],
            'segment': sc['segment'],
            'difficulty': sc['difficulty'],
            'trainee_brief': sc['trainee_brief'],
            'objectives': sc['objectives'],
            'opening_line': sc['opening_line'],
            'max_turns': sc.get('max_turns', 12),
            'segment_color': segment_color(sc['segment']),
            'attempts': st.get('attempts', 0),
            'best_overall': st.get('best_overall'),
            'best_result': st.get('best_result'),
            'suggested': sc['id'] in suggested_ids,
        })
    return render_template(
        'psc_roleplay.html',
        meta=PSC_TRAINING_META,
        scenarios=scenarios,
        scenarios_json=json.dumps(scenarios),
        suggested_ids=suggested_ids,
        display_name=user.get('display', user_key),
        segments=['Apartments', 'Condos', 'Hospitality / Commercial', 'Any'],
    )


@app.route('/api/psc-training/roleplay/turn', methods=['POST'])
@require_login
def psc_roleplay_turn_api():
    user_key = session['user_key']
    if not can_access_psc_roleplay(user_key):
        return jsonify({'error': 'Not authorized for role-play practice'}), 403
    if not CLAUDE_API_KEY:
        return jsonify({'error': 'Practice partner unavailable — try again later.'}), 503

    data = request.get_json(silent=True) or {}
    scenario_id = (data.get('scenario_id') or '').strip()
    scenario = get_roleplay_scenario(scenario_id)
    if not scenario:
        return jsonify({'error': 'Unknown scenario'}), 400

    max_turns = scenario.get('max_turns', 12)
    messages, err = _validate_roleplay_messages(data.get('messages'), max_turns)
    if err:
        return jsonify({'error': err}), 400

    trainee_turns = _count_trainee_turns(messages)
    if trainee_turns > max_turns:
        return jsonify({'error': f'Turn limit reached ({max_turns} trainee messages)'}), 400

    turn_count, grade_count = _roleplay_usage_today(user_key)
    if turn_count >= ROLEPLAY_DAILY_TURN_LIMIT:
        return jsonify({
            'error': f'Daily practice limit reached ({ROLEPLAY_DAILY_TURN_LIMIT} turns). Try again tomorrow.',
        }), 429

    if not messages or messages[-1].get('role') != 'user':
        return jsonify({'error': 'Last message must be from the trainee'}), 400

    system = _ROLEPLAY_PERSONA_SYSTEM.format(persona=scenario['persona'])
    api_messages = [{'role': m['role'], 'content': m['content']} for m in messages]

    try:
        reply = _claude_roleplay_call(system, api_messages, max_tokens=400)
    except Exception:
        return jsonify({'error': 'The practice partner is unavailable — try again in a minute.'}), 503

    _increment_roleplay_usage(user_key, turn_delta=1)
    turns_left = max(0, max_turns - trainee_turns)
    return jsonify({'success': True, 'reply': reply, 'turns_left': turns_left})


@app.route('/api/psc-training/roleplay/finish', methods=['POST'])
@require_login
def psc_roleplay_finish_api():
    user_key = session['user_key']
    if not can_access_psc_roleplay(user_key):
        return jsonify({'error': 'Not authorized for role-play practice'}), 403
    if not CLAUDE_API_KEY:
        return jsonify({'error': 'Practice partner unavailable — try again later.'}), 503

    data = request.get_json(silent=True) or {}
    scenario_id = (data.get('scenario_id') or '').strip()
    scenario = get_roleplay_scenario(scenario_id)
    if not scenario:
        return jsonify({'error': 'Unknown scenario'}), 400

    max_turns = scenario.get('max_turns', 12)
    messages, err = _validate_roleplay_messages(data.get('messages'), max_turns)
    if err:
        return jsonify({'error': err}), 400

    trainee_turns = _count_trainee_turns(messages)
    if trainee_turns < 3:
        return jsonify({
            'error': 'Have a real conversation first — send at least three messages before requesting feedback.',
        }), 400

    turn_count, grade_count = _roleplay_usage_today(user_key)
    if grade_count >= ROLEPLAY_DAILY_GRADE_LIMIT:
        return jsonify({
            'error': f'Daily feedback limit reached ({ROLEPLAY_DAILY_GRADE_LIMIT} sessions). Try again tomorrow.',
        }), 429

    feedback, err = _grade_roleplay_session(scenario, messages)
    if err:
        return jsonify({'error': err}), 500

    session_id = _save_roleplay_session(user_key, scenario_id, messages, feedback, trainee_turns)
    if not session_id:
        return jsonify({'error': 'Could not save session — try again.'}), 500

    _increment_roleplay_usage(user_key, grade_delta=1)
    return jsonify({'success': True, 'session_id': session_id, **feedback})


@app.route('/api/psc-training/roleplay/history')
@require_login
def psc_roleplay_history_api():
    user_key = session['user_key']
    target_key = (request.args.get('user_key') or '').strip() or user_key
    if target_key != user_key:
        if not can_psc_training_oversight(user_key):
            return jsonify({'error': 'Unauthorized'}), 403
    elif not can_access_psc_roleplay(user_key):
        return jsonify({'error': 'Not authorized'}), 403

    rows = get_roleplay_history_rows(target_key)
    history = []
    for row in rows:
        history.append({
            'scenario_id': row['scenario_id'],
            'overall': float(row['overall']) if row['overall'] is not None else None,
            'result': row['result'],
            'created_at': row['created_at'].isoformat() if row.get('created_at') else None,
        })
    return jsonify({'history': history, 'summary': get_roleplay_summary_for_oversight(target_key)})


def _psc_training_oversight_data(mark_read=True):
    enrolled = list_psc_enrolled_trainees()
    trainees = []
    for row in enrolled:
        key = row['user_key']
        stats = compute_psc_training_stats(key)
        trainees.append({
            'user_key': key,
            'display': row.get('display', key),
            'enrolled_at': row.get('enrolled_at'),
            'last_activity_at': row.get('last_activity_at'),
            'manager_key': row.get('manager_key'),
            'manager_display': USERS.get(row.get('manager_key', ''), {}).get('display', ''),
            'done': stats['done'],
            'pct': stats['pct'],
            'week_pcts': stats['week_pcts'],
            'roleplay': get_roleplay_summary_for_oversight(key),
        })
    trainees.sort(key=lambda t: (-t['pct'], t['display']))
    all_consultants = []
    for k, u in USERS.items():
        if u.get('role') != 'consultant':
            continue
        enr = get_psc_enrollment(k)
        all_consultants.append({
            'user_key': k,
            'display': u.get('display', k),
            'enrolled': bool(enr and enr.get('active') and not enr.get('graduated_at')),
        })
    feedback_items = []
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('SELECT * FROM psc_training_feedback ORDER BY submitted_at DESC LIMIT 100')
            feedback_items = cur.fetchall()
            if mark_read:
                cur.execute('UPDATE psc_training_feedback SET read_by_admin = TRUE WHERE read_by_admin = FALSE')
            conn.commit()
            cur.close()
            conn.close()
    except Exception as e:
        print(f"PSC training feedback error: {e}")
    return trainees, all_consultants, feedback_items


@app.route('/psc-training/oversight')
@require_login
def psc_training_oversight():
    user_key = session['user_key']
    if not can_psc_training_oversight(user_key):
        return redirect(url_for('dashboard'))
    trainees, all_consultants, feedback_items = _psc_training_oversight_data(mark_read=True)
    return render_template(
        'psc_training_oversight.html',
        trainees=trainees,
        all_consultants=all_consultants,
        feedback_items=feedback_items,
        total_items=count_trackable_items(),
        is_admin=(session.get('role') == 'admin'),
        can_signoff=True,
        current_user_key=user_key,
        self_enrolled_as_trainee=is_psc_training_enrolled(user_key),
        manager_name=USERS.get(PSC_TRAINING_MANAGER, {}).get('display', 'VP Sales'),
    )


@app.route('/admin/psc-training')
@require_admin
def admin_psc_training():
    return redirect(url_for('psc_training_oversight'))


@app.route('/api/psc-training/signoff', methods=['POST'])
@require_login
def psc_training_signoff_api():
    user_key = session['user_key']
    if not can_psc_training_oversight(user_key):
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json(silent=True) or {}
    trainee_key = (data.get('user_key') or '').strip()
    action = (data.get('action') or 'signoff').strip()
    if not trainee_key:
        return jsonify({'error': 'user_key required'}), 400
    try:
        week_num = int(data.get('week'))
    except (TypeError, ValueError):
        return jsonify({'error': 'week required'}), 400
    if action == 'revoke':
        if session.get('role') != 'admin':
            return jsonify({'error': 'Only admin can revoke sign-offs'}), 403
        ok = revoke_psc_manager_signoff(trainee_key, week_num)
        return jsonify({'success': ok}) if ok else (jsonify({'error': 'Could not revoke'}), 500)
    ok, err = manager_signoff_psc_week(trainee_key, week_num, user_key)
    if not ok:
        return jsonify({'error': err or 'Could not sign off'}), 400
    return jsonify({'success': True, 'stats': compute_psc_training_stats(trainee_key)})


@app.route('/api/psc-training/enroll', methods=['POST'])
@require_admin
def psc_training_enroll_api():
    data = request.get_json(silent=True) or {}
    target_key = (data.get('user_key') or '').strip()
    action = (data.get('action') or 'enroll').strip()
    if not target_key:
        return jsonify({'error': 'user_key required'}), 400
    if action == 'graduate':
        ok = graduate_psc_trainee(target_key)
        return jsonify({'success': ok}) if ok else (jsonify({'error': 'Could not graduate'}), 500)
    if action == 'unenroll':
        ok = unenroll_psc_trainee(target_key)
        return jsonify({'success': ok}) if ok else (jsonify({'error': 'Could not unenroll'}), 500)
    ok, err = enroll_psc_trainee(target_key, session.get('user_key'), data.get('manager_key'))
    if not ok:
        return jsonify({'error': err or 'Could not enroll'}), 400
    return jsonify({'success': True})


def _send_resend_document(to_email, doc_type, filename, property_name, doc_b64, sender_name):
    """Send a document attachment via Resend (internal — self or coworker, not client delivery)."""
    import urllib.request as _ur
    import urllib.error as _ur_err
    import json as _json
    from pps_brand import EMAIL_INTERNAL_NOTICE

    resend_key = os.environ.get('RESEND_API_KEY', '')
    from_email = os.environ.get('RESEND_FROM', 'noreply@purepropsolutions.com')
    reply_to = os.environ.get('RESEND_REPLY_TO', '').strip() or session.get('user_email', '')

    if not resend_key:
        return jsonify({'error': 'Email service not configured. Contact Thomas.'}), 500

    type_labels = {
        'proposal': 'Proposal',
        'ppm': 'PPM Checklist',
        'tps': 'Trade Partner Scope',
        'site_visit': 'Site Visit Report',
        'siding_estimate': 'Siding Estimate',
        'roofing_estimate': 'Roofing Estimate',
        'gutter_estimate': 'Gutter Estimate',
        'painting_estimate': 'Exterior Painting Estimate',
    }
    label = type_labels.get(doc_type, 'Document')
    subject = f'PPS {label} — {property_name}' if property_name else f'PPS {label}'
    prop_line = f'Property: {property_name}' if property_name else ''
    text_body = (
        f'PPS {label} attached — internal use.\n\n'
        f'{EMAIL_INTERNAL_NOTICE}\n\n'
        f'{prop_line + chr(10) if prop_line else ""}'
        f'Generated by: {sender_name}\n\n'
        'The Pure Way: Trust. Quality. Results.'
    )
    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;">
      <div style="background:#004C8C;padding:20px 24px;border-radius:8px 8px 0 0;">
        <p style="color:white;font-size:18px;font-weight:600;margin:0;">Pure Property Solutions</p>
      </div>
      <div style="background:#f8fafc;padding:24px;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;">
        <p style="color:#334155;font-size:15px;"><strong>PPS {label}</strong> attached — <em>internal use only</em>.</p>
        <p style="color:#7c5e10;font-size:13px;background:#fffbeb;border:1px solid #fde68a;border-radius:6px;padding:10px 12px;">
          {EMAIL_INTERNAL_NOTICE}
        </p>
        {'<p style="color:#64748b;font-size:14px;">Property: ' + property_name + '</p>' if property_name else ''}
        <p style="color:#64748b;font-size:14px;">Generated by: {sender_name}</p>
        <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0;">
        <p style="color:#94a3b8;font-size:12px;font-style:italic;">
          The Pure Way: Trust. Quality. Results.™
        </p>
      </div>
    </div>
    """
    email_payload = {
        'from': f'Pure Property Solutions <{from_email}>',
        'to': [to_email],
        'subject': subject,
        'html': html_body,
        'text': text_body,
        'tags': [{'name': 'source', 'value': doc_type[:50]}],
        'attachments': [{'filename': filename, 'content': doc_b64}],
    }
    if reply_to:
        email_payload['reply_to'] = [reply_to]

    payload = _json.dumps(email_payload).encode('utf-8')
    try:
        req = _ur.Request(
            'https://api.resend.com/emails',
            data=payload,
            headers={
                'Authorization': f'Bearer {resend_key}',
                'Content-Type': 'application/json',
                'User-Agent': 'PPS-Hub/1.0',
            },
            method='POST',
        )
        resp = _ur.urlopen(req, timeout=30)
        result = _json.loads(resp.read().decode('utf-8'))
        resend_id = result.get('id', '')
        if not resend_id:
            return jsonify({'error': 'Email service accepted the request but returned no message ID.'}), 500
        return jsonify({'success': True, 'sent_to': to_email, 'resend_id': resend_id, 'from_email': from_email})
    except _ur_err.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        try:
            msg = _json.loads(body).get('message', body)
        except Exception:
            msg = body.strip() or str(e)
        return jsonify({'error': msg}), 500
    except Exception as e:
        return _api_error(e)


@app.route('/email-doc', methods=['POST'])
def email_doc():
    """Email a generated document via Resend API."""
    api_key = request.headers.get('X-API-Key', '')
    internal_ok = api_key == INTERNAL_API_KEY
    if not session.get('user_key') and not internal_ok:
        return jsonify({'error': 'Not authenticated'}), 401

    import base64, urllib.request as _ur, urllib.error as _ur_err, json as _json

    if request.is_json:
        data = request.get_json(silent=True) or {}
        to_email  = (data.get('to_email') or '').strip()
        doc_type  = data.get('doc_type', 'document')
        filename  = data.get('filename', 'PPS_Document.docx')
        prop_name = data.get('property_name', '')
        doc_b64   = data.get('doc_base64', '')
        sender    = data.get('sender_name', 'PPS Proposal Tool')
    else:
        to_email  = request.form.get('to_email', '').strip()
        doc_type  = request.form.get('doc_type', 'document')
        filename  = request.form.get('filename', 'PPS_Document.docx')
        prop_name = request.form.get('property_name', '')
        doc_b64   = request.form.get('doc_base64', '')
        sender    = session.get('display_name', 'PPS Hub')

    if not to_email:
        to_email = session.get('user_email', '')
    if not to_email:
        return jsonify({'error': 'No email address available'}), 400
    if not doc_b64:
        return jsonify({'error': 'No document content'}), 400

    return _send_resend_document(
        to_email=to_email,
        doc_type=doc_type,
        filename=filename,
        property_name=prop_name,
        doc_b64=doc_b64,
        sender_name=sender,
    )


# ── CLIENT DATABASE ─────────────────────────────────────────────────────────

@app.route('/api/clients/search')
def clients_search():
    """Search clients by name or company — returns top 10 matches."""
    # Allow cross-origin from proposal tool (server-to-server or CORS)
    api_key = request.headers.get('X-API-Key', '')
    session_ok = session.get('user_key')
    internal_ok = api_key == INTERNAL_API_KEY
    if not session_ok and not internal_ok:
        resp = jsonify({'error': 'Not authenticated'})
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp, 401
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('''
                SELECT id, name, email, company, property_name, address
                FROM clients
                WHERE LOWER(name) LIKE %s
                   OR LOWER(company) LIKE %s
                   OR LOWER(property_name) LIKE %s
                ORDER BY
                    CASE WHEN LOWER(name) LIKE %s THEN 0 ELSE 1 END,
                    name
                LIMIT 10
            ''', (f'%{q.lower()}%', f'%{q.lower()}%', f'%{q.lower()}%', f'{q.lower()}%'))
            rows = cur.fetchall()
            cur.close(); conn.close()
            resp = jsonify([dict(r) for r in rows])
            resp.headers['Access-Control-Allow-Origin'] = '*'
            resp.headers['Access-Control-Allow-Headers'] = 'X-API-Key, Content-Type'
            return resp
    except Exception as e:
        _log_exception(e, 'clients/search')
        resp = jsonify({'error': GENERIC_API_ERROR})
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp, 500
    resp = jsonify([])
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp


@app.route('/api/clients/search', methods=['OPTIONS'])
def clients_search_options():
    resp = jsonify({})
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Headers'] = 'X-API-Key, Content-Type'
    resp.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    return resp


@app.route('/api/clients/save', methods=['POST', 'OPTIONS'])
def clients_save():
    """Create or update a client record."""
    if request.method == 'OPTIONS':
        resp = jsonify({})
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Headers'] = 'X-API-Key, Content-Type'
        resp.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        return resp

    data = request.get_json() or {}
    api_key = request.headers.get('X-API-Key', '')
    internal_ok = api_key == INTERNAL_API_KEY

    user_key = session.get('user_key')
    if internal_ok and data.get('user_key'):
        user_key = data.get('user_key')

    if not user_key:
        resp = jsonify({'error': 'Not authenticated'})
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp, 401

    user_role = USERS.get(user_key, {}).get('role', session.get('role', ''))
    if user_role not in ('admin', 'consultant'):
        resp = jsonify({'error': 'Permission denied'})
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp, 403
    client_id = data.get('id')
    name    = (data.get('name') or '').strip()
    email   = (data.get('email') or '').strip()
    company = (data.get('company') or '').strip()
    prop    = (data.get('property_name') or '').strip()
    address = (data.get('address') or '').strip()
    notes   = (data.get('notes') or '').strip()

    if not name:
        resp = jsonify({'error': 'Name is required'})
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp, 400

    try:
        conn = get_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            if client_id:
                cur.execute('''
                    UPDATE clients SET name=%s, email=%s, company=%s,
                    property_name=%s, address=%s, notes=%s, updated_at=NOW()
                    WHERE id=%s RETURNING id
                ''', (name, email, company, prop, address, notes, client_id))
            else:
                cur.execute('''
                    INSERT INTO clients (name, email, company, property_name, address, notes, added_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
                ''', (name, email, company, prop, address, notes, user_key))
            row = cur.fetchone()
            conn.commit(); cur.close(); conn.close()
            resp = jsonify({'success': True, 'id': row['id']})
            resp.headers['Access-Control-Allow-Origin'] = '*'
            return resp
    except Exception as e:
        _log_exception(e, 'clients/save')
        resp = jsonify({'error': GENERIC_API_ERROR})
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp, 500


@app.route('/api/clients/seed', methods=['POST'])
def clients_seed():
    """Seed clients from JSON — admin only, run once."""
    if session.get('role') != 'admin':
        return jsonify({'error': 'Admin only'}), 403
    data = request.get_json()
    clients_data = data.get('clients', [])
    inserted = 0
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor()
            for c in clients_data:
                name = (c.get('name') or '').strip()
                if not name: continue
                # Skip if name already exists
                cur.execute('SELECT id FROM clients WHERE LOWER(name) = LOWER(%s)', (name,))
                if cur.fetchone(): continue
                cur.execute('''
                    INSERT INTO clients (name, email, company, property_name, address, added_by)
                    VALUES (%s, %s, %s, %s, %s, %s)
                ''', (name, c.get('email',''), c.get('company',''),
                      c.get('property_name',''), c.get('address',''), 'seed'))
                inserted += 1
            conn.commit(); cur.close(); conn.close()
        return jsonify({'success': True, 'inserted': inserted})
    except Exception as e:
        return _api_error(e)


@app.route('/clients')
def clients_page():
    """Client database management page — Thomas only."""
    if session.get('user_key') != 'thomas_ellison':
        return redirect(url_for('dashboard'))
    rows = []
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('SELECT * FROM clients ORDER BY name')
            rows = cur.fetchall()
            cur.close(); conn.close()
    except Exception as e:
        print(f"Clients page error: {e}")
    return render_template('clients.html', rows=rows, can_edit=True)


@app.route('/admin/seed-clients')
def seed_clients_page():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    return render_template('seed_clients.html')


@app.route('/test-token')
@require_login
def test_token():
    """Debug endpoint - shows session state and SSO code generation."""
    code = generate_sso_code(
        get_db,
        session['user_key'],
        session.get('display_name', ''),
        session.get('role', 'user'),
    )
    return jsonify({
        'session': 'active',
        'user_key': session['user_key'],
        'code_generated': code is not None,
        'code_preview': code[:8] + '...' if code else None,
    })


def _send_resend_email(to_email, subject, html_body, text_body):
    import urllib.request as _ur
    import urllib.error as _ur_err
    resend_key = os.environ.get('RESEND_API_KEY', '')
    from_email = os.environ.get('RESEND_FROM', 'noreply@purepropsolutions.com')
    if not resend_key:
        return False, 'Email service not configured'
    payload = json.dumps({
        'from': f'Pure Property Solutions <{from_email}>',
        'to': [to_email],
        'subject': subject,
        'html': html_body,
        'text': text_body,
    }).encode('utf-8')
    try:
        req = _ur.Request(
            'https://api.resend.com/emails',
            data=payload,
            headers={
                'Authorization': f'Bearer {resend_key}',
                'Content-Type': 'application/json',
                'User-Agent': 'PPS-Hub/1.0',
            },
            method='POST',
        )
        resp = _ur.urlopen(req, timeout=30)
        result = json.loads(resp.read().decode('utf-8'))
        if result.get('id'):
            return True, result['id']
        return False, 'No message ID returned'
    except _ur_err.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        return False, body
    except Exception as e:
        return False, str(e)


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    message = None
    error = None
    if request.method == 'POST':
        user_key = _resolve_login_user_key(request.form.get('user_key', ''))
        user_def = USERS.get(user_key)
        if not user_def:
            error = 'Tap your name in the list first.'
        else:
            token = create_password_reset_token(get_db, user_key)
            to_email = user_def.get('email', '')
            if not token or not to_email:
                error = 'Could not start reset. Contact Thomas or Stephanie.'
            else:
                link = reset_url_for_token(token)
                ok, detail = _send_resend_email(
                    to_email.strip().lower(),
                    'Reset your PPS Hub password',
                    f'<p>Hi {user_def["display"].split()[0]},</p>'
                    f'<p><a href="{link}">Click here to reset your PPS Hub password</a>. '
                    f'This link expires in 1 hour.</p>'
                    f'<p>If you did not request this, ignore this email.</p>',
                    f'Reset your PPS password: {link}\n\nThis link expires in 1 hour.',
                )
                if ok:
                    # Reset email path also clears lockout so they aren't blocked
                    # while waiting for the link.
                    clear_login_failures(get_db, user_key)
                    message = (
                        f'If {to_email} is on file, a reset link was sent. '
                        f'Open it on this phone. Any temporary lockout was cleared.'
                    )
                else:
                    print(f'Password reset email failed: {detail}')
                    error = 'Could not send email. Contact Thomas or Stephanie.'
    return _no_store_html(
        'forgot_password.html',
        users=sorted(USERS.items(), key=lambda x: x[1]['display']),
        message=message,
        error=error,
    )


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password_with_token(token):
    error = None
    if request.method == 'GET':
        if not peek_password_reset_token(get_db, token):
            error = 'This reset link is invalid or has expired.'
            return _no_store_html('reset_password.html', error=error, token=None)
        return _no_store_html('reset_password.html', error=None, token=token)

    token = request.form.get('token', '').strip()
    new_password = request.form.get('new_password', '') or ''
    confirm = request.form.get('confirm_password', '') or ''
    user_key = consume_password_reset_token(get_db, token)
    if not user_key:
        error = 'This reset link is invalid or has expired.'
    elif len(new_password) < 8:
        error = 'Password must be at least 8 characters.'
    elif new_password != confirm:
        error = 'Passwords do not match.'
    else:
        try:
            ok, action = _upsert_hub_user_password(user_key, new_password, must_change=False)
            if ok:
                clear_login_failures(get_db, user_key)
                print(f'Password reset via token for {user_key} ({action})')
                session['login_flash_user'] = user_key
                session['login_flash_success'] = (
                    'Password updated. Tap your name and sign in with the new password.'
                )
                session.pop('login_flash_error', None)
                resp = redirect(url_for('login'))
                resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
                return resp
            if action == 'no_db' or str(action).startswith('db_error:'):
                error = 'Database is temporarily unavailable. Wait a minute and try the link again, or contact Thomas.'
            elif action == 'password_too_short':
                error = 'Password must be at least 8 characters.'
            else:
                error = 'Could not save the new password. Contact Thomas or Stephanie.'
            print(f'reset password upsert failed for {user_key}: {action}')
        except Exception as e:
            print(f'reset password error for {user_key}: {e}')
            error = 'Something went wrong saving the password. Try again or contact Thomas.'
    return _no_store_html('reset_password.html', error=error, token=token)


@app.route('/change-password', methods=['GET', 'POST'])
@require_login
def change_password():
    error = None
    if request.method == 'POST':
        current = request.form.get('current_password', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm = request.form.get('confirm_password', '').strip()
        user_key = session['user_key']
        if len(new_password) < 8:
            error = 'New password must be at least 8 characters.'
        elif new_password != confirm:
            error = 'Passwords do not match.'
        else:
            try:
                conn = get_db()
                if conn:
                    cur = conn.cursor(cursor_factory=RealDictCursor)
                    cur.execute('SELECT password_hash FROM hub_users WHERE user_key = %s', (user_key,))
                    row = cur.fetchone()
                    if not row or not check_password_hash(row['password_hash'], current):
                        error = 'Current password is incorrect.'
                    else:
                        hashed = generate_password_hash(new_password)
                        cur.execute(
                            'UPDATE hub_users SET password_hash = %s, must_change_password = FALSE WHERE user_key = %s',
                            (hashed, user_key),
                        )
                        conn.commit()
                        session.pop('must_change_password', None)
                        cur.close()
                        conn.close()
                        return redirect(url_for('dashboard'))
                    cur.close()
                    conn.close()
            except Exception as e:
                print(f'change password error: {e}')
                error = 'Something went wrong. Please try again.'
    return render_template('change_password.html', error=error)


def _parse_siding_pricing_upload(pricing_file):
    from estimators.siding.pricing_parser import parse_pricing_upload
    return parse_pricing_upload(pricing_file)


def _load_siding_estimate_row(estimate_id, user_key=None):
    conn = get_db()
    if not conn:
        return None
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT * FROM siding_estimate_log WHERE id = %s', (estimate_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None
    if user_key and row.get('generated_by') != user_key and session.get('role') != 'admin':
        return None
    return row


def _siding_job_data_from_row(row):
    data = row.get('job_data') or {}
    if isinstance(data, str):
        data = json.loads(data)
    return data


def _build_siding_excel_from_row(row):
    from estimators.siding import build_estimate_excel
    data = _siding_job_data_from_row(row)
    return build_estimate_excel(
        data.get('job', {}),
        data.get('buildings', []),
        data.get('inputs', {}),
        data.get('pricing', {}),
        library_rows=data.get('library', []),
        confidence=data.get('confidence'),
    )


def _siding_filename(job):
    prop = (job.get('property_name') or 'Property').replace(' ', '_')
    return f'PPS_Siding_Estimate_{prop}.xlsx'


def _siding_preview_context(row):
    from estimators.siding import calculate_quantities, aggregate_building_quantities
    from estimators.siding.excel_builder import SOURCE_LABELS

    data = _siding_job_data_from_row(row)
    job = data.get('job', {})
    inputs = data.get('inputs', {})
    building_rows = []
    for b in data.get('buildings', []):
        qty = max(int(b.get('qty') or 1), 1)
        q = calculate_quantities(b.get('measurements') or {}, inputs, qty=qty)
        building_rows.append({
            'label': b.get('label') or 'Building',
            'building_type': b.get('building_type') or 'Building',
            'qty': qty,
            'source_label': SOURCE_LABELS.get(b.get('source'), b.get('source', '')),
            'quantities': q,
        })
    totals = aggregate_building_quantities(building_rows)
    return {
        'job': job,
        'inputs': inputs,
        'building_rows': building_rows,
        'totals': totals,
    }


@app.route('/siding-estimator')
@require_login
def siding_estimator():
    return render_template(
        'siding_estimator.html',
        display_name=session.get('display_name', ''),
        pricing_defaults=_pricing_defaults(),
    )


@app.route('/siding-estimator/parse', methods=['POST'])
@require_login
def siding_estimator_parse():
    pdf_file = request.files.get('pdf')
    if not pdf_file:
        return jsonify({'error': 'No PDF uploaded'}), 400
    source = (request.form.get('source') or 'eagleview').strip()
    try:
        from estimators.siding import parse_eagleview_walls, parse_aerial_report
        pdf_bytes = pdf_file.read()
        if source == 'eagleview':
            measurements, warnings = parse_eagleview_walls(pdf_bytes)
        else:
            measurements, warnings = parse_aerial_report(pdf_bytes)
        from estimators.reliability import build_siding_reliability
        confidence = build_siding_reliability(measurements, source=source)
        return jsonify({'measurements': measurements, 'warnings': warnings, 'confidence': confidence})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return _api_error(e)


@app.route('/siding-estimator/generate', methods=['POST'])
@require_login
def siding_estimator_generate():
    import json as _json
    try:
        job = _json.loads(request.form.get('job', '{}'))
        buildings = _json.loads(request.form.get('buildings', '[]'))
        inputs = _json.loads(request.form.get('inputs', '{}'))
        parsed_pricing = _parse_siding_pricing_upload(request.files.get('pricing'))
        pricing = parsed_pricing.get('prices', {})
        library_rows = parsed_pricing.get('library', [])

        if not buildings:
            return jsonify({'error': 'Add at least one building'}), 400

        from estimators.siding import build_estimate_excel
        from estimators.reliability import build_siding_job_reliability
        pricing_loaded = parsed_pricing.get('loaded_count', 0)
        confidence = build_siding_job_reliability(buildings, pricing_loaded)
        buf = build_estimate_excel(
            job, buildings, inputs, pricing, library_rows=library_rows, confidence=confidence
        )

        user_key = session['user_key']
        display_name = session.get('display_name', '')
        job_data = {
            'job': job,
            'buildings': buildings,
            'inputs': inputs,
            'pricing': pricing,
            'library': library_rows,
            'confidence': confidence,
            'pricing_meta': {
                'loaded_count': pricing_loaded,
                'warnings': parsed_pricing.get('warnings', []),
            },
        }
        estimate_id = None
        conn = get_db()
        if conn:
            cur = conn.cursor()
            siding_summary = ' · '.join(x for x in [
                f"{len(buildings)} building{'s' if len(buildings) != 1 else ''}",
                inputs.get('siding_type'),
            ] if x)
            cur.execute(
                '''INSERT INTO siding_estimate_log (
                    generated_by, display_name, property_name, property_address,
                    building_count, siding_type, summary_meta, job_data
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
                (
                    user_key,
                    display_name,
                    job.get('property_name'),
                    job.get('address'),
                    len(buildings),
                    inputs.get('siding_type'),
                    siding_summary[:255],
                    _json.dumps(job_data),
                ),
            )
            estimate_id = cur.fetchone()[0]
            conn.commit()
            cur.close()
            conn.close()

        if not estimate_id:
            return jsonify({'error': 'Could not save estimate to history'}), 500

        return jsonify({
            'success': True,
            'estimate_id': estimate_id,
            'redirect_url': url_for('siding_estimator_result', estimate_id=estimate_id),
            'pricing_loaded': parsed_pricing.get('loaded_count', 0),
            'pricing_warnings': parsed_pricing.get('warnings', []),
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return _api_error(e)


@app.route('/siding-estimator/result/<int:estimate_id>')
@require_login
def siding_estimator_result(estimate_id):
    row = _load_siding_estimate_row(estimate_id, session['user_key'])
    if not row:
        return 'Estimate not found', 404
    ctx = _siding_preview_context(row)
    data = _siding_job_data_from_row(row)
    return render_template(
        'siding_result.html',
        estimate_id=estimate_id,
        property_name=row.get('property_name') or 'Property',
        building_count=row.get('building_count') or 1,
        filename=_siding_filename(data.get('job', {})),
        totals=ctx['totals'],
        confidence=data.get('confidence'),
        user_email=session.get('user_email', ''),
    )


@app.route('/siding-estimator/preview/<int:estimate_id>')
@require_login
def siding_estimator_preview(estimate_id):
    row = _load_siding_estimate_row(estimate_id, session['user_key'])
    if not row:
        return 'Estimate not found', 404
    ctx = _siding_preview_context(row)
    return render_template(
        'siding_preview.html',
        estimate_id=estimate_id,
        **ctx,
    )


@app.route('/siding-estimator/download/<int:estimate_id>')
@require_login
def siding_estimator_download(estimate_id):
    row = _load_siding_estimate_row(estimate_id, session['user_key'])
    if not row:
        return 'Estimate not found', 404
    try:
        data = _siding_job_data_from_row(row)
        buf = _build_siding_excel_from_row(row)
        return send_file(
            buf,
            as_attachment=True,
            download_name=_siding_filename(data.get('job', {})),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
    except Exception as e:
        _log_exception(e)
        return GENERIC_DOWNLOAD_ERROR, 500


@app.route('/siding-estimator/email/<int:estimate_id>', methods=['POST'])
@require_login
def siding_estimator_email(estimate_id):
    row = _load_siding_estimate_row(estimate_id, session['user_key'])
    if not row:
        return jsonify({'error': 'Estimate not found'}), 404
    payload = request.get_json(silent=True) or {}
    to_email = (payload.get('to_email') or session.get('user_email') or '').strip()
    if not to_email:
        return jsonify({'error': 'No email address'}), 400
    try:
        data = _siding_job_data_from_row(row)
        buf = _build_siding_excel_from_row(row)
        doc_b64 = base64.b64encode(buf.getvalue()).decode('ascii')
        return _send_resend_document(
            to_email=to_email,
            doc_type='siding_estimate',
            filename=_siding_filename(data.get('job', {})),
            property_name=data.get('job', {}).get('property_name', ''),
            doc_b64=doc_b64,
            sender_name=session.get('display_name', 'PPS Hub'),
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return _api_error(e)


@app.route('/siding-estimator/pricing-preview', methods=['POST'])
@require_login
def siding_pricing_preview():
    parsed = _parse_siding_pricing_upload(request.files.get('pricing'))
    return jsonify({
        'loaded_count': parsed.get('loaded_count', 0),
        'warnings': parsed.get('warnings', []),
        'price_count': len(parsed.get('prices', {})),
        'library_count': len(parsed.get('library', [])),
    })


@app.route('/siding-estimator/pricing-template')
@require_login
def siding_pricing_template():
    import csv
    import io
    from flask import Response

    template_rows = [
        ['item_name', 'unit_price', 'qty_per_sq'],
        ['NDX Vinyl Siding', '', ''],
        ['QA Starter', '', ''],
        ['NDX 5/8 J Channel', '', ''],
        ['NDX Inside Corner 3/4', '', ''],
        ["NDX 12' Outside Corner", '', ''],
        ['Roll of Coil Stock', '', ''],
        ['NDX Universal Trim', '', ''],
        ['House Wrap', '', ''],
        ['House Wrap Tape', '', ''],
        ['J Block Uniblock', '', ''],
        ['J Block M Block', '', ''],
        ['Exhaust Vent', '', ''],
        ['Roofing Nails', '', ''],
        ['Cap Nails', '', ''],
        ['', '', ''],
        ['NDX Vinyl Siding (per sq)', '', '1'],
        ['NDX 5/8 J Channel', '5', ''],
        ['QA Starter', '5', ''],
    ]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(template_rows)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=PPS_Siding_Pricing_Template.csv'},
    )


def _roofing_job_data_from_row(row):
    data = row.get('job_data') or {}
    if isinstance(data, str):
        data = json.loads(data)
    return data


def _load_roofing_estimate_row(estimate_id, user_key=None):
    conn = get_db()
    if not conn:
        return None
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT * FROM roofing_estimate_log WHERE id = %s', (estimate_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None
    if user_key and row.get('generated_by') != user_key and session.get('role') != 'admin':
        return None
    return row


def _roofing_preview_context(row):
    from estimators.roofing import calculate_materials, calculate_bid_summary
    from estimators.roofing.excel_builder import REPORT_LABELS
    from estimators.roofing.material_catalog import MATERIAL_LINES

    data = _roofing_job_data_from_row(row)
    measurements = data.get('measurements', {})
    inputs = data.get('inputs', {})
    report_type = measurements.get('report_type', 'premium')
    is_quick = report_type == 'bid_perfect'
    ctx = {
        'job': data.get('job', {}),
        'inputs': inputs,
        'measurements': measurements,
        'report_label': REPORT_LABELS.get(report_type, report_type),
        'is_quick_bid': is_quick,
    }
    if is_quick:
        ctx['summary'] = calculate_bid_summary(measurements, inputs)
    else:
        qty = calculate_materials(measurements, inputs)
        ctx['summary'] = qty
        ctx['material_lines'] = [
            {'label': label, 'qty': qty.get(qk, 0)}
            for _k, label, _u, qk in MATERIAL_LINES
        ]
    return ctx


def _roofing_filename(job):
    prop = (job.get('property_name') or 'Property').replace(' ', '_')
    return f'PPS_Roof_Estimate_{prop}.xlsx'


@app.route('/roofing-estimator')
@require_login
def roofing_estimator():
    return render_template(
        'roofing_estimator.html',
        display_name=session.get('display_name', ''),
        pricing_defaults=_pricing_defaults(),
    )


@app.route('/roofing-estimator/parse', methods=['POST'])
@require_login
def roofing_estimator_parse():
    pdf_file = request.files.get('pdf')
    if not pdf_file:
        return jsonify({'error': 'No PDF uploaded'}), 400
    try:
        from estimators.roofing import parse_roof_report
        from estimators.reliability import build_roofing_reliability
        measurements, warnings = parse_roof_report(pdf_file.read())
        confidence = build_roofing_reliability(measurements, {})
        return jsonify({'measurements': measurements, 'warnings': warnings, 'confidence': confidence})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return _api_error(e)


@app.route('/roofing-estimator/generate', methods=['POST'])
@require_login
def roofing_estimator_generate():
    import json as _json
    try:
        job = _json.loads(request.form.get('job', '{}'))
        measurements = _json.loads(request.form.get('measurements', '{}'))
        inputs = _json.loads(request.form.get('inputs', '{}'))

        if not measurements.get('roof_area_sqft') and not measurements.get('structures'):
            return jsonify({'error': 'No roof measurements — upload a valid report PDF.'}), 400

        from estimators.roofing import build_estimate_excel
        from estimators.reliability import build_roofing_reliability
        confidence = build_roofing_reliability(measurements, inputs)
        buf = build_estimate_excel(job, measurements, inputs, {}, confidence=confidence)

        job_data = {
            'job': job,
            'measurements': measurements,
            'inputs': inputs,
            'confidence': confidence,
        }
        estimate_id = None
        conn = get_db()
        if conn:
            cur = conn.cursor()
            roofing_summary = measurements.get('report_type') or 'report'
            if measurements.get('roof_area_squares'):
                roofing_summary = f"{roofing_summary} · {measurements.get('roof_area_squares')} sq"
            cur.execute(
                '''INSERT INTO roofing_estimate_log (
                    generated_by, display_name, property_name, property_address,
                    report_type, summary_meta, job_data
                ) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
                (
                    session['user_key'],
                    session.get('display_name', ''),
                    job.get('property_name'),
                    job.get('address'),
                    measurements.get('report_type'),
                    roofing_summary[:255],
                    _json.dumps(job_data),
                ),
            )
            estimate_id = cur.fetchone()[0]
            conn.commit()
            cur.close()
            conn.close()

        if not estimate_id:
            return jsonify({'error': 'Could not save estimate to history'}), 500

        return jsonify({
            'success': True,
            'estimate_id': estimate_id,
            'redirect_url': url_for('roofing_estimator_result', estimate_id=estimate_id),
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return _api_error(e)


@app.route('/roofing-estimator/result/<int:estimate_id>')
@require_login
def roofing_estimator_result(estimate_id):
    row = _load_roofing_estimate_row(estimate_id, session['user_key'])
    if not row:
        return 'Estimate not found', 404
    ctx = _roofing_preview_context(row)
    data = _roofing_job_data_from_row(row)
    return render_template(
        'roofing_result.html',
        estimate_id=estimate_id,
        property_name=row.get('property_name') or 'Property',
        filename=_roofing_filename(data.get('job', {})),
        report_label=ctx['report_label'],
        is_quick_bid=ctx['is_quick_bid'],
        summary=ctx['summary'],
        confidence=data.get('confidence'),
        user_email=session.get('user_email', ''),
    )


@app.route('/roofing-estimator/preview/<int:estimate_id>')
@require_login
def roofing_estimator_preview(estimate_id):
    row = _load_roofing_estimate_row(estimate_id, session['user_key'])
    if not row:
        return 'Estimate not found', 404
    ctx = _roofing_preview_context(row)
    return render_template('roofing_preview.html', estimate_id=estimate_id, **ctx)


@app.route('/roofing-estimator/download/<int:estimate_id>')
@require_login
def roofing_estimator_download(estimate_id):
    row = _load_roofing_estimate_row(estimate_id, session['user_key'])
    if not row:
        return 'Estimate not found', 404
    try:
        from estimators.roofing import build_estimate_excel
        data = _roofing_job_data_from_row(row)
        buf = build_estimate_excel(
            data.get('job', {}),
            data.get('measurements', {}),
            data.get('inputs', {}),
            data.get('pricing', {}),
            confidence=data.get('confidence'),
        )
        return send_file(
            buf,
            as_attachment=True,
            download_name=_roofing_filename(data.get('job', {})),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
    except Exception as e:
        _log_exception(e)
        return GENERIC_DOWNLOAD_ERROR, 500


@app.route('/roofing-estimator/email/<int:estimate_id>', methods=['POST'])
@require_login
def roofing_estimator_email(estimate_id):
    row = _load_roofing_estimate_row(estimate_id, session['user_key'])
    if not row:
        return jsonify({'error': 'Estimate not found'}), 404
    payload = request.get_json(silent=True) or {}
    to_email = (payload.get('to_email') or session.get('user_email') or '').strip()
    if not to_email:
        return jsonify({'error': 'No email address'}), 400
    try:
        from estimators.roofing import build_estimate_excel
        data = _roofing_job_data_from_row(row)
        buf = build_estimate_excel(
            data.get('job', {}),
            data.get('measurements', {}),
            data.get('inputs', {}),
            data.get('pricing', {}),
            confidence=data.get('confidence'),
        )
        doc_b64 = base64.b64encode(buf.getvalue()).decode('ascii')
        return _send_resend_document(
            to_email=to_email,
            doc_type='roofing_estimate',
            filename=_roofing_filename(data.get('job', {})),
            property_name=data.get('job', {}).get('property_name', ''),
            doc_b64=doc_b64,
            sender_name=session.get('display_name', 'PPS Hub'),
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return _api_error(e)


def _gutter_job_data_from_row(row):
    data = row.get('job_data') or {}
    if isinstance(data, str):
        data = json.loads(data)
    return data


def _load_gutter_estimate_row(estimate_id, user_key=None):
    conn = get_db()
    if not conn:
        return None
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT * FROM gutter_estimate_log WHERE id = %s', (estimate_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None
    if user_key and row.get('generated_by') != user_key and session.get('role') != 'admin':
        return None
    return row


def _gutter_preview_context(row):
    from estimators.gutter import calculate_gutter_estimate

    data = _gutter_job_data_from_row(row)
    summary = calculate_gutter_estimate(
        data.get('measurements', {}),
        data.get('inputs', {}),
    )
    return {
        'job': data.get('job', {}),
        'inputs': data.get('inputs', {}),
        'measurements': data.get('measurements', {}),
        'summary': summary,
    }


def _gutter_filename(job):
    prop = (job.get('property_name') or 'Property').replace(' ', '_')
    return f'PPS_Gutter_Estimate_{prop}.xlsx'


@app.route('/gutter-estimator')
@require_login
def gutter_estimator():
    return render_template(
        'gutter_estimator.html',
        display_name=session.get('display_name', ''),
        pricing_defaults=_pricing_defaults(),
    )


@app.route('/gutter-estimator/parse', methods=['POST'])
@require_login
def gutter_estimator_parse():
    pdf_file = request.files.get('pdf')
    if not pdf_file:
        return jsonify({'error': 'No PDF uploaded'}), 400
    try:
        from estimators.gutter import parse_gutter_measurements
        from estimators.reliability import build_gutter_reliability
        measurements, warnings = parse_gutter_measurements(pdf_file.read())
        confidence = build_gutter_reliability(measurements, {})
        return jsonify({'measurements': measurements, 'warnings': warnings, 'confidence': confidence})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return _api_error(e)


@app.route('/gutter-estimator/generate', methods=['POST'])
@require_login
def gutter_estimator_generate():
    import json as _json
    try:
        job = _json.loads(request.form.get('job', '{}'))
        measurements = _json.loads(request.form.get('measurements', '{}'))
        inputs = _json.loads(request.form.get('inputs', '{}'))

        gutter_lf = float(measurements.get('gutter_lf') or measurements.get('eaves_ft') or 0)
        if not gutter_lf:
            return jsonify({'error': 'Enter gutter run (LF) or upload a report with eaves length.'}), 400

        from estimators.gutter import build_estimate_excel, calculate_gutter_estimate
        from estimators.reliability import build_gutter_reliability
        user_overrides = inputs.pop('user_overrides', None) or {}
        calc = calculate_gutter_estimate(measurements, inputs)
        confidence = build_gutter_reliability(measurements, inputs, user_overrides)
        buf = build_estimate_excel(job, measurements, inputs, confidence=confidence)

        job_data = {
            'job': job,
            'measurements': measurements,
            'inputs': inputs,
            'confidence': confidence,
        }
        estimate_id = None
        conn = get_db()
        if conn:
            cur = conn.cursor()
            gutter_summary = f"{float(calc.get('gutter_lf_raw') or 0):.0f} LF"
            cur.execute(
                '''INSERT INTO gutter_estimate_log (
                    generated_by, display_name, property_name, property_address,
                    gutter_lf, summary_meta, job_data
                ) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
                (
                    session['user_key'],
                    session.get('display_name', ''),
                    job.get('property_name'),
                    job.get('address'),
                    calc.get('gutter_lf_raw'),
                    gutter_summary[:255],
                    _json.dumps(job_data),
                ),
            )
            estimate_id = cur.fetchone()[0]
            conn.commit()
            cur.close()
            conn.close()

        if not estimate_id:
            return jsonify({'error': 'Could not save estimate to history'}), 500

        return jsonify({
            'success': True,
            'estimate_id': estimate_id,
            'redirect_url': url_for('gutter_estimator_result', estimate_id=estimate_id),
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return _api_error(e)


@app.route('/gutter-estimator/preview/<int:estimate_id>')
@require_login
def gutter_estimator_preview(estimate_id):
    row = _load_gutter_estimate_row(estimate_id, session['user_key'])
    if not row:
        return 'Estimate not found', 404
    ctx = _gutter_preview_context(row)
    data = _gutter_job_data_from_row(row)
    return render_template(
        'gutter_preview.html',
        estimate_id=estimate_id,
        confidence=data.get('confidence'),
        **ctx,
    )


@app.route('/gutter-estimator/result/<int:estimate_id>')
@require_login
def gutter_estimator_result(estimate_id):
    row = _load_gutter_estimate_row(estimate_id, session['user_key'])
    if not row:
        return 'Estimate not found', 404
    ctx = _gutter_preview_context(row)
    data = _gutter_job_data_from_row(row)
    return render_template(
        'gutter_result.html',
        estimate_id=estimate_id,
        property_name=row.get('property_name') or 'Property',
        summary=ctx['summary'],
        confidence=data.get('confidence'),
        user_email=session.get('user_email', ''),
    )


@app.route('/gutter-estimator/download/<int:estimate_id>')
@require_login
def gutter_estimator_download(estimate_id):
    row = _load_gutter_estimate_row(estimate_id, session['user_key'])
    if not row:
        return 'Estimate not found', 404
    try:
        from estimators.gutter import build_estimate_excel
        data = _gutter_job_data_from_row(row)
        buf = build_estimate_excel(
            data.get('job', {}),
            data.get('measurements', {}),
            data.get('inputs', {}),
            confidence=data.get('confidence'),
        )
        return send_file(
            buf,
            as_attachment=True,
            download_name=_gutter_filename(data.get('job', {})),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
    except Exception as e:
        _log_exception(e)
        return GENERIC_DOWNLOAD_ERROR, 500


@app.route('/gutter-estimator/email/<int:estimate_id>', methods=['POST'])
@require_login
def gutter_estimator_email(estimate_id):
    row = _load_gutter_estimate_row(estimate_id, session['user_key'])
    if not row:
        return jsonify({'error': 'Estimate not found'}), 404
    payload = request.get_json(silent=True) or {}
    to_email = (payload.get('to_email') or session.get('user_email') or '').strip()
    if not to_email:
        return jsonify({'error': 'No email address'}), 400
    try:
        from estimators.gutter import build_estimate_excel
        data = _gutter_job_data_from_row(row)
        buf = build_estimate_excel(
            data.get('job', {}),
            data.get('measurements', {}),
            data.get('inputs', {}),
            confidence=data.get('confidence'),
        )
        doc_b64 = base64.b64encode(buf.getvalue()).decode('ascii')
        return _send_resend_document(
            to_email=to_email,
            doc_type='gutter_estimate',
            filename=_gutter_filename(data.get('job', {})),
            property_name=data.get('job', {}).get('property_name', ''),
            doc_b64=doc_b64,
            sender_name=session.get('display_name', 'PPS Hub'),
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return _api_error(e)


def _painting_job_data_from_row(row):
    data = row.get('job_data') or {}
    if isinstance(data, str):
        data = json.loads(data)
    return data


def _load_painting_estimate_row(estimate_id, user_key=None):
    conn = get_db()
    if not conn:
        return None
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT * FROM painting_estimate_log WHERE id = %s', (estimate_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None
    if user_key and row.get('generated_by') != user_key and session.get('role') != 'admin':
        return None
    return row


def _painting_preview_context(row):
    from estimators.painting import calculate_painting_estimate

    data = _painting_job_data_from_row(row)
    summary = calculate_painting_estimate(
        data.get('line_items', []),
        data.get('inputs', {}),
    )
    return {
        'job': data.get('job', {}),
        'inputs': data.get('inputs', {}),
        'measurements': data.get('measurements', {}),
        'line_items': data.get('line_items', []),
        'summary': summary,
    }


def _painting_filename(job):
    prop = (job.get('property_name') or 'Property').replace(' ', '_')
    return f'PPS_Painting_Estimate_{prop}.xlsx'


@app.route('/painting-estimator')
@require_login
def painting_estimator():
    from estimators.painting import sections_for_ui
    return render_template(
        'painting_estimator.html',
        display_name=session.get('display_name', ''),
        pricing_defaults=_pricing_defaults(),
        sections=sections_for_ui(),
    )


@app.route('/painting-estimator/generate', methods=['POST'])
@require_login
def painting_estimator_generate():
    import json as _json
    try:
        job = _json.loads(request.form.get('job', '{}'))
        measurements = _json.loads(request.form.get('measurements', '{}'))
        line_items = _json.loads(request.form.get('line_items', '[]'))
        inputs = _json.loads(request.form.get('inputs', '{}'))

        active = [li for li in line_items if li.get('measured')]
        if not active:
            return jsonify({'error': 'Enter at least one measured quantity in the takeoff.'}), 400

        from estimators.painting import build_estimate_excel, calculate_painting_estimate
        from estimators.reliability import build_painting_reliability
        user_overrides = inputs.pop('user_overrides', None) or {}
        calc = calculate_painting_estimate(active, inputs)
        confidence = build_painting_reliability(measurements, active, user_overrides)
        buf = build_estimate_excel(job, active, inputs, confidence=confidence)

        job_data = {
            'job': job,
            'measurements': measurements,
            'line_items': active,
            'inputs': inputs,
            'confidence': confidence,
        }
        estimate_id = None
        conn = get_db()
        if conn:
            cur = conn.cursor()
            painting_parts = []
            if calc.get('line_count'):
                painting_parts.append(f"{calc.get('line_count')} lines")
            if calc.get('one_coat_bid'):
                painting_parts.append(f"${float(calc.get('one_coat_bid')):,.0f} 1-coat")
            painting_summary = ' · '.join(painting_parts)
            cur.execute(
                '''INSERT INTO painting_estimate_log (
                    generated_by, display_name, property_name, property_address,
                    line_count, one_coat_bid, two_coat_bid, summary_meta, job_data
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
                (
                    session['user_key'],
                    session.get('display_name', ''),
                    job.get('property_name'),
                    job.get('address'),
                    calc.get('line_count'),
                    calc.get('one_coat_bid'),
                    calc.get('two_coat_bid'),
                    painting_summary[:255],
                    _json.dumps(job_data),
                ),
            )
            estimate_id = cur.fetchone()[0]
            conn.commit()
            cur.close()
            conn.close()

        if not estimate_id:
            return jsonify({'error': 'Could not save estimate to history'}), 500

        return jsonify({
            'success': True,
            'estimate_id': estimate_id,
            'redirect_url': url_for('painting_estimator_result', estimate_id=estimate_id),
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return _api_error(e)


@app.route('/painting-estimator/preview/<int:estimate_id>')
@require_login
def painting_estimator_preview(estimate_id):
    row = _load_painting_estimate_row(estimate_id, session['user_key'])
    if not row:
        return 'Estimate not found', 404
    ctx = _painting_preview_context(row)
    data = _painting_job_data_from_row(row)
    return render_template(
        'painting_preview.html',
        estimate_id=estimate_id,
        confidence=data.get('confidence'),
        **ctx,
    )


@app.route('/painting-estimator/result/<int:estimate_id>')
@require_login
def painting_estimator_result(estimate_id):
    row = _load_painting_estimate_row(estimate_id, session['user_key'])
    if not row:
        return 'Estimate not found', 404
    ctx = _painting_preview_context(row)
    data = _painting_job_data_from_row(row)
    return render_template(
        'painting_result.html',
        estimate_id=estimate_id,
        property_name=row.get('property_name') or 'Property',
        summary=ctx['summary'],
        confidence=data.get('confidence'),
        user_email=session.get('user_email', ''),
    )


@app.route('/painting-estimator/download/<int:estimate_id>')
@require_login
def painting_estimator_download(estimate_id):
    row = _load_painting_estimate_row(estimate_id, session['user_key'])
    if not row:
        return 'Estimate not found', 404
    try:
        from estimators.painting import build_estimate_excel
        data = _painting_job_data_from_row(row)
        buf = build_estimate_excel(
            data.get('job', {}),
            data.get('line_items', []),
            data.get('inputs', {}),
            confidence=data.get('confidence'),
        )
        return send_file(
            buf,
            as_attachment=True,
            download_name=_painting_filename(data.get('job', {})),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
    except Exception as e:
        _log_exception(e)
        return GENERIC_DOWNLOAD_ERROR, 500


@app.route('/painting-estimator/email/<int:estimate_id>', methods=['POST'])
@require_login
def painting_estimator_email(estimate_id):
    row = _load_painting_estimate_row(estimate_id, session['user_key'])
    if not row:
        return jsonify({'error': 'Estimate not found'}), 404
    payload = request.get_json(silent=True) or {}
    to_email = (payload.get('to_email') or session.get('user_email') or '').strip()
    if not to_email:
        return jsonify({'error': 'No email address'}), 400
    try:
        from estimators.painting import build_estimate_excel
        data = _painting_job_data_from_row(row)
        buf = build_estimate_excel(
            data.get('job', {}),
            data.get('line_items', []),
            data.get('inputs', {}),
            confidence=data.get('confidence'),
        )
        doc_b64 = base64.b64encode(buf.getvalue()).decode('ascii')
        return _send_resend_document(
            to_email=to_email,
            doc_type='painting_estimate',
            filename=_painting_filename(data.get('job', {})),
            property_name=data.get('job', {}).get('property_name', ''),
            doc_b64=doc_b64,
            sender_name=session.get('display_name', 'PPS Hub'),
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return _api_error(e)


@app.errorhandler(HTTPException)
def _handle_http_exception(e):
    if _wants_json_response():
        message = e.description or GENERIC_API_ERROR
        payload = {'success': False, 'error': message}
        if request.path.startswith('/api/'):
            payload = {'success': False, 'error': message}
        return jsonify(payload), e.code
    return e


@app.errorhandler(Exception)
def _handle_uncaught_exception(e):
    if isinstance(e, HTTPException):
        return e
    _log_exception(e, request.path)
    if _wants_json_response():
        payload = {'success': False, 'error': GENERIC_API_ERROR}
        if request.path.startswith('/api/'):
            payload = {'success': False, 'error': GENERIC_API_ERROR}
        return jsonify(payload), 500
    return GENERIC_API_ERROR, 500


@app.route('/logout')
def logout():
    import urllib.parse
    session.clear()
    final = f'{HUB_PUBLIC_URL}/login'
    if PROPOSAL_URL:
        nxt = urllib.parse.quote(final, safe='')
        return redirect(f'{PROPOSAL_URL}/logout?next={nxt}')
    return redirect(url_for('login'))


ask_pps.register_routes(app, get_db, USERS, CLAUDE_API_KEY, CLAUDE_MODEL, require_login)


if __name__ == '__main__':
    app.run(debug=True)
