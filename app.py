import os
import json
import base64
from io import BytesIO
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'pps-hub-secret-2026')

DATABASE_URL = os.environ.get('DATABASE_URL', '')
MASTER_PASSWORD = os.environ.get('MASTER_PASSWORD', 'Luther1985')
INTERNAL_API_KEY = os.environ.get('INTERNAL_API_KEY', 'pps-internal-2026')
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024  # 10 MB

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

    # Seed users with default password if not exists
    default_password = os.environ.get('DEFAULT_PASSWORD', 'PPS2026!')
    for key, user in USERS.items():
        cur.execute('SELECT id FROM hub_users WHERE user_key = %s', (key,))
        if not cur.fetchone():
            hashed = generate_password_hash(default_password)
            cur.execute(
                'INSERT INTO hub_users (user_key, display_name, password_hash, role) VALUES (%s, %s, %s, %s)',
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
            return redirect(url_for('login'))
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
        cur = conn.cursor(cursor_factory=RealDictCursor)
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


# ── ROUTES ──────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if session.get('user_key'):
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        user_key = request.form.get('user_key', '').strip()
        password = request.form.get('password', '').strip()

        # Master password override (Thomas admin access)
        if password == MASTER_PASSWORD:
            user = USERS.get(user_key)
            if user:
                session['user_key'] = user_key
                session['display_name'] = user['display']
                session['role'] = 'admin'
                session['admin'] = True
                session['proposal_access'] = list(CONSULTANTS.keys())
                session['team_view'] = user.get('team_view', False)
                session['team_view_scope'] = user.get('team_view_scope')
                _update_last_login(user_key)
                return redirect(url_for('dashboard'))

        # Normal login
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
                    session['user_key'] = user_key
                    session['display_name'] = user['display']
                    session['role'] = user['role']
                    session['proposal_access'] = get_user_proposal_access(user_key)
                    _update_last_login(user_key)
                    return redirect(url_for('dashboard'))
                else:
                    error = 'Incorrect password. Please try again.'
            else:
                error = 'Database unavailable. Please try again shortly.'
        except Exception as e:
            print(f"Login error: {e}")
            error = 'Something went wrong. Please try again.'

    return render_template('login.html',
                           users=sorted(USERS.items(), key=lambda x: x[1]['display']),
                           error=error)


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
    profile = get_profile_result(user_key)

    from datetime import datetime as _dt
    now_year = _dt.now().year
    is_admin = (user.get('role') == 'admin')
    # Check if profile taken this year
    profile_this_year = profile and profile.get('taken_date') and str(profile['taken_date'])[:4] == str(now_year) if profile else False
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
                           profile=profile if profile_this_year else None,
                           now_year=now_year,
                           date_events=date_events,
                           proposal_url=os.environ.get('PROPOSAL_URL', 'https://pps-proposal-tool.onrender.com'),
                           profile_url=os.environ.get('PROFILE_URL', 'https://pps-profile-web.onrender.com'))


@app.route('/log-proposal', methods=['POST'])
def log_proposal():
    """Called by proposal tool after successful generation."""
    data = request.get_json()
    api_key = request.headers.get('X-API-Key', '')
    if api_key != os.environ.get('INTERNAL_API_KEY', 'pps-internal-2026'):
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


def _internal_api_ok():
    api_key = request.headers.get('X-API-Key', '')
    return api_key == INTERNAL_API_KEY


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
             proposal_number, existing_issue, intended_outcome, scopes_selected, scope_notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
    if api_key != os.environ.get('INTERNAL_API_KEY', 'pps-internal-2026'):
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


@app.route('/admin')
@require_admin
def admin():
    rows = []
    all_proposals = []
    all_ppms = []
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
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Admin error: {e}")
    all_subscopes = []
    profile_rows = []
    profiles_taken = {}
    profile_count = 0
    unread_feedback = 0
    client_count = 0
    try:
        conn2 = get_db()
        if conn2:
            cur2 = conn2.cursor(cursor_factory=RealDictCursor)
            try:
                cur2.execute('SELECT * FROM subscope_log ORDER BY generated_at DESC LIMIT 50')
                all_subscopes = cur2.fetchall()
            except: pass
            try:
                cur2.execute('SELECT id, name, taken_date, primary_disc, secondary_disc, primary_motiv, character_match, character_show FROM profile_results ORDER BY taken_date DESC')
                profile_rows = cur2.fetchall()
                profile_count = len(profile_rows)
                for r in profile_rows:
                    key = r['name'].lower().replace(' ', '_')
                    if key not in profiles_taken:
                        profiles_taken[key] = r['taken_date']
            except: pass
            try:
                cur2.execute('SELECT COUNT(*) as cnt FROM feedback WHERE read_by_admin = FALSE')
                unread_feedback = cur2.fetchone()['cnt']
            except: pass
            client_count = 0
            try:
                cur2.execute('SELECT COUNT(*) as cnt FROM clients')
                client_count = cur2.fetchone()['cnt']
            except: pass
            cur2.close()
            conn2.close()
    except Exception as e:
        print(f"Admin extra data error: {e}")

    return render_template('admin.html', users=rows, all_proposals=all_proposals,
                           all_ppms=all_ppms, all_subscopes=all_subscopes,
                           profile_rows=profile_rows, profiles_taken=profiles_taken,
                           profile_count=profile_count, unread_feedback=unread_feedback,
                           client_count=client_count,
                           selected_year=2026,
                           user_definitions=USERS)


