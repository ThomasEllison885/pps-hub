"""Runway — startup airline simulation data (MVP v0.1)."""

RUNWAY_OWNER = 'thomas_ellison'

AIRCRAFT_TYPES = {
    'pc12': {
        'name': 'Pilatus PC-12',
        'category': 'Regional turboprop',
        'size': 'Small',
        'seats': 9,
        'seats_min': 6,
        'seats_max': 9,
        'comfort_rating': 3.2,
        'range_nm': 1800,
        'fuel_gal_hr': 95,
        'lease_monthly': 42_000,
        'purchase': 4_200_000,
        'maintenance_monthly': 8_500,
        'lifespan_years': 18,
        'crew_per_flight': 2,
    },
    'e145': {
        'name': 'Embraer ERJ-145',
        'category': 'Regional jet',
        'size': 'Small narrowbody',
        'seats': 50,
        'seats_min': 44,
        'seats_max': 50,
        'comfort_rating': 3.5,
        'range_nm': 1550,
        'fuel_gal_hr': 380,
        'lease_monthly': 118_000,
        'purchase': 16_500_000,
        'maintenance_monthly': 22_000,
        'lifespan_years': 22,
        'crew_per_flight': 3,
    },
    'e175': {
        'name': 'Embraer E175',
        'category': 'Regional jet',
        'size': 'Large regional',
        'seats': 76,
        'seats_min': 70,
        'seats_max': 76,
        'comfort_rating': 4.1,
        'range_nm': 2200,
        'fuel_gal_hr': 520,
        'lease_monthly': 185_000,
        'purchase': 28_000_000,
        'maintenance_monthly': 38_000,
        'lifespan_years': 25,
        'crew_per_flight': 4,
    },
    'a320': {
        'name': 'Airbus A320neo',
        'category': 'Narrowbody',
        'size': 'Medium',
        'seats': 180,
        'seats_min': 162,
        'seats_max': 180,
        'comfort_rating': 4.3,
        'range_nm': 3500,
        'fuel_gal_hr': 920,
        'lease_monthly': 340_000,
        'purchase': 55_000_000,
        'maintenance_monthly': 72_000,
        'lifespan_years': 28,
        'crew_per_flight': 5,
    },
    'b737': {
        'name': 'Boeing 737-800',
        'category': 'Narrowbody',
        'size': 'Medium',
        'seats': 162,
        'seats_min': 150,
        'seats_max': 162,
        'comfort_rating': 4.0,
        'range_nm': 3200,
        'fuel_gal_hr': 880,
        'lease_monthly': 310_000,
        'purchase': 52_000_000,
        'maintenance_monthly': 68_000,
        'lifespan_years': 28,
        'crew_per_flight': 5,
    },
}

