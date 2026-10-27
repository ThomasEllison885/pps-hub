"""Status-history log for the pipeline board. No live Postgres.

The cursor is a small in-memory stand-in that understands the statements
pipeline_board.py actually sends. It supports savepoints so a failed history
INSERT can roll back without undoing the edit, which is the behavior under test.
"""

import copy
from datetime import datetime, timedelta, timezone
from io import BytesIO

import openpyxl

import pipeline_board as pb


T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


class Store:
    def __init__(self):
        self.entries = {}
        self.history = []
        self.backups = []
        self.next_entry = 1
        self.next_hist = 1
        self.next_backup = 1
        self.now = T0
        self.fail_history = False
        self._sp = {}

    def add_entry(self, pair_key, status, created_at, archived=False, entry_id=None):
        eid = entry_id or self.next_entry
        self.next_entry = max(self.next_entry, eid + 1)
        self.entries[eid] = {
            'id': eid,
            'pair_key': pair_key,
            'proposal_number': None,
            'property_name': None,
            'address': None,
            'project': None,
            'status': status,
            'amount': None,
            'sub_pay': None,
            'trade_partner': None,
            'client_contact': None,
            'notes': None,
            'row_order': eid,
            'archived': archived,
            'created_by': None,
            'created_at': created_at,
            'updated_by': None,
            'updated_at': created_at,
        }
        return self.entries[eid]

    def push(self, name):
        self._sp[name] = {
            'entries': copy.deepcopy(self.entries),
            'history': copy.deepcopy(self.history),
            'backups': copy.deepcopy(self.backups),
            'next_entry': self.next_entry,
            'next_hist': self.next_hist,
            'next_backup': self.next_backup,
        }

    def rollback_to(self, name):
        snap = self._sp[name]
        self.entries = copy.deepcopy(snap['entries'])
        self.history = copy.deepcopy(snap['history'])
        self.backups = copy.deepcopy(snap['backups'])
        self.next_entry = snap['next_entry']
        self.next_hist = snap['next_hist']
        self.next_backup = snap['next_backup']

    def release(self, name):
        self._sp.pop(name, None)


class Conn:
    def __init__(self, store):
        self.store = store
        self.committed = False

    def cursor(self, cursor_factory=None):
        return Cur(self.store)

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        pass