@app.route('/admin/reset-password', methods=['POST'])
@require_admin
def reset_password():
    user_key = request.form.get('user_key')
    new_password = request.form.get('new_password', '').strip()
    if not user_key or not new_password or len(new_password) < 6:
        return jsonify({'error': 'Invalid request'}), 400
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor()
            hashed = generate_password_hash(new_password)
            cur.execute('UPDATE hub_users SET password_hash = %s WHERE user_key = %s', (hashed, user_key))
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
    if api_key != os.environ.get('INTERNAL_API_KEY', 'pps-internal-2026'):
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
    proposals, ppms, subscopes, profile, feedback_items = [], [], [], None, []
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
            cur.execute('SELECT * FROM profile_results WHERE LOWER(name) = LOWER(%s) ORDER BY taken_date DESC', (user_def['display'],))
            profile = cur.fetchone()
            cur.execute('SELECT * FROM feedback WHERE user_key = %s ORDER BY submitted_at DESC', (user_key,))
            feedback_items = cur.fetchall()
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Member detail error: {e}")
    return render_template('admin_member.html',
                           user=user_def, user_key=user_key,
                           proposals=proposals, ppms=ppms,
                           subscopes=subscopes, profile=profile,
                           feedback_items=feedback_items,
                           profile_url=os.environ.get('PROFILE_URL', 'https://pps-profile-web.onrender.com'))


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


def generate_sso_token(user_key, display_name, role):
    """Generate a short-lived SSO token and store in DB."""
    import secrets
    from datetime import datetime, timedelta
    token = secrets.token_urlsafe(32)
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM auth_tokens WHERE expires_at < NOW()")
            cur.execute(
                '''INSERT INTO auth_tokens (token, user_key, display_name, role, expires_at)
                   VALUES (%s, %s, %s, %s, NOW() + INTERVAL '5 minutes')''',
                (token, user_key, display_name, role)
            )
            conn.commit()
            cur.close()
            conn.close()
            return token
    except Exception as e:
        print(f"generate_sso_token error: {e}")
    return None


@app.route('/generate-token', methods=['POST'])
def generate_token():
    """Called by hub dashboard JS — session authenticated, returns SSO token."""
    try:
        if not session.get('user_key'):
            return jsonify({'error': 'Not authenticated', 'session_keys': list(session.keys())}), 401
        user_key = session['user_key']
        display_name = session.get('display_name', '')
        role = session.get('role', 'user')
        token = generate_sso_token(user_key, display_name, role)
        if not token:
            return jsonify({'error': 'Token generation failed - check DB connection'}), 500
        return jsonify({'token': token})
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"generate-token error: {tb}")
        return jsonify({'error': str(e), 'traceback': tb}), 500


@app.route('/validate-token', methods=['POST'])
def validate_token():
    """Called by proposal/profile tool to validate an SSO token."""
    api_key = request.headers.get('X-API-Key', '')
    if api_key != os.environ.get('INTERNAL_API_KEY', 'pps-internal-2026'):
        return jsonify({'error': 'Unauthorized'}), 401
    token = request.json.get('token', '')
    if not token:
        return jsonify({'valid': False}), 400
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                '''SELECT * FROM auth_tokens
                   WHERE token = %s AND used = FALSE AND expires_at > NOW()''',
                (token,)
            )
            row = cur.fetchone()
            if row:
                # Mark as used
                cur.execute('UPDATE auth_tokens SET used = TRUE WHERE token = %s', (token,))
                conn.commit()
                cur.close()
                conn.close()
                _touch_last_active(row['user_key'], force=True)
                return jsonify({
                    'valid': True,
                    'user_key': row['user_key'],
                    'display_name': row['display_name'],
                    'role': row['role'],
                })
            cur.close()
            conn.close()
            return jsonify({'valid': False, 'reason': 'Token invalid or expired'})
    except Exception as e:
        return jsonify({'valid': False, 'reason': str(e)}), 500


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
                    cur.execute('SELECT * FROM proposal_log WHERE consultant_key = %s ORDER BY generated_at DESC', (key,))
                    udata['proposals'] = cur.fetchall()
                elif scope == 'pms':
                    cur.execute('SELECT * FROM ppm_log WHERE generated_by = %s OR pm_key = %s ORDER BY generated_at DESC', (key, key))
                    udata['ppms'] = cur.fetchall()
                    cur.execute('SELECT * FROM subscope_log WHERE generated_by = %s ORDER BY generated_at DESC', (key,))
                    udata['tpscopes'] = cur.fetchall()
                # Profile
                display_name = USERS.get(key, {}).get('display', '')
                cur.execute('SELECT * FROM profile_results WHERE LOWER(name) = LOWER(%s) ORDER BY taken_date DESC LIMIT 1', (display_name,))
                prof = cur.fetchone()
                udata['profile'] = prof
                member_data[key] = udata
            cur.close()
            conn.close()
    except Exception as e:
        print(f"Team view error: {e}")

    return render_template('team_view.html',
                           user=user, user_key=user_key,
                           scope=scope, members=members,
                           member_data=member_data)


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


@app.route('/email-doc', methods=['POST'])
def email_doc():
    """Email a generated document via Resend API."""
    api_key = request.headers.get('X-API-Key', '')
    internal_ok = api_key == os.environ.get('INTERNAL_API_KEY', 'pps-internal-2026')
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
    internal_ok = api_key == os.environ.get('INTERNAL_API_KEY', 'pps-internal-2026')
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
    internal_ok = api_key == os.environ.get('INTERNAL_API_KEY', 'pps-internal-2026')

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
def test_token():
    """Debug endpoint - shows session state and token generation."""
    if not session.get('user_key'):
        return jsonify({'session': 'none', 'user_key': None})
    token = generate_sso_token(
        session['user_key'],
        session.get('display_name', ''),
        session.get('role', 'user')
    )
    return jsonify({
        'session': 'active',
        'user_key': session['user_key'],
        'token_generated': token is not None,
        'token_preview': token[:8] + '...' if token else None
    })


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)
