"""Client / Contact / Company on the proposal detail modal.

These rows are built by `_activity_detail_payload` in app.py, which no test can
import (Flask app at module scope). The rules are copied here as the reference
implementation and pinned; if you change one, change both.

Run: python -m pytest tests/test_proposal_contact_rows.py -v
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app.py')


# --- Reference implementation (mirrors app.py) -------------------------------

def format_contact(row, client=''):
    name = (row.get('contact_name') or '').strip()
    email = (row.get('contact_email') or '').strip()
    if name and client and name.casefold() == client.strip().casefold():
        name = ''
    return ' · '.join(p for p in (name, email) if p)


def contact_rows(row):
    """Returns [(label, value), ...] for the Client/Contact/Company block."""
    client = (row.get('client_name') or '').strip()
    company = (row.get('company') or '').strip()
    contact = format_contact(row, client)
    out = []
    if client:
        out.append(('Client', client))
    if contact:
        out.append(('Contact', contact))
    if company and company.casefold() != client.casefold():
        out.append(('Company', company))
    return out


# --- Behaviour ---------------------------------------------------------------

def test_name_and_email_join_onto_one_line():
    assert format_contact(
        {'contact_name': 'Dana Reed', 'contact_email': 'dana@acme.com'}
    ) == 'Dana Reed · dana@acme.com'


def test_either_half_alone_still_shows():
    assert format_contact({'contact_name': 'Dana Reed'}) == 'Dana Reed'
    assert format_contact({'contact_email': 'dana@acme.com'}) == 'dana@acme.com'


def test_a_pre_vault_proposal_gains_no_empty_rows():
    """`/log-proposal`, the original logging path, never wrote these columns —
    only `/api/vault/proposals` does. Every proposal older than that has them
    blank, and printing three dashes would make the modal worse, not better."""
    assert contact_rows({'client_name': None, 'contact_name': None,
                         'contact_email': None, 'company': None}) == []


def test_client_shows_without_contact_and_contact_without_client():
    assert contact_rows({'client_name': 'Acme Property Group'}) == [
        ('Client', 'Acme Property Group')]
    assert contact_rows({'contact_email': 'dana@acme.com'}) == [
        ('Contact', 'dana@acme.com')]


def test_company_is_dropped_when_it_only_repeats_the_client():
    """The proposal tool often sends the same string for both. A row that says
    what the row above it said is padding."""
    row = {'client_name': 'Acme Property Group', 'company': 'Acme Property Group'}
    assert [lab for lab, _ in contact_rows(row)] == ['Client']


def test_company_repetition_check_ignores_case_and_padding():
    row = {'client_name': 'Acme Property Group ', 'company': 'ACME PROPERTY GROUP'}
    assert [lab for lab, _ in contact_rows(row)] == ['Client']


def test_a_genuinely_different_company_survives():
    row = {'client_name': 'Dana Reed', 'company': 'Acme Property Group'}
    assert contact_rows(row) == [
        ('Client', 'Dana Reed'), ('Company', 'Acme Property Group')]


def test_whitespace_only_values_count_as_absent():
    assert contact_rows({'client_name': '   ', 'contact_name': '\t',
                         'contact_email': '', 'company': '  '}) == []


def test_full_row_orders_client_then_contact_then_company():
    row = {'client_name': 'Dana Reed', 'contact_name': 'Dana Reed',
           'contact_email': 'dana@acme.com', 'company': 'Acme Property Group'}
    assert [lab for lab, _ in contact_rows(row)] == ['Client', 'Contact', 'Company']


def test_contact_name_is_dropped_when_it_repeats_the_client():
    """Single-owner properties send the same person as both. Printing
    "Dana Reed" on the Client row and again on the Contact row is padding —
    the email is the part the Contact row is actually adding."""
    row = {'client_name': 'Dana Reed', 'contact_name': 'Dana Reed',
           'contact_email': 'dana@acme.com'}
    assert dict(contact_rows(row))['Contact'] == 'dana@acme.com'


def test_a_contact_who_is_not_the_client_keeps_their_name():
    row = {'client_name': 'Acme Property Group', 'contact_name': 'Dana Reed',
           'contact_email': 'dana@acme.com'}
    assert dict(contact_rows(row))['Contact'] == 'Dana Reed · dana@acme.com'


def test_a_repeated_contact_with_no_email_drops_the_row_entirely():
    """Nothing left to say once the duplicated name is removed."""
    row = {'client_name': 'Dana Reed', 'contact_name': 'Dana Reed'}
    assert [lab for lab, _ in contact_rows(row)] == ['Client']



# --- Guard against the reference drifting from app.py ------------------------

def test_app_py_still_builds_these_three_rows_before_address():
    """Cheap structural check: if someone deletes the block, this fails rather
    than the tests above passing against a copy nothing uses."""
    src = open(APP).read()
    start = src.index('def _activity_detail_payload')
    block = src[start:start + 2000]
    for label in ("'Client'", "'Contact'", "'Company'"):
        assert label in block, f'{label} row missing from _activity_detail_payload'
    assert block.index("'Client'") < block.index("'Address'"), (
        'Client should sit above Address — who it is for, then what it was')


def test_app_py_still_skips_a_company_that_repeats_the_client():
    src = open(APP).read()
    assert re.search(r'company\.casefold\(\)\s*!=\s*client\.casefold\(\)', src), (
        'the duplicate-company guard is gone from app.py')