# US-focused MVP airports (~55). Coordinates and scale from public data; gates approximate.
_AIRPORT_ROWS = [
    ('ATL', 'Hartsfield-Jackson Atlanta', 'Atlanta', 33.64, -84.43, 6.1, 110, 195, 8, False, 'Delta', 0.95),
    ('DFW', 'Dallas/Fort Worth', 'Dallas', 32.90, -97.04, 7.6, 87, 165, 14, False, 'American', 0.90),
    ('DEN', 'Denver Intl', 'Denver', 39.86, -104.67, 2.9, 78, 140, 22, False, 'United', 0.75),
    ('ORD', "O'Hare Intl", 'Chicago', 41.98, -87.90, 9.5, 80, 190, 6, False, 'United', 0.88),
    ('LAX', 'Los Angeles Intl', 'Los Angeles', 33.94, -118.41, 13.2, 88, 150, 10, False, 'American', 0.55),
    ('CLT', 'Charlotte Douglas', 'Charlotte', 35.21, -80.94, 2.7, 53, 115, 12, False, 'American', 0.92),
    ('LAS', 'Harry Reid Intl', 'Las Vegas', 36.08, -115.15, 2.3, 57, 110, 18, False, 'Southwest', 0.45),
    ('PHX', 'Phoenix Sky Harbor', 'Phoenix', 33.43, -112.01, 4.9, 52, 105, 16, False, 'American', 0.70),
    ('MCO', 'Orlando Intl', 'Orlando', 28.43, -81.31, 2.6, 57, 120, 15, False, None, 0.20),
    ('SEA', 'Seattle-Tacoma', 'Seattle', 47.45, -122.31, 4.0, 52, 95, 11, False, 'Alaska', 0.65),
    ('MIA', 'Miami Intl', 'Miami', 25.79, -80.29, 6.2, 50, 130, 9, False, 'American', 0.72),
    ('EWR', 'Newark Liberty', 'Newark', 40.69, -74.17, 20.1, 46, 125, 5, True, 'United', 0.80),
    ('SFO', 'San Francisco Intl', 'San Francisco', 37.62, -122.38, 4.7, 50, 115, 7, False, 'United', 0.68),
    ('IAH', 'George Bush Intercontinental', 'Houston', 29.98, -95.34, 7.1, 46, 130, 11, False, 'United', 0.82),
    ('BOS', 'Boston Logan', 'Boston', 42.36, -71.01, 4.9, 42, 95, 8, False, 'JetBlue', 0.55),
    ('FLL', 'Fort Lauderdale', 'Fort Lauderdale', 26.07, -80.15, 6.0, 35, 65, 14, False, 'Spirit', 0.35),
    ('MSP', 'Minneapolis-St Paul', 'Minneapolis', 44.88, -93.22, 3.7, 38, 130, 10, False, 'Delta', 0.90),
    ('DTW', 'Detroit Metro', 'Detroit', 42.21, -83.35, 4.3, 36, 120, 12, False, 'Delta', 0.88),
    ('PHL', 'Philadelphia Intl', 'Philadelphia', 39.87, -75.24, 6.2, 33, 125, 9, False, 'American', 0.70),
    ('LGA', 'LaGuardia', 'New York', 40.78, -73.87, 20.1, 30, 72, 3, True, 'Delta', 0.55),
    ('BWI', 'Baltimore/Washington', 'Baltimore', 39.18, -76.67, 9.8, 27, 75, 13, False, 'Southwest', 0.50),
    ('SLC', 'Salt Lake City', 'Salt Lake City', 40.79, -111.98, 1.2, 27, 85, 14, False, 'Delta', 0.85),
    ('DCA', 'Reagan National', 'Washington', 38.85, -77.04, 6.3, 24, 55, 2, True, 'American', 0.60),
    ('MDW', 'Chicago Midway', 'Chicago', 41.79, -87.75, 9.5, 22, 43, 4, False, 'Southwest', 0.78),
    ('BNA', 'Nashville Intl', 'Nashville', 36.12, -86.68, 2.0, 22, 55, 11, False, 'Southwest', 0.40),
    ('AUS', 'Austin-Bergstrom', 'Austin', 30.20, -97.67, 2.3, 22, 35, 9, False, 'Southwest', 0.35),
    ('SAN', 'San Diego Intl', 'San Diego', 32.73, -117.19, 3.3, 25, 51, 6, False, 'Alaska', 0.30),
    ('PDX', 'Portland Intl', 'Portland', 45.59, -122.60, 2.5, 20, 60, 8, False, 'Alaska', 0.45),
    ('STL', 'St Louis Lambert', 'St Louis', 38.75, -90.37, 2.8, 16, 70, 15, False, None, 0.15),
    ('MCI', 'Kansas City Intl', 'Kansas City', 39.30, -94.71, 2.2, 12, 45, 16, False, None, 0.10),
    ('RDU', 'Raleigh-Durham', 'Raleigh', 35.88, -78.79, 2.1, 14, 40, 10, False, None, 0.12),
    ('IND', 'Indianapolis Intl', 'Indianapolis', 39.72, -86.29, 2.1, 10, 48, 12, False, None, 0.08),
    ('CMH', 'John Glenn Columbus', 'Columbus', 39.99, -82.89, 2.1, 9, 42, 11, False, None, 0.08),
    ('PIT', 'Pittsburgh Intl', 'Pittsburgh', 40.49, -80.23, 2.4, 9, 75, 14, False, None, 0.10),
    ('CVG', 'Cincinnati/Northern KY', 'Cincinnati', 39.05, -84.66, 2.2, 9, 50, 10, False, None, 0.12),
    ('OAK', 'Oakland Intl', 'Oakland', 37.72, -122.22, 4.7, 11, 30, 7, False, 'Southwest', 0.25),
    ('SNA', 'John Wayne', 'Orange County', 33.68, -117.87, 13.2, 11, 22, 4, False, None, 0.10),
    ('RSW', 'Southwest Florida', 'Fort Myers', 26.54, -81.76, 1.1, 11, 28, 8, False, None, 0.08),
    ('PBI', 'Palm Beach Intl', 'West Palm Beach', 26.68, -80.10, 6.2, 7, 25, 6, False, None, 0.08),
    ('SAT', 'San Antonio Intl', 'San Antonio', 29.53, -98.47, 2.6, 10, 35, 9, False, None, 0.10),
    ('HOU', 'William P Hobby', 'Houston', 29.65, -95.28, 7.1, 14, 30, 5, False, 'Southwest', 0.55),
    ('TPA', 'Tampa Intl', 'Tampa', 27.98, -82.53, 3.2, 22, 60, 10, False, None, 0.15),
    ('JFK', 'John F Kennedy', 'New York', 40.64, -73.78, 20.1, 62, 130, 4, True, 'JetBlue', 0.45),
    ('SJC', 'San Jose Intl', 'San Jose', 37.36, -121.93, 4.7, 15, 35, 7, False, None, 0.12),
    ('SMF', 'Sacramento Intl', 'Sacramento', 38.70, -121.59, 2.4, 12, 32, 9, False, None, 0.08),
    ('MSY', 'Louis Armstrong New Orleans', 'New Orleans', 29.99, -90.26, 1.3, 10, 35, 8, False, None, 0.10),
    ('MEM', 'Memphis Intl', 'Memphis', 35.04, -89.98, 1.4, 5, 60, 18, False, None, 0.05),
    ('OMA', 'Eppley Airfield', 'Omaha', 41.30, -95.89, 0.9, 5, 24, 10, False, None, 0.06),
    ('DSM', 'Des Moines Intl', 'Des Moines', 41.53, -93.66, 0.7, 3, 20, 9, False, None, 0.05),
    ('GRR', 'Gerald R Ford Intl', 'Grand Rapids', 42.88, -85.52, 1.1, 3, 18, 8, False, None, 0.05),
    ('PWM', 'Portland Intl Jetport', 'Portland ME', 43.65, -70.31, 0.5, 2, 12, 6, False, None, 0.04),
    ('BTV', 'Burlington Intl', 'Burlington', 44.47, -73.15, 0.2, 1, 11, 5, False, None, 0.03),
    ('PVU', 'Provo Municipal', 'Provo', 40.22, -111.72, 0.7, 0.8, 6, 4, False, 'Breeze', 0.35),
    ('ISP', 'Long Island MacArthur', 'Islip', 40.79, -73.10, 20.1, 1.5, 10, 5, False, None, 0.08),
    ('LIT', 'Bill and Hillary Clinton', 'Little Rock', 34.73, -92.22, 0.7, 2, 14, 7, False, None, 0.05),
    # Ohio regionals — small terminals for turboprop / ERJ ops
    ('DAY', 'James M Cox Dayton Intl', 'Dayton', 39.90, -84.22, 0.85, 2.2, 18, 14, False, None, 0.06, 'OH'),
    ('LUK', 'Cincinnati Lunken', 'Cincinnati', 39.10, -84.42, 2.2, 0.45, 8, 9, False, None, 0.04, 'OH'),
    ('TOL', 'Toledo Express', 'Toledo', 41.59, -83.81, 0.65, 0.8, 14, 11, False, None, 0.05, 'OH'),
    ('CAK', 'Akron-Canton', 'Akron', 40.92, -81.44, 0.70, 1.6, 16, 12, False, None, 0.06, 'OH'),
    ('YNG', 'Youngstown-Warren', 'Youngstown', 41.26, -80.68, 0.45, 0.15, 6, 8, False, None, 0.03, 'OH'),
    ('FDY', 'Findlay Airport', 'Findlay', 41.01, -83.67, 0.10, 0.05, 4, 6, False, None, 0.02, 'OH'),
    # Ohio-region neighbors
    ('LEX', 'Blue Grass', 'Lexington', 38.04, -84.61, 0.75, 1.4, 12, 10, False, None, 0.06, 'KY'),
    ('SDF', 'Louisville Muhammad Ali Intl', 'Louisville', 38.17, -85.74, 1.2, 4.5, 22, 14, False, None, 0.10, 'KY'),
]