class Cur:
    def __init__(self, store):
        self.store = store
        self._rows = []

    def execute(self, sql, params=None):
        s = ' '.join(sql.split())
        params = params or ()
        store = self.store
        if s.startswith('SAVEPOINT'):
            store.push(s.split()[1])
            return
        if s.startswith('RELEASE SAVEPOINT'):
            store.release(s.split()[-1])
            return
        if s.startswith('ROLLBACK TO SAVEPOINT'):
            store.rollback_to(s.split()[-1])
            return
        if s.startswith('CREATE') or s.startswith('ALTER') or s.startswith('COMMENT'):
            return
        if s.startswith('INSERT INTO pipeline_board_status_history'):
            self._insert_history(s, params)
            return
        if s.startswith('WITH old AS'):
            self._update_with_old(s, params)
            return
        if s.startswith('INSERT INTO pipeline_board_entries'):
            self._insert_entry(s, params)
            return
        if s.startswith('UPDATE pipeline_board_entries') and 'RETURNING id, pair_key, status' in s:
            self._archive_one(params)
            return
        if s.startswith('UPDATE pipeline_board_entries') and 'RETURNING id' in s:
            self._restore_update(params)
            return
        if (s.startswith('UPDATE pipeline_board_entries')
                and 'archived = TRUE' in s and 'updated_by' in s):
            self._archive_pair(params)
            return
        if 'AS next_order' in s:
            pair = params[0]
            orders = [e['row_order'] for e in store.entries.values() if e['pair_key'] == pair]
            nxt = (max(orders) if orders else -1) + 1
            self._rows = [{'next_order': nxt}]
            return
        if s.startswith('SELECT proposal_number FROM pipeline_board_entries'):
            pair = params[0]
            self._rows = [
                {'proposal_number': e['proposal_number']}
                for e in store.entries.values()
                if e['pair_key'] == pair and e['proposal_number']
            ]
            return
        if 'FROM pipeline_board_entries e' in s and 'NOT EXISTS' in s:
            have = {h['entry_id'] for h in store.history}
            self._rows = [dict(e) for e in store.entries.values() if e['id'] not in have]
            return
        if s.startswith('SELECT id, status, archived'):
            pair = params[0]
            self._rows = [
                {'id': e['id'], 'status': e['status'], 'archived': e['archived']}
                for e in store.entries.values() if e['pair_key'] == pair
            ]
            return
        if 'FROM pipeline_board_backups' in s and 'WHERE id = %s' in s:
            bid, pair = params
            self._rows = [b for b in store.backups if b['id'] == bid and b['pair_key'] == pair]
            return
        if 'FROM pipeline_board_backups' in s and 'payload' in s:
            self._rows = sorted(store.backups, key=lambda b: (b['created_at'], b['id']))
            return
        if "changed_by = 'baseline'" in s:
            self._rows = [h for h in store.history if h['changed_by'] == 'baseline']
            return
        if "changed_by = 'backfill'" in s:
            self._rows = [h for h in store.history if h['changed_by'] == 'backfill']
            return
        if 'FROM pipeline_board_status_history' in s and 'ORDER BY' in s:
            rows = list(store.history)
            if 'WHERE pair_key = %s' in s:
                rows = [h for h in rows if h['pair_key'] == params[0]]
            rows.sort(key=lambda h: (h['pair_key'], h['entry_id'], h['changed_at'], h['id']))
            self._rows = rows
            return
        raise AssertionError(f'unexpected SQL: {s[:240]}')

    def _insert_history(self, sql, params):
        store = self.store
        if store.fail_history:
            raise RuntimeError('history insert failed')
        if 'changed_at' in sql.split('VALUES')[0]:
            entry_id, pair_key, event, from_status, to_status, changed_by, changed_at = params
        else:
            entry_id, pair_key, event, from_status, to_status, changed_by = params
            changed_at = store.now
        if changed_at is None:
            changed_at = store.now
        store.history.append({
            'id': store.next_hist,
            'entry_id': entry_id,
            'pair_key': pair_key,
            'event': event,
            'from_status': from_status,
            'to_status': to_status,
            'changed_by': changed_by,
            'changed_at': changed_at,
        })
        store.next_hist += 1
        self._rows = []

    def _insert_entry(self, sql, params):
        store = self.store
        eid = store.next_entry
        store.next_entry += 1
        if "'new'" in sql:
            pair_key, proposal_number, _pair_again, user_key, _user_again = params
            orders = [e['row_order'] for e in store.entries.values() if e['pair_key'] == pair_key]
            row = store.add_entry(pair_key, 'new', store.now, entry_id=eid)
            store.next_entry = max(store.next_entry, eid + 1)
            row['proposal_number'] = proposal_number
            row['row_order'] = (max(orders) + 1) if orders else 0
            row['created_by'] = user_key
            row['updated_by'] = user_key
            self._rows = [dict(row)]
            return
        if 'archived' in sql:
            (pair_key, proposal_number, property_name, address, project, status,
             amount, sub_pay, trade_partner, client_contact, notes, row_order,
             user_key, _user_again) = params
        else:
            (pair_key, proposal_number, property_name, address, project, status,
             amount, sub_pay, trade_partner, client_contact, notes, row_order,
             user_key, _user_again) = params
        row = store.add_entry(pair_key, status, store.now, entry_id=eid)
        store.next_entry = max(store.next_entry, eid + 1)
        row.update({
            'proposal_number': proposal_number,
            'property_name': property_name,
            'address': address,
            'project': project,
            'amount': amount,
            'sub_pay': sub_pay,
            'trade_partner': trade_partner,
            'client_contact': client_contact,
            'notes': notes,
            'row_order': row_order,
            'created_by': user_key,
            'updated_by': user_key,
            'archived': False,
        })
        self._rows = [{'id': eid}]

    def _update_with_old(self, sql, params):
        store = self.store
        entry_id, pair_key = params[0], params[1]
        entry = store.entries.get(entry_id)
        if not entry or entry['pair_key'] != pair_key or entry['archived']:
            self._rows = []
            return
        set_sql = sql.split(' SET ', 1)[1].split(' FROM old', 1)[0]
        values = list(params[2:])
        old_status = entry['status']
        vi = 0
        for part in set_sql.split(','):
            part = part.strip()
            col = part.split('=')[0].strip()
            if 'NOW()' in part:
                entry['updated_at'] = store.now
                continue
            entry[col] = values[vi]
            vi += 1
        out = dict(entry)
        out['_old_status'] = old_status
        self._rows = [out]

    def _archive_one(self, params):
        entry_id, pair_key = params
        entry = self.store.entries.get(entry_id)
        if not entry or entry['pair_key'] != pair_key or entry['archived']:
            self._rows = []
            return
        entry['archived'] = True
        entry['updated_at'] = self.store.now
        self._rows = [{'id': entry['id'], 'pair_key': entry['pair_key'], 'status': entry['status']}]

    def _archive_pair(self, params):
        user_key, pair_key = params
        for entry in self.store.entries.values():
            if entry['pair_key'] == pair_key and not entry['archived']:
                entry['archived'] = True
                entry['updated_by'] = user_key
                entry['updated_at'] = self.store.now
        self._rows = []

    def _restore_update(self, params):
        (proposal_number, property_name, address, project, status, amount, sub_pay,
         trade_partner, client_contact, notes, row_order, user_key, entry_id, pair_key) = params
        entry = self.store.entries.get(entry_id)
        if not entry or entry['pair_key'] != pair_key:
            self._rows = []
            return
        entry.update({
            'proposal_number': proposal_number,
            'property_name': property_name,
            'address': address,
            'project': project,
            'status': status,
            'amount': amount,
            'sub_pay': sub_pay,
            'trade_partner': trade_partner,
            'client_contact': client_contact,
            'notes': notes,
            'row_order': row_order,
            'archived': False,
            'updated_by': user_key,
            'updated_at': self.store.now,
        })
        self._rows = [{'id': entry_id}]

    def fetchone(self):
        if not self._rows:
            return None
        return self._rows[0]

    def fetchall(self):
        return list(self._rows)

    def close(self):
        pass


