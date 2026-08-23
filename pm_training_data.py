"""PM Onboarding — Project Manager training curriculum.

Week 1 Production Board content uses proper Monday column names from production_board_reference.py.
See docs/PM_TRAINING_ROADMAP.md and docs/PRODUCTION_BOARD_REFERENCE.md.
"""

import copy
from functools import lru_cache

from production_board_reference import (
    AWARD_TO_MOBILIZATION_CHECKLIST,
    PM_MORNING_CHECKLIST,
    PRODUCTION_BOARD_STATUS_GROUPS,
    UPDATES_GUIDANCE,
    get_production_board_reference,
)

PM_TRAINING_MANAGER = 'trey_hollmeyer'

PM_TRAINING_META = {
    'title': 'PM Onboarding',
    'subtitle': 'Project Manager Training Program',
    'status': 'under_construction',
    'under_construction': True,
    'under_construction_note': (
        'Under construction — content and Hub tracking are live for review. '
        'Expect refinements with Trey and senior PMs. Progress you check off is saved.'
    ),
    'description': (
        'A structured onboarding path for Project Managers — shadowing first, then building a '
        'personal operating system for routes, Trade Partners, materials discipline, callbacks, '
        'and time on site vs. desk work. Monday.com is shared with PSCs — they learn pipeline Monday '
        'in PSC Training; PM Week 1 deep-dives the Production Board (post-award).'
    ),
    'duration_weeks': 4,
    'reference_docs': [
        'docs/PRODUCTION_BOARD_REFERENCE.md',
        'production_board_reference.py',
    ],
}


def _status_groups_training_text():
    lines = ['Jobs live in status groups on the Production Board. Learn these names and what they mean:\n']
    for g in PRODUCTION_BOARD_STATUS_GROUPS:
        lines.append(f'• {g["name"]} — {g["meaning"]} PM action: {g["pm_action"]}')
    return '\n'.join(lines)


def _morning_checklist_training_text():
    lines = ['Start every production day on the Production Board:\n']
    for i, step in enumerate(PM_MORNING_CHECKLIST, 1):
        lines.append(f'{i}. {step}')
    lines.append(
        '\nMentor exercise: shadow one full morning. You narrate the checklist on the next day; mentor corrects.'
    )
    return '\n'.join(lines)


def _award_checklist_training_text():
    lines = [
        'When a job is awarded, the Production Board row must be complete before mobilization. '
        'Use these exact Monday column names:\n',
    ]
    for c in AWARD_TO_MOBILIZATION_CHECKLIST:
        lines.append(f'• {c["field"]} — {c["action"]}')
    lines.append(
        '\nMove from Awarded - On Hold → Needs Scheduled only when PPM is Yes (if required) and '
        'Trade Partner fields are filled for Sub jobs. Post an Update when you set Estimated Timeline - Start.'
    )
    return '\n'.join(lines)


