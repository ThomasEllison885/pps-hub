"""The Hub field guide, as content rather than a page.

Thomas wrote this as a PDF and sent it round on 2026-08-27. A PDF starts
drifting the day it is sent — by the time it landed, one line in it was
already wrong — and it is in an email from August rather than one tap from
the thing it explains. This is the same words, living next to the code they
describe.

── Three things this does that the PDF could not ───────────────────────────

**It shows you your Hub.** Every section carries an `access` predicate, so a
consultant does not read two pages about Office Ops they cannot open. The
`?all=1` view shows everything for anyone who wants the whole picture —
nothing here is secret, it is just noise if it is not yours.

**The facts that move are derived, not retyped.** Session length, the
pipeline statuses, the rolling-weeks window, the activity cap — these come
from the code that implements them (see `facts()`), so they cannot go stale
the way "the last-updated line is Eastern time" did. If you find yourself
typing a number into the prose below, check whether it can be derived
instead; a number in prose is a promise nobody is keeping.

**It records that it was read**, like every other page since F-03, so
"did anyone open the guide" is answerable.

── Editing it ──────────────────────────────────────────────────────────────

Sections are plain data. `body` is a list of blocks:

    ('p', 'a paragraph')
    ('ul', ['a bullet', 'another'])
    ('h', 'a sub-heading')
    ('note', 'a callout — used for the do-not-do items')
    ('dl', [('term', 'definition'), ...])

Ship a guide edit in the same commit as the change it describes. That is the
whole point of it being here.
"""

from __future__ import annotations

# ── Who sees which section ──────────────────────────────────────────────────
#
# `ctx` is what the route passes: booleans it already computed for the
# dashboard. Keeping these as lambdas over one dict means a section's
# audience is stated next to its content instead of in the route.

EVERYONE = lambda ctx: True                                        # noqa: E731
CONSULTANT_WORK = lambda ctx: bool(ctx.get('consultants'))         # noqa: E731
LEADERSHIP = lambda ctx: bool(ctx.get('is_leadership'))            # noqa: E731
OWNER = lambda ctx: bool(ctx.get('is_owner'))                      # noqa: E731
PSC = lambda ctx: bool(ctx.get('psc_training_enrolled')            # noqa: E731
                       or ctx.get('psc_training_oversight'))
BOARDS = lambda ctx: bool(ctx.get('pipeline_boards'))              # noqa: E731


def facts(session_days, statuses, completed_statuses, rolling_weeks,
          activity_cap, recap_day, recap_hour):
    """The numbers the prose would otherwise hardcode.

    Every one of these is read from the module that implements it, so the
    guide cannot claim a 30-day session after someone changes it to 14.
    """
    in_progress = [s['label'] for s in statuses
                   if s['value'] not in completed_statuses]
    done = [s['label'] for s in statuses if s['value'] in completed_statuses]
    return {
        'session_days': session_days,
        'statuses_in_progress': ', '.join(in_progress),
        'statuses_done': ', '.join(done),
        'rolling_weeks': rolling_weeks,
        'activity_cap': activity_cap,
        'recap_when': f'{recap_day} around {recap_hour}',
    }


# ── The guide ───────────────────────────────────────────────────────────────
#
# Thomas's words. Kept verbatim except where the page makes a sentence wrong:
# "this letter is the map" became "this page", and the page-number cross
# references are gone because a web page has anchors instead.

