"""PSC Onboarding — Property Solutions Consultant training curriculum."""

import copy
from functools import lru_cache

from production_board_reference import MONDAY_AT_PPS

PSC_TRAINING_MANAGER = 'tony_cumella'  # VP Sales — accountability owner for enrolled trainees

PSC_TRAINING_META = {
    'title': 'PSC Onboarding',
    'subtitle': 'Property Solutions Consultant Training Program',
    'description': (
        'A 12-week program (Weeks 0–12) built around judgment, client trust, and proposal craft — not just trade videos. '
        'The Pure Way (Trust · Quality · Results) is the standard behind every decision: commercial multifamily quality, '
        'honest scopes, and work that leads to the next award. '
        'You will partner with an experienced consultant on real projects, learn to evaluate work on site, and use the '
        'Proposal Generator as the system of record for how PPS writes and wins work. '
        'Company operations and Proposal Generator craft run Weeks 0–4 alongside apartment trade depth. '
        'The 4 Disciplines of Execution runs Weeks 9–12. '
        'Enrolled when you start — not tied to any specific past hire.'
    ),
    'duration_weeks': 12,
    'segments': [
        {'name': 'Apartments', 'weeks': [1, 2, 3, 4], 'color': '#004C8C'},
        {'name': 'Condos', 'weeks': [5, 6, 7, 8], 'color': '#0096D6'},
        {'name': 'Hospitality / Commercial', 'weeks': [9, 10, 11, 12], 'color': '#B8922A'},
    ],
}

# The 4 Disciplines of Execution — 2nd edition, revised & updated (© 2012, 2021)
FOUR_DX_CHAPTERS = [
    {'num': 1, 'title': 'The Challenge'},
    {'num': 2, 'title': 'Discipline 1 — Focus on the Wildly Important'},
    {'num': 3, 'title': 'Discipline 2 — Act on the Lead Measures'},
    {'num': 4, 'title': 'Discipline 3 — Keep a Compelling Scoreboard'},
    {'num': 5, 'title': 'Discipline 4 — Create a Cadence of Accountability'},
    {'num': 6, 'title': 'Choosing Where to Focus'},
    {'num': 7, 'title': 'Translating Organizational Focus into Executable Targets'},
    {'num': 8, 'title': 'Getting Your Leaders on Board'},
    {'num': 9, 'title': 'Leader of Leaders'},
    {'num': 10, 'title': 'Installing 4DX'},
    {'num': 11, 'title': 'Engaging the Organization'},
    {'num': 12, 'title': 'Sustaining the Results'},
    {'num': 13, 'title': 'Case Studies — Winning with 4DX'},
    {'num': 14, 'title': 'Case Studies — Marriott & Comcast'},
    {'num': 15, 'title': 'Applying 4DX to Your Life'},
]

# 4DX chapter slices for weeks 9–12 (full book over four weeks — densest reading segment)
FOUR_DX_WEEKLY = [
    {
        'chapters': FOUR_DX_CHAPTERS[0:4],
        'discussion': 'Discuss: What is the whirlwind in your role? What would a first WIG look like?',
        'reading_note': (
            '4DX is the hardest read in the program — go slowly. Week 9 covers the four core disciplines (Ch 1–4). '
            'Take notes; re-read any chapter that does not land on the first pass.'
        ),
    },
    {
        'chapters': FOUR_DX_CHAPTERS[4:7],
        'discussion': 'Discuss: How do you choose where to focus when everything feels urgent?',
        'reading_note': (
            'Continue 4DX (Ch 5–7). These chapters bridge personal execution to organizational focus. '
            'Schedule two reading blocks this week — this material rewards re-reading.'
        ),
    },
    {
        'chapters': FOUR_DX_CHAPTERS[7:11],
        'discussion': 'Discuss: Who are your leaders of leaders at PPS? What does installing 4DX look like on a team?',
        'reading_note': (
            'Hardest 4DX section (Ch 8–11): leader alignment, installation, and engagement. '
            'Budget extra time; do a mid-week check-in with your manager on what you are retaining.'
        ),
    },
    {
        'chapters': FOUR_DX_CHAPTERS[11:15],
        'discussion': 'Finish the book. Present your 90-day WIG, lead measures, and scoreboard in graduation review.',
        'reading_note': (
            'Finish 4DX (Ch 12–15): sustaining results, case studies, and personal application. '
            'Connect every chapter to your first 90 days as a PSC.'
        ),
    },
]

PSC_CORE_VALUES = {
    'title': 'Mission, Values & PPS Voice',
    'intro': (
        'Start with the PSC role, The Pure Way, then values and voice. This is training, not a document to memorize. '
        'Work through each activity before your first client-facing assignment. The Proposal Generator applies PPS voice; '
        'these exercises teach you how to evaluate projects, communicate with every stakeholder, and represent PPS on site. '
        'Trust · Quality · Results is a through-line for judgment — not a slogan to paste into every conversation.'
    ),
    'sections': [
        {
            'id': 'cv_psc_role',
            'title': 'The PSC Role — Purpose & Mindset',
            'content': (
                'A Property Solutions Consultant drives revenue by earning awarded contracts through trusted relationships '
                'with every stakeholder on a project — property manager, board, PM, Trade Partners, and residents or homeowners. '
                'Sales are the measurable outcome; trust is what earns them. Construction knowledge deepens over time; '
                'judgment, ownership, professionalism, and communication establish trust from day one.'
            ),
            'activities': [
                {
                    'id': 'cv_psc_role_stakeholders',
                    'title': 'Map your stakeholders',
                    'text': (
                        'For apartment, condo, and one hospitality or commercial account you will touch, list who approves work, '
                        'who manages day-to-day, and who is affected by the work. Note what each group cares about most. '
                        'Review with your manager.'
                    ),
                },
                {
                    'id': 'cv_psc_role_advocacy',
                    'title': 'Client advocacy vs. protecting PPS',
                    'text': (
                        'Write two sentences: how you advocate for the client without over-promising scope, schedule, or price '
                        'that production has not confirmed. Share examples your manager has seen go well — and go wrong.'
                    ),
                },
                {
                    'id': 'cv_psc_role_ownership',
                    'title': 'Ownership in everyday situations',
                    'text': (
                        'Describe what exceptional ownership looks like on: a delayed mobilization, a resident complaint, '
                        'and a scope question you cannot answer on site. Your manager coaches tone and escalation — not scripts.'
                    ),
                },
            ],
        },
        {
            'id': 'cv_pure_way',
            'title': 'The Pure Way — Trust · Quality · Results',
            'content': (
                'The Pure Way is how we decide, not a phrase we force into every sentence. '
                'Tagline on formal proposals and footers only (Trust. Quality. Results.™). '
                'Day to day: commercial multifamily / cap-ex standard — professional, durable, clean — not luxury residential finish. '
                'TRUST — do what you said; honest include/exclude; no dates production has not confirmed; '
                '48-hour notice; stop work, photo, written approval on extras. '
                'QUALITY — right prep and systems for the trade; daily cleanup; punch before invoice. '
                'RESULTS — jobs finish, get paid, and earn the next award (clear small scopes often open CapEx). '
                'Brand line for credentials: Improving People. Improving Property.'
            ),
            'activities': [
                {
                    'id': 'cv_pure_way_map',
                    'title': 'Map one job to Pure Way',
                    'text': (
                        'Pick a live or recent partner-project job. Write one bullet each: how we built trust with the client, '
                        'what quality looked like on site (commercial standard), and what result we needed (close, invoice, next work). '
                        'Review with your manager — challenge fluff.'
                    ),
                },
                {
                    'id': 'cv_pure_way_tradeoff',
                    'title': 'Commercial quality vs luxury',
                    'text': (
                        'In one short paragraph, explain to a property manager what "high quality" means at PPS for exterior paint '
                        'or roofing without promising custom-home millwork. Manager signs off that your bar is commercial and clear.'
                    ),
                },
                {
                    'id': 'cv_pure_way_breach',
                    'title': 'When Pure Way is broken',
                    'text': (
                        'List three field behaviors that break trust, quality, or results (e.g. invoice before punch, vague excludes, '
                        'promised start date with no PM). For each, write the Pure Way replacement behavior.'
                    ),
                },
            ],
        },
        {
            'id': 'cv_mission',
            'title': 'PPS Mission',
            'content': (
                'We believe in elevating lives and spaces through relentless improvement and unbreakable trust.'
            ),
            'activities': [
                {
                    'id': 'cv_mission_reflect',
                    'title': 'Mission in your own words',
                    'text': (
                        'In 3–4 sentences, explain what this mission looks like on a real project — '
                        'for residents, property staff, and ownership. Share with your manager in Week 0.'
                    ),
                },
                {
                    'id': 'cv_mission_site',
                    'title': 'Mission on a walkthrough',
                    'text': (
                        'On your first ride-along, note one moment where PPS elevated the experience '
                        '(communication, cleanliness, professionalism, or problem-solving). Write it down.'
                    ),
                },
            ],
        },
        {
            'id': 'cv_resourcefulness',
            'title': 'Resourcefulness',
            'content': (
                'We have a figure-it-out mentality. Obstacles are normal — waiting for perfect conditions '
                'is not the PPS way. Use the tools, ask the right person, and keep the work moving.'
            ),
            'activities': [
                {
                    'id': 'cv_resource_hub',
                    'title': 'Know your toolkit',
                    'text': (
                        'Open the PPS Hub and identify where you will: generate proposals, run a PPM, '
                        'build Trade Partner Scope, and log site visits. Ask your manager which you will use first.'
                    ),
                },
                {
                    'id': 'cv_resource_scenario',
                    'title': 'Figure-it-out scenario',
                    'text': (
                        'Scenario: A property manager needs a scope answer today, your PM is on another site, '
                        'and production has not confirmed crew dates. Write your next three moves before escalating. '
                        'Review with your manager.'
                    ),
                },
                {
                    'id': 'cv_resource_blocker',
                    'title': 'Remove one blocker',
                    'text': (
                        'In Week 0 or 1, identify something you do not know yet (a trade term, a client contact '
                        'workflow, a hub feature) and resolve it yourself — documentation, a teammate, or a tool — '
                        'before asking your manager to solve it for you.'
                    ),
                },
            ],
        },
        {
            'id': 'cv_integrity',
            'title': 'Integrity',
            'content': (
                'Your professional judgment has to hold up in any room — with a client, a Trade Partner, '
                'or a teammate. If you would not stand behind a scope call, timeline, or price in a direct '
                'conversation, do not commit to it privately.'
            ),
            'activities': [
                {
                    'id': 'cv_integrity_scope',
                    'title': 'Scope you would sign',
                    'text': (
                        'Pull any proposal from hub history. Find one scope line you would put your name on '
                        'and one that still needs refinement. Be ready to explain the difference to your manager.'
                    ),
                },
                {
                    'id': 'cv_integrity_concealed',
                    'title': 'Concealed conditions drill',
                    'text': (
                        'Role-play with your manager: on site you find rot behind siding that was not in scope. '
                        'Walk through exactly what PPS does before any extra work starts — words, photos, approvals.'
                    ),
                },
                {
                    'id': 'cv_integrity_promise',
                    'title': 'No promises production has not confirmed',
                    'text': (
                        'List three things a PSC must never promise a client without PM or production sign-off '
                        '(schedule, pricing beyond proposal, scope not in writing). Check with your manager.'
                    ),
                },
            ],
        },
        {
            'id': 'cv_loyalty',
            'title': 'Loyalty & Teamwork',
            'content': (
                'We look out for each other. Share what you learn, surface problems early, and back up '
                'the team on site and in client communication.'
            ),
            'activities': [
                {
                    'id': 'cv_loyalty_escalation',
                    'title': 'Build your escalation map',
                    'text': (
                        'Document who you go to for: production questions, pricing help, client complaints, '
                        'and urgent site issues. Confirm the list with your manager and save it in Monday.com.'
                    ),
                },
                {
                    'id': 'cv_loyalty_handoff',
                    'title': 'Clean handoffs',
                    'text': (
                        'After shadowing, write a 3-bullet handoff you would leave for the next person on that '
                        'account — open items, client preferences, and what still needs follow-up.'
                    ),
                },
                {
                    'id': 'cv_loyalty_habit',
                    'title': 'Weekly team habit',
                    'text': (
                        'Commit to one recurring habit for your first 90 days: share a site learning in team chat, '
                        'cover a follow-up for a busy teammate, or flag a risk before it becomes a client problem.'
                    ),
                },
            ],
        },
        {
            'id': 'cv_voice_practice',
            'title': 'PPS Voice — Learn by Doing',
            'content': (
                'PPS voice is confident, direct, and outcome-focused. The Proposal Generator applies the '
                'voice guide automatically — your job is to recognize good PPS language and refine it for each client.'
            ),
            'activities': [
                {
                    'id': 'cv_voice_generate',
                    'title': 'First practice proposal',
                    'text': (
                        'Generate a practice apartment proposal in the Proposal Generator (do not send). '
                        'Highlight five phrases that sound distinctly PPS vs. a generic contractor. '
                        'Discuss with your manager.'
                    ),
                },
                {
                    'id': 'cv_voice_rewrite',
                    'title': 'Rewrite drill',
                    'text': (
                        'Rewrite these three lines in PPS voice and share with your manager:\n'
                        '1. "We are pleased to present the following scope of work."\n'
                        '2. "The owner will be responsible for selecting paint colors."\n'
                        '3. "Hidden damage may be discovered during the project."'
                    ),
                },
                {
                    'id': 'cv_voice_vault',
                    'title': 'Approved proposal scavenger hunt',
                    'text': (
                        'From hub history, find an approved proposal and locate: the universal opening, '
                        'one resident-disruption phrase, and one concealed-conditions or T&M phrase. '
                        'Explain why each is there.'
                    ),
                },
            ],
        },
        {
            'id': 'cv_voice_property',
            'title': 'PPS Voice — Property Type Practice',
            'content': (
                'The same scope reads differently by property type. Apartments need operational precision; '
                'condos need board-ready trust-building. Hospitality and commercial prioritize continuity and brand.'
            ),
            'activities': [
                {
                    'id': 'cv_voice_apartment_condo',
                    'title': 'Apartment vs. condo openings',
                    'text': (
                        'Your manager gives you the same exterior scope for an apartment community and a condo HOA. '
                        'Write 2–3 opening sentences for each — tone and audience should clearly differ. Review together.'
                    ),
                },
                {
                    'id': 'cv_voice_audience',
                    'title': 'Name the decision-maker',
                    'text': (
                        'For each property type you will sell (apartment, condo, hospitality/commercial), write one '
                        'sentence: who approves the work day-to-day, who signs the contract, and what they care about most.'
                    ),
                },
                {
                    'id': 'cv_voice_diff',
                    'title': 'Proposal Comparison habit',
                    'text': (
                        'After your first real proposal edit, run the original and your version through the '
                        'Proposal Comparison Tool on the dashboard. Submit one voice improvement the guide should capture.'
                    ),
                },
            ],
        },
    ],
}

