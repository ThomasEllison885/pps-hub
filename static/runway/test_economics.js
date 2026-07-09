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
const cfg = E.mergeConfig({});

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
