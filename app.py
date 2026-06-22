import os
import json
import base64
from io import BytesIO
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from psc_training_data import (
    PSC_TRAINING_META, PSC_TRAINING_MANAGER, get_training_curriculum,
    get_all_item_ids, count_trackable_items,
)
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor
from auth_helpers import (
    HUB_PUBLIC_URL, PROPOSAL_URL, PROFILE_URL, LOGIN_LOCKOUT_MINUTES,
    safe_next_url, client_ip, record_login_attempt, is_login_locked,
    generate_sso_code, exchange_sso_code,
    create_password_reset_token, peek_password_reset_token,
    consume_password_reset_token, reset_url_for_token,
)


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
        'email': 'Ben@purepropsolutions.com',
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
        # User sees their own events
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
                    'message': f"🎂 Your birthday is {event_label(bday_days)} — {MONTH_NAMES[dates['birthday'][0]-1]} {dates['birthday'][1]}. Hope it's a good one.",
                })
            if hire_days <= 3 and years >= 1:
                events.append({
                    'type': 'anniversary',
                    'message': f"🏆 {years} year{'s' if years > 1 else ''} at PPS {event_label(hire_days)}. That's worth something.",
                })

    events.sort(key=lambda x: x['days'])
    return events

CONSULTANTS = {
    'tony_cumella': 'Tony Cumella',
    'adam_cupito': 'Adam Cupito',
    'rachel_farler': 'Rachel Farler',
    'andy_potts': 'Andy Potts',
}

# ── DATABASE ────────────────────────────────────────────────────────────────────