SECTIONS = [
    # "How to get in" was dropped 2026-08-27: you are reading this signed
    # in, so a section on signing in is telling you something you have just
    # done. The one part of it that was not about getting in — putting the
    # Hub on your phone's home screen — moved here. Same reason "What it is
    # for" merged into this section rather than repeating the tour twice.
    dict(
        id='start', title='Start here', access=EVERYONE,
        body=[
            ('p', 'PPS used to live in inboxes, side chats, and whoever had '
                  'the latest Excel. The Hub is the source of truth for the '
                  'work we produce: which proposal went out, which estimate '
                  'we ran, which row is sitting on a board, who finished '
                  'training.'),
            ('p', 'You do not need every module. Use the ones that match '
                  'your job. Do not invent a workaround in a spreadsheet we '
                  'already replaced.'),
            ('p', 'The dashboard is a launcher, not a second job. Jump back '
                  'in takes you to the last three tools you actually used. '
                  'The pills at the top are this week’s score, open '
                  'pipeline, and unfinished training. A zero does not show. '
                  'Quiet week, short dashboard.'),
            ('note', 'On your phone: open the Hub in Safari or Chrome, then '
                     'Add to Home Screen. That icon is the Hub, not a browser '
                     'bookmark, and sessions last {session_days} days of idle '
                     'time — you should not be logging in every morning.'),
        ],
    ),
    dict(
        id='dashboard', title='Dashboard', access=EVERYONE,
        body=[
            ('p', 'This is home. Sales &amp; Consulting on top, Production '
                  'below. On a phone the lanes fold; that is remembered. A '
                  'brand-new hire with no history keeps both lanes open so '
                  'they are not staring at grey bars.'),
            ('h', 'Jump back in'),
            ('p', 'Three cards, most recent first — not “most used this '
                  'month.” History is not permission: if you lost access '
                  'to a tool, it will not hand you a card that bounces you. '
                  'Pipeline Board opens the one you last used, then your '
                  'default board.'),
            ('h', 'Ask PPS and feedback'),
            ('p', 'Both sit in fold-down blocks on the dashboard. Ask PPS is '
                  'for “how do we do X at PPS.” Feedback is for '
                  '“the Hub should do Y.” Feedback comes to me. '
                  'Please use this! The more the better! Ask PPS answers from '
                  'our voice, training, and pricing notes — it is not allowed '
                  'to invent a number as policy. To be used in training. '
                  'Overtime will become more valuable.'),
        ],
    ),
    dict(
        id='proposal', title='Proposal Generator', access=EVERYONE,
        lane='Sales &amp; consulting',
        body=[
            ('p', 'Opens the proposal tool in a new window, already signed '
                  'in. Use it for client proposals, not for notes to '
                  'yourself. It writes in PPS language: residents, not '
                  'tenants; apartment community, not complex; Trade Partners, '
                  'not subcontractors; investment, not price, on the total. '
                  'You still own the walk-through and the number.'),
            ('ul', [
                'Pick the consultant the book belongs to. If you are writing '
                'for someone else, credit still follows whoever generated it.',
                'Site photos: take them upright. The tool now rotates them '
                'the right way.',
                'When you finish, it lands in Proposal History automatically.',
            ]),
        ],
    ),
    dict(
        id='proposal-history', title='Proposal History', access=EVERYONE,
        lane='Sales &amp; consulting',
        body=[
            ('p', 'Search what you have already produced. Consultants see '
                  'their book. PMs see their own plus paired consultants. '
                  'Download the Word file or regenerate. Client, contact, and '
                  'company show on the detail when we have them — older rows '
                  'logged before the vault path will be blank. That is not a '
                  'bug. Do not print “Contact —” on those.'),
        ],
    ),
    dict(
        id='clients', title='Clients', access=EVERYONE,
        lane='Sales &amp; consulting',
        body=[
            ('p', 'Shared contact list for proposals and pipeline. Search by '
                  'name, email, or company. Add a contact once. Monday CRM '
                  'syncs new contacts weekly (insert-only — it will not '
                  'overwrite a Hub-only contact). Placeholder names like '
                  '“New Contact” are skipped. Use this instead of a '
                  'personal spreadsheet.'),
        ],
    ),
    dict(
        id='ask-pps', title='Ask PPS', access=EVERYONE,
        lane='Sales &amp; consulting',
        body=[
            ('p', 'Type a real question. “How do we handle a concealed '
                  'condition on a condo?” is a good one. “Write me a '
                  'proposal” is not — that is the Proposal Generator. '
                  'Leadership curates answers. If you are assigned a prompt '
                  '(a gap we know we have), answer it. That is how the '
                  'library grows.'),
            ('note', 'Do not paste salaries, appraisals, or anyone’s '
                     'performance notes in here. That stays out of the Hub on '
                     'purpose.'),
        ],
    ),
    dict(
        id='psc-training', title='PSC Training', access=PSC,
        lane='Sales &amp; consulting',
        body=[
            ('p', 'Twelve-week onboarding for consultants: trades, '
                  'shadowing, PPS voice, sales. You only see it if you are '
                  'enrolled. Check off items as you finish them. A week that '
                  'is signed off stays signed off — new material added later '
                  'shows at the bottom as “Added since you started” '
                  'and does not reopen a finished week. Roleplay is a separate '
                  'page for enrolled PSCs. Tony, Trey, and Stephanie enroll '
                  'people and sign weeks off. Only I can revoke a sign-off.'),
        ],
    ),
    dict(
        id='pipeline', title='Pipeline Board', access=BOARDS,
        lane='Production',
        body=[
            ('p', 'One live board per consultant. PSC and PM (and anyone else '
                  'on the team) see the same rows. In-progress statuses are '
                  '{statuses_in_progress}. Yellow means in-progress — not '
                  '{statuses_done}. New rows start at new. It polls every 3 '
                  'seconds. That is on purpose — we are not putting the whole '
                  'Hub on one chat socket.'),
            ('ul', [
                'Search: the box in the toolbar, or press / (not while you '
                'are inside a cell). Terms AND together. “Walk” '
                'matches the status “Needs walk/scope.” Escape or '
                'the ✕ clears it. Hidden rows stay in the page so a '
                'refresh does not dump them back in the wrong order.',
                'Jump to open work: first open row you can still see.',
                'Client Contact is the client’s manager, not the PPS PM. '
                'It suggests last-used names on that property.',
                'Adding a row while a search is running clears the search so '
                'you are not creating an invisible row.',
                'Import from Excel is leadership-only. Editing and archiving a '
                'row is open to the whole roster. Import rewrites a board; '
                'editing moves one row.',
            ]),
            ('note', 'If the board ever looks empty, do not panic and do not '
                     'keep refreshing until it “comes back.” A '
                     'failed load keeps the last rows. Tell me.'),
        ],
    ),
    dict(
        id='estimating', title='Estimating', access=EVERYONE,
        lane='Production',
        body=[
            ('p', 'Four tools under one roof. Upload the measurement PDF you '
                  'already buy (EagleView, Roofr, Bid Perfect) or type field '
                  'numbers. You get a takeoff, a number, and an Excel file. '
                  'Yellow cells in Excel stay editable. Company rates pre-fill '
                  'from Pricing Defaults. You can still change a number on '
                  'that job. Changing the company default is leadership, not a '
                  'yellow cell.'),
            ('dl', [
                ('Siding', 'One takeoff per building type (A/B/C/D) and how '
                           'many of that type. Stack is Cost (labor + haul + '
                           'delivery) + Markup $ + Overhead $ = Invoice. '
                           'Margin % is Markup / Invoice. Those numbers write '
                           'into Excel Tab 6 — you should not be typing yellow '
                           'zeros after download.'),
                ('Roofing', 'GAF material list from a Premium or Roofr report, '
                            'or a quick bid from EagleView Bid Perfect. Labor '
                            'per square, material, tax, waste, dump loads.'),
                ('Gutters', 'Eaves length in, gutters / downspouts / guards '
                            'out. Spacing and downspout height are defaults you '
                            'can change on the job. Good for a same-day number '
                            'when the roof report is already in hand.'),
                ('Exterior painting', 'Field takeoff by category. Labor hours '
                                      'from production rates, paint, one-coat '
                                      'and two-coat bids. If the rate looks '
                                      'wrong, tell Trey or Tony — they can fix '
                                      'the company default now.'),
            ]),
            ('note', 'Same rule everywhere: override the job, do not silently '
                     'rewrite company defaults.'),
        ],
    ),
    dict(
        id='site-visit', title='Site Visit Report', access=EVERYONE,
        lane='Production',
        body=[
            ('p', 'Use it after a walk, not instead of a walk. Photos, notes, '
                  'what you saw versus what was proposed. This is the record '
                  'when someone asks three weeks later what was on the '
                  'building.'),
        ],
    ),
    dict(
        id='ppm', title='Pre-Project Meeting (PPM)', access=EVERYONE,
        lane='Production',
        body=[
            ('p', 'Checklist generated from an approved proposal. This is the '
                  'handoff between sales and production. If you skip it, the '
                  'job still starts — it just starts with gaps. History is '
                  'under My PPMs.'),
        ],
    ),
    dict(
        id='tps', title='Trade Partner Scope (TPS)', access=CONSULTANT_WORK,
        lane='Production',
        body=[
            ('p', 'Crew-ready scope from the proposal, English and Spanish. '
                  'This is what we send the Trade Partner, not a paste from '
                  'the client proposal. History: My TPS Scopes. PMs and '
                  'consultants who generated one, or who are PM on it, can '
                  'find it there.'),
        ],
    ),
    dict(
        id='pm-training', title='PM Training', access=EVERYONE,
        lane='Production',
        body=[
            ('p', 'Four weeks are live: Production Board, routes, Trade '
                  'Partners, materials/callbacks. Week 5 (scoreboard / '
                  'production-meeting cadence) is designed and not built yet — '
                  'do not wait on it. Same enrollment rules as PSC: leadership '
                  'enrolls and signs off. Added items after you started sit at '
                  'the bottom and do not undo a signed week.'),
        ],
    ),
    dict(
        id='team-view', title='Team View', access=EVERYONE,
        body=[
            ('p', 'Open to everyone, and the same scoring as the Monday '
                  'recap — this week plus a rolling {rolling_weeks}, ranked '
                  'inside Consultants / PMs / Office rather than one flat '
                  'list. Credit follows whoever generated the work, not whose '
                  'name is on the proposal. Pipeline and Hub actions are '
                  'capped at {activity_cap} a week so a week of real '
                  'deliverables still leads. If your number disagrees with '
                  'Monday’s email, that is a bug — tell me. Do not keep a '
                  'second spreadsheet of “my real number.”'),
        ],
    ),
    dict(
        id='recap', title='Monday recap', access=EVERYONE,
        body=[
            ('p', 'Every {recap_when} you get an email with last week’s '
                  'board. Your row is highlighted. A visible 0 is better than '
                  'a missing name. Completing work scores; opening pages does '
                  'not. I am on the board with you. If the email does not '
                  'arrive, it is not because you were left off — tell me so we '
                  'can see if the job ran.'),
        ],
    ),
    dict(
        id='office-ops', title='Office Ops', access=LEADERSHIP,
        lane='Leadership only',
        body=[
            ('p', 'Two cards: Numbers and Compliance. Numbers is the Thursday '
                  'pack from QuickBooks — Invoice List / Rep Sales YTD and AR '
                  'aging. Stephanie uploads the Excel as-is (filename '
                  '“Rep Sales YTD” is fine). Compliance is Trade '
                  'Partner insurance: expired, expiring, new, and pay-request '
                  'mismatches. View COI opens the file. Date overrides beat a '
                  'stale Monday board date and lose to a COI we can actually '
                  'read. Compliance is under construction.'),
            ('note', '“Run now” sends a real email. Do not click it '
                     'to see what it looks like.'),
        ],
    ),
    dict(
        id='training-editor', title='Training oversight and editor',
        access=LEADERSHIP, lane='Leadership only',
        body=[
            ('p', 'Enroll, sign weeks, read feedback. Edit Training is the '
                  'curriculum editor. Drafts are invisible to trainees until '
                  'you Publish. A published add shows in-week for new hires '
                  'and in “Added since you started” for people '
                  'already enrolled. Discard only works on never-published '
                  'drafts. Hide live items instead of deleting them.'),
            ('note', 'Do not insert an item in the middle of a list in the '
                     'Python files — that is how checkmarks silently move. Use '
                     'the editor.'),
        ],
    ),
    dict(
        id='pricing-defaults', title='Estimating pricing defaults',
        access=LEADERSHIP, lane='Leadership only',
        body=[
            ('p', 'You can edit the company rates that pre-fill siding, '
                  'roofing, gutter, and painting. Dashboard → Production '
                  '&amp; Field → Estimating Pricing Defaults, or Estimating '
                  '→ Company Pricing Defaults. Save writes for the whole team. A field '
                  'person can still change a number on one job. They cannot '
                  'change what the next job starts with.'),
            ('ul', [
                'If a trade’s labor or material moved, change it here the '
                'same day. Do not wait on me.',
                'Excel yellow cells remain the per-job override. Do not tell '
                'the team to “just edit Excel” as the new default.',
                'The last-updated line shows who saved.',
            ]),
        ],
    ),
    dict(
        id='what-not', title='What not to do', access=EVERYONE,
        body=[
            ('ul', [
                'Do not share a login. Ever. When someone leaves we take '
                'their name off the roster and their session dies — that only '
                'works if you never loaned them yours.',
                'Do not score yourself by opening pages. The recap ignores '
                'that on purpose.',
                'Do not put salaries, appraisals, or “who we might let '
                'go” in Ask PPS or a training note.',
                'Do not import a spreadsheet onto a Pipeline Board unless you '
                'are leadership — and even then, only when a new consultant is '
                'starting from Excel.',
                'Do not rebuild a personal tracker for something the Hub '
                'already stores.',
                'Do not call Office Ops “the admin page.” Admin is '
                'mine. Office Ops is Numbers and Compliance.',
            ]),
        ],
    ),
    dict(
        id='broken', title='If it is broken', access=EVERYONE,
        body=[
            ('p', 'Feedback box on the dashboard, or text me. Include which '
                  'page and what you clicked. “It froze” on a '
                  'proposal usually meant the detail modal — that close-button '
                  'bug is fixed. Pipeline looking empty is a load failure, not '
                  'a wipe. Estimating numbers that look like last year’s '
                  'rates probably mean the default was not updated — '
                  'leadership can fix that now.'),
        ],
    ),
]


def _fill(text, values):
    """Substitute the derived facts. A missing key leaves the text alone
    rather than raising — a guide that 500s is worse than one with a stray
    brace in it."""
    try:
        return text.format(**values)
    except (KeyError, IndexError, ValueError):
        return text


def sections_for(ctx, values, show_all=False):
    """The sections this person should read, with the facts filled in.

    `show_all` keeps every section, which is what `?all=1` does — the guide
    is not a secret, it is just noise when it is not yours.
    """
    out = []
    for section in SECTIONS:
        mine = bool(section['access'](ctx))
        if not mine and not show_all:
            continue
        body = []
        for kind, content in section['body']:
            if kind == 'ul':
                body.append((kind, [_fill(i, values) for i in content]))
            elif kind == 'dl':
                body.append((kind, [(t, _fill(d, values)) for t, d in content]))
            else:
                body.append((kind, _fill(content, values)))
        out.append({
            'id': section['id'],
            'title': section['title'],
            'lane': section.get('lane', ''),
            'body': body,
            'mine': mine,
        })
    return out


def hidden_count(ctx):
    """How many sections this person does not see — so the page can offer
    them rather than pretending they do not exist."""
    return sum(1 for s in SECTIONS if not s['access'](ctx))
