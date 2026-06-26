"""PPS Siding Estimator — multi-building Excel output."""
import io
import math

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from .calculator import calculate_quantities

DARK_BLUE = '004C8C'
BLUE = '0096D6'
LIGHT_BLUE = 'EBF6FC'
WHITE = 'FFFFFF'
GRAY_HDR = 'F2F7FB'
WARNING = 'FFF3CD'

SOURCE_LABELS = {
    'eagleview': 'EagleView',
    'aerial_other': 'Other Aerial Report',
    'field': 'Field Measurements',
}


def build_estimate_excel(job, buildings, inputs, pricing):
    """
    job: property metadata dict
    buildings: list of {label, building_type, qty, source, measurements}
    inputs: siding specs + accessory flags
    pricing: optional unit price map
    Returns BytesIO
    """
    building_results = []
    for b in buildings:
        qty = max(int(b.get('qty') or 1), 1)
        q = calculate_quantities(b.get('measurements') or {}, inputs, qty=qty)
        building_results.append({
            'label': b.get('label') or 'Building',
            'building_type': b.get('building_type') or 'Building',
            'qty': qty,
            'source': b.get('source') or 'field',
            'measurements': b.get('measurements') or {},
            'quantities': q,
        })

    wb = Workbook()
    wb.remove(wb.active)

    mat_subtotal_row = _build_summary(wb, job, building_results, inputs)
    mat_subtotal_row = _build_materials(wb, building_results, inputs, pricing)
    labor_subtotal_row = _build_labor(wb)
    _build_totals(wb, mat_subtotal_row, labor_subtotal_row)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _style(ws, cell_ref, bold=False, size=11, color='000000', bg=None, align='left', number_format=None):
    c = ws[cell_ref]
    c.font = Font(name='Arial', bold=bold, size=size, color=color)
    c.alignment = Alignment(horizontal=align, vertical='center', wrap_text=True)
    if bg:
        c.fill = PatternFill('solid', start_color=bg)
    if number_format:
        c.number_format = number_format


def _section_head(ws, row, col, text, width=8):
    end_col = get_column_letter(col + width - 1)
    cl = get_column_letter(col)
    ws.merge_cells(f'{cl}{row}:{end_col}{row}')
    ws[f'{cl}{row}'].value = text
    ws[f'{cl}{row}'].font = Font(name='Arial', bold=True, size=10, color=WHITE)
    ws[f'{cl}{row}'].fill = PatternFill('solid', start_color=DARK_BLUE)
    ws[f'{cl}{row}'].alignment = Alignment(horizontal='left', vertical='center', indent=1)
    ws.row_dimensions[row].height = 20


