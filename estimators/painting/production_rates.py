"""Production rates from PPS Exterior Estimating Worksheet (Lists / Standard table)."""

# production_rate = units per hour (SF/hr or count/hr)
# paint_coverage = SF (or units) per gallon; 0 = no paint
# paint_cost = $/gallon

RATE_CATALOG = {
    'Easy 1': {'exterior_type': 'Soffit', 'unit': 'sf', 'production_rate': 25, 'paint_coverage': 150, 'paint_cost': 50},
    'Easy 2': {'exterior_type': 'Soffit', 'unit': 'sf', 'production_rate': 20, 'paint_coverage': 150, 'paint_cost': 50},
    'Easy 3': {'exterior_type': 'Soffit', 'unit': 'sf', 'production_rate': 15, 'paint_coverage': 150, 'paint_cost': 50},
    'Easy Prep': {'exterior_type': 'Soffit', 'unit': 'sf', 'production_rate': 15, 'paint_coverage': 0, 'paint_cost': 0},
    'Hard 1': {'exterior_type': 'Soffit', 'unit': 'sf', 'production_rate': 12, 'paint_coverage': 150, 'paint_cost': 50},
    'Hard 2': {'exterior_type': 'Soffit', 'unit': 'sf', 'production_rate': 9, 'paint_coverage': 150, 'paint_cost': 50},
    'Hard 3': {'exterior_type': 'Soffit', 'unit': 'sf', 'production_rate': 6, 'paint_coverage': 150, 'paint_cost': 50},
    'Hard Prep': {'exterior_type': 'Soffit', 'unit': 'sf', 'production_rate': 9, 'paint_coverage': 0, 'paint_cost': 0},
    'Airless': {'exterior_type': 'Siding', 'unit': 'sf', 'production_rate': 200, 'paint_coverage': 250, 'paint_cost': 45},
    'Easy Roll': {'exterior_type': 'Siding', 'unit': 'sf', 'production_rate': 150, 'paint_coverage': 250, 'paint_cost': 50},
    'Hard Roll': {'exterior_type': 'Siding', 'unit': 'sf', 'production_rate': 100, 'paint_coverage': 250, 'paint_cost': 50},
    'Brushwork': {'exterior_type': 'Siding', 'unit': 'sf', 'production_rate': 70, 'paint_coverage': 250, 'paint_cost': 50},
    'Siding Prep': {'exterior_type': 'Siding', 'unit': 'sf', 'production_rate': 50, 'paint_coverage': 250, 'paint_cost': 50},
    'Linear Masking': {'exterior_type': 'Siding', 'unit': 'sf', 'production_rate': 120, 'paint_coverage': 250, 'paint_cost': 50},
    'Mask Spots': {'exterior_type': 'Siding', 'unit': 'ea', 'production_rate': 6, 'paint_coverage': 250, 'paint_cost': 50},
    'Downspouts': {'exterior_type': 'Trim', 'unit': 'sf', 'production_rate': 40, 'paint_coverage': 350, 'paint_cost': 50},
    'Easy Fascia': {'exterior_type': 'Trim', 'unit': 'sf', 'production_rate': 60, 'paint_coverage': 350, 'paint_cost': 50},
    'Hard Fascia': {'exterior_type': 'Trim', 'unit': 'sf', 'production_rate': 30, 'paint_coverage': 350, 'paint_cost': 50},
    'Simple Post': {'exterior_type': 'Trim', 'unit': 'ea', 'production_rate': 3, 'paint_coverage': 100, 'paint_cost': 50},
    'Ornate Post': {'exterior_type': 'Trim', 'unit': 'ea', 'production_rate': 2, 'paint_coverage': 100, 'paint_cost': 50},
    'Stairs': {'exterior_type': 'Trim', 'unit': 'ea', 'production_rate': 6, 'paint_coverage': 75, 'paint_cost': 50},
    'Lattice': {'exterior_type': 'Trim', 'unit': 'sf', 'production_rate': 50, 'paint_coverage': 250, 'paint_cost': 50},
    'Prep Spots': {'exterior_type': 'Trim', 'unit': 'ea', 'production_rate': 3, 'paint_coverage': 0, 'paint_cost': 0},
    'Flat': {'exterior_type': 'Doors', 'unit': 'sf', 'production_rate': 4, 'paint_coverage': 15, 'paint_cost': 50},
    '1-3': {'exterior_type': 'Doors', 'unit': 'ea', 'production_rate': 2, 'paint_coverage': 15, 'paint_cost': 50},
    '5-8': {'exterior_type': 'Doors', 'unit': 'ea', 'production_rate': 1.3333333333333333, 'paint_coverage': 15, 'paint_cost': 50},
    '9-15': {'exterior_type': 'Doors', 'unit': 'ea', 'production_rate': 1, 'paint_coverage': 15, 'paint_cost': 50},
    '16-24': {'exterior_type': 'Doors', 'unit': 'ea', 'production_rate': 0.8, 'paint_coverage': 15, 'paint_cost': 50},
    'Simple Frame': {'exterior_type': 'Doors', 'unit': 'ea', 'production_rate': 3.0303030303030303, 'paint_coverage': 150, 'paint_cost': 50},
    'Ornate Frame': {'exterior_type': 'Doors', 'unit': 'ea', 'production_rate': 1, 'paint_coverage': 150, 'paint_cost': 50},
    '7 (Hardest)': {'exterior_type': 'PowerWash', 'unit': 'sf', 'production_rate': 400, 'paint_coverage': 0, 'paint_cost': 0},
    '6': {'exterior_type': 'PowerWash', 'unit': 'sf', 'production_rate': 500, 'paint_coverage': 0, 'paint_cost': 0},
    '5': {'exterior_type': 'PowerWash', 'unit': 'sf', 'production_rate': 600, 'paint_coverage': 0, 'paint_cost': 0},
    '4 (Medium)': {'exterior_type': 'PowerWash', 'unit': 'sf', 'production_rate': 700, 'paint_coverage': 0, 'paint_cost': 0},
    '3': {'exterior_type': 'PowerWash', 'unit': 'sf', 'production_rate': 800, 'paint_coverage': 0, 'paint_cost': 0},
    '2': {'exterior_type': 'PowerWash', 'unit': 'sf', 'production_rate': 900, 'paint_coverage': 0, 'paint_cost': 0},
    '1 (Easiest)': {'exterior_type': 'PowerWash', 'unit': 'sf', 'production_rate': 1000, 'paint_coverage': 0, 'paint_cost': 0},
}

