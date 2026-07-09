"""RouteLab — airline network economics simulation data (MVP v0.1)."""

import os

RUNWAY_OWNER = 'thomas_ellison'

# Public Mapbox client token — set MAPBOX_ACCESS_TOKEN in Render/local .env.
RUNWAY_MAPBOX_TOKEN = os.environ.get('MAPBOX_ACCESS_TOKEN', '').strip()

# When true, /airline and /runway are playable without Hub login (shareable link).
RUNWAY_PUBLIC_ACCESS = os.environ.get('RUNWAY_PUBLIC_ACCESS', '').strip().lower() in (
    '1', 'true', 'yes', 'on',
)

# Optional share link: https://yoursite/airline?access=<token> (no Hub account required).
RUNWAY_SHARE_TOKEN = os.environ.get('RUNWAY_SHARE_TOKEN', '').strip()

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
        'target_block_hours_day': 6.5,
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
        'target_block_hours_day': 8.5,
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
        'target_block_hours_day': 9.5,
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
        'target_block_hours_day': 10.0,
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
        'target_block_hours_day': 10.0,
    },
}

# Midwest states covered by regional scenarios (Ohio Valley + Great Lakes + upper South).
MIDWEST_STATE_CODES = frozenset({
    'PA', 'OH', 'KY', 'IN', 'MI', 'TN', 'IL', 'WI', 'MN', 'MO', 'IA', 'WV',
})

# Real-world-ish competitor routes in the Ohio regional network (seed for active AI).
OHIO_COMPETITOR_ROUTE_SEEDS = [
    {'airline': 'Allegiant', 'origin': 'DAY', 'dest': 'CVG', 'frequency_week': 4, 'fare': 69, 'tier': 'lcc'},
    {'airline': 'Allegiant', 'origin': 'TOL', 'dest': 'CVG', 'frequency_week': 3, 'fare': 79, 'tier': 'lcc'},
    {'airline': 'Allegiant', 'origin': 'CAK', 'dest': 'CVG', 'frequency_week': 3, 'fare': 75, 'tier': 'lcc'},
    {'airline': 'Delta', 'origin': 'CVG', 'dest': 'DTW', 'frequency_week': 21, 'fare': 189, 'tier': 'legacy'},
    {'airline': 'Delta', 'origin': 'DTW', 'dest': 'CMH', 'frequency_week': 14, 'fare': 159, 'tier': 'legacy'},
    {'airline': 'Southwest', 'origin': 'CMH', 'dest': 'CVG', 'frequency_week': 7, 'fare': 119, 'tier': 'lcc'},
    {'airline': 'American', 'origin': 'CMH', 'dest': 'DAY', 'frequency_week': 14, 'fare': 139, 'tier': 'legacy'},
    {'airline': 'Frontier', 'origin': 'CMH', 'dest': 'CVG', 'frequency_week': 4, 'fare': 89, 'tier': 'lcc'},
    {'airline': 'United', 'origin': 'CMH', 'dest': 'IND', 'frequency_week': 14, 'fare': 149, 'tier': 'legacy'},
    {'airline': 'Southwest', 'origin': 'IND', 'dest': 'CMH', 'frequency_week': 7, 'fare': 129, 'tier': 'lcc'},
    {'airline': 'American', 'origin': 'PIT', 'dest': 'CMH', 'frequency_week': 7, 'fare': 159, 'tier': 'legacy'},
    {'airline': 'Delta', 'origin': 'CVG', 'dest': 'CMH', 'frequency_week': 14, 'fare': 169, 'tier': 'legacy'},
]

# Full Midwest competitor network (Ohio seeds + PA/KY/IN/MI/TN/IL/WI/MN/MO/IA/WV).
_MIDWEST_EXTRA_COMPETITOR_SEEDS = [
    # Pennsylvania
    {'airline': 'American', 'origin': 'PHL', 'dest': 'PIT', 'frequency_week': 21, 'fare': 149, 'tier': 'legacy'},
    {'airline': 'Southwest', 'origin': 'PHL', 'dest': 'MDW', 'frequency_week': 14, 'fare': 129, 'tier': 'lcc'},
    {'airline': 'Frontier', 'origin': 'PHL', 'dest': 'CVG', 'frequency_week': 4, 'fare': 89, 'tier': 'lcc'},
    {'airline': 'American', 'origin': 'MDT', 'dest': 'ORD', 'frequency_week': 14, 'fare': 159, 'tier': 'legacy'},
    {'airline': 'Allegiant', 'origin': 'LBE', 'dest': 'PIA', 'frequency_week': 3, 'fare': 59, 'tier': 'lcc'},
    {'airline': 'Allegiant', 'origin': 'AVP', 'dest': 'PIT', 'frequency_week': 3, 'fare': 65, 'tier': 'lcc'},
    {'airline': 'United', 'origin': 'ABE', 'dest': 'ORD', 'frequency_week': 7, 'fare': 139, 'tier': 'legacy'},
    {'airline': 'Allegiant', 'origin': 'ERI', 'dest': 'PIA', 'frequency_week': 2, 'fare': 55, 'tier': 'lcc'},
    {'airline': 'American', 'origin': 'PIT', 'dest': 'PHL', 'frequency_week': 14, 'fare': 139, 'tier': 'legacy'},
    # Kentucky
    {'airline': 'Southwest', 'origin': 'SDF', 'dest': 'BNA', 'frequency_week': 7, 'fare': 109, 'tier': 'lcc'},
    {'airline': 'American', 'origin': 'LEX', 'dest': 'CMH', 'frequency_week': 7, 'fare': 149, 'tier': 'legacy'},
    {'airline': 'Delta', 'origin': 'SDF', 'dest': 'DTW', 'frequency_week': 7, 'fare': 169, 'tier': 'legacy'},
    {'airline': 'Allegiant', 'origin': 'SDF', 'dest': 'PIA', 'frequency_week': 3, 'fare': 69, 'tier': 'lcc'},
    {'airline': 'American', 'origin': 'LEX', 'dest': 'ORD', 'frequency_week': 7, 'fare': 159, 'tier': 'legacy'},
    # Indiana
    {'airline': 'Southwest', 'origin': 'IND', 'dest': 'MDW', 'frequency_week': 14, 'fare': 99, 'tier': 'lcc'},
    {'airline': 'Allegiant', 'origin': 'IND', 'dest': 'PIA', 'frequency_week': 4, 'fare': 59, 'tier': 'lcc'},
    {'airline': 'American', 'origin': 'FWA', 'dest': 'ORD', 'frequency_week': 7, 'fare': 149, 'tier': 'legacy'},
    {'airline': 'Allegiant', 'origin': 'SBN', 'dest': 'PIA', 'frequency_week': 3, 'fare': 65, 'tier': 'lcc'},
    {'airline': 'Allegiant', 'origin': 'EVV', 'dest': 'PIA', 'frequency_week': 2, 'fare': 59, 'tier': 'lcc'},
    {'airline': 'United', 'origin': 'GYY', 'dest': 'ORD', 'frequency_week': 4, 'fare': 89, 'tier': 'legacy'},
    {'airline': 'Delta', 'origin': 'IND', 'dest': 'DTW', 'frequency_week': 14, 'fare': 149, 'tier': 'legacy'},
    # Michigan
    {'airline': 'Delta', 'origin': 'DTW', 'dest': 'ORD', 'frequency_week': 28, 'fare': 139, 'tier': 'legacy'},
    {'airline': 'Delta', 'origin': 'DTW', 'dest': 'MSP', 'frequency_week': 21, 'fare': 159, 'tier': 'legacy'},
    {'airline': 'American', 'origin': 'GRR', 'dest': 'ORD', 'frequency_week': 14, 'fare': 149, 'tier': 'legacy'},
    {'airline': 'Allegiant', 'origin': 'FNT', 'dest': 'PIA', 'frequency_week': 3, 'fare': 59, 'tier': 'lcc'},
    {'airline': 'Allegiant', 'origin': 'TVC', 'dest': 'PIA', 'frequency_week': 3, 'fare': 79, 'tier': 'lcc'},
    {'airline': 'Delta', 'origin': 'LAN', 'dest': 'DTW', 'frequency_week': 14, 'fare': 129, 'tier': 'legacy'},
    {'airline': 'United', 'origin': 'MBS', 'dest': 'ORD', 'frequency_week': 7, 'fare': 139, 'tier': 'legacy'},
    {'airline': 'American', 'origin': 'AZO', 'dest': 'ORD', 'frequency_week': 4, 'fare': 129, 'tier': 'legacy'},
    # Tennessee
    {'airline': 'Southwest', 'origin': 'BNA', 'dest': 'MDW', 'frequency_week': 14, 'fare': 119, 'tier': 'lcc'},
    {'airline': 'Southwest', 'origin': 'BNA', 'dest': 'STL', 'frequency_week': 7, 'fare': 109, 'tier': 'lcc'},
    {'airline': 'American', 'origin': 'BNA', 'dest': 'CMH', 'frequency_week': 7, 'fare': 149, 'tier': 'legacy'},
    {'airline': 'Allegiant', 'origin': 'TYS', 'dest': 'PIA', 'frequency_week': 4, 'fare': 69, 'tier': 'lcc'},
    {'airline': 'Allegiant', 'origin': 'CHA', 'dest': 'PIA', 'frequency_week': 3, 'fare': 59, 'tier': 'lcc'},
    {'airline': 'Delta', 'origin': 'MEM', 'dest': 'DTW', 'frequency_week': 7, 'fare': 169, 'tier': 'legacy'},
    {'airline': 'American', 'origin': 'TRI', 'dest': 'CMH', 'frequency_week': 4, 'fare': 159, 'tier': 'legacy'},
    {'airline': 'Southwest', 'origin': 'TYS', 'dest': 'BNA', 'frequency_week': 7, 'fare': 99, 'tier': 'lcc'},
    # Illinois / Chicago
    {'airline': 'United', 'origin': 'ORD', 'dest': 'MSP', 'frequency_week': 21, 'fare': 159, 'tier': 'legacy'},
    {'airline': 'American', 'origin': 'ORD', 'dest': 'STL', 'frequency_week': 14, 'fare': 149, 'tier': 'legacy'},
    {'airline': 'Southwest', 'origin': 'MDW', 'dest': 'STL', 'frequency_week': 14, 'fare': 99, 'tier': 'lcc'},
    {'airline': 'Allegiant', 'origin': 'RFD', 'dest': 'PIA', 'frequency_week': 3, 'fare': 65, 'tier': 'lcc'},
    {'airline': 'American', 'origin': 'PIA', 'dest': 'ORD', 'frequency_week': 7, 'fare': 139, 'tier': 'legacy'},
    {'airline': 'United', 'origin': 'SPI', 'dest': 'ORD', 'frequency_week': 4, 'fare': 129, 'tier': 'legacy'},
    # Wisconsin / Minnesota
    {'airline': 'Southwest', 'origin': 'MKE', 'dest': 'MDW', 'frequency_week': 14, 'fare': 89, 'tier': 'lcc'},
    {'airline': 'Delta', 'origin': 'MSP', 'dest': 'DTW', 'frequency_week': 21, 'fare': 149, 'tier': 'legacy'},
    {'airline': 'United', 'origin': 'MSN', 'dest': 'ORD', 'frequency_week': 14, 'fare': 139, 'tier': 'legacy'},
    {'airline': 'American', 'origin': 'GRB', 'dest': 'ORD', 'frequency_week': 7, 'fare': 129, 'tier': 'legacy'},
    {'airline': 'Delta', 'origin': 'DLH', 'dest': 'MSP', 'frequency_week': 7, 'fare': 149, 'tier': 'legacy'},
    # Missouri / Iowa
    {'airline': 'Southwest', 'origin': 'STL', 'dest': 'MDW', 'frequency_week': 14, 'fare': 109, 'tier': 'lcc'},
    {'airline': 'Southwest', 'origin': 'MCI', 'dest': 'MDW', 'frequency_week': 10, 'fare': 119, 'tier': 'lcc'},
    {'airline': 'American', 'origin': 'CID', 'dest': 'ORD', 'frequency_week': 7, 'fare': 139, 'tier': 'legacy'},
    {'airline': 'United', 'origin': 'DSM', 'dest': 'ORD', 'frequency_week': 10, 'fare': 129, 'tier': 'legacy'},
    {'airline': 'United', 'origin': 'OMA', 'dest': 'ORD', 'frequency_week': 10, 'fare': 129, 'tier': 'legacy'},
    {'airline': 'American', 'origin': 'SGF', 'dest': 'ORD', 'frequency_week': 7, 'fare': 149, 'tier': 'legacy'},
    # West Virginia
    {'airline': 'American', 'origin': 'CRW', 'dest': 'CMH', 'frequency_week': 7, 'fare': 159, 'tier': 'legacy'},
    {'airline': 'Allegiant', 'origin': 'HTS', 'dest': 'PIA', 'frequency_week': 2, 'fare': 59, 'tier': 'lcc'},
    # Cross-midwest thin routes
    {'airline': 'American', 'origin': 'CMH', 'dest': 'PHL', 'frequency_week': 7, 'fare': 149, 'tier': 'legacy'},
    {'airline': 'United', 'origin': 'IND', 'dest': 'ORD', 'frequency_week': 14, 'fare': 149, 'tier': 'legacy'},
    {'airline': 'Frontier', 'origin': 'CVG', 'dest': 'ORD', 'frequency_week': 4, 'fare': 89, 'tier': 'lcc'},
    {'airline': 'American', 'origin': 'PIT', 'dest': 'ORD', 'frequency_week': 7, 'fare': 159, 'tier': 'legacy'},
    {'airline': 'Southwest', 'origin': 'BNA', 'dest': 'STL', 'frequency_week': 7, 'fare': 109, 'tier': 'lcc'},
    {'airline': 'Delta', 'origin': 'MEM', 'dest': 'BNA', 'frequency_week': 7, 'fare': 139, 'tier': 'legacy'},
    {'airline': 'United', 'origin': 'MKE', 'dest': 'ORD', 'frequency_week': 14, 'fare': 119, 'tier': 'legacy'},
]