def _build_summary(wb, job, building_results, inputs):
    ws = wb.create_sheet('1 – Job Summary')
    ws.sheet_view.showGridLines = False
    ws.column_dimensions['A'].width = 2
    for col, w in [('B', 28), ('C', 22), ('D', 16), ('E', 22), ('F', 16)]:
        ws.column_dimensions[col].width = w

    ws.row_dimensions[1].height = 8
    ws.merge_cells('B2:F2')
    ws['B2'] = 'PURE PROPERTY SOLUTIONS'
    ws['B2'].font = Font(name='Arial', bold=True, size=16, color=WHITE)
    ws['B2'].fill = PatternFill('solid', start_color=DARK_BLUE)
    ws.row_dimensions[2].height = 28

    ws.merge_cells('B3:F3')
    ws['B3'] = 'Siding Material Estimate'
    ws['B3'].font = Font(name='Arial', size=12, color=WHITE, italic=True)
    ws['B3'].fill = PatternFill('solid', start_color=BLUE)
    ws.row_dimensions[3].height = 20
    ws.row_dimensions[4].height = 8

    info = [
        ('Property:', job.get('property_name', '')),
        ('Address:', job.get('address', '')),
        ('Estimator:', job.get('estimator', '')),
        ('Date:', job.get('date', '')),
        ('Buildings:', str(len(building_results))),
    ]
    row = 5
    for label, val in info:
        ws[f'B{row}'] = label
        ws[f'B{row}'].font = Font(name='Arial', bold=True, size=10, color=DARK_BLUE)
        ws[f'C{row}'] = val
        row += 1
    row += 1

    _section_head(ws, row, 2, 'BUILDINGS ON THIS JOB', 5)
    row += 1
    s = Side(style='thin', color='D0DCE8')
    for col, txt in [('B', 'Building'), ('C', 'Type'), ('D', 'Qty'), ('E', 'Source'), ('F', 'Siding Sq')]:
        ws[f'{col}{row}'] = txt
        ws[f'{col}{row}'].font = Font(name='Arial', bold=True, size=9, color=DARK_BLUE)
        ws[f'{col}{row}'].fill = PatternFill('solid', start_color=LIGHT_BLUE)
    row += 1

    for i, b in enumerate(building_results):
        q = b['quantities']
        vals = [
            b['label'],
            b['building_type'],
            b['qty'],
            SOURCE_LABELS.get(b['source'], b['source']),
            q['siding_squares'],
        ]
        for j, col in enumerate('BCDEF'):
            ws[f'{col}{row}'] = vals[j]
            ws[f'{col}{row}'].font = Font(name='Arial', size=10)
            ws[f'{col}{row}'].fill = PatternFill('solid', start_color=GRAY_HDR if i % 2 == 0 else WHITE)
            ws[f'{col}{row}'].border = Border(left=s, right=s, top=s, bottom=s)
        row += 1

    row += 1
    _section_head(ws, row, 2, 'JOB ASSUMPTIONS', 5)
    row += 1
    assumptions = [
        ('Siding Type', inputs.get('siding_type', 'Vinyl Lap')),
        ('Vinyl Exposure', f"{inputs.get('exposure_in', 'N/A')}\"" if 'vinyl' in inputs.get('siding_type', '').lower() else 'N/A'),
        ('Waste Factor', f"{inputs.get('waste_pct', 10)}%"),
        ('Corner Post Length', f"{inputs.get('post_length', 12)} ft"),
        ('Stories', str(inputs.get('stories', 2))),
        ('House Wrap', 'Yes' if inputs.get('include_housewrap') else 'No'),
        ('Fan Fold', 'Yes' if inputs.get('include_fanfold') else 'No'),
        ('Soffit', 'Yes' if inputs.get('include_soffit') else 'No'),
        ('Fascia Metal Wrap', 'Yes' if inputs.get('include_fascia_wrap') else 'No'),
    ]
    for j, (lbl, val) in enumerate(assumptions):
        rr = row + j
        ws[f'B{rr}'] = lbl
        ws[f'C{rr}'] = val
        for col in ['B', 'C']:
            ws[f'{col}{rr}'].font = Font(name='Arial', size=10, bold=(col == 'B'))
            ws[f'{col}{rr}'].fill = PatternFill('solid', start_color=GRAY_HDR if j % 2 == 0 else WHITE)
            ws[f'{col}{rr}'].border = Border(left=s, right=s, top=s, bottom=s)
    row += len(assumptions) + 1

    for b in building_results:
        _section_head(ws, row, 2, f"{b['label'].upper()} — MEASUREMENTS", 5)
        row += 1
        m = b['measurements']
        meas_rows = [
            ('Net Wall Area', m.get('wall_area_net'), 'sq ft'),
            ('Gross Wall Area', m.get('wall_area_gross'), 'sq ft'),
            ('W&D Perimeter', m.get('window_door_perimeter'), 'lin ft'),
            ('Inside Corners', m.get('inside_corners'), 'lin ft'),
            ('Outside Corners', m.get('outside_corners'), 'lin ft'),
            ('Fascia', m.get('fascia'), 'lin ft'),
        ]
        for lbl, val, unit in meas_rows:
            ws[f'B{row}'] = lbl
            ws[f'C{row}'] = val if val is not None else 'NOT FOUND'
            ws[f'D{row}'] = unit
            for col in ['B', 'C', 'D']:
                ws[f'{col}{row}'].font = Font(name='Arial', size=10, color='CC0000' if val is None else '000000')
                ws[f'{col}{row}'].fill = PatternFill('solid', start_color=WARNING if val is None else GRAY_HDR)
                ws[f'{col}{row}'].border = Border(left=s, right=s, top=s, bottom=s)
            row += 1
        row += 1

    ws.merge_cells(f'B{row}:F{row}')
    ws[f'B{row}'] = (
        'All quantities are estimates. Field verify before ordering. '
        'Accessory quantities may vary by manufacturer and profile.'
    )
    ws[f'B{row}'].font = Font(name='Arial', size=9, color='7A5C00', italic=True)
    ws[f'B{row}'].fill = PatternFill('solid', start_color=WARNING)
    ws.row_dimensions[row].height = 32
    return row