def _db(store=None):
    store = store or Store()
    return store, (lambda: Conn(store))


def _events(store, entry_id=None):
    rows = store.history
    if entry_id is not None:
        rows = [h for h in rows if h['entry_id'] == entry_id]
    return [(h['event'], h['from_status'], h['to_status']) for h in rows]


def test_create_writes_one_created_row():
    store, get_db = _db()
    row = pb.create_entry(get_db, 'rachel_farler', 'rachel_farler')
    assert row['status'] == 'new'
    assert _events(store) == [('created', None, 'new')]
    assert store.history[0]['changed_by'] == 'rachel_farler'


def test_status_change_records_from_and_to():
    store, get_db = _db()
    row = pb.create_entry(get_db, 'rachel_farler', 'rachel_farler')
    updated, err = pb.update_entry(
        get_db, row['id'], 'rachel_farler', 'rachel_farler', {'status': 'needs_scope'},
    )
    assert err is None
    assert updated['status'] == 'needs_scope'
    assert _events(store, row['id'])[-1] == ('status', 'new', 'needs_scope')


def test_saving_the_same_status_does_not_log():
    store, get_db = _db()
    row = pb.create_entry(get_db, 'rachel_farler', 'rachel_farler')
    before = len(store.history)
    updated, err = pb.update_entry(
        get_db, row['id'], 'rachel_farler', 'rachel_farler', {'status': 'new'},
    )
    assert err is None
    assert updated['status'] == 'new'
    assert len(store.history) == before


