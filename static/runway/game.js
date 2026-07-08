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
  };

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

  function applyScenarioMap(scenarioId) {
    const sc = bootstrap.scenarios[scenarioId];
    activeMapKey = sc && sc.region === 'ohio' ? 'ohio' : 'usa';
    syncMapDimensions();
    mapView = { x: 0, y: 0, w: MAP_W, h: MAP_H };
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
    }
  }

  function resolveDecision(choiceId) {
    if (!activeDecision) return;
    const option = activeDecision.options.find((o) => o.id === choiceId) || { effect: 'none' };
    if (activeDecision.onResolve) activeDecision.onResolve(option);
    applyDecisionEffect({ ...option, airport: activeDecision.airport });
    pushEvent(activeDecision.logLine || `Decision: ${activeDecision.title} — ${option.label}`);
    activeDecision = null;
    state.paused_reason = null;
    renderDecisionModal();
    if (decisionQueue.length) showNextDecision();
    else if (decisionSpeedBeforePause && decisionSpeedBeforePause !== 'pause') setSpeed(decisionSpeedBeforePause);
    saveGame();
    renderAll();
  }

  function showNextDecision() {
    if (activeDecision || !decisionQueue.length) return;
    activeDecision = decisionQueue.shift();
    if (state.speed !== 'pause') {
      decisionSpeedBeforePause = state.speed || speedBeforePause || 'day';
      setSpeed('pause');
    }
    state.paused_reason = 'Market shift — decision required';
    renderDecisionModal();
    renderHud();
    const banner = $('pause-banner');
    if (banner) {
      banner.style.display = 'block';
      banner.textContent = state.paused_reason;
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
    overlay.innerHTML = `
      <div class="decision-card" role="dialog" aria-modal="true">
        <p class="decision-kicker">${activeDecision.kicker || 'Market intelligence'}</p>
        <h2>${activeDecision.title}</h2>
        <p class="decision-body">${activeDecision.body}</p>
        ${activeDecision.teach ? `<p class="decision-teach">${activeDecision.teach}</p>` : ''}
        <div class="decision-options">${opts}</div>
      </div>`;
    overlay.classList.add('active');
    overlay.querySelectorAll('[data-choice]').forEach((btn) => {
      btn.addEventListener('click', () => resolveDecision(btn.dataset.choice));
    });
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
    };
    sanitizeMarketingSpend();
    normalizeGameState();
    initCompetitorMarkets();
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

  function normalizeGameState() {
    if (!state) return;
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
    });
    if (!state.competitor_markets) initCompetitorMarkets();
    if (state.last_competitor_event_day == null) state.last_competitor_event_day = 0;
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
    const fareFactor = fareDemandFactor(route, o, d);
    const reliability = (o.seasonal_reliability + d.seasonal_reliability) / 2;
    const macro = macroDemandMultiplier();
    const ota = otaEffects();
    const comfortFactor = 0.82 + ((ac.comfort_rating || 3) / 5) * 0.38;

    let demand =
      base * hubPenalty * freqBonus * marketing * rep * fareFactor * reliability * macro * ota.demandMult * comfortFactor;
    if (isCommonRoutePair(route.origin, route.dest)) demand *= 1.08;
    return demand;
  }

  function simulateRouteDay(route) {
    const ac = aircraftType(route.aircraft_type);
    if (!ac) return { revenue: 0, cost: 0, pax: 0, load: 0 };
    const dist = routeDistance(route);
    if (dist > ac.range_nm) return { revenue: 0, cost: 0, pax: 0, load: 0 };

    const plane = route.aircraft_id ? state.fleet.find((f) => f.id === route.aircraft_id) : null;
    const seats = plane ? fleetSeatCount(plane) : ac.seats;
    const flightsToday = route.frequency_week / 7;
    const dailySeats = seats * flightsToday;
    const demand = demandForRoute(route);
    const load = Math.min(0.92, demand / Math.max(dailySeats, 1));
    const pax = Math.floor(dailySeats * load);
    const ota = otaEffects();
    const revenue = pax * route.fare * ota.revenueMult;

    const block = blockHours(dist, ac) * flightsToday;
    const fuel = block * ac.fuel_gal_hr * state.fuel_price;
    const crew = block * bootstrap.crew_cost_per_block_hour;
    const fees = flightsToday * bootstrap.airport_fee_per_departure * 2;
    const variable = fuel + crew + fees;

    return { revenue, cost: variable, pax, load };
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

    if (state.day > 0 && state.day % 60 === 0) maybeCompetitorEvents();

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
      });
      pushPlayerEvent(`purchased ${ac.name} (${seatCount} seats).`);
    }
    fleetPending = null;
    saveGame();
    renderAll();
  }

  function openRoute(origin, dest, aircraftId, freq, fare) {
    if (!hasGateAt(origin)) {
      alert(`You need a gate at ${origin} first.`);
      return;
    }
    const plane = state.fleet.find((f) => f.id === aircraftId);
    if (!plane) {
      alert('Select an aircraft from your fleet.');
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
      aircraft_id: aircraftId,
    });
    pushPlayerEvent(`opened ${origin}–${dest} (${freq}x/wk @ $${fare}).`);
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
    mapView = { x: 0, y: 0, w: MAP_W, h: MAP_H };
    applyMapView();
  }

  function clampMapView() {
    if (mapView.w >= MAP_W) {
      mapView.x = -(mapView.w - MAP_W) / 2;
      mapView.y = -(mapView.h - MAP_H) / 2;
      return;
    }
    mapView.x = Math.max(0, Math.min(MAP_W - mapView.w, mapView.x));
    mapView.y = Math.max(0, Math.min(MAP_H - mapView.h, mapView.y));
  }

  function applyMapView() {
    const svg = $('runway-map');
    if (!svg) return;
    svg.setAttribute(
      'viewBox',
      `${mapView.x} ${mapView.y} ${mapView.w} ${mapView.h}`
    );
  }

  function zoomMapAt(factor, clientX, clientY) {
    const svg = $('runway-map');
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

  function setupMapInteraction() {
    const wrap = document.querySelector('.map-wrap');
    const svg = $('runway-map');
    if (!wrap || !svg || wrap.dataset.mapPanInit) return;
    wrap.dataset.mapPanInit = '1';

    const endDrag = () => {
      if (!mapDrag.active) return;
      if (!mapDrag.moved && mapDrag.clickIata) selectAirport(mapDrag.clickIata);
      mapDrag.active = false;
      wrap.classList.remove('dragging');
    };

    svg.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      mapDrag.active = true;
      mapDrag.moved = false;
      mapDrag.startX = e.clientX;
      mapDrag.startY = e.clientY;
      mapDrag.viewX = mapView.x;
      mapDrag.viewY = mapView.y;
      const dot = e.target.closest && e.target.closest('.ap-dot');
      mapDrag.clickIata = dot ? dot.dataset.iata : null;
      svg.setPointerCapture(e.pointerId);
      wrap.classList.add('dragging');
    });

    svg.addEventListener('pointermove', (e) => {
      if (!mapDrag.active) return;
      const dx = e.clientX - mapDrag.startX;
      const dy = e.clientY - mapDrag.startY;
      if (Math.abs(dx) > 5 || Math.abs(dy) > 5) mapDrag.moved = true;
      if (!mapDrag.moved) return;

      const rect = svg.getBoundingClientRect();
      mapView.x = mapDrag.viewX - (dx / rect.width) * mapView.w;
      mapView.y = mapDrag.viewY - (dy / rect.height) * mapView.h;
      clampMapView();
      applyMapView();
    });

    svg.addEventListener('pointerup', endDrag);
    svg.addEventListener('pointercancel', endDrag);

    wrap.addEventListener(
      'wheel',
      (e) => {
        e.preventDefault();
        zoomMapAt(e.deltaY > 0 ? 1.1 : 0.9, e.clientX, e.clientY);
      },
      { passive: false }
    );

    const zoomIn = $('map-zoom-in');
    const zoomOut = $('map-zoom-out');
    const zoomReset = $('map-zoom-reset');
    if (zoomIn) {
      zoomIn.addEventListener('click', () => {
        const r = svg.getBoundingClientRect();
        zoomMapAt(0.82, r.left + r.width / 2, r.top + r.height / 2);
      });
    }
    if (zoomOut) {
      zoomOut.addEventListener('click', () => {
        const r = svg.getBoundingClientRect();
        zoomMapAt(1.22, r.left + r.width / 2, r.top + r.height / 2);
      });
    }
    if (zoomReset) zoomReset.addEventListener('click', resetMapView);
  }

  function mapBounds() {
    const cfg = getActiveMapConfig();
    if (cfg && cfg.bounds) return cfg.bounds;
    return { lonMin: -125, lonMax: -66, latMin: 24, latMax: 50 };
  }

  function projectMap(lat, lon) {
    const b = mapBounds();
    return {
      x: ((lon - b.lonMin) / (b.lonMax - b.lonMin)) * MAP_W,
      y: ((b.latMax - lat) / (b.latMax - b.latMin)) * MAP_H,
    };
  }

  function drawMap() {
    const svg = $('runway-map');
    if (!svg) return;
    const cfg = getActiveMapConfig();
    const mapSrc = cfg ? cfg.src : '/static/runway/us-map-styled.png';

    let html = `
      <image class="map-raster" href="${mapSrc}" x="0" y="0" width="${MAP_W}" height="${MAP_H}" preserveAspectRatio="none"/>
    `;

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
      const fill = owned ? '#00e4a8' : ap.hub_strength > 0.7 ? '#ff6b5a' : '#5eb8ff';
      const r = owned || selected ? 6 : 4 + Math.min(3, ap.annual_pax_m / 25);
      const stroke = selected ? '#fff' : owned ? '#042' : 'rgba(255,255,255,0.45)';
      html += `<circle cx="${p.x}" cy="${p.y}" r="${r}" fill="${fill}" stroke="${stroke}" stroke-width="${selected ? 2 : 1.2}" class="ap-dot" data-iata="${ap.iata}" style="cursor:pointer"/>`;
      if (owned || selected || labelAll) {
        html += `<text x="${p.x + 8}" y="${p.y + 4}" fill="#f0f8ff" font-size="${labelAll ? 11 : 10}" font-weight="700" style="paint-order:stroke;stroke:#041018;stroke-width:3px">${ap.iata}</text>`;
      }
    });
    html += '</g>';

    svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    svg.innerHTML = html;
    applyMapView();
  }

  function selectAirport(iata) {
    selectedAirport = iata;
    renderAirportPanel(iata);
    drawMap();
    const routesPanel = $('panel-routes');
    if (routesPanel && routesPanel.classList.contains('active')) renderRoutes();
  }

  function renderAirportPanel(iata) {
    const ap = airport(iata);
    const panel = $('airport-panel');
    if (!ap || !panel) return;
    const gate = state.gates.find((g) => g.airport === iata);
    panel.innerHTML = `
      <h3>${ap.iata} — ${ap.city}${ap.regional ? '<span class="badge-regional">Regional</span>' : ''}</h3>
      <p class="muted">${ap.name}${ap.state ? ` · ${ap.state}` : ''}</p>
      <dl class="stat-dl">
        <dt>Metro pop</dt><dd>${ap.metro_pop_m}M</dd>
        <dt>Annual pax</dt><dd>${ap.annual_pax_m}M</dd>
        <dt>Wealth index</dt><dd>${(airportWealth(ap) * 100).toFixed(0)}</dd>
        <dt>Luxury demand</dt><dd>${(airportLuxury(ap) * 100).toFixed(0)}%</dd>
        <dt>Gates open</dt><dd>${ap.gates_available} / ${ap.gates_total}</dd>
        <dt>Top carrier</dt><dd>${ap.hub_airline || '—'} (${(ap.hub_strength * 100).toFixed(0)}%)</dd>
        <dt>Slot controlled</dt><dd>${ap.slot_controlled ? 'Yes' : 'No'}</dd>
        <dt>Your gate</dt><dd>${gate ? `${gate.tier} ($${gate.monthly.toLocaleString()}/mo)` : 'None'}</dd>
        <dt>Brand awareness</dt><dd>${(state.brand_awareness[iata] || 0).toFixed(0)}%</dd>
      </dl>
      ${
        ap.incumbents && ap.incumbents.length
          ? `<h4 style="font-size:0.82rem;margin:10px 0 6px;color:var(--gold);">Competitors here</h4>
        <ul class="list incumbent-list">${ap.incumbents
          .map(
            (c) =>
              `<li><strong>${c.airline}</strong> <span class="muted">${(c.share * 100).toFixed(0)}% · ${c.tier}</span></li>`
          )
          .join('')}</ul>`
          : '<p class="muted" style="font-size:0.75rem;">No major scheduled incumbents — thin or GA market.</p>'
      }
      ${gate ? '' : `
        <button class="btn" onclick="Runway.leaseGate('${iata}','common',3)">Lease common-use (3yr)</button>
        <button class="btn secondary" onclick="Runway.leaseGate('${iata}','exclusive',5)">Lease exclusive (5yr)</button>
      `}
      <div class="mkt-box">
        <label for="mkt-input-${iata}">Marketing budget $/mo
          <input type="number" id="mkt-input-${iata}" min="0" step="1000" value="${clampMoney(state.marketing_spend_monthly[iata])}">
        </label>
        <p class="muted" style="font-size:0.75rem;margin:6px 0;">Active spend: <b>${fmtMoney(clampMoney(state.marketing_spend_monthly[iata]))}/mo</b></p>
        <button type="button" class="btn" onclick="Runway.applyMarketing('${iata}')">Apply budget</button>
      </div>
      <p class="muted" style="margin-top:8px;font-size:0.75rem;">OTA amplify: ${otaEffects().marketingAmplify.toFixed(2)}× · Country demand: ${(macroDemandMultiplier() * 100).toFixed(0)}%</p>
    `;
  }

  function setText(id, text) {
    const el = $(id);
    if (el) el.textContent = text;
  }

  function renderHud() {
    if (!state) return;
    setText('hud-cash', fmtMoney(state.cash));
    setText('hud-runway', state.cash < 0 ? 'BANKRUPT' : `${runwayMonths().toFixed(1)} mo`);
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
    const macroEl = $('hud-macro');
    if (macroEl && state.macro) {
      ensureMacro();
      const cashYield = state.cash > 0 ? (cashInterestAnnualRate() * 100).toFixed(2) : '0.00';
      macroEl.textContent =
        `Infl ${state.macro.inflation_pct.toFixed(1)}% · GDP ${state.macro.gdp_growth_pct >= 0 ? '+' : ''}${state.macro.gdp_growth_pct.toFixed(1)}% · Travel ${state.macro.travel_spend_growth_pct >= 0 ? '+' : ''}${state.macro.travel_spend_growth_pct.toFixed(1)}% · US ${state.macro.country_health.toFixed(0)} · Cash yield ${cashYield}%`;
    }
  }

  function renderEconomy() {
    const el = $('tab-economy');
    if (!el) return;
    ensureMacro();
    const m = state.macro;
    const ota = otaEffects();
    let html = `<h3>${m.country} economy</h3>
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
    let html = `<h3>Capital structure</h3>
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
    let html = '<h3>Your fleet</h3>';
    if (!state.fleet.length) {
      html += '<p class="muted">No aircraft yet — select a type below, configure seats, then confirm lease or purchase.</p>';
    } else {
      html += '<ul class="list">';
      state.fleet.forEach((f) => {
        const ac = aircraftType(f.type);
        if (!ac) {
          html += `<li><strong>${f.type || 'Unknown aircraft'}</strong> — missing type data</li>`;
          return;
        }
        const seats = fleetSeatCount(f);
        const life = f.leased
          ? `${f.lease_months_left || '?'} mo lease left`
          : `${Math.ceil((f.life_months_left || 0) / 12)} yr life left · ${fmtMoney(ac.maintenance_monthly)}/mo maint`;
        html += `<li><strong>${ac.name}</strong> (${seats} seats) — ${f.leased ? 'Leased' : 'Owned'}<br>
          <span class="muted">${ac.size} · ${ac.range_nm} nm · Comfort ${comfortStars(ac.comfort_rating)} · ${life}</span></li>`;
      });
      html += '</ul>';
    }

    html += '<h4>Add aircraft</h4><p class="muted">Choose type → set seats → confirm lease or buy.</p><div class="fleet-grid">';
    Object.keys(bootstrap.aircraft_types || {}).forEach((tid) => {
      const ac = aircraftType(tid);
      if (!ac) return;
      const active = fleetPending && fleetPending.type === tid;
      html += `<div class="fleet-card ${active ? 'active' : ''}">
        <strong>${ac.name}</strong>
        <span class="muted">${ac.category} · ${ac.size}</span>
        <span>${ac.seats_min}–${ac.seats_max} seats · ${ac.range_nm} nm</span>
        <span>Comfort ${comfortStars(ac.comfort_rating)} (${ac.comfort_rating})</span>
        <span>Lease ${fmtMoney(ac.lease_monthly)}/mo · Buy ${fmtMoney(ac.purchase)}</span>
        ${ac.maintenance_monthly ? `<span class="muted">Owned maint ${fmtMoney(ac.maintenance_monthly)}/mo · ${ac.lifespan_years}yr life</span>` : ''}
        <div class="btn-row">
          <button class="btn secondary" onclick="Runway.selectFleet('${tid}','lease')">Lease…</button>
          <button class="btn secondary" onclick="Runway.selectFleet('${tid}','buy')">Buy…</button>
        </div>
      </div>`;
    });
    html += '</div>';

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

    let html = '<h3>Active routes</h3>';
    if (!state.routes.length) {
      html += '<p class="muted">No routes yet.</p>';
    } else {
      html += '<table class="data-table"><tr><th>Route</th><th>Freq</th><th>Fare</th><th>Market</th><th>Load</th><th>P&L</th></tr>';
      state.routes.forEach((route) => {
        const r = simulateRouteDay(route);
        const pnl = r.revenue - r.cost;
        const loadPct = Number.isFinite(r.load) ? `${(r.load * 100).toFixed(0)}%` : '—';
        const market = marketFareForPair(route.origin, route.dest, route.aircraft_type);
        const mode = route.fare_mode === 'manual' ? 'manual' : 'auto';
        html += `<tr>
          <td>${route.origin}–${route.dest}</td>
          <td>${route.frequency_week}/wk</td>
          <td>
            <input type="number" min="49" max="899" value="${route.fare}" style="width:62px;padding:4px;"
              onchange="Runway.setRouteFare('${route.id}', this.value, 'manual')">
            <span class="muted" style="font-size:0.65rem;">${mode}</span>
          </td>
          <td class="muted">$${market}</td>
          <td>${loadPct}</td>
          <td>${fmtMoney(pnl)}</td>
        </tr>`;
      });
      html += '</table><p class="muted" style="font-size:0.72rem;">Fares on <b>auto</b> drift monthly with load (supply & demand). Edit to lock manual. Market fare uses distance, local wealth, and luxury demand.</p>';
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

    html += `<h4>Open route</h4>
      <p class="muted">Pick a suggested destination or search manually. Origin defaults to your map selection.</p>
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
        <label>Aircraft (your fleet)
          <select id="rt-aircraft">${fleetOpts}</select>
        </label>
        <label>Freq/wk <input id="rt-freq" type="number" value="7" min="1" max="28"></label>
        <label>Fare $ <input id="rt-fare" type="number" value="129" min="49" max="899">
          <span class="muted" style="font-size:0.68rem;">Auto-adjusts unless you override · preview updates live</span>
        </label>
      </div>
      <button class="btn" onclick="Runway.submitRoute()">Launch route</button>`;
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
      html += `<li>
        <button type="button" class="route-suggest-btn" data-tier="${s.tier}"
          onclick="Runway.applyRouteSuggestion('${s.dest}','${s.acType}',${s.fare},${s.freq})">
          <span class="rs-route">${origin} → ${s.dest} <span class="muted">${s.destCity}</span>${s.common ? ' <span class="badge-regional">Common</span>' : ''}</span>
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

  function applyRouteSuggestion(destIata, acType, fare, freq) {
    const dAp = airport(destIata);
    if (!dAp) return;
    const destInput = $('rt-dest-search');
    const destCode = $('rt-dest-code');
    if (destInput) destInput.value = airportLabel(dAp);
    if (destCode) destCode.value = destIata;
    const fareInput = $('rt-fare');
    const freqInput = $('rt-freq');
    if (fareInput) fareInput.value = fare;
    if (freqInput) freqInput.value = freq;
    const plane = state.fleet.find((f) => f.type === acType);
    const acSelect = $('rt-aircraft');
    if (acSelect && plane) acSelect.value = plane.id;
    updateRoutePreview();
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
    if (selectedAirport) {
      try {
        renderAirportPanel(selectedAirport);
      } catch (err) {
        console.error('Runway render error: renderAirportPanel', err);
      }
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
    const oAp = resolveAirportQuery(oIn && oIn.value) || airport($('rt-origin-code').value);
    const dAp = resolveAirportQuery(dIn && dIn.value);
    if (!oAp || !dAp) {
      alert('Pick valid origin and destination from the list (IATA code or city).');
      return;
    }
    openRoute(oAp.iata, dAp.iata, $('rt-aircraft').value, +$('rt-freq').value, +$('rt-fare').value);
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
  }

  function showScenarioPicker() {
    pendingScenarioId = null;
    const picker = $('scenario-picker');
    const nameStep = $('scenario-name-step');
    if (picker) picker.classList.remove('hidden');
    if (nameStep) nameStep.classList.remove('active');
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
      setSpeed('day');
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
          bounds: { lonMin: -124.85, lonMax: -66.7, latMin: 24.3, latMax: 49.55 },
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
    setupMapInteraction();
    setupStartScreen();
    setupKeyboardShortcuts();

    document.querySelectorAll('[data-speed]').forEach((btn) => {
      btn.addEventListener('click', () => setSpeed(btn.dataset.speed));
    });

    document.querySelectorAll('[data-tab]').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('[data-tab]').forEach((b) => b.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach((p) => p.classList.remove('active'));
        btn.classList.add('active');
        $(`panel-${btn.dataset.tab}`).classList.add('active');
        if (btn.dataset.tab === 'routes') renderRoutes();
      });
    });

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
    resetRouteFare,
    toggleOta: toggleOtaListing,
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