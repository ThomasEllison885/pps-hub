/**
 * Runway — startup airline simulation (MVP v0.1)
 */
(function () {
  'use strict';

  const SAVE_KEY = 'runway_save_v1';
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
  let airportSections = { market: false, competition: true, position: true };
  let contextPulseTimer = null;
  let scoreboardOpen = false;
  let selectedRival = null;
  let pendingEmblem = 'wing';
  let state = null;
  let tickTimer = null;
  let selectedAirport = null;
  let mapView = { x: 0, y: 0, w: MAP_W, h: MAP_H };
  let fleetPending = null;
  let pendingScenarioId = null;
  let speedBeforePause = 'day';
  let decisionQueue = [];
  let activeDecision = null;
  let decisionSpeedBeforePause = 'day';
  let mapDrag = {
    active: false,
    moved: false,
    startX: 0,
    startY: 0,
    viewX: 0,
    viewY: 0,
    clickIata: null,
    pointerId: null,
  };
  let mapboxMap = null;
  let mapboxReady = false;
  let mapboxInitStarted = false;
  const MAPBOX_STYLE = 'mapbox://styles/mapbox/dark-v11';

  const $ = (id) => document.getElementById(id);

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
    const s = configured || ac.seats;
    return Math.min(ac.seats_max || ac.seats, Math.max(ac.seats_min || ac.seats, s));
  }

  function fleetSeatCount(plane) {
    return aircraftSeats(plane.type, plane.seats);
  }

  function isSmallAircraft(acType) {
    const ac = aircraftType(acType);
    if (!ac) return false;
    const max = ac.seats_max || ac.seats;
    return max < 76;
  }

  function comfortStars(rating) {
    const r = rating || 3;
    return '★'.repeat(Math.round(r)) + '☆'.repeat(5 - Math.round(r));
  }

  function airportLabel(ap) {
    return `${ap.iata} — ${ap.city}`;
  }

  function sortedAirports() {
    return [...bootstrap.airports].sort((a, b) => a.iata.localeCompare(b.iata));
  }

  function resolveAirportQuery(q) {
    if (!q) return null;
    const t = q.trim().toLowerCase();
    if (!t) return null;
    const exact = bootstrap.airports.find((a) => a.iata.toLowerCase() === t);
    if (exact) return exact;
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
          `${a.iata} ${a.city}`.toLowerCase().includes(t)
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

  function applyScenarioAirports(scenarioId) {
    if (!initialAirports) return;
    const sc = bootstrap.scenarios[scenarioId];
    const full = JSON.parse(JSON.stringify(initialAirports));
    if (sc && sc.region === 'ohio' && bootstrap.ohio_region_iata) {
      const allowed = new Set(bootstrap.ohio_region_iata);
      bootstrap.airports = full.filter((a) => allowed.has(a.iata));
    } else {
      bootstrap.airports = full;
    }
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
    activeMapKey = sc && sc.region === 'ohio' ? 'ohio' : 'usa';
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
        maxZoom: activeMapKey === 'ohio' ? 8.5 : 5.5,
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

  function fareDemandFactor(route, o, d) {
    const acType = route.aircraft_type;
    const market = marketFareForPair(route.origin, route.dest, acType);
    const ratio = route.fare / Math.max(market, 45);
    const elasticity = fareElasticity(o, d);
    if (ratio <= 1) return Math.min(1.38, 1 + (1 - ratio) * 0.48 * elasticity);
    return Math.max(0.22, 1 - (ratio - 1) * 0.82 * elasticity);
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
    const seeds = bootstrap.ohio_competitor_route_seeds || [];
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

  function hasCompetitorRoute(airline, origin, dest) {
    return (state.competitor_routes || []).some(
      (r) =>
        r.airline === airline &&
        ((r.origin === origin && r.dest === dest) || (r.origin === dest && r.dest === origin))
    );
  }

  function processCompetitorAI() {
    if (!state || !state.competitor_routes) return;
    const airports = bootstrap.airports || [];
    if (!airports.length) return;
    const invested = new Set(investedAirports());
    const actions = 1 + Math.floor(Math.random() * 2);
    const logs = [];

    for (let i = 0; i < actions; i++) {
      const roll = Math.random();
      if (roll < 0.38) {
        const ap = airports[Math.floor(Math.random() * airports.length)];
        if (!ap.incumbents || !ap.incumbents.length) continue;
        const inc = ap.incumbents[Math.floor(Math.random() * ap.incumbents.length)];
        const others = airports.filter((x) => x.iata !== ap.iata);
        const dest = others[Math.floor(Math.random() * others.length)];
        if (!dest || hasCompetitorRoute(inc.airline, ap.iata, dest.iata)) continue;
        const freq = inc.tier === 'lcc' ? 3 + Math.floor(Math.random() * 4) : 7 + Math.floor(Math.random() * 14);
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
        logs.push({
          msg: `${inc.airline} launched ${ap.iata}–${dest.iata} (${freq}x/wk from $${fare})`,
          big: invested.has(ap.iata) || invested.has(dest.iata),
          airport: ap.iata,
          airline: inc.airline,
          type: 'new_route',
          freq,
          fare,
        });
      } else if (roll < 0.68) {
        const cr = state.competitor_routes[Math.floor(Math.random() * state.competitor_routes.length)];
        if (!cr) continue;
        const delta = cr.tier === 'lcc' ? 2 + Math.floor(Math.random() * 3) : 4 + Math.floor(Math.random() * 7);
        const old = cr.frequency_week;
        cr.frequency_week = Math.min(28, cr.frequency_week + delta);
        if (cr.frequency_week - old >= 4) {
          bumpCompetitorMarket(cr.origin, cr.airline, { capacity_index: 1 + (cr.frequency_week - old) / 28 });
          logs.push({
            msg: `${cr.airline} added capacity on ${cr.origin}–${cr.dest} (${old}→${cr.frequency_week}x/wk)`,
            big: invested.has(cr.origin) || invested.has(cr.dest),
            airport: cr.origin,
            airline: cr.airline,
            type: 'capacity',
          });
        }
      } else if (roll < 0.88) {
        const cr = state.competitor_routes[Math.floor(Math.random() * state.competitor_routes.length)];
        if (!cr) continue;
        const cut = 0.1 + Math.random() * 0.14;
        const oldFare = cr.fare;
        cr.fare = Math.max(49, Math.round(cr.fare * (1 - cut)));
        if (oldFare - cr.fare >= 12) {
          bumpCompetitorMarket(cr.origin, cr.airline, { fare_index: 1 - cut });
          logs.push({
            msg: `${cr.airline} cut ${cr.origin}–${cr.dest} fares ~${Math.round(cut * 100)}% (now from $${cr.fare})`,
            big: invested.has(cr.origin) || invested.has(cr.dest),
            airport: cr.origin,
            airline: cr.airline,
            type: 'fare_cut',
            pct: cut,
          });
        }
      } else if (state.competitor_routes.length > 6) {
        const idx = Math.floor(Math.random() * state.competitor_routes.length);
        const cr = state.competitor_routes[idx];
        if (cr.frequency_week <= 3) {
          state.competitor_routes.splice(idx, 1);
          logs.push({
            msg: `${cr.airline} exited ${cr.origin}–${cr.dest}`,
            big: invested.has(cr.origin) || invested.has(cr.dest),
            airport: cr.origin,
            airline: cr.airline,
            type: 'exit',
          });
        } else {
          cr.frequency_week = Math.max(2, cr.frequency_week - 3);
        }
      }
    }

    logs.forEach((l) => pushEvent(l.msg));
    const big = logs.find((l) => l.big);
    if (big && state.day - (state.last_competitor_event_day || 0) >= 45) {
      state.last_competitor_event_day = state.day;
      if (big.type === 'new_route') {
        queueDecision({
          airport: big.airport,
          kicker: `${fmtDate(state.day)} · Competitor network`,
          title: `${big.airline} enters ${big.airport}`,
          body: `${big.msg}. This overlaps markets you may want.`,
          teach: 'Check Routes for load impact. Match only if the market is price-sensitive; otherwise lean on marketing or ancillaries.',
          logLine: big.msg,
          options: [
            { id: 'routes', label: 'A — Review my routes', hint: 'Check load and fares.', effect: 'tab_routes', airport: big.airport },
            { id: 'market', label: `B — Boost marketing at ${big.airport}`, hint: '+$12k/mo awareness.', effect: 'marketing', airport: big.airport, amount: 12000 },
            { id: 'ignore', label: 'C — Ignore for now', effect: 'none' },
          ],
        });
      } else if (big.type === 'fare_cut') {
        queueDecision({
          airport: big.airport,
          kicker: `${fmtDate(state.day)} · Competitor pricing`,
          title: `${big.airline} fare cut at ${big.airport}`,
          body: `${big.msg}.`,
          teach: 'Ancillary-heavy pricing can hold ticket low while protecting margin — or hold fare and spend on awareness.',
          logLine: big.msg,
          options: [
            { id: 'match', label: 'A — Match fare cut on overlapping routes', effect: 'match_fares', airport: big.airport, pct: big.pct || 0.12 },
            { id: 'ancillary', label: 'B — Shift to ancillary-heavy on those routes', effect: 'ancillary_aggressive', airport: big.airport },
            { id: 'ignore', label: 'C — Ignore for now', effect: 'none' },
          ],
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
    const mode = route.ancillary_mode || 'auto';
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

  function processFleetDay() {
    if (!state || !state.fleet) return;
    state.fleet.forEach((plane) => {
      if (plane.aog_days_left > 0) {
        plane.aog_days_left -= 1;
        if (plane.aog_days_left === 0) {
          const ac = aircraftType(plane.type);
          pushEvent(`${ac ? ac.name : plane.id} returned to service after maintenance.`);
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
        if (Math.random() < risk) {
          plane.aog_days_left = 1 + Math.floor(Math.random() * 4);
          const ac = aircraftType(plane.type);
          const affected = (state.routes || []).filter((r) => r.aircraft_id === plane.id).length;
          pushEvent(
            `AOG: ${ac ? ac.name : plane.type} (${plane.id}) — ${plane.aog_days_left}d out.` +
              (affected ? ` ${affected} route(s) grounded.` : ' Aircraft idle — lease still due.')
          );
        }
      });
    }

    if (state.day > 0 && state.day % 30 === 0) {
      state.fleet.forEach((plane) => {
        const util = planeMonthUtilizationPct(plane);
        if (util < 35 && (state.routes || []).some((r) => r.aircraft_id === plane.id)) {
          pushEvent(`Low utilization: ${plane.id} flew ${util.toFixed(0)}% of target block hours last month — lease cost unchanged.`);
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
      state.marketing_spend_monthly[option.airport] = clampMoney(
        (state.marketing_spend_monthly[option.airport] || 0) + (option.amount || 12000)
      );
      pushPlayerEvent(`boosted marketing at ${option.airport} to ${fmtMoney(state.marketing_spend_monthly[option.airport])}/mo.`);
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
    }
  }

  function switchTab(tabId) {
    const btn = document.querySelector(`[data-tab="${tabId}"]`);
    if (!btn) return;
    document.querySelectorAll('[data-tab]').forEach((b) => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach((p) => p.classList.remove('active'));
    btn.classList.add('active');
    const panel = $(`panel-${tabId}`);
    if (panel) panel.classList.add('active');
    if (tabId === 'routes') renderRoutes();
    if (tabId === 'finance') renderFinance();
    if (tabId === 'fleet') renderFleet();
    if (tabId === 'economy') renderEconomy();
    if (tabId === 'events') renderEvents();
  }

  function applyOnboardingChoice(option) {
    if (!option || option.effect === 'explore' || option.effect === 'none' || option.effect === 'tutorial_finish' || option.effect === 'tutorial_skip') return;
    if (option.effect === 'tab_routes') {
      if (option.airport) selectAirport(option.airport);
      switchTab('routes');
    } else if (option.effect === 'tab_finance') {
      switchTab('finance');
    } else if (option.effect === 'tab_fleet') {
      switchTab('fleet');
    } else if (option.effect === 'select_airport' && option.airport) {
      selectAirport(option.airport);
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

    if (scenarioId === 'beginner_2026' || sc.tutorial) {
      const total = 6;
      return [
        tutorialStep(
          scenarioId,
          1,
          total,
          `Welcome, ${state.player_name}`,
          `<b>${state.airline_name}</b> is a small Ohio carrier based at <b>CMH</b> (Columbus). ` +
            `You have <b>${fmtMoney(state.cash)}</b>, one leased <b>${planeLabel}</b>, and a profitable <b>${routeLabel}</b> route. ` +
            'The clock is <b>paused</b> until you finish this walkthrough.',
          'This tutorial covers the four core loops: map → fleet → routes → fares. Press ▶ only when you are ready to run days.',
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
            'To grow, tap <b>Lease…</b> or <b>Buy…</b> on an aircraft card — try an E175 for longer Ohio routes.',
          'Leasing preserves cash; buying builds asset value on your balance sheet. Match aircraft size to airport demand.',
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
          `You already fly <b>${routeLabel}</b>. To add a route: open <b>Routes</b>, pick origin (must have a gate), destination, aircraft, and frequency. ` +
            'Try suggestions like <b>CMH→CVG</b> or <b>DAY→CMH</b> after you lease a second plane.',
          'You need a gate at the origin airport before launching. Suggested routes show estimated load at market fare.',
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
          'Fares — auto vs manual',
          'In <b>Routes</b>, each line shows <b>Fare buckets</b> (basic/standard/flex), <b>Ancillary</b> mode (bags/seats fees), and revenue per passenger. ' +
            'Fares on <b>auto</b> drift monthly; ancillary-heavy works like Allegiant on thin markets.',
          'Competitor routes on the same city pair steal demand — watch dashed red lines on the map and the airport panel.',
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
          'You\'re ready to fly',
          'Tutorial complete. Keep the clock paused while you plan, then press <b>▶</b> (or Space) to advance time. ' +
            'Competitor alerts will pause the game when something big happens at your airports.',
          'Watch cash runway in the HUD. If load factors stay above ~70%, consider another route or marketing spend at your origin.',
          'Got it — let me play →',
          'tutorial_finish',
          null,
          true,
          { selector: '[data-speed="day"]', label: 'Press ▶ to advance time' }
        ),
      ];
    }
    return [];
  }

  function buildOhioQuickSteps(scenarioId) {
    const firstGate =
      (state.gates[0] && state.gates[0].airport) ||
      (bootstrap.airports[0] && bootstrap.airports[0].iata) ||
      'DAY';
    const plane = state.fleet[0];
    const ac = plane ? aircraftType(plane.type) : null;
    const planeLabel = ac ? ac.name : 'your aircraft';
    const total = 4;
    return [
      tutorialStep(
        scenarioId,
        1,
        total,
        `Welcome, ${state.player_name}`,
        `${state.airline_name} begins with <b>${fmtMoney(state.cash)}</b>, a gate at <b>${firstGate}</b>, and a leased <b>${planeLabel}</b>. ` +
          'The clock is paused — follow these quick steps, then press ▶.',
        'Ohio regional play: thin routes, real competitors, auto fares.',
        'Show my gate on the map →',
        'select_airport',
        firstGate,
        false,
        { selector: '.map-wrap', label: 'Regional map — your airports' }
      ),
      tutorialStep(
        scenarioId,
        2,
        total,
        'Scout competitors',
        'Before flying into CVG or CMH, check <b>Competitors here</b> on the airport panel — Allegiant, Delta, and others affect your demand.',
        'Lower wealth airports need smaller aircraft and sharper fares.',
        'Open CVG competitors →',
        'select_airport',
        'CVG',
        false,
        { selector: '#airport-panel', label: 'Competitors & market intel per airport' }
      ),
      tutorialStep(
        scenarioId,
        3,
        total,
        'Plan your first route',
        `Open <b>Routes</b> from <b>${firstGate}</b>. Pick a suggested destination (try DAY–CMH), choose your PC-12, set frequency, and launch. Leave fare on auto.`,
        'Market fare reflects distance and local wealth. You can edit it later in the active routes table.',
        'Open Routes tab →',
        'tab_routes',
        firstGate,
        false,
        { selector: '[data-tab="routes"]', label: 'Routes tab — plan your first flight' }
      ),
      tutorialStep(
        scenarioId,
        4,
        total,
        'Ready when you are',
        'Press <b>▶</b> when your first route looks good. The game will pause again if competitors make a big move.',
        'Fleet tab: lease before you buy while cash is tight.',
        'Got it →',
        'tutorial_finish',
        null,
        true,
        { selector: '[data-speed="day"]', label: 'Press ▶ to start the clock' }
      ),
    ];
  }

  function queueOnboarding(scenarioId) {
    if (!state || state.onboarding_done) return;
    const sc = bootstrap.scenarios[scenarioId] || {};
    let steps = [];
    if (sc.tutorial || scenarioId === 'beginner_2026') {
      steps = buildTutorialSteps(scenarioId);
    } else if (sc.region === 'ohio') {
      steps = buildOhioQuickSteps(scenarioId);
    }
    if (steps.length) {
      state.tutorial_total = steps.length;
      steps.forEach((s) => queueDecision(s));
      return;
    }
    const fallback = buildOnboardingFallback(scenarioId);
    if (fallback) queueDecision(fallback);
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

  function resolveDecision(choiceId) {
    if (!activeDecision) return;
    const option = activeDecision.options.find((o) => o.id === choiceId) || { effect: 'none' };
    const onboarding = !!activeDecision.onboarding;
    if (onboarding) {
      if (option.effect === 'tutorial_skip') {
        decisionQueue = decisionQueue.filter((d) => !d.tutorial);
        state.onboarding_done = true;
        pushPlayerEvent('skipped tutorial');
      } else {
        applyOnboardingChoice(option);
        if (activeDecision.tutorial) {
          pushPlayerEvent(`tutorial step ${activeDecision.tutorialStep || ''}: ${activeDecision.title}`);
          if (activeDecision.tutorialLast || option.effect === 'tutorial_finish') {
            state.onboarding_done = true;
            pushPlayerEvent('finished tutorial — press ▶ when ready');
          }
        } else {
          state.onboarding_done = true;
          pushPlayerEvent(`starting focus: ${option.label.replace(/^A — |^B — |^C — |^D — /, '')}`);
        }
      }
    } else {
      if (activeDecision.onResolve) activeDecision.onResolve(option);
      applyDecisionEffect({ ...option, airport: activeDecision.airport });
      pushEvent(activeDecision.logLine || `Decision: ${activeDecision.title} — ${option.label}`);
    }
    activeDecision = null;
    state.paused_reason = null;
    renderDecisionModal();
    if (decisionQueue.length) showNextDecision();
    else if (!onboarding && decisionSpeedBeforePause && decisionSpeedBeforePause !== 'pause') {
      setSpeed(decisionSpeedBeforePause);
    } else {
      setSpeed('pause');
    }
    saveGame();
    renderAll();
  }

  function showNextDecision() {
    if (activeDecision || !decisionQueue.length) return;
    activeDecision = decisionQueue.shift();
    if (!activeDecision.onboarding && state.speed !== 'pause') {
      decisionSpeedBeforePause = state.speed || speedBeforePause || 'day';
      setSpeed('pause');
    } else if (activeDecision.onboarding) {
      setSpeed('pause');
    }
    state.paused_reason = activeDecision.onboarding
      ? activeDecision.tutorial
        ? `Tutorial step ${activeDecision.tutorialStep || 1} of ${activeDecision.tutorialTotal || '?'}`
        : 'Getting started — pick a first step'
      : 'Market shift — decision required';
    renderDecisionModal();
    renderHud();
    const banner = $('pause-banner');
    if (banner) {
      banner.style.display = 'block';
      banner.textContent = activeDecision.onboarding
        ? activeDecision.tutorial
          ? `Paused — tutorial step ${activeDecision.tutorialStep || 1} of ${activeDecision.tutorialTotal || '?' } (▶ when finished)`
          : 'Paused — choose a first step below (▶ runs the clock when ready)'
        : `Paused: ${state.paused_reason}`;
    }
  }

  function queueDecision(decision) {
    decisionQueue.push(decision);
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
    const cardClass = activeDecision.onboarding ? 'decision-card onboarding' : 'decision-card';
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

  function maybeCompetitorEvents() {
    if (!state || state.game_over || activeDecision || decisionQueue.length) return;
    const gap = state.day - (state.last_competitor_event_day || 0);
    if (gap < 50) return;
    if (Math.random() > 0.34) return;
    const invested = investedAirports();
    if (!invested.length) return;
    const iata = invested[Math.floor(Math.random() * invested.length)];
    const ap = airport(iata);
    if (!ap || !ap.incumbents || !ap.incumbents.length) return;
    const incumbent = ap.incumbents[Math.floor(Math.random() * Math.min(3, ap.incumbents.length))];
    const roll = Math.random();
    let decision = null;

    if (roll < 0.38) {
      const pct = 0.14 + Math.random() * 0.12;
      bumpCompetitorMarket(iata, incumbent.airline, { fare_index: 1 - pct });
      decision = {
        airport: iata,
        kicker: `${fmtDate(state.day)} · ${ap.city}`,
        title: `${incumbent.airline} cuts fares at ${iata}`,
        body: `${incumbent.airline} dropped average fares about <b>${Math.round(pct * 100)}%</b> on overlapping city pairs. Shoppers are comparing every dollar — small moves won't matter; this one will.`,
        teach: 'Price-sensitive markets (lower wealth index) punish blind matching. Holding fare and buying awareness can protect margin on premium cabins.',
        logLine: `${incumbent.airline} fare war at ${iata} (−${Math.round(pct * 100)}%)`,
        options: [
          {
            id: 'match',
            label: `A — Match the cut on your ${iata} routes`,
            hint: 'Protect load factor; margin takes the hit.',
            effect: 'match_fares',
            airport: iata,
            pct,
          },
          {
            id: 'market',
            label: `B — Hold fares · add $15k/mo marketing at ${iata}`,
            hint: 'Teach the market your product; better when luxury share is higher.',
            effect: 'marketing',
            airport: iata,
            amount: 15000,
          },
          {
            id: 'ignore',
            label: 'C — Ignore for now',
            hint: 'Demand may soften until you react.',
            effect: 'none',
          },
        ],
      };
    } else if (roll < 0.62 && iata === 'CVG') {
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
          {
            id: 'market',
            label: 'B — Skip OTA · invest $12k/mo direct marketing',
            hint: 'Keep revenue per booking; grow awareness yourself.',
            effect: 'marketing',
            airport: iata,
            amount: 12000,
          },
          {
            id: 'ignore',
            label: 'C — Ignore for now',
            hint: 'No OTA boost; competitors may appear more often in search.',
            effect: 'none',
          },
        ],
      };
    } else {
      const pct = 0.1 + Math.random() * 0.08;
      bumpCompetitorMarket(iata, incumbent.airline, { capacity_index: 1 + pct });
      decision = {
        airport: iata,
        kicker: `${fmtDate(state.day)} · Capacity`,
        title: `${incumbent.airline} adds seats at ${iata}`,
        body: `${incumbent.airline} filed <b>+${Math.round(pct * 100)}% capacity</b> on key markets from ${iata}. More seats usually mean fare pressure unless you differentiate.`,
        teach: 'When competitors dump seats, either lean into service/schedule niche or compete on price selectively — not every route needs a response.',
        logLine: `${incumbent.airline} capacity increase at ${iata}`,
        options: [
          {
            id: 'cut',
            label: `A — Trim fares ~8% on ${iata} routes`,
            hint: 'Defend load factor against extra seats.',
            effect: 'cut_fares',
            airport: iata,
            pct: 0.08,
          },
          {
            id: 'premium',
            label: 'B — Hold premium · reputation push',
            hint: 'Works when luxury demand exists; accept softer loads short-term.',
            effect: 'hold_premium',
            airport: iata,
          },
          {
            id: 'ignore',
            label: 'C — Ignore for now',
            hint: 'Monitor loads; adjust fares manually later.',
            effect: 'none',
          },
        ],
      };
    }

    if (decision) {
      state.last_competitor_event_day = state.day;
      queueDecision(decision);
    }
  }

  function updateDynamicFares() {
    if (!state || !state.routes.length) return;
    state.routes.forEach((route) => {
      if (route.fare_mode === 'manual') return;
      const sim = simulateRouteDay(route);
      const market = marketFareForPair(route.origin, route.dest, route.aircraft_type);
      route.market_fare = market;
      if (sim.load > 0.86) route.fare = Math.min(Math.round(market * 1.22), route.fare + 4);
      else if (sim.load < 0.52) route.fare = Math.max(Math.round(market * 0.7), route.fare - 5);
      else route.fare = Math.round(route.fare * 0.9 + market * 0.1);
    });
  }

  function setRouteFare(routeId, fare, mode) {
    const route = state.routes.find((r) => r.id === routeId);
    if (!route) return;
    route.fare = Math.max(49, Math.min(899, Math.round(fare)));
    route.fare_mode = mode || 'manual';
    saveGame();
    renderRoutes();
    renderHud();
  }

  function setRouteAncillary(routeId, mode) {
    const route = state.routes.find((r) => r.id === routeId);
    if (!route) return;
    route.ancillary_mode = mode || 'auto';
    saveGame();
    renderRoutes();
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
      marketing_spend_monthly: {},
      ltm_revenue: 0,
      revenue_history: [],
      daily_pnl: 0,
      events: [],
      milestones: [],
      game_over: false,
      paused_reason: null,
      onboarding_done: false,
      airline_emblem: pendingEmblem || 'wing',
    };
    sanitizeMarketingSpend();
    normalizeGameState();
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

  function networkRouteStats() {
    if (!state || !state.routes.length) {
      return { count: 0, profitable: 0, dailyPnl: 0, avgLoad: 0 };
    }
    let profitable = 0;
    let dailyPnl = 0;
    let loadSum = 0;
    let loadN = 0;
    state.routes.forEach((route) => {
      const r = simulateRouteDay(route);
      const pnl = r.revenue - r.cost;
      dailyPnl += pnl;
      if (pnl > 0) profitable += 1;
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
    };
  }

  function hashHue(str) {
    let h = 0;
    const s = String(str || 'Airline');
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    return h % 360;
  }

  function emblemGlyph(id) {
    const opts = bootstrap.emblem_options || [];
    const hit = opts.find((o) => o.id === id);
    return hit ? hit.glyph : '✈';
  }

  function airlineLogoHtml(name, emblemId, size) {
    const hue = hashHue(name);
    const glyph = emblemGlyph(emblemId);
    const sz = size || 36;
    const initials = String(name || 'A')
      .split(/\s+/)
      .map((w) => w[0])
      .join('')
      .slice(0, 2)
      .toUpperCase();
    return `<span class="airline-logo" style="width:${sz}px;height:${sz}px;background:linear-gradient(145deg,hsl(${hue},52%,38%),hsl(${hue},48%,24%))" title="${name}">
      <span class="airline-logo-glyph">${glyph}</span>
      <span class="airline-logo-init">${initials}</span>
    </span>`;
  }

  function defaultLeagueScope() {
    if (!state) return 'national';
    const sc = bootstrap.scenarios[state.scenario_id] || {};
    return sc.region === 'ohio' ? 'ohio' : 'national';
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
    return cfg.airlines || ['Delta', 'American', 'Southwest'];
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
    return Math.max(0, Math.min(100, rep * 0.45 + net.avgLoad * 28 + 18 - aogN * 6));
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
    return corp + brand + sales;
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

    const playerSteal = Object.keys(state.brand_awareness || {}).reduce((s, iata) => {
      const ap = airport(iata);
      if (!ap || !aps.find((x) => x.iata === iata)) return s;
      const inc = (ap.incumbents || []).find((c) => c.airline === name);
      if (!inc) return s;
      return s + (state.brand_awareness[iata] || 0) * inc.share * 0.35;
    }, 0);
    dailyPax = Math.max(0, dailyPax - playerSteal * 14);
    dailyGross = Math.max(0, dailyGross - playerSteal * 14 * 125);

    const riders = Math.round(dailyPax * 30);
    const gross = dailyGross * 30;
    const margin = 0.06 + prof.financial_health * 0.11;
    const overhead =
      (prof.marketing_overhead_mo || prof.national_scale * 50_000_000) *
      scopeOverheadWeight(scopeKey);
    const profit = Math.round(gross * margin - overhead);

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
      overhead: Math.round(overhead),
      routesInScope,
      airportPresence,
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
      emblem: null,
      overall: 0,
    };
  }

  function playerLeagueEntry(scopeKey) {
    ensureMetrics();
    const riders = estimateMonthlyRiders(scopeKey);
    const profit = playerScopedMonthlyProfit(scopeKey);
    const csat = Math.round(computeCsat());
    return {
      id: 'player',
      name: state.airline_name || 'You',
      isPlayer: true,
      profit,
      riders: riders || estimateMonthlyRiders(scopeKey),
      csat,
      overall: 0,
      emblem: state.airline_emblem || 'wing',
    };
  }

  function leaguePillarPercentile(entries, key, entry) {
    const sorted = [...entries].sort((a, b) => b[key] - a[key]);
    const idx = sorted.findIndex((e) => e.id === entry.id);
    if (idx < 0) return 0;
    return Math.round((1 - idx / Math.max(1, entries.length - 1)) * 100);
  }

  function leagueRiderPercentile(entries, entry) {
    const sorted = [...entries].sort((a, b) => b.riders - a.riders);
    const idx = sorted.findIndex((e) => e.id === entry.id);
    let pct = Math.round((1 - idx / Math.max(1, entries.length - 1)) * 100);
    if (entry.isPlayer) {
      pct = Math.round(pct * 0.82);
    } else {
      const scale = airlineProfile(entry.name)?.national_scale || 0.4;
      pct = Math.round(Math.min(100, pct * (0.9 + scale * 0.12)));
    }
    return pct;
  }

  function applyLeagueOverallScores(entries) {
    entries.forEach((e) => {
      const profitPct = leaguePillarPercentile(entries, 'profit', e);
      const riderPct = leagueRiderPercentile(entries, e);
      e.overall = Math.round(profitPct * 0.45 + riderPct * 0.35 + e.csat * 0.2);
    });
  }

  function buildLeagueTable(scopeKey) {
    if (!state) return [];
    const scope = scopeKey || getLeagueScope();
    const entries = [
      playerLeagueEntry(scope),
      ...leagueAirlineNames(scope).map((n) => competitorLeagueEntry(n, scope)),
    ];
    applyLeagueOverallScores(entries);
    entries.sort((a, b) => b.overall - a.overall);
    return entries.map((e, i) => ({ ...e, rank: i + 1, scope }));
  }

  function pillarMeter(score) {
    const filled = Math.max(0, Math.min(5, Math.round(score / 20)));
    return Array.from({ length: 5 }, (_, i) => `<span class="pillar-dot${i < filled ? ' on' : ''}"></span>`).join('');
  }

  function metricLeverTip(pillar) {
    const tips = {
      profit: 'Scoped route margin minus fleet, gates, and growing corporate overhead',
      riders: 'Marketing · OTAs · frequency · new routes',
      csat: 'Load factor · AOG · reputation · fare fairness',
    };
    return tips[pillar] || '';
  }

  function updateDailyMetrics(econ) {
    if (!state) return;
    ensureMetrics();
    let dayPax = 0;
    const share = { ...state.metrics.airport_share };
    state.routes.forEach((route) => {
      const r = simulateRouteDay(route);
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

    if (player && prev.player != null && player.rank < prev.player) {
      pushEvent(`League (${region}): ${state.airline_name} rose to <b>#${player.rank}</b> overall.`);
    } else if (player && prev.player != null && player.rank > prev.player) {
      pushEvent(`League (${region}): ${state.airline_name} slipped to <b>#${player.rank}</b> — rivals gained ground.`);
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
          <dt>CSAT (est.)</dt><dd>${stats.csat}</dd>
          <dt>Gross revenue (scope)</dt><dd>${fmtMoney(stats.gross)}</dd>
          <dt>Brand & overhead</dt><dd>${fmtMoney(stats.overhead)}/mo</dd>
          <dt>Financial health</dt><dd>${health}%</dd>
        </dl>
        <p class="muted" style="font-size:0.72rem;margin:10px 0 6px;">
          Giants carry heavy marketing and corporate overhead — strong brand, thin scoped profit. Your startup avoids most of that… for now.
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
        ${airlineLogoHtml(state.airline_name, state.airline_emblem, 40)}
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
      pillars.innerHTML = `
        <div class="pillar" title="${metricLeverTip('profit')}">
          <span class="pillar-label">Profit</span>${pillarMeter(profitMeter)}
          <span class="pillar-rank">${fmtMoney(player.profit)}/mo · #${profitRank}</span>
        </div>
        <div class="pillar" title="${metricLeverTip('riders')}">
          <span class="pillar-label">Riders</span>${pillarMeter(riderMeter)}
          <span class="pillar-rank">${player.riders.toLocaleString()}/mo · #${ridersRank}</span>
        </div>
        <div class="pillar" title="${metricLeverTip('csat')}">
          <span class="pillar-label">CSAT</span>${pillarMeter(player.csat)}
          <span class="pillar-rank">${player.csat} · #${csatRank}</span>
        </div>`;
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
    const scope = leagueScopeLabel(getLeagueScope());
    const rows = data
      .map((e) => {
        const trend =
          e.trend > 0 ? `<span class="trend-up">▲${e.trend}</span>` : e.trend < 0 ? `<span class="trend-down">▼${Math.abs(e.trend)}</span>` : '<span class="muted">—</span>';
        const rowClass = e.isPlayer ? 'you' : 'rival-row';
        const dataAttr = e.isPlayer ? '' : ` data-rival-name="${e.name}"`;
        return `<tr class="${rowClass}"${dataAttr}>
          <td>${e.rank}</td>
          <td>${airlineLogoHtml(e.name, e.emblem, 26)} <span>${e.name}</span></td>
          <td class="${e.profit < 0 ? 'danger' : ''}">${fmtMoney(e.profit)}</td>
          <td>${e.riders.toLocaleString()}</td>
          <td>${e.csat}</td>
          <td><b>${e.overall}</b></td>
          <td>${trend}</td>
        </tr>`;
      })
      .join('');
    panel.innerHTML = `
      <div class="scoreboard-panel-inner">
        <h3>League — ${scope}</h3>
        <p class="muted" style="font-size:0.75rem;margin-bottom:10px;">Monthly operating profit (est.), riders, and CSAT within the selected scope. Click a rival for intel.</p>
        <table class="scoreboard-table">
          <thead><tr><th>#</th><th>Airline</th><th>Profit/mo</th><th>Riders/mo</th><th>CSAT</th><th>Overall</th><th>Trend</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
        <p class="muted" style="font-size:0.72rem;margin-top:10px;"><b>Levers:</b> Profit — route margin minus overhead. Riders — frequency &amp; marketing (giants win on brand). CSAT — reliability, load, fair fares.</p>
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
    state.revenue_history = Array.isArray(state.revenue_history) ? state.revenue_history : [];
    state.marketing_spend_monthly = state.marketing_spend_monthly || {};
    state.brand_awareness = state.brand_awareness || {};
    if (!Number.isFinite(state.fuel_price)) {
      state.fuel_price = bootstrap.fuel_base || 2.85;
    }
    if (state.hour == null) state.hour = 8;
    if (!state.player_name) state.player_name = 'CEO';
    if (!state.airline_emblem) state.airline_emblem = 'wing';
    ensureMetrics();
    ensureMacro();
    ensureFleet();
  }

  function ensureFleet() {
    if (!state || !state.fleet) return;
    state.fleet.forEach((f) => {
      if (!f.id) f.id = uid('ac');
      const ac = aircraftType(f.type);
      if (!ac) return;
      if (f.seats == null) f.seats = ac.seats;
      if (f.leased == null) f.leased = true;
      if (!f.leased && f.life_months_left == null) {
        f.life_months_left = (ac.lifespan_years || 25) * 12;
      }
      if (f.leased && f.lease_months_left == null) {
        f.lease_months_left = 60;
      }
      if (f.aog_days_left == null) f.aog_days_left = 0;
      if (f.block_hours_month == null) f.block_hours_month = 0;
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
    });
    if (!state.competitor_markets) initCompetitorMarkets();
    if (!state.competitor_routes) initCompetitorRoutes();
    if (state.last_competitor_event_day == null) state.last_competitor_event_day = 0;
    if (state.onboarding_done == null) state.onboarding_done = true;
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

  function otaEffects() {
    ensureMacro();
    const m = state.macro;
    const penetration = m.ota_market_penetration_pct / 100;
    let demandBoost = 1;
    let revenueMult = 1;
    let marketingAmplify = 1;
    let listingCost = 0;

    (bootstrap.ota_platforms || []).forEach((p) => {
      if (!m.ota_listed[p.id]) return;
      let fee = p.listing_monthly;
      const promo = m.ota_promo && m.ota_promo[p.id];
      if (promo && promo.months_left > 0) fee *= 1 - (promo.discount || 0);
      listingCost += fee;
      const share = penetration * p.demand_reach;
      demandBoost += share;
      revenueMult *= 1 - (p.commission_pct / 100) * share * 0.85;
      marketingAmplify = Math.max(marketingAmplify, p.marketing_amplify);
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
    pushEvent(
      `US economy Y${Math.floor(state.day / 365) + 1}: inflation ${m.inflation_pct.toFixed(1)}%, ` +
        `GDP ${m.gdp_growth_pct >= 0 ? '+' : ''}${m.gdp_growth_pct.toFixed(1)}%, ` +
        `travel spend ${m.travel_spend_growth_pct >= 0 ? '+' : ''}${m.travel_spend_growth_pct.toFixed(1)}%, ` +
        `health ${m.country_health.toFixed(0)}/100`
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

  function pushEvent(msg) {
    state.events.unshift({ day: state.day, msg });
    if (state.events.length > 80) state.events.length = 80;
  }

  function monthlyDebtService() {
    return state.debt.reduce((s, d) => s + (d.monthly_payment || 0), 0);
  }

  function quarterlyBondCoupons() {
    return state.bonds.reduce((s, b) => s + (b.principal * b.coupon) / 4, 0);
  }

  function fleetMonthlyCosts() {
    return state.fleet.reduce((s, f) => {
      const ac = aircraftType(f.type);
      if (!ac) return s;
      if (f.leased) return s + (ac.lease_monthly || 0);
      return s + (ac.maintenance_monthly || 0);
    }, 0);
  }

  function gateLeaseMonthly() {
    return state.gates.reduce((s, g) => s + g.monthly, 0);
  }

  function marketingMonthly() {
    return Object.values(state.marketing_spend_monthly).reduce((a, b) => a + clampMoney(b), 0);
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

  function estimateRouteViability(originIata, destIata, aircraftTypeId, freq, fare) {
    const ac = aircraftType(aircraftTypeId);
    if (!ac) return { label: 'Unknown', tier: 'bad', load: 0, dailyPax: 0 };
    const mock = {
      origin: originIata,
      dest: destIata,
      aircraft_type: aircraftTypeId,
      frequency_week: freq,
      fare,
    };
    let demand = demandForRoute(mock);
    if (isCommonRoutePair(originIata, destIata)) demand *= 1.12;
    const seats = ac.seats_max || ac.seats;
    const dailySeats = seats * (freq / 7);
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
    return { label, tier, load, dailyPax, seats };
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
      const via = estimateRouteViability(originIata, dest.iata, acType, freq, fare);
      const common = isCommonRoutePair(originIata, dest.iata);
      const score = via.load * (common ? 1.15 : 1) * (dest.annual_pax_m + 1);
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

  function blockHours(distNm, ac) {
    return (distNm / 420) * 2 + 0.5;
  }

  function demandForRoute(route) {
    const o = airport(route.origin);
    const d = airport(route.dest);
    const ac = aircraftType(route.aircraft_type);
    if (!o || !d || !ac) return 0;
    const dist = routeDistance(route);
    if (dist > ac.range_nm) return 0;

    const wealth = (airportWealth(o) + airportWealth(d)) / 2;
    const luxury = (airportLuxury(o) + airportLuxury(d)) / 2;
    const regionalBoost = (o.regional || d.regional) && isSmallAircraft(route.aircraft_type) ? 1.14 : 1;
    const wealthBoost = 0.72 + wealth * 0.55;
    const luxuryBoost = 1 + luxury * 0.35;
    const base = Math.sqrt(o.metro_pop_m * d.metro_pop_m) * 1200 * regionalBoost * wealthBoost * luxuryBoost;
    const compPenalty =
      1 -
      (incumbentPressure(o) +
        incumbentPressure(d) +
        competitorFarePressure(o) +
        competitorFarePressure(d)) *
        0.34;
    const hubPenalty = Math.max(0.42, compPenalty);
    const freqBonus = Math.min(1.4, 0.7 + route.frequency_week / 28);
    const awareO = (state.brand_awareness[route.origin] || 5) / 100;
    const awareD = (state.brand_awareness[route.dest] || 5) / 100;
    const marketing = 0.5 + (awareO + awareD) / 2;
    const rep = 1 + state.reputation / 200;
    const buckets = routeFareBuckets(route);
    const fareProbe = { ...route, fare: buckets[0].fare };
    const fareFactor = fareDemandFactor(fareProbe, o, d);
    const overlap = 1 - competitorRouteOverlapPenalty(route);
    const reliability = (o.seasonal_reliability + d.seasonal_reliability) / 2;
    const macro = macroDemandMultiplier();
    const ota = otaEffects();
    const comfortFactor = 0.82 + ((ac.comfort_rating || 3) / 5) * 0.38;

    let demand =
      base * hubPenalty * overlap * freqBonus * marketing * rep * fareFactor * reliability * macro * ota.demandMult * comfortFactor;
    if (isCommonRoutePair(route.origin, route.dest)) demand *= 1.08;
    return demand;
  }

  function simulateRouteDay(route) {
    const ac = aircraftType(route.aircraft_type);
    if (!ac) return { revenue: 0, cost: 0, pax: 0, load: 0, ticketRev: 0, ancillaryRev: 0, grounded: false };
    const dist = routeDistance(route);
    if (dist > ac.range_nm) return { revenue: 0, cost: 0, pax: 0, load: 0, ticketRev: 0, ancillaryRev: 0, grounded: false };

    const plane = route.aircraft_id ? state.fleet.find((f) => f.id === route.aircraft_id) : null;
    if (plane && !isPlaneAvailable(plane)) {
      return { revenue: 0, cost: 0, pax: 0, load: 0, ticketRev: 0, ancillaryRev: 0, grounded: true };
    }
    const o = airport(route.origin);
    const d = airport(route.dest);
    const seats = plane ? fleetSeatCount(plane) : ac.seats;
    const flightsToday = route.frequency_week / 7;
    const dailySeats = seats * flightsToday;
    const demand = demandForRoute(route);
    const load = Math.min(0.92, demand / Math.max(dailySeats, 1));
    const pax = Math.floor(dailySeats * load);
    const ota = otaEffects();
    const ticketRev = bucketedTicketRevenue(route, pax) * ota.revenueMult;
    const ancillaryRev = pax * ancillaryPerPax(route, load, o, d) * ota.revenueMult;
    const revenue = ticketRev + ancillaryRev;

    const block = blockHours(dist, ac) * flightsToday;
    if (plane) {
      plane.block_hours_month = (plane.block_hours_month || 0) + block;
    }
    const fuel = block * ac.fuel_gal_hr * state.fuel_price;
    const crew = block * bootstrap.crew_cost_per_block_hour;
    const fees = flightsToday * bootstrap.airport_fee_per_departure * 2;
    const variable = fuel + crew + fees;

    return { revenue, cost: variable, pax, load, ticketRev, ancillaryRev, grounded: false };
  }

  function simulateDayEconomics() {
    let dayRev = 0;
    let dayCost = 0;
    state.routes.forEach((route) => {
      const r = simulateRouteDay(route);
      dayRev += r.revenue;
      dayCost += r.cost;
    });
    const dailyFixed =
      (fleetMonthlyCosts() + gateLeaseMonthly() + monthlyDebtService()) / 30 +
      marketingMonthly() / 30;
    const pnl = dayRev - dayCost - dailyFixed;
    return { dayRev, dayCost, dailyFixed, pnl };
  }

  function processDayRollover(dayRev, dayCost) {
    if (state.day % 30 === 0) {
      updateDynamicFares();
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
          state.brand_awareness[ap] = Math.min(
            100,
            (state.brand_awareness[ap] || 0) + (spend / 50000) * amp
          );
        }
      });
      const otaCost = otaListingMonthly();
      if (otaCost > 0) state.cash -= otaCost;
      if (state.reputation < 50 && state.routes.length > 0 && dayRev > dayCost) {
        state.reputation = Math.min(100, state.reputation + 0.3);
      }
      processMonthlyScoreboard();
      const retired = [];
      state.fleet = state.fleet.filter((f) => {
        if (f.leased) return true;
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

    if (state.day > 0 && state.day % 60 === 0) maybeCompetitorEvents();

    if (state.day > 0 && state.day % 90 === 0) processCompetitorAI();

    if (state.day > 0 && state.day % 365 === 0) advanceMacroYear();

    state.gates.forEach((g) => {
      if (state.day % 30 === 0) g.months_left = (g.months_left || g.years_left * 12) - 1;
    });
  }

  function checkSurvivalTriggers() {
    if (state.cash < 0 && !state.milestones.includes('chapter11_warn')) {
      state.milestones.push('chapter11_warn');
      pushEvent('CRITICAL: Negative cash. Raise capital or cut burn.');
      setSpeed('pause');
      state.paused_reason = 'Cash below zero';
    }
    if (state.cash < -2_000_000) {
      state.game_over = true;
      pushEvent('BANKRUPTCY — game over.');
      setSpeed('pause');
    }
    if (runwayMonths() < 2 && state.cash > 0 && !state.milestones.includes('runway_warn')) {
      state.milestones.push('runway_warn');
      pushEvent(`Cash runway under 2 months (${runwayMonths().toFixed(1)} mo).`);
      setSpeed('pause');
      state.paused_reason = 'Low runway';
    }
  }

  function tickDays(n) {
    if (!state || state.game_over || n <= 0) return;

    for (let i = 0; i < n; i++) {
      state.day += 1;
      const econ = simulateDayEconomics();
      const interest = accrueCashInterest(1);
      state.daily_pnl = econ.pnl + interest;
      state.cash += econ.pnl;
      updateDailyMetrics(econ);
      processDayRollover(econ.dayRev, econ.dayCost);
      checkSurvivalTriggers();
      if (state.game_over || state.paused_reason) break;
    }
    saveGame();
    renderAll();
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
      processDayRollover(econ.dayRev, econ.dayCost);
      checkSurvivalTriggers();
      if (state.game_over || state.paused_reason) break;
    }

    saveGame();
    if (dayAdvanced) renderAll();
    else renderHud();
  }

  function resolveSpeedId(speedId) {
    if (speedId === 'year') return 'month';
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
    const hint = $('speed-hint');
    if (hint) {
      const labels = {
        pause: 'Paused',
        slow: '4-hour steps',
        day: '1 day / tick',
        week: '1 week / tick',
        month: '1 month / tick',
      };
      hint.textContent = labels[speedId] || '';
    }
  }

  function hasGateAt(iata) {
    return state.gates.some((g) => g.airport === iata);
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
    pushPlayerEvent(`leased ${tier} gate at ${iata} (${years}yr).`);
    saveGame();
    renderAll();
  }

  function selectFleetOffer(type, mode) {
    const ac = aircraftType(type);
    fleetShopOpen = true;
    fleetPending = {
      type,
      mode,
      seats: ac.seats,
    };
    renderFleet();
  }

  function cancelFleetOffer() {
    fleetPending = null;
    renderFleet();
  }

  function setFleetPendingSeats(val) {
    if (!fleetPending) return;
    const ac = aircraftType(fleetPending.type);
    fleetPending.seats = aircraftSeats(fleetPending.type, +val);
    renderFleet();
  }

  function confirmFleetOffer() {
    if (!fleetPending) return;
    const { type, mode, seats } = fleetPending;
    const ac = aircraftType(type);
    const seatCount = aircraftSeats(type, seats);

    if (mode === 'lease') {
      const deposit = ac.lease_monthly * 2;
      if (state.cash < deposit) {
        alert(`Insufficient cash — need ${fmtMoney(deposit)} deposit for lease.`);
        return;
      }
      if (!confirm(`Lease ${ac.name} (${seatCount} seats)?\n\nDeposit: ${fmtMoney(deposit)}\nMonthly: ${fmtMoney(ac.lease_monthly)}\nComfort: ${comfortStars(ac.comfort_rating)}`)) {
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
      });
      pushPlayerEvent(`leased ${ac.name} (${seatCount} seats).`);
    } else {
      if (state.cash < ac.purchase) {
        alert(`Insufficient cash — need ${fmtMoney(ac.purchase)} to purchase.`);
        return;
      }
      if (!confirm(`Purchase ${ac.name} (${seatCount} seats)?\n\nPrice: ${fmtMoney(ac.purchase)}\nMaintenance: ${fmtMoney(ac.maintenance_monthly)}/mo\nUseful life: ${ac.lifespan_years} years\nComfort: ${comfortStars(ac.comfort_rating)}`)) {
        return;
      }
      state.cash -= ac.purchase;
      state.fleet.push({
        id: uid('ac'),
        type,
        seats: seatCount,
        leased: false,
        life_months_left: (ac.lifespan_years || 25) * 12,
        aog_days_left: 0,
        block_hours_month: 0,
      });
      pushPlayerEvent(`purchased ${ac.name} (${seatCount} seats).`);
    }
    fleetPending = null;
    saveGame();
    renderAll();
  }

  function openRoute(origin, dest, aircraftId, freq, fare) {
    if (!hasGateAt(origin)) {
      alert(`You need a gate at ${origin} first. Lease one in the airport panel.`);
      return;
    }
    if (state.routes.some((r) => r.origin === origin && r.dest === dest)) {
      alert(`You already fly ${origin}–${dest}. Adjust frequency or fares on the active route card.`);
      return;
    }
    const plane = state.fleet.find((f) => f.id === aircraftId);
    if (!plane) {
      alert('Select an aircraft from your fleet (Fleet tab → add a plane if needed).');
      return;
    }
    const dist = haversineNm(
      airport(origin).lat,
      airport(origin).lon,
      airport(dest).lat,
      airport(dest).lon
    );
    const ac = aircraftType(plane.type);
    if (dist > ac.range_nm) {
      alert(`Route exceeds ${ac.name} range (${Math.round(dist)} nm).`);
      return;
    }
    const marketFare = marketFareForPair(origin, dest, plane.type);
    state.routes.push({
      id: uid('rt'),
      origin,
      dest,
      aircraft_type: plane.type,
      frequency_week: freq,
      fare: fare || marketFare,
      market_fare: marketFare,
      fare_mode: 'auto',
      ancillary_mode: 'auto',
      aircraft_id: aircraftId,
    });
    pushPlayerEvent(`opened ${origin}–${dest} (${freq}x/wk @ $${fare}).`);
    selectAirport(origin);
    saveGame();
    renderAll();
  }

  function raiseSeed() {
    const opt = bootstrap.financing_options.seed_equity;
    if (!opt.tiers.includes(state.financing_tier)) return;
    const amount = 4_500_000;
    const dilution = 0.22;
    state.cash += amount;
    state.equity_pct *= 1 - dilution;
    pushEvent(`Seed round closed: ${fmtMoney(amount)} (${(dilution * 100).toFixed(0)}% dilution).`);
    saveGame();
    renderAll();
  }

  function raiseGrowthEquity() {
    if (state.financing_tier !== 'serial') return;
    const amount = 40_000_000;
    const dilution = 0.15;
    state.cash += amount;
    state.equity_pct *= 1 - dilution;
    pushEvent(`Growth equity: ${fmtMoney(amount)} (${(dilution * 100).toFixed(0)}% dilution).`);
    saveGame();
    renderAll();
  }

  function takeBankLoan() {
    const amount = state.financing_tier === 'serial' ? 20_000_000 : 8_000_000;
    const rate = state.financing_tier === 'distressed' ? 0.11 : 0.085;
    const monthly = (amount * (rate / 12)) / (1 - Math.pow(1 + rate / 12, -60));
    state.cash += amount;
    state.debt.push({
      id: uid('debt'),
      name: 'Bank term loan',
      principal: amount,
      rate,
      monthly_payment: monthly,
      secured: false,
    });
    pushEvent(`Bank loan: ${fmtMoney(amount)} @ ${(rate * 100).toFixed(1)}%.`);
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
    pushEvent(`Bond issuance: ${fmtMoney(amount)} @ ${(coupon * 100).toFixed(1)}% coupon.`);
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
    pushEvent(`Asset-backed bonds: ${fmtMoney(amount)}.`);
    saveGame();
    renderAll();
  }

  function restructureDebt() {
    const d = state.debt.find((x) => x.id === 'inherit_term');
    if (!d) return;
    d.monthly_payment = 185_000;
    d.rate = 0.078;
    pushEvent('Creditors agreed to restructured payments (-30% monthly).');
    saveGame();
    renderAll();
  }

  function applyMarketing(iata) {
    const input = $(`mkt-input-${iata}`);
    const v = clampMoney(input ? input.valueAsNumber : 0);
    state.marketing_spend_monthly[iata] = v;
    saveGame();
    renderAirportPanel(iata);
    pushPlayerEvent(`set marketing at ${iata} to ${fmtMoney(v)}/mo`);
    renderEvents();
    return v;
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
    mapboxMap.addLayer({
      id: 'player-routes-layer',
      type: 'line',
      source: 'player-routes',
      paint: {
        'line-color': '#ffd166',
        'line-width': 2,
        'line-opacity': 0.7,
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
          selectAirport(ev.features[0].properties.iata);
        }
      });
      mapboxMap.on('mouseenter', 'airports-layer', () => {
        if (mapboxMap) mapboxMap.getCanvas().style.cursor = 'pointer';
      });
      mapboxMap.on('mouseleave', 'airports-layer', () => {
        if (mapboxMap) mapboxMap.getCanvas().style.cursor = 'grab';
      });
    });
  }

  function buildRoutesGeoJSON(routes) {
    const features = [];
    (routes || []).forEach((route) => {
      const o = airport(route.origin);
      const d = airport(route.dest);
      if (!o || !d) return;
      features.push({
        type: 'Feature',
        geometry: {
          type: 'LineString',
          coordinates: [
            [o.lon, o.lat],
            [d.lon, d.lat],
          ],
        },
        properties: { origin: route.origin, dest: route.dest },
      });
    });
    return { type: 'FeatureCollection', features };
  }

  function buildAirportsGeoJSON() {
    const labelAll = activeMapKey === 'ohio';
    const airportFeatures = [];
    const haloFeatures = [];

    bootstrap.airports.forEach((ap) => {
      const owned = state && hasGateAt(ap.iata);
      const selected = selectedAirport === ap.iata;
      const share = playerShareAtAirport(ap.iata);
      const fill = owned ? '#00e4a8' : ap.hub_strength > 0.7 ? '#ff6b5a' : '#5eb8ff';
      const r = owned || selected ? 6 : 4 + Math.min(3, ap.annual_pax_m / 25);

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
          fill,
          stroke: selected ? '#fff' : owned ? '#042' : 'rgba(255,255,255,0.45)',
          strokeWidth: selected ? 2 : 1.2,
          showLabel: owned || selected || labelAll,
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
      mapboxMap.getSource('player-routes').setData(buildRoutesGeoJSON(state.routes));
      mapboxMap
        .getSource('competitor-routes')
        .setData(buildRoutesGeoJSON(state.competitor_routes));
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
      if (!mapDrag.moved && mapDrag.clickIata) selectAirport(mapDrag.clickIata);
      mapDrag.active = false;
      mapDrag.pointerId = null;
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
      const dot = e.target.closest && e.target.closest('.ap-dot');
      mapDrag.clickIata = dot ? dot.dataset.iata : null;
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
        html += `<line x1="${p1.x}" y1="${p1.y}" x2="${p2.x}" y2="${p2.y}" stroke="#ffd166" stroke-width="2" opacity="0.7" stroke-linecap="round"/>`;
      });
      html += '</g>';
    }

    const labelAll = activeMapKey === 'ohio';
    html += '<g class="map-airports">';
    bootstrap.airports.forEach((ap) => {
      const p = projectMap(ap.lat, ap.lon);
      const owned = state && hasGateAt(ap.iata);
      const selected = selectedAirport === ap.iata;
      const share = playerShareAtAirport(ap.iata);
      const fill = owned ? '#00e4a8' : ap.hub_strength > 0.7 ? '#ff6b5a' : '#5eb8ff';
      const r = owned || selected ? 6 : 4 + Math.min(3, ap.annual_pax_m / 25);
      const stroke = selected ? '#fff' : owned ? '#042' : 'rgba(255,255,255,0.45)';
      if (share > 0.08) {
        const halo = r + 3 + share * 8;
        html += `<circle cx="${p.x}" cy="${p.y}" r="${halo}" fill="none" stroke="rgba(0,228,168,${0.15 + share * 0.45})" stroke-width="2" class="ap-share-ring"/>`;
      }
      html += `<circle cx="${p.x}" cy="${p.y}" r="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${selected ? 2 : 1.2}" class="ap-dot" data-iata="${ap.iata}" style="cursor:pointer"/>`;
      if (owned || selected || labelAll) {
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
    const routesFrom = state.routes.filter((r) => r.origin === iata);
    const compRoutes = competitorRoutesAt(iata);
    const hasCompetition = (ap.incumbents && ap.incumbents.length) || compRoutes.length > 0;

    airportSections = {
      market: false,
      competition: !!gate && hasCompetition,
      position: !gate || !hasCompetition,
    };
    if (!gate) airportSections.position = true;

    if (routesFrom.length) {
      switchTab('routes');
    } else if (!gate) {
      scheduleContextPulse('#ap-section-position');
    } else if (hasCompetition) {
      scheduleContextPulse('#ap-section-competition');
    }
  }

  function scheduleContextPulse(selector, scrollParent) {
    if (contextPulseTimer) clearTimeout(contextPulseTimer);
    requestAnimationFrame(() => {
      const el = document.querySelector(selector);
      if (!el) return;
      if (scrollParent) {
        const parent = document.querySelector(scrollParent);
        if (parent && parent.scrollIntoView) {
          try {
            el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
          } catch (e) {
            el.scrollIntoView();
          }
        }
      }
      el.classList.remove('context-pulse');
      void el.offsetWidth;
      el.classList.add('context-pulse');
      contextPulseTimer = setTimeout(() => el.classList.remove('context-pulse'), 2400);
    });
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
    selectedAirport = iata;
    const routesFrom = state.routes.filter((r) => r.origin === iata);
    applyAirportContext(iata);
    renderAirportPanel(iata);
    drawMap();
    const routesPanel = $('panel-routes');
    if (routesPanel && routesPanel.classList.contains('active')) {
      renderRoutes();
      if (routesFrom.length) scheduleContextPulse(`.route-card[data-origin="${iata}"]`, '#panel-routes');
    }
  }

  function renderAirportPanel(iata) {
    const ap = airport(iata);
    const panel = $('airport-panel');
    if (!ap || !panel) return;
    const gate = state.gates.find((g) => g.airport === iata);
    const compRoutes = competitorRoutesAt(iata);

    const marketBody = `
      <dl class="stat-dl">
        <dt>Wealth index</dt><dd>${(airportWealth(ap) * 100).toFixed(0)}</dd>
        <dt>Metro pop</dt><dd>${ap.metro_pop_m}M</dd>
        <dt>Top carrier</dt><dd>${ap.hub_airline || '—'} (${(ap.hub_strength * 100).toFixed(0)}%)</dd>
        <dt>Gates open</dt><dd>${ap.gates_available} of ${ap.gates_total}</dd>
      </dl>
      <p class="muted" style="font-size:0.72rem;margin-top:6px;">Annual pax ${ap.annual_pax_m}M · Luxury ${(airportLuxury(ap) * 100).toFixed(0)}% · Slots ${ap.slot_controlled ? 'controlled' : 'open'}</p>`;

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

    const positionBody = `
      <dl class="stat-dl">
        <dt>Your gate</dt><dd>${gate ? `${gate.tier} ($${gate.monthly.toLocaleString()}/mo)` : '<span class="danger">None — lease below</span>'}</dd>
        <dt>Brand awareness</dt><dd>${(state.brand_awareness[iata] || 0).toFixed(0)}%</dd>
      </dl>
      ${
        gate
          ? ''
          : `<div class="btn-row" style="margin-top:8px;">
        <button class="btn" onclick="Runway.leaseGate('${iata}','common',3)">Common-use (3yr)</button>
        <button class="btn secondary" onclick="Runway.leaseGate('${iata}','exclusive',5)">Exclusive (5yr)</button>
      </div>`
      }
      <div class="mkt-box" style="margin-top:10px;padding-top:10px;">
        <label for="mkt-input-${iata}">Marketing $/mo
          <input type="number" id="mkt-input-${iata}" min="0" step="1000" value="${clampMoney(state.marketing_spend_monthly[iata])}">
        </label>
        <p class="muted" style="font-size:0.72rem;margin:6px 0;">Active: <b>${fmtMoney(clampMoney(state.marketing_spend_monthly[iata]))}/mo</b></p>
        <button type="button" class="btn" onclick="Runway.applyMarketing('${iata}')">Apply budget</button>
      </div>`;

    panel.innerHTML = `
      <h3>${ap.iata} — ${ap.city}${ap.regional ? '<span class="badge-regional">Regional</span>' : ''}</h3>
      <p class="muted" style="font-size:0.75rem;margin-bottom:4px;">${ap.name}${ap.state ? ` · ${ap.state}` : ''}</p>
      ${panelSectionHtml('market', 'Market snapshot', airportSections.market, marketBody)}
      ${panelSectionHtml('competition', 'Competition', airportSections.competition, competitionBody)}
      ${panelSectionHtml('position', gate ? 'Your position' : 'Lease a gate', airportSections.position, positionBody)}
    `;
    bindAirportPanelToggles();
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

  function renderHud() {
    if (!state) return;
    setText('hud-cash', fmtMoney(state.cash));
    const runwayText = state.cash < 0 ? 'BANKRUPT' : `${runwayMonths().toFixed(1)} mo`;
    setText('hud-runway', runwayText);
    const showClock = state.speed === 'slow' || state.hour != null;
    setText('hud-date', fmtDate(state.day, showClock ? (state.hour ?? 8) : null));
    setText('hud-equity', `${(state.equity_pct || 0).toFixed(1)}%`);
    setText('hud-rep', (state.reputation || 0).toFixed(0));
    setText('hud-fuel', `$${(state.fuel_price || 0).toFixed(2)}/gal`);
    setText('hud-pnl', fmtMoney(state.daily_pnl));
    const identity = state.player_name
      ? `CEO ${state.player_name} · ${state.airline_name || 'Airline'}`
      : state.airline_name || 'Airline';
    setText('hud-airline', identity);
    setText('hud-networth', fmtMoney(computeNetWorth()));
    setText('hud-ltm', fmtMoney(state.ltm_revenue));

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
    let html = `<h3>Market — ${m.country}</h3>
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

  function renderFinance() {
    const el = $('tab-finance');
    if (!el) return;
    const tier = state.financing_tier;
    const nw = computeNetWorthBreakdown() || {
      total: 0, equity_value: 0, cash: 0, fleet: 0, gates: 0, brand: 0, routes: 0, debt: 0, bonds: 0, lease_liabilities: 0,
    };
    let html = `<h3>Capital</h3>
      <p>Debt: ${state.debt.map((d) => `${d.name} ${fmtMoney(d.principal)} @ ${(d.rate * 100).toFixed(1)}%`).join('<br>') || 'None'}</p>
      <p>Bonds: ${state.bonds.map((b) => `${b.name} ${fmtMoney(b.principal)} coupon ${(b.coupon * 100).toFixed(1)}%`).join('<br>') || 'None'}</p>
      <p class="muted">Bond rating: ${state.bond_rating || 'N/A'} · Monthly burn ~${fmtMoney(burnMonthly())}</p>
      <p class="muted">Idle cash yield: <b>${(cashInterestAnnualRate() * 100).toFixed(2)}%</b>/yr (nominal, inflation-linked, never negative)</p>
      <h4>Net worth</h4>
      <dl class="stat-dl">
        <dt>Total net worth</dt><dd><b>${fmtMoney(nw.total)}</b></dd>
        <dt>Your equity (${(state.equity_pct || 0).toFixed(1)}%)</dt><dd>${fmtMoney(nw.equity_value)}</dd>
        <dt>Cash</dt><dd>${fmtMoney(nw.cash)}</dd>
        <dt>Fleet value</dt><dd>${fmtMoney(nw.fleet)}</dd>
        <dt>Gate rights</dt><dd>${fmtMoney(nw.gates)}</dd>
        <dt>Brand</dt><dd>${fmtMoney(nw.brand)}</dd>
        <dt>Route network</dt><dd>${fmtMoney(nw.routes)}</dd>
        <dt>Debt</dt><dd>-${fmtMoney(nw.debt)}</dd>
        <dt>Bonds</dt><dd>-${fmtMoney(nw.bonds)}</dd>
        <dt>Lease liabilities</dt><dd>-${fmtMoney(nw.lease_liabilities)}</dd>
      </dl>
      <p class="muted" style="font-size:0.75rem;">Valuation is approximate — partial stake sales and full exit coming later.</p>
      <div class="btn-row">`;
    if (tier === 'startup') {
      html += `<button class="btn" onclick="Runway.raiseSeed()">Close seed round (~$4.5M)</button>`;
    }
    if (tier === 'serial') {
      html += `<button class="btn" onclick="Runway.raiseGrowthEquity()">Growth equity (~$40M)</button>`;
    }
    html += `<button class="btn secondary" onclick="Runway.takeBankLoan()">Bank term loan</button>`;
    if (tier === 'distressed') {
      html += `<button class="btn secondary" onclick="Runway.issueAssetBackedBonds()">Asset-backed bonds</button>`;
      html += `<button class="btn secondary" onclick="Runway.restructureDebt()">Restructure inherited debt</button>`;
    }
    html += `<button class="btn secondary" onclick="Runway.issueCorporateBonds()">Corporate bonds (needs revenue)</button>`;
    html += `</div>`;
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
        const aog = f.aog_days_left > 0 ? ` <span class="danger">AOG ${f.aog_days_left}d</span>` : '';
        const utilBarClass = util < 40 ? 'util-bad' : util > 85 ? '' : 'util-warn';
        const assigned = state.routes.filter((r) => r.aircraft_id === f.id).length;
        html += `<div class="fleet-owned-card">
          <strong>${ac.name}</strong>${aog}
          <span class="muted">${seats} seats · ${f.leased ? 'Leased' : 'Owned'} · ${life}</span>
          <span class="muted">${ac.range_nm} nm · ${assigned} route${assigned === 1 ? '' : 's'}</span>
          <span class="muted" style="font-size:0.7rem;">Util ${util.toFixed(0)}% MTD · ${utilToday.toFixed(0)}% today</span>
          <div class="util-bar ${utilBarClass}"><span style="width:${Math.min(100, util)}%"></span></div>
        </div>`;
      });
      html += '</div>';
      html +=
        '<p class="muted" style="font-size:0.72rem;">Leased aircraft bill monthly even when <b>AOG</b>. Match size to route demand.</p>';
    }

    html += `<div class="btn-row">
      <button type="button" class="btn ${fleetShopOpen ? 'secondary' : ''}" onclick="Runway.toggleFleetShop()">${fleetShopOpen ? 'Hide aircraft shop' : '+ Lease / Buy aircraft'}</button>
    </div>`;

    if (fleetShopOpen) {
      html += `<div class="fleet-shop-panel">
        <p class="muted" style="font-size:0.75rem;margin-bottom:8px;">Choose type → set seats → confirm.</p>
        <div class="fleet-grid">`;
      Object.keys(bootstrap.aircraft_types || {}).forEach((tid) => {
        const ac = aircraftType(tid);
        if (!ac) return;
        const active = fleetPending && fleetPending.type === tid;
        html += `<div class="fleet-card ${active ? 'active' : ''}">
          <strong>${ac.name}</strong>
          <span class="muted">${ac.category} · ${ac.size}</span>
          <span>${ac.seats_min}–${ac.seats_max} seats · ${ac.range_nm} nm</span>
          <span>Lease ${fmtMoney(ac.lease_monthly)}/mo · Buy ${fmtMoney(ac.purchase)}</span>
          <div class="btn-row">
            <button class="btn secondary" onclick="Runway.selectFleet('${tid}','lease')">Lease…</button>
            <button class="btn secondary" onclick="Runway.selectFleet('${tid}','buy')">Buy…</button>
          </div>
        </div>`;
      });
      html += '</div></div>';
    }

    if (fleetPending) {
      const ac = aircraftType(fleetPending.type);
      html += `<div class="fleet-confirm">
        <h4>Confirm ${fleetPending.mode === 'lease' ? 'lease' : 'purchase'}: ${ac.name}</h4>
        <label>Seats (${ac.seats_min}–${ac.seats_max})
          <input type="number" min="${ac.seats_min}" max="${ac.seats_max}" value="${fleetPending.seats}"
            oninput="Runway.setFleetSeats(this.value)">
        </label>
        <div class="btn-row">
          <button class="btn" onclick="Runway.confirmFleet()">Confirm ${fleetPending.mode === 'lease' ? 'lease' : 'purchase'}</button>
          <button class="btn secondary" onclick="Runway.cancelFleet()">Cancel</button>
        </div>
      </div>`;
    }
    el.innerHTML = html;
  }

  function renderRoutes() {
    const el = $('tab-routes');
    if (!el) return;
    const defOrigin = defaultRouteOrigin();
    const defAp = airport(defOrigin);
    const defLabel = defAp ? airportLabel(defAp) : '';

    const net = networkRouteStats();
    let html = '<h3>Routes</h3>';
    if (net.count) {
      const pnlClass = net.dailyPnl >= 0 ? 'chip-pnl-pos' : 'chip-pnl-neg';
      html += `<div class="panel-card" style="margin-bottom:10px;padding:10px 11px;">
        <p style="font-size:0.78rem;margin:0 0 6px;color:var(--gold);font-weight:600;">Network snapshot</p>
        <p style="font-size:0.75rem;margin:0;line-height:1.45;">
          <span class="${pnlClass}"><b>${fmtMoney(net.dailyPnl)}/day</b></span> route P&L ·
          <b>${net.profitable}/${net.count}</b> profitable ·
          avg load <b>${(net.avgLoad * 100).toFixed(0)}%</b>
        </p>
        <p class="muted" style="font-size:0.68rem;margin:6px 0 0;">Unprofitable routes can still make sense short-term to pressure weak competitors — check their health in the airport Competition card.</p>
      </div>`;
    }
    html += '<p class="ops-section-title">Running now</p>';
    if (!state.routes.length) {
      html += '<p class="muted" style="font-size:0.78rem;">No routes yet — launch one below from your gate.</p>';
    } else {
      html += '<div class="route-list">';
      state.routes.forEach((route) => {
        const r = simulateRouteDay(route);
        const pnl = r.revenue - r.cost;
        const loadNum = r.grounded ? null : r.load;
        const loadLabel = r.grounded ? 'AOG' : Number.isFinite(loadNum) ? `${(loadNum * 100).toFixed(0)}% load` : '—';
        const loadClass = r.grounded
          ? 'chip-load-bad'
          : loadNum >= 0.7
            ? 'chip-load-good'
            : loadNum >= 0.45
              ? 'chip-load-warn'
              : 'chip-load-bad';
        const market = marketFareForPair(route.origin, route.dest, route.aircraft_type);
        const mode = route.fare_mode === 'manual' ? 'manual' : 'auto';
        const anc = route.ancillary_mode || 'auto';
        const revPerPax = r.pax > 0 ? Math.round(r.revenue / r.pax) : 0;
        const buckets = routeFareBuckets(route);
        const bucketHint = buckets.map((b) => `$${b.fare}`).join(' / ');
        const pnlClass = pnl >= 0 ? 'chip-pnl-pos' : 'chip-pnl-neg';
        html += `<div class="route-card" data-origin="${route.origin}" data-dest="${route.dest}">
          <div class="route-card-head">
            <strong>${route.origin}–${route.dest}</strong>
            <span class="${loadClass}" style="font-size:0.72rem;font-weight:600;">${loadLabel}</span>
          </div>
          <div class="route-card-meta">
            <span>${route.frequency_week}/wk</span>
            <span class="${pnlClass}">${fmtMoney(pnl)}/day</span>
            <span class="muted">$${revPerPax}/pax · mkt $${market}</span>
          </div>
          <div class="route-card-controls">
            <label>Fare $ (${mode})
              <input type="number" min="49" max="899" value="${route.fare}"
                onchange="Runway.setRouteFare('${route.id}', this.value, 'manual')" title="Buckets: ${bucketHint}">
            </label>
            <label>Ancillary
              <select onchange="Runway.setRouteAncillary('${route.id}', this.value)">
                <option value="auto" ${anc === 'auto' ? 'selected' : ''}>Auto</option>
                <option value="aggressive" ${anc === 'aggressive' ? 'selected' : ''}>Heavy</option>
                <option value="minimal" ${anc === 'minimal' ? 'selected' : ''}>Min</option>
              </select>
            </label>
          </div>
          <p class="route-card-hint muted">Buckets: ${bucketHint}</p>
        </div>`;
      });
      html += '</div>';
    }

    const fleetOpts = state.fleet.length
      ? state.fleet
          .map((f) => {
            const ac = aircraftType(f.type);
            const label = ac ? ac.name : f.type || 'Aircraft';
            return `<option value="${f.id}">${label} (${fleetSeatCount(f)} seats)</option>`;
          })
          .join('')
      : '<option value="">— add aircraft in Fleet tab —</option>';

    html += `<p class="ops-section-title">Launch route</p>
      <p class="muted" style="font-size:0.75rem;">Origin follows your map selection (<b>${defOrigin}</b>). Try a suggestion first.</p>
      <div id="route-suggestions"></div>
      <datalist id="airport-list">${airportDatalistHtml()}</datalist>
      <div id="route-preview" class="route-preview muted"></div>
      <div class="form-grid">
        <label>Origin
          <input type="text" id="rt-origin-search" list="airport-list" placeholder="DAY — Dayton" value="${defLabel}">
          <input type="hidden" id="rt-origin-code" value="${defOrigin}">
        </label>
        <label>Destination
          <input type="text" id="rt-dest-search" list="airport-list" placeholder="CVG — Cincinnati">
          <input type="hidden" id="rt-dest-code" value="">
        </label>
        <label>Aircraft
          <select id="rt-aircraft">${fleetOpts}</select>
        </label>
        <label>Freq/wk <input id="rt-freq" type="number" value="7" min="1" max="28"></label>
        <label>Fare $
          <input id="rt-fare" type="number" value="129" min="49" max="899">
        </label>
      </div>
      <div class="launch-route-sticky">
        <button class="btn" onclick="Runway.submitRoute()">Launch route</button>
      </div>`;
    el.innerHTML = html;
    bindRouteAirportInputs();
    renderRouteSuggestions();
    updateRoutePreview();
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
    const hasGate = hasGateAt(origin);
    const ideas = routeSuggestionsFrom(origin);
    if (!ideas.length) {
      box.innerHTML = '<p class="muted">No viable destinations in range from this airport.</p>';
      return;
    }
    let html = `<h4 style="margin:12px 0 6px;font-size:0.88rem;color:var(--gold);">Popular from ${origin}${oAp ? ` (${oAp.city})` : ''}</h4>`;
    if (!hasGate) {
      html += `<p class="muted" style="font-size:0.75rem;margin-bottom:8px;">You need a gate at ${origin} before launching.</p>`;
    }
    html += '<ul class="route-suggest-list">';
    ideas.forEach((s) => {
      const fleetPlane = state.fleet.find((f) => f.type === s.acType);
      const fleetNote = fleetPlane ? '' : ' <span class="muted">(not in fleet)</span>';
      const launchLabel = hasGate && fleetPlane ? 'Launch' : 'Plan';
      html += `<li>
        <button type="button" class="route-suggest-btn" data-tier="${s.tier}"
          onclick="Runway.applyRouteSuggestion('${s.dest}','${s.acType}',${s.fare},${s.freq},${hasGate && fleetPlane ? 'true' : 'false'})">
          <span class="rs-route">${launchLabel}: ${origin} → ${s.dest} <span class="muted">${s.destCity}</span>${s.common ? ' <span class="badge-regional">Common</span>' : ''}</span>
          <span class="rs-meta">${s.dist} nm · ${s.acName}${fleetNote} · ~${s.dailyPax} pax/day</span>
          <span class="rs-via via-${s.tier}">${s.label} (${(s.load * 100).toFixed(0)}% est. load)</span>
        </button>
      </li>`;
    });
    html += '</ul>';
    box.innerHTML = html;
  }

  function updateRoutePreview() {
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
    const via = estimateRouteViability(oCode, dCode, acType, freq, fare);
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
    el.innerHTML = `<strong>Preview:</strong> ${dist} nm · ${ac ? ac.name : acType} · ${via.label} · ~${via.dailyPax} pax/day at $${fare} (${(via.load * 100).toFixed(0)}% load) · market $${market} · wealth ${wealth}`;
  }

  function applyRouteSuggestion(destIata, acType, fare, freq, autoLaunch) {
    const dAp = airport(destIata);
    if (!dAp) return;
    const origin = ($('rt-origin-code') && $('rt-origin-code').value) || defaultRouteOrigin();
    const destInput = $('rt-dest-search');
    const destCode = $('rt-dest-code');
    if (destInput) destInput.value = airportLabel(dAp);
    if (destCode) destCode.value = destIata;
    const fareInput = $('rt-fare');
    const freqInput = $('rt-freq');
    if (fareInput) fareInput.value = fare;
    if (freqInput) freqInput.value = freq;
    const plane = state.fleet.find((f) => f.type === acType) || state.fleet[0];
    const acSelect = $('rt-aircraft');
    if (acSelect && plane) acSelect.value = plane.id;
    updateRoutePreview();

    const shouldLaunch = autoLaunch === true || autoLaunch === 'true';
    if (shouldLaunch && origin && plane) {
      if (!hasGateAt(origin)) {
        alert(`Lease a gate at ${origin} before launching this route.`);
        selectAirport(origin);
        return;
      }
      openRoute(origin, destIata, plane.id, freq, fare);
      return;
    }
    document.querySelector('[data-tab="routes"]')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  function bindRouteAirportInputs() {
    const bind = (inputId, hiddenId, onSync) => {
      const input = $(inputId);
      const hidden = $(hiddenId);
      if (!input || !hidden) return;
      const sync = () => {
        const ap = resolveAirportQuery(input.value);
        hidden.value = ap ? ap.iata : '';
        if (onSync) onSync();
      };
      input.addEventListener('change', sync);
      input.addEventListener('blur', sync);
      input.addEventListener('input', () => {
        window.clearTimeout(input._rtDebounce);
        input._rtDebounce = window.setTimeout(sync, 280);
      });
    };
    const refresh = () => {
      renderRouteSuggestions();
      updateRoutePreview();
    };
    bind('rt-origin-search', 'rt-origin-code', refresh);
    bind('rt-dest-search', 'rt-dest-code', updateRoutePreview);
    ['rt-aircraft', 'rt-freq', 'rt-fare'].forEach((id) => {
      const el = $(id);
      if (el) el.addEventListener('input', updateRoutePreview);
      if (el) el.addEventListener('change', updateRoutePreview);
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
    el.innerHTML = `<ul class="list">${state.events.map((e) => `<li><span class="muted">${fmtDate(e.day)}</span> ${e.msg}</li>`).join('')}</ul>`;
  }

  function renderAll() {
    if (!state) return;
    const panels = [
      renderScoreboardBar,
      renderHud,
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
    const banner = $('pause-banner');
    if (banner) {
      if (state.paused_reason) {
        banner.textContent = `Paused: ${state.paused_reason}`;
        banner.style.display = 'block';
      } else {
        banner.style.display = 'none';
      }
    }
  }

  function submitRoute() {
    const oIn = $('rt-origin-search');
    const dIn = $('rt-dest-search');
    const oCode = ($('rt-origin-code') && $('rt-origin-code').value) || '';
    const dCode = ($('rt-dest-code') && $('rt-dest-code').value) || '';
    const oAp = resolveAirportQuery(oIn && oIn.value) || airport(oCode);
    const dAp = resolveAirportQuery(dIn && dIn.value) || airport(dCode);
    if (!oAp || !dAp) {
      alert('Pick valid origin and destination (IATA code or city from the list).');
      return;
    }
    const acEl = $('rt-aircraft');
    const freqEl = $('rt-freq');
    const fareEl = $('rt-fare');
    if (!acEl || !acEl.value) {
      alert('Select an aircraft from your fleet.');
      return;
    }
    openRoute(oAp.iata, dAp.iata, acEl.value, +(freqEl && freqEl.value) || 7, +(fareEl && fareEl.value) || 129);
  }

  function saveGame() {
    if (!state) return;
    localStorage.setItem(SAVE_KEY, JSON.stringify({ state, airports: bootstrap.airports }));
  }

  function loadGame() {
    const raw = localStorage.getItem(SAVE_KEY);
    if (!raw) return false;
    try {
      const data = JSON.parse(raw);
      state = data.state;
      if (data.airports) bootstrap.airports = data.airports;
      mergeAirportsFromBootstrap();
      applyScenarioAirports(state.scenario_id);
      applyScenarioMap(state.scenario_id);
      syncMapDimensions();
      fitMapToManagedArea();
      sanitizeMarketingSpend();
      normalizeGameState();
      return true;
    } catch (e) {
      return false;
    }
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
    if (picker) picker.classList.remove('hidden');
    if (nameStep) nameStep.classList.remove('active');
  }

  function renderEmblemPicker() {
    const box = $('emblem-picker');
    if (!box || !bootstrap.emblem_options) return;
    box.innerHTML = bootstrap.emblem_options
      .map(
        (o) =>
          `<button type="button" class="emblem-opt${pendingEmblem === o.id ? ' active' : ''}" data-emblem="${o.id}" title="${o.label}" onclick="Runway.setEmblem('${o.id}')">
            <span class="emblem-glyph">${o.glyph}</span>
            <span class="emblem-label">${o.label}</span>
          </button>`
      )
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
    if (picker) picker.classList.add('hidden');
    if (nameStep) nameStep.classList.add('active');
    if (title) title.textContent = sc.name;
    if (brief) brief.textContent = sc.briefing;
    if (playerInput) playerInput.value = sc.player_name || '';
    if (airlineInput) airlineInput.value = sc.airline_name || '';
    renderEmblemPicker();
    if (playerInput) {
      playerInput.focus();
      playerInput.select();
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
    initialAirports = JSON.parse(JSON.stringify(bootstrap.airports));
    await loadMapConfig();
    sanitizeAirportGateCounts();
    setupMapInteraction();
    window.addEventListener('resize', ensureMapboxSize);
    setupStartScreen();
    setupKeyboardShortcuts();

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

    if (loadGame()) {
      showScreen('screen-game');
      setSpeed(state.speed || 'pause');
      renderAll();
    } else {
      showScreen('screen-start');
      showScenarioPicker();
      renderScenarioPicker();
    }
  }

  function renderScenarioPicker() {
    const el = $('scenario-list');
    if (!el) return;
    el.innerHTML = Object.values(bootstrap.scenarios)
      .map(
        (s) => `
      <button type="button" class="scenario-card" data-scenario="${s.id}">
        <strong>${s.name}</strong>
        <span>${s.tagline}</span>
        <p>${s.briefing}</p>
      </button>`
      )
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
    raiseSeed,
    raiseGrowthEquity,
    takeBankLoan,
    issueCorporateBonds,
    issueAssetBackedBonds,
    restructureDebt,
    applyMarketing,
    applyRouteSuggestion,
    setRouteFare,
    setRouteAncillary,
    resetRouteFare,
    toggleOta: toggleOtaListing,
    toggleFleetShop,
    toggleScoreboard,
    setLeagueScope,
    selectRival,
    closeRivalDetail,
    setEmblem: (id) => {
      pendingEmblem = id;
      document.querySelectorAll('[data-emblem]').forEach((btn) => {
        btn.classList.toggle('active', btn.dataset.emblem === id);
      });
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
    reset: () => {
      localStorage.removeItem(SAVE_KEY);
      location.reload();
    },
  };

  document.addEventListener('DOMContentLoaded', init);
})();