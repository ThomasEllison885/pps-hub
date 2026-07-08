# RouteLab economics reference (creator)

This document explains how launch judgment, demand, gates, and overhead math work. Tune coefficients in `runway_game_data.py` → `ROUTE_ECONOMICS` and airport ops fields; the browser reads them via bootstrap.

## Route launch judgment

**Steady-state** (what you see at the top of the judgment card):

1. `simulateRouteDay()` — daily revenue (fare buckets + ancillaries − OTA commission) minus variable cost (fuel, crew, airport fees).
2. **Allocated fixed costs** (monthly):
   - Gate lease at origin ÷ (routes from origin + 1)
   - Aircraft lease ÷ (routes on that plane + 1)
   - Marketing selections on the launch form (airport / state / national / world)
   - OTA listing + feature + hub push
   - **HQ & corporate overhead** — `playerNaturalOverheadMonthly() ÷ (network routes + 1)`
3. **Net contribution** = steady route margin − fixed allocation.
4. **Payback** = upfront (station + new OTA listings) ÷ monthly net (if positive).

**Why HQ is included:** Without overhead, every new route at an existing hub looks artificially better than opening a new station. New stations carry a full overhead share until the network grows.

**Hub profit target:** `ROUTE_ECONOMICS.hub_profit_target_years` (default 2.5). Real airlines aim for station profitability in roughly 2–3 years; judgment copy references this.

## Years 1–3 outlook (conservative ramp)

Not a promise — a **conservative projection**:

| Year | Load multiplier (default) | Cost creep |
|------|---------------------------|------------|
| 1    | 55% of steady load        | +0% base   |
| 2    | 78%                       | +3%/yr     |
| 3    | 92%                       | +6% + inflation |

Cumulative column = upfront + sum of yearly net. Competition in judgment stays **static**; live sim adds rival moves, GDP, fuel, etc.

## Fare → demand → ROI

- `marketFareForPair()` — distance, wealth, aircraft comfort.
- `fareDemandFactor()` — elasticity from wealth/luxury; fare above market reduces demand (~0.82× per 100% over market).
- Judgment **recalculates on every fare/freq change** in the launch modal.
- `recommendLaunchFare()` sweeps fares ±28% of market and suggests a starting point — **hint only**, not a guarantee.

## Airline ancillary strategy

Set at **airline creation** (Balanced / Ancillary-heavy / All-inclusive). Stored as `state.ancillary_strategy`. Change anytime in **Market** tab.

- Affects `ancillaryPerPax()` for routes set to "Auto".
- Per-route override still available on route cards.

## Gate & schedule limits

Per airport (from `annual_pax_m`):

- `ops_hours_per_day` — not 24/7; regionals ~9–11h, majors ~18h.
- `max_departures_per_hour` — turnaround spacing (no 3:00 and 3:50 departures on one gate).
- `min_turnaround_min` — block time + ground time between departures.
- `max_weekly_departures_per_gate` — ops_hours × dep/hour × operating_days × 0.8.

**Two caps:**

1. **Gate total** — sum of all route frequencies from origin ≤ gates × weekly cap.
2. **Per route** — `maxFrequencyForRoute()` from block hours + turnaround within ops window.

## CSAT (scoreboard)

Customer Satisfaction 0–100: reputation × 0.45 + avg load × 28 + 18 − AOG×6. Click **CSAT** pillar to sort league.

## Files

| Concern | Location |
|---------|----------|
| Airport ops, ROUTE_ECONOMICS | `runway_game_data.py` |
| Sim + judgment UI | `static/runway/game.js` |
| `projectRouteBusinessCase`, `recommendLaunchFare` | game.js |
| Gate capacity | `airportGateWeeklyCapacity`, `gateCapacityError` |

## Remembered for later (Thomas)

- League pillars → rank **your routes** by profit/riders/CSAT (not built yet; detail-first idea saved).