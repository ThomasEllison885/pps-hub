#!/usr/bin/env node
/**
 * Route Lab economics regression tests — run: node static/runway/test_economics.js
 */
'use strict';

const path = require('path');
const fs = require('fs');

// Minimal global for economics.js
const window = {};
const code = fs.readFileSync(path.join(__dirname, 'economics.js'), 'utf8');
eval(code);

const E = window.RunwayEconomics;
// Empty merge = JS defaults (fallback path).
const cfg = E.mergeConfig({});
// Bootstrap-shaped payload mirrors runway_game_data.ROUTE_ECONOMICS live values.
const cfgFromBootstrap = E.mergeConfig({
  route_economics: {
    hub_profit_target_years: 2.5,
    marginal_payback_warn_years: 3.0,
    ramp_load_multipliers: [0.55, 0.78, 0.92],
    ramp_cost_creep_per_year: 0.03,
    avg_pax_load_factor: 0.8,
    rival_traffic_buffer: 1.12,
    cancel_load_threshold: 0.1,
    market_capture: {
      origin_share_floor: 0.002,
      pair_share_floor: 0.06,
      capture_cap: 0.9,
      origin_presence_min: 0.55,
      presence_origin_target: 0.04,
      rep_divisor: 400,
      awareness_factor: 0.42,
      freq_presence_base: 0.85,
      freq_presence_max_add: 0.22,
      freq_presence_divisor: 28,
      origin_share_cap: 0.95,
      mature_capture_floor: 0.14,
      // legacy dead keys must not break merge
      presence_scale_min: 0.42,
      presence_scale_range: 0.58,
    },
    hub_maturity: {
      aware_new: 12,
      aware_building: 35,
      aware_mature: 55,
      capture_floor_new: 0.04,
      capture_floor_building: 0.09,
      origin_presence_brand_boost: 0.18,
      overhead_new_mult: 1.55,
      overhead_building_mult: 1.22,
      overhead_mature_mult: 1.0,
      mkt_efficiency_new: 0.62,
      mkt_efficiency_building: 0.88,
      mkt_efficiency_mature: 1.12,
      ramp_brand_lift: 0.28,
      organic_brand_per_route_mo: 0.4,
      organic_brand_cap_without_ads: 30,
    },
    judgment: {
      fuzzy_outside_tutorial: true,
      research_base_cost: 18000,
      research_origin_pax_rate: 2800,
      research_dest_pax_rate: 1600,
      research_min_cost: 12000,
      research_max_cost: 95000,
    },
    imputed_pair: { size_multiplier: 3.2, dist_divisor: 180, min_weekly: 4 },
    market_departures: {
      avg_pax_tiers: [
        { max_pax_m: 0.6, avg_pax: 48 },
        { max_pax_m: 3, avg_pax: 80 },
        { max_pax_m: 12, avg_pax: 102 },
        { max_pax_m: 35, avg_pax: 118 },
        { max_pax_m: 1e9, avg_pax: 132 },
      ],
      min_daily: 2,
    },
  },
});

let passed = 0;
let failed = 0;

function assert(cond, msg) {
  if (cond) {
    passed++;
  } else {
    failed++;
    console.error('FAIL:', msg);
  }
}

// Bootstrap + defaults must agree on live knobs (single source of truth).
assert(cfgFromBootstrap.market_capture.pair_share_floor === 0.06, 'bootstrap pair_share_floor 0.06');
assert(cfgFromBootstrap.market_capture.origin_presence_min === 0.55, 'bootstrap origin_presence_min');
assert(cfgFromBootstrap.market_capture.mature_capture_floor === 0.14, 'bootstrap mature_capture_floor');
assert(cfgFromBootstrap.cancel_load_threshold === 0.1, 'bootstrap cancel_load_threshold');
assert(
  cfgFromBootstrap.market_capture.presence_scale_min == null,
  'legacy presence_scale_min stripped'
);
assert(cfg.market_capture.pair_share_floor === cfgFromBootstrap.market_capture.pair_share_floor, 'empty merge matches bootstrap pair floor');

// DAY ~2.2M pax → ~94 daily deps
const dayAp = {
  annual_pax_m: 2.2,
  operating_days_per_week: 6,
  market_departures_daily: 0,
  market_departures_weekly: 0,
};
const dayDaily = E.airportMarketDeparturesDaily(dayAp, cfg);
assert(dayDaily >= 85 && dayDaily <= 105, `DAY daily departures ${dayDaily} in 85–105`);

// CMH ~9M → ~280–320 daily
const cmhAp = { annual_pax_m: 9, operating_days_per_week: 6 };
const cmhDaily = E.airportMarketDeparturesDaily(cmhAp, cfg);
assert(cmhDaily >= 270 && cmhDaily <= 330, `CMH daily departures ${cmhDaily} in 270–330`);

// 1 plane 7/wk at DAY → origin share ~1%
const dayWeekly = E.airportMarketDeparturesWeekly(dayAp, cfg);
const originShare7 = 7 / dayWeekly;
assert(originShare7 > 0.008 && originShare7 < 0.02, `7/wk DAY share ${(originShare7 * 100).toFixed(2)}% in 0.8–2%`);

