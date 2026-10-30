"""Build an editable, deduplicated term-registration workbook from Gold R14."""
from collections import OrderedDict
from pathlib import Path
import hashlib
import json
import math
import zipfile

import xlsxwriter
from openpyxl import load_workbook
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent
SOURCE = OUT.parent / 'DATAIKU_GOLD_DOMAIN_CORRECTION_20261029_R14' / 'MODEL.json'
FILE = OUT / '골드_R14_용어등록_38개_복사용.xlsx'
HEADERS = ['논리명', '물리명', '타입 및 크기', '정의']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    source_hash = sha(SOURCE)
    model = json.loads(SOURCE.read_text(encoding='utf-8'))
    terms = OrderedDict()
    for ti, table in enumerate(model['tables'], 1):
        for ci, col in enumerate(table['columns'], 1):
            entry = terms.setdefault(col['name'], {
                'id': len(terms) + 1,
                'values': [col['logical'], col['name'], col['type'], col['definition']],
                'metadata_basis': col['metadata_basis'],
                'usages': [],
            })
            assert entry['values'][:3] == [col['logical'], col['name'], col['type']]
            entry['usages'].append({'table_number': ti, 'table': table['suffix'],
                                    'table_logical': table['logical'], 'column_number': ci,
                                    'original_definition': col['definition']})
    items = list(terms.values())
    assert len(items) == 38 and sum(len(x['usages']) for x in items) == 60
    assert len({x['values'][0] for x in items}) == 38
    book = xlsxwriter.Workbook(FILE)
    book.set_properties({'title': '골드 R14 용어등록 38개', 'author': '8-AGENT',
                         'comments': 'R14 기준 등록 보조 파일. 용어목록의 4개 필드만 편집.'})
    book.set_calc_mode('auto')
    copy = book.add_worksheet('오른쪽복사')
    master = book.add_worksheet('용어목록')
    change = book.add_worksheet('변경확인')
    base = book.add_worksheet('원본기준')
    base.hide()
    navy, teal, line = '#16324F', '#DCEEF0', '#D8E2EC'
    normal = {'font_name': '맑은 고딕', 'font_size': 11, 'valign': 'vcenter', 'text_wrap': True}
    def fmt(**kwargs):
        return book.add_format({**normal, **kwargs})
    title = fmt(bold=True, font_size=16, font_color=navy)
    note = fmt(font_size=10, font_color='#526273')
    head = fmt(bold=True, font_color='white', bg_color=navy)
    label = fmt(bold=True, font_size=10, bg_color=teal, bottom=1, bottom_color=line)
    value = fmt(bg_color='#FFFFFF', bottom=1, bottom_color=line, indent=1)
    editable = fmt(bg_color='#FFF9E9', bottom=1, bottom_color=line, indent=1)
    soft = fmt(font_size=10, font_color='#526273', bg_color='#F0F4F8')
    link = fmt(font_color='#136D91', underline=True, font_size=10)
    changed = fmt(bg_color='#FFE7BA', font_color='#8C4800')
    error = fmt(bg_color='#FDE7E7', font_color='#9C1C1C')
    for sheet in (copy, master, change):
        sheet.hide_gridlines(2)
        sheet.set_tab_color(navy if sheet is copy else '#438A99')
        sheet.set_landscape()
        sheet.set_paper(9)
        sheet.fit_to_pages(1, 0)
        sheet.set_margins(0.3, 0.3, 0.4, 0.4)
    master.set_zoom(80)
    for ci, width in enumerate([21, 29, 25, 44]):
        master.set_column(ci, ci, width)
    master.set_column('E:E', 10, None, {'hidden': True})
    master.merge_range('A1:D1', '용어등록 목록 · 중복 없이 38개', title)
    master.merge_range('A2:D2', '이 네 칸에서만 수정 → 오른쪽복사·변경확인에 함께 반영', note)
    master.merge_range('A3:D3', '타입·크기는 R14 유지. 실제 등록한 명칭과 정의를 여기에 기록하세요.', note)
    master.set_row(0, 29)
    master.set_row(1, 21)
    master.set_row(2, 21)
    master.set_row(3, 25)
    master.freeze_panes(4, 0)
    master.add_table(3, 0, 41, 4, {'name': 'GoldTerms', 'style': 'Table Style Medium 2',
        'columns': [{'header': h} for h in HEADERS + ['고정연결번호']],
        'data': [x['values'] + [x['id']] for x in items]})
    base.write_row(0, 0, ['고정연결번호', *HEADERS, '사용테이블'])
    for idx, entry in enumerate(items):
        row = idx + 4
        for ci, text in enumerate(entry['values']):
            master.write_string(row, ci, text, editable)
        master.set_row(row, 90)
        usage = '\n'.join(f"{u['table_number']:02d} {u['table_logical']} ({u['table']})" for u in entry['usages'])
        master.write_comment(row, 0, 'R14 원래 용어: ' + entry['values'][0] + '\n사용 위치:\n' + usage)
        basis = entry['metadata_basis']
        type_note = '\n'.join(f'{k}: {basis[v]}' for k, v in [
            ('기준 도메인 형식', 'domain_format'), ('기준 길이', 'base_size'),
            ('한글 배수', 'korean_multiplier'), ('물리 크기', 'physical_size'), ('근거', 'basis')])
        master.write_comment(row, 2, type_note, {'width': 420, 'height': 180})
        base.write_row(idx + 1, 0, [entry['id'], *entry['values'], usage])
    master.conditional_format('A5:B42', {'type': 'blanks', 'format': error})
    for col in ['A', 'B']:
        master.conditional_format(f'{col}5:{col}42', {'type': 'duplicate', 'format': error})
    master.print_area('A1:D42')
    master.repeat_rows(0, 3)

    def lookup(number, col):
        return f'INDEX(\'용어목록\'!${col}$5:${col}$42,MATCH({number},\'용어목록\'!$E$5:$E$42,0))'

    copy.set_column('A:A', 14)
    copy.set_column('B:B', 49)
    copy.set_zoom(100)
    copy.merge_range('A1:B1', '골드 용어등록 · 38개', title)
    copy.merge_range('A2:B2', '오른쪽 값 셀을 복사해서 신청 화면에 붙여넣으세요.', note)
    copy.merge_range('A3:B3', '', link)
    copy.write_url('A3', "internal:'용어목록'!A5", link, '이름·물리명·정의 변경 → 용어목록에서 한 번만 수정')
    for r in range(3):
        copy.set_row(r, 28 if r == 0 else 22)
    copy.freeze_panes(3, 0)
    copy.activate()
    copy.set_selection('B5')
    change.set_zoom(85)
    for ci, width in enumerate([7, 21, 21, 29, 29, 25, 25, 14, 44, 48]):
        change.set_column(ci, ci, width)
    change.merge_range('A1:J1', '변경 확인 · 원래 용어와 현재 등록값, 사용되는 모든 테이블', title)
    change.merge_range('A2:J2', '용어목록의 수정값을 자동 표시합니다. 기존 B03·B05 신청 파일은 별도로 변경되지 않습니다.', note)
    change.set_row(0, 29)
    change.set_row(1, 24)
    change.write_row(3, 0, ['번호', '원래 논리명', '현재 논리명', '원래 물리명', '현재 물리명',
                              '원래 타입·크기', '현재 타입·크기', '변경 상태', '사용 테이블', '현재 정의'], head)
    change.set_row(3, 28)
    change.freeze_panes(4, 2)
    change.autofilter(3, 0, 41, 9)
    for idx, entry in enumerate(items):
        number = entry['id']
        row = 3 + idx * 6
        copy.merge_range(row, 0, row, 1, '', head)
        copy.write_formula(row, 0, f'="{number:02d} / 38 · "&{lookup(number, "A")}', head,
                           f'{number:02d} / 38 · {entry["values"][0]}')
        copy.set_row(row, 27)
        for ci, field in enumerate(HEADERS):
            rr = row + ci + 1
            copy.write_string(rr, 0, field, label)
            copy.write_formula(rr, 1, '=' + lookup(number, chr(65 + ci)), value, entry['values'][ci])
            copy.set_row(rr, 90 if ci == 3 else (38 if ci == 2 else 29))
        copy.write_comment(row + 3, 1, 'R14 물리 타입·크기입니다. 기준 도메인 형식·한글 환산 근거는 용어목록의 같은 타입 셀 메모에 있습니다.')
        copy.write_formula(row + 5, 0,
            f'=HYPERLINK("#\'용어목록\'!A"&(MATCH({number},\'용어목록\'!$E$5:$E$42,0)+4),"수정하기")',
            link, '수정하기')
        copy.write_string(row + 5, 1, f"사용 {len(entry['usages'])}곳 · 위치는 변경확인 시트", soft)
        copy.set_row(row + 5, 23)
        cr = idx + 4
        br = idx + 2
        change.write_number(cr, 0, number, value)
        for target_col, source_col, original_index in [(1, 'B', 0), (3, 'C', 1), (5, 'D', 2)]:
            change.write_formula(cr, target_col, f"='원본기준'!{source_col}{br}", soft, entry['values'][original_index])
        for target_col, source_col, original_index in [(2, 'A', 0), (4, 'B', 1), (6, 'C', 2), (9, 'D', 3)]:
            change.write_formula(cr, target_col, '=' + lookup(number, source_col), value, entry['values'][original_index])
        exprs = ','.join(f"{lookup(number, chr(65 + n))}<>'원본기준'!{chr(66 + n)}{br}" for n in range(4))
        change.write_formula(cr, 7, f'=IF(OR({exprs}),"변경됨","동일")', value, '동일')
        usage = '\n'.join(f"{u['table_number']:02d} {u['table_logical']} ({u['table']})" for u in entry['usages'])
        change.write_string(cr, 8, usage, value)
        change.set_row(cr, max(82, 18 * len(entry['usages'])))
    change.conditional_format('H5:H42', {'type': 'text', 'criteria': 'containing', 'value': '변경됨', 'format': changed})
    copy.print_area(0, 0, 230, 1)
    copy.repeat_rows(0, 2)
    book.close()

    # Read back both formulas and cached displayed values; no native Excel available here.
    displayed = load_workbook(FILE, data_only=True)
    formulas = load_workbook(FILE, data_only=False)
    assert displayed.active.title == '오른쪽복사'
    assert displayed['용어목록'].max_row == 42
    assert formulas['용어목록'].column_dimensions['E'].hidden
    assert formulas['원본기준'].sheet_state == 'hidden'
    count = 0
    for idx, entry in enumerate(items):
        assert [displayed['용어목록'].cell(idx + 5, c).value for c in range(1, 5)] == entry['values']
        for ci, text in enumerate(entry['values']):
            cell = displayed['오른쪽복사'].cell(5 + idx * 6 + ci, 2)
            assert cell.value == text
            expected = '=' + lookup(entry['id'], chr(65 + ci))
            assert formulas['오른쪽복사'][cell.coordinate].value == expected
            count += 1
        assert displayed['변경확인'].cell(idx + 5, 8).value == '동일'
    with zipfile.ZipFile(FILE) as z:
        assert z.testzip() is None
        assert not any('externalLinks/' in p or 'vbaProject' in p for p in z.namelist())
    assert sha(SOURCE) == source_hash
    dump('TERMS.json', {'source': str(SOURCE), 'source_sha256': source_hash, 'terms': items})
    dump('VALIDATION.json', {'status': 'PASS', 'unique_terms': 38, 'table_column_occurrences': 60,
        'tables': 13, 'copy_fields_checked': count, 'editable_fields_per_term': 4,
        'source_types_names_sizes_preserved': True, 'common_definition_policy': 'R14 first-occurrence generic definition; all role definitions retained in TERMS.json',
        'lookup_key': 'hidden immutable numeric key; name/physical-name edits do not alter joins',
        'formula_results': 'cached values verified; Excel recalculates on open/edit',
        'native_excel_render_or_calculation_tested': False, 'source_model_unchanged': True,
        'existing_submission_workbooks_modified': False, 'email_sent': False,
        'file': FILE.name, 'bytes': FILE.stat().st_size, 'sha256': sha(FILE)})
    preview(displayed)
    print(json.dumps({'file': str(FILE), 'terms': len(items), 'copy_fields_checked': count, 'bytes': FILE.stat().st_size}, ensure_ascii=False))


