/**
 * Route Lab — pure economics helpers.
 * Live balance: runway_game_data.py → ROUTE_ECONOMICS → bootstrap.route_economics.
 * DEFAULTS below are fallbacks only when a key is missing from bootstrap
 * (keep in sync with Python ROUTE_ECONOMICS).
 * Loaded before game.js; exposed as window.RunwayEconomics.
 */
(function (global) {
  'use strict';

  /** Fallback defaults — mirror runway_game_data.ROUTE_ECONOMICS */
  const DEFAULTS = {
    hub_profit_target_years: 2.5,
    marginal_payback_warn_years: 3.0,
    ramp_load_multipliers: [0.55, 0.78, 0.92],
    ramp_cost_creep_per_year: 0.03,
    avg_pax_load_factor: 0.8,
    /**
     * City-pair capture — pair competition dominates.
     * Whole-airport share is only a soft presence boost (a 7/wk regional hop
     * should not be crushed because CMH has 1800 deps/week).
     */
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
    cancel_load_threshold: 0.1,
  };

  function mergeConfig(bootstrap) {
    const src = (bootstrap && bootstrap.route_economics) || {};
    const mc = { ...DEFAULTS.market_capture, ...(src.market_capture || {}) };
    // Drop legacy dead keys so they never confuse creators.
    delete mc.presence_scale_min;
    delete mc.presence_scale_range;
    const ip = { ...DEFAULTS.imputed_pair, ...(src.imputed_pair || {}) };
    const mdSrc = src.market_departures || {};
    const md = {
      ...DEFAULTS.market_departures,
      ...mdSrc,
      avg_pax_tiers: mdSrc.avg_pax_tiers || DEFAULTS.market_departures.avg_pax_tiers,
    };
    // Python uses 1e9 as last-tier max; JS avgPax treats Infinity the same.
    if (md.avg_pax_tiers && md.avg_pax_tiers.length) {
      md.avg_pax_tiers = md.avg_pax_tiers.map((t) =>
        t.max_pax_m >= 1e8 ? { ...t, max_pax_m: Infinity } : t
      );
    }
    return {
      ...DEFAULTS,
      ...src,
      market_capture: mc,
      imputed_pair: ip,
      market_departures: md,
      ramp_load_multipliers: src.ramp_load_multipliers || DEFAULTS.ramp_load_multipliers,
      cancel_load_threshold:
        src.cancel_load_threshold != null ? src.cancel_load_threshold : DEFAULTS.cancel_load_threshold,
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

  /**
   * Capture of addressable city-pair demand.
   * Pair capacity share is the core lever; airport-wide share only softens presence.
   */
  function computeMarketCapture(params, cfg) {
    const mc = cfg.market_capture;
    const originShare = Math.min(
      mc.origin_share_cap,
      params.playerOriginDeps / Math.max(1, params.originMarketWeekly)
    );
    const pairDenom = Math.max(
      1,
      params.effectivePlayerFreq + params.compPairWeekly + params.imputedPairWeekly
    );
    const pairCapacityShare = params.effectivePlayerFreq / pairDenom;
    const repBoost = 1 + (params.reputation || 0) / mc.rep_divisor;
    const awareAvg = ((params.brandAwareOrigin || 5) + (params.brandAwareDest || 5)) / 2;
    const awareBoost = 1 + (awareAvg / 100) * mc.awareness_factor;
    const freqPresence =
      mc.freq_presence_base +
      Math.min(mc.freq_presence_max_add, params.effectivePlayerFreq / mc.freq_presence_divisor);

    // Pair-first core (not sqrt of airport share × pair — that zeroed thin majors).
    const pairCore = Math.max(mc.pair_share_floor, pairCapacityShare);
    const originPresence =
      mc.origin_presence_min +
      (1 - mc.origin_presence_min) *
        Math.min(1, Math.pow(Math.max(mc.origin_share_floor, originShare) / mc.presence_origin_target, 0.45));

    let capture = pairCore * originPresence * repBoost * awareBoost * freqPresence;

    // Mature brand on a known city-pair — floor so "existing airline" isn't empty.
    if (params.mature || awareAvg >= 40) {
      const floor = mc.mature_capture_floor || 0.14;
      capture = Math.max(capture, floor * Math.min(1.15, awareBoost));
    }

    capture = Math.min(mc.capture_cap, capture);

    return {
      originShare,
      destShare: Math.min(
        mc.origin_share_cap,
        (params.playerDestDeps || 0) / Math.max(1, params.destMarketWeekly || 1)
      ),
      pairCapacityShare,
      captureFactor: capture,
      pairDenom,
      originPresence,
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
