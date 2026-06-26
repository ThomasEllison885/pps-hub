"""Parse EagleView Walls PDF for exterior painting takeoff hints."""
from estimators.siding.eagleview_parser import parse_eagleview_walls


def parse_painting_measurements(pdf_bytes):
    """
    Returns (measurements, warnings, suggestions).
    suggestions maps category keys to suggested measured quantities.
    """
    measurements, warnings = parse_eagleview_walls(pdf_bytes)
    measurements['report_type'] = 'eagleview_walls'
    suggestions = {}

    wall = measurements.get('wall_area_net')
    if wall:
        suggestions['Easy Roll'] = {'measured': wall, 'note': 'Net wall area from EagleView'}

    soffit = measurements.get('soffit')
    if soffit:
        suggestions['Easy 1'] = {'measured': soffit, 'note': 'Soffit LF from report — confirm SF if width ≠ 1 ft'}

    fascia = measurements.get('fascia')
    if fascia:
        suggestions['Easy Fascia'] = {'measured': fascia, 'note': 'Fascia LF from report — confirm SF'}

    wd_perim = measurements.get('window_door_perimeter')
    if wd_perim:
        suggestions['Linear Masking'] = {'measured': wd_perim, 'note': 'W&D perimeter LF — masking labor'}

    if not suggestions:
        warnings.append('No wall/soffit/fascia quantities found — enter takeoff manually.')

    return measurements, warnings, suggestions