# Real-world passenger incumbents (approx. market share for sim flavor, 2025–2026 public sources).
INCUMBENTS_BY_IATA = {
    'CVG': [
        {'airline': 'Allegiant', 'share': 0.26, 'tier': 'lcc'},
        {'airline': 'Delta', 'share': 0.21, 'tier': 'legacy'},
        {'airline': 'American', 'share': 0.16, 'tier': 'legacy'},
        {'airline': 'Frontier', 'share': 0.11, 'tier': 'lcc'},
        {'airline': 'Southwest', 'share': 0.08, 'tier': 'lcc'},
        {'airline': 'Sun Country', 'share': 0.04, 'tier': 'lcc'},
    ],
    'CMH': [
        {'airline': 'Southwest', 'share': 0.28, 'tier': 'lcc'},
        {'airline': 'American', 'share': 0.18, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.16, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.12, 'tier': 'legacy'},
        {'airline': 'Frontier', 'share': 0.09, 'tier': 'lcc'},
        {'airline': 'Allegiant', 'share': 0.07, 'tier': 'lcc'},
    ],
    'DAY': [
        {'airline': 'Allegiant', 'share': 0.52, 'tier': 'lcc'},
        {'airline': 'American', 'share': 0.28, 'tier': 'legacy'},
    ],
    'LUK': [
        {'airline': 'Ultimate Air Shuttle', 'share': 0.42, 'tier': 'shuttle'},
        {'airline': 'Charter / GA', 'share': 0.38, 'tier': 'charter'},
    ],
    'CAK': [
        {'airline': 'Allegiant', 'share': 0.34, 'tier': 'lcc'},
        {'airline': 'American', 'share': 0.22, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.18, 'tier': 'legacy'},
    ],
    'TOL': [
        {'airline': 'Allegiant', 'share': 0.44, 'tier': 'lcc'},
        {'airline': 'American', 'share': 0.20, 'tier': 'legacy'},
    ],
    'YNG': [
        {'airline': 'Allegiant', 'share': 0.35, 'tier': 'lcc'},
        {'airline': 'Southern Airways Express', 'share': 0.18, 'tier': 'regional'},
    ],
    'FDY': [
        {'airline': 'Charter / GA', 'share': 0.55, 'tier': 'charter'},
    ],
    'IND': [
        {'airline': 'Southwest', 'share': 0.30, 'tier': 'lcc'},
        {'airline': 'Delta', 'share': 0.18, 'tier': 'legacy'},
        {'airline': 'American', 'share': 0.16, 'tier': 'legacy'},
        {'airline': 'Allegiant', 'share': 0.10, 'tier': 'lcc'},
        {'airline': 'Frontier', 'share': 0.08, 'tier': 'lcc'},
    ],
    'PIT': [
        {'airline': 'Southwest', 'share': 0.26, 'tier': 'lcc'},
        {'airline': 'American', 'share': 0.18, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.16, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.12, 'tier': 'legacy'},
        {'airline': 'Frontier', 'share': 0.08, 'tier': 'lcc'},
    ],
    'DTW': [
        {'airline': 'Delta', 'share': 0.68, 'tier': 'legacy'},
        {'airline': 'American', 'share': 0.08, 'tier': 'legacy'},
        {'airline': 'Southwest', 'share': 0.07, 'tier': 'lcc'},
        {'airline': 'United', 'share': 0.06, 'tier': 'legacy'},
    ],
    'LEX': [
        {'airline': 'American', 'share': 0.32, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.24, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.14, 'tier': 'legacy'},
        {'airline': 'Allegiant', 'share': 0.10, 'tier': 'lcc'},
    ],
    'SDF': [
        {'airline': 'Southwest', 'share': 0.30, 'tier': 'lcc'},
        {'airline': 'American', 'share': 0.22, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.18, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.10, 'tier': 'legacy'},
    ],
}