def preview(book):
    """Small layout preview using actual cached worksheet cells, not an Excel screenshot."""
    sheet = book['오른쪽복사']
    width, height = 480, 790
    image = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(image)
    fontpath = '/mnt/c/Windows/Fonts/malgun.ttf'
    font = ImageFont.truetype(fontpath, 14)
    small = ImageFont.truetype(fontpath, 12)
    large = ImageFont.truetype(fontpath, 20)
    def write_wrapped(text, x, y, max_width, f, color, max_height):
        lines, line = [], ''
        for ch in str(text):
            if ch == '\n' or draw.textlength(line + ch, font=f) > max_width:
                lines.append(line)
                line = '' if ch == '\n' else ch
            else:
                line += ch
        if line:
            lines.append(line)
        lineheight = f.size + 6
        assert len(lines) * lineheight <= max_height, (text, len(lines), max_height)
        for n, part in enumerate(lines):
            draw.text((x, y + n * lineheight), part, font=f, fill=color)
    y = 10
    for r in range(1, 16):
        h = math.ceil((sheet.row_dimensions[r].height or 15) * 96 / 72)
        if r <= 3:
            write_wrapped(sheet.cell(r, 1).value, 12, y + 2, 456, large if r == 1 else small, '#16324F', h)
        elif (r - 4) % 6 == 0:
            draw.rectangle((8, y, 472, y + h), fill='#16324F')
            write_wrapped(sheet.cell(r, 1).value, 16, y + 6, 440, font, 'white', h - 4)
        else:
            is_footer = (r - 4) % 6 == 5
            draw.rectangle((8, y, 113, y + h), fill='#F0F4F8' if is_footer else '#DCEEF0')
            draw.line((8, y + h, 472, y + h), fill='#D8E2EC')
            write_wrapped(sheet.cell(r, 1).value or '', 14, y + 6, 95, small, '#16324F', h - 4)
            write_wrapped(sheet.cell(r, 2).value or '', 123, y + 6, 339, small if is_footer else font, '#16324F', h - 4)
        y += h
    image.crop((0, 0, width, min(y + 10, height))).save(OUT / '오른쪽복사_배치미리보기.png')


if __name__ == '__main__':
    main()
