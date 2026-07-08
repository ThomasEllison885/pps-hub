"""Monday.com & Production Board — operational reference for PPS.

Source: Production Board export (July 2026). Used by PSC Training (ops_monday), PM Training,
Ask PPS seeding, and internal recommendations.

Monday.com is shared across the company — PSCs and PMs both live there, in different ways.
PSC onboarding covers Monday in PSC Training Week 0 (Company Operations — ops_monday).
PM onboarding deep-dives the Production Board in PM Training Week 1.
"""

# How PSC vs PM use Monday.com (PSC Training ops_monday + PM Training Week 1).
MONDAY_AT_PPS = {
    'intro': (
        'Monday.com is not PM-only — PSCs live there too. Everyone uses the same platform; '
        'role determines which boards you work in daily and which columns you own.'
    ),
    'psc_focus': {
        'when': 'Pre-award — prospecting through proposal and client review.',
        'you_own': (
            'Contacts, properties, follow-up dates, outreach log, site visits, proposals sent, '
            'and pipeline stage. Your manager shows you which boards hold your pipeline in Week 0.'
        ),
        'training': 'PSC Training Week 0 — Company Operations module ops_monday (Monday.com at PPS).',
        'hygiene': (
            'Log every meaningful touch in Monday — calls, emails, site visits, proposals. '
            'A CRM is only as good as what you put into it. Weekly cadence with your manager.'
        ),
    },
    'pm_focus': {
        'when': 'Post-award — mobilization through close-out and invoicing.',
        'you_own': (
            'Production Board row: Project Manager, timelines, PPM, Trade Partner fields, Updates, '
            'margins, and status groups (Needs Scheduled → In Progress → Completed - Final).'
        ),
        'training': 'PM Training Week 1 — Production Board deep-dive (this reference).',
        'hygiene': (
            'Start the day on the Production Board. Read Updates before calling anyone. '
            'Post an Update when status or scope changes.'
        ),
    },
    'shared': {
        'updates': (
            'Updates threads on Monday items are shared — PSCs may post on pre-award items; '
            'PMs and office post draws, files, and coordination on Production Board items.'
        ),
        'hub_tools': (
            'Hub outputs feed Monday: Proposal Generator, Site Visit, PPM, and TPS map to '
            'specific Production Board columns at handoff.'
        ),
    },
    'handoff_at_award': (
        'When a job is awarded, it lands on the Production Board. Consultant = PSC who sold it; '
        'Project Manager = who runs field execution. PSC stays the relationship point of contact; '
        'PM owns schedule, Trade Partners, and board hygiene. PSC Training ops_lifecycle traces '
        'this handoff end-to-end.'
    ),
}

PRODUCTION_BOARD_META = {
    'board_name': 'Production Board',
    'platform': 'Monday.com',
    'role': (
        'System of record for every awarded job — people, documents, Trade Partners, '
        'timelines, margins, and status from mobilization through invoicing and close-out.'
    ),
    'source_note': 'Documented from Production Board export, July 2026 (~425 active job rows).',
    'related_sheets': [
        {'name': 'production board', 'purpose': 'Master job record — one row per awarded project'},
        {'name': 'updates', 'purpose': 'Operational thread — draw schedules, file shares, @mentions, coordination'},
        {'name': 'Time tracking', 'purpose': 'Per-job time entries (Started By, dates, duration)'},
    ],
}