def test_notes_and_amount_edits_do_not_log():
    store, get_db = _db()
    row = pb.create_entry(get_db, 'rachel_farler', 'rachel_farler')
    before = len(store.history)
    updated, err = pb.update_entry(
        get_db, row['id'], 'rachel_farler', 'rachel_farler',
        {'notes': 'called the board', 'amount': 1200},
    )
    assert err is None
    assert updated['notes'] == 'called the board'
    assert updated['amount'] == 1200
    assert len(store.history) == before
    assert store.entries[row['id']]['amount'] == 1200


def test_archive_records_the_status_it_left():
    store, get_db = _db()
    row = pb.create_entry(get_db, 'rachel_farler', 'rachel_farler')
    pb.update_entry(get_db, row['id'], 'rachel_farler', 'rachel_farler', {'status': 'sent'})
    assert pb.archive_entry(get_db, row['id'], 'rachel_farler', 'thomas_ellison') is True
    assert store.entries[row['id']]['archived'] is True
    assert _events(store, row['id'])[-1] == ('archived', 'sent', None)
    assert store.history[-1]['changed_by'] == 'thomas_ellison'
    # Archiving again is a no-op. It must not add a second archived row.
    assert pb.archive_entry(get_db, row['id'], 'rachel_farler', 'thomas_ellison') is True
    assert [h['event'] for h in store.history if h['entry_id'] == row['id']].count('archived') == 1


def test_failed_history_insert_still_saves_the_edit():
    store, get_db = _db()
    row = pb.create_entry(get_db, 'rachel_farler', 'rachel_farler')
    store.fail_history = True
    updated, err = pb.update_entry(
        get_db, row['id'], 'rachel_farler', 'rachel_farler', {'status': 'draft'},
    )
    assert err is None
    assert updated['status'] == 'draft'
    assert store.entries[row['id']]['status'] == 'draft'
    assert [h['event'] for h in store.history] == ['created']


def test_baseline_is_idempotent_and_marks_archived_rows():
    store, get_db = _db()
    store.now = datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc)
    store.add_entry('rachel_farler', 'sent', datetime(2026, 3, 1, tzinfo=timezone.utc))
    store.add_entry(
        'rachel_farler', 'draft', datetime(2026, 4, 1, tzinfo=timezone.utc), archived=True,
    )
    pb.init_tables(Conn(store).cursor())
    first = list(store.history)
    pb.init_tables(Conn(store).cursor())
    assert store.history == first
    by_entry = {}
    for h in first:
        by_entry.setdefault(h['entry_id'], []).append(h['event'])
    assert sorted(by_entry.values()) == [['created', 'archived'], ['created', 'baseline']]
    active = next(e for e in store.entries.values() if not e['archived'])
    base = next(h for h in first if h['entry_id'] == active['id'] and h['event'] == 'baseline')
    assert base['to_status'] == 'sent'
    assert base['from_status'] is None
    created = next(h for h in first if h['entry_id'] == active['id'] and h['event'] == 'created')
    assert created['to_status'] is None
    assert created['changed_at'] == active['created_at']


def test_backup_mining_records_snapshot_transitions_once():
    store, get_db = _db()
    opened = datetime(2026, 9, 1, tzinfo=timezone.utc)
    entry = store.add_entry('rachel_farler', 'sent', opened)
    store.now = datetime(2026, 10, 1, tzinfo=timezone.utc)

    def snap(when, status):
        store.backups.append({
            'id': store.next_backup,
            'pair_key': 'rachel_farler',
            'created_at': when,
            'payload': [{
                'id': entry['id'],
                'pair_key': 'rachel_farler',
                'status': status,
                'archived': False,
            }],
        })
        store.next_backup += 1

    snap(datetime(2026, 9, 10, tzinfo=timezone.utc), 'new')
    snap(datetime(2026, 9, 20, tzinfo=timezone.utc), 'draft')
    snap(datetime(2026, 9, 25, tzinfo=timezone.utc), 'draft')
    pb.init_tables(Conn(store).cursor())
    pb.init_tables(Conn(store).cursor())
    backfill = [h for h in store.history if h['changed_by'] == 'backfill']
    assert len(backfill) == 1
    assert backfill[0]['event'] == 'status'
    assert backfill[0]['from_status'] == 'new'
    assert backfill[0]['to_status'] == 'draft'
    assert backfill[0]['changed_at'] == datetime(2026, 9, 20, tzinfo=timezone.utc)


