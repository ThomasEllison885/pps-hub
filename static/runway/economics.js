/**
 * Route Lab — pure economics helpers (config from bootstrap.route_economics).
 * Loaded before game.js; exposed as window.RunwayEconomics.
 */
(function (global) {
  'use strict';

  const DEFAULTS = {
    hub_profit_target_years: 2.5,
    marginal_payback_warn_years: 3.0,
    ramp_load_multipliers: [0.55, 0.78, 0.92],
    ramp_cost_creep_per_year: 0.03,
    avg_pax_load_factor: 0.8,
    market_capture: {
      origin_share_floor: 0.0005,
      pair_share_floor: 0.03,
      capture_cap: 0.88,
      presence_origin_target: 0.08,
      presence_scale_min: 0.42,
      presence_scale_range: 0.58,
      rep_divisor: 450,
      awareness_factor: 0.35,
      freq_presence_base: 0.72,
      freq_presence_max_add: 0.28,
      freq_presence_divisor: 42,
      origin_share_cap: 0.95,
    },
    imputed_pair: {
      size_multiplier: 3.2,
      dist_divisor: 180,
      min_weekly: 4,
    },
    market_departures: {
      avg_pax_tiers: [
        { max_pax_m: 0.6, avg_pax: 48 },
        { max_pax_m: 3, avg_pax: 80 },
        { max_pax_m: 12, avg_pax: 102 },
        { max_pax_m: 35, avg_pax: 118 },
        { max_pax_m: Infinity, avg_pax: 132 },
      ],
      min_daily: 2,
    },
    rival_traffic_buffer: 1.12,
  };

  function mergeConfig(bootstrap) {
    const src = (bootstrap && bootstrap.route_economics) || {};
    const mc = { ...DEFAULTS.market_capture, ...(src.market_capture || {}) };
    const ip = { ...DEFAULTS.imputed_pair, ...(src.imputed_pair || {}) };
    const md = { ...DEFAULTS.market_departures, ...(src.market_departures || {}) };
    return {
      ...DEFAULTS,
      ...src,
      market_capture: mc,
      imputed_pair: ip,
      market_departures: md,
      ramp_load_multipliers: src.ramp_load_multipliers || DEFAULTS.ramp_load_multipliers,
    };
  }

  function avgPaxPerDeparture(paxM, cfg) {
    const tiers = cfg.market_departures.avg_pax_tiers;
    for (let i = 0; i < tiers.length; i++) {
      if (paxM < tiers[i].max_pax_m) return tiers[i].avg_pax;
    }
    return 132;
  }

  function airportMarketDeparturesDaily(ap, cfg) {
    if (!ap) return 50;
    if (ap.market_departures_daily > 0) return ap.market_departures_daily;
    const pax = ap.annual_pax_m || 1;
    const avgPax = avgPaxPerDeparture(pax, cfg);
    const lf = cfg.avg_pax_load_factor;
    return Math.max(cfg.market_departures.min_daily, Math.round((pax * 1e6) / 365 / (avgPax * lf)));
  }

  function airportMarketDeparturesWeekly(ap, cfg) {
    if (!ap) return 300;
    if (ap.market_departures_weekly > 0) return ap.market_departures_weekly;
    return airportMarketDeparturesDaily(ap, cfg) * (ap.operating_days_per_week || 6);
  }

  function imputedPairMarketWeekly(originAp, destAp, distNm, cfg) {
    if (!originAp || !destAp) return cfg.imputed_pair.min_weekly;
    const size = Math.sqrt((originAp.annual_pax_m || 0.5) * (destAp.annual_pax_m || 0.5));
    const ip = cfg.imputed_pair;
    return Math.max(ip.min_weekly, Math.round(size * ip.size_multiplier + distNm / ip.dist_divisor));
  }

  function computeMarketCapture(params, cfg) {
    const mc = cfg.market_capture;
    const originShare = Math.min(mc.origin_share_cap, params.playerOriginDeps / Math.max(1, params.originMarketWeekly));
    const pairDenom = Math.max(1, params.effectivePlayerFreq + params.compPairWeekly + params.imputedPairWeekly);
    const pairCapacityShare = params.effectivePlayerFreq / pairDenom;
    const repBoost = 1 + (params.reputation || 0) / mc.rep_divisor;
    const awareBoost =
      1 + (((params.brandAwareOrigin || 5) + (params.brandAwareDest || 5)) / 2 / 100) * mc.awareness_factor;
    const freqPresence =
      mc.freq_presence_base +
      Math.min(mc.freq_presence_max_add, params.effectivePlayerFreq / mc.freq_presence_divisor);
    const shareCore = Math.sqrt(
      Math.max(mc.origin_share_floor, originShare) * Math.max(mc.pair_share_floor, pairCapacityShare)
    );
    const presenceScale =
      mc.presence_scale_min +
      mc.presence_scale_range * Math.min(1, Math.sqrt(originShare / mc.presence_origin_target));
    const capture = Math.min(mc.capture_cap, shareCore * presenceScale * repBoost * awareBoost * freqPresence);
    return {
      originShare,
      destShare: Math.min(mc.origin_share_cap, (params.playerDestDeps || 0) / Math.max(1, params.destMarketWeekly || 1)),
      pairCapacityShare,
      captureFactor: capture,
      pairDenom,
    };
  }

  function estimateLoadFromDemand(demand, dailySeats, cap) {
    const loadCap = cap != null ? cap : 0.95;
    return Math.min(loadCap, demand / Math.max(dailySeats, 1));
  }

  global.RunwayEconomics = {
    DEFAULTS,
    mergeConfig,
    avgPaxPerDeparture,
    airportMarketDeparturesDaily,
    airportMarketDeparturesWeekly,
    imputedPairMarketWeekly,
    computeMarketCapture,
    estimateLoadFromDemand,
  };
})(typeof window !== 'undefined' ? window : global);