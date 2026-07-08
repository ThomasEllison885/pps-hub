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

function approx(a, b, tol, msg) {
  assert(Math.abs(a - b) <= tol, `${msg} (got ${a}, want ~${b})`);
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

// Capture for thin startup (7/wk CMH-DAY, 14 comp on pair)
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
assert(captureThin.captureFactor < 0.12, `thin capture ${captureThin.captureFactor} < 0.12`);
assert(captureThin.captureFactor > 0.008, `thin capture ${captureThin.captureFactor} > 0.8%`);

// Load estimate: low demand vs seats
const demand = 12;
const seats = 50;
const load = E.estimateLoadFromDemand(demand, seats * (7 / 7), 0.95);
assert(load < 0.35, `1 E145/day thin load ${load} < 35%`);

// Imputed pair CMH-DAY
const pair = E.imputedPairMarketWeekly(cmhAp, dayAp, 72, cfg);
assert(pair >= 4 && pair < 30, `CMH-DAY imputed pair ${pair}`);

console.log(`\nEconomics tests: ${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);