// Capture for thin startup (7/wk CMH-DAY, 14 comp on pair) — pair-first model
const captureThin = E.computeMarketCapture(
  {
    playerOriginDeps: 7,
    originMarketWeekly: E.airportMarketDeparturesWeekly(cmhAp, cfg),
    destMarketWeekly: dayWeekly,
    playerDestDeps: 0,
    effectivePlayerFreq: 7,
    compPairWeekly: 14,
    imputedPairWeekly: 14,
    reputation: 8,
    brandAwareOrigin: 14,
    brandAwareDest: 10,
  },
  cfg
);
assert(captureThin.captureFactor < 0.35, `thin capture ${captureThin.captureFactor} < 0.35`);
assert(captureThin.captureFactor > 0.05, `thin capture ${captureThin.captureFactor} > 5%`);

// Mature established carrier on same pair — capture floor so seats fill
const captureMature = E.computeMarketCapture(
  {
    playerOriginDeps: 7,
    originMarketWeekly: E.airportMarketDeparturesWeekly(cmhAp, cfg),
    destMarketWeekly: dayWeekly,
    playerDestDeps: 7,
    effectivePlayerFreq: 7,
    compPairWeekly: 14,
    imputedPairWeekly: 14,
    reputation: 32,
    brandAwareOrigin: 62,
    brandAwareDest: 48,
    mature: true,
  },
  cfg
);
assert(captureMature.captureFactor >= 0.14, `mature capture ${captureMature.captureFactor} >= 14%`);
assert(captureMature.captureFactor > captureThin.captureFactor, 'mature capture > thin startup');

// Hub maturity: high origin brand beats greenfield on same capacity
const captureNewHub = E.computeMarketCapture(
  {
    playerOriginDeps: 7,
    originMarketWeekly: E.airportMarketDeparturesWeekly(cmhAp, cfg),
    destMarketWeekly: dayWeekly,
    playerDestDeps: 0,
    effectivePlayerFreq: 7,
    compPairWeekly: 14,
    imputedPairWeekly: 14,
    reputation: 20,
    brandAwareOrigin: 8,
    brandAwareDest: 8,
    mature: false,
  },
  cfg
);
const captureKnownHub = E.computeMarketCapture(
  {
    playerOriginDeps: 7,
    originMarketWeekly: E.airportMarketDeparturesWeekly(cmhAp, cfg),
    destMarketWeekly: dayWeekly,
    playerDestDeps: 0,
    effectivePlayerFreq: 7,
    compPairWeekly: 14,
    imputedPairWeekly: 14,
    reputation: 20,
    brandAwareOrigin: 62,
    brandAwareDest: 20,
    mature: false,
  },
  cfg
);
assert(
  captureKnownHub.captureFactor > captureNewHub.captureFactor,
  `known hub capture ${captureKnownHub.captureFactor} > new hub ${captureNewHub.captureFactor}`
);
assert(captureKnownHub.hubMaturity && captureKnownHub.hubMaturity.tier === 'mature', 'known hub tier mature');
assert(captureNewHub.hubMaturity && captureNewHub.hubMaturity.tier === 'new', 'greenfield tier new');

const matNew = E.hubMaturityFactors(8, cfg);
const matMature = E.hubMaturityFactors(62, cfg);
assert(matNew.overheadMult > matMature.overheadMult, 'new stations pay more HQ share');
assert(matMature.mktEfficiency > matNew.mktEfficiency, 'mature hubs convert ads better');
assert(cfg.judgment && cfg.judgment.fuzzy_outside_tutorial === true, 'fuzzy judgment default on');
assert(cfgFromBootstrap.hub_maturity.aware_mature === 55, 'bootstrap hub maturity merge');

// Load estimate: low demand vs seats
const demand = 12;
const seats = 50;
const load = E.estimateLoadFromDemand(demand, seats * (7 / 7), 0.95);
assert(load < 0.35, `1 E145/day thin load ${load} < 35%`);

// Airport fees: one landing per one-way (return is separate route or ferry)
const regSeats = 50;
const regFare = 139;
const feePerDep = 450;
const regFreqWeek = 7;
const regLoad = 0.65;
const paxPerDay = regSeats * (regFreqWeek / 7) * regLoad;
const revPerDay = paxPerDay * regFare;
const feesPerDay = (regFreqWeek / 7) * feePerDep; // one-way landings
assert(feesPerDay < revPerDay * 0.25, `airport fees ${feesPerDay.toFixed(0)} < 25% of ticket rev ${revPerDay.toFixed(0)}`);

// Marketing at 4.5% of gross should be materially less than lease on one E145
const monthlyGross = revPerDay * 30;
const marketingSpend = Math.round(monthlyGross * 0.045);
assert(marketingSpend < 118_000 * 0.2, `marketing ${marketingSpend} < 20% of E145 lease`);

// Imputed pair CMH-DAY
const pair = E.imputedPairMarketWeekly(cmhAp, dayAp, 72, cfg);
assert(pair >= 4 && pair < 30, `CMH-DAY imputed pair ${pair}`);

// Cancel threshold present (non-established only in game; established never cancels)
assert(cfg.cancel_load_threshold > 0 && cfg.cancel_load_threshold <= 0.15, `cancel threshold ${cfg.cancel_load_threshold}`);

console.log(`\nEconomics tests: ${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
