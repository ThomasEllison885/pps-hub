"""The working notes, and the hook that makes us keep them.

Run: python -m pytest tests/test_working_notes.py -v

Thomas, 2026-08-30: "Can you make it to where you and grok update it
everytime?"

Two agents share `CLAUDE.md` and neither remembers the other's sessions. Up to
now the rule was a sentence at the top of the file asking nicely, and three
commits went unrecorded for two days — including one that had caused a
production restart. A hook is the same rule with teeth.

The failure this file exists to prevent is not "someone deleted the hook on
purpose". It is a fresh clone where nobody ran `git config core.hooksPath
hooks`, so the hook is present, tracked, and never runs — enforcement that
looks fine and does nothing.
"""
import os
import stat
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(ROOT, 'hooks', 'pre-commit')
NOTES = os.path.join(ROOT, 'CLAUDE.md')


def _in_a_git_checkout():
    done = subprocess.run(['git', 'rev-parse', '--is-inside-work-tree'],
                          cwd=ROOT, capture_output=True, text=True)
    return done.returncode == 0 and done.stdout.strip() == 'true'


# An agent's scratch copy of the repo is not a checkout, and the two git tests
# below would fail there for a reason that says nothing about the code. Skip
# rather than fail — but skip *loudly*, because "passed where it did not
# matter" is exactly how the template guard sat red on main for three days.
needs_git = pytest.mark.skipif(
    not _in_a_git_checkout(),
    reason='not a git checkout — run this in the real repo, where it counts')


@needs_git
def test_the_working_notes_live_in_this_repo():
    """They used to sit one level up, outside both repos: no history, no
    merge, no conflict — whoever wrote last silently won."""
    assert os.path.exists(NOTES)
    tracked = subprocess.run(
        ['git', 'ls-files', '--error-unmatch', 'CLAUDE.md'],
        cwd=ROOT, capture_output=True, text=True)
    assert tracked.returncode == 0, 'CLAUDE.md is not tracked by git'


def test_the_hook_exists_and_can_run():
    assert os.path.exists(HOOK), 'the pre-commit hook is gone'
    assert os.stat(HOOK).st_mode & stat.S_IXUSR, (
        'the hook is not executable, so git will skip it silently')


def test_the_hook_is_valid_shell():
    done = subprocess.run(['sh', '-n', HOOK], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


@needs_git
def test_git_is_actually_pointed_at_the_hooks_directory():
    """The quiet failure: a fresh clone has the hook tracked and never runs
    it, because `core.hooksPath` is local config and does not travel."""
    done = subprocess.run(['git', 'config', '--get', 'core.hooksPath'],
                          cwd=ROOT, capture_output=True, text=True)
    assert done.stdout.strip() == 'hooks', (
        "run: git config core.hooksPath hooks   (once per clone — it is local "
        "config, so cloning this repo does not bring it along)")


def test_the_hook_lets_a_notes_only_or_tests_only_commit_through():
    """Blocking a test tweak trains people to reach for --no-verify, which is
    how a hook stops working."""
    body = open(HOOK, encoding='utf-8').read()
    assert "grep -v '^tests/'" in body
    assert '--no-verify' in body, 'there must be a documented escape hatch'


def test_the_hook_names_what_to_do_rather_than_just_refusing():
    body = open(HOOK, encoding='utf-8').read()
    assert 'git add' in body
    assert 'Active threads' in body


def test_resolved_entries_are_kept_rather_than_deleted():
    """Thomas: "I would more want to keep track of changes as they happen.
    Not necessarily delete things unless that is necessary." The file's own
    instruction used to say the opposite."""
    notes = open(NOTES, encoding='utf-8').read()
    assert 'Resolve entries; do not delete them' in notes
    assert "delete a line once it's fully resolved" not in notes, (
        'the old delete-when-done instruction is back')


def test_the_notes_say_where_they_now_live():
    notes = open(NOTES, encoding='utf-8').read()
    assert 'pps-hub/CLAUDE.md' in notes
    assert 'core.hooksPath hooks' in notes, (
        'a fresh clone needs the one-time command written down somewhere it '
        'will be read')
