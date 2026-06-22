"""PSC Onboarding — Property Solutions Consultant training curriculum."""

PSC_TRAINING_META = {
    'title': 'PSC Onboarding',
    'subtitle': 'Property Solutions Consultant Training Program',
    'description': (
        'A guided 9-week program covering PPS culture and voice, sales fundamentals, '
        'construction trades by property segment, field shadowing, and PPS tools.'
    ),
    'duration_weeks': 9,
    'segments': [
        {'name': 'Apartments', 'weeks': [1, 2, 3, 4], 'color': '#004C8C'},
        {'name': 'Condos', 'weeks': [5, 6, 7, 8], 'color': '#0096D6'},
        {'name': 'Hospitality / Commercial', 'weeks': [9], 'color': '#B8922A'},
    ],
}

PSC_CORE_VALUES = {
    'title': 'Core Values & PPS Voice',
    'intro': (
        'Every proposal, site conversation, and client email should sound like PPS. '
        'Study these standards before your first client-facing work and revisit them weekly.'
    ),
    'sections': [
        {
            'id': 'cv_why',
            'title': 'PPS Why',
            'content': 'We believe in elevating lives and spaces through relentless improvement and unbreakable trust.',
            'bullets': [
                'PPS is a capital expenditure partner — planning through close-out, not just a contractor.',
                'One point of contact across all trades streamlines communication for ownership and management.',
                'Every project reflects who we are: Trust. Quality. Results.™',
            ],
        },
        {
            'id': 'cv_brand',
            'title': 'Brand & Credentials',
            'content': 'Improving People. Improving Property.',
            'bullets': [
                'First mention: "Pure Property Solutions (PPS)" — then "PPS." Never "Pure Prop" or "Pure" alone.',
                'Tagline for closings: Trust. Quality. Results.™',
                '12+ years in business · $60M+ completed across 6 states · multi-family and commercial only.',
                'Management relationships: Morgan, Connor, Hills, Neyer, Towne. Trade Partners: many 8+ year relationships.',
                'PPM standard on every project. References available upon request.',
            ],
        },
        {
            'id': 'cv_pillars',
            'title': 'Why PPS — Three Pillars',
            'bullets': [
                'Multi-Family Expertise — operational experience, named management relationships, resident-aware execution.',
                'Experience & Stability — track record, long-term Trade Partner relationships, professional on-site standards.',
                'Comprehensive Services — single point of contact across all trades.',
            ],
        },
        {
            'id': 'cv_language',
            'title': 'Universal Language Rules',
            'bullets': [
                '"residents" not "tenants" · "apartment community" not "complex"',
                '"ownership" or "ownership/management" not "the owner"',
                '"Trade Partners" not "subcontractors" or "subs"',
                '"investment" not "cost/price" for totals · "homeowners" in condo/HOA context',
                '"T&M" not "hourly" · "concealed conditions" not "hidden damage"',
                '"Trade Partner Scope" not "sub scope" · "punch list" not "final items"',
                'Work hours: 8am–7pm M–F unless specified.',
            ],
        },
        {
            'id': 'cv_voice',
            'title': 'Voice & Tone',
            'content': 'Confident, direct, contractor-fluent, outcome-focused. NOT bureaucratic, passive, or filler-heavy.',
            'bullets': [
                'Active voice always. Lead with PPS: "PPS will remove and dispose of all existing roofing material."',
                'Universal opening: "Pure Property Solutions (PPS) will provide all labor, materials, equipment, and supervision necessary to complete [scope] as outlined below."',
                'Never use: "is committed to" / "strives to" / "is pleased to present" / "looks forward to" / "we are excited to" / "please be advised".',
                'Key phrase: "PPS will coordinate with property management and onsite staff to minimize disruption to residents."',
                'Key phrase: "If work extends beyond scope, PPS will cease work, document with photos, and reach out for written approval before proceeding."',
                'Key phrase: "A Pre-Project Meeting will be scheduled prior to mobilization."',
            ],
        },
        {
            'id': 'cv_property',
            'title': 'Property Type Tone',
            'bullets': [
                'Apartments — clinical, efficient, operationally precise. Prioritize resident disruption, phasing, communication protocols.',
                'Condos / HOAs — warm, trust-building, explanatory. Write for the Board. Connect scope to homeowner investment value.',
                'Hospitality — guest experience and brand standards first. Say "guests" not "residents."',
                'Commercial — business continuity first. ADA/code compliance. After-hours work when needed.',
            ],
        },
        {
            'id': 'cv_pricing',
            'title': 'Pricing Language',
            'bullets': [
                '"Investment" not "Cost/Price" for totals · "Base Contract Amount" for primary line.',
                'T&M: "Any work not included can be performed at agreed T&M rates."',
                'Multi-scope: "Pricing is contingent upon all scopes being awarded."',
                'Towne Condo/HOA ONLY: Towne Preferred Customer Discount (10%). Not apartments. Not non-Towne clients.',
                'Tariff clause: "Pricing is based on current market conditions. Due to potential tariff or supply chain fluctuations, PPS reserves the right to adjust pricing with prompt written notice."',
            ],
        },
    ],
}