def test_status_durations_for_a_known_sequence():
    store, get_db = _db()
    store.now = T0
    row = pb.create_entry(get_db, 'rachel_farler', 'rachel_farler')
    store.now = T0 + timedelta(hours=2)
    pb.update_entry(get_db, row['id'], 'rachel_farler', 'rachel_farler', {'status': 'draft'})
    store.now = T0 + timedelta(hours=5)
    pb.update_entry(get_db, row['id'], 'rachel_farler', 'rachel_farler', {'status': 'sent'})
    rows, err = pb.status_durations(get_db, pair_key='rachel_farler', now=T0 + timedelta(hours=9))
    assert err is None
    assert rows == [{
        'entry_id': row['id'],
        'pair_key': 'rachel_farler',
        'current_status': 'sent',
        'by_status': [
            {'status': 'new', 'label': 'New', 'seconds': 2 * 3600},
            {'status': 'draft', 'label': 'Draft', 'seconds': 3 * 3600},
            {'status': 'sent', 'label': 'Sent', 'seconds': 4 * 3600},
        ],
    }]
    clipped, err = pb.status_durations(
        get_db, pair_key='rachel_farler', since=T0 + timedelta(hours=3),
        now=T0 + timedelta(hours=9),
    )
    assert err is None
    assert [item['seconds'] for item in clipped[0]['by_status']] == [2 * 3600, 4 * 3600]
    assert [item['status'] for item in clipped[0]['by_status']] == ['draft', 'sent']


def test_import_logs_imported_status():
    store, get_db = _db()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['Property', 'Status', 'Amount'])
    ws.append(['Monastery', 'sent', 5000])
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    result = pb.import_workbook(get_db, buf, 'rachel_farler', 'rachel_farler')
    assert result['success'] is True
    assert result['imported'] == 1
    assert _events(store) == [('imported', None, 'sent')]


def test_restore_logs_only_rows_whose_status_or_archive_changed():
    store, get_db = _db()
    staying = store.add_entry('rachel_farler', 'draft', T0)
    leaving = store.add_entry('rachel_farler', 'sent', T0)
    coming = store.add_entry('rachel_farler', 'new', T0)
    store.backups.append({
        'id': 1,
        'pair_key': 'rachel_farler',
        'reason': 'manual',
        'created_by': 'thomas_ellison',
        'created_at': T0,
        'entry_count': 2,
        'payload': [
            {'id': staying['id'], 'status': 'draft', 'archived': False,
             'proposal_number': None, 'property_name': 'Same', 'address': None,
             'project': None, 'amount': None, 'sub_pay': None, 'trade_partner': None,
             'client_contact': None, 'notes': None, 'row_order': 1},
            {'id': coming['id'], 'status': 'scoped', 'archived': False,
             'proposal_number': None, 'property_name': 'Back', 'address': None,
             'project': None, 'amount': None, 'sub_pay': None, 'trade_partner': None,
             'client_contact': None, 'notes': None, 'row_order': 2},
        ],
    })
    summary, err = pb.restore_from_backup(get_db, 'rachel_farler', 1, 'thomas_ellison')
    assert err is None
    assert summary['restored'] == 2
    logged = {
        (h['entry_id'], h['event'], h['from_status'], h['to_status'])
        for h in store.history
    }
    assert (staying['id'], 'restored', 'draft', 'draft') not in logged
    assert (leaving['id'], 'restored', 'sent', None) in logged
    assert (coming['id'], 'restored', 'new', 'scoped') in logged
    assert store.entries[leaving['id']]['archived'] is True
    assert store.entries[coming['id']]['status'] == 'scoped'
    assert store.entries[coming['id']]['archived'] is False