MIDWEST_COMPETITOR_ROUTE_SEEDS = OHIO_COMPETITOR_ROUTE_SEEDS + _MIDWEST_EXTRA_COMPETITOR_SEEDS

ANCILLARY_MODES = [
    {'id': 'auto', 'label': 'Balanced', 'desc': 'Balances bags/seats with load and market.'},
    {'id': 'aggressive', 'label': 'Ancillary-heavy', 'desc': 'Low base, high bags/seats/priority fees (LCC / Allegiant style).'},
    {'id': 'minimal', 'label': 'All-inclusive', 'desc': 'Fewer fees, more ticket in the quoted fare.'},
]

# Creator-tunable route / hub economics (mirrored in game.js via bootstrap).
ROUTE_ECONOMICS = {
    'hub_profit_target_years': 2.5,
    'marginal_payback_warn_years': 3.0,
    'ramp_load_multipliers': [0.55, 0.78, 0.92],
    'ramp_cost_creep_per_year': 0.03,
    'avg_pax_load_factor': 0.80,
    'rival_traffic_buffer': 1.12,
    'market_capture': {
        'origin_share_floor': 0.0005,
        'pair_share_floor': 0.03,
        'capture_cap': 0.88,
        'presence_origin_target': 0.08,
        'presence_scale_min': 0.42,
        'presence_scale_range': 0.58,
        'rep_divisor': 450,
        'awareness_factor': 0.35,
        'freq_presence_base': 0.72,
        'freq_presence_max_add': 0.28,
        'freq_presence_divisor': 42,
        'origin_share_cap': 0.95,
    },
    'imputed_pair': {
        'size_multiplier': 3.2,
        'dist_divisor': 180,
        'min_weekly': 4,
    },
    'market_departures': {
        'avg_pax_tiers': [
            {'max_pax_m': 0.6, 'avg_pax': 48},
            {'max_pax_m': 3, 'avg_pax': 80},
            {'max_pax_m': 12, 'avg_pax': 102},
            {'max_pax_m': 35, 'avg_pax': 118},
            {'max_pax_m': 1e9, 'avg_pax': 132},
        ],
        'min_daily': 2,
    },
    'projection_note': (
        'Launch projections use conservative ramp-up, static competition, and HQ overhead. '
        'Actual results vary with GDP, inflation, marketing, and rival moves.'
    ),
}