def _build_materials(wb, building_results, inputs, pricing):
    ws = wb.create_sheet('2 – Materials')
    ws.sheet_view.showGridLines = False
    ws.column_dimensions['A'].width = 2
    for col, w in [('B', 34), ('C', 14), ('D', 14), ('E', 12), ('F', 10), ('G', 14), ('H', 14)]:
        ws.column_dimensions[col].width = w

    ws.row_dimensions[1].height = 8
    ws.merge_cells('B2:H2')
    ws['B2'] = 'MATERIAL QUANTITIES & PRICING'
    ws['B2'].font = Font(name='Arial', bold=True, size=14, color=WHITE)
    ws['B2'].fill = PatternFill('solid', start_color=DARK_BLUE)
    ws.row_dimensions[2].height = 26
    ws.row_dimensions[3].height = 8

    s = Side(style='thin', color='D0DCE8')
    row = 4
    price_rows = []

    def hdr(r):
        for col, txt in [
            ('B', 'Item'), ('C', 'Basis'), ('D', 'Lin Ft / Sq Ft'),
            ('E', 'Pieces / Qty'), ('F', 'Unit'), ('G', 'Unit Price'), ('H', 'Extended $'),
        ]:
            ws[f'{col}{r}'] = txt
            ws[f'{col}{r}'].font = Font(name='Arial', bold=True, size=9, color=WHITE)
            ws[f'{col}{r}'].fill = PatternFill('solid', start_color=BLUE)
        ws.row_dimensions[r].height = 18

    def item_row(r, label, basis, lin_or_sq, pieces, unit, price_key, bg):
        ws[f'B{r}'] = label
        ws[f'C{r}'] = basis
        ws[f'D{r}'] = lin_or_sq
        ws[f'E{r}'] = pieces
        ws[f'F{r}'] = unit
        unit_price = pricing.get(price_key)
        ws[f'G{r}'] = unit_price if unit_price else ''
        ws[f'H{r}'] = f'=E{r}*G{r}' if unit_price else ''
        if unit_price or pieces:
            price_rows.append(r)
        for col in 'BCDEFGH':
            ws[f'{col}{r}'].font = Font(name='Arial', size=10)
            ws[f'{col}{r}'].fill = PatternFill('solid', start_color=bg)
            ws[f'{col}{r}'].border = Border(left=s, right=s, top=s, bottom=s)
            if col in ('D', 'E'):
                ws[f'{col}{r}'].alignment = Alignment(horizontal='center')
            if col == 'G' and not unit_price:
                ws[f'{col}{r}'].fill = PatternFill('solid', start_color=WARNING)
            if col in ('G', 'H'):
                ws[f'{col}{r}'].number_format = '_($* #,##0.00_)'
                ws[f'{col}{r}'].alignment = Alignment(horizontal='right')
        ws.row_dimensions[r].height = 15
        return r

    for bi, b in enumerate(building_results):
        q = b['quantities']
        title = f"{b['label'].upper()} — {b['building_type']} × {b['qty']}"
        _section_head(ws, row, 2, title, 7)
        row += 1
        hdr(row)
        row += 1

        stype = q['siding_type']
        exposure_note = f"Exposure: {q['exposure_in']}\"" if 'vinyl' in stype.lower() else ''
        row = item_row(
            row,
            f'{stype} Siding {exposure_note}',
            f"Net wall {q['wall_area_net']} sq ft × {q['waste_pct']}% waste × qty {q['qty']}",
            q['siding_area_with_waste'],
            round(q['siding_squares'], 2),
            'sq',
            'siding_sq',
            GRAY_HDR,
        )
        row += 1

        trim_items = [
            ('Starter Strip / Receiver Track', q['starter_lin_ft'], q['starter_pieces'], '10ft pieces', 'starter_piece', WHITE),
            ('J-Channel', q['jchannel_lin_ft'], q['jchannel_pieces'], '12ft sticks', 'jchannel_piece', GRAY_HDR),
            ('Inside Corner Post', q['inside_corners_lin_ft'], q['inside_corner_pieces'], f"{q['post_length']}ft posts", 'inside_corner_post', WHITE),
            ('Outside Corner Post', q['outside_corners_lin_ft'], q['outside_corner_pieces'], f"{q['post_length']}ft posts", 'outside_corner_post', GRAY_HDR),
            ('Under-Sill / Utility Trim', q['utility_lin_ft'], q['utility_pieces'], '12ft pieces', 'utility_piece', WHITE),
        ]
        if inputs.get('include_fascia_wrap') and q['fascia_lin_ft']:
            trim_items.append(
                ('Fascia Cover / Aluminum Coil', q['fascia_lin_ft'], q['fascia_pieces'], '12ft pieces', 'fascia_piece', GRAY_HDR)
            )
        if inputs.get('include_soffit') and q.get('soffit_lin_ft'):
            trim_items.append(
                ('Soffit', q['soffit_lin_ft'], q['soffit_pieces'], '12ft pieces', 'soffit_piece', WHITE)
            )

        for label, linft, pcs, unit, key, bg in trim_items:
            row = item_row(row, label, f'{linft} lin ft', linft, pcs, unit, key, bg)
            row += 1

        if inputs.get('include_housewrap'):
            row = item_row(
                row, 'House Wrap',
                f"Gross wall {q['housewrap_sqft']} sq ft",
                q['housewrap_sqft'], q['housewrap_rolls'], '9-sq rolls',
                'housewrap_roll', GRAY_HDR,
            )
            row += 1
        if inputs.get('include_fanfold'):
            row = item_row(
                row, 'Fan Fold Insulation',
                f"Net wall ~{q['fanfold_squares']} sq",
                q['siding_area_with_waste'], q['fanfold_squares'], 'squares',
                'fanfold_sq', WHITE,
            )
            row += 1
        row += 1

    subtotal_row = row
    ws.merge_cells(f'B{subtotal_row}:G{subtotal_row}')
    ws[f'B{subtotal_row}'] = 'MATERIAL SUBTOTAL (ALL BUILDINGS)'
    ws[f'B{subtotal_row}'].font = Font(name='Arial', bold=True, size=11, color=WHITE)
    ws[f'B{subtotal_row}'].fill = PatternFill('solid', start_color=DARK_BLUE)
    ws[f'B{subtotal_row}'].alignment = Alignment(horizontal='right', vertical='center', indent=1)
    if price_rows:
        refs = ','.join(f'H{r}' for r in price_rows)
        ws[f'H{subtotal_row}'] = f'=SUM({refs})'
    else:
        ws[f'H{subtotal_row}'] = 0
    ws[f'H{subtotal_row}'].font = Font(name='Arial', bold=True, size=11, color=WHITE)
    ws[f'H{subtotal_row}'].fill = PatternFill('solid', start_color=DARK_BLUE)
    ws[f'H{subtotal_row}'].number_format = '_($* #,##0.00_)'
    ws.row_dimensions[subtotal_row].height = 22

    note_row = subtotal_row + 2
    ws.merge_cells(f'B{note_row}:H{note_row}')
    ws[f'B{note_row}'] = 'Yellow unit price cells are blank — enter pricing to calculate extended costs.'
    ws[f'B{note_row}'].font = Font(name='Arial', size=9, italic=True, color='7A5C00')
    ws[f'B{note_row}'].fill = PatternFill('solid', start_color=WARNING)
    return subtotal_row