PM_TRAINING_WEEKS = [
    {
        'week': 1,
        'title': 'Shadow & Orientation',
        'topic_summary': (
            'See what a typical PM day and week look like before you own a route. Monday.com is not PM-only — '
            'PSCs live there too (pipeline, contacts, pre-award). Your Week 1 focus is the Production Board '
            'after award: status groups, column names, Updates, Consultant handoff from PSC, and how Hub tools '
            '(PPM, TPS, Proposal) map to the row.'
        ),
        'shadowing': [
            'Shadow an experienced PM for a full week — observe daily and weekly rhythm, not just site visits.',
            'Watch them open the Production Board first thing: how they filter to Project Manager, which status groups they scan, and how they read Updates before calling anyone.',
            'Ride along on jobs in different status groups: Awarded - On Hold, Scheduled, In Progress, and Completed Needs Customer Walk.',
            'Sit in while they post at least one Update on a live job (draw schedule, mobilization note, or @mention).',
        ],
        'additional': [
            {
                'title': 'Monday.com at PPS — PSC vs PM',
                'text': (
                    'Monday.com is shared across PPS. PSCs learn pipeline Monday in PSC Training Week 0 '
                    '(Company Operations → Monday.com at PPS / ops_monday): contacts, properties, follow-up, '
                    'proposals before award. PMs live on the Production Board after award. '
                    'At handoff, Consultant on the row = PSC who sold it; Project Manager = you. '
                    'PSC stays the client relationship; you own schedule, Trade Partners, and board hygiene. '
                    'Read docs/PRODUCTION_BOARD_REFERENCE.md — section "Monday.com at PPS".'
                ),
            },
            {
                'title': 'Production Board — what it is',
                'text': (
                    'The Production Board is the post-award system of record — one row per awarded job. '
                    'It holds Consultant, Project Manager, Proposal Number, Job Size, Trade, timelines, Trade Partner '
                    'fields (Sub Assigned, Sub Contract $), PPM, Files, margins, and status groups. '
                    'PSCs rarely drive status groups day-to-day; PMs do. Walk through with your mentor before your first solo session.'
                ),
            },
            {
                'title': 'Status groups — read top to bottom',
                'text': _status_groups_training_text(),
            },
            {
                'title': 'Morning order of operations on the Production Board',
                'text': _morning_checklist_training_text(),
            },
            {
                'title': 'Award → mobilization — column checklist',
                'text': _award_checklist_training_text(),
            },
            {
                'title': 'Hub tools on the board',
                'text': (
                    'Know which Hub output goes in which Monday column:\n'
                    '• Proposal Generator → Proposal Number, Files, Job Size, Trade, Company Type, Mgmt Company\n'
                    '• Site Visit → Survey, Files\n'
                    '• PPM Checklist Generator → PPM (set Yes; attach/link before mobilization)\n'
                    '• TPS (Trade Partner Scope) → Sub Assigned, Sub Contract $, Sold to Sub, link to Pay Request\n\n'
                    'There is no separate TPS column — Trade Partner work lives in the Sub fields. '
                    'Pair with your mentor: open one awarded row and trace each field to its Hub source.'
                ),
            },
            {
                'title': 'Updates — the operational thread',
                'text': UPDATES_GUIDANCE + (
                    ' During shadow week, read Updates on three active jobs. Note who posts (PM vs. office), '
                    'what gets attached (draw schedules, PDFs), and when @mentions are used. '
                    'Practice: draft one Update your mentor would post — review before sending.'
                ),
            },
            {
                'title': 'Communication avenues & contacts',
                'text': (
                    'Channels PPS uses: email, text, phone, Monday Updates, Hub tools, vendor portals. '
                    'The Production Board row is the anchor — Consultant, Customer Name, Email, Sub Assigned, '
                    'and Updates history tell you who to contact. '
                    '[TO DOCUMENT] central contact reference for preferred Trade Partners and key vendors.'
                ),
            },
        ],
        'pps_focus': [
            {
                'title': 'Trace one job on the Production Board',
                'text': (
                    'With your mentor, pick one real job. Starting at the row: read Name, Proposal Number, '
                    'status group, Project Manager, Estimated Timeline - Start/End, PPM, Sub Assigned, and the '
                    'last three Updates. Write 5 bullets: what stage it is in, what is missing on the board, '
                    'and what you would do tomorrow morning.'
                ),
            },
            {
                'title': 'Map your first-week observations',
                'text': (
                    'After shadowing, write a one-page summary: what surprised you, what repeats daily vs. weekly, '
                    'which Production Board columns you still confuse, and which status groups you saw most. '
                    'Review with your manager before Week 2.'
                ),
            },
        ],
        'manager_checkin': (
            'Can you walk through a typical Monday morning on the Production Board — which status groups you scan '
            'first, which columns you check on an In Progress job, and where PPM and Sub Contract $ get filled? '
            'Can you name the path from Awarded - On Hold to Scheduled?'
        ),
    },
    {
        'week': 2,
        'title': 'Your Route & Operating System',
        'topic_summary': (
            'Build a route and daily system that works for you. Practice Trade Partner communication, '
            'set clear expectations as a PM, and learn to balance site time with estimates, vendor follow-up, '
            'material checks, and email.'
        ),
        'shadowing': [
            'Shadow the same PM (or a second PM) while they build or adjust their weekly route — note how they batch site vs. desk time.',
            'Sit in on at least two Trade Partner calls or on-site coordination moments (mobilization, mid-job check-in, or punch).',
            'Watch them move a job on the Production Board (e.g. Needs Scheduled → Scheduled) and what columns they update the same day.',
        ],
        'additional': [
            {
                'title': 'Route planning & personal system',
                'text': (
                    'Create a route and weekly rhythm — use City and Location on the Production Board to group visits. '
                    'Decide which properties get drive-bys vs. scheduled visits and when you protect desk time for '
                    'Updates, email, and board hygiene. [TO DOCUMENT] route template and mentor review criteria.'
                ),
            },
            {
                'title': 'Trade Partner communication',
                'text': (
                    'Get comfortable contacting Trade Partners through the job lifecycle: award → mobilization → '
                    'In Progress → punch → close-out. Sub Assigned and Sub Contract $ on the board should match '
                    'what you communicated. Use PPS voice — Trade Partners, not subs. '
                    '[TO DOCUMENT] call/text examples by phase.'
                ),
            },
            {
                'title': 'Setting PM expectations',
                'text': (
                    'Define what you hold yourself and crews accountable to: response time, photo documentation, '
                    'site standards, escalation to Consultant or leadership. Board hygiene is part of this — '
                    'PPM Yes before mobilization, Updates when status changes, margins before invoicing. '
                    'Align with your manager on non-negotiables. [TO DOCUMENT] PM expectations one-pager.'
                ),
            },
            {
                'title': 'Dividing your time: site vs. desk',
                'text': (
                    'Plan how to split time between being on site and handling estimates, Trade Partner and vendor '
                    'communication, Production Board Updates, material status checks, and email. Block calendar '
                    'time for each — do not let reactive site visits consume the whole week. '
                    '[TO DOCUMENT] sample weekly time budget.'
                ),
            },
        ],
        'pps_focus': [
            {
                'title': 'Draft your Week-2 operating plan',
                'text': (
                    'Present your route sketch, Production Board morning routine, Trade Partner contact habit, '
                    'and a sample weekly calendar (site blocks vs. desk blocks) to your manager. '
                    'Adjust based on feedback before taking lead on a job.'
                ),
            },
        ],
        'manager_checkin': (
            'Do you have a workable route, a Production Board morning habit, a Trade Partner contact rhythm, '
            'and protected time for estimates and email — not just firefighting on site?'
        ),
    },
    {
        'week': 3,
        'title': 'Trade Partners & Materials Discipline',
        'topic_summary': (
            'You inherit the Trade Partner relationship at handoff — PSC vetted them for the sale, '
            'you run them day-to-day. This week is QC standards, payment triggers, and getting '
            'materials on site at the right time, not too early and not too late.'
        ),
        'shadowing': [
            'Shadow a Trade Partner mobilization from schedule confirmation through first-day site walk.',
            'Sit in on one payment-request decision — who requests it (you or the Consultant) and how it gets tagged in Monday.',
        ],
        'additional': [
            {
                'title': 'Trade Partner payment requests — who does it',
                'text': (
                    'Either the PM or the Consultant can submit a Trade Partner payment request — the requirement '
                    'is that you tag the other person on it. Tagging means you can search Monday by project and '
                    'see every payment request tied to that job, and everyone tagged gets the email confirming '
                    'the Trade Partner was paid. This came directly from the team via Ask PPS — it is the standard, '
                    'not a suggestion. (Source: field capture Jul 2026.)'
                ),
            },
            {
                'title': 'QC before you pay',
                'text': (
                    '[TO DOCUMENT] — pull the QC checklist from the PSC-side Trade Partner SOP '
                    '(ops_trade_partners in psc_training_data.py) and confirm with Trey which items are PM sign-off '
                    'vs. PSC sign-off before a Trade Partner invoice gets approved.'
                ),
            },
            {
                'title': 'Just-in-time materials — the rule',
                'text': (
                    'Do not order stock materials months before a job starts just to get it off your plate. '
                    'For commodity items you keep on hand (filters, common fixtures, standard fasteners), order '
                    'close to mobilization. For specialized or long-lead one-offs (custom light fixtures, '
                    'special-order doors, anything with a multi-week lead time), order right away — those are the '
                    'items that cause delays. Rule of thumb straight from Thomas: "don\'t order the stuff you have '
                    'stock of just to have it sitting there — order the stragglers first."'
                ),
            },
            {
                'title': 'Warehouse vs. site delivery',
                'text': (
                    'Where possible, use the supplier as the warehouse (e.g. Home Depot) and get materials delivered '
                    'straight to site instead of staging them at the PPS shop and hauling twice. Ask your mentor '
                    'which trades/vendors currently support this.'
                ),
            },
        ],
        'pps_focus': [
            {
                'title': "Audit one upcoming job's materials plan",
                'text': (
                    'Pick a job in Needs Scheduled or Scheduled. List every material needed, mark each as '
                    '"stock — order at mobilization" or "specialized — order now," and check whether it is already '
                    'ordered. Flag any specialized item that is not yet on order.'
                ),
            },
        ],
        'manager_checkin': (
            'Walk me through a Trade Partner payment request you tagged correctly, and tell me which materials '
            'on your current jobs are stock vs. specialized — and whether the specialized ones are already ordered.'
        ),
    },
    {
        'week': 4,
        'title': 'Callbacks, Warranty & Quality Standard',
        'topic_summary': (
            'Call Backs/Warranty is one of the largest dollar groups on the whole Production Board. '
            'How you handle it — speed, documentation, tone — protects trust as much as the original job did.'
        ),
        'shadowing': [
            'Shadow one callback from first report to close, including the client-facing update if one goes out.',
        ],
        'additional': [
            {
                'title': 'Your role on a callback',
                'text': (
                    'Acknowledge promptly, document with photos before anything else happens, and get it logged in '
                    'Monday with a field owner assigned. No blame language internally or to the client — PPS labor '
                    'vs. manufacturer warranty is a documented distinction, not something to improvise on-site. '
                    '(Keep language aligned with PSC Training ops_callbacks — same story to the client.)'
                ),
            },
            {
                'title': 'PM expectations one-pager',
                'text': (
                    '[TO DOCUMENT] — response-time standard, photo documentation standard, and escalation path '
                    '(Consultant vs. Trey vs. leadership). Draft with Trey and senior PMs before this goes live — '
                    'flagged as high-impact in docs/PM_TRAINING_ROADMAP.md.'
                ),
            },
        ],
        'pps_focus': [
            {
                'title': 'Service recovery draft',
                'text': (
                    'Draft a short client-facing update for a hypothetical warranty callback (schedule TBD, findings '
                    'pending). Mentor coaches tone — proactive, accountable, no over-promising.'
                ),
            },
        ],
        'manager_checkin': (
            'Walk me through a callback from your jobs — what you documented, who you looped in, and how you '
            'closed the loop with the client.'
        ),
    },
]