PSC_SALES_TRAINING = {
    'title': 'PPS Sales Training',
    'intro': (
        'PPS wins work through relationships and communication as much as scope quality. Use this section alongside '
        'weekly trade training — especially prospecting weeks 5–8. Your manager assigns modules based on what you need; '
        'prioritize communication and judgment modules in your first 90 days.'
    ),
    'modules': [
        {
            'id': 'sales_communication',
            'title': 'Communication, Judgment & Difficult Conversations',
            'items': [
                {
                    'id': 'sales_comm_proactive',
                    'title': 'Proactive communication standard',
                    'text': (
                        'Clients remember how they were communicated with as much as the finished work. '
                        'List the touchpoints you owe on an active job: proposal follow-up, award, mobilization notice, '
                        'mid-project updates, and close-out. Confirm cadence with your manager and Monday.com.'
                    ),
                },
                {
                    'id': 'sales_comm_stakeholders',
                    'title': 'Different audiences, different messages',
                    'text': (
                        'Same project update — write one sentence for the property manager, one for a condo board context, '
                        'and one internal note for your PM. Tone and detail should match who needs what.'
                    ),
                },
                {
                    'id': 'sales_comm_difficult',
                    'title': 'Difficult conversation drills',
                    'text': (
                        'Role-play with your manager: schedule delay, concealed conditions, change order, and callback. '
                        'Focus on listening first, documenting, and who you loop in before committing.'
                    ),
                },
                {
                    'id': 'sales_comm_uncertainty',
                    'title': 'Reduce uncertainty',
                    'text': (
                        'Your value is not only estimating — it is aligning expectations and being a reliable point of contact. '
                        'After shadowing, note one moment where clear communication prevented a problem. Write what you would do differently.'
                    ),
                },
            ],
        },
        {
            'id': 'sales_pipeline',
            'title': 'Pipeline & Prospecting',
            'items': [
                {
                    'id': 'sales_pipe_1',
                    'title': 'Know your numbers',
                    'text': 'Track outreach attempts, conversations, site visits, proposals sent, and close rate in Monday.com. You cannot improve what you do not measure.',
                },
                {
                    'id': 'sales_pipe_2',
                    'title': 'Protect golden hours',
                    'text': 'Block dedicated prospecting time on your calendar. Treat it like a client appointment — non-negotiable.',
                },
                {
                    'id': 'sales_pipe_3',
                    'title': 'Balanced prospecting mix',
                    'text': 'Use phone, email, in-person, and social touchpoints. No single channel fills a pipeline alone.',
                },
                {
                    'id': 'sales_pipe_4',
                    'title': 'Own your database',
                    'text': 'Every contact, property, and follow-up date lives in Monday.com. A CRM is only as good as what you put into it.',
                },
                {
                    'id': 'sales_pipe_5',
                    'title': 'One-time hits vs. real commercial',
                    'text': (
                        'A one-time job with no next job — small residential-style work, a single old contact reaching out — '
                        'is not worth chasing if it is small dollar and high-effort-to-standard. Past hotels, senior living, '
                        'and real commercial relationships are worth pursuing even if new. Test: is there a next job here, '
                        'or is this the only one?'
                    ),
                },
            ],
        },
        {
            'id': 'sales_property',
            'title': 'Selling by Property Type',
            'items': [
                {
                    'id': 'sales_prop_1',
                    'title': 'Apartment communities',
                    'text': 'Sell to the property manager day-to-day; ownership/regional approves. Lead with operational confidence: phasing, resident communication, single point of contact.',
                },
                {
                    'id': 'sales_prop_2',
                    'title': 'Condos & HOAs',
                    'text': 'The property manager presents; the Board votes. Your proposal is a relationship document. Explain WHY, connect scope to homeowner value, offer to attend a board meeting.',
                },
                {
                    'id': 'sales_prop_3',
                    'title': 'Hospitality & commercial',
                    'text': 'Lead with business continuity and brand standards. Address work-hour restrictions, phasing around guests or tenants, and after-hours options.',
                },
            ],
        },
        {
            'id': 'sales_proposal',
            'title': 'The Proposal as a Sales Tool',
            'items': [
                {
                    'id': 'sales_prop_tool_1',
                    'title': 'Generator first — then judgment',
                    'text': (
                        'Complete Company Operations → Proposal Generator Craft. Use the generator for every live proposal '
                        'unless your manager approves an exception. Craft lives in your form inputs; polish in Word.'
                    ),
                },
                {
                    'id': 'sales_prop_tool_2',
                    'title': 'Scope to investment',
                    'text': (
                        'Help clients see scope as protecting their asset — not just a line-item cost. '
                        'Use investment language and deferred-risk framing on condo work; clinical operational framing on apartments.'
                    ),
                },
                {
                    'id': 'sales_prop_tool_3',
                    'title': 'Walk the client through it',
                    'text': (
                        'Never email a proposal cold without context. Schedule a review call or meeting. '
                        'Highlight issue → outcome, what is excluded, investment, and what happens at mobilization (PPM).'
                    ),
                },
                {
                    'id': 'sales_prop_tool_4',
                    'title': 'Earn trust scopes → CapEx',
                    'text': (
                        'Identify one small, clear scope that builds trust with a target account (concrete, soffit, single deck, '
                        'gutter repair). Document how you will use it to open larger CapEx — without over-promising the big job early.'
                    ),
                },
                {
                    'id': 'sales_prop_tool_5',
                    'title': 'Comparison feeds the company',
                    'text': (
                        'After your first real client proposal edit, run Proposal Comparison. '
                        'One submitted improvement is required before you are cleared for independent proposals.'
                    ),
                },
                {
                    'id': 'sales_prop_tool_6',
                    'title': 'The comprehensive path — the harder proposal',
                    'text': (
                        'Build one full Comprehensive-template proposal (not Standard) end to end for a real or practice '
                        'commercial/large-scope job. Comprehensive proposals need more PPS-story and credentialing language '
                        'than Standard ones — get Tony to review this one specifically before you are cleared to send a '
                        'comprehensive proposal to a client solo.'
                    ),
                },
            ],
        },
        {
            'id': 'sales_objections',
            'title': 'Objections & Difficult Conversations',
            'items': [
                {
                    'id': 'sales_obj_1',
                    'title': 'Price objections',
                    'text': 'Acknowledge, reframe to scope quality and risk reduction, compare apples-to-apples. PPS pricing reflects resident-aware execution and long-term Trade Partner relationships.',
                },
                {
                    'id': 'sales_obj_2',
                    'title': 'Complaints & resident issues',
                    'text': 'Listen first. Document. Coordinate through property management. Never dismiss a resident concern — escalate to your PM immediately.',
                },
                {
                    'id': 'sales_obj_3',
                    'title': 'Gatekeepers & brush-offs',
                    'text': 'Be respectful, persistent, and concise. Ask for the right person. Follow up on a schedule, not when you "get around to it."',
                },
                {
                    'id': 'sales_obj_4',
                    'title': 'Bid-platform Q&A visibility',
                    'text': (
                        "On platforms like Vayner/Morgan's bidding system, any question you ask in the platform is often "
                        'visible to every invited bidder — that is by design, so all bidders answer the same RFP. Be '
                        'thoughtful about what you reveal in a platform question; call the property contact directly for '
                        'anything you do not want competitors to see.'
                    ),
                },
            ],
        },
        {
            'id': 'sales_relationship',
            'title': 'Relationships & Follow-Through',
            'items': [
                {
                    'id': 'sales_rel_1',
                    'title': 'Law of familiarity',
                    'text': 'Consistent, professional touchpoints build trust before you need it. Show up on site. Send useful updates. Be the consultant they think of first.',
                },
                {
                    'id': 'sales_rel_2',
                    'title': 'Post-award handoff',
                    'text': 'A signed proposal is the start, not the finish. Ensure PPM happens, PM intro is smooth, and the client hears from you during mobilization.',
                },
                {
                    'id': 'sales_rel_3',
                    'title': 'Trade Partner relationships',
                    'text': 'Understand how PPS works with Trade Partners. Never promise scope or schedule that production has not confirmed.',
                },
            ],
        },
    ],
}

