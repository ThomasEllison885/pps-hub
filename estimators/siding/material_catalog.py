"""Material line definitions aligned with PPS estimator worksheet."""

TAKEOFF_LINES = [
    ('wall_area', 'Wall Area', 'wall_area_net'),
    ('top_walls', 'Top Of Walls', 'top_walls_ft'),
    ('bottom_walls', 'Bottom Of Walls', 'bottom_walls_ft'),
    ('inside_corners', 'Inside Corners', 'inside_corners'),
    ('outside_corners', 'Outside Corners', 'outside_corners'),
    ('window_door_perimeter', 'Window and Door Perimeter', 'window_door_perimeter'),
    ('unit_count', 'Number of Units / Apartments', 'unit_count'),
    ('fascia', 'Fascia', 'fascia'),
]

LIBRARY_LINES = [
    ('siding_sq', 'NDX Vinyl Siding (per sq)', 1.0),
    ('outside_corner_post', "NDX 12' Outside Corner", 0.2),
    ('inside_corner_post', 'NDX Inside Corner 3/4', 0.15),
    ('jchannel_piece', 'NDX 5/8 J Channel', 5.0),
    ('utility_piece', 'NDX Universal Trim', 1.5),
    ('starter_piece', 'QA Starter', 5.0),
    ('housewrap_roll', 'House Wrap', 1.0),
    ('housewrap_tape', 'House Wrap Tape', 0.5),
    ('jblock_uniblock', 'J Block Uniblock', 1.5),
    ('jblock_mblock', 'J Block M Block', 1.5),
    ('exhaust_vent', 'Exhaust Vent', 2.0),
    ('roofing_nails', 'Roofing Nails', 0.5),
    ('cap_nails', 'Cap Nails', 0.5),
    ('fascia_piece', 'Roll of Coil Stock', 0.5),
]

# Each entry: key, label, takeoff_key|None, divisor|None, unit, fixed_qty|None, count_mult|None
DETAIL_LINES = [
    ('siding_sq', 'NDX Vinyl Siding', 'wall_area', 100.0, 'sq', None, None),
    ('outside_corner_post', "NDX 12' Outside Corner White", 'outside_corners', 12.0, 'pcs', None, None),
    ('inside_corner_post', 'NDX Inside Corner 3/4 White', 'inside_corners', 12.0, 'pcs', None, None),
    ('jchannel_piece', 'NDX 5/8 J Channel White', 'jchannel_total', 12.0, 'pcs', None, None),
    ('utility_piece', 'NDX Universal Trim', 'top_walls', 12.0, 'pcs', None, None),
    ('starter_piece', 'QA Starter', 'bottom_walls', 12.0, 'pcs', None, None),
    ('housewrap_roll', 'House Wrap', 'wall_area', 1350.0, 'rolls', None, None),
    ('housewrap_tape', 'House Wrap Tape', 'housewrap_rolls', 2.0, 'rolls', None, None),
    ('jblock_uniblock', 'J Block Uniblock White', 'unit_count', 1.0, 'pcs', None, 2.0),
    ('jblock_mblock', 'J Block M Block White', 'unit_count', 1.0, 'pcs', None, 2.0),
    ('exhaust_vent', 'Exhaust Vent', 'unit_count', 1.0, 'pcs', None, 2.0),
    ('roofing_nails', 'Roofing Nails', None, None, 'box', 2.0, None),
    ('cap_nails', 'Cap Nails', None, None, 'box', 2.0, None),
    ('fascia_piece', 'Roll of Coil Stock', 'fascia', 50.0, 'rolls', None, None),
    ('haul_off_building', 'Haul Off and Dump Fees', 'siding_sq_order', 1.0, 'allowance', None, None),
]


def measurement_values(measurements, quantities):
    """Flatten measurements + derived takeoff helpers for one building."""
    m = measurements or {}
    q = quantities or {}
    top = q.get('starter_lin_ft') or m.get('window_door_perimeter') or 0
    bottom = top
    return {
        'wall_area_net': m.get('wall_area_net') or q.get('wall_area_net') or 0,
        'top_walls_ft': top,
        'bottom_walls_ft': bottom,
        'inside_corners': m.get('inside_corners') or 0,
        'outside_corners': m.get('outside_corners') or 0,
        'window_door_perimeter': m.get('window_door_perimeter') or 0,
        'wd_count': m.get('window_door_count') or q.get('wd_count') or 0,
        'unit_count': m.get('unit_count') or m.get('apartment_count') or 0,
        'fascia': m.get('fascia') or 0,
        'jchannel_total': (m.get('window_door_perimeter') or 0) + top,
        'housewrap_rolls': q.get('housewrap_rolls') or 0,
        'siding_sq_order': q.get('siding_squares') or 0,
    }