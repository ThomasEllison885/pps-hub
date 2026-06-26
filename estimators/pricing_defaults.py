"""Company-wide estimator pricing defaults (admin-editable, stored in hub_settings)."""

SETTINGS_KEY = 'estimator_pricing_defaults'

SYSTEM_DEFAULTS = {
    'siding': {
        'labor_per_sq': 180,
        'haul_per_sq': 25,
        'tax_pct': 7,
        'delivery': 15,
        'waste_pct': 14,
    },
    'roofing': {
        'labor_per_sq': 60,
        'material_per_sq': 65,
        'tax_pct': 7.5,
        'margin_pct': 25,
        'waste_pct': 12,
        'dump_divisor': 45,
        'dump_cost': 200,
    },
    'gutter': {
        'gutter_price_per_lf': 7,
        'guard_price_per_lf': 2,
        'labor_per_lf': 0,
        'tax_pct': 7.5,
        'margin_pct': 25,
        'waste_pct': 10,
        'downspout_lf_each': 10,
        'downspout_spacing_ft': 35,
    },
    'painting': {
        'labor_per_hour': 38,
        'margin_one_coat_pct': 42,
        'margin_two_coat_pct': 38,
        'two_coat_multiplier': 1.6,
    },
}


def _deep_merge(base, overrides):
    out = {}
    for trade, fields in base.items():
        merged = dict(fields)
        if overrides and trade in overrides:
            for k, v in (overrides[trade] or {}).items():
                if v is not None and v != '':
                    merged[k] = v
        out[trade] = merged
    return out


def get_pricing_defaults(get_db_fn):
    """Load merged defaults (system + DB). Returns dict with meta keys."""
    stored = {}
    meta = {'updated_at': None, 'updated_by': None, 'updated_by_name': None}
    try:
        conn = get_db_fn()
        if conn:
            cur = conn.cursor()
            cur.execute(
                'SELECT value, updated_at, updated_by FROM hub_settings WHERE key = %s',
                (SETTINGS_KEY,),
            )
            row = cur.fetchone()
            cur.close()
            conn.close()
            if row:
                import json
                raw = row[0]
                if isinstance(raw, str):
                    raw = json.loads(raw)
                stored = raw.get('trades') or raw
                meta['updated_at'] = row[1]
                meta['updated_by'] = row[2]
                meta['updated_by_name'] = raw.get('updated_by_name')
    except Exception as e:
        print(f'Pricing defaults load error: {e}')

    trades = _deep_merge(SYSTEM_DEFAULTS, stored)
    return {
        'trades': trades,
        'siding': trades['siding'],
        'roofing': trades['roofing'],
        'gutter': trades['gutter'],
        'painting': trades['painting'],
        **meta,
    }


def save_pricing_defaults(get_db_fn, trades, user_key, display_name=''):
    """Persist admin overrides (trades dict with siding/roofing/gutter keys)."""
    import json
    from datetime import datetime

    cleaned = {}
    for trade in ('siding', 'roofing', 'gutter', 'painting'):
        src = trades.get(trade) or SYSTEM_DEFAULTS.get(trade, {})
        cleaned[trade] = {}
        for key, default in SYSTEM_DEFAULTS.get(trade, {}).items():
            val = src.get(key, default)
            try:
                cleaned[trade][key] = float(val) if '.' in str(val) or isinstance(val, float) else int(val)
            except (TypeError, ValueError):
                cleaned[trade][key] = default

    payload = {
        'trades': cleaned,
        'updated_at': datetime.utcnow().isoformat() + 'Z',
        'updated_by': user_key,
        'updated_by_name': display_name,
    }

    conn = get_db_fn()
    if not conn:
        raise RuntimeError('Database unavailable')
    cur = conn.cursor()
    cur.execute(
        '''INSERT INTO hub_settings (key, value, updated_at, updated_by)
           VALUES (%s, %s, NOW(), %s)
           ON CONFLICT (key) DO UPDATE SET
             value = EXCLUDED.value,
             updated_at = NOW(),
             updated_by = EXCLUDED.updated_by''',
        (SETTINGS_KEY, json.dumps(payload), user_key),
    )
    conn.commit()
    cur.close()
    conn.close()
    return get_pricing_defaults(get_db_fn)