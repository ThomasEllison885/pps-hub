"""Search hub records by property address — does not fetch external measurement data."""


def lookup_property_by_address(get_db_fn, query, limit=12):
    """
    Return prior hub records matching an address (clients, proposals, estimates).
    Measurement takeoffs still require EagleView/Roofr PDFs or field entry.
    """
    q = (query or '').strip()
    if len(q) < 3:
        return {'results': [], 'note': None}

    pattern = f'%{q}%'
    results = []

    conn = get_db_fn()
    if not conn:
        return {
            'results': [],
            'note': 'Database unavailable — enter job details manually.',
        }

    from psycopg2.extras import RealDictCursor
    cur = conn.cursor(cursor_factory=RealDictCursor)

    def _add(row, rtype, title_key, meta_fn):
        results.append({
            'type': rtype,
            'title': row.get(title_key) or row.get('property_name') or row.get('name'),
            'property_name': row.get('property_name') or row.get('name'),
            'address': row.get('property_address') or row.get('address'),
            'meta': meta_fn(row),
            'date': row['generated_at'].strftime('%b %d, %Y') if row.get('generated_at') else (
                row['updated_at'].strftime('%b %d, %Y') if row.get('updated_at') else ''
            ),
            'link': row.get('link'),
        })

    cur.execute(
        '''SELECT name, company, property_name, address, updated_at
           FROM clients
           WHERE address ILIKE %s OR property_name ILIKE %s OR name ILIKE %s
           ORDER BY updated_at DESC NULLS LAST LIMIT 5''',
        (pattern, pattern, pattern),
    )
    for row in cur.fetchall():
        _add(row, 'Client', 'name', lambda r: r.get('company') or r.get('property_name') or '')

    cur.execute(
        '''SELECT id, property_name, property_address, consultant_name, generated_at
           FROM proposal_log
           WHERE property_address ILIKE %s OR property_name ILIKE %s
           ORDER BY generated_at DESC LIMIT 4''',
        (pattern, pattern),
    )
    for row in cur.fetchall():
        row['link'] = None
        _add(row, 'Proposal', 'property_name', lambda r: r.get('consultant_name') or '')

    for table, label, meta_col in (
        ('roofing_estimate_log', 'Roofing estimate', 'report_type'),
        ('siding_estimate_log', 'Siding estimate', 'building_count'),
        ('gutter_estimate_log', 'Gutter estimate', 'gutter_lf'),
        ('painting_estimate_log', 'Painting estimate', 'line_count'),
    ):
        cur.execute(
            f'''SELECT id, property_name, property_address, {meta_col}, generated_at
                FROM {table}
                WHERE property_address ILIKE %s OR property_name ILIKE %s
                ORDER BY generated_at DESC LIMIT 3''',
            (pattern, pattern),
        )
        for row in cur.fetchall():
            if label == 'Roofing estimate':
                meta = row.get('report_type') or ''
            elif label == 'Siding estimate':
                meta = f"{row.get('building_count') or 1} buildings"
            elif label == 'Gutter estimate':
                meta = f"{row.get('gutter_lf') or 0:.0f} LF gutter" if row.get('gutter_lf') else ''
            else:
                meta = f"{row.get('line_count') or 0} takeoff lines"
            row['_meta'] = meta
            _add(row, label, 'property_name', lambda r, m=meta: m)

    cur.close()
    conn.close()

    # Dedupe by title+type, keep order
    seen = set()
    unique = []
    for r in results:
        key = (r.get('type'), r.get('title'), r.get('address'))
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)

    return {
        'results': unique[:limit],
        'note': (
            'Hub history only — roof squares, wall SF, and paint takeoff still require '
            'an EagleView/Roofr report PDF or field measurements.'
        ),
    }