"""Daily PSC training alerts to Thomas and the trainer (2026-11-09).

Fake cursor, no database: what matters is which emails go out, to whom, and
that the dedupe keeps the five hourly cron calls to one email per day.
"""
import os
import sys
from datetime import date, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import psc_training_alerts as A  # noqa: E402
import psc_training_data  # noqa: E402

TITLES = A.item_titles(psc_training_data.read_curriculum())
LABELS = psc_training_data.get_week_labels()
CHECKINS = psc_training_data.get_week_checkin_questions()


class DB:
    """Answers the module's handful of queries from in-memory lists."""

    def __init__(self, items=(), notes=(), roleplays=(), feedback=(), last=None):
        self.items, self.notes, self.roleplays, self.feedback = items, notes, roleplays, feedback
        self.last = last
        self.sent_keys = set()
        self._result = []
        self.commits = 0

    # connection
    def cursor(self):
        return self

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass

    # cursor
    def execute(self, sql, params=None):
        q = ' '.join(sql.split())
        if 'FROM psc_training_progress WHERE user_key' in q and 'completed_at >=' in q:
            self._result = [(i,) for i in self.items]
        elif 'FROM psc_training_notes WHERE' in q and 'updated_at >=' in q:
            self._result = list(self.notes)
        elif 'FROM psc_roleplay_sessions WHERE' in q and 'created_at >=' in q:
            self._result = list(self.roleplays)
        elif 'FROM psc_training_feedback WHERE' in q and 'submitted_at >=' in q:
            self._result = list(self.feedback)
        elif q.startswith('SELECT GREATEST'):
            self._result = [(self.last,)]
        elif 'FROM psc_training_notifications' in q:
            self._result = [(1,)] if (params[1], params[2]) in self.sent_keys else []
        elif q.startswith('INSERT INTO psc_training_notifications'):
            self.sent_keys.add((params[1], params[2]))
            self._result = []
        else:
            raise AssertionError(q)

    def fetchall(self):
        return self._result


def _stats(ready_week=None):
    weeks = [{'week': w, 'ready_for_signoff': w == ready_week} for w in range(13)]
    return {'pct': 12, 'done': 30, 'total': 246, 'signed_weeks': 0, 'week_pcts': weeks}


def _run(db, report_date=date(2026, 11, 17), ready_week=None, enrolled=datetime(2026, 11, 16, 13)):
    outbox = []

    def send(subject, text, html, recipients):
        outbox.append((subject, text, recipients))
        return True

    result = A.run(
        lambda: db, [('harrison_hollon', 'Harrison Hollon', enrolled)], report_date,
        datetime(2026, 11, 17, 5), datetime(2026, 11, 18, 5),
        titles=TITLES, week_labels=LABELS, checkins=CHECKINS,
        scenario_title=lambda s: {'rp_cold_call': 'Cold Call — Regional Manager'}.get(s, s),
        stats_fn=lambda k: _stats(ready_week),
        recipients_fn=lambda k: ['thomas@x', 'adam@x'],
        send_fn=send, oversight_url='https://hub/psc-training/oversight', trainer='Adam Cupito')
    return result, outbox


def test_a_day_of_work_is_one_email_with_titles_not_ids():
    db = DB(items=['w0_add_hub', 'cv_pure_way_map'], roleplays=[('rp_cold_call', 7.5, 'pass')],
            notes=[(0, 'Rode along with Adam at Indian Creek.')], last=datetime(2026, 11, 17, 18))
    _, out = _run(db)
    assert len(out) == 1
    subject, text, recipients = out[0]
    assert recipients == ['thomas@x', 'adam@x']
    assert 'Explore the PPS Hub Dashboard' in text and 'Map one job to Pure Way' in text
    assert 'w0_add_hub' not in text
    assert 'Cold Call — Regional Manager — 7.5/10, pass' in text
    assert 'Rode along with Adam' in text


def test_hourly_retries_send_once():
    db = DB(items=['w0_add_hub'], last=datetime(2026, 11, 17, 18))
    _run(db)
    _, out = _run(db)
    assert out == []


def test_nothing_done_and_not_quiet_sends_nothing():
    db = DB(last=datetime(2026, 11, 16, 18))
    result, out = _run(db)
    assert out == [] and result['skipped'] == ['harrison_hollon']


def test_week_ready_is_the_headline_and_fires_once():
    db = DB(items=['w0_focus_vocab'], last=datetime(2026, 11, 17, 18))
    _, out = _run(db, ready_week=0)
    assert 'ready for check-in' in out[0][0]
    assert CHECKINS[0][:40] in out[0][1]
    db.items = []  # nothing new the next day
    _, out = _run(db, report_date=date(2026, 11, 18), ready_week=0)
    assert out == []  # week already announced


def test_quiet_after_three_weekdays_once_per_stretch():
    db = DB(last=datetime(2026, 11, 17, 15))  # Tuesday
    _, out = _run(db, report_date=date(2026, 11, 19))  # Wed, Thu = 2 weekdays
    assert out == []
    _, out = _run(db, report_date=date(2026, 11, 20))  # + Fri = 3
    assert len(out) == 1 and 'no training activity since Tue Nov 17' in out[0][0]
    _, out = _run(db, report_date=date(2026, 11, 23))
    assert out == []


def test_a_new_hire_is_not_called_quiet_in_week_one():
    db = DB(last=None)
    _, out = _run(db, report_date=date(2026, 11, 18), enrolled=datetime(2026, 11, 16, 13))
    assert out == []


def test_weekends_do_not_count_toward_quiet():
    assert A.weekdays_between(date(2026, 11, 20), date(2026, 11, 23)) == 1  # Fri -> Mon


def test_every_trackable_item_has_a_title():
    missing = [i for i in psc_training_data.get_all_item_ids() if i not in TITLES]
    assert missing == []


def test_evening_eastern_activity_counts_on_its_own_day():
    # 9:30pm ET Tuesday is 02:30 UTC Wednesday. Quiet must count from Tuesday.
    db = DB(last=datetime(2026, 11, 18, 2, 30))
    _, out = _run(db, report_date=date(2026, 11, 20))
    assert len(out) == 1 and 'since Tue Nov 17' in out[0][0]