def get_db():
    if not DATABASE_URL:
        return None
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn


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
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_psc_training_notes_user ON psc_training_notes(user_key)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_psc_training_feedback_time ON psc_training_feedback(submitted_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_psc_training_enrollment_active ON psc_training_enrollment(active)")
    except Exception:
        pass

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


try:
    init_db()
except Exception as e:
    print(f"DB init error: {e}")

# Safe migration — create auth_tokens if it doesn't exist yet
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


# ── HELPERS ─────────────────────────────────────────────────────────────────────

def get_current_user():
    return session.get('user_key')


def require_login(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_key'):
            return redirect(url_for('login', next=request.url))
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
        with smtplib.SMTP_SSL(smtp_host, 465) as s:
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
        return True
    except Exception as e:
        print(f"PSC accountability email failed: {e}")
        return False


def _psc_week_labels():
    onboarding, weeks, _, _ = get_training_curriculum()
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
    onboarding, weeks, _, _ = get_training_curriculum()
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
    onboarding, weeks, core_values, sales_training = get_training_curriculum()
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

    result[0] = collect(onboarding)
    for section in core_values['sections']:
        for act in section.get('activities', []):
            result[0].append(act['id'])
    for module in sales_training['modules']:
        for item in module['items']:
            result[0].append(item['id'])
    for w in weeks:
        result[w['week']] = collect(w)
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


def _internal_api_ok():
    if not INTERNAL_API_KEY:
        return False
    api_key = request.headers.get('X-API-Key', '')
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

    if DATABASE_URL:
        try:
            conn = get_db()
            if conn:
                cur = conn.cursor()
                cur.execute('SELECT 1')
                cur.close()
                conn.close()
                add('database_connect', True)
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


@app.route('/')
def index():
    if session.get('user_key'):
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


def _post_login_redirect():
    nxt = safe_next_url(session.pop('login_next', None) or request.args.get('next', ''))
    if nxt:
        return redirect(nxt)
    return redirect(url_for('dashboard'))


def _establish_session(user_key, user_def, db_user=None):
    session.permanent = True
    session['user_key'] = user_key
    session['display_name'] = user_def.get('display', '')
    session['role'] = user_def.get('role', 'consultant')
    session['proposal_access'] = get_user_proposal_access(user_key)
    session['team_view'] = user_def.get('team_view', False)
    session['team_view_scope'] = user_def.get('team_view_scope')
    if db_user and db_user.get('must_change_password'):
        session['must_change_password'] = True


@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_key'):
        return _post_login_redirect()

    error = None
    next_url = safe_next_url(request.args.get('next', ''))
    if next_url:
        session['login_next'] = next_url

    if request.method == 'POST':
        next_from_form = safe_next_url(request.form.get('next', ''))
        if next_from_form:
            session['login_next'] = next_from_form
        user_key = request.form.get('user_key', '').strip()
        password = request.form.get('password', '').strip()
        ip = client_ip(request)

        if is_login_locked(get_db, user_key):
            error = f'Too many failed attempts. Try again in {LOGIN_LOCKOUT_MINUTES} minutes or use Forgot Password.'
        else:
            logged_in = False
            db_user = None

            # Optional break-glass master password (env only, disabled when unset)
            if MASTER_PASSWORD and password == MASTER_PASSWORD:
                user = USERS.get(user_key)
                if user:
                    session['role'] = 'admin'
                    session['admin'] = True
                    session['proposal_access'] = list(CONSULTANTS.keys())
                    _establish_session(user_key, user)
                    record_login_attempt(get_db, user_key, True, ip)
                    _update_last_login(user_key)
                    return _post_login_redirect()

            try:
                conn = get_db()
                if conn:
                    cur = conn.cursor(cursor_factory=RealDictCursor)
                    cur.execute('SELECT * FROM hub_users WHERE user_key = %s', (user_key,))
                    db_user = cur.fetchone()
                    cur.close()
                    conn.close()

                    if db_user and check_password_hash(db_user['password_hash'], password):
                        user = USERS.get(user_key, {})
                        _establish_session(user_key, user, db_user)
                        record_login_attempt(get_db, user_key, True, ip)
                        _update_last_login(user_key)
                        logged_in = True
                        if session.get('must_change_password'):
                            return redirect(url_for('change_password'))
                        return _post_login_redirect()

                if not logged_in:
                    record_login_attempt(get_db, user_key, False, ip)
                    error = 'Incorrect password. Please try again.'
            except Exception as e:
                print(f"Login error: {e}")
                error = 'Something went wrong. Please try again.'

            if not logged_in and not error and not DATABASE_URL:
                error = 'Database unavailable. Please try again shortly.'

    return render_template('login.html',
                           users=sorted(USERS.items(), key=lambda x: x[1]['display']),
                           error=error,
                           next_url=next_url or '')


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
    # Recent Trade Partner Scopes
    recent_tpscopes = []
    all_my_ppms = []
    all_my_tpscopes = []
    try:
        conn_tps = get_db()
        if conn_tps:
            cur_tps = conn_tps.cursor(cursor_factory=RealDictCursor)
            # Recent TPS
            cur_tps.execute('SELECT * FROM subscope_log WHERE generated_by = %s ORDER BY generated_at DESC LIMIT 5', (user_key,))
            recent_tpscopes = cur_tps.fetchall()
            # Full PPM history — PMs see all PPMs where they are listed as PM
            user_def = USERS.get(user_key, {})
            if user_def.get('role') in ('pm', 'admin'):
                cur_tps.execute(
                    '''SELECT * FROM ppm_log WHERE generated_by = %s OR pm_key = %s
                       ORDER BY generated_at DESC''',
                    (user_key, user_key)
                )
            else:
                cur_tps.execute('SELECT * FROM ppm_log WHERE generated_by = %s ORDER BY generated_at DESC', (user_key,))
            all_my_ppms = cur_tps.fetchall()
            # Full TPS history
            cur_tps.execute('SELECT * FROM subscope_log WHERE generated_by = %s ORDER BY generated_at DESC', (user_key,))
            all_my_tpscopes = cur_tps.fetchall()
            cur_tps.close()
            conn_tps.close()
    except Exception as e:
        print(f"Recent activity error: {e}")
    is_admin = (user.get('role') == 'admin')
    # Get date events
    date_events = get_date_events(user_key, is_admin=is_admin)
    # Get full proposal history for consultants
    all_my_proposals = []
    if user.get('role') in ('consultant', 'admin'):
        try:
            conn2 = get_db()
            if conn2:
                cur2 = conn2.cursor(cursor_factory=RealDictCursor)
                cur2.execute('SELECT * FROM proposal_log WHERE generated_by = %s ORDER BY generated_at DESC', (user_key,))
                all_my_proposals = cur2.fetchall()
                cur2.close()
                conn2.close()
        except: pass
    team_view = user.get('team_view', False)
    team_view_scope = user.get('team_view_scope')
    psc_training_stats = None
    psc_training_enrolled = is_psc_training_enrolled(user_key)
    if psc_training_enrolled:
        psc_training_stats = compute_psc_training_stats(user_key)
    psc_training_oversight = can_psc_training_oversight(user_key)
    return render_template('dashboard.html',
                           user=user,
                           user_key=user_key,
                           team_view=team_view,
                           team_view_scope=team_view_scope,
                           consultants=accessible_consultants,
                           recent_proposals=recent_proposals,
                           recent_ppms=recent_ppms,
                           recent_tpscopes=recent_tpscopes,
                           all_my_proposals=all_my_proposals,
                           all_my_ppms=all_my_ppms,
                           all_my_tpscopes=all_my_tpscopes,
                           date_events=date_events,
                           psc_training_stats=psc_training_stats,
                           psc_training_enrolled=psc_training_enrolled,
                           psc_training_oversight=psc_training_oversight,
                           proposal_url=os.environ.get('PROPOSAL_URL', 'https://pps-proposal-tool.onrender.com'))


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
            _touch_last_active(data.get('generated_by'))
        return jsonify({'success': True})
    except Exception as e:
        print(f"Log proposal error: {e}")
        return jsonify({'error': str(e)}), 500


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
        return jsonify({'error': str(e)}), 500


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
             property_name, property_address, property_type, template_type,
             proposal_number, existing_issue, intended_outcome, scopes_selected, scope_notes,
             contact_name, contact_email, company, scope_details, other_scope,
             pricing_json, warranty_pps, warranty_mfg, proposal_date, expiry_date, contract_total)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
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
        _touch_last_active(data.get('generated_by') or user_key)
        return jsonify({'success': True, 'log_id': log_id, 'document_id': document_id})
    except Exception as e:
        print(f"Vault store error: {e}")
        return jsonify({'error': str(e)}), 500


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
        return jsonify({'error': str(e)}), 500


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
        return jsonify({'error': str(e)}), 500


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
            SELECT d.id, d.doc_type, d.filename, d.size_bytes, d.created_at, d.user_key,
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
    unread_feedback = 0
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
                cur.execute('SELECT COUNT(*) as cnt FROM feedback WHERE read_by_admin = FALSE')
                unread_feedback = cur.fetchone()['cnt']
            except Exception:
                pass
            try:
                cur.execute('SELECT COUNT(*) as cnt FROM clients')
                client_count = cur.fetchone()['cnt']
            except Exception:
                pass
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Admin error: {e}")

    return render_template('admin.html', users=rows, all_proposals=all_proposals,
                           all_ppms=all_ppms, all_subscopes=all_subscopes,
                           unread_feedback=unread_feedback,
                           client_count=client_count,
                           proposals_30d=proposals_30d, ppms_30d=ppms_30d, subscopes_30d=subscopes_30d,
                           breakdown=breakdown, vault=vault,
                           user_definitions=USERS)


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
        return jsonify({'error': str(e)}), 500
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
        return jsonify({'error': str(e)}), 500


@app.route('/admin/reset-password', methods=['POST'])
@require_admin
def admin_reset_password():
    user_key = request.form.get('user_key')
    new_password = request.form.get('new_password', '').strip()
    if not user_key or not new_password or len(new_password) < 6:
        return jsonify({'error': 'Invalid request'}), 400
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor()
            hashed = generate_password_hash(new_password)
            cur.execute(
                'UPDATE hub_users SET password_hash = %s, must_change_password = FALSE WHERE user_key = %s',
                (hashed, user_key),
            )
            conn.commit()
            cur.close()
            conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


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
        return jsonify({'error': str(e)}), 500


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
        return jsonify({'error': str(e)}), 500


def _send_feedback_email(name, message):
    import smtplib
    from email.mime.text import MIMEText
    smtp_host = os.environ.get('SMTP_HOST', '')
    smtp_user = os.environ.get('SMTP_USER', '')
    smtp_pass = os.environ.get('SMTP_PASS', '')
    if not smtp_host:
        print(f"Feedback from {name}: {message}")
        return
    try:
        msg = MIMEText(f"Feedback from {name}:\n\n{message}")
        msg['Subject'] = f'PPS Hub Feedback — {name}'
        msg['From'] = smtp_user
        msg['To'] = 'thomas@purepropsolutions.com'
        with smtplib.SMTP_SSL(smtp_host, 465) as s:
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
    except Exception as e:
        print(f"Email send failed: {e}")


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
        return jsonify({'error': str(e)}), 500


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
        return jsonify({'error': str(e)}), 500


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
        return jsonify({'error': str(e)}), 500


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


def _extract_upload_text(file_storage, label='file'):
    """Extract plain text from an uploaded proposal (.docx, .txt; .pdf if pdftotext available)."""
    if not file_storage or not file_storage.filename:
        raise ValueError(f'Missing {label}')
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
    property_name = (request.form.get('property_name') or '').strip()

    try:
        original_text = _extract_upload_text(original_file, 'original proposal')
        edited_text = _extract_upload_text(edited_file, 'edited proposal')
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': f'Could not read files: {e}'}), 400

    if not original_text.strip() or not edited_text.strip():
        return jsonify({'success': False, 'error': 'Could not extract text from one or both files.'}), 400

    prop_line = f'Property: {property_name}\n\n' if property_name else ''
    prompt = f"""You are helping improve the PPS (Pure Property Solutions) construction proposal voice guide.

A consultant generated a proposal with AI, then edited it before sending to the client.
Compare the ORIGINAL and EDITED versions. Focus on meaningful changes to tone, structure,
wording, scope language, and client-facing phrasing — not trivial formatting.

{prop_line}ORIGINAL (AI-generated):
{original_text[:14000]}

EDITED (consultant's final version):
{edited_text[:14000]}

Respond with ONLY valid JSON (no markdown fences) using exactly these keys:
{{
  "diff_analysis": "Bullet-style summary of what changed and why it matters for client-facing proposals",
  "voice_recommendations": "Specific, actionable updates to recommend for pps_voice.txt — phrasing rules, tone shifts, trade language, or sections to add"
}}"""

    try:
        import anthropic
        cl = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        msg = cl.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2500,
            messages=[{'role': 'user', 'content': prompt}],
        )
        raw = msg.content[0].text.strip()
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
        return jsonify({
            'success': True,
            'diff_analysis': diff_analysis,
            'voice_recommendations': voice_recommendations,
        })
    except json.JSONDecodeError:
        return jsonify({'success': False, 'error': 'Could not parse Claude response. Try again.'}), 500
    except Exception as e:
        print(f"Analyze diff error: {e}")
        return jsonify({'success': False, 'error': f'Analysis failed: {e}'}), 500