# US-focused airports (~99). Coordinates and scale from public data; gates approximate.
_AIRPORT_ROWS = [
    ('ATL', 'Hartsfield-Jackson Atlanta', 'Atlanta', 33.64, -84.43, 6.1, 110, 195, 8, False, 'Delta', 0.95),
    ('DFW', 'Dallas/Fort Worth', 'Dallas', 32.90, -97.04, 7.6, 87, 165, 14, False, 'American', 0.90),
    ('DEN', 'Denver Intl', 'Denver', 39.86, -104.67, 2.9, 78, 140, 22, False, 'United', 0.75),
    ('ORD', "O'Hare Intl", 'Chicago', 41.98, -87.90, 9.5, 80, 190, 6, False, 'United', 0.88, 'IL'),
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
    ('MSP', 'Minneapolis-St Paul', 'Minneapolis', 44.88, -93.22, 3.7, 38, 130, 10, False, 'Delta', 0.90, 'MN'),
    ('DTW', 'Detroit Metro', 'Detroit', 42.21, -83.35, 4.3, 36, 120, 12, False, 'Delta', 0.88, 'MI'),
    ('PHL', 'Philadelphia Intl', 'Philadelphia', 39.87, -75.24, 6.2, 33, 125, 9, False, 'American', 0.70, 'PA'),
    ('LGA', 'LaGuardia', 'New York', 40.78, -73.87, 20.1, 30, 72, 3, True, 'Delta', 0.55),
    ('BWI', 'Baltimore/Washington', 'Baltimore', 39.18, -76.67, 9.8, 27, 75, 13, False, 'Southwest', 0.50),
    ('SLC', 'Salt Lake City', 'Salt Lake City', 40.79, -111.98, 1.2, 27, 85, 14, False, 'Delta', 0.85),
    ('DCA', 'Reagan National', 'Washington', 38.85, -77.04, 6.3, 24, 55, 2, True, 'American', 0.60),
    ('MDW', 'Chicago Midway', 'Chicago', 41.79, -87.75, 9.5, 22, 43, 4, False, 'Southwest', 0.78, 'IL'),
    ('BNA', 'Nashville Intl', 'Nashville', 36.12, -86.68, 2.0, 22, 55, 11, False, 'Southwest', 0.40, 'TN'),
    ('AUS', 'Austin-Bergstrom', 'Austin', 30.20, -97.67, 2.3, 22, 35, 9, False, 'Southwest', 0.35),
    ('SAN', 'San Diego Intl', 'San Diego', 32.73, -117.19, 3.3, 25, 51, 6, False, 'Alaska', 0.30),
    ('PDX', 'Portland Intl', 'Portland', 45.59, -122.60, 2.5, 20, 60, 8, False, 'Alaska', 0.45),
    ('STL', 'St Louis Lambert', 'St Louis', 38.75, -90.37, 2.8, 16, 70, 15, False, None, 0.15, 'MO'),
    ('MCI', 'Kansas City Intl', 'Kansas City', 39.30, -94.71, 2.2, 12, 45, 16, False, None, 0.10, 'MO'),
    ('RDU', 'Raleigh-Durham', 'Raleigh', 35.88, -78.79, 2.1, 14, 40, 10, False, None, 0.12),
    ('IND', 'Indianapolis Intl', 'Indianapolis', 39.72, -86.29, 2.1, 10, 48, 12, False, None, 0.08, 'IN'),
    ('CMH', 'John Glenn Columbus', 'Columbus', 39.99, -82.89, 2.1, 9, 42, 11, False, None, 0.08, 'OH'),
    ('PIT', 'Pittsburgh Intl', 'Pittsburgh', 40.49, -80.23, 2.4, 9, 75, 14, False, None, 0.10, 'PA'),
    ('CVG', 'Cincinnati/Northern KY', 'Cincinnati', 39.05, -84.66, 2.2, 9, 50, 10, False, None, 0.12, 'KY'),
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
    ('MEM', 'Memphis Intl', 'Memphis', 35.04, -89.98, 1.4, 5, 60, 18, False, None, 0.05, 'TN'),
    ('OMA', 'Eppley Airfield', 'Omaha', 41.30, -95.89, 0.9, 5, 24, 10, False, None, 0.06, 'IA'),
    ('DSM', 'Des Moines Intl', 'Des Moines', 41.53, -93.66, 0.7, 3, 20, 9, False, None, 0.05, 'IA'),
    ('GRR', 'Gerald R Ford Intl', 'Grand Rapids', 42.88, -85.52, 1.1, 3, 18, 8, False, None, 0.05, 'MI'),
    ('PWM', 'Portland Intl Jetport', 'Portland ME', 43.65, -70.31, 0.5, 2, 12, 6, False, None, 0.04),
    ('BTV', 'Burlington Intl', 'Burlington', 44.47, -73.15, 0.2, 1, 11, 5, False, None, 0.03),
    ('PVU', 'Provo Municipal', 'Provo', 40.22, -111.72, 0.7, 0.8, 6, 4, False, 'Breeze', 0.35),
    ('ISP', 'Long Island MacArthur', 'Islip', 40.79, -73.10, 20.1, 1.5, 10, 5, False, None, 0.08),
    ('LIT', 'Bill and Hillary Clinton', 'Little Rock', 34.73, -92.22, 0.7, 2, 14, 7, False, None, 0.05),
    # Ohio regionals — small terminals for turboprop / ERJ ops
    ('DAY', 'James M Cox Dayton Intl', 'Dayton', 39.90, -84.22, 0.85, 2.2, 18, 14, False, None, 0.06, 'OH'),
    ('LUK', 'Cincinnati Lunken', 'Cincinnati', 39.10, -84.42, 2.2, 0.45, 9, 7, False, None, 0.04, 'OH'),
    ('TOL', 'Toledo Express', 'Toledo', 41.59, -83.81, 0.65, 0.8, 14, 11, False, None, 0.05, 'OH'),
    ('CAK', 'Akron-Canton', 'Akron', 40.92, -81.44, 0.70, 1.6, 16, 12, False, None, 0.06, 'OH'),
    ('YNG', 'Youngstown-Warren', 'Youngstown', 41.26, -80.68, 0.45, 0.15, 8, 6, False, None, 0.03, 'OH'),
    ('FDY', 'Findlay Airport', 'Findlay', 41.01, -83.67, 0.10, 0.05, 6, 4, False, None, 0.02, 'OH'),
    # Ohio-region neighbors
    ('LEX', 'Blue Grass', 'Lexington', 38.04, -84.61, 0.75, 1.4, 12, 10, False, None, 0.06, 'KY'),
    ('SDF', 'Louisville Muhammad Ali Intl', 'Louisville', 38.17, -85.74, 1.2, 4.5, 22, 14, False, None, 0.10, 'KY'),
    ('OWB', 'Owensboro-Daviess County', 'Owensboro', 37.74, -87.17, 0.12, 0.06, 6, 4, False, None, 0.02, 'KY'),
    ('PAH', 'Barkley Regional', 'Paducah', 37.06, -88.77, 0.10, 0.05, 6, 4, False, None, 0.02, 'KY'),
    # Pennsylvania regionals
    ('MDT', 'Harrisburg Intl', 'Harrisburg', 40.19, -76.76, 0.65, 1.3, 14, 10, False, None, 0.08, 'PA'),
    ('ABE', 'Lehigh Valley Intl', 'Allentown', 40.65, -75.44, 0.85, 0.9, 10, 8, False, None, 0.07, 'PA'),
    ('AVP', 'Wilkes-Barre/Scranton Intl', 'Scranton', 41.34, -75.72, 0.55, 0.55, 8, 6, False, None, 0.06, 'PA'),
    ('ERI', 'Erie Intl', 'Erie', 42.08, -80.18, 0.28, 0.22, 6, 5, False, None, 0.05, 'PA'),
    ('LBE', 'Arnold Palmer Regional', 'Latrobe', 40.28, -79.40, 0.35, 0.18, 6, 4, False, None, 0.05, 'PA'),
    ('IPT', 'Williamsport Regional', 'Williamsport', 41.24, -76.92, 0.12, 0.08, 4, 3, False, None, 0.03, 'PA'),
    # Indiana regionals
    ('FWA', 'Fort Wayne Intl', 'Fort Wayne', 40.98, -85.19, 0.65, 0.95, 14, 10, False, None, 0.08, 'IN'),
    ('SBN', 'South Bend Intl', 'South Bend', 41.71, -86.32, 0.32, 0.72, 12, 9, False, None, 0.07, 'IN'),
    ('EVV', 'Evansville Regional', 'Evansville', 38.04, -87.53, 0.32, 0.38, 8, 6, False, None, 0.06, 'IN'),
    ('GYY', 'Gary/Chicago Intl', 'Gary', 41.62, -87.41, 0.70, 0.12, 6, 4, False, None, 0.04, 'IN'),
    ('HUF', 'Terre Haute Regional', 'Terre Haute', 39.45, -87.31, 0.18, 0.05, 4, 3, False, None, 0.02, 'IN'),
    # Michigan regionals
    ('LAN', 'Capital Region Intl', 'Lansing', 42.78, -84.59, 0.48, 0.52, 10, 8, False, None, 0.06, 'MI'),
    ('FNT', 'Bishop Intl', 'Flint', 42.97, -83.74, 0.42, 0.48, 10, 8, False, None, 0.06, 'MI'),
    ('MBS', 'MBS Intl', 'Saginaw', 43.53, -84.08, 0.18, 0.35, 8, 6, False, None, 0.05, 'MI'),
    ('AZO', 'Kalamazoo/Battle Creek Intl', 'Kalamazoo', 42.24, -85.55, 0.26, 0.22, 6, 5, False, None, 0.05, 'MI'),
    ('TVC', 'Cherry Capital', 'Traverse City', 44.74, -85.58, 0.15, 0.55, 10, 8, False, None, 0.06, 'MI'),
    ('MKG', 'Muskegon County', 'Muskegon', 43.17, -86.24, 0.17, 0.08, 4, 3, False, None, 0.03, 'MI'),
    # Tennessee regionals
    ('TYS', 'McGhee Tyson', 'Knoxville', 35.81, -83.99, 0.88, 2.8, 18, 12, False, None, 0.12, 'TN'),
    ('CHA', 'Chattanooga Metropolitan', 'Chattanooga', 35.04, -85.20, 0.58, 0.62, 10, 8, False, None, 0.07, 'TN'),
    ('TRI', 'Tri-Cities', 'Bristol', 36.48, -82.41, 0.22, 0.42, 8, 6, False, None, 0.06, 'TN'),
    # Illinois regionals
    ('RFD', 'Chicago Rockford Intl', 'Rockford', 42.20, -89.10, 0.34, 0.28, 8, 6, False, None, 0.06, 'IL'),
    ('PIA', 'General Wayne A Downing Peoria', 'Peoria', 40.66, -89.69, 0.40, 0.55, 10, 8, False, None, 0.06, 'IL'),
    ('SPI', 'Abraham Lincoln Capital', 'Springfield', 39.84, -89.68, 0.22, 0.25, 8, 6, False, None, 0.05, 'IL'),
    # Wisconsin
    ('MKE', 'Milwaukee Mitchell Intl', 'Milwaukee', 42.95, -87.90, 1.6, 9.5, 55, 14, False, None, 0.14, 'WI'),
    ('MSN', 'Dane County Regional', 'Madison', 43.14, -89.34, 0.68, 2.1, 14, 10, False, None, 0.10, 'WI'),
    ('GRB', 'Green Bay Austin Straubel Intl', 'Green Bay', 44.48, -88.13, 0.32, 0.95, 10, 8, False, None, 0.07, 'WI'),
    ('CWA', 'Central Wisconsin', 'Wausau', 44.78, -89.67, 0.14, 0.18, 6, 5, False, None, 0.04, 'WI'),
    # Minnesota regionals
    ('DLH', 'Duluth Intl', 'Duluth', 46.84, -92.19, 0.28, 0.32, 8, 6, False, None, 0.05, 'MN'),
    ('RST', 'Rochester Intl', 'Rochester', 43.91, -92.50, 0.22, 0.28, 6, 5, False, None, 0.05, 'MN'),
    # Missouri regionals
    ('SGF', 'Springfield-Branson National', 'Springfield', 37.25, -93.39, 0.48, 1.1, 12, 9, False, None, 0.08, 'MO'),
    # Iowa regionals
    ('CID', 'The Eastern Iowa', 'Cedar Rapids', 41.89, -91.71, 0.28, 1.45, 12, 9, False, None, 0.08, 'IA'),
    ('DBQ', 'Dubuque Regional', 'Dubuque', 42.40, -90.71, 0.10, 0.05, 4, 3, False, None, 0.02, 'IA'),
    # West Virginia
    ('CRW', 'Yeager', 'Charleston', 38.37, -81.59, 0.26, 0.42, 10, 8, False, None, 0.06, 'WV'),
    ('HTS', 'Tri-State', 'Huntington', 38.37, -82.56, 0.14, 0.28, 8, 6, False, None, 0.05, 'WV'),
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
    'OWB': [
        {'airline': 'Southern Airways Express', 'share': 0.38, 'tier': 'regional'},
        {'airline': 'Charter / GA', 'share': 0.42, 'tier': 'charter'},
    ],
    'PAH': [
        {'airline': 'United', 'share': 0.28, 'tier': 'legacy'},
        {'airline': 'Charter / GA', 'share': 0.35, 'tier': 'charter'},
    ],
    # Pennsylvania
    'PHL': [
        {'airline': 'American', 'share': 0.58, 'tier': 'legacy'},
        {'airline': 'Frontier', 'share': 0.10, 'tier': 'lcc'},
        {'airline': 'Southwest', 'share': 0.08, 'tier': 'lcc'},
        {'airline': 'Delta', 'share': 0.07, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.06, 'tier': 'legacy'},
    ],
    'MDT': [
        {'airline': 'American', 'share': 0.34, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.22, 'tier': 'legacy'},
        {'airline': 'Frontier', 'share': 0.12, 'tier': 'lcc'},
        {'airline': 'Delta', 'share': 0.10, 'tier': 'legacy'},
    ],
    'ABE': [
        {'airline': 'Allegiant', 'share': 0.28, 'tier': 'lcc'},
        {'airline': 'American', 'share': 0.24, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.18, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.12, 'tier': 'legacy'},
    ],
    'AVP': [
        {'airline': 'Allegiant', 'share': 0.26, 'tier': 'lcc'},
        {'airline': 'American', 'share': 0.28, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.16, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.12, 'tier': 'legacy'},
    ],
    'ERI': [
        {'airline': 'Allegiant', 'share': 0.32, 'tier': 'lcc'},
        {'airline': 'United', 'share': 0.22, 'tier': 'legacy'},
        {'airline': 'American', 'share': 0.14, 'tier': 'legacy'},
    ],
    'LBE': [
        {'airline': 'Allegiant', 'share': 0.48, 'tier': 'lcc'},
        {'airline': 'Southern Airways Express', 'share': 0.12, 'tier': 'regional'},
    ],
    'IPT': [
        {'airline': 'American', 'share': 0.38, 'tier': 'legacy'},
        {'airline': 'Charter / GA', 'share': 0.32, 'tier': 'charter'},
    ],
    # Indiana regionals
    'FWA': [
        {'airline': 'American', 'share': 0.30, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.18, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.16, 'tier': 'legacy'},
        {'airline': 'Allegiant', 'share': 0.12, 'tier': 'lcc'},
    ],
    'SBN': [
        {'airline': 'Allegiant', 'share': 0.24, 'tier': 'lcc'},
        {'airline': 'American', 'share': 0.22, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.18, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.14, 'tier': 'legacy'},
    ],
    'EVV': [
        {'airline': 'Allegiant', 'share': 0.28, 'tier': 'lcc'},
        {'airline': 'American', 'share': 0.26, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.18, 'tier': 'legacy'},
    ],
    'GYY': [
        {'airline': 'Allegiant', 'share': 0.42, 'tier': 'lcc'},
        {'airline': 'Charter / GA', 'share': 0.22, 'tier': 'charter'},
    ],
    'HUF': [
        {'airline': 'Charter / GA', 'share': 0.52, 'tier': 'charter'},
    ],
    # Michigan regionals
    'GRR': [
        {'airline': 'American', 'share': 0.28, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.24, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.18, 'tier': 'legacy'},
        {'airline': 'Allegiant', 'share': 0.10, 'tier': 'lcc'},
    ],
    'LAN': [
        {'airline': 'American', 'share': 0.30, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.22, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.16, 'tier': 'legacy'},
        {'airline': 'Allegiant', 'share': 0.08, 'tier': 'lcc'},
    ],
    'FNT': [
        {'airline': 'Allegiant', 'share': 0.32, 'tier': 'lcc'},
        {'airline': 'American', 'share': 0.24, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.18, 'tier': 'legacy'},
    ],
    'MBS': [
        {'airline': 'American', 'share': 0.28, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.24, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.18, 'tier': 'legacy'},
    ],
    'AZO': [
        {'airline': 'American', 'share': 0.32, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.26, 'tier': 'legacy'},
    ],
    'TVC': [
        {'airline': 'American', 'share': 0.28, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.22, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.14, 'tier': 'legacy'},
        {'airline': 'Allegiant', 'share': 0.12, 'tier': 'lcc'},
    ],
    'MKG': [
        {'airline': 'Charter / GA', 'share': 0.45, 'tier': 'charter'},
        {'airline': 'Southern Airways Express', 'share': 0.18, 'tier': 'regional'},
    ],
    # Tennessee
    'BNA': [
        {'airline': 'Southwest', 'share': 0.34, 'tier': 'lcc'},
        {'airline': 'American', 'share': 0.16, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.14, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.10, 'tier': 'legacy'},
        {'airline': 'Allegiant', 'share': 0.08, 'tier': 'lcc'},
    ],
    'MEM': [
        {'airline': 'Delta', 'share': 0.32, 'tier': 'legacy'},
        {'airline': 'American', 'share': 0.18, 'tier': 'legacy'},
        {'airline': 'Southwest', 'share': 0.12, 'tier': 'lcc'},
        {'airline': 'United', 'share': 0.10, 'tier': 'legacy'},
    ],
    'TYS': [
        {'airline': 'Allegiant', 'share': 0.26, 'tier': 'lcc'},
        {'airline': 'American', 'share': 0.24, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.20, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.12, 'tier': 'legacy'},
    ],
    'CHA': [
        {'airline': 'Allegiant', 'share': 0.28, 'tier': 'lcc'},
        {'airline': 'American', 'share': 0.26, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.18, 'tier': 'legacy'},
    ],
    'TRI': [
        {'airline': 'Allegiant', 'share': 0.30, 'tier': 'lcc'},
        {'airline': 'American', 'share': 0.28, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.16, 'tier': 'legacy'},
    ],
    # Illinois / Chicago
    'ORD': [
        {'airline': 'United', 'share': 0.42, 'tier': 'legacy'},
        {'airline': 'American', 'share': 0.28, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.08, 'tier': 'legacy'},
        {'airline': 'Southwest', 'share': 0.04, 'tier': 'lcc'},
    ],
    'MDW': [
        {'airline': 'Southwest', 'share': 0.72, 'tier': 'lcc'},
        {'airline': 'Delta', 'share': 0.08, 'tier': 'legacy'},
        {'airline': 'Frontier', 'share': 0.06, 'tier': 'lcc'},
    ],
    'RFD': [
        {'airline': 'Allegiant', 'share': 0.38, 'tier': 'lcc'},
        {'airline': 'Southern Airways Express', 'share': 0.14, 'tier': 'regional'},
    ],
    'PIA': [
        {'airline': 'American', 'share': 0.32, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.22, 'tier': 'legacy'},
        {'airline': 'Allegiant', 'share': 0.18, 'tier': 'lcc'},
    ],
    'SPI': [
        {'airline': 'American', 'share': 0.34, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.24, 'tier': 'legacy'},
    ],
    # Wisconsin
    'MKE': [
        {'airline': 'Southwest', 'share': 0.38, 'tier': 'lcc'},
        {'airline': 'Delta', 'share': 0.18, 'tier': 'legacy'},
        {'airline': 'American', 'share': 0.14, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.12, 'tier': 'legacy'},
        {'airline': 'Frontier', 'share': 0.06, 'tier': 'lcc'},
    ],
    'MSN': [
        {'airline': 'American', 'share': 0.30, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.24, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.18, 'tier': 'legacy'},
    ],
    'GRB': [
        {'airline': 'American', 'share': 0.30, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.22, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.16, 'tier': 'legacy'},
        {'airline': 'Allegiant', 'share': 0.08, 'tier': 'lcc'},
    ],
    'CWA': [
        {'airline': 'American', 'share': 0.32, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.24, 'tier': 'legacy'},
    ],
    # Minnesota
    'MSP': [
        {'airline': 'Delta', 'share': 0.62, 'tier': 'legacy'},
        {'airline': 'American', 'share': 0.08, 'tier': 'legacy'},
        {'airline': 'Southwest', 'share': 0.06, 'tier': 'lcc'},
        {'airline': 'United', 'share': 0.06, 'tier': 'legacy'},
    ],
    'DLH': [
        {'airline': 'Delta', 'share': 0.38, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.22, 'tier': 'legacy'},
        {'airline': 'American', 'share': 0.14, 'tier': 'legacy'},
    ],
    'RST': [
        {'airline': 'American', 'share': 0.32, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.26, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.16, 'tier': 'legacy'},
    ],
    # Missouri / Iowa
    'STL': [
        {'airline': 'Southwest', 'share': 0.42, 'tier': 'lcc'},
        {'airline': 'American', 'share': 0.18, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.12, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.10, 'tier': 'legacy'},
    ],
    'MCI': [
        {'airline': 'Southwest', 'share': 0.36, 'tier': 'lcc'},
        {'airline': 'Delta', 'share': 0.16, 'tier': 'legacy'},
        {'airline': 'American', 'share': 0.14, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.12, 'tier': 'legacy'},
    ],
    'SGF': [
        {'airline': 'American', 'share': 0.32, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.22, 'tier': 'legacy'},
        {'airline': 'Allegiant', 'share': 0.12, 'tier': 'lcc'},
    ],
    'DSM': [
        {'airline': 'American', 'share': 0.28, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.22, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.20, 'tier': 'legacy'},
        {'airline': 'Allegiant', 'share': 0.08, 'tier': 'lcc'},
    ],
    'OMA': [
        {'airline': 'Southwest', 'share': 0.30, 'tier': 'lcc'},
        {'airline': 'American', 'share': 0.22, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.16, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.14, 'tier': 'legacy'},
    ],
    'CID': [
        {'airline': 'American', 'share': 0.30, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.22, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.16, 'tier': 'legacy'},
        {'airline': 'Allegiant', 'share': 0.10, 'tier': 'lcc'},
    ],
    'DBQ': [
        {'airline': 'Charter / GA', 'share': 0.48, 'tier': 'charter'},
    ],
    # West Virginia
    'CRW': [
        {'airline': 'American', 'share': 0.36, 'tier': 'legacy'},
        {'airline': 'Delta', 'share': 0.22, 'tier': 'legacy'},
        {'airline': 'United', 'share': 0.16, 'tier': 'legacy'},
    ],
    'HTS': [
        {'airline': 'Allegiant', 'share': 0.32, 'tier': 'lcc'},
        {'airline': 'American', 'share': 0.26, 'tier': 'legacy'},
    ],
}

