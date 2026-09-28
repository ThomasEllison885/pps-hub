"""Client contact attachments — filenames, blocked types, vault math.

Stored in the existing `documents` table as doc_type='client_file' with
log_id = clients.id. Same BYTEA vault as generated proposals, so every
site-map photo counts against VAULT_STORAGE_LIMIT_MB (512 on Render).

Blocked types are a denylist, not an allowlist: consultants attach whatever
they have (phone photos, PDFs, CAD, Excel). Executables and script/HTML
payloads are refused. Downloads always go out as attachments.
"""
import os
import re

CLIENT_FILE_DOC_TYPE = 'client_file'

# Last-extension denylist. A file named site-map.jpg.exe is blocked.
BLOCKED_EXTENSIONS = frozenset({
    'exe', 'bat', 'cmd', 'com', 'msi', 'scr', 'pif', 'dll', 'sys', 'gadget',
    'sh', 'bash', 'zsh', 'ps1', 'vbs', 'vbe', 'js', 'jse', 'ws', 'wsf', 'wsh',
    'hta', 'cpl', 'py', 'pyc', 'pyo', 'rb', 'pl', 'php', 'asp', 'aspx', 'jsp',
    'cgi', 'jar', 'apk', 'app', 'dmg', 'pkg', 'iso', 'deb', 'rpm',
    'html', 'htm', 'xhtml', 'shtml',
    'so', 'dylib', 'bin',
})

_UNPRINTABLE = re.compile(r'[\x00-\x1f\x7f]')


def filename_extension(filename):
    name = (filename or '').rsplit('.', 1)
    if len(name) != 2 or not name[1]:
        return ''
    return name[1].lower()


def is_blocked_client_filename(filename):
    ext = filename_extension(filename)
    if not ext:
        return True
    return ext in BLOCKED_EXTENSIONS


def safe_client_filename(filename):
    """Basename only, no path, no control chars, capped at the VARCHAR(255)."""
    raw = (filename or '').replace('\\', '/')
    name = os.path.basename(raw).strip()
    name = _UNPRINTABLE.sub('', name)
    if not name or name in ('.', '..'):
        return ''
    return name[:255]


def vault_would_exceed(used_bytes, incoming_bytes, limit_bytes):
    used = int(used_bytes or 0)
    incoming = int(incoming_bytes or 0)
    limit = int(limit_bytes or 0)
    if incoming < 0:
        incoming = 0
    if limit <= 0:
        return True
    return (used + incoming) > limit


def format_bytes(n):
    n = int(n or 0)
    if n < 1024:
        return f'{n} B'
    kb = n / 1024
    if kb < 1024:
        return f'{kb:.1f} KB'
    return f'{n / (1024 * 1024):.1f} MB'