# PPS Company Operations — manager-led 1:1 modules (SOP placeholders until ops capture sessions)
PSC_COMPANY_OPERATIONS = {
    'title': 'PPS Company Operations',
    'intro': (
        'How PPS actually runs — not generic construction knowledge. Weeks 0–3 pair you with an experienced consultant '
        'on real projects while you complete these modules with your manager. Each module has SOP bullets (many still '
        'being captured from the field), a required manager 1:1, and hands-on exercises. '
        'Training develops judgment and confidence — not just information transfer. '
        'Company standard (2026-08): awarded jobs use a PSC + PM + Trade Partner three-way text chain — see Trade Partners module.'
    ),
    'draft_note': (
        'SOP sections marked [TO DOCUMENT] are gaps we are filling through Ask PPS and manager capture sessions. '
        'Field reality may differ from leadership intent — document what actually happens. '
        'Three-way text chain SOP captured from Sales Meeting 2026-08-10 (Andy/Adam/Tony/Thomas/Rachel).'
    ),
    'modules': [
        {
            'id': 'ops_partner_projects',
            'title': 'Partner-Project Onboarding (5–10 Projects)',
            'assigned_week': 0,
            'summary': (
                'New PSCs learn fastest by partnering with an experienced consultant on 5–10 complete projects — '
                'from opportunity through close-out — with responsibility shifting gradually from observation to participation '
                'to independent execution with coaching.'
            ),
            'sop_placeholders': [
                'Mentor consultant assigned by VP Sales; project mix includes apartment and condo if possible',
                'Progressive ownership: observe → participate → lead with manager/mentor coaching at each stage',
                'Exposure required: opportunity, discovery, site visit, estimate/proposal, award, PPM, mobilization, '
                'active job, change orders, callbacks, punch/close-out',
                'Post-project debrief after each partner project — lessons learned and decision-making review',
                '[TO DOCUMENT] When is a new PSC ready for solo client work?',
            ],
            'manager_1on1': (
                '45-minute kickoff: name your mentor consultant, list the first 3–5 partner projects in Monday.com, '
                'and agree how you will track observation vs. participation on each.'
            ),
            'items': [
                {
                    'id': 'ops_partner_kickoff',
                    'title': 'Partner-project kickoff',
                    'text': 'Meet your mentor consultant. Confirm which active or upcoming jobs you will join and your role on each.',
                },
                {
                    'id': 'ops_partner_log',
                    'title': 'Partner-project log',
                    'text': (
                        'Start a simple log (Monday.com or notes): project name, stage you observed, what you owned, '
                        'one judgment call you watched, and one question for debrief.'
                    ),
                },
                {
                    'id': 'ops_partner_debrief',
                    'title': 'First project debrief',
                    'text': (
                        'After your first partner project milestone (site visit, proposal, or mobilization), '
                        '30-minute debrief with mentor + manager: what would you do differently alone?'
                    ),
                },
            ],
        },
        {
            'id': 'ops_monday',
            'title': 'Monday.com at PPS',
            'assigned_week': 0,
            'summary': (
                'Monday.com is shared — PSCs and PMs both live there, in different ways. '
                'As a PSC you own pre-award pipeline: contacts, properties, follow-up, site visits, and proposals. '
                'After award, jobs live on the Production Board (PM-led) where you appear as Consultant. '
                'Not a generic Monday tutorial — learn PPS boards and column names with your manager.'
            ),
            'sop_placeholders': [
                MONDAY_AT_PPS['intro'],
                (
                    'PSC boards (your manager shows in 1:1): pipeline, contacts, properties, follow-up dates — '
                    'log every meaningful touch before award.'
                ),
                (
                    'Production Board (post-award): system of record for awarded jobs — Proposal Number, '
                    'Consultant, Project Manager, Job Size, PPM, Trade Partner fields, status groups, Updates. '
                    'See docs/PRODUCTION_BOARD_REFERENCE.md.'
                ),
                MONDAY_AT_PPS['handoff_at_award'],
                '[TO DOCUMENT] How do we name properties, contacts, and deals in Monday?',
                MONDAY_AT_PPS['psc_focus']['hygiene'],
            ],
            'manager_1on1': (
                '60-minute screen share: walk your PSC pipeline boards and preview the Production Board. '
                'Update one real or test contact/property/follow-up. Confirm where your pipeline lives, '
                'what happens at award (Consultant on Production Board row), and your weekly CRM cadence.'
            ),
            'items': [
                {
                    'id': 'ops_monday_read',
                    'title': 'Review Monday.com SOP',
                    'text': (
                        'Read the SOP bullets above — especially PSC vs PM ownership and the award handoff. '
                        'Write three questions for your manager 1:1 (pipeline boards, Production Board, Updates).'
                    ),
                },
                {
                    'id': 'ops_monday_1on1',
                    'title': 'Manager 1:1 — Monday.com walkthrough',
                    'text': (
                        'Complete the screen-share: your pipeline boards plus a look at Production Board columns '
                        '(Consultant, Proposal Number, status groups). Manager confirms boards and update cadence.'
                    ),
                },
                {
                    'id': 'ops_monday_practice',
                    'title': 'Hands-on — update Monday.com',
                    'text': 'Add or update one contact, property, or follow-up date on your pipeline. Show your manager before checking off.',
                },
                {
                    'id': 'ops_monday_award_handoff',
                    'title': 'Trace award → Production Board',
                    'text': (
                        'With your manager, open one recently awarded job on the Production Board. '
                        'Find Consultant (PSC), Project Manager, Proposal Number, and Date Awarded. '
                        'Note what the PSC logged pre-award vs what the PM owns post-award. '
                        'Pair with Project Lifecycle (ops_lifecycle) module.'
                    ),
                },
            ],
        },
        {
            'id': 'ops_lifecycle',
            'title': 'Project Lifecycle at PPS',
            'assigned_week': 0,
            'summary': (
                'End-to-end flow from first client conversation through close-out — opportunity, discovery, site visit, '
                'proposal, award, PPM, mobilization, production, change orders, callbacks, and punch/close-out. '
                'Know where the PSC leads vs. supports the PM at each stage.'
            ),
            'sop_placeholders': [
                'Opportunity & discovery → site visit → scope capture → proposal → client review conversation (never cold-send)',
                'Award → PPM → mobilization → active job — PSC stays the relationship point of contact',
                (
                    'At award + ready to schedule: start PSC + PM + Trade Partner three-way text for that job '
                    '(see Trade Partners module). All field Q&A, photos, delays live there until punch/pay.'
                ),
                'Change orders: cease/document/approve in writing before extra work; PSC coordinates client, PM owns field',
                'Punch list and close-out walkthrough — who attends, what gets documented',
                'PSC leads: relationship, scope narrative, client communication, site visit quality',
                'PM/production lead: crew schedule, Trade Partner coordination, field execution',
                '[TO DOCUMENT] At close-out, how do callbacks and warranty hand off?',
            ],
            'manager_1on1': (
                '45-minute session: trace one real job on Monday.com and in Hub history from site visit to '
                'current status. You narrate the stages; manager corrects gaps.'
            ),
            'items': [
                {
                    'id': 'ops_lifecycle_read',
                    'title': 'Review project lifecycle SOP',
                    'text': 'Read the SOP bullets. Sketch the lifecycle in your own words before the 1:1.',
                },
                {
                    'id': 'ops_lifecycle_1on1',
                    'title': 'Manager 1:1 — trace a real project',
                    'text': 'Walk one live or recent job end-to-end with your manager. Note where you would have been stuck alone.',
                },
                {
                    'id': 'ops_lifecycle_map',
                    'title': 'Draw your lifecycle map',
                    'text': (
                        'After the 1:1, write the lifecycle in 8–10 steps. Mark where PSC leads vs. supports. '
                        'Share with your manager.'
                    ),
                },
            ],
        },
        {
            'id': 'ops_project_evaluation',
            'title': 'Project Evaluation & Scope Development',
            'assigned_week': 1,
            'summary': (
                'The Hub standardizes proposal output; your job is judgment — identify the real issue, understand client objectives, '
                'surface unknown conditions, and develop the right scope before you generate a proposal.'
            ),
            'sop_placeholders': [
                'Define the existing problem before proposing a solution — observations, photos, measurements, questions',
                'Document unknown conditions and assumptions; use concealed-condition language when appropriate',
                'Scope decisions: what is in, what is excluded, alternatives (e.g. one coat vs. two), who supplies materials',
                'Proposal review = coaching on decision-making, not just formatting',
                'Hub Proposal Generator + estimators + Scope Library — tools apply after evaluation is sound',
                '[TO DOCUMENT] Site visit checklist by main trade — what must you capture?',
            ],
            'manager_1on1': (
                '60-minute session: walk a recent site visit or hub proposal. Manager narrates how they identified the issue, '
                'what they chose to exclude, and what they would not price without PM input.'
            ),
            'items': [
                {
                    'id': 'ops_eval_issue_first',
                    'title': 'Issue before solution',
                    'text': (
                        'On a partner-project site visit, write: what is failing, why it matters to the client, '
                        'and what you still do not know. Do not scope until your manager reviews.'
                    ),
                },
                {
                    'id': 'ops_eval_unknowns',
                    'title': 'Unknown conditions log',
                    'text': (
                        'List three unknowns you would flag on a real property (access, concealed damage, phasing). '
                        'Draft how you would communicate each without over-promising.'
                    ),
                },
                {
                    'id': 'ops_eval_review',
                    'title': 'Proposal review as coaching',
                    'text': (
                        'Review a hub proposal with your manager — for each major scope section, explain the reasoning '
                        '(not just the line item). Note one assumption you would challenge.'
                    ),
                },
            ],
        },
        {
            'id': 'ops_estimating',
            'title': 'How PPS Estimates & Pricing',
            'assigned_week': 1,
            'summary': (
                'You do not need to be a production estimator — but you must know how pricing is built, what information '
                'PMs need from your site visit, and how complexity, mobilization, risk, and Trade Partner input affect the number.'
            ),
            'sop_placeholders': [
                'Site visit capture: photos, measurements, failure modes, access, phasing, resident impact',
                'Hub tools by trade: Proposal Generator, trade estimators, Trade Partner Scope',
                'PSC gathers information and defines scope; PM/production builds production pricing with Trade Partner input',
                'Escalate scope uncertainty before the client sees a proposal',
                'Hub pricing defaults are starting points — final numbers confirmed with Tony/PM for context',
                'Quality bar: proposal reviewed in conversation with client; PPS voice; no unconfirmed schedule promises',
                '[TO DOCUMENT] Where do we look up typical unit costs by trade?',
            ],
            'manager_1on1': (
                '60-minute session: open a recent estimate or proposal in Hub history. Manager narrates every '
                'decision from site notes to final numbers. You take notes.'
            ),
            'items': [
                {
                    'id': 'ops_estimating_read',
                    'title': 'Review estimating SOP',
                    'text': 'Read the SOP bullets. List which Hub tools you will use first in your role.',
                },
                {
                    'id': 'ops_estimating_1on1',
                    'title': 'Manager 1:1 — estimate walkthrough',
                    'text': 'Debrief one real estimate with your manager same week. Identify three inputs you would have missed.',
                },
                {
                    'id': 'ops_estimating_proposal',
                    'title': 'Hands-on — read a hub proposal',
                    'text': (
                        'Find a recent proposal in hub history. Identify scope language, unit counts, '
                        'investment framing, and warranty terms. Be ready to explain how scope became a proposal.'
                    ),
                },
            ],
        },
        {
            'id': 'ops_proposal_generator',
            'title': 'Proposal Generator Craft (New Standard)',
            'assigned_week': 1,
            'summary': (
                'The Proposal Generator is the new standard for how PPS writes proposals — not freeform Word from a '
                'copied old file. You still own judgment: what is failing, what is in/out of scope, pricing mode, '
                'and field notes. The tool owns company voice, structure, terms, and consistency. '
                'Goal: a document a PM can sell to a Trade Partner and a client can sign without rewriting the whole scope. '
                'Pure Way through-line: honest scopes (trust), commercial quality language (quality), clear path to award (results).'
            ),
            'sop_placeholders': [
                'Old Way = copy past Word; New Way = Hub form + Claude PPS voice + named Word styles + vault + proposal number',
                'Consultant owns: client, property type, issue/outcome, trade details, scope notes, site observations, pricing mode/lines, warranties',
                'Tool owns: PPS voice, active "PPS will…", short vs comprehensive structure, terms, Investment Summary, optional Site Observations rewrite',
                'Short template = default most jobs; Comprehensive = typically $100k+ or relationship/board-heavy wins (Why PPS pillars)',
                'Material responsibility: PPS supplies / owner supplies / unspecified — must match opening labor-materials language',
                'Pricing modes: fixed total, multi-option (do not sum options), open/T&M (service call + rates, no fake fixed total)',
                'Scope notes must feed include/exclude, unit rates (e.g. decking per sheet), T&M thresholds, access, 48-hour notice',
                'Site observations: raw field notes only; tool rewrites — never invent findings; leave blank to omit section',
                'Always review live with client — never cold-send; edit in Word then run Proposal Comparison',
                'Production-ready test: can a PM who never walked the site sell this to a Trade Partner?',
                'Number format {INITIALS}{YY}{XXX} from Hub sequence; U/U2 culture = regenerate or save revised vault copy thoughtfully',
            ],
            'manager_1on1': (
                '75-minute session: open Proposal Generator together. Walk short vs comprehensive, goals on/off, '
                'one fixed-price job and one multi-option or T&M example. Generate a practice proposal from real field notes '
                '(do not send). Manager grades: judgment in the form fields, not pretty Word alone.'
            ),
            'items': [
                {
                    'id': 'ops_pg_old_vs_new',
                    'title': 'Old Way vs New Way',
                    'text': (
                        'Write five bullets: what the old copy-paste Word process did well, and five the generator improves '
                        '(voice, speed, vault, numbers, training). Note one craft skill you still must bring from the field. '
                        'Review with your manager.'
                    ),
                },
                {
                    'id': 'ops_pg_form_map',
                    'title': 'Map the seven form steps',
                    'text': (
                        'Open Proposal Generator (do not send). List each step 1–7 in your own words and who the input protects '
                        '(client, production, you). Screenshot or note where property type and template type live.'
                    ),
                },
                {
                    'id': 'ops_pg_short_vs_full',
                    'title': 'Short vs comprehensive',
                    'text': (
                        'With your manager, decide template for: (a) $4k concrete walk, (b) $45k hallway package, '
                        '(c) $150k multi-building paint, (d) condo board CapEx. Write one sentence why for each. '
                        'Remember: Comprehensive adds Why PPS (including Trust. Quality. Results.™ as a pillar) — not for every job.'
                    ),
                },
                {
                    'id': 'ops_pg_issue_outcome',
                    'title': 'Issue → outcome (Goals)',
                    'text': (
                        'On a partner project, draft Existing Issue and Intended Outcome before opening the generator. '
                        'Issue = what is failing / risk. Outcome = end state only (no "we will supply materials" in outcome). '
                        'Manager edits once for commercial clarity.'
                    ),
                },
                {
                    'id': 'ops_pg_scope_notes',
                    'title': 'Scope notes that production can use',
                    'text': (
                        'For one trade (paint, roof, deck, gutter, or concrete), write scope notes that include: '
                        'include list, exclude list, material responsibility, any unit rate (e.g. sheathing $/sheet), '
                        'access/dumpster/parking, notice to residents, and one option if relevant. '
                        'Paste into generator practice and read the output for missing excludes.'
                    ),
                },
                {
                    'id': 'ops_pg_site_obs',
                    'title': 'Site observations (raw → voice)',
                    'text': (
                        'From a real walk, write 5–8 raw field bullets (no marketing). Generate with Site Observations filled. '
                        'Confirm the section opens in PPS voice, only states what you wrote, and omits inventing a visit date '
                        'you did not record. Leave blank on a second generate and confirm the section disappears.'
                    ),
                },
                {
                    'id': 'ops_pg_pricing_modes',
                    'title': 'Pricing modes: fixed / multi-option / open',
                    'text': (
                        'Create three mini pricing plans for the same property problem: fixed package, multi-option '
                        '(e.g. one coat vs two / repair vs replace), and open/T&M diagnostic. '
                        'Note when each builds trust and when each destroys margin. Manager confirms before you use open mode live.'
                    ),
                },
                {
                    'id': 'ops_pg_generate_practice',
                    'title': 'Generate a full practice proposal',
                    'text': (
                        'Using partner-project notes, generate a real practice proposal (Short or Comprehensive as agreed). '
                        'Download .docx. Highlight in yellow anything you would change before a client sees it. '
                        'Do not email the client.'
                    ),
                },
                {
                    'id': 'ops_pg_comparison',
                    'title': 'Proposal Comparison habit',
                    'text': (
                        'Edit your practice proposal in Word (scope clarity, exclude, product name, or condo tone). '
                        'Run Proposal Comparison on the dashboard with original vs edited. '
                        'Submit one concrete voice/scope improvement for the company guide.'
                    ),
                },
                {
                    'id': 'ops_pg_production_ready',
                    'title': 'Production-ready handoff test',
                    'text': (
                        'Give your practice proposal to a PM or your manager. Ask: "Could you sell this to a Trade Partner '
                        'without calling me?" Capture every gap (address, exclude, unit rate, access). Fix notes and regenerate once.'
                    ),
                },
                {
                    'id': 'ops_pg_live_review',
                    'title': 'Never cold-send — review conversation',
                    'text': (
                        'Role-play walking a client through a generated proposal: goals, scope phases, investment, next step. '
                        'Script three questions you ask them. Manager grades for clarity and no over-promise on schedule.'
                    ),
                },
                {
                    'id': 'ops_pg_pure_way_check',
                    'title': 'Pure Way check on a draft',
                    'text': (
                        'On your practice proposal, mark one place each that builds trust, signals commercial quality, '
                        'and drives a result (award/next step). If any pillar is missing, revise scope notes and regenerate.'
                    ),
                },
            ],
        },
        {
            'id': 'ops_decision_ownership',
            'title': 'Decision-Making & Who Owns What',
            'assigned_week': 2,
            'summary': (
                'Flexibility is required on every job — but new consultants need a framework for who leads, who collaborates, '
                'and when to escalate pricing, callbacks, scope changes, and client communication.'
            ),
            'sop_placeholders': [
                'PSC primary: client relationship, site visit quality, scope narrative, proposal delivery conversation',
                'PM primary: field schedule, Trade Partner coordination, production execution, change orders in field',
                'Tony/leadership: pricing exceptions, major client escalations, proposal sign-off when assigned',
                'Loop in PM before: promising dates, pricing beyond proposal, scope not documented, resident complaints on site',
                'Simple guides for: pricing support, callbacks, change orders, concealed conditions',
                '[TO DOCUMENT] After hours or urgent site issue — who do you call?',
            ],
            'manager_1on1': (
                '30-minute scenario session: three situations — callback, change order, client wants price today. '
                'For each, name primary owner, who you copy, and what you never decide alone.'
            ),
            'items': [
                {
                    'id': 'ops_ownership_card',
                    'title': 'Ownership quick-reference',
                    'text': (
                        'One-page card: I own / PM owns / escalate to leadership — for pricing, schedule, scope changes, '
                        'callbacks, and client complaints. Manager signs off.'
                    ),
                },
                {
                    'id': 'ops_ownership_scenarios',
                    'title': 'Three scenario walk-throughs',
                    'text': (
                        'With your manager, walk through real hub/Monday examples of a change order, a schedule slip, '
                        'and a scope dispute. Note who moved each phase forward.'
                    ),
                },
            ],
        },
        {
            'id': 'ops_trade_partners',
            'title': 'Trade Partners — Find, Vet & Work With Subs',
            'assigned_week': 2,
            'summary': (
                'Trade Partners are an extension of the PPS team. Learn through partner projects — estimating conversations, '
                'scope discussions, and site coordination alongside your mentor — not in isolation. '
                'Company standard after award: PSC + PM + Trade Partner share one job text chain (see SOP).'
            ),
            'sop_placeholders': [
                '[TO DOCUMENT] How do we find and recruit new Trade Partners?',
                (
                    'Before first use: signed sub agreement, current COI, workers’ comp (or documented exemption) — '
                    'Stephanie owns DocuSign packet; you send name + email + company. Board tracks Sub Compliance.'
                ),
                'Trade Partner Scope = crew-ready language; PSC does not promise scope production has not confirmed',
                'Scheduling and 48-hour resident notice — PM/production lead; PSC communicates to client',
                (
                    'THREE-WAY TEXT CHAIN (company standard — Sales Meeting 2026-08-10): When a job is awarded and '
                    'ready to schedule, start a group text = you (PSC) + PM + Trade Partner lead for that job. '
                    'Not required at walk/estimate only. Super-simple one-loop jobs may be light — do not default to silence.'
                ),
                (
                    'On the chain: job questions, ETAs, material issues, progress/finish photos, delays. Not private '
                    'PM↔sub only. Whoever can answer fastest answers (PSC or PM). You stay informed so the client never '
                    'surprises you with “where are the guys?”'
                ),
                (
                    'Why you stay on the chain even if the PM “runs” the field: (1) more informed on your jobs, '
                    '(2) you see issues and potential solutions as they form — even when silent — so you learn and can '
                    'brief the client, (3) you can take point on pay: tell the TP you will enter the pay request when '
                    'work/photos check out (punch before pay; ACH preferred).'
                ),
                (
                    'Trust but verify — not distrust of production. Simple jobs may need almost no texts; you never fully '
                    'step away because it is your sale and next award. Prefer many small chains (per job / per TP) over '
                    'one mega-group. Client-wide chains (e.g. Morgan) are OK for multi-job traffic.'
                ),
                (
                    'TP buy-in takes time: some will only text the PM at first. Set the expectation, answer real questions '
                    'on the three-way, build trust — they will use the group. If a PM refuses the standard, escalate to '
                    'manager / production leadership (not optional style).'
                ),
                (
                    'Pay / QC: photos and completion on the thread support QC. PSC often enters or drives the pay request '
                    'once work is accepted; incomplete punch should not get final pay. Stephanie/office handles ACH setup.'
                ),
                'Include new PSC in Trade Partner site visits and estimate conversations during partner projects',
                '[TO DOCUMENT] Preferred Trade Partners by trade — who and specialty?',
            ],
            'manager_1on1': (
                '45-minute session: (1) review one Trade Partner Scope and the Monday/production record for that job; '
                '(2) open or mock a real PSC + PM + TP three-way text on an active/scheduled job; (3) confirm who enters '
                'pay requests and what photos/QC are required before pay.'
            ),
            'items': [
                {
                    'id': 'ops_tp_read',
                    'title': 'Review Trade Partner SOP',
                    'text': (
                        'Read the SOP bullets — especially the three-way text chain and pay/QC rules. '
                        'Note what you may promise clients vs. what requires production sign-off.'
                    ),
                },
                {
                    'id': 'ops_tp_1on1',
                    'title': 'Manager 1:1 — Trade Partner handoff + text chain',
                    'text': (
                        'Review a real Trade Partner Scope with your manager. Identify crew-ready vs. client-facing language. '
                        'Confirm when the three-way text starts (award + ready to schedule) and who is on it.'
                    ),
                },
                {
                    'id': 'ops_tp_shadow',
                    'title': 'Shadow production/sub coordination',
                    'text': (
                        'On a shadow day, note how the consultant and PM coordinate Trade Partner arrival, scope questions, '
                        'and site issues. Count how many updates lived on a shared text vs. private side channels.'
                    ),
                },
                {
                    'id': 'ops_tp_text_chain',
                    'title': 'Start or join a three-way text chain',
                    'text': (
                        'On a partner or solo job that is awarded and ready to schedule: create (or join) the group text '
                        'PSC + PM + Trade Partner. Send a short kickoff line (job name, address, start window, who answers '
                        'what). Show your manager. If the TP only replies to the PM, coach once on the group and log it.'
                    ),
                },
                {
                    'id': 'ops_tp_pay_point',
                    'title': 'Pay-request path with the TP',
                    'text': (
                        'With your manager, walk how a TP gets paid on one real job: photos/QC, who enters the pay request, '
                        'when you tell the TP “I’ll submit the request.” Write the one-sentence script you will use on the chain.'
                    ),
                },
            ],
        },
        {
            'id': 'ops_client_comms',
            'title': 'Client Communication & Escalation',
            'assigned_week': 3,
            'summary': (
                'Who gets copied when, resident-aware communication, 48-hour notice, and escalation paths.'
            ),
            'sop_placeholders': [
                'Touchpoints: site visit follow-up, proposal review call (not cold email), award, mobilization, mid-job, close-out',
                '48-hour notice and resident communication through property management',
                'Copy PM/production on schedule, scope, and complaint threads; ownership on major investment decisions',
                (
                    'Job text chain (PSC + PM + TP) is your live field feed — use it so client updates are accurate '
                    '(delay, crew status, finish). You can brief the client without a second detective call to the PM.'
                ),
                'Escalation: complaints and resident issues → PM immediately; pricing exceptions → Tony/manager',
                'Never to client without PM/manager review: production dates, pricing outside proposal, scope commitments',
                '[TO DOCUMENT] Sample client update for one phase (award, delay, or close-out)?',
            ],
            'manager_1on1': (
                '30-minute role-play: proposal review call, schedule delay conversation, and resident complaint '
                'escalation. Manager coaches tone and escalation.'
            ),
            'items': [
                {
                    'id': 'ops_comms_read',
                    'title': 'Review client communication SOP',
                    'text': 'Read the SOP bullets. Draft your personal escalation list (who to call for what).',
                },
                {
                    'id': 'ops_comms_1on1',
                    'title': 'Manager 1:1 — communication role-play',
                    'text': 'Complete the three role-play scenarios with your manager. Incorporate feedback before checking off.',
                },
                {
                    'id': 'ops_comms_escalation',
                    'title': 'Build your escalation card',
                    'text': (
                        'Write a one-page reference: PM contact, production contact, urgent site issues, '
                        'after-hours path. Confirm with your manager and save in Monday.com.'
                    ),
                },
            ],
        },
        {
            'id': 'ops_callbacks',
            'title': 'Callbacks, Warranty & Service Recovery',
            'assigned_week': 3,
            'summary': (
                'Callbacks affect trust as much as the original install. Know the operational process and your communication '
                'role — respond quickly, set expectations, document findings, and follow through to resolution.'
            ),
            'sop_placeholders': [
                'PSC role: acknowledge promptly, coordinate through PM, document with photos, no blame language to client',
                'Internal: log in Monday.com, assign field owner, track to resolution',
                'Warranty language: PPS labor vs. manufacturer — do not improvise; use documented trade language',
                '[TO DOCUMENT] Callback from first call to closed — what are the steps?',
                'Use completed callbacks as partner-project learning — debrief what communication worked',
            ],
            'manager_1on1': (
                '30-minute review: walk one real callback from report to resolution. Role-play the client update you would send.'
            ),
            'items': [
                {
                    'id': 'ops_callback_role',
                    'title': 'Your role on a callback',
                    'text': (
                        'Shadow or review a callback case. Write: first client response, who you loop in, '
                        'what you document, and how you close the loop with the client.'
                    ),
                },
                {
                    'id': 'ops_callback_draft',
                    'title': 'Service recovery draft',
                    'text': (
                        'Draft a short client update for a hypothetical warranty call-back (schedule TBD, findings pending). '
                        'Manager coaches tone — proactive, accountable, no over-promise.'
                    ),
                },
            ],
        },
        {
            'id': 'ops_common_mistakes',
            'title': 'Common PSC Mistakes (Month 1)',
            'assigned_week': 3,
            'summary': (
                'The things new consultants get wrong before tribal knowledge kicks in — '
                'compiled from leadership and field experience.'
            ),
            'sop_placeholders': [
                '[TO DOCUMENT] Instead of promising schedule/scope without PM — what do you do?',
                '[TO DOCUMENT] Site visit under-documented — what photos/notes are required?',
                '[TO DOCUMENT] Why never send a proposal cold, and what do you do instead?',
                '[TO DOCUMENT] Monday hygiene first 30 days — what must stay current?',
                '[TO DOCUMENT] When must you involve the PM on site or client issues?',
                '[TO DOCUMENT] PPS voice vs generic contractor speak — give one rewrite?',
            ],
            'manager_1on1': (
                '30-minute debrief: manager shares top mistakes they have seen from new PSCs. '
                'You identify which you are most at risk for and one habit to prevent each.'
            ),
            'items': [
                {
                    'id': 'ops_mistakes_read',
                    'title': 'Review common mistakes list',
                    'text': 'Read the SOP bullets. Star the three you are most likely to make in month one.',
                },
                {
                    'id': 'ops_mistakes_1on1',
                    'title': 'Manager 1:1 — mistake prevention',
                    'text': 'Discuss your starred items with your manager. Agree on one prevention habit per risk.',
                },
                {
                    'id': 'ops_mistakes_commit',
                    'title': 'Write your month-1 guardrails',
                    'text': (
                        'Three sentences: what you will always do, what you will never do, '
                        'and who you will ask before committing. Share with your manager.'
                    ),
                },
            ],
        },
        {
            'id': 'ops_market_expansion',
            'title': 'New Market Expansion — The Pure Way Formula',
            'assigned_week': 4,
            'summary': (
                'PPS grows hub-and-spoke: Cincinnati/Dayton is the main office; new cities are spokes until they earn footing. '
                'Every PSC should understand the formula — even if you never launch a city yourself — because it is how we '
                'protect margin, capacity, and client trust when we leave home turf. Full playbook: business-intel/strategy/'
                'PPS_New_Market_Expansion_Playbook.md (leadership).'
            ),
            'sop_placeholders': [
                'Main office stays Cincinnati/Dayton — new markets use Ohio standards (PPM, Hub, voice), not a second culture',
                'Anchor first: national client (Morgan-type) soft commitment before hire; year-one base target $750K–$1M; '
                'below ~$500K committed written work = no launch',
                'Apartments are the entry wedge; condo/HOA and commercial follow once the market is established',
                'Financial gates before spend: company ICC toward $500K, revenue on plan, PM capacity free '
                '(e.g. major guarantee work complete) — expansion is not a cash bandage',
                'Drive time within ~2 hours of Cincinnati/Dayton applies to initial launch only; '
                'after proof of concept (typically Month 6 green gate) the range can expand',
                'Roles (no dual commanders): Adam owns anchor relationship and city sequencing; market lead owns day-to-day '
                'sales/PM and non-anchor BD; Tony (VP Sales) is available for support — PSC training standards, culture, '
                'condo/board motion later — he does not run the Morgan anchor lane or compete for city sequencing; '
                'Trey/Production owns PPM quality and traveling Trade Partner bench; Stephanie owns credit checks, '
                'invoicing terms, and market P&L vs budget; Thomas owns go/no-go gates and capital',
                'Trade Partner bench before volume: 3–5 local partners per core trade + Ohio travelers + company-wide '
                'traveling bench; scorecard quality/schedule/price in Monday.com',
                'Margin floor 28% blended; AR discipline from day one (credit-check, clear terms, watch DSO) — '
                'new-market enthusiasm is how bad receivables get born',
                'Gates over gut: formal reviews Month 3 / 6 / 9 / 12 with pre-agreed green/red and pull-back plan',
                'Earn-trust motion still applies: small maintenance/repair scopes before large CapEx in a new city',
            ],
            'manager_1on1': (
                '30–45 minutes with VP Sales (Tony) or assigned mentor: walk the expansion formula, who owns what '
                '(Adam vs market lead vs Tony support), and what a PSC must never do in a new market '
                '(cold-send proposals, skip PPM, promise schedule without production, chase volume without a TP bench).'
            ),
            'items': [
                {
                    'id': 'ops_expansion_read',
                    'title': 'Learn the formula',
                    'text': (
                        'Read the SOP bullets above. Write the one-sentence model in your own words: '
                        'anchor → market lead (sales+PM) → apartments first → Trade Partner bench before volume.'
                    ),
                },
                {
                    'id': 'ops_expansion_roles',
                    'title': 'Role map — clear ownership',
                    'text': (
                        'Draw a simple responsibility map for a new city: Adam (national anchor), market lead '
                        '(local delivery + non-anchor), Tony (support: training, standards, condo motion when ready), '
                        'Trey (production), Stephanie (AR/credit), leadership (go/no-go). Note one place a new PSC '
                        'would escalate to the wrong person if they skipped this map.'
                    ),
                },
                {
                    'id': 'ops_expansion_gates',
                    'title': 'Gates over gut',
                    'text': (
                        'List the Month 6 green and red criteria from memory (or notes). '
                        'Explain why pre-agreed kill criteria protect the company better than “give it another quarter.”'
                    ),
                },
                {
                    'id': 'ops_expansion_1on1',
                    'title': 'Manager 1:1 — expansion briefing',
                    'text': (
                        'Complete the expansion 1:1 with Tony or your mentor. Confirm how the team works together: '
                        'Adam leads national-anchor relationships; Tony supports training, standards, and later '
                        'condo/board diversification; the market lead runs local day-to-day work.'
                    ),
                },
            ],
        },
    ],
}