@app.route('/submit-diff', methods=['POST'])
def submit_diff():
    if not session.get('user_key'):
        return jsonify({'error': 'Not authenticated'}), 401
    property_name = request.form.get('property_name', '').strip()
    diff_analysis = request.form.get('diff_analysis', '').strip()
    user_notes = request.form.get('user_notes', '').strip()
    voice_recommendations = request.form.get('voice_recommendations', '').strip()
    user_key = session['user_key']
    display_name = session.get('display_name', '')
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor()
            cur.execute(
                '''INSERT INTO proposal_diffs
                   (user_key, display_name, property_name, diff_analysis, user_notes, voice_recommendations)
                   VALUES (%s, %s, %s, %s, %s, %s)''',
                (user_key, display_name, property_name, diff_analysis, user_notes, voice_recommendations)
            )
            conn.commit()
            cur.close()
            conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


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
    return render_template('site_visit.html',
                           user_key=session['user_key'],
                           display_name=session.get('display_name', ''))


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
        return jsonify({'error': str(e)}), 500


@app.route('/site-visit/download/<int:visit_id>')
def site_visit_download(visit_id):
    if not session.get('user_key'):
        return redirect(url_for('login'))
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('SELECT * FROM site_visit_log WHERE id = %s', (visit_id,))
            row = cur.fetchone()
            cur.close(); conn.close()
        if not row:
            return "Not found", 404
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
        return str(e), 500


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