# Status groups on the Production Board (top → bottom = typical job progression).
PRODUCTION_BOARD_STATUS_GROUPS = [
    {
        'name': 'Awarded - On Hold',
        'meaning': 'Job is awarded but not yet ready to schedule — missing info, client hold, or pre-mobilization prep.',
        'pm_action': 'Confirm award data is complete; run PPM; assign Trade Partner fields before moving to Needs Scheduled.',
    },
    {
        'name': 'Needs Scheduled',
        'meaning': 'Ready to schedule — PM owns getting a start date with the Trade Partner and client.',
        'pm_action': 'Set Estimated Timeline - Start/End; post an Update with mobilization plan; move to Scheduled when confirmed.',
    },
    {
        'name': 'Scheduled',
        'meaning': 'Start date confirmed — crew/Trade Partner knows when to mobilize.',
        'pm_action': '48-hour notice to property; confirm building access; move to In Progress on mobilization day.',
    },
    {
        'name': 'In Progress',
        'meaning': 'Active field work.',
        'pm_action': 'Post Updates on milestones, issues, and photos; keep Sub Assigned and Sub Contract $ current.',
    },
    {
        'name': 'Call Backs/ Warranty Work',
        'meaning': 'Return visits or warranty items on an otherwise active or recent job.',
        'pm_action': 'Document scope in Updates; link Files; coordinate Trade Partner return.',
    },
    {
        'name': 'Completed Needs Internal Walk',
        'meaning': 'Field work done — internal quality walk before customer walk.',
        'pm_action': 'Complete punch internally; confirm scope matches proposal/PPM.',
    },
    {
        'name': 'Completed Needs Customer Walk',
        'meaning': 'Ready for client walkthrough.',
        'pm_action': 'Schedule walk with property manager; document punch items in Updates.',
    },
    {
        'name': 'ON HOLD - MISSING INFORMATION',
        'meaning': 'Stalled — required board data or documents are missing.',
        'pm_action': 'Identify missing columns (PPM, Sub fields, margins, etc.) and clear before advancing.',
    },
    {
        'name': 'Needs Invoiced - All Information Entered',
        'meaning': 'Close-out complete — all cost/margin fields ready for invoicing.',
        'pm_action': 'Verify Supply Cost, Sub Cost, Overhead Cost, Actual margin $, Margin %, Quarter Invoiced.',
    },
    {
        'name': 'Invoiced - Needs Approved',
        'meaning': 'Invoice sent — awaiting approval/payment.',
        'pm_action': 'Monitor approval; respond to client questions via Updates.',
    },
    {
        'name': 'Waiting on Margins',
        'meaning': 'Job complete or invoiced — margin/cost data still being finalized.',
        'pm_action': 'Backfill financial columns; largest backlog group — prioritize margin entry.',
    },
    {
        'name': 'Completed - Final',
        'meaning': 'Fully closed — financials and close-out done.',
        'pm_action': 'Reference for historical jobs; no active PM work.',
    },
    {
        'name': 'Completed Call Backs',
        'meaning': 'Callback/warranty work fully resolved.',
        'pm_action': 'Archive pattern for warranty close-out.',
    },
]

PRODUCTION_BOARD_COLUMNS = {
    'people': [
        {'name': 'Consultant', 'when': 'Set at award — PSC who sold the job.'},
        {'name': 'Project Manager', 'when': 'Set at award — you own the row once assigned.'},
        {'name': 'Support PM', 'when': 'Optional — second PM on large or complex jobs.'},
    ],
    'identity': [
        {'name': 'Name', 'when': 'Job title on the board — property + scope descriptor.'},
        {'name': 'Proposal Number', 'when': 'Links to Hub proposal (e.g. AP26292). Fill at award.'},
        {'name': 'Trade', 'when': 'Primary trade — Carpentry, Exterior Painting, Roofing, etc.'},
        {'name': 'Company Type', 'when': 'Apartments, Condo, Commercial, etc.'},
        {'name': 'Mgmt Company', 'when': 'Property management company.'},
        {'name': 'VC', 'when': 'Venture/classification when applicable.'},
        {'name': 'City', 'when': 'Job city.'},
        {'name': 'Location', 'when': 'Property or site identifier.'},
        {'name': 'Customer Name', 'when': 'Primary client contact.'},
        {'name': 'Email', 'when': 'Client email for coordination.'},
    ],
    'timeline': [
        {'name': 'Date Awarded', 'when': 'When client awarded the job.'},
        {'name': 'Estimated Timeline - Start', 'when': 'Target mobilization — set in Needs Scheduled.'},
        {'name': 'Estimated Timeline - End', 'when': 'Target completion.'},
        {'name': 'Check in Date', 'when': 'Next PM check-in or follow-up date.'},
    ],
    'hub_documents': [
        {'name': 'Survey', 'when': 'Link to site visit / survey output when used.'},
        {'name': 'PPM', 'when': 'Yes/No + link — Pre-Project Meeting checklist from Hub before mobilization.'},
        {'name': 'Files', 'when': 'Uploaded proposal, scope, or project documents.'},
        {'name': 'monday Doc v2', 'when': 'Monday doc attached to the item when used.'},
    ],
    'financial': [
        {'name': 'Job Size', 'when': 'Sold contract value — fill at award.'},
        {'name': 'Estimated margin %', 'when': 'Expected margin at award or scheduling.'},
        {'name': 'Supply Cost', 'when': 'Material cost — typically at close-out/invoicing.'},
        {'name': 'Sub Cost', 'when': 'Trade Partner cost component.'},
        {'name': 'Overhead Cost', 'when': 'Overhead allocation.'},
        {'name': 'Actual margin $', 'when': 'Realized margin dollars.'},
        {'name': 'Margin %', 'when': 'Realized margin percent.'},
        {'name': 'Quarter Invoiced', 'when': 'Accounting quarter when invoiced.'},
    ],
    'trade_partners': [
        {'name': 'Sold to Sub', 'when': 'Whether work is sold through a Trade Partner (board checkbox).' },
        {'name': 'Sub Contract $', 'when': 'Trade Partner contract amount — aligns with TPS / payout.'},
        {'name': 'Sub Assigned', 'when': 'Trade Partner name assigned to the job.'},
        {'name': 'Sub Compliance', 'when': 'Compliance status for assigned Trade Partner.'},
        {'name': 'Sub Responsible for Material', 'when': 'Whether Trade Partner supplies materials.'},
        {'name': 'link to Pay Request', 'when': 'Link to pay request workflow for Trade Partner payment.'},
    ],
    'other': [
        {'name': 'Subitems', 'when': 'Sub-tasks under the job when used.'},
        {'name': 'Priority', 'when': 'Escalation flag when needed.'},
        {'name': 'Time tracking', 'when': 'Linked time entries for the job.'},
        {'name': 'Item ID (auto generated)', 'when': 'Monday item ID — used in Updates export.'},
    ],
}