def _build_labor(wb):
    ws = wb.create_sheet('3 – Labor')
    ws.sheet_view.showGridLines = False
    ws.column_dimensions['A'].width = 2
    for col, w in [('B', 36), ('C', 14), ('D', 12), ('E', 14), ('F', 14)]:
        ws.column_dimensions[col].width = w

    ws.merge_cells('B2:F2')
    ws['B2'] = 'LABOR ESTIMATE'
    ws['B2'].font = Font(name='Arial', bold=True, size=14, color=WHITE)
    ws['B2'].fill = PatternFill('solid', start_color=DARK_BLUE)
    ws.row_dimensions[2].height = 26

    s = Side(style='thin', color='D0DCE8')
    for col, txt in [('B', 'Labor Item'), ('C', 'Quantity'), ('D', 'Unit'), ('E', 'Unit Price'), ('F', 'Extended $')]:
        ws[f'{col}5'] = txt
        ws[f'{col}5'].font = Font(name='Arial', bold=True, size=9, color=WHITE)
        ws[f'{col}5'].fill = PatternFill('solid', start_color=BLUE)

    labor_items = [
        ('Tear off & removal of existing siding', 'sq'),
        ('Dumpster / haul away', 'allowance'),
        ('Siding installation', 'sq'),
        ('House wrap / fan fold installation', 'sq'),
        ('Window wrap (per opening)', 'each'),
        ('Door wrap (per opening)', 'each'),
        ('Fascia wrap – aluminum', 'lin ft'),
        ('Soffit installation', 'sq ft'),
        ('Metal corner wrap', 'lin ft'),
        ('J-channel / trim installation', 'lin ft'),
        ('Corner post installation', 'each'),
        ('Caulking / sealants', 'allowance'),
        ('Miscellaneous / contingency', '%'),
        ('', ''),
        ('', ''),
    ]
    for i, (label, unit) in enumerate(labor_items):
        r = 6 + i
        bg = GRAY_HDR if i % 2 == 0 else WHITE
        ws[f'B{r}'] = label
        ws[f'C{r}'] = ''
        ws[f'D{r}'] = unit
        ws[f'E{r}'] = ''
        ws[f'F{r}'] = f'=IF(AND(C{r}<>"",E{r}<>""),C{r}*E{r},"")'
        for col in 'BCDEF':
            ws[f'{col}{r}'].font = Font(name='Arial', size=10)
            ws[f'{col}{r}'].fill = PatternFill('solid', start_color=bg)
            ws[f'{col}{r}'].border = Border(left=s, right=s, top=s, bottom=s)
            if col in ('E', 'F'):
                ws[f'{col}{r}'].number_format = '_($* #,##0.00_)'

    last_data = 6 + len(labor_items) - 1
    subtotal_row = last_data + 2
    ws.merge_cells(f'B{subtotal_row}:E{subtotal_row}')
    ws[f'B{subtotal_row}'] = 'LABOR SUBTOTAL'
    ws[f'B{subtotal_row}'].font = Font(name='Arial', bold=True, size=11, color=WHITE)
    ws[f'B{subtotal_row}'].fill = PatternFill('solid', start_color=DARK_BLUE)
    ws[f'F{subtotal_row}'] = f'=IFERROR(SUM(F6:F{last_data}),0)'
    ws[f'F{subtotal_row}'].font = Font(name='Arial', bold=True, size=11, color=WHITE)
    ws[f'F{subtotal_row}'].fill = PatternFill('solid', start_color=DARK_BLUE)
    ws[f'F{subtotal_row}'].number_format = '_($* #,##0.00_)'
    return subtotal_row