@app.route('/psc-training')
@require_login
def psc_training():
    user_key = session['user_key']
    if not is_psc_training_enrolled(user_key):
        return redirect(url_for('dashboard'))
    user = USERS.get(user_key, {})
    enrollment = get_psc_enrollment(user_key) or {}
    manager = USERS.get(enrollment.get('manager_key') or PSC_TRAINING_MANAGER, {})
    onboarding, weeks, core_values, sales_training = get_training_curriculum()
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
        total_items=count_trackable_items(),
        progress_json=json.dumps(progress),
        notes_json=json.dumps(notes),
        enrollment=enrollment,
        manager=manager,
        stats=stats,
        week_status=week_status,
        user=user,
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

    resend_key  = os.environ.get('RESEND_API_KEY', '')
    from_email  = os.environ.get('RESEND_FROM', 'noreply@purepropsolutions.com')
    reply_to    = os.environ.get('RESEND_REPLY_TO', '').strip() or session.get('user_email', '')

    if not resend_key:
        return jsonify({'error': 'Email service not configured. Contact Thomas.'}), 500

    type_labels = {
        'proposal':   'Proposal',
        'ppm':        'PPM Checklist',
        'tps':        'Trade Partner Scope',
        'site_visit': 'Site Visit Report',
    }
    label   = type_labels.get(doc_type, 'Document')
    subject = f'PPS {label} — {prop_name}' if prop_name else f'PPS {label}'

    prop_line = f'Property: {prop_name}' if prop_name else ''
    text_body = (
        f'Please find your PPS {label} attached.\n\n'
        f'{prop_line + chr(10) if prop_line else ""}'
        f'Generated by: {sender}\n\n'
        'The Pure Way: Trust. Quality. Results.'
    )

    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;">
      <div style="background:#004C8C;padding:20px 24px;border-radius:8px 8px 0 0;">
        <p style="color:white;font-size:18px;font-weight:600;margin:0;">Pure Property Solutions</p>
      </div>
      <div style="background:#f8fafc;padding:24px;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px;">
        <p style="color:#334155;font-size:15px;">Please find your <strong>PPS {label}</strong> attached.</p>
        {'<p style="color:#64748b;font-size:14px;">Property: ' + prop_name + '</p>' if prop_name else ''}
        <p style="color:#64748b;font-size:14px;">Generated by: {sender}</p>
        <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0;">
        <p style="color:#94a3b8;font-size:12px;font-style:italic;">
          The Pure Way: Trust. Quality. Results.™
        </p>
      </div>
    </div>
    """

    email_payload = {
        'from':    f'Pure Property Solutions <{from_email}>',
        'to':      [to_email],
        'subject': subject,
        'html':    html_body,
        'text':    text_body,
        'tags':    [{'name': 'source', 'value': doc_type[:50]}],
        'attachments': [{
            'filename': filename,
            'content':  doc_b64,
        }],
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
                'Content-Type':  'application/json',
                'User-Agent':    'PPS-Hub/1.0',
            },
            method='POST'
        )
        resp = _ur.urlopen(req, timeout=30)
        result = _json.loads(resp.read().decode('utf-8'))
        resend_id = result.get('id', '')
        print(f"Resend accept: to={to_email} from={from_email} id={resend_id} result={result}")
        if not resend_id:
            return jsonify({'error': 'Email service accepted the request but returned no message ID. Check Resend configuration.'}), 500
        return jsonify({
            'success': True,
            'sent_to': to_email,
            'resend_id': resend_id,
            'from_email': from_email,
        })
    except _ur_err.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        try:
            err_json = _json.loads(body)
            msg = err_json.get('message', body)
        except Exception:
            msg = body.strip() or str(e)
        print(f"Resend HTTP error {e.code}: {msg}")
        return jsonify({'error': msg}), 500
    except Exception as e:
        print(f"Resend error: {e}")
        return jsonify({'error': str(e)}), 500


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
        resp = jsonify({'error': str(e)})
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
        resp = jsonify({'error': str(e)})
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
        return jsonify({'error': str(e)}), 500


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
        user_key = request.form.get('user_key', '').strip()
        user_def = USERS.get(user_key)
        if not user_def:
            error = 'Select your name from the list.'
        else:
            token = create_password_reset_token(get_db, user_key)
            to_email = user_def.get('email', '')
            if not token or not to_email:
                error = 'Could not start reset. Contact Thomas or Stephanie.'
            else:
                link = reset_url_for_token(token)
                ok, detail = _send_resend_email(
                    to_email,
                    'Reset your PPS Hub password',
                    f'<p>Hi {user_def["display"].split()[0]},</p>'
                    f'<p><a href="{link}">Click here to reset your PPS Hub password</a>. '
                    f'This link expires in 1 hour.</p>'
                    f'<p>If you did not request this, ignore this email.</p>',
                    f'Reset your PPS password: {link}\n\nThis link expires in 1 hour.',
                )
                if ok:
                    message = f'If {to_email} is on file, a reset link was sent.'
                else:
                    print(f'Password reset email failed: {detail}')
                    error = 'Could not send email. Contact Thomas or Stephanie.'
    return render_template(
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
            return render_template('reset_password.html', error=error, token=None)
        return render_template('reset_password.html', error=None, token=token)

    token = request.form.get('token', '').strip()
    new_password = request.form.get('new_password', '').strip()
    confirm = request.form.get('confirm_password', '').strip()
    user_key = consume_password_reset_token(get_db, token)
    if not user_key:
        error = 'This reset link is invalid or has expired.'
    elif len(new_password) < 8:
        error = 'Password must be at least 8 characters.'
    elif new_password != confirm:
        error = 'Passwords do not match.'
    else:
        try:
            conn = get_db()
            if conn:
                cur = conn.cursor()
                hashed = generate_password_hash(new_password)
                cur.execute(
                    'UPDATE hub_users SET password_hash = %s, must_change_password = FALSE WHERE user_key = %s',
                    (hashed, user_key),
                )
                conn.commit()
                cur.close()
                conn.close()
                return redirect(url_for('login'))
        except Exception as e:
            print(f'reset password error: {e}')
            error = 'Something went wrong. Try again or contact Thomas.'
    return render_template('reset_password.html', error=error, token=token)


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


@app.route('/logout')
def logout():
    import urllib.parse
    session.clear()
    final = f'{HUB_PUBLIC_URL}/login'
    if PROPOSAL_URL:
        nxt = urllib.parse.quote(final, safe='')
        return redirect(f'{PROPOSAL_URL}/logout?next={nxt}')
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)
