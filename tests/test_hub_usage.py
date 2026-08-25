"""Daily-digest usage helpers — no live Postgres."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import daily_digest as dd
import hub_usage


def test_event_label_known_feature_and_count():
    feat, head, extra = hub_usage.event_label('pipeline', 'open', 'Andy Potts', 4)
    assert feat == 'Pipeline'
    assert head == 'Pipeline · Opened · Andy Potts'
    assert extra == '4×'


def test_event_label_unknown_feature_still_readable():
    feat, head, extra = hub_usage.event_label('site_visit_v2', 'export', '', 1)
    assert feat == 'Site Visit V2'
    assert 'Export' in head
    assert extra == ''


def test_record_usage_no_conn_does_not_raise():
    hub_usage.record_usage(lambda: None, 'andy_potts', 'pipeline', 'open', 'Andy')


def test_kind_totals_includes_pipeline_compliance_and_unknowns():
    lines = dd._kind_totals({
        'proposal': 2,
        'pipeline': 5,
        'compliance': 3,
        'new_gadget': 1,
        'login': 0,
    })
    labels = [label for label, _ in lines]
    assert 'Proposals' in labels
    assert 'Pipeline Board' in labels
    assert 'Compliance' in labels
    assert 'New Gadget' in labels
    assert 'Hub logins' not in labels


def test_board_title():
    users = {'andy_potts': {'display': 'Andy Potts'}}
    assert dd._board_title(users, 'andy_potts') == "Andy Potts's board"


# ── F-06: the table is not created on every write (2026-08-26) ──────────────

def test_ensure_tables_only_runs_the_ddl_once():
    """record_usage used to call init_tables before every insert — a CREATE
    TABLE and two CREATE INDEX to log one event. All no-ops after the first
    time, but each is a round trip and CREATE INDEX IF NOT EXISTS takes a
    lock on the table it is about to not create."""
    import hub_usage

    hub_usage.reset_tables_ready()
    statements = []

    class Cur:
        def execute(self, sql, params=None):
            statements.append(' '.join(str(sql).split())[:40])

    cur = Cur()
    assert hub_usage.ensure_tables(cur) is True
    first = len(statements)
    assert first == 3, 'CREATE TABLE + two CREATE INDEX'

    for _ in range(5):
        assert hub_usage.ensure_tables(cur) is True
    assert len(statements) == first, 'later calls must issue nothing'
    hub_usage.reset_tables_ready()


def test_a_failed_create_is_retried_rather_than_assumed_done():
    """Set the flag only after the DDL actually worked — otherwise one blip
    at startup means the table is never created for the life of the worker."""
    import hub_usage

    hub_usage.reset_tables_ready()
    calls = {'n': 0}

    class BadCur:
        def execute(self, sql, params=None):
            calls['n'] += 1
            raise RuntimeError('permission denied')

    assert hub_usage.ensure_tables(BadCur()) is False
    assert hub_usage.ensure_tables(BadCur()) is False
    assert calls['n'] == 2, 'still trying'

    ok = []

    class GoodCur:
        def execute(self, sql, params=None):
            ok.append(sql)

    assert hub_usage.ensure_tables(GoodCur()) is True
    assert hub_usage.ensure_tables(GoodCur()) is True
    assert len(ok) == 3, 'created once, then never again'
    hub_usage.reset_tables_ready()


def test_record_usage_does_not_repeat_the_ddl():
    """The end to end shape: one insert per event after the first."""
    import hub_usage

    hub_usage.reset_tables_ready()
    seen = []

    class Cur:
        def execute(self, sql, params=None):
            seen.append(' '.join(str(sql).split()).split(' ')[0].upper())

        def close(self):
            pass

    class Conn:
        def cursor(self):
            return Cur()

        def commit(self):
            pass

        def close(self):
            pass

    get_db = lambda: Conn()
    hub_usage.record_usage(get_db, 'andy_potts', 'pipeline', 'open', 'Andy Potts')
    assert seen.count('CREATE') == 3 and seen.count('INSERT') == 1

    seen.clear()
    for _ in range(4):
        hub_usage.record_usage(get_db, 'andy_potts', 'pipeline', 'open', 'Andy Potts')
    assert seen.count('CREATE') == 0, 'no DDL after the first event'
    assert seen.count('INSERT') == 4
    hub_usage.reset_tables_ready()
