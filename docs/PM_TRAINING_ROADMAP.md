# PM Training — Roadmap & Seed Content

**Source:** PM field feedback — July 2026 (informal requests from active PMs).  
**Stance:** Starting point, not final SOP. Validate with Trey and senior PMs before rollout.  
**Data file:** `pm_training_data.py` (seed only — not exposed in Hub UI yet).

## What PMs asked for (captured)

### Week 1 — Shadow & orientation

- **Shadowing** — see a typical day-to-week flow and what to expect before owning work.
- **Monday.com** — checklist for navigation and order of operations.
- **Communication** — all avenues PPS uses; how and where to find contacts.

### Week 2 — Route & operating system

- **Route planning** — build a system that works for them to operate effectively.
- **Trade Partners** — contacting subs and communicating through jobs (PPS voice: Trade Partners).
- **Expectations** — what they hold themselves and crews accountable to as a PM.
- **Time management** — balance site time with estimates, vendor/subs follow-up, materials, and email.

## Current status

| Item | Status |
|------|--------|
| Seed curriculum in `pm_training_data.py` | Done |
| Hub `/pm-training` page | Not built |
| Progress tracking / enrollment tables | Not built |
| Manager accountability (Trey oversight view) | Not built |
| Production Board reference (`production_board_reference.py`, `docs/PRODUCTION_BOARD_REFERENCE.md`) | Done |
| PM Training Week 1 — Production Board language & checklists | Done |
| Monday.com checklist SOPs (screenshots/Loom) | `[TO DOCUMENT]` |
| Contact directory / communication examples | `[TO DOCUMENT]` |
| Route template & time-budget samples | `[TO DOCUMENT]` |

## Future module (mirror PSC Training)

When ready to ship, reuse the PSC Training patterns in `app.py`:

1. **Enrollment** — `pm_training_enrollment` table; enroll on PM start date.
2. **Progress** — checkbox completion per item ID from `get_pm_training_item_ids()`.
3. **Notes** — per-week trainee notes.
4. **Manager sign-offs** — weekly check-in questions already seeded in week data.
5. **Dashboard card** — show for enrolled PMs (like PSC Training card).
6. **Oversight view** — Trey (or delegate) sees cohort progress and graduation.

Suggested accountability owner: **Trey Hollmeyer** (`PM_TRAINING_MANAGER` in data file).

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

- Weeks 3+ curriculum (callbacks, change orders, close-out, estimating depth).
- Ask PPS integration for PM-specific SOP gaps.
- Graduation criteria and manager rubric.

## Owners (suggested)

| Area | Owner |
|------|--------|
| Production SOPs, Trade Partner standards | Trey |
| Monday.com workflows & boards | Trey + Thomas |
| Hub module, data, Ask PPS | Thomas |
| PM expectations & route norms | Trey + senior PMs |

*Last updated: July 2026*