# Hub tool → Production Board column mapping.
HUB_TO_PRODUCTION_BOARD = [
    {
        'hub_tool': 'Proposal Generator',
        'monday_fields': ['Proposal Number', 'Files', 'Job Size', 'Trade', 'Company Type', 'Mgmt Company'],
        'timing': 'At award — copy proposal number and attach generated files.',
    },
    {
        'hub_tool': 'Site Visit',
        'monday_fields': ['Survey', 'Files'],
        'timing': 'When site visit report exists — link or attach before/at award.',
    },
    {
        'hub_tool': 'PPM Checklist Generator',
        'monday_fields': ['PPM'],
        'timing': 'After award, before mobilization — set PPM to Yes and attach/link checklist.',
    },
    {
        'hub_tool': 'TPS (Trade Partner Scope)',
        'monday_fields': ['Sub Assigned', 'Sub Contract $', 'Sold to Sub', 'Sub Compliance', 'link to Pay Request'],
        'timing': 'When Trade Partner is assigned — scope doc drives sub fields and payout.',
    },
]

# Recommended morning order of operations for a PM.
PM_MORNING_CHECKLIST = [
    'Open the Production Board in Monday.com.',
    'Filter or sort to your name in Project Manager.',
    'Scan status groups top-down: In Progress → Scheduled → Needs Scheduled → Awarded - On Hold.',
    'For each active job: read recent Updates (draw schedules, client asks, file attachments).',
    'Confirm timeline columns (Estimated Timeline - Start/End) match what you told the client and Trade Partner.',
    'Clear ON HOLD - MISSING INFORMATION items — PPM, Sub Assigned, and Proposal Number are common gaps.',
    'Post at least one Update on any job with movement today (mobilization, delay, punch, invoice).',
]

# Award → mobilization field checklist (proper board language).
AWARD_TO_MOBILIZATION_CHECKLIST = [
    {'field': 'Proposal Number', 'action': 'Enter from Hub proposal — must match awarded scope.'},
    {'field': 'Project Manager', 'action': 'Confirm you are assigned; add Support PM if needed.'},
    {'field': 'Consultant', 'action': 'Verify PSC name matches who sold the job.'},
    {'field': 'Date Awarded', 'action': 'Set award date.'},
    {'field': 'Job Size', 'action': 'Enter sold contract value.'},
    {'field': 'Trade', 'action': 'Confirm primary trade.'},
    {'field': 'Company Type', 'action': 'Apartments, Condo, Commercial, etc.'},
    {'field': 'Mgmt Company', 'action': 'Property management company.'},
    {'field': 'City / Location', 'action': 'Property location for routing.'},
    {'field': 'Customer Name / Email', 'action': 'Primary client contact.'},
    {'field': 'PPM', 'action': 'Generate in Hub → set to Yes → attach/link before mobilization.'},
    {'field': 'Sold to Sub', 'action': 'Check if Trade Partner job.'},
    {'field': 'Sub Assigned', 'action': 'Trade Partner name once selected.'},
    {'field': 'Sub Contract $', 'action': 'Trade Partner contract amount from TPS.'},
    {'field': 'Files', 'action': 'Attach proposal, PPM, TPS, or client-facing docs.'},
    {'field': 'Update', 'action': 'Post mobilization plan, draw schedule, or @mention office as needed.'},
]

