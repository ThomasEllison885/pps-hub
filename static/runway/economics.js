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
    /**
     * Station maturity from origin brand_awareness (0–100).
     * New / unknown cities capture less, pay more HQ share in judgment, ads work less.
     */
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

  function clamp01(x) {
    return Math.max(0, Math.min(1, x));
  }

  function lerp(a, b, t) {
    return a + (b - a) * clamp01(t);
  }

  function mergeConfig(bootstrap) {
    const src = (bootstrap && bootstrap.route_economics) || {};
    const mc = { ...DEFAULTS.market_capture, ...(src.market_capture || {}) };
    // Drop legacy dead keys so they never confuse creators.
    delete mc.presence_scale_min;
    delete mc.presence_scale_range;
    const hm = { ...DEFAULTS.hub_maturity, ...(src.hub_maturity || {}) };
    const ju = { ...DEFAULTS.judgment, ...(src.judgment || {}) };
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
      hub_maturity: hm,
      judgment: ju,
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
   * Hub maturity at a station from brand_awareness (0–100).
   * tier: new | building | mature
   */
  function hubMaturityFactors(brandOrigin, cfg) {
    const hm = (cfg && cfg.hub_maturity) || DEFAULTS.hub_maturity;
    const mc = (cfg && cfg.market_capture) || DEFAULTS.market_capture;
    const brand = Math.max(0, Math.min(100, brandOrigin == null ? 5 : +brandOrigin));
    let tier = 'new';
    if (brand >= hm.aware_mature) tier = 'mature';
    else if (brand >= hm.aware_building) tier = 'building';

    const span = Math.max(1, hm.aware_mature - hm.aware_new);
    const t = clamp01((brand - hm.aware_new) / span);
    const matureFloor = mc.mature_capture_floor != null ? mc.mature_capture_floor : 0.14;
    const captureFloor = lerp(hm.capture_floor_new, matureFloor, t);

    let overheadMult = hm.overhead_new_mult;
    let mktEfficiency = hm.mkt_efficiency_new;
    if (tier === 'building') {
      overheadMult = hm.overhead_building_mult;
      mktEfficiency = hm.mkt_efficiency_building;
    } else if (tier === 'mature') {
      overheadMult = hm.overhead_mature_mult;
      mktEfficiency = hm.mkt_efficiency_mature;
    }

    // Smooth overhead / efficiency between building and mature for nicer curves.
    if (brand >= hm.aware_building && brand < hm.aware_mature) {
      const t2 = clamp01((brand - hm.aware_building) / Math.max(1, hm.aware_mature - hm.aware_building));
      overheadMult = lerp(hm.overhead_building_mult, hm.overhead_mature_mult, t2);
      mktEfficiency = lerp(hm.mkt_efficiency_building, hm.mkt_efficiency_mature, t2);
    } else if (brand < hm.aware_building) {
      const t0 = clamp01(brand / Math.max(1, hm.aware_building));
      overheadMult = lerp(hm.overhead_new_mult, hm.overhead_building_mult, t0);
      mktEfficiency = lerp(hm.mkt_efficiency_new, hm.mkt_efficiency_building, t0);
    }

    const originPresenceBrandAdd = hm.origin_presence_brand_boost * (brand / 100);
    // Year-1 ramp multiplier boost: unknown hubs stay at base ramp; mature hubs ramp faster.
    const rampBrandBoost = (hm.ramp_brand_lift || 0) * (brand / 100);

    return {
      brand,
      tier,
      captureFloor,
      originPresenceBrandAdd,
      overheadMult,
      mktEfficiency,
      rampBrandBoost,
      organicBrandPerRouteMo: hm.organic_brand_per_route_mo,
      organicBrandCapWithoutAds: hm.organic_brand_cap_without_ads,
      label:
        tier === 'mature' ? 'Mature hub' : tier === 'building' ? 'Building presence' : 'New station',
    };
  }

  /**
   * Capture of addressable city-pair demand.
   * Pair capacity share is the core lever; airport-wide share only softens presence.
   * Origin brand_awareness scales presence boost and capture floor (hub maturity).
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
    const brandO = params.brandAwareOrigin != null ? params.brandAwareOrigin : 5;
    const brandD = params.brandAwareDest != null ? params.brandAwareDest : 5;
    const awareAvg = (brandO + brandD) / 2;
    const awareBoost = 1 + (awareAvg / 100) * mc.awareness_factor;
    const freqPresence =
      mc.freq_presence_base +
      Math.min(mc.freq_presence_max_add, params.effectivePlayerFreq / mc.freq_presence_divisor);

    const maturity = hubMaturityFactors(brandO, cfg);

    // Pair-first core (not sqrt of airport share × pair — that zeroed thin majors).
    const pairCore = Math.max(mc.pair_share_floor, pairCapacityShare);
    let originPresence =
      mc.origin_presence_min +
      (1 - mc.origin_presence_min) *
        Math.min(1, Math.pow(Math.max(mc.origin_share_floor, originShare) / mc.presence_origin_target, 0.45));
    // Known stations punch above pure departure share.
    originPresence = Math.min(1, originPresence + maturity.originPresenceBrandAdd);

    let capture = pairCore * originPresence * repBoost * awareBoost * freqPresence;

    // Brand-scaled capture floor — mature/established pairs fill seats; greenfield stays soft.
    const hm = cfg.hub_maturity || DEFAULTS.hub_maturity;
    const floor = maturity.captureFloor;
    if (params.mature || brandO >= hm.aware_building || awareAvg >= 40) {
      capture = Math.max(capture, floor * Math.min(1.15, awareBoost));
    } else {
      // Soft greenfield floor so brand building still matters without zeroing load.
      capture = Math.max(capture, floor * 0.72 * Math.min(1.08, awareBoost));
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
      hubMaturity: maturity,
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
    hubMaturityFactors,
    computeMarketCapture,
    estimateLoadFromDemand,
  };
})(typeof window !== 'undefined' ? window : global);