OHIO_REGION_IATA = [
    'DAY', 'LUK', 'CVG', 'CMH', 'TOL', 'CAK', 'YNG', 'FDY',
    'IND', 'PIT', 'LEX', 'SDF', 'DTW',
]

# Financial health / scale for competitor intel (approximate public-market flavor).
# Competitor brands. Private builds use real logo files under static/runway/logos/.
# Public release: set USE_REAL_COMPETITOR_LOGOS=false and swap names to near-names.
USE_REAL_COMPETITOR_LOGOS = os.environ.get('ROUTELAB_REAL_LOGOS', '1').strip().lower() not in (
    '0', 'false', 'no', 'off',
)

def _logo(slug):
    """Path to private-build competitor logo (PNG). Missing files fall back to SVG marks in UI."""
    return f'/static/runway/logos/{slug}.png'


AIRLINE_PROFILES = {
    'Delta': {
        'tier': 'legacy', 'financial_health': 0.84, 'route_sensitivity': 0.38, 'cash_runway_years': 1.8,
        'brand': {
            'code': 'DL', 'primary': '#003268', 'secondary': '#C8102E', 'accent': '#FFFFFF',
            'mark': 'delta', 'logo': _logo('delta'), 'domain': 'delta.com',
        },
    },
    'American': {
        'tier': 'legacy', 'financial_health': 0.72, 'route_sensitivity': 0.42, 'cash_runway_years': 1.4,
        'brand': {
            'code': 'AA', 'primary': '#0078D2', 'secondary': '#C8102E', 'accent': '#FFFFFF',
            'mark': 'american', 'logo': _logo('american'), 'domain': 'aa.com',
        },
    },
    'United': {
        'tier': 'legacy', 'financial_health': 0.78, 'route_sensitivity': 0.40, 'cash_runway_years': 1.6,
        'brand': {
            'code': 'UA', 'primary': '#002244', 'secondary': '#FFB81C', 'accent': '#FFFFFF',
            'mark': 'united', 'logo': _logo('united'), 'domain': 'united.com',
        },
    },
    'Southwest': {
        'tier': 'lcc', 'financial_health': 0.76, 'route_sensitivity': 0.55, 'cash_runway_years': 2.1,
        'brand': {
            'code': 'WN', 'primary': '#304CB2', 'secondary': '#FFBF27', 'accent': '#E31837',
            'mark': 'southwest', 'logo': _logo('southwest'), 'domain': 'southwest.com',
        },
    },
    'Allegiant': {
        'tier': 'lcc', 'financial_health': 0.81, 'route_sensitivity': 0.72, 'cash_runway_years': 2.4,
        'brand': {
            'code': 'G4', 'primary': '#003B70', 'secondary': '#FDB913', 'accent': '#FFFFFF',
            'mark': 'allegiant', 'logo': _logo('allegiant'), 'domain': 'allegiantair.com',
        },
    },
    'Frontier': {
        'tier': 'lcc', 'financial_health': 0.58, 'route_sensitivity': 0.88, 'cash_runway_years': 1.1,
        'brand': {
            'code': 'F9', 'primary': '#006341', 'secondary': '#8DC63F', 'accent': '#FFFFFF',
            'mark': 'frontier', 'logo': _logo('frontier'), 'domain': 'flyfrontier.com',
        },
    },
    'Spirit': {
        'tier': 'lcc', 'financial_health': 0.41, 'route_sensitivity': 0.92, 'cash_runway_years': 0.7,
        'brand': {
            'code': 'NK', 'primary': '#1B0A3D', 'secondary': '#FFE016', 'accent': '#FFFFFF',
            'mark': 'spirit', 'logo': _logo('spirit'), 'domain': 'spirit.com',
        },
    },
    'JetBlue': {
        'tier': 'lcc', 'financial_health': 0.52, 'route_sensitivity': 0.78, 'cash_runway_years': 0.9,
        'brand': {
            'code': 'B6', 'primary': '#003876', 'secondary': '#68BBE3', 'accent': '#FFFFFF',
            'mark': 'jetblue', 'logo': _logo('jetblue'), 'domain': 'jetblue.com',
        },
    },
    'Sun Country': {
        'tier': 'lcc', 'financial_health': 0.64, 'route_sensitivity': 0.80, 'cash_runway_years': 1.2,
        'brand': {
            'code': 'SY', 'primary': '#F15A22', 'secondary': '#FFC72C', 'accent': '#FFFFFF',
            'mark': 'suncountry', 'logo': _logo('suncountry'), 'domain': 'suncountry.com',
        },
    },
    'Alaska': {
        'tier': 'legacy', 'financial_health': 0.70, 'route_sensitivity': 0.48, 'cash_runway_years': 1.5,
        'brand': {
            'code': 'AS', 'primary': '#01426A', 'secondary': '#7CB82F', 'accent': '#FFFFFF',
            'mark': 'alaska', 'logo': _logo('alaska'), 'domain': 'alaskaair.com',
        },
    },
    'Breeze': {
        'tier': 'lcc', 'financial_health': 0.48, 'route_sensitivity': 0.85, 'cash_runway_years': 0.8,
        'brand': {
            'code': 'MX', 'primary': '#6C2EB9', 'secondary': '#00C2A8', 'accent': '#FFFFFF',
            'mark': 'breeze', 'logo': _logo('breeze'), 'domain': 'flybreeze.com',
        },
    },
    'Ultimate Air Shuttle': {
        'tier': 'shuttle', 'financial_health': 0.55, 'route_sensitivity': 0.95, 'cash_runway_years': 0.6,
        'brand': {'code': 'UE', 'primary': '#1A1A2E', 'secondary': '#E94560', 'accent': '#FFFFFF', 'mark': 'shuttle'},
    },
    'Southern Airways Express': {
        'tier': 'regional', 'financial_health': 0.50, 'route_sensitivity': 0.90, 'cash_runway_years': 0.7,
        'brand': {'code': '9X', 'primary': '#0B3D5C', 'secondary': '#D4A017', 'accent': '#FFFFFF', 'mark': 'southern'},
    },
    'Charter / GA': {
        'tier': 'charter', 'financial_health': 0.35, 'route_sensitivity': 0.30, 'cash_runway_years': 0.4,
        'brand': {'code': 'GA', 'primary': '#3D3D3D', 'secondary': '#A0A0A0', 'accent': '#FFFFFF', 'mark': 'charter'},
    },
}