# Week 0 — onboarding before trade-specific weeks
PSC_ONBOARDING = {
    'week': 0,
    'title': 'Week 0 · PPS Foundations',
    'segment': 'All Segments',
    'topic': 'Company, Tools & Workflow',
    'book': 'The Infinite Game',
    'book_chapters': {
        'title': 'The Infinite Game',
        'author': 'Simon Sinek',
        'chapters': [
            {'num': 1, 'title': 'To Play or Not to Play'},
        ],
        'discussion': 'Preview only — discuss finite vs. infinite mindset with your manager before Week 1.',
    },
    'videos': [],
    'shadowing': [
        {
            'id': 'w0_shadow_intro',
            'text': 'Meet with your manager for a 60-minute PPS orientation: org chart, who does what, and your first 30/60/90-day goals.',
        },
        {
            'id': 'w0_shadow_partner',
            'text': (
                'Meet your mentor consultant and join your first partner project touchpoint (site visit, client call, or proposal review) '
                'before Week 1 — observe only; debrief with manager same week.'
            ),
        },
        {
            'id': 'w0_shadow_ride',
            'text': 'Ride along on one consultant site visit before Week 1 ends — observe how scope is discussed with property staff.',
        },
    ],
    'additional': [
        {
            'id': 'w0_add_monday',
            'type': 'reading',
            'title': 'Monday.com at PPS — start here',
            'text': (
                'Complete the Monday.com at PPS module in PPS Company Operations (reference section above) '
                'with your manager — not the generic platform alone. Optional supplement: '
                'Monday.com Tutorial for Beginners on YouTube if you have never used the platform.'
            ),
        },
        {
            'id': 'w0_add_hub',
            'type': 'tool',
            'title': 'Explore the PPS Hub Dashboard',
            'text': 'Familiarize yourself with every tool card — Proposal Generator, PPM, Trade Partner Scope, and Site Visit Report.',
        },
        {
            'id': 'w0_add_proposal',
            'type': 'tool',
            'title': 'Walk through the Proposal Generator',
            'text': (
                'Open Proposal Generator (do not send). Click through all steps. Note short vs comprehensive, property type, '
                'and where scope notes and site observations go. Full craft module starts Week 1 — this is orientation only.'
            ),
        },
        {
            'id': 'w0_add_ppm',
            'type': 'tool',
            'title': 'Review a sample PPM',
            'text': 'Open Pre-Project Meeting and load an approved proposal. Understand what PMs need before mobilization.',
        },
        {
            'id': 'w0_add_site_visit',
            'type': 'tool',
            'title': 'Complete a practice Site Visit Report',
            'text': 'Use the Site Visit tool on a property you have already toured. Get comfortable with the checklist format.',
        },
        {
            'id': 'w0_add_crm',
            'type': 'reading',
            'title': 'Client contact workflow',
            'text': 'Learn how PPS tracks client contacts in the hub. Ask your manager where your pipeline lives in Monday.com.',
        },
    ],
    'pps_focus': [
        {
            'id': 'w0_focus_partner',
            'title': 'Partner-project onboarding — start here',
            'text': (
                'Complete the Partner-Project Onboarding module first: mentor assigned, 3–5 projects identified, '
                'partner-project log started. This runs parallel to all Week 0–3 operations modules.'
            ),
        },
        {
            'id': 'w0_focus_ops',
            'title': 'Company Operations — Monday.com & project lifecycle',
            'text': (
                'Complete Monday.com at PPS and Project Lifecycle modules in the Company Operations section '
                '(manager 1:1 required for each).'
            ),
        },
        {
            'id': 'w0_focus_core',
            'title': 'Complete Mission, Values, Pure Way & PPS Voice',
            'text': (
                'Finish every training activity above — including The Pure Way (Trust · Quality · Results) — '
                'before Week 1. Pure Way is judgment, not a slogan to paste into proposals.'
            ),
        },
        {
            'id': 'w0_focus_vocab',
            'title': 'Start your scope vocabulary list',
            'text': 'Begin a personal glossary: tuck pointing, EIFS, B&B, mobilization, punch list, change order. Add terms each week.',
        },
    ],
    'manager_checkin': (
        'Confirm Week 0 complete — Pure Way map, Company Operations (Monday.com + lifecycle), partner projects started — '
        'before trade-specific training. Proposal Generator Craft begins Week 1.'
    ),
}

