"""The digest, when the author is a short consultant key.

Run: python -m pytest tests/test_daily_digest_attribution.py -v

── Why this one survived the fix for the same bug ──────────────────────────

`user_aliases` was created on 2026-08-29 because Rachel's proposals were
logged under `'rachel'` rather than `'rachel_farler'` and every consumer
filtered `if user_key in users`, which **dropped** the rows. Fixing the weekly
recap meant hunting for work that had gone missing, and that is a loud kind of
wrong: Thomas noticed within a week that her number was zero.

The digest is the quiet kind. It never dropped anything. It grouped by the raw
column and `_display_name` falls back to `key.replace('_', ' ').title()`, so
`'rachel'` came out as **"Rachel"** — a name, sitting a few lines above
"Rachel Farler", looking for all the world like the digest working. Three
symptoms, one cause, and each of them individually reads as a small oddity
rather than a bug:

  * a second person named after a dropdown value,
  * that same person under QUIET TODAY on a day she filed proposals, because
    `active_keys` was built from the raw key and never matched her roster
    entry, and
  * `DAILY_DIGEST_EXCLUDE=thomas_ellison` failing to exclude Thomas's own
    bookmark-logged work, because that arrives as `'thomas'`.

The tests below are written from those three symptoms rather than from the
implementation, because the implementation is one line and the symptoms are
what anyone would actually notice.
"""
import os
import sys
from datetime import date, datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import daily_digest as dd  # noqa: E402
import user_aliases  # noqa: E402

USERS = {
    'andy_potts': {'display': 'Andy Potts', 'role': 'consultant'},
    'rachel_farler': {'display': 'Rachel Farler', 'role': 'consultant'},
    'phil_miller': {'display': 'Phil Miller', 'role': 'pm'},
    'thomas_ellison': {'display': 'Thomas Ellison', 'role': 'admin'},
}
AT = datetime(2026, 8, 26, 14, 30)


def _did(user_key, kind='proposal', label='Proposal', title='Cedar Ridge'):
    """Built the way the collectors build it: the key straight off the row,
    and the display name derived from it."""
    return dd._item(user_key, dd._display_name(USERS, user_key),
                    kind, label, title, '', AT)


def _email(items, exclude=None, counts=None):
    return dd.build_digest_email(
        date(2026, 8, 26), items, counts or {}, USERS,
        exclude if exclude is not None else {'thomas_ellison'})


# ── symptom 1: the invented second person ───────────────────────────────────

def test_a_short_key_lands_on_the_person_it_belongs_to():
    item = _did('rachel')
    assert item['user_key'] == 'rachel_farler'
    assert item['display_name'] == 'Rachel Farler'


def test_the_digest_does_not_grow_a_second_rachel():
    """The whole symptom in one assertion: two proposals, one under each
    spelling, must read as one person with two items."""
    _, text, _ = _email([_did('rachel'), _did('rachel_farler', title='Maple Court')])
    assert 'Rachel Farler (2)' in text
    assert text.count('Rachel') == text.count('Rachel Farler'), (
        'a bare "Rachel" appears somewhere — the short key became a person')
    assert 'from 1 people' in text


def test_a_key_belonging_to_nobody_still_gets_a_readable_name():
    """The `.title()` fallback stays. A departed employee's rows keep arriving
    and "Derek Kidney" reads better than a bare key — the fix is that the
    fallback now only fires when there really is nobody behind the key."""
    item = _did('derek_kidney')
    assert item['user_key'] == 'derek_kidney'
    assert item['display_name'] == 'Derek Kidney'


def test_unattributed_work_is_not_given_an_owner():
    """'unknown' is what the PPM and TPS loggers write when there is no
    session. Resolving must not invent someone to blame it on."""
    item = _did(user_aliases.UNATTRIBUTED)
    assert item['user_key'] == 'unknown'


# ── symptom 2: quiet on a day she worked ────────────────────────────────────

def test_she_is_not_listed_as_quiet_on_a_day_she_filed_a_proposal():
    """`active_keys` is built from `item['user_key']`, so before the fix her
    roster entry never matched anything and she appeared in QUIET TODAY —
    below her own proposal."""
    _, text, _ = _email([_did('rachel')])
    quiet = text.split('QUIET TODAY')[1].split('\n')[1]
    assert 'Rachel Farler' not in quiet, 'quiet on a day she produced work'
    assert 'Phil Miller' in quiet, 'and someone who really was quiet still is'


# ── symptom 3: the exclude list ─────────────────────────────────────────────

def test_excluding_a_person_excludes_their_short_key_too(monkeypatch):
    monkeypatch.setenv('DAILY_DIGEST_EXCLUDE', 'thomas_ellison')
    keys = dd._digest_exclude_keys()
    assert 'thomas_ellison' in keys
    assert 'thomas' in keys, (
        "Thomas's own bookmark-logged proposals are still in his digest")


def test_it_works_from_the_short_form_as_well(monkeypatch):
    """Whoever sets the variable should not have to know which spelling the
    proposal form emits."""
    monkeypatch.setenv('DAILY_DIGEST_EXCLUDE', 'rachel')
    keys = dd._digest_exclude_keys()
    assert {'rachel', 'rachel_farler'} <= keys


def test_excluding_someone_with_no_alias_is_unchanged(monkeypatch):
    monkeypatch.setenv('DAILY_DIGEST_EXCLUDE', 'phil_miller,stephanie_shrout')
    assert dd._digest_exclude_keys() == {'phil_miller', 'stephanie_shrout'}


def test_one_persons_alias_does_not_drag_in_anybody_else(monkeypatch):
    """The expansion is per-person, not "add every alias we know"."""
    monkeypatch.setenv('DAILY_DIGEST_EXCLUDE', 'thomas_ellison')
    keys = dd._digest_exclude_keys()
    assert 'rachel' not in keys and 'rachel_farler' not in keys


def test_an_empty_setting_still_excludes_nobody(monkeypatch):
    monkeypatch.setenv('DAILY_DIGEST_EXCLUDE', '')
    assert dd._digest_exclude_keys() == set()


# ── the Hub-side columns are untouched ──────────────────────────────────────

@pytest.mark.parametrize('key', ['andy_potts', 'phil_miller', 'stephanie_shrout',
                                 'unknown', 'derek_kidney'])
def test_keys_that_were_never_aliases_pass_through(key):
    """`actor`, `override_by` and `user_key` come from Hub SSO and have always
    been roster keys. Resolving them must be a no-op — this is the assertion
    that the fix cannot break the eleven collectors that were already right."""
    assert dd._item(key, 'X', 'proposal', 'Proposal', 'T', '', AT)['user_key'] == key