OHIO_REGION_IATA = [
    'DAY', 'LUK', 'CVG', 'CMH', 'TOL', 'CAK', 'YNG', 'FDY',
    'IND', 'PIT', 'LEX', 'SDF', 'DTW',
]

def _build_airport(r):
    iata = r[0]
    incumbents = INCUMBENTS_BY_IATA.get(iata, [])
    hub_airline = r[10]
    hub_strength = r[11]
    if incumbents:
        hub_airline = incumbents[0]['airline']
        hub_strength = max(x['share'] for x in incumbents)
    metro = r[5]
    pax = r[6]
    wealth_index = round(min(1.0, max(0.06, 0.06 + metro * 0.11 + pax * 0.012)), 3)
    luxury_share = round(min(0.45, max(0.02, 0.04 + metro * 0.028 + (0.14 if r[9] else 0.02))), 3)
    if pax < 2.0:
        luxury_share = round(luxury_share * 0.55, 3)
    if pax < 0.6:
        wealth_index = round(wealth_index * 0.62, 3)
        luxury_share = round(luxury_share * 0.45, 3)
    return {
        'iata': iata,
        'name': r[1],
        'city': r[2],
        'lat': r[3],
        'lon': r[4],
        'metro_pop_m': metro,
        'annual_pax_m': pax,
        'gates_total': r[7],
        'gates_available': r[8],
        'slot_controlled': r[9],
        'hub_airline': hub_airline,
        'hub_strength': hub_strength,
        'incumbents': incumbents,
        'wealth_index': wealth_index,
        'luxury_share': luxury_share,
        'state': r[12] if len(r) > 12 else None,
        'lease_exclusive_monthly': int(12_000 + r[6] * 800 + (20 if r[9] else 0)),
        'lease_common_monthly': int(5_000 + r[6] * 350),
        'seasonal_reliability': 0.92 if iata in ('ORD', 'DTW', 'BOS', 'MSP', 'DEN') else 0.98,
        'regional': r[6] < 3 or (len(r) > 12 and r[12] in ('OH', 'KY')),
    }