# National scale (0–1) and est. monthly brand/marketing + corporate overhead for league economics.
_AIRLINE_SCALE_DEFAULTS = {
    'Delta': (0.98, 390_000_000),
    'American': (0.96, 360_000_000),
    'United': (0.95, 340_000_000),
    'Southwest': (0.82, 175_000_000),
    'Allegiant': (0.34, 11_000_000),
    'Frontier': (0.38, 14_000_000),
    'Spirit': (0.36, 13_000_000),
    'JetBlue': (0.52, 42_000_000),
    'Alaska': (0.44, 26_000_000),
    'Sun Country': (0.22, 4_500_000),
    'Breeze': (0.18, 3_200_000),
    'Ultimate Air Shuttle': (0.06, 180_000),
    'Southern Airways Express': (0.08, 420_000),
    'Charter / GA': (0.02, 50_000),
}
for _name, _prof in AIRLINE_PROFILES.items():
    _scale, _overhead = _AIRLINE_SCALE_DEFAULTS.get(
        _name,
        (_prof['financial_health'] * 0.45, _prof['financial_health'] * 8_000_000),
    )
    _prof['national_scale'] = _scale
    _prof['marketing_overhead_mo'] = _overhead


def _normalize_gate_counts(gates_total, gates_available):
    """Ensure gates_available is never greater than gates_total (common data-entry swap)."""
    total = max(1, int(gates_total))
    avail = max(0, int(gates_available))
    if avail > total:
        total, avail = avail, total
    avail = min(avail, total)
    return total, avail


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
    gates_total, gates_available = _normalize_gate_counts(r[7], r[8])
    wealth_index = round(min(1.0, max(0.06, 0.06 + metro * 0.11 + pax * 0.012)), 3)
    luxury_share = round(min(0.45, max(0.02, 0.04 + metro * 0.028 + (0.14 if r[9] else 0.02))), 3)
    if pax < 2.0:
        luxury_share = round(luxury_share * 0.55, 3)
    if pax < 0.6:
        wealth_index = round(wealth_index * 0.62, 3)
        luxury_share = round(luxury_share * 0.45, 3)
    state_code = r[12] if len(r) > 12 else None
    regional_flag = r[6] < 3 or (state_code in MIDWEST_STATE_CODES and r[6] < 3)
    if pax < 0.5:
        ops_hours, dep_per_hour, op_days, turnaround = 9, 1, 5, 100
    elif pax < 2:
        ops_hours, dep_per_hour, op_days, turnaround = 11, 1, 6, 95
    elif pax < 10:
        ops_hours, dep_per_hour, op_days, turnaround = 14, 2, 6, 85
    elif pax < 40:
        ops_hours, dep_per_hour, op_days, turnaround = 16, 3, 7, 75
    else:
        ops_hours, dep_per_hour, op_days, turnaround = 18, 4, 7, 65
    max_weekly_dep = max(4, int(ops_hours * dep_per_hour * op_days * 0.8))
    # Estimated total airline departures (market size) from annual enplanements.
    if pax < 0.6:
        avg_pax_per_dep = 48
    elif pax < 3:
        avg_pax_per_dep = 80
    elif pax < 12:
        avg_pax_per_dep = 102
    elif pax < 35:
        avg_pax_per_dep = 118
    else:
        avg_pax_per_dep = 132
    load_factor = 0.80
    market_dep_daily = max(2, int((pax * 1_000_000 / 365) / (avg_pax_per_dep * load_factor)))
    market_dep_weekly = market_dep_daily * op_days
    return {
        'iata': iata,
        'name': r[1],
        'city': r[2],
        'lat': r[3],
        'lon': r[4],
        'metro_pop_m': metro,
        'annual_pax_m': pax,
        'gates_total': gates_total,
        'gates_available': gates_available,
        'slot_controlled': r[9],
        'hub_airline': hub_airline,
        'hub_strength': hub_strength,
        'incumbents': incumbents,
        'wealth_index': wealth_index,
        'luxury_share': luxury_share,
        'state': r[12] if len(r) > 12 else None,
        'lease_exclusive_monthly': int(12_000 + r[6] * 800 + (20 if r[9] else 0)),
        'lease_common_monthly': int(5_000 + r[6] * 350),
        'seasonal_reliability': 0.92 if iata in (
            'ORD', 'DTW', 'BOS', 'MSP', 'DEN', 'MKE', 'GRR', 'LAN', 'FNT', 'MBS', 'DLH', 'RST', 'CWA', 'TVC',
        ) else 0.98,
        'regional': regional_flag,
        'ops_hours_per_day': ops_hours,
        'max_departures_per_hour': dep_per_hour,
        'operating_days_per_week': op_days,
        'min_turnaround_min': turnaround,
        'max_weekly_departures_per_gate': max_weekly_dep,
        'market_departures_daily': market_dep_daily,
        'market_departures_weekly': market_dep_weekly,
    }


