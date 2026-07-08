/**
 * Runway — startup airline simulation (MVP v0.1)
 */
(function () {
  'use strict';

  const SAVE_KEY = 'runway_save_v1';
  let bootstrap = null;
  let initialAirports = null;
  let state = null;
  let tickTimer = null;
  let selectedAirport = null;

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
      marketing_spend_monthly: {},
      ltm_revenue: 0,
      revenue_history: [],
      daily_pnl: 0,
      events: [],
      milestones: [],
      game_over: false,
      paused_reason: null,
    };
    pushEvent(`Started: ${base.name}`);
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
    return Object.values(state.marketing_spend_monthly).reduce((a, b) => a + b, 0);
  }

  function burnMonthly() {
    return (
      fleetLeaseMonthly() +
      gateLeaseMonthly() +
      marketingMonthly() +
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

    return base * hubPenalty * freqBonus * marketing * rep * fareFactor * reliability;
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
    const revenue = pax * route.fare;

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
          const spend = state.marketing_spend_monthly[ap] || 0;
          if (spend > 0) {
            state.brand_awareness[ap] = Math.min(100, (state.brand_awareness[ap] || 0) + spend / 50000);
          }
        });
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

      if (state.day % 7 === 0) {
        state.fuel_price = Math.max(
          1.8,
          state.fuel_price + (Math.random() - 0.48) * 0.12
        );
      }

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
    state.marketing_spend_monthly[iata] = Math.max(0, monthly);
    saveGame();
    renderHud();
  }

  function drawMap() {
    const svg = $('runway-map');
    if (!svg) return;
    const w = 960;
    const h = 480;
    const project = (lat, lon) => ({
      x: ((lon + 180) / 360) * w,
      y: ((90 - lat) / 180) * h,
    });

    let html = `<rect width="${w}" height="${h}" fill="#0a1628"/>`;
    html += `<text x="12" y="20" fill="#5a8ab0" font-size="11">CONUS + select airports (MVP)</text>`;

    bootstrap.airports.forEach((ap) => {
      const p = project(ap.lat, ap.lon);
      const owned = hasGateAt(ap.iata);
      const fill = owned ? '#00c896' : ap.hub_strength > 0.7 ? '#e85d4c' : '#4da3ff';
      const r = owned ? 5 : 3 + Math.min(4, ap.annual_pax_m / 25);
      html += `<circle cx="${p.x}" cy="${p.y}" r="${r}" fill="${fill}" opacity="0.9" class="ap-dot" data-iata="${ap.iata}" style="cursor:pointer"/>`;
      if (owned || selectedAirport === ap.iata) {
        html += `<text x="${p.x + 6}" y="${p.y + 3}" fill="#cde4f7" font-size="9">${ap.iata}</text>`;
      }
    });

    state.routes.forEach((route) => {
      const o = airport(route.origin);
      const d = airport(route.dest);
      const p1 = project(o.lat, o.lon);
      const p2 = project(d.lat, d.lon);
      html += `<line x1="${p1.x}" y1="${p1.y}" x2="${p2.x}" y2="${p2.y}" stroke="#ffd166" stroke-width="1.2" opacity="0.55"/>`;
    });

    svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
    svg.innerHTML = html;
    svg.querySelectorAll('.ap-dot').forEach((el) => {
      el.addEventListener('click', () => selectAirport(el.dataset.iata));
    });
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
        <input type="number" step="5000" value="${state.marketing_spend_monthly[iata] || 0}"
          onchange="Runway.setMarketing('${iata}', +this.value)">
      </label>
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
      return true;
    } catch (e) {
      return false;
    }
  }

  function showScreen(id) {
    document.querySelectorAll('.screen').forEach((s) => s.classList.remove('active'));
    $(id).classList.add('active');
  }

  function init() {
    bootstrap = window.RUNWAY_BOOTSTRAP;
    if (!bootstrap) return;
    initialAirports = JSON.parse(JSON.stringify(bootstrap.airports));

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