# How Updates are used in practice (from export patterns).
UPDATES_GUIDANCE = (
    'The Updates sheet is the operational conversation log — not optional. PSCs, PMs, and office staff '
    'all use Updates on their Monday items. On the Production Board, PMs and office post phase draw '
    'schedules, deposit breakdowns, PDF attachments, insurance packets, and @mentions '
    '(e.g. @Stephanie Whetstone, @Thomas Ellison). When something important happens on a job, '
    'post it on the item Updates thread so the team has one source of truth alongside the columns.'
)

PPS_PRODUCTION_FLOW = (
    'Site visit → Proposal → Review call (never cold-send) → Award → Production Board row → '
    'PPM → TPS → schedule (Needs Scheduled → Scheduled) → In Progress → close-out walks → '
    'invoicing (Needs Invoiced → Invoiced) → margins → Completed - Final'
)


def get_production_board_reference():
    """Return full reference dict for training modules and Ask PPS."""
    return {
        'monday_at_pps': MONDAY_AT_PPS,
        'meta': PRODUCTION_BOARD_META,
        'status_groups': PRODUCTION_BOARD_STATUS_GROUPS,
        'columns': PRODUCTION_BOARD_COLUMNS,
        'hub_mapping': HUB_TO_PRODUCTION_BOARD,
        'pm_morning_checklist': PM_MORNING_CHECKLIST,
        'award_checklist': AWARD_TO_MOBILIZATION_CHECKLIST,
        'updates_guidance': UPDATES_GUIDANCE,
        'production_flow': PPS_PRODUCTION_FLOW,
    }


def production_board_ask_pps_entries():
    """Knowledge seed rows for Ask PPS (production_process / company_operations)."""
    ref = get_production_board_reference()
    groups = '\n'.join(f'- {g["name"]}: {g["meaning"]}' for g in ref['status_groups'][:8])
    groups += '\n- … plus close-out, invoicing, Waiting on Margins, Completed - Final'
    award = '\n'.join(f'- {c["field"]}: {c["action"]}' for c in ref['award_checklist'])
    hub = '\n'.join(
        f'- {m["hub_tool"]} → {", ".join(m["monday_fields"])} ({m["timing"]})'
        for m in ref['hub_mapping']
    )
    morning = '\n'.join(f'- {s}' for s in ref['pm_morning_checklist'])
    cols_people = ', '.join(c['name'] for c in ref['columns']['people'])
    cols_fin = ', '.join(c['name'] for c in ref['columns']['financial'])
    cols_sub = ', '.join(c['name'] for c in ref['columns']['trade_partners'])

    monday = ref['monday_at_pps']
    return [
        {
            'category': 'company_operations',
            'title': 'Monday.com at PPS — PSC and PM roles',
            'content': (
                f'{monday["intro"]}\n\n'
                f'PSC (pre-award): {monday["psc_focus"]["you_own"]} '
                f'Training: {monday["psc_focus"]["training"]}\n\n'
                f'PM (post-award): {monday["pm_focus"]["you_own"]} '
                f'Training: {monday["pm_focus"]["training"]}\n\n'
                f'Handoff at award: {monday["handoff_at_award"]}'
            )[:2400],
        },
        {
            'category': 'production_process',
            'title': 'Production Board — overview & status groups',
            'content': (
                f'{ref["meta"]["role"]}\n\n'
                f'Lifecycle: {ref["production_flow"]}\n\n'
                f'Status groups (order matters):\n{groups}\n\n'
                f'Updates: {ref["updates_guidance"]}'
            )[:2400],
        },
        {
            'category': 'production_process',
            'title': 'Production Board — award to mobilization checklist',
            'content': (
                'When a job is awarded, open or create the Production Board row and complete these fields '
                'using proper Monday column names:\n\n'
                f'{award}\n\n'
                'Move from Awarded - On Hold → Needs Scheduled only when PPM is done and Trade Partner '
                'fields are ready (if applicable).'
            )[:2400],
        },
        {
            'category': 'company_operations',
            'title': 'Production Board — PM morning order of operations',
            'content': (
                'Recommended start-of-day on the Production Board:\n\n'
                f'{morning}'
            )[:1800],
        },
        {
            'category': 'company_operations',
            'title': 'Production Board — columns & Hub tool mapping',
            'content': (
                f'People: {cols_people}\n'
                f'Financial: {cols_fin}\n'
                f'Trade Partners: {cols_sub}\n\n'
                f'Hub tools map to Monday fields:\n{hub}'
            )[:2400],
        },
    ]