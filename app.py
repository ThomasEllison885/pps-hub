import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'pps-hub-secret-2026')

DATABASE_URL = os.environ.get('DATABASE_URL', '')
MASTER_PASSWORD = os.environ.get('MASTER_PASSWORD', 'Luther1985')

# ── USER DEFINITIONS ────────────────────────────────────────────────────────────

USERS = {
    'thomas_ellison': {
        'display': 'Thomas Ellison',
        'role': 'admin',
        'proposal_access': 'all',
        'ppm_access': True,
    },
    'tony_cumella': {
        'display': 'Tony Cumella',
        'role': 'consultant',
        'proposal_access': ['tony_cumella'],
        'ppm_access': True,
    },
    'adam_cupito': {
        'display': 'Adam Cupito',
        'role': 'consultant',
        'proposal_access': ['adam_cupito'],
        'ppm_access': True,
    },
    'rachel_farler': {
        'display': 'Rachel Farler',
        'role': 'consultant',
        'proposal_access': ['rachel_farler'],
        'ppm_access': True,
    },
    'andy_potts': {
        'display': 'Andy Potts',
        'role': 'consultant',
        'proposal_access': ['andy_potts'],
        'ppm_access': True,
    },
    'phil_miller': {
        'display': 'Phil Miller',
        'role': 'pm',
        'proposal_access': 'all',
        'ppm_access': True,
    },
    'derek_kidney': {
        'display': 'Derek Kidney',
        'role': 'pm',
        'proposal_access': ['rachel_farler'],
        'ppm_access': True,
    },
    'nick_triplett': {
        'display': 'Nick Triplett',
        'role': 'pm',
        'proposal_access': ['tony_cumella'],
        'ppm_access': True,
    },
    'trey_hollmeyer': {
        'display': 'Trey Hollmeyer',
        'role': 'pm',
        'proposal_access': 'all',
        'ppm_access': True,
    },
    'james_boling': {
        'display': 'James Boling',
        'role': 'pm',
        'proposal_access': ['andy_potts', 'adam_cupito'],
        'ppm_access': True,
    },
    'jordan_allen': {
        'display': 'Jordan Allen',
        'role': 'pm',
        'proposal_access': 'all',
        'ppm_access': True,
    },
    'ben_ramsey': {
        'display': 'Ben Ramsey',
        'role': 'pm',
        'proposal_access': ['andy_potts'],
        'ppm_access': True,
    },
    'stephanie_whetstone': {
        'display': 'Stephanie Whetstone',
        'role': 'office_manager',
        'proposal_access': [],
        'ppm_access': True,
    },
}

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
            property_type VARCHAR(100),
            template_type VARCHAR(100),
            generated_at TIMESTAMP DEFAULT NOW()
        )
    ''')

    # PPM activity log
    cur.execute('''
        CREATE TABLE IF NOT EXISTS ppm_log (
            id SERIAL PRIMARY KEY,
            generated_by VARCHAR(100) NOT NULL,
            property_name VARCHAR(255),
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

    conn.commit()
    cur.close()
    conn.close()


try:
    init_db()
except Exception as e:
    print(f"DB init error: {e}")


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
                session['proposal_access'] = list(CONSULTANTS.keys())
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


def _update_last_login(user_key):
    try:
        conn = get_db()
        if conn:
            cur = conn.cursor()
            cur.execute('UPDATE hub_users SET last_login = NOW() WHERE user_key = %s', (user_key,))
            conn.commit()
            cur.close()
            conn.close()
    except:
        pass


@app.route('/dashboard')
@require_login
def dashboard():
    user_key = session['user_key']
    user = USERS.get(user_key, {})
    proposal_access = get_user_proposal_access(user_key)
    accessible_consultants = {k: CONSULTANTS[k] for k in proposal_access if k in CONSULTANTS}
    recent_proposals = get_recent_proposals(user_key)
    recent_ppms = get_recent_ppms(user_key)
    profile = get_profile_result(user_key)

    return render_template('dashboard.html',
                           user=user,
                           user_key=user_key,
                           consultants=accessible_consultants,
                           recent_proposals=recent_proposals,
                           recent_ppms=recent_ppms,
                           profile=profile,
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
                 property_name, property_type, template_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (
                data.get('generated_by'),
                data.get('consultant_key'),
                data.get('consultant_name'),
                data.get('client_name'),
                data.get('property_name'),
                data.get('property_type'),
                data.get('template_type'),
            ))
            conn.commit()
            cur.close()
            conn.close()
        return jsonify({'success': True})
    except Exception as e:
        print(f"Log proposal error: {e}")
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
                'INSERT INTO ppm_log (generated_by, property_name) VALUES (%s, %s)',
                (data.get('generated_by'), data.get('property_name'))
            )
            conn.commit()
            cur.close()
            conn.close()
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
    return render_template('admin.html',
                           users=rows,
                           all_proposals=all_proposals,
                           all_ppms=all_ppms,
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


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)