AIRPORTS = [_build_airport(r) for r in _AIRPORT_ROWS]

AIRPORT_BY_IATA = {a['iata']: a for a in AIRPORTS}

SCENARIOS = {
    'ohio_regional_2026': {
        'id': 'ohio_regional_2026',
        'name': '2026 — Ohio Regional',
        'tagline': 'Real competitors · regional airports · prove the model locally.',
        'year': 2026,
        'region': 'ohio',
        'briefing': (
            'You are building a regional airline in Ohio and nearby markets. Allegiant dominates Dayton; '
            'Delta still matters at CVG; Lunken is turboprop and shuttle territory. Lease a PC-12, win thin '
            'routes like DAY–CMH, and watch net worth grow before you take on Detroit or Cincinnati mainline.'
        ),
        'cash': 3_200_000,
        'debt': [],
        'bonds': [],
        'equity_pct': 100.0,
        'reputation': 8,
        'brand_awareness': {'DAY': 14},
        'financing_tier': 'startup',
        'bond_rating': 'B',
        'player_name': 'CEO',
        'airline_name': 'Buckeye Air',
        'fleet': [
            {'id': 'oh-1', 'type': 'pc12', 'leased': True, 'lease_months_left': 48, 'seats': 9},
        ],
        'gates': [
            {'airport': 'DAY', 'tier': 'common', 'years_left': 3, 'monthly': 7_200},
        ],
        'routes': [],
    },
    'beginner_2026': {
        'id': 'beginner_2026',
        'name': '2026 — Beginner',
        'tagline': 'Learn the ropes — leased jets, hub gates, already profitable.',
        'year': 2026,
        'briefing': (
            'Training scenario. You run Gateway Air, a small Midwest carrier with two leased E175s, '
            'gates at Columbus, Indianapolis, and Nashville, and two established routes already in the black. '
            'Explore the map, fleet, and finance tabs before trying Greenfield or Lake State.'
        ),
        'cash': 12_000_000,
        'debt': [],
        'bonds': [],
        'equity_pct': 100.0,
        'reputation': 32,
        'brand_awareness': {'CMH': 62, 'IND': 58, 'BNA': 55},
        'financing_tier': 'startup',
        'bond_rating': 'BB',
        'airline_name': 'Gateway Air',
        'fleet': [
            {'id': 'ga-1', 'type': 'e175', 'leased': True, 'lease_months_left': 48, 'seats': 76},
            {'id': 'ga-2', 'type': 'e175', 'leased': True, 'lease_months_left': 48, 'seats': 76},
        ],
        'gates': [
            {'airport': 'CMH', 'tier': 'exclusive', 'years_left': 4, 'monthly': 18_000},
            {'airport': 'IND', 'tier': 'common', 'years_left': 3, 'monthly': 9_000},
            {'airport': 'BNA', 'tier': 'common', 'years_left': 3, 'monthly': 11_000},
        ],
        'routes': [
            {
                'id': 'ga-r1',
                'origin': 'CMH',
                'dest': 'BNA',
                'aircraft_type': 'e175',
                'frequency_week': 21,
                'fare': 169,
                'aircraft_id': 'ga-1',
            },
            {
                'id': 'ga-r2',
                'origin': 'IND',
                'dest': 'CMH',
                'aircraft_type': 'e175',
                'frequency_week': 21,
                'fare': 159,
                'aircraft_id': 'ga-2',
            },
        ],
    },
    'greenfield_2026': {
        'id': 'greenfield_2026',
        'name': '2026 — Greenfield Startup',
        'tagline': 'Pitch deck, no planes, brutal hubs.',
        'year': 2026,
        'briefing': (
            'Present day. Fortress hubs are locked. You have a concept and $500K of founder savings. '
            'Prove the model on unconstrained airports (Provo, Islip, secondary cities) before touching ATL or ORD.'
        ),
        'cash': 500_000,
        'debt': [],
        'bonds': [],
        'equity_pct': 100.0,
        'reputation': 0,
        'brand_awareness': {},
        'financing_tier': 'startup',
        'airline_name': 'Your Airline',
        'fleet': [],
        'gates': [],
        'routes': [],
    },
    'exit_ceo': {
        'id': 'exit_ceo',
        'name': 'The Exit — Former Regional CEO',
        'tagline': 'Sold your last airline. Capital and credibility.',
        'year': 2026,
        'briefing': (
            'You sold a successful regional for $180M two years ago. You kept $45M liquid, gave 15% to a '
            'co-founding team, and retain deep investor and lessor relationships. Banks know your name. '
            'Seed rounds are beneath you — but hub incumbents still fight you the same way.'
        ),
        'cash': 45_000_000,
        'debt': [],
        'bonds': [],
        'equity_pct': 85.0,
        'reputation': 35,
        'brand_awareness': {'BNA': 15, 'AUS': 12, 'RDU': 10},
        'financing_tier': 'serial',
        'bond_rating': 'BB',
        'airline_name': 'Meridian Air',
        'fleet': [],
        'gates': [],
        'routes': [],
    },
    'inheritance': {
        'id': 'inheritance',
        'name': 'Inheritance — Lake State Air',
        'tagline': 'Debt-laden regional; fix it or fold.',
        'year': 2026,
        'briefing': (
            'A family member left you Lake State Air — 4 leased E175s, gates at GRR, DSM, and OMA, '
            'three thin local routes, $2.1M cash, and $28M term debt at 9.2%. Creditors want a plan. '
            'You can restructure debt, issue asset-backed bonds, or sell gates to survive.'
        ),
        'cash': 2_100_000,
        'debt': [
            {
                'id': 'inherit_term',
                'name': 'Inherited term loan',
                'principal': 28_000_000,
                'rate': 0.092,
                'monthly_payment': 265_000,
                'secured': True,
            }
        ],
        'bonds': [],
        'equity_pct': 100.0,
        'reputation': 8,
        'brand_awareness': {'GRR': 42, 'DSM': 38, 'OMA': 35},
        'financing_tier': 'distressed',
        'bond_rating': 'B',
        'airline_name': 'Lake State Air',
        'fleet': [
            {'id': 'lsa-1', 'type': 'e175', 'leased': True, 'lease_months_left': 36},
            {'id': 'lsa-2', 'type': 'e175', 'leased': True, 'lease_months_left': 36},
            {'id': 'lsa-3', 'type': 'e175', 'leased': True, 'lease_months_left': 24},
            {'id': 'lsa-4', 'type': 'e175', 'leased': True, 'lease_months_left': 24},
        ],
        'gates': [
            {'airport': 'GRR', 'tier': 'exclusive', 'years_left': 3, 'monthly': 28_000},
            {'airport': 'DSM', 'tier': 'common', 'years_left': 2, 'monthly': 12_000},
            {'airport': 'OMA', 'tier': 'common', 'years_left': 4, 'monthly': 14_000},
        ],
        'routes': [
            {
                'id': 'lsa-r1',
                'origin': 'GRR',
                'dest': 'ORD',
                'aircraft_type': 'e175',
                'frequency_week': 14,
                'fare': 189,
                'aircraft_id': 'lsa-1',
            },
            {
                'id': 'lsa-r2',
                'origin': 'DSM',
                'dest': 'ORD',
                'aircraft_type': 'e175',
                'frequency_week': 10,
                'fare': 165,
                'aircraft_id': 'lsa-2',
            },
            {
                'id': 'lsa-r3',
                'origin': 'OMA',
                'dest': 'DEN',
                'aircraft_type': 'e175',
                'frequency_week': 7,
                'fare': 149,
                'aircraft_id': 'lsa-3',
            },
        ],
    },
}

