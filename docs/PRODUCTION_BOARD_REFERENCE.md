# Monday.com & Production Board — Operational Reference

**Source:** Monday.com export (`Production_Board_1782990846.xlsx`), July 2026  
**Purpose:** How PPS uses Monday.com — PSC pipeline and PM production. Used for PSC Training (`ops_monday`), PM Training, Ask PPS, and Hub recommendations.  
**Code:** `production_board_reference.py`

## Monday.com is shared — PSC and PM

Monday.com is **not PM-only**. PSCs and PMs both live there, in different ways:

| Role | When | What you own on Monday |
|------|------|------------------------|
| **PSC** | Pre-award | Pipeline, contacts, properties, follow-up dates, outreach, site visits, proposals sent |
| **PM** | Post-award | **Production Board** — schedule, Trade Partners, PPM, Updates, margins, status groups |

**Training paths:**
- **PSC:** Week 0 Company Operations → `ops_monday` (Monday.com at PPS) in `psc_training_data.py`
- **PM:** Week 1 Production Board deep-dive in `pm_training_data.py`

**Handoff at award:** Job lands on the Production Board. **Consultant** = PSC who sold it. **Project Manager** = field execution owner. PSC stays the relationship point of contact; PM owns mobilization through close-out.

## Production Board (post-award)

The **Production Board** is the system of record for every **awarded** job. One row per project.

Export sheets:

| Sheet | Purpose |
|-------|---------|
| **production board** | Master job record |
| **updates** | Operational thread — draws, files, @mentions (PSCs, PMs, and office) |
| **Time tracking** | Per-job time entries |

### Production flow

```
Site visit → Proposal → Review call → Award → Production Board row
  → PPM → TPS → Needs Scheduled → Scheduled → In Progress
  → close-out walks → invoicing → margins → Completed - Final
```

### Status groups

| Group | Meaning |
|-------|---------|
| **Awarded - On Hold** | Awarded; complete board data, run PPM |
| **Needs Scheduled** | Ready to schedule — timelines, Trade Partner |
| **Scheduled** | Start confirmed — 48-hour notice, access |
| **In Progress** | Active field work |
| **Call Backs/ Warranty Work** | Return visits |
| **Completed Needs Internal Walk** | Internal punch |
| **Completed Needs Customer Walk** | Client walkthrough pending |
| **ON HOLD - MISSING INFORMATION** | Missing columns/docs |
| **Needs Invoiced - All Information Entered** | Ready to invoice |
| **Invoiced - Needs Approved** | Invoice out |
| **Waiting on Margins** | Financial close-out backlog |
| **Completed - Final** | Fully closed |
| **Completed Call Backs** | Warranty resolved |

### Key columns

**People:** Consultant (PSC), Project Manager, Support PM  
**Identity:** Name, Proposal Number, Trade, Company Type, Mgmt Company, City, Location, Customer Name, Email  
**Timeline:** Date Awarded, Estimated Timeline - Start/End, Check in Date  
**Hub docs:** Survey, PPM, Files  
**Financial:** Job Size, Estimated margin %, Supply/Sub/Overhead Cost, Actual margin $, Margin %, Quarter Invoiced  
**Trade Partners:** Sold to Sub, Sub Contract $, Sub Assigned, Sub Compliance, link to Pay Request (TPS maps here — no separate TPS column)

### Hub → Production Board

| Hub tool | Fields | When |
|----------|--------|------|
| Proposal Generator | Proposal Number, Files, Job Size, Trade… | At award |
| Site Visit | Survey, Files | When survey exists |
| PPM | PPM | Before mobilization |
| TPS | Sub Assigned, Sub Contract $, Sold to Sub… | Trade Partner assigned |

## PM morning checklist (Production Board)

1. Open Production Board → filter **Project Manager** = you  
2. Scan **In Progress** → **Scheduled** → **Needs Scheduled** → **Awarded - On Hold**  
3. Read **Updates** on active jobs  
4. Confirm **Estimated Timeline - Start/End**  
5. Clear **ON HOLD - MISSING INFORMATION**  
6. Post an **Update** on any job with movement today  

## PSC Monday hygiene (pre-award)

Log every meaningful touch — calls, site visits, proposals, follow-ups. Weekly cadence with your manager. At award, ensure Proposal Number and client data hand off cleanly to the Production Board row.

## Owners

| Area | Owner |
|------|--------|
| PSC Monday / pipeline | Tony Cumella |
| Production Board SOPs | Trey Hollmeyer |
| Hub tools & reference | Thomas Ellison |

*Last updated: July 2026*