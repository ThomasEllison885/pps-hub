/**
 * RouteLab — airline network economics simulation (MVP v0.1)
 */
(function () {
  'use strict';

  /** Legacy single-blob key (migrated into v2 slot index on first load). */
  const SAVE_KEY_LEGACY = 'runway_save_v1';
  /** Multi-slot save index: state only (no airport tables). */
  const SAVE_INDEX_KEY = 'routelab_saves_v2';
  const SAVE_FORMAT_VERSION = 2;
  const MANUAL_SLOT_IDS = ['slot1', 'slot2', 'slot3', 'slot4', 'slot5'];
  const AUTOSAVE_SLOT_ID = 'autosave';
  let activeSaveSlotId = AUTOSAVE_SLOT_ID;
  let saveModalMode = null; // 'save' | 'load'
  let MAP_W = 960;
  let MAP_H = 520;
  let MAP_ZOOM_MIN_W = MAP_W * 0.22;
  let MAP_ZOOM_MAX_W = MAP_W * 2.2;
  let bootstrap = null;
  let initialAirports = null;
  let mapConfig = null;
  let activeMapKey = 'usa';
  let tutorialHighlightResize = null;
  let tutorialGlowTarget = null;
  let fleetShopOpen = false;
  let hudPanels = { financials: false, economy: false };
  let hudFinancialsView = 'company';
  let opsGuideCollapsed = null; // null = not yet defaulted this session; see renderOpsGuide
  let airportSections = { market: false, competition: true, position: true };
  let contextPulseTimer = null;
  let scoreboardOpen = false;
  let scoreboardSortBy = 'overall';
  let selectedRival = null;
  let routeLaunchDraft = null;
  let routeLaunchActive = false;
  let routeLaunchStep = 1; // 1 Market · 2 Product · 3 Growth · 4 Launch
  /** Soft-closed studio draft so map/backdrop mis-taps don't lose work. */
  let routeStudioResume = null;
  let routeFormDraft = null;
  let routeReviewRouteId = null;
  let planeDetailId = null;
  let pendingEmblem = 'routes';
  let pendingAncillaryStrategy = 'auto';
  let state = null;
  let tickTimer = null;
  let selectedAirport = null;
  let selectedRouteId = null;
  let mapView = { x: 0, y: 0, w: MAP_W, h: MAP_H };
  let fleetPending = null;
  let pendingScenarioId = null;
  let speedBeforePause = 'day';
  let decisionQueue = [];
  let activeDecision = null;
  let decisionSpeedBeforePause = 'day';
  let coalescedDecisionCount = 0;
  let mapDrag = {
    active: false,
    moved: false,
    startX: 0,
    startY: 0,
    viewX: 0,
    viewY: 0,
    clickIata: null,
    clickRouteId: null,
    pointerId: null,
  };
  let mapboxMap = null;
  let mapboxReady = false;
  let mapboxInitStarted = false;
  const MAPBOX_STYLE = 'mapbox://styles/mapbox/dark-v11';
  const DEPARTURES_PER_GATE_PER_WEEK = 14; // fallback if airport ops data missing
  const ROUTE_STATS_WINDOW_DAYS = 30;
  const ROUTE_HISTORY_MAX_DAYS = 90;
  const REACTIVE_COMPETITOR_COOLDOWN_DAYS = 14;
  /**
   * Staged mid-game goals after the 9-step regional build track.
   * phase: expand → sustain → scale → exit (shown in coach / session recap).
   */
  const OPS_MIDGAME_GOALS = [
    {
      id: 'rt_pairs_2',
      phase: 'expand',
      phaseLabel: 'Phase 2 · Expand',
      label: 'Two round-trip markets',
      hint: 'Sell seats both ways — open return legs so planes do not ferry empty.',
      tab: 'routes',
    },
    {
      id: 'profit_month',
      phase: 'sustain',
      phaseLabel: 'Phase 3 · Sustain',
      label: 'Profitable trailing month',
      hint: 'Fix losing routes before adding more thin markets.',
      tab: 'routes',
    },
    {
      id: 'hub_presence',
      phase: 'sustain',
      phaseLabel: 'Phase 3 · Sustain',
      label: 'Hub presence: 8%+ of departures at main base',
      hint: 'Add frequency from your busiest gate until you own real share.',
      tab: 'routes',
    },
    {
      id: 'network_6',
      phase: 'scale',
      phaseLabel: 'Phase 4 · Scale',
      label: 'Network: six active routes',
      hint: 'A true regional web — six city pairs flying.',
      tab: 'routes',
    },
    {
      id: 'ltm_25m',
      phase: 'scale',
      phaseLabel: 'Phase 4 · Scale',
      label: 'Scale: $25M LTM revenue',
      hint: 'Grow frequency and markets — PE/IPO ladder starts here.',
      tab: 'routes',
    },
    {
      id: 'pressure_win',
      phase: 'scale',
      phaseLabel: 'Phase 4 · Scale',
      label: 'Win a contested route (pressure ≥55, green P&L)',
      hint: 'Hold load and margin where rivals fight you.',
      tab: 'routes',
    },
    {
      id: 'second_base_profit',
      phase: 'scale',
      phaseLabel: 'Phase 4 · Scale',
      label: 'Two profitable bases',
      hint: 'Green variable P&L from two different origin airports.',
      tab: 'routes',
    },
    {
      id: 'capital_event',
      phase: 'exit',
      phaseLabel: 'Phase 5 · Capital',
      label: 'Close PE, secondary, or IPO',
      hint: 'Use Capital when the network can carry board pressure.',
      tab: 'finance',
    },
  ];

  const $ = (id) => document.getElementById(id);
  const MOBILE_MQ = '(max-width: 900px)';
  const TOUCH_MQ = '(max-width: 900px), (pointer: coarse)';

  function isMobileLayout() {
    return window.matchMedia(MOBILE_MQ).matches;
  }

  function isCoarsePointer() {
    return window.matchMedia(TOUCH_MQ).matches;
  }

  function mapDotRadius(baseR) {
    return isCoarsePointer() ? baseR + 8 : baseR;
  }

  function syncMobileDock(active) {
    document.querySelectorAll('[data-mobile-nav]').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.mobileNav === active);
    });
  }

  function scrollToMap(opts) {
    opts = opts || {};
    const wrap = $('map-wrap') || document.querySelector('.map-wrap');
    if (wrap && opts.expand !== false && wrap.classList.contains('map-collapsed')) {
      wrap.classList.remove('map-collapsed');
      ensureMapboxSize();
      drawMap();
    }
    if (wrap) wrap.scrollIntoView({ behavior: opts.instant ? 'auto' : 'smooth', block: 'start' });
    syncMobileDock('map');
  }

  function scrollToSidePanel() {
    const panel = document.querySelector('.side-panel');
    if (!panel) return;
    // Mobile: bring the panel into the viewport. Desktop: map is fixed — only scroll the panel itself.
    if (isMobileLayout()) {
      panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } else {
      panel.scrollTo({ top: 0, behavior: 'smooth' });
    }
  }

  /** Scroll a node into view inside the side panel without moving the map/page. */
  function scrollSidePanelTo(el, opts) {
    if (!el) return;
    opts = opts || {};
    const behavior = opts.behavior || 'smooth';
    const block = opts.block || 'nearest';
    // Prefer native scrollIntoView so sticky footers / tall fleet shop always reach the CTA.
    try {
      el.scrollIntoView({ behavior, block: block === 'nearest' ? 'center' : block, inline: 'nearest' });
    } catch (e) {
      el.scrollIntoView(true);
    }
    if (isMobileLayout()) return;
    const panel = document.querySelector('.side-panel');
    if (!panel) return;
    // Nudge the side panel itself if the element is still clipped (sticky header/footer).
    requestAnimationFrame(() => {
      const pRect = panel.getBoundingClientRect();
      const eRect = el.getBoundingClientRect();
      if (eRect.bottom > pRect.bottom - 12) {
        panel.scrollBy({ top: eRect.bottom - pRect.bottom + 48, behavior });
      } else if (eRect.top < pRect.top + 8) {
        panel.scrollBy({ top: eRect.top - pRect.top - 24, behavior });
      }
    });
  }

  function setMapCollapsed(collapsed) {
    const wrap = $('map-wrap');
    if (!wrap || !isMobileLayout()) return;
    wrap.classList.toggle('map-collapsed', !!collapsed);
    if (!collapsed) {
      ensureMapboxSize();
      drawMap();
    }
  }

  function routeEconomics() {
    const E = window.RunwayEconomics;
    if (E && bootstrap) return E.mergeConfig(bootstrap);
    return (
      bootstrap.route_economics || {
        hub_profit_target_years: 2.5,
        marginal_payback_warn_years: 3.0,
        ramp_load_multipliers: [0.55, 0.78, 0.92],
        ramp_cost_creep_per_year: 0.03,
      }
    );
  }

  const RunwayEcon = () => window.RunwayEconomics;

  function airportGateWeeklyCapacity(ap) {
    if (!ap) return DEPARTURES_PER_GATE_PER_WEEK;
    if (ap.max_weekly_departures_per_gate) return ap.max_weekly_departures_per_gate;
    const hrs = ap.ops_hours_per_day || 14;
    const dph = ap.max_departures_per_hour || 2;
    const days = ap.operating_days_per_week || 6;
    return Math.max(4, Math.floor(hrs * dph * days * 0.82));
  }

  function maxFrequencyForRoute(origin, dest, acTypeId) {
    const ap = airport(origin);
    const dAp = airport(dest);
    const ac = aircraftType(acTypeId);
    if (!ap || !dAp || !ac) return 28;
    const dist = haversineNm(ap.lat, ap.lon, dAp.lat, dAp.lon);
    const block = blockHours(dist, ac);
    const turnaroundH = (ap.min_turnaround_min || 90) / 60;
    const cycleH = Math.max(0.75, block + turnaroundH);
    const dailySlots = Math.floor((ap.ops_hours_per_day || 14) / cycleH);
    const weekly = dailySlots * (ap.operating_days_per_week || 6);
    return Math.max(1, Math.min(28, weekly));
  }

  /** Round block hours for stable UI math (avoids 37.400000000000006). */
  function cleanHours(n, decimals) {
    const d = decimals != null ? decimals : 2;
    const x = +n;
    if (!Number.isFinite(x)) return 0;
    const f = 10 ** d;
    return Math.round(x * f) / f;
  }

  /**
   * Weekly block hours a route consumes on its assigned aircraft.
   * One-way only counts once if a return leg exists on the same metal; otherwise
   * ferry-home is charged (plane can't vanish at destination).
   */
  function routeWeeklyBlockHours(route, opts) {
    opts = opts || {};
    const ac = aircraftType(route.aircraft_type);
    if (!ac) return 0;
    const dist = routeDistance(route);
    if (!Number.isFinite(dist)) return 0;
    const freq = route.frequency_week || 0;
    const prod = routeProduct(routeProductId(route));
    // Tag A–B–C: both revenue segments on the same trip (no separate ferry if C is end)
    if (prod.isTag && route.tag_dest) {
      const mid = airport(route.dest);
      const end = airport(route.tag_dest);
      let hours = blockHours(dist, ac) * freq;
      if (mid && end) {
        hours += blockHours(haversineNm(mid.lat, mid.lon, end.lat, end.lon), ac) * freq;
      }
      // Optional deadhead C→A if no reverse tag — charge half ferry home
      hours += blockHours(dist, ac) * freq * 0.45;
      return cleanHours(hours);
    }
    const oneWay = blockHours(dist, ac) * freq;
    // Same aircraft flying the reverse route = real RT product; don't double-count ferry.
    const reverse =
      !opts.ignoreReturn &&
      (state.routes || []).find(
        (r) =>
          r.id !== route.id &&
          r.aircraft_id &&
          route.aircraft_id &&
          r.aircraft_id === route.aircraft_id &&
          r.origin === route.dest &&
          r.dest === route.origin
      );
    if (reverse) return cleanHours(oneWay);
    // No paired return on this metal → empty ferry home (or assume RT block).
    return cleanHours(oneWay * 2);
  }

  function planeWeeklyBlockHoursCapacity(plane) {
    const ac = aircraftType(plane.type);
    // 6 operating days × target block hours/day — one plane, one timeline.
    const daily = ac?.target_block_hours_day || 8;
    return cleanHours(daily * 6, 1);
  }

  function planeWeeklyBlockHoursUsed(planeId, excludeRouteId) {
    return cleanHours(
      (state.routes || []).reduce((sum, r) => {
        if (r.aircraft_id !== planeId || r.id === excludeRouteId) return sum;
        return sum + routeWeeklyBlockHours(r);
      }, 0)
    );
  }

  function planeScheduleScaleForRoute(planeId, mockRoute, excludeRouteId) {
    const plane = state.fleet.find((f) => f.id === planeId);
    if (!plane) return 1;
    let scheduledDaily = 0;
    (state.routes || []).forEach((r) => {
      if (r.aircraft_id !== planeId || r.id === excludeRouteId) return;
      // Convert weekly block (incl. ferry when unpaired) to average daily
      scheduledDaily += routeWeeklyBlockHours(r) / 7;
    });
    if (mockRoute) {
      const ac = aircraftType(mockRoute.aircraft_type);
      if (ac && Number.isFinite(routeDistance(mockRoute))) {
        const mock = {
          ...mockRoute,
          aircraft_id: planeId,
          aircraft_type: mockRoute.aircraft_type || (plane && plane.type),
        };
        // Tentative: if mock creates a pair with existing reverse, no ferry
        scheduledDaily += routeWeeklyBlockHours(mock) / 7;
      }
    }
    const target = planeTargetBlockHoursDay(plane);
    if (scheduledDaily <= target || scheduledDaily <= 0) return 1;
    return target / scheduledDaily;
  }

  function planeScheduleLabel(planeId, origin, dest, freq, acTypeId, excludeRouteId) {
    const plane = state.fleet.find((f) => f.id === planeId);
    if (!plane) return null;
    const cap = planeWeeklyBlockHoursCapacity(plane);
    const baseUsed = planeWeeklyBlockHoursUsed(planeId, excludeRouteId);
    let after = baseUsed;
    const ac = aircraftType(acTypeId);
    const oAp = airport(origin);
    const dAp = airport(dest);
    if (freq > 0 && ac && oAp && dAp) {
      const dist = haversineNm(oAp.lat, oAp.lon, dAp.lat, dAp.lon);
      const perOneWay = blockHours(dist, ac);
      const hasPairOnMetal = (state.routes || []).some(
        (r) =>
          r.aircraft_id === planeId &&
          r.id !== excludeRouteId &&
          r.origin === dest &&
          r.dest === origin
      );
      // Unpaired = ferry home (2× one-way); paired return product = 1× per weekly dep
      after = cleanHours(baseUsed + perOneWay * freq * (hasPairOnMetal ? 1 : 2));
    }
    const remaining = cleanHours(Math.max(0, cap - after));
    return {
      cap,
      used: baseUsed,
      after,
      ok: after <= cap + 0.05,
      remaining,
      routesOn: (state.routes || []).filter((r) => r.aircraft_id === planeId && r.id !== excludeRouteId).length,
      ferryIfUnpaired: true,
    };
  }

  function maxFrequencyForAircraft(planeId, origin, dest, acTypeId, excludeRouteId) {
    const plane = state.fleet.find((f) => f.id === planeId);
    const ac = aircraftType(acTypeId);
    const oAp = airport(origin);
    const dAp = airport(dest);
    if (!plane || !ac || !oAp || !dAp) return 0;
    const perOneWay = blockHours(haversineNm(oAp.lat, oAp.lon, dAp.lat, dAp.lon), ac);
    if (perOneWay <= 0) return 28;
    // If reverse already on this metal, adding freq only costs one-way; else ferry = 2×
    const hasPairOnMetal = (state.routes || []).some(
      (r) =>
        r.aircraft_id === planeId &&
        r.id !== excludeRouteId &&
        r.origin === dest &&
        r.dest === origin
    );
    const hoursPerWeeklyDep = hasPairOnMetal ? perOneWay : perOneWay * 2;
    const remaining = Math.max(
      0,
      planeWeeklyBlockHoursCapacity(plane) - planeWeeklyBlockHoursUsed(planeId, excludeRouteId)
    );
    return Math.max(0, Math.floor(remaining / Math.max(0.01, hoursPerWeeklyDep)));
  }

  function launchFrequencyCap(draft, excludeRouteId) {
    const plane = state.fleet.find((f) => f.id === draft.aircraftId);
    const acType = plane ? plane.type : 'e175';
    const gateHeadroom = gateCapacityRemaining(draft.origin, excludeRouteId) + (draft.freq || 0);
    const aircraftHeadroom = maxFrequencyForAircraft(
      draft.aircraftId,
      draft.origin,
      draft.dest,
      acType,
      excludeRouteId
    );
    const cap = Math.min(
      28,
      maxFrequencyForRoute(draft.origin, draft.dest, acType),
      gateHeadroom,
      aircraftHeadroom
    );
    return cap > 0 ? cap : 0;
  }

  function aircraftScheduleError(planeId, origin, dest, freq, acTypeId, excludeRouteId) {
    const plane = state.fleet.find((f) => f.id === planeId);
    if (!plane) return 'Select an aircraft from your fleet.';
    const sched = planeScheduleLabel(planeId, origin, dest, freq, acTypeId, excludeRouteId);
    if (!sched || sched.ok) return null;
    const ac = aircraftType(acTypeId);
    const routeNote =
      sched.routesOn > 0
        ? ` — aircraft already flies ${sched.routesOn} other route${sched.routesOn === 1 ? '' : 's'}`
        : '';
    return (
      `This plane's already booked solid — cut your frequency, shift an existing route to another aircraft, or lease a second plane. ` +
      `(One ${ac ? ac.name : 'plane'} can only be in one place at a time: ~${fmtHours(sched.cap)} block-hr/wk available, ` +
      `this plan needs ${fmtHours(sched.after)} hr/wk${routeNote}.)`
    );
  }

  function routeAvailabilityContext(origin, dest, aircraftId, freq, excludeRouteId) {
    const f = freq || 0;
    const plane = aircraftId ? state.fleet.find((p) => p.id === aircraftId) : null;
    const acType = plane ? plane.type : origin && dest ? recommendAircraftTypeForPair(origin, dest) : null;
    const hasGate = origin ? hasGateAt(origin) : false;
    const exists =
      origin && dest
        ? state.routes.some(
            (r) => r.origin === origin && r.dest === dest && r.id !== excludeRouteId
          )
        : false;

    const gate = hasGate
      ? {
          max: maxFrequencyAtOrigin(origin),
          used: originFrequencyUsed(origin, excludeRouteId),
          remaining: gateCapacityRemaining(origin, excludeRouteId),
          after: originFrequencyUsed(origin, excludeRouteId) + f,
          ok: originFrequencyUsed(origin, excludeRouteId) + f <= maxFrequencyAtOrigin(origin),
        }
      : null;

    let aircraft = null;
    let airportOps = null;
    if (origin && dest && acType) {
      airportOps = { max: maxFrequencyForRoute(origin, dest, acType) };
      if (plane) {
        const sched = planeScheduleLabel(plane.id, origin, dest, f, acType, excludeRouteId);
        aircraft = {
          id: plane.id,
          name: aircraftType(acType)?.name || plane.type,
          cap: sched.cap,
          used: sched.used,
          after: sched.after,
          remaining: Math.max(0, sched.cap - sched.after),
          maxFreq: maxFrequencyForAircraft(plane.id, origin, dest, acType, excludeRouteId),
          routesOn: sched.routesOn,
          ok: sched.ok,
        };
      }
    }

    const launchMax =
      origin && dest && plane
        ? launchFrequencyCap(
            { origin, dest, aircraftId: plane.id, freq: f || 7 },
            excludeRouteId
          )
        : 0;

    let market = null;
    if (origin) {
      if (dest && acType) {
        const mockRoute = {
          origin,
          dest,
          aircraft_type: acType,
          aircraft_id: aircraftId,
          frequency_week: f,
        };
        const schedScale = aircraftId ? planeScheduleScaleForRoute(aircraftId, mockRoute, excludeRouteId) : 1;
        market = routeMarketContext(mockRoute, {
          isProposed: true,
          proposedFreq: f,
          excludeRouteId,
        });
        market.opDays = airport(origin)?.operating_days_per_week || 6;
        market.schedScale = schedScale;
        market.imputedPairWeekly = imputedPairMarketWeekly(origin, dest);
      } else {
        market = airportMarketPresence(origin, excludeRouteId, f);
      }
    }

    const limits = [];
    if (gate) limits.push({ key: 'gate', headroom: gate.remaining, label: 'Gate' });
    if (aircraft) limits.push({ key: 'aircraft', headroom: aircraft.maxFreq, label: 'Aircraft' });
    if (airportOps) limits.push({ key: 'airport', headroom: airportOps.max, label: 'Airport hours' });
    if (market && market.originShare != null && market.originShare < 0.12) {
      limits.push({
        key: 'airport_presence',
        headroom: market.originShare * 100,
        label: 'Airport market share',
      });
    }
    limits.sort((a, b) => a.headroom - b.headroom);
    const bottleneck = limits.length ? limits[0].key : null;
    if (market) market.bottleneck = bottleneck;

    const options = [];
    if (!hasGate && origin) {
      options.push({ type: 'lease_gate', text: `Lease a gate at <b>${origin}</b> before launching departures.` });
    }
    if (exists) {
      options.push({ type: 'exists', text: `You already fly <b>${origin}–${dest}</b> — bump frequency on the running route instead.` });
    }
    if (launchMax > 0 && f > launchMax) {
      options.push({
        type: 'lower_freq',
        text: `Max <b>${launchMax}/wk</b> right now on this pair — lower frequency or free capacity first.`,
        freq: launchMax,
      });
    } else if (launchMax > 0 && bottleneck === 'aircraft' && aircraft && aircraft.routesOn > 0) {
      options.push({
        type: 'aircraft_shared',
        text: `Aircraft already on <b>${aircraft.routesOn}</b> route${aircraft.routesOn === 1 ? '' : 's'} — up to <b>${launchMax}/wk</b> more on this leg.`,
        freq: launchMax,
      });
    } else if (launchMax > 0) {
      options.push({ type: 'ok', text: `Up to <b>${launchMax}/wk</b> available on this route now.`, freq: launchMax });
    }
    if (bottleneck === 'aircraft' && gate && gate.remaining >= 3) {
      const busy = (state.fleet || []).every((p) => {
        const cap = planeWeeklyBlockHoursCapacity(p);
        return planeWeeklyBlockHoursUsed(p.id, excludeRouteId) >= cap * 0.9;
      });
      if (busy && state.fleet.length === 1) {
        options.push({ type: 'fleet', text: 'Gate has open slots — <b>lease a second aircraft</b> to use them.', tab: 'fleet' });
      }
    }
    if (origin && hasGate && !exists) {
      const util = gateUtilizationAt(origin);
      if (util.routesFrom.length === 1 && util.remaining >= 2) {
        const r = util.routesFrom[0];
        options.push({
          type: 'bump',
          text: `Or add frequency on <b>${r.origin}–${r.dest}</b> (+${Math.min(7, util.remaining)}/wk gate room).`,
          routeId: r.id,
          delta: Math.min(7, util.remaining),
        });
      }
    }
    if (market && market.originShare < 0.04 && dest) {
      const daily = airportMarketDeparturesDaily(airport(origin));
      options.push({
        type: 'market_thin',
        text: `You're <b>${formatMarketSharePct(market.originShare)}</b> of ~<b>${daily}</b> daily departures at <b>${origin}</b> — loads stay thin until you grow frequency, fleet, or airport presence.`,
      });
    } else if (market && market.originShare < 0.04 && !dest) {
      const daily = market.originMarketDaily || 0;
      options.push({
        type: 'market_thin',
        text: `With one plane you might fly <b>1</b> of ~<b>${daily}</b> daily departures here — roughly <b>${formatMarketSharePct(1 / Math.max(1, daily))}</b> airport share before you add routes.`,
      });
    }

    const fleet = (state.fleet || []).map((p) => {
      const ac = aircraftType(p.type);
      const cap = planeWeeklyBlockHoursCapacity(p);
      const used = planeWeeklyBlockHoursUsed(p.id, excludeRouteId);
      const routesOn = state.routes.filter((r) => r.aircraft_id === p.id && r.id !== excludeRouteId).length;
      const maxFreq =
        origin && dest ? maxFrequencyForAircraft(p.id, origin, dest, p.type, excludeRouteId) : 0;
      return {
        id: p.id,
        name: ac?.name || p.type,
        cap,
        used,
        pct: cap > 0 ? (used / cap) * 100 : 0,
        routesOn,
        maxFreq,
        headroom: Math.max(0, cap - used),
      };
    });

    const routesOnPlane =
      plane && state.routes
        ? state.routes.filter((r) => r.aircraft_id === plane.id && r.id !== excludeRouteId).length
        : 0;

    return {
      origin,
      dest,
      freq: f,
      plane,
      acType,
      hasGate,
      exists,
      gate,
      aircraft,
      airportOps,
      launchMax,
      bottleneck,
      market,
      options,
      fleet,
      singlePlaneSingleRoute: state.fleet.length === 1 && routesOnPlane === 0 && !!dest,
      valid: hasGate && !exists && launchMax > 0 && f <= launchMax && f >= 1,
    };
  }

  function formatMarketSharePct(share) {
    const pct = (share || 0) * 100;
    if (pct >= 10) return `${pct.toFixed(1)}%`;
    if (pct >= 1) return `${pct.toFixed(2)}%`;
    return `${pct.toFixed(2)}%`;
  }

  function playerDeparturesDailyFrom(iata, excludeRouteId, addWeekly) {
    const ap = airport(iata);
    const opDays = ap?.operating_days_per_week || 6;
    return playerDeparturesWeeklyFrom(iata, excludeRouteId, addWeekly) / opDays;
  }

  function airportMarketPresence(origin, excludeRouteId, addWeekly) {
    const oAp = airport(origin);
    if (!oAp) return null;
    const originMarketWeekly = totalMarketDeparturesWeeklyAt(origin);
    const playerOriginDeps = playerDeparturesWeeklyFrom(origin, excludeRouteId, addWeekly || 0);
    const opDays = oAp.operating_days_per_week || 6;
    return {
      origin,
      originMarketWeekly,
      originMarketDaily: airportMarketDeparturesDaily(oAp),
      playerOriginDeps,
      playerOriginDepsCurrent: playerDeparturesWeeklyFrom(origin, excludeRouteId, 0),
      playerOriginDaily: playerOriginDeps / opDays,
      originShare: Math.min(0.95, playerOriginDeps / Math.max(1, originMarketWeekly)),
      opDays,
    };
  }

  function marketScopePanelHtml(mkt, opts) {
    opts = opts || {};
    if (!mkt || !mkt.origin) return '';
    const bn = opts.bottleneck || mkt.bottleneck;
    const currentWeekly = mkt.playerOriginDepsCurrent != null ? mkt.playerOriginDepsCurrent : mkt.playerOriginDeps;
    const plannedWeekly = opts.plannedWeekly != null ? opts.plannedWeekly : mkt.playerOriginDeps;
    const plannedDaily = plannedWeekly / (mkt.opDays || 6);
    const sharePct = formatMarketSharePct(
      plannedWeekly / Math.max(1, mkt.originMarketWeekly || 1)
    );
    const originShare = plannedWeekly / Math.max(1, mkt.originMarketWeekly || 1);
    const collapseMarket = originShare >= 0.12 || (mkt.captureFactor || 0) >= 0.35;

    let rows = availabilityBarRow(
      `${mkt.origin} deps`,
      currentWeekly,
      mkt.originMarketWeekly,
      '/wk',
      bn,
      'airport_presence',
      { after: plannedWeekly !== currentWeekly ? plannedWeekly : null }
    );

    let pairBlock = '';
    if (mkt.dest) {
      rows += availabilityBarRow(
        `${mkt.origin}–${mkt.dest}`,
        mkt.effectivePlayerFreq || 0,
        Math.max(1, (mkt.effectivePlayerFreq || 0) + (mkt.compPairWeekly || 0) + (mkt.imputedPairWeekly || 0)),
        '/wk cap.',
        bn,
        'route_competition',
        { after: opts.plannedFreq || null }
      );
      pairBlock = `<p class="avail-market-note muted">Route capacity share <b>${formatMarketSharePct(mkt.pairCapacityShare || 0)}</b> on this city-pair · demand capture <b>${formatMarketSharePct(mkt.captureFactor || 0)}</b> of addressable O-D traffic.</p>`;
    }

    const planeNote =
      opts.singlePlaneSingleRoute && bn !== 'aircraft'
        ? '<p class="avail-market-note muted">One plane on one route — <b>aircraft hours are not the limit</b>; your slice of airport departures caps realistic loads.</p>'
        : opts.schedScale < 0.98
          ? `<p class="avail-market-note muted">Aircraft over-scheduled — only ~<b>${Math.round((opts.schedScale || 1) * 100)}%</b> of planned frequency can fly.</p>`
          : '';

    return `<details class="avail-market-scope"${collapseMarket ? '' : ' open'}>
      <summary class="avail-market-title">Market scope <span class="muted">(all airlines)</span> · you <b>${sharePct}</b> of ${mkt.origin}</summary>
      ${rows}
      <p class="avail-market-note muted"><b>${mkt.origin}</b> sees ~<b>${Math.round(mkt.originMarketDaily || 0)}</b> departures/day (~<b>${Math.round(mkt.originMarketWeekly || 0)}</b>/wk). You would operate <b>${plannedDaily.toFixed(1)}</b>/day — <b>${sharePct}</b> of that airport's traffic. Gate slots are separate; this is total market size.</p>
      ${mkt.destMarketDaily ? `<p class="avail-market-note muted"><b>${mkt.dest}</b> market ~<b>${Math.round(mkt.destMarketDaily)}</b>/day — you don't need a gate there to land, but you're not originating from ${mkt.dest} on this route.</p>` : ''}
      ${pairBlock}
      ${planeNote}
    </details>`;
  }

  function launchLimitsStripHtml(draft) {
    if (!draft || !draft.origin) return '';
    const ctx = routeAvailabilityContext(draft.origin, draft.dest, draft.aircraftId, draft.freq);
    if (!ctx) return '';
    const chips = [];
    if (ctx.gate) {
      const pct = ctx.gate.max > 0 ? Math.min(100, (ctx.gate.after / ctx.gate.max) * 100) : 0;
      const cls = pct >= 92 ? 'danger' : pct >= 78 ? 'warn' : '';
      chips.push(
        `<span class="launch-limit-chip ${cls}" title="Gate departures per week">Gate <b>${ctx.gate.after}/${ctx.gate.max}</b>/wk</span>`
      );
    }
    if (ctx.aircraft) {
      const pct = ctx.aircraft.cap > 0 ? Math.min(100, (ctx.aircraft.after / ctx.aircraft.cap) * 100) : 0;
      const cls = pct >= 92 ? 'danger' : pct >= 78 ? 'warn' : '';
      chips.push(
        `<span class="launch-limit-chip ${cls}" title="Block hours scheduled on this aircraft">Aircraft <b>${fmtHours(ctx.aircraft.after)}/${fmtHours(ctx.aircraft.cap)}</b> hr/wk</span>`
      );
    }
    if (ctx.market) {
      const share = formatMarketSharePct(
        (ctx.market.playerOriginDeps || 0) / Math.max(1, ctx.market.originMarketWeekly || 1)
      );
      const cap = formatMarketSharePct(ctx.market.captureFactor || 0);
      const cls = (ctx.market.captureFactor || 0) < 0.1 ? 'warn' : '';
      chips.push(
        `<span class="launch-limit-chip ${cls}" title="Your share of airport departures and O-D demand capture">Market <b>${share}</b> · <b>${cap}</b> capture</span>`
      );
    }
    if (!chips.length) return '';
    const bn =
      ctx.bottleneck === 'gate'
        ? 'gate'
        : ctx.bottleneck === 'aircraft'
          ? 'aircraft'
          : ctx.bottleneck === 'airport_presence' || ctx.bottleneck === 'route_competition'
            ? 'market'
            : '';
    return `<div class="launch-limits-strip" aria-label="Three limits: gate, aircraft, market">${chips.join('')}${
      bn ? `<span class="launch-limit-bn muted">Limiting: <b>${bn}</b></span>` : ''
    }</div>`;
  }

  function marketJudgmentOneLiner(draft) {
    const plane = state.fleet.find((f) => f.id === draft.aircraftId);
    if (!plane) return '';
    const via = estimateRouteViability(
      draft.origin,
      draft.dest,
      plane.type,
      draft.freq,
      draft.fare,
      draft.aircraftId
    );
    const mkt = via.market;
    if (!mkt) return '';
    const share = formatMarketSharePct(mkt.originShare || 0);
    const cap = formatMarketSharePct(mkt.captureFactor || 0);
    const loadPct = (via.load * 100).toFixed(0);
    const thin = via.load < 0.45;
    return `<p class="judgment-market-line${thin ? ' thin' : ''}">Market slice: <b>${share}</b> of <b>${draft.origin}</b> departures · <b>${cap}</b> demand capture → ~<b>${loadPct}%</b> est. load${
      thin ? ' — thin market; smaller aircraft or more weekly frequency usually helps.' : '.'
    }</p>`;
  }

  /** Clean display for block hours (avoids 37.400000000000006). */
  function fmtHours(n, decimals) {
    if (n == null || !Number.isFinite(+n)) return '—';
    const d = decimals != null ? decimals : 1;
    const v = +(+n).toFixed(d);
    // Drop trailing .0 for whole numbers when using 1 decimal
    if (d === 1 && Math.abs(v - Math.round(v)) < 1e-9) return String(Math.round(v));
    return v.toFixed(d);
  }

  function availabilityBarRow(label, used, max, unit, bottleneckKey, rowKey, opts) {
    opts = opts || {};
    const dec = opts.decimals != null ? opts.decimals : 0;
    const pct = max > 0 ? Math.min(100, (used / max) * 100) : 0;
    const isBn = bottleneckKey === rowKey;
    const barClass = pct >= 92 ? 'danger' : pct >= 78 ? 'warn' : '';
    const bn = isBn ? '<span class="avail-bottleneck-badge">limiting</span>' : '';
    const afterVal = opts.after;
    const afterNote =
      afterVal != null && Number.isFinite(+afterVal) && Math.abs(+afterVal - +used) > 0.05
        ? ` → ${fmtHours(afterVal, dec || 1)}${unit} planned`
        : '';
    return `<div class="avail-row${isBn ? ' bottleneck' : ''}">
      <span class="avail-label">${label}${bn}</span>
      <div class="avail-bar ${barClass}"><span style="width:${pct}%"></span></div>
      <span class="avail-meta">${fmtHours(used, dec)}/${fmtHours(max, dec)}${unit}${afterNote}</span>
    </div>`;
  }

  function availabilityPanelHtml(ctx, opts) {
    opts = opts || {};
    if (!ctx || !ctx.origin) return '';
    const title = opts.title || 'What you can fly';
    let rows = '';
    if (ctx.hasGate && ctx.gate) {
      rows += availabilityBarRow(
        'Gate',
        ctx.gate.used,
        ctx.gate.max,
        '/wk',
        ctx.bottleneck,
        'gate',
        { after: ctx.freq ? ctx.gate.after : null }
      );
    } else if (ctx.origin) {
      rows += `<p class="muted" style="font-size:0.72rem;margin:0 0 6px;">No gate at <b>${ctx.origin}</b> — lease one to originate flights.</p>`;
    }
    if (ctx.aircraft) {
      rows += availabilityBarRow(
        'Aircraft',
        ctx.aircraft.used,
        ctx.aircraft.cap,
        ' hr/wk',
        ctx.bottleneck,
        'aircraft',
        { after: ctx.freq ? ctx.aircraft.after : null, decimals: 1 }
      );
    } else if (ctx.dest && !state.fleet.length) {
      rows += `<p class="muted" style="font-size:0.72rem;margin:6px 0;">No aircraft in fleet — open <b>Fleet</b> to lease a plane.</p>`;
    }
    if (ctx.airportOps && ctx.dest) {
      rows += availabilityBarRow(
        'Airport ops',
        ctx.freq || 0,
        ctx.airportOps.max,
        '/wk max',
        ctx.bottleneck,
        'airport',
        { after: ctx.freq || null }
      );
    }

    let fleetRows = '';
    if (ctx.fleet.length && ctx.dest) {
      fleetRows = `<p class="muted" style="font-size:0.66rem;margin:8px 0 4px;">Aircraft headroom on <b>${ctx.origin}–${ctx.dest}</b>:</p><ul class="avail-option-list">`;
      ctx.fleet.forEach((p) => {
        const sel = ctx.plane && ctx.plane.id === p.id ? ' <span class="muted">(selected)</span>' : '';
        const freqNote =
          p.maxFreq > 0 ? `<b>+${p.maxFreq}/wk</b> on this route` : '<span class="danger">no hours left</span>';
        fleetRows += `<li><b>${p.name}</b>${sel} · ${fmtHours(p.used)}/${fmtHours(p.cap)} hr scheduled · ${freqNote}</li>`;
      });
      fleetRows += '</ul>';
    } else if (ctx.fleet.length) {
      fleetRows = '<ul class="avail-option-list">';
      ctx.fleet.forEach((p) => {
        fleetRows += `<li><b>${p.name}</b> · ${fmtHours(p.used)}/${fmtHours(p.cap)} hr/wk · ${p.routesOn} route${p.routesOn === 1 ? '' : 's'}</li>`;
      });
      fleetRows += '</ul>';
    }

    const optItems = (ctx.options || [])
      .filter((o) => o.type !== 'ok' || opts.showOk)
      .map((o) => `<li>${o.text}</li>`)
      .join('');
    const chips = [];
    (ctx.options || []).forEach((o) => {
      if (o.type === 'lower_freq' && o.freq) {
        chips.push(`<button type="button" class="avail-chip" data-avail-freq="${o.freq}">Set ${o.freq}/wk</button>`);
      }
      if (o.type === 'fleet' && o.tab) {
        chips.push(`<button type="button" class="avail-chip secondary" data-ops-tab="${o.tab}">Open Fleet</button>`);
      }
      if (o.type === 'bump' && o.routeId) {
        chips.push(
          `<button type="button" class="avail-chip secondary" data-bump-freq="${o.routeId}" data-bump-delta="${o.delta}">+${o.delta}/wk existing route</button>`
        );
      }
    });
    if (ctx.hasGate && ctx.origin && !ctx.exists) {
      chips.push(
        `<button type="button" class="avail-chip secondary" data-hub-routes="${ctx.origin}">Browse routes from ${ctx.origin}</button>`
      );
    }

    const bottleneckLabel =
      ctx.bottleneck === 'gate'
        ? 'gate slots'
        : ctx.bottleneck === 'aircraft'
          ? 'aircraft hours'
          : ctx.bottleneck === 'airport_presence'
            ? 'airport market share'
            : ctx.bottleneck === 'route_competition'
              ? 'route competition'
              : 'airport hours';

    const maxLine =
      ctx.dest && ctx.launchMax != null
        ? `<p class="avail-max-freq">Max frequency now: <b class="${ctx.valid ? '' : 'danger'}">${ctx.launchMax}/wk</b>${
            ctx.bottleneck
              ? ` <span class="muted">(${bottleneckLabel} is the limit)</span>`
              : ''
          }</p>`
        : '';

    const marketBlock = ctx.market
      ? marketScopePanelHtml(ctx.market, {
          bottleneck: ctx.bottleneck,
          plannedWeekly: ctx.market.playerOriginDeps,
          plannedFreq: ctx.freq ? ctx.market.effectivePlayerFreq : null,
          addWeekly: 0,
          singlePlaneSingleRoute: ctx.singlePlaneSingleRoute,
          schedScale: ctx.market.schedScale,
        })
      : '';

    return `<div class="avail-panel">
      <h4>${title}</h4>
      ${marketBlock}
      ${rows}
      ${maxLine}
      ${fleetRows}
      ${
        optItems
          ? `<div class="avail-options"><strong>Options</strong><ul class="avail-option-list">${optItems}</ul>${chips.length ? `<div class="avail-chips">${chips.join('')}</div>` : ''}</div>`
          : chips.length
            ? `<div class="avail-chips">${chips.join('')}</div>`
            : ''
      }
    </div>`;
  }

  function fleetAvailabilityNetworkHtml() {
    if (!state.fleet.length) return '';
    let rows = '';
    state.fleet.forEach((f) => {
      const ac = aircraftType(f.type);
      const cap = planeWeeklyBlockHoursCapacity(f);
      const used = planeWeeklyBlockHoursUsed(f.id);
      const pct = cap > 0 ? Math.min(100, (used / cap) * 100) : 0;
      const routesOn = state.routes.filter((r) => r.aircraft_id === f.id).length;
      const barClass = pct >= 92 ? 'util-warn' : pct < 40 ? 'util-bad' : 'util-good';
      rows += `<div class="gate-hub-row">
        <strong style="font-size:0.72rem;min-width:72px;">${ac ? ac.name.split(' ').slice(-1)[0] : f.id}</strong>
        <div class="util-bar ${barClass}" style="flex:1;"><span style="width:${pct}%"></span></div>
        <span class="muted" style="font-size:0.66rem;">${fmtHours(used)}/${fmtHours(cap)} hr · ${routesOn} rt</span>
      </div>`;
    });
    return `<p style="font-size:0.78rem;margin:12px 0 6px;color:var(--gold);font-weight:600;">Aircraft schedule</p>${rows}
      <p class="muted" style="font-size:0.64rem;margin:6px 0 0;">One plane, one place — block hours cap total flying per week across all routes.</p>`;
  }

  function enrichRouteSuggestion(origin, s) {
    const hasGate = hasGateAt(origin);
    const exists = state.routes.some((r) => r.origin === origin && r.dest === s.dest);
    const fleetMatches = (state.fleet || []).filter((f) => f.type === s.acType);
    let status = 'ready';
    let reason = '';
    let bestPlane = null;
    let maxFreq = 0;

    if (exists) {
      status = 'exists';
      reason = 'Already flying this pair';
    } else if (!hasGate) {
      status = 'no_gate';
      reason = `Lease a gate at ${origin}`;
    } else if (!fleetMatches.length) {
      status = 'no_fleet_type';
      reason = `${s.acName} not in fleet`;
    } else {
      fleetMatches.forEach((f) => {
        const mf = maxFrequencyForAircraft(f.id, origin, s.dest, s.acType);
        if (mf >= maxFreq) {
          maxFreq = mf;
          bestPlane = f;
        }
      });
      const want = s.freq || 7;
      const cap = launchFrequencyCap({
        origin,
        dest: s.dest,
        aircraftId: bestPlane ? bestPlane.id : fleetMatches[0].id,
        freq: want,
      });
      maxFreq = Math.min(maxFreq, cap);
      if (maxFreq < want) {
        status = maxFreq > 0 ? 'limited' : 'no_hours';
        reason =
          maxFreq > 0
            ? `Max ${maxFreq}/wk now (gate or aircraft)`
            : 'No gate or aircraft hours left';
      }
    }

    return {
      ...s,
      status,
      reason,
      bestPlaneId: bestPlane ? bestPlane.id : fleetMatches[0]?.id,
      maxFreq: maxFreq || 0,
      canLaunch: status === 'ready' || (status === 'limited' && maxFreq > 0),
    };
  }

  function bindAvailabilityActions(root) {
    const scope = root || document;
    scope.querySelectorAll('[data-avail-freq]').forEach((btn) => {
      if (btn._availBound) return;
      btn._availBound = true;
      btn.addEventListener('click', () => {
        const n = +btn.dataset.availFreq;
        const freqEl = $('rt-freq') || $('rl-freq');
        if (freqEl) {
          freqEl.value = n;
          freqEl.dispatchEvent(new Event('input', { bubbles: true }));
        }
      });
    });
    bindGateCapacityActions(scope);
  }

  function updateRouteAvailabilityPanel() {
    const panel = $('route-availability-panel');
    if (!panel) return;
    const oCode = $('rt-origin-code') && $('rt-origin-code').value;
    const dCode = $('rt-dest-code') && $('rt-dest-code').value;
    const plane = state.fleet.find((f) => f.id === ($('rt-aircraft') && $('rt-aircraft').value));
    const freq = +($('rt-freq') && $('rt-freq').value) || 7;
    const ctx = routeAvailabilityContext(oCode, dCode || null, plane ? plane.id : null, freq);
    panel.innerHTML = availabilityPanelHtml(ctx, { title: 'Capacity & options' });
    bindAvailabilityActions(panel);
    const freqEl = $('rt-freq');
    if (freqEl && ctx.launchMax > 0) {
      freqEl.max = String(ctx.launchMax);
    }
  }

  function updateLaunchAvailabilityPanel(draft) {
    const panel = $('rl-availability');
    if (!panel || !draft) return;
    const ctx = routeAvailabilityContext(draft.origin, draft.dest, draft.aircraftId, draft.freq);
    panel.innerHTML = availabilityPanelHtml(ctx, { title: 'Capacity check' });
    bindAvailabilityActions(panel);
    const freqEl = $('rl-freq');
    if (freqEl && ctx.launchMax > 0) freqEl.max = String(ctx.launchMax);
  }

  function effectiveAncillaryMode(route) {
    const mode = (route && route.ancillary_mode) || 'auto';
    if (mode !== 'auto') return mode;
    return (state && state.ancillary_strategy) || 'auto';
  }

  function haversineNm(lat1, lon1, lat2, lon2) {
    const R = 3440.065;
    const toR = (d) => (d * Math.PI) / 180;
    const dLat = toR(lat2 - lat1);
    const dLon = toR(lon2 - lon1);
    const a =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(toR(lat1)) * Math.cos(toR(lat2)) * Math.sin(dLon / 2) ** 2;
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }

  function fmtMoney(n) {
    const abs = Math.abs(n);
    if (abs >= 1e9) return `${n < 0 ? '-' : ''}$${(abs / 1e9).toFixed(2)}B`;
    if (abs >= 1e6) return `${n < 0 ? '-' : ''}$${(abs / 1e6).toFixed(2)}M`;
    if (abs >= 1e3) return `${n < 0 ? '-' : ''}$${(abs / 1e3).toFixed(0)}K`;
    return `${n < 0 ? '-' : ''}$${abs.toFixed(0)}`;
  }

  function fmtDate(day, hour) {
    const start = new Date(2026, 0, 1, hour ?? 0, 0, 0);
    start.setDate(start.getDate() + day);
    const opts = { year: 'numeric', month: 'short', day: 'numeric' };
    if (hour != null) {
      opts.hour = 'numeric';
      opts.minute = '2-digit';
    }
    return start.toLocaleString('en-US', opts);
  }

  function uid(prefix) {
    return `${prefix}-${Math.random().toString(36).slice(2, 9)}`;
  }

  function airport(iata) {
    return bootstrap.airports.find((a) => a.iata === iata);
  }

  function aircraftType(id) {
    return (bootstrap.aircraft_types || {})[id] || null;
  }

  function aircraftSeats(acType, configured) {
    const ac = aircraftType(acType);
    if (!ac) return configured || 0;
    const s = configured != null ? configured : ac.seats;
    return Math.min(ac.seats_max || ac.seats, Math.max(ac.seats_min || ac.seats, s));
  }

  function fleetSeatCount(plane) {
    return aircraftSeats(plane.type, plane.seats);
  }

  /**
   * Cabin density: more seats = more capacity + slightly higher lease/buy,
   * but less legroom (comfort / satisfaction). Fewer seats = premium cabin feel.
   */
  function seatDensityInfo(acType, seats) {
    const ac = aircraftType(acType);
    if (!ac) return { seats: seats || 0, t: 0.5, costMult: 1, comfortAdj: 0, comfort: 3 };
    const min = ac.seats_min != null ? ac.seats_min : ac.seats;
    const max = ac.seats_max != null ? ac.seats_max : ac.seats;
    const s = aircraftSeats(acType, seats);
    const t = max > min ? (s - min) / (max - min) : 0.5; // 0 = roomiest, 1 = densest
    // Denser cabins cost a bit more to equip/maintain; roomier = slightly cheaper metal bill
    const costMult = 0.9 + t * 0.2; // 0.90 … 1.10
    // Comfort: roomier (+legroom / fewer pax per exit) vs dense
    const baseComfort = ac.comfort_rating != null ? ac.comfort_rating : 3;
    const comfortAdj = (0.5 - t) * 1.4; // about ±0.7 stars
    const comfort = Math.max(1, Math.min(5, baseComfort + comfortAdj));
    return { seats: s, min, max, t, costMult, comfortAdj, comfort, baseComfort };
  }

  function planeLeaseMonthly(typeOrPlane, seatsOpt) {
    const type = typeof typeOrPlane === 'string' ? typeOrPlane : typeOrPlane && typeOrPlane.type;
    const seats =
      seatsOpt != null
        ? seatsOpt
        : typeof typeOrPlane === 'object' && typeOrPlane
          ? typeOrPlane.seats
          : null;
    const ac = aircraftType(type);
    if (!ac) return 0;
    const dens = seatDensityInfo(type, seats != null ? seats : ac.seats);
    return Math.round((ac.lease_monthly || 0) * dens.costMult);
  }

  function planePurchasePrice(typeOrPlane, seatsOpt) {
    const type = typeof typeOrPlane === 'string' ? typeOrPlane : typeOrPlane && typeOrPlane.type;
    const seats =
      seatsOpt != null
        ? seatsOpt
        : typeof typeOrPlane === 'object' && typeOrPlane
          ? typeOrPlane.seats
          : null;
    const ac = aircraftType(type);
    if (!ac) return 0;
    const dens = seatDensityInfo(type, seats != null ? seats : ac.seats);
    return Math.round((ac.purchase || 0) * dens.costMult);
  }

  function planeMaintMonthly(typeOrPlane, seatsOpt) {
    const type = typeof typeOrPlane === 'string' ? typeOrPlane : typeOrPlane && typeOrPlane.type;
    const seats =
      seatsOpt != null
        ? seatsOpt
        : typeof typeOrPlane === 'object' && typeOrPlane
          ? typeOrPlane.seats
          : null;
    const ac = aircraftType(type);
    if (!ac) return 0;
    const dens = seatDensityInfo(type, seats != null ? seats : ac.seats);
    return Math.round((ac.maintenance_monthly || 0) * dens.costMult);
  }

  function planeComfortRating(plane) {
    if (!plane) return 3;
    return seatDensityInfo(plane.type, plane.seats).comfort;
  }

  function isSmallAircraft(acType) {
    const ac = aircraftType(acType);
    if (!ac) return false;
    const max = ac.seats_max || ac.seats;
    return max < 76;
  }


  /** Flight product specialties — flavor + economics without minute-level banks. */
  const ROUTE_PRODUCTS = {
    standard: {
      id: 'standard',
      label: 'Scheduled',
      blurb: 'Normal year-round service',
      demandMult: 1,
      yieldMult: 1,
      costMult: 1,
      repOnAog: 1,
    },
    essential: {
      id: 'essential',
      label: 'Essential / PSO',
      blurb: 'Thin community market — demand floor, fare cap, rep for serving',
      demandMult: 0.78,
      yieldMult: 0.88,
      costMult: 0.96,
      subsidyPerDep: 380,
      loadFloor: 0.28,
      fareMax: 199,
      repOnAog: 1.65,
      repMonthly: 0.12,
      hardToCancel: true,
    },
    leisure: {
      id: 'leisure',
      label: 'Leisure / sun',
      blurb: 'VFR leisure — strong peaks, soft shoulders',
      demandMult: 1.06,
      yieldMult: 0.94,
      costMult: 1,
      seasonal: 'leisure',
      repOnAog: 0.95,
    },
    business_bank: {
      id: 'business_bank',
      label: 'Business bank',
      blurb: 'Premium timing brand — higher yield; AOG hurts more',
      demandMult: 0.94,
      yieldMult: 1.2,
      costMult: 1.07,
      fareMin: 99,
      repOnAog: 2.05,
    },
    redeye: {
      id: 'redeye',
      label: 'Red-eye',
      blurb: 'Overnight cheap seats — lower cost & yield, softer CSAT',
      demandMult: 0.8,
      yieldMult: 0.74,
      costMult: 0.84,
      csatAdj: -7,
      repOnAog: 0.9,
    },
    feeder: {
      id: 'feeder',
      label: 'Codeshare / feeder',
      blurb: 'Contract feed to a major — steadier loads, lower yield, cancel risk',
      demandMult: 1.2,
      yieldMult: 0.8,
      costMult: 0.97,
      loadFloor: 0.42,
      fareCapVsMarket: 0.95,
      repOnAog: 2.35,
      hardToCancel: true,
      forceFlySoft: true,
    },
    cargo_lite: {
      id: 'cargo_lite',
      label: 'Cargo-in-bin',
      blurb: 'Belly cargo on empty seats — cushion when loads soft',
      demandMult: 0.97,
      yieldMult: 1,
      costMult: 1.05,
      cargoPerEmptySeat: 32,
      repOnAog: 1.05,
    },
    event: {
      id: 'event',
      label: 'Event / charter season',
      blurb: 'College, sports, events — burst weekends & pulse weeks',
      demandMult: 1.02,
      yieldMult: 1.14,
      costMult: 1.08,
      seasonal: 'event',
      repOnAog: 1.35,
    },
    tag: {
      id: 'tag',
      label: 'Tag flight A–B–C',
      blurb: 'Multi-stop on one plane — efficient hours, fragile if late/AOG',
      demandMult: 0.9,
      yieldMult: 0.92,
      costMult: 1.06,
      repOnAog: 1.55,
      isTag: true,
    },
  };

  function routeProduct(id) {
    return ROUTE_PRODUCTS[id] || ROUTE_PRODUCTS.standard;
  }

  function routeProductId(routeOrDraft) {
    if (!routeOrDraft) return 'standard';
    return routeOrDraft.product || routeOrDraft.productId || 'standard';
  }

  function productSeasonalMult(product, day) {
    if (!product || !product.seasonal) return 1;
    const d = day != null ? day : (state && state.day) || 0;
    const dow = ((d % 7) + 7) % 7;
    const month = Math.floor((((d % 365) + 365) % 365) / 30.42); // 0–11
    if (product.seasonal === 'leisure') {
      if (month >= 5 && month <= 7) return 1.42; // summer
      if (month === 11 || month === 0) return 1.28; // holidays
      if (month >= 1 && month <= 3) return 0.74; // soft winter/spring shoulder
      return 0.92;
    }
    if (product.seasonal === 'event') {
      const pulse = d % 42 < 5 ? 1.75 : 1; // multi-day event every ~6 weeks
      const weekend = dow === 5 || dow === 6 || dow === 0 ? 1.28 : 0.82;
      return pulse * weekend;
    }
    return 1;
  }

  function productOptionsHtml(selected) {
    const sel = selected || 'standard';
    return Object.values(ROUTE_PRODUCTS)
      .map((p) => {
        const s = p.id === sel ? ' selected' : '';
        return `<option value="${p.id}"${s}>${p.label}</option>`;
      })
      .join('');
  }

  function productChipHtml(route) {
    const p = routeProduct(routeProductId(route));
    if (p.id === 'standard') return '';
    const tag =
      p.isTag && route.tag_dest
        ? ` · via ${route.dest}→${route.tag_dest}`
        : '';
    return `<span class="product-chip product-${p.id}" title="${p.blurb}">${p.label}${tag}</span>`;
  }

  function comfortStars(rating) {
    const r = Math.max(0, Math.min(5, Math.round(rating || 3)));
    return '★'.repeat(r) + '☆'.repeat(5 - r);
  }

  function airportLabel(ap) {
    return `${ap.iata} — ${ap.city}`;
  }

  function sortedAirports() {
    return [...bootstrap.airports].sort((a, b) => a.iata.localeCompare(b.iata));
  }

  function resolveAirportQuery(q) {
    if (!q) return null;
    const raw = String(q).trim();
    if (!raw) return null;
    const t = raw.toLowerCase();
    const exact = bootstrap.airports.find((a) => a.iata.toLowerCase() === t);
    if (exact) return exact;
    const dashParts = raw.split(/\s*[—–-]\s*/);
    if (dashParts[0] && dashParts[0].length >= 3) {
      const head = dashParts[0].trim().slice(0, 3).toLowerCase();
      const byDash = bootstrap.airports.find((a) => a.iata.toLowerCase() === head);
      if (byDash) return byDash;
    }
    const m = t.match(/^([a-z0-9]{3})\b/);
    if (m) {
      const byCode = bootstrap.airports.find((a) => a.iata.toLowerCase() === m[1]);
      if (byCode) return byCode;
    }
    return (
      bootstrap.airports.find(
        (a) =>
          a.city.toLowerCase().includes(t) ||
          a.name.toLowerCase().includes(t) ||
          `${a.iata} ${a.city}`.toLowerCase().includes(t) ||
          `${a.iata} — ${a.city}`.toLowerCase().includes(t)
      ) || null
    );
  }

  function defaultRouteOrigin() {
    if (selectedAirport) return selectedAirport;
    if (state && state.gates.length) return state.gates[0].airport;
    return 'DAY';
  }

  function airportDatalistHtml() {
    return sortedAirports()
      .map((a) => `<option value="${airportLabel(a)}">${a.name}${a.state ? ` (${a.state})` : ''}</option>`)
      .join('');
  }

  function cloneScenario(id) {
    const raw = bootstrap.scenarios[id];
    if (!raw) throw new Error(`Unknown scenario: ${id}`);
    const s = JSON.parse(JSON.stringify(raw));
    s.fleet = (s.fleet || []).map((f) => ({ ...f }));
    s.gates = (s.gates || []).map((g) => ({ ...g }));
    s.routes = (s.routes || []).map((r) => ({ ...r }));
    s.debt = (s.debt || []).map((d) => ({ ...d }));
    s.bonds = (s.bonds || []).map((b) => ({ ...b }));
    s.brand_awareness = { ...(s.brand_awareness || {}) };
    return s;
  }

  function scenarioRegionAirportSet(scenarioId) {
    const sc = bootstrap.scenarios[scenarioId];
    if (!sc) return null;
    if (sc.region === 'ohio' && bootstrap.ohio_region_iata) {
      return new Set(bootstrap.ohio_region_iata);
    }
    if (sc.region === 'midwest' && bootstrap.midwest_region_iata) {
      return new Set(bootstrap.midwest_region_iata);
    }
    return null;
  }

  function isRegionalMapKey(key) {
    return key === 'ohio' || key === 'midwest';
  }

  function applyScenarioAirports(scenarioId) {
    if (!initialAirports) return;
    const full = JSON.parse(JSON.stringify(initialAirports));
    const allowed = scenarioRegionAirportSet(scenarioId);
    bootstrap.airports = allowed ? full.filter((a) => allowed.has(a.iata)) : full;
  }

  function incumbentPressure(ap) {
    if (!ap) return 0;
    if (ap.incumbents && ap.incumbents.length) {
      return Math.min(0.92, ap.incumbents.reduce((s, x) => s + (x.share || 0), 0) * 0.72);
    }
    return ap.hub_strength || 0;
  }

  function getActiveMapConfig() {
    if (!mapConfig) return null;
    return mapConfig[activeMapKey] || mapConfig.usa || null;
  }

  function syncMapDimensions() {
    const cfg = getActiveMapConfig();
    if (!cfg) return;
    MAP_W = cfg.width;
    MAP_H = cfg.height;
    MAP_ZOOM_MIN_W = MAP_W * 0.22;
    MAP_ZOOM_MAX_W = MAP_W * 2.2;
    mapView.w = MAP_W;
    mapView.h = MAP_H;
  }

  function getMapboxToken() {
    return (window.RUNWAY_MAPBOX_TOKEN || '').trim();
  }

  function useMapbox() {
    return !!getMapboxToken() && typeof mapboxgl !== 'undefined';
  }

  function applyScenarioMap(scenarioId) {
    const sc = bootstrap.scenarios[scenarioId];
    activeMapKey =
      sc && sc.region === 'ohio' ? 'ohio' : sc && sc.region === 'midwest' ? 'midwest' : 'usa';
    syncMapDimensions();
    if (useMapbox() && mapboxMap && mapboxReady) fitMapToManagedArea();
  }

  function airportLngLatBounds(padRatio = 0.12) {
    const airports = bootstrap.airports || [];
    if (!airports.length) return null;
    const lngs = airports.map((a) => a.lon);
    const lats = airports.map((a) => a.lat);
    const minLng = Math.min(...lngs);
    const maxLng = Math.max(...lngs);
    const minLat = Math.min(...lats);
    const maxLat = Math.max(...lats);
    const lngPad = Math.max(0.35, (maxLng - minLng) * padRatio);
    const latPad = Math.max(0.25, (maxLat - minLat) * padRatio);
    return [
      [minLng - lngPad, minLat - latPad],
      [maxLng + lngPad, maxLat + latPad],
    ];
  }

  function fitMapToManagedArea(padRatio = 0.16) {
    if (useMapbox() && mapboxMap && mapboxReady) {
      const bounds = airportLngLatBounds(padRatio);
      if (!bounds) return;
      mapboxMap.fitBounds(bounds, {
        padding: { top: 48, bottom: 32, left: 40, right: 40 },
        maxZoom: isRegionalMapKey(activeMapKey) ? 8.5 : 5.5,
        duration: 0,
      });
      return;
    }
    const airports = bootstrap.airports || [];
    if (!airports.length) {
      mapView = { x: 0, y: 0, w: MAP_W, h: MAP_H };
      applyMapView();
      return;
    }
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    airports.forEach((ap) => {
      const p = projectMap(ap.lat, ap.lon);
      minX = Math.min(minX, p.x);
      minY = Math.min(minY, p.y);
      maxX = Math.max(maxX, p.x);
      maxY = Math.max(maxY, p.y);
    });
    const spanX = Math.max(100, maxX - minX);
    const spanY = Math.max(100, maxY - minY);
    const padX = spanX * padRatio + 55;
    const padY = spanY * padRatio + 55;
    const aspect = MAP_H / MAP_W;
    let w = spanX + padX * 2;
    let h = spanY + padY * 2;
    if (w * aspect > h) h = w * aspect;
    else w = h / aspect;
    w = Math.min(MAP_W * 0.9, Math.max(MAP_W * 0.32, w));
    h = w * aspect;
    let x = (minX + maxX) / 2 - w / 2;
    let y = (minY + maxY) / 2 - h / 2;
    mapView = { x, y, w, h };
    clampMapView();
    applyMapView();
  }

  function ensureMapboxSize() {
    if (mapboxMap) {
      try {
        mapboxMap.resize();
      } catch (e) {
        /* ignore resize races during teardown */
      }
    }
  }

  function airportWealth(ap) {
    if (!ap) return 0.2;
    return ap.wealth_index != null ? ap.wealth_index : Math.min(1, Math.sqrt(ap.metro_pop_m || 0.5) * 0.2);
  }

  function airportLuxury(ap) {
    if (!ap) return 0.05;
    return ap.luxury_share != null ? ap.luxury_share : 0.06;
  }

  function fareElasticity(o, d) {
    const wealth = (airportWealth(o) + airportWealth(d)) / 2;
    const luxury = (airportLuxury(o) + airportLuxury(d)) / 2;
    return 0.95 + (1 - wealth) * 0.55 + luxury * 0.35;
  }

  function marketFareForPair(originIata, destIata, acTypeId) {
    const mock = { origin: originIata, dest: destIata };
    const dist = routeDistance(mock);
    const o = airport(originIata);
    const d = airport(destIata);
    if (!o || !d || !Number.isFinite(dist)) return 129;
    const ac = aircraftType(acTypeId);
    const wealth = (airportWealth(o) + airportWealth(d)) / 2;
    const luxury = (airportLuxury(o) + airportLuxury(d)) / 2;
    const regional = o.regional || d.regional;
    const distFare = 42 + dist * (regional ? 0.38 : 0.48);
    const wealthMult = 0.72 + wealth * 0.62;
    const luxuryPrem = 1 + luxury * 0.42;
    const comfortPrem = ac ? 0.88 + ((ac.comfort_rating || 3) / 5) * 0.28 : 1;
    const smallAcDisc = ac && (ac.seats_max || ac.seats) < 20 ? 0.82 : 1;
    const floor = regional ? 59 : 79;
    const ceiling = regional ? 349 : 599;
    return Math.min(ceiling, Math.max(floor, Math.round(distFare * wealthMult * luxuryPrem * comfortPrem * smallAcDisc)));
  }

  function representativeFareForDemand(route) {
    const buckets = routeFareBuckets(route);
    return buckets.reduce((sum, b) => sum + b.fare * b.share, 0);
  }

  function fareDemandFactor(route, o, d) {
    const acType = route.aircraft_type;
    const market = marketFareForPair(route.origin, route.dest, acType);
    const repFare = representativeFareForDemand(route);
    const ratio = repFare / Math.max(market, 45);
    const elasticity = fareElasticity(o, d);
    if (ratio <= 1) return Math.min(1.38, 1 + (1 - ratio) * 0.48 * elasticity);
    return Math.max(0.12, 1 - (ratio - 1) * 1.05 * elasticity);
  }

  function competitorFarePressure(ap) {
    if (!ap || !state || !state.competitor_markets) return 0;
    const cm = state.competitor_markets[ap.iata];
    if (!cm || !ap.incumbents) return 0;
    let pressure = 0;
    ap.incumbents.forEach((inc) => {
      const m = cm[inc.airline];
      if (!m) return;
      if (m.fare_index < 0.9) pressure += inc.share * (1 - m.fare_index) * 0.75;
      if (m.capacity_index > 1.1) pressure += inc.share * (m.capacity_index - 1) * 0.45;
    });
    return Math.min(0.38, pressure);
  }

  function initCompetitorMarkets() {
    const markets = {};
    bootstrap.airports.forEach((ap) => {
      if (!ap.incumbents || !ap.incumbents.length) return;
      markets[ap.iata] = {};
      ap.incumbents.forEach((inc) => {
        markets[ap.iata][inc.airline] = { fare_index: 1, capacity_index: 1 };
      });
    });
    state.competitor_markets = markets;
    state.last_competitor_event_day = state.last_competitor_event_day || 0;
  }

  function initCompetitorRoutes() {
    const sc = state && bootstrap.scenarios[state.scenario_id];
    let seeds = bootstrap.ohio_competitor_route_seeds || [];
    if (sc && sc.region === 'midwest') {
      seeds = bootstrap.midwest_competitor_route_seeds || seeds;
    }
    const allowed = new Set((bootstrap.airports || []).map((a) => a.iata));
    state.competitor_routes = seeds
      .filter((s) => allowed.has(s.origin) && allowed.has(s.dest))
      .map((s) => ({
        id: `cr-${s.airline}-${s.origin}-${s.dest}`,
        airline: s.airline,
        origin: s.origin,
        dest: s.dest,
        frequency_week: s.frequency_week,
        fare: s.fare,
        tier: s.tier || 'legacy',
        started_day: 0,
      }));
    state.last_competitor_ai_day = state.last_competitor_ai_day || 0;
  }

  function competitorRoutesAt(iata) {
    return (state.competitor_routes || []).filter((r) => r.origin === iata || r.dest === iata);
  }

  function competitorRouteOverlapPenalty(route) {
    let penalty = 0;
    (state.competitor_routes || []).forEach((cr) => {
      const match =
        (cr.origin === route.origin && cr.dest === route.dest) ||
        (cr.origin === route.dest && cr.dest === route.origin);
      if (!match) return;
      const fareAdv = cr.fare < (route.fare || 999) * 0.92 ? 1.12 : 1;
      penalty += 0.07 + (cr.frequency_week / 28) * 0.14 * fareAdv;
    });
    return Math.min(0.48, penalty);
  }

  /**
   * Single competitive-pressure score (0–100) for a route or airport.
   * Collapses hub incumbents + fare wars + pair overlap into one meter + one tip.
   */
  function routeCompetitivePressure(route) {
    if (!route) return null;
    const o = airport(route.origin);
    const d = airport(route.dest);
    const hubN = Math.min(1, (incumbentPressure(o) + incumbentPressure(d)) / 2);
    const fareN = Math.min(1, (competitorFarePressure(o) + competitorFarePressure(d)) / 2 / 0.38);
    const ovRaw = competitorRouteOverlapPenalty(route);
    const ovN = Math.min(1, ovRaw / 0.48);
    const score = Math.round(Math.min(100, (hubN * 0.32 + fareN * 0.28 + ovN * 0.4) * 100));
    let tip = 'Pressure is light — good place to grow frequency or brand.';
    let driver = 'open';
    if (ovN >= hubN && ovN >= fareN && ovN >= 0.25) {
      tip = 'Rivals fly this pair — match fare, add frequency, or push airport ads.';
      driver = 'pair';
    } else if (hubN >= fareN && hubN >= 0.35) {
      tip = 'Fortress hub pressure — denser frequency, marketing, or a thinner alternate city.';
      driver = 'hub';
    } else if (fareN >= 0.3) {
      tip = 'Cheaper rival fares nearby — cut price, go ancillary-heavy, or out-advertise them.';
      driver = 'fare';
    } else if (score >= 30) {
      tip = 'Moderate pressure — protect load with ads and steady frequency.';
      driver = 'mixed';
    }
    const tier = score >= 55 ? 'high' : score >= 30 ? 'mid' : 'low';
    return { score, tier, tip, driver, hubN, fareN, ovN };
  }

  function airportCompetitivePressure(iata) {
    const ap = airport(iata);
    if (!ap) return null;
    const hubN = Math.min(1, incumbentPressure(ap));
    const fareN = Math.min(1, competitorFarePressure(ap) / 0.38);
    const comps = competitorRoutesAt(iata);
    const ovN = Math.min(1, comps.length / 8);
    const score = Math.round(Math.min(100, (hubN * 0.45 + fareN * 0.3 + ovN * 0.25) * 100));
    let tip = 'Soft market — room to build brand and frequency.';
    if (hubN >= 0.5) tip = 'Strong incumbent share — lease gates and fight with frequency + marketing.';
    else if (fareN >= 0.35) tip = 'Fare fighting nearby — don’t race to the bottom without ads.';
    else if (comps.length >= 3) tip = `${comps.length} rival routes touch this airport — watch pair overlap.`;
    const tier = score >= 55 ? 'high' : score >= 30 ? 'mid' : 'low';
    return { score, tier, tip, comps: comps.length };
  }

  function competitivePressureHtml(pressure, opts) {
    opts = opts || {};
    if (!pressure) return '';
    const label =
      pressure.tier === 'high' ? 'High' : pressure.tier === 'mid' ? 'Medium' : 'Low';
    const compact = !!opts.compact;
    if (compact) {
      return `<span class="pressure-chip pressure-${pressure.tier}" title="${pressure.tip}">Pressure ${pressure.score} · ${label}</span>`;
    }
    return `<div class="pressure-meter pressure-${pressure.tier}" title="${pressure.tip}">
      <div class="pressure-meter-head">
        <span>Competitive pressure</span>
        <strong>${pressure.score}<span class="muted">/100 · ${label}</span></strong>
      </div>
      <div class="pressure-bar"><span style="width:${pressure.score}%"></span></div>
      <p class="pressure-tip muted">${pressure.tip}</p>
    </div>`;
  }

  function hasCompetitorRoute(airline, origin, dest) {
    return (state.competitor_routes || []).some(
      (r) =>
        r.airline === airline &&
        ((r.origin === origin && r.dest === dest) || (r.origin === dest && r.dest === origin))
    );
  }

  function playerRouteOnPair(origin, dest) {
    return (state.routes || []).find(
      (r) =>
        (r.origin === origin && r.dest === dest) || (r.origin === dest && r.dest === origin)
    );
  }

  function competitorThreatScore(cr, trigger, origin, dest) {
    let score = 0;
    const onPair =
      origin &&
      dest &&
      ((cr.origin === origin && cr.dest === dest) || (cr.origin === dest && cr.dest === origin));
    const playerRoute = playerRouteOnPair(cr.origin, cr.dest);
    if (trigger === 'player_route' && onPair) score += 55;
    else if (playerRoute) score += 38;
    else if (trigger !== 'weekly') return 0;

    if (playerRoute) {
      if (playerRoute.fare <= cr.fare * 0.96) score += 22;
      const sim = simulateRouteDay(playerRoute);
      if (!sim.grounded && sim.load > 0.5) score += 18;
      if (!sim.grounded && sim.load > 0.68) score += 12;
    }
    if (playerShareAtAirport(cr.origin) > 0.1) score += 14;
    if (playerShareAtAirport(cr.dest) > 0.08) score += 8;
    if (trigger === 'weekly' && (investedAirports().includes(cr.origin) || investedAirports().includes(cr.dest))) {
      score += 10;
    }
    return score;
  }

  function executeCompetitorReaction(cr, score, trigger) {
    const invested = new Set(investedAirports());
    const playerRoute = playerRouteOnPair(cr.origin, cr.dest);
    const roll = Math.random();
    const big = invested.has(cr.origin) || invested.has(cr.dest);

    if (playerRoute && cr.fare >= playerRoute.fare * 0.94 && roll < 0.58) {
      const target = Math.max(49, Math.round(playerRoute.fare * (0.9 + Math.random() * 0.08)));
      const oldFare = cr.fare;
      if (target < oldFare - 6) {
        cr.fare = target;
        const pct = 1 - target / oldFare;
        bumpCompetitorMarket(cr.origin, cr.airline, { fare_index: 1 - pct });
        return enrichCompetitorLog(
          {
            msg: `${cr.airline} matched your pricing on ${cr.origin}–${cr.dest} ($${oldFare}→$${cr.fare})`,
            big,
            airport: cr.origin,
            airline: cr.airline,
            type: 'fare_cut',
            pct,
          },
          cr
        );
      }
    }

    if (cr.frequency_week < 28 && roll < 0.72) {
      const delta = cr.tier === 'lcc' ? 2 + Math.floor(Math.random() * 3) : 3 + Math.floor(Math.random() * 5);
      const old = cr.frequency_week;
      cr.frequency_week = Math.min(28, cr.frequency_week + delta);
      if (cr.frequency_week - old >= 2) {
        bumpCompetitorMarket(cr.origin, cr.airline, { capacity_index: 1 + (cr.frequency_week - old) / 28 });
        return enrichCompetitorLog(
          {
            msg: `${cr.airline} added capacity on ${cr.origin}–${cr.dest} (${old}→${cr.frequency_week}x/wk)`,
            big,
            airport: cr.origin,
            airline: cr.airline,
            type: 'capacity',
          },
          cr
        );
      }
    }

    if (score > 62 && cr.frequency_week <= 5 && roll > 0.78 && state.competitor_routes.length > 5) {
      const idx = state.competitor_routes.indexOf(cr);
      if (idx >= 0) {
        state.competitor_routes.splice(idx, 1);
        return enrichCompetitorLog(
          {
            msg: `${cr.airline} pulled out of thin ${cr.origin}–${cr.dest} market`,
            big,
            airport: cr.origin,
            airline: cr.airline,
            type: 'exit',
          },
          cr
        );
      }
    }

    return null;
  }

  function queueReactiveCompetitorDecision(log) {
    if (!log || !log.big) return;
    if (state.day - (state.last_competitor_event_day || 0) < 30) return;
    state.last_competitor_event_day = state.day;
    const impact = competitorImpactHtml(log);
    if (log.type === 'fare_cut') {
      queueDecision({
        airport: log.airport,
        kicker: `${fmtDate(state.day)} · Competitor pricing`,
        title: `${log.airline} responds to your route`,
        body: `${log.msg}. They are defending share on a market you entered.${impact}`,
        teach: 'You never have to match. Marketing builds demand without cutting price; doing nothing is valid if loads still look fine.',
        logLine: log.msg,
        options: fareWarResponseOptions(log.airport, log.airline, log.pct || 0.1),
      });
    } else if (log.type === 'capacity') {
      queueDecision({
        airport: log.airport,
        kicker: `${fmtDate(state.day)} · Competitor capacity`,
        title: `${log.airline} adds seats against you`,
        body: `${log.msg}. Extra seats usually mean fare pressure unless you differentiate.${impact}`,
        teach: 'Match with price, fight back with marketing, or hold premium — or wait and watch loads.',
        logLine: log.msg,
        options: [
          { id: 'cut', label: `A — Trim fares ~8% on ${log.airport} routes`, hint: 'Defend load factor.', effect: 'cut_fares', airport: log.airport, pct: 0.08 },
          marketingDecisionOption(
            'market',
            'B — Hold fares ·',
            log.airport,
            'response',
            {
              competitorResponse: true,
              awarenessBoost: true,
              softenCompetitor: true,
              airline: log.airline,
            }
          ),
          { id: 'premium', label: 'C — Hold premium · reputation push', hint: 'Accept softer loads short-term.', effect: 'hold_premium', airport: log.airport },
          { id: 'ignore', label: 'D — Do nothing for now', hint: 'Monitor loads in Routes.', effect: 'none' },
        ],
      });
    } else if (log.type === 'exit') {
      queueDecision({
        airport: log.airport,
        kicker: `${fmtDate(state.day)} · Market opening`,
        title: `${log.airline} left a market you serve`,
        body: `${log.msg}. Less competition should lift loads on overlapping routes.${impact}`,
        teach: 'Positive events are openings — invest in marketing to capture freed demand, or simply enjoy stronger margins.',
        logLine: log.msg,
        options: [
          marketingDecisionOption('market', 'A — Capitalize:', log.airport, 'capitalize', {
            competitorResponse: true,
            awarenessBoost: true,
          }),
          { id: 'premium', label: 'B — Hold fares · take the demand bump', hint: 'Reputation +2; let loads rise naturally.', effect: 'hold_premium', airport: log.airport },
          { id: 'ignore', label: 'C — Do nothing', hint: 'The opening applies either way.', effect: 'none' },
        ],
      });
    }
  }

  /** Rivals hit harder after PE / IPO / scale — markets notice capital. */
  function competitorAggressionMult() {
    if (!state) return 1;
    let m = 1.08; // slightly hotter baseline so empty markets don't stay quiet forever
    // Grace period: learn the loop before full rival heat
    if ((state.day || 0) < 50) m *= 0.7;
    else if ((state.day || 0) < 100) m *= 0.88;
    if (state.pe_done) m *= 1.42;
    if (state.public || state.ipo_done) m *= 1.55;
    if ((state.ltm_revenue || 0) >= 25_000_000) m *= 1.1;
    if ((state.ltm_revenue || 0) >= 60_000_000) m *= 1.12;
    if ((state.routes || []).length >= 4) m *= 1.08;
    if ((state.routes || []).length >= 8) m *= 1.1;
    // Cash pile after a raise invites match capacity
    if ((state.cash || 0) >= 15_000_000) m *= 1.1;
    return m;
  }

  function reactiveCompetitorCooldownDays() {
    const base = REACTIVE_COMPETITOR_COOLDOWN_DAYS;
    const mult = competitorAggressionMult();
    return Math.max(6, Math.round(base / mult));
  }

  function processReactiveCompetitorThreats(trigger, origin, dest) {
    if (!state || !state.competitor_routes || !state.competitor_routes.length) return;
    state.last_reactive_competitor_day = state.last_reactive_competitor_day || 0;
    const skipCooldown = trigger === 'player_route';
    if (!skipCooldown && state.day - state.last_reactive_competitor_day < reactiveCompetitorCooldownDays()) return;

    let candidates = state.competitor_routes;
    if (trigger === 'player_route' && origin && dest) {
      candidates = candidates.filter(
        (cr) =>
          (cr.origin === origin && cr.dest === dest) ||
          (cr.origin === dest && cr.dest === origin) ||
          cr.origin === origin ||
          cr.dest === origin ||
          cr.origin === dest ||
          cr.dest === dest
      );
    } else if (trigger === 'weekly') {
      const invested = new Set(investedAirports());
      candidates = candidates.filter((cr) => invested.has(cr.origin) || invested.has(cr.dest));
    }

    const agg = competitorAggressionMult();
    const scoreFloor = trigger === 'player_route' ? 30 / agg : 42 / agg;
    const scored = candidates
      .map((cr) => ({
        cr,
        score: competitorThreatScore(cr, trigger, origin, dest) * (0.85 + 0.15 * agg),
      }))
      .filter((x) => x.score >= scoreFloor)
      .sort((a, b) => b.score - a.score);

    if (!scored.length) return;

    const maxActions = trigger === 'player_route' ? 2 : agg >= 1.3 ? 2 : 1;
    const logs = [];
    for (let i = 0; i < Math.min(maxActions, scored.length); i++) {
      const log = executeCompetitorReaction(scored[i].cr, scored[i].score, trigger);
      if (log) logs.push(log);
    }
    if (!logs.length) return;

    logs.forEach((l) => pushEvent(formatCompetitorEventMsg(l), competitorEventTier(l.type)));
    if (trigger === 'player_route' && logs.length) {
      const tier = competitorEventTier(logs[0].type);
      showEventToast(formatCompetitorEventMsg(logs[0]), tier === 'good' ? 'good' : 'bad');
    }
    queueReactiveCompetitorDecision(
      logs.find((l) => l.big && (l.type === 'fare_cut' || l.type === 'capacity' || l.type === 'exit'))
    );
    state.last_reactive_competitor_day = state.day;
  }

  function competitorAirportPool(preferInvested) {
    const all = bootstrap.airports || [];
    if (!all.length) return [];
    const region = scenarioRegionAirportSet(state && state.scenario_id);
    let pool = region ? all.filter((a) => region.has(a.iata)) : all.slice();
    if (!pool.length) pool = all.slice();
    if (preferInvested) {
      const invested = new Set(investedAirports());
      const focused = pool.filter((a) => invested.has(a.iata));
      if (focused.length) {
        // Weight player markets: 70% chance pick from invested when available.
        if (Math.random() < 0.7) return focused;
      }
    }
    return pool;
  }

  function pickCompetitorAirport(preferInvested) {
    const pool = competitorAirportPool(preferInvested);
    if (!pool.length) return null;
    return pool[Math.floor(Math.random() * pool.length)];
  }

  function pickCompetitorDest(originIata) {
    const pool = competitorAirportPool(true).filter((x) => x.iata !== originIata);
    if (!pool.length) {
      const fallback = (bootstrap.airports || []).filter((x) => x.iata !== originIata);
      return fallback[Math.floor(Math.random() * fallback.length)] || null;
    }
    const o = airport(originIata);
    // Prefer shorter regional pairs (under ~1200 nm) when lat/lon available.
    const scored = pool.map((d) => {
      let dist = 500;
      if (o && d.lat != null && o.lat != null) {
        dist = haversineNm(o.lat, o.lon, d.lat, d.lon);
      }
      const invested = new Set(investedAirports());
      const touch = invested.has(d.iata) ? 0.35 : 1;
      const rangePenalty = dist > 1200 ? 3 : dist > 800 ? 1.6 : 1;
      return { d, w: touch * rangePenalty * (0.6 + Math.random()) };
    });
    scored.sort((a, b) => a.w - b.w);
    return scored[0] ? scored[0].d : pool[0];
  }

  /** Soft fleet/gate budget for rivals — same physics, abstracted (no full sim fleet). */
  function competitorAirlineBlockHoursCap(airline) {
    const prof = airlineProfile(airline);
    const scale = prof && prof.national_scale != null ? prof.national_scale : 0.4;
    return 48 + scale * 220;
  }

  function competitorAirlineBlockHoursUsed(airline, excludeId) {
    return (state.competitor_routes || []).reduce((sum, r) => {
      if (r.airline !== airline || r.id === excludeId) return sum;
      const o = airport(r.origin);
      const d = airport(r.dest);
      if (!o || !d) return sum + (r.frequency_week || 0) * 2.2;
      const bh = blockHours(haversineNm(o.lat, o.lon, d.lat, d.lon), { cruise_kts: 420 });
      return sum + bh * (r.frequency_week || 0) * 1.7;
    }, 0);
  }

  function competitorOriginDepCap(iata) {
    const ap = airport(iata);
    const weekly = airportMarketDeparturesWeekly(ap) || 80;
    return Math.max(40, Math.round(weekly * 0.9));
  }

  function competitorOriginDepsUsed(iata, excludeId) {
    return (state.competitor_routes || []).reduce((sum, r) => {
      if (r.origin !== iata || r.id === excludeId) return sum;
      return sum + (r.frequency_week || 0);
    }, 0);
  }

  function canCompetitorAddRoute(airline, origin, dest, freq) {
    const usedH = competitorAirlineBlockHoursUsed(airline);
    const capH = competitorAirlineBlockHoursCap(airline);
    const o = airport(origin);
    const d = airport(dest);
    const bh = o && d ? blockHours(haversineNm(o.lat, o.lon, d.lat, d.lon), { cruise_kts: 420 }) : 2;
    const addH = bh * freq * 1.7;
    if (usedH + addH > capH * 1.05) return { ok: false, reason: 'fleet' };
    if (competitorOriginDepsUsed(origin) + freq > competitorOriginDepCap(origin)) {
      return { ok: false, reason: 'gate' };
    }
    return { ok: true };
  }

  function clampCompetitorCapacityBump(cr, delta) {
    if (!cr || !(delta > 0)) return 0;
    let add = delta;
    const usedH = competitorAirlineBlockHoursUsed(cr.airline, cr.id);
    const capH = competitorAirlineBlockHoursCap(cr.airline);
    const o = airport(cr.origin);
    const d = airport(cr.dest);
    const bh = o && d ? blockHours(haversineNm(o.lat, o.lon, d.lat, d.lon), { cruise_kts: 420 }) : 2;
    const curH = bh * (cr.frequency_week || 0) * 1.7;
    const headroomH = Math.max(0, capH - (usedH - curH));
    const maxByFleet = Math.floor(headroomH / Math.max(0.01, bh * 1.7)) - (cr.frequency_week || 0);
    const oUsed = competitorOriginDepsUsed(cr.origin, cr.id);
    const maxByGate = competitorOriginDepCap(cr.origin) - oUsed - (cr.frequency_week || 0);
    add = Math.min(add, Math.max(0, maxByFleet), Math.max(0, maxByGate));
    return add;
  }

  function processCompetitorAogWeek() {
    if (!state || !(state.competitor_routes || []).length) return;
    if (Math.random() > 0.12) return;
    const cr = state.competitor_routes[Math.floor(Math.random() * state.competitor_routes.length)];
    if (!cr || cr.frequency_week <= 3) return;
    const cut = 2 + Math.floor(Math.random() * 4);
    const old = cr.frequency_week;
    cr.frequency_week = Math.max(2, cr.frequency_week - cut);
    cr.aog_until_day = (state.day || 0) + 3 + Math.floor(Math.random() * 5);
    const invested = new Set(investedAirports());
    if (invested.has(cr.origin) || invested.has(cr.dest)) {
      pushEvent(
        `${cr.airline} grounded metal on ${cr.origin}–${cr.dest} (${old}→${cr.frequency_week}/wk) — their cancellations free a little demand.`,
        'good'
      );
    }
  }

  function restoreCompetitorAog() {
    if (!state || !state.competitor_routes) return;
    state.competitor_routes.forEach((cr) => {
      if (cr.aog_until_day != null && state.day >= cr.aog_until_day) {
        cr.frequency_week = Math.min(28, (cr.frequency_week || 7) + 2);
        delete cr.aog_until_day;
      }
    });
  }

  function processCompetitorAI() {
    if (!state || !state.competitor_routes) return;
    restoreCompetitorAog();
    processReactiveCompetitorThreats('periodic');
    if (state.day > 0 && state.day % 7 === 0) processCompetitorAogWeek();
    const airports = competitorAirportPool(true);
    if (!airports.length) return;
    const invested = new Set(investedAirports());
    const actions = 1 + Math.floor(Math.random() * 2);
    const logs = [];

    for (let i = 0; i < actions; i++) {
      const roll = Math.random();
      if (roll < 0.38) {
        const ap = pickCompetitorAirport(true);
        if (!ap || !ap.incumbents || !ap.incumbents.length) continue;
        const inc = ap.incumbents[Math.floor(Math.random() * ap.incumbents.length)];
        const dest = pickCompetitorDest(ap.iata);
        if (!dest || hasCompetitorRoute(inc.airline, ap.iata, dest.iata)) continue;
        let freq = inc.tier === 'lcc' ? 3 + Math.floor(Math.random() * 4) : 7 + Math.floor(Math.random() * 14);
        if (!canCompetitorAddRoute(inc.airline, ap.iata, dest.iata, freq).ok) {
          freq = Math.max(3, Math.floor(freq / 2));
          if (!canCompetitorAddRoute(inc.airline, ap.iata, dest.iata, freq).ok) continue;
        }
        const fare = Math.round(marketFareForPair(ap.iata, dest.iata, 'e175') * (inc.tier === 'lcc' ? 0.78 : 1.05));
        state.competitor_routes.push({
          id: uid('cr'),
          airline: inc.airline,
          origin: ap.iata,
          dest: dest.iata,
          frequency_week: freq,
          fare,
          tier: inc.tier,
          started_day: state.day,
        });
        logs.push(
          enrichCompetitorLog(
            {
              msg: `${inc.airline} launched ${ap.iata}–${dest.iata} (${freq}x/wk from $${fare})`,
              big: invested.has(ap.iata) || invested.has(dest.iata),
              airport: ap.iata,
              airline: inc.airline,
              type: 'new_route',
              freq,
              fare,
            },
            { origin: ap.iata, dest: dest.iata }
          )
        );
      } else if (roll < 0.68) {
        const cr = state.competitor_routes[Math.floor(Math.random() * state.competitor_routes.length)];
        if (!cr) continue;
        let delta = cr.tier === 'lcc' ? 2 + Math.floor(Math.random() * 3) : 4 + Math.floor(Math.random() * 7);
        delta = clampCompetitorCapacityBump(cr, delta);
        if (delta < 1) continue;
        const old = cr.frequency_week;
        cr.frequency_week = Math.min(28, cr.frequency_week + delta);
        if (cr.frequency_week - old >= 2) {
          bumpCompetitorMarket(cr.origin, cr.airline, { capacity_index: 1 + (cr.frequency_week - old) / 28 });
          logs.push(
            enrichCompetitorLog(
              {
                msg: `${cr.airline} added capacity on ${cr.origin}–${cr.dest} (${old}→${cr.frequency_week}x/wk)`,
                big: invested.has(cr.origin) || invested.has(cr.dest),
                airport: cr.origin,
                airline: cr.airline,
                type: 'capacity',
              },
              cr
            )
          );
        }
      } else if (roll < 0.88) {
        const cr = state.competitor_routes[Math.floor(Math.random() * state.competitor_routes.length)];
        if (!cr) continue;
        const cut = 0.1 + Math.random() * 0.14;
        const oldFare = cr.fare;
        cr.fare = Math.max(49, Math.round(cr.fare * (1 - cut)));
        if (oldFare - cr.fare >= 12) {
          bumpCompetitorMarket(cr.origin, cr.airline, { fare_index: 1 - cut });
          logs.push(
            enrichCompetitorLog(
              {
                msg: `${cr.airline} cut ${cr.origin}–${cr.dest} fares ~${Math.round(cut * 100)}% (now from $${cr.fare})`,
                big: invested.has(cr.origin) || invested.has(cr.dest),
                airport: cr.origin,
                airline: cr.airline,
                type: 'fare_cut',
                pct: cut,
              },
              cr
            )
          );
        }
      } else if (state.competitor_routes.length > 6) {
        const idx = Math.floor(Math.random() * state.competitor_routes.length);
        const cr = state.competitor_routes[idx];
        if (cr.frequency_week <= 3) {
          state.competitor_routes.splice(idx, 1);
          logs.push(
            enrichCompetitorLog(
              {
                msg: `${cr.airline} exited ${cr.origin}–${cr.dest}`,
                big: invested.has(cr.origin) || invested.has(cr.dest),
                airport: cr.origin,
                airline: cr.airline,
                type: 'exit',
              },
              cr
            )
          );
        } else {
          cr.frequency_week = Math.max(2, cr.frequency_week - 3);
        }
      }
    }

    logs.forEach((l) => pushEvent(formatCompetitorEventMsg(l), competitorEventTier(l.type)));
    const big = logs.find((l) => l.big);
    if (big && state.day - (state.last_competitor_event_day || 0) >= 45) {
      state.last_competitor_event_day = state.day;
      const impact = competitorImpactHtml(big);
      if (big.type === 'new_route') {
        queueDecision({
          airport: big.airport,
          kicker: `${fmtDate(state.day)} · Competitor network`,
          title: `${big.airline} enters ${big.airport}`,
          body: `${big.msg}. This overlaps markets you may want.${impact}`,
          teach: 'Check Routes for load impact. Match only if the market is price-sensitive; otherwise lean on marketing or ancillaries.',
          logLine: big.msg,
          options: [
            { id: 'routes', label: 'A — Review my routes', hint: 'Check load and fares.', effect: 'tab_routes', airport: big.airport },
            marketingDecisionOption('market', 'B — Boost marketing', big.airport, 'capitalize', {
              competitorResponse: true,
              awarenessBoost: true,
            }),
            { id: 'ignore', label: 'C — Ignore for now', effect: 'none' },
          ],
        });
      } else if (big.type === 'fare_cut') {
        queueDecision({
          kind: 'threat',
          airport: big.airport,
          kicker: `${fmtDate(state.day)} · Fare war`,
          title: `${big.airline} undercuts at ${big.airport}`,
          body: `${big.msg}.${impact}`,
          teach: 'Price fight — match, ancillary, advertise, or wait. Resumes at Slow.',
          logLine: big.msg,
          options: fareWarResponseOptions(big.airport, big.airline, big.pct || 0.12),
        });
      } else if (big.type === 'exit') {
        queueDecision({
          kind: 'opportunity',
          airport: big.airport,
          kicker: `${fmtDate(state.day)} · Market opening`,
          title: `${big.airline} leaves ${big.airport}`,
          body: `${big.msg}. Capacity left the market — room to raise fares, add frequency, or advertise.${impact}`,
          teach: 'Opening, not a fare war. Resumes at Slow so you can watch loads.',
          logLine: big.msg,
          options: opportunityResponseOptions(big.airport, 'exit'),
        });
      }
    }
    state.last_competitor_ai_day = state.day;
  }

  function routeFareBuckets(route) {
    const base = route.fare || 129;
    const mode = route.ancillary_mode || 'auto';
    let basicMult = 0.84;
    let flexMult = 1.32;
    if (mode === 'aggressive') {
      basicMult = 0.72;
      flexMult = 1.18;
    } else if (mode === 'minimal') {
      basicMult = 0.94;
      flexMult = 1.45;
    }
    return [
      { id: 'basic', fare: Math.max(49, Math.round(base * basicMult)), share: mode === 'aggressive' ? 0.52 : 0.42 },
      { id: 'standard', fare: base, share: 0.38 },
      { id: 'flex', fare: Math.min(899, Math.round(base * flexMult)), share: 0.2 },
    ];
  }

  function bucketedTicketRevenue(route, pax) {
    const buckets = routeFareBuckets(route);
    let rev = 0;
    let assigned = 0;
    buckets.forEach((b) => {
      const n = Math.floor(pax * b.share);
      rev += n * b.fare;
      assigned += n;
    });
    const rem = pax - assigned;
    if (rem > 0) rev += rem * route.fare;
    return rev;
  }

  function ancillaryPerPax(route, load, o, d) {
    const mode = effectiveAncillaryMode(route);
    const regional = (o && o.regional) || (d && d.regional);
    let base = regional ? 22 : 16;
    if (mode === 'aggressive') base *= 1.55;
    else if (mode === 'minimal') base *= 0.45;
    else base *= 0.92 + Math.min(0.35, (load || 0.5) * 0.25);
    const buckets = routeFareBuckets(route);
    const basicShare = buckets[0].share;
    if (mode === 'auto' || mode === 'aggressive') base *= 0.85 + basicShare * 0.35;
    return Math.round(base);
  }

  function planeTargetBlockHoursDay(plane) {
    const ac = aircraftType(plane.type);
    return ac?.target_block_hours_day || 8;
  }

  function planeBlockHoursToday(plane) {
    if (!plane || plane.aog_days_left > 0) return 0;
    let hours = 0;
    (state.routes || []).forEach((r) => {
      if (r.aircraft_id !== plane.id) return;
      const ac = aircraftType(r.aircraft_type);
      if (!ac) return;
      hours += blockHours(routeDistance(r), ac) * (r.frequency_week / 7);
    });
    return hours;
  }

  function planeUtilizationPct(plane) {
    const target = planeTargetBlockHoursDay(plane);
    const today = planeBlockHoursToday(plane);
    return Math.min(100, (today / Math.max(target, 0.5)) * 100);
  }

  function planeMonthUtilizationPct(plane) {
    const target = planeTargetBlockHoursDay(plane) * 30;
    const actual = plane.block_hours_month || 0;
    return Math.min(100, (actual / Math.max(target, 1)) * 100);
  }

  function isPlaneAvailable(plane) {
    return plane && (!plane.aog_days_left || plane.aog_days_left <= 0);
  }

  function ensurePlaneTelemetry(plane) {
    if (!plane) return plane;
    if (plane.aog_days_left == null) plane.aog_days_left = 0;
    if (plane.block_hours_month == null) plane.block_hours_month = 0;
    if (plane.total_aog_days == null) plane.total_aog_days = 0;
    if (!Array.isArray(plane.aog_log)) plane.aog_log = [];
    if (plane.acquired_day == null) plane.acquired_day = Math.max(0, (state && state.day) || 0);
    if (plane.aog_events == null) plane.aog_events = 0;
    const ac = aircraftType(plane.type);
    if (!plane.leased && plane.life_months_left == null && ac) {
      plane.life_months_left = (ac.lifespan_years || 25) * 12;
    }
    if (plane.leased && plane.lease_months_left == null) plane.lease_months_left = 60;
    return plane;
  }

  /** Reliability 0–100 from utilization stress + AOG history (display + AOG risk context). */
  function planeReliabilityScore(plane) {
    ensurePlaneTelemetry(plane);
    const util = planeMonthUtilizationPct(plane);
    let score = 90;
    // Sweet spot ~50–78% monthly utilization
    if (util > 94) score -= 22;
    else if (util > 85) score -= 12;
    else if (util > 78) score -= 5;
    else if (util < 25 && (state.routes || []).some((r) => r.aircraft_id === plane.id)) score -= 4;
    score -= Math.min(28, (plane.total_aog_days || 0) * 1.4);
    score -= Math.min(18, (plane.aog_events || 0) * 3.5);
    if (plane.aog_days_left > 0) score -= 15;
    // Age wear on owned metal
    if (!plane.leased) {
      const ac = aircraftType(plane.type);
      const lifeTotal = (ac && ac.lifespan_years ? ac.lifespan_years : 25) * 12;
      const left = plane.life_months_left != null ? plane.life_months_left : lifeTotal;
      const usedPct = 1 - left / Math.max(1, lifeTotal);
      if (usedPct > 0.7) score -= 10;
      else if (usedPct > 0.5) score -= 5;
    }
    return Math.max(12, Math.min(99, Math.round(score)));
  }

  function planeAogRiskPct(plane) {
    if (!isPlaneAvailable(plane)) return 0;
    const util = planeMonthUtilizationPct(plane);
    let risk = 0.006;
    if (util > 82) risk = 0.018;
    if (util > 94) risk = 0.032;
    // Soften with reliability
    const rel = planeReliabilityScore(plane) / 100;
    risk *= 1.35 - rel * 0.5;
    return Math.min(12, risk * 100);
  }

  function planeUsefulLifeInfo(plane) {
    ensurePlaneTelemetry(plane);
    const ac = aircraftType(plane.type);
    if (plane.leased) {
      const left = plane.lease_months_left || 0;
      const total = 60;
      return {
        kind: 'lease',
        label: 'Lease remaining',
        monthsLeft: left,
        yearsLeft: left / 12,
        pctLeft: Math.max(0, Math.min(100, (left / total) * 100)),
        detail: `${left} months on lease · deposit already paid`,
      };
    }
    const lifeTotal = (ac && ac.lifespan_years ? ac.lifespan_years : 25) * 12;
    const left = plane.life_months_left != null ? plane.life_months_left : lifeTotal;
    return {
      kind: 'owned',
      label: 'Useful life left',
      monthsLeft: left,
      yearsLeft: left / 12,
      pctLeft: Math.max(0, Math.min(100, (left / lifeTotal) * 100)),
      detail: `${Math.ceil(left / 12)} of ${ac ? ac.lifespan_years || 25 : 25} years remaining · retired at 0`,
    };
  }

  function recordPlaneAog(plane, daysOut, util) {
    ensurePlaneTelemetry(plane);
    plane.aog_events = (plane.aog_events || 0) + 1;
    plane.total_aog_days = (plane.total_aog_days || 0) + daysOut;
    plane.aog_log.push({
      day: state.day,
      days: daysOut,
      util: Math.round(util),
    });
    if (plane.aog_log.length > 24) plane.aog_log.shift();
  }

  function processFleetDay() {
    if (!state || !state.fleet) return;
    state.fleet.forEach((plane) => {
      ensurePlaneTelemetry(plane);
      if (plane.aog_days_left > 0) {
        plane.aog_days_left -= 1;
        if (plane.aog_days_left === 0) {
          const ac = aircraftType(plane.type);
          // Partial reputation recovery when service resumes (rest via marketing / clean ops).
          const recover = Math.min(2.8, (state.aog_rep_debt || 0) * 0.35 + 0.8);
          if (recover > 0.2) {
            state.reputation = Math.min(100, (state.reputation || 0) + recover);
            state.aog_rep_debt = Math.max(0, (state.aog_rep_debt || 0) - recover);
          }
          pushEvent(
            `${ac ? ac.name : plane.id} returned to service after maintenance.` +
              (recover > 0.2 ? ` Reputation +${recover.toFixed(1)} as flights resume.` : ''),
            'good'
          );
        }
      }
    });

    if (state.day > 0 && state.day % 7 === 0) {
      state.fleet.forEach((plane) => {
        if (!isPlaneAvailable(plane)) return;
        const util = planeMonthUtilizationPct(plane);
        let risk = 0.006;
        if (util > 82) risk = 0.018;
        if (util > 94) risk = 0.032;
        const rel = planeReliabilityScore(plane) / 100;
        risk *= 1.35 - rel * 0.5;
        if (Math.random() < risk) {
          plane.aog_days_left = 1 + Math.floor(Math.random() * 4);
          recordPlaneAog(plane, plane.aog_days_left, util);
          const ac = aircraftType(plane.type);
          const affectedRoutes = (state.routes || []).filter((r) => r.aircraft_id === plane.id);
          const affected = affectedRoutes.length;
          // Product specialties: feeder / business bank / essential punish cancellations harder.
          let prodMult = 1;
          affectedRoutes.forEach((r) => {
            const p = routeProduct(routeProductId(r));
            prodMult = Math.max(prodMult, p.repOnAog != null ? p.repOnAog : 1);
          });
          // Cancellations hurt trust immediately — loads (demand capture) use reputation.
          const repHit = Math.min(
            8.5,
            (1.2 + affected * 0.85 + plane.aog_days_left * 0.35) * prodMult
          );
          const before = state.reputation || 0;
          state.reputation = Math.max(0, before - repHit);
          state.aog_rep_debt = (state.aog_rep_debt || 0) + repHit * 0.55; // recover later when metal returns
          pushEvent(
            `AOG: ${ac ? ac.name : plane.type} (${plane.id}) — ${plane.aog_days_left}d out.` +
              (affected
                ? ` <b>${affected}</b> route(s) cancel until return — reputation <b>−${repHit.toFixed(1)}</b> (now ${state.reputation.toFixed(0)}). Soft loads until trust recovers.`
                : ' Aircraft idle — lease still due. Reputation soft hit.'),
            'bad'
          );
        }
      });
    }

    if (state.day > 0 && state.day % 30 === 0) {
      state.fleet.forEach((plane) => {
        const util = planeMonthUtilizationPct(plane);
        if (util < 35 && (state.routes || []).some((r) => r.aircraft_id === plane.id)) {
          pushEvent(`Low utilization: ${plane.id} flew ${util.toFixed(0)}% of target block hours last month — lease cost unchanged.`, 'bad');
        }
        plane.block_hours_month = 0;
      });
    }
  }

  function investedAirports() {
    const set = new Set();
    (state.gates || []).forEach((g) => set.add(g.airport));
    (state.routes || []).forEach((r) => {
      set.add(r.origin);
      set.add(r.dest);
    });
    return [...set];
  }

  function routesTouchingAirport(iata) {
    return (state.routes || []).filter((r) => r.origin === iata || r.dest === iata);
  }

  /**
   * Rough airport revenue proxy — does NOT call simulateRouteDay.
   * Used by marketing demand (which is itself used inside demand/sim) to avoid stack overflow.
   */
  function airportGrossProxyMonthly(iata) {
    let monthly = 0;
    (state.routes || []).forEach((route) => {
      if (route.origin !== iata && route.dest !== iata) return;
      const ac = aircraftType(route.aircraft_type);
      const plane = route.aircraft_id ? (state.fleet || []).find((f) => f.id === route.aircraft_id) : null;
      const seats = plane ? fleetSeatCount(plane) : ac ? ac.seats : 50;
      // Conservative 55% load · daily flights · fare (ticket only)
      const dailyPax = seats * ((route.frequency_week || 0) / 7) * 0.55;
      monthly += dailyPax * (route.fare || 129) * 30;
    });
    return Math.max(0, Math.round(monthly));
  }

  function airportScopedDailyEconomics(iata) {
    let dayRev = 0;
    let dayCost = 0;
    let dayPax = 0;
    (state.routes || []).forEach((route) => {
      if (route.origin !== iata && route.dest !== iata) return;
      const sim = simulateRouteDay(route);
      dayRev += sim.revenue;
      dayCost += sim.cost;
      dayPax += sim.pax || 0;
    });
    const monthlyGross = Math.round(dayRev * 30);
    const monthlyContribution = Math.round((dayRev - dayCost) * 30);
    return { dayRev, dayCost, dayPax, monthlyGross, monthlyContribution };
  }

  /** Marketing $ scaled to ~3–5% of airport route revenue (regional airline benchmark). */
  function scaledMarketingAmount(iata, purpose) {
    // Prefer full sim when available, but never recurse through demand→marketing.
    let monthlyGross = airportGrossProxyMonthly(iata);
    try {
      if (!simulatingDemandDepth) {
        monthlyGross = Math.max(monthlyGross, airportScopedDailyEconomics(iata).monthlyGross);
      }
    } catch (e) {
      /* keep proxy */
    }
    const routes = routesTouchingAirport(iata).length || 1;
    const pctByPurpose = {
      response: 0.045,
      capitalize: 0.035,
      surge: 0.03,
      starter: 0.05,
      coach: 0.04,
      ota_alt: 0.038,
    };
    const pct = pctByPurpose[purpose] || 0.04;
    const grossFloor = routes === 1 ? 55_000 : 80_000;
    monthlyGross = Math.max(monthlyGross, grossFloor);
    let amount = Math.round(monthlyGross * pct);
    const min = routes === 1 ? 4_000 : 6_000;
    const max = routes === 1 ? 14_000 : Math.min(40_000, Math.round(monthlyGross * 0.1));
    return clampMoney(Math.min(max, Math.max(min, amount)));
  }

  function formatMarketingK(amount) {
    const n = clampMoney(amount);
    return (n / 1000).toFixed(n % 1000 === 0 ? 0 : 1);
  }

  function marketingDecisionOption(id, labelCore, iata, purpose, extra) {
    const amount = scaledMarketingAmount(iata, purpose);
    return {
      id,
      label: `${labelCore} $${formatMarketingK(amount)}k/mo at ${iata}`,
      hint: marketingPaybackHint(iata, amount),
      effect: 'marketing',
      airport: iata,
      amount,
      ...(extra || {}),
    };
  }

  function marketingPaybackHint(iata, amount) {
    const routes = routesTouchingAirport(iata);
    const avgFare = routes.length
      ? routes.reduce((s, r) => s + (r.fare || 129), 0) / routes.length
      : 120;
    const revPerPax = Math.max(65, Math.round(avgFare * 0.88 + 18));
    const dailyCost = amount / 30;
    const pax = Math.max(1, Math.ceil(dailyCost / revPerPax));
    const pct =
      airportScopedDailyEconomics(iata).monthlyGross > 0
        ? Math.round((amount / airportScopedDailyEconomics(iata).monthlyGross) * 100)
        : null;
    const pctNote = pct != null ? `${pct}% of ${iata} route revenue · ` : '';
    return `${pctNote}needs ~${pax} extra pax/day to cover spend`;
  }

  function applyMarketingSpend(option) {
    const ap = option.airport;
    if (!ap) return;
    const amount = option.amount || 12000;
    const prev = clampMoney(state.marketing_spend_monthly[ap]);
    const next = option.setAmount ? clampMoney(option.amount || amount) : clampMoney(prev + (option.amount || amount));
    state.marketing_spend_monthly[ap] = next;
    // Immediate brand bump when you change spend (was nearly invisible: /22000).
    const awarenessDelta = option.setAmount ? Math.max(0, next - prev) : amount;
    if (awarenessDelta > 0 || option.awarenessBoost || option.competitorResponse) {
      const bump = Math.max(1.5, awarenessDelta / 3500);
      state.brand_awareness[ap] = Math.min(100, (state.brand_awareness[ap] || 0) + bump);
      // Marketing also rebuilds system-wide reputation (bookings + trust).
      const repBump = Math.min(1.4, 0.2 + awarenessDelta / 12000);
      state.reputation = Math.min(100, (state.reputation || 0) + repBump);
      if ((state.aog_rep_debt || 0) > 0) {
        state.aog_rep_debt = Math.max(0, state.aog_rep_debt - repBump * 0.5);
      }
    }
    if (option.softenCompetitor && option.airline && state.competitor_markets[ap]) {
      const m = state.competitor_markets[ap][option.airline];
      if (m) {
        if (m.fare_index < 1) m.fare_index = Math.min(1, m.fare_index + (1 - m.fare_index) * 0.3);
        if (m.capacity_index > 1) m.capacity_index = Math.max(1, m.capacity_index - (m.capacity_index - 1) * 0.25);
      }
    }
    const impact = marketingImpactSummary(ap);
    pushPlayerEvent(
      `marketing at ${ap}: ${impact.line}. Watch <b>route load %</b> and brand on the airport card over the next days (load moves gradually).`
    );
    saveGame();
    renderAll();
  }

  function applyDecisionEffect(option) {
    if (!option || option.effect === 'none') return;
    if (option.effect === 'match_fares') {
      const pct = option.pct || 0.15;
      const mult = 1 - pct;
      routesTouchingAirport(option.airport).forEach((r) => {
        r.fare = Math.max(49, Math.round(r.fare * mult));
        r.fare_mode = 'manual';
      });
      pushPlayerEvent(`matched competitor fare cut at ${option.airport} (~${Math.round(pct * 100)}%).`);
    } else if (option.effect === 'marketing') {
      applyMarketingSpend(option);
    } else if (option.effect === 'hub_routes' && option.airport) {
      focusHubForRoutes(option.airport);
    } else if (option.effect === 'open_tab' && option.tab) {
      switchTab(option.tab);
    } else if (option.effect === 'tab_routes') {
      switchTab('routes');
    } else if (option.effect === 'tab_finance') {
      switchTab('finance');
    } else if (option.effect === 'tab_fleet') {
      switchTab('fleet');
    } else if (option.effect === 'tab' && option.tab) {
      switchTab(option.tab);
    } else if (option.effect === 'route_review' && option.routeId) {
      switchTab('routes');
      openRouteReview(option.routeId);
    } else if (option.effect === 'open_event_route' && option.origin && option.dest) {
      openRouteStudio({
        origin: option.origin,
        dest: option.dest,
        step: 2,
      });
      if (routeLaunchDraft) {
        routeLaunchDraft.product = 'event';
        routeLaunchDraft.withReturn = true;
        renderRouteLaunchModal();
      }
    } else if (option.effect === 'goal_hangar') {
      setSpeed('pause');
      saveGame();
      showScreen('screen-start');
      showScenarioPicker();
      renderScenarioPicker();
      renderStartSaves();
    } else if (option.effect === 'bump_route_freq' && option.routeId) {
      bumpRouteFrequency(option.routeId, option.delta || 1, {
        mirrorReturn: option.mirrorReturn !== false,
      });
    } else if (option.effect === 'hold_premium') {
      state.reputation = Math.min(100, (state.reputation || 0) + 2);
      pushPlayerEvent(`held premium positioning at ${option.airport} — reputation +2.`);
    } else if (option.effect === 'ota_promo') {
      const p = (bootstrap.ota_platforms || []).find((x) => x.id === option.platform);
      if (p) {
        state.macro.ota_listed[option.platform] = true;
        state.macro.ota_promo = state.macro.ota_promo || {};
        state.macro.ota_promo[option.platform] = {
          months_left: option.months || 3,
          discount: option.discount || 0.5,
          airport: option.airport,
        };
        pushPlayerEvent(`joined ${p.name} spotlight at ${option.airport} (${Math.round((option.discount || 0.5) * 100)}% off fees).`);
      }
    } else if (option.effect === 'cut_fares') {
      routesTouchingAirport(option.airport).forEach((r) => {
        r.fare = Math.max(49, Math.round(r.fare * (1 - (option.pct || 0.08))));
        r.fare_mode = 'manual';
      });
      pushPlayerEvent(`trimmed fares ~${Math.round((option.pct || 0.08) * 100)}% on ${option.airport} routes.`);
    } else if (option.effect === 'ancillary_aggressive') {
      routesTouchingAirport(option.airport).forEach((r) => {
        r.ancillary_mode = 'aggressive';
        if (r.fare_mode !== 'manual') r.fare = Math.max(49, Math.round(r.fare * 0.94));
      });
      pushPlayerEvent(`shifted ${option.airport} routes to ancillary-heavy pricing.`);
    } else if (option.effect === 'raise_fares' && option.airport) {
      const pct = option.pct || 0.05;
      routesTouchingAirport(option.airport).forEach((r) => {
        r.fare = Math.min(899, Math.max(49, Math.round(r.fare * (1 + pct))));
        r.fare_mode = 'manual';
      });
      pushPlayerEvent(`raised fares ~${Math.round(pct * 100)}% on ${option.airport} routes while competitors retreated.`);
    } else if (option.effect === 'demand_surge' && option.airport) {
      if (!state.airport_demand_surges) state.airport_demand_surges = {};
      state.airport_demand_surges[option.airport] = {
        days_left: option.days || 45,
        mult: option.mult || 1.12,
      };
      pushPlayerEvent(
        `travel demand surge at ${option.airport} — +${Math.round(((option.mult || 1.12) - 1) * 100)}% local demand for ${option.days || 45} days.`
      );
    } else if (option.effect === 'chapter11_restructure') {
      applyChapter11Restructure();
    } else if (option.effect === 'chapter11_sell_gates') {
      applyChapter11SellGates();
    } else if (option.effect === 'chapter11_park_fleet') {
      applyChapter11ParkFleet();
    } else if (option.effect === 'chapter11_liquidate') {
      applyChapter11Liquidate();
    }
  }

  function airportDemandSurgeMult(iata) {
    if (!state || !state.airport_demand_surges) return 1;
    const s = state.airport_demand_surges[iata];
    if (!s || s.days_left <= 0) return 1;
    return s.mult || 1;
  }

  function processAirportDemandSurges() {
    if (!state || !state.airport_demand_surges) return;
    Object.keys(state.airport_demand_surges).forEach((ap) => {
      const s = state.airport_demand_surges[ap];
      if (!s) return;
      s.days_left -= 1;
      if (s.days_left <= 0) delete state.airport_demand_surges[ap];
    });
  }

  function bestRouteTouching(iata) {
    const routes = routesTouchingAirport(iata);
    if (!routes.length) return null;
    // Prefer thinnest load / lowest frequency for "add capacity" responses
    return [...routes].sort((a, b) => {
      const la = a.smooth_load != null ? a.smooth_load : a.yesterday_load != null ? a.yesterday_load : 0.5;
      const lb = b.smooth_load != null ? b.smooth_load : b.yesterday_load != null ? b.yesterday_load : 0.5;
      return la - lb || (a.frequency_week || 0) - (b.frequency_week || 0);
    })[0];
  }

  function fareWarResponseOptions(iata, airline, pct) {
    const amount = scaledMarketingAmount(iata, 'response');
    const amtK = (amount / 1000).toFixed(amount % 1000 === 0 ? 0 : 1);
    const cutPct = Math.round((pct || 0.12) * 100);
    const thin = bestRouteTouching(iata);
    const opts = [
      {
        id: 'match',
        label: `A — Match the ~${cutPct}% cut on ${iata} routes`,
        hint: `Defend seats today — ticket margin falls with ${airline}.`,
        effect: 'match_fares',
        airport: iata,
        pct: pct || 0.12,
      },
      {
        id: 'ancillary',
        label: 'B — Keep base fare · go ancillary-heavy',
        hint: 'Compete on bags/seats fees without matching ticket price.',
        effect: 'ancillary_aggressive',
        airport: iata,
      },
      {
        id: 'market',
        label: `C — Hold fares · $${amtK}k/mo ads at ${iata}`,
        hint: marketingPaybackHint(iata, amount),
        effect: 'marketing',
        airport: iata,
        amount,
        competitorResponse: true,
        awarenessBoost: true,
        softenCompetitor: true,
        airline,
      },
    ];
    if (thin) {
      opts.push({
        id: 'freq',
        label: `D — Add +2/wk on ${thin.origin}–${thin.dest} (match return)`,
        hint: 'More frequency vs their cheap seats — uses gate/aircraft hours.',
        effect: 'bump_route_freq',
        routeId: thin.id,
        delta: 2,
        mirrorReturn: true,
      });
    }
    opts.push({
      id: 'ignore',
      label: `${thin ? 'E' : 'D'} — Hold everything · watch loads`,
      hint: 'No spend. Revisit Routes if load softens over the next week.',
      effect: 'none',
    });
    return opts;
  }

  function opportunityResponseOptions(iata, kind) {
    const amount = scaledMarketingAmount(iata, kind === 'surge' ? 'surge' : 'capitalize');
    const amtK = (amount / 1000).toFixed(amount % 1000 === 0 ? 0 : 1);
    const thin = bestRouteTouching(iata);
    const opts = [];
    if (kind === 'fare_rise' || kind === 'pullback' || kind === 'exit') {
      opts.push({
        id: 'raise',
        label: `A — Raise fares ~5% on ${iata} routes`,
        hint: 'Harvest margin while competitors ease pressure.',
        effect: 'raise_fares',
        airport: iata,
        pct: 0.05,
      });
      opts.push({
        id: 'hold_rep',
        label: 'B — Hold fares · bank reputation',
        hint: 'Loads should improve; reputation +2.',
        effect: 'hold_premium',
        airport: iata,
      });
    } else {
      // demand surge
      opts.push({
        id: 'raise',
        label: `A — Raise fares ~5% on ${iata} routes`,
        hint: 'Hot market can absorb a small fare bump.',
        effect: 'raise_fares',
        airport: iata,
        pct: 0.05,
      });
      opts.push({
        id: 'hold_rep',
        label: 'B — Hold fares · take the loads',
        hint: 'Fill seats at current price; reputation +2.',
        effect: 'hold_premium',
        airport: iata,
      });
    }
    opts.push({
      id: 'market',
      label: `C — Spend $${amtK}k/mo ads at ${iata}`,
      hint: marketingPaybackHint(iata, amount),
      effect: 'marketing',
      airport: iata,
      amount,
      awarenessBoost: true,
      competitorResponse: true,
    });
    if (thin) {
      opts.push({
        id: 'freq',
        label: `D — Add +2/wk on ${thin.origin}–${thin.dest}`,
        hint: 'Capture more of the opening with frequency (return matched).',
        effect: 'bump_route_freq',
        routeId: thin.id,
        delta: 2,
        mirrorReturn: true,
      });
    }
    opts.push({
      id: 'ignore',
      label: `${thin ? 'E' : 'D'} — Ride it out · no change`,
      hint: 'Market effect already applied; you spend nothing.',
      effect: 'none',
    });
    return opts;
  }

  function capacityPressureOptions(iata, airline, pct) {
    const amount = scaledMarketingAmount(iata, 'response');
    const amtK = (amount / 1000).toFixed(amount % 1000 === 0 ? 0 : 1);
    const thin = bestRouteTouching(iata);
    const opts = [
      {
        id: 'cut',
        label: `A — Trim fares ~8% on ${iata} routes`,
        hint: 'Defend load against their extra seats.',
        effect: 'cut_fares',
        airport: iata,
        pct: 0.08,
      },
      {
        id: 'ancillary',
        label: 'B — Ancillary-heavy pricing (keep base fare)',
        hint: 'Compete on bags/seats without a full fare war.',
        effect: 'ancillary_aggressive',
        airport: iata,
      },
      {
        id: 'market',
        label: `C — Hold fares · $${amtK}k/mo marketing`,
        hint: marketingPaybackHint(iata, amount),
        effect: 'marketing',
        airport: iata,
        amount,
        competitorResponse: true,
        awarenessBoost: true,
        airline,
      },
    ];
    if (thin) {
      opts.push({
        id: 'freq',
        label: `D — Match capacity: +2/wk on ${thin.origin}–${thin.dest}`,
        hint: 'Fight seats with seats (uses gate/aircraft).',
        effect: 'bump_route_freq',
        routeId: thin.id,
        delta: 2,
        mirrorReturn: true,
      });
    }
    opts.push({
      id: 'ignore',
      label: `${thin ? 'E' : 'D'} — Do nothing · reassess in Routes`,
      hint: 'Watch loads for a week before reacting.',
      effect: 'none',
    });
    return opts;
  }

  function dismissDecisionsForRouteLaunch() {
    if (!activeDecision && !decisionQueue.length) return;
    activeDecision = null;
    decisionQueue = [];
    state.paused_reason = null;
    state.onboarding_done = true;
    renderDecisionModal();
    clearTutorialHighlight();
    coalescedDecisionCount = 0;
    renderPauseBanner();
  }

  function showRouteFormError(msg) {
    const el = $('route-form-error');
    if (el) {
      el.textContent = msg;
      el.style.display = msg ? 'block' : 'none';
    } else if (msg) {
      alert(msg);
    }
  }

  function captureRouteFormDraft() {
    const oSearch = $('rt-origin-search');
    const oCode = $('rt-origin-code');
    const dSearch = $('rt-dest-search');
    const dCode = $('rt-dest-code');
    const ac = $('rt-aircraft');
    const freq = $('rt-freq');
    const fare = $('rt-fare');
    if (!oSearch && routeFormDraft) return routeFormDraft;
    const draft = {
      origin: (oCode && oCode.value) || defaultRouteOrigin(),
      originLabel: (oSearch && oSearch.value) || '',
      dest: (dCode && dCode.value) || '',
      destLabel: (dSearch && dSearch.value) || '',
      aircraftId: (ac && ac.value) || '',
      freq: (freq && freq.value) || '7',
      fare: (fare && fare.value) || '129',
    };
    if (oSearch && oSearch.value.trim()) {
      const oAp = resolveAirportQuery(oSearch.value);
      if (oAp) {
        draft.origin = oAp.iata;
        draft.originLabel = airportLabel(oAp);
      }
    }
    if (dSearch && dSearch.value.trim()) {
      const dAp = resolveAirportQuery(dSearch.value);
      if (dAp) {
        draft.dest = dAp.iata;
        draft.destLabel = airportLabel(dAp);
      }
    }
    routeFormDraft = draft;
    return draft;
  }

  function setRouteFormDraft(patch) {
    routeFormDraft = { ...captureRouteFormDraft(), ...patch };
    applyRouteFormDraftToDom();
  }

  function syncRouteOriginFromMap(draft) {
    if (!selectedAirport) return draft;
    const ap = airport(selectedAirport);
    const label = ap ? airportLabel(ap) : selectedAirport;
    if (draft.origin === selectedAirport && draft.originLabel === label) return draft;
    const next = {
      ...draft,
      origin: selectedAirport,
      originLabel: label,
    };
    if (draft.origin !== selectedAirport) {
      next.dest = '';
      next.destLabel = '';
    }
    routeFormDraft = next;
    return next;
  }

  function applyRouteFormDraftToDom() {
    const draft = routeFormDraft || captureRouteFormDraft();
    const oSearch = $('rt-origin-search');
    const oCode = $('rt-origin-code');
    const dSearch = $('rt-dest-search');
    const dCode = $('rt-dest-code');
    const ac = $('rt-aircraft');
    const freq = $('rt-freq');
    const fare = $('rt-fare');
    if (oSearch) oSearch.value = draft.originLabel || '';
    if (oCode) oCode.value = draft.origin || '';
    if (dSearch) dSearch.value = draft.destLabel || '';
    if (dCode) dCode.value = draft.dest || '';
    if (ac && draft.aircraftId && [...ac.options].some((o) => o.value === draft.aircraftId)) {
      ac.value = draft.aircraftId;
    }
    if (freq) freq.value = draft.freq || '7';
    if (fare) fare.value = draft.fare || '129';
  }

  function switchTab(tabId) {
    const btn = document.querySelector(`[data-tab="${tabId}"]`);
    if (!btn) return;
    document.querySelectorAll('[data-tab]').forEach((b) => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach((p) => p.classList.remove('active'));
    btn.classList.add('active');
    const panel = $(`panel-${tabId}`);
    if (panel) panel.classList.add('active');
    if (tabId === 'routes') {
      dismissDecisionsForRouteLaunch();
      renderRoutes({ forceForm: !$('route-launch-form') });
    }
    if (tabId === 'finance') renderFinance();
    if (tabId === 'fleet') renderFleet();
    if (tabId === 'economy') renderEconomy();
    if (tabId === 'events') renderEvents();
    renderOpsGuide();
    if (isMobileLayout()) {
      syncMobileDock(tabId);
      requestAnimationFrame(() => scrollToSidePanel());
    }
  }

  /**
   * Compact welcome snapshot — does not restate scenario briefing from the previous screen.
   * Only what matters to act: cash, assets, and urgent gaps.
   */
  function formatBriefingSections(scenarioId) {
    const sc = bootstrap.scenarios[scenarioId] || {};
    const cards = [];

    // Fleet card
    if (state.fleet.length) {
      const f = state.fleet[0];
      const ac = aircraftType(f.type);
      const more = state.fleet.length > 1 ? ` +${state.fleet.length - 1}` : '';
      cards.push({
        label: 'Fleet',
        value: `${ac ? ac.name : f.type}${more}`,
        sub: `${fleetSeatCount(f)} seats · ${f.leased ? 'leased' : 'owned'}`,
      });
    } else {
      cards.push({ label: 'Fleet', value: 'None yet', sub: 'Lease in Fleet tab', warn: true });
    }

    // Gate card
    if (state.gates.length) {
      const g = state.gates[0];
      const more = state.gates.length > 1 ? ` +${state.gates.length - 1}` : '';
      cards.push({
        label: 'Gate',
        value: `${g.airport}${more}`,
        sub: `${g.tier} · ${fmtMoney(g.monthly)}/mo`,
      });
    } else {
      cards.push({ label: 'Gate', value: 'None yet', sub: 'Click map → lease', warn: true });
    }

    // Route card
    if (state.routes.length) {
      const r = state.routes[0];
      const more = state.routes.length > 1 ? ` +${state.routes.length - 1}` : '';
      cards.push({
        label: 'Route',
        value: `${r.origin}–${r.dest}${more}`,
        sub: `${r.frequency_week}x/wk · $${r.fare}`,
      });
    } else {
      cards.push({ label: 'Route', value: 'None yet', sub: 'Open Routes to launch', warn: true });
    }

    const cardsHtml = cards
      .map(
        (c) =>
          `<div class="brief-card${c.warn ? ' brief-card-warn' : ''}">
            <span class="brief-card-label">${c.label}</span>
            <strong class="brief-card-value">${c.value}</strong>
            <span class="brief-card-sub">${c.sub}</span>
          </div>`
      )
      .join('');

    let alertHtml = '';
    if (state.debt.length) {
      const d = state.debt[0];
      alertHtml = `<p class="brief-alert danger"><b>Debt pressure</b> — ${d.name}: ${fmtMoney(d.principal)} · ${fmtMoney(d.monthly_payment)}/mo. Capital tab is your first stop.</p>`;
    } else if (!state.fleet.length && !state.gates.length) {
      alertHtml = `<p class="brief-alert"><b>Cold start</b> — lease a gate on the map, then an aircraft, then a route.</p>`;
    } else if (!state.routes.length && state.gates.length && state.fleet.length) {
      alertHtml = `<p class="brief-alert"><b>Ready to launch</b> — open Routes and pick a destination from ${state.gates[0].airport}.</p>`;
    }

    const coachNote = sc.winning_track
      ? `<p class="brief-coach muted">A short coach may check in as you grow — nothing to prepare for now.</p>`
      : '';

    const goalNote = sc.goal
      ? `<p class="brief-goal"><b>Your goal:</b> ${sc.goal.label}. No deadline — your finish time is recorded.</p>`
      : '';

    const html = `
      <div class="brief-snapshot">
        <p class="brief-hero"><b>${state.airline_name}</b> · <b>${fmtMoney(state.cash)}</b> cash · clock <b>paused</b></p>
        ${goalNote}
        <div class="brief-cards">${cardsHtml}</div>
        ${alertHtml}
        ${coachNote}
      </div>`;

    let teach = 'Map left · controls right. Press ▶ when you are ready.';
    if (!state.fleet.length) teach = 'Start in Fleet (or Capital if you need cash), then lease a gate on the map.';
    else if (!state.gates.length) teach = 'Click an airport on the map and lease a gate before launching routes.';
    else if (!state.routes.length) teach = 'Open Routes, pick a destination, then press ▶.';
    else if (state.debt.length) teach = 'Watch monthly debt service in Capital — grow cash or restructure early.';

    return { html, teach };
  }

  function buildNewGameBriefing(scenarioId) {
    const sc = bootstrap.scenarios[scenarioId] || {};
    const sections = formatBriefingSections(scenarioId);
    const guided = !!(sc.tutorial || sc.winning_track || scenarioId === 'beginner_2026');

    // Only two clear choices — tour vs jump in. No overlapping A/B that open the same UI.
    const options = guided
      ? [
          {
            id: 'tour',
            label: 'A — Show me around',
            hint: 'Recommended — short tour of map, fleet, and routes.',
            effect: 'start_tutorial',
          },
          {
            id: 'play',
            label: 'B — Jump in',
            hint: 'Skip the tour. Clock stays paused until you press ▶.',
            effect: 'explore',
          },
        ]
      : [
          {
            id: 'play',
            label: 'A — Jump in',
            hint: 'Clock stays paused until you press ▶.',
            effect: 'explore',
          },
          {
            id: 'tour',
            label: 'B — Quick tour',
            hint: 'Optional walkthrough of map, fleet, and routes.',
            effect: 'start_tutorial',
          },
        ];

    return {
      onboarding: true,
      briefing: true,
      kicker: 'You are cleared in',
      title: `Welcome, ${state.player_name}`,
      body: sections.html,
      teach: sections.teach,
      options,
    };
  }

  function applyOnboardingChoice(option) {
    if (!option || option.effect === 'explore' || option.effect === 'none' || option.effect === 'tutorial_finish' || option.effect === 'tutorial_skip' || option.effect === 'start_tutorial') return;
    if (option.effect === 'tab_routes') {
      if (option.airport) selectAirport(option.airport);
      switchTab('routes');
    } else if (option.effect === 'tab_finance') {
      switchTab('finance');
    } else if (option.effect === 'tab_fleet') {
      switchTab('fleet');
    } else if (option.effect === 'select_airport' && option.airport) {
      selectAirport(option.airport);
    } else if (option.effect === 'hub_routes' && option.airport) {
      focusHubForRoutes(option.airport);
    } else if (option.effect === 'bump_route_freq' && option.routeId) {
      bumpRouteFrequency(option.routeId, option.delta || 1);
    }
  }

  function tutorialStep(scenarioId, step, total, title, body, teach, goLabel, goEffect, goAirport, tutorialLast, highlight) {
    return {
      onboarding: true,
      tutorial: true,
      tutorialStep: step,
      tutorialTotal: total,
      tutorialLast: !!tutorialLast,
      highlight: highlight || null,
      kicker: `Tutorial · Step ${step} of ${total}`,
      title,
      body,
      teach,
      options: [
        {
          id: 'go',
          label: goLabel,
          hint: 'Opens the right screen and keeps the game paused.',
          effect: goEffect,
          airport: goAirport,
        },
        {
          id: 'skip',
          label: 'Skip tutorial',
          hint: 'Dismiss remaining steps.',
          effect: 'tutorial_skip',
        },
      ],
    };
  }

  function buildTutorialSteps(scenarioId) {
    const sc = bootstrap.scenarios[scenarioId] || {};
    const hub = (state.gates[0] && state.gates[0].airport) || 'CMH';
    const plane = state.fleet[0];
    const ac = plane ? aircraftType(plane.type) : null;
    const planeLabel = ac ? ac.name : 'regional jet';
    const route = state.routes[0];
    const routeLabel = route ? `${route.origin}–${route.dest}` : `${hub}–DAY`;

    if (scenarioId === 'beginner_2026' || sc.tutorial || sc.winning_track) {
      const winning = isWinningTrackScenario(scenarioId);
      const freq = route ? route.frequency_week : 10;
      const fare = route ? route.fare : 139;
      const total = 8;
      return [
        tutorialStep(
          scenarioId,
          1,
          total,
          `Welcome, ${state.player_name}`,
          `<b>${state.airline_name}</b> is a small Ohio carrier flying a <b>round trip</b> <b>CMH⇄DAY</b> — ` +
            `paying passengers both ways on one leased <b>${planeLabel}</b>, with gates at both cities and <b>${fmtMoney(state.cash)}</b> cash.` +
            (winning ? ` Fares are set near <b>$${fare}</b> and CMH marketing is already on.` : '') +
            ' The clock is <b>paused</b> until you finish this walkthrough.',
          winning
            ? 'Tour the UI first — do not fast-forward until Daily P&L stays green.'
            : 'This tutorial covers the four core loops: map → fleet → routes → fares. Press ▶ only when you are ready to run days.',
          'Start with the map →',
          'select_airport',
          'CMH',
          false,
          { selector: '.map-wrap', label: 'Ohio map — click airports here' }
        ),
        tutorialStep(
          scenarioId,
          2,
          total,
          'Explore your hub on the map',
          'Click airports to see <b>competitors</b>, wealth index, and lease gates. CMH is your home — Allegiant and Southwest matter on Ohio routes.',
          'Drag the map to pan, scroll to zoom. Green dots are airports you control; blue are open markets.',
          'Show CMH on the map →',
          'select_airport',
          'CMH',
          false,
          { selector: '#airport-panel', label: 'Airport panel — competitors & gates' }
        ),
        tutorialStep(
          scenarioId,
          3,
          total,
          'Fleet — lease or buy aircraft',
          `Your <b>${planeLabel}</b> is leased (monthly payment, no big upfront cost). Open <b>Fleet</b> to see range and seats. ` +
            'Do <b>not</b> lease a second plane until <b>Daily P&L</b> stays positive on your first route — overhead bills every day whether seats are full or empty.',
          'Leasing preserves cash; buying builds asset value. Match aircraft size to demand — one profitable route before two planes.',
          'Open Fleet tab →',
          'tab_fleet',
          null,
          false,
          { selector: '[data-tab="fleet"]', label: 'Fleet tab — lease or buy aircraft' }
        ),
        tutorialStep(
          scenarioId,
          4,
          total,
          'Routes — launch or review flights',
          `You already fly <b>CMH⇄DAY</b> both ways. Real airlines sell seats on the return — one-way only means an empty ferry home. ` +
            'When you launch a new city pair, keep <b>Launch with return leg</b> checked (and lease a gate at the far end first).',
          'You need a gate at the origin for each direction. Thin loads cancel automatically so you do not burn fuel empty.',
          'Open Routes tab →',
          'tab_routes',
          hub,
          false,
          { selector: '[data-tab="routes"]', label: 'Routes tab — launch new flights' }
        ),
        tutorialStep(
          scenarioId,
          5,
          total,
          'Fares — dynamic vs fixed',
          'In <b>Routes</b>, set fares to <b>Dynamic</b> and the system reprices weekly like real airlines: weekend peaks, summer/holiday surges, and load-based bumps when planes are full (cuts when empty). ' +
            '<b>Fare buckets</b> (basic/standard/flex) still apply — passengers pay across a range, not one flat price.',
          '<b>Load factor</b> drives revenue management — full flights trigger higher targets; weak loads trigger sales fares. ' +
            'Use <b>Fixed</b> when you want a locked price (e.g. CMH–DAY at $139).',
          'Open Routes & fares →',
          'tab_routes',
          hub,
          false,
          { selector: '#panel-routes', label: 'Fare buckets, ancillary mode & active routes' }
        ),
        tutorialStep(
          scenarioId,
          6,
          total,
          'Market scope — why loads look thin',
          'When you launch a route, <b>Market scope</b> shows the whole airport — not just your gate. ' +
            `<b>CMH</b> runs ~300 departures/week from all airlines; your one E145 at ${freq}/wk is roughly <b>${Math.max(1, Math.round((freq / 300) * 100))}%</b> of that traffic. ` +
            'Demand capture blends airport share, city-pair competition, and frequency — thin loads are normal until you add planes or frequency.',
          'Gate slots cap how many flights <em>you</em> can run; market scope caps how many passengers you can realistically win. ' +
            'Check the three limits strip on launch: <b>Gate · Aircraft · Market</b>.',
          'Open Routes tab →',
          'tab_routes',
          hub,
          false,
          { selector: '#panel-routes', label: 'Launch modal — Market scope panel' }
        ),
        tutorialStep(
          scenarioId,
          7,
          total,
          'Capital — debt, equity, exits',
          'Open the <b>Capital</b> tab anytime. Loans charge <b>interest + principal</b> each month (not just a vague fee). ' +
            'Seed / Series A / PE dilute ownership for company cash; <b>secondary sale</b> and <b>IPO</b> can put money in your personal pocket.',
          'Building a regional is ops + financing. Debt service hits cash on the month tick — watch runway after debt service.',
          'Open Capital tab →',
          'tab_finance',
          null,
          false,
          { selector: '[data-tab="finance"]', label: 'Capital — loans, PE, IPO' }
        ),
        tutorialStep(
          scenarioId,
          8,
          total,
          'You\'re ready to fly',
          'Tutorial complete. Keep the clock paused while you plan, then press <b>▶</b> (or Space) to advance time. ' +
            'Competitor alerts pause the clock — finish the alert, then run at day speed again.',
          'Watch cash runway and Daily P&L in the HUD. Follow the <b>Build a regional</b> steps in Capital / coach when unsure what\'s next.',
          'Got it — let me play →',
          'tutorial_finish',
          null,
          true,
          { selector: '[data-speed="day"]', label: 'Press ▶ to advance time' }
        ),
      ];
    }
    return buildQuickTourSteps(scenarioId);
  }

  function buildQuickTourSteps(scenarioId) {
    const firstGate =
      (state.gates[0] && state.gates[0].airport) ||
      (bootstrap.airports[0] && bootstrap.airports[0].iata) ||
      'DAY';
    const plane = state.fleet[0];
    const ac = plane ? aircraftType(plane.type) : null;
    const planeLabel = ac ? ac.name : 'your first aircraft';
    const hasRoutes = state.routes.length > 0;
    const total = 4;
    const routeNote = hasRoutes
      ? `You already have <b>${state.routes[0].origin}–${state.routes[0].dest}</b> flying.`
      : `Lease a gate if needed, then launch from <b>${firstGate}</b>.`;
    return [
      tutorialStep(
        scenarioId,
        1,
        total,
        `Welcome, ${state.player_name}`,
        `<b>${state.airline_name}</b> starts with <b>${fmtMoney(state.cash)}</b>. ${routeNote} The clock is paused — four quick steps, then press ▶.`,
        'Route Lab loop: map → fleet → routes → run time.',
        firstGate ? `Show ${firstGate} on the map →` : 'Show the map →',
        firstGate ? 'select_airport' : 'explore',
        firstGate,
        false,
        { selector: '.map-wrap', label: 'Map — click airports' }
      ),
      tutorialStep(
        scenarioId,
        2,
        total,
        'Airport panel',
        'Each airport shows <b>competitors</b>, gate lease options, and local marketing. Check demand before you add frequency.',
        'Wealthier airports support higher fares; thin markets need smaller planes.',
        firstGate ? `Open ${firstGate} →` : 'Pick an airport →',
        firstGate ? 'select_airport' : 'explore',
        firstGate,
        false,
        { selector: '#airport-panel', label: 'Airport intel & gates' }
      ),
      tutorialStep(
        scenarioId,
        3,
        total,
        state.fleet.length ? 'Fleet & routes' : 'Get aircraft & routes',
        state.fleet.length
          ? `Your <b>${planeLabel}</b> is in <b>Fleet</b>. Open <b>Routes</b> to launch or tune fares on running flights.`
          : 'Open <b>Fleet</b> to lease an aircraft, then <b>Routes</b> to launch your first flight.',
        'Launch modal shows a business case — judgment is advice, not a block.',
        'Open Routes tab →',
        'tab_routes',
        firstGate,
        false,
        { selector: '[data-tab="routes"]', label: 'Routes — flights & fares' }
      ),
      tutorialStep(
        scenarioId,
        4,
        total,
        'Ready when you are',
        'Press <b>▶</b> when your network looks right. Use the <b>What to do next</b> strip anytime. Rivals react in the Log.',
        'Financials drawer: company vs your personal stake.',
        'Got it →',
        'tutorial_finish',
        null,
        true,
        { selector: '[data-speed="day"]', label: 'Press ▶ to start the clock' }
      ),
    ];
  }

  function isWinningTrackScenario(scenarioId) {
    const id = scenarioId || (state && state.scenario_id);
    const sc = bootstrap.scenarios[id] || {};
    return !!(sc.winning_track || id === 'beginner_winning_2026');
  }

  function tutorialOverheadScale() {
    if (!state) return 1;
    const sc = bootstrap.scenarios[state.scenario_id] || {};
    const n = sc.tutorial_overhead_scale;
    return n != null && Number.isFinite(n) ? Math.max(0.5, Math.min(1, n)) : 1;
  }

  function ensureWinningPlaybook() {
    if (!state) return;
    if (!isWinningTrackScenario()) {
      state.winning_playbook = null;
      return;
    }
    if (!state.winning_playbook || typeof state.winning_playbook !== 'object') {
      state.winning_playbook = { completed: [] };
    }
    if (!Array.isArray(state.winning_playbook.completed)) {
      state.winning_playbook.completed = [];
    }
  }

  function isPlaybookPhaseDone(id) {
    ensureWinningPlaybook();
    return (state.winning_playbook.completed || []).includes(id);
  }

  function markWinningPlaybookDone(id) {
    ensureWinningPlaybook();
    if (!id || isPlaybookPhaseDone(id)) return;
    state.winning_playbook.completed.push(id);
  }

  function routeByEndpoints(origin, dest) {
    return (state.routes || []).find((r) => r.origin === origin && r.dest === dest);
  }

  function winningPlaybookPhases() {
    const route = routeByEndpoints('CMH', 'DAY') || state.routes[0];
    const routeId = route ? route.id : null;
    return [
      {
        id: 'wp_start',
        triggerDay: 0,
        triggerOnStart: true,
        title: 'Phase 1 — Run your first week (paused → slow)',
        body:
          'Your <b>CMH–DAY</b> route is tuned for profit: <b>10/wk</b>, fare <b>$139</b>, and modest <b>CMH marketing</b> (~4–5% of route revenue) already running. ' +
          'Open <b>Financials</b> and watch <b>Daily P&L</b> and <b>Avg load</b> in the HUD.',
        teach:
          'Do <b>not</b> fast-forward (▶▶▶) until Daily P&L stays green. Overhead (lease + gate + HQ) bills every day whether the plane is full or empty.',
        options: [
          {
            id: 'slow',
            label: 'A — Set speed to Slow & open Financials',
            hint: '4-hour steps — safe way to watch loads build.',
            effect: 'playbook_slow_finance',
          },
          {
            id: 'day',
            label: 'B — Set speed to Day & open Routes',
            hint: '1 day per tick — check load % on CMH–DAY.',
            effect: 'playbook_day_routes',
            routeId,
          },
        ],
      },
      {
        id: 'wp_day14',
        triggerDay: 14,
        title: 'Phase 2 — Tune fares & marketing (day 14)',
        body:
          'Two weeks in. If loads are thin, match American’s <b>$139</b> fare and add CMH marketing. ' +
          'If <b>Avg load</b> is already ≥55% and P&L is green, you can skip.',
        teach: 'Marketing raises demand (seat load). It cannot fix a second empty plane — grow one route first.',
        skipIf: (st) => {
          const net = networkRouteStats();
          const econ = simulateDayEconomics();
          return net.avgLoad >= 0.55 && econ.pnl > 200;
        },
        options: [
          {
            id: 'fare_mkt',
            label: 'A — Fare $139 + scaled CMH marketing',
            hint: 'One-click tune for CMH–DAY.',
            effect: 'playbook_tune_cmh_day',
            routeId,
            airport: 'CMH',
            fare: 139,
          },
          {
            id: 'mkt_only',
            label: 'B — CMH marketing only (scaled to revenue)',
            hint: 'Keep fare; buy awareness.',
            effect: 'set_marketing',
            airport: 'CMH',
          },
          {
            id: 'skip',
            label: 'C — Skip — metrics look good',
            hint: 'Mark step done; continue at day speed.',
            effect: 'none',
          },
        ],
      },
      {
        id: 'wp_day45',
        triggerDay: 45,
        title: 'Phase 3 — Fly the pair more often (both ways)',
        body:
          'If <b>Daily P&L</b> is green, add <b>+3 departures/week each way</b> on <b>CMH⇄DAY</b> before leasing another plane. ' +
          'That sells more seats <b>CMH→DAY and DAY→CMH</b> (return traffic from Dayton counts too) — more city-pair share, more revenue, still one aircraft. ' +
          'This is not a new destination; it is denser service on the route you already fly.',
        teach:
          'Keep both legs matched when you can. One-way bumps leave the return thin and waste gate time at the other city. Gate + aircraft hours are the limits.',
        skipIf: (st) => simulateDayEconomics().pnl <= 0,
        options: [
          {
            id: 'freq',
            label: 'A — CMH⇄DAY +3/wk both directions',
            hint: 'Outbound and return — more pax both ways on the same E145.',
            effect: 'bump_route_freq',
            routeId,
            delta: 3,
            mirrorReturn: true,
            origin: 'CMH',
            dest: 'DAY',
          },
          {
            id: 'routes',
            label: 'B — Open Routes to adjust manually',
            hint: 'Review load % on each leg first.',
            effect: 'tab_routes',
            airport: 'CMH',
          },
          {
            id: 'wait',
            label: 'C — Not profitable yet — fix fares first',
            hint: 'Stay at current frequency; tune fare or marketing.',
            effect: 'tab_routes',
            airport: 'CMH',
          },
        ],
      },
      {
        id: 'wp_day90',
        triggerDay: 90,
        title: 'Phase 4 — Second aircraft when you can afford it (day 90)',
        body:
          'Roughly three months in. Only add a plane if <b>Daily P&L</b> is green and <b>cash runway</b> is ≥6 months. ' +
          'A <b>PC-12</b> turboprop is best for thin Ohio pairs like CMH–CVG.',
        teach: 'Leasing bills ~$84k deposit + $42k/mo — never add capacity while the first route loses money net.',
        skipIf: (st) => simulateDayEconomics().pnl <= 0 || runwayMonths() < 6,
        options: [
          {
            id: 'pc12',
            label: 'A — Lease PC-12 (coach applies deposit)',
            hint: 'Small plane for thin markets — ~$84k deposit.',
            effect: 'guided_lease',
            aircraftType: 'pc12',
          },
          {
            id: 'fleet',
            label: 'B — Open Fleet shop myself',
            hint: 'Compare lease costs before committing.',
            effect: 'tab_fleet',
          },
          {
            id: 'wait',
            label: 'C — Wait — strengthen CMH–DAY first',
            hint: 'Recommended if P&L is still shaky.',
            effect: 'none',
          },
        ],
      },
      {
        id: 'wp_day120',
        triggerDay: 120,
        title: 'Phase 5 — Launch a second route (day 120)',
        body:
          'With two aircraft (or strong CMH–DAY profits), plan <b>CMH→CVG</b> at <b>7/wk</b>. ' +
          'Skip heavy launch marketing — use modest airport spend only after the route is flying.',
        teach: 'Station build-out is upfront cash. Open the launch modal, check judgment, confirm only if payback looks acceptable.',
        skipIf: (st) => st.fleet.length < 2 && simulateDayEconomics().pnl <= 800,
        options: [
          {
            id: 'launch',
            label: 'A — Open CMH→CVG launch (7/wk preview)',
            hint: 'Uses your second plane if leased.',
            effect: 'prefill_route',
            origin: 'CMH',
            dest: 'CVG',
            freq: 7,
          },
          {
            id: 'routes',
            label: 'B — Browse route suggestions from CMH',
            hint: 'Pick your own pair.',
            effect: 'hub_routes',
            airport: 'CMH',
          },
          {
            id: 'done',
            label: 'C — Winning path complete — fly solo',
            hint: 'Coach steps done; use Profit playbook strip.',
            effect: 'none',
          },
        ],
      },
    ];
  }

  function enrichPlaybookBody(phase) {
    let body = phase.body || '';
    if (!state) return body;
    const net = networkRouteStats();
    const econ = simulateDayEconomics();
    body += `<p class="muted" style="font-size:0.76rem;margin-top:10px;">Snapshot: Avg load <b>${(net.avgLoad * 100).toFixed(0)}%</b> · Daily P&L <b class="${econ.pnl >= 0 ? '' : 'danger'}">${fmtMoney(econ.pnl)}</b> · Cash runway <b>${runwayMonths().toFixed(1)} mo</b></p>`;
    return body;
  }

  function enrichPlaybookOptions(options) {
    return (options || []).map((o) => {
      if (o.effect === 'playbook_tune_cmh_day' && o.airport) {
        const amount = scaledMarketingAmount(o.airport, 'coach');
        return {
          ...o,
          amount,
          setAmount: true,
          label: `A — Fare $${o.fare || 139} + ${o.airport} marketing $${formatMarketingK(amount)}k/mo`,
          hint: marketingPaybackHint(o.airport, amount),
        };
      }
      if (o.effect === 'set_marketing' && o.airport) {
        const amount = scaledMarketingAmount(o.airport, 'coach');
        return {
          ...o,
          amount,
          setAmount: true,
          label: `B — ${o.airport} marketing → $${formatMarketingK(amount)}k/mo`,
          hint: marketingPaybackHint(o.airport, amount),
        };
      }
      return o;
    });
  }

  function buildPlaybookDecision(phase) {
    const route = routeByEndpoints('CMH', 'DAY') || state.routes[0];
    const options = enrichPlaybookOptions(
      (phase.options || []).map((o) => ({
        ...o,
        routeId: o.routeId || (route && route.id),
      }))
    );
    return {
      winningPlaybook: true,
      playbookId: phase.id,
      kicker: `Winning path · Day ${state.day}`,
      title: phase.title,
      body: enrichPlaybookBody(phase),
      teach: phase.teach || '',
      logLine: `Winning path: ${phase.title}`,
      options,
    };
  }

  function queueWinningPlaybookPhase(phaseId) {
    if (!isWinningTrackScenario() || !state || state.game_over) return;
    ensureWinningPlaybook();
    if (isPlaybookPhaseDone(phaseId)) return;
    const phase = winningPlaybookPhases().find((p) => p.id === phaseId);
    if (!phase) return;
    if (phase.skipIf && phase.skipIf(state)) {
      markWinningPlaybookDone(phaseId);
      pushPlayerEvent(`winning path: skipped ${phase.title} — already on track`);
      return;
    }
    queueDecision(buildPlaybookDecision(phase));
  }

  function checkWinningPlaybookDayTriggers() {
    if (!state || state.game_over || !state.onboarding_done || !isWinningTrackScenario()) return;
    if (activeDecision || decisionQueue.length) return;
    ensureWinningPlaybook();
    winningPlaybookPhases().forEach((phase) => {
      if (!phase.triggerDay || phase.triggerOnStart) return;
      if (state.day !== phase.triggerDay) return;
      if (isPlaybookPhaseDone(phase.id)) return;
      queueWinningPlaybookPhase(phase.id);
    });
  }

  function maybeStartWinningPlaybook() {
    if (!state || !state.onboarding_done || !isWinningTrackScenario()) return;
    if (!isPlaybookPhaseDone('wp_start')) {
      queueWinningPlaybookPhase('wp_start');
    }
  }

  function leaseAircraftGuided(type) {
    const ac = aircraftType(type);
    if (!ac) return null;
    const seats = ac.seats != null ? ac.seats : ac.seats_max || ac.seats_min || 50;
    const leaseMo = planeLeaseMonthly(type, seats);
    const deposit = leaseMo * 2;
    if (state.cash < deposit) {
      pushPlayerEvent(`coach lease skipped — need ${fmtMoney(deposit)} deposit for ${ac.name}`);
      return null;
    }
    state.cash -= deposit;
    const plane = {
      id: uid('ac'),
      type,
      seats,
      leased: true,
      lease_months_left: 60,
      aog_days_left: 0,
      block_hours_month: 0,
      total_aog_days: 0,
      aog_events: 0,
      aog_log: [],
      acquired_day: state.day || 0,
    };
    state.fleet.push(plane);
    pushPlayerEvent(`coach: leased ${ac.name} (${seats} seats) — ${fmtMoney(deposit)} deposit`);
    saveGame();
    renderAll();
    return plane.id;
  }

  function applyPlaybookEffect(option) {
    if (!option || option.effect === 'none') return;
    if (option.effect === 'playbook_slow_finance') {
      setSpeed('slow');
      toggleHudPanel('financials');
      pushPlayerEvent('coach: slow speed + Financials — watch Daily P&L for 7+ days before fast-forward.');
      return;
    }
    if (option.effect === 'playbook_day_routes') {
      setSpeed('day');
      switchTab('routes');
      pushPlayerEvent('coach: day speed + Routes — check load % on each route card.');
      return;
    }
    if (option.effect === 'playbook_tune_cmh_day') {
      const fare = option.fare || 139;
      // Apply to both legs of the pair so return traffic stays aligned.
      ['CMH-DAY', 'DAY-CMH'].forEach((pair) => {
        const [o, d] = pair.split('-');
        const r = routeByEndpoints(o, d);
        if (r) setRouteFare(r.id, fare, 'manual');
      });
      const route = routeByEndpoints('CMH', 'DAY') || routeById(option.routeId);
      if (route && !routeByEndpoints('CMH', 'DAY')) setRouteFare(route.id, fare, 'manual');
      if (option.airport) {
        const amt = option.amount || scaledMarketingAmount(option.airport, 'coach');
        applyMarketingSpend({
          airport: option.airport,
          amount: amt,
          setAmount: true,
          competitorResponse: true,
          awarenessBoost: true,
        });
      }
      // Light DAY marketing so return demand keeps pace (does not replace CMH spend).
      if (!state.marketing_spend_monthly.DAY || state.marketing_spend_monthly.DAY < 3000) {
        applyMarketingSpend({
          airport: 'DAY',
          amount: Math.min(4500, scaledMarketingAmount('DAY', 'coach')),
          setAmount: true,
          awarenessBoost: true,
        });
      }
      pushPlayerEvent(
        `coach: fare $${fare} both ways CMH⇄DAY + modest marketing — load moves gradually, not overnight.`
      );
      return;
    }
    if (option.effect === 'set_marketing' && option.airport) {
      applyMarketingSpend({
        airport: option.airport,
        amount: option.amount || scaledMarketingAmount(option.airport, 'coach'),
        setAmount: true,
        competitorResponse: true,
        awarenessBoost: true,
      });
      return;
    }
    if (option.effect === 'set_route_fare' && option.routeId) {
      setRouteFare(option.routeId, option.fare, 'manual');
      pushPlayerEvent(`coach: set fare to $${option.fare}`);
      return;
    }
    if (option.effect === 'guided_lease' && option.aircraftType) {
      leaseAircraftGuided(option.aircraftType);
      return;
    }
    if (option.effect === 'prefill_route' && option.origin && option.dest) {
      const plane =
        state.fleet.find((f) => f.id !== 'ga-1' && !state.routes.some((r) => r.aircraft_id === f.id)) ||
        state.fleet[state.fleet.length - 1];
      if (!plane) {
        pushPlayerEvent('coach: lease a second aircraft before opening CMH–CVG');
        switchTab('fleet');
        return;
      }
      const fare = suggestFareForPair(option.origin, option.dest, plane.type);
      openRouteLaunchModal(option.origin, option.dest, plane.id, option.freq || 7, fare);
      pushPlayerEvent(`coach: opened launch preview ${option.origin}→${option.dest} — confirm only if judgment looks acceptable`);
      return;
    }
    if (option.effect === 'set_speed' && option.speed) {
      setSpeed(option.speed);
      return;
    }
    if (option.effect === 'bump_route_freq' && option.routeId) {
      bumpRouteFrequency(option.routeId, option.delta || 1, {
        mirrorReturn: option.mirrorReturn !== false,
      });
      return;
    }
    applyOnboardingChoice(option);
  }

  function queueOnboarding(scenarioId) {
    if (!state || state.onboarding_done) return;
    queueDecision(buildNewGameBriefing(scenarioId));
  }

  function buildOnboardingFallback(scenarioId) {
    const firstGate =
      (state.gates[0] && state.gates[0].airport) ||
      (bootstrap.airports[0] && bootstrap.airports[0].iata) ||
      'DAY';
    return {
      onboarding: true,
      kicker: 'Getting started',
      title: `Welcome, ${state.player_name}`,
      body:
        `You have <b>${fmtMoney(state.cash)}</b> to launch <b>${state.airline_name}</b>. ` +
        'The clock is <b>paused</b> — pick a first step, then press ▶ when you are ready.',
      teach: 'Lease a gate, open a route, then unpause.',
      options: [
        { id: 'map', label: 'A — Pick an airport', effect: 'select_airport', airport: firstGate },
        { id: 'finance', label: 'B — Review finances', effect: 'tab_finance' },
        { id: 'explore', label: 'C — Explore on my own', effect: 'explore' },
      ],
    };
  }

  function clearTutorialHighlight() {
    const overlay = $('tutorial-highlight');
    if (overlay) {
      overlay.classList.remove('active');
      overlay.innerHTML = '';
    }
    const modal = $('decision-modal');
    if (modal) {
      modal.classList.remove('tutorial-mode', 'tutorial-modal-left', 'tutorial-modal-right', 'tutorial-modal-bottom');
    }
    if (tutorialGlowTarget) {
      tutorialGlowTarget.classList.remove('tutorial-target-glow');
      tutorialGlowTarget = null;
    }
    if (tutorialHighlightResize) {
      window.removeEventListener('resize', tutorialHighlightResize);
      tutorialHighlightResize = null;
    }
  }

  function pickTutorialModalSide(rect) {
    if (isMobileLayout()) return 'bottom';
    const cx = rect.left + rect.width / 2;
    if (cx > window.innerWidth * 0.58) return 'left';
    if (rect.bottom > window.innerHeight * 0.72) return 'bottom';
    return 'right';
  }

  function positionTutorialCallout(callout, rect, pad) {
    const margin = 10;
    if (rect.bottom + 44 < window.innerHeight - 120) {
      callout.style.left = `${Math.max(margin, rect.left)}px`;
      callout.style.top = `${rect.bottom + pad + 6}px`;
    } else if (rect.top > 56) {
      callout.style.left = `${Math.max(margin, rect.left)}px`;
      callout.style.top = `${Math.max(margin, rect.top - pad - 38)}px`;
    } else if (rect.right + 180 < window.innerWidth) {
      callout.style.left = `${rect.right + pad + 8}px`;
      callout.style.top = `${rect.top}px`;
    } else {
      callout.style.left = `${Math.max(margin, rect.left - 8)}px`;
      callout.style.top = `${rect.bottom + pad + 6}px`;
    }
  }

  function applyTutorialHighlight(highlight) {
    clearTutorialHighlight();
    if (!highlight || !highlight.selector) return;

    const target = document.querySelector(highlight.selector);
    const overlay = $('tutorial-highlight');
    if (!target || !overlay) return;

    const pad = highlight.pad != null ? highlight.pad : 8;
    const rect = target.getBoundingClientRect();
    const left = rect.left - pad;
    const top = rect.top - pad;
    const width = rect.width + pad * 2;
    const height = rect.height + pad * 2;
    const style = `left:${left}px;top:${top}px;width:${width}px;height:${height}px`;

    overlay.innerHTML = `
      <div class="tutorial-spotlight" style="${style}"></div>
      <div class="tutorial-ring" style="${style}"></div>
      <p class="tutorial-callout">${highlight.label || ''}</p>`;
    overlay.classList.add('active');

    const callout = overlay.querySelector('.tutorial-callout');
    if (callout) positionTutorialCallout(callout, rect, pad);

    const modal = $('decision-modal');
    if (modal) {
      modal.classList.add('tutorial-mode', `tutorial-modal-${pickTutorialModalSide(rect)}`);
    }

    target.classList.add('tutorial-target-glow');
    tutorialGlowTarget = target;

    const refresh = () => applyTutorialHighlight(highlight);
    tutorialHighlightResize = refresh;
    window.addEventListener('resize', refresh);
  }

  function scheduleTutorialHighlight(highlight) {
    if (!highlight) {
      clearTutorialHighlight();
      return;
    }
    requestAnimationFrame(() => {
      requestAnimationFrame(() => applyTutorialHighlight(highlight));
    });
  }

  function speedAfterInterrupt() {
    // After any alert / popup, always resume at Slow so the next days are
    // readable — not full day/week/month speed where events blur together.
    return 'slow';
  }

  function renderPauseBanner() {
    const banner = $('pause-banner');
    if (!banner || !state) return;
    const hasDecision = !!(activeDecision || decisionQueue.length);
    const manualPause = state.speed === 'pause' && state.onboarding_done && !routeLaunchActive && !hasDecision;
    const show = !!(state.paused_reason || hasDecision || manualPause);
    if (!show) {
      banner.style.display = 'none';
      banner.innerHTML = '';
      return;
    }
    let text = state.paused_reason || '';
    if (!text && hasDecision && activeDecision) {
      text = activeDecision.onboarding
        ? activeDecision.tutorial
          ? `Tutorial step ${activeDecision.tutorialStep || 1} of ${activeDecision.tutorialTotal || '?'}`
          : 'Getting started — pick a first step'
        : 'Market shift — decision required';
    } else if (!text && manualPause) {
      text = 'Clock paused — press Resume when ready';
    }
    const coalescedNote =
      coalescedDecisionCount > 0
        ? `<span class="pause-banner-note">${coalescedDecisionCount} more alert${coalescedDecisionCount === 1 ? '' : 's'} logged to <b>Log</b> while you read this one</span>`
        : '';
    const resumeBtn = hasDecision
      ? ''
      : `<button type="button" class="pause-resume-chip" data-pause-resume title="Resume time">Resume ▶</button>`;
    banner.innerHTML = `<span class="pause-banner-text">Paused — ${text}</span>${coalescedNote}${resumeBtn}`;
    banner.style.display = 'flex';
    const resume = banner.querySelector('[data-pause-resume]');
    if (resume) {
      resume.onclick = () => {
        state.paused_reason = null;
        coalescedDecisionCount = 0;
        resumeSpeedAfterInterrupt();
        renderPauseBanner();
        renderHud();
      };
    }
  }

  function pauseForInterrupt() {
    if (!state || state.speed === 'pause') return;
    decisionSpeedBeforePause = state.speed || speedBeforePause || 'day';
    setSpeed('pause');
  }

  function resumeSpeedAfterInterrupt() {
    if (!state || state.game_over) return;
    if (activeDecision || decisionQueue.length || routeLaunchActive || routeReviewRouteId) return;
    const next = speedAfterInterrupt();
    decisionSpeedBeforePause = null;
    setSpeed(next);
  }

  function resolveDecision(choiceId) {
    if (!activeDecision) return;
    const option = activeDecision.options.find((o) => o.id === choiceId) || { effect: 'none' };
    if (activeDecision.winningPlaybook) {
      // Speed-setting coach options must stick — do not force pause after them.
      const startSpeed =
        option.effect === 'playbook_slow_finance'
          ? 'slow'
          : option.effect === 'playbook_day_routes'
            ? 'day'
            : null;
      applyPlaybookEffect(option);
      markWinningPlaybookDone(activeDecision.playbookId);
      pushPlayerEvent(`winning path: ${activeDecision.title} — ${option.label}`);
      activeDecision = null;
      coalescedDecisionCount = 0;
      renderDecisionModal();
      if (startSpeed) {
        setSpeed(startSpeed);
        state.paused_reason =
          startSpeed === 'slow'
            ? 'Coach: Slow speed — watch Daily P&L, then speed up when green'
            : 'Coach: Day speed — check route loads, press pause anytime';
        setTimeout(() => {
          if (
            state &&
            state.paused_reason &&
            String(state.paused_reason).indexOf('Coach:') === 0 &&
            state.speed !== 'pause'
          ) {
            state.paused_reason = null;
            renderPauseBanner();
          }
        }, 6000);
      } else {
        setSpeed('pause');
        state.paused_reason = 'Winning path coach — review your choice, then press ▶';
      }
      saveGame();
      renderAll();
      if (decisionQueue.length && !startSpeed) showNextDecision();
      return;
    }
    const onboarding = !!activeDecision.onboarding;
    if (onboarding) {
      if (option.effect === 'tutorial_skip') {
        decisionQueue = decisionQueue.filter((d) => !d.tutorial);
        state.onboarding_done = true;
        pushPlayerEvent('skipped tutorial');
        maybeStartWinningPlaybook();
      } else if (option.effect === 'start_tutorial') {
        const steps = buildTutorialSteps(state.scenario_id);
        if (steps.length) {
          state.tutorial_total = steps.length;
          steps.forEach((s) => queueDecision(s));
          pushPlayerEvent('started guided tour');
        }
      } else {
        applyOnboardingChoice(option);
        if (activeDecision.briefing) {
          state.onboarding_done = true;
          pushPlayerEvent('reviewed situation report');
          maybeStartWinningPlaybook();
        } else if (activeDecision.tutorial) {
          pushPlayerEvent(`tutorial step ${activeDecision.tutorialStep || ''}: ${activeDecision.title}`);
          if (activeDecision.tutorialLast || option.effect === 'tutorial_finish') {
            state.onboarding_done = true;
            pushPlayerEvent('finished tutorial — press ▶ when ready');
            maybeStartWinningPlaybook();
          }
        } else {
          state.onboarding_done = true;
          pushPlayerEvent(`starting focus: ${option.label.replace(/^A — |^B — |^C — |^D — /, '')}`);
          maybeStartWinningPlaybook();
        }
      }
    } else {
      if (activeDecision.onResolve) activeDecision.onResolve(option);
      applyDecisionEffect({ ...option, airport: activeDecision.airport });
      pushEvent(activeDecision.logLine || `Decision: ${activeDecision.title} — ${option.label}`);
    }
    activeDecision = null;
    coalescedDecisionCount = 0;
    renderDecisionModal();
    if (decisionQueue.length) {
      state.paused_reason = null;
      showNextDecision();
    } else if (!onboarding) {
      decisionSpeedBeforePause = null;
      setSpeed('slow');
      state.paused_reason = 'Event handled — running at Slow so you can watch the impact';
      // Clear reason after a short beat so the banner does not stick forever.
      setTimeout(() => {
        if (state && state.paused_reason && state.paused_reason.indexOf('Event handled') === 0) {
          state.paused_reason = null;
          renderPauseBanner();
        }
      }, 4500);
    } else {
      setSpeed('pause');
      state.paused_reason = null;
    }
    saveGame();
    renderAll();
  }

  function showNextDecision() {
    if (activeDecision || !decisionQueue.length) return;
    activeDecision = decisionQueue.shift();
    pauseForInterrupt();
    const kind = activeDecision.kind || (activeDecision.winningPlaybook ? 'coach' : activeDecision.onboarding ? 'tour' : 'alert');
    state.paused_reason = activeDecision.winningPlaybook
      ? 'Coach — choose a step, then time stays paused until you press ▶'
      : activeDecision.onboarding
        ? activeDecision.tutorial
          ? `Tutorial step ${activeDecision.tutorialStep || 1} of ${activeDecision.tutorialTotal || '?'}`
          : 'Getting started — pick a first step'
        : kind === 'opportunity'
          ? 'Opportunity — clock paused (will resume at Slow)'
          : 'Alert — clock paused (will resume at Slow)';
    renderDecisionModal();
    renderHud();
    renderPauseBanner();
  }

  function queueDecision(decision) {
    // Chapter 11 / tutorials / playbook must never be collapsed into the log.
    const critical =
      decision.onboarding || decision.tutorial || decision.winningPlaybook || decision.chapter11;
    if (!critical && (activeDecision || decisionQueue.length)) {
      const note = decision.logLine || decision.title || 'Market event';
      pushEvent(`${note} <span class="muted">(logged while you handle another alert)</span>`);
      coalescedDecisionCount += 1;
      renderPauseBanner();
      return;
    }
    if (decision.chapter11) {
      // Front of queue — cash crisis beats market noise.
      decisionQueue.unshift(decision);
    } else {
      decisionQueue.push(decision);
    }
    showNextDecision();
  }

  function renderDecisionModal() {
    const overlay = $('decision-modal');
    if (!overlay) return;
    if (!activeDecision) {
      overlay.classList.remove('active');
      overlay.innerHTML = '';
      clearTutorialHighlight();
      return;
    }
    const opts = activeDecision.options
      .map(
        (o) =>
          `<button type="button" class="decision-opt" data-choice="${o.id}">
            <strong>${o.label}</strong>
            ${o.hint ? `<span>${o.hint}</span>` : ''}
          </button>`
      )
      .join('');
    const kindClass =
      activeDecision.kind === 'opportunity'
        ? ' decision-opportunity'
        : activeDecision.kind === 'threat'
          ? ' decision-threat'
          : '';
    const cardClass =
      activeDecision.onboarding || activeDecision.winningPlaybook
        ? 'decision-card onboarding'
        : `decision-card${kindClass}`;
    const progress =
      activeDecision.tutorial && activeDecision.tutorialTotal
        ? `<div class="tutorial-progress" aria-hidden="true">${Array.from({ length: activeDecision.tutorialTotal }, (_, i) =>
            `<span class="tutorial-dot${i + 1 <= (activeDecision.tutorialStep || 1) ? ' done' : ''}${i + 1 === activeDecision.tutorialStep ? ' current' : ''}"></span>`
          ).join('')}</div>`
        : '';
    overlay.innerHTML = `
      <div class="${cardClass}" role="dialog" aria-modal="true">
        <p class="decision-kicker">${activeDecision.kicker || 'Market intelligence'}</p>
        ${progress}
        <h2>${activeDecision.title}</h2>
        <p class="decision-body">${activeDecision.body}</p>
        ${activeDecision.teach ? `<p class="decision-teach">${activeDecision.teach}</p>` : ''}
        <div class="decision-options">${opts}</div>
      </div>`;
    overlay.classList.add('active');
    overlay.querySelectorAll('[data-choice]').forEach((btn) => {
      btn.addEventListener('click', () => resolveDecision(btn.dataset.choice));
    });
    if (activeDecision.tutorial && activeDecision.highlight) {
      scheduleTutorialHighlight(activeDecision.highlight);
    } else {
      clearTutorialHighlight();
    }
  }

  function bumpCompetitorMarket(iata, airline, patch) {
    if (!state.competitor_markets[iata]) state.competitor_markets[iata] = {};
    const cur = state.competitor_markets[iata][airline] || { fare_index: 1, capacity_index: 1 };
    state.competitor_markets[iata][airline] = { ...cur, ...patch };
  }

  function maybeWindfallEvent() {
    if (!state || state.game_over || activeDecision || decisionQueue.length) return;
    const gap = state.day - (state.last_windfall_event_day || 0);
    if (gap < 45) return;
    if (Math.random() > 0.3) return;

    const invested = investedAirports();
    const roll = Math.random();

    if (roll < 0.5 && invested.length) {
      const iata = invested[Math.floor(Math.random() * invested.length)];
      const ap = airport(iata);
      const incumbents = (ap && ap.incumbents) || [];
      if (incumbents.length) {
        const incumbent = incumbents[Math.floor(Math.random() * Math.min(3, incumbents.length))];
        const pct = 0.08 + Math.random() * 0.1;
        bumpCompetitorMarket(iata, incumbent.airline, { capacity_index: 1 - pct });
        state.last_windfall_event_day = state.day;
        pushEvent(`${incumbent.airline} quietly pulled back capacity at <b>${iata}</b> — an opening for you.`, 'good');
        return;
      }
    }

    const underGate = allGateUtilizations().find((u) => u.underutilized || u.idle);
    if (!underGate) return;
    const idlePlane = (state.fleet || []).find((p) => {
      if (!isPlaneAvailable(p) || planeMonthUtilizationPct(p) >= 60) return false;
      const routesOn = (state.routes || []).filter((r) => r.aircraft_id === p.id);
      if (!routesOn.length) return true;
      return routesOn.some((r) => r.origin === underGate.iata);
    });
    if (idlePlane) {
      const bonus = Math.round(80_000 + Math.random() * 120_000);
      state.cash += bonus;
      state.last_windfall_event_day = state.day;
      pushEvent(
        `Charter contract: spare gate time at <b>${underGate.iata}</b> let you fly a one-off on ${idlePlane.id} — <b>${fmtMoney(bonus)}</b> booked.`,
        'good'
      );
    }
  }

  /**
   * College / sports / event charter opportunity — temporary demand pulse on a market.
   */
  function maybeEventCharterOffer() {
    if (!state || state.game_over || activeDecision || decisionQueue.length) return;
    if (!(state.gates || []).length || !(state.fleet || []).length) return;
    if (Math.random() > 0.55) return;
    const gate = state.gates[Math.floor(Math.random() * state.gates.length)];
    const iata = gate.airport;
    const ap = airport(iata);
    if (!ap) return;
    const destPool = (bootstrap.airports || []).filter(
      (a) => a.iata !== iata && ((a.regional && ap.regional) || Math.random() > 0.4)
    );
    if (!destPool.length) return;
    const dest = destPool[Math.floor(Math.random() * destPool.length)];
    const events = [
      'college football weekend',
      'conference / convention surge',
      'playoff travel',
      'graduation weekend',
      'festival charter demand',
    ];
    const label = events[Math.floor(Math.random() * events.length)];
    queueDecision({
      kicker: `${fmtDate(state.day)} · Event charter`,
      title: `${label} out of ${iata}`,
      body:
        `<p>Local organizers want lift toward <b>${dest.iata} (${dest.city})</b> for a <b>${label}</b>.</p>` +
        `<p class="muted" style="font-size:0.85rem;">You can stand up an <b>Event / charter season</b> product (burst demand, higher yield) or ignore. Uses gate + aircraft like any route.</p>`,
      teach: 'Event product spikes on weekends and every few weeks — great filler metal if you have hours.',
      logLine: `Event charter offer ${iata}–${dest.iata}`,
      options: [
        {
          id: 'event_open',
          label: `A — Open ${iata}–${dest.iata} as Event product`,
          hint: 'Route Studio with Event / charter season pre-selected.',
          effect: 'open_event_route',
          origin: iata,
          dest: dest.iata,
        },
        {
          id: 'event_skip',
          label: 'B — Pass',
          hint: 'Keep metal on core markets.',
          effect: 'none',
        },
      ],
    });
  }

  function maybeCompetitorEvents() {
    if (!state || state.game_over || activeDecision || decisionQueue.length) return;
    const gap = state.day - (state.last_competitor_event_day || 0);
    const agg = competitorAggressionMult();
    const minGap = Math.max(28, Math.round(50 / agg));
    if (gap < minGap) return;
    // Public / PE airlines face more board-visible competitive drama
    const fireChance = Math.min(0.72, 0.42 * agg);
    if (Math.random() > fireChance) return;
    const invested = investedAirports();
    if (!invested.length) return;
    const iata = invested[Math.floor(Math.random() * invested.length)];
    const ap = airport(iata);
    if (!ap || !ap.incumbents || !ap.incumbents.length) return;
    const incumbent = ap.incumbents[Math.floor(Math.random() * Math.min(3, ap.incumbents.length))];
    const roll = Math.random();
    let decision = null;

    if (roll < 0.30) {
      const pct = 0.14 + Math.random() * 0.12;
      bumpCompetitorMarket(iata, incumbent.airline, { fare_index: 1 - pct });
      decision = {
        kind: 'threat',
        airport: iata,
        kicker: `${fmtDate(state.day)} · Fare war · ${ap.city}`,
        title: `${incumbent.airline} undercuts fares at ${iata}`,
        body:
          `${incumbent.airline} dropped fares about <b>${Math.round(pct * 100)}%</b> on overlapping pairs from <b>${iata}</b>. ` +
          `This is a <b>price</b> fight — different from a capacity dump or a demand surge.` +
          competitorImpactHtml({ airport: iata, type: 'fare_cut', airline: incumbent.airline }),
        teach: 'Match tickets, lean on ancillaries, buy demand with ads, or wait. After you choose, the clock resumes at <b>Slow</b>.',
        logLine: `${incumbent.airline} fare war at ${iata} (−${Math.round(pct * 100)}%)`,
        options: fareWarResponseOptions(iata, incumbent.airline, pct),
      };
    } else if (roll < 0.40 && iata === 'CVG') {
      decision = {
        airport: iata,
        kicker: `${fmtDate(state.day)} · Distribution`,
        title: 'Expedia regional spotlight — CVG',
        body: 'Expedia is offering a <b>50% listing-fee discount</b> for three months on CVG regional routes. Competitors on the platform may capture OTA shoppers you are missing.',
        teach: 'OTAs trade margin for reach. Good when you need volume; less ideal if you already sell out with direct marketing.',
        logLine: 'Expedia CVG spotlight offer',
        options: [
          {
            id: 'join',
            label: 'A — Enroll on Expedia (discounted listing 3 mo)',
            hint: '~$14k/mo after discount; +demand via OTA reach.',
            effect: 'ota_promo',
            platform: 'expedia',
            airport: iata,
            months: 3,
            discount: 0.5,
          },
          marketingDecisionOption('market', 'B — Skip OTA · invest', iata, 'ota_alt'),
          {
            id: 'ignore',
            label: 'C — Ignore for now',
            hint: 'No OTA boost; competitors may appear more often in search.',
            effect: 'none',
          },
        ],
      };
    } else if (roll < 0.52) {
      const pct = 0.1 + Math.random() * 0.08;
      bumpCompetitorMarket(iata, incumbent.airline, { capacity_index: 1 + pct });
      decision = {
        kind: 'threat',
        airport: iata,
        kicker: `${fmtDate(state.day)} · Capacity dump · ${ap.city}`,
        title: `${incumbent.airline} floods ${iata} with seats`,
        body:
          `${incumbent.airline} added about <b>+${Math.round(pct * 100)}% capacity</b> from ${iata}. ` +
          `This is a <b>supply</b> shock (more seats), not a pure fare cut — you can price, advertise, or match frequency.` +
          competitorImpactHtml({ airport: iata, type: 'capacity', airline: incumbent.airline }),
        teach: 'Capacity wars burn cash if you only match seats. Fares and ancillaries often defend better. Resumes at Slow.',
        logLine: `${incumbent.airline} capacity increase at ${iata}`,
        options: capacityPressureOptions(iata, incumbent.airline, pct),
      };
    } else if (roll < 0.72) {
      const pct = 0.08 + Math.random() * 0.12;
      bumpCompetitorMarket(iata, incumbent.airline, { capacity_index: Math.max(0.72, 1 - pct) });
      pushEvent(
        `${incumbent.airline} quietly <b>reduced capacity</b> at <b>${iata}</b> (−${Math.round(pct * 100)}%) — less competition on your routes.`,
        'good'
      );
      decision = {
        kind: 'opportunity',
        airport: iata,
        kicker: `${fmtDate(state.day)} · Competitor retreat · ${ap.city}`,
        title: `${incumbent.airline} pulls flights at ${iata}`,
        body:
          `${incumbent.airline} cut schedules at <b>${iata}</b> by about <b>${Math.round(pct * 100)}%</b>. ` +
          `This is an <b>opening</b> — you can raise price, add frequency, advertise, or pocket the free lift.` +
          competitorImpactHtml({ airport: iata, type: 'pullback', airline: incumbent.airline }),
        teach: 'Unlike a fare war, the market just got easier. Resumes at Slow so you can watch loads.',
        logLine: `${incumbent.airline} capacity pullback at ${iata}`,
        options: opportunityResponseOptions(iata, 'pullback'),
      };
    } else if (roll < 0.86) {
      const mult = 1.1 + Math.random() * 0.08;
      if (!state.airport_demand_surges) state.airport_demand_surges = {};
      state.airport_demand_surges[iata] = { days_left: 45, mult };
      pushEvent(
        `<b>Travel demand surge</b> at <b>${iata}</b> — conventions &amp; corporate travel up <b>+${Math.round((mult - 1) * 100)}%</b> for ~45 days.`,
        'good'
      );
      decision = {
        kind: 'opportunity',
        airport: iata,
        kicker: `${fmtDate(state.day)} · Demand surge · ${ap.city}`,
        title: `Travel boom at ${iata} (~45 days)`,
        body:
          `Demand at <b>${iata}</b> is up <b>+${Math.round((mult - 1) * 100)}%</b> for ~45 days (already active). ` +
          `This is a <b>demand</b> spike — not a competitor move. Harvest fares, add seats, or advertise into the heat.` +
          competitorImpactHtml({ airport: iata, type: 'demand_surge', airline: incumbent.airline }),
        teach: 'Surge is already on. Your choice is how to exploit it. Clock resumes at Slow.',
        logLine: `Travel demand surge at ${iata}`,
        options: opportunityResponseOptions(iata, 'surge'),
      };
    } else {
      const pct = 0.06 + Math.random() * 0.1;
      bumpCompetitorMarket(iata, incumbent.airline, { fare_index: 1 + pct });
      pushEvent(
        `${incumbent.airline} is <b>raising fares</b> at <b>${iata}</b> (+${Math.round(pct * 100)}%) — less fare pressure on your routes.`,
        'good'
      );
      decision = {
        kind: 'opportunity',
        airport: iata,
        kicker: `${fmtDate(state.day)} · Pricing room · ${ap.city}`,
        title: `${incumbent.airline} raises fares at ${iata}`,
        body:
          `${incumbent.airline} raised fares about <b>${Math.round(pct * 100)}%</b> at <b>${iata}</b>. ` +
          `Shoppers feel less pressure — room to raise, hold for reputation, advertise, or add frequency.` +
          competitorImpactHtml({ airport: iata, type: 'fare_rise', airline: incumbent.airline }),
        teach: 'Different from a capacity pullback: the fight is on price, and they just stepped up. Resumes at Slow.',
        logLine: `${incumbent.airline} fare increase at ${iata}`,
        options: opportunityResponseOptions(iata, 'fare_rise'),
      };
    }

    if (decision) {
      state.last_competitor_event_day = state.day;
      queueDecision(decision);
    }
  }

  function routeTimingDemandFactor(route) {
    const dow = state.day % 7;
    const o = airport(route.origin);
    const d = airport(route.dest);
    if (!o || !d) return { mult: 1, reason: 'Steady demand' };
    const leisure = (airportLuxury(o) + airportLuxury(d)) / 2;
    let dowMult = 1;
    let reason = 'Steady demand';
    if (dow === 5 || dow === 6) {
      dowMult = 1 + leisure * 0.14 + 0.05;
      reason = 'Weekend travel premium';
    } else if (dow === 0) {
      dowMult = 1 + leisure * 0.1 + 0.03;
      reason = 'Sunday return demand';
    } else if (dow === 1 || dow === 2) {
      dowMult = 1 - leisure * 0.08 - 0.03;
      reason = 'Mid-week softness';
    }
    const yearDay = state.day % 365;
    let seasonMult = 1;
    if (yearDay >= 140 && yearDay <= 260) {
      seasonMult = 1.06;
      reason = 'Summer peak';
    } else if (yearDay >= 300 || yearDay <= 18) {
      seasonMult = 1.04;
      reason = 'Holiday season';
    } else if (yearDay >= 45 && yearDay <= 90) {
      seasonMult = 0.97;
      reason = 'Post-holiday lull';
    }
    const surge = Math.max(airportDemandSurgeMult(route.origin), airportDemandSurgeMult(route.dest));
    if (surge > 1.02) reason = 'Local demand surge';
    return { mult: dowMult * seasonMult * surge, reason };
  }

  function computeRevenueManagementTarget(route) {
    const o = airport(route.origin);
    const d = airport(route.dest);
    const market = marketFareForPair(route.origin, route.dest, route.aircraft_type);
    const timing = routeTimingDemandFactor(route);
    const todaySim = simulateRouteDay(route);
    const actual = routeActualStats(route);
    const avgLoad = actual ? actual.avgLoad : todaySim.load;
    const recentLoad = todaySim.grounded ? avgLoad : todaySim.load;
    const loadTrend = recentLoad - avgLoad;
    const compAdj = 1 - ((competitorFarePressure(o) + competitorFarePressure(d)) / 2) * 0.18;
    const macroAdj = 0.96 + Math.min(0.1, (macroDemandMultiplier() - 1) * 0.35);

    let target = market * timing.mult * compAdj * macroAdj;

    if (avgLoad >= 0.84 || recentLoad >= 0.9) target *= 1.14;
    else if (avgLoad >= 0.72) target *= 1.07;
    else if (avgLoad >= 0.58) target *= 1.02;
    else if (avgLoad < 0.38) target *= 0.86;
    else if (avgLoad < 0.5) target *= 0.92;

    if (loadTrend > 0.1) target *= 1.05;
    else if (loadTrend < -0.1) target *= 0.94;

    const floor = Math.max(49, Math.round(market * 0.62));
    const ceiling = Math.min(899, Math.round(market * 1.45));
    target = Math.max(floor, Math.min(ceiling, Math.round(target)));

    let reason = timing.reason;
    if (avgLoad >= 0.72) reason = `Strong loads (${Math.round(avgLoad * 100)}%)`;
    else if (avgLoad < 0.45) reason = `Weak loads (${Math.round(avgLoad * 100)}%)`;
    if (loadTrend > 0.1) reason += ' · demand rising';
    else if (loadTrend < -0.1) reason += ' · demand fading';

    return { target, market, floor, ceiling, timing, avgLoad, recentLoad, reason };
  }

  function updateDynamicFares() {
    if (!state || !state.routes.length) return;
    state.routes.forEach((route) => {
      if (route.fare_mode === 'manual') return;
      const rm = computeRevenueManagementTarget(route);
      route.market_fare = rm.market;
      const prev = route.fare || rm.market;
      const maxStep = Math.max(6, Math.round(prev * 0.09));
      let next = prev;
      if (prev < rm.target - 2) next = Math.min(rm.target, prev + maxStep);
      else if (prev > rm.target + 2) next = Math.max(rm.target, prev - maxStep);
      else next = rm.target;
      next = Math.max(rm.floor, Math.min(rm.ceiling, next));
      const delta = next - prev;
      if (Math.abs(delta) < 2) return;
      route.fare = next;
      route.fare_rm = {
        last_day: state.day,
        delta,
        target: rm.target,
        floor: rm.floor,
        ceiling: rm.ceiling,
        timing_mult: rm.timing.mult,
        reason: rm.reason,
        avg_load: rm.avgLoad,
      };
      if (Math.abs(delta) >= Math.max(8, prev * 0.06)) {
        pushEvent(
          `<b>${route.origin}–${route.dest}</b> dynamic fare ${delta > 0 ? '↑' : '↓'} to <b>$${next}</b> — ${rm.reason}.`,
          delta > 0 ? 'good' : 'warn'
        );
      }
    });
    saveGame();
  }

  function fareRmHintHtml(route) {
    if (route.fare_mode === 'manual') return '';
    const rm = route.fare_rm;
    const market = route.market_fare || marketFareForPair(route.origin, route.dest, route.aircraft_type);
    const buckets = routeFareBuckets(route);
    const low = buckets[0].fare;
    const high = buckets[buckets.length - 1].fare;
    let line = `Selling <b>$${low}–$${high}</b> (basic→flex) · mkt $${market}`;
    if (rm && rm.last_day != null) {
      const arrow = rm.delta > 0 ? '↑' : rm.delta < 0 ? '↓' : '→';
      const deltaTxt = rm.delta ? ` · ${arrow}$${Math.abs(rm.delta)} this week` : '';
      line += ` · ${rm.reason || 'RM'}${deltaTxt}`;
    }
    return `<p class="route-fare-rm muted" style="font-size:0.66rem;margin:4px 0 0;">${line}</p>`;
  }

  function setRouteFare(routeId, fare, mode) {
    const route = state.routes.find((r) => r.id === routeId);
    if (!route) return;
    route.fare = Math.max(49, Math.min(899, Math.round(fare)));
    route.fare_mode = mode || 'manual';
    if (route.fare_mode === 'manual') route.fare_rm = null;
    saveGame();
    renderRoutes();
    renderHud();
  }

  function setRouteFareMode(routeId, mode) {
    const route = state.routes.find((r) => r.id === routeId);
    if (!route) return;
    if (mode === 'auto') {
      route.fare_mode = 'auto';
      const rm = computeRevenueManagementTarget(route);
      route.fare = rm.target;
      route.market_fare = rm.market;
      route.fare_rm = {
        last_day: state.day,
        delta: 0,
        target: rm.target,
        floor: rm.floor,
        ceiling: rm.ceiling,
        reason: 'Dynamic pricing enabled',
        avg_load: rm.avgLoad,
      };
      pushPlayerEvent(`${route.origin}–${route.dest}: switched to dynamic fares (target $${rm.target}).`);
    } else {
      route.fare_mode = 'manual';
      route.fare_rm = null;
      pushPlayerEvent(`${route.origin}–${route.dest}: fixed fare at $${route.fare}.`);
    }
    saveGame();
    renderRoutes();
    renderHud();
  }

  function setRouteAncillary(routeId, mode) {
    const route = state.routes.find((r) => r.id === routeId);
    if (!route) return;
    route.ancillary_mode = mode || 'auto';
    pushPlayerEvent(
      `${route.origin}–${route.dest}: ancillary package → ${mode === 'aggressive' ? 'heavy' : mode === 'minimal' ? 'minimal' : 'auto'}.`
    );
    saveGame();
    renderRoutes();
  }

  /**
   * Set absolute weekly frequency (mirrors return leg by default).
   * delta helpers call this via adjustRouteFrequency.
   */
  function setRouteFrequency(routeId, newFreq, opts) {
    opts = opts || {};
    const mirrorReturn = opts.mirrorReturn !== false;
    const quiet = !!opts.quiet;
    const route = routeById(routeId);
    if (!route) return false;
    const target = Math.max(1, Math.min(28, Math.round(+newFreq || 1)));
    const before = route.frequency_week || 0;
    if (target === before) return true;

    if (target > before) {
      return bumpRouteFrequency(routeId, target - before, opts);
    }

    // Decrease
    const routeMax = maxFrequencyForRoute(route.origin, route.dest, route.aircraft_type);
    const capped = Math.min(target, routeMax);
    if (capped >= before) return false;
    route.frequency_week = capped;
    const actualCut = before - capped;
    if (!quiet) {
      pushPlayerEvent(
        `reduced ${route.origin}–${route.dest} to ${capped}x/wk (−${actualCut}) — fewer seats, lower gate use at ${route.origin}.`
      );
    }
    if (mirrorReturn && actualCut > 0) {
      const reverse = findReverseRoute(route);
      if (reverse) {
        const revTarget = Math.max(1, (reverse.frequency_week || 0) - actualCut);
        setRouteFrequency(reverse.id, revTarget, { mirrorReturn: false, quiet: true });
        if (!quiet) {
          pushPlayerEvent(
            `matched return ${reverse.origin}–${reverse.dest} −${actualCut}/wk — keep both legs balanced.`
          );
        }
      }
    }
    if (!quiet) {
      saveGame();
      renderRoutes();
      if (selectedAirport === route.origin || selectedAirport === route.dest) {
        renderAirportPanel(selectedAirport);
      }
      renderOpsGuide();
      renderHud();
    }
    return true;
  }

  function adjustRouteFrequency(routeId, delta) {
    const route = routeById(routeId);
    if (!route || !delta) return false;
    const next = Math.max(1, (route.frequency_week || 0) + Math.round(delta));
    return setRouteFrequency(routeId, next);
  }

  function setRouteAircraft(routeId, aircraftId) {
    const route = routeById(routeId);
    if (!route || !aircraftId) return false;
    const plane = state.fleet.find((f) => f.id === aircraftId);
    if (!plane) {
      alert('Aircraft not in fleet.');
      return false;
    }
    if (plane.id === route.aircraft_id) return true;
    const ac = aircraftType(plane.type);
    const oAp = airport(route.origin);
    const dAp = airport(route.dest);
    if (oAp && dAp && ac) {
      const dist = haversineNm(oAp.lat, oAp.lon, dAp.lat, dAp.lon);
      if (dist > (ac.range_nm || 0)) {
        alert(`${ac.name} cannot fly ${route.origin}–${route.dest} (${Math.round(dist)} nm exceeds range).`);
        return false;
      }
    }
    const schedErr = aircraftScheduleError(
      plane.id,
      route.origin,
      route.dest,
      route.frequency_week || 7,
      plane.type,
      route.id
    );
    if (schedErr) {
      alert(schedErr);
      return false;
    }
    const prevType = route.aircraft_type;
    route.aircraft_id = plane.id;
    route.aircraft_type = plane.type;
    // Keep fare roughly market-aligned if still on auto
    if (route.fare_mode === 'auto') {
      route.fare = marketFareForPair(route.origin, route.dest, plane.type);
      route.market_fare = route.fare;
    }
    pushPlayerEvent(
      `reassigned ${route.origin}–${route.dest} to ${ac ? ac.name : plane.type}` +
        (prevType !== plane.type ? ` (was ${prevType})` : '') +
        ` — ${fleetSeatCount(plane)} seats, different unit economics.`
    );
    saveGame();
    renderRoutes();
    renderHud();
    renderFleet();
    return true;
  }

  function boostRouteMarketing(routeId, amount) {
    const route = routeById(routeId);
    if (!route) return false;
    const add = Math.max(1000, Math.round(+amount || 3000));
    applyMarketingSpend({
      airport: route.origin,
      amount: add,
      setAmount: false,
    });
    return true;
  }

  function resetRouteFare(routeId) {
    const route = state.routes.find((r) => r.id === routeId);
    if (!route) return;
    route.fare = marketFareForPair(route.origin, route.dest, route.aircraft_type);
    route.fare_mode = 'auto';
    saveGame();
    renderRoutes();
  }

  function computeNetWorthBreakdown() {
    if (!state) return null;
    const b = {
      cash: state.cash || 0,
      fleet: 0,
      gates: 0,
      brand: 0,
      routes: 0,
      debt: 0,
      bonds: 0,
      lease_liabilities: 0,
    };
    state.fleet.forEach((f) => {
      if (f.leased) {
        const ac = aircraftType(f.type);
        if (ac) b.lease_liabilities += (ac.lease_monthly || 0) * (f.lease_months_left || 36) * 0.4;
      } else {
        const ac = aircraftType(f.type);
        if (ac) {
          const lifeTotal = (ac.lifespan_years || 25) * 12;
          const lifeLeft = f.life_months_left != null ? f.life_months_left : lifeTotal;
          b.fleet += ac.purchase * Math.max(0, lifeLeft / lifeTotal) * 0.55;
        }
      }
    });
    state.gates.forEach((g) => {
      const months = g.months_left != null ? g.months_left : (g.years_left || 0) * 12;
      b.gates += (g.monthly || 0) * months * 0.35;
    });
    b.brand = Object.values(state.brand_awareness || {}).reduce((s, v) => s + v * 25_000, 0);
    const ltm = state.ltm_revenue || 0;
    const margin =
      ltm > 0 ? Math.min(1.2, Math.max(0.15, ((state.daily_pnl || 0) * 365) / ltm)) : 0.25;
    b.routes = ltm * margin * 0.45;
    b.debt = state.debt.reduce((s, d) => s + (d.principal || 0), 0);
    b.bonds = state.bonds.reduce((s, x) => s + (x.principal || 0), 0);
    b.total =
      b.cash + b.fleet + b.gates + b.brand + b.routes - b.debt - b.bonds - b.lease_liabilities;
    b.equity_value = b.total * ((state.equity_pct || 100) / 100);
    return b;
  }

  function computeNetWorth() {
    const b = computeNetWorthBreakdown();
    return b ? b.total : 0;
  }

  function computePersonalNetWorth() {
    const b = computeNetWorthBreakdown();
    return b ? b.equity_value : 0;
  }

  function pushPlayerEvent(msg) {
    const who = (state && state.player_name) || 'CEO';
    pushEvent(`${who} — ${msg}`);
  }

  function newGame(scenarioId, airlineName, playerName) {
    applyScenarioAirports(scenarioId);
    applyScenarioMap(scenarioId);
    const base = cloneScenario(scenarioId);
    state = {
      scenario_id: scenarioId,
      player_name: playerName || base.player_name || 'CEO',
      airline_name: airlineName || base.airline_name,
      day: 0,
      hour: 8,
      speed: 'pause',
      cash: base.cash,
      debt: base.debt,
      bonds: base.bonds,
      equity_pct: base.equity_pct,
      reputation: base.reputation,
      brand_awareness: base.brand_awareness,
      financing_tier: base.financing_tier,
      bond_rating: base.bond_rating || 'B',
      fleet: base.fleet,
      gates: base.gates,
      routes: base.routes,
      fuel_price: bootstrap.fuel_base,
      macro: createMacroState(),
      marketing_spend_monthly: { ...(base.marketing_spend_monthly || {}) },
      ltm_revenue: 0,
      revenue_history: [],
      daily_pnl: 0,
      events: [],
      milestones: [],
      starter_route_count: (base.routes || []).length,
      positive_day_streak: 0,
      ff_month_confirmed: false,
      game_over: false,
      paused_reason: null,
      onboarding_done: false,
      airline_emblem: pendingEmblem || 'wing',
      ancillary_strategy: pendingAncillaryStrategy || 'auto',
      personal_cash: 0,
      seed_done: false,
      series_a_done: false,
      growth_equity_done: false,
      pe_done: false,
      ipo_done: false,
      public: false,
      raises: [],
      debt_month: null,
      ops_goals_done: [],
    };
    sanitizeMarketingSpend();
    normalizeGameState();
    if (isWinningTrackScenario(scenarioId)) ensureWinningPlaybook();
    ensureMetrics();
    state.metrics.league_scope = defaultLeagueScope();
    state.metrics.league_snapshot = buildLeagueTable(state.metrics.league_scope);
    initCompetitorMarkets();
    initCompetitorRoutes();
    resetMapView();
    pushEvent(`${state.player_name} founded ${state.airline_name} — ${base.name}`);
    saveGame();
    renderAll();
  }

  function clampMoney(n) {
    const v = Number(n);
    return Math.max(0, Number.isFinite(v) ? v : 0);
  }

  function sanitizeMarketingSpend() {
    if (!state || !state.marketing_spend_monthly) return;
    Object.keys(state.marketing_spend_monthly).forEach((k) => {
      state.marketing_spend_monthly[k] = clampMoney(state.marketing_spend_monthly[k]);
    });
  }

  function clampPct(n, min, max) {
    const v = Number(n);
    if (!Number.isFinite(v)) return min;
    return Math.min(max, Math.max(min, v));
  }

  function createMacroState() {
    const base = bootstrap.macro_usa_base || {};
    const listed = {};
    (bootstrap.ota_platforms || []).forEach((p) => {
      listed[p.id] = false;
    });
    return {
      country: base.country || 'United States',
      inflation_pct: base.inflation_pct ?? 2.4,
      gdp_growth_pct: base.gdp_growth_pct ?? 2.1,
      gdp_index: base.gdp_index ?? 100,
      travel_spend_index: base.travel_spend_index ?? 100,
      travel_spend_growth_pct: base.travel_spend_growth_pct ?? 2.5,
      country_health: base.country_health ?? 72,
      ota_market_penetration_pct: base.ota_market_penetration_pct ?? 74,
      ota_listed: listed,
      ota_promo: {},
    };
  }

  function ensureMacro() {
    if (!state) return;
    if (!state.macro) state.macro = createMacroState();
    if (!state.macro.ota_listed) {
      state.macro.ota_listed = {};
      (bootstrap.ota_platforms || []).forEach((p) => {
        state.macro.ota_listed[p.id] = false;
      });
    }
    if (!state.macro.ota_promo) state.macro.ota_promo = {};
    if (state.macro) {
      state.macro.country_health = computeCountryHealth();
    }
  }

  function sanitizeAirportGateCounts() {
    if (!bootstrap || !bootstrap.airports) return;
    bootstrap.airports.forEach((ap) => {
      let total = Math.max(1, parseInt(ap.gates_total, 10) || 1);
      let avail = Math.max(0, parseInt(ap.gates_available, 10) || 0);
      if (avail > total) {
        const swap = total;
        total = avail;
        avail = swap;
      }
      avail = Math.min(avail, total);
      ap.gates_total = total;
      ap.gates_available = avail;
    });
  }

  function airlineProfile(name) {
    return (bootstrap.airline_profiles && bootstrap.airline_profiles[name]) || null;
  }

  function incumbentAirportImportance(ap, incumbent) {
    if (!ap || !incumbent) return 0;
    const paxWeight = Math.min(1, ap.annual_pax_m / 12);
    return incumbent.share * paxWeight;
  }

  function formatIncumbentIntel(ap, incumbent) {
    const prof = airlineProfile(incumbent.airline);
    const importance = incumbentAirportImportance(ap, incumbent);
    const impPct = (importance * 100).toFixed(0);
    if (!prof) {
      return `<span class="muted">~${impPct}% network weight here</span>`;
    }
    const health = (prof.financial_health * 100).toFixed(0);
    const sens = (prof.route_sensitivity * 100).toFixed(0);
    let pain = 'moderate';
    if (importance >= 0.12 && prof.financial_health < 0.55) pain = 'high — route losses hurt';
    else if (importance >= 0.08 && prof.route_sensitivity >= 0.8) pain = 'high — thin margins';
    else if (importance < 0.04) pain = 'low — airport is minor for them';
    else if (prof.financial_health >= 0.75) pain = 'low — can absorb a fare war';
    return `<span class="muted">Health ${health}% · This airport ~${impPct}% of their focus · ${pain}</span>`;
  }

  function planeSeatLoadToday(planeId) {
    const routes = (state.routes || []).filter((r) => r.aircraft_id === planeId);
    if (!routes.length) return null;
    let sum = 0;
    let n = 0;
    routes.forEach((route) => {
      const r = simulateRouteDay(route);
      if (!r.grounded && Number.isFinite(r.load)) {
        sum += r.load;
        n += 1;
      }
    });
    return n ? sum / n : null;
  }

  function networkRouteStats() {
    if (!state || !state.routes.length) {
      return { count: 0, profitable: 0, dailyPnl: 0, avgLoad: 0, canceled: 0, ferry: 0 };
    }
    let profitable = 0;
    let dailyPnl = 0;
    let loadSum = 0;
    let loadN = 0;
    let canceled = 0;
    let ferry = 0;
    state.routes.forEach((route) => {
      const r = simulateRouteDay(route);
      const pnl = r.revenue - r.cost;
      dailyPnl += pnl;
      if (pnl > 0) profitable += 1;
      if (r.canceled) canceled += 1;
      if (r.ferryReturn && !r.canceled && r.flightsToday > 0) ferry += 1;
      // Use projected load even when canceled (HUD must not flash 0% overnight).
      if (!r.grounded && Number.isFinite(r.load)) {
        loadSum += r.load;
        loadN += 1;
      }
    });
    return {
      count: state.routes.length,
      profitable,
      dailyPnl,
      avgLoad: loadN ? loadSum / loadN : 0,
      canceled,
      ferry,
    };
  }

  function hashHue(str) {
    let h = 0;
    const s = String(str || 'Airline');
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    return h % 360;
  }

  function emblemOption(id) {
    const opts = bootstrap.emblem_options || [];
    return opts.find((o) => o.id === id) || opts[0] || null;
  }

  function emblemGlyph(id) {
    const hit = emblemOption(id);
    return hit ? hit.glyph : '✈';
  }

  let emblemSvgSeq = 0;

  /** Unique SVG player emblem marks — visual only (no names in UI). */
  function emblemSvgMarkup(mark, colors, size) {
    const c = colors || ['#00c896', '#1e3a5f', '#ffd166'];
    const a = c[0] || '#00c896';
    const b = c[1] || '#1e3a5f';
    const d = c[2] || '#ffd166';
    const s = size || 36;
    emblemSvgSeq += 1;
    const uid = `em${emblemSvgSeq}`;
    const common = `xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40" width="${s}" height="${s}" aria-hidden="true"`;
    const bg = `<defs>
      <linearGradient id="${uid}-bg" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="${b}"/>
        <stop offset="100%" stop-color="${shadeHex(b, -18)}"/>
      </linearGradient>
      <linearGradient id="${uid}-fg" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${a}"/>
        <stop offset="100%" stop-color="${shadeHex(a, -12)}"/>
      </linearGradient>
      <radialGradient id="${uid}-glow" cx="30%" cy="25%" r="70%">
        <stop offset="0%" stop-color="rgba(255,255,255,0.18)"/>
        <stop offset="100%" stop-color="rgba(255,255,255,0)"/>
      </radialGradient>
    </defs>
    <rect width="40" height="40" rx="10" fill="url(#${uid}-bg)"/>
    <rect width="40" height="40" rx="10" fill="url(#${uid}-glow)"/>`;
    switch (mark) {
      case 'routes':
        return `<svg ${common}>${bg}
          <circle cx="11" cy="12" r="3.4" fill="${a}"/>
          <circle cx="29" cy="11" r="2.8" fill="${d}"/>
          <circle cx="27" cy="27" r="3.6" fill="url(#${uid}-fg)"/>
          <circle cx="13" cy="28" r="2.6" fill="${d}"/>
          <path d="M13.2 14.2 C18 12, 22 11.2, 26.5 12.2" stroke="${a}" stroke-width="1.7" fill="none" stroke-linecap="round"/>
          <path d="M14.2 25.8 C18.5 22, 22 20, 25.2 24.2" stroke="${d}" stroke-width="1.5" fill="none" stroke-linecap="round" opacity="0.9"/>
          <path d="M12.5 15.5 L13.2 25" stroke="${a}" stroke-width="1.4" fill="none" opacity="0.75"/>
        </svg>`;
      case 'wing':
        return `<svg ${common}>${bg}
          <path d="M5 25 C12 9, 22 6, 36 11 L29 16.5 C23 14, 16 16.5, 11 23.5 Z" fill="url(#${uid}-fg)"/>
          <path d="M9 27 L31 17.5" stroke="${d}" stroke-width="1.6" opacity="0.75" stroke-linecap="round"/>
          <circle cx="31" cy="16.5" r="2.3" fill="${d}"/>
          <path d="M14 28 C20 24, 26 22, 33 21" stroke="rgba(255,255,255,0.25)" stroke-width="1.2" fill="none"/>
        </svg>`;
      case 'compass':
        return `<svg ${common}>${bg}
          <circle cx="20" cy="20" r="12.5" fill="none" stroke="${a}" stroke-width="1.5" opacity="0.85"/>
          <circle cx="20" cy="20" r="9.5" fill="none" stroke="${d}" stroke-width="0.9" opacity="0.45"/>
          <path d="M20 7.5 L23.4 20 L20 32.5 L16.6 20 Z" fill="${d}"/>
          <path d="M7.5 20 L20 16.6 L32.5 20 L20 23.4 Z" fill="url(#${uid}-fg)" opacity="0.92"/>
          <circle cx="20" cy="20" r="2.4" fill="#fff"/>
          <circle cx="20" cy="20" r="1.1" fill="${b}"/>
        </svg>`;
      case 'star':
        return `<svg ${common}>${bg}
          <path d="M20 5.5 L23.5 15.2 L33.5 15.6 L25.5 21.6 L28.4 31.4 L20 25.8 L11.6 31.4 L14.5 21.6 L6.5 15.6 L16.5 15.2 Z" fill="url(#${uid}-fg)"/>
          <circle cx="20" cy="20" r="2.4" fill="${d}"/>
          <circle cx="20" cy="7.2" r="1.1" fill="${d}" opacity="0.7"/>
        </svg>`;
      case 'bolt':
        return `<svg ${common}>${bg}
          <path d="M23 5.5 L11.5 21.5 H19 L15.5 34.5 L32 15.5 H24.5 Z" fill="url(#${uid}-fg)"/>
          <path d="M7 29 Q20 24.5 33 31" stroke="${d}" stroke-width="1.5" fill="none" opacity="0.8" stroke-linecap="round"/>
        </svg>`;
      case 'globe':
        return `<svg ${common}>${bg}
          <circle cx="20" cy="20" r="12.5" fill="none" stroke="url(#${uid}-fg)" stroke-width="2"/>
          <ellipse cx="20" cy="20" rx="6.2" ry="12.5" fill="none" stroke="${d}" stroke-width="1.25"/>
          <path d="M8 20 H32" stroke="${a}" stroke-width="1.1" opacity="0.8"/>
          <path d="M11 13 H29 M11 27 H29" stroke="${a}" stroke-width="0.9" opacity="0.55"/>
          <circle cx="20" cy="20" r="1.6" fill="${d}"/>
        </svg>`;
      case 'stripe':
        return `<svg ${common}>${bg}
          <path d="M7 11 H33" stroke="${a}" stroke-width="4.2" stroke-linecap="round"/>
          <path d="M7 20 H33" stroke="${d}" stroke-width="4.2" stroke-linecap="round"/>
          <path d="M7 29 H33" stroke="${a}" stroke-width="4.2" stroke-linecap="round" opacity="0.72"/>
          <path d="M8 11 L32 29" stroke="rgba(255,255,255,0.12)" stroke-width="2"/>
        </svg>`;
      case 'talon':
        return `<svg ${common}>${bg}
          <path d="M9 29 L20 6.5 L25 18 L32 9.5 L29.5 31.5 L17.5 24.5 Z" fill="url(#${uid}-fg)"/>
          <path d="M13 31 L23 21.5" stroke="${d}" stroke-width="1.8" stroke-linecap="round"/>
          <path d="M18 30 L26 24" stroke="${d}" stroke-width="1.2" opacity="0.65" stroke-linecap="round"/>
        </svg>`;
      case 'contrail':
        return `<svg ${common}>${bg}
          <path d="M5 29 C14 26.5, 18 18, 23 13.5 L35 9" stroke="url(#${uid}-fg)" stroke-width="2.4" fill="none" stroke-linecap="round"/>
          <path d="M5.5 31.5 C16 28.5, 20.5 22, 27 16" stroke="${d}" stroke-width="1.3" fill="none" opacity="0.65" stroke-linecap="round"/>
          <path d="M28.5 11.5 L35.5 9 L31 16.5 Z" fill="${a}"/>
          <circle cx="12" cy="27.5" r="1.2" fill="${d}" opacity="0.5"/>
        </svg>`;
      default:
        return `<svg ${common}>${bg}
          <path d="M12 24 C16 12, 24 10, 30 14 L26 17 C22 15, 18 16, 15 22 Z" fill="url(#${uid}-fg)"/>
          <circle cx="28" cy="16" r="2" fill="${d}"/>
        </svg>`;
    }
  }

  /** Darken/lighten a #rrggbb hex by amount (-255..255). */
  function shadeHex(hex, amount) {
    const h = String(hex || '#1e3a5f').replace('#', '');
    if (h.length !== 6) return hex || '#1e3a5f';
    const n = (i) => Math.max(0, Math.min(255, parseInt(h.slice(i, i + 2), 16) + amount));
    const to = (v) => v.toString(16).padStart(2, '0');
    return `#${to(n(0))}${to(n(2))}${to(n(4))}`;
  }

  /** Stylized competitor brand marks (colors match real airline identities). */
  function competitorBrandSvg(name, brand, size) {
    const s = size || 36;
    const p = (brand && brand.primary) || '#1e3a5f';
    const sec = (brand && brand.secondary) || '#00c896';
    const acc = (brand && brand.accent) || '#ffffff';
    const code = (brand && brand.code) || String(name || '?').slice(0, 2).toUpperCase();
    const mark = (brand && brand.mark) || 'generic';
    const common = `xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40" width="${s}" height="${s}" aria-hidden="true"`;
    switch (mark) {
      case 'delta':
        // Red widget triangle on deep blue — Delta-inspired
        return `<svg ${common}><rect width="40" height="40" rx="9" fill="${p}"/><path d="M20 7 L33 31 H7 Z" fill="${sec}"/><path d="M20 14 L27 28 H13 Z" fill="${p}"/></svg>`;
      case 'american':
        // AA + red/blue bar — American-inspired
        return `<svg ${common}><rect width="40" height="40" rx="9" fill="${p}"/><path d="M8 28 L14 10 H18 L12 28 Z" fill="${acc}"/><path d="M22 10 L28 28 H24 L21 18 L18 28 H14 L20 10 Z" fill="${acc}"/><rect x="6" y="31" width="28" height="3" fill="${sec}"/></svg>`;
      case 'united':
        // Globe ring + gold arc — United-inspired
        return `<svg ${common}><rect width="40" height="40" rx="9" fill="${p}"/><circle cx="20" cy="20" r="11" fill="none" stroke="${acc}" stroke-width="1.6"/><ellipse cx="20" cy="20" rx="5" ry="11" fill="none" stroke="${acc}" stroke-width="1.1"/><path d="M9 20 H31" stroke="${acc}" stroke-width="1"/><path d="M8 14 Q20 8 32 14" stroke="${sec}" stroke-width="2.2" fill="none" stroke-linecap="round"/></svg>`;
      case 'southwest':
        // Heart-ish blue with gold/red accents — Southwest-inspired
        return `<svg ${common}><rect width="40" height="40" rx="9" fill="${p}"/><path d="M20 30 C12 24, 10 18, 14 14 C16 12, 19 13, 20 16 C21 13, 24 12, 26 14 C30 18, 28 24, 20 30 Z" fill="${acc}"/><circle cx="14" cy="32" r="2" fill="${sec}"/><circle cx="20" cy="33" r="2" fill="#E31837"/><circle cx="26" cy="32" r="2" fill="${sec}"/></svg>`;
      case 'allegiant':
        // Sun disc on navy — Allegiant-inspired
        return `<svg ${common}><rect width="40" height="40" rx="9" fill="${p}"/><circle cx="20" cy="20" r="9" fill="${sec}"/><circle cx="20" cy="20" r="4.5" fill="${p}"/><g stroke="${sec}" stroke-width="1.6">${[0, 45, 90, 135]
          .map((deg) => {
            const r = (deg * Math.PI) / 180;
            const x1 = 20 + Math.cos(r) * 11;
            const y1 = 20 + Math.sin(r) * 11;
            const x2 = 20 + Math.cos(r) * 15;
            const y2 = 20 + Math.sin(r) * 15;
            return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>`;
          })
          .join('')}</g></svg>`;
      case 'frontier':
        // Green leaf/animal silhouette cue — Frontier-inspired
        return `<svg ${common}><rect width="40" height="40" rx="9" fill="${p}"/><ellipse cx="20" cy="22" rx="11" ry="9" fill="${sec}"/><circle cx="15" cy="14" r="4" fill="${sec}"/><circle cx="16.5" cy="13.5" r="1.1" fill="${p}"/><path d="M28 18 Q34 22 30 28" stroke="${acc}" stroke-width="1.5" fill="none"/></svg>`;
      case 'spirit':
        // Yellow on deep purple — Spirit-inspired
        return `<svg ${common}><rect width="40" height="40" rx="9" fill="${p}"/><text x="20" y="26" text-anchor="middle" fill="${sec}" font-size="13" font-weight="800" font-family="Arial Black, system-ui, sans-serif">S</text><path d="M8 31 H32" stroke="${sec}" stroke-width="2"/></svg>`;
      case 'jetblue':
        return `<svg ${common}><rect width="40" height="40" rx="9" fill="${p}"/><path d="M8 24 C14 10, 26 10, 32 24 L28 24 C24 16, 16 16, 12 24 Z" fill="${sec}"/><circle cx="20" cy="28" r="2.5" fill="${acc}"/></svg>`;
      case 'suncountry':
        return `<svg ${common}><rect width="40" height="40" rx="9" fill="${p}"/><circle cx="20" cy="18" r="8" fill="${sec}"/><path d="M10 30 Q20 24 30 30" stroke="${acc}" stroke-width="2" fill="none"/></svg>`;
      case 'alaska':
        return `<svg ${common}><rect width="40" height="40" rx="9" fill="${p}"/><path d="M12 28 L20 8 L28 28 Z" fill="${acc}"/><path d="M16 28 L20 16 L24 28" fill="${p}"/><path d="M8 30 H32" stroke="${sec}" stroke-width="2.5"/></svg>`;
      case 'breeze':
        return `<svg ${common}><rect width="40" height="40" rx="9" fill="${p}"/><path d="M8 22 C14 12, 22 12, 32 18" stroke="${sec}" stroke-width="2.4" fill="none" stroke-linecap="round"/><path d="M10 28 C18 20, 26 20, 34 26" stroke="${acc}" stroke-width="1.6" fill="none" opacity="0.8"/></svg>`;
      case 'shuttle':
        return `<svg ${common}><rect width="40" height="40" rx="9" fill="${p}"/><rect x="8" y="14" width="24" height="12" rx="3" fill="${sec}"/><circle cx="14" cy="28" r="2.5" fill="${acc}"/><circle cx="26" cy="28" r="2.5" fill="${acc}"/></svg>`;
      case 'southern':
        return `<svg ${common}><rect width="40" height="40" rx="9" fill="${p}"/><path d="M8 26 L20 10 L32 26" stroke="${sec}" stroke-width="2.4" fill="none"/><text x="20" y="30" text-anchor="middle" fill="${acc}" font-size="8" font-weight="700" font-family="system-ui,sans-serif">SAE</text></svg>`;
      case 'charter':
        return `<svg ${common}><rect width="40" height="40" rx="9" fill="${p}"/><path d="M10 26 L20 12 L30 26" fill="${sec}"/><rect x="17" y="24" width="6" height="8" fill="${sec}"/></svg>`;
      default:
        return `<svg ${common}><rect width="40" height="40" rx="9" fill="${p}"/><text x="20" y="25" text-anchor="middle" fill="${acc}" font-size="11" font-weight="800" font-family="system-ui,sans-serif">${code}</text></svg>`;
    }
  }

  function getRoutelabBrand() {
    const brand = (bootstrap && bootstrap.routelab) || {};
    return {
      name: brand.name || 'RouteLab',
      logo_url: brand.logo_url || '/static/routelab/routelab-app-logo.jpg',
      tagline:
        brand.tagline ||
        'Airline network economics — routes, gates, rivals, and capital.',
    };
  }

  function routelabBrandLogoHtml(size, alt) {
    const brand = getRoutelabBrand();
    const sz = size || 72;
    const radius = sz >= 56 ? 14 : 10;
    const label = alt || brand.name;
    return `<img class="routelab-brand-logo${sz <= 44 ? ' sm' : ''}" src="${brand.logo_url}" alt="${label}" width="${sz}" height="${sz}" style="border-radius:${radius}px">`;
  }

  function renderStartBrand() {
    const brand = getRoutelabBrand();
    const logo = $('start-brand-logo');
    const name = $('start-brand-name');
    const tag = $('start-brand-tagline');
    if (logo) {
      logo.src = brand.logo_url;
      logo.alt = brand.name;
    }
    if (name) name.textContent = brand.name;
    if (tag) tag.textContent = brand.tagline;
    document.title = `${brand.name} · Airline Simulation`;
    let favicon = document.querySelector('link[rel="icon"]');
    if (!favicon) {
      favicon = document.createElement('link');
      favicon.rel = 'icon';
      document.head.appendChild(favicon);
    }
    favicon.href = brand.logo_url;
    favicon.type = 'image/jpeg';
  }

  function useRealCompetitorLogos() {
    if (bootstrap && bootstrap.use_real_competitor_logos === false) return false;
    return true; // private default
  }

  function competitorLogoFallbackSvg(name, brand, size) {
    return competitorBrandSvg(name, brand, size);
  }

  function airlineLogoHtml(name, emblemId, size) {
    const sz = size || 36;
    const safeName = String(name || 'Airline').replace(/"/g, '&quot;');
    const prof = airlineProfile(name);
    // Player airline → unique emblem SVG
    if (emblemId) {
      const opt = emblemOption(emblemId);
      const mark = (opt && opt.mark) || emblemId;
      const colors = (opt && opt.colors) || ['#00c896', '#1e3a5f', '#ffd166'];
      return `<span class="airline-logo airline-logo-player" style="width:${sz}px;height:${sz}px" title="${safeName}">${emblemSvgMarkup(
        mark,
        colors,
        sz
      )}</span>`;
    }
    // Known competitor — real logo file (private) with SVG mark fallback
    if (prof && prof.brand) {
      const brand = prof.brand;
      const logoUrl = useRealCompetitorLogos() ? brand.logo : null;
      if (logoUrl) {
        const bg = brand.primary || '#0f1c2e';
        return `<span class="airline-logo airline-logo-real" style="width:${sz}px;height:${sz}px;background:${bg}" title="${safeName}">
          <img class="airline-logo-img" src="${logoUrl}" alt="${safeName}" width="${sz}" height="${sz}" loading="lazy" decoding="async"
            onerror="this.remove();var f=this.parentNode&&this.parentNode.querySelector('.airline-logo-fallback');if(f)f.hidden=false;">
          <span class="airline-logo-fallback" hidden>${competitorLogoFallbackSvg(name, brand, sz)}</span>
        </span>`;
      }
      return `<span class="airline-logo airline-logo-brand" style="width:${sz}px;height:${sz}px" title="${safeName}">${competitorBrandSvg(
        name,
        brand,
        sz
      )}</span>`;
    }
    // Fallback initials on hashed hue
    const hue = hashHue(name);
    const initials = String(name || 'A')
      .split(/\s+/)
      .map((w) => w[0])
      .join('')
      .slice(0, 2)
      .toUpperCase();
    return `<span class="airline-logo" style="width:${sz}px;height:${sz}px;background:linear-gradient(145deg,hsl(${hue},52%,38%),hsl(${hue},48%,24%))" title="${safeName}">
      <span class="airline-logo-init" style="position:static;font-size:${Math.max(10, sz * 0.32)}px">${initials}</span>
    </span>`;
  }

  function defaultLeagueScope() {
    if (!state) return 'national';
    const sc = bootstrap.scenarios[state.scenario_id] || {};
    if (sc.region === 'ohio') return 'ohio';
    if (sc.region === 'midwest') return 'midwest';
    return 'national';
  }

  function getLeagueScope() {
    if (!state) return 'national';
    ensureMetrics();
    const scopes = bootstrap.league_scopes || {};
    const key = state.metrics.league_scope || defaultLeagueScope();
    return scopes[key] ? key : defaultLeagueScope();
  }

  function leagueScopeConfig(scopeKey) {
    const scopes = bootstrap.league_scopes || {};
    return scopes[scopeKey || getLeagueScope()] || scopes.national || {};
  }

  function leagueScopeLabel(scopeKey) {
    const cfg = leagueScopeConfig(scopeKey);
    return cfg.label || 'League';
  }

  function leagueAirlineNames(scopeKey) {
    const cfg = leagueScopeConfig(scopeKey);
    // Scope lists are curated (Ohio ≠ World). Do NOT merge every profile in —
    // that used to make national look like the same 15 names as Ohio.
    let names = cfg.airlines && cfg.airlines.length ? cfg.airlines.slice() : [];
    if (!names.length) {
      const profiles = bootstrap.airline_profiles || {};
      names = Object.keys(profiles).filter((n) => {
        const p = profiles[n] || {};
        const presence = (p.scope_presence || {})[scopeKey || 'national'];
        return presence == null || presence >= 0.04;
      });
    }
    return names;
  }

  function scopeAirportSet(scopeKey) {
    const cfg = leagueScopeConfig(scopeKey);
    if (!cfg.airports) return null;
    return new Set(cfg.airports);
  }

  function airportsInLeagueScope(scopeKey) {
    const allowed = scopeAirportSet(scopeKey);
    if (!allowed) return bootstrap.airports || [];
    return (bootstrap.airports || []).filter((a) => allowed.has(a.iata));
  }

  function routeTouchesScope(route, scopeKey) {
    const allowed = scopeAirportSet(scopeKey);
    if (!allowed) return true;
    return allowed.has(route.origin) || allowed.has(route.dest);
  }

  function scopeOverheadWeight(scopeKey) {
    const cfg = leagueScopeConfig(scopeKey);
    return cfg.overhead_weight != null ? cfg.overhead_weight : 1;
  }

  function airlineScopePresence(name, scopeKey) {
    const prof = airlineProfile(name) || {};
    const map = prof.scope_presence || {};
    if (map[scopeKey] != null) return Math.max(0, Math.min(1.2, map[scopeKey]));
    // Fallback from national_scale
    const scale = prof.national_scale != null ? prof.national_scale : 0.3;
    if (scopeKey === 'world') return scale * 0.45;
    if (scopeKey === 'national') return scale;
    if (scopeKey === 'midwest') return scale * 0.55;
    if (scopeKey === 'ohio') return scale * 0.4;
    return scale;
  }

  /**
   * How well the player is known / present inside a league scope.
   * Intensity where you operate (DAY/CMH) can be high; coverage dilution across the
   * whole arena makes national/world recognition collapse.
   */
  function playerScopeRecognition(scopeKey) {
    const aps = airportsInLeagueScope(scopeKey);
    // Prefer commercial airports for dilution so tiny GA strips don't dominate.
    const commercial = aps.filter((a) => (a.annual_pax_m || 0) >= 0.05 || (a.metro_pop_m || 0) >= 0.15);
    const pool = commercial.length >= 8 ? commercial : aps;
    const n = Math.max(1, pool.length);
    let brandSumAll = 0;
    let brandKnown = 0;
    let intensitySum = 0;
    let intensityN = 0;
    let opsAirports = 0;
    const opsSet = new Set();
    (state.routes || []).forEach((r) => {
      if (!routeTouchesScope(r, scopeKey)) return;
      opsSet.add(r.origin);
      opsSet.add(r.dest);
    });
    (state.gates || []).forEach((g) => {
      const allowed = scopeAirportSet(scopeKey);
      if (!allowed || allowed.has(g.airport)) opsSet.add(g.airport);
    });
    pool.forEach((ap) => {
      const b = (state.brand_awareness && state.brand_awareness[ap.iata]) || 0;
      brandSumAll += b;
      if (b >= 8) {
        brandKnown += 1;
        intensitySum += b;
        intensityN += 1;
      }
      if (opsSet.has(ap.iata)) opsAirports += 1;
    });
    // Also count ops airports even if brand is still low
    opsSet.forEach((iata) => {
      if (!pool.find((a) => a.iata === iata)) return;
      const b = (state.brand_awareness && state.brand_awareness[iata]) || 0;
      if (b < 8) {
        intensitySum += Math.max(b, 12);
        intensityN += 1;
      }
    });
    const avgBrand = brandSumAll / n;
    const intensity = intensityN ? intensitySum / intensityN : 0;
    const brandCoverage = brandKnown / n;
    const opsCoverage = opsAirports / n;
    const brandStock = Object.values(state.brand_awareness || {}).reduce((s, v) => s + (v || 0), 0);
    const cfg = leagueScopeConfig(scopeKey);
    const floor = cfg.recognition_floor != null ? cfg.recognition_floor : 0.02;
    // Local: high intensity + modest coverage → mid recognition.
    // National: same intensity, tiny coverage → near-floor recognition.
    const coverageFactor = 0.28 + brandCoverage * 0.55 + opsCoverage * 0.35;
    let recognition = intensity * coverageFactor + brandCoverage * 40 + opsCoverage * 28 + Math.sqrt(brandStock) * 0.45;
    // Arena size penalty beyond Ohio home pond
    if (scopeKey === 'midwest') recognition *= 0.72;
    else if (scopeKey === 'national') recognition *= 0.42;
    else if (scopeKey === 'world') recognition *= 0.12;
    recognition = Math.max(0, Math.min(100, recognition));
    const presenceShare = Math.max(floor * 0.2, (recognition / 100) * (0.4 + opsCoverage * 0.8));
    return {
      avgBrand,
      intensity,
      brandCoverage,
      opsCoverage,
      brandStock,
      recognition: Math.round(recognition * 10) / 10,
      presenceShare,
      airportsInScope: n,
      opsAirports,
    };
  }

  function setLeagueScope(scopeKey) {
    if (!bootstrap.league_scopes || !bootstrap.league_scopes[scopeKey]) return;
    ensureMetrics();
    state.metrics.league_scope = scopeKey;
    selectedRival = null;
    saveGame();
    renderScoreboardBar();
  }

  function ensureMetrics() {
    if (!state) return;
    if (!state.metrics) {
      state.metrics = {
        passengers_mtd: 0,
        passengers_month: 0,
        op_revenue_mtd: 0,
        op_cost_mtd: 0,
        csat: state.reputation || 20,
        month_index: 0,
        airport_share: {},
        prev_ranks: {},
        league_snapshot: [],
      };
    }
    if (!state.metrics.airport_share) state.metrics.airport_share = {};
    if (!state.metrics.prev_ranks) state.metrics.prev_ranks = {};
    if (!state.metrics.league_scope) state.metrics.league_scope = defaultLeagueScope();
  }

  function computeCsat() {
    if (!state) return 0;
    const net = networkRouteStats();
    const rep = state.reputation || 0;
    const aogN = (state.fleet || []).filter((f) => f.aog_days_left > 0).length;
    // Cabin density: roomier fleet configs lift satisfaction (legroom / less packed)
    let comfortBoost = 0;
    if ((state.fleet || []).length) {
      const avgC =
        state.fleet.reduce((s, f) => s + planeComfortRating(f), 0) / state.fleet.length;
      comfortBoost = (avgC - 3) * 4; // ±~8 pts vs mid comfort
    }
    return Math.max(
      0,
      Math.min(100, rep * 0.4 + net.avgLoad * 26 + 16 - aogN * 6 + comfortBoost)
    );
  }

  function playerNaturalOverheadMonthly() {
    let daily = 0;
    (state.routes || []).forEach((route) => {
      daily += simulateRouteDay(route).pax || 0;
    });
    const riders = Math.round(daily * 30);
    const routes = state.routes.length;
    const fleet = state.fleet.length;
    const gates = state.gates.length;
    const corp = 22000 + routes * 7500 + fleet * 9000 + gates * 3500;
    const brand = Math.sqrt(Math.max(0, riders)) * 280;
    const revenue = (state.ltm_revenue || 0) / 12;
    const sales = revenue * 0.015;
    return (corp + brand + sales) * tutorialOverheadScale();
  }

  function estimateMonthlyRiders(scopeKey) {
    let daily = 0;
    (state.routes || []).forEach((route) => {
      if (!routeTouchesScope(route, scopeKey)) return;
      daily += simulateRouteDay(route).pax || 0;
    });
    return Math.round(daily * 30);
  }

  function playerScopedMonthlyProfit(scopeKey) {
    let dayRev = 0;
    let dayCost = 0;
    (state.routes || []).forEach((route) => {
      if (!routeTouchesScope(route, scopeKey)) return;
      const r = simulateRouteDay(route);
      dayRev += r.revenue;
      dayCost += r.cost;
    });
    const total = simulateDayEconomics();
    const scopeShare = total.dayRev > 0 ? dayRev / total.dayRev : state.routes.length ? 0.35 : 0;
    const monthlyFixed =
      fleetMonthlyCosts() + gateLeaseMonthly() + monthlyDebtService() + marketingMonthly();
    const allocatedFixed = monthlyFixed * Math.min(1, scopeShare + 0.12);
    return Math.round((dayRev - dayCost) * 30 - allocatedFixed - playerNaturalOverheadMonthly());
  }

  function competitorScopedStats(name, scopeKey) {
    const prof = airlineProfile(name) || {
      financial_health: 0.55,
      route_sensitivity: 0.6,
      national_scale: 0.35,
      marketing_overhead_mo: 8_000_000,
      tier: 'lcc',
    };
    const aps = airportsInLeagueScope(scopeKey);
    const presence = airlineScopePresence(name, scopeKey);
    const cfg = leagueScopeConfig(scopeKey);
    const globalMult = cfg.global_multiplier != null ? cfg.global_multiplier : 1;
    let dailyPax = 0;
    let dailyGross = 0;
    const airportPresence = [];

    aps.forEach((ap) => {
      (ap.incumbents || []).forEach((inc) => {
        if (inc.airline !== name) return;
        const daily = (ap.annual_pax_m * 1_000_000 * inc.share) / 365;
        const avgFare = inc.tier === 'lcc' ? 108 : inc.tier === 'legacy' ? 168 : 142;
        dailyPax += daily;
        dailyGross += daily * avgFare;
        airportPresence.push({ iata: ap.iata, city: ap.city, share: inc.share, tier: inc.tier });
      });
    });

    const routesInScope = [];
    (state.competitor_routes || []).forEach((r) => {
      if (r.airline !== name) return;
      if (!routeTouchesScope(r, scopeKey)) return;
      const daily = (r.frequency_week / 7) * (48 + r.fare * 0.18) * (0.75 + prof.financial_health * 0.2);
      dailyPax += daily;
      dailyGross += daily * r.fare;
      routesInScope.push(r);
    });

    // Network floor: scale-heavy so majors stay on top; tiny regionals stay small
    // even with high local presence (Contour ≠ Delta in absolute riders).
    const scale = prof.national_scale != null ? prof.national_scale : 0.3;
    const apCount = Math.max(8, aps.length);
    const floorDaily =
      Math.pow(Math.max(0.015, scale), 1.45) * Math.pow(Math.max(0.05, presence), 0.85) * apCount * 70 * globalMult;
    if (dailyPax < floorDaily) {
      const fare = prof.tier === 'lcc' ? 95 : prof.tier === 'regional' || prof.tier === 'shuttle' ? 120 : 165;
      const add = floorDaily - dailyPax;
      dailyPax = floorDaily;
      dailyGross += add * fare;
    }

    const playerSteal = Object.keys(state.brand_awareness || {}).reduce((s, iata) => {
      const ap = airport(iata);
      if (!ap || !aps.find((x) => x.iata === iata)) return s;
      const inc = (ap.incumbents || []).find((c) => c.airline === name);
      if (!inc) return s;
      return s + (state.brand_awareness[iata] || 0) * inc.share * 0.35;
    }, 0);
    dailyPax = Math.max(floorDaily * 0.35, dailyPax - playerSteal * 14);
    dailyGross = Math.max(0, dailyGross - playerSteal * 14 * 125);

    const riders = Math.round(dailyPax * 30);
    const gross = dailyGross * 30;
    const margin = 0.06 + prof.financial_health * 0.11;
    // Overhead scales with scope, but never erase presence for ranking —
    // use soft overhead so tiny regionals don't go −$50M and lose to a startup.
    const rawOverhead =
      (prof.marketing_overhead_mo || scale * 50_000_000) * scopeOverheadWeight(scopeKey) * presence;
    const opProfit = gross * margin;
    // Rankable profit: can't fall below −15% of gross (giants stay huge; minnows stay small)
    const profit = Math.round(Math.max(opProfit * -0.15, opProfit - rawOverhead * 0.55));
    const recognition = Math.round(
      Math.min(98, presence * 88 + scale * 10 + Math.min(8, routesInScope.length))
    );

    const csat = Math.max(
      22,
      Math.min(
        94,
        32 +
          prof.financial_health * 42 +
          Math.min(12, routesInScope.length * 1.5) -
          playerSteal * 0.08
      )
    );

    return {
      profit,
      riders,
      csat: Math.round(csat),
      gross: Math.round(gross),
      overhead: Math.round(rawOverhead),
      routesInScope,
      airportPresence,
      recognition,
      presence,
      prof,
    };
  }

  function competitorLeagueEntry(name, scopeKey) {
    const stats = competitorScopedStats(name, scopeKey);
    return {
      id: name.replace(/\s+/g, '_').toLowerCase(),
      name,
      isPlayer: false,
      profit: stats.profit,
      riders: stats.riders,
      csat: stats.csat,
      gross: stats.gross,
      overhead: stats.overhead,
      recognition: stats.recognition,
      presence: stats.presence,
      emblem: null,
      overall: 0,
    };
  }

  function playerLeagueEntry(scopeKey) {
    ensureMetrics();
    const rec = playerScopeRecognition(scopeKey);
    const ridersRaw = estimateMonthlyRiders(scopeKey);
    // Dilute effective riders as arena grows — you're a big fish only where you fly.
    // National/world: same absolute pax count as a smaller share of the market.
    const scopeN = Math.max(1, rec.airportsInScope);
    const homeN = Math.max(
      1,
      (bootstrap.ohio_region_iata || []).length || 50
    );
    const arenaDilution = Math.min(1, Math.sqrt(homeN / scopeN) * (0.55 + rec.opsCoverage * 0.9));
    const riders = Math.round(ridersRaw * Math.max(0.04, arenaDilution));
    const profitRaw = playerScopedMonthlyProfit(scopeKey);
    // Profit also "feels" smaller vs giants when recognition is tiny (brand can't convert nationally)
    const profit = Math.round(profitRaw * (0.35 + rec.presenceShare * 1.4));
    const csat = Math.round(computeCsat());
    return {
      id: 'player',
      name: state.airline_name || 'You',
      isPlayer: true,
      profit,
      riders: Math.max(0, riders),
      ridersRaw,
      csat,
      recognition: rec.recognition,
      presence: rec.presenceShare,
      brandAvg: rec.avgBrand,
      opsCoverage: rec.opsCoverage,
      overall: 0,
      emblem: state.airline_emblem || 'wing',
    };
  }

  function leaguePillarPercentile(entries, key, entry) {
    const sorted = [...entries].sort((a, b) => (b[key] || 0) - (a[key] || 0));
    const idx = sorted.findIndex((e) => e.id === entry.id);
    if (idx < 0) return 0;
    return Math.round((1 - idx / Math.max(1, entries.length - 1)) * 100);
  }

  function leagueLogPercentile(entries, key, entry) {
    // Log-scale ranks so Delta (millions) doesn't make every small carrier look identical.
    const vals = entries.map((e) => Math.log10(Math.max(1, e[key] || 0)));
    const mine = Math.log10(Math.max(1, entry[key] || 0));
    const max = Math.max(...vals, 1e-6);
    const min = Math.min(...vals);
    if (max <= min) return 50;
    return Math.round(((mine - min) / (max - min)) * 100);
  }

  function applyLeagueOverallScores(entries, scopeKey) {
    // Presence-first: riders + brand recognition dominate. Profit is secondary so
    // overhead accounting never ranks a startup above Delta nationally.
    entries.forEach((e) => {
      const riderPct = leagueLogPercentile(entries, 'riders', e);
      const recPct = leagueLogPercentile(entries, 'recognition', e);
      const profitPct = leaguePillarPercentile(entries, 'profit', e);
      const csatPct = Math.max(0, Math.min(100, e.csat || 0));
      let overall = riderPct * 0.42 + recPct * 0.28 + profitPct * 0.15 + csatPct * 0.15;
      // Extra penalty for the player outside their home pond
      if (e.isPlayer) {
        const rec = playerScopeRecognition(scopeKey);
        // Home pond can be competitive; leave Ohio and standing collapses.
        const homeBoost =
          scopeKey === 'ohio' ? 1.12 : scopeKey === 'midwest' ? 0.82 : scopeKey === 'national' ? 0.58 : 0.28;
        overall *= homeBoost * (0.62 + Math.min(0.55, rec.presenceShare * 2.8));
      }
      e.overall = Math.round(Math.max(1, Math.min(99, overall)));
      e.riderPct = riderPct;
      e.recPct = recPct;
    });
  }

  function buildLeagueTable(scopeKey) {
    if (!state) return [];
    const scope = scopeKey || getLeagueScope();
    const entries = [
      playerLeagueEntry(scope),
      ...leagueAirlineNames(scope).map((n) => competitorLeagueEntry(n, scope)),
    ];
    applyLeagueOverallScores(entries, scope);
    entries.sort((a, b) => b.overall - a.overall || b.riders - a.riders);
    return entries.map((e, i) => ({ ...e, rank: i + 1, scope }));
  }

  function pillarMeter(score) {
    const filled = Math.max(0, Math.min(5, Math.round(score / 20)));
    return Array.from({ length: 5 }, (_, i) => `<span class="pillar-dot${i < filled ? ' on' : ''}"></span>`).join('');
  }

  function metricLeverTip(pillar) {
    const tips = {
      profit: 'Scoped operating profit — click to sort. Giants look weaker in tiny ponds (heavy brand cost).',
      riders: 'Estimated monthly passengers in this arena — diluted when you leave your home markets',
      csat: 'Passenger satisfaction — reputation, load factor, reliability',
      overall:
        'Rank vs rivals in this arena. #1 is best. Expanding scope (Ohio → Midwest → US → World) should make your rank worse until you grow brand and routes.',
    };
    return tips[pillar] || '';
  }

  function pillarSortLabel(key) {
    const labels = {
      profit: 'Profit',
      riders: 'Riders',
      csat: 'Satisfaction',
      overall: 'Rank',
    };
    return labels[key] || key;
  }

  function sortLeagueByMetric(entries, sortKey) {
    const key = sortKey || 'overall';
    const sorted = [...entries].sort((a, b) => (b[key] || 0) - (a[key] || 0));
    return sorted.map((e, i) => ({ ...e, rank: i + 1 }));
  }

  function routePillarMetrics(route) {
    const hist = routeHistoryAverages(route, 30);
    const sim = simulateRouteDay(route);
    const dailyPnl = hist ? hist.avgPnl : (sim.revenue || 0) - (sim.cost || 0);
    const dailyPax = hist ? hist.avgPax : sim.pax || 0;
    const load = hist ? hist.avgLoad : sim.grounded ? 0 : sim.load || 0;
    const plane = state.fleet.find((f) => f.id === route.aircraft_id);
    const aog = plane && plane.aog_days_left > 0 ? 6 : 0;
    const repShare = (state.reputation || 0) * 0.15;
    const comfort = plane ? planeComfortRating(plane) : 3;
    const comfortPts = (comfort - 3) * 5;
    const prod = routeProduct(routeProductId(route));
    const csat = Math.max(
      0,
      Math.min(
        100,
        Math.round(repShare + load * 26 + 16 - aog + comfortPts + (prod.csatAdj || 0))
      )
    );
    return {
      profit: dailyPnl * 30,
      riders: Math.round(dailyPax * 30),
      csat,
    };
  }

  function sortPlayerRoutesByPillar(sortKey) {
    if (!state || !state.routes.length) return [];
    const key = sortKey === 'overall' ? 'profit' : sortKey;
    if (!['profit', 'riders', 'csat'].includes(key)) return [];
    return state.routes
      .map((route) => ({ route, ...routePillarMetrics(route) }))
      .sort((a, b) => (b[key] || 0) - (a[key] || 0))
      .map((e, i) => ({ ...e, rank: i + 1, sortKey: key }));
  }

  function formatRoutePillarValue(sortKey, metrics) {
    if (sortKey === 'profit') return `${fmtMoney(metrics.profit)}/mo`;
    if (sortKey === 'riders') return `${metrics.riders.toLocaleString()}/mo`;
    if (sortKey === 'csat') return String(metrics.csat);
    return '';
  }

  function yourRoutesRankHtml(sortKey) {
    const ranked = sortPlayerRoutesByPillar(sortKey);
    if (!ranked.length || !['profit', 'riders', 'csat'].includes(sortKey)) return '';
    const rows = ranked
      .map((e) => {
        const val = formatRoutePillarValue(sortKey, e);
        return `<tr><td>#${e.rank}</td><td><b>${e.route.origin}–${e.route.dest}</b></td><td>${val}</td></tr>`;
      })
      .join('');
    return `<div class="your-routes-rank" style="margin-top:14px;padding-top:12px;border-top:1px solid rgba(255,255,255,0.08);">
      <h4 style="font-size:0.82rem;color:var(--gold);margin:0 0 6px;">Your routes — by ${pillarSortLabel(sortKey)}</h4>
      <p class="muted" style="font-size:0.7rem;margin:0 0 8px;">Same pillar as the league table. Routes tab re-sorts to match.</p>
      <table class="scoreboard-table" style="font-size:0.74rem;">
        <thead><tr><th>#</th><th>Route</th><th>${pillarSortLabel(sortKey)}</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
  }

  function openScoreboardSorted(sortKey) {
    if (!state) return;
    scoreboardSortBy = sortKey || 'overall';
    scoreboardOpen = true;
    selectedRival = null;
    renderScoreboardBar();
    const runningEl = $('route-list-running');
    if (runningEl) runningEl.innerHTML = runningRoutesHtml();
  }

  function ensureRouteStats(route) {
    if (!route.stats) route.stats = { days: 0, pax_sum: 0, load_sum: 0 };
    if (!Array.isArray(route.history)) route.history = [];
  }

  function recordRouteDailyStats(route, sim) {
    if (!route || !state) return;
    ensureRouteStats(route);
    if (!sim.grounded) {
      const s = route.stats;
      if (s.days >= ROUTE_STATS_WINDOW_DAYS) {
        const k = (ROUTE_STATS_WINDOW_DAYS - 1) / ROUTE_STATS_WINDOW_DAYS;
        s.pax_sum *= k;
        s.load_sum *= k;
      } else {
        s.days += 1;
      }
      s.pax_sum += sim.pax || 0;
      s.load_sum += sim.load || 0;
    }
    const last = route.history.length ? route.history[route.history.length - 1] : null;
    if (!last || last.day !== state.day) {
      route.history.push({
        day: state.day,
        load: sim.grounded ? null : sim.load,
        pax: sim.grounded ? 0 : sim.pax || 0,
        rev: sim.revenue || 0,
        cost: sim.cost || 0,
        pnl: (sim.revenue || 0) - (sim.cost || 0),
        grounded: !!sim.grounded,
      });
      if (route.history.length > ROUTE_HISTORY_MAX_DAYS) {
        route.history = route.history.slice(-ROUTE_HISTORY_MAX_DAYS);
      }
    }
  }

  function routeActualStats(route) {
    ensureRouteStats(route);
    const s = route.stats;
    if (!s.days) return null;
    return {
      days: s.days,
      avgLoad: s.load_sum / Math.max(1, s.days),
      avgPax: s.pax_sum / Math.max(1, s.days),
    };
  }

  function routeById(routeId) {
    return (state && state.routes || []).find((r) => r.id === routeId) || null;
  }

  function routeHistoryWindow(route, days) {
    ensureRouteStats(route);
    const hist = route.history || [];
    if (!days || days >= hist.length) return hist.slice();
    return hist.slice(-days);
  }

  function routeHistoryAverages(route, days) {
    const window = routeHistoryWindow(route, days).filter((h) => !h.grounded && h.load != null);
    if (!window.length) return null;
    const n = window.length;
    return {
      days: n,
      avgLoad: window.reduce((s, h) => s + h.load, 0) / n,
      avgPax: window.reduce((s, h) => s + h.pax, 0) / n,
      avgPnl: window.reduce((s, h) => s + h.pnl, 0) / n,
      totalRev: window.reduce((s, h) => s + h.rev, 0),
      totalPnl: window.reduce((s, h) => s + h.pnl, 0),
    };
  }

  function renderLineChart(points, opts) {
    opts = opts || {};
    const valueKey = opts.valueKey || 'y';
    const width = opts.width || 340;
    const height = opts.height || 108;
    const color = opts.color || '#00c896';
    const forecast = opts.forecast;
    const formatValue = opts.formatValue || ((v) => String(Math.round(v)));
    const unit = opts.unit || '';

    if (!points || !points.length) {
      return '<p class="muted chart-empty">No history yet — data builds day by day.</p>';
    }
    const vals = points.map((p) => p[valueKey]).filter((v) => v != null && Number.isFinite(v));
    if (!vals.length) {
      return '<p class="muted chart-empty">No readings for this metric yet.</p>';
    }

    let min = Math.min(...vals);
    let max = Math.max(...vals);
    if (forecast != null && Number.isFinite(forecast)) {
      min = Math.min(min, forecast);
      max = Math.max(max, forecast);
    }
    const span = max - min || 1;
    const pad = span * 0.1;
    min -= pad;
    max += pad;
    const margin = { l: 40, r: 10, t: 10, b: 24 };
    const innerW = width - margin.l - margin.r;
    const innerH = height - margin.t - margin.b;
    const xAt = (i) => margin.l + (i / Math.max(1, points.length - 1)) * innerW;
    const yAt = (v) => margin.t + innerH - ((v - min) / (max - min)) * innerH;

    let pathD = '';
    points.forEach((p, i) => {
      const v = p[valueKey];
      if (v == null || !Number.isFinite(v)) return;
      const seg = `${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`;
      pathD += pathD ? ` L${seg}` : `M${seg}`;
    });

    const yTicks = [min, min + (max - min) * 0.5, max];
    const yGrid = yTicks
      .map((v) => {
        const y = yAt(v).toFixed(1);
        return `<line x1="${margin.l}" y1="${y}" x2="${width - margin.r}" y2="${y}" class="chart-grid"/>`;
      })
      .join('');
    const yLabels = yTicks
      .map((v) => {
        const y = yAt(v) + 3;
        return `<text x="${margin.l - 6}" y="${y}" class="chart-axis" text-anchor="end">${formatValue(v)}${unit}</text>`;
      })
      .join('');

    const firstDay = points[0].day;
    const lastDay = points[points.length - 1].day;
    const xLabels = `<text x="${margin.l}" y="${height - 4}" class="chart-axis">${fmtDate(firstDay)}</text>
      <text x="${width - margin.r}" y="${height - 4}" class="chart-axis" text-anchor="end">${fmtDate(lastDay)}</text>`;

    let forecastLine = '';
    if (forecast != null && Number.isFinite(forecast)) {
      const fy = yAt(forecast).toFixed(1);
      forecastLine = `<line x1="${margin.l}" y1="${fy}" x2="${width - margin.r}" y2="${fy}" class="chart-forecast"/>
        <text x="${width - margin.r}" y="${+fy - 4}" class="chart-forecast-label" text-anchor="end">plan ${formatValue(forecast)}${unit}</text>`;
    }

    const last = vals[vals.length - 1];
    const lastPoint = points.slice().reverse().find((p) => p[valueKey] != null && Number.isFinite(p[valueKey]));
    const lastIdx = lastPoint ? points.indexOf(lastPoint) : points.length - 1;
    const lastV = lastPoint ? lastPoint[valueKey] : last;
    const dot = lastPoint
      ? `<circle cx="${xAt(lastIdx).toFixed(1)}" cy="${yAt(lastV).toFixed(1)}" r="3.5" class="chart-dot"/>`
      : '';

    return `<svg class="metric-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${opts.label || 'Trend chart'}">
      ${yGrid}
      ${forecastLine}
      <path d="${pathD}" class="chart-line" style="stroke:${color}"/>
      ${dot}
      ${yLabels}
      ${xLabels}
    </svg>`;
  }

  function renderRouteReviewModal() {
    const overlay = $('route-review-modal');
    if (!overlay) return;
    if (!routeReviewRouteId || !state) {
      overlay.classList.remove('active');
      overlay.innerHTML = '';
      document.body.classList.remove('route-review-active');
      return;
    }
    const route = routeById(routeReviewRouteId);
    if (!route) {
      routeReviewRouteId = null;
      renderRouteReviewModal();
      return;
    }
    backfillRouteForecast(route);
    ensureRouteStats(route);
    const hist = route.history || [];
    const avg7 = routeHistoryAverages(route, 7);
    const avg30 = routeHistoryAverages(route, 30);
    const avgAll = routeHistoryAverages(route, hist.length);
    const oAp = airport(route.origin);
    const dAp = airport(route.dest);
    const dist =
      oAp && dAp ? Math.round(haversineNm(oAp.lat, oAp.lon, dAp.lat, dAp.lon)) : null;
    const plane = route.aircraft_id ? state.fleet.find((f) => f.id === route.aircraft_id) : null;
    const ac = aircraftType(route.aircraft_type);
    const launchDay = hist.length ? hist[0].day : null;
    const daysLive = hist.length;
    const forecastLoad = route.launch_forecast_load;
    const forecastPax = route.launch_forecast_pax_day;

    const loadChart = renderLineChart(hist, {
      valueKey: 'load',
      label: 'Load factor trend',
      color: '#00c896',
      forecast: forecastLoad,
      formatValue: (v) => `${(v * 100).toFixed(0)}`,
      unit: '%',
    });
    const paxChart = renderLineChart(hist, {
      valueKey: 'pax',
      label: 'Daily passengers',
      color: '#7eb8e8',
      forecast: forecastPax,
      formatValue: (v) => String(Math.round(v)),
    });
    const pnlChart = renderLineChart(hist, {
      valueKey: 'pnl',
      label: 'Daily route P&L',
      color: '#ffd166',
      formatValue: (v) => fmtMoney(v),
    });

    const statRow = (label, avg) => {
      if (!avg) return `<tr><td>${label}</td><td class="muted" colspan="3">—</td></tr>`;
      return `<tr>
        <td>${label}</td>
        <td>${(avg.avgLoad * 100).toFixed(0)}%</td>
        <td>${Math.round(avg.avgPax)}</td>
        <td class="${avg.avgPnl >= 0 ? '' : 'danger'}">${fmtMoney(avg.avgPnl)}</td>
      </tr>`;
    };

    overlay.innerHTML = `
      <div class="route-review-card" role="dialog" aria-modal="true">
        <button type="button" class="btn secondary route-review-close" data-route-review-close>← Back to routes</button>
        <p class="decision-kicker">Route review</p>
        <h2>${route.origin} → ${route.dest}</h2>
        <p class="muted" style="font-size:0.76rem;line-height:1.45;margin-bottom:12px;">
          ${oAp ? oAp.city : route.origin} to ${dAp ? dAp.city : route.dest}
          ${dist != null ? ` · ${dist} nm` : ''}
          · ${route.frequency_week}/wk @ $${route.fare}
          · ${ac ? ac.name : route.aircraft_type}${plane ? ` (${fleetSeatCount(plane)} seats)` : ''}
        </p>
        <dl class="stat-dl route-review-summary">
          <dt>Days operating</dt><dd>${daysLive || '—'}${launchDay != null ? ` <span class="muted">since ${fmtDate(launchDay)}</span>` : ''}</dd>
          <dt>Launch plan</dt><dd>${forecastLoad != null ? `${(forecastLoad * 100).toFixed(0)}% load · ~${forecastPax} pax/day` : '—'}</dd>
          <dt>Latest day</dt><dd>${
            hist.length
              ? (() => {
                  const h = hist[hist.length - 1];
                  if (h.grounded) return '<span class="danger">AOG — no service</span>';
                  return `${(h.load * 100).toFixed(0)}% load · ${h.pax} pax · <span class="${h.pnl >= 0 ? '' : 'danger'}">${fmtMoney(h.pnl)}</span>`;
                })()
              : 'Collecting…'
          }</dd>
        </dl>
        <table class="route-review-table">
          <thead><tr><th>Window</th><th>Avg load</th><th>Avg pax/day</th><th>Avg P&L/day</th></tr></thead>
          <tbody>
            ${statRow('Last 7 days', avg7)}
            ${statRow('Last 30 days', avg30)}
            ${statRow('All time', avgAll)}
          </tbody>
        </table>
        <div class="route-review-charts">
          <div class="chart-panel">
            <h4>Load factor</h4>
            ${loadChart}
          </div>
          <div class="chart-panel">
            <h4>Daily passengers</h4>
            ${paxChart}
          </div>
          <div class="chart-panel">
            <h4>Daily P&amp;L (route variable)</h4>
            ${pnlChart}
          </div>
        </div>
        <p class="muted" style="font-size:0.68rem;margin-top:10px;">Daily snapshots (up to ${ROUTE_HISTORY_MAX_DAYS} days). Same chart pattern will extend to fleet, gates, and league metrics.</p>
      </div>`;
    overlay.classList.add('active');
    document.body.classList.add('route-review-active');
    overlay.querySelector('[data-route-review-close]')?.addEventListener('click', closeRouteReview);
    overlay.onclick = (e) => {
      if (e.target === overlay) closeRouteReview();
    };
  }

  function openRouteReview(routeId) {
    if (!state || !routeId) return;
    const route = routeById(routeId);
    if (!route) return;
    pauseForInterrupt();
    routeReviewRouteId = routeId;
    renderRouteReviewModal();
  }

  function closeRouteReview() {
    routeReviewRouteId = null;
    renderRouteReviewModal();
    resumeSpeedAfterInterrupt();
  }

  function planeById(planeId) {
    return (state.fleet || []).find((f) => f.id === planeId) || null;
  }

  function renderPlaneDetailModal() {
    const overlay = $('plane-detail-modal');
    if (!overlay) return;
    if (!planeDetailId || !state) {
      overlay.classList.remove('active');
      overlay.innerHTML = '';
      document.body.classList.remove('plane-detail-active');
      return;
    }
    const plane = planeById(planeDetailId);
    if (!plane) {
      planeDetailId = null;
      renderPlaneDetailModal();
      return;
    }
    ensurePlaneTelemetry(plane);
    const ac = aircraftType(plane.type);
    const seats = fleetSeatCount(plane);
    const routes = (state.routes || []).filter((r) => r.aircraft_id === plane.id);
    const util = planeMonthUtilizationPct(plane);
    const utilToday = planeUtilizationPct(plane);
    const rel = planeReliabilityScore(plane);
    const aogRisk = planeAogRiskPct(plane);
    const life = planeUsefulLifeInfo(plane);
    const blockCap = planeWeeklyBlockHoursCapacity(plane);
    const blockUsed = planeWeeklyBlockHoursUsed(plane.id);
    const seatLoad = planeSeatLoadToday(plane.id);
    const maintMo = plane.leased ? 0 : ac ? ac.maintenance_monthly || 0 : 0;
    const leaseMo = plane.leased && ac ? ac.lease_monthly || 0 : 0;
    const comfort = ac ? comfortStars(ac.comfort_rating) : '—';
    const daysOwned = Math.max(0, (state.day || 0) - (plane.acquired_day || 0));
    const relTone = rel >= 80 ? 'chip-load-good' : rel >= 55 ? 'chip-load-warn' : 'chip-load-bad';
    const utilBarClass = util < 40 ? 'util-bad' : util > 85 ? 'util-warn' : '';
    const lifeBarClass = life.pctLeft < 25 ? 'util-bad' : life.pctLeft < 50 ? 'util-warn' : '';

    const routeRows = routes.length
      ? routes
          .map((r) => {
            const sim = simulateRouteDay(r);
            const load =
              sim.grounded
                ? 'AOG'
                : Number.isFinite(sim.load)
                  ? `${(sim.load * 100).toFixed(0)}%`
                  : '—';
            return `<tr>
              <td><button type="button" class="linkish" data-plane-open-route="${r.id}">${r.origin}–${r.dest}</button></td>
              <td>${r.frequency_week}/wk</td>
              <td>$${r.fare}</td>
              <td>${load}</td>
              <td class="${sim.revenue - sim.cost >= 0 ? '' : 'danger'}">${fmtMoney(sim.revenue - sim.cost)}/d</td>
            </tr>`;
          })
          .join('')
      : '<tr><td colspan="5" class="muted">No routes assigned — open Routes or Route Studio.</td></tr>';

    const logRows =
      plane.aog_log && plane.aog_log.length
        ? [...plane.aog_log]
            .reverse()
            .slice(0, 12)
            .map(
              (e) =>
                `<li><span class="muted">${fmtDate(e.day)}</span> — AOG ${e.days}d out · util was ${e.util != null ? e.util + '%' : '—'}</li>`
            )
            .join('')
        : '<li class="muted">No AOG events recorded yet — keep monthly utilization out of the red zone.</li>';

    const statusLine = plane.aog_days_left > 0
      ? `<span class="danger">On ground (AOG) — ${plane.aog_days_left} day${plane.aog_days_left === 1 ? '' : 's'} left</span>`
      : '<span class="via-good">In service</span>';

    overlay.innerHTML = `
      <div class="route-review-card plane-detail-card" role="dialog" aria-modal="true" aria-label="Aircraft detail">
        <button type="button" class="btn secondary route-review-close" data-plane-detail-close>← Back to fleet</button>
        <p class="decision-kicker">Aircraft</p>
        <h2>${ac ? ac.name : plane.type}</h2>
        <p class="muted" style="font-size:0.76rem;line-height:1.45;margin-bottom:12px;">
          ${plane.id} · ${plane.leased ? 'Leased' : 'Owned'} · ${seats} seats · ${ac ? ac.range_nm + ' nm' : '—'}
          · Comfort ${comfort} · ${statusLine}
        </p>
        <dl class="stat-dl route-review-summary">
          <dt>Reliability</dt><dd class="${relTone}"><b>${rel}</b>/100</dd>
          <dt>AOG risk (weekly check)</dt><dd>~${aogRisk.toFixed(1)}%</dd>
          <dt>Schedule util</dt><dd>${utilToday.toFixed(0)}% today · ${util.toFixed(0)}% MTD</dd>
          <dt>Block hours</dt><dd><b>${fmtHours(blockUsed)}</b> / ${fmtHours(blockCap)} hr/wk scheduled</dd>
          <dt>Seat load today</dt><dd>${
            seatLoad != null ? `${(seatLoad * 100).toFixed(0)}%` : routes.length ? '—' : 'idle'
          }</dd>
          <dt>In fleet</dt><dd>${daysOwned} day${daysOwned === 1 ? '' : 's'}${
            plane.acquired_day != null ? ` <span class="muted">(from ${fmtDate(plane.acquired_day)})</span>` : ''
          }</dd>
          <dt>Monthly cost</dt><dd>${
            plane.leased
              ? `${fmtMoney(leaseMo)} lease`
              : `${fmtMoney(maintMo)} maintenance`
          }</dd>
          <dt>AOG history</dt><dd>${plane.aog_events || 0} events · ${plane.total_aog_days || 0} days grounded</dd>
        </dl>

        <div class="plane-life-block">
          <div class="pressure-meter-head">
            <span>${life.label}</span>
            <strong>${
              life.kind === 'lease'
                ? `${life.monthsLeft} mo`
                : `${life.yearsLeft.toFixed(1)} yr`
            } <span class="muted">(${life.pctLeft.toFixed(0)}% left)</span></strong>
          </div>
          <div class="util-bar ${lifeBarClass}"><span style="width:${life.pctLeft}%"></span></div>
          <p class="muted" style="font-size:0.68rem;margin:6px 0 0;">${life.detail}</p>
        </div>

        <div class="plane-life-block" style="margin-top:10px;">
          <div class="pressure-meter-head">
            <span>Monthly utilization (block hours)</span>
            <strong>${util.toFixed(0)}%</strong>
          </div>
          <div class="util-bar ${utilBarClass}"><span style="width:${Math.min(100, util)}%"></span></div>
          <p class="muted" style="font-size:0.68rem;margin:6px 0 0;">
            High util raises AOG risk; very low util wastes lease cost. Target roughly 50–80% MTD.
          </p>
        </div>

        <h4 class="rival-section-title" style="margin-top:14px;">Assigned routes</h4>
        <table class="route-review-table">
          <thead><tr><th>Route</th><th>Freq</th><th>Fare</th><th>Load</th><th>P&amp;L</th></tr></thead>
          <tbody>${routeRows}</tbody>
        </table>

        <h4 class="rival-section-title">Maintenance log</h4>
        <ul class="list" style="font-size:0.78rem;">${logRows}</ul>
        <p class="muted" style="font-size:0.68rem;margin-top:10px;">
          AOG = aircraft on ground. Lease bills continue while grounded. Reliability falls after repeated AOGs and extreme utilization.
        </p>
      </div>`;
    overlay.classList.add('active');
    document.body.classList.add('plane-detail-active');
    overlay.querySelector('[data-plane-detail-close]')?.addEventListener('click', closePlaneDetail);
    overlay.querySelectorAll('[data-plane-open-route]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const rid = btn.getAttribute('data-plane-open-route');
        closePlaneDetail();
        openRouteReview(rid);
      });
    });
    overlay.onclick = (e) => {
      if (e.target === overlay) closePlaneDetail();
    };
  }

  function openPlaneDetail(planeId) {
    if (!state || !planeId) return;
    const plane = planeById(planeId);
    if (!plane) return;
    pauseForInterrupt();
    planeDetailId = planeId;
    renderPlaneDetailModal();
  }

  function closePlaneDetail() {
    planeDetailId = null;
    renderPlaneDetailModal();
    resumeSpeedAfterInterrupt();
  }

  function backfillRouteForecast(route) {
    if (route.launch_forecast_load != null) return;
    const via = estimateRouteViability(
      route.origin,
      route.dest,
      route.aircraft_type,
      route.frequency_week,
      route.fare,
      route.aircraft_id
    );
    route.launch_forecast_load = via.load;
    route.launch_forecast_pax_day = via.dailyPax;
    ensureRouteStats(route);
  }

  function updateDailyMetrics(econ) {
    if (!state) return;
    ensureMetrics();
    let dayPax = 0;
    const share = { ...state.metrics.airport_share };
    state.routes.forEach((route) => {
      const r = simulateRouteDay(route);
      recordRouteDailyStats(route, r);
      dayPax += r.pax || 0;
      if (r.pax > 0) {
        share[route.origin] = (share[route.origin] || 0) + r.pax * 0.6;
        share[route.dest] = (share[route.dest] || 0) + r.pax * 0.4;
      }
    });
    state.metrics.passengers_mtd += dayPax;
    state.metrics.op_revenue_mtd += econ.dayRev || 0;
    state.metrics.op_cost_mtd += (econ.dayCost || 0) + (econ.dailyFixed || 0);
    Object.keys(share).forEach((k) => {
      share[k] = Math.min(100, share[k] / 80);
    });
    state.metrics.airport_share = share;
    state.metrics.csat = computeCsat();
  }

  function processMonthlyScoreboard() {
    if (!state) return;
    ensureMetrics();
    const table = buildLeagueTable();
    const prev = state.metrics.prev_ranks || {};
    const player = table.find((e) => e.isPlayer);
    const region = leagueScopeLabel(getLeagueScope());

    table.forEach((entry) => {
      const oldRank = prev[entry.id];
      entry.trend = oldRank != null ? oldRank - entry.rank : 0;
    });

    if (player && player.rank <= 3) {
      markMilestoneOnce(
        'league_top_3',
        `${state.airline_name} cracked the <b>top 3</b> in the ${region} league — rivals are watching.`
      );
    }
    if (player && prev.player != null && player.rank < prev.player) {
      pushEvent(
        `League (${region}): ${state.airline_name} rose to <b>#${player.rank}</b> in the league.`,
        player.rank === 1 ? 'milestone' : 'good'
      );
    } else if (player && prev.player != null && player.rank > prev.player) {
      pushEvent(`League (${region}): ${state.airline_name} slipped to <b>#${player.rank}</b> — rivals gained ground.`, 'bad');
    }

    ['profit', 'riders', 'csat'].forEach((key) => {
      const sorted = [...table].sort((a, b) => {
        const av = key === 'riders' ? a.riders : a[key];
        const bv = key === 'riders' ? b.riders : b[key];
        return bv - av;
      });
      const p = sorted.findIndex((e) => e.isPlayer) + 1;
      const old = prev[`player_${key}`];
      if (old != null && p < old) {
        const label = key === 'riders' ? 'Riders' : key === 'csat' ? 'Satisfaction' : 'Profitability';
        pushPlayerEvent(`${label} rank improved to #${p} in ${region} league.`);
      }
      prev[`player_${key}`] = p;
    });

    state.metrics.passengers_month = state.metrics.passengers_mtd;
    state.metrics.prev_ranks = table.reduce((acc, e) => {
      acc[e.id] = e.rank;
      return acc;
    }, { ...prev });
    state.metrics.league_snapshot = table;
    state.metrics.month_index += 1;
    state.metrics.passengers_mtd = 0;
    state.metrics.op_revenue_mtd = 0;
    state.metrics.op_cost_mtd = 0;
  }

  function playerShareAtAirport(iata) {
    if (!state || !state.metrics) return (state.brand_awareness && state.brand_awareness[iata]) / 100 || 0;
    const share = state.metrics.airport_share[iata];
    if (share != null) return Math.min(1, share / 100);
    return ((state.brand_awareness && state.brand_awareness[iata]) || 0) / 100;
  }

  function leagueScopePickerHtml() {
    const scopes = bootstrap.league_scopes || {};
    const active = getLeagueScope();
    return Object.entries(scopes)
      .map(
        ([key, cfg]) =>
          `<button type="button" class="scope-btn${key === active ? ' active' : ''}" data-league-scope="${key}" title="Compare within ${cfg.label}">${cfg.label}</button>`
      )
      .join('');
  }

  function bindLeagueScopeButtons() {
    document.querySelectorAll('[data-league-scope]').forEach((btn) => {
      if (btn.dataset.scopeBound) return;
      btn.dataset.scopeBound = '1';
      btn.addEventListener('click', () => setLeagueScope(btn.dataset.leagueScope));
    });
  }

  function bindRivalClicks() {
    document.querySelectorAll('[data-rival-name]').forEach((el) => {
      el.addEventListener('click', (e) => {
        e.stopPropagation();
        selectRival(el.dataset.rivalName);
      });
    });
  }

  function selectRival(name) {
    selectedRival = name;
    scoreboardOpen = true;
    renderScoreboardBar();
  }

  function closeRivalDetail() {
    selectedRival = null;
    renderScoreboardBar();
  }

  function renderRivalDetail(name) {
    const scope = getLeagueScope();
    const stats = competitorScopedStats(name, scope);
    const prof = stats.prof;
    const scale = Math.round((prof.national_scale || 0.35) * 100);
    const health = Math.round((prof.financial_health || 0.5) * 100);
    const routesHtml = stats.routesInScope.length
      ? `<ul class="list incumbent-list">${stats.routesInScope
          .map(
            (r) =>
              `<li><strong>${r.origin}–${r.dest}</strong> <span class="muted">${r.frequency_week}x/wk · $${r.fare}</span></li>`
          )
          .join('')}</ul>`
      : '<p class="muted">No seeded competitor routes in this scope.</p>';
    const airportsHtml = stats.airportPresence.length
      ? `<ul class="list incumbent-list">${stats.airportPresence
          .map((a) => {
            const ap = airport(a.iata);
            const intel = ap
              ? formatIncumbentIntel(ap, { airline: name, share: a.share, tier: a.tier })
              : '';
            return `<li><strong>${a.iata}</strong> ${a.city} <span class="muted">${(a.share * 100).toFixed(0)}% share</span><br>${intel}</li>`;
          })
          .join('')}</ul>`
      : '<p class="muted">Thin or no incumbent presence in this scope.</p>';

    return `
      <div class="scoreboard-panel-inner rival-detail">
        <button type="button" class="btn secondary rival-back" data-rival-back>← Back to league</button>
        <div class="rival-detail-head">
          ${airlineLogoHtml(name, null, 44)}
          <div>
            <h3>${name}</h3>
            <p class="muted">${leagueScopeLabel(scope)} · ${prof.tier || 'carrier'} · national scale ${scale}%</p>
          </div>
        </div>
        <dl class="stat-dl rival-stats">
          <dt>Est. monthly profit</dt><dd class="${stats.profit >= 0 ? '' : 'danger'}">${fmtMoney(stats.profit)}</dd>
          <dt>Est. monthly riders</dt><dd>${stats.riders.toLocaleString()}</dd>
          <dt>Brand / mindshare</dt><dd>${stats.recognition != null ? Math.round(stats.recognition) : '—'}/100</dd>
          <dt>Scope presence</dt><dd>${Math.round((stats.presence || 0) * 100)}%</dd>
          <dt>Satisfaction (est.)</dt><dd>${stats.csat}</dd>
          <dt>Gross revenue (scope)</dt><dd>${fmtMoney(stats.gross)}</dd>
          <dt>Brand & overhead</dt><dd>${fmtMoney(stats.overhead)}/mo</dd>
          <dt>Financial health</dt><dd>${health}%</dd>
        </dl>
        <p class="muted" style="font-size:0.72rem;margin:10px 0 6px;">
          Presence is scoped — a shuttle can matter in Ohio and vanish nationally. Your rank follows where passengers actually know you.
        </p>
        <h4 class="rival-section-title">Routes in scope</h4>
        ${routesHtml}
        <h4 class="rival-section-title">Airport presence</h4>
        ${airportsHtml}
      </div>`;
  }

  function renderScoreboardBar() {
    const bar = $('scoreboard-bar');
    if (!bar || !state) return;
    ensureMetrics();
    const scope = getLeagueScope();
    const table = buildLeagueTable(scope);
    state.metrics.league_snapshot = table;
    const player = table.find((e) => e.isPlayer) || playerLeagueEntry(scope);
    const region = leagueScopeLabel(scope);
    const profitRank =
      [...table].sort((a, b) => b.profit - a.profit).findIndex((e) => e.isPlayer) + 1;
    const ridersRank =
      [...table].sort((a, b) => b.riders - a.riders).findIndex((e) => e.isPlayer) + 1;
    const csatRank = [...table].sort((a, b) => b.csat - a.csat).findIndex((e) => e.isPlayer) + 1;

    const brand = $('scoreboard-brand');
    if (brand) {
      brand.innerHTML = `
        ${airlineLogoHtml(state.airline_name, state.airline_emblem, 56)}
        <span class="scoreboard-brand-text">
          <strong>${state.airline_name || 'Airline'}</strong>
          <span class="muted">#${player.rank} of ${table.length} · ${region}</span>
        </span>`;
      brand.setAttribute('aria-expanded', scoreboardOpen ? 'true' : 'false');
    }

    let scopeBar = $('scoreboard-scope');
    if (!scopeBar) {
      scopeBar = document.createElement('div');
      scopeBar.id = 'scoreboard-scope';
      scopeBar.className = 'scoreboard-scope';
      scopeBar.setAttribute('aria-label', 'League scope');
      const pillars = $('scoreboard-pillars');
      if (pillars && pillars.parentNode) pillars.parentNode.insertBefore(scopeBar, pillars);
    }
    scopeBar.innerHTML = leagueScopePickerHtml();
    bindLeagueScopeButtons();

    const pillars = $('scoreboard-pillars');
    if (pillars) {
      const profitMeter = Math.max(0, Math.min(100, 50 + player.profit / 40000));
      const riderMeter = Math.min(100, Math.log10(Math.max(10, player.riders)) * 28);
      const csatMeter = Math.max(0, Math.min(100, player.csat));
      const pillarBtn = (key, label, meter, rankLine) =>
        `<button type="button" class="pillar pillar-btn${scoreboardSortBy === key ? ' active' : ''}" data-pillar-sort="${key}" title="${metricLeverTip(key)}" aria-pressed="${scoreboardSortBy === key}">
          <span class="pillar-label">${label}</span>${pillarMeter(meter)}
          <span class="pillar-rank">${rankLine}</span>
        </button>`;
      const rankMeter = Math.max(0, Math.min(100, player.overall || 0));
      pillars.innerHTML =
        pillarBtn('overall', 'Rank', rankMeter, `#${player.rank} of ${table.length}`) +
        pillarBtn('profit', 'Profit', profitMeter, `${fmtMoney(player.profit)}/mo · #${profitRank}`) +
        pillarBtn('riders', 'Riders', riderMeter, `${player.riders.toLocaleString()}/mo · #${ridersRank}`) +
        pillarBtn('csat', 'Satisfaction', csatMeter, `${player.csat} · #${csatRank}`);
    }

    const rivals = $('scoreboard-rivals');
    if (rivals) {
      rivals.innerHTML = table
        .filter((e) => !e.isPlayer)
        .slice(0, 6)
        .map(
          (e) =>
            `<button type="button" class="rival-logo" data-rival-name="${e.name}" title="${e.name} — #${e.rank} · click for intel">${airlineLogoHtml(e.name, null, 28)}</button>`
        )
        .join('');
      bindRivalClicks();
    }

    renderScoreboardPanel(table);
  }

  function renderScoreboardPanel(table) {
    const panel = $('scoreboard-panel');
    if (!panel || !state) return;
    const data = table || buildLeagueTable();
    if (!scoreboardOpen) {
      panel.classList.remove('open');
      panel.innerHTML = '';
      return;
    }
    panel.classList.add('open');
    if (selectedRival) {
      panel.innerHTML = renderRivalDetail(selectedRival);
      const back = panel.querySelector('[data-rival-back]');
      if (back) back.addEventListener('click', closeRivalDetail);
      return;
    }
    const scopeKey = getLeagueScope();
    const scope = leagueScopeLabel(scopeKey);
    const scopeCfg = leagueScopeConfig(scopeKey);
    const player = data.find((e) => e.isPlayer);
    const sorted = sortLeagueByMetric(data, scoreboardSortBy);
    const sortCol = (key, label) =>
      `<th class="${scoreboardSortBy === key ? 'sort-active' : ''}">${label}</th>`;
    const rows = sorted
      .map((e) => {
        const trend =
          e.trend > 0 ? `<span class="trend-up">▲${e.trend}</span>` : e.trend < 0 ? `<span class="trend-down">▼${Math.abs(e.trend)}</span>` : '<span class="muted">—</span>';
        const rowClass = e.isPlayer ? 'you' : 'rival-row';
        const dataAttr = e.isPlayer ? '' : ` data-rival-name="${e.name}"`;
        const hl = (key) => (scoreboardSortBy === key ? ' sort-col' : '');
        const rec = e.recognition != null ? Math.round(e.recognition) : '—';
        return `<tr class="${rowClass}"${dataAttr}>
          <td>${e.rank}</td>
          <td>${airlineLogoHtml(e.name, e.emblem, 26)} <span>${e.name}</span></td>
          <td class="${e.profit < 0 ? 'danger' : ''}${hl('profit')}">${fmtMoney(e.profit)}</td>
          <td class="${hl('riders')}">${e.riders.toLocaleString()}</td>
          <td class="${hl('csat')}">${e.csat}</td>
          <td title="Brand / mindshare in this arena">${rec}</td>
          <td class="${hl('overall')}"><b>${e.overall}</b></td>
          <td>${trend}</td>
        </tr>`;
      })
      .join('');
    const satNote =
      scoreboardSortBy === 'csat'
        ? '<p class="muted" style="font-size:0.72rem;margin-top:8px;"><b>Satisfaction</b> blends reputation, average load factor, and penalties when aircraft are out of service (AOG).</p>'
        : '';
    const standingNote =
      '<p class="muted" style="font-size:0.72rem;margin-top:8px;"><b>#1 is best.</b> Rank is presence-first (riders + brand in this arena). ' +
      'You can be mid-pack in Ohio and near the bottom nationally — same airline, bigger pond. ' +
      'World ranks you against global giants (large foreign airports come later).</p>';
    const recLine =
      player && player.recognition != null
        ? `<p class="muted" style="font-size:0.72rem;margin:0 0 8px;">Your brand in <b>${scope}</b>: recognition <b>${Math.round(player.recognition)}</b>/100 · ops coverage ${((player.opsCoverage || 0) * 100).toFixed(0)}% of airports · field <b>${data.length}</b> carriers</p>`
        : '';
    const worldNote = scopeCfg.note
      ? `<p class="muted" style="font-size:0.72rem;margin:0 0 8px;color:var(--gold);">${scopeCfg.note}</p>`
      : '';
    panel.innerHTML = `
      <div class="scoreboard-panel-inner">
        <h3>League — ${scope} · by ${pillarSortLabel(scoreboardSortBy)}</h3>
        <p class="muted" style="font-size:0.75rem;margin-bottom:6px;">Ranked by <b>${pillarSortLabel(scoreboardSortBy)}</b>. <b>#1 is best.</b> Switch Ohio → Midwest → US → World — your rank should fall until you grow beyond your home markets.</p>
        ${recLine}
        ${worldNote}
        <table class="scoreboard-table">
          <thead><tr><th>#</th><th>Airline</th>${sortCol('profit', 'Profit/mo')}${sortCol('riders', 'Riders/mo')}${sortCol('csat', 'Sat.')}<th>Brand</th>${sortCol('overall', 'Standing')}<th>Trend</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
        <p class="muted" style="font-size:0.72rem;margin-top:10px;"><b>Levers:</b> fly + market where you want to be known. Brand dilutes outside airports you serve.</p>
        ${standingNote}
        ${satNote}
        ${yourRoutesRankHtml(scoreboardSortBy)}
      </div>`;
    bindRivalClicks();
  }

  function toggleScoreboard() {
    scoreboardOpen = !scoreboardOpen;
    if (!scoreboardOpen) selectedRival = null;
    renderScoreboardBar();
  }

  function normalizeGameState() {
    if (!state) return;
    sanitizeAirportGateCounts();
    state.fleet = Array.isArray(state.fleet) ? state.fleet : [];
    state.gates = Array.isArray(state.gates) ? state.gates : [];
    state.routes = Array.isArray(state.routes) ? state.routes : [];
    state.debt = Array.isArray(state.debt) ? state.debt : [];
    state.bonds = Array.isArray(state.bonds) ? state.bonds : [];
    state.events = Array.isArray(state.events) ? state.events : [];
    state.milestones = Array.isArray(state.milestones) ? state.milestones : [];
    state.raises = Array.isArray(state.raises) ? state.raises : [];
    state.ops_goals_done = Array.isArray(state.ops_goals_done) ? state.ops_goals_done : [];
    if (state.personal_cash == null || !Number.isFinite(state.personal_cash)) state.personal_cash = 0;
    if (state.seed_done == null) state.seed_done = false;
    if (state.series_a_done == null) state.series_a_done = false;
    if (state.growth_equity_done == null) state.growth_equity_done = false;
    if (state.pe_done == null) state.pe_done = false;
    if (state.ipo_done == null) state.ipo_done = !!state.public;
    if (state.public == null) state.public = !!state.ipo_done;
    if (state.starter_route_count == null) {
      state.starter_route_count = state.milestones.includes('first_route') ? 0 : state.routes.length;
    }
    if (state.positive_day_streak == null) state.positive_day_streak = 0;
    if (state.ff_month_confirmed == null) state.ff_month_confirmed = false;
    state.revenue_history = Array.isArray(state.revenue_history) ? state.revenue_history : [];
    state.marketing_spend_monthly = state.marketing_spend_monthly || {};
    state.brand_awareness = state.brand_awareness || {};
    // Infer raises already taken from equity below 100 on older saves
    if (!state.seed_done && (state.equity_pct || 100) < 95 && state.financing_tier === 'startup') {
      state.seed_done = true;
    }
    ensureMarketingInvestments();
    if (!Number.isFinite(state.fuel_price)) {
      state.fuel_price = bootstrap.fuel_base || 2.85;
    }
    if (state.hour == null) state.hour = 8;
    if (!state.player_name) state.player_name = 'CEO';
    if (!state.airline_emblem) state.airline_emblem = 'wing';
    if (!state.ancillary_strategy) state.ancillary_strategy = 'auto';
    if (!state.gate_nudge_day) state.gate_nudge_day = {};
    ensureMetrics();
    ensureMacro();
    ensureFleet();
    ensureWinningPlaybook();
  }

  function ensureFleet() {
    if (!state || !state.fleet) return;
    state.fleet.forEach((f) => {
      if (!f.id) f.id = uid('ac');
      const ac = aircraftType(f.type);
      if (!ac) return;
      if (f.seats == null) f.seats = ac.seats;
      if (f.leased == null) f.leased = true;
      ensurePlaneTelemetry(f);
    });
    (state.routes || []).forEach((r) => {
      if (!r.aircraft_id && state.fleet.length) {
        const match = state.fleet.find((f) => f.type === r.aircraft_type);
        if (match) r.aircraft_id = match.id;
      }
      if (!r.fare_mode) r.fare_mode = 'auto';
      if (!Number.isFinite(r.fare)) {
        r.fare = marketFareForPair(r.origin, r.dest, r.aircraft_type);
      }
      if (!r.ancillary_mode) r.ancillary_mode = 'auto';
      backfillRouteForecast(r);
    });
    if (state.last_reactive_competitor_day == null) state.last_reactive_competitor_day = 0;
    if (!state.competitor_markets) initCompetitorMarkets();
    if (!state.competitor_routes) initCompetitorRoutes();
    if (state.last_competitor_event_day == null) state.last_competitor_event_day = 0;
    if (!state.airport_demand_surges) state.airport_demand_surges = {};
    if (state.onboarding_done == null) state.onboarding_done = true;
    if (state.ff_year_confirmed == null) state.ff_year_confirmed = false;
    if (state.chapter11 == null) state.chapter11 = { active: false };
    if (!Array.isArray(state.pnl_history)) state.pnl_history = [];
  }

  function mergeAirportsFromBootstrap() {
    if (!initialAirports || !bootstrap.airports) return;
    const byIata = Object.fromEntries(bootstrap.airports.map((a) => [a.iata, a]));
    initialAirports.forEach((ap) => {
      if (!byIata[ap.iata]) bootstrap.airports.push(JSON.parse(JSON.stringify(ap)));
    });
  }

  function computeCountryHealth() {
    if (!state || !state.macro) return 72;
    const m = state.macro;
    let score = 68;
    score += m.gdp_growth_pct * 3.5;
    score += Math.min(3, m.travel_spend_growth_pct) * 2.5;
    score -= Math.max(0, m.inflation_pct - 3.5) * 4;
    score -= Math.max(0, 2 - m.inflation_pct) * 1.5;
    score -= Math.max(0, -m.travel_spend_growth_pct) * 5;
    return clampPct(score, 25, 100);
  }

  function macroDemandMultiplier() {
    ensureMacro();
    const m = state.macro;
    const gdpFactor = Math.pow(m.gdp_index / 100, 0.55);
    const travelFactor = Math.pow(m.travel_spend_index / 100, 0.75);
    const healthFactor = 0.65 + (m.country_health / 100) * 0.45;
    return gdpFactor * travelFactor * healthFactor;
  }

  /**
   * OTA demand/revenue effects.
   * opts.draftOta — Route Studio draft { [platformId]: { list, feature, hubPush } }
   * treats draft list as if already listed for projection.
   */
  function otaEffects(opts) {
    opts = opts || {};
    ensureMacro();
    const m = state.macro;
    const draftOta = opts.draftOta || null;
    const penetration = m.ota_market_penetration_pct / 100;
    let demandBoost = 1;
    let revenueMult = 1;
    let marketingAmplify = 1;
    let listingCost = 0;

    (bootstrap.ota_platforms || []).forEach((p) => {
      const draftList = !!(draftOta && draftOta[p.id] && draftOta[p.id].list);
      if (!m.ota_listed[p.id] && !draftList) return;
      let fee = p.listing_monthly;
      const promo = m.ota_promo && m.ota_promo[p.id];
      if (promo && promo.months_left > 0) fee *= 1 - (promo.discount || 0);
      listingCost += fee;
      const share = penetration * p.demand_reach;
      demandBoost += share;
      revenueMult *= 1 - (p.commission_pct / 100) * share * 0.85;
      marketingAmplify = Math.max(marketingAmplify, p.marketing_amplify || 1);
    });

    return {
      demandMult: demandBoost,
      revenueMult: Math.max(0.72, revenueMult),
      marketingAmplify,
      listingCost,
    };
  }

  function otaListingMonthly() {
    return otaEffects().listingCost;
  }

  function advanceMacroYear() {
    ensureMacro();
    const m = state.macro;
    m.inflation_pct = clampPct(
      m.inflation_pct + (Math.random() - 0.48) * 1.8,
      -2,
      6
    );
    m.gdp_growth_pct = clampPct(
      1.2 + (Math.random() - 0.4) * 2.2 + m.inflation_pct * 0.15,
      -1.5,
      5.5
    );
    m.gdp_index *= 1 + m.gdp_growth_pct / 100;

    m.travel_spend_growth_pct = clampPct(
      m.gdp_growth_pct * 0.85 + (Math.random() - 0.35) * 2.4,
      -4,
      7
    );
    m.travel_spend_index *= 1 + m.travel_spend_growth_pct / 100;

    m.ota_market_penetration_pct = clampPct(
      m.ota_market_penetration_pct + (Math.random() - 0.42) * 4,
      52,
      90
    );

    state.gates.forEach((g) => {
      g.monthly = Math.round(g.monthly * (1 + m.inflation_pct / 100));
    });

    m.country_health = computeCountryHealth();
    const yearN = Math.floor(state.day / 365);
    const trail30 = (state.pnl_history || []).reduce((a, b) => a + b, 0);
    const table = buildLeagueTable();
    const player = table.find((e) => e.isPlayer);
    const rankNote = player ? ` · league <b>#${player.rank}</b>` : '';
    pushEvent(
      `Year ${yearN} scorecard — trailing 30d P&L <b class="${trail30 >= 0 ? '' : 'danger'}">${fmtMoney(trail30)}</b>, ` +
        `<b>${state.routes.length}</b> routes, cash <b>${fmtMoney(state.cash)}</b>${rankNote}. ` +
        `Macro: inflation ${m.inflation_pct.toFixed(1)}%, GDP ${m.gdp_growth_pct >= 0 ? '+' : ''}${m.gdp_growth_pct.toFixed(1)}%, ` +
        `travel ${m.travel_spend_growth_pct >= 0 ? '+' : ''}${m.travel_spend_growth_pct.toFixed(1)}%, health ${m.country_health.toFixed(0)}/100`,
      trail30 > 0 ? 'good' : 'neutral'
    );
  }

  function updateFuelPrice() {
    ensureMacro();
    const m = state.macro;
    const inflWeekly = m.inflation_pct / 100 / 52;
    const gdpPressure = Math.max(0, m.gdp_growth_pct / 100) * 0.004;
    const marketNoise = (Math.random() - 0.5) * 0.06;
    const healthRelief = m.country_health < 50 ? 0.01 : 0;
    state.fuel_price = Math.max(
      1.45,
      state.fuel_price * (1 + inflWeekly + gdpPressure - healthRelief * 0.5 + marketNoise)
    );
  }

  function toggleOtaListing(platformId) {
    ensureMacro();
    const p = (bootstrap.ota_platforms || []).find((x) => x.id === platformId);
    if (!p) return;
    const next = !state.macro.ota_listed[platformId];
    if (next && state.cash < p.listing_monthly) {
      alert(`Need ~${fmtMoney(p.listing_monthly)} for first month on ${p.name}.`);
      return;
    }
    state.macro.ota_listed[platformId] = next;
    pushEvent(next ? `Listed on ${p.name} (OTA channel).` : `Removed listing from ${p.name}.`);
    saveGame();
    renderAll();
  }

  function pushEvent(msg, tier) {
    state.events.unshift({ day: state.day, msg, tier: tier || 'neutral' });
    if (state.events.length > 80) state.events.length = 80;
    if (tier === 'good' || tier === 'milestone') showEventToast(msg, tier);
  }

  function showEventToast(msg, tier) {
    const stack = document.getElementById('event-toast-stack');
    if (!stack) return;
    const el = document.createElement('div');
    el.className = `event-toast ${tier}`;
    el.innerHTML = msg;
    stack.appendChild(el);
    setTimeout(() => el.remove(), 4200);
    while (stack.children.length > 3) stack.removeChild(stack.firstChild);
  }

  /** Monthly interest accrual on a loan (balance-sheet / P&L). */
  function debtMonthInterest(d) {
    if (!d || !(d.principal > 0)) return 0;
    return (d.principal || 0) * (d.rate || 0) / 12;
  }

  /**
   * Split this month's scheduled payment into interest vs principal.
   * Amortizing loans: payment covers interest first, remainder pays principal down.
   */
  function debtMonthPaymentSplit(d) {
    const principal = Math.max(0, d && d.principal ? d.principal : 0);
    if (principal <= 0) return { interest: 0, principal: 0, total: 0 };
    const interest = debtMonthInterest(d);
    const scheduled =
      d.monthly_payment != null && d.monthly_payment > 0
        ? d.monthly_payment
        : interest; // interest-only if no schedule
    // Cap total at interest + remaining principal (final month)
    let total = Math.min(scheduled, interest + principal);
    // Always recognize full interest expense even if schedule is oddly low
    if (total < interest) total = interest;
    let prinPay = Math.max(0, total - interest);
    if (prinPay > principal) {
      prinPay = principal;
      total = interest + prinPay;
    }
    return { interest, principal: prinPay, total };
  }

  function monthlyDebtService() {
    return (state.debt || []).reduce((s, d) => s + debtMonthPaymentSplit(d).total, 0);
  }

  function monthlyDebtInterestOnly() {
    return (state.debt || []).reduce((s, d) => s + debtMonthInterest(d), 0);
  }

  /** Month-end: cash out for debt service; principal declines; log I+P split. */
  function applyMonthlyDebtService() {
    if (!state || !(state.debt || []).length) {
      state.debt_month = { interest: 0, principal: 0, total: 0, day: state.day };
      return;
    }
    let totalInt = 0;
    let totalPrin = 0;
    let totalPay = 0;
    (state.debt || []).forEach((d) => {
      if (!(d.principal > 0)) return;
      const split = debtMonthPaymentSplit(d);
      state.cash -= split.total;
      d.principal = Math.max(0, (d.principal || 0) - split.principal);
      d.last_interest = split.interest;
      d.last_principal = split.principal;
      d.last_payment = split.total;
      if (d.months_left != null) d.months_left = Math.max(0, d.months_left - 1);
      totalInt += split.interest;
      totalPrin += split.principal;
      totalPay += split.total;
    });
    const before = state.debt.length;
    state.debt = state.debt.filter((d) => (d.principal || 0) > 1);
    state.debt_month = {
      interest: totalInt,
      principal: totalPrin,
      total: totalPay,
      day: state.day,
    };
    if (totalPay > 0) {
      pushEvent(
        `Debt service paid: <b>${fmtMoney(totalPay)}</b> (` +
          `<b>${fmtMoney(totalInt)}</b> interest · <b>${fmtMoney(totalPrin)}</b> principal).`,
        totalPrin > 0 ? 'good' : 'bad'
      );
    }
    if (state.debt.length < before) {
      pushEvent('A loan was fully amortized — principal retired.', 'milestone');
    }
    checkScenarioGoal();
  }

  function quarterlyBondCoupons() {
    return state.bonds.reduce((s, b) => s + (b.principal * b.coupon) / 4, 0);
  }

  /** Enterprise valuation for PE / IPO term sheets. */
  function companyEnterpriseValue() {
    const nw = computeNetWorthBreakdown() || { total: 0 };
    const ltm = state.ltm_revenue || 0;
    const mult =
      state.public || state.ipo_done
        ? 1.35
        : state.financing_tier === 'serial'
          ? 1.9
          : state.pe_done
            ? 1.6
            : 1.25;
    const fromLtm = ltm * mult;
    const fromNw = (nw.total || 0) * 1.08;
    return Math.max(fromLtm, fromNw, (state.cash || 0) * 1.05, 1_000_000);
  }

  function founderStakeValue() {
    return companyEnterpriseValue() * ((state.equity_pct || 0) / 100);
  }

  function fleetMonthlyCosts() {
    return state.fleet.reduce((s, f) => {
      const ac = aircraftType(f.type);
      if (!ac) return s;
      if (f.leased) return s + planeLeaseMonthly(f);
      return s + planeMaintMonthly(f);
    }, 0);
  }

  function gateLeaseMonthly() {
    return state.gates.reduce((s, g) => s + g.monthly, 0);
  }

  function marketingMonthly() {
    return (
      Object.values(state.marketing_spend_monthly).reduce((a, b) => a + clampMoney(b), 0) +
      scopedMarketingMonthly() +
      hubOtaMonthlyCost() +
      routeOtaFeatureMonthlyCost()
    );
  }

  function cashInterestAnnualRate() {
    ensureMacro();
    const infl = state.macro.inflation_pct / 100;
    return Math.max(0.0025, infl * 0.85 + 0.004);
  }

  function accrueCashInterest(dayFraction) {
    if (!state || state.cash <= 0 || dayFraction <= 0) return 0;
    const earned = state.cash * (cashInterestAnnualRate() / 365) * dayFraction;
    state.cash += earned;
    return earned;
  }

  function isCommonRoutePair(a, b) {
    const pairs = bootstrap.common_route_pairs || [];
    return pairs.some(([x, y]) => (x === a && y === b) || (x === b && y === a));
  }

  function recommendAircraftTypeForPair(originIata, destIata) {
    const o = airport(originIata);
    const d = airport(destIata);
    if (!o || !d) return 'e175';
    const dist = haversineNm(o.lat, o.lon, d.lat, d.lon);
    const pop = Math.sqrt(o.metro_pop_m * d.metro_pop_m);
    const regional =
      o.regional || d.regional || o.metro_pop_m < 2.5 || d.metro_pop_m < 2.5;
    let order;
    if (regional || pop < 1.2) order = ['pc12', 'e145', 'e175', 'a320', 'b737'];
    else if (pop < 3.5) order = ['e145', 'e175', 'a320', 'b737', 'pc12'];
    else if (pop < 8) order = ['e175', 'a320', 'b737', 'e145', 'pc12'];
    else order = ['a320', 'b737', 'e175', 'e145', 'pc12'];
    for (const tid of order) {
      const ac = aircraftType(tid);
      if (ac && dist <= ac.range_nm) return tid;
    }
    return 'e175';
  }

  function suggestFareForPair(originIata, destIata, acTypeId) {
    const acType = acTypeId || recommendAircraftTypeForPair(originIata, destIata);
    return marketFareForPair(originIata, destIata, acType);
  }

  function estimateRouteViability(originIata, destIata, aircraftTypeId, freq, fare, aircraftId, demandOpts) {
    const ac = aircraftType(aircraftTypeId);
    if (!ac) return { label: 'Unknown', tier: 'bad', load: 0, dailyPax: 0 };
    const mock = {
      origin: originIata,
      dest: destIata,
      aircraft_type: aircraftTypeId,
      aircraft_id: aircraftId,
      frequency_week: freq,
      fare,
      featured_ota: (demandOpts && demandOpts.featured_ota) || undefined,
    };
    if (demandOpts && demandOpts.draftOta) {
      const featured = [];
      Object.keys(demandOpts.draftOta).forEach((pid) => {
        if (demandOpts.draftOta[pid] && demandOpts.draftOta[pid].feature) featured.push(pid);
      });
      if (featured.length) mock.featured_ota = featured;
    }
    const dOpts = {
      isProposed: !state.routes.some((r) => r.origin === originIata && r.dest === destIata),
      proposedFreq: freq,
      ...(demandOpts || {}),
    };
    let demand = demandForRoute(mock, dOpts);
    // Note: common-pair boost is already applied inside demandForRoute (×1.18).
    // Do not double-apply here — judgment must match live sim.
    const mkt = routeMarketContext(mock, { isProposed: true, proposedFreq: freq, excludeRouteId: null });
    const plane = aircraftId ? state.fleet.find((f) => f.id === aircraftId) : null;
    const seats = plane ? fleetSeatCount(plane) : ac.seats_max || ac.seats;
    const schedScale = aircraftId ? planeScheduleScaleForRoute(aircraftId, mock) : 1;
    const effectiveFreq = freq * schedScale;
    const dailySeats = seats * (effectiveFreq / 7);
    const load = Math.min(0.95, demand / Math.max(dailySeats, 1));
    const dailyPax = Math.floor(dailySeats * load);
    let label = 'Poor fit';
    let tier = 'bad';
    if (load >= 0.72) {
      label = 'Strong demand';
      tier = 'good';
    } else if (load >= 0.45) {
      label = 'Moderate';
      tier = 'ok';
    } else if (load >= 0.22) {
      label = 'Thin';
      tier = 'warn';
    }
    if ((ac.seats_max || ac.seats) >= 150 && load < 0.35) {
      label = 'Too much aircraft';
      tier = 'bad';
    }
    return {
      label,
      tier,
      load,
      dailyPax,
      seats,
      schedScale,
      effectiveFreq,
      market: mkt,
      originSharePct: (mkt.originShare * 100).toFixed(1),
      pairSharePct: (mkt.pairCapacityShare * 100).toFixed(1),
      capturePct: (mkt.captureFactor * 100).toFixed(1),
    };
  }

  /**
   * Directional demand for a city pair: outbound may fill hard while the return
   * is thinner (or vice versa). Planes still need to get home — RT economics
   * matter more than a single leg's load factor.
   */
  function estimateDirectionalPair(originIata, destIata, aircraftTypeId, freq, fare, aircraftId) {
    const out = estimateRouteViability(originIata, destIata, aircraftTypeId, freq, fare, aircraftId);
    const retFare = suggestFareForPair(destIata, originIata, aircraftTypeId);
    const ret = estimateRouteViability(
      destIata,
      originIata,
      aircraftTypeId,
      freq,
      retFare,
      aircraftId
    );
    const outLoad = out.load || 0;
    const retLoad = ret.load || 0;
    const rtAvgLoad = (outLoad + retLoad) / 2;
    // Empty ferry: full cost of the reverse leg, zero revenue
    const ferryAvgLoad = outLoad * 0.5;
    const stronger = outLoad >= retLoad ? 'out' : 'ret';
    const strongerLoad = Math.max(outLoad, retLoad);
    const weakerLoad = Math.min(outLoad, retLoad);
    // Worth flying RT even if one side is soft, if average clears ~42% or the
    // strong leg is excellent and the weak leg is not a disaster.
    const worthRt =
      rtAvgLoad >= 0.42 || (strongerLoad >= 0.7 && weakerLoad >= 0.3) || (strongerLoad >= 0.85 && weakerLoad >= 0.22);
    const imbalanced = Math.abs(outLoad - retLoad) >= 0.18;
    let directionNote = '';
    let prompt = '';
    if (imbalanced && stronger === 'out') {
      directionNote = `Out ${Math.round(outLoad * 100)}% · return ${Math.round(retLoad * 100)}%`;
      prompt = worthRt
        ? `Strong ${originIata}→${destIata}; thinner return is still worth selling seats home (don't ferry empty).`
        : `Demand is one-way heavy ${originIata}→${destIata}. Soften fare on the return or fly fewer RT days.`;
    } else if (imbalanced && stronger === 'ret') {
      directionNote = `Out ${Math.round(outLoad * 100)}% · return ${Math.round(retLoad * 100)}%`;
      prompt = worthRt
        ? `Stronger demand ${destIata}→${originIata}. Launch both ways — outbound may be softer but RT still works.`
        : `Return demand (${destIata}→${originIata}) is better. Consider starting service from ${destIata} if you have a gate.`;
    } else {
      directionNote = `Both ways ~${Math.round(rtAvgLoad * 100)}%`;
      prompt = worthRt
        ? `Balanced pair — sell seats both directions (avoids empty ferry).`
        : `Thin both ways — smaller metal, lower fare, or skip for now.`;
    }
    // Score favors RT-average load, with a bonus for balanced pairs and common routes
    const balanceBonus = imbalanced ? 0.92 : 1.05;
    const rtScore = rtAvgLoad * balanceBonus * (worthRt ? 1.12 : 0.85);

    return {
      out,
      ret,
      outLoad,
      retLoad,
      outDailyPax: out.dailyPax || 0,
      retDailyPax: ret.dailyPax || 0,
      retFare,
      rtAvgLoad,
      ferryAvgLoad,
      stronger,
      worthRt,
      imbalanced,
      directionNote,
      prompt,
      rtScore,
    };
  }

  function directionalLoadChipsHtml(origin, dest, dir) {
    if (!dir) return '';
    const outPct = Math.round((dir.outLoad || 0) * 100);
    const retPct = Math.round((dir.retLoad || 0) * 100);
    const outCls = outPct >= 72 ? 'good' : outPct >= 45 ? 'ok' : 'warn';
    const retCls = retPct >= 72 ? 'good' : retPct >= 45 ? 'ok' : 'warn';
    const flag = dir.worthRt
      ? '<span class="dir-flag worth">RT worth it</span>'
      : '<span class="dir-flag thin">RT thin</span>';
    return `<span class="dir-loads" title="${(dir.prompt || '').replace(/"/g, "'")}">
      <span class="dir-chip via-${outCls}">${origin}→${dest} ${outPct}%</span>
      <span class="dir-chip via-${retCls}">${dest}→${origin} ${retPct}%</span>
      ${flag}
    </span>`;
  }

  function routeSuggestionsFrom(originIata) {
    if (!originIata || !state) return [];
    const o = airport(originIata);
    if (!o) return [];
    const suggestions = [];
    bootstrap.airports.forEach((dest) => {
      if (dest.iata === originIata) return;
      const dist = Math.round(haversineNm(o.lat, o.lon, dest.lat, dest.lon));
      const acType = recommendAircraftTypeForPair(originIata, dest.iata);
      const ac = aircraftType(acType);
      if (!ac || dist > ac.range_nm) return;
      const freq = dist < 350 ? 14 : 7;
      const fare = suggestFareForPair(originIata, dest.iata, acType);
      const assignPlane =
        state.fleet.find((f) => maxFrequencyForAircraft(f.id, originIata, dest.iata, acType) >= freq) ||
        state.fleet[0];
      const planeId = assignPlane ? assignPlane.id : null;
      const via = estimateRouteViability(originIata, dest.iata, acType, freq, fare, planeId);
      const dir = estimateDirectionalPair(originIata, dest.iata, acType, freq, fare, planeId);
      const common = isCommonRoutePair(originIata, dest.iata);
      // Prefer RT-profitable pairs (not just one hot outbound)
      const cap =
        (dir.out && dir.out.market && dir.out.market.captureFactor) || 0;
      const score =
        dir.rtScore * (common ? 1.15 : 1) * ((dest.annual_pax_m || 0) + 1) * (1 + cap * 0.3);
      suggestions.push({
        dest: dest.iata,
        destCity: dest.city,
        dist,
        acType,
        acName: ac.name,
        freq,
        fare,
        common,
        score,
        dir,
        directionNote: dir.directionNote,
        directionPrompt: dir.prompt,
        outLoad: dir.outLoad,
        retLoad: dir.retLoad,
        rtAvgLoad: dir.rtAvgLoad,
        worthRt: dir.worthRt,
        ...via,
      });
    });
    return suggestions.sort((a, b) => b.score - a.score).slice(0, 8);
  }

  function burnMonthly() {
    return (
      fleetMonthlyCosts() +
      gateLeaseMonthly() +
      marketingMonthly() +
      otaListingMonthly() +
      monthlyDebtService() +
      quarterlyBondCoupons() / 3
    );
  }

  function runwayMonths() {
    const burn = burnMonthly();
    if (burn <= 0) return 99;
    return state.cash / burn;
  }

  function routeDistance(route) {
    const o = airport(route.origin);
    const d = airport(route.dest);
    if (!o || !d) return Infinity;
    return haversineNm(o.lat, o.lon, d.lat, d.lon);
  }

  /**
   * One-way block hours (taxi + cruise + pad). Round-trips are 2× this when both
   * legs fly, or ferry return adds a second one-way when no reverse route exists.
   */
  function blockHours(distNm, ac) {
    const cruiseKt = (ac && ac.cruise_kts) || 420;
    const cruise = (distNm || 0) / cruiseKt;
    return cleanHours(Math.max(0.55, cruise + 0.4));
  }

  function findReverseRoute(route, excludeId) {
    if (!route || !state) return null;
    return (state.routes || []).find(
      (r) =>
        r.id !== route.id &&
        r.id !== excludeId &&
        r.origin === route.dest &&
        r.dest === route.origin
    );
  }

  function hasReturnLeg(route) {
    return !!findReverseRoute(route);
  }

  function airportMarketDeparturesDaily(ap) {
    const E = RunwayEcon();
    if (E) return E.airportMarketDeparturesDaily(ap, routeEconomics());
    if (!ap) return 50;
    if (ap.market_departures_daily > 0) return ap.market_departures_daily;
    return 50;
  }

  function airportMarketDeparturesWeekly(ap) {
    const E = RunwayEcon();
    if (E) return E.airportMarketDeparturesWeekly(ap, routeEconomics());
    if (!ap) return 300;
    if (ap.market_departures_weekly > 0) return ap.market_departures_weekly;
    return airportMarketDeparturesDaily(ap) * (ap.operating_days_per_week || 6);
  }

  function competitorDeparturesWeeklyFrom(iata) {
    return (state.competitor_routes || [])
      .filter((r) => r.origin === iata)
      .reduce((s, r) => s + (r.frequency_week || 0), 0);
  }

  function totalMarketDeparturesWeeklyAt(iata) {
    const ap = airport(iata);
    if (!ap) return 100;
    const fromTraffic = airportMarketDeparturesWeekly(ap);
    const fromSeededRivals = competitorDeparturesWeeklyFrom(iata);
    const buf = routeEconomics().rival_traffic_buffer || 1.12;
    return Math.max(fromTraffic, Math.round(fromSeededRivals * buf));
  }

  function playerDeparturesWeeklyFrom(iata, excludeRouteId, addWeekly) {
    let sum = 0;
    (state.routes || []).forEach((r) => {
      if (r.origin !== iata || r.id === excludeRouteId) return;
      const plane = r.aircraft_id ? state.fleet.find((f) => f.id === r.aircraft_id) : null;
      const scale = plane ? planeScheduleScaleForRoute(plane.id, r) : 1;
      sum += (r.frequency_week || 0) * scale;
    });
    return sum + (addWeekly || 0);
  }

  function competitorWeeklyOnPair(origin, dest) {
    return (state.competitor_routes || []).reduce((s, cr) => {
      const match =
        (cr.origin === origin && cr.dest === dest) || (cr.origin === dest && cr.dest === origin);
      return match ? s + (cr.frequency_week || 0) : s;
    }, 0);
  }

  function imputedPairMarketWeekly(origin, dest) {
    const o = airport(origin);
    const d = airport(dest);
    if (!o || !d) return 6;
    const dist = haversineNm(o.lat, o.lon, d.lat, d.lon);
    const E = RunwayEcon();
    if (E) return E.imputedPairMarketWeekly(o, d, dist, routeEconomics());
    return 6;
  }

  function routeMarketContext(route, opts) {
    opts = opts || {};
    const excludeRouteId = opts.excludeRouteId || route.id;
    const proposedFreq = opts.proposedFreq != null ? opts.proposedFreq : route.frequency_week || 0;
    const plane = route.aircraft_id ? state.fleet.find((f) => f.id === route.aircraft_id) : null;
    const schedScale = plane ? planeScheduleScaleForRoute(plane.id, route, excludeRouteId) : 1;
    const effectivePlayerFreq = proposedFreq * schedScale;

    const originMarket = totalMarketDeparturesWeeklyAt(route.origin);
    const destMarket = totalMarketDeparturesWeeklyAt(route.dest);
    const playerOriginDeps = playerDeparturesWeeklyFrom(
      route.origin,
      excludeRouteId,
      opts.isProposed ? effectivePlayerFreq : 0
    );
    const playerDestDeps = playerDeparturesWeeklyFrom(route.dest, excludeRouteId, 0);

    const compPair = competitorWeeklyOnPair(route.origin, route.dest);
    const imputedPair = imputedPairMarketWeekly(route.origin, route.dest);
    const playerOriginDepsCurrent = playerDeparturesWeeklyFrom(route.origin, excludeRouteId, 0);
    const E = RunwayEcon();
    const brandO = state.brand_awareness[route.origin] || 5;
    const brandD = state.brand_awareness[route.dest] || 5;
    const mature =
      !!route.established ||
      isCommonRoutePair(route.origin, route.dest) ||
      (brandO + brandD) / 2 >= 40;
    const cap = E
      ? E.computeMarketCapture(
          {
            playerOriginDeps,
            originMarketWeekly: originMarket,
            destMarketWeekly: destMarket,
            playerDestDeps,
            effectivePlayerFreq,
            compPairWeekly: compPair,
            imputedPairWeekly: imputedPair,
            reputation: state.reputation || 0,
            brandAwareOrigin: brandO,
            brandAwareDest: brandD,
            mature,
          },
          routeEconomics()
        )
      : null;
    const originShare = cap ? cap.originShare : playerOriginDeps / Math.max(1, originMarket);
    const destShare = cap ? cap.destShare : playerDestDeps / Math.max(1, destMarket);
    const pairCapacityShare = cap ? cap.pairCapacityShare : effectivePlayerFreq / Math.max(1, effectivePlayerFreq + compPair + imputedPair);
    const capture = cap ? cap.captureFactor : 0.1;

    const oAp = airport(route.origin);
    const dAp = airport(route.dest);

    return {
      origin: route.origin,
      dest: route.dest,
      originMarketWeekly: originMarket,
      destMarketWeekly: destMarket,
      originMarketDaily: oAp ? airportMarketDeparturesDaily(oAp) : 0,
      destMarketDaily: dAp ? airportMarketDeparturesDaily(dAp) : 0,
      playerOriginDeps,
      playerOriginDepsCurrent,
      playerDestDeps,
      originShare,
      destShare,
      effectivePlayerFreq,
      schedScale,
      compPairWeekly: compPair,
      imputedPairWeekly: imputedPair,
      pairCapacityShare,
      captureFactor: capture,
      bottleneck:
        originShare < pairCapacityShare * 0.45
          ? 'airport_presence'
          : schedScale < 0.92
            ? 'aircraft_hours'
            : pairCapacityShare < originShare * 0.45
              ? 'route_competition'
              : 'balanced',
    };
  }

  function routeMarketCaptureFactor(route, opts) {
    return routeMarketContext(route, opts).captureFactor;
  }

  function demandForRoute(route, opts) {
    opts = opts || {};
    const o = airport(route.origin);
    const d = airport(route.dest);
    const ac = aircraftType(route.aircraft_type);
    if (!o || !d || !ac) return 0;
    const dist = routeDistance(route);
    if (dist > ac.range_nm) return 0;

    const wealth = (airportWealth(o) + airportWealth(d)) / 2;
    const luxury = (airportLuxury(o) + airportLuxury(d)) / 2;
    const regionalBoost = (o.regional || d.regional) && isSmallAircraft(route.aircraft_type) ? 1.22 : 1;
    const wealthBoost = 0.72 + wealth * 0.55;
    const luxuryBoost = 1 + luxury * 0.35;
    // Short hops (CMH–DAY etc.) have denser O-D demand than long thin routes.
    const shortHopBoost = dist < 180 ? 2.35 : dist < 350 ? 1.55 : dist < 600 ? 1.15 : 1;
    const base =
      Math.sqrt(Math.max(0.15, o.metro_pop_m) * Math.max(0.15, d.metro_pop_m)) *
      1450 *
      regionalBoost *
      wealthBoost *
      luxuryBoost *
      shortHopBoost;
    const compPenalty =
      1 -
      (incumbentPressure(o) +
        incumbentPressure(d) +
        competitorFarePressure(o) +
        competitorFarePressure(d)) *
        0.28;
    const hubPenalty = Math.max(0.55, compPenalty);
    const awareO = (state.brand_awareness[route.origin] || 5) / 100;
    const awareD = (state.brand_awareness[route.dest] || 5) / 100;
    const marketing =
      (0.55 + (awareO + awareD) / 2) *
      marketingDemandBonus(route.origin, route.dest, opts);
    const rep = 1 + state.reputation / 200;
    const fareFactor = fareDemandFactor(route, o, d);
    const overlap = 1 - competitorRouteOverlapPenalty(route) * 0.72;
    const reliability = (o.seasonal_reliability + d.seasonal_reliability) / 2;
    const macro = macroDemandMultiplier();
    const ota = otaEffects(opts);
    const plane = route.aircraft_id ? state.fleet.find((f) => f.id === route.aircraft_id) : null;
    // Cabin density: roomier configs (fewer seats) lift comfort / willingness-to-fly
    const comfortRating = plane ? planeComfortRating(plane) : ac.comfort_rating || 3;
    const comfortFactor = 0.82 + (comfortRating / 5) * 0.38;
    const marketCapture = routeMarketCaptureFactor(route, opts);

    const surge = Math.max(airportDemandSurgeMult(route.origin), airportDemandSurgeMult(route.dest));

    let demand =
      base *
      hubPenalty *
      overlap *
      marketing *
      rep *
      fareFactor *
      reliability *
      macro *
      ota.demandMult *
      comfortFactor *
      marketCapture *
      surge;
    if (isCommonRoutePair(route.origin, route.dest)) demand *= 1.18;
    if (route.established) demand *= 1.12;
    // Return leg on a pair you already fly outbound — some traffic already knows you.
    if (hasReturnLeg(route)) demand *= 1.08;
    (route.featured_ota || []).forEach((pid) => {
      const p = (bootstrap.ota_platforms || []).find((x) => x.id === pid);
      if (p) demand *= 1 + (p.demand_reach || 0.1) * 0.45;
    });
    // Live hub push, or draft hub push from Route Studio
    const hubPushIds = new Set(
      (state.hub_ota_push && state.hub_ota_push[route.origin]) || []
    );
    if (opts.draftOta) {
      Object.keys(opts.draftOta).forEach((pid) => {
        if (opts.draftOta[pid] && opts.draftOta[pid].hubPush) hubPushIds.add(pid);
      });
    }
    hubPushIds.forEach((pid) => {
      const p = (bootstrap.ota_platforms || []).find((x) => x.id === pid);
      if (p) demand *= 1 + (p.demand_reach || 0.08) * 0.35;
    });

    // Flight product specialty (feeder, leisure, essential, etc.)
    const prod = routeProduct(routeProductId(route));
    demand *= prod.demandMult != null ? prod.demandMult : 1;
    demand *= productSeasonalMult(prod, state.day);
    if (prod.loadFloor && demand < prod.loadFloor * Math.max(dailySeatsHint(route, opts), 1)) {
      // soft floor applied later via load; here boost thin essential/feeder demand slightly
      demand = Math.max(demand, prod.loadFloor * 12);
    }
    return demand;
  }

  function dailySeatsHint(route, opts) {
    const ac = aircraftType(route.aircraft_type);
    const plane = route.aircraft_id ? state.fleet.find((f) => f.id === route.aircraft_id) : null;
    const seats = plane ? fleetSeatCount(plane) : (ac && ac.seats) || 50;
    const freq = route.frequency_week || 7;
    return seats * (freq / 7);
  }

  /** Depth guard: demand path must never re-enter full route simulation. */
  let simulatingDemandDepth = 0;

  /**
   * Smooth load so a single decision (fare, marketing, rival move) cannot
   * yank avg load from healthy → 0% overnight. Caps day-over-day change.
   * Only mutates route when opts.commit is true (authoritative day tick).
   */
  function stabilizeRouteLoad(route, rawLoad, opts) {
    opts = opts || {};
    const commit = !!opts.commit;
    if (!route || !Number.isFinite(rawLoad)) return rawLoad;
    const prev =
      route.yesterday_load != null && Number.isFinite(route.yesterday_load)
        ? route.yesterday_load
        : route.smooth_load != null && Number.isFinite(route.smooth_load)
          ? route.smooth_load
          : null;

    let next = rawLoad;
    if (prev != null) {
      // Blend + hard cap ±12 percentage points per day
      const blended = prev * 0.58 + rawLoad * 0.42;
      const maxDelta = 0.12;
      next = Math.max(prev - maxDelta, Math.min(prev + maxDelta, blended));
    }
    if (route.established || route.force_fly) {
      next = Math.max(0.4, next);
    }
    next = Math.max(0, Math.min(0.92, next));

    if (!commit) return next;

    // Commit once per calendar day so re-renders don't re-blend.
    if (route._load_commit_day !== state.day) {
      route.smooth_load = next;
      route._load_commit_day = state.day;
    } else if (route.smooth_load != null && Number.isFinite(route.smooth_load)) {
      next = route.smooth_load;
    }
    return next;
  }

  function commitRouteLoadHistory() {
    if (!state || !state.routes) return;
    state.routes.forEach((r) => {
      if (r.smooth_load != null && Number.isFinite(r.smooth_load)) {
        r.yesterday_load = r.smooth_load;
      }
    });
  }

  /**
   * Simulate one day of a route.
   * opts.commit — only true from authoritative day ticks. Previews (HUD, Studio,
   * league) must leave block hours and smooth_load untouched.
   * opts.airportSpendByIata / opts.investments / opts.draftOta — Studio draft projection.
   */
  function simulateRouteDay(route, opts) {
    opts = opts || {};
    const commit = !!opts.commit;
    const empty = {
      revenue: 0,
      cost: 0,
      pax: 0,
      load: 0,
      ticketRev: 0,
      ancillaryRev: 0,
      grounded: false,
      canceled: false,
      ferryReturn: false,
      schedScale: 1,
      flightsToday: 0,
      market: null,
    };
    const ac = aircraftType(route.aircraft_type);
    if (!ac) return { ...empty };
    const dist = routeDistance(route);
    if (dist > ac.range_nm) return { ...empty };

    const plane = route.aircraft_id ? state.fleet.find((f) => f.id === route.aircraft_id) : null;
    if (plane && !isPlaneAvailable(plane)) {
      return { ...empty, grounded: true };
    }
    const o = airport(route.origin);
    const d = airport(route.dest);
    const seats = plane ? fleetSeatCount(plane) : ac.seats;
    const schedScale = plane ? planeScheduleScaleForRoute(plane.id, route) : 1;
    const flightsToday = (route.frequency_week / 7) * schedScale;
    const dailySeats = seats * flightsToday;
    const mkt = routeMarketContext(route, opts);
    simulatingDemandDepth += 1;
    let demand;
    try {
      demand = demandForRoute(route, opts);
    } finally {
      simulatingDemandDepth -= 1;
    }
    let rawLoad = Math.min(0.92, demand / Math.max(dailySeats, 1));
    const prod = routeProduct(routeProductId(route));
    // Established / starter / contract products keep a floor so tutorial & feeder don't free-fall.
    if (route.established || route.force_fly || prod.forceFlySoft) {
      rawLoad = Math.max(0.4, rawLoad);
    }
    if (prod.loadFloor) {
      rawLoad = Math.max(prod.loadFloor * 0.85, rawLoad);
    }

    // Day-to-day stability: never jump more than ~12 pts overnight (checks & balances).
    let load = stabilizeRouteLoad(route, rawLoad, { commit });

    const reverse = findReverseRoute(route);
    const ferryReturn = !reverse && routeProductId(route) !== 'tag';
    let cancelThreshold = (routeEconomics().cancel_load_threshold != null
      ? routeEconomics().cancel_load_threshold
      : 0.1);
    if (prod.hardToCancel) cancelThreshold = Math.min(cancelThreshold, 0.06);

    // Cancel only truly hopeless non-established services (and never on day 0–21).
    const canCancel =
      !route.established &&
      !route.force_fly &&
      !prod.hardToCancel &&
      (state.day || 0) > 21 &&
      load < cancelThreshold &&
      flightsToday > 0;
    if (canCancel) {
      const oneWayBlock = blockHours(dist, ac) * flightsToday;
      const cancelCost = oneWayBlock * bootstrap.crew_cost_per_block_hour * 0.15;
      return {
        ...empty,
        cost: cancelCost,
        load, // keep projected load for HUD (not fake 0%)
        canceled: true,
        ferryReturn,
        schedScale,
        flightsToday: 0,
        market: mkt,
        demand,
        rawLoad,
        cancelReason: `projected load ${(rawLoad * 100).toFixed(0)}% — departures scrubbed to save fuel`,
      };
    }

    const pax = Math.floor(dailySeats * load);
    const ota = otaEffects(opts);
    const yieldM = prod.yieldMult != null ? prod.yieldMult : 1;
    let ticketRev = bucketedTicketRevenue(route, pax) * ota.revenueMult * yieldM;
    let ancillaryRev = pax * ancillaryPerPax(route, load, o, d) * ota.revenueMult * yieldM;
    // Cargo-in-bin: sell empty seats as belly freight
    let cargoRev = 0;
    if (prod.cargoPerEmptySeat && flightsToday > 0) {
      const emptySeats = Math.max(0, dailySeats - pax);
      cargoRev = emptySeats * prod.cargoPerEmptySeat;
    }
    // Essential PSO-style subsidy per operated departure
    let subsidy = 0;
    if (prod.subsidyPerDep && flightsToday > 0) {
      subsidy = prod.subsidyPerDep * flightsToday;
    }
    const revenue = ticketRev + ancillaryRev + cargoRev + subsidy;

    // Block hours: tag A–B–C uses both segments; unpaired one-way ferries home.
    let block = blockHours(dist, ac) * flightsToday;
    if (prod.isTag && route.tag_dest) {
      const mid = airport(route.dest);
      const end = airport(route.tag_dest);
      if (mid && end) {
        const leg2 = haversineNm(mid.lat, mid.lon, end.lat, end.lon);
        block += blockHours(leg2, ac) * flightsToday;
      }
    } else if (ferryReturn) {
      block += blockHours(dist, ac) * flightsToday * 0.92;
    }
    // Only authoritative day ticks accumulate utilization / AOG risk.
    if (commit && plane) {
      plane.block_hours_month = (plane.block_hours_month || 0) + block;
    }
    const costM = prod.costMult != null ? prod.costMult : 1;
    const fuel = block * ac.fuel_gal_hr * state.fuel_price;
    const crew = block * bootstrap.crew_cost_per_block_hour;
    // Airport fees: once per landing. Ferry return still lands at origin. Tag = 2 landings.
    let landings = flightsToday;
    if (prod.isTag && route.tag_dest) landings = flightsToday * 2;
    else if (ferryReturn) landings = flightsToday * 2;
    const fees = landings * bootstrap.airport_fee_per_departure;
    const variable = (fuel + crew + fees) * costM;

    return {
      revenue,
      cost: variable,
      pax,
      load,
      ticketRev,
      ancillaryRev,
      cargoRev,
      subsidy,
      product: prod.id,
      grounded: false,
      canceled: false,
      ferryReturn,
      schedScale,
      flightsToday,
      market: mkt,
      demand,
    };
  }

  function simulateDayEconomics() {
    let dayRev = 0;
    let dayCost = 0;
    state.routes.forEach((route) => {
      const r = simulateRouteDay(route, { commit: true });
      dayRev += r.revenue;
      dayCost += r.cost;
    });
    // Debt service hits cash on the month tick (interest + principal), not daily —
    // so principal actually declines. Daily fixed = ops overhead only.
    // Interest is still reflected in burn/runway via monthlyDebtService().
    const dailyFixed =
      (fleetMonthlyCosts() + gateLeaseMonthly()) / 30 + marketingMonthly() / 30;
    const pnl = dayRev - dayCost - dailyFixed;
    return { dayRev, dayCost, dailyFixed, pnl };
  }

  function processDayRollover(dayRev, dayCost) {
    const decisionPending = !!(activeDecision || decisionQueue.length);
    if (state.day > 0 && state.day % 7 === 0) updateDynamicFares();

    if (state.day % 30 === 0) {
      if (state.macro && state.macro.ota_promo) {
        Object.keys(state.macro.ota_promo).forEach((pid) => {
          const promo = state.macro.ota_promo[pid];
          if (promo.months_left > 0) promo.months_left -= 1;
          if (promo.months_left <= 0) delete state.macro.ota_promo[pid];
        });
      }
      state.ltm_revenue = state.revenue_history.slice(-365).reduce((a, b) => a + b, 0) + dayRev * 30;
      Object.keys(state.brand_awareness).forEach((ap) => {
        const spend = clampMoney(state.marketing_spend_monthly[ap]);
        state.marketing_spend_monthly[ap] = spend;
        if (spend > 0) {
          const amp = otaEffects().marketingAmplify;
          // ~$9k/mo → ~1.5 brand pts/mo (was ~0.2 — felt like marketing did nothing).
          state.brand_awareness[ap] = Math.min(
            100,
            (state.brand_awareness[ap] || 0) + (spend / 6000) * amp
          );
        }
      });
      // System reputation: sustained airport ads rebuild trust after AOG / soft service
      const totalAirportAds = Object.values(state.marketing_spend_monthly || {}).reduce(
        (a, b) => a + clampMoney(b),
        0
      );
      if (totalAirportAds >= 6000) {
        const repLift = Math.min(1.2, 0.15 + totalAirportAds / 50000);
        state.reputation = Math.min(100, (state.reputation || 0) + repLift);
        if ((state.aog_rep_debt || 0) > 0) {
          state.aog_rep_debt = Math.max(0, state.aog_rep_debt - repLift * 0.4);
        }
      }
      const otaCost = otaListingMonthly();
      if (otaCost > 0) state.cash -= otaCost;
      applyMonthlyDebtService();
      applyMonthlyReputation(dayRev, dayCost);
      processMonthlyScoreboard();
      if (!decisionPending) processMonthlyGateEfficiency();
      maybeCapitalCoach();
      if (!decisionPending) maybeMonthlyOpsReview();
      if (!decisionPending) maybePublicOrPePressure();
      // Mid-game ops goals tick (achievements fire inside activeMidgameOpsGoal)
      try {
        activeMidgameOpsGoal();
      } catch (e) {
        /* midgame goals optional */
      }
      const retired = [];
      state.fleet = state.fleet.filter((f) => {
        ensurePlaneTelemetry(f);
        if (f.leased) {
          f.lease_months_left = Math.max(0, (f.lease_months_left || 0) - 1);
          return true;
        }
        f.life_months_left = (f.life_months_left || 0) - 1;
        if (f.life_months_left <= 0) {
          retired.push(f);
          return false;
        }
        return true;
      });
      retired.forEach((f) => {
        const ac = aircraftType(f.type);
        pushEvent(`Retired ${ac ? ac.name : f.type} (${f.id}) — useful life ended.`);
      });
    }

    if (state.day % 90 === 0 && state.bonds.length) {
      const coupon = quarterlyBondCoupons();
      state.cash -= coupon;
      pushEvent(`Bond coupon paid: ${fmtMoney(-coupon)}`);
    }

    state.revenue_history.push(dayRev);
    if (state.revenue_history.length > 400) state.revenue_history.shift();

    if (state.day % 7 === 0) updateFuelPrice();

    processFleetDay();

    if (!decisionPending && state.day > 0 && state.day % 60 === 0) maybeCompetitorEvents();

    if (!decisionPending && state.day > 0 && state.day % 45 === 0) maybeWindfallEvent();

    if (!decisionPending && state.day > 0 && state.day % 7 === 0) processReactiveCompetitorThreats('weekly');

    if (!decisionPending && state.day > 0 && state.day % 50 === 0) maybeEventCharterOffer();

    if (!decisionPending && state.day > 0 && state.day % 90 === 0) processCompetitorAI();

    if (state.day > 0 && state.day % 365 === 0) advanceMacroYear();

    state.gates.forEach((g) => {
      if (state.day % 30 === 0) g.months_left = (g.months_left || g.years_left * 12) - 1;
    });

    if (!decisionPending && state.onboarding_done) checkWinningPlaybookDayTriggers();

    processAirportDemandSurges();
    // Lock today's smoothed loads as baseline for tomorrow (prevents overnight free-falls).
    commitRouteLoadHistory();
  }

  function applyMonthlyReputation(dayRev, dayCost) {
    if (!state) return;
    let delta = 0;
    const notes = [];
    const aogPlanes = (state.fleet || []).filter((f) => (f.aog_days_left || 0) > 0).length;
    if (aogPlanes > 0) {
      const hit = Math.min(2.4, 0.55 * aogPlanes);
      delta -= hit;
      notes.push(`AOG reliability −${hit.toFixed(1)}`);
    }
    const trail = (state.pnl_history || []).reduce((a, b) => a + b, 0);
    if ((state.pnl_history || []).length >= 14 && trail < 0 && (state.routes || []).length > 0) {
      delta -= 0.55;
      notes.push('chronic losses −0.6');
    }
    if ((state.positive_day_streak || 0) === 0 && dayRev < dayCost * 0.85 && (state.routes || []).length > 0) {
      delta -= 0.15;
    }

    // Marketing rebuilds trust (brand ads + national/world), not only bookings.
    const mktMo =
      Object.values(state.marketing_spend_monthly || {}).reduce((a, b) => a + clampMoney(b), 0) +
      scopedMarketingMonthly();
    if (mktMo >= 8000) {
      const lift = Math.min(1.8, 0.25 + mktMo / 45000);
      delta += lift;
      notes.push(`marketing trust +${lift.toFixed(1)}`);
    }

    // Clean ops recovery: no AOG, profitable month trail, pay down AOG debt
    if (aogPlanes === 0 && (state.routes || []).length > 0 && dayRev > dayCost) {
      const clean = 0.35 + Math.min(0.5, (state.positive_day_streak || 0) * 0.02);
      delta += clean;
      if ((state.aog_rep_debt || 0) > 0) {
        const pay = Math.min(state.aog_rep_debt, clean * 0.6);
        state.aog_rep_debt = Math.max(0, state.aog_rep_debt - pay);
      }
    }
    // Essential / community products quietly build goodwill each month they fly
    (state.routes || []).forEach((r) => {
      const p = routeProduct(routeProductId(r));
      if (p.repMonthly) delta += p.repMonthly;
    });

    if (Math.abs(delta) < 0.05) return;
    const before = state.reputation || 0;
    state.reputation = Math.max(0, Math.min(100, before + delta));
    if (delta < 0 && before - state.reputation >= 0.4) {
      pushEvent(
        `Reputation softens to ${state.reputation.toFixed(0)} (${notes.join('; ') || 'ops pressure'}). Lower trust trims demand capture until you recover.`,
        'bad'
      );
    } else if (delta > 0 && state.reputation - before >= 0.35) {
      pushEvent(
        `Reputation recovers to ${state.reputation.toFixed(0)} (${notes.filter((n) => n.includes('+')).join('; ') || 'steady ops'}).`,
        'good'
      );
    }
  }

  function chapter11Active() {
    return !!(state && state.chapter11 && state.chapter11.active);
  }

  function queueChapter11Decision(force) {
    if (!state || state.game_over) return;
    if (activeDecision && activeDecision.chapter11) return;
    if (decisionQueue.some((d) => d && d.chapter11)) return;
    if (!force && state.milestones.includes('chapter11_board') && chapter11Active()) return;

    const debtPrin = (state.debt || []).reduce((s, d) => s + (d.principal || 0), 0);
    const gateN = (state.gates || []).length;
    const fleetN = (state.fleet || []).length;
    const body =
      `<p>Cash is <b class="danger">${fmtMoney(state.cash)}</b>. Creditors and lessors are circling.</p>` +
      `<p class="muted" style="font-size:0.85rem;margin-top:8px;">Debt principal ~${fmtMoney(debtPrin)} · ${gateN} gate(s) · ${fleetN} aircraft. ` +
      `Chapter 11 is a <b>playable rescue</b> — not instant liquidation. Choose a path; you can still raise capital afterward.</p>`;

    queueDecision({
      chapter11: true,
      kicker: `${fmtDate(state.day)} · Creditor board`,
      title: force ? 'Emergency — deep insolvency' : 'Cash crisis — creditor board',
      body,
      teach:
        'Restructure cuts debt service but dilutes ownership and reputation. Selling gates/fleet buys time. Liquidation ends the game.',
      logLine: 'Creditor board convened over cash crisis',
      options: [
        {
          id: 'c11_restructure',
          label: 'A — Chapter 11 restructure',
          hint: 'Cut ~40% debt principal, DIP cash, equity & reputation hit.',
          effect: 'chapter11_restructure',
        },
        {
          id: 'c11_gates',
          label: 'B — Sell gates for liquidity',
          hint: gateN ? 'Monetize gate deposits; drop stations you cannot fund.' : 'No gates to sell — try restructure.',
          effect: 'chapter11_sell_gates',
        },
        {
          id: 'c11_fleet',
          label: 'C — Park / return fleet',
          hint: fleetN ? 'Return leases; routes on those jets cancel.' : 'No fleet left.',
          effect: 'chapter11_park_fleet',
        },
        {
          id: 'c11_out',
          label: 'D — Liquidate airline',
          hint: 'Game over — creditors take the keys.',
          effect: 'chapter11_liquidate',
        },
      ],
    });
    if (!state.milestones.includes('chapter11_board')) state.milestones.push('chapter11_board');
  }

  function applyChapter11Restructure() {
    if (!state) return;
    let principalCut = 0;
    (state.debt || []).forEach((d) => {
      const cut = Math.round((d.principal || 0) * 0.4);
      d.principal = Math.max(0, (d.principal || 0) - cut);
      principalCut += cut;
      if (d.monthly_payment) d.monthly_payment = Math.max(0, Math.round(d.monthly_payment * 0.65));
      if (d.rate) d.rate = Math.max(0.04, d.rate * 0.9);
    });
    const dip = 2_500_000;
    state.cash += dip;
    state.equity_pct = Math.max(5, (state.equity_pct || 100) * 0.72);
    state.reputation = Math.max(0, (state.reputation || 0) - 10);
    state.financing_tier = 'distressed';
    state.bond_rating = 'CCC';
    state.chapter11 = {
      active: true,
      entered_day: state.day,
      exit_by_day: state.day + 180,
    };
    if (state.cash < 0) state.cash = Math.min(500_000, state.cash + 1_500_000);
    pushEvent(
      `Chapter 11 restructure: −${fmtMoney(principalCut)} debt principal, DIP ${fmtMoney(dip)}, ` +
        `equity now ${state.equity_pct.toFixed(0)}%. Court watch for 180 days.`,
      'milestone'
    );
    pushPlayerEvent('entered Chapter 11 — prove a plan or liquidate later.');
    markMilestoneOnce('chapter11_filed', `${state.airline_name} filed <b>Chapter 11</b> — restructuring in progress.`);
  }

  function applyChapter11SellGates() {
    if (!state || !(state.gates || []).length) {
      pushEvent('No gates left to sell — restructure or park fleet instead.', 'bad');
      queueChapter11Decision(true);
      return;
    }
    let raised = 0;
    const sold = state.gates.splice(0, Math.max(1, Math.ceil(state.gates.length / 2)));
    sold.forEach((g) => {
      const refund = Math.round((g.monthly || 10000) * 4);
      raised += refund;
      (state.routes || [])
        .filter((r) => r.origin === g.airport)
        .forEach((r) => {
          r._drop = true;
        });
    });
    state.routes = (state.routes || []).filter((r) => !r._drop);
    state.cash += raised;
    state.reputation = Math.max(0, (state.reputation || 0) - 4);
    pushEvent(`Emergency gate sale: +${fmtMoney(raised)} · ${sold.length} gate(s) returned · related routes closed.`, 'bad');
    if (state.cash < 0) queueChapter11Decision(true);
  }

  function applyChapter11ParkFleet() {
    if (!state || !(state.fleet || []).length) {
      pushEvent('No aircraft to park.', 'bad');
      queueChapter11Decision(true);
      return;
    }
    const keep = Math.max(0, Math.ceil(state.fleet.length / 3));
    const drop = state.fleet.splice(keep);
    const dropIds = new Set(drop.map((f) => f.id));
    state.routes = (state.routes || []).filter((r) => !dropIds.has(r.aircraft_id));
    const credit = drop.length * 180_000;
    state.cash += credit;
    state.reputation = Math.max(0, (state.reputation || 0) - 5);
    pushEvent(
      `Fleet contraction: returned ${drop.length} aircraft · routes pruned · lessor credit ${fmtMoney(credit)}.`,
      'bad'
    );
    if (state.cash < 0) queueChapter11Decision(true);
  }

  function applyChapter11Liquidate() {
    if (!state) return;
    state.game_over = true;
    state.chapter11 = { active: false, liquidated: true, day: state.day };
    state.cash = 0;
    pushEvent('LIQUIDATION — creditors take the keys. Game over.', 'bad');
    setSpeed('pause');
    state.paused_reason = 'Airline liquidated';
  }

  function checkChapter11Exit() {
    if (!chapter11Active()) return;
    const c11 = state.chapter11;
    if (state.cash >= 1_000_000 && (state.pnl_history || []).length >= 14) {
      const trail = state.pnl_history.reduce((a, b) => a + b, 0);
      if (trail > 0) {
        c11.active = false;
        c11.exited_day = state.day;
        state.reputation = Math.min(100, (state.reputation || 0) + 3);
        pushEvent('Chapter 11 plan confirmed — exited restructuring with positive trail P&L.', 'good');
        markMilestoneOnce('chapter11_exit', `${state.airline_name} <b>emerged from Chapter 11</b>.`);
        return;
      }
    }
    if (state.day >= (c11.exit_by_day || 0) && state.cash < 0) {
      pushEvent('Court deadline missed with negative cash — forced liquidation path.', 'bad');
      queueChapter11Decision(true);
    }
  }

  function queueRunwayPrimerDecision() {
    if (!state || state.game_over) return;
    if (state.milestones.includes('runway_primer')) return;
    state.milestones.push('runway_primer');
    queueDecision({
      kicker: `${fmtDate(state.day)} · CFO briefing`,
      title: 'Cash runway is getting short',
      body:
        `<p>At the current burn rate, cash lasts about <b>${runwayMonths().toFixed(1)} months</b>. Nothing is wrong yet — this is the moment to plan, not panic.</p>` +
        `<p class="muted" style="font-size:0.85rem;margin-top:8px;">Here is how trouble escalates if cash keeps falling:</p>` +
        `<ul class="list" style="font-size:0.8rem;">` +
        `<li><b>Under 2 months</b> — the game pauses and warns you.</li>` +
        `<li><b>Cash below zero</b> — a creditor board convenes: restructure in Chapter 11, sell gates, or park fleet. Still playable.</li>` +
        `<li><b>Chapter 11 fails</b> (deep insolvency or missed court deadline) — liquidation, game over.</li>` +
        `</ul>`,
      teach:
        'Ways to extend runway: raise capital (Capital tab), cut unprofitable routes, trim marketing spend, or return idle aircraft. Raising money early is far cheaper than raising it desperate.',
      logLine: 'CFO briefing: cash runway getting short',
      options: [
        {
          id: 'primer_capital',
          label: 'A — Review financing options',
          hint: 'Open the Capital tab — equity, loans, and bonds.',
          effect: 'open_tab',
          tab: 'finance',
        },
        {
          id: 'primer_routes',
          label: 'B — Review route profitability',
          hint: 'Open Routes — find what is burning cash.',
          effect: 'open_tab',
          tab: 'routes',
        },
        {
          id: 'primer_ok',
          label: 'C — Understood, carry on',
          hint: 'No action now; the warnings above still apply.',
          effect: 'none',
        },
      ],
    });
  }

  function checkSurvivalTriggers() {
    if (!state || state.game_over) return;

    if (
      runwayMonths() < 4 &&
      state.cash > 0 &&
      state.day > 14 &&
      !state.milestones.includes('runway_primer')
    ) {
      queueRunwayPrimerDecision();
    }

    if (runwayMonths() < 2 && state.cash > 0 && !state.milestones.includes('runway_warn')) {
      state.milestones.push('runway_warn');
      pushEvent(`Cash runway under 2 months (${runwayMonths().toFixed(1)} mo).`, 'bad');
      setSpeed('pause');
      state.paused_reason = 'Low runway';
    }

    if (state.cash < 0 && !state.milestones.includes('chapter11_warn')) {
      state.milestones.push('chapter11_warn');
      pushEvent('CRITICAL: Negative cash. Creditor board will convene — restructure, sell assets, or liquidate.', 'bad');
      setSpeed('pause');
      state.paused_reason = 'Cash below zero';
      queueChapter11Decision(false);
      return;
    }

    if (state.cash < -2_000_000 && !chapter11Active()) {
      setSpeed('pause');
      state.paused_reason = 'Deep insolvency — emergency board';
      queueChapter11Decision(true);
      return;
    }

    if (chapter11Active() && state.cash < -8_000_000) {
      state.game_over = true;
      pushEvent('BANKRUPTCY — Chapter 11 failed; estate liquidated. Game over.', 'bad');
      setSpeed('pause');
      state.paused_reason = 'Chapter 11 failed';
      return;
    }

    if (state.day > 0 && state.day % 30 === 0) checkChapter11Exit();
  }

  function markMilestoneOnce(id, msg) {
    if (state.milestones.includes(id)) return;
    state.milestones.push(id);
    pushEvent(msg, 'milestone');
  }

  function recordPositiveDayStreak(pnl) {
    if (!state) return;
    if (pnl > 0) {
      state.positive_day_streak = (state.positive_day_streak || 0) + 1;
      if (state.positive_day_streak >= 7) {
        markMilestoneOnce('first_green_week', `${state.airline_name} posted <b>7 profitable days in a row</b> — overhead is covered.`);
      }
    } else {
      state.positive_day_streak = 0;
    }
  }

  function checkPositiveMilestones() {
    if (!state || state.game_over) return;

    if ((state.pnl_history || []).length >= 30) {
      const sum30 = state.pnl_history.reduce((a, b) => a + b, 0);
      if (sum30 > 0) markMilestoneOnce('first_profitable_month', `${state.airline_name} closed a <b>profitable trailing month</b> — the model is working.`);
    }
    (state.routes || []).forEach((route) => {
      const st = route.stats || {};
      if (st.days >= 7 && st.load_sum / st.days >= 0.5) {
        markMilestoneOnce(
          `load_50_${route.id}`,
          `<b>${route.origin}–${route.dest}</b> averaged <b>${Math.round((st.load_sum / st.days) * 100)}%</b> load over the last week — solid demand.`
        );
      }
    });
    if ((state.fleet || []).length >= 3) markMilestoneOnce('fleet_3', `Fleet milestone: ${state.airline_name} now operates <b>3 aircraft</b>.`);
    if ((state.fleet || []).length >= 5) markMilestoneOnce('fleet_5', `Fleet milestone: ${state.airline_name} now operates <b>5 aircraft</b>.`);
    if ((state.routes || []).length >= 5) markMilestoneOnce('routes_5', `Network milestone: ${state.airline_name} now flies <b>5 routes</b>.`);
    if ((state.routes || []).length >= 10) markMilestoneOnce('routes_10', `Network milestone: ${state.airline_name} now flies <b>10 routes</b>.`);
    if (state.day >= 365) markMilestoneOnce('survive_year1', `${state.airline_name} made it to <b>year 2</b> — one year in the air.`);
    if (state.day >= 730) markMilestoneOnce('survive_year2', `${state.airline_name} made it to <b>year 3</b> — still flying strong.`);
    if (state.cash >= 20_000_000) markMilestoneOnce('cash_20m', `${state.airline_name} crossed <b>${fmtMoney(20_000_000)}</b> cash on hand.`);
  }

  // ── SCENARIO GOALS ─────────────────────────────────────────────────
  function scenarioGoal() {
    if (!state || !state.scenario_id) return null;
    const sc = bootstrap.scenarios[state.scenario_id];
    return (sc && sc.goal) || null;
  }

  function trailingMonthPnl() {
    const h = state.pnl_history || [];
    if (h.length < 30) return null;
    return h.reduce((a, b) => a + b, 0);
  }

  function totalDebtAndBondPrincipal() {
    const debt = (state.debt || []).reduce((s, d) => s + (d.principal || 0), 0);
    const bonds = (state.bonds || []).reduce((s, b) => s + (b.principal || 0), 0);
    return debt + bonds;
  }

  function goalConditions(goal) {
    if (!goal) return [];
    const conds = [];
    if (goal.ltm_revenue) {
      const cur = state.ltm_revenue || 0;
      conds.push({
        label: `${fmtMoney(goal.ltm_revenue)} annual revenue`,
        progress: `${fmtMoney(cur)} of ${fmtMoney(goal.ltm_revenue)}`,
        pct: Math.min(100, (cur / goal.ltm_revenue) * 100),
        done: cur >= goal.ltm_revenue,
      });
    }
    if (goal.max_debt != null) {
      const cur = totalDebtAndBondPrincipal();
      conds.push({
        label: `Total debt below ${fmtMoney(goal.max_debt)}`,
        progress: `${fmtMoney(cur)} outstanding`,
        pct: cur <= goal.max_debt ? 100 : Math.max(0, Math.min(100, (1 - (cur - goal.max_debt) / goal.max_debt) * 100)),
        done: cur <= goal.max_debt,
      });
    }
    if (goal.profit_month) {
      const trail = trailingMonthPnl();
      conds.push({
        label: 'Profitable trailing month',
        progress: trail == null ? 'collecting 30 days of data…' : `${fmtMoney(trail)} last 30 days`,
        pct: trail != null && trail > 0 ? 100 : 0,
        done: trail != null && trail > 0,
      });
    }
    return conds;
  }

  function checkScenarioGoal() {
    if (!state || state.game_over || state.goal_won) return;
    const goal = scenarioGoal();
    if (!goal) return;
    const conds = goalConditions(goal);
    if (!conds.length || !conds.every((c) => c.done)) return;
    state.goal_won = { day: state.day };
    pushEvent(`SCENARIO GOAL ACHIEVED — ${goal.label} (day ${state.day}).`, 'milestone');
    queueGoalVictoryDecision(goal);
  }

  function queueGoalVictoryDecision(goal) {
    const years = state.day >= 365 ? `${(state.day / 365).toFixed(1)} years` : `${state.day} days`;
    queueDecision({
      kicker: `${fmtDate(state.day)} · Scenario goal`,
      title: 'Goal achieved',
      body:
        `<p><b>${goal.label}</b> — done, in <b>${years}</b>.</p>` +
        `<p class="muted" style="font-size:0.85rem;margin-top:8px;">${state.airline_name} did what this scenario asked of it. ` +
        `The sky stays open: keep growing this airline, or take a fresh challenge from the hangar.</p>`,
      logLine: `Scenario goal achieved on day ${state.day}`,
      options: [
        {
          id: 'goal_continue',
          label: 'A — Keep flying',
          hint: 'Continue this airline in free play.',
          effect: 'none',
        },
        {
          id: 'goal_hangar',
          label: 'B — Back to the hangar',
          hint: 'Save and return to scenario select.',
          effect: 'goal_hangar',
        },
      ],
    });
  }

  let yearTickBusy = false;

  function updateSpeedHintLabel(speedId) {
    const hint = $('speed-hint');
    if (!hint) return;
    const labels = isMobileLayout()
      ? {
          pause: 'Paused',
          slow: '4-hour steps',
          day: '1 day / tick',
          week: '1 week / tick',
          month: '1 month / tick',
          year: '1 year / tick',
        }
      : {
          pause: 'Paused',
          slow: '4-hour steps',
          day: '1 day / tick',
          week: '1 week / tick — alerts will pause & slow you',
          month: '1 month / tick — alerts will pause & slow you',
          year: '365 days / tick — alerts still pause mid-year',
        };
    hint.textContent = labels[speedId] || '';
  }

  /** Core day loop without save/render — used by tickDays and year chunking. */
  function tickDaysCore(n) {
    if (!state || state.game_over || n <= 0) return 0;
    let ran = 0;
    for (let i = 0; i < n; i++) {
      state.day += 1;
      ran += 1;
      const econ = simulateDayEconomics();
      const interest = accrueCashInterest(1);
      state.daily_pnl = econ.pnl + interest;
      state.cash += econ.pnl;
      recordPnlHistory(state.daily_pnl);
      recordPositiveDayStreak(state.daily_pnl);
      updateDailyMetrics(econ);
      processDayRollover(econ.dayRev, econ.dayCost);
      checkSurvivalTriggers();
      checkPositiveMilestones();
      checkScenarioGoal();
      if (state.game_over || state.paused_reason) break;
    }
    return ran;
  }

  function tickDays(n) {
    if (!state || state.game_over || n <= 0) return;
    // Year / long jumps: chunk so the browser can paint quarterly progress.
    if (n >= 120) {
      if (yearTickBusy) return;
      yearTickBusy = true;
      let remaining = n;
      const step = () => {
        if (!state || state.game_over) {
          yearTickBusy = false;
          return;
        }
        const chunk = Math.min(30, remaining);
        tickDaysCore(chunk);
        remaining -= chunk;
        const hint = $('speed-hint');
        if (hint && remaining > 0 && !state.paused_reason) {
          const dayInYear = ((state.day - 1) % 365) + 1;
          const q = Math.min(4, Math.ceil(dayInYear / 91.25));
          hint.textContent = `Simulating… day ${state.day} · Q${q} · ${fmtMoney(state.cash)} cash`;
        }
        if (remaining > 0 && !state.paused_reason && !state.game_over) {
          requestAnimationFrame(() => setTimeout(step, 0));
        } else {
          yearTickBusy = false;
          saveGame();
          renderAll();
          if (state && state.speed) updateSpeedHintLabel(state.speed);
        }
      };
      const hint = $('speed-hint');
      if (hint) hint.textContent = `Simulating ${n} days…`;
      step();
      return;
    }

    tickDaysCore(n);
    saveGame();
    renderAll();
  }

  function recordPnlHistory(pnl) {
    if (!Array.isArray(state.pnl_history)) state.pnl_history = [];
    state.pnl_history.push(pnl);
    if (state.pnl_history.length > 30) state.pnl_history.shift();
  }

  function tickHours(hours) {
    if (!state || state.game_over || hours <= 0) return;
    if (state.hour == null) state.hour = 8;

    const econ = simulateDayEconomics();
    const frac = hours / 24;
    const interest = accrueCashInterest(frac);
    state.daily_pnl = econ.pnl + interest;
    state.cash += econ.pnl * frac;

    state.hour += hours;
    let dayAdvanced = false;
    while (state.hour >= 24) {
      state.hour -= 24;
      state.day += 1;
      dayAdvanced = true;
      recordPnlHistory(state.daily_pnl);
      recordPositiveDayStreak(state.daily_pnl);
      processDayRollover(econ.dayRev, econ.dayCost);
      checkSurvivalTriggers();
      checkPositiveMilestones();
      checkScenarioGoal();
      if (state.game_over || state.paused_reason) break;
    }

    saveGame();
    if (dayAdvanced) renderAll();
    else renderHud();
  }

  function resolveSpeedId(speedId) {
    // Keep unknown aliases honest — do not silently remap year→month.
    return speedId;
  }

  function togglePause() {
    if (!state || state.game_over) return;
    if (state.speed === 'pause') {
      setSpeed(speedBeforePause || 'day');
    } else {
      setSpeed('pause');
    }
  }

  function setSpeed(speedId) {
    if (!state) return;
    speedId = resolveSpeedId(speedId);
    if (speedId === 'month' && !state.ff_month_confirmed) {
      const ok = window.confirm(
        'Fast-forward one month per tick? Alerts will still pause the clock and log extras to the Event Log. Continue?'
      );
      if (!ok) return;
      state.ff_month_confirmed = true;
      saveGame();
    }
    if (speedId === 'year' && !state.ff_year_confirmed) {
      const ok = window.confirm(
        'Year speed advances 365 simulated days per tick (full day economics). Alerts and crises still pause mid-year. Continue?'
      );
      if (!ok) return;
      state.ff_year_confirmed = true;
      saveGame();
    }
    if (speedId !== 'pause') speedBeforePause = speedId;
    state.speed = speedId;
    if (tickTimer) clearInterval(tickTimer);
    tickTimer = null;
    const tickMs = bootstrap.tick_ms || {};
    const ms = tickMs[speedId] || 0;
    const speeds = bootstrap.time_speeds || [];
    const spec = speeds.find((t) => t.id === speedId) || {};
    const days = spec.days_per_tick || 0;
    const hours = spec.hours_per_tick || 0;
    if (hours > 0 && ms > 0) {
      tickTimer = setInterval(() => tickHours(hours), ms);
    } else if (days > 0 && ms > 0) {
      tickTimer = setInterval(() => tickDays(days), ms);
    }
    document.querySelectorAll('[data-speed]').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.speed === speedId);
    });
    updateSpeedHintLabel(speedId);
  }

  function setupMobileDock() {
    const dock = $('mobile-dock');
    if (!dock || dock._runwayInit) return;
    dock._runwayInit = true;
    dock.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-mobile-nav]');
      if (!btn) return;
      const nav = btn.dataset.mobileNav;
      if (nav === 'map') {
        scrollToMap();
        return;
      }
      switchTab(nav);
    });
    const collapseBtn = $('map-collapse-btn');
    const expandBtn = $('map-expand-btn');
    if (collapseBtn) {
      collapseBtn.addEventListener('click', () => setMapCollapsed(true));
    }
    if (expandBtn) {
      expandBtn.addEventListener('click', () => {
        setMapCollapsed(false);
        scrollToMap({ instant: true });
      });
    }
    window.matchMedia(MOBILE_MQ).addEventListener('change', () => {
      if (!isMobileLayout()) {
        const wrap = $('map-wrap');
        if (wrap) wrap.classList.remove('map-collapsed');
      }
      setSpeed(state ? state.speed : 'pause');
      drawMap();
    });
  }

  function gateCountAt(iata) {
    return state.gates.filter((g) => g.airport === iata).length;
  }

  function hasGateAt(iata) {
    return gateCountAt(iata) > 0;
  }

  function originFrequencyUsed(iata, excludeRouteId) {
    return (state.routes || [])
      .filter((r) => r.origin === iata && r.id !== excludeRouteId)
      .reduce((sum, r) => sum + (r.frequency_week || 0), 0);
  }

  function maxFrequencyAtOrigin(iata) {
    const ap = airport(iata);
    return gateCountAt(iata) * airportGateWeeklyCapacity(ap);
  }

  function gateCapacityRemaining(iata, excludeRouteId) {
    return Math.max(0, maxFrequencyAtOrigin(iata) - originFrequencyUsed(iata, excludeRouteId));
  }

  function gateCapacityLabel(iata, extraFreq, excludeRouteId) {
    const max = maxFrequencyAtOrigin(iata);
    const used = originFrequencyUsed(iata, excludeRouteId);
    const add = extraFreq || 0;
    const after = used + add;
    return { max, used, after, ok: after <= max, remaining: Math.max(0, max - after) };
  }

  function gateCapacityError(iata, freq, excludeRouteId) {
    if (!hasGateAt(iata)) return `Lease a gate at ${iata} first.`;
    const cap = gateCapacityLabel(iata, freq, excludeRouteId);
    if (cap.ok) return null;
    const gates = gateCountAt(iata);
    const per = airportGateWeeklyCapacity(airport(iata));
    return (
      `Your gates at ${iata} are full — lease another gate, lower frequency, or move departures. ` +
      `(${cap.after}/${cap.max} weekly departures = ${gates} gate${gates !== 1 ? 's' : ''} × ~${per}/wk each. ` +
      `Not “one route per gate” — it's total departures/week from this airport.)`
    );
  }

  /**
   * Human-readable gate math: capacity is departures/week, not “number of routes”.
   * Station build-out (Route Studio) is separate from leasing a gate.
   */
  function gateCapacityExplainHtml(iata) {
    if (!hasGateAt(iata)) {
      return `<p class="gate-math muted"><b>Gate vs station:</b> You need a <b>leased gate</b> at ${iata} to schedule departures. ` +
        `Route Studio’s <b>station build-out</b> is a one-time counters/signage cost when you open a market — it is <em>not</em> another gate.</p>`;
    }
    const util = gateUtilizationAt(iata);
    const per = util.perGate || airportGateWeeklyCapacity(airport(iata));
    const needAnother =
      util.remaining <= 0
        ? `At capacity — lease another gate at ${iata} (or cut frequency) before adding flights.`
        : util.remaining <= 3
          ? `Only <b>${util.remaining}</b> deps/wk free — next frequency bump may require another gate.`
          : `<b>${util.remaining}</b> departures/wk still open on your gate(s).`;
    return `<div class="gate-math">
      <p><b>${iata} gate capacity</b></p>
      <p class="muted" style="font-size:0.72rem;line-height:1.45;margin:4px 0 0;">
        <b>${util.gates}</b> gate${util.gates !== 1 ? 's' : ''} × ~<b>${per}</b> deps/wk each =
        <b>${util.max}</b>/wk max · using <b>${util.used}</b> · ${needAnother}<br>
        Math is <b>total weekly departures from ${iata}</b>, not “one route = one gate”.
        A single busy route can fill a gate; many thin routes can share one if total freq fits.
      </p>
      <p class="muted" style="font-size:0.68rem;margin:6px 0 0;">
        <b>Station build-out</b> (in Route Studio) ≠ leasing a gate. Build-out is paid once when you launch a new city-pair from here; gate lease is the ongoing slot that lets you fly.
      </p>
    </div>`;
  }

  function gateUtilizationAt(iata) {
    const cap = gateCapacityLabel(iata);
    const ap = airport(iata);
    const gates = gateCountAt(iata);
    const pct = cap.max > 0 ? (cap.used / cap.max) * 100 : 0;
    const routesFrom = (state.routes || []).filter((r) => r.origin === iata);
    const perGate = gates > 0 && ap ? airportGateWeeklyCapacity(ap) : 0;
    const idle = gates > 0 && cap.used === 0;
    const underutilized =
      gates > 0 &&
      cap.remaining >= 3 &&
      (pct < 70 || (routesFrom.length === 1 && pct < 85) || routesFrom.length === 0);
    const tight = cap.max > 0 && cap.remaining <= Math.max(1, Math.floor(cap.max * 0.08));
    return {
      iata,
      ap,
      ...cap,
      pct,
      gates,
      perGate,
      routesFrom,
      routeCount: routesFrom.length,
      idle,
      underutilized,
      tight,
    };
  }

  function allGateUtilizations() {
    const iatas = [...new Set((state.gates || []).map((g) => g.airport))];
    return iatas.map((iata) => gateUtilizationAt(iata)).sort((a, b) => a.pct - b.pct);
  }

  function primaryUnderutilizedHub() {
    return allGateUtilizations().find((u) => u.underutilized) || null;
  }

  function gateUtilPctClass(pct, util) {
    if (util && util.idle) return 'low';
    if (pct >= 78) return 'high';
    if (pct >= 45) return 'mid';
    return 'low';
  }

  function gateCapacityBarHtml(util, opts) {
    opts = opts || {};
    if (!util || !util.gates) return '';
    const pct = Math.min(100, util.pct || 0);
    const barClass =
      util.idle || util.pct < 35 ? 'util-bad' : util.underutilized ? 'util-warn' : util.tight ? 'util-warn' : 'util-good';
    const pctClass = gateUtilPctClass(pct, util);
    const label = opts.compact
      ? `${util.used}/${util.max}/wk`
      : `${util.used} of ${util.max} departures/wk scheduled`;
    return `<div class="gate-cap-head">
        <strong>${opts.title || util.iata + ' gate capacity'}</strong>
        <span class="gate-cap-pct ${pctClass}">${pct.toFixed(0)}% used</span>
      </div>
      <div class="util-bar ${barClass}" title="${label}"><span style="width:${pct}%"></span></div>
      <p class="gate-cap-note">${label} · <b>${util.remaining}</b> open · ${util.gates} gate${util.gates !== 1 ? 's' : ''} × ${util.perGate}/wk</p>`;
  }

  function gateUtilizationSuggestions(util) {
    if (!util || (!util.underutilized && !util.idle)) return [];
    return gateInefficiencyAlternatives(util).map((alt) => ({
      text: alt.text,
      action:
        alt.action === 'hub_routes'
          ? 'add_route'
          : alt.action === 'bump_freq'
            ? 'bump_freq'
            : alt.action === 'tab'
              ? 'fleet_tab'
              : alt.type || 'info',
      routeId: alt.routeId,
      delta: alt.delta,
      airport: alt.airport || util.iata,
      tab: alt.tab,
    }));
  }

  function gateUtilizationPromptHtml(util, opts) {
    opts = opts || {};
    if (!util || (!util.underutilized && !util.idle)) return '';
    const cardClass = util.idle ? 'gate-cap-card idle' : 'gate-cap-card warn';
    const suggestions = gateUtilizationSuggestions(util);
    const sugHtml = suggestions
      .map((s) => `<li>${s.text}</li>`)
      .join('');
    const actions = [];
    if (suggestions.some((s) => s.action === 'add_route')) {
      actions.push(
        `<button type="button" class="btn" data-hub-routes="${util.iata}">Plan route from ${util.iata}</button>`
      );
    }
    const bump = suggestions.find((s) => s.action === 'bump_freq');
    if (bump) {
      const br = routeById(bump.routeId) || (util.routesFrom && util.routesFrom[0]);
      const leg = br ? `${br.origin}–${br.dest}` : util.iata;
      actions.push(
        `<button type="button" class="btn" data-bump-freq="${bump.routeId}" data-bump-delta="${bump.delta}">+${bump.delta}/wk on ${leg}${findReverseRoute(br) ? ' (+ return)' : ''}</button>`
      );
    }
    if (suggestions.some((s) => s.action === 'fleet_tab')) {
      actions.push(
        `<button type="button" class="btn secondary" data-ops-tab="fleet">Open Fleet</button>`
      );
    }
    if (opts.showScout) {
      actions.push(
        `<button type="button" class="btn secondary" data-hub-scout="${util.iata}">View ${util.iata} on map</button>`
      );
    }
    return `<div class="${cardClass}">
      ${gateCapacityBarHtml(util, opts)}
      <ul class="list" style="margin:8px 0 0;font-size:0.72rem;">${sugHtml}</ul>
      ${actions.length ? `<div class="gate-cap-actions">${actions.join('')}</div>` : ''}
    </div>`;
  }

  function gateCapacityNetworkHtml() {
    const utils = allGateUtilizations();
    if (!utils.length) return '';
    const under = utils.filter((u) => u.underutilized || u.idle);
    let html = `<div class="panel-card" style="margin-bottom:10px;padding:10px 11px;">
      <p style="font-size:0.78rem;margin:0 0 8px;color:var(--gold);font-weight:600;">Gate capacity</p>`;
    utils.forEach((u) => {
      html += `<div class="gate-hub-row">
        <strong style="font-size:0.76rem;min-width:42px;">${u.iata}</strong>
        <div class="util-bar ${u.underutilized ? 'util-warn' : u.tight ? 'util-warn' : 'util-good'}" style="flex:1;">
          <span style="width:${Math.min(100, u.pct)}%"></span>
        </div>
        <span class="gate-cap-pct ${gateUtilPctClass(u.pct, u)}" style="min-width:52px;text-align:right;">${u.pct.toFixed(0)}%</span>
        <span class="muted" style="font-size:0.68rem;">${u.used}/${u.max}</span>
      </div>`;
    });
    html += `<p class="muted" style="font-size:0.66rem;margin:8px 0 0;">Departures/week per gate — limited by airport hours and turnaround.</p>`;
    html += fleetAvailabilityNetworkHtml();
    if (under.length) {
      html += under
        .slice(0, 2)
        .map((u) => gateUtilizationPromptHtml(u, { compact: true, showScout: false }))
        .join('');
    }
    html += '</div>';
    return html;
  }

  function bindGateCapacityActions(root) {
    const scope = root || document;
    scope.querySelectorAll('[data-hub-routes]').forEach((btn) => {
      if (btn._gateCapBound) return;
      btn._gateCapBound = true;
      btn.addEventListener('click', () => focusHubForRoutes(btn.dataset.hubRoutes));
    });
    scope.querySelectorAll('[data-hub-scout]').forEach((btn) => {
      if (btn._gateCapBound) return;
      btn._gateCapBound = true;
      btn.addEventListener('click', () => selectAirport(btn.dataset.hubScout));
    });
    scope.querySelectorAll('[data-bump-freq]').forEach((btn) => {
      if (btn._gateCapBound) return;
      btn._gateCapBound = true;
      btn.addEventListener('click', () => {
        bumpRouteFrequency(btn.dataset.bumpFreq, +btn.dataset.bumpDelta || 1);
      });
    });
    scope.querySelectorAll('[data-ops-tab]').forEach((btn) => {
      if (btn._gateCapBound) return;
      btn._gateCapBound = true;
      btn.addEventListener('click', () => switchTab(btn.dataset.opsTab));
    });
  }

  function focusHubForRoutes(iata) {
    if (!iata || !state) return;
    selectAirport(iata);
    switchTab('routes');
    const ap = airport(iata);
    setRouteFormDraft({
      origin: iata,
      originLabel: ap ? airportLabel(ap) : iata,
      dest: '',
      destLabel: '',
    });
    renderRoutes({ forceForm: true });
    // Jump straight into Route Studio from this hub when ready
    if (hasGateAt(iata) && state.fleet.length) {
      openRouteStudio({ origin: iata, step: 1 });
      return;
    }
    const form = $('route-launch-form');
    if (form) scrollSidePanelTo(form, { block: 'nearest' });
  }

  /**
   * Raise weekly frequency on a route. By default also bumps the reverse leg
   * by the same amount when it exists (keeps CMH⇄DAY balanced).
   */
  function bumpRouteFrequency(routeId, delta, opts) {
    opts = opts || {};
    const mirrorReturn = opts.mirrorReturn !== false;
    const quiet = !!opts.quiet;
    const route = routeById(routeId);
    if (!route || !delta) return false;
    const add = Math.max(1, Math.round(delta));
    const newFreq = (route.frequency_week || 0) + add;
    const routeMax = maxFrequencyForRoute(route.origin, route.dest, route.aircraft_type);
    const aircraftMax =
      maxFrequencyForAircraft(
        route.aircraft_id,
        route.origin,
        route.dest,
        route.aircraft_type,
        route.id
      ) + (route.frequency_week || 0);
    const capped = Math.min(newFreq, routeMax, aircraftMax);
    if (capped <= (route.frequency_week || 0)) {
      if (!quiet) {
        pushPlayerEvent(
          `could not add frequency on ${route.origin}–${route.dest} — at gate or aircraft schedule limit.`
        );
      }
      return false;
    }
    const capErr = gateCapacityError(route.origin, capped, route.id);
    if (capErr) {
      if (!quiet) pushPlayerEvent(capErr);
      return false;
    }
    const schedErr = aircraftScheduleError(
      route.aircraft_id,
      route.origin,
      route.dest,
      capped,
      route.aircraft_type,
      route.id
    );
    if (schedErr) {
      if (!quiet) pushPlayerEvent(schedErr);
      return false;
    }
    const before = route.frequency_week || 0;
    route.frequency_week = capped;
    const actualAdd = capped - before;
    if (!quiet) {
      pushPlayerEvent(
        `increased ${route.origin}–${route.dest} to ${capped}x/wk (+${actualAdd}) — more seats sold that direction, more gate use at ${route.origin}.`
      );
    }

    if (mirrorReturn && actualAdd > 0) {
      const reverse = findReverseRoute(route);
      if (reverse) {
        const revOk = bumpRouteFrequency(reverse.id, actualAdd, { mirrorReturn: false, quiet: true });
        if (revOk) {
          pushPlayerEvent(
            `matched return ${reverse.origin}–${reverse.dest} +${actualAdd}/wk — keep both legs balanced so Dayton traffic flies home paying, not empty.`
          );
        } else {
          pushEvent(
            `Could not fully match return ${reverse.origin}–${reverse.dest} (+${actualAdd}/wk) — check gate at ${reverse.origin} or aircraft hours.`,
            'bad'
          );
        }
      } else if (!quiet) {
        pushEvent(
          `No return leg for ${route.origin}–${route.dest}. Open ${route.dest}→${route.origin} so the plane does not ferry empty.`,
          'bad'
        );
      }
    }

    if (!quiet) {
      saveGame();
      renderRoutes();
      if (selectedAirport === route.origin || selectedAirport === route.dest) {
        renderAirportPanel(selectedAirport);
      }
      renderOpsGuide();
      renderHud();
    }
    return true;
  }

  function fleetMaxRangeNm() {
    let max = 0;
    (state.fleet || []).forEach((f) => {
      const ac = aircraftType(f.type);
      if (ac) max = Math.max(max, ac.range_nm || 0);
    });
    return max;
  }

  function reachableDestinationsFrom(originIata, opts) {
    opts = opts || {};
    const o = airport(originIata);
    if (!o) return [];
    const maxRange = opts.maxRange != null ? opts.maxRange : fleetMaxRangeNm();
    const excludeExisting = opts.excludeExisting !== false;
    const existing = new Set(
      (state.routes || []).filter((r) => r.origin === originIata).map((r) => r.dest)
    );
    const out = [];
    bootstrap.airports.forEach((dest) => {
      if (dest.iata === originIata) return;
      const dist = Math.round(haversineNm(o.lat, o.lon, dest.lat, dest.lon));
      if (maxRange > 0 && dist > maxRange) return;
      if (excludeExisting && existing.has(dest.iata)) return;
      out.push({ dest: dest.iata, city: dest.city, dist });
    });
    return out.sort((a, b) => a.dist - b.dist);
  }

  function bestFrequencyBumpFromGate(util) {
    if (!util || !util.routesFrom || !util.routesFrom.length) return null;
    // Prefer the thinnest leg or the one with most headroom — often the return from this city.
    let best = null;
    util.routesFrom.forEach((r) => {
      const routeMax = maxFrequencyForRoute(r.origin, r.dest, r.aircraft_type);
      const gateHead = util.remaining;
      const acHead =
        maxFrequencyForAircraft(r.aircraft_id, r.origin, r.dest, r.aircraft_type, r.id) || 0;
      const headroom = Math.min(gateHead, Math.max(0, routeMax - (r.frequency_week || 0)), acHead || 99);
      if (headroom < 1) return;
      const delta = Math.min(7, Math.max(1, headroom));
      const reverse = findReverseRoute(r);
      const score = headroom + (reverse ? 2 : 0) + ((r.frequency_week || 0) < 10 ? 1 : 0);
      if (!best || score > best.score) {
        best = { route: r, delta, reverse, headroom, score };
      }
    });
    return best;
  }

  function gateInefficiencyAlternatives(util) {
    if (!util || !state) return [];
    const alts = [];
    const leaseMo = (state.gates || [])
      .filter((g) => g.airport === util.iata)
      .reduce((s, g) => s + (g.monthly || 0), 0);

    if (!state.fleet.length) {
      alts.push({
        type: 'fleet',
        text: `Paying <b>${fmtMoney(leaseMo)}/mo</b> for an empty gate — lease aircraft in <b>Fleet</b> first.`,
        action: 'tab',
        tab: 'fleet',
      });
      return alts;
    }

    const maxRange = fleetMaxRangeNm();
    const reachable = reachableDestinationsFrom(util.iata);
    const ideas = routeSuggestionsFrom(util.iata).filter(
      (s) => !(state.routes || []).some((r) => r.origin === util.iata && r.dest === s.dest)
    );
    const idlePlanes = state.fleet.filter((f) => !(state.routes || []).some((r) => r.aircraft_id === f.id));

    // 1) Prefer increasing frequency on existing service from this gate (e.g. DAY→CMH return).
    const bump = bestFrequencyBumpFromGate(util);
    if (bump) {
      const r = bump.route;
      const revNote = bump.reverse
        ? ` Also matches return <b>${bump.reverse.origin}–${bump.reverse.dest}</b> when capacity allows.`
        : ` No return leg yet — consider opening <b>${r.dest}→${r.origin}</b>.`;
      alts.push({
        type: 'bump_freq',
        text:
          `Add <b>+${bump.delta}/wk</b> on <b>${r.origin}–${r.dest}</b> (departures from <b>${util.iata}</b>) — sells more seats that direction and uses open gate time.${revNote}`,
        action: 'bump_freq',
        routeId: r.id,
        delta: bump.delta,
        mirrorReturn: true,
      });
    }

    if (idlePlanes.length) {
      const ac = aircraftType(idlePlanes[0].type);
      alts.push({
        type: 'idle_plane',
        text: `<b>${ac ? ac.name : 'Aircraft'}</b> has no route — assign it from <b>${util.iata}</b> or elsewhere.`,
        action: 'hub_routes',
        airport: util.iata,
      });
    } else if (state.fleet.length && !bump) {
      const busiest = state.fleet
        .map((f) => {
          const cap = planeWeeklyBlockHoursCapacity(f);
          const used = planeWeeklyBlockHoursUsed(f.id);
          return { f, cap, used, pct: cap > 0 ? (used / cap) * 100 : 100 };
        })
        .sort((a, b) => b.pct - a.pct)[0];
      if (busiest && busiest.pct >= 92) {
        alts.push({
          type: 'plane_full',
          text:
            `Gate has open slots but <b>every aircraft is fully scheduled</b> (~${busiest.used.toFixed(0)}/${busiest.cap.toFixed(0)} block-hr/wk). ` +
            `Lease a second plane — one aircraft, one place at a time.`,
          action: 'tab',
          tab: 'fleet',
        });
      }
    }

    // 2) New destinations are secondary — only after frequency on what you already fly.
    if (ideas.length) {
      const top = ideas
        .slice(0, 3)
        .map((s) => s.dest)
        .join(', ');
      alts.push({
        type: 'add_route',
        text: `Or open a <b>new</b> market from ${util.iata}: <b>${reachable.length}</b> in range · top demand <b>${top}</b>.`,
        action: 'hub_routes',
        airport: util.iata,
      });
    } else if (util.routeCount > 0 && util.remaining >= 3 && !bump) {
      const r = util.routesFrom[0];
      if (r) {
        alts.push({
          type: 'freq_maxed',
          text: `${r.origin}–${r.dest} is near schedule max for your aircraft — need another route or longer-range plane.`,
        });
      }
    } else if (reachable.length === 0 && maxRange > 0) {
      const longer = Object.values(bootstrap.aircraft_types || {})
        .filter((ac) => ac.range_nm > maxRange)
        .sort((a, b) => (a.lease_monthly || 0) - (b.lease_monthly || 0))[0];
      if (longer) {
        alts.push({
          type: 'range',
          text: `Fleet max <b>${maxRange} nm</b> — can't reach new markets from ${util.iata}. <b>${longer.name}</b> (${longer.range_nm} nm) opens more routes.`,
          action: 'tab',
          tab: 'fleet',
        });
      } else {
        alts.push({
          type: 'range',
          text: `Nothing in range with current aircraft (${maxRange} nm max from ${util.iata}).`,
        });
      }
    }

    if (leaseMo > 0 && util.pct < 55) {
      alts.push({
        type: 'cost',
        text: `~<b>${fmtMoney(leaseMo * (util.remaining / Math.max(1, util.max)))}/mo</b> of lease buys unused departure slots.`,
      });
    }

    return alts;
  }

  function enrichCompetitorLog(log, cr) {
    if (!log) return log;
    if (cr) {
      log.routeOrigin = cr.origin;
      log.routeDest = cr.dest;
    }
    return log;
  }

  function routesAffectedByCompetitor(log) {
    if (!log || !state || !state.routes.length) return [];
    const hits = [];
    state.routes.forEach((route) => {
      let reason = null;
      let severity = 1;
      if (
        log.routeOrigin &&
        log.routeDest &&
        ((route.origin === log.routeOrigin && route.dest === log.routeDest) ||
          (route.origin === log.routeDest && route.dest === log.routeOrigin))
      ) {
        reason = 'same city pair';
        severity = 3;
      } else if (log.airport && route.origin === log.airport) {
        reason = `origin ${log.airport}`;
        severity = 2;
      } else if (log.airport && route.dest === log.airport) {
        reason = `serves ${log.airport}`;
        severity = 1.5;
      } else if (
        log.routeOrigin &&
        (route.origin === log.routeOrigin ||
          route.dest === log.routeOrigin ||
          route.origin === log.routeDest ||
          route.dest === log.routeDest)
      ) {
        reason = 'overlapping market';
        severity = 2;
      }
      if (!reason) return;
      const sim = simulateRouteDay(route);
      hits.push({
        route,
        reason,
        severity,
        load: sim.grounded ? null : sim.load,
        pnl: (sim.revenue || 0) - (sim.cost || 0),
      });
    });
    return hits.sort((a, b) => b.severity - a.severity);
  }

  function competitorImpactHtml(log) {
    const hits = routesAffectedByCompetitor(log);
    if (!hits.length) {
      return '<div class="competitor-impact"><h4>Your routes</h4><p class="muted">No direct overlap with active routes — monitor loads if you expand into this market.</p></div>';
    }
    const rows = hits
      .map((h) => {
        const load =
          h.load != null ? `${(h.load * 100).toFixed(0)}% load` : 'AOG';
        const pnlClass = h.pnl >= 0 ? '' : 'danger';
        return `<li><b>${h.route.origin}–${h.route.dest}</b> <span class="muted">(${h.reason})</span> · ${load} · <span class="${pnlClass}">${fmtMoney(h.pnl)}/day</span></li>`;
      })
      .join('');
    return `<div class="competitor-impact"><h4>Your routes affected</h4><ul class="list">${rows}</ul></div>`;
  }

  function formatCompetitorEventMsg(log) {
    const hits = routesAffectedByCompetitor(log);
    if (!hits.length) return log.msg;
    const names = hits
      .slice(0, 3)
      .map((h) => `${h.route.origin}–${h.route.dest}`)
      .join(', ');
    return `${log.msg} — affects <b>${names}</b>`;
  }

  function competitorEventTier(type) {
    return type === 'exit' || type === 'pullback' || type === 'fare_rise' || type === 'demand_surge' ? 'good' : 'bad';
  }

  function processMonthlyGateEfficiency() {
    // Soft start: no gate-tax nagging while you're still learning (first ~2 months)
    if (!state || state.game_over || state.day < 55) return;
    const utils = allGateUtilizations().filter((u) => u.underutilized || u.idle);
    if (!utils.length) return;
    if (!state.gate_nudge_day) state.gate_nudge_day = {};

    utils.forEach((util) => {
      // When cash is critical, nudge less often — focus on runway coach instead
      const nudgeGap = runwayMonths() < 3 ? 45 : 28;
      if (state.day - (state.gate_nudge_day[util.iata] || 0) < nudgeGap) return;
      state.gate_nudge_day[util.iata] = state.day;
      const leaseMo = state.gates
        .filter((g) => g.airport === util.iata)
        .reduce((s, g) => s + (g.monthly || 0), 0);
      const alts = gateInefficiencyAlternatives(util);
      let msg = `<b>${util.iata}</b> gate <b>${util.pct.toFixed(0)}%</b> used (${util.used}/${util.max} departures/wk) — <b>${util.remaining}</b> open · ${fmtMoney(leaseMo)}/mo lease.`;
      if (alts[0]) msg += ` ${alts[0].text}`;
      pushEvent(msg);
    });

    const worst = utils[0];
    // Skip modal pile-on when you're already in a cash crisis
    if (runwayMonths() < 2.5) return;
    if (
      !worst ||
      worst.pct >= 58 ||
      activeDecision ||
      decisionQueue.length ||
      state.day - (state.last_gate_efficiency_decision_day || 0) < 50
    ) {
      return;
    }

    const alts = gateInefficiencyAlternatives(worst);
    const leaseMo = state.gates
      .filter((g) => g.airport === worst.iata)
      .reduce((s, g) => s + (g.monthly || 0), 0);
    const options = [];
    const letters = 'ABCDEFG';
    let optIdx = 0;
    const bump = alts.find((a) => a.action === 'bump_freq') || bestFrequencyBumpFromGate(worst);
    if (bump && (bump.routeId || (bump.route && bump.route.id))) {
      const routeId = bump.routeId || bump.route.id;
      const r = routeById(routeId);
      const delta = bump.delta || 3;
      const leg = r ? `${r.origin}–${r.dest}` : 'existing route';
      const hasRev = r && findReverseRoute(r);
      options.push({
        id: 'bump',
        label: `${letters[optIdx++]} — Increase ${leg} +${delta}/wk${hasRev ? ' (match return)' : ''}`,
        hint: hasRev
          ? `More departures from ${worst.iata}; return leg bumps by the same amount when capacity allows.`
          : `Uses open gate time at ${worst.iata} — open a return later so the plane does not ferry empty.`,
        effect: 'bump_route_freq',
        routeId,
        delta,
        mirrorReturn: true,
      });
    }
    if (alts.some((a) => a.action === 'hub_routes')) {
      options.push({
        id: 'route',
        label: `${letters[optIdx++]} — Plan a new route from ${worst.iata}`,
        hint: 'Only if frequency on current legs is already solid.',
        effect: 'hub_routes',
        airport: worst.iata,
      });
    }
    if (alts.some((a) => a.action === 'tab' && a.tab === 'fleet')) {
      options.push({
        id: 'fleet',
        label: `${letters[optIdx++]} — Review Fleet (range / idle aircraft)`,
        hint: 'Longer range or spare aircraft may unlock routes.',
        effect: 'tab_fleet',
      });
    }
    options.push({
      id: 'ignore',
      label: `${letters[optIdx] || 'A'} — Ignore for now`,
      hint: 'Idle gate time still costs lease every month.',
      effect: 'none',
    });

    state.last_gate_efficiency_decision_day = state.day;
    const fromHere = (worst.routesFrom || []).map((r) => `${r.origin}–${r.dest} ${r.frequency_week}/wk`).join(' · ');
    queueDecision({
      airport: worst.iata,
      kicker: `${fmtDate(state.day)} · Gate efficiency`,
      title: `${worst.iata} gate underused (${worst.pct.toFixed(0)}%)`,
      body:
        `You lease <b>${fmtMoney(leaseMo)}/mo</b> at <b>${worst.iata}</b> but only schedule <b>${worst.used}/${worst.max}</b> weekly departures (<b>${worst.remaining}</b> open).` +
        (fromHere
          ? `<p class="muted" style="font-size:0.8rem;margin:8px 0 0;">Departures you already fly from ${worst.iata}: <b>${fromHere}</b>. Increasing frequency here is usually better than a brand-new city.</p>`
          : '') +
        (alts.length
          ? `<ul class="list" style="margin:10px 0;font-size:0.78rem;">${alts
              .slice(0, 3)
              .map((a) => `<li>${a.text}</li>`)
              .join('')}</ul>`
          : ''),
      teach:
        'Prefer adding frequency on the pair you already fly (both ways when possible). New destinations come after the current service is dense enough to use the gate you pay for.',
      logLine: `${worst.iata} gate ${worst.pct.toFixed(0)}% utilized`,
      options,
    });
  }

  function fareOptimizerChartHtml(draft) {
    const plane = state.fleet.find((f) => f.id === draft.aircraftId);
    if (!plane) return '';
    const market = marketFareForPair(draft.origin, draft.dest, plane.type);
    const scanMin = Math.max(49, Math.round(market * 0.52));
    const scanMax = Math.min(899, Math.round(market * 2.15));
    const points = [];
    for (let f = scanMin; f <= scanMax; f += 5) {
      const econ = projectRouteBusinessCase({ ...draft, fare: f });
      if (!econ) continue;
      points.push({
        fare: f,
        monthlyNet: econ.monthlyNet,
        load: econ.via.load || 0,
        monthlyVariable: econ.monthlyVariable || 0,
      });
    }
    if (points.length < 4) return '';

    const best = points.reduce((a, b) => (b.monthlyNet > a.monthlyNet ? b : a), points[0]);
    let peakIdx = points.findIndex((p) => p.fare === best.fare);
    if (peakIdx < 0) peakIdx = points.reduce((bi, p, i, arr) => (p.monthlyNet > arr[bi].monthlyNet ? i : bi), 0);
    const tailDecline = points.slice(peakIdx).some((p, i, arr) => i > 0 && p.monthlyNet < arr[i - 1].monthlyNet - 500);
    const viewStart = Math.max(0, peakIdx - 6);
    const viewEnd = Math.min(
      points.length - 1,
      tailDecline ? Math.min(points.length - 1, peakIdx + 14) : Math.min(points.length - 1, peakIdx + 8)
    );
    const view = points.slice(viewStart, viewEnd + 1);

    const width = 320;
    const height = 108;
    const margin = { l: 44, r: 12, t: 10, b: 24 };
    const innerW = width - margin.l - margin.r;
    const innerH = height - margin.t - margin.b;
    const minF = view[0].fare;
    const maxF = view[view.length - 1].fare;
    const nets = view.map((p) => p.monthlyNet);
    let minN = Math.min(...nets, 0);
    let maxN = Math.max(...nets);
    if (minN === maxN) {
      minN -= 5000;
      maxN += 5000;
    }
    const pad = (maxN - minN) * 0.14;
    minN -= pad;
    maxN += pad;
    const xAt = (fare) => margin.l + ((fare - minF) / (maxF - minF || 1)) * innerW;
    const yAt = (v) => margin.t + innerH - ((v - minN) / (maxN - minN)) * innerH;

    let pathD = '';
    view.forEach((p) => {
      const seg = `${xAt(p.fare).toFixed(1)},${yAt(p.monthlyNet).toFixed(1)}`;
      pathD += pathD ? ` L${seg}` : `M${seg}`;
    });

    const cur = projectRouteBusinessCase(draft);
    const curLoad = cur && cur.via ? cur.via.load || 0 : 0;
    const curFareClamped = Math.max(minF, Math.min(maxF, draft.fare));
    const curX = xAt(curFareClamped).toFixed(1);
    const curY = cur ? yAt(cur.monthlyNet).toFixed(1) : yAt(0).toFixed(1);
    const mktX = xAt(Math.max(minF, Math.min(maxF, market))).toFixed(1);
    const peakX = xAt(best.fare).toFixed(1);
    const peakY = yAt(best.monthlyNet).toFixed(1);
    const zeroY = yAt(0).toFixed(1);

    const capNote =
      curLoad >= 0.88
        ? ' <span class="muted">· High load — yield rises until demand thins</span>'
        : '';
    const offChart =
      draft.fare < minF || draft.fare > maxF
        ? ` <span class="muted">· Your fare ($${draft.fare}) is outside the zoom window</span>`
        : '';

    return `<div class="judgment-fare-chart">
      <p class="muted" style="font-size:0.66rem;margin:0 0 6px;">Fare vs burdened net/mo — demand eases as price rises above market; peak near <b>$${best.fare}</b> (~${Math.round((best.load || 0) * 100)}% load).${capNote}${offChart}</p>
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Fare optimizer chart">
        <line x1="${margin.l}" y1="${zeroY}" x2="${width - margin.r}" y2="${zeroY}" class="chart-grid"/>
        <line x1="${mktX}" y1="${margin.t}" x2="${mktX}" y2="${height - margin.b}" class="chart-fare-market"/>
        <path d="${pathD}" fill="none" stroke="#00c896" stroke-width="2"/>
        <circle cx="${peakX}" cy="${peakY}" r="3" fill="none" stroke="#00c896" stroke-width="1.5"/>
        <line x1="${curX}" y1="${margin.t}" x2="${curX}" y2="${height - margin.b}" class="chart-fare-cursor"/>
        <circle cx="${curX}" cy="${curY}" r="4" fill="#ffd166" stroke="#041018" stroke-width="1"/>
        <text x="${margin.l}" y="${height - 6}" class="chart-axis">$${minF}</text>
        <text x="${width - margin.r}" y="${height - 6}" class="chart-axis" text-anchor="end">$${maxF}</text>
        <text x="${margin.l - 4}" y="${yAt(maxN).toFixed(1)}" class="chart-axis" text-anchor="end">${fmtMoney(maxN)}</text>
        <text x="${margin.l - 4}" y="${zeroY}" class="chart-axis" text-anchor="end">$0</text>
        <text x="${mktX}" y="${margin.t + 8}" class="chart-axis" text-anchor="middle">mkt</text>
      </svg>
    </div>`;
  }

  function ensureMarketingInvestments() {
    if (!state) return;
    if (!state.marketing_investments) {
      state.marketing_investments = { state: {}, national: 0, world: 0 };
    }
    if (!state.marketing_investments.state) state.marketing_investments.state = {};
    if (!state.hub_ota_push) state.hub_ota_push = {};
  }

  function stationSetupCost(origin, dest) {
    const o = airport(origin);
    const d = airport(dest);
    if (!o || !d) return 25000;
    // First city-pair launched FROM this origin pays full station build-out;
    // additional markets from the same station are cheaper (already set up).
    const routesAtOrigin = state.routes.filter((r) => r.origin === origin).length;
    const base = 16000 + (o.annual_pax_m || 1) * 2400;
    const destPremium = (d.annual_pax_m || 1) * 900;
    const firstStation = routesAtOrigin === 0 ? 14000 : 4000;
    return Math.round(base + destPremium + firstStation);
  }

  function stationSetupExplainHtml(origin, dest) {
    const cost = stationSetupCost(origin, dest);
    const first = !(state.routes || []).some((r) => r.origin === origin);
    const hasGate = hasGateAt(origin);
    return `<p class="station-math muted" style="font-size:0.72rem;line-height:1.45;">
      <b>Station build-out ${fmtMoney(cost)}</b> — one-time counters/signage/ground ops for this market
      ${first ? '(first launch from ' + origin + ' is pricier)' : '(you already have a station footprint at ' + origin + ')'}.
      ${hasGate
        ? `You <b>already lease a gate</b> at ${origin}; build-out is <em>not</em> a second gate.`
        : `You still need a <b>gate lease</b> at ${origin} before departures can schedule.`}
    </p>`;
  }

  function hubOtaMonthlyCost() {
    ensureMarketingInvestments();
    let total = 0;
    Object.keys(state.hub_ota_push || {}).forEach((iata) => {
      (state.hub_ota_push[iata] || []).forEach((pid) => {
        const p = (bootstrap.ota_platforms || []).find((x) => x.id === pid);
        if (p) total += p.hub_push_monthly || 0;
      });
    });
    return total;
  }

  function routeOtaFeatureMonthlyCost() {
    let total = 0;
    (state.routes || []).forEach((route) => {
      (route.featured_ota || []).forEach((pid) => {
        const p = (bootstrap.ota_platforms || []).find((x) => x.id === pid);
        if (p) total += p.route_feature_monthly || 0;
      });
    });
    return total;
  }

  function scopedMarketingMonthly() {
    ensureMarketingInvestments();
    const inv = state.marketing_investments;
    const stateSum = Object.values(inv.state || {}).reduce((s, v) => s + clampMoney(v), 0);
    return stateSum + clampMoney(inv.national) + clampMoney(inv.world);
  }

  function airportMarketingDemandLift(iata, opts) {
    opts = opts || {};
    // Must not call simulateRouteDay / airportScopedDailyEconomics (infinite recursion via demandForRoute).
    const gross = Math.max(airportGrossProxyMonthly(iata), 40_000);
    let spend = clampMoney(state.marketing_spend_monthly[iata]);
    if (opts.airportSpendByIata && opts.airportSpendByIata[iata] != null) {
      spend = clampMoney(opts.airportSpendByIata[iata]);
    }
    if (spend <= 0) return 0;
    // ~$5–12k/mo at a thin station should feel like +10–25% demand, not a rounding error.
    return Math.min(0.35, (spend / gross) * 3.6);
  }

  /**
   * Marketing demand multiplier. opts.investments / opts.airportSpendByIata for Studio drafts
   * so judgment load rises when the player turns ads on before launch.
   */
  function marketingDemandBonus(origin, dest, opts) {
    opts = opts || {};
    ensureMarketingInvestments();
    const inv = opts.investments || null;
    let mult = 1;
    const o = airport(origin);
    const d = airport(dest);
    mult += airportMarketingDemandLift(origin, opts);
    if (d) mult += airportMarketingDemandLift(dest, opts) * 0.65;
    if (o && o.state) {
      const stateSpend =
        inv && inv.state != null
          ? clampMoney(inv.state)
          : clampMoney(state.marketing_investments.state[o.state]);
      mult += stateSpend / 140000;
    }
    const national =
      inv && inv.national != null
        ? clampMoney(inv.national)
        : clampMoney(state.marketing_investments.national);
    const world =
      inv && inv.world != null
        ? clampMoney(inv.world)
        : clampMoney(state.marketing_investments.world);
    mult += national / 320000;
    mult += world / 700000;
    return Math.min(1.65, mult);
  }

  /** Human-readable marketing effect for a city (for UI + coach messages). */
  function marketingImpactSummary(iata) {
    const spend = clampMoney(state.marketing_spend_monthly[iata]);
    const lift = airportMarketingDemandLift(iata);
    const aware = state.brand_awareness[iata] || 0;
    const liftPct = Math.round(lift * 100);
    return {
      spend,
      lift,
      liftPct,
      aware,
      line:
        spend > 0
          ? `${fmtMoney(spend)}/mo at ${iata} → about <b>+${liftPct}%</b> local demand · brand ${aware.toFixed(0)}%`
          : `No airport marketing at ${iata} — brand ${aware.toFixed(0)}%`,
    };
  }

  function routeMarketingLiftPct(route) {
    if (!route) return 0;
    const before = 1;
    const after = marketingDemandBonus(route.origin, route.dest);
    return Math.round((after / before - 1) * 100);
  }

  function syncRouteFormFields() {
    const pairs = [
      ['rt-origin-search', 'rt-origin-code'],
      ['rt-dest-search', 'rt-dest-code'],
    ];
    pairs.forEach(([inputId, hiddenId]) => {
      const input = $(inputId);
      const hidden = $(hiddenId);
      if (!input || !hidden) return;
      const ap = resolveAirportQuery(input.value);
      if (ap) hidden.value = ap.iata;
    });
  }

  function leaseGate(iata, tier, years) {
    const ap = airport(iata);
    if (!ap) return;
    const monthly = tier === 'exclusive' ? ap.lease_exclusive_monthly : ap.lease_common_monthly;
    const upfront = monthly * 2;
    if (state.cash < upfront) {
      alert('Insufficient cash for deposit.');
      return;
    }
    if (ap.gates_available <= 0) {
      alert('No gates available at this airport.');
      return;
    }
    state.cash -= upfront;
    ap.gates_available -= 1;
    state.gates.push({
      airport: iata,
      tier,
      monthly,
      months_left: years * 12,
      years_left: years,
    });
    const n = gateCountAt(iata) + 1;
    pushPlayerEvent(`leased ${tier} gate #${n} at ${iata} (${years}yr, ${fmtMoney(upfront)} deposit).`);
    saveGame();
    renderAll();
  }

  function buildRouteLaunchDraft(origin, dest, aircraftId, freq, fare) {
    ensureMarketingInvestments();
    ensureMacro();
    const oAp = airport(origin);
    const plane = state.fleet.find((f) => f.id === aircraftId);
    const acType = plane ? plane.type : null;
    const marketFare =
      origin && dest && origin !== dest ? marketFareForPair(origin, dest, acType) : 129;
    const f = fare || marketFare;
    const returnExists =
      !!(dest && origin) &&
      (state.routes || []).some((r) => r.origin === dest && r.dest === origin);
    const draft = {
      origin: origin || '',
      dest: dest || '',
      aircraftId: aircraftId || '',
      freq: freq || 7,
      fare: f,
      fareMode: 'manual',
      withReturn: !returnExists,
      product: 'standard',
      tag_dest: '',
      stationCost: stationSetupCost(origin || dest, dest || origin),
      investments: {
        airport: clampMoney(state.marketing_spend_monthly[origin] || 0),
        state: oAp && oAp.state ? clampMoney(state.marketing_investments?.state?.[oAp.state]) : 0,
        national: clampMoney(state.marketing_investments?.national),
        world: clampMoney(state.marketing_investments?.world),
      },
      ota: {},
    };
    (bootstrap.ota_platforms || []).forEach((p) => {
      draft.ota[p.id] = {
        list: !!(state.macro && state.macro.ota_listed && state.macro.ota_listed[p.id]),
        feature: false,
        hubPush: !!(state.hub_ota_push && state.hub_ota_push[origin] && state.hub_ota_push[origin].includes(p.id)),
      };
    });
    return draft;
  }

  function projectRouteBusinessCase(draft) {
    const plane = state.fleet.find((f) => f.id === draft.aircraftId);
    const ac = plane ? aircraftType(plane.type) : null;
    if (!plane || !ac) return null;

    const routesAtOrigin = state.routes.filter((r) => r.origin === draft.origin).length;
    // Draft marketing/OTA so judgment load rises when ads/distribution are selected
    // (cost and demand must use the same snapshot — otherwise more spend looks worse).
    const airportSpendByIata = {
      ...(state.marketing_spend_monthly || {}),
      [draft.origin]: clampMoney(draft.investments?.airport),
    };
    const featured = [];
    (bootstrap.ota_platforms || []).forEach((p) => {
      const o = draft.ota && draft.ota[p.id];
      if (o && o.feature) featured.push(p.id);
    });
    const projOpts = {
      commit: false,
      airportSpendByIata,
      investments: draft.investments || {},
      draftOta: draft.ota || {},
    };
    const mockRoute = {
      origin: draft.origin,
      dest: draft.dest,
      aircraft_type: plane.type,
      aircraft_id: draft.aircraftId,
      frequency_week: draft.freq,
      fare: draft.fare,
      fare_mode: 'manual',
      ancillary_mode: state.ancillary_strategy || 'auto',
      featured_ota: featured,
    };
    const sim = simulateRouteDay(mockRoute, projOpts);
    const via = estimateRouteViability(
      draft.origin,
      draft.dest,
      plane.type,
      draft.freq,
      draft.fare,
      draft.aircraftId,
      projOpts
    );
    const schedScale = planeScheduleScaleForRoute(plane.id, mockRoute);
    const dailyVariable = (sim.revenue || 0) - (sim.cost || 0);
    const monthlyVariable = dailyVariable * 30;

    let upfront = draft.stationCost || 0;
    ensureMacro();
    (bootstrap.ota_platforms || []).forEach((p) => {
      const o = draft.ota && draft.ota[p.id];
      if (o && o.list && !state.macro.ota_listed[p.id]) upfront += p.listing_monthly || 0;
    });

    const routesOnPlane = state.routes.filter((r) => r.aircraft_id === draft.aircraftId).length;
    const isNewStation = routesAtOrigin === 0;
    const gateMonthly = state.gates
      .filter((g) => g.airport === draft.origin)
      .reduce((s, g) => s + (g.monthly || 0), 0);
    const gateShare = gateMonthly / Math.max(1, routesAtOrigin + 1);
    const fleetShare = plane.leased ? (ac.lease_monthly || 0) / Math.max(1, routesOnPlane + 1) : 0;
    const marketingMonthly =
      clampMoney(draft.investments?.airport) +
      clampMoney(draft.investments?.state) +
      clampMoney(draft.investments?.national) +
      clampMoney(draft.investments?.world);
    let otaMonthly = 0;
    (bootstrap.ota_platforms || []).forEach((p) => {
      const o = draft.ota && draft.ota[p.id];
      if (!o) return;
      if (o.list) otaMonthly += p.listing_monthly || 0;
      if (o.feature) otaMonthly += p.route_feature_monthly || 0;
      if (o.hubPush) otaMonthly += p.hub_push_monthly || 0;
    });
    const corpShare = playerNaturalOverheadMonthly() / Math.max(1, state.routes.length + 1);
    const monthlyFixed = gateShare + fleetShare + marketingMonthly + otaMonthly + corpShare;
    const monthlyNet = monthlyVariable - monthlyFixed;

    let breakEvenMonths = null;
    let breakEvenYears = null;
    let breakEvenMonthsRoute = null;
    let breakEvenYearsRoute = null;
    if (monthlyNet > 0 && upfront > 0) {
      breakEvenMonths = upfront / monthlyNet;
      breakEvenYears = breakEvenMonths / 12;
    } else if (monthlyNet > 0 && upfront <= 0) {
      breakEvenMonths = 0;
      breakEvenYears = 0;
    }
    if (monthlyVariable > 0 && upfront > 0) {
      breakEvenMonthsRoute = upfront / monthlyVariable;
      breakEvenYearsRoute = breakEvenMonthsRoute / 12;
    } else if (monthlyVariable > 0 && upfront <= 0) {
      breakEvenMonthsRoute = 0;
      breakEvenYearsRoute = 0;
    }

    let verdict = 'poor';
    let verdictLabel = 'Weak business case';
    let verdictClass = 'judgment-poor';
    if (monthlyNet <= 0) {
      verdictLabel = 'Does not break even';
      verdictClass = 'judgment-poor';
    } else if (breakEvenYears <= 1) {
      verdict = 'strong';
      verdictLabel = 'Strong business case';
      verdictClass = 'judgment-strong';
    } else if (breakEvenYears <= 2) {
      verdict = 'ok';
      verdictLabel = 'Acceptable — patience required';
      verdictClass = 'judgment-ok';
    } else if (breakEvenYears <= routeEconomics().marginal_payback_warn_years) {
      verdict = 'marginal';
      verdictLabel = 'Marginal — long payback';
      verdictClass = 'judgment-warn';
    } else {
      verdictLabel = `Poor — ~${breakEvenYears.toFixed(1)} years to recover launch costs`;
      verdictClass = 'judgment-poor';
    }

    return {
      sim,
      via,
      dailyVariable,
      monthlyVariable,
      monthlyFixed,
      monthlyNet,
      upfront,
      breakEvenMonths,
      breakEvenYears,
      breakEvenMonthsRoute,
      breakEvenYearsRoute,
      monthlyNetRouteOnly: monthlyVariable,
      verdict,
      verdictLabel,
      verdictClass,
      gateShare,
      fleetShare,
      marketingMonthly,
      otaMonthly,
      corpShare,
      routesAtOrigin,
      isNewStation,
      schedScale,
    };
  }

  function recommendLaunchFare(draft) {
    const plane = state.fleet.find((f) => f.id === draft.aircraftId);
    if (!plane) return null;
    const market = marketFareForPair(draft.origin, draft.dest, plane.type);
    let best = null;
    for (let f = Math.max(49, Math.round(market * 0.72)); f <= Math.min(899, Math.round(market * 1.28)); f += 4) {
      const econ = projectRouteBusinessCase({ ...draft, fare: f });
      if (!econ) continue;
      const score =
        econ.monthlyNet > 0
          ? econ.monthlyNet * 12 - (econ.breakEvenYears || 99) * 8000
          : econ.monthlyNet;
      if (!best || score > best.score) best = { fare: f, econ, score, market };
    }
    return best;
  }

  function projectRouteYearlyOutlook(draft) {
    const steady = projectRouteBusinessCase(draft);
    if (!steady) return [];
    const cfg = routeEconomics();
    const ramps = cfg.ramp_load_multipliers || [0.55, 0.78, 0.92];
    const creep = cfg.ramp_cost_creep_per_year || 0.03;
    ensureMacro();
    const infl = (state.macro.inflation_pct || 2) / 100;
    let cumulative = -(steady.upfront || 0);
    return ramps.map((ramp, i) => {
      const year = i + 1;
      const monthlyVar = steady.monthlyVariable * ramp * (1 + infl * i * 0.35);
      const monthlyFixed = steady.monthlyFixed * (1 + creep * i + infl * i * 0.25);
      const monthlyNet = monthlyVar - monthlyFixed;
      const yearProfit = monthlyNet * 12;
      cumulative += yearProfit;
      return {
        year,
        monthlyNet,
        yearProfit,
        cumulative,
        loadPct: Math.round((steady.via.load || 0) * ramp * 100),
      };
    });
  }

  function fareSensitivityHtml(draft) {
    const plane = state.fleet.find((f) => f.id === draft.aircraftId);
    if (!plane) return '';
    const market = marketFareForPair(draft.origin, draft.dest, plane.type);
    const lowFare = Math.max(49, Math.round(draft.fare * 0.85));
    const highFare = Math.min(899, Math.round(draft.fare * 1.15));
    const base = projectRouteBusinessCase(draft);
    const low = projectRouteBusinessCase({ ...draft, fare: lowFare });
    const high = projectRouteBusinessCase({ ...draft, fare: highFare });
    if (!base || !low || !high) return '';
    const fmtNet = (e) =>
      e.monthlyNet >= 0 ? fmtMoney(e.monthlyNet) + '/mo' : fmtMoney(e.monthlyNet) + '/mo loss';
    return `<p class="judgment-fare-note">
      Fare <b>$${draft.fare}</b> vs market <b>$${market}</b> — judgment updates as you change fare or frequency.
      Sensitivity: <span class="muted">$${lowFare}</span> → ${(low.via.load * 100).toFixed(0)}% load · ${fmtNet(low)};
      <span class="muted">$${highFare}</span> → ${(high.via.load * 100).toFixed(0)}% load · ${fmtNet(high)}.
    </p>`;
  }

  function routeBusinessJudgmentHtml(draft) {
    const econ = projectRouteBusinessCase(draft);
    if (!econ) return '<p class="muted">Select an aircraft to judge this route.</p>';
    const cfg = routeEconomics();
    const rec = recommendLaunchFare(draft);
    const yearly = projectRouteYearlyOutlook(draft);
    const loadPct = (econ.via.load * 100).toFixed(0);
    const hubTarget = cfg.hub_profit_target_years || 2.5;
    const paybackBurdened =
      econ.monthlyNet <= 0
        ? `<span class="danger">Never</span> — loses <b>${fmtMoney(Math.abs(econ.monthlyNet))}/mo</b> after gate, aircraft, HQ &amp; launch costs.`
        : econ.breakEvenYears <= 0
          ? '<b>Immediate</b>'
          : `<b>~${econ.breakEvenYears.toFixed(1)} yr</b> (${Math.round(econ.breakEvenMonths)} mo)`;
    const paybackRoute =
      econ.monthlyNetRouteOnly <= 0
        ? `<span class="danger">Never</span> on route margin alone`
        : econ.breakEvenYearsRoute <= 0
          ? '<b>Immediate</b>'
          : `<b>~${econ.breakEvenYearsRoute.toFixed(1)} yr</b> (${Math.round(econ.breakEvenMonthsRoute)} mo)`;

    let patienceNote = '';
    if (econ.monthlyNet > 0 && econ.breakEvenYears >= 2) {
      const yearsCeil = Math.max(2, Math.ceil(econ.breakEvenYears));
      patienceNote = `<p class="judgment-note">Under these fares, frequency, and cost assumptions, you would need to operate this route for roughly <b>${yearsCeil} years</b> before cumulative profit covers station build-out and launch spending.</p>`;
    } else if (econ.monthlyNet <= 0) {
      patienceNote =
        '<p class="judgment-note danger">Even a multi-year horizon does not turn positive unless load, fares, or costs improve.</p>';
    }

    const recHtml = rec
      ? `<p class="judgment-rec">Suggested starting fare: <b>$${rec.fare}</b> (market $${rec.market}) — model hint only; GDP, rivals, and marketing will move results.</p>`
      : '';
    const hqNote = econ.isNewStation
      ? `<p class="judgment-note">Includes <b>${fmtMoney(econ.corpShare)}/mo</b> HQ &amp; corporate overhead share. New stations bear more overhead per route until the hub matures — existing hubs look cheaper for the same aircraft.</p>`
      : `<p class="judgment-note">Includes <b>${fmtMoney(econ.corpShare)}/mo</b> HQ overhead (split across ${state.routes.length + 1} routes). Airlines typically want a <b>hub station profitable within ~${hubTarget} years</b>.</p>`;
    const yearRows = yearly
      .map(
        (y) =>
          `<tr><td>Year ${y.year}</td><td>${y.loadPct}% est. load</td><td class="${y.monthlyNet >= 0 ? '' : 'danger'}">${fmtMoney(y.monthlyNet)}/mo</td><td class="${y.cumulative >= 0 ? '' : 'danger'}">${fmtMoney(y.cumulative)} cumulative</td></tr>`
      )
      .join('');
    const yearTable = yearly.length
      ? `<table class="route-review-table judgment-years"><thead><tr><th>Horizon</th><th>Conservative load</th><th>Net/mo</th><th>Cumulative</th></tr></thead><tbody>${yearRows}</tbody></table>
         <p class="muted" style="font-size:0.66rem;margin:4px 0 0;">Years 1–3 use conservative ramp (brand building), cost creep, and inflation — not a guarantee.</p>`
      : '';

    const hasReverse = (state.routes || []).some(
      (r) => r.origin === draft.dest && r.dest === draft.origin
    );
    const returnHtml = hasReverse
      ? `<p class="judgment-note">Return service <b>${draft.dest}→${draft.origin}</b> already flies — both legs carry paying passengers.</p>`
      : `<p class="judgment-note danger"><b>Empty return:</b> without a <b>${draft.dest}→${draft.origin}</b> flight, the plane ferries home empty (fuel + crew, $0 tickets). Open the return leg — or check “Launch with return” below.</p>`;

    return `<div class="route-judgment ${econ.verdictClass}">
      <p class="judgment-kicker">Business judgment</p>
      <p class="judgment-verdict"><strong>${econ.verdictLabel}</strong></p>
      ${marketJudgmentOneLiner(draft)}
      ${returnHtml}
      ${recHtml}
      <dl class="stat-dl judgment-stats">
        <dt>Est. route margin (steady-state)</dt><dd>${fmtMoney(econ.monthlyVariable)}/mo <span class="muted">(${loadPct}% load · ~${econ.via.dailyPax} pax/day${econ.schedScale < 0.98 ? ` · aircraft flies ~${Math.round(econ.schedScale * 100)}% of ${draft.freq}/wk — plane shared` : ''} · ${(bootstrap.ancillary_modes || []).find((m) => m.id === (state.ancillary_strategy || 'auto'))?.label || 'Balanced'} strategy)</span></dd>
        <dt>Allocated fixed costs</dt><dd>${fmtMoney(econ.monthlyFixed)}/mo <span class="muted">(gate ${fmtMoney(econ.gateShare)} · aircraft ${fmtMoney(econ.fleetShare)} · mkt/OTA ${fmtMoney(econ.marketingMonthly + econ.otaMonthly)} · HQ ${fmtMoney(econ.corpShare)})</span></dd>
        <dt>Route margin only</dt><dd class="${econ.monthlyNetRouteOnly >= 0 ? '' : 'danger'}">${fmtMoney(econ.monthlyNetRouteOnly)}/mo <span class="muted">(fuel, crew, fees — no gate/HQ split)</span></dd>
        <dt>Net contribution</dt><dd class="${econ.monthlyNet >= 0 ? '' : 'danger'}">${fmtMoney(econ.monthlyNet)}/mo <span class="muted">(fully burdened)</span></dd>
        <dt>Upfront at launch</dt><dd>${fmtMoney(econ.upfront)}</dd>
        <dt>Payback — route margin</dt><dd>${paybackRoute} <span class="muted">to recover ${fmtMoney(econ.upfront)}</span></dd>
        <dt>Payback — fully burdened</dt><dd>${paybackBurdened} <span class="muted">to recover ${fmtMoney(econ.upfront)}</span></dd>
      </dl>
      ${hqNote}
      ${fareOptimizerChartHtml(draft)}
      ${yearTable}
      ${fareSensitivityHtml(draft)}
      ${patienceNote}
      <p class="muted" style="font-size:0.64rem;margin-top:6px;">${cfg.projection_note || 'Projections are conservative estimates — competition is static here; live sim adds variance.'}</p>
    </div>`;
  }

  function routeLaunchPreviewHtml(draft) {
    if (!draft || !draft.origin || !draft.dest || draft.origin === draft.dest) {
      return '<span class="muted">Pick origin and destination to preview demand.</span>';
    }
    const plane = state.fleet.find((f) => f.id === draft.aircraftId);
    const acType = plane ? plane.type : null;
    if (!acType) return '<span class="danger">Select an aircraft.</span>';
    const via = estimateRouteViability(
      draft.origin,
      draft.dest,
      acType,
      draft.freq,
      draft.fare,
      draft.aircraftId
    );
    const oAp = airport(draft.origin);
    const dAp = airport(draft.dest);
    const dist = oAp && dAp ? Math.round(haversineNm(oAp.lat, oAp.lon, dAp.lat, dAp.lon)) : 0;
    const market = marketFareForPair(draft.origin, draft.dest, acType);
    const sched = planeScheduleLabel(
      draft.aircraftId,
      draft.origin,
      draft.dest,
      draft.freq,
      acType
    );
    let investMo = draft.stationCost;
    investMo += clampMoney(draft.investments.airport) + clampMoney(draft.investments.state);
    investMo += clampMoney(draft.investments.national) + clampMoney(draft.investments.world);
    (bootstrap.ota_platforms || []).forEach((p) => {
      const o = draft.ota[p.id];
      if (!o) return;
      if (o.list && !state.macro.ota_listed[p.id]) investMo += p.listing_monthly;
      if (o.feature) investMo += p.route_feature_monthly || 0;
      if (o.hubPush) investMo += p.hub_push_monthly || 0;
    });
    const cap = gateCapacityLabel(draft.origin, draft.freq);
    const capClass = cap.ok ? '' : ' danger';
    const capNote = cap.max
      ? `<br><span class="muted${capClass}">Gate capacity at ${draft.origin}: <b>${cap.after}/${cap.max}</b> departures/wk (${gateCountAt(draft.origin)} gate${gateCountAt(draft.origin) !== 1 ? 's' : ''} × ${airportGateWeeklyCapacity(oAp)}/wk · ${oAp && oAp.ops_hours_per_day ? oAp.ops_hours_per_day + 'h ops' : 'limited hours'})</span>`
      : '';
    const schedClass = sched && !sched.ok ? ' danger' : '';
    const schedNote =
      sched && plane
        ? `<br><span class="muted${schedClass}">Aircraft <b>${plane.id}</b>: <b>${fmtHours(sched.after)}/${fmtHours(sched.cap)}</b> block-hr/wk` +
          (sched.routesOn > 0 ? ` (${sched.routesOn} other route${sched.routesOn === 1 ? '' : 's'} on this plane)` : '') +
          (via.schedScale < 0.98 ? ` · only ~${Math.round(via.schedScale * 100)}% of ${draft.freq}/wk can fly` : '') +
          `</span>`
        : '';
    const mkt = via.market;
    const mktNote = mkt
      ? `<br><span class="muted">Market: <b>${formatMarketSharePct(mkt.originShare)}</b> of ~${mkt.originMarketDaily}/day at ${draft.origin} · <b>${formatMarketSharePct(mkt.pairCapacityShare)}</b> on pair · <b>${formatMarketSharePct(mkt.captureFactor)}</b> demand capture</span>`
      : '';
    return `<strong>${draft.origin}–${draft.dest}</strong> · ${dist} nm · ~${via.dailyPax} pax/day · ${(via.load * 100).toFixed(0)}% est. load · market $${market}${mktNote}<br>
      <span class="muted">Upfront station build-out <b>${fmtMoney(draft.stationCost)}</b> · new recurring ~<b>${fmtMoney(investMo)}/mo</b> from selections below</span>${capNote}${schedNote}`;
  }

  function setRouteLaunchActive(active) {
    const wasActive = routeLaunchActive;
    routeLaunchActive = !!active;
    const overlay = $('route-launch-modal');
    const dm = $('decision-modal');
    const th = $('tutorial-highlight');
    if (overlay) overlay.classList.toggle('route-launch-open', routeLaunchActive);
    if (dm) dm.classList.toggle('suppressed', routeLaunchActive);
    if (th && routeLaunchActive) {
      th.classList.remove('active');
      th.innerHTML = '';
    }
    document.body.classList.toggle('route-launch-active', routeLaunchActive);
    if (routeLaunchActive && !wasActive) pauseForInterrupt();
    else if (!routeLaunchActive && wasActive) resumeSpeedAfterInterrupt();
  }

  function ensureRouteLaunchOta(draft) {
    if (!draft.ota) draft.ota = {};
    (bootstrap.ota_platforms || []).forEach((p) => {
      if (!draft.ota[p.id]) {
        draft.ota[p.id] = { list: false, feature: false, hubPush: false };
      }
    });
    return draft.ota;
  }

  function routeStudioStepsMeta() {
    return [
      { id: 1, key: 'market', label: 'Market', blurb: 'Pick the city pair' },
      { id: 2, key: 'product', label: 'Product', blurb: 'Aircraft, seats & price' },
      { id: 3, key: 'growth', label: 'Growth', blurb: 'Marketing & distribution' },
      { id: 4, key: 'launch', label: 'Launch', blurb: 'Business case & go' },
    ];
  }

  function routeStudioStepperHtml(step) {
    return `<nav class="studio-stepper" aria-label="Route Studio steps">
      ${routeStudioStepsMeta()
        .map((s) => {
          const cls =
            s.id === step ? 'active' : s.id < step ? 'done' : '';
          return `<button type="button" class="studio-step ${cls}" data-studio-goto="${s.id}" ${
            s.id > step + 1 ? 'disabled' : ''
          }>
            <span class="studio-step-num">${s.id < step ? '✓' : s.id}</span>
            <span class="studio-step-label">${s.label}</span>
            <span class="studio-step-blurb">${s.blurb}</span>
          </button>`;
        })
        .join('<span class="studio-step-rail" aria-hidden="true"></span>')}
    </nav>`;
  }

  function routeStudioMarketStepHtml(d) {
    const oAp = airport(d.origin);
    const dAp = airport(d.dest);
    const oLabel = oAp ? airportLabel(oAp) : d.origin || '';
    const dLabel = dAp ? airportLabel(dAp) : d.dest || '';
    const util = d.origin && hasGateAt(d.origin) ? gateUtilizationAt(d.origin) : null;
    const gateNote =
      d.origin && hasGateAt(d.origin)
        ? util
          ? `<span class="studio-pill ok">${util.remaining} deps/wk open at ${d.origin}</span>`
          : `<span class="studio-pill ok">Gate leased at ${d.origin}</span>`
        : d.origin
          ? `<span class="studio-pill bad">Lease a gate at ${d.origin} first</span>`
          : '';
    let marketIntel = '';
    if (d.origin && d.dest && oAp && dAp) {
      const dist = Math.round(haversineNm(oAp.lat, oAp.lon, dAp.lat, dAp.lon));
      const plane = state.fleet.find((f) => f.id === d.aircraftId) || state.fleet[0];
      const acType = plane ? plane.type : recommendAircraftTypeForPair(d.origin, d.dest);
      const via = estimateRouteViability(d.origin, d.dest, acType, d.freq || 7, d.fare, plane && plane.id);
      const market = marketFareForPair(d.origin, d.dest, acType);
      marketIntel = `<div class="studio-intel">
        <div class="studio-intel-stat"><span class="muted">Distance</span><strong>${dist} nm</strong></div>
        <div class="studio-intel-stat"><span class="muted">Market fare</span><strong>$${market}</strong></div>
        <div class="studio-intel-stat"><span class="muted">Est. demand</span><strong>~${via.dailyPax} pax/day</strong></div>
        <div class="studio-intel-stat"><span class="muted">Est. load</span><strong>${(via.load * 100).toFixed(0)}%</strong></div>
      </div>`;
    }
    return `<div class="studio-step-body" data-studio-step="1">
      <header class="studio-step-head">
        <p class="studio-kicker">Step 1 · Market</p>
        <h2>Where do you want to fly?</h2>
        <p class="studio-lead">Choose origin and destination. This is a <b>network decision</b> — not just a fare slider. Demand, gates, and competitors all start here.</p>
        ${gateNote}
      </header>
      <datalist id="studio-airport-list">${airportDatalistHtml()}</datalist>
      <div class="studio-pair-grid">
        <label class="studio-field">
          <span>Origin (your gate)</span>
          <input type="text" id="rl-origin-search" list="studio-airport-list" placeholder="DAY — Dayton" value="${oLabel}">
          <input type="hidden" id="rl-origin-code" value="${d.origin || ''}">
        </label>
        <div class="studio-pair-arrow" aria-hidden="true">→</div>
        <label class="studio-field">
          <span>Destination</span>
          <input type="text" id="rl-dest-search" list="studio-airport-list" placeholder="CVG — Cincinnati" value="${dLabel}">
          <input type="hidden" id="rl-dest-code" value="${d.dest || ''}">
        </label>
      </div>
      ${marketIntel}
      <div id="rl-studio-suggestions" class="studio-suggestions"></div>
    </div>`;
  }

  function routeStudioProductStepHtml(d) {
    const freqCap = launchFrequencyCap(d);
    const returnExists = (state.routes || []).some((r) => r.origin === d.dest && r.dest === d.origin);
    return `<div class="studio-step-body" data-studio-step="2">
      <header class="studio-step-head">
        <p class="studio-kicker">Step 2 · Product &amp; ops</p>
        <h2>${d.origin || '—'} → ${d.dest || '—'}</h2>
        <p class="studio-lead">Frequency and aircraft shape capacity and cost more than price alone. More flights win share; the wrong metal burns cash.</p>
      </header>
      <div id="rl-availability">${availabilityPanelHtml(
        routeAvailabilityContext(d.origin, d.dest, d.aircraftId, d.freq),
        { title: 'Capacity check' }
      )}</div>
      <div id="rl-limits">${launchLimitsStripHtml(d)}</div>
      <div class="studio-product-grid">
        <label class="studio-field studio-field-wide">
          <span>Aircraft</span>
          <select id="rl-aircraft">${fleetOptionsHtml(d.aircraftId, d.origin, d.dest)}</select>
        </label>
        <label class="studio-field studio-field-wide">
          <span>Flight product</span>
          <select id="rl-product">${productOptionsHtml(d.product || 'standard')}</select>
          <em class="muted studio-field-hint" id="rl-product-hint">${(routeProduct(d.product || 'standard').blurb) || ''}</em>
        </label>
        <label class="studio-field studio-field-wide" id="rl-tag-wrap" style="${(d.product || 'standard') === 'tag' ? '' : 'display:none'}">
          <span>Tag third city (A→B→C)</span>
          <input type="text" id="rl-tag-dest" list="studio-airport-list" placeholder="e.g. CLE" value="${d.tag_dest || ''}">
          <em class="muted studio-field-hint">Same plane continues ${d.dest || 'B'} → third city. Uses more block hours; efficient when loads on both legs work.</em>
        </label>
        <label class="studio-field">
          <span>Frequency / week <em class="muted">(max ${freqCap})</em></span>
          <div class="studio-stepper-input">
            <button type="button" class="studio-nudge" data-rl-nudge="freq" data-delta="-1">−</button>
            <input type="number" id="rl-freq" min="1" max="${freqCap}" value="${d.freq}">
            <button type="button" class="studio-nudge" data-rl-nudge="freq" data-delta="1">+</button>
          </div>
        </label>
        <label class="studio-field">
          <span>Launch fare $</span>
          <div class="studio-stepper-input">
            <button type="button" class="studio-nudge" data-rl-nudge="fare" data-delta="-10">−</button>
            <input type="number" id="rl-fare" min="49" max="899" value="${d.fare}">
            <button type="button" class="studio-nudge" data-rl-nudge="fare" data-delta="10">+</button>
          </div>
        </label>
      </div>
      <div class="studio-return-box">
        <label>
          <input type="checkbox" id="rl-with-return" ${
            returnExists ? '' : d.withReturn !== false ? 'checked' : ''
          } ${returnExists ? 'disabled' : ''}>
          <span>
            <strong>Launch with return leg</strong> (${d.dest || '…'} → ${d.origin || '…'})
            <em class="muted">Same aircraft, fare &amp; frequency. One-way only = empty ferry home.${
              d.dest && !hasGateAt(d.dest)
                ? ` Needs a gate at <b>${d.dest}</b>.`
                : ''
            }${returnExists ? ' Return already flying.' : ''}</em>
          </span>
        </label>
      </div>
      <div class="route-launch-preview" id="rl-preview"></div>
    </div>`;
  }

  function routeStudioGrowthStepHtml(d) {
    const oAp = airport(d.origin);
    const channels = bootstrap.marketing_channels || [];
    const channelRows = channels
      .map((ch) => {
        if (ch.id === 'airport') {
          return `<div class="invest-row">
            <label><input type="checkbox" data-inv-toggle="airport" checked disabled> <strong>${ch.label}</strong> at ${d.origin}
              <span class="invest-hint">${ch.hint}</span></label>
            <input type="number" min="0" step="1000" data-inv-amount="airport" value="${d.investments.airport}">
          </div>`;
        }
        if (ch.id === 'state' && oAp && oAp.state) {
          return `<div class="invest-row">
            <label><input type="checkbox" data-inv-toggle="state" ${d.investments.state > 0 ? 'checked' : ''}> <strong>${ch.label}</strong> (${oAp.state})
              <span class="invest-hint">${ch.hint}</span></label>
            <input type="number" min="0" step="1000" data-inv-amount="state" value="${d.investments.state}">
          </div>`;
        }
        if (ch.id === 'national') {
          return `<div class="invest-row">
            <label><input type="checkbox" data-inv-toggle="national" ${d.investments.national > 0 ? 'checked' : ''}> <strong>${ch.label}</strong>
              <span class="invest-hint">${ch.hint}</span></label>
            <input type="number" min="0" step="5000" data-inv-amount="national" value="${d.investments.national}">
          </div>`;
        }
        if (ch.id === 'world') {
          return `<div class="invest-row">
            <label><input type="checkbox" data-inv-toggle="world" ${d.investments.world > 0 ? 'checked' : ''}> <strong>${ch.label}</strong>
              <span class="invest-hint">${ch.hint}</span></label>
            <input type="number" min="0" step="5000" data-inv-amount="world" value="${d.investments.world}">
          </div>`;
        }
        return '';
      })
      .join('');

    const otaRows = (bootstrap.ota_platforms || [])
      .map((p) => {
        const o = d.ota[p.id] || { list: false, feature: false, hubPush: false };
        return `<div class="invest-row">
          <label><input type="checkbox" data-ota-list="${p.id}" ${o.list ? 'checked' : ''}> <strong>${p.name}</strong> — list airline
            <span class="invest-hint">${fmtMoney(p.listing_monthly)}/mo + ${p.commission_pct}% commission · ${p.note || ''}</span></label>
        </div>
        <div class="invest-row" style="padding-left:18px;">
          <label><input type="checkbox" data-ota-feature="${p.id}" ${o.feature ? 'checked' : ''}> Route featured placement (+${fmtMoney(p.route_feature_monthly || 0)}/mo)</label>
        </div>
        <div class="invest-row" style="padding-left:18px;">
          <label><input type="checkbox" data-ota-hub="${p.id}" ${o.hubPush ? 'checked' : ''}> Hub push at ${d.origin} (+${fmtMoney(p.hub_push_monthly || 0)}/mo)</label>
        </div>`;
      })
      .join('');

    return `<div class="studio-step-body" data-studio-step="3">
      <header class="studio-step-head">
        <p class="studio-kicker">Step 3 · Growth engines</p>
        <h2>Fill the seats you just planned</h2>
        <p class="studio-lead">Marketing and OTAs lift demand independently of fare. Airport ads are the strongest local lever; distribution gets you on the shelf.</p>
      </header>
      <div class="studio-station-card">
        <p class="route-launch-section" style="margin-top:0;">Station build-out (one-time)</p>
        <p style="font-size:0.84rem;line-height:1.45;margin:0;">Counters, signage, ground ops at <b>${d.origin}</b> — <b class="studio-money">${fmtMoney(d.stationCost)}</b> due at launch.</p>
        ${stationSetupExplainHtml(d.origin, d.dest)}
        ${d.origin ? gateCapacityExplainHtml(d.origin) : ''}
      </div>
      <p class="route-launch-section">Marketing investments</p>
      ${channelRows}
      <p class="route-launch-section">Distribution — OTAs (pay to play)</p>
      ${otaRows || '<p class="muted">No OTA platforms configured.</p>'}
    </div>`;
  }

  function routeStudioLaunchStepHtml(d) {
    return `<div class="studio-step-body" data-studio-step="4">
      <header class="studio-step-head">
        <p class="studio-kicker">Step 4 · Commit</p>
        <h2>Launch ${d.origin} → ${d.dest}</h2>
        <p class="studio-lead">Review the business case. Frequency, metal, and marketing are locked at launch — you can still tune them later on the route card.</p>
      </header>
      <div class="studio-launch-summary">
        <div class="studio-summary-chip"><span class="muted">Aircraft</span><strong id="rl-sum-ac">—</strong></div>
        <div class="studio-summary-chip"><span class="muted">Frequency</span><strong id="rl-sum-freq">${d.freq}/wk</strong></div>
        <div class="studio-summary-chip"><span class="muted">Fare</span><strong id="rl-sum-fare">$${d.fare}</strong></div>
        <div class="studio-summary-chip"><span class="muted">Station</span><strong>${fmtMoney(d.stationCost)}</strong></div>
        <div class="studio-summary-chip"><span class="muted">Airport ads</span><strong id="rl-sum-mkt">${fmtMoney(d.investments.airport)}/mo</strong></div>
      </div>
      <div id="rl-availability">${availabilityPanelHtml(
        routeAvailabilityContext(d.origin, d.dest, d.aircraftId, d.freq),
        { title: 'Capacity check' }
      )}</div>
      <div class="route-launch-preview" id="rl-preview"></div>
      <div class="route-launch-judgment" id="rl-judgment"></div>
    </div>`;
  }

  function routeStudioBodyHtml(d, step) {
    if (step === 1) return routeStudioMarketStepHtml(d);
    if (step === 2) return routeStudioProductStepHtml(d);
    if (step === 3) return routeStudioGrowthStepHtml(d);
    return routeStudioLaunchStepHtml(d);
  }

  function syncRouteStudioDraftFromDom() {
    if (!routeLaunchDraft) return;
    const oSearch = $('rl-origin-search');
    const dSearch = $('rl-dest-search');
    const oHidden = $('rl-origin-code');
    const dHidden = $('rl-dest-code');
    if (oSearch) {
      const oAp = resolveAirportQuery(oSearch.value) || airport(oHidden && oHidden.value);
      if (oAp) {
        routeLaunchDraft.origin = oAp.iata;
        if (oHidden) oHidden.value = oAp.iata;
      }
    }
    if (dSearch) {
      const dAp = resolveAirportQuery(dSearch.value) || airport(dHidden && dHidden.value);
      if (dAp) {
        routeLaunchDraft.dest = dAp.iata;
        if (dHidden) dHidden.value = dAp.iata;
      }
    }
    const acEl = $('rl-aircraft');
    if (acEl && acEl.value) routeLaunchDraft.aircraftId = acEl.value;
    const prodEl = $('rl-product');
    if (prodEl && prodEl.value) routeLaunchDraft.product = prodEl.value;
    const tagEl = $('rl-tag-dest');
    if (tagEl) {
      const tAp = resolveAirportQuery(tagEl.value) || airport((tagEl.value || '').trim().toUpperCase());
      routeLaunchDraft.tag_dest = tAp ? tAp.iata : (tagEl.value || '').trim().toUpperCase();
    }
    const fareEl = $('rl-fare');
    const freqEl = $('rl-freq');
    if (fareEl) routeLaunchDraft.fare = +fareEl.value || routeLaunchDraft.fare;
    if (freqEl) routeLaunchDraft.freq = +freqEl.value || routeLaunchDraft.freq;
    const withRet = $('rl-with-return');
    if (withRet && !withRet.disabled) routeLaunchDraft.withReturn = !!withRet.checked;
    // Tag products usually don't launch a separate reverse the same way
    if (routeLaunchDraft.product === 'tag' && withRet) {
      routeLaunchDraft.withReturn = false;
    }
    document.querySelectorAll('#route-launch-modal [data-inv-amount]').forEach((inp) => {
      const key = inp.dataset.invAmount;
      const toggle = document.querySelector(`#route-launch-modal [data-inv-toggle="${key}"]`);
      const on = !toggle || toggle.checked;
      routeLaunchDraft.investments[key] = on ? clampMoney(inp.valueAsNumber) : 0;
    });
    (bootstrap.ota_platforms || []).forEach((p) => {
      const list = document.querySelector(`#route-launch-modal [data-ota-list="${p.id}"]`);
      const feat = document.querySelector(`#route-launch-modal [data-ota-feature="${p.id}"]`);
      const hub = document.querySelector(`#route-launch-modal [data-ota-hub="${p.id}"]`);
      if (list || feat || hub) {
        routeLaunchDraft.ota[p.id] = {
          list: !!(list && list.checked),
          feature: !!(feat && feat.checked),
          hubPush: !!(hub && hub.checked),
        };
      }
    });
    if (routeLaunchDraft.origin) {
      routeLaunchDraft.stationCost = stationSetupCost(
        routeLaunchDraft.origin,
        routeLaunchDraft.dest || routeLaunchDraft.origin
      );
    }
  }

  function refreshRouteStudioLivePanels() {
    if (!routeLaunchDraft) return;
    const d = routeLaunchDraft;
    const prev = $('rl-preview');
    const judgment = $('rl-judgment');
    const limits = $('rl-limits');
    try {
      if (prev) prev.innerHTML = routeLaunchPreviewHtml(d);
      if (judgment) judgment.innerHTML = routeBusinessJudgmentHtml(d);
      if (limits) limits.innerHTML = launchLimitsStripHtml(d);
    } catch (err) {
      console.error('Runway: studio preview failed', err);
    }
    updateLaunchAvailabilityPanel(d);
    const sumAc = $('rl-sum-ac');
    const sumFreq = $('rl-sum-freq');
    const sumFare = $('rl-sum-fare');
    const sumMkt = $('rl-sum-mkt');
    if (sumAc) {
      const plane = state.fleet.find((f) => f.id === d.aircraftId);
      const ac = plane ? aircraftType(plane.type) : null;
      sumAc.textContent = ac
        ? `${ac.name} · ${fleetSeatCount(plane)} seats`
        : '—';
    }
    if (sumFreq) sumFreq.textContent = `${d.freq}/wk`;
    if (sumFare) sumFare.textContent = `$${d.fare}`;
    if (sumMkt) sumMkt.textContent = `${fmtMoney(d.investments.airport)}/mo`;
  }

  function canAdvanceRouteStudioStep(fromStep) {
    syncRouteStudioDraftFromDom();
    const d = routeLaunchDraft;
    if (!d) return 'Studio closed.';
    if (fromStep >= 1) {
      if (!d.origin || !airport(d.origin)) return 'Pick a valid origin airport.';
      if (!hasGateAt(d.origin)) {
        return `Lease a gate at ${d.origin} first (map → airport → Your position).`;
      }
      if (!d.dest || !airport(d.dest)) return 'Pick a valid destination.';
      if (d.origin === d.dest) return 'Origin and destination must differ.';
    }
    if (fromStep >= 2) {
      if (!d.aircraftId || !state.fleet.find((f) => f.id === d.aircraftId)) {
        return 'Select an aircraft from your fleet.';
      }
      const err = validateOpenRoute(d.origin, d.dest, d.aircraftId, d.freq);
      if (err) return err;
    }
    return null;
  }

  function setRouteStudioStep(step) {
    if (!routeLaunchDraft) return;
    const next = Math.max(1, Math.min(4, Math.round(step)));
    syncRouteStudioDraftFromDom();
    if (next > routeLaunchStep) {
      for (let s = routeLaunchStep; s < next; s++) {
        const err = canAdvanceRouteStudioStep(s);
        if (err) {
          alert(err);
          return;
        }
      }
    }
    if (!routeLaunchDraft.aircraftId && state.fleet[0]) {
      routeLaunchDraft.aircraftId = state.fleet[0].id;
    }
    if (
      routeLaunchDraft.origin &&
      routeLaunchDraft.dest &&
      routeLaunchDraft.origin !== routeLaunchDraft.dest
    ) {
      const plane = state.fleet.find((f) => f.id === routeLaunchDraft.aircraftId);
      if (!routeLaunchDraft.fare || routeLaunchDraft.fare === 129) {
        routeLaunchDraft.fare = marketFareForPair(
          routeLaunchDraft.origin,
          routeLaunchDraft.dest,
          plane ? plane.type : null
        );
      }
      routeLaunchDraft.stationCost = stationSetupCost(
        routeLaunchDraft.origin,
        routeLaunchDraft.dest
      );
    }
    routeLaunchStep = next;
    renderRouteLaunchModal();
  }

  function renderStudioSuggestions() {
    const box = $('rl-studio-suggestions');
    if (!box || !routeLaunchDraft) return;
    const origin = routeLaunchDraft.origin;
    if (!origin || !hasGateAt(origin)) {
      box.innerHTML = origin
        ? `<p class="muted">Lease a gate at <b>${origin}</b> to see launch-ready markets.</p>`
        : '<p class="muted">Select an origin to see demand suggestions.</p>';
      return;
    }
    const ideas = routeSuggestionsFrom(origin)
      .map((s) => enrichRouteSuggestion(origin, s))
      .filter((s) => s.status === 'ready' || s.status === 'limited')
      .slice(0, 8);
    if (!ideas.length) {
      box.innerHTML = '<p class="muted">No ready destinations in range — add fleet hours or gates.</p>';
      return;
    }
    box.innerHTML = `<p class="studio-suggest-label">Ready markets from ${origin} <span class="muted" style="font-weight:400;">· out vs return loads</span></p>
      <div class="studio-suggest-grid">
        ${ideas
          .map((s) => {
            const freq = s.status === 'limited' && s.maxFreq > 0 ? s.maxFreq : s.freq;
            const outPct = Math.round((s.outLoad != null ? s.outLoad : s.load) * 100);
            const retPct = Math.round((s.retLoad != null ? s.retLoad : s.load) * 100);
            return `<button type="button" class="studio-suggest-card" data-studio-pick="${s.dest}"
              data-ac-type="${s.acType}" data-aircraft-id="${s.bestPlaneId || ''}"
              data-fare="${s.fare}" data-freq="${freq}" title="${(s.directionPrompt || '').replace(/"/g, "'")}">
              <strong>${origin} ⇄ ${s.dest}</strong>
              <span class="muted">${s.destCity}</span>
              <span class="studio-suggest-meta">${s.dist} nm · ${freq}/wk · out ${outPct}% · ret ${retPct}%</span>
              <span class="studio-suggest-via via-${s.tier}">${s.label}${s.worthRt ? ' · RT ✓' : ''}</span>
            </button>`;
          })
          .join('')}
      </div>`;
  }

  function applyStudioMarketPick(btn) {
    if (!routeLaunchDraft || !btn) return;
    const dest = btn.dataset.studioPick;
    const dAp = airport(dest);
    if (!dAp) return;
    routeLaunchDraft.dest = dest;
    routeLaunchDraft.freq = +(btn.dataset.freq) || 7;
    routeLaunchDraft.fare = +(btn.dataset.fare) || routeLaunchDraft.fare;
    const plane = btn.dataset.aircraftId
      ? state.fleet.find((f) => f.id === btn.dataset.aircraftId)
      : state.fleet.find((f) => f.type === btn.dataset.acType) || state.fleet[0];
    if (plane) routeLaunchDraft.aircraftId = plane.id;
    routeLaunchStep = 2;
    renderRouteLaunchModal();
  }

  function renderRouteLaunchModal() {
    const overlay = $('route-launch-modal');
    if (!overlay) return;
    if (!routeLaunchDraft) {
      overlay.classList.remove('active');
      overlay.classList.remove('route-studio');
      overlay.innerHTML = '';
      setRouteLaunchActive(false);
      return;
    }
    const d = routeLaunchDraft;
    ensureRouteLaunchOta(d);
    if (!d.aircraftId && state.fleet[0]) d.aircraftId = state.fleet[0].id;
    const step = Math.max(1, Math.min(4, routeLaunchStep || 1));
    routeLaunchStep = step;
    const meta = routeStudioStepsMeta().find((s) => s.id === step) || routeStudioStepsMeta()[0];

    let liveRail = '';
    try {
      if (d.origin && d.dest && d.aircraftId) {
        liveRail = `<aside class="studio-rail">
          <p class="studio-rail-title">Live case</p>
          <div class="route-launch-preview" id="rl-rail-preview">${routeLaunchPreviewHtml(d)}</div>
          <div id="rl-rail-judgment" class="studio-rail-judgment">${
            step >= 2 ? routeBusinessJudgmentHtml(d) : '<p class="muted" style="font-size:0.72rem;">Complete product step for full P&amp;L judgment.</p>'
          }</div>
        </aside>`;
      } else {
        liveRail = `<aside class="studio-rail studio-rail-empty">
          <p class="studio-rail-title">Live case</p>
          <p class="muted" style="font-size:0.78rem;line-height:1.45;">Pick origin &amp; destination to see demand, load, and cash impact update live.</p>
        </aside>`;
      }
    } catch (err) {
      console.error('Runway: studio rail failed', err);
      liveRail = `<aside class="studio-rail"><p class="danger">Preview unavailable</p></aside>`;
    }

    overlay.innerHTML = `
      <div class="route-studio-shell" role="dialog" aria-modal="true" aria-label="Route Studio">
        <header class="studio-topbar">
          <div class="studio-brand">
            <span class="studio-brand-mark">✈</span>
            <div>
              <p class="studio-brand-kicker">Route Studio</p>
              <h1>Open a new market</h1>
            </div>
          </div>
          <p class="studio-step-indicator">Step ${step} of 4 · ${meta.label}</p>
          <button type="button" class="studio-close" id="rl-cancel" title="Close">✕</button>
        </header>
        ${routeStudioStepperHtml(step)}
        <div class="studio-main">
          <div class="studio-content">${routeStudioBodyHtml(d, step)}</div>
          ${liveRail}
        </div>
        <footer class="studio-footer">
          <button type="button" class="btn secondary" id="rl-back" ${step <= 1 ? 'disabled' : ''}>← Back</button>
          <div class="studio-footer-actions">
            <button type="button" class="btn secondary" id="rl-cancel-2">Cancel</button>
            ${
              step < 4
                ? `<button type="button" class="btn studio-primary" id="rl-next">Continue →</button>`
                : `<button type="button" class="btn studio-primary" id="rl-confirm">Confirm launch</button>`
            }
          </div>
        </footer>
      </div>`;
    overlay.classList.add('active', 'route-studio');
    setRouteLaunchActive(true);
    dismissDecisionsForRouteLaunch();
    overlay.scrollTop = 0;

    // Fill live previews in body (product/launch steps)
    refreshRouteStudioLivePanels();
    if (step === 1) renderStudioSuggestions();

    const syncAndRefresh = () => {
      syncRouteStudioDraftFromDom();
      // Soft refresh of rail without full re-render when possible
      const railPrev = $('rl-rail-preview');
      const railJudg = $('rl-rail-judgment');
      try {
        if (railPrev && routeLaunchDraft.origin && routeLaunchDraft.dest) {
          railPrev.innerHTML = routeLaunchPreviewHtml(routeLaunchDraft);
        }
        if (railJudg && routeLaunchStep >= 2 && routeLaunchDraft.origin && routeLaunchDraft.dest) {
          railJudg.innerHTML = routeBusinessJudgmentHtml(routeLaunchDraft);
        }
      } catch (e) { /* ignore live rail glitches */ }
      refreshRouteStudioLivePanels();
      if (routeLaunchStep === 1) {
        // Update market intel / suggestions only on origin change via re-render is heavy;
        // suggestions re-bind on pick.
      }
    };

    // Origin/dest binding
    const bindAirportField = (searchId, hiddenId) => {
      const input = $(searchId);
      const hidden = $(hiddenId);
      if (!input || !hidden) return;
      const apply = () => {
        const ap = resolveAirportQuery(input.value);
        if (ap) {
          const prevCode = searchId === 'rl-origin-search' ? routeLaunchDraft.origin : routeLaunchDraft.dest;
          const changed = prevCode !== ap.iata;
          hidden.value = ap.iata;
          if (searchId === 'rl-origin-search') {
            routeLaunchDraft.origin = ap.iata;
            routeLaunchDraft.stationCost = stationSetupCost(
              ap.iata,
              routeLaunchDraft.dest || ap.iata
            );
            routeLaunchDraft.investments.airport = clampMoney(
              state.marketing_spend_monthly[ap.iata]
            );
          } else {
            routeLaunchDraft.dest = ap.iata;
          }
          syncAndRefresh();
          // Full re-render only when the resolved code changes (keeps focus while typing)
          if (routeLaunchStep === 1 && changed) {
            renderRouteLaunchModal();
            const focusId = searchId;
            requestAnimationFrame(() => {
              const el = $(focusId);
              if (el) {
                el.focus();
                try {
                  el.selectionStart = el.selectionEnd = el.value.length;
                } catch (e) { /* ignore */ }
              }
            });
          } else if (routeLaunchStep === 1) {
            renderStudioSuggestions();
          }
        }
      };
      input.addEventListener('change', apply);
      input.addEventListener('blur', apply);
      input.addEventListener('input', () => {
        window.clearTimeout(input._studioDebounce);
        input._studioDebounce = window.setTimeout(apply, 280);
      });
    };
    bindAirportField('rl-origin-search', 'rl-origin-code');
    bindAirportField('rl-dest-search', 'rl-dest-code');

    const prodSel = $('rl-product');
    if (prodSel) {
      prodSel.addEventListener('change', () => {
        syncRouteStudioDraftFromDom();
        const hint = $('rl-product-hint');
        const p = routeProduct(prodSel.value);
        if (hint) hint.textContent = p.blurb || '';
        const tagWrap = $('rl-tag-wrap');
        if (tagWrap) tagWrap.style.display = p.isTag ? '' : 'none';
        const withRet = $('rl-with-return');
        if (withRet && p.isTag) {
          withRet.checked = false;
          withRet.disabled = true;
        } else if (withRet && !withRet.dataset.forceDisabled) {
          withRet.disabled = false;
        }
        syncAndRefresh();
      });
    }

    overlay.querySelectorAll('[data-studio-pick]').forEach((btn) => {
      btn.addEventListener('click', () => applyStudioMarketPick(btn));
    });
    overlay.querySelectorAll('[data-studio-goto]').forEach((btn) => {
      btn.addEventListener('click', () => setRouteStudioStep(+btn.dataset.studioGoto));
    });
    overlay.querySelectorAll('[data-rl-nudge]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const kind = btn.dataset.rlNudge;
        const delta = +btn.dataset.delta || 0;
        if (kind === 'freq') {
          const el = $('rl-freq');
          if (el) {
            const cap = launchFrequencyCap(routeLaunchDraft);
            el.value = Math.max(1, Math.min(cap, (+el.value || 7) + delta));
          }
        } else if (kind === 'fare') {
          const el = $('rl-fare');
          if (el) el.value = Math.max(49, Math.min(899, (+el.value || 129) + delta));
        }
        syncAndRefresh();
      });
    });

    bindAvailabilityActions(overlay);
    overlay.querySelectorAll('input, select').forEach((inp) => {
      inp.addEventListener('change', syncAndRefresh);
      inp.addEventListener('input', syncAndRefresh);
    });

    const back = $('rl-back');
    if (back) {
      back.addEventListener('click', () => setRouteStudioStep(routeLaunchStep - 1));
    }
    const next = $('rl-next');
    if (next) {
      next.addEventListener('click', () => setRouteStudioStep(routeLaunchStep + 1));
    }
    const confirm = $('rl-confirm');
    if (confirm) confirm.addEventListener('click', confirmRouteLaunch);
    const cancel = () => softCloseRouteStudio();
    const c1 = $('rl-cancel');
    const c2 = $('rl-cancel-2');
    if (c1) {
      c1.title = 'Close — draft is saved so you can Resume from Routes';
      c1.addEventListener('click', cancel);
    }
    if (c2) {
      c2.textContent = 'Close (save draft)';
      c2.addEventListener('click', cancel);
    }
    // Backdrop tap soft-closes and keeps draft — hard to recover if we wiped it.
    overlay.onclick = (e) => {
      if (e.target === overlay) softCloseRouteStudio();
    };
  }

  function openRouteStudio(opts) {
    opts = opts || {};
    dismissDecisionsForRouteLaunch();
    showRouteFormError('');
    const origin = opts.origin || defaultRouteOrigin() || (state.gates[0] && state.gates[0].airport) || '';
    const dest = opts.dest || '';
    let aircraftId = opts.aircraftId || (state.fleet[0] && state.fleet[0].id) || '';
    const freq = opts.freq || 7;
    const fare = opts.fare || null;

    if (origin && !hasGateAt(origin) && !opts.allowNoGate) {
      // Still open studio so player sees market step with gate warning
    }
    if (!state.fleet.length && opts.requireFleet !== false) {
      // Allow opening — product step will block
    }

    try {
      routeLaunchDraft = buildRouteLaunchDraft(
        origin || (bootstrap.airports[0] && bootstrap.airports[0].iata) || 'DAY',
        dest || origin || 'DAY',
        aircraftId,
        freq,
        fare
      );
      // If no real dest yet, clear dest so market step is empty destination
      if (!opts.dest) {
        routeLaunchDraft.dest = '';
      }
      if (!aircraftId) routeLaunchDraft.aircraftId = '';
      routeLaunchStep = opts.step || (opts.dest && aircraftId ? 2 : 1);
      renderRouteLaunchModal();
      if (!$('route-launch-modal')?.classList.contains('active')) {
        showRouteFormError('Could not open Route Studio — try again or hard-refresh.');
      }
    } catch (err) {
      console.error('Runway: openRouteStudio failed', err);
      routeLaunchDraft = null;
      showRouteFormError('Route Studio failed to open. Hard-refresh (Cmd+Shift+R) and try again.');
      alert('Route Studio failed to open. Check the browser console for details.');
    }
  }

  function openRouteLaunchModal(origin, dest, aircraftId, freq, fare) {
    openRouteStudio({
      origin,
      dest,
      aircraftId,
      freq,
      fare,
      step: dest && aircraftId ? 2 : 1,
    });
  }

  function softCloseRouteStudio(opts) {
    opts = opts || {};
    // Preserve in-progress work so a map tap / backdrop mis-click isn't fatal.
    if (routeLaunchDraft) {
      try {
        syncRouteStudioDraftFromDom();
      } catch (e) {
        /* draft may be partial */
      }
      try {
        routeStudioResume = {
          draft: JSON.parse(JSON.stringify(routeLaunchDraft)),
          step: routeLaunchStep || 1,
        };
      } catch (e) {
        routeStudioResume = { draft: { ...routeLaunchDraft }, step: routeLaunchStep || 1 };
      }
    }
    routeLaunchDraft = null;
    routeLaunchStep = 1;
    renderRouteLaunchModal();
    if (!opts.skipRoutesRender) {
      try {
        renderRoutes();
      } catch (e) {
        /* ignore */
      }
    }
  }

  function resumeRouteStudio() {
    if (!routeStudioResume || !routeStudioResume.draft) {
      alert('No saved Route Studio draft to resume.');
      return;
    }
    routeLaunchDraft = routeStudioResume.draft;
    routeLaunchStep = routeStudioResume.step || 1;
    routeStudioResume = null;
    renderRouteLaunchModal();
  }

  function discardRouteStudioDraft() {
    routeStudioResume = null;
    routeLaunchDraft = null;
    routeLaunchStep = 1;
    renderRouteLaunchModal();
    try {
      renderRoutes();
    } catch (e) {
      /* ignore */
    }
  }

  function cancelRouteLaunch() {
    softCloseRouteStudio();
  }

  function confirmRouteLaunch() {
    if (!routeLaunchDraft) return;
    syncRouteStudioDraftFromDom();
    const d = routeLaunchDraft;

    let upfront = d.stationCost;
    ensureMacro();
    ensureMarketingInvestments();
    (bootstrap.ota_platforms || []).forEach((p) => {
      const o = d.ota[p.id];
      if (o && o.list && !state.macro.ota_listed[p.id]) upfront += p.listing_monthly;
    });

    const wantReturn =
      d.withReturn !== false &&
      !(state.routes || []).some((r) => r.origin === d.dest && r.dest === d.origin);

    const routeErr = validateOpenRoute(d.origin, d.dest, d.aircraftId, d.freq);
    if (routeErr) {
      alert(routeErr);
      return;
    }
    if (wantReturn) {
      if (!hasGateAt(d.dest)) {
        alert(
          `Return leg ${d.dest}→${d.origin} needs a gate at ${d.dest}. Lease one on the map, then relaunch with return checked.`
        );
        return;
      }
      const retErr = validateOpenRoute(d.dest, d.origin, d.aircraftId, d.freq);
      if (retErr) {
        alert(`Return leg: ${retErr}`);
        return;
      }
    }
    if (state.cash < upfront) {
      alert(`Need ${fmtMoney(upfront)} upfront (station build-out + first month on new OTA listings).`);
      return;
    }

    const featured = [];
    if (!state.hub_ota_push[d.origin]) state.hub_ota_push[d.origin] = [];
    (bootstrap.ota_platforms || []).forEach((p) => {
      const o = d.ota[p.id];
      if (!o) return;
      if (o.list) state.macro.ota_listed[p.id] = true;
      if (o.feature) featured.push(p.id);
      if (o.hubPush && !state.hub_ota_push[d.origin].includes(p.id)) {
        state.hub_ota_push[d.origin].push(p.id);
      }
    });

    const copy = {
      origin: d.origin,
      dest: d.dest,
      aircraftId: d.aircraftId,
      freq: d.freq,
      fare: d.fare,
      wantReturn: d.product === 'tag' ? false : wantReturn,
      product: d.product || 'standard',
      tag_dest: d.tag_dest || '',
    };
    if (copy.product === 'tag') {
      if (!copy.tag_dest || copy.tag_dest === copy.origin || copy.tag_dest === copy.dest) {
        alert('Tag flights need a third city different from origin and destination.');
        return;
      }
      if (!airport(copy.tag_dest)) {
        alert(`Unknown tag city ${copy.tag_dest}. Pick a valid airport code.`);
        return;
      }
    }

    state.cash -= upfront;
    state.marketing_spend_monthly[d.origin] = clampMoney(d.investments.airport);
    const oAp = airport(d.origin);
    if (oAp && oAp.state) {
      state.marketing_investments.state[oAp.state] = clampMoney(d.investments.state);
    }
    state.marketing_investments.national = clampMoney(d.investments.national);
    state.marketing_investments.world = clampMoney(d.investments.world);

    routeLaunchDraft = null;
    routeLaunchStep = 1;
    routeStudioResume = null;
    renderRouteLaunchModal();

    const launched = openRoute(copy.origin, copy.dest, copy.aircraftId, copy.freq, copy.fare, {
      featured_ota: featured,
      expectReturn: copy.wantReturn,
      product: copy.product,
      tag_dest: copy.tag_dest,
    });
    if (!launched) {
      state.cash += upfront;
      pushPlayerEvent(`route launch cancelled — ${fmtMoney(upfront)} station/OTA upfront refunded`);
      saveGame();
      renderAll();
      return;
    }
    if (copy.wantReturn) {
      const ret = openRoute(copy.dest, copy.origin, copy.aircraftId, copy.freq, copy.fare, {
        featured_ota: featured,
        quiet: true,
        product: copy.product === 'standard' ? 'standard' : copy.product,
      });
      if (ret) {
        pushPlayerEvent(
          `also opened return ${copy.dest}–${copy.origin} (${copy.freq}x/wk) — both legs sell seats.`
        );
      } else {
        pushEvent(
          `Outbound ${copy.origin}–${copy.dest} launched, but return failed validation — plane may ferry empty.`,
          'bad'
        );
      }
      saveGame();
      renderAll();
    }
  }

  function selectFleetOffer(type, mode) {
    const ac = aircraftType(type);
    if (!ac) {
      alert(`Unknown aircraft type: ${type}`);
      return;
    }
    fleetShopOpen = true;
    fleetPending = {
      type,
      mode: mode === 'buy' ? 'buy' : 'lease',
      seats: ac.seats != null ? ac.seats : ac.seats_max || ac.seats_min || 50,
    };
    renderFleet();
    // Sticky confirm sits at the bottom — scroll so Confirm is always reachable.
    requestAnimationFrame(() => {
      const box = $('fleet-confirm-box');
      if (box) scrollSidePanelTo(box, { block: 'end' });
      const btn = box && box.querySelector('[data-fleet-action="confirm"]');
      if (btn) {
        try {
          btn.focus({ preventScroll: true });
        } catch (e) {
          /* ignore */
        }
      }
    });
  }

  function cancelFleetOffer() {
    fleetPending = null;
    renderFleet();
  }

  function setFleetPendingSeats(val) {
    if (!fleetPending) return;
    const ac = aircraftType(fleetPending.type);
    if (!ac) return;
    fleetPending.seats = aircraftSeats(fleetPending.type, +val);
    const active = document.activeElement;
    const keepFocus = active && active.id === 'fleet-seats-input';
    const selStart = keepFocus ? active.selectionStart : null;
    const selEnd = keepFocus ? active.selectionEnd : null;
    renderFleet();
    if (keepFocus) {
      const inp = $('fleet-seats-input');
      if (inp) {
        inp.focus();
        try {
          if (selStart != null) inp.setSelectionRange(selStart, selEnd);
        } catch (e) {
          /* ignore */
        }
      }
    }
  }

  function confirmFleetOffer() {
    if (!fleetPending) {
      alert('Pick an aircraft and Lease or Buy first.');
      return;
    }
    const { type, mode, seats } = fleetPending;
    const ac = aircraftType(type);
    if (!ac) {
      alert(`Unknown aircraft type: ${type}`);
      fleetPending = null;
      renderFleet();
      return;
    }
    const seatCount = aircraftSeats(type, seats);
    const dens = seatDensityInfo(type, seatCount);
    const leaseMo = planeLeaseMonthly(type, seatCount);
    const deposit = leaseMo * 2;
    const purchase = planePurchasePrice(type, seatCount);
    const maint = planeMaintMonthly(type, seatCount);
    const comfortLabel = comfortStars(dens.comfort);
    const densNote =
      dens.t < 0.35
        ? 'roomier cabin (more legroom)'
        : dens.t > 0.65
          ? 'dense cabin (more seats, less legroom)'
          : 'standard cabin density';

    if (mode === 'lease') {
      if (state.cash < deposit) {
        alert(`Insufficient cash — need ${fmtMoney(deposit)} deposit for this seat config.`);
        return;
      }
      if (
        !window.confirm(
          `Lease ${ac.name} (${seatCount} seats · ${densNote})?\n\n` +
            `Deposit: ${fmtMoney(deposit)}\nMonthly: ${fmtMoney(leaseMo)}\n` +
            `Comfort: ${comfortLabel}\n\n` +
            `Fewer seats → cheaper monthly + higher satisfaction.\n` +
            `More seats → higher capacity & monthly cost + tighter cabin.`
        )
      ) {
        return;
      }
      state.cash -= deposit;
      state.fleet.push({
        id: uid('ac'),
        type,
        seats: seatCount,
        leased: true,
        lease_months_left: 60,
        aog_days_left: 0,
        block_hours_month: 0,
        total_aog_days: 0,
        aog_events: 0,
        aog_log: [],
        acquired_day: state.day || 0,
      });
      pushPlayerEvent(
        `leased ${ac.name} (${seatCount} seats · ${densNote} · ${fmtMoney(leaseMo)}/mo · comfort ${comfortLabel}).`
      );
    } else {
      if (state.cash < purchase) {
        alert(`Insufficient cash — need ${fmtMoney(purchase)} for this seat config.`);
        return;
      }
      if (
        !window.confirm(
          `Purchase ${ac.name} (${seatCount} seats · ${densNote})?\n\n` +
            `Price: ${fmtMoney(purchase)}\nMaintenance: ${fmtMoney(maint)}/mo\n` +
            `Useful life: ${ac.lifespan_years} years\nComfort: ${comfortLabel}`
        )
      ) {
        return;
      }
      state.cash -= purchase;
      state.fleet.push({
        id: uid('ac'),
        type,
        seats: seatCount,
        leased: false,
        life_months_left: (ac.lifespan_years || 25) * 12,
        aog_days_left: 0,
        block_hours_month: 0,
        total_aog_days: 0,
        aog_events: 0,
        aog_log: [],
        acquired_day: state.day || 0,
      });
      pushPlayerEvent(
        `purchased ${ac.name} (${seatCount} seats · ${densNote} · comfort ${comfortLabel}).`
      );
    }
    fleetPending = null;
    fleetShopOpen = false;
    saveGame();
    renderAll();
    switchTab('fleet');
  }

  function validateOpenRoute(origin, dest, aircraftId, freq) {
    if (!hasGateAt(origin)) {
      return `You need a gate at ${origin} first. Lease one in the airport panel.`;
    }
    if (state.routes.some((r) => r.origin === origin && r.dest === dest)) {
      return `You already fly ${origin}–${dest}. Adjust frequency or fares on the active route card.`;
    }
    const plane = state.fleet.find((f) => f.id === aircraftId);
    if (!plane) {
      return 'Select an aircraft from your fleet (Fleet tab → add a plane if needed).';
    }
    const oAp = airport(origin);
    const dAp = airport(dest);
    if (!oAp || !dAp) return 'Invalid origin or destination airport.';
    const dist = haversineNm(oAp.lat, oAp.lon, dAp.lat, dAp.lon);
    const ac = aircraftType(plane.type);
    if (!ac) return 'Unknown aircraft type.';
    if (dist > ac.range_nm) {
      return `Route exceeds ${ac.name} range (${Math.round(dist)} nm).`;
    }
    const capErr = gateCapacityError(origin, freq);
    if (capErr) return capErr;
    const schedErr = aircraftScheduleError(aircraftId, origin, dest, freq, plane.type);
    if (schedErr) return schedErr;
    const routeMax = maxFrequencyForRoute(origin, dest, plane.type);
    const aircraftMax = maxFrequencyForAircraft(aircraftId, origin, dest, plane.type);
    if (freq > routeMax) {
      const ap = airport(origin);
      const hrs = ap ? ap.ops_hours_per_day : 14;
      const turn = ap ? ap.min_turnaround_min : 90;
      return (
        `Airport schedule limit at ${origin}: ${freq}/wk exceeds ~${routeMax}/wk for this aircraft ` +
        `(~${hrs}h ops window, ${turn}min turnaround between departures).`
      );
    }
    if (freq > aircraftMax) {
      const cap = planeWeeklyBlockHoursCapacity(plane);
      return (
        `Aircraft schedule limit: ${freq}/wk needs more block hours than this plane has left ` +
        `(~${fmtHours(cap)} hr/wk total — one aircraft, one place at a time). Max ~${aircraftMax}/wk on this route.`
      );
    }
    return null;
  }

  function openRoute(origin, dest, aircraftId, freq, fare, extras) {
    extras = extras || {};
    const routeErr = validateOpenRoute(origin, dest, aircraftId, freq);
    if (routeErr) {
      if (!extras.quiet) alert(routeErr);
      return false;
    }
    const plane = state.fleet.find((f) => f.id === aircraftId);
    const marketFare = marketFareForPair(origin, dest, plane.type);
    const finalFare = fare || marketFare;
    const via = estimateRouteViability(origin, dest, plane.type, freq, finalFare, aircraftId);
    let product = extras.product || 'standard';
    if (!ROUTE_PRODUCTS[product]) product = 'standard';
    const prodDef = routeProduct(product);
    let fareUse = finalFare;
    if (prodDef.fareMax) fareUse = Math.min(fareUse, prodDef.fareMax);
    if (prodDef.fareMin) fareUse = Math.max(fareUse, prodDef.fareMin);
    if (prodDef.fareCapVsMarket) {
      fareUse = Math.min(fareUse, Math.round(marketFare * prodDef.fareCapVsMarket));
    }
    const route = {
      id: uid('rt'),
      origin,
      dest,
      aircraft_type: plane.type,
      frequency_week: freq,
      fare: fareUse,
      market_fare: marketFare,
      fare_mode: extras.fare_mode || 'manual',
      ancillary_mode: state.ancillary_strategy || 'auto',
      aircraft_id: aircraftId,
      featured_ota: extras.featured_ota || [],
      established: !!extras.established || product === 'feeder' || product === 'essential',
      product,
      tag_dest: prodDef.isTag && extras.tag_dest ? extras.tag_dest : null,
      launch_forecast_load: via.load,
      launch_forecast_pax_day: via.dailyPax,
      stats: { days: 0, pax_sum: 0, load_sum: 0 },
      history: [],
    };
    state.routes.push(route);
    const starter = state.starter_route_count || 0;
    const routeCount = state.routes.length;
    if (!extras.quiet) {
      if (routeCount === 1 && starter === 0) {
        markMilestoneOnce('first_route', `${state.airline_name} launched its first route. Wheels up!`);
      } else if (routeCount > starter) {
        markMilestoneOnce('first_new_route', `${state.airline_name} added <b>${origin}–${dest}</b> — network growing.`);
      }
      const otaNote = (extras.featured_ota || []).length ? ` · OTA featured: ${extras.featured_ota.join(', ')}` : '';
      const ferryNote =
        extras.expectReturn || hasReturnLeg(route) || product === 'tag'
          ? ''
          : ' · ⚠ no return — empty ferry home';
      const prodNote = product !== 'standard' ? ` · ${prodDef.label}` : '';
      const tagNote = route.tag_dest ? ` → ${route.tag_dest}` : '';
      pushPlayerEvent(
        `opened ${origin}–${dest}${tagNote} (${freq}x/wk @ $${fareUse}${prodNote}) · planned ~${via.dailyPax} pax/day (${(via.load * 100).toFixed(0)}% load)${otaNote}${ferryNote}`
      );
      processReactiveCompetitorThreats('player_route', origin, dest);
      selectAirport(origin);
      routeFormDraft = {
        origin,
        originLabel: airport(origin) ? airportLabel(airport(origin)) : origin,
        dest: '',
        destLabel: '',
        aircraftId: aircraftId,
        freq: String(freq),
        fare: String(finalFare),
      };
      switchTab('routes');
    }
    saveGame();
    renderAll();
    return true;
  }

  function raiseSeed() {
    const opt = bootstrap.financing_options && bootstrap.financing_options.seed_equity;
    if (opt && opt.tiers && !opt.tiers.includes(state.financing_tier)) {
      alert('Seed equity is for startup-tier scenarios.');
      return;
    }
    if (state.seed_done) {
      alert('Seed round already closed. Look at Series A, PE, or debt.');
      return;
    }
    const amount = 4_500_000;
    const dilution = 0.22;
    state.cash += amount;
    state.equity_pct *= 1 - dilution;
    state.seed_done = true;
    state.raises = state.raises || [];
    state.raises.push({ type: 'seed', amount, dilution, day: state.day, ev: companyEnterpriseValue() });
    pushEvent(
      `Seed round closed: <b>${fmtMoney(amount)}</b> for <b>${(dilution * 100).toFixed(0)}%</b> of the company. You now own <b>${state.equity_pct.toFixed(1)}%</b>.`,
      'milestone'
    );
    markMilestoneOnce('raise_seed', `${state.airline_name} closed a seed round.`);
    saveGame();
    renderAll();
  }

  function raiseSeriesA() {
    if (state.series_a_done) {
      alert('Series A already closed.');
      return;
    }
    if ((state.day || 0) < 210) {
      alert('Series A opens after ~7 months of operations (day 210).');
      return;
    }
    if ((state.routes || []).length < 3) {
      alert('Series A needs at least 3 active routes.');
      return;
    }
    if ((state.ltm_revenue || 0) < 12_000_000) {
      alert(`Series A needs ~${fmtMoney(12_000_000)} LTM revenue (now ${fmtMoney(state.ltm_revenue || 0)}).`);
      return;
    }
    const trail = trailingMonthPnl();
    if (trail != null && trail < -500_000) {
      alert('Series A wants a network that is not free-falling — fix monthly losses first.');
      return;
    }
    const ev = companyEnterpriseValue();
    // Smaller check, steeper dilution than the old free $30M
    const amount = Math.round(Math.min(28_000_000, Math.max(12_000_000, ev * 0.22)));
    const dilution = Math.min(0.3, Math.max(0.22, amount / (ev + amount) + 0.04));
    state.cash += amount;
    state.equity_pct *= 1 - dilution;
    state.series_a_done = true;
    state.raises = state.raises || [];
    state.raises.push({ type: 'series_a', amount, dilution, day: state.day, ev });
    pushEvent(
      `Series A closed: <b>${fmtMoney(amount)}</b> at ~${fmtMoney(ev)} enterprise value ` +
        `(${(dilution * 100).toFixed(0)}% new shares). You retain <b>${state.equity_pct.toFixed(1)}%</b>. Rivals will notice the war chest.`,
      'milestone'
    );
    markMilestoneOnce('raise_series_a', `${state.airline_name} closed Series A.`);
    processReactiveCompetitorThreats('weekly');
    saveGame();
    renderAll();
  }

  function raiseGrowthEquity() {
    if (state.financing_tier !== 'serial') {
      alert('Growth equity via your CEO network is for the Exit CEO scenario (or after you unlock serial tier).');
      return;
    }
    if (state.growth_equity_done) {
      alert('Growth equity round already taken.');
      return;
    }
    const amount = 40_000_000;
    const dilution = 0.15;
    state.cash += amount;
    state.equity_pct *= 1 - dilution;
    state.growth_equity_done = true;
    state.raises = state.raises || [];
    state.raises.push({ type: 'growth', amount, dilution, day: state.day, ev: companyEnterpriseValue() });
    pushEvent(
      `Growth equity: <b>${fmtMoney(amount)}</b> (${(dilution * 100).toFixed(0)}% dilution). Ownership now <b>${state.equity_pct.toFixed(1)}%</b>.`,
      'milestone'
    );
    saveGame();
    renderAll();
  }

  /** PE / growth buyout of primary shares (company raise). */
  function raisePrivateEquity() {
    if (state.pe_done) {
      alert('A PE round is already on the books. Use secondary sale or IPO next.');
      return;
    }
    if ((state.routes || []).length < 4) {
      alert('PE wants a real network — open at least 4 routes first.');
      return;
    }
    if ((state.ltm_revenue || 0) < 28_000_000) {
      alert(`PE minimum ~${fmtMoney(28_000_000)} LTM revenue (now ${fmtMoney(state.ltm_revenue || 0)}).`);
      return;
    }
    if ((state.day || 0) < 330 && !state.series_a_done && state.financing_tier !== 'serial') {
      alert('PE usually arrives after ~11 months or a Series A. Keep flying or raise Series A first.');
      return;
    }
    const trail = trailingMonthPnl();
    if (trail == null || trail <= 0) {
      alert('PE wants a profitable trailing month before writing a check.');
      return;
    }
    const ev = companyEnterpriseValue();
    // Harder money: smaller of EV slice, steeper dilution, board pressure starts now
    const amount = Math.round(Math.min(55_000_000, Math.max(18_000_000, ev * 0.2)));
    const dilution = Math.min(0.38, Math.max(0.22, amount / (ev + amount) + 0.06));
    state.cash += amount;
    state.equity_pct *= 1 - dilution;
    state.pe_done = true;
    state.financing_tier = state.financing_tier === 'distressed' ? 'distressed' : 'serial';
    state.raises = state.raises || [];
    state.raises.push({ type: 'pe', amount, dilution, day: state.day, ev });
    pushEvent(
      `Private equity closed: <b>${fmtMoney(amount)}</b> into the airline at ~${fmtMoney(ev)} EV ` +
        `(${(dilution * 100).toFixed(0)}% dilution). You own <b>${state.equity_pct.toFixed(1)}%</b>. ` +
        `Board will watch red routes — rivals will match your capital.`,
      'milestone'
    );
    markMilestoneOnce('raise_pe', `${state.airline_name} took private equity capital.`);
    // Immediate competitive heat + board tick
    processReactiveCompetitorThreats('weekly');
    processReactiveCompetitorThreats('player_route');
    checkScenarioGoal();
    saveGame();
    renderAll();
  }

  /**
   * Sell part of YOUR stake (secondary) — cash goes to personal wealth, not company.
   * pctPoints = percentage points of the company (e.g. 10 = sell 10% of company).
   */
  function sellPersonalStake(pctPoints) {
    const pts = Math.round(pctPoints);
    if (!state || pts < 5 || pts > 40) {
      alert('Secondary sales are 5–40 percentage points of the company.');
      return;
    }
    const own = state.equity_pct || 0;
    if (pts >= own - 1) {
      alert(`You only own ${own.toFixed(1)}% — keep at least ~1% or do a full exit via IPO.`);
      return;
    }
    if (!state.seed_done && !state.series_a_done && !state.pe_done && state.financing_tier === 'startup') {
      alert('Find a PE buyer or close a round first — no liquid market for your shares yet.');
      return;
    }
    const ev = companyEnterpriseValue();
    const proceeds = Math.round(ev * (pts / 100));
    state.equity_pct = Math.max(1, own - pts);
    state.personal_cash = (state.personal_cash || 0) + proceeds;
    state.raises = state.raises || [];
    state.raises.push({ type: 'secondary', amount: proceeds, dilution: pts / 100, day: state.day, ev });
    pushEvent(
      `Secondary sale: you sold <b>${pts}pp</b> of the company for <b>${fmtMoney(proceeds)}</b> personal cash ` +
        `(EV ~${fmtMoney(ev)}). Company cash unchanged. You still own <b>${state.equity_pct.toFixed(1)}%</b>.`,
      'milestone'
    );
    markMilestoneOnce('secondary_sale', `${state.player_name} took chips off the table.`);
    saveGame();
    renderAll();
  }

  function canLaunchIPO() {
    if (!state || state.ipo_done || state.public) return { ok: false, reason: 'IPO already done or not applicable.' };
    const reasons = [];
    if ((state.ltm_revenue || 0) < 100_000_000) {
      reasons.push(`LTM revenue ${fmtMoney(state.ltm_revenue || 0)} (need ${fmtMoney(100_000_000)})`);
    }
    if ((state.routes || []).length < 8) reasons.push(`${state.routes.length}/8 routes`);
    if ((state.reputation || 0) < 42) reasons.push(`reputation ${(state.reputation || 0).toFixed(0)}/42`);
    if ((state.equity_pct || 100) < 18) reasons.push('ownership too thin for a clean IPO story');
    const trail = trailingMonthPnl();
    if (trail == null || trail <= 0) reasons.push('need a profitable trailing month');
    if (runwayMonths() < 6) reasons.push('need ≥6 months cash runway at IPO');
    if (reasons.length) return { ok: false, reason: reasons.join(' · ') };
    return { ok: true, reason: '' };
  }

  function launchIPO() {
    const gate = canLaunchIPO();
    if (!gate.ok) {
      alert(`IPO not ready: ${gate.reason}`);
      return;
    }
    const evPre = companyEnterpriseValue();
    // Primary: company raises; Secondary: founder sells a slice into the IPO
    const primary = Math.round(Math.min(95_000_000, Math.max(35_000_000, evPre * 0.28)));
    const primaryDilution = Math.min(0.32, primary / (evPre + primary) + 0.03);
    state.cash += primary;
    state.equity_pct *= 1 - primaryDilution;
    const secondaryPts = Math.min(10, Math.max(4, Math.floor((state.equity_pct || 0) * 0.12)));
    const evPost = evPre + primary;
    const secondaryProceeds = Math.round(evPost * (secondaryPts / 100));
    state.equity_pct = Math.max(5, (state.equity_pct || 0) - secondaryPts);
    state.personal_cash = (state.personal_cash || 0) + secondaryProceeds;
    state.ipo_done = true;
    state.public = true;
    state.financing_tier = 'serial';
    state.bond_rating = 'BB';
    state.raises = state.raises || [];
    state.raises.push({
      type: 'ipo',
      amount: primary,
      dilution: primaryDilution,
      secondary: secondaryProceeds,
      day: state.day,
      ev: evPost,
    });
    pushEvent(
      `IPO priced: company raised <b>${fmtMoney(primary)}</b> · you sold <b>${secondaryPts}pp</b> for ` +
        `<b>${fmtMoney(secondaryProceeds)}</b> personal cash · EV ~${fmtMoney(evPost)}. ` +
        `You retain <b>${state.equity_pct.toFixed(1)}%</b> of a public regional.`,
      'milestone'
    );
    markMilestoneOnce('ipo', `${state.airline_name} went public.`);
    queueDecision({
      kicker: `${fmtDate(state.day)} · IPO`,
      title: 'You took the airline public',
      body:
        `<p><b>${state.airline_name}</b> is now a public company.</p>` +
        `<p>Primary raise <b>${fmtMoney(primary)}</b> (company cash). Your secondary <b>${fmtMoney(secondaryProceeds)}</b> is personal wealth. ` +
        `Ownership now <b>${state.equity_pct.toFixed(1)}%</b>.</p>` +
        `<p class="muted" style="font-size:0.85rem;">Keep scaling routes — or sell more on the secondary market from Capital.</p>`,
      logLine: `IPO on day ${state.day}`,
      options: [
        { id: 'ipo_continue', label: 'A — Keep building', hint: 'Stay CEO of a public regional.', effect: 'none' },
        { id: 'ipo_hangar', label: 'B — Back to hangar', hint: 'Save and pick a new scenario.', effect: 'goal_hangar' },
      ],
    });
    checkScenarioGoal();
    saveGame();
    renderAll();
  }

  function maybeCapitalCoach() {
    if (!state || state.game_over) return;
    const burn = burnMonthly();
    const runway = burn > 0 ? state.cash / burn : 99;
    const debtSvc = monthlyDebtService();
    // Earlier, clearer cash warning — before the death spiral (was only debt + <3 mo)
    if (runway < 4.5 && !(state.capital_coach_day > state.day - 40)) {
      state.capital_coach_day = state.day;
      const idleGates = allGateUtilizations().filter((u) => u.idle || u.pct < 35).length;
      const idleNote =
        idleGates > 0
          ? ` You have <b>${idleGates}</b> underused gate(s) still charging lease — fill them or give them back.`
          : '';
      pushEvent(
        `Cash runway ~<b>${runway.toFixed(1)} mo</b>${debtSvc > 0 ? ` · debt service ${fmtMoney(debtSvc)}/mo` : ''}.` +
          idleNote +
          ` Fix loads, cut idle metal/gates, or raise capital before Chapter 11 is the only door left.`,
        runway < 2.5 ? 'bad' : 'neutral'
      );
    }
  }

  function payDownDebt(debtId, amount) {
    if (!state) return;
    const d = (state.debt || []).find((x) => x.id === debtId);
    if (!d || !(d.principal > 0)) return;
    const pay = Math.min(amount, d.principal, Math.max(0, state.cash));
    if (pay < 1) return;
    const before = d.principal;
    state.cash -= pay;
    d.principal = Math.max(0, d.principal - pay);
    if (d.monthly_payment && before > 0) {
      d.monthly_payment = Math.round(d.monthly_payment * (d.principal / before));
    }
    if (d.principal <= 0) {
      state.debt = state.debt.filter((x) => x !== d);
      pushEvent(`${d.name} fully repaid — final payment ${fmtMoney(pay)}. Debt retired.`, 'good');
      markMilestoneOnce(`debt_retired_${debtId}`, `${state.airline_name} retired <b>${d.name}</b> in full.`);
    } else {
      pushEvent(`Paid down ${fmtMoney(pay)} of ${d.name} — ${fmtMoney(d.principal)} remaining.`, 'good');
    }
    checkScenarioGoal();
    saveGame();
    renderAll();
  }

  /** Redeem / buy back bond principal with cash (counts toward max_debt goals). */
  function payDownBond(bondId, amount) {
    if (!state) return;
    const b = (state.bonds || []).find((x) => x.id === bondId);
    if (!b || !(b.principal > 0)) return;
    const pay = Math.min(amount, b.principal, Math.max(0, state.cash));
    if (pay < 1) return;
    state.cash -= pay;
    b.principal = Math.max(0, b.principal - pay);
    if (b.principal <= 0) {
      state.bonds = state.bonds.filter((x) => x !== b);
      pushEvent(`${b.name} redeemed in full — ${fmtMoney(pay)} paid from cash.`, 'good');
      markMilestoneOnce(`bond_retired_${bondId}`, `${state.airline_name} retired <b>${b.name}</b>.`);
    } else {
      pushEvent(`Bond buyback: paid ${fmtMoney(pay)} on ${b.name} — ${fmtMoney(b.principal)} still out.`, 'good');
    }
    checkScenarioGoal();
    saveGame();
    renderAll();
  }

  function takeBankLoan() {
    if ((state.routes || []).length < 1 && state.financing_tier !== 'distressed') {
      alert('Banks want at least one flying route before a term loan (except distressed rescues).');
      return;
    }
    const termMonths = 60;
    const amount = state.financing_tier === 'serial' || state.pe_done || state.public ? 20_000_000 : 8_000_000;
    const rate = state.financing_tier === 'distressed' ? 0.11 : 0.085;
    const r = rate / 12;
    const monthly = (amount * r) / (1 - Math.pow(1 + r, -termMonths));
    state.cash += amount;
    state.debt.push({
      id: uid('debt'),
      name: 'Bank term loan',
      principal: amount,
      rate,
      monthly_payment: monthly,
      months_left: termMonths,
      term_months: termMonths,
      secured: false,
    });
    const split = debtMonthPaymentSplit(state.debt[state.debt.length - 1]);
    pushEvent(
      `Bank loan: <b>${fmtMoney(amount)}</b> @ ${(rate * 100).toFixed(1)}% · ${termMonths} mo · ` +
        `~${fmtMoney(monthly)}/mo (<b>${fmtMoney(split.interest)}</b> interest / <b>${fmtMoney(split.principal)}</b> principal first month).`,
      'good'
    );
    saveGame();
    renderAll();
  }

  function issueCorporateBonds() {
    const rating = state.bond_rating || 'B';
    const coupons = bootstrap.financing_options.corporate_bonds.coupon_by_rating;
    const coupon = coupons[rating] || 0.1;
    if (state.ltm_revenue < 25_000_000 && state.financing_tier !== 'serial') {
      alert('Need ~$25M LTM revenue for unsecured bonds.');
      return;
    }
    const amount = 35_000_000;
    state.cash += amount;
    state.bonds.push({
      id: uid('bond'),
      name: `${rating} corporate notes`,
      principal: amount,
      coupon,
      months_left: 120,
    });
    pushEvent(`Bond issuance: ${fmtMoney(amount)} @ ${(coupon * 100).toFixed(1)}% coupon.`, 'good');
    saveGame();
    renderAll();
  }

  function issueAssetBackedBonds() {
    if (state.gates.length < 2) {
      alert('Need at least 2 gate leases for asset-backed bonds.');
      return;
    }
    const amount = 12_000_000;
    const coupon = 0.088;
    state.cash += amount;
    state.bonds.push({
      id: uid('bond'),
      name: 'Asset-backed notes (gates)',
      principal: amount,
      coupon,
      months_left: 60,
      secured: true,
    });
    pushEvent(`Asset-backed bonds: ${fmtMoney(amount)}.`, 'good');
    saveGame();
    renderAll();
  }

  function restructureDebt() {
    const d = state.debt.find((x) => x.id === 'inherit_term');
    if (!d) {
      alert('No inherited term loan to restructure.');
      return;
    }
    if (d.restructured) {
      alert('Already restructured — use Pay down on the loan (or bonds) to cut principal toward your goal.');
      return;
    }
    d.monthly_payment = 185_000;
    d.rate = 0.078;
    d.restructured = true;
    // Restructure eases cash burn only — principal is unchanged (goal max_debt still needs paydowns).
    pushEvent(
      'Creditors agreed to restructured payments (−30% monthly). Principal is unchanged — pay down the loan to hit debt goals.',
      'good'
    );
    saveGame();
    renderAll();
  }

  function marketingInvestmentsFromPanel(iata) {
    ensureMarketingInvestments();
    ensureMacro();
    const oAp = airport(iata);
    const inv = {
      airport: 0,
      state: 0,
      national: 0,
      world: 0,
    };
    document.querySelectorAll(`[data-mkt-inv-amount="${iata}"]`).forEach((inp) => {
      const key = inp.dataset.mktInvKey;
      const toggle = document.querySelector(`[data-mkt-inv-toggle="${iata}"][data-mkt-inv-key="${key}"]`);
      const on = !toggle || toggle.checked;
      if (key && on) inv[key] = clampMoney(inp.valueAsNumber);
    });
    const ota = {};
    (bootstrap.ota_platforms || []).forEach((p) => {
      const list = document.querySelector(`[data-mkt-ota-list="${iata}"][data-ota-id="${p.id}"]`);
      const feat = document.querySelector(`[data-mkt-ota-feature="${iata}"][data-ota-id="${p.id}"]`);
      const hub = document.querySelector(`[data-mkt-ota-hub="${iata}"][data-ota-id="${p.id}"]`);
      ota[p.id] = {
        list: !!(list && list.checked),
        feature: !!(feat && feat.checked),
        hubPush: !!(hub && hub.checked),
      };
    });
    return { inv, ota, oAp };
  }

  function renderMarketingPanelHtml(iata) {
    ensureMarketingInvestments();
    ensureMacro();
    const oAp = airport(iata);
    const airportSpend = clampMoney(state.marketing_spend_monthly[iata]);
    const stateSpend = oAp && oAp.state ? clampMoney(state.marketing_investments.state[oAp.state]) : 0;
    const nationalSpend = clampMoney(state.marketing_investments.national);
    const worldSpend = clampMoney(state.marketing_investments.world);
    const channels = bootstrap.marketing_channels || [];
    const channelRows = channels
      .map((ch) => {
        if (ch.id === 'airport') {
          return `<div class="invest-row">
            <label><input type="checkbox" data-mkt-inv-toggle="${iata}" data-mkt-inv-key="airport" checked disabled> <strong>${ch.label}</strong> at ${iata}
              <span class="invest-hint">${ch.hint}</span></label>
            <input type="number" min="0" step="1000" data-mkt-inv-amount="${iata}" data-mkt-inv-key="airport" value="${airportSpend}">
          </div>`;
        }
        if (ch.id === 'state' && oAp && oAp.state) {
          return `<div class="invest-row">
            <label><input type="checkbox" data-mkt-inv-toggle="${iata}" data-mkt-inv-key="state" ${stateSpend > 0 ? 'checked' : ''}> <strong>${ch.label}</strong> (${oAp.state})
              <span class="invest-hint">${ch.hint}</span></label>
            <input type="number" min="0" step="1000" data-mkt-inv-amount="${iata}" data-mkt-inv-key="state" value="${stateSpend}">
          </div>`;
        }
        if (ch.id === 'national') {
          return `<div class="invest-row">
            <label><input type="checkbox" data-mkt-inv-toggle="${iata}" data-mkt-inv-key="national" ${nationalSpend > 0 ? 'checked' : ''}> <strong>${ch.label}</strong>
              <span class="invest-hint">${ch.hint}</span></label>
            <input type="number" min="0" step="5000" data-mkt-inv-amount="${iata}" data-mkt-inv-key="national" value="${nationalSpend}">
          </div>`;
        }
        if (ch.id === 'world') {
          return `<div class="invest-row">
            <label><input type="checkbox" data-mkt-inv-toggle="${iata}" data-mkt-inv-key="world" ${worldSpend > 0 ? 'checked' : ''}> <strong>${ch.label}</strong>
              <span class="invest-hint">${ch.hint}</span></label>
            <input type="number" min="0" step="5000" data-mkt-inv-amount="${iata}" data-mkt-inv-key="world" value="${worldSpend}">
          </div>`;
        }
        return '';
      })
      .join('');

    const impact = marketingImpactSummary(iata);
    const impactHtml = `<p class="mkt-impact-line" style="font-size:0.78rem;margin:0 0 10px;padding:8px 10px;border-radius:8px;border:1px solid var(--border);background:rgba(0,200,150,0.06);line-height:1.4;">
      <b>What this does:</b> ${impact.line}. Look for higher <b>load %</b> on routes touching ${iata} (moves over a few days, not instantly). Brand awareness also lifts monthly while you keep spending.
    </p>`;
    const hubList = state.hub_ota_push[iata] || [];
    const otaRows = (bootstrap.ota_platforms || [])
      .map(
        (p) => `<div class="invest-row">
          <label><input type="checkbox" data-mkt-ota-list="${iata}" data-ota-id="${p.id}" ${state.macro.ota_listed[p.id] ? 'checked' : ''}> <strong>${p.name}</strong> — list airline
            <span class="invest-hint">${fmtMoney(p.listing_monthly)}/mo + ${p.commission_pct}% commission</span></label>
        </div>
        <div class="invest-row" style="padding-left:18px;">
          <label><input type="checkbox" data-mkt-ota-feature="${iata}" data-ota-id="${p.id}"> Route featured on new launches (+${fmtMoney(p.route_feature_monthly || 0)}/mo)</label>
        </div>
        <div class="invest-row" style="padding-left:18px;">
          <label><input type="checkbox" data-mkt-ota-hub="${iata}" data-ota-id="${p.id}" ${hubList.includes(p.id) ? 'checked' : ''}> Hub push at ${iata} (+${fmtMoney(p.hub_push_monthly || 0)}/mo)</label>
        </div>`
      )
      .join('');

    const monthlyTotal =
      airportSpend +
      stateSpend +
      nationalSpend +
      worldSpend +
      hubList.reduce((sum, pid) => {
        const p = (bootstrap.ota_platforms || []).find((x) => x.id === pid);
        return sum + (p ? p.hub_push_monthly || 0 : 0);
      }, 0);

    return `<div class="mkt-panel">
      <p class="route-launch-section" style="margin-top:0;">Marketing &amp; distribution</p>
      ${impactHtml}
      <p class="muted" style="font-size:0.68rem;margin:0 0 8px;">Airport ads are the main lever for local load. State/national/world help brand across the network.</p>
      ${channelRows}
      <p class="route-launch-section">Distribution — OTAs</p>
      ${otaRows}
      <p class="muted" style="font-size:0.72rem;margin:8px 0;">Active recurring from saved settings: <b>${fmtMoney(monthlyTotal)}/mo</b> (plus route-level OTA features)</p>
      <button type="button" class="btn" onclick="Runway.applyMarketingInvestments('${iata}')">Apply marketing &amp; distribution</button>
    </div>`;
  }

  function applyMarketingInvestments(iata) {
    const { inv, ota, oAp } = marketingInvestmentsFromPanel(iata);
    let upfront = 0;
    (bootstrap.ota_platforms || []).forEach((p) => {
      const o = ota[p.id];
      if (o && o.list && !state.macro.ota_listed[p.id]) upfront += p.listing_monthly;
    });
    if (upfront > 0 && state.cash < upfront) {
      alert(`Need ${fmtMoney(upfront)} upfront for new OTA listings.`);
      return;
    }
    if (upfront > 0) state.cash -= upfront;

    state.marketing_spend_monthly[iata] = clampMoney(inv.airport);
    if (oAp && oAp.state) state.marketing_investments.state[oAp.state] = clampMoney(inv.state);
    state.marketing_investments.national = clampMoney(inv.national);
    state.marketing_investments.world = clampMoney(inv.world);

    if (!state.hub_ota_push[iata]) state.hub_ota_push[iata] = [];
    (bootstrap.ota_platforms || []).forEach((p) => {
      const o = ota[p.id];
      if (!o) return;
      if (o.list) state.macro.ota_listed[p.id] = true;
      const hubIdx = state.hub_ota_push[iata].indexOf(p.id);
      if (o.hubPush && hubIdx < 0) state.hub_ota_push[iata].push(p.id);
      if (!o.hubPush && hubIdx >= 0) state.hub_ota_push[iata].splice(hubIdx, 1);
    });

    saveGame();
    renderAirportPanel(iata);
    pushPlayerEvent(
      `updated marketing at ${iata}: ${fmtMoney(inv.airport)}/mo local` +
        (upfront ? ` · ${fmtMoney(upfront)} OTA listing upfront` : '')
    );
    renderEvents();
    renderEconomy();
    return inv.airport;
  }

  function applyMarketing(iata) {
    return applyMarketingInvestments(iata);
  }

  function resetMapView() {
    fitMapToManagedArea();
  }

  function setupMapboxLayers() {
    if (!mapboxMap || mapboxMap.getSource('airports')) return;

    mapboxMap.addSource('competitor-routes', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    });
    mapboxMap.addSource('player-routes', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    });
    mapboxMap.addSource('airport-halos', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    });
    mapboxMap.addSource('airports', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    });

    mapboxMap.addLayer({
      id: 'competitor-routes-layer',
      type: 'line',
      source: 'competitor-routes',
      paint: {
        'line-color': '#ff7b5a',
        'line-width': 1.2,
        'line-opacity': 0.35,
        'line-dasharray': [2, 2],
      },
    });
    // Wide invisible hit target for easier route taps
    mapboxMap.addLayer({
      id: 'player-routes-hit-layer',
      type: 'line',
      source: 'player-routes',
      paint: {
        'line-color': '#ffffff',
        'line-width': 14,
        'line-opacity': 0.01,
      },
    });
    mapboxMap.addLayer({
      id: 'player-routes-glow-layer',
      type: 'line',
      source: 'player-routes',
      filter: ['==', ['get', 'selected'], true],
      paint: {
        'line-color': ['get', 'color'],
        'line-width': 10,
        'line-opacity': 0.28,
        'line-blur': 2,
      },
    });
    mapboxMap.addLayer({
      id: 'player-routes-layer',
      type: 'line',
      source: 'player-routes',
      paint: {
        'line-color': ['get', 'color'],
        'line-width': ['get', 'width'],
        'line-opacity': ['get', 'opacity'],
      },
    });
    mapboxMap.addLayer({
      id: 'airport-halos-layer',
      type: 'circle',
      source: 'airport-halos',
      paint: {
        'circle-radius': ['get', 'haloRadius'],
        'circle-color': 'transparent',
        'circle-stroke-color': '#00e4a8',
        'circle-stroke-width': 2,
        'circle-stroke-opacity': ['get', 'haloOpacity'],
      },
    });
    mapboxMap.addLayer({
      id: 'airports-layer',
      type: 'circle',
      source: 'airports',
      paint: {
        'circle-radius': ['get', 'radius'],
        'circle-color': ['get', 'fill'],
        'circle-stroke-color': ['get', 'stroke'],
        'circle-stroke-width': ['get', 'strokeWidth'],
      },
    });
    mapboxMap.addLayer({
      id: 'airport-labels-layer',
      type: 'symbol',
      source: 'airports',
      filter: ['==', ['get', 'showLabel'], true],
      layout: {
        'text-field': ['get', 'iata'],
        'text-size': 11,
        'text-offset': [0.9, 0],
        'text-anchor': 'left',
      },
      paint: {
        'text-color': '#f0f8ff',
        'text-halo-color': '#041018',
        'text-halo-width': 2,
      },
    });
    mapboxMap.addLayer({
      id: 'airport-cap-labels-layer',
      type: 'symbol',
      source: 'airports',
      filter: ['==', ['get', 'showCapBadge'], true],
      layout: {
        'text-field': ['get', 'capLabel'],
        'text-size': 9,
        'text-offset': [0, -1.35],
        'text-anchor': 'bottom',
        'text-font': ['Open Sans Bold', 'Arial Unicode MS Bold'],
      },
      paint: {
        'text-color': [
          'case',
          ['<', ['get', 'gateUtilPct'], 50],
          '#ff9b7a',
          ['<', ['get', 'gateUtilPct'], 75],
          '#ffd166',
          '#5dffa8',
        ],
        'text-halo-color': '#041018',
        'text-halo-width': 1.5,
      },
    });
    mapboxMap.addLayer({
      id: 'airport-cap-sub-layer',
      type: 'symbol',
      source: 'airports',
      filter: ['all', ['==', ['get', 'showCapBadge'], true], ['>', ['get', 'gateRemaining'], 0]],
      layout: {
        'text-field': ['get', 'capSub'],
        'text-size': 8,
        'text-offset': [0, -2.1],
        'text-anchor': 'bottom',
      },
      paint: {
        'text-color': '#a8c4e0',
        'text-halo-color': '#041018',
        'text-halo-width': 1.2,
      },
    });
  }

  function mapboxFatalError(err) {
    const msg = err && err.message ? String(err.message) : String(err || '');
    return /unauthorized|invalid token|401|403|forbidden/i.test(msg);
  }

  function abandonMapbox(reason) {
    console.warn('Runway: Mapbox unavailable — using raster fallback.', reason);
    mapboxReady = false;
    mapboxInitStarted = false;
    window.RUNWAY_MAPBOX_TOKEN = '';
    const wrap = document.querySelector('.map-wrap');
    if (wrap) wrap.classList.remove('mapbox-active');
    if (mapboxMap) {
      try {
        mapboxMap.remove();
      } catch (e) {
        /* ignore teardown errors */
      }
      mapboxMap = null;
    }
    const container = $('runway-map');
    if (container) container.innerHTML = '';
    drawMapSvg();
    fitMapToManagedArea();
  }

  function initMapbox() {
    if (!useMapbox() || mapboxMap || mapboxInitStarted) return;
    const container = $('runway-map');
    if (!container) return;
    mapboxInitStarted = true;

    mapboxgl.accessToken = getMapboxToken();
    const bounds = airportLngLatBounds(0.2) || [
      [-125.5, 24.0],
      [-66.0, 49.55],
    ];
    let loadTimeout = null;
    const wrap = document.querySelector('.map-wrap');
    if (wrap) wrap.classList.add('mapbox-active');

    try {
      mapboxMap = new mapboxgl.Map({
        container: 'runway-map',
        style: MAPBOX_STYLE,
        bounds,
        fitBoundsOptions: { padding: 48 },
        attributionControl: false,
        dragRotate: false,
        pitchWithRotate: false,
        touchPitch: false,
        dragPan: true,
        scrollZoom: true,
        boxZoom: false,
      });
    } catch (err) {
      abandonMapbox(err);
      return;
    }

    loadTimeout = window.setTimeout(() => {
      if (!mapboxReady) abandonMapbox('load timeout');
    }, 45000);

    mapboxMap.on('error', (e) => {
      const err = e && e.error ? e.error : e;
      if (!mapboxReady && mapboxFatalError(err)) abandonMapbox(err);
    });

    mapboxMap.on('load', () => {
      if (loadTimeout) window.clearTimeout(loadTimeout);
      setupMapboxLayers();
      mapboxReady = true;
      ensureMapboxSize();
      drawMap();
      fitMapToManagedArea();

      mapboxMap.on('click', 'airports-layer', (ev) => {
        if (ev.features && ev.features[0] && ev.features[0].properties) {
          selectedRouteId = null;
          selectAirport(ev.features[0].properties.iata);
        }
      });
      const clickRoute = (ev) => {
        if (ev.features && ev.features[0] && ev.features[0].properties) {
          const rid = ev.features[0].properties.routeId;
          if (rid) {
            ev.originalEvent && ev.originalEvent.stopPropagation && ev.originalEvent.stopPropagation();
            selectMapRoute(rid);
          }
        }
      };
      mapboxMap.on('click', 'player-routes-hit-layer', clickRoute);
      mapboxMap.on('click', 'player-routes-layer', clickRoute);
      const apPopup = new mapboxgl.Popup({
        closeButton: false,
        closeOnClick: false,
        offset: 14,
        className: 'map-ap-popup',
        maxWidth: '260px',
      });
      mapboxMap.on('mouseenter', 'airports-layer', () => {
        if (mapboxMap) mapboxMap.getCanvas().style.cursor = 'pointer';
      });
      mapboxMap.on('mousemove', 'airports-layer', (ev) => {
        if (!ev.features || !ev.features[0]) return;
        const p = ev.features[0].properties || {};
        const coords = ev.features[0].geometry.coordinates.slice();
        const tip = p.tip || `${p.iata} · ${p.oppLabel || ''}`;
        apPopup
          .setLngLat(coords)
          .setHTML(
            `<div class="map-ap-popup-inner"><strong>${p.iata}</strong> · ${p.oppLabel || 'Market'}` +
              (p.oppScore != null ? ` · ${p.oppScore}/100` : '') +
              `<br><span class="muted">${String(tip).replace(/^[^—]*—\s*/, '')}</span></div>`
          )
          .addTo(mapboxMap);
      });
      mapboxMap.on('mouseleave', 'airports-layer', () => {
        if (mapboxMap) mapboxMap.getCanvas().style.cursor = 'grab';
        apPopup.remove();
      });
      const routePopup = new mapboxgl.Popup({
        closeButton: false,
        closeOnClick: false,
        offset: 10,
        className: 'map-ap-popup',
        maxWidth: '280px',
      });
      mapboxMap.on('mouseenter', 'player-routes-hit-layer', () => {
        if (mapboxMap) mapboxMap.getCanvas().style.cursor = 'pointer';
      });
      mapboxMap.on('mousemove', 'player-routes-hit-layer', (ev) => {
        if (!ev.features || !ev.features[0]) return;
        const p = ev.features[0].properties || {};
        routePopup
          .setLngLat(ev.lngLat)
          .setHTML(
            `<div class="map-ap-popup-inner"><strong>${p.origin}–${p.dest}</strong> · ${p.label || 'Route'}` +
              `<br><span class="muted">${p.tip || 'Click to review'}</span></div>`
          )
          .addTo(mapboxMap);
      });
      mapboxMap.on('mouseleave', 'player-routes-hit-layer', () => {
        if (mapboxMap) mapboxMap.getCanvas().style.cursor = 'grab';
        routePopup.remove();
      });
    });
  }

  /**
   * Map line style for an active player route — color = health / profitability.
   * Green cash engines, gold ok, amber watch, red structural loss; thicker when selected.
   */
  function routeMapStyle(route) {
    if (!route) {
      return { color: '#ffd166', width: 2.6, opacity: 0.85, selected: false, label: 'Route', tip: '' };
    }
    const health = diagnoseRouteHealth(route);
    const selected = selectedRouteId === route.id;
    let color = '#ffd166';
    let label = 'Active route';
    let tip = `${route.origin}–${route.dest}`;
    if (health) {
      const pnl = health.pnl || 0;
      if (health.severity === 'critical' || pnl < -400) {
        color = '#ff5c4a';
        label = 'Losing / weak';
      } else if (health.severity === 'watch' || pnl < 0) {
        color = '#ffb020';
        label = 'Needs attention';
      } else if (pnl > 800) {
        color = '#5dffa8';
        label = 'Cash engine';
      } else {
        color = '#00c896';
        label = 'Healthy';
      }
      tip = `${route.origin}–${route.dest} · ${label} · ${fmtMoney(pnl)}/day var · load ${
        health.load != null ? Math.round(health.load * 100) + '%' : '—'
      } · click to review`;
    }
    return {
      color,
      width: selected ? 5.2 : 3.1,
      opacity: selected ? 1 : 0.92,
      selected,
      label,
      tip,
      routeId: route.id,
    };
  }

  function buildRoutesGeoJSON(routes, isPlayer) {
    const features = [];
    (routes || []).forEach((route) => {
      const o = airport(route.origin);
      const d = airport(route.dest);
      if (!o || !d) return;
      const style = isPlayer ? routeMapStyle(route) : null;
      features.push({
        type: 'Feature',
        geometry: {
          type: 'LineString',
          coordinates: [
            [o.lon, o.lat],
            [d.lon, d.lat],
          ],
        },
        properties: isPlayer
          ? {
              origin: route.origin,
              dest: route.dest,
              routeId: route.id,
              color: style.color,
              width: style.width,
              opacity: style.opacity,
              selected: style.selected,
              tip: style.tip,
              label: style.label,
            }
          : {
              origin: route.origin,
              dest: route.dest,
              color: '#ff7b5a',
              width: 1.4,
              opacity: 0.4,
            },
      });
    });
    return { type: 'FeatureCollection', features };
  }

  function selectMapRoute(routeId) {
    if (!routeId || !state) return;
    const route = (state.routes || []).find((r) => r.id === routeId);
    if (!route) return;
    selectedRouteId = routeId;
    selectedAirport = null;
    drawMap();
    switchTab('routes');
    openRouteReview(routeId);
    if (isMobileLayout()) scrollToSidePanel();
  }

  /**
   * Map opportunity scoring for airport dots.
   * Size ≈ market scale; color ≈ opportunity type for the player.
   */
  function airportOpportunityScore(ap) {
    if (!ap) {
      return {
        score: 0,
        size: 4,
        fill: '#5eb8ff',
        tier: 'open',
        label: 'Market',
        tip: '',
        underserved: 0,
        fareOpp: 0,
        scale: 0,
      };
    }
    const pax = ap.annual_pax_m || 1;
    const pop = ap.metro_pop_m || 0.5;
    const hub = ap.hub_strength != null ? ap.hub_strength : 0.35;
    const wealth = airportWealth(ap);
    const comps = (ap.incumbents || []).length;
    const rivalDeps = competitorDeparturesWeeklyFrom(ap.iata);
    const marketDeps = airportMarketDeparturesWeekly(ap) || 80;
    // Underserved: population/pax pressure not fully absorbed by hub share + rivals
    const serviceRatio = Math.min(1.4, (marketDeps + rivalDeps * 0.5) / Math.max(40, pop * 90));
    const underserved = Math.max(0, Math.min(1, 1 - serviceRatio * (0.55 + hub * 0.45)));
    // Fare opportunity: wealthier / longer-haul style hubs with soft competition
    const fareOpp = Math.max(0, Math.min(1, wealth * 0.65 + (1 - hub) * 0.25 + (comps <= 2 ? 0.15 : 0)));
    // Scale for dot size
    const scale = Math.max(0, Math.min(1, Math.log10(1 + pax * 3) / 2.2));

    const owned = state && hasGateAt(ap.iata);
    const util = owned ? gateUtilizationAt(ap.iata) : null;
    const underCap = util && (util.underutilized || util.idle);

    let tier = 'open';
    let fill = '#5eb8ff';
    let label = 'Open market';
    let tip = 'Scout competitors and demand before leasing.';

    if (owned) {
      tier = underCap ? 'yours_open' : 'yours';
      fill = underCap ? '#5dffa8' : '#00c896';
      label = underCap ? 'Your gate · capacity open' : 'Your gate';
      tip = underCap
        ? `${util.remaining} deps/wk open — add frequency or a new market from here.`
        : 'Your operation. Expand carefully if gate is tight.';
    } else if (underserved >= 0.55 && fareOpp >= 0.4) {
      tier = 'gold';
      fill = '#ffd166';
      label = 'High opportunity';
      tip = 'Underserved demand + solid fare potential — strong candidate to lease and launch.';
    } else if (underserved >= 0.48) {
      tier = 'underserved';
      fill = '#7dd3fc';
      label = 'Underserved';
      tip = 'Population wants more lift than the market fully serves — good growth city if you can win share.';
    } else if (fareOpp >= 0.58 && hub < 0.55) {
      tier = 'premium';
      fill = '#c4b5fd';
      label = 'Premium fares';
      tip = 'Wealthier market — higher average fares if you can compete on schedule/product.';
    } else if (hub >= 0.62 || comps >= 4) {
      tier = 'fortress';
      fill = '#ff6b5a';
      label = 'Fortress / contested';
      tip = 'Strong incumbents — hard but high traffic. Expect fare and capacity fights.';
    } else {
      tier = 'open';
      fill = '#5eb8ff';
      label = 'Open market';
      tip = 'Balanced market — scout pair ideas from a nearby gate you control.';
    }

    const score = Math.round((underserved * 0.45 + fareOpp * 0.35 + scale * 0.2) * 100);
    // Size: market scale primary; opportunity bumps radius slightly
    let size = 3.6 + scale * 5.2 + underserved * 1.4 + fareOpp * 0.8;
    if (owned) size = Math.max(size, 6.2);
    if (selectedAirport === ap.iata) size = Math.max(size, 7);

    return {
      score,
      size,
      fill,
      tier,
      label,
      tip,
      underserved,
      fareOpp,
      scale,
      owned: !!owned,
      underCap: !!underCap,
    };
  }

  function mapAirportDotStyle(ap) {
    const opp = airportOpportunityScore(ap);
    const selected = selectedAirport === ap.iata;
    return {
      ...opp,
      radius: mapDotRadius(opp.size),
      stroke: selected ? '#fff' : opp.owned ? '#042018' : 'rgba(255,255,255,0.5)',
      strokeWidth: selected ? 2.2 : 1.2,
      title: `${ap.iata} · ${opp.label} · score ${opp.score}/100 — ${opp.tip}`,
    };
  }

  function buildAirportsGeoJSON() {
    const labelAll = isRegionalMapKey(activeMapKey);
    const airportFeatures = [];
    const haloFeatures = [];

    bootstrap.airports.forEach((ap) => {
      const owned = state && hasGateAt(ap.iata);
      const selected = selectedAirport === ap.iata;
      const share = playerShareAtAirport(ap.iata);
      const util = owned && state ? gateUtilizationAt(ap.iata) : null;
      const style = mapAirportDotStyle(ap);
      const r = style.radius;
      const capLabel = util ? `${Math.round(util.pct)}%` : '';
      const capSub = util && util.remaining > 0 ? `${util.remaining}o` : '';

      if (share > 0.08) {
        haloFeatures.push({
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [ap.lon, ap.lat] },
          properties: {
            haloRadius: r + 3 + share * 8,
            haloOpacity: 0.15 + share * 0.45,
          },
        });
      }

      airportFeatures.push({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [ap.lon, ap.lat] },
        properties: {
          iata: ap.iata,
          radius: r,
          fill: style.fill,
          stroke: style.stroke,
          strokeWidth: style.strokeWidth,
          showLabel: owned || selected || labelAll || style.tier === 'gold',
          showCapBadge: !!owned && !!util,
          capLabel,
          capSub,
          gateUtilPct: util ? util.pct : 0,
          gateRemaining: util ? util.remaining : 0,
          oppScore: style.score,
          oppTier: style.tier,
          oppLabel: style.label,
          tip: style.title,
        },
      });
    });

    return { airportFeatures, haloFeatures };
  }

  function drawMapbox() {
    if (!mapboxMap) {
      initMapbox();
      return;
    }
    if (!mapboxReady) return;

    const { airportFeatures, haloFeatures } = buildAirportsGeoJSON();
    mapboxMap.getSource('airports').setData({
      type: 'FeatureCollection',
      features: airportFeatures,
    });
    mapboxMap.getSource('airport-halos').setData({
      type: 'FeatureCollection',
      features: haloFeatures,
    });

    if (state) {
      mapboxMap.getSource('player-routes').setData(buildRoutesGeoJSON(state.routes, true));
      mapboxMap
        .getSource('competitor-routes')
        .setData(buildRoutesGeoJSON(state.competitor_routes, false));
    }
  }

  function clampMapView() {
    const aspect = MAP_H / MAP_W;
    mapView.w = Math.min(MAP_ZOOM_MAX_W, Math.max(MAP_ZOOM_MIN_W, mapView.w));
    mapView.h = mapView.w * aspect;
    mapView.x = Math.max(0, Math.min(MAP_W - mapView.w, mapView.x));
    mapView.y = Math.max(0, Math.min(MAP_H - mapView.h, mapView.y));
  }

  function applyMapView() {
    const svg = document.querySelector('#runway-map svg.map-fallback');
    if (!svg) return;
    svg.setAttribute(
      'viewBox',
      `${mapView.x} ${mapView.y} ${mapView.w} ${mapView.h}`
    );
  }

  function zoomMapAt(factor, clientX, clientY) {
    const svg = document.querySelector('#runway-map svg.map-fallback');
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    if (!rect.width || !rect.height) return;

    const mx = ((clientX - rect.left) / rect.width) * mapView.w + mapView.x;
    const my = ((clientY - rect.top) / rect.height) * mapView.h + mapView.y;

    const aspect = MAP_H / MAP_W;
    let newW = mapView.w * factor;
    newW = Math.min(MAP_ZOOM_MAX_W, Math.max(MAP_ZOOM_MIN_W, newW));
    const newH = newW * aspect;

    mapView.x = mx - ((mx - mapView.x) * newW) / mapView.w;
    mapView.y = my - ((my - mapView.y) * newH) / mapView.h;
    mapView.w = newW;
    mapView.h = newH;
    clampMapView();
    applyMapView();
  }

  function setupMapControls() {
    const wrap = document.querySelector('.map-wrap');
    if (!wrap || wrap.dataset.mapControlsInit) return;
    wrap.dataset.mapControlsInit = '1';

    const zoomIn = $('map-zoom-in');
    const zoomOut = $('map-zoom-out');
    const zoomReset = $('map-zoom-reset');

    if (useMapbox()) {
      if (zoomIn) {
        zoomIn.addEventListener('click', () => {
          if (mapboxMap) mapboxMap.zoomIn({ duration: 200 });
        });
      }
      if (zoomOut) {
        zoomOut.addEventListener('click', () => {
          if (mapboxMap) mapboxMap.zoomOut({ duration: 200 });
        });
      }
      if (zoomReset) zoomReset.addEventListener('click', resetMapView);
      return;
    }

    if (zoomIn) {
      zoomIn.addEventListener('click', () => {
        const svg = wrap.querySelector('svg.map-fallback');
        if (!svg) return;
        const r = svg.getBoundingClientRect();
        zoomMapAt(0.82, r.left + r.width / 2, r.top + r.height / 2);
      });
    }
    if (zoomOut) {
      zoomOut.addEventListener('click', () => {
        const svg = wrap.querySelector('svg.map-fallback');
        if (!svg) return;
        const r = svg.getBoundingClientRect();
        zoomMapAt(1.22, r.left + r.width / 2, r.top + r.height / 2);
      });
    }
    if (zoomReset) zoomReset.addEventListener('click', resetMapView);
  }

  function setupSvgMapInteraction() {
    const wrap = document.querySelector('.map-wrap');
    const svg = wrap && wrap.querySelector('svg.map-fallback');
    if (!wrap || !svg || wrap.dataset.svgPanInit) return;
    wrap.dataset.svgPanInit = '1';

    const endDrag = (e) => {
      if (!mapDrag.active) return;
      if (mapDrag.pointerId != null && wrap.hasPointerCapture(mapDrag.pointerId)) {
        wrap.releasePointerCapture(mapDrag.pointerId);
      }
      if (!mapDrag.moved) {
        if (mapDrag.clickRouteId) selectMapRoute(mapDrag.clickRouteId);
        else if (mapDrag.clickIata) selectAirport(mapDrag.clickIata);
      }
      mapDrag.active = false;
      mapDrag.pointerId = null;
      mapDrag.clickRouteId = null;
      wrap.classList.remove('dragging');
    };

    const onPointerDown = (e) => {
      if (e.button !== 0) return;
      if (e.target.closest && e.target.closest('.map-controls')) return;
      mapDrag.active = true;
      mapDrag.moved = false;
      mapDrag.startX = e.clientX;
      mapDrag.startY = e.clientY;
      mapDrag.viewX = mapView.x;
      mapDrag.viewY = mapView.y;
      mapDrag.pointerId = e.pointerId;
      const routeEl =
        (e.target.closest &&
          (e.target.closest('.map-route-hit') || e.target.closest('.map-route-line'))) ||
        null;
      const dot =
        (e.target.closest && (e.target.closest('.ap-dot-hit') || e.target.closest('.ap-dot'))) || null;
      mapDrag.clickRouteId = routeEl ? routeEl.getAttribute('data-route-id') : null;
      mapDrag.clickIata = !mapDrag.clickRouteId && dot ? dot.dataset.iata : null;
      wrap.setPointerCapture(e.pointerId);
      wrap.classList.add('dragging');
      e.preventDefault();
    };

    const onPointerMove = (e) => {
      if (!mapDrag.active || e.pointerId !== mapDrag.pointerId) return;
      const dx = e.clientX - mapDrag.startX;
      const dy = e.clientY - mapDrag.startY;
      if (Math.abs(dx) > 4 || Math.abs(dy) > 4) mapDrag.moved = true;
      if (!mapDrag.moved) return;

      const rect = svg.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      mapView.x = mapDrag.viewX - (dx / rect.width) * mapView.w;
      mapView.y = mapDrag.viewY - (dy / rect.height) * mapView.h;
      clampMapView();
      applyMapView();
      e.preventDefault();
    };

    wrap.addEventListener('pointerdown', onPointerDown);
    wrap.addEventListener('pointermove', onPointerMove);
    wrap.addEventListener('pointerup', endDrag);
    wrap.addEventListener('pointercancel', endDrag);

    wrap.addEventListener(
      'wheel',
      (e) => {
        e.preventDefault();
        zoomMapAt(e.deltaY > 0 ? 1.1 : 0.9, e.clientX, e.clientY);
      },
      { passive: false }
    );
  }

  function setupMapInteraction() {
    setupMapControls();
  }

  function mapBounds() {
    const cfg = getActiveMapConfig();
    if (cfg && cfg.bounds) return cfg.bounds;
    return { lonMin: -125.5, lonMax: -66.0, latMin: 24.0, latMax: 49.55 };
  }

  function mapPadding() {
    const cfg = getActiveMapConfig();
    if (!cfg) return { left: 20, top: 40, right: 20, bottom: 4 };
    if (cfg.padding) return cfg.padding;
    return { left: 0, top: 0, right: 0, bottom: 0 };
  }

  function projectMap(lat, lon) {
    const b = mapBounds();
    const pad = mapPadding();
    const left = pad.left || 0;
    const top = pad.top || 0;
    const right = pad.right || 0;
    const bottom = pad.bottom || 0;
    const uw = MAP_W - left - right;
    const uh = MAP_H - top - bottom;
    return {
      x: left + ((lon - b.lonMin) / (b.lonMax - b.lonMin)) * uw,
      y: top + ((b.latMax - lat) / (b.latMax - b.latMin)) * uh,
    };
  }

  function drawMapSvg() {
    const container = $('runway-map');
    if (!container) return;
    const cfg = getActiveMapConfig();
    const mapSrc = cfg ? cfg.src : '/static/runway/us-map-styled.png';

    let svg = container.querySelector('svg.map-fallback');
    if (!svg) {
      container.innerHTML = '';
      svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('id', 'runway-map-svg');
      svg.classList.add('map-fallback');
      svg.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
      container.appendChild(svg);
    }

    let html = `
      <image class="map-raster" href="${mapSrc}" x="0" y="0" width="${MAP_W}" height="${MAP_H}" preserveAspectRatio="none"/>
      <rect class="map-pan-surface" x="0" y="0" width="${MAP_W}" height="${MAP_H}" fill="transparent"/>
    `;

    if (state && state.competitor_routes && state.competitor_routes.length) {
      html += '<g class="map-competitor-routes">';
      state.competitor_routes.forEach((route) => {
        const o = airport(route.origin);
        const d = airport(route.dest);
        if (!o || !d) return;
        const p1 = projectMap(o.lat, o.lon);
        const p2 = projectMap(d.lat, d.lon);
        html += `<line x1="${p1.x}" y1="${p1.y}" x2="${p2.x}" y2="${p2.y}" stroke="#ff7b5a" stroke-width="1.2" opacity="0.35" stroke-dasharray="6 4" stroke-linecap="round"/>`;
      });
      html += '</g>';
    }

    if (state && state.routes) {
      html += '<g class="map-routes">';
      state.routes.forEach((route) => {
        const o = airport(route.origin);
        const d = airport(route.dest);
        if (!o || !d) return;
        const p1 = projectMap(o.lat, o.lon);
        const p2 = projectMap(d.lat, d.lon);
        const style = routeMapStyle(route);
        // Invisible fat stroke for easier clicks
        html += `<line class="map-route-hit" data-route-id="${route.id}" x1="${p1.x}" y1="${p1.y}" x2="${p2.x}" y2="${p2.y}" stroke="transparent" stroke-width="14" stroke-linecap="round" style="cursor:pointer"/>`;
        if (style.selected) {
          html += `<line x1="${p1.x}" y1="${p1.y}" x2="${p2.x}" y2="${p2.y}" stroke="${style.color}" stroke-width="9" opacity="0.3" stroke-linecap="round"/>`;
        }
        html += `<line class="map-route-line" data-route-id="${route.id}" x1="${p1.x}" y1="${p1.y}" x2="${p2.x}" y2="${p2.y}" stroke="${style.color}" stroke-width="${style.width}" opacity="${style.opacity}" stroke-linecap="round" style="cursor:pointer"><title>${String(style.tip).replace(/"/g, "'")}</title></line>`;
      });
      html += '</g>';
    }

    const labelAll = isRegionalMapKey(activeMapKey);
    html += '<g class="map-airports">';
    bootstrap.airports.forEach((ap) => {
      const p = projectMap(ap.lat, ap.lon);
      const owned = state && hasGateAt(ap.iata);
      const selected = selectedAirport === ap.iata;
      const share = playerShareAtAirport(ap.iata);
      const util = owned && state ? gateUtilizationAt(ap.iata) : null;
      const style = mapAirportDotStyle(ap);
      const r = style.radius;
      const fill = style.fill;
      const stroke = style.stroke;
      if (share > 0.08) {
        const halo = r + 3 + share * 8;
        html += `<circle cx="${p.x}" cy="${p.y}" r="${halo}" fill="none" stroke="rgba(0,228,168,${0.15 + share * 0.45})" stroke-width="2" class="ap-share-ring"/>`;
      }
      if (isCoarsePointer()) {
        html += `<circle cx="${p.x}" cy="${p.y}" r="${Math.max(18, r + 10)}" fill="transparent" class="ap-dot-hit" data-iata="${ap.iata}"/>`;
      }
      html += `<circle cx="${p.x}" cy="${p.y}" r="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${style.strokeWidth}" class="ap-dot" data-iata="${ap.iata}" style="cursor:pointer"><title>${style.title.replace(/"/g, "'")}</title></circle>`;
      if (owned && util) {
        const capClass = util.pct < 50 ? 'low' : '';
        html += `<text x="${p.x}" y="${p.y - 10}" text-anchor="middle" class="map-cap-badge ${capClass}">${Math.round(util.pct)}%</text>`;
        if (util.remaining > 0) {
          html += `<text x="${p.x}" y="${p.y - 18}" text-anchor="middle" class="map-cap-badge" fill="#a8c4e0" font-size="7">${util.remaining} open</text>`;
        }
      }
      if (owned || selected || labelAll || style.tier === 'gold') {
        html += `<text x="${p.x + 8}" y="${p.y + 4}" fill="#f0f8ff" font-size="${labelAll ? 11 : 10}" font-weight="700" style="paint-order:stroke;stroke:#041018;stroke-width:3px">${ap.iata}</text>`;
      }
    });
    html += '</g>';

    svg.setAttribute('width', '100%');
    svg.setAttribute('height', '100%');
    svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    svg.innerHTML = html;
    applyMapView();
    setupSvgMapInteraction();
  }

  function drawMap() {
    if (useMapbox()) {
      drawMapbox();
      return;
    }
    drawMapSvg();
  }

  function panelSectionHtml(sectionId, title, expanded, bodyHtml) {
    return `
      <div class="panel-card" id="ap-section-${sectionId}">
        <button type="button" class="panel-section-toggle" data-airport-section="${sectionId}" aria-expanded="${expanded}">
          <span>${title}</span>
          <span class="chevron" aria-hidden="true">▾</span>
        </button>
        <div class="panel-section-body${expanded ? '' : ' collapsed'}">${bodyHtml}</div>
      </div>`;
  }

  function bindAirportPanelToggles() {
    document.querySelectorAll('[data-airport-section]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const key = btn.dataset.airportSection;
        airportSections[key] = !airportSections[key];
        if (selectedAirport) renderAirportPanel(selectedAirport);
      });
    });
  }

  function applyAirportContext(iata) {
    const ap = airport(iata);
    if (!ap || !state) return;
    const gate = state.gates.find((g) => g.airport === iata);
    const hasCompetition =
      (ap.incumbents && ap.incumbents.length) || competitorRoutesAt(iata).length > 0;

    // Always land on gate / your position — not Routes. Scout first, then act.
    // If a gate is already leased here, there's nothing actionable to show by default —
    // collapse to a one-line summary. If there's no gate yet, keep it open since leasing
    // one is the next required step.
    airportSections = {
      market: false,
      competition: false,
      position: !gate,
    };
    if (gate && hasCompetition) {
      // Optional: show competition collapsed closed; position stays open.
      airportSections.competition = false;
    }

    // Do not switch tabs away from where the player is — keep airport panel focused.
    scheduleContextPulse('#ap-section-position', true);
  }

  function scheduleContextPulse(selector, scrollParent) {
    if (contextPulseTimer) clearTimeout(contextPulseTimer);
    requestAnimationFrame(() => {
      const el = document.querySelector(selector);
      if (!el) return;
      if (scrollParent) scrollSidePanelTo(el, { block: 'nearest' });
      el.classList.remove('context-pulse');
      void el.offsetWidth;
      el.classList.add('context-pulse');
      contextPulseTimer = setTimeout(() => el.classList.remove('context-pulse'), 2400);
    });
  }

  function setupHudLoadClick() {
    const pill = $('hud-pill-load');
    if (!pill || pill._loadClick) return;
    pill._loadClick = true;
    pill.style.cursor = 'pointer';
    pill.title = 'Click: open Routes — fares, frequency, and marketing drive load';
    pill.addEventListener('click', () => focusLoadLevers());
  }

  function toggleHudPanel(name) {
    if (!hudPanels.hasOwnProperty(name)) return;
    hudPanels[name] = !hudPanels[name];
    const panel = $(`hud-panel-${name}`);
    const btn = $(`hud-toggle-${name}`);
    if (panel) panel.classList.toggle('open', hudPanels[name]);
    if (btn) {
      btn.classList.toggle('open', hudPanels[name]);
      btn.setAttribute('aria-expanded', hudPanels[name] ? 'true' : 'false');
    }
    if (name === 'financials' && hudPanels.financials) {
      renderFinancialsPanel();
      hudPanels.economy = false;
      const ecoPanel = $('hud-panel-economy');
      const ecoBtn = $('hud-toggle-economy');
      if (ecoPanel) ecoPanel.classList.remove('open');
      if (ecoBtn) {
        ecoBtn.classList.remove('open');
        ecoBtn.setAttribute('aria-expanded', 'false');
      }
    }
    if (name === 'economy' && hudPanels.economy) {
      hudPanels.financials = false;
      const finPanel = $('hud-panel-financials');
      const finBtn = $('hud-toggle-financials');
      if (finPanel) finPanel.classList.remove('open');
      if (finBtn) {
        finBtn.classList.remove('open');
        finBtn.setAttribute('aria-expanded', 'false');
      }
    }
  }

  function toggleFleetShop(force) {
    fleetShopOpen = typeof force === 'boolean' ? force : !fleetShopOpen;
    renderFleet();
  }

  function renderAirportEmpty() {
    const panel = $('airport-panel');
    if (!panel) return;
    panel.innerHTML =
      '<p class="airport-empty muted">Click an airport on the map to scout <b>markets</b>, <b>competitors</b>, and <b>gates</b>.</p>';
  }

  function selectAirport(iata) {
    const prev = selectedAirport;
    selectedAirport = iata;
    const ap = airport(iata);
    if (prev !== iata) {
      routeFormDraft = {
        ...(routeFormDraft || captureRouteFormDraft()),
        origin: iata,
        originLabel: ap ? airportLabel(ap) : iata,
        dest: '',
        destLabel: '',
      };
    }
    applyAirportContext(iata);
    renderAirportPanel(iata);
    drawMap();
    // Stay on airport scout — scroll to gate / position, not the Routes tab.
    const apPanel = $('airport-panel');
    if (apPanel) scrollSidePanelTo(apPanel, { block: 'nearest' });
    requestAnimationFrame(() => {
      const pos = document.querySelector('#ap-section-position');
      if (pos) scrollSidePanelTo(pos, { block: 'nearest' });
    });
  }

  /** Avg load HUD → Routes (fares, frequency, marketing on cards). */
  function focusLoadLevers() {
    if (!state) return;
    switchTab('routes');
    renderRoutes();
    const panel = $('panel-routes') || $('tab-routes');
    if (panel) scrollSidePanelTo(panel, { block: 'nearest' });
    scheduleContextPulse('#tab-routes .route-card, #panel-routes .route-card', true);
    const first = document.querySelector('#tab-routes .route-card, #panel-routes .route-card');
    if (first) {
      first.classList.add('context-pulse');
      setTimeout(() => first.classList.remove('context-pulse'), 2400);
    }
    pushEvent(
      'Load levers: fares, frequency, and marketing on <b>Routes</b>. Thin loads also cancel flights — keep both legs of a pair flying.',
      'neutral'
    );
  }

  function renderAirportPanel(iata) {
    const ap = airport(iata);
    const panel = $('airport-panel');
    if (!ap || !panel) return;
    const myGates = state.gates.filter((g) => g.airport === iata);
    const gate = myGates[0];
    const compRoutes = competitorRoutesAt(iata);

    const apMarketDaily = airportMarketDeparturesDaily(ap);
    const apMarketWeekly = totalMarketDeparturesWeeklyAt(iata);
    const playerDeps = playerDeparturesWeeklyFrom(iata, null, 0);
    const playerDaily = playerDeps / (ap.operating_days_per_week || 6);
    const playerShare = formatMarketSharePct(playerDeps / Math.max(1, apMarketWeekly));
    const marketBody = `
      <dl class="stat-dl">
        <dt>Market departures</dt><dd>~${apMarketDaily}/day · ${apMarketWeekly}/wk</dd>
        <dt>Your departures</dt><dd>${playerDaily.toFixed(1)}/day · ${playerDeps}/wk <span class="muted">(${playerShare})</span></dd>
        <dt>Wealth index</dt><dd>${(airportWealth(ap) * 100).toFixed(0)}</dd>
        <dt>Metro pop</dt><dd>${ap.metro_pop_m}M</dd>
        <dt>Top carrier</dt><dd>${ap.hub_airline || '—'} (${(ap.hub_strength * 100).toFixed(0)}%)</dd>
        <dt>Gates open</dt><dd>${ap.gates_available} of ${ap.gates_total}</dd>
      </dl>
      <p class="muted" style="font-size:0.72rem;margin-top:6px;">Annual pax ${ap.annual_pax_m}M · Luxury ${(airportLuxury(ap) * 100).toFixed(0)}% · Slots ${ap.slot_controlled ? 'controlled' : 'open'} · Gate slots ≠ total airport traffic</p>`;

    let competitionBody = '';
    if (ap.incumbents && ap.incumbents.length) {
      competitionBody += `<ul class="list incumbent-list">${ap.incumbents
        .map(
          (c) =>
            `<li><strong>${c.airline}</strong> <span class="muted">${(c.share * 100).toFixed(0)}% · ${c.tier}</span><br>${formatIncumbentIntel(ap, c)}</li>`
        )
        .join('')}</ul>`;
    } else {
      competitionBody += '<p class="muted">No major scheduled incumbents — thin or GA market.</p>';
    }
    if (compRoutes.length) {
      competitionBody += `<p class="muted" style="font-size:0.72rem;margin:8px 0 4px;color:#ff9b7a;">Competitor routes</p>
        <ul class="list incumbent-list">${compRoutes
          .map(
            (cr) =>
              `<li><strong>${cr.airline}</strong> ${cr.origin}–${cr.dest} <span class="muted">${cr.frequency_week}x/wk · $${cr.fare}</span></li>`
          )
          .join('')}</ul>`;
    }
    const apPressure = airportCompetitivePressure(iata);
    const pressureBlock = competitivePressureHtml(apPressure);
    competitionBody = pressureBlock + competitionBody;

    const gateSummary = myGates.length
      ? `${myGates.length} gate${myGates.length > 1 ? 's' : ''} · ${myGates.map((g) => `${g.tier} $${g.monthly.toLocaleString()}/mo`).join(' · ')}`
      : '<span class="danger">None — lease below</span>';
    const util = myGates.length ? gateUtilizationAt(iata) : null;
    const capPrompt = util ? gateUtilizationPromptHtml(util, { title: `${iata} — your gate`, showScout: false }) : '';
    const availCtx = myGates.length
      ? routeAvailabilityContext(iata, null, state.fleet[0]?.id, 0)
      : null;
    const availFromHub = availCtx
      ? availabilityPanelHtml(availCtx, { title: `${iata} — your capacity` })
      : '';
    const hubIdeas = myGates.length
      ? routeSuggestionsFrom(iata)
          .map((s) => enrichRouteSuggestion(iata, s))
          .filter((s) => s.canLaunch)
          .slice(0, 4)
      : [];
    const hubRoutesHtml = hubIdeas.length
      ? `<p class="muted" style="font-size:0.68rem;margin:8px 0 4px;color:var(--gold);">Can launch now from ${iata} <span class="muted">(out % · return %)</span></p>
        <div class="avail-chips">${hubIdeas
          .map((s) => {
            const outPct = Math.round((s.outLoad != null ? s.outLoad : s.load) * 100);
            const retPct = Math.round((s.retLoad != null ? s.retLoad : s.load) * 100);
            return `<button type="button" class="avail-chip" data-hub-route="${iata}" data-hub-dest="${s.dest}" data-hub-freq="${s.maxFreq || s.freq}" data-hub-ac="${s.bestPlaneId || ''}" title="${(s.directionPrompt || '').replace(/"/g, "'")}">${iata}⇄${s.dest} · ${s.maxFreq || s.freq}/wk · ${outPct}%/${retPct}%</button>`;
          })
          .join('')}</div>`
      : myGates.length
        ? `<p class="muted" style="font-size:0.68rem;margin:8px 0;">No new routes fit gate + aircraft hours from ${iata} — bump frequency or lease another plane.</p>`
        : '';
    const routesFromList =
      util && util.routesFrom.length
        ? `<p class="muted" style="font-size:0.68rem;margin-top:6px;">Routes from ${iata}: ${util.routesFrom
            .map((r) => `${r.origin}–${r.dest} ${r.frequency_week}/wk`)
            .join(' · ')}</p>`
        : util && myGates.length
          ? `<p class="muted" style="font-size:0.68rem;margin-top:6px;">No departures scheduled from ${iata} yet.</p>`
          : '';
    const canLeaseMore = ap.gates_available > 0;
    const positionBody = `
      <div class="ap-gate-hero ${gate ? 'has-gate' : 'no-gate'}">
        <p style="margin:0 0 6px;font-size:0.88rem;line-height:1.4;">
          ${
            gate
              ? `<b class="via-good">You have a gate</b> at ${iata} — ${gateSummary}`
              : `<b class="danger">No gate yet</b> at ${iata}. Lease one to originate flights from here.`
          }
        </p>
        <p class="muted" style="margin:0;font-size:0.72rem;">Brand awareness ${(state.brand_awareness[iata] || 0).toFixed(0)}%${
          routesFromList ? '' : ''
        }</p>
        ${routesFromList || ''}
        ${gateCapacityExplainHtml(iata)}
      </div>
      ${
        canLeaseMore
          ? `<div class="btn-row" style="margin-top:8px;">
        <button type="button" class="btn" onclick="Runway.leaseGate('${iata}','common',3)">${gate ? 'Add ' : ''}Common-use (3yr)</button>
        <button type="button" class="btn secondary" onclick="Runway.leaseGate('${iata}','exclusive',5)">${gate ? 'Add ' : ''}Exclusive (5yr)</button>
      </div>
      <p class="muted" style="font-size:0.68rem;margin-top:6px;">${ap.gates_available} open slot${ap.gates_available !== 1 ? 's' : ''} · 2-month deposit</p>`
          : gate
            ? '<p class="muted" style="font-size:0.68rem;margin-top:6px;">No additional gate slots here.</p>'
            : '<p class="muted" style="font-size:0.68rem;margin-top:6px;">Airport full — no gates available.</p>'
      }
      ${capPrompt}
      <details class="ap-more" style="margin-top:10px;">
        <summary class="muted" style="cursor:pointer;font-size:0.75rem;">Capacity &amp; route ideas</summary>
        ${availFromHub}
        ${hubRoutesHtml}
      </details>
      <details class="ap-more" style="margin-top:8px;">
        <summary class="muted" style="cursor:pointer;font-size:0.75rem;">Marketing at ${iata}</summary>
        ${renderMarketingPanelHtml(iata)}
      </details>`;

    const positionTitle = gate ? `Your gate — ${gateSummary}` : 'Lease a gate';
    const opp = airportOpportunityScore(ap);
    const oppBanner = `<div class="ap-opp-banner tier-${opp.tier}" title="${(opp.tip || '').replace(/"/g, "'")}">
      <span class="ap-opp-dot" style="background:${opp.fill}"></span>
      <div>
        <strong>${opp.label}</strong> · score ${opp.score}/100
        <span class="muted" style="display:block;font-size:0.68rem;margin-top:2px;">${opp.tip}</span>
        <span class="muted" style="display:block;font-size:0.64rem;margin-top:2px;">Underserved ${(opp.underserved * 100).toFixed(0)}% · fare opp ${(opp.fareOpp * 100).toFixed(0)}% · size = market scale</span>
      </div>
    </div>`;
    panel.innerHTML = `
      <h3>${ap.iata} — ${ap.city}${ap.regional ? '<span class="badge-regional">Regional</span>' : ''}</h3>
      <p class="muted" style="font-size:0.75rem;margin-bottom:8px;">${ap.name}${ap.state ? ` · ${ap.state}` : ''}</p>
      ${oppBanner}
      ${panelSectionHtml('position', positionTitle, airportSections.position, positionBody)}
      ${panelSectionHtml('competition', 'Competition', airportSections.competition, competitionBody)}
      ${panelSectionHtml('market', 'Market snapshot', airportSections.market, marketBody)}
    `;
    bindAirportPanelToggles();
    bindGateCapacityActions(panel);
    bindAvailabilityActions(panel);
    panel.querySelectorAll('[data-hub-route]').forEach((btn) => {
      if (btn._hubRouteBound) return;
      btn._hubRouteBound = true;
      btn.addEventListener('click', () => {
        focusHubForRoutes(btn.dataset.hubRoute);
        const dAp = airport(btn.dataset.hubDest);
        if (!dAp) return;
        const oApHub = airport(btn.dataset.hubRoute);
        setRouteFormDraft({
          origin: btn.dataset.hubRoute,
          originLabel: oApHub ? airportLabel(oApHub) : btn.dataset.hubRoute,
          dest: btn.dataset.hubDest,
          destLabel: airportLabel(dAp),
          aircraftId: btn.dataset.hubAc || '',
          freq: btn.dataset.hubFreq || '7',
        });
        renderRoutes({ forceForm: true });
      });
    });
  }

  function setText(id, text) {
    const el = $(id);
    if (el) el.textContent = text;
  }

  function setStatPillTone(pillId, tone) {
    const pill = $(pillId);
    if (!pill) return;
    pill.classList.remove('stat-pill-warn', 'stat-pill-danger', 'stat-pill-good');
    if (tone) pill.classList.add(`stat-pill-${tone}`);
  }

  function applyRouteLabBranding() {
    const rb = bootstrap && bootstrap.routelab ? bootstrap.routelab : {};
    const name = rb.name || 'Route Lab';
    const tagline = rb.tagline || 'Airline network economics — routes, gates, rivals, and capital.';
    document.title = `${name} · Airline Simulation`;
    setText('start-brand-name', name);
    setText('start-brand-tagline', tagline);
    const logo = $('start-brand-logo');
    if (logo && rb.logo_url) {
      logo.src = rb.logo_url;
      logo.alt = `${name} logo`;
    }
  }

  function scenarioDifficultyMeta(sc) {
    if (!sc) return { label: 'Custom', tone: 'mid' };
    if (sc.tutorial) return { label: 'Guided tutorial', tone: 'guided' };
    if ((sc.debt || []).length || sc.financing_tier === 'distressed') return { label: 'Turnaround', tone: 'hard' };
    if ((sc.cash || 0) >= 20_000_000) return { label: 'Well-funded', tone: 'easy' };
    if ((sc.cash || 0) < 1_000_000) return { label: 'Lean startup', tone: 'hard' };
    return { label: 'Regional build', tone: 'mid' };
  }

  function scenarioStartingChips(sc) {
    if (!sc) return [];
    const fleet = (sc.fleet || []).length;
    const gates = (sc.gates || []).length;
    const routes = (sc.routes || []).length;
    return [
      fmtMoney(sc.cash || 0),
      fleet ? `${fleet} aircraft` : 'No aircraft',
      gates ? `${gates} gate${gates !== 1 ? 's' : ''}` : 'No gates',
      routes ? `${routes} route${routes !== 1 ? 's' : ''}` : 'No routes',
    ];
  }

  function scenarioSnapshotHtml(sc) {
    if (!sc) return '';
    const diff = scenarioDifficultyMeta(sc);
    const chips = scenarioStartingChips(sc)
      .map((c) => `<span class="scenario-chip">${c}</span>`)
      .join('');
    const debt =
      (sc.debt || []).length > 0
        ? `<p class="muted" style="font-size:0.74rem;margin-top:8px;">Debt: ${sc.debt
            .map((d) => `${d.name} ${fmtMoney(d.principal)}`)
            .join(' · ')}</p>`
        : '';
    const goalLine = sc.goal ? `<span class="scenario-goal">Goal: ${sc.goal.label}</span>` : '';
    return `<div class="scenario-snapshot">
      <span class="scenario-diff ${diff.tone}">${diff.label}</span>
      ${goalLine}
      <div class="scenario-card-meta">${chips}</div>
      ${debt}
    </div>`;
  }

  function routeDailyPnls() {
    return (state.routes || []).map((route) => {
      const r = simulateRouteDay(route);
      return {
        route,
        pnl: r.revenue - r.cost,
        load: r.grounded ? 0 : r.load,
        revenue: r.revenue,
        cost: r.cost,
        grounded: r.grounded,
      };
    });
  }


  /**
   * Structural health of a single route — why it loses money and what to do.
   * Used by route cards, ops coach, and monthly ops review.
   */
  function diagnoseRouteHealth(route) {
    if (!route || !state) return null;
    const r = simulateRouteDay(route);
    const pnl = (r.revenue || 0) - (r.cost || 0);
    const pressure = routeCompetitivePressure(route);
    const mkt = r.market || routeMarketContext(route);
    const hasRet = !!hasReturnLeg(route);
    const reasons = [];
    const fixes = [];
    let severity = 'ok';

    if (r.grounded) {
      return {
        severity: 'critical',
        title: 'Aircraft grounded (AOG)',
        reasons: ['This metal is not flying — fix maintenance / AOG in Fleet.'],
        fixes: [{ label: 'Open Fleet', effect: 'tab', tab: 'fleet' }],
        pnl,
        load: r.load,
        pressure,
        route,
      };
    }

    if (pnl < -1200) {
      severity = 'critical';
      reasons.push(`Losing <b>${fmtMoney(Math.abs(pnl))}/day</b> on variable ops (before gate/lease overhead)`);
    } else if (pnl < 0) {
      severity = 'watch';
      reasons.push(`Negative route P&L · <b>${fmtMoney(pnl)}/day</b>`);
    } else if (pnl > 800) {
      reasons.push(`Cash engine · <b>+${fmtMoney(pnl)}/day</b>`);
    }

    if (!r.canceled && r.load != null && r.load < 0.38) {
      reasons.push(`Thin load <b>${(r.load * 100).toFixed(0)}%</b> — not enough passengers for this capacity`);
      fixes.push({ label: `Review ${route.origin}–${route.dest}`, effect: 'route_review', routeId: route.id });
      if (severity === 'ok') severity = 'watch';
    }

    if (!r.canceled && r.load != null && r.load >= 0.72 && pnl < 0) {
      reasons.push(
        '<b>Structurally weak:</b> planes are full but still lose money — fare too low or aircraft too costly for this stage'
      );
      fixes.push({ label: 'Raise fare / change metal', effect: 'route_review', routeId: route.id });
      severity = 'critical';
    }

    if (mkt && (mkt.captureFactor || 0) < 0.08) {
      reasons.push(
        `Tiny demand capture (<b>${formatMarketSharePct(mkt.captureFactor || 0)}</b>) — speck of airport traffic`
      );
      fixes.push({ label: 'Add frequency or ads', effect: 'route_review', routeId: route.id });
      if (severity === 'ok') severity = 'watch';
    }

    if (pressure && pressure.score >= 55) {
      reasons.push(`High competitive pressure <b>${pressure.score}/100</b> — ${pressure.tip}`);
      if (severity === 'ok') severity = 'watch';
    }

    if (!hasRet) {
      reasons.push('No return leg — empty ferry home burns fuel and block hours');
      fixes.push({ label: 'Open Routes', effect: 'tab', tab: 'routes' });
      if (severity === 'ok') severity = 'watch';
    }

    if (r.schedScale != null && r.schedScale < 0.85) {
      reasons.push(
        `Aircraft overscheduled — only ~<b>${Math.round(r.schedScale * 100)}%</b> of planned flights can operate`
      );
      fixes.push({ label: 'Open Fleet', effect: 'tab', tab: 'fleet' });
      if (severity === 'ok') severity = 'watch';
    }

    if (r.canceled) {
      reasons.push('Flights scrubbed for thin load — cash-safe but not building the market');
      if (severity === 'ok') severity = 'watch';
    }

    let title = 'Healthy route';
    if (severity === 'critical') title = 'Structurally weak';
    else if (severity === 'watch') title = 'Needs attention';
    else if (pnl > 800) title = 'Cash engine';

    if (!fixes.length) {
      fixes.push({ label: `Review ${route.origin}–${route.dest}`, effect: 'route_review', routeId: route.id });
    }

    return { severity, title, reasons, fixes, pnl, load: r.load, pressure, route };
  }

  function diagnoseNetworkRoutes() {
    return (state.routes || [])
      .map((route) => diagnoseRouteHealth(route))
      .filter(Boolean)
      .sort((a, b) => {
        const rank = { critical: 0, watch: 1, ok: 2 };
        return (rank[a.severity] ?? 3) - (rank[b.severity] ?? 3) || a.pnl - b.pnl;
      });
  }

  function mainHubIata() {
    if (!state || !(state.gates || []).length) return null;
    const counts = {};
    (state.routes || []).forEach((r) => {
      counts[r.origin] = (counts[r.origin] || 0) + (r.frequency_week || 0);
    });
    let best = state.gates[0].airport;
    let bestN = -1;
    state.gates.forEach((g) => {
      const n = counts[g.airport] || 0;
      if (n > bestN) {
        bestN = n;
        best = g.airport;
      }
    });
    return best;
  }

  function playerHubDepartureShare(iata) {
    if (!iata || !state) return 0;
    let playerDeps = 0;
    (state.routes || []).forEach((r) => {
      if (r.origin === iata) playerDeps += r.frequency_week || 0;
    });
    const sample = (state.routes || []).find((r) => r.origin === iata);
    if (sample) {
      const ctx = routeMarketContext(sample);
      if (ctx && ctx.originMarketWeekly > 0) return playerDeps / ctx.originMarketWeekly;
    }
    const util = gateUtilizationAt(iata);
    if (util && util.max > 0) return Math.min(1, playerDeps / Math.max(util.max * 3, 28));
    return 0;
  }

  function midgameGoalProgress(goal) {
    if (!goal || !state) return { done: false, pct: 0, progress: '—' };
    if (goal.id === 'rt_pairs_2') {
      const pairs = new Set();
      (state.routes || []).forEach((r) => {
        if (hasReturnLeg(r)) {
          pairs.add([r.origin, r.dest].sort().join('-'));
        }
      });
      const n = pairs.size;
      return {
        done: n >= 2,
        pct: Math.min(100, (n / 2) * 100),
        progress: `${n} of 2 RT pairs (sell both directions)`,
      };
    }
    if (goal.id === 'ltm_25m') {
      const cur = state.ltm_revenue || 0;
      return {
        done: cur >= 25_000_000,
        pct: Math.min(100, (cur / 25_000_000) * 100),
        progress: `${fmtMoney(cur)} of ${fmtMoney(25_000_000)}`,
      };
    }
    if (goal.id === 'hub_presence') {
      const hub = mainHubIata();
      const share = playerHubDepartureShare(hub);
      return {
        done: share >= 0.08,
        pct: Math.min(100, (share / 0.08) * 100),
        progress: hub ? `${hub} · ${formatMarketSharePct(share)} of deps` : 'lease a hub first',
      };
    }
    if (goal.id === 'profit_month') {
      const trail = trailingMonthPnl();
      return {
        done: trail != null && trail > 0,
        pct: trail != null && trail > 0 ? 100 : 0,
        progress: trail == null ? 'collecting 30 days…' : `${fmtMoney(trail)} last 30 days`,
      };
    }
    if (goal.id === 'network_6') {
      const n = (state.routes || []).length;
      return { done: n >= 6, pct: Math.min(100, (n / 6) * 100), progress: `${n} of 6 routes` };
    }
    if (goal.id === 'pressure_win') {
      const win = (state.routes || []).some((route) => {
        const h = diagnoseRouteHealth(route);
        return h && h.severity === 'ok' && h.pnl > 200 && h.pressure && h.pressure.score >= 55;
      });
      return {
        done: !!win,
        pct: win ? 100 : 0,
        progress: win ? 'holding a green contested route' : 'need green P&L under pressure ≥55',
      };
    }
    if (goal.id === 'second_base_profit') {
      const byOrigin = {};
      (state.routes || []).forEach((route) => {
        const h = diagnoseRouteHealth(route);
        if (!h) return;
        byOrigin[route.origin] = (byOrigin[route.origin] || 0) + (h.pnl || 0);
      });
      const greenBases = Object.keys(byOrigin).filter((k) => byOrigin[k] > 150);
      const n = greenBases.length;
      return {
        done: n >= 2,
        pct: Math.min(100, (n / 2) * 100),
        progress:
          n >= 2
            ? `${greenBases.slice(0, 2).join(' + ')} cash-positive`
            : `${n}/2 bases with green day P&L`,
      };
    }
    if (goal.id === 'capital_event') {
      const done = !!(state.pe_done || state.ipo_done || (state.personal_cash || 0) > 50_000);
      return {
        done,
        pct: done ? 100 : state.series_a_done ? 40 : state.seed_done ? 15 : 0,
        progress: done
          ? 'capital event closed'
          : state.series_a_done
            ? 'Series A done — PE / secondary / IPO next'
            : 'raise when LTM and network support it',
      };
    }
    return { done: false, pct: 0, progress: '—' };
  }

  function activeMidgameOpsGoal() {
    if (!state) return null;
    const build = regionalBuildSteps();
    const buildProgress = build.filter((s) => s.done).length;
    if (buildProgress < 4 && (state.routes || []).length < 2) return null;

    state.ops_goals_done = state.ops_goals_done || [];
    for (let i = 0; i < OPS_MIDGAME_GOALS.length; i++) {
      const g = OPS_MIDGAME_GOALS[i];
      if (state.ops_goals_done.includes(g.id)) continue;
      const prog = midgameGoalProgress(g);
      if (prog.done) {
        state.ops_goals_done.push(g.id);
        pushEvent(`${g.phaseLabel || 'Ops'}: achieved <b>${g.label}</b>`, 'milestone');
        markMilestoneOnce(`ops_goal_${g.id}`, `${state.airline_name}: ${g.label}`);
        continue;
      }
      return { ...g, ...prog };
    }
    return null;
  }

  /** Single “what next” for coach, HUD, and session recap. */
  function nextObjectiveSnapshot() {
    if (!state) return null;
    if (state.game_over) {
      return {
        phase: 'Over',
        label: 'Game over',
        progress: state.paused_reason || 'Liquidated',
        pct: 100,
        tab: 'finance',
      };
    }
    const build = regionalBuildSteps();
    const doneN = build.filter((s) => s.done).length;
    const nextBuild = build.find((s) => !s.done);
    if (nextBuild && doneN < 6) {
      return {
        phase: 'Phase 1 · Build',
        label: nextBuild.label,
        progress: `${doneN}/${build.length} build steps`,
        pct: (doneN / build.length) * 100,
        tab: nextBuild.tab === 'map' ? 'routes' : nextBuild.tab,
        hint: 'Finish the regional build track first.',
      };
    }
    const g = activeMidgameOpsGoal();
    if (g) {
      return {
        phase: g.phaseLabel || 'Ops',
        label: g.label,
        progress: g.progress,
        pct: g.pct,
        tab: g.tab || 'routes',
        hint: g.hint,
      };
    }
    const runway = runwayMonths();
    if (runway < 4) {
      return {
        phase: 'Cash',
        label: 'Extend runway',
        progress: `${runway.toFixed(1)} mo cash left — cut burn or raise`,
        pct: Math.min(100, (runway / 6) * 100),
        tab: 'finance',
      };
    }
    return {
      phase: 'Free play',
      label: 'Grow or exit',
      progress: 'Track complete — scale, defend share, or take capital',
      pct: 100,
      tab: 'routes',
    };
  }

  function midgameOpsGoalHtml() {
    const obj = nextObjectiveSnapshot();
    if (!obj) return '';
    const hint = obj.hint ? ` <span class="muted">— ${obj.hint}</span>` : '';
    return `<p class="ops-midgame-line"><span class="ops-phase">${obj.phase}</span> · <b>${obj.label}</b> · ${obj.progress} <span class="muted">(${Math.round(obj.pct || 0)}%)</span>${hint}</p>`;
  }

  function maybeMonthlyOpsReview() {
    if (!state || state.game_over) return;
    if (activeDecision || decisionQueue.length) return;
    if ((state.routes || []).length < 1) return;
    if (state.last_ops_review_day && state.day - state.last_ops_review_day < 28) return;

    const diagnoses = diagnoseNetworkRoutes();
    const critical = diagnoses.filter((d) => d.severity === 'critical');
    const watch = diagnoses.filter((d) => d.severity === 'watch');
    if (!critical.length && watch.length < 2) return;

    state.last_ops_review_day = state.day;
    const worst = critical[0] || watch[0];
    if (!worst || !worst.route) return;

    const list = diagnoses
      .filter((d) => d.severity !== 'ok')
      .slice(0, 4)
      .map((d) => `<li><b>${d.route.origin}–${d.route.dest}</b> — ${d.title}: ${d.reasons[0] || ''}</li>`)
      .join('');

    const pubNote =
      state.public || state.ipo_done
        ? `<p class="muted" style="font-size:0.82rem;">As a <b>public</b> carrier, soft routes show up in the narrative — reputation can slip if you ignore them.</p>`
        : state.pe_done
          ? `<p class="muted" style="font-size:0.82rem;">Your <b>PE partners</b> watch route economics — clean up red ink or expect board pressure.</p>`
          : '';

    queueDecision({
      kicker: `${fmtDate(state.day)} · Monthly ops review`,
      title: critical.length
        ? `${critical.length} route${critical.length === 1 ? '' : 's'} structurally weak`
        : 'Network needs attention',
      body:
        `<p>Route-level diagnosis (variable P&L before gate/lease overhead):</p>` +
        `<ul style="margin:8px 0;padding-left:18px;font-size:0.85rem;line-height:1.45;">${list}</ul>${pubNote}` +
        `<p class="muted" style="font-size:0.82rem;">Fix fares, frequency, return legs, or metal — don't just open another thin market.</p>`,
      teach: 'Full planes that still lose money = structural. Thin loads = demand/share. No return = ferry tax.',
      logLine: `Ops review: ${critical.length} critical / ${watch.length} watch routes`,
      options: [
        {
          id: 'ops_fix_worst',
          label: `A — Fix ${worst.route.origin}–${worst.route.dest}`,
          hint: worst.title,
          effect: 'route_review',
          routeId: worst.route.id,
        },
        {
          id: 'ops_routes',
          label: 'B — Open Routes tab',
          hint: 'Review the whole network.',
          effect: 'tab_routes',
        },
        {
          id: 'ops_later',
          label: 'C — Note it and continue',
          hint: 'Coach will keep flagging red routes.',
          effect: 'none',
        },
      ],
    });
  }

  function maybePublicOrPePressure() {
    if (!state || state.game_over) return;
    if (!state.public && !state.pe_done) return;
    if (state.day % 30 !== 0) return;
    if (state.last_board_pressure_day === state.day) return;
    state.last_board_pressure_day = state.day;

    const trail = trailingMonthPnl();
    const critical = diagnoseNetworkRoutes().filter((d) => d.severity === 'critical');
    const burn = burnMonthly();
    const runway = burn > 0 ? state.cash / burn : 99;

    if (trail != null && trail < 0) {
      const hit = state.public || state.ipo_done ? 3.2 : 1.8;
      state.reputation = Math.max(0, (state.reputation || 0) - hit);
      pushEvent(
        state.public || state.ipo_done
          ? `Markets punish a losing month — reputation <b>−${hit.toFixed(1)}</b> (now ${(state.reputation || 0).toFixed(0)}). Public regionals live under a microscope.`
          : `PE board notes a soft month — reputation <b>−${hit.toFixed(1)}</b>. Clean up route losses.`,
        'bad'
      );
    }

    if (critical.length >= 2 && !(activeDecision || decisionQueue.length)) {
      const w = critical[0];
      queueDecision({
        kicker: `${fmtDate(state.day)} · ${state.public || state.ipo_done ? 'Public markets' : 'PE board'}`,
        title: state.public || state.ipo_done ? 'Analyst note: network quality' : 'Board letter: fix the red routes',
        body:
          `<p>${critical.length} routes look <b>structurally weak</b>. Worst: <b>${w.route.origin}–${w.route.dest}</b> — ${w.reasons[0] || w.title}.</p>` +
          `<p class="muted" style="font-size:0.85rem;">Cash runway ~${runway.toFixed(1)} mo. Ignoring this invites fare wars you cannot win.</p>`,
        teach: 'Growth capital attracts competitors. Defend with healthy routes, not vanity markets.',
        logLine: 'Board pressure on weak routes',
        options: [
          {
            id: 'board_fix',
            label: `A — Repair ${w.route.origin}–${w.route.dest}`,
            hint: 'Open route review.',
            effect: 'route_review',
            routeId: w.route.id,
          },
          {
            id: 'board_routes',
            label: 'B — Open Routes tab',
            hint: 'Review the network.',
            effect: 'tab_routes',
          },
          {
            id: 'board_ack',
            label: 'C — Acknowledge and continue',
            hint: 'Reputation already reflects the month.',
            effect: 'none',
          },
        ],
      });
    }

    if ((state.public || state.pe_done) && trail != null && trail < 0 && Math.random() < 0.55) {
      processReactiveCompetitorThreats('weekly');
    }
  }

  function routeHealthBannerHtml(health) {
    if (!health) return '';
    if (health.severity === 'ok') {
      if (health.pnl > 800) {
        return `<p class="route-health route-health-good"><b>Cash engine</b> · ${fmtMoney(health.pnl)}/day variable</p>`;
      }
      return '';
    }
    const cls = health.severity === 'critical' ? 'route-health-critical' : 'route-health-watch';
    const why = (health.reasons || []).slice(0, 2).join(' · ');
    return `<p class="route-health ${cls}"><b>${health.title}</b> — ${why}</p>`;
  }

  function profitCoachContext() {
    if (!state || !state.routes.length || state.day < 10) return null;
    const econ = simulateDayEconomics();
    const diagnoses = diagnoseNetworkRoutes();
    const worstH = diagnoses.find((d) => d.severity === 'critical') || diagnoses.find((d) => d.severity === 'watch');
    const bestH = [...diagnoses].reverse().find((d) => d.pnl > 0 && d.severity === 'ok');
    const pnls = routeDailyPnls().sort((a, b) => b.pnl - a.pnl);
    const best = pnls.find((x) => x.pnl > 0);
    const thin = pnls.filter((x) => !x.grounded && x.load < 0.38);
    const routeMargin = econ.dayRev - econ.dayCost;
    const fixedDaily = econ.dailyFixed;
    const netDaily = econ.pnl;
    const debtSvc = monthlyDebtService();

    if (worstH && worstH.severity === 'critical') {
      const r = worstH.route;
      const why = worstH.reasons.slice(0, 2).join(' ');
      const actions = (worstH.fixes || []).slice(0, 2);
      if (bestH && bestH.route) {
        actions.push({
          label: `Grow ${bestH.route.origin}–${bestH.route.dest}`,
          effect: 'route_review',
          routeId: bestH.route.id,
        });
      }
      return {
        step: 0,
        text:
          `<b>Route health:</b> <b>${r.origin}–${r.dest}</b> is <b>${worstH.title.toLowerCase()}</b>. ${why} ` +
          `Network variable margin <b>${fmtMoney(routeMargin)}/day</b> · overhead <b>−${fmtMoney(fixedDaily)}/day</b>` +
          (debtSvc > 0 ? ` · debt service ~${fmtMoney(debtSvc)}/mo` : '') +
          `.`,
        actions,
        profit: true,
        tone: 'warn',
      };
    }

    if (netDaily < -200 || (fixedDaily > routeMargin && state.day > 21)) {
      let text = `Losing <b>${fmtMoney(Math.abs(netDaily))}/day</b> after overhead. Routes earn <b>${fmtMoney(routeMargin)}/day</b> variable; gates/leases/marketing cost <b>${fmtMoney(fixedDaily)}/day</b>`;
      if (debtSvc > 0) text += ` · debt ~${fmtMoney(debtSvc)}/mo on the month tick`;
      text += '. ';
      if (worstH && worstH.route) {
        text += `Weakest: <b>${worstH.route.origin}–${worstH.route.dest}</b> — ${worstH.reasons[0] || worstH.title}. `;
      }
      if (best) {
        text += `Winner: <b>${best.route.origin}–${best.route.dest}</b> (+${fmtMoney(best.pnl)}/day) — grow what works.`;
      } else {
        text += 'Cover fixed costs on one strong route before opening another thin market.';
      }
      const actions = [];
      if (worstH && worstH.route) {
        actions.push({
          label: `Fix ${worstH.route.origin}–${worstH.route.dest}`,
          effect: 'route_review',
          routeId: worstH.route.id,
        });
      }
      if (best) {
        actions.push({
          label: `Review ${best.route.origin}–${best.route.dest}`,
          effect: 'route_review',
          routeId: best.route.id,
        });
      }
      actions.push({ label: 'Open Routes', effect: 'tab', tab: 'routes' });
      return { step: 0, text, actions, profit: true, tone: 'warn' };
    }

    if (netDaily > 500 && best) {
      const mid = activeMidgameOpsGoal();
      const midNote = mid ? ` Next ops goal: <b>${mid.label}</b> (${mid.progress}).` : '';
      return {
        step: 0,
        text:
          `Profitable: <b>+${fmtMoney(netDaily)}/day</b> net (routes +${fmtMoney(routeMargin)} · overhead −${fmtMoney(fixedDaily)}). ` +
          `Double down on <b>${best.route.origin}–${best.route.dest}</b> before vanity expansion.${midNote}`,
        actions: [
          { label: `Grow ${best.route.origin}–${best.route.dest}`, effect: 'route_review', routeId: best.route.id },
          { label: 'Open Routes', effect: 'tab', tab: 'routes' },
        ],
        profit: true,
        tone: 'good',
      };
    }

    if (thin.length && state.routes.length >= 1) {
      const r = thin[0].route;
      const health = diagnoseRouteHealth(r);
      const extra = health && health.reasons[1] ? ` ${health.reasons[1]}` : '';
      const rec = recommendLaunchFare({
        origin: r.origin,
        dest: r.dest,
        aircraftId: r.aircraft_id,
        freq: r.frequency_week,
        fare: r.fare,
        stationCost: 0,
        investments: { airport: 0, state: 0, national: 0, world: 0 },
      });
      const fareHint = rec ? ` Try fare near <b>$${rec.fare}</b> (market $${rec.market}).` : '';
      return {
        step: 0,
        text: `<b>${r.origin}–${r.dest}</b> is only <b>${(thin[0].load * 100).toFixed(0)}%</b> full — demand capture or fare may be wrong.${extra}${fareHint}`,
        actions: [
          { label: `Review ${r.origin}–${r.dest}`, effect: 'route_review', routeId: r.id },
          { label: 'Open Fleet', effect: 'tab', tab: 'fleet' },
        ],
        profit: true,
        tone: 'warn',
      };
    }

    return null;
  }

  function opsGuideContext() {
    if (!state) return null;
    const profitCoach = profitCoachContext();
    if (profitCoach) return profitCoach;
    const firstGate = state.gates[0] && state.gates[0].airport;
    const build = regionalBuildSteps();
    const nextBuild = build.find((s) => !s.done);

    if (!state.gates.length) {
      return {
        step: 1,
        text: '<b>Build a regional · 1/9</b> — Click an airport on the map, then lease a gate before you can launch flights.',
        actions: [{ label: 'Show map', effect: 'focus_map' }],
      };
    }
    if (!state.fleet.length) {
      return {
        step: 2,
        text: `<b>Build a regional · 2/9</b> — Gate at <b>${firstGate}</b>. Open <b>Fleet</b> and lease an aircraft.`,
        actions: [{ label: 'Open Fleet', effect: 'tab', tab: 'fleet' }],
      };
    }
    if (!state.routes.length) {
      const idle = firstGate ? gateUtilizationAt(firstGate) : null;
      const idleNote =
        idle && idle.gates
          ? ` Your gate allows <b>${idle.max}</b> departures/wk — none scheduled yet.`
          : '';
      return {
        step: 3,
        text: `<b>Build a regional · 3/9</b> — Launch your first route from <b>${firstGate}</b>.${idleNote}`,
        actions: [
          { label: `Plan route from ${firstGate}`, effect: 'hub_routes', airport: firstGate },
          { label: `Scout ${firstGate}`, effect: 'airport', airport: firstGate },
        ],
      };
    }
    if (nextBuild && nextBuild.id === 'return') {
      return {
        step: 4,
        text: '<b>Build a regional · 4/9</b> — Launch the <b>return leg</b> (or a second city pair). Empty ferries waste aircraft hours.',
        actions: [{ label: 'Open Routes', effect: 'tab', tab: 'routes' }],
      };
    }
    if (nextBuild && nextBuild.id === 'week') {
      return {
        step: 5,
        text: '<b>Build a regional · 5/9</b> — Run time until you post a <b>profitable week</b>. Watch Daily P&L and debt service on Capital.',
        actions: [
          { label: 'Open Capital', effect: 'tab', tab: 'finance' },
          { label: 'Open Routes', effect: 'tab', tab: 'routes' },
        ],
      };
    }
    if (nextBuild && nextBuild.id === 'city2') {
      return {
        step: 6,
        text: '<b>Build a regional · 6/9</b> — Lease a gate in a <b>second city</b> to expand the network.',
        actions: [{ label: 'Show map', effect: 'focus_map' }],
      };
    }
    if (nextBuild && nextBuild.id === 'capital') {
      return {
        step: 7,
        text: '<b>Build a regional · 7/9</b> — Visit <b>Capital</b>: seed/Series A, bank loan (interest + principal), or PE. Financing is part of building the airline.',
        actions: [{ label: 'Open Capital', effect: 'tab', tab: 'finance' }],
      };
    }
    if (nextBuild && nextBuild.id === 'scale') {
      return {
        step: 8,
        text: '<b>Build a regional · 8/9</b> — Scale to <b>four routes</b>. Match frequency to gates and aircraft hours.',
        actions: [{ label: 'Open Routes', effect: 'tab', tab: 'routes' }],
      };
    }
    if (nextBuild && nextBuild.id === 'exit') {
      return {
        step: 9,
        text: '<b>Build a regional · 9/9</b> — Optional exit path: <b>PE</b>, sell part of your stake, or unlock an <b>IPO</b> when revenue and profits allow.',
        actions: [{ label: 'Open Capital', effect: 'tab', tab: 'finance' }],
      };
    }
    const underHub = primaryUnderutilizedHub();
    if (underHub) {
      const sug = gateUtilizationSuggestions(underHub)[0];
      return {
        step: 0,
        text: sug ? sug.text : `Gate at <b>${underHub.iata}</b> is only <b>${underHub.pct.toFixed(0)}%</b> used (${underHub.remaining} departures/wk open).`,
        actions: [
          { label: `Use ${underHub.iata} capacity`, effect: 'hub_routes', airport: underHub.iata },
          ...(underHub.routesFrom.length === 1 &&
          gateUtilizationSuggestions(underHub).find((s) => s.action === 'bump_freq')
            ? [
                {
                  label: `+freq ${underHub.routesFrom[0].origin}–${underHub.routesFrom[0].dest}`,
                  effect: 'bump_freq',
                  routeId: underHub.routesFrom[0].id,
                  delta: gateUtilizationSuggestions(underHub).find((s) => s.action === 'bump_freq').delta,
                },
              ]
            : []),
        ],
      };
    }
    if (state.speed === 'pause' && state.day < 120) {
      return {
        step: 4,
        text: 'Routes are live. Press <b>▶</b> for day speed. Check <b>Capital</b> for debt interest/principal and raises.',
        actions: [
          { label: 'Open Capital', effect: 'tab', tab: 'finance' },
          { label: 'Open Routes', effect: 'tab', tab: 'routes' },
        ],
      };
    }
    const done = build.filter((s) => s.done).length;
    const mid = activeMidgameOpsGoal();
    if (mid) {
      return {
        step: 0,
        text:
          `<b>Mid-game ops:</b> ${mid.label} · ${mid.progress} (${Math.round(mid.pct)}%). ` +
          `${mid.hint || ''} Regional track ${done}/${build.length}.`,
        actions: [
          { label: 'Open Routes', effect: 'tab', tab: 'routes' },
          { label: 'Open Capital', effect: 'tab', tab: 'finance' },
        ],
      };
    }
    return {
      step: 0,
      text: `<b>Regional track ${done}/${build.length}</b> · Map · Routes · Fleet · <b>Capital</b> (debt I+P, PE, IPO). Route health banners flag weak markets. Profit coach appears when daily P&L turns red.`,
      actions: [
        { label: 'Open Capital', effect: 'tab', tab: 'finance' },
        ...(state.routes.length ? [{ label: 'Open Routes', effect: 'tab', tab: 'routes' }] : []),
      ],
    };
  }

  function goalProgressLineHtml() {
    const goal = scenarioGoal();
    if (!goal) return '';
    if (state.goal_won) {
      return `<p class="ops-goal-line ops-goal-done">Goal achieved on day ${state.goal_won.day} — free play.</p>`;
    }
    const conds = goalConditions(goal);
    if (!conds.length) return '';
    const parts = conds.map(
      (c) => `${c.done ? '<b class="via-good">✓</b>' : '○'} ${c.label} <span class="muted">(${c.progress})</span>`
    );
    return `<p class="ops-goal-line">Goal: ${parts.join(' · ')}</p>`;
  }

  /** Compact goal for HUD pill (always visible). */
  function goalHudSummary() {
    const goal = scenarioGoal();
    if (!goal) return null;
    if (state.goal_won) {
      return { short: 'Done', title: `${goal.label} · day ${state.goal_won.day}`, tone: 'good' };
    }
    const conds = goalConditions(goal);
    if (!conds.length) return { short: '—', title: goal.label, tone: null };
    const done = conds.filter((c) => c.done).length;
    const pct = Math.round(conds.reduce((s, c) => s + (c.pct || 0), 0) / conds.length);
    const next = conds.find((c) => !c.done) || conds[0];
    return {
      short: `${pct}%`,
      title: `${goal.label} · ${next.progress} (${done}/${conds.length})`,
      tone: pct >= 100 ? 'good' : pct >= 40 ? 'warn' : null,
    };
  }

  function renderOpsGuide() {
    const el = $('ops-guide');
    if (!el || !state) {
      if (el) el.innerHTML = '';
      return;
    }
    const ctx = opsGuideContext();
    if (!ctx) return;
    if (opsGuideCollapsed === null) {
      // First render this session: stay open while genuinely onboarding or something needs
      // attention; once the player is past setup and nothing is urgent, start collapsed to
      // one line instead of permanently occupying sidebar space.
      const onboarding = ctx.step >= 1 && ctx.step <= 4;
      opsGuideCollapsed = !(onboarding || ctx.tone === 'warn' || ctx.profit);
    }
    const collapsedClass = opsGuideCollapsed ? ' collapsed' : '';
    const toneClass = ctx.tone === 'good' ? ' ops-guide-good' : ctx.tone === 'warn' ? ' ops-guide-warn' : '';
    const stepLabel = ctx.step > 0 ? `<span class="ops-guide-step">Step ${ctx.step}</span>` : ctx.profit ? `<span class="ops-guide-step">Playbook</span>` : '';
    const actions =
      ctx.actions && ctx.actions.length
        ? `<div class="ops-guide-actions">${ctx.actions
            .map((a) => {
              if (a.effect === 'tab') {
                return `<button type="button" class="btn secondary" data-ops-tab="${a.tab}">${a.label}</button>`;
              }
              if (a.effect === 'airport' && a.airport) {
                return `<button type="button" class="btn secondary" data-ops-airport="${a.airport}">${a.label}</button>`;
              }
              if (a.effect === 'focus_map') {
                return `<button type="button" class="btn secondary" data-ops-map="1">${a.label}</button>`;
              }
              if (a.effect === 'hub_routes' && a.airport) {
                return `<button type="button" class="btn secondary" data-ops-hub-routes="${a.airport}">${a.label}</button>`;
              }
              if (a.effect === 'bump_freq' && a.routeId) {
                return `<button type="button" class="btn secondary" data-ops-bump-freq="${a.routeId}" data-ops-bump-delta="${a.delta || 1}">${a.label}</button>`;
              }
              if (a.effect === 'route_review' && a.routeId) {
                return `<button type="button" class="btn secondary" data-ops-route-review="${a.routeId}">${a.label}</button>`;
              }
              return '';
            })
            .join('')}</div>`
        : '';
    const profitHow = `<details class="ops-profit-how">
        <summary>How profit works</summary>
        <p class="muted" style="font-size:0.72rem;line-height:1.45;margin:6px 0 0;">
          <b>Route margin</b> = ticket + ancillary revenue minus fuel, crew, and airport fees.
          <b>Net</b> subtracts gate lease, aircraft lease, marketing, OTA, and HQ overhead split across your network.
          Thin loads often mean low <b>market share</b> at the origin — not a broken route.
          Grow frequency or fleet before opening a second thin market.
        </p>
      </details>`;
    el.className = `ops-guide${collapsedClass}${toneClass}`;
    // Goal line stays outside collapsed body so progress never disappears when coach is hidden.
    el.innerHTML = `<div class="ops-guide-head">
        <strong>${ctx.profit ? 'Profit playbook' : 'What to do next'}</strong>
        <button type="button" class="ops-guide-toggle" data-ops-collapse>${opsGuideCollapsed ? 'Show' : 'Hide'}</button>
      </div>
      ${goalProgressLineHtml()}
      ${midgameOpsGoalHtml()}
      <div class="ops-guide-body">
        <p>${stepLabel}${ctx.text}</p>
        ${actions}
        ${profitHow}
      </div>`;
    const collapseBtn = el.querySelector('[data-ops-collapse]');
    if (collapseBtn) {
      collapseBtn.addEventListener('click', () => {
        opsGuideCollapsed = !opsGuideCollapsed;
        renderOpsGuide();
      });
    }
    el.querySelectorAll('[data-ops-tab]').forEach((btn) => {
      btn.addEventListener('click', () => {
        switchTab(btn.dataset.opsTab);
        if (isMobileLayout()) scrollToSidePanel();
      });
    });
    el.querySelectorAll('[data-ops-airport]').forEach((btn) => {
      btn.addEventListener('click', () => selectAirport(btn.dataset.opsAirport));
    });
    const mapBtn = el.querySelector('[data-ops-map]');
    if (mapBtn) {
      mapBtn.addEventListener('click', () => {
        const map = $('runway-map');
        if (map) map.scrollIntoView({ block: 'center', behavior: 'smooth' });
      });
    }
    el.querySelectorAll('[data-ops-hub-routes]').forEach((btn) => {
      btn.addEventListener('click', () => focusHubForRoutes(btn.dataset.opsHubRoutes));
    });
    el.querySelectorAll('[data-ops-bump-freq]').forEach((btn) => {
      btn.addEventListener('click', () => bumpRouteFrequency(btn.dataset.opsBumpFreq, +btn.dataset.opsBumpDelta || 1));
    });
    el.querySelectorAll('[data-ops-route-review]').forEach((btn) => {
      btn.addEventListener('click', () => {
        switchTab('routes');
        openRouteReview(btn.dataset.opsRouteReview);
      });
    });
  }

  function setHudFinancialsView(view) {
    hudFinancialsView = view === 'personal' ? 'personal' : 'company';
    renderFinancialsPanel();
  }

  function renderFinancialsPanel() {
    const panel = $('hud-panel-financials');
    if (!panel || !state) return;
    const b = computeNetWorthBreakdown() || {
      total: 0,
      equity_value: 0,
      cash: 0,
    };
    const pct = state.equity_pct || 100;
    const personalCash = Math.round((b.cash || 0) * (pct / 100));
    const companyBtn = hudFinancialsView === 'company' ? ' active' : '';
    const personalBtn = hudFinancialsView === 'personal' ? ' active' : '';
    const toggle = `<div class="hud-fin-toggle" role="tablist" aria-label="Financials view">
      <button type="button" class="hud-fin-tab${companyBtn}" data-fin-view="company" role="tab" aria-selected="${hudFinancialsView === 'company'}">Company</button>
      <button type="button" class="hud-fin-tab${personalBtn}" data-fin-view="personal" role="tab" aria-selected="${hudFinancialsView === 'personal'}">Your stake</button>
    </div>`;
    let pills = '';
    if (hudFinancialsView === 'personal') {
      const stakeEv = founderStakeValue();
      pills = `
        <div class="stat-pill"><span class="stat-pill-label">Your stake (EV)</span><b>${fmtMoney(stakeEv)}</b></div>
        <div class="stat-pill"><span class="stat-pill-label">Ownership</span><b>${pct.toFixed(1)}%</b></div>
        <div class="stat-pill"><span class="stat-pill-label">Personal cash</span><b>${fmtMoney(state.personal_cash || 0)}</b></div>
        <div class="stat-pill"><span class="stat-pill-label">Your share of co. cash</span><b>${fmtMoney(personalCash)}</b></div>
        <p class="hud-fin-note muted">Personal cash comes from secondary sales / IPO. Company cash pays debt, leases, and routes. Stake value uses enterprise valuation (Capital tab).</p>`;
    } else {
      const econ = state.routes.length ? simulateDayEconomics() : null;
      const routeMargin = econ ? econ.dayRev - econ.dayCost : 0;
      const fixedDaily = econ ? econ.dailyFixed : burnMonthly() / 30;
      const debtSvc = monthlyDebtService();
      const pnlBreakdown = econ
        ? `<p class="hud-fin-note muted">Today: routes <b class="${routeMargin >= 0 ? '' : 'danger'}">${fmtMoney(routeMargin)}</b> variable margin · overhead <b>−${fmtMoney(fixedDaily)}</b> · net <b class="${econ.pnl >= 0 ? '' : 'danger'}">${fmtMoney(econ.pnl)}</b>/day · debt service ~${fmtMoney(debtSvc)}/mo (month tick)</p>`
        : '';
      pills = `
        <div class="stat-pill"><span class="stat-pill-label">Company net worth</span><b>${fmtMoney(b.total)}</b></div>
        <div class="stat-pill"><span class="stat-pill-label">Cash</span><b>${fmtMoney(b.cash)}</b></div>
        <div class="stat-pill"><span class="stat-pill-label">Monthly burn</span><b>${fmtMoney(burnMonthly())}</b></div>
        <div class="stat-pill"><span class="stat-pill-label">Debt service</span><b>${fmtMoney(debtSvc)}</b></div>
        <div class="stat-pill"><span class="stat-pill-label">LTM revenue</span><b>${fmtMoney(state.ltm_revenue)}</b></div>
        <div class="stat-pill"><span class="stat-pill-label">Reputation</span><b>${(state.reputation || 0).toFixed(0)}</b></div>
        <div class="stat-pill"><span class="stat-pill-label">Fuel</span><b>$${(state.fuel_price || 0).toFixed(2)}/gal</b></div>
        ${pnlBreakdown}`;
    }
    panel.innerHTML = toggle + `<div class="hud-fin-body">${pills}</div>`;
    panel.querySelectorAll('[data-fin-view]').forEach((btn) => {
      btn.addEventListener('click', () => setHudFinancialsView(btn.dataset.finView));
    });
  }

  function renderHud() {
    if (!state) return;
    setText('hud-cash', fmtMoney(state.cash));
    const runwayText = state.cash < 0 ? 'BANKRUPT' : `${runwayMonths().toFixed(1)} mo`;
    setText('hud-runway', runwayText);
    const showClock = state.speed === 'slow' || state.hour != null;
    setText('hud-date', fmtDate(state.day, showClock ? (state.hour ?? 8) : null));
    setText('hud-pnl', fmtMoney(state.daily_pnl));
    const net = networkRouteStats();
    const loadPct = net.count ? Math.round(net.avgLoad * 100) : null;
    setText(
      'hud-load',
      loadPct != null
        ? `${loadPct}%${net.canceled ? ' · cx' : ''}${net.ferry ? ' · ferry' : ''}`
        : '—'
    );
    if (loadPct != null) {
      if (loadPct >= 70) setStatPillTone('hud-pill-load', 'good');
      else if (loadPct >= 45) setStatPillTone('hud-pill-load', 'warn');
      else setStatPillTone('hud-pill-load', 'danger');
    } else {
      setStatPillTone('hud-pill-load', null);
    }
    const rb = bootstrap.routelab || {};
    const productName = rb.name || 'Route Lab';
    setText('hud-product-name', productName);
    const logo = $('hud-product-logo');
    if (logo && rb.logo_url) logo.src = rb.logo_url;
    const airlineLine = state.player_name
      ? `${state.airline_name || 'Airline'} · CEO ${state.player_name}`
      : state.airline_name || 'Your airline';
    setText('hud-airline', airlineLine);
    renderFinancialsPanel();

    const goalPill = $('hud-pill-goal');
    const goalSum = goalHudSummary();
    if (goalPill) {
      if (!goalSum) {
        goalPill.style.display = 'none';
      } else {
        goalPill.style.display = '';
        goalPill.title = goalSum.title;
        setText('hud-goal', goalSum.short);
        setStatPillTone('hud-pill-goal', goalSum.tone);
      }
    }

    const runwayMo = runwayMonths();
    if (state.cash < 0) setStatPillTone('hud-pill-runway', 'danger');
    else if (runwayMo < 4) setStatPillTone('hud-pill-runway', 'warn');
    else setStatPillTone('hud-pill-runway', null);

    if (state.cash < 500_000) setStatPillTone('hud-pill-cash', 'warn');
    else setStatPillTone('hud-pill-cash', null);

    const pnl = state.daily_pnl || 0;
    if (pnl > 0) setStatPillTone('hud-pill-pnl', 'good');
    else if (pnl < 0) setStatPillTone('hud-pill-pnl', 'danger');
    else setStatPillTone('hud-pill-pnl', null);

    const macroEl = $('hud-macro');
    if (macroEl && state.macro) {
      ensureMacro();
      const cashYield = state.cash > 0 ? (cashInterestAnnualRate() * 100).toFixed(2) : '0.00';
      const ota = otaEffects();
      macroEl.textContent =
        `Inflation ${state.macro.inflation_pct.toFixed(1)}% · GDP ${state.macro.gdp_growth_pct >= 0 ? '+' : ''}${state.macro.gdp_growth_pct.toFixed(1)}% · Travel demand ${state.macro.travel_spend_growth_pct >= 0 ? '+' : ''}${state.macro.travel_spend_growth_pct.toFixed(1)}% · Country health ${state.macro.country_health.toFixed(0)}/100 · Passenger demand ${(macroDemandMultiplier() * 100).toFixed(0)}% · OTA boost +${((ota.demandMult - 1) * 100).toFixed(0)}% · Cash yield ${cashYield}%/yr`;
    }
  }

  function renderEconomy() {
    const el = $('tab-economy');
    if (!el) return;
    ensureMacro();
    const m = state.macro;
    const ota = otaEffects();
    const strat = state.ancillary_strategy || 'auto';
    const stratLabel = (bootstrap.ancillary_modes || []).find((x) => x.id === strat);
    let html = `<h3>Market — ${m.country}</h3>
      <h4 style="margin-top:12px;">Airline pricing strategy</h4>
      <p class="muted" style="font-size:0.75rem;margin-bottom:8px;">Company-wide ancillary approach — new routes inherit this unless you override per route. Change mid-game as your marketing strategy evolves.</p>
      <div class="btn-row" style="flex-wrap:wrap;gap:6px;margin-bottom:14px;">`;
    (bootstrap.ancillary_modes || []).forEach((mode) => {
      html += `<button type="button" class="btn ${strat === mode.id ? '' : 'secondary'}" onclick="Runway.setAirlineAncillaryStrategy('${mode.id}')">${mode.label}</button>`;
    });
    html += `</div>
      <p class="muted" style="font-size:0.72rem;margin-bottom:12px;">Active: <b>${stratLabel ? stratLabel.label : strat}</b> — ${stratLabel ? stratLabel.desc : ''}</p>
      <dl class="stat-dl">
        <dt>Inflation</dt><dd>${m.inflation_pct.toFixed(1)}% <span class="muted">(-2% to 6%)</span></dd>
        <dt>GDP growth</dt><dd>${m.gdp_growth_pct >= 0 ? '+' : ''}${m.gdp_growth_pct.toFixed(1)}%</dd>
        <dt>GDP index</dt><dd>${m.gdp_index.toFixed(1)}</dd>
        <dt>Travel spend index</dt><dd>${m.travel_spend_index.toFixed(1)}</dd>
        <dt>Travel spend growth</dt><dd>${m.travel_spend_growth_pct >= 0 ? '+' : ''}${m.travel_spend_growth_pct.toFixed(1)}%</dd>
        <dt>Country health</dt><dd>${m.country_health.toFixed(0)} / 100</dd>
        <dt>Demand multiplier</dt><dd>${(macroDemandMultiplier() * 100).toFixed(0)}%</dd>
        <dt>OTA market share</dt><dd>${m.ota_market_penetration_pct.toFixed(0)}%</dd>
      </dl>
      <p class="muted">Inflation feeds jet fuel indirectly each week. GDP and travel spend drive passenger demand. List on OTAs in Marketing &amp; Distribution below.</p>
      <h4>Marketing &amp; distribution (OTAs)</h4>
      <p class="muted">Expedia, Google Flights, Kayak, Travelocity — listing fees plus commission on bookings. Boosts demand and marketing efficiency.</p>
      <ul class="list">`;
    (bootstrap.ota_platforms || []).forEach((p) => {
      const on = m.ota_listed[p.id];
      html += `<li style="display:flex;flex-wrap:wrap;align-items:center;gap:8px;justify-content:space-between;">
        <span><strong>${p.name}</strong><br><span class="muted">${fmtMoney(p.listing_monthly)}/mo · ${p.commission_pct}% comm · +${(p.demand_reach * 100).toFixed(0)}% reach</span></span>
        <button class="btn ${on ? '' : 'secondary'}" onclick="Runway.toggleOta('${p.id}')">${on ? 'Listed ✓' : 'List airline'}</button>
      </li>`;
    });
    html += `</ul>
      <p class="muted" style="margin-top:10px;">Active OTA demand boost: ${((ota.demandMult - 1) * 100).toFixed(0)}% · Revenue retention: ${(ota.revenueMult * 100).toFixed(0)}% · Marketing amplify: ${ota.marketingAmplify.toFixed(2)}×</p>`;
    el.innerHTML = html;
  }

  function regionalBuildSteps() {
    if (!state) return [];
    const hubs = new Set((state.gates || []).map((g) => g.airport));
    const hasReturn = (state.routes || []).some((r) => hasReturnLeg(r));
    const trail7 = (state.pnl_history || []).slice(-7);
    const weekProfit = trail7.length >= 7 && trail7.reduce((a, b) => a + b, 0) > 0;
    const raised =
      !!state.seed_done ||
      !!state.series_a_done ||
      !!state.pe_done ||
      !!state.growth_equity_done ||
      ((state.debt || []).length > 0 && (state.scenario_id !== 'inheritance' || state.day > 30));
    return [
      { id: 'hub', label: 'Lease a hub gate', done: hubs.size >= 1, tab: 'map' },
      { id: 'fleet', label: 'Add first aircraft', done: (state.fleet || []).length >= 1, tab: 'fleet' },
      { id: 'route', label: 'Open first route', done: (state.routes || []).length >= 1, tab: 'routes' },
      { id: 'return', label: 'Fly a return leg', done: hasReturn || (state.routes || []).length >= 2, tab: 'routes' },
      { id: 'week', label: 'Profitable week', done: weekProfit, tab: 'routes' },
      { id: 'city2', label: 'Second city gate', done: hubs.size >= 2, tab: 'map' },
      { id: 'capital', label: 'Close capital (equity or loan)', done: raised, tab: 'finance' },
      { id: 'scale', label: 'Four routes flying', done: (state.routes || []).length >= 4, tab: 'routes' },
      { id: 'exit', label: 'PE round, secondary, or IPO', done: !!(state.pe_done || state.ipo_done || (state.personal_cash || 0) > 0), tab: 'finance' },
    ];
  }

  function regionalBuildTrackHtml() {
    const steps = regionalBuildSteps();
    if (!steps.length) return '';
    const done = steps.filter((s) => s.done).length;
    const next = steps.find((s) => !s.done);
    return `<div class="build-track">
      <div class="build-track-head">
        <strong>Build a regional</strong>
        <span class="muted">${done}/${steps.length}${next ? ` · next: ${next.label}` : ' · track complete'}</span>
      </div>
      <ol class="build-track-list">
        ${steps
          .map(
            (s) =>
              `<li class="${s.done ? 'done' : ''}">${s.done ? '✓' : '○'} ${s.label}</li>`
          )
          .join('')}
      </ol>
    </div>`;
  }

  function renderFinance() {
    const el = $('tab-finance');
    if (!el) return;
    const tier = state.financing_tier;
    const nw = computeNetWorthBreakdown() || {
      total: 0, equity_value: 0, cash: 0, fleet: 0, gates: 0, brand: 0, routes: 0, debt: 0, bonds: 0, lease_liabilities: 0,
    };
    const totalOblig = totalDebtAndBondPrincipal();
    const debtSvc = monthlyDebtService();
    const debtInt = monthlyDebtInterestOnly();
    const debtPrinMo = Math.max(0, debtSvc - debtInt);
    const dm = state.debt_month || null;
    const ev = companyEnterpriseValue();
    const stake = founderStakeValue();
    const burn = burnMonthly();
    const runwayAfterDebt = burn > 0 ? state.cash / burn : 99;
    const goal = scenarioGoal();
    const ipoGate = canLaunchIPO();

    const debtGoalNote =
      goal && goal.max_debt != null
        ? `<p class="muted capital-note">Scenario goal counts <b>loans + bonds</b> (now <b>${fmtMoney(totalOblig)}</b> · target below ${fmtMoney(goal.max_debt)}). Restructure lowers monthly payments only — use <b>Pay down</b> to cut principal.</p>`
        : `<p class="muted capital-note">Loans + bonds: <b>${fmtMoney(totalOblig)}</b> · scheduled debt service ~<b>${fmtMoney(debtSvc)}</b>/mo (` +
          `<b>${fmtMoney(debtInt)}</b> interest · <b>${fmtMoney(debtPrinMo)}</b> principal). Cash runway ~<b>${runwayAfterDebt.toFixed(1)} mo</b> at current burn.</p>`;

    const debtRows = state.debt.length
      ? state.debt
          .map((d) => {
            const split = debtMonthPaymentSplit(d);
            const canPayOff = state.cash >= d.principal && d.principal > 0;
            const btns = [1_000_000, 5_000_000]
              .filter((amt) => d.principal > amt)
              .map(
                (amt) =>
                  `<button type="button" class="btn secondary debt-pay-btn" ${state.cash >= amt ? '' : 'disabled'} onclick="Runway.payDownDebt('${d.id}', ${amt})">Pay $${amt / 1_000_000}M</button>`
              )
              .join('');
            const payoffBtn = `<button type="button" class="btn secondary debt-pay-btn" ${canPayOff ? '' : 'disabled'} onclick="Runway.payDownDebt('${d.id}', ${d.principal})">Pay off ${fmtMoney(d.principal)}</button>`;
            const last =
              d.last_payment != null
                ? `Last paid ${fmtMoney(d.last_payment)} (${fmtMoney(d.last_interest || 0)} int / ${fmtMoney(d.last_principal || 0)} prin)`
                : `Next ~${fmtMoney(split.total)} (${fmtMoney(split.interest)} int / ${fmtMoney(split.principal)} prin)`;
            const term =
              d.months_left != null
                ? ` · ${d.months_left} mo left`
                : d.term_months
                  ? ` · ${d.term_months} mo term`
                  : '';
            return `<div class="debt-row capital-loan">
              <div class="debt-row-main">
                <span class="debt-title">${d.name} <b>${fmtMoney(d.principal)}</b> @ ${(d.rate * 100).toFixed(1)}%${term}${d.restructured ? ' · restructured' : ''}</span>
                <span class="debt-split muted">${last}</span>
              </div>
              <span class="debt-row-actions">${btns}${payoffBtn}</span>
            </div>`;
          })
          .join('')
      : '<p class="muted">No bank loans. Term loans add cash now; each month pays <b>interest + principal</b>.</p>';

    const bondRows = (state.bonds || []).length
      ? state.bonds
          .map((b) => {
            const canPayOff = state.cash >= b.principal && b.principal > 0;
            const qCoupon = ((b.principal || 0) * (b.coupon || 0)) / 4;
            const btns = [1_000_000, 5_000_000]
              .filter((amt) => b.principal > amt)
              .map(
                (amt) =>
                  `<button type="button" class="btn secondary debt-pay-btn" ${state.cash >= amt ? '' : 'disabled'} onclick="Runway.payDownBond('${b.id}', ${amt})">Buy back $${amt / 1_000_000}M</button>`
              )
              .join('');
            const payoffBtn = `<button type="button" class="btn secondary debt-pay-btn" ${canPayOff ? '' : 'disabled'} onclick="Runway.payDownBond('${b.id}', ${b.principal})">Redeem ${fmtMoney(b.principal)}</button>`;
            return `<div class="debt-row">
              <div class="debt-row-main">
                <span class="debt-title">${b.name} <b>${fmtMoney(b.principal)}</b> · ${(b.coupon * 100).toFixed(1)}% coupon${b.months_left != null ? ` · ${b.months_left} mo` : ''}</span>
                <span class="debt-split muted">Interest-only ~${fmtMoney(qCoupon)}/quarter until buyback or maturity</span>
              </div>
              <span class="debt-row-actions">${btns}${payoffBtn}</span>
            </div>`;
          })
          .join('')
      : '<p class="muted">No bonds. Coupons are interest; principal stays until you buy back or mature.</p>';

    const lastDebtLine = dm && dm.total
      ? `<p class="capital-last-debt">Last month debt service: <b>${fmtMoney(dm.total)}</b> = ${fmtMoney(dm.interest)} interest + ${fmtMoney(dm.principal)} principal</p>`
      : '';

    let html = `<h3>Capital</h3>
      ${regionalBuildTrackHtml()}
      <div class="capital-stack">
        <div class="capital-card"><span class="muted">Company cash</span><b>${fmtMoney(state.cash)}</b></div>
        <div class="capital-card"><span class="muted">Debt service / mo</span><b>${fmtMoney(debtSvc)}</b><em class="muted">${fmtMoney(debtInt)} int · ${fmtMoney(debtPrinMo)} prin</em></div>
        <div class="capital-card"><span class="muted">Your ownership</span><b>${(state.equity_pct || 0).toFixed(1)}%</b><em class="muted">stake ~${fmtMoney(stake)}</em></div>
        <div class="capital-card"><span class="muted">Enterprise value</span><b>${fmtMoney(ev)}</b><em class="muted">PE / IPO basis</em></div>
        <div class="capital-card"><span class="muted">Personal cash</span><b>${fmtMoney(state.personal_cash || 0)}</b><em class="muted">from secondaries / IPO</em></div>
        <div class="capital-card"><span class="muted">Runway</span><b>${runwayAfterDebt.toFixed(1)} mo</b><em class="muted">incl. debt service</em></div>
      </div>
      ${debtGoalNote}
      ${lastDebtLine}
      <h4>Loans <span class="muted" style="font-weight:400;font-size:0.78rem;">(interest expense + principal paydown each month)</span></h4>
      ${debtRows}
      <h4 style="margin-top:14px;">Bonds</h4>
      ${bondRows}
      <p class="muted" style="margin-top:8px;">Bond rating: ${state.bond_rating || 'N/A'} · Monthly burn ~${fmtMoney(burn)} · Idle cash yield ${(cashInterestAnnualRate() * 100).toFixed(2)}%/yr</p>

      <h4 style="margin-top:16px;">Equity &amp; exit</h4>
      <p class="muted capital-note">Raising equity dilutes ownership but funds growth. <b>Secondary</b> sells part of <em>your</em> stake for personal cash. <b>IPO</b> raises company cash and can cash you out partially.</p>
      <div class="btn-row capital-actions">`;

    if (tier === 'startup' && !state.seed_done) {
      html += `<button type="button" class="btn" onclick="Runway.raiseSeed()">Seed round (~$4.5M · ~22%)</button>`;
    } else if (state.seed_done) {
      html += `<button type="button" class="btn secondary" disabled>Seed closed</button>`;
    }
    html += `<button type="button" class="btn" onclick="Runway.raiseSeriesA()" title="Day 180+, 2 routes, $8M LTM">Series A (~$30M)</button>`;
    if (tier === 'serial') {
      html += `<button type="button" class="btn" onclick="Runway.raiseGrowthEquity()">Growth equity (~$40M)</button>`;
    }
    html += `<button type="button" class="btn" onclick="Runway.raisePrivateEquity()" title="3 routes, ~$15M LTM">Private equity</button>`;
    html += `<button type="button" class="btn secondary" onclick="Runway.sellPersonalStake(10)">Sell 10% (secondary)</button>`;
    html += `<button type="button" class="btn secondary" onclick="Runway.sellPersonalStake(20)">Sell 20% (secondary)</button>`;
    if (state.ipo_done) {
      html += `<button type="button" class="btn secondary" disabled>IPO complete</button>`;
    } else {
      html += `<button type="button" class="btn ${ipoGate.ok ? '' : 'secondary'}" onclick="Runway.launchIPO()" title="${ipoGate.ok ? 'Ready' : ipoGate.reason}">IPO ${ipoGate.ok ? '· ready' : '· locked'}</button>`;
    }

    html += `</div>
      <h4 style="margin-top:16px;">Debt markets</h4>
      <div class="btn-row capital-actions">
        <button type="button" class="btn secondary" onclick="Runway.takeBankLoan()">Bank term loan</button>`;
    if (tier === 'distressed') {
      html += `<button type="button" class="btn secondary" onclick="Runway.issueAssetBackedBonds()">Asset-backed bonds</button>`;
      html += `<button type="button" class="btn secondary" onclick="Runway.restructureDebt()" title="Lowers monthly payment — principal stays">Restructure payments</button>`;
    }
    html += `<button type="button" class="btn secondary" onclick="Runway.issueCorporateBonds()">Corporate bonds</button>
      </div>`;

    if (!ipoGate.ok && !state.ipo_done) {
      html += `<p class="muted capital-note">IPO unlock: ${ipoGate.reason}</p>`;
    }

    html += `<h4 style="margin-top:16px;">Balance sheet</h4>
      <dl class="stat-dl">
        <dt>Total net worth</dt><dd><b>${fmtMoney(nw.total)}</b></dd>
        <dt>Your equity (${(state.equity_pct || 0).toFixed(1)}%)</dt><dd>${fmtMoney(stake)} <span class="muted">(EV-based)</span></dd>
        <dt>Book equity slice</dt><dd>${fmtMoney(nw.equity_value)}</dd>
        <dt>Cash</dt><dd>${fmtMoney(nw.cash)}</dd>
        <dt>Personal cash</dt><dd>${fmtMoney(state.personal_cash || 0)}</dd>
        <dt>Fleet / gates / brand / routes</dt><dd>${fmtMoney(nw.fleet)} · ${fmtMoney(nw.gates)} · ${fmtMoney(nw.brand)} · ${fmtMoney(nw.routes)}</dd>
        <dt>Debt / bonds / leases</dt><dd>−${fmtMoney(nw.debt)} · −${fmtMoney(nw.bonds)} · −${fmtMoney(nw.lease_liabilities)}</dd>
      </dl>`;

    if ((state.raises || []).length) {
      html += `<h4 style="margin-top:12px;">Raise history</h4><ul class="capital-raises">`;
      state.raises
        .slice()
        .reverse()
        .forEach((r) => {
          html += `<li>Day ${r.day}: <b>${r.type}</b> · ${fmtMoney(r.amount || 0)}${r.secondary ? ` + secondary ${fmtMoney(r.secondary)}` : ''} · dil ${(100 * (r.dilution || 0)).toFixed(0)}%</li>`;
        });
      html += `</ul>`;
    }

    el.innerHTML = html;
  }

  function renderFleet() {
    const el = $('tab-fleet');
    if (!el) return;
    let html = '<h3>Fleet</h3>';
    if (!state.fleet.length) {
      html += '<p class="muted">No aircraft yet — open the shop to lease or buy your first plane.</p>';
    } else {
      html += '<div class="fleet-owned-list">';
      state.fleet.forEach((f) => {
        const ac = aircraftType(f.type);
        if (!ac) {
          html += `<div class="fleet-owned-card"><strong>${f.type || 'Unknown'}</strong> — missing type data</div>`;
          return;
        }
        const seats = fleetSeatCount(f);
        const life = f.leased
          ? `${f.lease_months_left || '?'} mo lease`
          : `${Math.ceil((f.life_months_left || 0) / 12)} yr life`;
        const util = planeMonthUtilizationPct(f);
        const utilToday = planeUtilizationPct(f);
        const assigned = state.routes.filter((r) => r.aircraft_id === f.id).length;
        const seatLoad = planeSeatLoadToday(f.id);
        const seatLoadLabel =
          seatLoad != null
            ? `<b class="${seatLoad >= 0.7 ? 'chip-load-good' : seatLoad >= 0.45 ? 'chip-load-warn' : 'chip-load-bad'}">${(seatLoad * 100).toFixed(0)}%</b> seats full today`
            : assigned
              ? '—'
              : 'idle';
        ensurePlaneTelemetry(f);
        const aog = f.aog_days_left > 0 ? ` <span class="danger">AOG ${f.aog_days_left}d</span>` : '';
        const utilBarClass = util < 40 ? 'util-bad' : util > 85 ? 'util-warn' : '';
        const blockCap = planeWeeklyBlockHoursCapacity(f);
        const blockUsed = planeWeeklyBlockHoursUsed(f.id);
        const rel = planeReliabilityScore(f);
        const relTone = rel >= 80 ? 'chip-load-good' : rel >= 55 ? 'chip-load-warn' : 'chip-load-bad';
        html += `<button type="button" class="fleet-owned-card fleet-owned-card-btn" data-plane-detail="${f.id}" title="Open aircraft details">
          <strong>${ac.name}</strong>${aog}
          <span class="muted">${seats} seats · ${f.leased ? 'Leased' : 'Owned'} · ${life}</span>
          <span class="muted">${ac.range_nm} nm · ${assigned} route${assigned === 1 ? '' : 's'} · <b>${fmtHours(blockUsed)}/${fmtHours(blockCap)}</b> block-hr/wk scheduled</span>
          <span class="muted" style="font-size:0.7rem;">Seat load: ${seatLoadLabel} · Util ${utilToday.toFixed(0)}% today / ${util.toFixed(0)}% MTD · Reliability <b class="${relTone}">${rel}</b></span>
          <div class="util-bar ${utilBarClass}"><span style="width:${Math.min(100, util)}%"></span></div>
          <span class="fleet-card-hint muted">Tap for maintenance · reliability · life →</span>
        </button>`;
      });
      html += '</div>';
      html +=
        '<p class="muted" style="font-size:0.72rem;">Tap a plane for the full info page. Leased aircraft bill monthly even when <b>AOG</b>.</p>';
    }

    html += `<div class="btn-row">
      <button type="button" class="btn ${fleetShopOpen ? 'secondary' : ''}" data-fleet-action="toggle-shop">${fleetShopOpen ? 'Hide aircraft shop' : '+ Lease / Buy aircraft'}</button>
    </div>`;

    if (fleetShopOpen) {
      html += `<div class="fleet-shop-panel">
        <p class="muted" style="font-size:0.75rem;margin-bottom:8px;">Tap <b>Lease</b> or <b>Buy</b> on a type, then confirm below.</p>
        <div class="fleet-grid">`;
      Object.keys(bootstrap.aircraft_types || {}).forEach((tid) => {
        const ac = aircraftType(tid);
        if (!ac) return;
        const active = fleetPending && fleetPending.type === tid;
        const deposit = (ac.lease_monthly || 0) * 2;
        const canLease = state.cash >= deposit;
        const canBuy = state.cash >= (ac.purchase || 0);
        html += `<div class="fleet-card ${active ? 'active' : ''}">
          <strong>${ac.name}</strong>
          <span class="muted">${ac.category} · ${ac.size}</span>
          <span>${ac.seats_min}–${ac.seats_max} seats · ${ac.range_nm} nm</span>
          <span>Lease ${fmtMoney(ac.lease_monthly)}/mo · Buy ${fmtMoney(ac.purchase)}</span>
          <span class="muted" style="font-size:0.68rem;">Lease deposit ${fmtMoney(deposit)}${canLease ? '' : ' · <span class="danger">need more cash</span>'}</span>
          <div class="btn-row">
            <button type="button" class="btn ${active && fleetPending.mode === 'lease' ? '' : 'secondary'}" data-fleet-action="select" data-fleet-type="${tid}" data-fleet-mode="lease" ${canLease ? '' : 'disabled'} title="${canLease ? 'Lease this aircraft' : 'Not enough cash for deposit'}">Lease</button>
            <button type="button" class="btn ${active && fleetPending.mode === 'buy' ? '' : 'secondary'}" data-fleet-action="select" data-fleet-type="${tid}" data-fleet-mode="buy" ${canBuy ? '' : 'disabled'} title="${canBuy ? 'Buy this aircraft' : 'Not enough cash to buy'}">Buy</button>
          </div>
        </div>`;
      });
      html += '</div></div>';
    }

    if (fleetPending) {
      const ac = aircraftType(fleetPending.type);
      if (ac) {
        const dens = seatDensityInfo(fleetPending.type, fleetPending.seats);
        const leaseMo = planeLeaseMonthly(fleetPending.type, dens.seats);
        const deposit = leaseMo * 2;
        const purchase = planePurchasePrice(fleetPending.type, dens.seats);
        const maint = planeMaintMonthly(fleetPending.type, dens.seats);
        const densLabel =
          dens.t < 0.35 ? 'Roomier · more legroom' : dens.t > 0.65 ? 'Dense · max capacity' : 'Standard density';
        const costLine =
          fleetPending.mode === 'lease'
            ? `Deposit due now: <b>${fmtMoney(deposit)}</b> · then <b>${fmtMoney(leaseMo)}/mo</b>`
            : `Purchase due now: <b>${fmtMoney(purchase)}</b> · maint <b>${fmtMoney(maint)}/mo</b>`;
        const baseLease = ac.lease_monthly || 0;
        const baseBuy = ac.purchase || 0;
        const deltaNote =
          fleetPending.mode === 'lease'
            ? leaseMo !== baseLease
              ? ` <span class="muted">(${leaseMo > baseLease ? '+' : ''}${fmtMoney(leaseMo - baseLease)} vs standard config)</span>`
              : ''
            : purchase !== baseBuy
              ? ` <span class="muted">(${purchase > baseBuy ? '+' : ''}${fmtMoney(purchase - baseBuy)} vs standard)</span>`
              : '';
        html += `<div class="fleet-confirm fleet-confirm-sticky" id="fleet-confirm-box">
          <h4>Confirm ${fleetPending.mode === 'lease' ? 'lease' : 'purchase'}: ${ac.name}</h4>
          <p class="muted" style="font-size:0.78rem;margin:0 0 8px;">${costLine}${deltaNote}</p>
          <label class="fleet-seats-label">Cabin seats (${ac.seats_min}–${ac.seats_max})
            <input type="number" id="fleet-seats-input" min="${ac.seats_min}" max="${ac.seats_max}" value="${dens.seats}" step="1">
          </label>
          <p class="fleet-seats-hint muted">
            <b>${dens.seats} seats</b> · ${densLabel} · Comfort <b>${comfortStars(dens.comfort)}</b><br>
            Fewer seats → lower cost + happier pax (legroom). More seats → more capacity + higher lease/buy + tighter cabin.
          </p>
          <div class="btn-row fleet-confirm-actions">
            <button type="button" class="btn" data-fleet-action="confirm">Confirm ${fleetPending.mode === 'lease' ? 'lease' : 'purchase'}</button>
            <button type="button" class="btn secondary" data-fleet-action="cancel">Cancel</button>
          </div>
        </div>`;
      }
    }
    el.innerHTML = html;
  }

  function setupFleetPanelDelegation() {
    const panel = $('panel-fleet');
    if (!panel || panel._fleetDelegation) return;
    panel._fleetDelegation = true;
    panel.addEventListener('click', (e) => {
      const planeBtn = e.target.closest('[data-plane-detail]');
      if (planeBtn) {
        e.preventDefault();
        openPlaneDetail(planeBtn.getAttribute('data-plane-detail'));
        return;
      }
      const btn = e.target.closest('[data-fleet-action]');
      if (!btn || btn.disabled) return;
      e.preventDefault();
      const action = btn.dataset.fleetAction;
      try {
        if (action === 'toggle-shop') {
          toggleFleetShop();
        } else if (action === 'select') {
          selectFleetOffer(btn.dataset.fleetType, btn.dataset.fleetMode || 'lease');
        } else if (action === 'confirm') {
          const seatInp = $('fleet-seats-input');
          if (seatInp && fleetPending) setFleetPendingSeats(seatInp.value);
          confirmFleetOffer();
        } else if (action === 'cancel') {
          cancelFleetOffer();
        }
      } catch (err) {
        console.error('Runway fleet action failed', action, err);
        alert(`Fleet action failed: ${err && err.message ? err.message : err}`);
      }
    });
    panel.addEventListener('change', (e) => {
      if (e.target && e.target.id === 'fleet-seats-input') {
        setFleetPendingSeats(e.target.value);
      }
    });
    panel.addEventListener('input', (e) => {
      if (e.target && e.target.id === 'fleet-seats-input' && fleetPending) {
        fleetPending.seats = aircraftSeats(fleetPending.type, +e.target.value);
      }
    });
  }

  function networkSnapshotHtml() {
    const gateBlock = gateCapacityNetworkHtml();
    const net = networkRouteStats();
    if (!net.count && !gateBlock) return '';
    const pnlClass = net.dailyPnl >= 0 ? 'chip-pnl-pos' : 'chip-pnl-neg';
    const routeBlock = net.count
      ? `<div class="panel-card" style="margin-bottom:10px;padding:10px 11px;">
        <p style="font-size:0.78rem;margin:0 0 6px;color:var(--gold);font-weight:600;">Network snapshot</p>
        <p style="font-size:0.75rem;margin:0;line-height:1.45;">
          <span class="${pnlClass}"><b>${fmtMoney(net.dailyPnl)}/day</b></span> route P&L ·
          <b>${net.profitable}/${net.count}</b> profitable ·
          avg load <b>${(net.avgLoad * 100).toFixed(0)}%</b>
        </p>
      </div>`
      : '';
    return gateBlock + routeBlock;
  }

  function runningRoutesHtml() {
    if (!state.routes.length) {
      return '<p class="muted" style="font-size:0.78rem;">No routes yet — open <b>Route Studio</b> to launch your first market.</p>';
    }
    const ranked = sortPlayerRoutesByPillar(scoreboardSortBy);
    const rankById = {};
    ranked.forEach((e) => {
      rankById[e.route.id] = e;
    });
    const routes =
      ranked.length && ['profit', 'riders', 'csat'].includes(scoreboardSortBy)
        ? ranked.map((e) => e.route)
        : state.routes;
    const sortNote =
      ranked.length && ['profit', 'riders', 'csat'].includes(scoreboardSortBy)
        ? `<p class="muted" style="font-size:0.7rem;margin:0 0 8px;">Sorted by <b>${pillarSortLabel(scoreboardSortBy)}</b> (click scoreboard pillars to change).</p>`
        : '';
    let html = sortNote + '<div class="route-list">';
    routes.forEach((route) => {
        const rankEntry = rankById[route.id];
        const rankBadge =
          rankEntry && ['profit', 'riders', 'csat'].includes(scoreboardSortBy)
            ? `<span class="route-rank-badge" title="${pillarSortLabel(scoreboardSortBy)} #${rankEntry.rank}">#${rankEntry.rank}</span> `
            : '';
        const r = simulateRouteDay(route);
        const pnl = r.revenue - r.cost;
        const loadNum = r.grounded ? null : r.load;
        const loadLabel = r.grounded
          ? 'AOG'
          : r.canceled
            ? `${Number.isFinite(loadNum) ? (loadNum * 100).toFixed(0) : '—'}% (canceled)`
            : Number.isFinite(loadNum)
              ? `${(loadNum * 100).toFixed(0)}% load`
              : '—';
        const loadClass = r.grounded || r.canceled
          ? 'chip-load-bad'
          : loadNum >= 0.7
            ? 'chip-load-good'
            : loadNum >= 0.45
              ? 'chip-load-warn'
              : 'chip-load-bad';
        const mktLift = routeMarketingLiftPct(route);
        const awareO = (state.brand_awareness[route.origin] || 0).toFixed(0);
        const awareD = (state.brand_awareness[route.dest] || 0).toFixed(0);
        const mktSpendO = clampMoney(state.marketing_spend_monthly[route.origin]);
        const mktSpendD = clampMoney(state.marketing_spend_monthly[route.dest]);
        const market = marketFareForPair(route.origin, route.dest, route.aircraft_type);
        const mode = route.fare_mode === 'manual' ? 'manual' : 'auto';
        const modeLabel = mode === 'manual' ? 'fixed' : 'dynamic';
        const anc = route.ancillary_mode || 'auto';
        const revPerPax = r.pax > 0 ? Math.round(r.revenue / r.pax) : 0;
        const buckets = routeFareBuckets(route);
        const bucketHint = buckets.map((b) => `$${b.fare}`).join(' / ');
        const fareRmNote = fareRmHintHtml(route);
        const pnlClass = pnl >= 0 ? 'chip-pnl-pos' : 'chip-pnl-neg';
        const actual = routeActualStats(route);
        const forecastLoad = route.launch_forecast_load;
        const forecastPax = route.launch_forecast_pax_day;
        let forecastHtml = '';
        if (forecastLoad != null) {
          const actualLoad = actual ? actual.avgLoad : loadNum;
          const actualDays = actual ? actual.days : 0;
          const actualLabel =
            actualDays > 0 ? `${(actualLoad * 100).toFixed(0)}% (${actualDays}d)` : 'collecting…';
          const underperform = actualDays >= 14 && actualLoad < forecastLoad * 0.78;
          const forecastClass = underperform ? 'route-forecast-warn' : 'route-forecast';
          const paxNote =
            forecastPax != null && actual && actualDays >= 7
              ? ` · ~${Math.round(actual.avgPax)} vs ${forecastPax} pax/day`
              : forecastPax != null
                ? ` · planned ~${forecastPax} pax/day`
                : '';
          forecastHtml = `<p class="${forecastClass}">Planned ${(forecastLoad * 100).toFixed(0)}% → Actual ${actualLabel}${paxNote}</p>`;
        }
        const originUtil = gateUtilizationAt(route.origin);
        const routeMaxFreq = maxFrequencyForRoute(route.origin, route.dest, route.aircraft_type);
        const aircraftFreqHeadroom = route.aircraft_id
          ? maxFrequencyForAircraft(
              route.aircraft_id,
              route.origin,
              route.dest,
              route.aircraft_type,
              route.id
            )
          : 0;
        const freqHeadroom = Math.min(
          originUtil.remaining,
          Math.max(0, routeMaxFreq - (route.frequency_week || 0)),
          aircraftFreqHeadroom
        );
        const gateSharePct =
          originUtil.max > 0 ? ((route.frequency_week || 0) / originUtil.max) * 100 : 0;
        let capActionHtml = '';
        if (freqHeadroom >= 2 && originUtil.underutilized) {
          const bump = Math.min(7, freqHeadroom);
          capActionHtml = `<button type="button" class="btn secondary" style="font-size:0.66rem;padding:4px 8px;margin-top:6px;" data-bump-freq="${route.id}" data-bump-delta="${bump}">Use more gate time (+${bump}/wk)</button>`;
        }
        const schedNote =
          r.schedScale < 0.98
            ? `<p class="muted" style="font-size:0.66rem;margin:4px 0 0;">Aircraft shared — flying ~<b>${Math.round(r.schedScale * (route.frequency_week || 0))}</b> of <b>${route.frequency_week}</b>/wk scheduled (one plane, one place)</p>`
            : '';
        const mkt = r.market || routeMarketContext(route);
        const mktNote = mkt
          ? `<p class="muted" style="font-size:0.66rem;margin:4px 0 0;">${route.origin} market: <b>${formatMarketSharePct(mkt.originShare)}</b> of ~${mkt.originMarketDaily}/day (${mkt.playerOriginDeps}/${mkt.originMarketWeekly} deps/wk) · pair ${formatMarketSharePct(mkt.pairCapacityShare)}</p>`
          : '';
        const mktImpactNote = `<p class="muted" style="font-size:0.66rem;margin:4px 0 0;">Marketing: <b>+${mktLift}%</b> demand from spend · brand ${route.origin} ${awareO}% / ${route.dest} ${awareD}%${
          mktSpendO + mktSpendD > 0
            ? ` · ${fmtMoney(mktSpendO + mktSpendD)}/mo airport ads`
            : ' · <span class="danger">$0 ads</span>'
        }</p>`;
        const gateNote = originUtil.gates
          ? `<p class="muted" style="font-size:0.66rem;margin:4px 0 0;">${route.origin} gate: <b>${route.frequency_week}</b> of <b>${originUtil.max}</b>/wk (${gateSharePct.toFixed(0)}% of your gate) · <b>${originUtil.remaining}</b> open</p>${mktNote}${mktImpactNote}${schedNote}${capActionHtml}`
          : `${mktNote}${mktImpactNote}${schedNote}`;
        const plane = route.aircraft_id
          ? state.fleet.find((f) => f.id === route.aircraft_id)
          : null;
        const acName = plane
          ? (aircraftType(plane.type) || {}).name || plane.type
          : route.aircraft_type || '—';
        const seatN = plane ? fleetSeatCount(plane) : '—';
        html += `<div class="route-card" data-route-id="${route.id}" data-origin="${route.origin}" data-dest="${route.dest}">
          <div class="route-card-head">
            <button type="button" class="route-card-title" data-route-review="${route.id}" title="Review performance over time">
              ${rankBadge}<strong>${route.origin}–${route.dest}</strong>
            </button>
            <span class="${loadClass}" style="font-size:0.72rem;font-weight:600;">${loadLabel}</span>
          </div>
          ${forecastHtml}
          ${routeHealthBannerHtml(diagnoseRouteHealth(route))}
          <div class="route-card-meta">
            <span>${route.frequency_week}/wk · ${acName}</span>
            ${productChipHtml(route)}
            <span class="${pnlClass}">${fmtMoney(pnl)}/day</span>
            <span class="muted">$${revPerPax}/pax · mkt $${market}</span>
            ${competitivePressureHtml(routeCompetitivePressure(route), { compact: true })}
          </div>
          <div class="route-card-footer-actions">
            <button type="button" class="btn secondary route-review-btn" data-route-review="${route.id}">Review trends →</button>
          </div>
          <details class="ap-more route-card-tune">
            <summary class="muted" style="cursor:pointer;font-size:0.75rem;">Tune this route</summary>
            ${competitivePressureHtml(routeCompetitivePressure(route))}
            ${gateNote}
            <div class="route-levers">
              <div class="route-lever">
                <span class="route-lever-label">Frequency</span>
                <div class="route-lever-row">
                  <button type="button" class="studio-nudge" onclick="Runway.adjustRouteFrequency('${route.id}', -1)" title="Fewer flights/wk">−</button>
                  <strong class="route-lever-value">${route.frequency_week}<span class="muted">/wk</span></strong>
                  <button type="button" class="studio-nudge" onclick="Runway.adjustRouteFrequency('${route.id}', 1)" title="More flights/wk">+</button>
                </div>
              </div>
              <div class="route-lever">
                <span class="route-lever-label">Marketing</span>
                <button type="button" class="btn secondary route-mkt-boost" onclick="Runway.boostRouteMarketing('${route.id}', 3000)" title="Add $3k/mo airport ads at ${route.origin}">+ads $3k</button>
              </div>
            </div>
            <div class="route-card-controls">
              <label>Aircraft (${seatN} seats)
                <select onchange="Runway.setRouteAircraft('${route.id}', this.value)">
                  ${fleetOptionsHtml(route.aircraft_id, route.origin, route.dest)}
                </select>
              </label>
              <label>Fare $ (${modeLabel})
                <input type="number" min="49" max="899" value="${route.fare}"
                  onchange="Runway.setRouteFare('${route.id}', this.value, 'manual')" title="Buckets: ${bucketHint}">
              </label>
              <label>Pricing
                <select onchange="Runway.setRouteFareMode('${route.id}', this.value)">
                  <option value="auto" ${mode === 'auto' ? 'selected' : ''}>Dynamic</option>
                  <option value="manual" ${mode === 'manual' ? 'selected' : ''}>Fixed</option>
                </select>
              </label>
              <label>Ancillary
                <select onchange="Runway.setRouteAncillary('${route.id}', this.value)">
                  <option value="auto" ${anc === 'auto' ? 'selected' : ''}>Auto</option>
                  <option value="aggressive" ${anc === 'aggressive' ? 'selected' : ''}>Heavy</option>
                  <option value="minimal" ${anc === 'minimal' ? 'selected' : ''}>Min</option>
                </select>
              </label>
            </div>
            ${fareRmNote}
            <p class="route-card-hint muted">Buckets: ${bucketHint} · levers: freq · metal · marketing · fare</p>
          </details>
        </div>`;
    });
    html += '</div>';
    return html;
  }

  function bindRunningRouteActions() {
    const running = $('route-list-running');
    if (running) bindGateCapacityActions(running);
  }

  function fleetOptionsHtml(selectedId, origin, dest) {
    if (!state.fleet.length) {
      return '<option value="">— add aircraft in Fleet tab —</option>';
    }
    return state.fleet
      .map((f) => {
        const ac = aircraftType(f.type);
        const label = ac ? ac.name : f.type || 'Aircraft';
        const sel = selectedId === f.id ? ' selected' : '';
        const cap = planeWeeklyBlockHoursCapacity(f);
        const used = planeWeeklyBlockHoursUsed(f.id);
        const hrNote = `${fmtHours(used)}/${fmtHours(cap)} hr/wk`;
        const routeNote =
          origin && dest
            ? ` · +${maxFrequencyForAircraft(f.id, origin, dest, f.type)}/wk`
            : ` · ${fmtHours(Math.max(0, cap - used))} hr open`;
        return `<option value="${f.id}"${sel}>${label} (${fleetSeatCount(f)} seats · ${hrNote}${routeNote})</option>`;
      })
      .join('');
  }

  function routeLaunchFormHtml(draft) {
    const defOrigin = draft.origin || defaultRouteOrigin();
    const util = hasGateAt(defOrigin) ? gateUtilizationAt(defOrigin) : null;
    const gateNote = hasGateAt(defOrigin)
      ? util
        ? `Gate at <b>${defOrigin}</b>: <b>${util.used}/${util.max}</b>/wk used · <b>${util.remaining}</b> open`
        : `Gate leased at <b>${defOrigin}</b>`
      : defOrigin
        ? `<span class="danger">Lease a gate at ${defOrigin} first (map → airport)</span>`
        : 'Select a hub on the map';
    const capBanner = util && util.underutilized ? gateUtilizationPromptHtml(util, { compact: true }) : '';
    const fleetReady = state.fleet.length > 0;
    // Hidden fields keep captureRouteFormDraft / suggestions working
    const defAp = airport(defOrigin);
    const defLabel = draft.originLabel || (defAp ? airportLabel(defAp) : '');
    const destAp = draft.dest ? airport(draft.dest) : null;
    const destLabel = draft.destLabel || (destAp ? airportLabel(destAp) : '');
    const aircraftId = draft.aircraftId || (state.fleet[0] && state.fleet[0].id) || '';
    return `<div class="route-studio-cta-card">
        <div class="route-studio-cta-glow" aria-hidden="true"></div>
        <p class="studio-kicker" style="margin:0 0 4px;">Route Studio</p>
        <h3 style="margin:0 0 8px;font-size:1.05rem;color:#fff;">Open a new market</h3>
        <p class="muted" style="font-size:0.78rem;line-height:1.45;margin:0 0 12px;">
          Full-screen launch: market pick → product &amp; frequency → marketing → business case.
          Not just fares — aircraft, seats, and demand engines live here.
        </p>
        <p class="route-origin-hint" style="font-size:0.74rem;margin:0 0 10px;">${gateNote}</p>
        ${capBanner}
        <p id="route-form-error" class="route-form-error" style="display:none;" role="alert"></p>
        <button type="button" class="btn studio-primary" id="btn-open-studio" data-action="open-studio"
          ${!fleetReady || !hasGateAt(defOrigin) ? '' : ''}>
          Open Route Studio ✈
        </button>
        ${
          !fleetReady
            ? '<p class="muted" style="font-size:0.7rem;margin:8px 0 0;">Add a plane in <b>Fleet</b> first.</p>'
            : !hasGateAt(defOrigin)
              ? `<p class="muted" style="font-size:0.7rem;margin:8px 0 0;">Need a gate at ${defOrigin || 'your hub'} before launch.</p>`
              : ''
        }
      </div>
      <div class="route-panel-quick" style="margin-top:12px;">
        <p class="ops-section-title" style="margin-bottom:6px;">Quick ideas from ${defOrigin || '…'}</p>
        <div id="route-suggestions"></div>
      </div>
      <!-- Keep draft fields off-screen for form capture / keyboard flows -->
      <div class="route-form-hidden" aria-hidden="true" style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);">
        <datalist id="airport-list">${airportDatalistHtml()}</datalist>
        <input type="text" id="rt-origin-search" list="airport-list" value="${defLabel}">
        <input type="hidden" id="rt-origin-code" value="${defOrigin}">
        <input type="text" id="rt-dest-search" list="airport-list" value="${destLabel}">
        <input type="hidden" id="rt-dest-code" value="${draft.dest || ''}">
        <select id="rt-aircraft">${fleetOptionsHtml(aircraftId, defOrigin, draft.dest || '')}</select>
        <input id="rt-freq" type="number" value="${draft.freq || '7'}">
        <input id="rt-fare" type="number" value="${draft.fare || '129'}">
        <div id="route-availability-panel"></div>
        <div id="route-preview"></div>
        <button type="button" id="btn-submit-route" data-action="submit-route"></button>
      </div>`;
  }

  function refreshRouteLaunchFormSections(draft) {
    const form = $('route-launch-form');
    if (!form) return;
    const oCode = $('rt-origin-code');
    if (oCode && oCode.value !== draft.origin) applyRouteFormDraftToDom();
    const defOrigin = draft.origin || defaultRouteOrigin();
    const originHint = form.querySelector('.route-origin-hint');
    const gateNote = hasGateAt(defOrigin)
      ? `<span class="muted"> · gate leased</span>`
      : `<span class="danger"> · lease a gate here first</span>`;
    if (originHint) {
      originHint.innerHTML = `Launching from <b>${defOrigin}</b>${gateNote} — click map airports to change origin, or edit the field below.`;
    }
    const acSelect = $('rt-aircraft');
    if (acSelect) {
      const prev = acSelect.value;
      const nextHtml = fleetOptionsHtml(
        draft.aircraftId || prev,
        defOrigin,
        draft.dest || ($('rt-dest-code') && $('rt-dest-code').value) || ''
      );
      if (acSelect.innerHTML !== nextHtml) {
        acSelect.innerHTML = nextHtml;
        if (draft.aircraftId) acSelect.value = draft.aircraftId;
        else if (prev && [...acSelect.options].some((o) => o.value === prev)) acSelect.value = prev;
      }
    }
    renderRouteSuggestions();
    updateRoutePreview();
    bindAvailabilityActions($('route-availability-panel'));
  }

  function routeStudioResumeBannerHtml() {
    if (!routeStudioResume || !routeStudioResume.draft) return '';
    const d = routeStudioResume.draft;
    const o = d.origin || '…';
    const dest = d.dest || '…';
    const step = routeStudioResume.step || 1;
    return `<div class="studio-resume-banner" id="studio-resume-banner">
      <div>
        <strong>Route Studio draft saved</strong>
        <span class="muted">${o} → ${dest} · step ${step}/4</span>
        <p class="muted" style="margin:4px 0 0;font-size:0.72rem;">Closed by accident? Resume — map taps no longer wipe your work.</p>
      </div>
      <div class="btn-row" style="margin:0;gap:8px;">
        <button type="button" class="btn" id="btn-resume-studio">Resume →</button>
        <button type="button" class="btn secondary" id="btn-discard-studio">Discard</button>
      </div>
    </div>`;
  }

  function bindRouteStudioResumeBanner(root) {
    const scope = root || document;
    const resume = scope.querySelector('#btn-resume-studio');
    const discard = scope.querySelector('#btn-discard-studio');
    if (resume && !resume._bound) {
      resume._bound = true;
      resume.addEventListener('click', () => resumeRouteStudio());
    }
    if (discard && !discard._bound) {
      discard._bound = true;
      discard.addEventListener('click', () => discardRouteStudioDraft());
    }
  }

  function renderRoutes(opts) {
    const el = $('tab-routes');
    if (!el) return;
    const forceForm = !!(opts && opts.forceForm);
    let draft = captureRouteFormDraft();
    draft = syncRouteOriginFromMap(draft);
    if (!selectedAirport && !draft.origin) {
      const mapOrigin = defaultRouteOrigin();
      const mapAp = airport(mapOrigin);
      draft.origin = mapOrigin;
      draft.originLabel = mapAp ? airportLabel(mapAp) : draft.originLabel;
      routeFormDraft = draft;
    }

    const snapshotEl = $('route-network-snapshot');
    const runningEl = $('route-list-running');
    const formEl = $('route-launch-form');
    const resumeEl = $('studio-resume-banner');

    if (snapshotEl && runningEl && formEl && !forceForm) {
      // Keep resume banner in sync without full rebuild
      if (routeStudioResume && routeStudioResume.draft) {
        if (!resumeEl) {
          const ban = document.createElement('div');
          ban.innerHTML = routeStudioResumeBannerHtml();
          const node = ban.firstElementChild;
          if (node) el.insertBefore(node, el.firstChild);
          bindRouteStudioResumeBanner(el);
        }
      } else if (resumeEl) {
        resumeEl.remove();
      }
      snapshotEl.innerHTML = networkSnapshotHtml();
      runningEl.innerHTML = runningRoutesHtml();
      bindRunningRouteActions();
      bindGateCapacityActions(snapshotEl);
      bindGateCapacityActions(formEl);
      bindAvailabilityActions(formEl);
      refreshRouteLaunchFormSections(draft);
      return;
    }

    let html = '<h3>Network</h3>';
    html += routeStudioResumeBannerHtml();
    html += `<div id="route-network-snapshot">${networkSnapshotHtml()}</div>`;
    html += `<div id="route-launch-form">${routeLaunchFormHtml(draft)}</div>`;
    html += '<p class="ops-section-title">Flying now</p>';
    html += `<div id="route-list-running">${runningRoutesHtml()}</div>`;
    el.innerHTML = html;
    bindRouteStudioResumeBanner(el);
    bindRouteAirportInputs();
    bindGateCapacityActions(el);
    bindAvailabilityActions(el);
    bindRunningRouteActions();
    renderRouteSuggestions();
    updateRoutePreview();
  }

  function renderRouteSuggestionButton(origin, s) {
    const freq = s.status === 'limited' && s.maxFreq > 0 ? s.maxFreq : s.freq;
    const launchLabel = s.canLaunch ? 'Launch' : s.status === 'exists' ? 'Flying' : 'Plan';
    const blocked = !s.canLaunch && s.status !== 'exists';
    const statusClass =
      s.status === 'ready' || s.status === 'limited' ? '' : s.status === 'exists' ? 'muted' : 'danger';
    const statusLine = s.reason
      ? `<span class="rs-status ${statusClass}">${s.reason}${s.maxFreq > 0 && s.status === 'limited' ? ` · try ${s.maxFreq}/wk` : ''}</span>`
      : s.maxFreq > 0
        ? `<span class="rs-status">Up to ${s.maxFreq}/wk available</span>`
        : '';
    const dirHtml = s.dir ? directionalLoadChipsHtml(origin, s.dest, s.dir) : '';
    const promptLine = s.directionPrompt
      ? `<span class="rs-prompt">${s.directionPrompt}</span>`
      : '';
    return `<li>
      <button type="button" class="route-suggest-btn${blocked ? ' blocked' : ''}" data-tier="${s.tier}"
        data-route-suggest="1"
        data-dest="${s.dest}"
        data-ac-type="${s.acType}"
        data-aircraft-id="${s.bestPlaneId || ''}"
        data-fare="${s.fare}"
        data-freq="${freq}"
        data-auto-launch="${s.canLaunch ? 'true' : 'false'}">
        <span class="rs-route">${launchLabel}: ${origin} ⇄ ${s.dest} <span class="muted">${s.destCity}</span>${s.common ? ' <span class="badge-regional">Common</span>' : ''}</span>
        <span class="rs-meta">${s.dist} nm · ${s.acName} · ${freq}/wk · ~${s.dailyPax} pax/day out${s.market ? ` · ${formatMarketSharePct(s.market.originShare)} of ${origin}` : ''}</span>
        <span class="rs-via via-${s.tier}">${s.label} · RT avg ${((s.rtAvgLoad != null ? s.rtAvgLoad : s.load) * 100).toFixed(0)}%${s.capturePct ? ` · ${s.capturePct}% capture` : ''}</span>
        ${dirHtml}
        ${promptLine}
        ${statusLine}
      </button>
    </li>`;
  }

  function renderRouteSuggestions() {
    const box = $('route-suggestions');
    if (!box) return;
    const origin = $('rt-origin-code') && $('rt-origin-code').value;
    if (!origin) {
      box.innerHTML = '<p class="muted">Select an origin to see demand suggestions.</p>';
      return;
    }
    const oAp = airport(origin);
    const ideas = routeSuggestionsFrom(origin).map((s) => enrichRouteSuggestion(origin, s));
    if (!ideas.length) {
      box.innerHTML = '<p class="muted">No viable destinations in range from this airport.</p>';
      return;
    }
    const ready = ideas.filter((s) => s.status === 'ready' || s.status === 'limited');
    const blocked = ideas.filter((s) => !['ready', 'limited'].includes(s.status));

    let html = `<h4 style="margin:0 0 6px;font-size:0.88rem;color:var(--gold);">Where to fly from ${origin}${oAp ? ` (${oAp.city})` : ''}</h4>
      <p class="muted" style="font-size:0.68rem;margin:0 0 8px;">Loads are directional — a full outbound with a softer return can still be profitable if you sell seats both ways (planes must come home either way).</p>`;
    if (ready.length) {
      html += `<p class="route-suggest-group ready">Ready or partially available (${ready.length})</p><ul class="route-suggest-list">`;
      ready.forEach((s) => {
        html += renderRouteSuggestionButton(origin, s);
      });
      html += '</ul>';
    }
    if (blocked.length) {
      html += `<p class="route-suggest-group">Needs gate, aircraft, or hours (${blocked.length})</p><ul class="route-suggest-list">`;
      blocked.forEach((s) => {
        html += renderRouteSuggestionButton(origin, s);
      });
      html += '</ul>';
    }
    box.innerHTML = html;
    bindAvailabilityActions(box);
  }

  function updateRoutePreview() {
    updateRouteAvailabilityPanel();
    const el = $('route-preview');
    if (!el) return;
    const oCode = $('rt-origin-code') && $('rt-origin-code').value;
    const dCode = $('rt-dest-code') && $('rt-dest-code').value;
    if (!oCode || !dCode) {
      el.textContent = '';
      return;
    }
    const plane = state.fleet.find((f) => f.id === ($('rt-aircraft') && $('rt-aircraft').value));
    const acType = plane ? plane.type : recommendAircraftTypeForPair(oCode, dCode);
    const freq = +($('rt-freq') && $('rt-freq').value) || 7;
    const fare = +($('rt-fare') && $('rt-fare').value) || suggestFareForPair(oCode, dCode);
    const planeId = plane ? plane.id : null;
    const via = estimateRouteViability(oCode, dCode, acType, freq, fare, planeId);
    const dir = estimateDirectionalPair(oCode, dCode, acType, freq, fare, planeId);
    const ac = aircraftType(acType);
    const oAp = airport(oCode);
    const dAp = airport(dCode);
    if (!oAp || !dAp) {
      el.textContent = '';
      return;
    }
    const dist = Math.round(haversineNm(oAp.lat, oAp.lon, dAp.lat, dAp.lon));
    const market = marketFareForPair(oCode, dCode, acType);
    const wealth = ((airportWealth(oAp) + airportWealth(dAp)) / 2 * 100).toFixed(0);
    const cap = gateCapacityLabel(oCode, freq);
    const capNote = hasGateAt(oCode)
      ? cap.ok
        ? ` · gate cap ${cap.after}/${cap.max}/wk`
        : ` · <span class="danger">over gate cap ${cap.after}/${cap.max}/wk</span>`
      : '';
    const sched =
      planeId && plane ? planeScheduleLabel(planeId, oCode, dCode, freq, acType) : null;
    const schedNote =
      sched && plane
        ? sched.ok
          ? ` · aircraft ${fmtHours(sched.after)}/${fmtHours(sched.cap)} block-hr/wk`
          : ` · <span class="danger">over aircraft schedule ${fmtHours(sched.after)}/${fmtHours(sched.cap)} hr/wk</span>`
        : '';
    const flyNote =
      via.schedScale < 0.98 ? ` · flies ~${Math.round(via.schedScale * 100)}% of ${freq}/wk` : '';
    const ctx = routeAvailabilityContext(oCode, dCode, planeId, freq);
    const validNote = ctx.valid
      ? '<span style="color:var(--accent);"> · OK to launch</span>'
      : '<span class="danger"> · fix capacity above</span>';
    const mkt = via.market;
    const mktLine = mkt
      ? `<br><span class="muted">Market scope: <b>${formatMarketSharePct(mkt.originShare)}</b> of ~${mkt.originMarketDaily}/day at ${oCode} (${mkt.playerOriginDeps}/${mkt.originMarketWeekly} deps/wk) · pair ${formatMarketSharePct(mkt.pairCapacityShare)} · capture ${formatMarketSharePct(mkt.captureFactor)}</span>`
      : '';
    const dirLine = `<br>${directionalLoadChipsHtml(oCode, dCode, dir)}
      <span class="muted" style="font-size:0.72rem;"> · RT avg ${(dir.rtAvgLoad * 100).toFixed(0)}% · ferry-only would be ~${(dir.ferryAvgLoad * 100).toFixed(0)}% effective
      <br>${dir.prompt}</span>`;
    el.innerHTML = `<strong>Demand preview:</strong> ${dist} nm · ${via.label} · ~${via.dailyPax} pax/day out at $${fare} · market $${market}${validNote}${flyNote}${dirLine}${mktLine}`;
  }

  function applyRouteSuggestion(destIata, acType, fare, freq, autoLaunch, aircraftId) {
    dismissDecisionsForRouteLaunch();
    showRouteFormError('');
    const dAp = airport(destIata);
    if (!dAp) return;
    const origin = ($('rt-origin-code') && $('rt-origin-code').value) || defaultRouteOrigin();
    const plane = aircraftId
      ? state.fleet.find((f) => f.id === aircraftId)
      : state.fleet.find((f) => f.type === acType) || state.fleet[0];
    setRouteFormDraft({
      origin,
      originLabel: airport(origin) ? airportLabel(airport(origin)) : origin,
      dest: destIata,
      destLabel: airportLabel(dAp),
      aircraftId: plane ? plane.id : '',
      freq: String(freq),
      fare: String(fare),
    });
    updateRoutePreview();

    const shouldLaunch = autoLaunch === true || autoLaunch === 'true';
    if (shouldLaunch && origin && plane) {
      openRouteLaunchModal(origin, destIata, plane.id, freq, fare);
      return;
    }
    if (!hasGateAt(origin)) {
      showRouteFormError(`Lease a gate at ${origin} first, then click Plan & launch route…`);
      selectAirport(origin);
    } else if (!plane) {
      showRouteFormError('Add matching aircraft in Fleet, then click Plan & launch route…');
    } else {
      showRouteFormError(`${origin} → ${destIata} ready — click Plan & launch route… below.`);
    }
    const preview = $('route-preview');
    if (preview) scrollSidePanelTo(preview, { block: 'nearest' });
    const submitBtn = $('btn-submit-route');
    if (submitBtn) scrollSidePanelTo(submitBtn, { block: 'nearest' });
  }

  function bindRouteAirportInputs() {
    const form = $('route-launch-form');
    if (form && form._routeInputsBound) return;
    if (form) form._routeInputsBound = true;
    const bind = (inputId, hiddenId, onSync) => {
      const input = $(inputId);
      const hidden = $(hiddenId);
      if (!input || !hidden) return;
      const sync = () => {
        const ap = resolveAirportQuery(input.value);
        hidden.value = ap ? ap.iata : '';
        if (onSync) onSync();
      };
      const syncNow = () => {
        const ap = resolveAirportQuery(input.value);
        if (ap) {
          hidden.value = ap.iata;
          if (onSync) onSync();
        }
      };
      input.addEventListener('change', sync);
      input.addEventListener('blur', sync);
      input.addEventListener('input', () => {
        syncNow();
        window.clearTimeout(input._rtDebounce);
        input._rtDebounce = window.setTimeout(sync, 180);
      });
    };
    const refresh = () => {
      captureRouteFormDraft();
      const code = $('rt-origin-code');
      if (code && code.value) selectedAirport = code.value;
      const acSelect = $('rt-aircraft');
      if (acSelect) {
        const o = $('rt-origin-code') && $('rt-origin-code').value;
        const d = $('rt-dest-code') && $('rt-dest-code').value;
        acSelect.innerHTML = fleetOptionsHtml(acSelect.value, o, d);
      }
      renderRouteSuggestions();
      updateRoutePreview();
    };
    const onDest = () => {
      captureRouteFormDraft();
      const acSelect = $('rt-aircraft');
      if (acSelect) {
        const o = $('rt-origin-code') && $('rt-origin-code').value;
        const d = $('rt-dest-code') && $('rt-dest-code').value;
        acSelect.innerHTML = fleetOptionsHtml(acSelect.value, o, d);
      }
      renderRouteSuggestions();
      updateRoutePreview();
    };
    bind('rt-origin-search', 'rt-origin-code', refresh);
    bind('rt-dest-search', 'rt-dest-code', onDest);
    ['rt-aircraft', 'rt-freq', 'rt-fare'].forEach((id) => {
      const el = $(id);
      if (!el) return;
      const sync = () => {
        captureRouteFormDraft();
        updateRoutePreview();
      };
      el.addEventListener('input', sync);
      el.addEventListener('change', sync);
    });
  }

  function isTypingTarget(el) {
    if (!el) return false;
    const tag = el.tagName;
    return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
  }

  function setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
      if (e.code !== 'Space' || e.repeat) return;
      const game = $('screen-game');
      if (!game || !game.classList.contains('active') || !state) return;
      if (isTypingTarget(document.activeElement)) return;
      e.preventDefault();
      togglePause();
    });
  }

  function renderEvents() {
    const el = $('tab-events');
    if (!el) return;
    el.innerHTML = `<ul class="list">${state.events.map((e) => {
      const cls = e.tier === 'good' ? 'log-good' : e.tier === 'bad' ? 'log-bad' : e.tier === 'milestone' ? 'log-milestone' : '';
      return `<li class="${cls}"><span class="muted">${fmtDate(e.day)}</span> ${e.msg}</li>`;
    }).join('')}</ul>`;
  }

  function renderAll() {
    if (!state) return;
    const panels = [
      renderScoreboardBar,
      renderHud,
      renderOpsGuide,
      drawMap,
      renderFinance,
      renderEconomy,
      renderFleet,
      renderRoutes,
      renderEvents,
    ];
    panels.forEach((fn) => {
      try {
        fn();
      } catch (err) {
        console.error('Runway render error:', fn.name || 'panel', err);
      }
    });
    try {
      if (selectedAirport) renderAirportPanel(selectedAirport);
      else renderAirportEmpty();
    } catch (err) {
      console.error('Runway render error: renderAirportPanel', err);
    }
    try {
      if (planeDetailId) renderPlaneDetailModal();
      if (routeReviewRouteId) renderRouteReviewModal();
    } catch (err) {
      console.error('Runway render error: detail modals', err);
    }
    renderPauseBanner();
  }

  function submitRoute() {
    // Opens Route Studio (fullscreen). Prefer draft / form fields when present.
    dismissDecisionsForRouteLaunch();
    showRouteFormError('');
    syncRouteFormFields();
    const oIn = $('rt-origin-search');
    const dIn = $('rt-dest-search');
    const oHidden = $('rt-origin-code');
    const dHidden = $('rt-dest-code');
    const oAp = resolveAirportQuery(oIn && oIn.value) || airport(oHidden && oHidden.value);
    const dAp = resolveAirportQuery(dIn && dIn.value) || airport(dHidden && dHidden.value);
    if (oAp && oHidden) oHidden.value = oAp.iata;
    if (dAp && dHidden) dHidden.value = dAp.iata;

    const origin = (oAp && oAp.iata) || defaultRouteOrigin();
    if (!state.fleet.length) {
      showRouteFormError('No aircraft — open Fleet and lease or buy a plane first.');
      switchTab('fleet');
      return;
    }
    if (origin && !hasGateAt(origin)) {
      showRouteFormError(`Lease a gate at ${origin} first (map → airport panel → Your position).`);
      selectAirport(origin);
      return;
    }

    const acEl = $('rt-aircraft');
    const freqEl = $('rt-freq');
    const fareEl = $('rt-fare');
    if (dAp && oAp && oAp.iata !== dAp.iata && acEl && acEl.value) {
      openRouteLaunchModal(
        oAp.iata,
        dAp.iata,
        acEl.value,
        +(freqEl && freqEl.value) || 7,
        +(fareEl && fareEl.value) || 129
      );
      return;
    }
    openRouteStudio({
      origin,
      dest: dAp && oAp && dAp.iata !== oAp.iata ? dAp.iata : '',
      aircraftId: (acEl && acEl.value) || (state.fleet[0] && state.fleet[0].id) || '',
      freq: +(freqEl && freqEl.value) || 7,
      fare: +(fareEl && fareEl.value) || null,
      step: 1,
    });
  }

  function emptySaveIndex() {
    const slots = {};
    slots[AUTOSAVE_SLOT_ID] = null;
    MANUAL_SLOT_IDS.forEach((id) => {
      slots[id] = null;
    });
    return { version: SAVE_FORMAT_VERSION, slots, lastSlotId: null };
  }

  function readSaveIndex() {
    try {
      const raw = localStorage.getItem(SAVE_INDEX_KEY);
      if (raw) {
        const data = JSON.parse(raw);
        if (data && data.slots) {
          MANUAL_SLOT_IDS.forEach((id) => {
            if (!(id in data.slots)) data.slots[id] = null;
          });
          if (!(AUTOSAVE_SLOT_ID in data.slots)) data.slots[AUTOSAVE_SLOT_ID] = null;
          data.version = SAVE_FORMAT_VERSION;
          return data;
        }
      }
    } catch (e) {
      /* fall through to migrate */
    }
    const migrated = migrateLegacySave();
    if (migrated) return migrated;
    return emptySaveIndex();
  }

  function writeSaveIndex(index) {
    try {
      localStorage.setItem(SAVE_INDEX_KEY, JSON.stringify(index));
    } catch (e) {
      console.warn('Route Lab: save failed', e);
      alert('Could not write save (browser storage full or blocked). Try Download save file.');
    }
  }

  function migrateLegacySave() {
    const raw = localStorage.getItem(SAVE_KEY_LEGACY);
    if (!raw) return null;
    try {
      const data = JSON.parse(raw);
      if (!data || !data.state) return null;
      const index = emptySaveIndex();
      const entry = buildSaveEntry(data.state, 'Migrated autosave');
      index.slots[AUTOSAVE_SLOT_ID] = entry;
      index.lastSlotId = AUTOSAVE_SLOT_ID;
      writeSaveIndex(index);
      try {
        localStorage.removeItem(SAVE_KEY_LEGACY);
      } catch (e) {
        /* keep legacy if remove fails */
      }
      return index;
    } catch (e) {
      return null;
    }
  }

  function buildSaveMeta(gameState, label) {
    const sc = bootstrap.scenarios[(gameState && gameState.scenario_id) || ''] || {};
    // Snapshot next objective without requiring live `state` (saves can build from any blob)
    let nextObj = null;
    const prev = state;
    try {
      if (gameState) {
        state = gameState;
        nextObj = nextObjectiveSnapshot();
      }
    } catch (e) {
      nextObj = null;
    } finally {
      state = prev;
    }
    return {
      label: label || null,
      savedAt: new Date().toISOString(),
      airline_name: (gameState && gameState.airline_name) || 'Airline',
      player_name: (gameState && gameState.player_name) || 'CEO',
      scenario_id: (gameState && gameState.scenario_id) || null,
      scenario_name: sc.name || gameState.scenario_id || 'Scenario',
      day: (gameState && gameState.day) || 0,
      cash: (gameState && gameState.cash) || 0,
      routes: ((gameState && gameState.routes) || []).length,
      fleet: ((gameState && gameState.fleet) || []).length,
      game_over: !!(gameState && gameState.game_over),
      reputation: (gameState && gameState.reputation) || 0,
      ltm_revenue: (gameState && gameState.ltm_revenue) || 0,
      next_phase: nextObj ? nextObj.phase : null,
      next_label: nextObj ? nextObj.label : null,
      next_progress: nextObj ? nextObj.progress : null,
    };
  }

  function buildSaveEntry(gameState, label) {
    // State only — never embed airport tables (0.2). Live defs load from bootstrap.
    return {
      version: SAVE_FORMAT_VERSION,
      meta: buildSaveMeta(gameState, label),
      state: JSON.parse(JSON.stringify(gameState)),
    };
  }

  function slotLabel(slotId) {
    if (slotId === AUTOSAVE_SLOT_ID) return 'Autosave';
    const n = String(slotId).replace('slot', '');
    return `Slot ${n}`;
  }

  function formatSaveMetaLine(meta) {
    if (!meta) return 'Empty';
    const when = meta.savedAt
      ? new Date(meta.savedAt).toLocaleString(undefined, {
          month: 'short',
          day: 'numeric',
          hour: 'numeric',
          minute: '2-digit',
        })
      : '—';
    const day = meta.day != null ? `Day ${meta.day}` : '';
    return `${meta.airline_name || 'Airline'} · ${meta.scenario_name || ''} · ${day} · ${fmtMoney(meta.cash || 0)} · ${when}`;
  }

  function listSaveSlots() {
    const index = readSaveIndex();
    const order = [AUTOSAVE_SLOT_ID].concat(MANUAL_SLOT_IDS);
    return order.map((id) => ({
      id,
      title: slotLabel(id),
      entry: index.slots[id] || null,
      meta: (index.slots[id] && index.slots[id].meta) || null,
    }));
  }

  function hasAnySave() {
    return listSaveSlots().some((s) => s.entry && s.entry.state);
  }

  function mostRecentSaveSlot() {
    const slots = listSaveSlots().filter((s) => s.entry && s.entry.state);
    if (!slots.length) return null;
    slots.sort((a, b) => {
      const ta = (a.meta && a.meta.savedAt) || '';
      const tb = (b.meta && b.meta.savedAt) || '';
      return tb.localeCompare(ta);
    });
    return slots[0];
  }

  /** Autosave current session (crash recovery). Does not open UI. */
  function saveGame() {
    if (!state) return;
    writeStateToSlot(AUTOSAVE_SLOT_ID, null, { quiet: true });
  }

  function writeStateToSlot(slotId, label, opts) {
    opts = opts || {};
    if (!state) return false;
    const index = readSaveIndex();
    if (!(slotId in index.slots) && slotId !== AUTOSAVE_SLOT_ID) return false;
    const entry = buildSaveEntry(state, label || null);
    index.slots[slotId] = entry;
    index.lastSlotId = slotId;
    writeSaveIndex(index);
    activeSaveSlotId = slotId;
    if (!opts.quiet) {
      pushEvent(`Game saved to ${slotLabel(slotId)}.`, 'good');
      setSaveModalStatus(`Saved to ${slotLabel(slotId)}.`);
    }
    return true;
  }

  function applyLoadedState(gameState) {
    if (!gameState) return false;
    state = gameState;
    // Always rebuild airports from live bootstrap data (never trust save-embedded tables).
    if (initialAirports) {
      bootstrap.airports = JSON.parse(JSON.stringify(initialAirports));
    }
    applyScenarioAirports(state.scenario_id);
    applyScenarioMap(state.scenario_id);
    syncMapDimensions();
    fitMapToManagedArea();
    sanitizeMarketingSpend();
    normalizeGameState();
    fleetPending = null;
    decisionQueue = [];
    activeDecision = null;
    routeLaunchActive = false;
    routeLaunchDraft = null;
    routeReviewRouteId = null;
    selectedRival = null;
    coalescedDecisionCount = 0;
    return true;
  }

  function loadStateFromSlot(slotId) {
    const index = readSaveIndex();
    const entry = index.slots[slotId];
    if (!entry || !entry.state) return false;
    if (!applyLoadedState(JSON.parse(JSON.stringify(entry.state)))) return false;
    activeSaveSlotId = slotId;
    index.lastSlotId = slotId;
    writeSaveIndex(index);
    return true;
  }

  /** Resume most recent save into the game screen. */
  function continueMostRecentSave() {
    const recent = mostRecentSaveSlot();
    if (!recent) {
      alert('No saved games found.');
      return;
    }
    if (!loadStateFromSlot(recent.id)) {
      alert('Could not load that save.');
      return;
    }
    enterLoadedGame({ showRecap: true });
  }

  function sessionRecapHtml() {
    if (!state) return '';
    const obj = nextObjectiveSnapshot() || {};
    const net = networkRouteStats();
    const loadPct = net.count ? Math.round(net.avgLoad * 100) : null;
    const trail = typeof trailingMonthPnl === 'function' ? trailingMonthPnl() : null;
    return `
      <div class="session-recap">
        <h3>Session recap</h3>
        <p class="session-recap-airline"><b>${state.airline_name || 'Airline'}</b> · Day ${state.day} · ${fmtMoney(state.cash)} cash</p>
        <ul class="session-recap-stats">
          <li>${(state.routes || []).length} routes · ${(state.fleet || []).length} aircraft · ${(state.gates || []).length} gates</li>
          <li>LTM rev ${fmtMoney(state.ltm_revenue || 0)}${loadPct != null ? ` · network load ~${loadPct}%` : ''}</li>
          ${trail != null ? `<li>Trailing month P&amp;L <b class="${trail >= 0 ? '' : 'danger'}">${fmtMoney(trail)}</b></li>` : ''}
          <li>Runway ~${runwayMonths().toFixed(1)} mo · rep ${(state.reputation || 0).toFixed(0)}</li>
        </ul>
        <p class="session-recap-next"><span class="ops-phase">${obj.phase || 'Next'}</span><br><b>${obj.label || 'Play on'}</b><br><span class="muted">${obj.progress || ''}</span></p>
        ${obj.hint ? `<p class="muted" style="font-size:0.78rem;">${obj.hint}</p>` : ''}
      </div>`;
  }

  function queueSessionRecapDecision() {
    if (!state || state.game_over) return;
    if (activeDecision || decisionQueue.length) return;
    const obj = nextObjectiveSnapshot() || {};
    const tab = obj.tab || 'routes';
    queueDecision({
      kicker: `${fmtDate(state.day)} · Welcome back`,
      title: `Continue ${state.airline_name || 'your airline'}`,
      body: sessionRecapHtml(),
      teach: 'Short sessions: do one objective, save, come back.',
      logLine: `Resumed session day ${state.day}`,
      options: [
        {
          id: 'session_do_next',
          label: `A — Do next: ${obj.label || 'Open routes'}`,
          hint: obj.progress || 'Jump to the objective',
          effect: tab === 'finance' ? 'tab_finance' : tab === 'fleet' ? 'tab_fleet' : 'tab_routes',
        },
        {
          id: 'session_play',
          label: 'B — Just press ▶',
          hint: 'Resume at Slow when you dismiss.',
          effect: 'none',
        },
        {
          id: 'session_capital',
          label: 'C — Open Capital',
          hint: 'Cash, debt, PE / IPO',
          effect: 'tab_finance',
        },
      ],
    });
  }

  function enterLoadedGame(opts) {
    opts = opts || {};
    if (!state) return;
    showScreen('screen-game');
    setSpeed('pause');
    state.paused_reason = state.game_over
      ? state.paused_reason || 'Game over'
      : 'Loaded save — press ▶ when ready';
    renderAll();
    if (opts.showRecap && !state.game_over) {
      // After first paint so decision modal can open cleanly
      setTimeout(() => {
        try {
          queueSessionRecapDecision();
          renderAll();
        } catch (e) {
          /* recap optional */
        }
      }, 80);
    }
    if (isMobileLayout()) {
      const activeTab = document.querySelector('[data-tab].active');
      syncMobileDock(activeTab ? activeTab.dataset.tab : 'routes');
    }
  }

  function deleteSaveSlot(slotId) {
    const index = readSaveIndex();
    if (!(slotId in index.slots)) return;
    index.slots[slotId] = null;
    if (index.lastSlotId === slotId) index.lastSlotId = null;
    writeSaveIndex(index);
    renderStartSaves();
    if (saveModalMode) openSaveLoadModal(saveModalMode);
  }

  function exportSaveSlot(slotId) {
    const index = readSaveIndex();
    let entry = index.slots[slotId];
    if (!entry && state && slotId === 'current') {
      entry = buildSaveEntry(state, 'Export');
    }
    if (!entry && state && slotId === AUTOSAVE_SLOT_ID) {
      entry = buildSaveEntry(state, 'Export');
    }
    if (!entry) {
      alert('Nothing to export in that slot.');
      return;
    }
    const payload = {
      format: 'routelab_save',
      version: SAVE_FORMAT_VERSION,
      exportedAt: new Date().toISOString(),
      meta: entry.meta,
      state: entry.state,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    const name = (entry.meta && entry.meta.airline_name) || 'airline';
    const day = (entry.meta && entry.meta.day) || 0;
    a.href = URL.createObjectURL(blob);
    a.download = `routelab-${name.replace(/[^\w-]+/g, '_').slice(0, 24)}-day${day}.json`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      URL.revokeObjectURL(a.href);
      a.remove();
    }, 500);
  }

  function exportCurrentGame() {
    if (!state) {
      alert('No active game to export.');
      return;
    }
    const entry = buildSaveEntry(state, 'Export');
    const payload = {
      format: 'routelab_save',
      version: SAVE_FORMAT_VERSION,
      exportedAt: new Date().toISOString(),
      meta: entry.meta,
      state: entry.state,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    const name = state.airline_name || 'airline';
    a.href = URL.createObjectURL(blob);
    a.download = `routelab-${name.replace(/[^\w-]+/g, '_').slice(0, 24)}-day${state.day || 0}.json`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      URL.revokeObjectURL(a.href);
      a.remove();
    }, 500);
  }

  function importSaveFromFile(file) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const data = JSON.parse(reader.result);
        const gameState = data.state || (data.airline_name ? data : null);
        if (!gameState || typeof gameState !== 'object') {
          alert('Invalid Route Lab save file.');
          return;
        }
        if (!applyLoadedState(JSON.parse(JSON.stringify(gameState)))) {
          alert('Could not apply imported save.');
          return;
        }
        // Park import into first empty manual slot, else slot1.
        const index = readSaveIndex();
        let target = MANUAL_SLOT_IDS.find((id) => !index.slots[id]);
        if (!target) target = 'slot1';
        index.slots[target] = buildSaveEntry(state, 'Imported');
        index.slots[AUTOSAVE_SLOT_ID] = buildSaveEntry(state, 'Imported autosave');
        index.lastSlotId = target;
        writeSaveIndex(index);
        activeSaveSlotId = target;
        closeSaveLoadModal();
        enterLoadedGame({ showRecap: true });
        pushEvent(`Imported save into ${slotLabel(target)}.`, 'good');
      } catch (e) {
        alert('Could not read that save file. Pick a Route Lab download from this game.');
      }
    };
    reader.readAsText(file);
  }

  function setSaveModalStatus(msg) {
    const el = $('save-modal-status');
    if (el) el.textContent = msg || '';
  }

  function closeSaveLoadModal() {
    const modal = $('save-load-modal');
    if (modal) {
      modal.classList.remove('open');
      modal.innerHTML = '';
    }
    saveModalMode = null;
  }

  function openSaveLoadModal(mode) {
    saveModalMode = mode === 'save' ? 'save' : 'load';
    const modal = $('save-load-modal');
    if (!modal) return;
    const isSave = saveModalMode === 'save';
    if (isSave && !state) {
      alert('Start or load a game before saving.');
      return;
    }
    const slots = listSaveSlots().filter((s) => (isSave ? s.id !== AUTOSAVE_SLOT_ID : true));
    const rows = slots
      .map((s) => {
        const empty = !s.entry;
        const actions = isSave
          ? `<button type="button" class="btn" data-save-to="${s.id}">${empty ? 'Save here' : 'Overwrite'}</button>
             ${empty ? '' : `<button type="button" class="btn secondary" data-export-slot="${s.id}">Download</button>`}`
          : empty
            ? ''
            : `<button type="button" class="btn" data-load-slot="${s.id}">Load</button>
               <button type="button" class="btn secondary" data-export-slot="${s.id}">Download</button>
               <button type="button" class="btn danger-outline" data-delete-slot="${s.id}">Delete</button>`;
        return `<div class="save-slot${empty ? ' empty' : ''}">
          <div>
            <strong>${s.title}${s.id === activeSaveSlotId && !empty ? ' · last used' : ''}</strong>
            <div class="save-meta">${empty ? 'Empty slot' : formatSaveMetaLine(s.meta)}</div>
            ${!empty && s.meta && s.meta.label ? `<div class="save-meta">${s.meta.label}</div>` : ''}
          </div>
          <div class="save-slot-actions">${actions || '<span class="muted" style="font-size:0.75rem;">—</span>'}</div>
        </div>`;
      })
      .join('');

    modal.innerHTML = `<div class="save-modal-card">
      <h2 id="save-load-title">${isSave ? 'Save game' : 'Load game'}</h2>
      <p class="muted">${
        isSave
          ? 'Pick a slot. Autosave still runs in the background while you play; manual slots are yours to manage.'
          : 'Load a slot, open a saved file from your computer, or continue from the start screen. Airport data always comes from the latest game build.'
      }</p>
      ${rows}
      <div class="save-modal-footer">
        ${
          isSave
            ? `<button type="button" class="btn secondary" id="save-export-current">Download save file</button>`
            : `<button type="button" class="btn secondary" id="save-import-btn">Open save file…</button>`
        }
        <button type="button" class="btn secondary" id="save-modal-close">Close</button>
        <span class="save-toast" id="save-modal-status"></span>
      </div>
    </div>`;
    modal.classList.add('open');

    modal.querySelectorAll('[data-save-to]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = btn.getAttribute('data-save-to');
        const existing = readSaveIndex().slots[id];
        if (existing && !window.confirm(`Overwrite ${slotLabel(id)}?`)) return;
        writeStateToSlot(id, null, { quiet: false });
        openSaveLoadModal('save');
      });
    });
    modal.querySelectorAll('[data-load-slot]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = btn.getAttribute('data-load-slot');
        if (state && !state.game_over) {
          if (!window.confirm('Load this save? Unsaved progress in the current session will remain only in Autosave.')) {
            return;
          }
          saveGame();
        }
        if (!loadStateFromSlot(id)) {
          alert('Could not load that slot.');
          return;
        }
        closeSaveLoadModal();
        enterLoadedGame({ showRecap: true });
      });
    });
    modal.querySelectorAll('[data-export-slot]').forEach((btn) => {
      btn.addEventListener('click', () => exportSaveSlot(btn.getAttribute('data-export-slot')));
    });
    modal.querySelectorAll('[data-delete-slot]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = btn.getAttribute('data-delete-slot');
        if (!window.confirm(`Delete ${slotLabel(id)}?`)) return;
        deleteSaveSlot(id);
      });
    });
    const closeBtn = $('save-modal-close');
    if (closeBtn) closeBtn.addEventListener('click', closeSaveLoadModal);
    const exp = $('save-export-current');
    if (exp) exp.addEventListener('click', exportCurrentGame);
    const imp = $('save-import-btn');
    if (imp) {
      imp.addEventListener('click', () => {
        const input = $('save-import-input');
        if (input) {
          input.value = '';
          input.click();
        }
      });
    }
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeSaveLoadModal();
    });
  }

  function renderStartSaves() {
    const box = $('start-saves');
    if (!box) return;
    if (!hasAnySave()) {
      box.classList.add('hidden');
      box.innerHTML = '';
      return;
    }
    const recent = mostRecentSaveSlot();
    const m = (recent && recent.meta) || {};
    const metaLine = recent ? formatSaveMetaLine(m) : '';
    const nextLine =
      m.next_label
        ? `<p class="start-session-next"><span class="ops-phase">${m.next_phase || 'Next'}</span> · <b>${m.next_label}</b>${
            m.next_progress ? ` <span class="muted">· ${m.next_progress}</span>` : ''
          }</p>`
        : '';
    box.classList.remove('hidden');
    box.innerHTML = `
      <h2>Continue your experiment</h2>
      <p class="muted" style="margin-bottom:8px;">Private sandbox — your saves only. Pick up in one click.</p>
      <div class="start-session-card">
        <p class="start-session-title"><b>${m.airline_name || 'Airline'}</b> · Day ${m.day != null ? m.day : '—'} · ${fmtMoney(m.cash || 0)}</p>
        <p class="muted" style="font-size:0.78rem;margin:0 0 6px;">${m.scenario_name || ''} · ${(m.routes != null ? m.routes : '—')} routes · ${(m.fleet != null ? m.fleet : '—')} aircraft</p>
        ${nextLine}
        <div class="btn-row" style="margin-top:12px;">
          <button type="button" class="btn" id="btn-continue-save">Continue — ${m.airline_name || 'last save'}</button>
          <button type="button" class="btn secondary" id="btn-open-load">All saves…</button>
          <button type="button" class="btn secondary" id="btn-import-start">Open file…</button>
        </div>
      </div>
      <p class="muted" style="margin-top:10px;margin-bottom:0;font-size:0.72rem;">${metaLine}</p>`;
    const cont = $('btn-continue-save');
    if (cont) cont.addEventListener('click', continueMostRecentSave);
    const openLoad = $('btn-open-load');
    if (openLoad) openLoad.addEventListener('click', () => openSaveLoadModal('load'));
    const imp = $('btn-import-start');
    if (imp) {
      imp.addEventListener('click', () => {
        const input = $('save-import-input');
        if (input) {
          input.value = '';
          input.click();
        }
      });
    }
  }

  function setupSaveLoadUi() {
    const saveBtn = $('btn-save-game');
    const loadBtn = $('btn-load-game');
    const newBtn = $('btn-new-game');
    if (saveBtn) saveBtn.addEventListener('click', () => openSaveLoadModal('save'));
    if (loadBtn) loadBtn.addEventListener('click', () => openSaveLoadModal('load'));
    if (newBtn) newBtn.addEventListener('click', requestNewGame);
    const fileInput = $('save-import-input');
    if (fileInput && !fileInput._routelabBound) {
      fileInput._routelabBound = true;
      fileInput.addEventListener('change', () => {
        const f = fileInput.files && fileInput.files[0];
        if (f) importSaveFromFile(f);
      });
    }
  }

  function requestNewGame() {
    if (state && !state.game_over) {
      const ok = window.confirm(
        'Return to the scenario picker? Your current session will autosave first. Manual save slots are kept.'
      );
      if (!ok) return;
      saveGame();
    }
    leaveToStartScreen();
  }

  function leaveToStartScreen() {
    if (tickTimer) {
      clearInterval(tickTimer);
      tickTimer = null;
    }
    state = null;
    fleetPending = null;
    decisionQueue = [];
    activeDecision = null;
    routeLaunchActive = false;
    routeLaunchDraft = null;
    pendingScenarioId = null;
    showScreen('screen-start');
    showScenarioPicker();
    renderScenarioPicker();
    renderStartSaves();
  }

  /** @deprecated use requestNewGame — kept for API compat */
  function resetToNewGameHard() {
    if (!window.confirm('Delete autosave and reload? Manual slots are kept.')) return;
    const index = readSaveIndex();
    index.slots[AUTOSAVE_SLOT_ID] = null;
    writeSaveIndex(index);
    try {
      localStorage.removeItem(SAVE_KEY_LEGACY);
    } catch (e) {
      /* ignore */
    }
    location.reload();
  }

  function showScreen(id) {
    document.querySelectorAll('.screen').forEach((s) => s.classList.remove('active'));
    const screen = $(id);
    if (screen) screen.classList.add('active');
    if (id === 'screen-game') {
      requestAnimationFrame(() => {
        ensureMapboxSize();
        if (useMapbox() && !mapboxMap && state) drawMap();
      });
    }
  }

  function showScenarioPicker() {
    pendingScenarioId = null;
    const picker = $('scenario-picker');
    const nameStep = $('scenario-name-step');
    const startScreen = $('screen-start');
    if (picker) picker.classList.remove('hidden');
    if (nameStep) nameStep.classList.remove('active');
    if (startScreen) startScreen.classList.remove('name-step-active');
    window.scrollTo(0, 0);
  }

  function renderAncillaryStrategyPicker() {
    const box = $('ancillary-strategy-picker');
    if (!box || !bootstrap.ancillary_modes) return;
    // Dedicated strategy cards (not emblem-opt — labels were hidden by logo CSS)
    box.innerHTML = bootstrap.ancillary_modes
      .map((m) => {
        const active = pendingAncillaryStrategy === m.id ? ' active' : '';
        const desc = (m.desc || '').replace(/"/g, '&quot;');
        return `<button type="button" class="strategy-opt${active}" data-ancillary-strategy="${m.id}" title="${desc}" onclick="Runway.setPendingAncillaryStrategy('${m.id}')">
            <span class="strategy-opt-label">${m.label || m.id}</span>
            <span class="strategy-opt-desc">${m.desc || ''}</span>
          </button>`;
      })
      .join('');
  }

  function renderEmblemPicker() {
    const box = $('emblem-picker');
    if (!box || !bootstrap.emblem_options) return;
    box.innerHTML = bootstrap.emblem_options
      .map((o) => {
        const mark = o.mark || o.id;
        const svg = emblemSvgMarkup(mark, o.colors, 48);
        // Visual marks only — no name labels under logos
        return `<button type="button" class="emblem-opt${pendingEmblem === o.id ? ' active' : ''}" data-emblem="${o.id}" aria-label="Mark ${o.id}" onclick="Runway.setEmblem('${o.id}')">
            <span class="emblem-glyph emblem-glyph-svg">${svg}</span>
          </button>`;
      })
      .join('');
  }

  function showScenarioNameStep(scenarioId) {
    const sc = bootstrap.scenarios[scenarioId];
    if (!sc) return;
    pendingScenarioId = scenarioId;
    const picker = $('scenario-picker');
    const nameStep = $('scenario-name-step');
    const title = $('name-step-title');
    const brief = $('name-step-brief');
    const playerInput = $('player-name-input');
    const airlineInput = $('airline-name-input');
    const startScreen = $('screen-start');
    if (picker) picker.classList.add('hidden');
    if (nameStep) nameStep.classList.add('active');
    if (startScreen) startScreen.classList.add('name-step-active');
    window.scrollTo(0, 0);
    if (title) title.textContent = sc.name;
    if (brief) {
      // Briefings may include simple HTML (<b>, etc.) — never textContent or tags show literally.
      brief.innerHTML = sc.briefing || '';
    }
    const snapshot = $('name-step-snapshot');
    if (snapshot) snapshot.innerHTML = scenarioSnapshotHtml(sc);
    if (playerInput) playerInput.value = sc.player_name || '';
    if (airlineInput) airlineInput.value = sc.airline_name || '';
    renderEmblemPicker();
    renderAncillaryStrategyPicker();
    if (nameStep) {
      requestAnimationFrame(() => {
        nameStep.scrollIntoView({ block: 'center', behavior: 'smooth' });
      });
    }
    if (playerInput) {
      requestAnimationFrame(() => {
        playerInput.focus({ preventScroll: true });
        playerInput.select();
      });
    }
  }

  function startPendingGame() {
    if (!pendingScenarioId) return;
    const sc = bootstrap.scenarios[pendingScenarioId];
    const playerInput = $('player-name-input');
    const airlineInput = $('airline-name-input');
    const playerName = playerInput ? playerInput.value.trim() : '';
    const airlineName = airlineInput ? airlineInput.value.trim() : '';
    const resolvedPlayer = playerName || (sc && sc.player_name) || 'CEO';
    const resolvedAirline = airlineName || (sc && sc.airline_name) || 'Your Airline';
    try {
      fleetPending = null;
      showScreen('screen-game');
      newGame(pendingScenarioId, resolvedAirline, resolvedPlayer);
      setSpeed('pause');
      queueOnboarding(pendingScenarioId);
      pendingScenarioId = null;
    } catch (err) {
      console.error('Runway: failed to start game', err);
      showScreen('screen-start');
      showScenarioPicker();
      const detail = err && err.message ? ` (${err.message})` : '';
      alert(`Could not start the game${detail}. Try a hard refresh (Cmd+Shift+R), or clear your save with New game.`);
    }
  }

  function setupScoreboardDelegation() {
    const bar = $('scoreboard-bar');
    if (!bar || bar._sbDelegation) return;
    bar._sbDelegation = true;
    bar.addEventListener('click', (e) => {
      const pillar = e.target.closest('[data-pillar-sort]');
      if (!pillar) return;
      e.preventDefault();
      e.stopPropagation();
      openScoreboardSorted(pillar.dataset.pillarSort);
    });
  }

  function setupRoutePanelDelegation() {
    const panel = $('panel-routes');
    if (!panel || panel._routeDelegation) return;
    panel._routeDelegation = true;
    panel.addEventListener('click', (e) => {
      const studioBtn = e.target.closest('[data-action="open-studio"], [data-action="submit-route"]');
      if (studioBtn) {
        e.preventDefault();
        submitRoute();
        return;
      }
      const sugBtn = e.target.closest('[data-route-suggest]');
      if (sugBtn) {
        e.preventDefault();
        applyRouteSuggestion(
          sugBtn.dataset.dest,
          sugBtn.dataset.acType,
          +sugBtn.dataset.fare,
          +sugBtn.dataset.freq,
          sugBtn.dataset.autoLaunch === 'true',
          sugBtn.dataset.aircraftId || ''
        );
        return;
      }
      const reviewBtn = e.target.closest('[data-route-review]');
      if (reviewBtn) {
        e.preventDefault();
        openRouteReview(reviewBtn.dataset.routeReview);
      }
    });
  }

  function setupStartScreen() {
    const startBtn = $('btn-start-game');
    const backBtn = $('btn-back-scenarios');
    const playerInput = $('player-name-input');
    const airlineInput = $('airline-name-input');
    if (startBtn) startBtn.addEventListener('click', startPendingGame);
    if (backBtn) backBtn.addEventListener('click', showScenarioPicker);
    [playerInput, airlineInput].forEach((input) => {
      if (!input) return;
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          startPendingGame();
        }
      });
    });
  }

  async function loadMapConfig() {
    try {
      const resp = await fetch('/static/runway/map-config.json');
      if (resp.ok) mapConfig = await resp.json();
    } catch (e) {
      console.warn('Runway: map config failed to load', e);
    }
    if (!mapConfig) {
      mapConfig = {
        usa: {
          src: '/static/runway/us-map-styled.png',
          width: 1920,
          height: 1188,
          bounds: { lonMin: -125.5, lonMax: -66.0, latMin: 24.0, latMax: 49.55 },
          padding: { left: 20, top: 40, right: 20, bottom: 4 },
        },
      };
    }
    syncMapDimensions();
  }

  async function init() {
    bootstrap = window.RUNWAY_BOOTSTRAP;
    if (!bootstrap) return;
    renderStartBrand();
    initialAirports = JSON.parse(JSON.stringify(bootstrap.airports));
    await loadMapConfig();
    sanitizeAirportGateCounts();
    setupMapInteraction();
    window.addEventListener('resize', ensureMapboxSize);
    setupStartScreen();
    setupRoutePanelDelegation();
    setupFleetPanelDelegation();
    setupScoreboardDelegation();
    setupHudLoadClick();
    setupKeyboardShortcuts();
    setupMobileDock();

    document.querySelectorAll('[data-speed]').forEach((btn) => {
      btn.addEventListener('click', () => setSpeed(btn.dataset.speed));
    });

    document.querySelectorAll('[data-tab]').forEach((btn) => {
      btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    const hudFin = $('hud-toggle-financials');
    const hudEco = $('hud-toggle-economy');
    if (hudFin) hudFin.addEventListener('click', () => toggleHudPanel('financials'));
    if (hudEco) hudEco.addEventListener('click', () => toggleHudPanel('economy'));

    const sbToggle = $('scoreboard-brand');
    if (sbToggle) sbToggle.addEventListener('click', toggleScoreboard);

    applyRouteLabBranding();
    setupSaveLoadUi();
    // Natural flow: always land on start screen. Continue/Load are explicit.
    showScreen('screen-start');
    showScenarioPicker();
    renderScenarioPicker();
    renderStartSaves();
  }

  function renderScenarioPicker() {
    const el = $('scenario-list');
    if (!el) return;
    const sorted = Object.values(bootstrap.scenarios).sort((a, b) => {
      if (a.winning_track && !b.winning_track) return -1;
      if (!a.winning_track && b.winning_track) return 1;
      if (a.tutorial && !b.tutorial) return -1;
      if (!a.tutorial && b.tutorial) return 1;
      return (a.name || '').localeCompare(b.name || '');
    });
    el.innerHTML = sorted
      .map((s) => {
        const diff = scenarioDifficultyMeta(s);
        const chips = scenarioStartingChips(s)
          .map((c) => `<span class="scenario-chip">${c}</span>`)
          .join('');
        const tutorialBadge = s.winning_track
          ? '<span class="scenario-chip" style="border-color:var(--accent);color:var(--accent);">Recommended — profit coach</span>'
          : s.tutorial
            ? '<span class="scenario-chip" style="border-color:var(--accent);color:var(--accent);">Recommended for new players</span>'
            : '';
        const goalLine = s.goal
          ? `<span class="scenario-goal">Goal: ${s.goal.label}</span>`
          : '';
        return `<button type="button" class="scenario-card" data-scenario="${s.id}">
        <span class="scenario-diff ${diff.tone}">${diff.label}</span>
        <strong>${s.name}</strong>
        <span>${s.tagline}</span>
        ${goalLine}
        <div class="scenario-card-meta">${chips}${tutorialBadge}</div>
        <p>${s.briefing}</p>
      </button>`;
      })
      .join('');
    el.querySelectorAll('[data-scenario]').forEach((btn) => {
      btn.addEventListener('click', () => showScenarioNameStep(btn.dataset.scenario));
    });
  }

  window.Runway = {
    leaseGate,
    selectFleet: selectFleetOffer,
    cancelFleet: cancelFleetOffer,
    confirmFleet: confirmFleetOffer,
    setFleetSeats: setFleetPendingSeats,
    submitRoute,
    openRouteStudio,
    confirmRouteLaunch,
    cancelRouteLaunch,
    resumeRouteStudio,
    discardRouteStudioDraft,
    softCloseRouteStudio,
    setRouteStudioStep,
    adjustRouteFrequency,
    setRouteFrequency,
    setRouteAircraft,
    boostRouteMarketing,
    raiseSeed,
    raiseSeriesA,
    raiseGrowthEquity,
    raisePrivateEquity,
    sellPersonalStake,
    launchIPO,
    takeBankLoan,
    payDownDebt,
    payDownBond,
    issueCorporateBonds,
    issueAssetBackedBonds,
    restructureDebt,
    applyMarketing,
    applyMarketingInvestments,
    applyRouteSuggestion,
    focusHubForRoutes,
    bumpRouteFrequency,
    setRouteFare,
    setRouteFareMode,
    setRouteAncillary,
    resetRouteFare,
    toggleOta: toggleOtaListing,
    toggleFleetShop,
    toggleScoreboard,
    openScoreboardSorted,
    setLeagueScope,
    selectRival,
    closeRivalDetail,
    openRouteReview,
    closeRouteReview,
    openPlaneDetail,
    closePlaneDetail,
    setEmblem: (id) => {
      pendingEmblem = id;
      document.querySelectorAll('[data-emblem]').forEach((btn) => {
        btn.classList.toggle('active', btn.dataset.emblem === id);
      });
    },
    setPendingAncillaryStrategy: (id) => {
      pendingAncillaryStrategy = id;
      renderAncillaryStrategyPicker();
    },
    setAirlineAncillaryStrategy: (id) => {
      if (!state) return;
      state.ancillary_strategy = id;
      pushPlayerEvent(`shifted airline pricing strategy to ${(bootstrap.ancillary_modes || []).find((m) => m.id === id)?.label || id}.`);
      saveGame();
      renderEconomy();
      if (routeLaunchDraft) {
        const judgment = $('rl-judgment');
        if (judgment) judgment.innerHTML = routeBusinessJudgmentHtml(routeLaunchDraft);
      }
    },
    toggleAirportSection: (section) => {
      if (!airportSections.hasOwnProperty(section)) return;
      airportSections[section] = !airportSections[section];
      if (selectedAirport) renderAirportPanel(selectedAirport);
    },
    newGame: (id) => {
      showScreen('screen-game');
      newGame(id);
    },
    /** Explicit save/load UI */
    openSave: () => openSaveLoadModal('save'),
    openLoad: () => openSaveLoadModal('load'),
    continueSave: continueMostRecentSave,
    exportSave: exportCurrentGame,
    /** Return to scenario picker (autosaves first). */
    reset: requestNewGame,
    newGameMenu: requestNewGame,
    hardResetAutosave: resetToNewGameHard,
  };
  window.RouteLab = window.Runway;

  document.addEventListener('DOMContentLoaded', init);
})();