PSC_SALES_TRAINING = {
    'title': 'PPS Sales Training',
    'intro': (
        'Use this section to build or sharpen sales skills. Work through it alongside your weekly trade training — '
        'especially prospecting weeks 5–8. Your manager can assign specific modules based on what you need.'
    ),
    'modules': [
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
                    'title': 'Generate, then refine',
                    'text': 'Use the Proposal Generator for PPS-standard language, then adjust for client context. Submit before/after edits via the Comparison Tool to improve our voice guide.',
                },
                {
                    'id': 'sales_prop_tool_2',
                    'title': 'Scope to investment',
                    'text': 'Help clients see scope as protecting their asset — not just a line-item cost. Use "investment" language and deferred-risk framing on condo work.',
                },
                {
                    'id': 'sales_prop_tool_3',
                    'title': 'Walk the client through it',
                    'text': 'Never email a proposal cold without context. Schedule a review call or meeting. Highlight phasing, warranties, and what happens at mobilization (PPM).',
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
            'id': 'w0_shadow_ride',
            'text': 'Ride along on one consultant site visit before Week 1 ends — observe how scope is discussed with property staff.',
        },
    ],
    'additional': [
        {
            'id': 'w0_add_monday',
            'type': 'video',
            'url': 'https://www.youtube.com/watch?v=EKiOeLSxDBA',
            'title': 'Monday.com Tutorial for Beginners (Step-by-Step)',
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
            'text': 'Generate a practice proposal (do not send to client). Study how PPS voice, scopes, and property type work together.',
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
            'id': 'w0_focus_core',
            'title': 'Complete Core Values & PPS Voice section',
            'text': 'Read every subsection above and check each item off before Week 1.',
        },
        {
            'id': 'w0_focus_vocab',
            'title': 'Start your scope vocabulary list',
            'text': 'Begin a personal glossary: tuck pointing, EIFS, B&B, mobilization, punch list, change order. Add terms each week.',
        },
    ],
    'manager_checkin': 'Confirm Week 0 complete before starting trade-specific training.',
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
                'id': 'w1_focus_proposal',
                'title': 'Review a painting proposal in the vault',
                'text': 'Find a recent painting proposal in hub history. Identify scope language, unit counts, and warranty terms.',
            },
            {
                'id': 'w1_focus_identify',
                'title': 'Photo challenge',
                'text': 'On site, photograph 3 examples of paint failure (peeling, chalking, lap marks). Note likely cause.',
            },
        ],
        'manager_checkin': 'Can you explain prep vs. finish coat to a property manager in plain language?',
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
                'id': 'w2_focus_tps',
                'title': 'Understand Trade Partner Scope handoff',
                'text': 'After shadowing a roof job, review the Trade Partner Scope document for that trade. Note crew-ready language.',
            },
        ],
        'manager_checkin': 'Can you describe the difference between a repair scope and a full re-roof?',
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
                'id': 'w3_focus_objections',
                'title': 'Practice objection handling',
                'text': 'Role-play: "Your price is higher than the last vendor." Use the Sales Objections video and PPS Sales Training module.',
            },
        ],
        'manager_checkin': 'Can you spot failed mortar joints vs. efflorescence on a walkthrough?',
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
        ],
        'pps_focus': [
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
        'book': 'The 4 Disciplines of Execution',
        'book_chapters': {
            'chapters': [
                {'num': 1, 'title': 'The Challenge'},
                {'num': 2, 'title': 'Discipline 1 — Focus on the Wildly Important'},
                {'num': 3, 'title': 'Discipline 2 — Act on Lead Measures'},
                {'num': 4, 'title': 'Discipline 3 — Keep a Compelling Scoreboard'},
                {'num': 5, 'title': 'Discipline 4 — Create a Cadence of Accountability'},
            ],
            'discussion': 'Define your 90-day WIG (Wildly Important Goal) and lead measures. Review in graduation check-in.',
        },
        'topic': 'Remodels & Interior Renovation',
        'topic_summary': (
            'Hospitality and commercial remodels involve phasing, occupied spaces, and permit requirements. '
            'Learn renovation scope structure and how PPS handles complex interior projects.'
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
                'id': 'w9_focus_permits',
                'title': 'Permit workflow',
                'text': 'Ask your PM: when does PPS pull permits vs. client? Document the answer for your market.',
            },
            {
                'id': 'w9_focus_graduation',
                'title': 'Graduation prep',
                'text': 'Prepare a 10-minute presentation: one trade you mastered, one still developing, and your 90-day WIG.',
            },
        ],
        'manager_checkin': 'Final graduation review — sign-off for independent client-facing work.',
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
    for section in data['sections']:
        section['check_id'] = section['id']
    return data


def _prepare_sales_training():
    data = dict(PSC_SALES_TRAINING)
    for module in data['modules']:
        for item in module['items']:
            if 'id' not in item:
                item['id'] = f"sales_{module['id']}_{item['title'][:12].lower().replace(' ', '_')}"
    return data


def get_training_curriculum():
    """Return full curriculum with IDs assigned."""
    onboarding = _assign_ids(dict(PSC_ONBOARDING))
    weeks = [_assign_ids(dict(w)) for w in PSC_TRAINING_WEEKS]
    core_values = _prepare_core_values()
    sales_training = _prepare_sales_training()
    return onboarding, weeks, core_values, sales_training


def get_all_item_ids():
    """Flat list of every trackable item ID."""
    onboarding, weeks, core_values, sales_training = get_training_curriculum()
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
        if week_data.get('checkin_id'):
            ids.append(week_data['checkin_id'])

    for section in core_values['sections']:
        ids.append(section['check_id'])
    for module in sales_training['modules']:
        for item in module['items']:
            ids.append(item['id'])
    collect(onboarding)
    for w in weeks:
        collect(w)
    return ids


def count_trackable_items():
    return len(get_all_item_ids())