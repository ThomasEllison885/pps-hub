# Runway: A Startup Airline Simulation

Design framework stored from Thomas's v0.2 spec. **Playable MVP:** `/runway` — Thomas login only. Linked from **Hub Admin** (dashboard Admin lane + `/admin` page). Not in sales/production lanes, Ask PPS, or team-facing UI.

## MVP shipped (v0.1+)

- ~120 real US airports on geographic map (Ohio + bordering states / Midwest / national scopes)
- Scenarios: Winning Path Ohio coach (sole tutorial), regional, greenfield, exit CEO, inheritance, **Peak Network ULC scale** (Frontier-class sandbox)
- Financing: seed equity, growth equity, bank loans, corporate bonds, asset-backed bonds, debt restructure
- Gate leasing, fleet (PC-12 through B737), routes with P&L, marketing per city
- Time: Pause / Slow / Day / Week / Month / **Year (365 days per tick)**
- Save: multi-slot + autosave + export/import JSON (`routelab_saves_v2`); start screen Continue/Load (no silent resume)
- Chapter 11 creditor board when cash goes negative; reputation grows and decays
- Competitor AI biased to scenario region and player markets

## v0.2+ (from original spec)

- 300+ airports, slot markets, bilateral rights, historical scenarios (1978, 1997, 2002, 2021)
- Real incumbents with scripted fare wars, codex, IPO, Chapter 11, year-speed rollups
- Public release: swap real airline names for evocative near-names

See Thomas's full v0.2 framework in conversation history / this doc's sections below when expanded.

*Code: `runway_game_data.py`, `static/runway/game.js`, `templates/runway.html`*