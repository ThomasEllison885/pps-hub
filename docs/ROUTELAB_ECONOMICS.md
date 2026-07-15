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
| Judgment precision | **Full math** in tutorials; **directional/fuzzy** elsewhere until market research or flying the pair |
| Hub maturity | Driven by origin **`brand_awareness`** — capture floor, HQ judgment share, ad efficiency, year-1 ramp |
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

## Market scope & demand capture

Total airport traffic is **not** the same as your gate slots. A regional hub like CMH runs ~300 departures/week across all carriers; one E145 at 7/wk is ~2% of that market.

Pure math lives in `static/runway/economics.js` (`window.RunwayEconomics`), loaded before `game.js`. **Single source of truth for live knobs:** `ROUTE_ECONOMICS` in `runway_game_data.py` (bootstrap). JS `DEFAULTS` are fallbacks only when a key is missing — keep them aligned. After tuning: `node static/runway/test_economics.js`.

`simulateRouteDay(route, { commit: true })` only on day ticks — HUD/Studio previews must not accumulate block hours or mutate smooth load. Route Studio judgment passes **draft** marketing + OTA into demand so spend lifts projected load.

### Airport market departures

When `market_departures_daily` / `market_departures_weekly` are not set on an airport:

```
daily_deps = max(min_daily, round(annual_pax_m × 1e6 / 365 / (avg_pax × load_factor)))
weekly_deps = daily_deps × operating_days_per_week
```

`avg_pax` comes from tiered `market_departures.avg_pax_tiers` by `annual_pax_m`. Default `load_factor` = 0.80.

### Imputed city-pair market

When no competitor frequency is known for a pair:

```
pair_weekly = max(min_weekly, round(sqrt(origin_pax × dest_pax) × size_multiplier + dist_nm / dist_divisor))
```

Defaults: `size_multiplier` 3.2, `dist_divisor` 180, `min_weekly` 4.

### Capture factor (addressable O-D demand)

**Pair-first model** (airport-wide share only softens presence — a 7/wk hop at CMH is not crushed to ~1% load):

```
originShare = player_origin_deps / origin_market_weekly
pairCapacityShare = player_freq / (player_freq + comp_pair_weekly + imputed_pair_weekly)
pairCore = max(pair_floor, pairCapacityShare)
originPresence = origin_presence_min + (1 − min) × (originShare / presence_target)^0.45
capture = pairCore × originPresence × rep × awareness × freqPresence
```

**Capture floor scales with origin brand** (`hub_maturity` + `mature_capture_floor`): greenfield stations get a soft ~4% floor; known hubs rise toward ~14% so existing services fill seats.

### Round trips, ferry, and cancellations

- Routes are **one-way**. Block hours are one-way; a reverse route is a second one-way with its own pax.
- No reverse route → **empty ferry return** (fuel/crew, $0 tickets) — judgment and launch warn; “Launch with return leg” is checked by default.
- Projected load below **12%** → flight **cancels** that day (tiny cancel cost, no full burn). Airlines do not fly 1% full.

### Load estimate

```
load = min(0.95, demand / max(daily_seats, 1))
```

Demand = addressable O-D × capture × fare elasticity × GDP/travel macro.

### Regression tests

```bash
node static/runway/test_economics.js
```

Expects DAY ~94 daily deps, CMH ~300/day, thin 7/wk capture &lt; 12%.

## Fare → demand → ROI

- `marketFareForPair()` — distance, wealth, aircraft comfort.
- `fareDemandFactor()` — elasticity from wealth/luxury; fare above market reduces demand (~0.82× per 100% over market).
- Judgment **recalculates on every fare/freq change** in the launch modal.
- `recommendLaunchFare()` sweeps fares ±28% of market and suggests a starting point — **hint only**, not a guarantee. Profit playbook surfaces the same hint on thin routes.

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

## Exclusive vs common gates

| | Common-use | Exclusive |
|--|------------|-----------|
| Term (UI) | 3 years | 5 years |
| Rent | `lease_common_monthly` | `lease_exclusive_monthly` (higher) |
| Capacity | Base deps/wk per gate | **+~10%** deps/wk (min +1) |
| Load stability | ±12 pts/day | **Tighter** (±9 default) |
| Cancel threshold | Base | **Lower** (prefer to fly) |
| Organic brand | Base | **×1.25** |
| Ad efficiency | Hub maturity only | **×1.10** extra |
| Rival pressure | Full | Softer threat score / fewer new routes / less event heat |