PSC_TRAINING_WEEKS = [
    {
        'week': 1,
        'segment': 'Apartments',
        'book': 'The Infinite Game',
        'book_chapters': {
            'chapters': [
                {'num': 1, 'title': 'To Play or Not to Play'},
                {'num': 2, 'title': 'The Infinite Game'},
                {'num': 3, 'title': 'The Responsibility of Businesses'},
            ],
            'discussion': 'Discuss: Is PPS playing a finite or infinite game? What does that mean for client relationships?',
        },
        'topic': 'Painting & Drywall',
        'topic_summary': (
            'Interior and exterior paint scope is one of the highest-volume trades in multifamily. '
            'Learn prep, application, and what "good" looks like on a turnover or capital project.'
        ),
        'videos': [
            {'url': 'https://www.youtube.com/watch?v=bLbUIevOxzY', 'title': 'How To Paint A Room | DIY For Beginners'},
            {'url': 'https://www.youtube.com/watch?v=2eUxz_or2Qs', 'title': 'DIY How to Paint like a Pro Series A to Z'},
            {'url': 'https://www.youtube.com/watch?v=oNagIA8sKY0', 'title': 'Interior Painting Step 1: Prepping a Room'},
            {'url': 'https://www.youtube.com/watch?v=UsXrIP1og90', 'title': 'Drywall Tips and Tricks'},
        ],
        'shadowing': [
            'Shadow an experienced consultant on painting jobs in apartment properties.',
            'Visit projects where a painting project has happened or is in progress.',
        ],
        'additional': [],
        'pps_focus': [
            {
                'id': 'w1_focus_ops',
                'title': 'Company Operations — Estimates + Proposal Generator Craft',
                'text': (
                    'Complete How PPS Estimates and start Proposal Generator Craft (Old vs New, form map, short vs full, '
                    'issue → outcome). Manager 1:1 on the generator is required this week or Week 2.'
                ),
            },
            {
                'id': 'w1_focus_proposal',
                'title': 'Proposal craft — painting scope notes',
                'text': (
                    'For a real or shadow painting job, write generator-ready scope notes: include, exclude, coats, product, '
                    'access, 48-hour notice. Generate a practice Short proposal (do not send). Yellow-highlight edits you still need.'
                ),
            },
            {
                'id': 'w1_focus_identify',
                'title': 'Photo challenge',
                'text': 'On site, photograph 3 examples of paint failure (peeling, chalking, lap marks). Note likely cause.',
            },
        ],
        'manager_checkin': (
            'Can you explain prep vs finish coat in plain language, and walk me through your practice painting proposal '
            'like you would a property manager?'
        ),
    },
    {
        'week': 2,
        'segment': 'Apartments',
        'book': 'The Infinite Game',
        'book_chapters': {
            'chapters': [
                {'num': 4, 'title': 'Just Cause'},
                {'num': 5, 'title': "A Cause That's Worth the Cost"},
                {'num': 6, 'title': 'Trusting Teams'},
            ],
            'discussion': 'Discuss: What is PPS\'s Just Cause? How do trusting teams show up on a job site?',
        },
        'topic': 'Roofing & Gutters',
        'topic_summary': (
            'Roofing drives major capital decisions. Understand shingle systems, drainage, and when a gutter scope '
            'is standalone vs. bundled with re-roof.'
        ),
        'videos': [
            {'url': 'https://www.youtube.com/watch?v=aEV1OoGKBpE', 'title': 'How to Install a Rain Gutter | Ask This Old House'},
            {'url': 'https://www.youtube.com/watch?v=qo24NKpYv2c', 'title': 'DIY Guide To Installing Gutters'},
            {'url': 'https://www.youtube.com/watch?v=PioKr-pyR7k', 'title': 'How to Roof a House'},
            {'url': 'https://www.youtube.com/watch?v=p0VM9L-0SYE', 'title': 'How to Install Roof Shingles'},
        ],
        'shadowing': [
            'Shadow an experienced consultant on roofing and gutter jobs in apartment properties.',
            'Visit projects where a roofing and/or gutter project has happened or is in progress.',
        ],
        'additional': [
            {'type': 'video', 'url': 'https://www.youtube.com/watch?v=NkVE3_nqfHk', 'title': 'Trade Partners'},
            {'type': 'video', 'url': 'https://www.youtube.com/watch?v=4xCs0JunUhs', 'title': 'Pros and Cons of Employees vs Subcontractors'},
            {'type': 'channel', 'url': 'https://www.youtube.com/@TheExcellentLaborer', 'title': 'The Excellent Laborer (channel)'},
        ],
        'pps_focus': [
            {
                'id': 'w2_focus_ops',
                'title': 'Company Operations — Trade Partners + proposal craft',
                'text': (
                    'Complete Trade Partners (1:1 + TPS review + shadow). Continue Proposal Generator Craft: '
                    'scope notes that production can use, site observations raw→voice, pricing modes.'
                ),
            },
            {
                'id': 'w2_lifecycle_site',
                'title': 'Project lifecycle — Site visit → generator inputs',
                'text': (
                    'Shadow a site visit end-to-end. Capture photos, measurements, failure modes, access, phasing. '
                    'Same day: turn notes into generator fields (issue/outcome, scope notes, site observations) — do not send.'
                ),
            },
            {
                'id': 'w2_focus_tps',
                'title': 'Understand Trade Partner Scope handoff',
                'text': (
                    'After shadowing a roof or gutter job, review Trade Partner Scope for that trade. '
                    'Compare to your generator proposal: would production have enough include/exclude and unit rates?'
                ),
            },
        ],
        'manager_checkin': (
            'Trade Partners module complete? Can you describe the difference between a repair scope and a full re-roof?'
        ),
    },
    {
        'week': 3,
        'segment': 'Apartments',
        'book': 'The Infinite Game',
        'book_chapters': {
            'chapters': [
                {'num': 7, 'title': 'Ethical Fading'},
                {'num': 8, 'title': 'Worthy Rival'},
                {'num': 9, 'title': 'Existential Flexibility'},
            ],
            'discussion': 'Discuss: Who is a worthy rival in our market? What would existential flexibility look like at PPS?',
        },
        'topic': 'Masonry (Tuck Pointing & Brick)',
        'topic_summary': (
            'Masonry scopes require visual identification of mortar joint failure. Learn tuck pointing, '
            'brick repair, and when structural vs. cosmetic work applies.'
        ),
        'videos': [
            {'url': 'https://www.youtube.com/watch?v=uRU-qPKMC7Q', 'title': 'Tuck Pointing for Beginners'},
            {'url': 'https://www.youtube.com/watch?v=eHsoNLm78ys', 'title': 'How to Repoint a House | This Old House'},
            {'url': 'https://www.youtube.com/watch?v=nF_Y79k_q4Y', 'title': 'DIY How to Tuck Point by an Actual Mason'},
            {'url': 'https://www.youtube.com/watch?v=NZ8brDJAMdE', 'title': 'How to Lay Brick for Beginners'},
        ],
        'shadowing': [
            'Shadow an experienced consultant on masonry jobs in apartment properties.',
            'Visit projects where tuck pointing has happened or is in progress.',
        ],
        'additional': [
            {'type': 'video', 'url': 'https://www.youtube.com/watch?v=WZx-hsb-H9A', 'title': 'Sales Objections'},
        ],
        'pps_focus': [
            {
                'id': 'w3_focus_ops',
                'title': 'Company Operations — Client comms, mistakes, proposal craft',
                'text': (
                    'Complete Client Communication & Escalation and Common PSC Mistakes. Finish Proposal Generator Craft '
                    'items: full practice generate, Proposal Comparison, production-ready handoff test, Pure Way check.'
                ),
            },
            {
                'id': 'w3_lifecycle_proposal',
                'title': 'Project lifecycle — Site visit to generated proposal',
                'text': (
                    'Trace one real job from site notes through Proposal Generator to .docx. '
                    'What transferred cleanly? What did you still edit? Would a PM sell this to a Trade Partner cold?'
                ),
            },
            {
                'id': 'w3_focus_objections',
                'title': 'Practice objection handling',
                'text': (
                    'Role-play: "Your price is higher than the last vendor." Defend scope quality and process '
                    '(Pure Way: trust + quality + results) without inventing a discount. Use Sales Objections module.'
                ),
            },
        ],
        'manager_checkin': (
            'Company Operations modules through Week 3 complete? '
            'Can you spot failed mortar joints vs. efflorescence on a walkthrough?'
        ),
    },
    {
        'week': 4,
        'segment': 'Apartments',
        'book': 'The Infinite Game',
        'book_chapters': {
            'chapters': [
                {'num': 10, 'title': 'The Courage to Lead'},
                {'num': 11, 'title': 'The Infinite Game'},
            ],
            'discussion': 'Finish the book. Share your top takeaway with your manager — how will it change how you show up for clients?',
        },
        'topic': 'Concrete',
        'topic_summary': (
            'Sidewalks, pads, and curbs are everywhere on apartment communities. Learn pour basics, '
            'jointing, and common failure modes (spalling, settling).'
        ),
        'videos': [
            {'url': 'https://www.youtube.com/watch?v=k1XFWNT7pAM', 'title': 'How to Pour a Concrete Slab for Beginners DIY'},
            {'url': 'https://www.youtube.com/watch?v=-5SU8CRCQ-0', 'title': 'Quick Concrete Basics'},
            {'url': 'https://www.youtube.com/watch?v=5dL5y06RnCI', 'title': 'Pouring a 60×36 Large Slab'},
            {'url': 'https://www.youtube.com/watch?v=z-vGkb-VCdk', 'title': 'Simple DIY Concrete Slab'},
            {'url': 'https://www.youtube.com/watch?v=SDeBDcFEDXQ', 'title': 'Sidewalk Repair'},
        ],
        'shadowing': [
            'Shadow an experienced consultant on concrete jobs in apartment properties.',
            'Visit projects where a concrete pour has happened or is in progress.',
        ],
        'additional': [
            {'type': 'video', 'url': 'https://www.youtube.com/watch?v=gLRIW64ZcOo', 'title': '5 Tips for Handling Complaints'},
        ],
        'pps_focus': [
            {
                'id': 'w4_focus_ops_expansion',
                'title': 'Company Operations — New Market Expansion formula',
                'text': (
                    'Complete the New Market Expansion module in PPS Company Operations. '
                    'Know the hub-and-spoke model, anchor-first gate, and who owns what '
                    '(Adam = anchor; Tony = support for training/standards/condo motion — not a second city commander).'
                ),
            },
            {
                'id': 'w4_lifecycle_review',
                'title': 'Project lifecycle — Live proposal review',
                'text': (
                    'Shadow or role-play walking a *generator* proposal with a property manager: issue → outcome, '
                    'includes/excludes, investment, next step. Never cold-send. Complete sales_prop_tool_3 + ops_pg_live_review if not done.'
                ),
            },
            {
                'id': 'w4_focus_scope_edit',
                'title': 'Proposal craft — refine & compare',
                'text': (
                    'Generate a practice apartment proposal, then edit three scope lines to better fit the property '
                    '(phasing, resident disruption, concealed conditions). Manager reviews before you check this off.'
                ),
            },
            {
                'id': 'w4_focus_complaints',
                'title': 'Complaint response drill',
                'text': 'Review the complaints video. Write a 3-step response you would use if a resident complains about noise during concrete work.',
            },
            {
                'id': 'w4_focus_apartment_complete',
                'title': 'Apartment segment recap',
                'text': 'List the 4 apartment trades you studied. For each, name one scope question you would ask on a new walkthrough.',
            },
        ],
        'manager_checkin': 'Apartment segment review — ready to transition to condos?',
    },
    {
        'week': 5,
        'segment': 'Condos',
        'book': 'Fanatical Prospecting',
        'book_chapters': {
            'chapters': [
                {'num': 1, 'title': 'The Case for Prospecting'},
                {'num': 2, 'title': 'Seven Mindsets of Fanatical Prospectors'},
                {'num': 3, 'title': 'To Cold Call or Not to Cold Call?'},
                {'num': 4, 'title': 'Adopt a Balanced Prospecting Methodology'},
                {'num': 5, 'title': 'The More You Prospect, the Luckier You Get'},
            ],
            'discussion': 'Discuss: What is your prospecting block schedule? Which channels will you use for condo/HOA outreach?',
        },
        'topic': 'EIFS',
        'topic_summary': (
            'Condos and HOAs frequently have EIFS (synthetic stucco) cladding. Learn identification, '
            'common failure points, and how EIFS differs from traditional stucco.'
        ),
        'videos': [
            {'url': 'https://www.youtube.com/watch?v=qIjAuYOQCsY', 'title': 'What is EIFS (short video)'},
            {'url': 'https://www.youtube.com/watch?v=nLjgnXf5zqQ', 'title': 'Patching and Painting EIFS'},
            {'url': 'https://www.youtube.com/watch?v=TMz8L8ut7Kc', 'title': 'EIFS Install Overview'},
            {'url': 'https://www.youtube.com/watch?v=jEY_JISUdy4', 'title': 'Stucco vs EIFS Inspection'},
        ],
        'shadowing': [
            'Shadow an experienced consultant on EIFS jobs in condo properties.',
            'Visit projects where EIFS work has happened or is in progress.',
        ],
        'additional': [
            {'type': 'video', 'url': 'https://www.youtube.com/watch?v=j2qPguCTTis', 'title': 'Everything You Need to Know About Condos'},
            {'type': 'video', 'url': 'https://www.youtube.com/watch?v=FuPGcv-NYJs', 'title': "What's It Like Being an HOA Manager"},
        ],
        'pps_focus': [
            {
                'id': 'w5_lifecycle_award',
                'title': 'Project lifecycle — Award & handoff',
                'text': (
                    'Ask your manager to walk you through what happens when a client awards a job: internal notifications, '
                    'PM assignment, PPS handoff from sales to production, and what the PSC still owns.'
                ),
            },
            {
                'id': 'w5_focus_hoa',
                'title': 'HOA decision-maker map',
                'text': 'For your condo prospects, identify: board president, property manager, and who signs contracts. Document in Monday.com.',
            },
        ],
        'manager_checkin': 'Can you explain EIFS vs. stucco to an HOA board member?',
    },
    {
        'week': 6,
        'segment': 'Condos',
        'book': 'Fanatical Prospecting',
        'book_chapters': {
            'chapters': [
                {'num': 6, 'title': 'Know Your Numbers'},
                {'num': 7, 'title': 'The Three Ps That Are Holding You Back'},
                {'num': 8, 'title': 'Time: The Great Equalizer of Sales'},
                {'num': 9, 'title': 'The Four Objectives of Prospecting'},
                {'num': 10, 'title': 'Leveraging the Prospecting Pyramid'},
                {'num': 11, 'title': 'Own Your Database'},
            ],
            'discussion': 'Review your outreach ratios with your manager. What are your numbers this week?',
        },
        'topic': 'Siding (Vinyl)',
        'topic_summary': (
            'Vinyl siding is common on condo townhome-style construction. Learn installation, '
            'repair techniques, and manufacturer spec requirements.'
        ),
        'videos': [
            {'url': 'https://www.youtube.com/watch?v=l1MwrqImWXs', 'title': 'How to Install Vinyl Siding'},
            {'url': 'https://youtu.be/FYWcDfZeH_4', 'title': 'Vinyl Siding Install — Part 2'},
            {'url': 'https://youtu.be/lzhSsmWnHfw', 'title': 'Vinyl Siding Repair'},
            {'url': 'https://www.youtube.com/watch?v=SS1x9ZaouQs', 'title': 'Install Siding A to Z'},
        ],
        'shadowing': [
            'Shadow an experienced consultant on vinyl siding jobs in condo properties.',
            'Visit projects where vinyl siding installation has happened or is in progress.',
        ],
        'additional': [
            {'type': 'video', 'url': 'https://www.youtube.com/watch?v=u4ZoJKF_VuA', 'title': 'Find Your Why'},
            {'type': 'reading', 'title': 'PPS Why', 'text': 'We believe in elevating lives and spaces through relentless improvement and unbreakable trust.'},
        ],
        'pps_focus': [
            {
                'id': 'w6_lifecycle_ppm',
                'title': 'Project lifecycle — Pre-Project Meeting',
                'text': (
                    'Shadow or review a PPM for an awarded job. Identify what the PM needs from the proposal, '
                    'who attends, and what the PSC must confirm before mobilization.'
                ),
            },
            {
                'id': 'w6_focus_condo_proposal',
                'title': 'Estimating track — Step 3: Build a condo proposal',
                'text': (
                    'Generate a practice condo/HOA proposal in the Proposal Generator. Adjust tone for a board audience '
                    '(homeowner value, deferred risk). Manager reviews before client-facing use.'
                ),
            },
            {
                'id': 'w6_focus_prospecting',
                'title': 'Prospecting block',
                'text': 'Apply Fanatical Prospecting: schedule 10 new condo/HOA outreach touches this week. Log in Monday.com.',
            },
        ],
        'manager_checkin': 'How many new condo prospects did you add to pipeline this week?',
    },
    {
        'week': 7,
        'segment': 'Condos',
        'book': 'Fanatical Prospecting',
        'book_chapters': {
            'chapters': [
                {'num': 12, 'title': 'The Law of Familiarity'},
                {'num': 13, 'title': 'Social Selling'},
                {'num': 14, 'title': 'Message Matters'},
                {'num': 15, 'title': 'Telephone Prospecting Excellence'},
                {'num': 16, 'title': 'Turning Around RBOs'},
            ],
            'discussion': 'Role-play a brush-off and turnaround using the RBO framework from Chapter 16.',
        },
        'topic': 'Siding (Hardie & Board-and-Batten)',
        'topic_summary': (
            'Fiber cement (Hardie) and board-and-batten are premium siding systems with strict '
            'manufacturer installation requirements. Learn fastening, flashing, and warranty implications.'
        ),
        'videos': [
            {'url': 'https://www.youtube.com/watch?v=IqtH1I6SBQQ', 'title': 'How to Install Hardie Siding'},
            {'url': 'https://www.youtube.com/watch?v=tSN21iIuDU0', 'title': 'Hardie Board and Batten'},
            {'url': 'https://www.youtube.com/watch?v=F3zXg9p_A8M', 'title': 'Vinyl Board and Batten'},
            {'url': 'https://youtu.be/kr2pyd8tLHI', 'title': 'Siding Install Secrets — Hardie'},
            {'url': 'https://www.youtube.com/watch?v=TcJiXlUK90Q', 'title': 'Manufacturer Specs on Hardie Install'},
        ],
        'shadowing': [
            'Shadow an experienced consultant on Hardie or board-and-batten jobs in condo properties.',
            'Visit projects where Hardie siding installation has happened or is in progress.',
        ],
        'additional': [
            {'type': 'video', 'url': 'https://www.youtube.com/watch?v=vXJ_vL4_vsA', 'title': 'The Power of Moments'},
        ],
        'pps_focus': [
            {
                'id': 'w7_lifecycle_mobilization',
                'title': 'Project lifecycle — Mobilization',
                'text': (
                    'Observe mobilization on an active job or debrief with a PM. Document the PSC role: client communication, '
                    'resident notice, Trade Partner arrival, and what gets escalated on day one.'
                ),
            },
            {
                'id': 'w7_focus_warranty',
                'title': 'Warranty language review',
                'text': 'Pull a Hardie siding proposal. Identify PPS warranty vs. manufacturer warranty sections.',
            },
        ],
        'manager_checkin': 'Why does improper Hardie install void manufacturer warranty?',
    },
    {
        'week': 8,
        'segment': 'Condos',
        'book': 'Fanatical Prospecting',
        'book_chapters': {
            'chapters': [
                {'num': 17, 'title': 'The Secret Lives of Gatekeepers'},
                {'num': 18, 'title': 'In-Person Prospecting'},
                {'num': 19, 'title': 'E-Mail Prospecting'},
                {'num': 20, 'title': 'Text Messaging'},
                {'num': 21, 'title': 'Developing Mental Toughness'},
                {'num': 22, 'title': 'Eleven Words That Changed My Life'},
                {'num': 23, 'title': 'The Only Question That Really Matters'},
            ],
            'discussion': 'Finish the book. Answer Chapter 23\'s question for yourself and share with your manager.',
        },
        'topic': 'Carpentry (Decks & Wood Replacement)',
        'topic_summary': (
            'Deck rebuilds and wood trim replacement are high-visibility scopes. Learn structural basics, '
            'material choices (wood vs. PVC/composite), and rot identification.'
        ),
        'videos': [
            {'url': 'https://www.youtube.com/watch?v=vuaFXAK06YI', 'title': 'How to Replace an Old Deck Step by Step'},
            {'url': 'https://www.youtube.com/watch?v=9aR8h_TgRss', 'title': 'Easiest Deck Build Ever | Step by Step'},
            {'url': 'https://www.youtube.com/watch?v=Z5s7NGb0cqw', 'title': 'Remodel Your Deck on a Budget | DIY Tutorial'},
            {'url': 'https://www.youtube.com/watch?v=PkvKO8GchyE', 'title': 'How to Build a Deck'},
            {'url': 'https://www.youtube.com/watch?v=jHZoDVB_AS8', 'title': 'Deck Building Series (full playlist)'},
            {'url': 'https://www.youtube.com/watch?v=eUzS5qkcdbM', 'title': 'Replacing Rotten Trim'},
            {'url': 'https://www.youtube.com/watch?v=UZYGw1nmWuo', 'title': 'PVC vs Wood Trim'},
        ],
        'shadowing': [
            'Shadow an experienced consultant on carpentry jobs in condo properties.',
            'Visit projects where deck installation or wood replacement has happened or is in progress.',
        ],
        'additional': [
            {'type': 'video', 'url': 'https://www.youtube.com/watch?v=wapajOJ8z1Q', 'title': 'Real vs Nominal Wood Sizes'},
            {'type': 'video', 'url': 'https://www.youtube.com/watch?v=bbu8lAQ4xDg', 'title': 'Wood Selection Basics'},
        ],
        'pps_focus': [
            {
                'id': 'w8_lifecycle_active',
                'title': 'Project lifecycle — Active job communication',
                'text': (
                    'On a job in progress, note how the PSC and PM coordinate updates with property management. '
                    'What does the client hear from you vs. production? Write three rules for yourself.'
                ),
            },
            {
                'id': 'w8_focus_condo_complete',
                'title': 'Condo segment recap',
                'text': 'Compare EIFS vs. vinyl vs. Hardie: when would you recommend each? Write a one-paragraph answer.',
            },
        ],
        'manager_checkin': 'Condo segment review — ready for hospitality/commercial?',
    },
    {
        'week': 9,
        'segment': 'Hospitality / Commercial',
        'book': 'The 4 Disciplines of Execution (2nd ed., rev. 2021)',
        'book_chapters': {
            **FOUR_DX_WEEKLY[0],
        },
        'topic': 'Remodels & Interior Renovation',
        'topic_summary': (
            'Hospitality and commercial remodels involve phasing, occupied spaces, and permit requirements. '
            'Week 9 begins the 4DX reading track — allow extra time alongside field training.'
        ),
        'videos': [
            {'url': 'https://www.youtube.com/watch?v=KnMe4LC22lc', 'title': 'Renovation Overview (DIY)'},
            {'url': 'https://www.youtube.com/watch?v=xcoCkq0CcrA', 'title': 'Worst Case Renovation (similar to Bridges-style projects)'},
            {'url': 'https://www.youtube.com/watch?v=LzvTmkNKm9U', 'title': '233 Apartment Reno'},
            {'url': 'https://www.youtube.com/watch?v=GwXjdZNkCR0', 'title': 'Quick Reno Overview'},
        ],
        'shadowing': [
            'Shadow an experienced consultant on remodel jobs in hospitality/commercial properties.',
            'Visit projects where an interior renovation has happened or is in progress.',
        ],
        'additional': [
            {'type': 'video', 'url': 'https://www.youtube.com/watch?v=vKNdNN03vw4', 'title': 'Construction Permits'},
        ],
        'pps_focus': [
            {
                'id': 'w9_lifecycle_change',
                'title': 'Project lifecycle — Change orders & T&M',
                'text': (
                    'Review a real change order or T&M scenario with your manager. Walk through: cease work, photos, '
                    'written approval, and how the PSC communicates scope additions to the client.'
                ),
            },
            {
                'id': 'w9_focus_permits',
                'title': 'Permit workflow',
                'text': 'Ask your PM: when does PPS pull permits vs. client? Document the answer for your market.',
            },
            {
                'id': 'w9_focus_4dx_start',
                'title': 'Start your 4DX reading log',
                'text': 'Keep a running doc of whirlwind vs. WIG examples from your shadowing. You will use this through Week 12.',
            },
        ],
        'manager_checkin': 'Remodel scope basics clear? 4DX Ch 1–4 complete?',
    },
    {
        'week': 10,
        'segment': 'Hospitality / Commercial',
        'book': 'The 4 Disciplines of Execution (2nd ed., rev. 2021)',
        'book_chapters': {
            **FOUR_DX_WEEKLY[1],
        },
        'topic': 'Pressure Washing & Gutter Cleaning',
        'topic_summary': (
            'Pressure washing and gutter cleaning are common hospitality/commercial scopes. '
            'Learn equipment, technique, and how these services are scoped and sold in commercial contexts.'
        ),
        'videos': [
            {'url': 'https://www.youtube.com/watch?v=R3CZw2xam40', 'title': 'Gutter Cleaning and Pressure Washing Business'},
            {'url': 'https://www.youtube.com/watch?v=X39Wdk9zVEk', 'title': 'How I Wash Gutters, Fascias and Soffits With a Pressure Washer'},
            {'url': 'https://www.youtube.com/watch?v=Mzbe7uUnphk', 'title': 'Pressure Washing — 2 Story Gutter Cleaning (Small Business)'},
        ],
        'shadowing': [
            'Shadow an experienced consultant (e.g. Adam) on pressure washing and gutter cleaning in hospitality/commercial properties.',
            'Goal: Master techniques for pressure washing and gutter cleaning in commercial/hospitality contexts.',
        ],
        'additional': [],
        'pps_focus': [
            {
                'id': 'w10_lifecycle_concealed',
                'title': 'Project lifecycle — Concealed conditions',
                'text': (
                    'Find an example of concealed conditions discovered mid-project. Document the PPS sequence: '
                    'stop work, photograph, notify client/management, written approval before proceeding.'
                ),
            },
            {
                'id': 'w10_focus_wig_draft',
                'title': 'Draft your 90-day WIG',
                'text': 'Using 4DX Ch 5–7, write a rough WIG in "from X to Y by when" format. Review with your manager.',
            },
        ],
        'manager_checkin': 'Can you scope a pressure washing / gutter cleaning job on a walkthrough?',
    },
    {
        'week': 11,
        'segment': 'Hospitality / Commercial',
        'book': 'The 4 Disciplines of Execution (2nd ed., rev. 2021)',
        'book_chapters': {
            **FOUR_DX_WEEKLY[2],
        },
        'topic': 'Estimating & Building Proposals',
        'topic_summary': (
            'Commercial estimating and proposal building are core PSC skills. '
            'This week pairs the hardest 4DX chapters with hands-on estimate and proposal shadowing.'
        ),
        'videos': [
            {'url': 'https://www.youtube.com/watch?v=paXn-Ff5LPA', 'title': 'Mastering Construction Estimation — A Beginner\'s Guide'},
            {'url': 'https://www.youtube.com/watch?v=6R-QkVe6Nfg', 'title': 'The Ultimate Construction Estimating Guide'},
            {'url': 'https://www.youtube.com/watch?v=42PcHNSOSEg', 'title': 'Construction Cost Estimating — Complete Guide'},
        ],
        'shadowing': [
            'Shadow an experienced consultant on estimating and proposal-building in hospitality/commercial properties.',
            'Goal: Assist in on-site estimates and learn to build proposals for commercial projects.',
        ],
        'additional': [],
        'pps_focus': [
            {
                'id': 'w11_lifecycle_punch',
                'title': 'Project lifecycle — Punch list & close-out',
                'text': (
                    'Shadow a punch walk or close-out with a PM. Note how remaining items get documented, '
                    'who signs off, and when the PSC reconnects with the client after production wraps.'
                ),
            },
            {
                'id': 'w11_focus_estimate_live',
                'title': 'Estimating track — Step 4: Assist on a live estimate',
                'text': (
                    'Join an experienced consultant on an on-site estimate. Take notes on measurements, scope decisions, '
                    'Trade Partner input, and what goes into the proposal. Debrief with your manager same week.'
                ),
            },
            {
                'id': 'w11_focus_scoreboard',
                'title': 'Build your scoreboard',
                'text': 'Define 2–3 lead measures for your WIG. Track them weekly in Monday.com — simple, visible, shows if you are winning.',
            },
            {
                'id': 'w11_focus_proposal',
                'title': 'Commercial proposal review',
                'text': 'Pull a hospitality/commercial proposal from hub history. Identify scope structure, phasing language, and investment framing.',
            },
        ],
        'manager_checkin': '4DX Ch 8–11 complete? WIG and lead measures approved?',
    },
    {
        'week': 12,
        'segment': 'Hospitality / Commercial',
        'book': 'The 4 Disciplines of Execution (2nd ed., rev. 2021)',
        'book_chapters': {
            **FOUR_DX_WEEKLY[3],
        },
        'topic': 'Prospecting & Graduation',
        'topic_summary': (
            'Finish 4DX and demonstrate commercial prospecting skills. '
            'Graduation week: present your 90-day WIG, lead measures, and readiness for independent client-facing work.'
        ),
        'videos': [
            {'url': 'https://www.youtube.com/watch?v=Hls3vpyAYAo', 'title': 'Prospecting Masterclass — How To Get More Listings Fast'},
            {'url': 'https://www.youtube.com/watch?v=iFYGB5bBH94', 'title': 'Prospecting Tips Every Salesperson Should Know'},
            {'url': 'https://www.youtube.com/watch?v=8IP4_3jAjyU', 'title': 'Prospecting Tips for Effective Real Estate Sales'},
        ],
        'shadowing': [
            'Shadow an experienced consultant on prospecting activities in hospitality/commercial properties.',
            'Goal: Observe and practice sales prospecting techniques for acquiring new commercial clients.',
            'Lead a site visit walkthrough with your manager observing (you drive, they coach).',
        ],
        'additional': [],
        'pps_focus': [
            {
                'id': 'w12_lifecycle_recap',
                'title': 'Project lifecycle — Full recap',
                'text': (
                    'Write the lifecycle in your own words: site visit → proposal → award → PPM → mobilization → '
                    'active job → change order → punch/close-out. Identify where the PSC leads vs. supports the PM.'
                ),
            },
            {
                'id': 'w12_focus_estimate_lead',
                'title': 'Estimating track — Step 5: Lead a walkthrough',
                'text': (
                    'Lead a site visit walkthrough with your manager observing. You drive scope conversation, '
                    'photos, and notes. Debrief on what you would put in a proposal.'
                ),
            },
            {
                'id': 'w12_focus_graduation',
                'title': 'Graduation presentation',
                'text': '10-minute presentation: one trade mastered, one still developing, your 90-day WIG, lead measures, and scoreboard.',
            },
            {
                'id': 'w12_focus_cadence',
                'title': 'Commit to weekly accountability',
                'text': 'Schedule a recurring 30-minute WIG session with your manager for your first 90 days post-graduation.',
            },
            {
                'id': 'w12_focus_continuous',
                'title': 'Continuous learning — after graduation',
                'text': (
                    'Onboarding is the start, not the finish. Commit to: monthly proposal review with manager, '
                    'one post-project debrief per quarter, and contributing one lesson learned to the team '
                    '(Ask PPS or manager capture).'
                ),
            },
        ],
        'manager_checkin': (
            'Final graduation sign-off — partner-project log reviewed, 90-day WIG approved, '
            'VP Sales + President notified. Schedule first post-graduation coaching cadence.'
        ),
    },
]


