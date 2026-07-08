# RouteLab economics reference (creator)

This document explains how launch judgment, demand, gates, and overhead math work. Tune coefficients in `runway_game_data.py` → `ROUTE_ECONOMICS` and airport ops fields; the browser reads them via bootstrap.

## Design decisions (Thomas Q&A)

| Topic | Decision |
|-------|----------|
| Fare buckets | Keep current per-route bucket handling |
| Ancillary strategy | **Airline-wide** — pick at creation, change in **Market** tab as marketing strategy |
| HQ / overhead | **Always in judgment** so existing hubs do not automatically beat new stations |
| Hub profit horizon | Real-world ~2.5 yr target; **3 yr** marginal warning OK; projections use ramp + inflation + cost creep — not a simple formula |
| Gate costs | **Split** across routes at origin; gate lease ÷ (routes from origin + 1) |
| Gate schedule | Ops hours, turnaround spacing, per-gate weekly cap — no 24/7; per-route max frequency from block + turnaround |
| Launch competition | **Static** in judgment; live sim adds rival moves |
| Brand ramp | **Conservative** years 1–3 in outlook table |
| Fare recommendation | Sweep from known variables — **hint only**; live results diverge (GDP, marketing, inflation, rivals) |
| Payback display | Monthly net + steady payback; years 1–3 outlook table |
| Verdict | **Show recommendation, never block** launch |
| League pillars → your routes | Click Profit/Riders/CSAT → league re-sorts **and** your routes rank (scoreboard panel + Routes tab) |
| In-game math UI | **No** for players; this doc is for creator tuning |

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

## Your routes ranking (league pillars)

When you click **Profit**, **Riders**, or **CSAT** on the scoreboard:

- League table re-sorts (unchanged).
- Scoreboard panel adds **Your routes** table for the same metric.
- **Routes** tab re-orders cards with `#rank` badges.

Per-route metrics (30-day history when available, else today’s sim):

- **Profit** — variable margin × 30 (`avgPnl` from history).
- **Riders** — avg daily pax × 30.
- **CSAT** — load × 28 + reputation share + base − AOG penalty (route-level approximation).

## Reputation

0–100 brand trust score. **Starts** from scenario (`runway_game_data.py` scenarios). **Grows** when:

- You run routes profitably while reputation is under 50 (+0.3/month)
- You choose “Hold premium” in a competitor decision (+2)

**Used for:** passenger demand (`1 + reputation/200`), and satisfaction score (`reputation × 0.45 + …`).

Does not decay in the current build.

## Satisfaction (scoreboard pillar)

Renamed from CSAT. 0–100 passenger satisfaction index: reputation × 0.45 + avg load × 28 + 18 − AOG×6. Click **Satisfaction** pillar to sort league.

## Rank vs standing

- **# column** = rank (**1 is best**).
- **Standing** = blended index 0–100 (profit percentile × 0.45 + riders × 0.35 + satisfaction × 0.2). Higher is better, but it is **not** the same as rank — a startup can be #4 with standing 47 while Delta is #1 at 94.

## Files

| Concern | Location |
|---------|----------|
| Airport ops, ROUTE_ECONOMICS | `runway_game_data.py` |
| Sim + judgment UI | `static/runway/game.js` |
| `projectRouteBusinessCase`, `recommendLaunchFare` | game.js |
| Gate capacity | `airportGateWeeklyCapacity`, `gateCapacityError` |
| Route pillar ranking | `routePillarMetrics`, `sortPlayerRoutesByPillar` |

## Remembered for later

- Dual payback display (route-only vs fully burdened) in launch UI.
- Fare optimizer chart on launch modal.
- Hub maturity curve tied more tightly to `brand_awareness`.