AIRPORTS = [_build_airport(r) for r in _AIRPORT_ROWS]

AIRPORT_BY_IATA = {a['iata']: a for a in AIRPORTS}


def _validate_airport_gate_data():
    for ap in AIRPORTS:
        if ap['gates_available'] > ap['gates_total']:
            raise ValueError(
                f"Airport {ap['iata']}: gates_available ({ap['gates_available']}) "
                f"exceeds gates_total ({ap['gates_total']})"
            )
        if ap['gates_total'] < 1 or ap['gates_available'] < 0:
            raise ValueError(f"Airport {ap['iata']}: invalid gate counts")


_validate_airport_gate_data()

SCENARIOS = {
    'beginner_2026': {
        'id': 'beginner_2026',
        'name': '2026 — Beginner (Ohio Tutorial)',
        'tagline': 'Step-by-step — routes, fleet, fares in Ohio.',
        'goal': {
            'label': 'Graduate: post a profitable trailing month',
            'profit_month': True,
        },
        'year': 2026,
        'region': 'ohio',
        'tutorial': True,
        'briefing': (
            'Training scenario in Ohio. You run Gateway Air with one E145 on a <b>round trip</b> '
            'CMH⇄DAY (paying passengers both ways), gates at both ends, and a short UI tour before you unpause.'
        ),
        'cash': 8_500_000,
        'debt': [],
        'bonds': [],
        'equity_pct': 100.0,
        'reputation': 28,
        'brand_awareness': {'CMH': 58, 'DAY': 42},
        'financing_tier': 'startup',
        'bond_rating': 'BB',
        'player_name': 'CEO',
        'airline_name': 'Gateway Air',
        'fleet': [
            {'id': 'ga-1', 'type': 'e145', 'leased': True, 'lease_months_left': 48, 'seats': 50},
        ],
        'gates': [
            {'airport': 'CMH', 'tier': 'exclusive', 'years_left': 4, 'monthly': 16_000},
            {'airport': 'DAY', 'tier': 'common', 'years_left': 3, 'monthly': 7_200},
        ],
        'routes': [
            {
                'id': 'ga-r1',
                'origin': 'CMH',
                'dest': 'DAY',
                'aircraft_type': 'e145',
                'frequency_week': 7,
                'fare': 149,
                'fare_mode': 'auto',
                'aircraft_id': 'ga-1',
                'established': True,
            },
            {
                'id': 'ga-r2',
                'origin': 'DAY',
                'dest': 'CMH',
                'aircraft_type': 'e145',
                'frequency_week': 7,
                'fare': 149,
                'fare_mode': 'auto',
                'aircraft_id': 'ga-1',
                'established': True,
            },
        ],
    },
    'beginner_winning_2026': {
        'id': 'beginner_winning_2026',
        'name': '2026 — Winning Path (Ohio Coach)',
        'tagline': 'Same Ohio tutorial — round-trip CMH⇄DAY tuned for profit.',
        'goal': {
            'label': 'Graduate: post a profitable trailing month',
            'profit_month': True,
        },
        'year': 2026,
        'region': 'ohio',
        'tutorial': True,
        'winning_track': True,
        'tutorial_overhead_scale': 0.78,
        'briefing': (
            'Gateway Air starts on a <b>winning track</b>: daily <b>CMH⇄DAY</b> round trips with paying '
            'passengers both ways, gates at both cities, and CMH marketing already on. Tour the UI, then press ▶.'
        ),
        'cash': 8_500_000,
        'debt': [],
        'bonds': [],
        'equity_pct': 100.0,
        'reputation': 32,
        'brand_awareness': {'CMH': 62, 'DAY': 48},
        'marketing_spend_monthly': {'CMH': 9_000, 'DAY': 4_500},
        'financing_tier': 'startup',
        'bond_rating': 'BB',
        'player_name': 'CEO',
        'airline_name': 'Gateway Air',
        'fleet': [
            {'id': 'ga-1', 'type': 'e145', 'leased': True, 'lease_months_left': 48, 'seats': 50},
        ],
        'gates': [
            {'airport': 'CMH', 'tier': 'exclusive', 'years_left': 4, 'monthly': 16_000},
            {'airport': 'DAY', 'tier': 'common', 'years_left': 3, 'monthly': 7_200},
        ],
        'routes': [
            {
                'id': 'ga-r1',
                'origin': 'CMH',
                'dest': 'DAY',
                'aircraft_type': 'e145',
                'frequency_week': 7,
                'fare': 139,
                'fare_mode': 'manual',
                'aircraft_id': 'ga-1',
                'established': True,
            },
            {
                'id': 'ga-r2',
                'origin': 'DAY',
                'dest': 'CMH',
                'aircraft_type': 'e145',
                'frequency_week': 7,
                'fare': 139,
                'fare_mode': 'manual',
                'aircraft_id': 'ga-1',
                'established': True,
            },
        ],
    },
    'ohio_regional_2026': {
        'id': 'ohio_regional_2026',
        'name': '2026 — Ohio Regional',
        'tagline': 'Real competitors · regional airports · prove the model locally.',
        'goal': {
            'label': 'Build Ohio to $20M annual revenue',
            'ltm_revenue': 20_000_000,
        },
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
    'midwest_regional_2026': {
        'id': 'midwest_regional_2026',
        'name': '2026 — Midwest Regional',
        'tagline': 'PA to the Great Lakes — thin routes, real rivals, turboprop economics.',
        'goal': {
            'label': 'Build the Midwest to $35M annual revenue',
            'ltm_revenue': 35_000_000,
        },
        'year': 2026,
        'region': 'midwest',
        'briefing': (
            'Build a regional airline across the full Midwest: Pennsylvania and West Virginia on the east, '
            'Kentucky and Tennessee in the Ohio Valley, Indiana and Michigan in the Great Lakes, plus Chicago, '
            'Milwaukee, Minneapolis, St. Louis, and Iowa. Allegiant still dominates many small fields; Delta '
            'anchors Detroit and Minneapolis; Southwest owns Nashville and Midway. Lease a PC-12, win unconstrained '
            'gates at places like DAY, FWA, or TYS, and grow toward hub economics at IND, CVG, or MKE.'
        ),
        'cash': 3_800_000,
        'debt': [],
        'bonds': [],
        'equity_pct': 100.0,
        'reputation': 10,
        'brand_awareness': {'IND': 12, 'DAY': 10},
        'financing_tier': 'startup',
        'bond_rating': 'B',
        'player_name': 'CEO',
        'airline_name': 'Heartland Air',
        'fleet': [
            {'id': 'ha-1', 'type': 'pc12', 'leased': True, 'lease_months_left': 48, 'seats': 9},
        ],
        'gates': [
            {'airport': 'IND', 'tier': 'common', 'years_left': 3, 'monthly': 8_500},
        ],
        'routes': [],
    },
    'greenfield_2026': {
        'id': 'greenfield_2026',
        'name': '2026 — Greenfield Startup',
        'tagline': 'Pitch deck, no planes, brutal hubs.',
        'goal': {
            'label': 'Prove the model: $50M annual revenue and a profitable month',
            'ltm_revenue': 50_000_000,
            'profit_month': True,
        },
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
        'goal': {
            'label': 'Build it bigger: $150M annual revenue and a profitable month',
            'ltm_revenue': 150_000_000,
            'profit_month': True,
        },
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
        'goal': {
            'label': 'Fix it: cut total debt below $14M with a profitable month',
            'max_debt': 14_000_000,
            'profit_month': True,
        },
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
# Landing + pax facility per departure touch (~$400–550 for regional jets at mid-size US airports).
AIRPORT_FEE_PER_DEPARTURE = 450

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
        'route_feature_monthly': 6_500,
        'hub_push_monthly': 18_000,
        'note': 'Pay-to-play listing + commission; optional route spotlight or hub push.',
    },
    {
        'id': 'google_flights',
        'name': 'Google Flights',
        'listing_monthly': 9_500,
        'commission_pct': 0,
        'demand_reach': 0.18,
        'marketing_amplify': 1.15,
        'route_feature_monthly': 3_200,
        'hub_push_monthly': 8_500,
        'note': 'Metasearch feed fee; strong reach, thinner margin.',
    },
    {
        'id': 'kayak',
        'name': 'Kayak',
        'listing_monthly': 16_000,
        'commission_pct': 10,
        'demand_reach': 0.14,
        'marketing_amplify': 1.2,
        'route_feature_monthly': 4_800,
        'hub_push_monthly': 12_000,
        'note': 'Listing + commission; deal-hunter audience.',
    },
    {
        'id': 'travelocity',
        'name': 'Travelocity',
        'listing_monthly': 12_000,
        'commission_pct': 11,
        'demand_reach': 0.1,
        'marketing_amplify': 1.12,
        'route_feature_monthly': 3_800,
        'hub_push_monthly': 9_000,
        'note': 'Legacy OTA shelf space; moderate reach.',
    },
]

# Marketing spend tiers — toggled in route launch & airport panels.
MARKETING_CHANNELS = [
    {
        'id': 'airport',
        'label': 'Airport / city',
        'scope': 'local',
        'hint': 'Billboards, local digital, airport ads at origin.',
        'efficiency': 1.0,
    },
    {
        'id': 'state',
        'label': 'State / region',
        'scope': 'state',
        'hint': 'Regional TV/radio, state tourism boards, sports sponsorship.',
        'efficiency': 0.72,
    },
    {
        'id': 'national',
        'label': 'National brand',
        'scope': 'national',
        'hint': 'National streaming, podcast, broad brand — expensive for a startup.',
        'efficiency': 0.45,
    },
    {
        'id': 'world',
        'label': 'Global reach',
        'scope': 'world',
        'hint': 'International campaigns — only matters once you fly abroad.',
        'efficiency': 0.25,
    },
]

TIME_SPEEDS = [
    {'id': 'pause', 'label': 'Pause', 'days_per_tick': 0, 'hours_per_tick': 0},
    {'id': 'slow', 'label': 'Slow (4 hr)', 'days_per_tick': 0, 'hours_per_tick': 4},
    {'id': 'day', 'label': 'Normal (1 day)', 'days_per_tick': 1, 'hours_per_tick': 0},
    {'id': 'week', 'label': 'Fast (1 week)', 'days_per_tick': 7, 'hours_per_tick': 0},
    {'id': 'month', 'label': 'Faster (1 month)', 'days_per_tick': 30, 'hours_per_tick': 0},
    # Real year advance: one full year of day-sim per tick (alerts still pause mid-tick).
    {'id': 'year', 'label': 'Year (365 days)', 'days_per_tick': 365, 'hours_per_tick': 0},
]

TICK_MS = {
    'pause': 0,
    'slow': 1100,
    'day': 750,
    'week': 580,
    'month': 460,
    'year': 1200,
}

# Well-traveled city pairs (either direction) — boosts route suggestions & demand hint.
COMMON_ROUTE_PAIRS = [
    # Ohio core
    ('DAY', 'CMH'), ('DAY', 'CVG'), ('DAY', 'IND'), ('CVG', 'CMH'), ('CVG', 'IND'),
    ('CMH', 'IND'), ('CMH', 'BNA'), ('CMH', 'ORD'), ('DAY', 'ORD'), ('LUK', 'CVG'),
    ('LUK', 'CMH'), ('CAK', 'CMH'), ('TOL', 'ORD'), ('YNG', 'PIT'), ('CAK', 'PIT'),
    # Pennsylvania
    ('PHL', 'PIT'), ('PIT', 'CMH'), ('PIT', 'ORD'), ('MDT', 'ORD'), ('ABE', 'ORD'),
    ('AVP', 'PIT'), ('ERI', 'PIT'), ('LBE', 'PIT'), ('PHL', 'MDW'),
    # Kentucky
    ('LEX', 'CVG'), ('LEX', 'CMH'), ('SDF', 'BNA'), ('SDF', 'CVG'), ('SDF', 'IND'),
    # Indiana
    ('IND', 'ORD'), ('IND', 'DTW'), ('IND', 'MDW'), ('FWA', 'ORD'), ('SBN', 'ORD'),
    ('EVV', 'IND'), ('GYY', 'ORD'), ('SBN', 'DTW'),
    # Michigan
    ('DTW', 'ORD'), ('DTW', 'MSP'), ('GRR', 'ORD'), ('GRR', 'DTW'), ('LAN', 'DTW'),
    ('FNT', 'ORD'), ('MBS', 'DTW'), ('TVC', 'ORD'), ('AZO', 'ORD'),
    # Tennessee
    ('BNA', 'MDW'), ('BNA', 'STL'), ('BNA', 'CMH'), ('TYS', 'BNA'), ('CHA', 'BNA'),
    ('MEM', 'BNA'), ('MEM', 'DTW'), ('TRI', 'CMH'),
    # Illinois / Wisconsin / Minnesota
    ('ORD', 'MDW'), ('ORD', 'MSP'), ('ORD', 'STL'), ('MDW', 'STL'), ('MKE', 'ORD'),
    ('MKE', 'MDW'), ('MSN', 'ORD'), ('GRB', 'ORD'), ('RFD', 'PIA'), ('PIA', 'ORD'),
    ('SPI', 'ORD'), ('DLH', 'MSP'), ('RST', 'MSP'),
    # Missouri / Iowa
    ('STL', 'MDW'), ('MCI', 'MDW'), ('DSM', 'ORD'), ('OMA', 'ORD'), ('CID', 'ORD'),
    ('SGF', 'ORD'), ('MCI', 'STL'),
    # West Virginia
    ('CRW', 'CMH'), ('CRW', 'CVG'), ('HTS', 'CMH'), ('HTS', 'PIT'),
    # National anchors (non-midwest pairs kept for other scenarios)
    ('BNA', 'ATL'), ('OMA', 'DEN'), ('RDU', 'ATL'), ('AUS', 'DFW'),
]

# Full Midwest playfield — PA, OH, KY, IN, MI, TN, IL, WI, MN, MO, IA, WV.
MIDWEST_REGION_IATA = sorted(set(OHIO_REGION_IATA + [
    # Pennsylvania
    'PHL', 'MDT', 'ABE', 'AVP', 'ERI', 'LBE', 'IPT',
    # Kentucky extras
    'OWB', 'PAH',
    # Indiana
    'FWA', 'SBN', 'EVV', 'GYY', 'HUF',
    # Michigan
    'GRR', 'LAN', 'FNT', 'MBS', 'AZO', 'TVC', 'MKG',
    # Tennessee
    'BNA', 'MEM', 'TYS', 'CHA', 'TRI',
    # Illinois
    'ORD', 'MDW', 'RFD', 'PIA', 'SPI',
    # Wisconsin
    'MKE', 'MSN', 'GRB', 'CWA',
    # Minnesota
    'MSP', 'DLH', 'RST',
    # Missouri
    'STL', 'MCI', 'SGF',
    # Iowa
    'DSM', 'OMA', 'CID', 'DBQ',
    # West Virginia
    'CRW', 'HTS',
    # Already in OHIO_REGION or above: IND PIT DTW GRR LEX SDF BNA MEM DSM OMA CVG CMH
]))

LEAGUE_SCOPES = {
    'ohio': {
        'label': 'Ohio & nearby',
        'airports': OHIO_REGION_IATA,
        'airlines': ['Allegiant', 'Delta', 'American', 'Southwest', 'Frontier', 'United', 'Spirit'],
        'overhead_weight': 0.04,
    },
    'midwest': {
        'label': 'Midwest (PA · OH · KY · IN · MI · TN · Great Lakes)',
        'airports': MIDWEST_REGION_IATA,
        'airlines': [
            'Delta', 'American', 'United', 'Southwest', 'Allegiant', 'Frontier', 'Spirit', 'JetBlue',
            'Sun Country', 'Southern Airways Express',
        ],
        'overhead_weight': 0.15,
    },
    'national': {
        'label': 'United States',
        'airports': None,
        'airlines': ['Delta', 'American', 'United', 'Southwest', 'Allegiant', 'Frontier', 'Spirit', 'JetBlue', 'Alaska'],
        'overhead_weight': 1.0,
    },
}

# Back-compat alias
LEAGUE_BY_REGION = {
    'ohio': LEAGUE_SCOPES['ohio']['airlines'],
    'midwest': LEAGUE_SCOPES['midwest']['airlines'],
    'national': LEAGUE_SCOPES['national']['airlines'],
}

# Player emblem marks — unique SVG shapes (rendered in game.js). Labels are internal only; UI shows marks without names.
EMBLEM_OPTIONS = [
    {
        'id': 'routes',
        'label': '',
        'glyph': '◎',
        'colors': ['#00e0a8', '#0b1f36', '#ffd166'],
        'mark': 'routes',
    },
    {
        'id': 'wing',
        'label': '',
        'glyph': '✈',
        'colors': ['#5bb4ff', '#071422', '#e8f2ff'],
        'mark': 'wing',
    },
    {
        'id': 'compass',
        'label': '',
        'glyph': '✦',
        'colors': ['#ffd166', '#132a45', '#00c896'],
        'mark': 'compass',
    },
    {
        'id': 'star',
        'label': '',
        'glyph': '★',
        'colors': ['#ffd166', '#1c1238', '#ffffff'],
        'mark': 'star',
    },
    {
        'id': 'bolt',
        'label': '',
        'glyph': '⚡',
        'colors': ['#6dffb4', '#041c12', '#00c896'],
        'mark': 'bolt',
    },
    {
        'id': 'globe',
        'label': '',
        'glyph': '◌',
        'colors': ['#7ec8ef', '#012a5c', '#ffffff'],
        'mark': 'globe',
    },
    {
        'id': 'stripe',
        'label': '',
        'glyph': '▮',
        'colors': ['#e11d38', '#0b3d8c', '#ffffff'],
        'mark': 'stripe',
    },
    {
        'id': 'talon',
        'label': '',
        'glyph': '⌃',
        'colors': ['#ff5a76', '#12121f', '#ffd166'],
        'mark': 'talon',
    },
    {
        'id': 'contrail',
        'label': '',
        'glyph': '⟶',
        'colors': ['#e6f0fa', '#132a45', '#00c896'],
        'mark': 'contrail',
    },
]


def get_runway_bootstrap():
    """JSON-safe payload for the browser game."""
    profiles = AIRLINE_PROFILES
    if not USE_REAL_COMPETITOR_LOGOS:
        # Public / near-name mode: drop real logo paths (stylized SVG marks only).
        profiles = {}
        for name, prof in AIRLINE_PROFILES.items():
            p = dict(prof)
            brand = dict(p.get('brand') or {})
            brand.pop('logo', None)
            p['brand'] = brand
            profiles[name] = p
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
        'marketing_channels': MARKETING_CHANNELS,
        'time_speeds': TIME_SPEEDS,
        'tick_ms': TICK_MS,
        'common_route_pairs': COMMON_ROUTE_PAIRS,
        'ohio_region_iata': OHIO_REGION_IATA,
        'midwest_region_iata': MIDWEST_REGION_IATA,
        'midwest_state_codes': sorted(MIDWEST_STATE_CODES),
        'ohio_competitor_route_seeds': OHIO_COMPETITOR_ROUTE_SEEDS,
        'midwest_competitor_route_seeds': MIDWEST_COMPETITOR_ROUTE_SEEDS,
        'ancillary_modes': ANCILLARY_MODES,
        'route_economics': ROUTE_ECONOMICS,
        'airline_profiles': profiles,
        'use_real_competitor_logos': USE_REAL_COMPETITOR_LOGOS,
        'league_by_region': LEAGUE_BY_REGION,
        'league_scopes': LEAGUE_SCOPES,
        'emblem_options': EMBLEM_OPTIONS,
        'routelab': {
            'name': 'Route Lab',
            'logo_url': '/static/routelab/routelab-app-logo.jpg',
            'tagline': 'Airline network economics — routes, gates, rivals, and capital.',
        },
    }


def scenario_has_tutorial(scenario_id):
    sc = SCENARIOS.get(scenario_id) or {}
    return bool(sc.get('tutorial'))