def _build_totals(wb, mat_subtotal_row, labor_subtotal_row):
    ws = wb.create_sheet('4 – Estimate Total')
    ws.sheet_view.showGridLines = False
    ws.column_dimensions['B'].width = 30
    ws.column_dimensions['C'].width = 20

    ws.merge_cells('B2:C2')
    ws['B2'] = 'ESTIMATE TOTAL SUMMARY'
    ws['B2'].font = Font(name='Arial', bold=True, size=14, color=WHITE)
    ws['B2'].fill = PatternFill('solid', start_color=DARK_BLUE)
    ws.row_dimensions[2].height = 26

    s = Side(style='thin', color='D0DCE8')

    def total_row(r, label, formula, bg=GRAY_HDR, bold=False, size=10):
        ws[f'B{r}'] = label
        ws[f'C{r}'] = formula
        for col in 'BC':
            ws[f'{col}{r}'].font = Font(name='Arial', bold=bold, size=size, color=WHITE if bg == DARK_BLUE else '000000')
            ws[f'{col}{r}'].fill = PatternFill('solid', start_color=bg)
            ws[f'{col}{r}'].border = Border(left=s, right=s, top=s, bottom=s)
        ws[f'C{r}'].number_format = '_($* #,##0.00_)'
        ws[f'C{r}'].alignment = Alignment(horizontal='right')
        ws[f'B{r}'].alignment = Alignment(horizontal='left', indent=1)

    total_row(4, 'Material Subtotal', f"='2 – Materials'!H{mat_subtotal_row}")
    total_row(5, 'Labor Subtotal', f"='3 – Labor'!F{labor_subtotal_row}")
    total_row(7, 'COMBINED TOTAL (Materials + Labor)', '=C4+C5', DARK_BLUE, bold=True, size=12)
    total_row(9, 'Markup / Margin (%)', '', WARNING)
    ws['C9'] = 0
    ws['C9'].number_format = '0.0%'
    total_row(10, 'Markup Amount', '=C7*C9')
    total_row(12, 'FINAL ESTIMATE', '=C7+C10', DARK_BLUE, bold=True, size=13)

    ws.merge_cells('B14:C14')
    ws['B14'] = (
        'Material subtotal pulls from Tab 2. Labor subtotal pulls from Tab 3. '
        'Enter markup as a decimal (e.g. 0.15 = 15%). Verify all quantities before use.'
    )
    ws['B14'].font = Font(name='Arial', size=9, italic=True, color='666666')
    ws.row_dimensions[14].height = 40

    ws.merge_cells('B17:C17')
    ws['B17'] = 'Pure Property Solutions  ·  Trust. Quality. Results.™'
    ws['B17'].font = Font(name='Arial', size=9, color='888888', italic=True)
    ws['B17'].alignment = Alignment(horizontal='center')