def _assign_ids(week_data):
    w = week_data['week']
    for i, s in enumerate(week_data.get('shadowing', [])):
        if isinstance(s, str):
            week_data['shadowing'][i] = {'id': f'pm_w{w}_shadow_{i}', 'text': s}
        elif isinstance(s, dict) and 'id' not in s:
            s['id'] = f'pm_w{w}_shadow_{i}'
    for i, a in enumerate(week_data.get('additional', [])):
        if 'id' not in a:
            a['id'] = f'pm_w{w}_additional_{i}'
    for item in week_data.get('pps_focus', []):
        if 'id' not in item:
            slug = item['title'][:24].lower().replace(' ', '_').replace("'", '')
            item['id'] = f'pm_w{w}_focus_{slug}'
    if week_data.get('manager_checkin'):
        week_data['checkin_id'] = f'pm_w{w}_checkin'
    return week_data


@lru_cache(maxsize=1)
def _prepared_pm_curriculum():
    """Same fix as psc_training_data._prepared_curriculum — see the note there.

    `dict(w)` was shallow, so `_assign_ids` replaced shadowing strings with
    dicts inside the module-level PM_TRAINING_WEEKS while merely reading it.
    """
    weeks = [_assign_ids(copy.deepcopy(w)) for w in PM_TRAINING_WEEKS]
    meta = dict(PM_TRAINING_META)
    meta['production_board_reference'] = get_production_board_reference()
    return meta, weeks