Tune: `ROUTE_ECONOMICS.exclusive_gate`. Exclusive only pays when the station is densified.

## Hub maturity (`brand_awareness` at origin)

Stations progress **new → building → mature** from origin brand (defaults: &lt;12 / 12–35 / 35–55+).

| Lever | New station | Mature hub |
|-------|-------------|------------|
| Capture floor | Soft / low | Full mature floor |
| Origin presence | Share only | Share + brand boost |
| HQ share in **judgment** | ×1.55-ish | ×1.0 |
| Airport ad efficiency | ~0.62× | ~1.12× |
| Years 1–3 load ramp | Base ramp | Faster toward steady |
| Organic brand (monthly) | Routes build brand up to ~30 without ads | Ads still needed past cap |

Live sim uses the same capture/ad efficiency; the HQ multiplier is **judgment only** so new cities do not look free vs known bases.

Tune in `ROUTE_ECONOMICS.hub_maturity`.

## Launch judgment precision

- **Tutorials** (`scenario.tutorial`): full P&amp;L, fare chart, suggested fare (teaching mode).
- **Other scenarios**: directional bands (load word, money ranges, payback horizon) unless:
  - player **commissions market research** on the city-pair (cash cost from `ROUTE_ECONOMICS.judgment`), or
  - player **already flies** that pair.
- Research is stored on `state.market_research` and survives saves. Never blocks launch.

## Reputation

0–100 brand trust score. **Starts** from scenario (`runway_game_data.py` scenarios).

**Grows** when (monthly, only if no decay that month):

- You run routes profitably while reputation is under 50 (+0.3/month)
- You choose “Hold premium” in a competitor decision (+2)

**Decays** monthly from:

- Aircraft AOG (−0.55 per AOG plane, cap −2.4)
- Chronic losses (trailing ~14–30d P&L negative with active routes, −0.55)
- Soft day underperformance while streak is broken (−0.15)

**Used for:** passenger demand (`1 + reputation/200`), and satisfaction score (`reputation × 0.45 + …`).

## Satisfaction (scoreboard pillar)

Renamed from CSAT. 0–100 passenger satisfaction index: reputation × 0.45 + avg load × 28 + 18 − AOG×6. Click **Satisfaction** pillar to sort league.

## Rank vs standing

- **# column** = rank (**1 is best**).
- **Standing** = blended index 0–100 (profit percentile × 0.45 + riders × 0.35 + satisfaction × 0.2). Higher is better, but it is **not** the same as rank — a startup can be #4 with standing 47 while Delta is #1 at 94.

## Saves (v2)

- **Explicit Save / Load** in the HUD; start screen **Continue** / **Load game** (no silent auto-enter).
- **5 manual slots** + **autosave** (background while playing).
- **Export / Import JSON** for backup and move between browsers.
- Payload is **state only** (no airport tables). Live airport ops always come from `runway_game_data.py` bootstrap.
- localStorage keys: `routelab_saves_v2` (index); legacy `runway_save_v1` migrates once into autosave.

## Survival / Chapter 11

- Cash &lt; 0 → creditor board (restructure, sell gates, park fleet, or liquidate).
- Cash &lt; −$2M without an active plan → emergency board.
- Restructure: debt haircut, DIP cash, equity/reputation hit, 180-day court watch.
- Exit when cash ≥ $1M and trailing P&L positive; deep failure after Chapter 11 can still liquidate.

## Files

| Concern | Location |
|---------|----------|
| Airport ops, ROUTE_ECONOMICS | `runway_game_data.py` |
| Pure capture / market math | `static/runway/economics.js` |
| Node regression tests | `static/runway/test_economics.js` |
| Sim + judgment UI | `static/runway/game.js` |
| Save / load slots | `saveGame`, `openSaveLoadModal`, `routelab_saves_v2` |
| `projectRouteBusinessCase`, `recommendLaunchFare` | game.js |
| Gate capacity | `airportGateWeeklyCapacity`, `gateCapacityError` |
| Route pillar ranking | `routePillarMetrics`, `sortPlayerRoutesByPillar` |

## Remembered for later

- Dual payback display (route-only vs fully burdened) in launch UI. *(shipped)*
- Fare optimizer chart on launch modal. *(shipped as chart + sensitivity; refine interactivity if needed)*
- Hub maturity curve tied more tightly to `brand_awareness`. *(shipped — capture/overhead/ads/ramp/organic brand)*
- Fuzzy judgment outside tutorials + market research unlock. *(shipped)*