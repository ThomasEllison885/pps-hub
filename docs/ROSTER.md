# Roster protocol

**Hub `USERS` in `app.py` is the only live list.** Adding a person without a
role is not allowed — the app will not boot. Dropdowns on TPS, PPM, and login
must follow this list. History (proposal_log, PPM, TPS files already made)
keeps the name that was on the work.

## Add someone

Do not commit until every item has a value. Role is not optional.

1. **Required on the `USERS` row:** `user_key`, `display`, **`role`**, `tier`,
   `title`, `email`. Role must be one of `admin`, `consultant`, `pm`,
   `office_manager`.
2. **Login** comes from that row. `init_db` seeds `hub_users` with an unusable
   password. Send *that person* Forgot Password. Do **not** run the
   all-hands password campaign.
3. **Dashboard lane** (`dashboard_lanes.py`): jobs PMs → Production first.
   Consultants usually Sales first. Ask if unsure (Trey is a PM who stays
   Sales-first on purpose).
4. **Pipeline assignment** (`PRIMARY_PM_FOR_CONSULTANT`): a PM is paired with
   a consultant or left unpaired on purpose. A consultant who needs a board
   is in `BOARD_CONSULTANTS`.
5. **Proposal numbers** (`PROPOSAL_NUMBER_INITIALS`) only for people who
   generate proposals (consultants / admin).
6. **Proposal-tool short keys** (`CONSULTANTS`, `CONSULTANT_KEY_MAP`) only if
   they appear on the proposal form dropdown.
7. TPS / PPM dropdowns **do not get hand-edited HTML**. They load
   `/api/roster`. A PM added here with `role: pm` shows on TPS after Hub
   deploy, without a proposal-tool HTML change.

Call the person what they will see on the login list. Two Andys: Baur vs Potts.

## Remove someone

Deleting the `USERS` row only stops login. The same person is copied into
other lists, and those lists do not read `USERS`. That is why someone is
still on a dropdown after they have been "taken off." Walk every line.
Two repos. History is a different list and is not cleared.

Thomas, 2026-11-20: every time someone leaves they are still somewhere.
This is the full pass. Search both repos for the display name, the
`user_key`, and the proposal-form short key (`tony` for Tony Cumella)
before calling it done.

### Take them off

These are choices, logins, and labels that say they still work here.

**Hub (`pps-hub`)**

1. `USERS` in `app.py`. This is login. A leftover session fails on the
   next request.
2. `roster.RETIRED_USER_KEYS`. Boot deletes the `hub_users` row. Do not
   put the key back in `USERS`.
3. `pipeline_board.BOARD_CONSULTANTS`. This is the pipeline switcher.
   A key that is not in this tuple cannot be opened, including by typing
   `/pipeline-board?pair=their_key`. The page sends you back to the
   dashboard.
4. `pipeline_board.PRIMARY_PM_FOR_CONSULTANT`. Both sides. Take down
   their board, and take their name off any board that lists them as the
   PM.
5. `dashboard_lanes.LANE_ORDER`.
6. `PROPOSAL_NUMBER_INITIALS`. New numbers stop. Numbers already issued
   stay.
7. `CONSULTANTS` in `app.py`. This is the book filter on All Proposals.
8. `user_aliases.CONSULTANT_ALIASES`. Remove the short form as well as
   the long key.
9. `TEAM_DATES`. Birthday and anniversary.
10. `PSC_TRAINING_MANAGER` and `PSC_TRAINING_MENTOR` in
    `psc_training_data.py`, if they hold either. Point the constant at
    the person who has the job now.
11. Nightly digest and Monday ranking. Ask. Add both spellings to
    `roster.REPORT_OMIT_KEYS` only when Thomas wants them left out of
    those emails. Derek Kidney is retired and still appears there. Tony
    Cumella is on the omit list. Do not assume.

**Proposal tool (`pps-proposal-tool`)**

The proposal radio grid does not read Hub `USERS`. Removing someone on
the Hub does not take them off that grid. This is how Tony was still a
choice on 2026-11-19.

12. Add both spellings to `RETIRED_PROPOSAL_KEYS` in `app.py` and to
    `roster_client.RETIRED_USER_KEYS`. The second list is what Trade
    Partner Scope and PPM use, including when the Hub is asleep and the
    tool falls back to its own names.
13. The proposal page must render `_proposal_form_consultants()`, which
    drops `RETIRED_PROPOSAL_KEYS`. Do not loop the full `CONSULTANTS`
    dict into the radio grid.
14. Fill Sample must not select them or stamp their initials.
15. Generate must refuse a missing or retired consultant. It used to
    fill a blank with Tony.

### Keep

Do not delete these. An old job should still show the person who did it.

- `proposal_log`, `ppm_log`, `subscope_log`: `generated_by`,
  `consultant_name`, `consultant_key`, `pm_name`. Do not rewrite the key.
- Pipeline rows stored under their `pair_key`. They stay in the
  database. They are not on the switcher, and `can_access_board`
  returns false, so nobody opens that board.
- Office Ops invoice matching: `_SALES_REP_ALIASES` and the QuickBooks
  sales-rep name. A past invoice that says their name still says their
  name. `office_ops_generate.py` sales rows read a historical workbook.
  They are not a dropdown.
- Pricing "updated by" text already stored on a row.
- Monday contact owner history. `FORMER_MONDAY_USERS` is only a label
  for an ID Monday no longer returns. Reassign the contacts in Monday
  if they should move. Do not blank an owner that has not been
  reassigned.
- Ask PPS answers they wrote.
- In the proposal tool, their row in `CONSULTANTS`, `ALL_CONSULTANTS`,
  and `CONSULTANT_KEY_MAP`, and their headshot file. A PPM read and an
  old proposal still need the name, phone, email, and photo. The
  retired-key lists are what keep that record off the form.

### Tony Cumella, checked 2026-11-20

He is off the pipeline switcher. Live boards are Andy Potts, Adam
Cupito, and Rachel Farler. `/pipeline-board?pair=tony_cumella` does not
open his board. The rows he already had stay in the database.

He is also off login, the proposal radio grid, Trade Partner Scope,
PPM, proposal-number initials, the digest, and the Monday ranking.
His name still resolves on old proposals, old invoices, and his photo.

### Harrison Hollon, added 2026-11-23

He has a pipeline board, paired with Nick Triplett, the shape Tony had.
The switcher is Andy Potts, Adam Cupito, Rachel Farler, Harrison Hollon.
His board starts empty. Tony's rows are not on it. He is still off
proposal-number initials, aliases, team dates, and phone.

## Check

`tests/test_roster.py` fails if a live user is missing a role, email,
or title, or if a retired key is back in `USERS`.
`tests/test_pipeline_board.py` fails if Tony is back on
`BOARD_CONSULTANTS`. Proposal-tool `tests/test_roster_dropdowns.py`
fails if the proposal page or a TPS/PPM fallback still offers him.
