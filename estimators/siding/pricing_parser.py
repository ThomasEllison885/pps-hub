"""Parse siding pricing uploads (simple CSV or per-square library CSV)."""
import csv
import io
import re

# Friendly aliases → internal price keys used in Excel
KEY_ALIASES = {
    'siding': 'siding_sq',
    'siding_sq': 'siding_sq',
    'vinyl siding': 'siding_sq',
    'ndx vinyl siding': 'siding_sq',
    'ndx vinyl siding (per sq)': 'siding_sq',
    'ndx woodsman': 'siding_sq',
    'starter': 'starter_piece',
    'starter_piece': 'starter_piece',
    'qa starter': 'starter_piece',
    'starter strip': 'starter_piece',
    'starter strip / receiver track': 'starter_piece',
    'j-channel': 'jchannel_piece',
    'j channel': 'jchannel_piece',
    'jchannel': 'jchannel_piece',
    'ndx 5/8 j channel': 'jchannel_piece',
    'jchannel_piece': 'jchannel_piece',
    'inside corner': 'inside_corner_post',
    'inside corner post': 'inside_corner_post',
    'ndx inside corner 3/4': 'inside_corner_post',
    'inside_corner_post': 'inside_corner_post',
    'outside corner': 'outside_corner_post',
    'outside corner post': 'outside_corner_post',
    "ndx 12' outside corner": 'outside_corner_post',
    'outside_corner_post': 'outside_corner_post',
    'fascia': 'fascia_piece',
    'coil stock': 'fascia_piece',
    'roll of coil stock': 'fascia_piece',
    'fascia_piece': 'fascia_piece',
    'utility trim': 'utility_piece',
    'universal trim': 'utility_piece',
    'ndx universal trim': 'utility_piece',
    'utility_piece': 'utility_piece',
    'house wrap': 'housewrap_roll',
    'housewrap_roll': 'housewrap_roll',
    'house wrap tape': 'housewrap_tape',
    'housewrap_tape': 'housewrap_tape',
    'fan fold': 'fanfold_sq',
    'fanfold_sq': 'fanfold_sq',
    'soffit': 'soffit_piece',
    'soffit_piece': 'soffit_piece',
    'j block': 'jblock_uniblock',
    'j block uniblock': 'jblock_uniblock',
    'jblock_uniblock': 'jblock_uniblock',
    'm block': 'jblock_mblock',
    'j block m block': 'jblock_mblock',
    'jblock_mblock': 'jblock_mblock',
    'exhaust vent': 'exhaust_vent',
    'exhaust_vent': 'exhaust_vent',
    'roofing nails': 'roofing_nails',
    'roofing_nails': 'roofing_nails',
    'cap nails': 'cap_nails',
    'cap_nails': 'cap_nails',
    'haul off': 'haul_off_building',
    'haul_off_building': 'haul_off_building',
}


def _parse_price(val):
    if val is None:
        return None
    s = str(val).strip().replace('$', '').replace(',', '')
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _norm_header(h):
    return re.sub(r'[^a-z0-9]+', '_', (h or '').strip().lower()).strip('_')


def _resolve_key(raw_key, raw_name):
    for candidate in (raw_key, raw_name):
        if not candidate:
            continue
        c = str(candidate).strip().lower()
        if c in KEY_ALIASES:
            return KEY_ALIASES[c]
        norm = _norm_header(c)
        if norm in KEY_ALIASES:
            return KEY_ALIASES[norm]
    return (raw_key or '').strip() or None


def parse_pricing_upload(file_storage):
    """
    Parse uploaded pricing CSV.
    Returns dict with keys: prices (key->float), library (optional per-sq rows), warnings, loaded_count.
    """
    result = {'prices': {}, 'library': [], 'warnings': [], 'loaded_count': 0}
    if not file_storage:
        return result

    raw = file_storage.read()
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('latin-1')

    if not text.strip():
        result['warnings'].append('Pricing file was empty.')
        return result

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        result['warnings'].append('Could not read column headers from pricing file.')
        return result

    fields = {_norm_header(h): h for h in reader.fieldnames if h}

    key_col = fields.get('key') or fields.get('item_key') or fields.get('item_name') or fields.get('item')
    name_col = fields.get('description') or fields.get('item_name') or fields.get('item')
    price_col = (
        fields.get('unit_price')
        or fields.get('item_price')
        or fields.get('price')
        or fields.get('cost')
    )
    factor_col = fields.get('qty_per_sq') or fields.get('quantity_per_sq') or fields.get('qty_per_square')

    if not price_col:
        result['warnings'].append('No price column found (use unit_price or Item Price).')
        return result

    for i, row in enumerate(reader, start=2):
        raw_key = row.get(key_col, '').strip() if key_col else ''
        if name_col and name_col != key_col:
            raw_name = (row.get(name_col) or '').strip()
        elif key_col:
            raw_name = raw_key
        else:
            raw_name = (row.get(name_col) or '').strip() if name_col else ''
        price = _parse_price(row.get(price_col))
        factor = _parse_price(row.get(factor_col)) if factor_col else None

        if factor_col and factor is not None and raw_name:
            result['library'].append({
                'name': raw_name,
                'qty_per_sq': factor,
                'unit_price': price,
            })
            lib_key = _resolve_key(raw_key, raw_name)
            if lib_key and price is not None and lib_key not in result['prices']:
                result['prices'][lib_key] = price
            if price is not None:
                result['loaded_count'] += 1
            continue

        key = _resolve_key(raw_key, raw_name)
        if not key:
            if raw_name or raw_key:
                result['warnings'].append(f'Row {i}: could not match item "{raw_name or raw_key}" — skipped.')
            continue
        if price is None:
            result['warnings'].append(f'Row {i}: "{raw_name or key}" has no price — skipped.')
            continue
        result['prices'][key] = price
        result['loaded_count'] += 1

    if result['loaded_count'] == 0 and not result['warnings']:
        result['warnings'].append('No prices were loaded — check column headers and save as CSV from Excel.')
    return result