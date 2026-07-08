# Production Board — Operational Reference

**Source:** Monday.com export (`Production_Board_1782990846.xlsx`), July 2026  
**Purpose:** How PPS runs production after award. Used for PM Training, Ask PPS, and Hub recommendations.  
**Code:** `production_board_reference.py`

## What it is

The **Production Board** on Monday.com is PPS’s system of record for every **awarded** job. One row per project. It tracks people, Hub documents, Trade Partners, timelines, margins, and workflow status from mobilization through invoicing and close-out.

The export includes three sheets:

| Sheet | Purpose |
|-------|---------|
| **production board** | Master job record |
| **updates** | Operational thread — draws, files, @mentions |
| **Time tracking** | Per-job time entries |

## Production flow (where the board sits)

```
Site visit → Proposal → Review call → Award → Production Board row
  → PPM → TPS → Needs Scheduled → Scheduled → In Progress
  → close-out walks → invoicing → margins → Completed - Final
```

## Status groups

Jobs move through these groups (typical progression):

| Group | PM meaning |
|-------|------------|
| **Awarded - On Hold** | Awarded; not ready to schedule — complete board data, run PPM |
| **Needs Scheduled** | Ready to schedule — set timelines, confirm Trade Partner |
| **Scheduled** | Start date confirmed — 48-hour notice, access |
| **In Progress** | Active field work — Updates on milestones |
| **Call Backs/ Warranty Work** | Return visits |
| **Completed Needs Internal Walk** | Internal punch before client |
| **Completed Needs Customer Walk** | Client walkthrough pending |
| **ON HOLD - MISSING INFORMATION** | Stalled — missing columns/docs |
| **Needs Invoiced - All Information Entered** | Ready to invoice |
| **Invoiced - Needs Approved** | Invoice out — awaiting approval |
| **Waiting on Margins** | Financial close-out backlog |
| **Completed - Final** | Fully closed |
| **Completed Call Backs** | Warranty work resolved |

## Key columns (proper Monday language)

### People
- **Consultant** — PSC who sold the job
- **Project Manager** — owns the row
- **Support PM** — optional second PM

### Identity
- **Name**, **Proposal Number**, **Trade**, **Company Type**, **Mgmt Company**, **VC**, **City**, **Location**, **Customer Name**, **Email**

### Timeline
- **Date Awarded**, **Estimated Timeline - Start**, **Estimated Timeline - End**, **Check in Date**

### Hub documents
- **Survey** — site visit link
- **PPM** — Yes/No + Pre-Project Meeting checklist from Hub
- **Files** — proposal, scope, project docs
- **monday Doc v2** — Monday doc when used

### Financial
- **Job Size**, **Estimated margin %**, **Supply Cost**, **Sub Cost**, **Overhead Cost**, **Actual margin $**, **Margin %**, **Quarter Invoiced**

### Trade Partners (TPS lives here — no separate TPS column)
- **Sold to Sub**, **Sub Contract $**, **Sub Assigned**, **Sub Compliance**, **Sub Responsible for Material**, **link to Pay Request**

## Hub tool → Monday mapping

| Hub tool | Production Board fields | When |
|----------|-------------------------|------|
| Proposal Generator | Proposal Number, Files, Job Size, Trade, Company Type, Mgmt Company | At award |
| Site Visit | Survey, Files | When survey exists |
| PPM Checklist | PPM | After award, before mobilization |
| TPS (Trade Partner Scope) | Sub Assigned, Sub Contract $, Sold to Sub, link to Pay Request | When Trade Partner assigned |

## Updates

The **updates** sheet is the operational conversation log. PMs and office post phase draw schedules, deposit breakdowns, PDFs, and @mentions. If something important happens on a job, post it on the item **Updates** thread — not only in email or text.

## PM morning checklist

1. Open Production Board → filter to **Project Manager** = you  
2. Scan **In Progress** → **Scheduled** → **Needs Scheduled** → **Awarded - On Hold**  
3. Read recent **Updates** on active jobs  
4. Confirm **Estimated Timeline - Start/End**  
5. Clear **ON HOLD - MISSING INFORMATION** (common gaps: PPM, Sub Assigned, Proposal Number)  
6. Post an **Update** on any job with movement today  

## Owners

| Area | Owner |
|------|--------|
| Production SOPs, board hygiene | Trey Hollmeyer |
| Hub tools (PPM, TPS, Proposal) | Thomas Ellison |
| PM Training Week 1 board content | `pm_training_data.py` |

*Last updated: July 2026*