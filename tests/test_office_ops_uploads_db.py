"""latest_upload_by_kind against a real Postgres.

Run: TEST_DATABASE_URL=postgresql://... python -m pytest tests/test_office_ops_uploads_db.py -v

The unit tests above cover what the box *says*. This covers the one thing
they cannot: that the box is describing the **newest** file of its kind.
`DISTINCT ON (kind) ... ORDER BY kind, uploaded_at DESC` is easy to write
with the sort backwards, and the failure is quiet — the box shows a real
file with a real date, just the wrong one, which is exactly the confusion
this feature exists to remove.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DSN = os.environ.get('TEST_DATABASE_URL')
pytestmark = pytest.mark.skipif(not DSN, reason='TEST_DATABASE_URL not set')

if DSN:
    import psycopg2

    import office_ops


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def db():
    conn = psycopg2.connect(DSN)
    cur = conn.cursor()
    cur.execute('DROP TABLE IF EXISTS office_ops_packs CASCADE')
    cur.execute('DROP TABLE IF EXISTS office_ops_files CASCADE')
    office_ops.init_tables(cur)
    conn.commit()
    cur.close()
    conn.close()
    yield lambda: psycopg2.connect(DSN)


def _insert(get_db, kind, filename, when, who='stephanie_whetstone'):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        '''INSERT INTO office_ops_files
               (kind, filename, mime_type, size_bytes, file_data, uploaded_by,
                uploaded_at)
           VALUES (%s, %s, 'application/vnd.ms-excel', 10, %s, %s, %s)''',
        (kind, filename, psycopg2.Binary(b'xxxxxxxxxx'), who, when))
    conn.commit()
    cur.close()
    conn.close()


def test_the_newest_file_of_each_kind_wins(db):
    now = _utcnow()
    _insert(db, 'invoice_list', 'old.xlsx', now - timedelta(days=8))
    _insert(db, 'invoice_list', 'new.xlsx', now - timedelta(hours=2))
    _insert(db, 'ar_aging_summary', 'ar.xlsx', now - timedelta(days=1))
    latest = office_ops.latest_upload_by_kind(db)
    assert latest['invoice_list']['filename'] == 'new.xlsx'
    assert latest['ar_aging_summary']['filename'] == 'ar.xlsx'


def test_a_kind_with_no_upload_is_absent_rather_than_empty(db):
    _insert(db, 'invoice_list', 'only.xlsx', _utcnow())
    latest = office_ops.latest_upload_by_kind(db)
    assert 'profit_loss' not in latest
    boxes = office_ops.uploads_for_boxes(db, ('invoice_list', 'profit_loss'))
    assert set(boxes) == {'invoice_list'}, 'an empty box must not fake a file'


def test_it_asks_for_one_kind_when_told_to(db):
    now = _utcnow()
    _insert(db, 'invoice_list', 'inv.xlsx', now)
    _insert(db, 'profit_loss', 'pl.xlsx', now)
    assert set(office_ops.latest_upload_by_kind(db, ('profit_loss',))) == {'profit_loss'}


def test_an_unreachable_database_leaves_the_boxes_empty(db):
    """A page that 500s because it could not label a box is worse than a page
    with unlabelled boxes."""
    assert office_ops.latest_upload_by_kind(lambda: None) == {}
    assert office_ops.uploads_for_boxes(lambda: None, ('invoice_list',)) == {}