def get_pm_training_curriculum():
    """Caller owns the result — deep-copied out of the cache."""
    return copy.deepcopy(_prepared_pm_curriculum())


def get_pm_training_item_ids():
    _, weeks = _prepared_pm_curriculum()
    ids = []
    for week_data in weeks:
        for v in week_data.get('videos', []):
            ids.append(v['id'])
        for s in week_data.get('shadowing', []):
            ids.append(s['id'] if isinstance(s, dict) else s)
        for a in week_data.get('additional', []):
            ids.append(a['id'])
        for f in week_data.get('pps_focus', []):
            ids.append(f['id'])
        if week_data.get('checkin_id'):
            ids.append(week_data['checkin_id'])
    return ids


def count_pm_trackable_items():
    return len(get_pm_training_item_ids())


def get_pm_week_item_ids():
    """Map week number -> list of trainee item IDs for that week."""
    _, weeks = _prepared_pm_curriculum()
    result = {}
    for week_data in weeks:
        w = week_data['week']
        ids = []
        for s in week_data.get('shadowing', []):
            ids.append(s['id'] if isinstance(s, dict) else s)
        for a in week_data.get('additional', []):
            ids.append(a['id'])
        for f in week_data.get('pps_focus', []):
            ids.append(f['id'])
        if week_data.get('checkin_id'):
            ids.append(week_data['checkin_id'])
        result[w] = ids
    return result


def get_pm_week_checkin_questions():
    _, weeks = _prepared_pm_curriculum()
    return {w['week']: (w.get('manager_checkin') or '') for w in weeks}