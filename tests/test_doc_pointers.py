"""No source comment may cite a document that is not in this repo.

Run: python -m pytest tests/test_doc_pointers.py -v

── The specific case ───────────────────────────────────────────────────────

`docs/HUB_REVIEW_2026-08-21.md` was cited from `app.py` (twice),
`weekly_recap.py` and `CLAUDE.md` for ten days. There is no `docs/` directory.
Grok found it by reading the code; a person would have found it by going to
look for the file, which is worse — a pointer to a missing document reads as
"the reasoning is written down somewhere", so the next reader spends twenty
minutes looking for it before concluding it was never there.

Those three now point at the summaries in `CLAUDE.md`, which is the only place
the findings actually live.

── And the reason the file itself is not being added ───────────────────────

The surviving copy of that review **quotes the retired shared-Admin password
in plaintext**, in its F-01 finding. Committing it would put a credential back
into this repo's history, which is the exact thing `2f6dd58`…`e07043b` were
cleaned up for. The password is not restated here or anywhere else in the
tree.

Standing instruction from Thomas, 2026-08-31: if anyone wants that review in
`docs/`, **redact the password first and ask him.** The test below is the
tripwire — putting the file in the repo turns this suite red until someone
reads this paragraph.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

MISSING_DOC = 'HUB_REVIEW_2026-08-21.md'

SOURCE_FILES = [
    f for f in os.listdir(ROOT)
    if f.endswith('.py') and os.path.isfile(os.path.join(ROOT, f))
]


def _read(name):
    with open(os.path.join(ROOT, name)) as fh:
        return fh.read()


def test_no_module_points_at_the_missing_review():
    offenders = []
    for name in SOURCE_FILES:
        for match in re.finditer(re.escape(f'docs/{MISSING_DOC}'), _read(name)):
            line = _read(name)[:match.start()].count('\n') + 1
            offenders.append(f'{name}:{line}')
    assert not offenders, (
        f'these cite a document that is not in the repo: {offenders} — '
        f'point them at the summaries in CLAUDE.md instead')


def test_the_findings_they_used_to_point_at_are_reachable():
    """Repointing is only an improvement if the destination exists. F-01 is the
    retired shared login; F-04 is the weekly recap."""
    notes = _read('CLAUDE.md')
    assert 'Shared "Admin" login REMOVED' in notes, 'the F-01 summary is gone'
    assert 'Hub review (2026-08-21)' in notes, 'the review summary is gone'


def test_the_two_repointed_comments_say_where_to_look():
    """A bare "F-01" is not better than a broken path — the point of the change
    is that a reader can follow it."""
    assert 'See CLAUDE.md' in _read('app.py')
    assert 'See CLAUDE.md' in _read('weekly_recap.py')


def test_the_review_itself_has_not_been_added_without_redacting_it():
    """A tripwire, not a prohibition. The file may go into docs/ — but only
    with the retired shared-Admin password taken out of its F-01 finding, and
    only with Thomas's say-so. If this fails, read this module's docstring
    before deleting the test."""
    assert not os.path.exists(os.path.join(ROOT, 'docs', MISSING_DOC)), (
        'the 2026-08-21 review is in the repo — confirm the shared-Admin '
        'password was redacted from it first')