FINANCING_OPTIONS = {
    'seed_equity': {
        'name': 'Seed round (equity)',
        'tiers': ['startup'],
        'min_day': 0,
        'amount_range': (2_000_000, 8_000_000),
        'dilution': (0.18, 0.28),
        'requires_routes': 0,
    },
    'series_a': {
        'name': 'Series A (equity)',
        'tiers': ['startup', 'serial'],
        'min_day': 180,
        'amount_range': (15_000_000, 55_000_000),
        'dilution': (0.20, 0.32),
        'requires_routes': 2,
        'requires_ltm_revenue': 8_000_000,
    },
    'growth_equity': {
        'name': 'Growth equity (former CEO network)',
        'tiers': ['serial'],
        'min_day': 0,
        'amount_range': (25_000_000, 80_000_000),
        'dilution': (0.12, 0.20),
        'requires_routes': 0,
    },
    'bank_term_loan': {
        'name': 'Bank term loan',
        'tiers': ['startup', 'serial', 'distressed'],
        'min_day': 90,
        'amount_range': (5_000_000, 30_000_000),
        'rate_range': (0.075, 0.11),
        'term_months': 60,
        'requires_routes': 1,
        'covenants': 'Min cash $1M; debt service coverage > 1.1x quarterly',
    },
    'aircraft_financing': {
        'name': 'Aircraft sale-leaseback / secured note',
        'tiers': ['startup', 'serial', 'distressed'],
        'per_aircraft_pct': 0.65,
        'rate_range': (0.065, 0.095),
        'term_months': 84,
        'requires_owned_aircraft': True,
    },
    'corporate_bonds': {
        'name': 'Corporate bond issuance',
        'tiers': ['startup', 'serial', 'distressed'],
        'min_day': 365,
        'amount_range': (10_000_000, 150_000_000),
        'coupon_by_rating': {'BB': 0.072, 'B': 0.095, 'BBB': 0.058, 'CCC': 0.14},
        'term_months': 120,
        'requires_ltm_revenue': 25_000_000,
        'requires_routes': 4,
    },
    'asset_backed_bonds': {
        'name': 'Asset-backed bonds (gates + routes)',
        'tiers': ['distressed', 'serial'],
        'min_day': 0,
        'amount_range': (5_000_000, 40_000_000),
        'coupon': 0.088,
        'term_months': 60,
        'requires_gates': 2,
        'secured': True,
    },
    'debt_restructure': {
        'name': 'Debt restructuring (creditor workout)',
        'tiers': ['distressed'],
        'min_day': 0,
        'effect': 'extend_maturity_reduce_payment',
        'requires_debt': True,
    },
}

