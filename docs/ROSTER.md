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

1. Delete their key from `USERS`. That is what revokes login.
2. Add the key to `roster.RETIRED_USER_KEYS` so `hub_users` is cleaned on
   boot. Do not re-add them to `USERS`.
3. Remove them from `PRIMARY_PM_FOR_CONSULTANT`, `BOARD_CONSULTANTS`,
   `LANE_ORDER`, `PROPOSAL_NUMBER_INITIALS`, `CONSULTANTS` / `CONSULTANT_KEY_MAP`.
4. **Do not rewrite history.** Old `generated_by` / `consultant_name` /
   `pm_name` rows stay. Digests and recaps already fall back to the stored
   name or the raw key.

They must disappear from **new** dropdowns (TPS, PPM, login, proposal
consultant list). They must remain readable on work they already did.

## Check

`tests/test_roster.py` fails if a live user is missing a role/email/title, or
if a retired key is back in `USERS`. Proposal-tool tests fail if TPS/PPM
templates hardcode a person (including Derek).