EXTERIOR_SECTIONS = [
    {
        'type': 'Soffit',
        'hint': 'Measured in square feet unless noted.',
        'categories': ['Easy 1', 'Easy 2', 'Easy 3', 'Easy Prep', 'Hard 1', 'Hard 2', 'Hard 3', 'Hard Prep'],
    },
    {
        'type': 'Siding',
        'hint': 'Wall surface SF. Mask Spots = count of spots.',
        'categories': ['Airless', 'Easy Roll', 'Hard Roll', 'Brushwork', 'Siding Prep', 'Linear Masking', 'Mask Spots'],
    },
    {
        'type': 'Trim',
        'hint': 'Fascia/lattice in SF. Posts, stairs, prep spots in each (ea).',
        'categories': ['Downspouts', 'Easy Fascia', 'Hard Fascia', 'Simple Post', 'Ornate Post', 'Stairs', 'Lattice', 'Prep Spots'],
    },
    {
        'type': 'Doors',
        'hint': 'Panel doors in each. Flat doors in SF of slab.',
        'categories': ['Flat', '1-3', '5-8', '9-15', '16-24', 'Simple Frame', 'Ornate Frame'],
    },
    {
        'type': 'PowerWash',
        'hint': 'Building SF at selected difficulty (1 = easiest, 7 = hardest).',
        'categories': ['7 (Hardest)', '6', '5', '4 (Medium)', '3', '2', '1 (Easiest)'],
    },
]


def get_rate(category):
    return RATE_CATALOG.get(category)


def sections_for_ui():
    """Sections with category metadata for templates."""
    out = []
    for sec in EXTERIOR_SECTIONS:
        cats = []
        for name in sec['categories']:
            meta = RATE_CATALOG[name]
            cats.append({
                'name': name,
                'unit': meta['unit'],
                'production_rate': meta['production_rate'],
                'paint_coverage': meta['paint_coverage'],
            })
        out.append({'type': sec['type'], 'hint': sec['hint'], 'categories': cats})
    return out