/**
 * Runway — startup airline simulation (MVP v0.1)
 */
(function () {
  'use strict';

  const SAVE_KEY = 'runway_save_v1';
  const MAP_W = 960;
  const MAP_H = 520;
  let bootstrap = null;
  let initialAirports = null;
  let usMap = null;
  let state = null;
  let tickTimer = null;
  let selectedAirport = null;
  let mapView = { x: 0, y: 0, w: MAP_W, h: MAP_H };
  const MAP_ZOOM_MIN_W = MAP_W * 0.22;
  const MAP_ZOOM_MAX_W = MAP_W * 2.2;
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

  function fmtDate(day) {
    const start = new Date(2026, 0, 1);
    start.setDate(start.getDate() + day);
    return start.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
  }

  function uid(prefix) {
    return `${prefix}-${Math.random().toString(36).slice(2, 9)}`;
  }

  function airport(iata) {
    return bootstrap.airports.find((a) => a.iata === iata);
  }

  function aircraftType(id) {
    return bootstrap.aircraft_types[id];
  }

  function cloneScenario(id) {
    const s = JSON.parse(JSON.stringify(bootstrap.scenarios[id]));
    s.fleet = (s.fleet || []).map((f) => ({ ...f }));
    s.gates = (s.gates || []).map((g) => ({ ...g }));
    s.routes = (s.routes || []).map((r) => ({ ...r }));
    s.debt = (s.debt || []).map((d) => ({ ...d }));
    s.bonds = (s.bonds || []).map((b) => ({ ...b }));
    s.brand_awareness = { ...(s.brand_awareness || {}) };
    return s;
  }

  function newGame(scenarioId, airlineName) {
    if (initialAirports) bootstrap.airports = JSON.parse(JSON.stringify(initialAirports));
    const base = cloneScenario(scenarioId);
    state = {
      scenario_id: scenarioId,
      airline_name: airlineName || base.airline_name,
      day: 0,
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
    resetMapView();
    pushEvent(`Started: ${base.name}`);
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
    state.macro.country_health = computeCountryHealth();
  }

  function computeCountryHealth() {
    ensureMacro();
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
      listingCost += p.listing_monthly;
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

  function fleetLeaseMonthly() {
    return state.fleet.reduce((s, f) => {
      if (!f.leased) return s;
      return s + aircraftType(f.type).lease_monthly;
    }, 0);
  }

  function gateLeaseMonthly() {
    return state.gates.reduce((s, g) => s + g.monthly, 0);
  }

  function marketingMonthly() {
    return Object.values(state.marketing_spend_monthly).reduce((a, b) => a + clampMoney(b), 0);
  }

  function burnMonthly() {
    return (
      fleetLeaseMonthly() +
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
    return haversineNm(o.lat, o.lon, d.lat, d.lon);
  }

  function blockHours(distNm, ac) {
    return (distNm / 420) * 2 + 0.5;
  }

  function demandForRoute(route) {
    const o = airport(route.origin);
    const d = airport(route.dest);
    const dist = routeDistance(route);
    const ac = aircraftType(route.aircraft_type);
    if (dist > ac.range_nm) return 0;

    const base = Math.sqrt(o.metro_pop_m * d.metro_pop_m) * 1200;
    const hubPenalty = 1 - (o.hub_strength + d.hub_strength) * 0.35;
    const freqBonus = Math.min(1.4, 0.7 + route.frequency_week / 28);
    const awareO = (state.brand_awareness[route.origin] || 5) / 100;
    const awareD = (state.brand_awareness[route.dest] || 5) / 100;
    const marketing = 0.5 + (awareO + awareD) / 2;
    const rep = 1 + state.reputation / 200;
    const fareFactor = Math.max(0.35, 1.1 - route.fare / 280);
    const reliability = (o.seasonal_reliability + d.seasonal_reliability) / 2;
    const macro = macroDemandMultiplier();
    const ota = otaEffects();

    return base * hubPenalty * freqBonus * marketing * rep * fareFactor * reliability * macro * ota.demandMult;
  }

  function simulateRouteDay(route) {
    const ac = aircraftType(route.aircraft_type);
    const dist = routeDistance(route);
    if (dist > ac.range_nm) return { revenue: 0, cost: 0, pax: 0 };

    const flightsToday = route.frequency_week / 7;
    const dailySeats = ac.seats * flightsToday;
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

  function tickDays(n) {
    if (!state || state.game_over || n <= 0) return;

    for (let i = 0; i < n; i++) {
      state.day += 1;
      let dayRev = 0;
      let dayCost = 0;

      state.routes.forEach((route) => {
        const r = simulateRouteDay(route);
        dayRev += r.revenue;
        dayCost += r.cost;
      });

      const dailyFixed =
        (fleetLeaseMonthly() + gateLeaseMonthly() + monthlyDebtService()) / 30 +
        marketingMonthly() / 30;

      state.daily_pnl = dayRev - dayCost - dailyFixed;
      state.cash += state.daily_pnl;

      if (state.day % 30 === 0) {
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
      }

      if (state.day % 90 === 0 && state.bonds.length) {
        const coupon = quarterlyBondCoupons();
        state.cash -= coupon;
        pushEvent(`Bond coupon paid: ${fmtMoney(-coupon)}`);
      }

      state.revenue_history.push(dayRev);
      if (state.revenue_history.length > 400) state.revenue_history.shift();

      if (state.day % 7 === 0) updateFuelPrice();

      if (state.day > 0 && state.day % 365 === 0) advanceMacroYear();

      state.gates.forEach((g) => {
        if (state.day % 30 === 0) g.months_left = (g.months_left || g.years_left * 12) - 1;
      });

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
    saveGame();
    renderAll();
  }

  function setSpeed(speedId) {
    state.speed = speedId;
    if (tickTimer) clearInterval(tickTimer);
    tickTimer = null;
    const ms = bootstrap.tick_ms[speedId];
    const days = bootstrap.time_speeds.find((t) => t.id === speedId)?.days_per_tick || 0;
    if (days > 0 && ms > 0) {
      tickTimer = setInterval(() => tickDays(days), ms);
    }
    document.querySelectorAll('[data-speed]').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.speed === speedId);
    });
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
    pushEvent(`Leased ${tier} gate at ${iata} (${years}yr).`);
    saveGame();
    renderAll();
  }

  function leaseAircraft(type) {
    const ac = aircraftType(type);
    const deposit = ac.lease_monthly * 2;
    if (state.cash < deposit) {
      alert('Insufficient cash for aircraft deposit.');
      return;
    }
    state.cash -= deposit;
    state.fleet.push({
      id: uid('ac'),
      type,
      leased: true,
      lease_months_left: 60,
    });
    pushEvent(`Leased ${ac.name}.`);
    saveGame();
    renderAll();
  }

  function openRoute(origin, dest, aircraftTypeId, freq, fare, aircraftId) {
    if (!hasGateAt(origin)) {
      alert(`You need a gate at ${origin} first.`);
      return;
    }
    const dist = haversineNm(
      airport(origin).lat,
      airport(origin).lon,
      airport(dest).lat,
      airport(dest).lon
    );
    const ac = aircraftType(aircraftTypeId);
    if (dist > ac.range_nm) {
      alert(`Route exceeds ${ac.name} range (${Math.round(dist)} nm).`);
      return;
    }
    state.routes.push({
      id: uid('rt'),
      origin,
      dest,
      aircraft_type: aircraftTypeId,
      frequency_week: freq,
      fare,
      aircraft_id: aircraftId || null,
    });
    pushEvent(`Opened ${origin}–${dest} (${freq}x/wk @ $${fare}).`);
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

  function setMarketing(iata, monthly) {
    const v = clampMoney(monthly);
    state.marketing_spend_monthly[iata] = v;
    saveGame();
    renderHud();
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
    if (usMap && usMap.bounds) return usMap.bounds;
    return { lonMin: -130, lonMax: -60, latMin: 22, latMax: 52 };
  }

  function projectMap(lat, lon) {
    const b = mapBounds();
    return {
      x: ((lon - b.lonMin) / (b.lonMax - b.lonMin)) * MAP_W,
      y: ((b.latMax - lat) / (b.latMax - b.latMin)) * MAP_H,
    };
  }

  function statePathD(coords) {
    return (
      coords
        .map((pair, i) => {
          const pt = projectMap(pair[1], pair[0]);
          return `${i ? 'L' : 'M'}${pt.x.toFixed(1)},${pt.y.toFixed(1)}`;
        })
        .join(' ') + ' Z'
    );
  }

  function drawMapLandmass() {
    if (!usMap || !usMap.paths) return '';
    let html = '<g class="us-land">';
    usMap.paths.forEach((ring) => {
      html += `<path d="${statePathD(ring)}" fill="#1e4a6e" stroke="#3d7ab5" stroke-width="0.7" stroke-linejoin="round"/>`;
    });
    html += '</g>';
    return html;
  }

  function drawMap() {
    const svg = $('runway-map');
    if (!svg) return;

    let html = `<defs>
      <linearGradient id="ocean" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#081420"/>
        <stop offset="100%" stop-color="#0c2238"/>
      </linearGradient>
    </defs>`;
    html += `<rect width="${MAP_W}" height="${MAP_H}" fill="url(#ocean)"/>`;
    html += drawMapLandmass();

    if (state && state.routes) {
      state.routes.forEach((route) => {
        const o = airport(route.origin);
        const d = airport(route.dest);
        const p1 = projectMap(o.lat, o.lon);
        const p2 = projectMap(d.lat, d.lon);
        html += `<line x1="${p1.x}" y1="${p1.y}" x2="${p2.x}" y2="${p2.y}" stroke="#ffd166" stroke-width="1.4" opacity="0.55"/>`;
      });
    }

    bootstrap.airports.forEach((ap) => {
      const p = projectMap(ap.lat, ap.lon);
      const owned = hasGateAt(ap.iata);
      const fill = owned ? '#00c896' : ap.hub_strength > 0.7 ? '#e85d4c' : '#4da3ff';
      const r = owned ? 5 : 3 + Math.min(4, ap.annual_pax_m / 25);
      html += `<circle cx="${p.x}" cy="${p.y}" r="${r}" fill="${fill}" opacity="0.95" class="ap-dot" data-iata="${ap.iata}" style="cursor:pointer"/>`;
      if (owned || selectedAirport === ap.iata) {
        html += `<text x="${p.x + 6}" y="${p.y + 3}" fill="#e8f4ff" font-size="9" font-weight="600">${ap.iata}</text>`;
      }
    });

    html += `<text x="14" y="22" fill="#6a9fc0" font-size="11" opacity="0.85">United States · airport network</text>`;

    svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    svg.innerHTML = html;
    applyMapView();
  }

  function selectAirport(iata) {
    selectedAirport = iata;
    renderAirportPanel(iata);
    drawMap();
  }

  function renderAirportPanel(iata) {
    const ap = airport(iata);
    const panel = $('airport-panel');
    if (!ap || !panel) return;
    const gate = state.gates.find((g) => g.airport === iata);
    panel.innerHTML = `
      <h3>${ap.iata} — ${ap.city}</h3>
      <p class="muted">${ap.name}</p>
      <dl class="stat-dl">
        <dt>Metro pop</dt><dd>${ap.metro_pop_m}M</dd>
        <dt>Annual pax</dt><dd>${ap.annual_pax_m}M</dd>
        <dt>Gates open</dt><dd>${ap.gates_available} / ${ap.gates_total}</dd>
        <dt>Hub incumbent</dt><dd>${ap.hub_airline || '—'} (${(ap.hub_strength * 100).toFixed(0)}%)</dd>
        <dt>Slot controlled</dt><dd>${ap.slot_controlled ? 'Yes' : 'No'}</dd>
        <dt>Your gate</dt><dd>${gate ? `${gate.tier} ($${gate.monthly.toLocaleString()}/mo)` : 'None'}</dd>
        <dt>Brand awareness</dt><dd>${(state.brand_awareness[iata] || 0).toFixed(0)}%</dd>
      </dl>
      ${gate ? '' : `
        <button class="btn" onclick="Runway.leaseGate('${iata}','common',3)">Lease common-use (3yr)</button>
        <button class="btn secondary" onclick="Runway.leaseGate('${iata}','exclusive',5)">Lease exclusive (5yr)</button>
      `}
      <label>Marketing $/mo
        <input type="number" min="0" step="1000" value="${clampMoney(state.marketing_spend_monthly[iata])}"
          oninput="var v=Math.max(0,this.valueAsNumber||0);this.value=v;Runway.setMarketing('${iata}', v)">
      </label>
      <p class="muted" style="margin-top:8px;font-size:0.75rem;">OTA amplify: ${otaEffects().marketingAmplify.toFixed(2)}× · Country demand: ${(macroDemandMultiplier() * 100).toFixed(0)}%</p>
    `;
  }

  function renderHud() {
    if (!state) return;
    $('hud-cash').textContent = fmtMoney(state.cash);
    $('hud-runway').textContent =
      state.cash < 0 ? 'BANKRUPT' : `${runwayMonths().toFixed(1)} mo`;
    $('hud-date').textContent = fmtDate(state.day);
    $('hud-equity').textContent = `${state.equity_pct.toFixed(1)}%`;
    $('hud-rep').textContent = state.reputation.toFixed(0);
    $('hud-fuel').textContent = `$${state.fuel_price.toFixed(2)}/gal`;
    $('hud-pnl').textContent = fmtMoney(state.daily_pnl);
    $('hud-airline').textContent = state.airline_name;
    $('hud-ltm').textContent = fmtMoney(state.ltm_revenue);
    const macroEl = $('hud-macro');
    if (macroEl && state.macro) {
      ensureMacro();
      macroEl.textContent =
        `Infl ${state.macro.inflation_pct.toFixed(1)}% · GDP ${state.macro.gdp_growth_pct >= 0 ? '+' : ''}${state.macro.gdp_growth_pct.toFixed(1)}% · Travel ${state.macro.travel_spend_growth_pct >= 0 ? '+' : ''}${state.macro.travel_spend_growth_pct.toFixed(1)}% · US ${state.macro.country_health.toFixed(0)}`;
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
    let html = `<h3>Capital structure</h3>
      <p>Debt: ${state.debt.map((d) => `${d.name} ${fmtMoney(d.principal)} @ ${(d.rate * 100).toFixed(1)}%`).join('<br>') || 'None'}</p>
      <p>Bonds: ${state.bonds.map((b) => `${b.name} ${fmtMoney(b.principal)} coupon ${(b.coupon * 100).toFixed(1)}%`).join('<br>') || 'None'}</p>
      <p class="muted">Bond rating: ${state.bond_rating || 'N/A'} · Monthly burn ~${fmtMoney(burnMonthly())}</p>
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
    let html = '<h3>Fleet</h3><ul class="list">';
    state.fleet.forEach((f) => {
      const ac = aircraftType(f.type);
      html += `<li>${ac.name} ${f.leased ? '(leased)' : '(owned)'} — ${ac.seats} seats, ${ac.range_nm} nm</li>`;
    });
    html += '</ul><h4>Lease aircraft</h4><div class="btn-row">';
    Object.keys(bootstrap.aircraft_types).forEach((tid) => {
      const ac = aircraftType(tid);
      html += `<button class="btn secondary" onclick="Runway.leaseAircraft('${tid}')">${ac.name} ($${ac.lease_monthly.toLocaleString()}/mo)</button>`;
    });
    html += '</div>';
    el.innerHTML = html;
  }

  function renderRoutes() {
    const el = $('tab-routes');
    if (!el) return;
    let html = '<h3>Active routes</h3><table class="data-table"><tr><th>Route</th><th>Freq</th><th>Fare</th><th>Load</th><th>Daily P&L</th></tr>';
    state.routes.forEach((route) => {
      const r = simulateRouteDay(route);
      const pnl = r.revenue - r.cost;
      html += `<tr><td>${route.origin}–${route.dest}</td><td>${route.frequency_week}/wk</td><td>$${route.fare}</td><td>${(r.load * 100).toFixed(0)}%</td><td>${fmtMoney(pnl)}</td></tr>`;
    });
    html += `</table>
      <h4>Open route</h4>
      <div class="form-grid">
        <label>Origin <select id="rt-origin">${bootstrap.airports.map((a) => `<option value="${a.iata}">${a.iata}</option>`).join('')}</select></label>
        <label>Dest <select id="rt-dest">${bootstrap.airports.map((a) => `<option value="${a.iata}">${a.iata}</option>`).join('')}</select></label>
        <label>Aircraft <select id="rt-ac">${Object.keys(bootstrap.aircraft_types).map((t) => `<option value="${t}">${bootstrap.aircraft_types[t].name}</option>`).join('')}</select></label>
        <label>Freq/wk <input id="rt-freq" type="number" value="7" min="1" max="28"></label>
        <label>Fare $ <input id="rt-fare" type="number" value="149" min="49" max="899"></label>
      </div>
      <button class="btn" onclick="Runway.submitRoute()">Launch route</button>`;
    el.innerHTML = html;
  }

  function renderEvents() {
    const el = $('tab-events');
    if (!el) return;
    el.innerHTML = `<ul class="list">${state.events.map((e) => `<li><span class="muted">${fmtDate(e.day)}</span> ${e.msg}</li>`).join('')}</ul>`;
  }

  function renderAll() {
    renderHud();
    drawMap();
    renderFinance();
    renderEconomy();
    renderFleet();
    renderRoutes();
    renderEvents();
    if (selectedAirport) renderAirportPanel(selectedAirport);
    if (state.paused_reason) {
      $('pause-banner').textContent = `Paused: ${state.paused_reason}`;
      $('pause-banner').style.display = 'block';
    } else {
      $('pause-banner').style.display = 'none';
    }
  }

  function submitRoute() {
    openRoute(
      $('rt-origin').value,
      $('rt-dest').value,
      $('rt-ac').value,
      +$('rt-freq').value,
      +$('rt-fare').value
    );
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
      sanitizeMarketingSpend();
      ensureMacro();
      return true;
    } catch (e) {
      return false;
    }
  }

  function showScreen(id) {
    document.querySelectorAll('.screen').forEach((s) => s.classList.remove('active'));
    $(id).classList.add('active');
  }

  async function loadUsMap() {
    try {
      const resp = await fetch('/static/runway/us-states.json');
      if (resp.ok) usMap = await resp.json();
    } catch (e) {
      console.warn('Runway: US map data failed to load', e);
    }
  }

  async function init() {
    bootstrap = window.RUNWAY_BOOTSTRAP;
    if (!bootstrap) return;
    initialAirports = JSON.parse(JSON.stringify(bootstrap.airports));
    await loadUsMap();
    setupMapInteraction();

    document.querySelectorAll('[data-speed]').forEach((btn) => {
      btn.addEventListener('click', () => setSpeed(btn.dataset.speed));
    });

    document.querySelectorAll('[data-tab]').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('[data-tab]').forEach((b) => b.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach((p) => p.classList.remove('active'));
        btn.classList.add('active');
        $(`panel-${btn.dataset.tab}`).classList.add('active');
      });
    });

    if (loadGame()) {
      showScreen('screen-game');
      setSpeed(state.speed || 'pause');
      renderAll();
    } else {
      showScreen('screen-start');
      renderScenarioPicker();
    }
  }

  function renderScenarioPicker() {
    const el = $('scenario-list');
    if (!el) return;
    el.innerHTML = Object.values(bootstrap.scenarios)
      .map(
        (s) => `
      <button class="scenario-card" data-scenario="${s.id}">
        <strong>${s.name}</strong>
        <span>${s.tagline}</span>
        <p>${s.briefing}</p>
      </button>`
      )
      .join('');
    el.querySelectorAll('[data-scenario]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const sc = bootstrap.scenarios[btn.dataset.scenario];
        const name = prompt('Airline name:', sc.airline_name) || sc.airline_name;
        newGame(btn.dataset.scenario, name);
        showScreen('screen-game');
        setSpeed('day');
      });
    });
  }

  window.Runway = {
    leaseGate,
    leaseAircraft,
    submitRoute,
    raiseSeed,
    raiseGrowthEquity,
    takeBankLoan,
    issueCorporateBonds,
    issueAssetBackedBonds,
    restructureDebt,
    setMarketing,
    toggleOta: toggleOtaListing,
    newGame: (id) => {
      newGame(id);
      showScreen('screen-game');
    },
    reset: () => {
      localStorage.removeItem(SAVE_KEY);
      location.reload();
    },
  };

  document.addEventListener('DOMContentLoaded', init);
})();