def _assign_ids(week_data):
    """Attach stable item IDs for progress tracking."""
    w = week_data['week']
    for i, v in enumerate(week_data.get('videos', [])):
        v['id'] = f'w{w}_video_{i}'
    for i, s in enumerate(week_data.get('shadowing', [])):
        if isinstance(s, str):
            week_data['shadowing'][i] = {'id': f'w{w}_shadow_{i}', 'text': s}
        elif isinstance(s, dict) and 'id' not in s:
            s['id'] = f'w{w}_shadow_{i}'
    for i, a in enumerate(week_data.get('additional', [])):
        if 'id' not in a:
            a['id'] = f'w{w}_additional_{i}'
    for item in week_data.get('pps_focus', []):
        if 'id' not in item:
            item['id'] = f'w{w}_focus_{item["title"][:20].lower().replace(" ", "_")}'
    if week_data.get('book') or week_data.get('book_chapters'):
        week_data['book_id'] = f'w{w}_book'
    if week_data.get('manager_checkin'):
        week_data['checkin_id'] = f'w{w}_checkin'
    return week_data


def _prepare_core_values():
    data = dict(PSC_CORE_VALUES)
    sections = []
    for section in data['sections']:
        sec = dict(section)
        activities = []
        for i, act in enumerate(sec.get('activities', [])):
            item = dict(act)
            if 'id' not in item:
                item['id'] = f"{sec['id']}_{i}"
            activities.append(item)
        sec['activities'] = activities
        sections.append(sec)
    data['sections'] = sections
    return data