FUEL_BASE_USD_GAL = 2.85
CREW_COST_PER_BLOCK_HOUR = 420
AIRPORT_FEE_PER_DEPARTURE = 2800

# US macro baseline (2026 present-day scenario).
MACRO_USA_BASE = {
    'country': 'United States',
    'inflation_pct': 2.4,
    'gdp_growth_pct': 2.1,
    'gdp_index': 100.0,
    'travel_spend_index': 100.0,
    'travel_spend_growth_pct': 2.5,
    'country_health': 72,
    'ota_market_penetration_pct': 74,
}

# Online travel agencies / metasearch — listing fees and demand reach.
OTA_PLATFORMS = [
    {
        'id': 'expedia',
        'name': 'Expedia',
        'listing_monthly': 28_000,
        'commission_pct': 12,
        'demand_reach': 0.22,
        'marketing_amplify': 1.35,
    },
    {
        'id': 'google_flights',
        'name': 'Google Flights',
        'listing_monthly': 9_500,
        'commission_pct': 0,
        'demand_reach': 0.18,
        'marketing_amplify': 1.15,
    },
    {
        'id': 'kayak',
        'name': 'Kayak',
        'listing_monthly': 16_000,
        'commission_pct': 10,
        'demand_reach': 0.14,
        'marketing_amplify': 1.2,
    },
    {
        'id': 'travelocity',
        'name': 'Travelocity',
        'listing_monthly': 12_000,
        'commission_pct': 11,
        'demand_reach': 0.1,
        'marketing_amplify': 1.12,
    },
]

