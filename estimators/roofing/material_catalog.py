"""GAF material line definitions and default unit assumptions."""

# GAF product coverage assumptions (editable on Tab 1)
GAF_DEFAULTS = {
    'bundles_per_square': 3,
    'pro_start_lf_per_bundle': 120.0,
    'seal_a_ridge_lf_per_bundle': 25.0,
    'weatherwatch_lf_per_roll': 65.0,
    'synthetic_sqft_per_roll': 1000.0,  # Pro Guard 20 — 10 squares
    'valley_piece_ft': 10.0,
    'drip_edge_piece_ft': 10.0,
    'coil_nails_sqft_per_box': 2000.0,
    'cap_nails_sqft_per_pail': 2000.0,
}

MATERIAL_LINES = [
    # key, label, unit, qty_key
    ('timberline_bundles', 'GAF Timberline HDZ (field shingles)', 'bundle', 'timberline_bundles'),
    ('pro_start_bundles', 'GAF Pro-Start (starter)', 'bundle', 'pro_start_bundles'),
    ('weatherwatch_rolls', 'GAF WeatherWatch (ice & water)', 'roll', 'weatherwatch_rolls'),
    ('pro_guard_rolls', 'GAF Pro Guard 20 (synthetic underlayment)', 'roll', 'pro_guard_rolls'),
    ('seal_a_ridge_bundles', 'GAF Seal-A-Ridge (hip & ridge cap)', 'bundle', 'seal_a_ridge_bundles'),
    ('valley_metal', 'Valley metal (10 ft)', 'pc', 'valley_metal_pcs'),
    ('drip_edge', 'Drip edge (10 ft)', 'pc', 'drip_edge_pcs'),
    ('pipe_boots', 'Neverleak / pipe flashing', 'ea', 'pipe_boots'),
    ('coil_nails', 'Coil nails 1-1/4" EG', 'box', 'coil_nails_boxes'),
    ('cap_nails', 'Plastic cap nails', 'pail', 'cap_nails_pails'),
    ('step_flashing', 'Aluminum step flashing (100 pc bundle)', 'bundle', 'step_flashing_bundles'),
]

QUICK_BID_LINES = [
    ('shingles_material', 'Shingle material (order squares)', 'sq', 'order_squares'),
    ('labor', 'Roofing labor', 'sq', 'order_squares'),
    ('dump', 'Dump / haul off', 'load', 'dump_loads'),
]