def _prepare_sales_training():
    """NOTE: these IDs are derived from `item['title']`, so renaming an item
    renames its ID and orphans every progress row pointing at it. Frozen by
    tests/test_training_item_ids.py — when the editor lands, each item needs an
    explicit `id` in the source before its title becomes editable.

    `dict()` here was shallow, so the loop below wrote ids into the module-level
    PSC_SALES_TRAINING. Deep-copied now.
    """
    data = copy.deepcopy(PSC_SALES_TRAINING)
    for module in data['modules']:
        for item in module['items']:
            if 'id' not in item:
                item['id'] = f"sales_{module['id']}_{item['title'][:12].lower().replace(' ', '_')}"
    return data


def _prepare_company_operations():
    data = dict(PSC_COMPANY_OPERATIONS)
    modules = []
    for module in data['modules']:
        mod = dict(module)
        items = []
        for i, item in enumerate(mod.get('items', [])):
            row = dict(item)
            if 'id' not in row:
                row['id'] = f"{mod['id']}_{i}"
            items.append(row)
        mod['items'] = items
        modules.append(mod)
    data['modules'] = modules
    return data


@lru_cache(maxsize=1)
def _prepared_curriculum():
    """Build the ID-assigned curriculum once per process.

    `_assign_ids` writes into whatever it is handed, and it used to be handed
    `dict(w)` — a shallow copy whose `videos` and `shadowing` lists were the
    module-level ones. Reading the curriculum therefore rewrote it. Deep-copying
    here makes the source read-only, which is the precondition for the training
    editor's overlay: an overlay that appended into the module globals would
    grow them on every page load for the life of the worker.
    """
    onboarding = _assign_ids(copy.deepcopy(PSC_ONBOARDING))
    weeks = [_assign_ids(copy.deepcopy(w)) for w in PSC_TRAINING_WEEKS]
    core_values = _prepare_core_values()
    sales_training = _prepare_sales_training()
    company_operations = _prepare_company_operations()
    return onboarding, weeks, core_values, sales_training, company_operations


def get_training_curriculum():
    """Full curriculum with IDs assigned. The caller owns the result.

    Deep-copied out of the cache so a template filter, a future overlay, or a
    careless caller cannot write back into the shared prepared copy and have it
    persist for every later request on this worker.
    """
    return copy.deepcopy(_prepared_curriculum())


