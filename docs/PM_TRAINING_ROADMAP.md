# PM Training — Roadmap & Seed Content

**Source:** PM field feedback — July 2026 (informal requests from active PMs).  
**Stance:** Starting point, not final SOP. Validate with Trey and senior PMs before rollout.  
**Data file:** `pm_training_data.py`, live in the Hub at `/pm-training`.

## What PMs asked for (captured)

### Week 1 — Shadow & orientation

- **Shadowing** — see a typical day-to-week flow and what to expect before owning work.
- **Monday.com** — Production Board deep-dive (PSCs learn shared Monday in PSC Training `ops_monday` first).
- **Communication** — all avenues PPS uses; how and where to find contacts.

### Week 2 — Route & operating system

- **Route planning** — build a system that works for them to operate effectively.
- **Trade Partners** — contacting subs and communicating through jobs (PPS voice: Trade Partners).
- **Expectations** — what they hold themselves and crews accountable to as a PM.
- **Time management** — balance site time with estimates, vendor/subs follow-up, materials, and email.

## Current status

| Item | Status |
|------|--------|
| Seed curriculum in `pm_training_data.py`, Weeks 1–4 | Done (`c3fa97c`, 2026-07-28) |
| Hub `/pm-training` page | Built (`app.py:5995`) |
| Progress tracking / enrollment tables (`pm_training_progress`, `_notes`, `_feedback`, `_enrollment`, `_manager_signoffs`) | Built (`app.py:1043-1092`, API routes `app.py:6024-6165`) |
| Manager accountability (Trey oversight view) | Built (`/pm-training/oversight` + `/admin/pm-training` alias, `app.py:6087,6116`) |
| Production Board reference (`production_board_reference.py`, `docs/PRODUCTION_BOARD_REFERENCE.md`) | Done |
| PM Training Week 1 — Production Board language & checklists | Done |
| **Week 5 (4DX for production: WIG / lead measures / scoreboard / production-meeting cadence)** | Product-designed, **not built in code** — blocked on Trey's input, see below |
| Monday.com checklist SOPs (screenshots/Loom) | `[TO DOCUMENT]` (`pm_training_data.py:146`) |
| Contact directory / communication examples | `[TO DOCUMENT]` (`pm_training_data.py:194,203,212,221`) |
| Route template & time-budget samples | `[TO DOCUMENT]` (`pm_training_data.py:266,329`, `TBD` at line 339) |

## Shipped module (2026-07-28, `c3fa97c`)

Built by mirroring the PSC Training patterns in `app.py`:

1. **Enrollment** — `pm_training_enrollment` table; enroll on PM start date.
2. **Progress** — checkbox completion per item ID from `get_pm_training_item_ids()`.
3. **Notes** — per-week trainee notes.
4. **Manager sign-offs** — weekly check-in questions already seeded in week data.
5. **Dashboard card** — shows for enrolled PMs (like PSC Training card).
6. **Oversight view** — Trey (or delegate) sees cohort progress and graduation.

Accountability owner: **Trey Hollmeyer** (`PM_TRAINING_MANAGER` in data file).

The `[TO DOCUMENT]` bullets above and Week 5 content still need Trey's actual input — don't invent SOP/route/contact content to fill them in.

## Content to add before launch

### High impact

- Monday.com order-of-operations checklist (screenshots or Loom).
- Trade Partner communication scripts by job phase (mobilization, in-progress, punch).
- PM expectations one-pager (response time, photos, escalation).
- Sample weekly calendar: site blocks vs. desk blocks.

### Medium impact

- Central contact reference (consultants, preferred Trade Partners, key vendors).
- Route-planning template (geography, drive-by vs. scheduled visit rules).
- Link to Hub tools PMs touch daily: PPM, TPS, Estimating.

### Lower priority

- Ask PPS integration for PM-specific SOP gaps.
- Graduation criteria and manager rubric.
- Week 5 (4DX for production) — still needs Trey's input before it can be written into `pm_training_data.py`.

## Owners (suggested)

| Area | Owner |
|------|--------|
| Production SOPs, Trade Partner standards | Trey |
| Monday.com workflows & boards | Trey + Thomas |
| Hub module, data, Ask PPS | Thomas |
| PM expectations & route norms | Trey + senior PMs |

*Last updated: July 2026*
*Last reconciled against shipped code: 2026-08-04*