TIME_SPEEDS = [
    {'id': 'pause', 'label': 'Pause', 'days_per_tick': 0, 'hours_per_tick': 0},
    {'id': 'slow', 'label': 'Slow (4 hr)', 'days_per_tick': 0, 'hours_per_tick': 4},
    {'id': 'day', 'label': 'Normal (1 day)', 'days_per_tick': 1, 'hours_per_tick': 0},
    {'id': 'week', 'label': 'Fast (1 week)', 'days_per_tick': 7, 'hours_per_tick': 0},
    {'id': 'month', 'label': 'Faster (1 month)', 'days_per_tick': 30, 'hours_per_tick': 0},
]

TICK_MS = {'pause': 0, 'slow': 1100, 'day': 750, 'week': 580, 'month': 460}

# Well-traveled city pairs (either direction) — boosts route suggestions & demand hint.
COMMON_ROUTE_PAIRS = [
    ('DAY', 'CMH'), ('DAY', 'CVG'), ('DAY', 'IND'), ('CVG', 'CMH'), ('CVG', 'IND'),
    ('CMH', 'IND'), ('CMH', 'BNA'), ('IND', 'ORD'), ('BNA', 'ATL'), ('CMH', 'ORD'),
    ('DAY', 'ORD'), ('LUK', 'CVG'), ('LUK', 'CMH'), ('CAK', 'CMH'), ('TOL', 'ORD'),
    ('GRR', 'ORD'), ('DSM', 'ORD'), ('OMA', 'DEN'), ('RDU', 'ATL'), ('AUS', 'DFW'),
]


def get_runway_bootstrap():
    """JSON-safe payload for the browser game."""
    return {
        'airports': AIRPORTS,
        'aircraft_types': AIRCRAFT_TYPES,
        'scenarios': SCENARIOS,
        'financing_options': FINANCING_OPTIONS,
        'fuel_base': FUEL_BASE_USD_GAL,
        'crew_cost_per_block_hour': CREW_COST_PER_BLOCK_HOUR,
        'airport_fee_per_departure': AIRPORT_FEE_PER_DEPARTURE,
        'macro_usa_base': MACRO_USA_BASE,
        'ota_platforms': OTA_PLATFORMS,
        'time_speeds': TIME_SPEEDS,
        'tick_ms': TICK_MS,
        'common_route_pairs': COMMON_ROUTE_PAIRS,
        'ohio_region_iata': OHIO_REGION_IATA,
    }