def get_all_item_ids():
    """Flat list of every trackable item ID.

    Reads the cached structure directly rather than through
    `get_training_curriculum()` — it only reads strings, and this is called on
    every dashboard load via `compute_psc_training_stats`, twice.
    """
    onboarding, weeks, core_values, sales_training, company_operations = _prepared_curriculum()
    ids = []

    def collect(week_data):
        for v in week_data.get('videos', []):
            ids.append(v['id'])
        for s in week_data.get('shadowing', []):
            ids.append(s['id'] if isinstance(s, dict) else s)
        for a in week_data.get('additional', []):
            ids.append(a['id'])
        for f in week_data.get('pps_focus', []):
            ids.append(f['id'])
        if week_data.get('book_id'):
            ids.append(week_data['book_id'])

    for section in core_values['sections']:
        for act in section.get('activities', []):
            ids.append(act['id'])
    for module in company_operations['modules']:
        for item in module['items']:
            ids.append(item['id'])
    for module in sales_training['modules']:
        for item in module['items']:
            ids.append(item['id'])
    collect(onboarding)
    for w in weeks:
        collect(w)
    return ids


def read_curriculum():
    """The cached, ID-assigned curriculum **for reading only**.

    `get_training_curriculum()` deep-copies on every call — right for anything
    that renders or transforms, wrong for the several helpers that just walk the
    structure pulling out IDs and check-in strings. `compute_psc_training_stats`
    reaches three of those on every dashboard load, so the copies added up to
    real milliseconds for no benefit.

    **Do not mutate what this returns.** It is the shared per-process cache, and
    a write here persists for every later request on this worker — the exact
    failure the deep-copying was introduced to prevent. If you need to change
    anything, call `get_training_curriculum()` and change your own copy.
    """
    return _prepared_curriculum()


def get_week_checkin_questions():
    """{week_number: manager check-in question}. Read-only path."""
    onboarding, weeks, _, _, _ = _prepared_curriculum()
    questions = {}
    if onboarding.get('manager_checkin'):
        questions[0] = onboarding['manager_checkin']
    for w in weeks:
        if w.get('manager_checkin'):
            questions[w['week']] = w['manager_checkin']
    return questions


def get_week_labels():
    """{week_number: 'Week 3 · Flooring'}. Read-only path."""
    onboarding, weeks, _, _, _ = _prepared_curriculum()
    labels = {0: onboarding.get('title', 'Week 0 · PPS Foundations')}
    for w in weeks:
        labels[w['week']] = f"Week {w['week']} · {w['topic']}"
    return labels


def count_trackable_items():
    return len(get_all_item_ids())


# ── Role-play practice (PSC Training → Practice Arena) ─────────────────────────

PSC_ROLEPLAY_GRADER_RULES = """
PPS UNIVERSAL LANGUAGE (grade strictly):
- "residents" not "tenants" | "apartment community" not "complex"
- "ownership" or "ownership/management" not "the owner"
- "Trade Partners" not "subcontractors" or "subs"
- "homeowners" not "tenants" in condo/HOA context
- "concealed conditions" not "hidden damage"
- Active voice; lead with "PPS will…"
- Never: "is committed to" / "strives to" / "is pleased to present" / "looks forward to" /
  "we are excited to" / "it is important to note" / "please be advised"

CONDO vs APARTMENT TONE:
- Apartments: clinical, efficient, operationally precise
- Condos/HOA: warm, explanatory, connect scope to homeowner value — board-meeting ready language
- Hospitality: guests (not residents), business continuity, brand standards, minimal guest disruption
"""

PSC_ROLEPLAY_SCENARIOS = [
    {
        'id': 'rp_skeptical_pm',
        'title': 'The Cheaper Bid',
        'week_link': 4,
        'segment': 'Apartments',
        'difficulty': 'Core',
        'grader_focus': (
            'Weight discovery and value_communication highest. Trainee must uncover what the cheaper bid '
            'includes before defending PPS scope. Discounting or trashing the competitor should tank integrity.'
        ),
        'persona': (
            'You are Dana Whitfield, property manager of a 240-unit apartment community. '
            'You are busy, direct, and under budget pressure from your regional. You have a bid '
            'from another contractor that is 18% cheaper than the PPS proposal for exterior painting. '
            'You like PPS but need to justify the difference to ownership. Invent plausible details '
            'when asked — never reference real companies or people.'
        ),
        'opening_line': (
            "Thanks for coming by. I'll be straight with you — I've got another bid on my desk "
            "and it's a lot cheaper. Why shouldn't I just go with them?"
        ),
        'trainee_brief': (
            'Dana has a competing bid 18% below ours on the exterior painting project. '
            'Your objective: defend the PPS value without trashing the competitor or discounting on the spot. '
            'Uncover what the cheaper bid includes, connect scope differences to resident and ownership outcomes, '
            'and land a concrete next step.'
        ),
        'objectives': [
            'Ask discovery questions about what the competing bid actually covers',
            'Tie PPS scope/warranty/process to outcomes for residents and ownership',
            'Never bad-mouth the competitor or invent a discount',
            'Close on a specific next step (side-by-side scope review, ownership call, site walk)',
        ],
        'max_turns': 12,
    },
    {
        'id': 'rp_concealed_conditions',
        'title': 'Concealed Conditions Call',
        'week_link': 2,
        'segment': 'Apartments',
        'difficulty': 'Core',
        'grader_focus': (
            'Integrity is the hard gate. Any promise of extra work, pricing, or proceeding without written '
            'approval must score integrity ≤ 2. Weight clear documentation and stop-work protocol.'
        ),
        'persona': (
            'You are Marcus Reed, property manager of a 180-unit garden-style apartment community. '
            'PPS crews are on site for siding repair. Your phone rang — the superintendent says they '
            'found rot behind siding that was not in scope. You are concerned about cost, resident '
            'perception, and timeline. You want answers now. Invent plausible details when asked.'
        ),
        'opening_line': (
            "Hey — my superintendent just called. Your crew found rot behind the siding that wasn't "
            "in the proposal. What's going on, and what am I looking at here?"
        ),
        'trainee_brief': (
            'You are on site (by phone). Crew found concealed rot not in scope. '
            'Explain what was found, what PPS will and will not do before written approval, '
            'photos/documentation, and that no additional work proceeds without sign-off.'
        ),
        'objectives': [
            'Explain what was discovered in plain language',
            'State clearly that work stops until written approval',
            'Describe photo documentation and next steps for scope change',
            'Never quote a price or promise extra work on the spot',
        ],
        'max_turns': 12,
    },
    {
        'id': 'rp_board_meeting',
        'title': 'The Board Meeting',
        'week_link': 6,
        'segment': 'Condos',
        'difficulty': 'Advanced',
        'grader_focus': (
            'Weight pps_voice highest — condo board tone (warm, explanatory, homeowner-value framing). '
            'Patience under detailed questions matters. Pitch-dumping or apartment-style clinical tone fails voice.'
        ),
        'persona': (
            'You are Carol Jennings, a detail-oriented HOA board member at a 42-unit condo association. '
            'You are at a special board meeting about a deck replacement project. You have reviewed the '
            'reserve study and the PPS proposal — the numbers do not match. You ask hard questions about '
            'special assessments, homeowner disruption, and why repair is not enough. Invent plausible details.'
        ),
        'opening_line': (
            "Thanks for joining us. I've got the reserve study and your proposal side by side — "
            "the numbers don't line up. Can you walk the board through why full replacement is necessary "
            "and what this means for homeowners?"
        ),
        'trainee_brief': (
            'Carol is a board member at a special meeting on deck replacement. '
            'Explain in plain language, connect scope to homeowner value, stay patient, '
            'and offer follow-up materials. Condo tone — not apartment clinical.'
        ),
        'objectives': [
            'Explain scope in homeowner-friendly language',
            'Address reserve study vs proposal gap honestly',
            'Connect work to long-term homeowner investment protection',
            'Offer follow-up (attend next meeting, written FAQ, phased options) without overpromising',
        ],
        'max_turns': 12,
    },
    {
        'id': 'rp_nervous_gm',
        'title': 'The Nervous GM',
        'week_link': 10,
        'segment': 'Hospitality / Commercial',
        'difficulty': 'Core',
        'grader_focus': (
            'Weight value_communication and next_step_close. Lead with business continuity — phasing, '
            'hours, guest experience. "Guests" not "residents." Scaffolding and brand-standard language expected.'
        ),
        'persona': (
            'You are Priya Nair, General Manager of a 140-key select-service hotel. PPS is proposing '
            'EIFS repair near the main entrance and pool deck. You are worried about guest experience, '
            'noise, scaffolding near the lobby, and passing brand-standard inspections. Invent plausible details.'
        ),
        'opening_line': (
            "I appreciate the proposal, but I'll be honest — I'm nervous. We've got peak season coming "
            "and your work is right by our main entrance. How do I know guests won't be walking through "
            "a construction zone?"
        ),
        'trainee_brief': (
            'Priya needs EIFS repair but fears guest disruption and brand inspection risk. '
            'Lead with business continuity: phasing, work hours, after-hours options, communication plan.'
        ),
        'objectives': [
            'Lead with guest experience and operational continuity',
            'Propose phasing, work hours, and communication to property leadership',
            'Address brand-standard / inspection concerns concretely',
            'Close on a site walk or phased plan review with GM and engineering',
        ],
        'max_turns': 12,
    },
    {
        'id': 'rp_schedule_slip',
        'title': 'Schedule Slip',
        'week_link': 3,
        'segment': 'Any',
        'difficulty': 'Advanced',
        'grader_focus': (
            'Weight integrity and value_communication. Owning the communication gap without blaming weather '
            'or production excuses. Concrete recovery plan and cadence required for next_step_close.'
        ),
        'persona': (
            'You are Tom Brooks, property manager overseeing a 320-unit apartment community. '
            'Weather pushed the roofing start twice and residents are complaining in the portal. '
            'You feel out of the loop and frustrated. You liked PPS until now. Invent plausible details.'
        ),
        'opening_line': (
            "I need to talk about the roof schedule. We've been pushed twice and I've got residents "
            "asking me what's going on. I didn't even know about the second delay until someone posted "
            "in the community Facebook group. Where are we?"
        ),
        'trainee_brief': (
            'Tom is frustrated: weather delays, poor communication, resident complaints. '
            'Own the gap without blaming production or weather excuses. Give a concrete recovery plan '
            'and communication cadence. Keep the relationship.'
        ),
        'objectives': [
            'Acknowledge the communication failure directly',
            'Provide a specific updated schedule or recovery plan',
            'Commit to a resident/management communication cadence',
            'Avoid blaming Trade Partners, weather, or other excuses',
        ],
        'max_turns': 12,
    },
    {
        'id': 'rp_cold_call',
        'title': 'Cold Call — Regional Manager',
        'week_link': None,
        'link_ref': 'sales',
        'segment': 'Any',
        'difficulty': 'Advanced',
        'grader_focus': (
            'Weight discovery and next_step_close highest. Three-minute attention span — pitch-dumping fails. '
            'Must ask about portfolio pain points before earning a site walk.'
        ),
        'persona': (
            'You are Alexis Grant, regional manager over nine multifamily properties in the metro. '
            'You do not know the caller well. You picked up but you have about three minutes before '
            'your next call. You are skeptical of cold outreach but open if they are relevant. '
            'Invent property names and portfolio details when asked — all fictional.'
        ),
        'opening_line': (
            "You've got about three minutes — I'm between calls. What do you need?"
        ),
        'trainee_brief': (
            'Alexis manages nine properties and gives you three minutes. '
            "Earn a site walk at one property. Ask about her portfolio's pain points — do not pitch-dump."
        ),
        'objectives': [
            'Open with relevance, not a company monologue',
            'Ask discovery questions about portfolio challenges',
            'Connect PPS capabilities to a specific pain point she names',
            'Close on a concrete site walk at one property',
        ],
        'max_turns': 12,
    },
]

_ROLEPLAY_BY_ID = {s['id']: s for s in PSC_ROLEPLAY_SCENARIOS}

ROLEPLAY_DAILY_GRADE_LIMIT = 10
ROLEPLAY_DAILY_TURN_LIMIT = 150

ROLEPLAY_SEGMENTS = ['Apartments', 'Condos', 'Hospitality / Commercial', 'Any']


def get_roleplay_scenario(scenario_id):
    return _ROLEPLAY_BY_ID.get(scenario_id)


def get_roleplay_week_links():
    """Map week_num -> [{id, title}, ...] for training page links."""
    by_week = {}
    for sc in PSC_ROLEPLAY_SCENARIOS:
        wl = sc.get('week_link')
        if wl is not None:
            by_week.setdefault(wl, []).append({'id': sc['id'], 'title': sc['title']})
    return by_week


def get_roleplay_sales_links():
    """Scenarios linked from the Sales Training ref-card."""
    return [
        {'id': sc['id'], 'title': sc['title']}
        for sc in PSC_ROLEPLAY_SCENARIOS
        if sc.get('link_ref') == 'sales'
    ]


def get_suggested_roleplay_ids(week_pcts):
    """Suggest 1–3 scenarios based on trainee's current week progress."""
    current = 0
    for w in week_pcts or []:
        if w.get('trainee_pct', 0) < 100:
            current = w['week']
            break
    else:
        if week_pcts:
            current = week_pcts[-1]['week']
    suggested = []
    for sc in PSC_ROLEPLAY_SCENARIOS:
        wl = sc.get('week_link')
        if wl is not None and abs(wl - current) <= 1:
            suggested.append(sc['id'])
    if not suggested:
        for sc in PSC_ROLEPLAY_SCENARIOS:
            if sc.get('difficulty') == 'Core':
                suggested.append(sc['id'])
                if len(suggested) >= 2:
                    break
    return suggested[:3]


def segment_color(segment_name):
    for seg in PSC_TRAINING_META['segments']:
        if seg['name'] == segment_name:
            return seg['color']
    if segment_name == 'Any':
        return '#004C8C'
    return '#004C8C'