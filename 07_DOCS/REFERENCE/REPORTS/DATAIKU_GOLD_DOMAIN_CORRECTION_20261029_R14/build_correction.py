"""Correct Gold metadata documents only; read local source IDs without DB writes."""
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import csv
import hashlib
import json
import re
import sqlite3
import zipfile

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
BASE = OUT.parent
R13 = BASE / 'DATAIKU_GOLD_SUBMISSION_20261029_R13'
R12 = BASE / 'DATAIKU_GOLD_COMPACT_20261029_R12'
AUDIT = ROOT / '09_ARTIFACTS/AUDITS/20261028-gold-photo-schema-review'
SHORT_IDS = {'DOC_ID', 'STRC_UNIT_ID', 'UPPR_STRC_UNIT_ID', 'BODY_SLC_ID', 'SRC_UNIT_ID'}
KOREAN_CONTENT = {'RFRN_DTA_IDNF_CTNT', 'BLNG_DTA_IDNF_CTNT', 'TAGT_DTA_IDNF_CTNT'}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def dump(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def measure():
    pointer_path = ROOT / '01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'
    pointer = json.loads(pointer_path.read_text())
    release = json.loads((ROOT / pointer['manifest_path']).read_text())
    generation = ROOT / release['data_path']
    checks = [
        ('store.sqlite', 'document', 'document_id', 50),
        ('store.sqlite', 'document', 'name', 2250),
        ('store.sqlite', 'source_unit', 'unit_id', 50),
        ('store.sqlite', 'source_unit', 'parent_id', 50),
        ('store.sqlite', 'block_payload', 'block_id', 50),
        ('store.sqlite', 'block_payload', 'unit_id', 50),
        ('navigation/navigation.sqlite', 'source', 'id', 50),
    ]
    results = []
    for filename, table, column, limit in checks:
        path = generation / filename
        before = path.stat()
        with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as db:
            db.execute('PRAGMA query_only=ON')
            db.execute('PRAGMA cache_size=-4096')
            sql = (f'SELECT COUNT({column}), MAX(LENGTH({column})), '
                   f'MAX(LENGTH(CAST({column} AS BLOB))), '
                   f'SUM(CASE WHEN LENGTH({column}) != LENGTH(CAST({column} AS BLOB)) THEN 1 ELSE 0 END), '
                   f'SUM(CASE WHEN LENGTH(CAST({column} AS BLOB)) > ? THEN 1 ELSE 0 END) FROM {table}')
            values = db.execute(sql, (limit,)).fetchone()
        after = path.stat()
        assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
        assert values[-1] == 0
        results.append(dict(file=str(path.relative_to(ROOT)), table=table, column=column,
                            limit_bytes=limit, **dict(zip(
                                ['non_null_rows', 'max_chars', 'max_utf8_bytes', 'non_ascii_rows', 'over_limit'], values))))
    return {'scope': 'Selected local generation; not onsite Oracle',
            'release_id': pointer['release_id'], 'generation_path': release['data_path'],
            'measurements': results}


def rules(c):
    name = c['name']
    if name in SHORT_IDS:
        return ('ID / VARCHAR2(50)', '50', '1', '50 BYTE',
                '사진 판독 기록의 ID 50을 같은 ID 도메인에 재사용. 현재 로컬 문서16·구조/본문5·원문32 BYTE. 문자열·선행 0 보존. 미래 50 BYTE 초과값은 절단하지 않고 이행 시 거절.')
    if name in KOREAN_CONTENT:
        return ('내용 / VARCHAR2(1000)', '1000', '3', '3000 BYTE',
                '사용자가 확인한 내용 도메인 1000을 기준으로 한글 3바이트 지시 적용. 1000×3=3000 BYTE는 물리 저장 길이이며 새 인포타입 3000을 임의 선택한 것이 아님. 기존 검색키 512 BYTE 초과 해시 규칙은 별도 계약으로 유지.')
    if name == 'DOC_NAME':
        return ('명 / 사진 기재 2250 BYTE', '사진 최종값 2250 BYTE', '추가 곱셈 없음', '2250 BYTE',
                '사진 판독 기록에 이미 2250 BYTE로 기재된 최종 길이를 유지. 기준 인포타입 이름이나 최초 환산 전 길이는 추정하지 않음. 중복 3배 적용 없음.')
    if c['dtype'] == 'CLOB':
        return ('내용 / CLOB', '가변', '해당 없음', '가변', 'CLOB에는 고정 문자열 길이 곱셈을 적용하지 않음.')
    if c['dtype'] == 'VECTOR':
        return ('값 / VECTOR (기존 벡터안)', '가변 차원 / FLOAT32', '해당 없음', c['size'],
                '벡터 차원은 문자열 길이가 아님. 기존 설계 유지; 벡터의 정식 인포타입명·현장 지원은 제공 자료에 없어 확인 완료로 표시하지 않음.')
    if c['dtype'] == 'VARCHAR2':
        return (f"{c['domain']} / VARCHAR2(100)", '100', '1', '100 BYTE',
                '사진 및 사용자 후속 지시의 같은 도메인 100 재사용. 한글 직접 저장 열이 아니므로 3배 적용 없음.')
    return (f"{c['domain']} / {c['type']}", c['size'], '해당 없음', c['size'],
            '숫자 정밀도·소수자리·시간대·여부 타입은 기존 정의 유지. 문자열 한글 배수와 구분.')


def model():
    original = json.loads((R12 / 'MODEL.json').read_text())
    result = deepcopy(original)
    result['version'] = 'gold-domain-correction-r14'
    result['status'] = 'R14 도메인별 확인값·한글 길이 정정 / DB·제품 미반영'
    changes = []
    for table in result['tables']:
        for c in table['columns']:
            before = {k: c[k] for k in ('domain', 'words', 'type', 'dtype', 'size', 'korean')}
            if c['name'] in SHORT_IDS:
                assert c['domain'] == 'ID' and c['type'] == 'VARCHAR2(1000 BYTE)'
                c.update(type='VARCHAR2(50 BYTE)', size='50 BYTE', korean='N')
            if c['name'] in KOREAN_CONTENT:
                assert c['domain'] == '내용' and c['korean'] == 'Y'
                c.update(type='VARCHAR2(3000 BYTE)', size='3000 BYTE')
            if c['name'] == 'CHAN_NO':
                c.update(domain='순번', words='변경', korean='해당 없음')
            after = {k: c[k] for k in before}
            c['metadata_basis'] = dict(zip(
                ['domain_format', 'base_size', 'korean_multiplier', 'physical_size', 'basis'], rules(c)))
            if before != after:
                c['change'] = 'R14 도메인별 허용 형식 및 한글 바이트 정정'
                changes.append({'table': table['suffix'], 'column': c['name'], 'before': before, 'after': after,
                                'basis': c['metadata_basis']['basis']})
    assert len(changes) == 16
    assert sum(x['column'] in SHORT_IDS for x in changes) == 12
    assert sum(x['column'] in KOREAN_CONTENT for x in changes) == 3
    return original, result, changes


def workbook(m, agent):
    source = R13 / f'법률에이전트_{agent}_골드신청용_R13.xlsx'
    book = load_workbook(source)
    for sheet in book:
        for row in sheet:
            for cell in row:
                if isinstance(cell.value, str):
                    cell.value = cell.value.replace('R13', 'R14')
        sheet.oddFooter.center.text = 'R14 도메인·길이 정정 · &P / &N'
    book.worksheets[0]['A2'] = 'R14 도메인·길이 정정 · 13개 테이블 / 60개 컬럼 · DB 생성 미완료'
    for sheet, table in zip(book.worksheets[1:14], m['tables'], strict=True):
        sheet['A2'] = 'R14 신청용 정의서 · 도메인별 기준 길이 및 한글 환산 적용 · DB 생성 미완료'
        for row, c in enumerate(table['columns'], 5):
            assert sheet.cell(row, 3).value == c['name']
            for col, key in ((4, 'domain'), (5, 'words'), (6, 'dtype'), (7, 'size'), (12, 'korean')):
                sheet.cell(row, col).value = c[key]
            basis = c['metadata_basis']
            sheet.cell(row, 7).comment = Comment(
                f"기준 형식: {basis['domain_format']}\n기준 길이: {basis['base_size']}\n"
                f"한글 환산: {basis['korean_multiplier']}\nDB 길이: {basis['physical_size']}\n{basis['basis']}",
                'R14 도메인·길이 근거')
    book.properties.title = f'{agent} 골드 신청용 R14 — 도메인·한글 길이 정정'
    book.properties.description = 'R13 대체. ID 50/100; 한글 식별내용 기준1000×3; 문서명2250 BYTE 유지. 13표60열·PK·일반인덱스11개 유지.'
    path = OUT / f'법률에이전트_{agent}_골드신청용_R14.xlsx'
    book.save(path)
    return source, path


def ddl(m, agent):
    lines = ['-- R14 REVIEW TEMPLATE ONLY. No database execution.',
             '-- Domain baseline and physical Korean byte size are documented in the R14 inventory.',
             '-- {{APPROVED_GOLD_OWNER}} must be resolved before any deployment.',
             '-- Physical PK/NOT NULL and regular indexes; soft FK validation remains in the application.', '']
    for t in m['tables']:
        name = f"IDD_{agent}_LGL_{t['suffix']}"
        pk = [c['name'] for c in sorted(t['columns'], key=lambda x: x['pk']) if c['pk']]
        fields = ['  ' + c['name'] + ' ' + c['type'] + (' DEFAULT ' + c['default'] if c.get('default') else '')
                  + (' NOT NULL' if c['required'] else '') for c in t['columns']]
        fields.append('  CONSTRAINT X0_' + name + ' PRIMARY KEY (' + ', '.join(pk) + ')')
        lines += ['-- ' + t['logical'], 'CREATE TABLE {{APPROVED_GOLD_OWNER}}.' + name + ' (', ',\n'.join(fields), ');']
        for i, cols in enumerate(t['indexes'], 1):
            lines.append(f'CREATE INDEX {{{{APPROVED_GOLD_OWNER}}}}.X{i}_{name} ON {{{{APPROVED_GOLD_OWNER}}}}.{name} (' + ', '.join(cols) + ');')
        lines.append('')
    (OUT / f'GOLD_{agent}_DDL_REVIEW.sql').write_text('\n'.join(lines), encoding='utf-8')


def add_sheet(book, name, headers, rows, widths):
    s = book.create_sheet(name)
    s.append(headers)
    for row in rows:
        s.append(row)
    s.freeze_panes = 'A2'
    s.auto_filter.ref = s.dimensions
    s.sheet_view.showGridLines = False
    for i, width in enumerate(widths, 1):
        s.column_dimensions[get_column_letter(i)].width = width
    for row in s:
        s.row_dimensions[row[0].row].height = 32 if row[0].row == 1 else 70
        for cell in row:
            cell.font = Font(name='맑은 고딕', size=10, bold=cell.row == 1, color='FFFFFF' if cell.row == 1 else '172A3A')
            cell.fill = PatternFill('solid', fgColor='17365D' if cell.row == 1 else 'EEF3F8' if cell.row % 2 == 0 else 'FFFFFF')
            cell.alignment = Alignment(wrap_text=True, vertical='center')
    s.print_title_rows = '1:1'
    s.sheet_properties.pageSetUpPr.fitToPage = True
    s.page_setup.orientation = 'landscape'
    s.page_setup.fitToWidth = 1
    s.page_setup.fitToHeight = 0


def inventory(m, changes, measurements):
    book = Workbook()
    book.remove(book.active)
    groups, unique = defaultdict(list), defaultdict(list)
    for t in m['tables']:
        for c in t['columns']:
            groups[(c['domain'], c['type'])].append((t['short'], c))
            unique[c['name']].append((t['short'], c))
    group_rows = []
    for i, ((domain, typ), values) in enumerate(sorted(groups.items()), 1):
        c = values[0][1]
        b = c['metadata_basis']
        group_rows.append([i, domain, b['domain_format'], b['base_size'], b['korean_multiplier'], typ,
                           len(values), ' · '.join(dict.fromkeys(x['logical'] for _, x in values)), b['basis']])
    add_sheet(book, '01_중복제거12', ['번호', '도메인', '기준 형식 (정식명 아님)', '기준 길이', '한글 배수', 'DB 타입·길이', '적용 열 수', '사용 컬럼', '근거·적용 구분'],
              group_rows, [7, 12, 30, 25, 20, 35, 12, 75, 85])
    column_rows = []
    for i, (name, values) in enumerate(sorted(unique.items()), 1):
        c = values[0][1]
        column_rows.append([i, c['logical'], name, c['domain'], c['metadata_basis']['domain_format'], c['type'],
                            c['korean'], len(values), '\n'.join(t for t, _ in values)])
    add_sheet(book, '02_고유컬럼38', ['번호', '논리명', '물리명', '도메인', '기준 형식', 'DB 타입·길이', '한글', '사용 표 수', '사용 테이블'],
              column_rows, [7, 28, 35, 12, 32, 35, 10, 12, 36])
    add_sheet(book, '03_변경16행', ['테이블', '컬럼', '이전 도메인·타입·한글', '수정 도메인·타입·한글', '수정 근거'],
              [[x['table'], x['column'], x['before']['domain'] + ' / ' + x['before']['type'] + ' / ' + x['before']['korean'],
                x['after']['domain'] + ' / ' + x['after']['type'] + ' / ' + x['after']['korean'], x['basis']] for x in changes], [20, 35, 40, 40, 105])
    add_sheet(book, '04_로컬실측', ['테이블', '컬럼', '값 있는 행 수', '최대 글자 수', '최대 UTF8 BYTE', '수정 한도 BYTE', '초과 행 수', '비ASCII 행 수'],
              [[x['table'], x['column'], x['non_null_rows'], x['max_chars'], x['max_utf8_bytes'], x['limit_bytes'], x['over_limit'], x['non_ascii_rows']]
               for x in measurements['measurements']], [22, 22, 18, 18, 22, 22, 16, 20])
    notes = [
        ['범위', 'R14 골드 신청안 13표60열. B03/B05 동일 모델. 도메인·타입12조합, 고유컬럼38개. DB 생성·제품 반영 없음.'],
        ['도메인별 선택', 'ID 도메인 50/100, 값 도메인100, 내용 도메인1000/CLOB 등 사용자 확인값의 해당 도메인 안에서 선택. 다른 도메인의 길이를 복사하지 않음. 정식 인포타입 이름·코드는 만들어 쓰지 않음.'],
        ['사진 근거', '원본 사진의 임시 경로는 현재 없음. 당시 사진 전사 검토표·검토 스크립트와 사용자 정정 지시를 대조. 현재 사진을 직접 재열람했다고 표시하지 않음.'],
        ['ID 수정', '문서ID 사진값50을 같은 ID 도메인의 원문·구조·본문 ID에 재사용. 게시·조회자료·개념그룹·벡터구간 ID는 사용자 확인100 유지. ID 1000은 전부 제거.'],
        ['한글 환산', '조회·소속·대상 자료식별내용 3열은 기준 내용1000×3=DB3000 BYTE. CLOB·숫자·일시·벡터·영문ID는 곱하지 않음.'],
        ['한글 표시 정정', '벡터 표의 DOC_ID·SRC_UNIT_ID는 실제 영문·숫자 생성 규칙에 맞춰 Y→N. VCTR_HEAD의 숫자 CHAN_NO는 N→해당 없음.'],
        ['문서명', '사진 판독 기록의 최종 2250 BYTE 유지. 기준 인포타입이750이었다고 추정하지 않으며2250에 다시3을 곱하지 않음. 사용자의 추가 정정이 있으면 그 확인값을 적용.'],
        ['실측 범위', '선택된 로컬 데이터만 읽기 전용으로 실측. 현장 Oracle 적재·실행계획·인덱스 생성 시험은 수행하지 않음.'],
        ['운영 이행', '기존 제품은 일부 ID512 BYTE까지 허용한다. R14 물리 모델로 전환할 때50/100 BYTE 경계 검증을 연결하고 초과값을 자르지 않는다. 이번에는 제품 코드를 변경하지 않음.'],
        ['유지', 'PK13개·필수·NULL·기본값·11일반인덱스·13표60열 유지. 소프트FK 정책 유지. 기존 관계키·조회 알고리즘 변경 없음.'],
        ['기존 1000의 원인', '과거512가없다는 요청을ID와내용도메인에 구분없이1000으로 적용하고 후속본까지 유지했던 부분을 정정. 사진의 문서ID50을 복구하고 같은 도메인에 재사용.'],
        ['벡터', '임베딩값의 기존VECTOR(*,FLOAT32) 유지. 제공 자료에 없는 정식 벡터 인포타입명/현장 지원은 확인 완료로 표시하지 않음.'],
    ]
    add_sheet(book, '05_근거와범위', ['항목', '설명'], notes, [25, 145])
    path = OUT / '골드_R14_인포타입_중복제거.xlsx'
    book.save(path)
    with (OUT / '인포타입_중복제거.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([cell.value for cell in book.worksheets[0][1]])
        writer.writerows(group_rows)
    return path


def verify(original, m, pairs, inv):
    signatures = {}
    for ot, t in zip(original['tables'], m['tables'], strict=True):
        assert t['indexes'] == ot['indexes']
        for old, c in zip(ot['columns'], t['columns'], strict=True):
            for key in ('name', 'logical', 'pk', 'required', 'definition', 'source', 'default'):
                assert c.get(key) == old.get(key), (t['suffix'], c['name'], key)
            # Definitions describe each table role; compare the shared domain/type/encoding contract.
            sig = (c['logical'], c['domain'], c['words'].replace(' · ', ''), c['type'], c['korean'])
            assert c['name'] not in signatures or signatures[c['name']] == sig
            signatures[c['name']] = sig
            if c['domain'] == 'ID':
                assert c['type'] in {'VARCHAR2(50 BYTE)', 'VARCHAR2(100 BYTE)'}
    assert len(signatures) == 38
    assert m['relationships'] == original['relationships']
    results = []
    for source, path in pairs:
        before, after = load_workbook(source), load_workbook(path)
        assert after.sheetnames == before.sheetnames and len(after.worksheets) == 15
        assert list(after.worksheets[-1].iter_rows(min_row=4, values_only=True)) == list(before.worksheets[-1].iter_rows(min_row=4, values_only=True))
        rows = 0
        cell_diffs = []
        for old, new, t in zip(before.worksheets[1:14], after.worksheets[1:14], m['tables'], strict=True):
            for r, c in enumerate(t['columns'], 5):
                rows += 1
                for col in range(1, 13):
                    if old.cell(r, col).value != new.cell(r, col).value:
                        assert col in (4, 5, 6, 7, 12)
                        cell_diffs.append({'sheet': new.title, 'cell': new.cell(r, col).coordinate,
                                           'before': old.cell(r, col).value, 'after': new.cell(r, col).value})
                assert [new.cell(r, x).value for x in (3, 4, 5, 6, 7, 12)] == [c[x] for x in ('name', 'domain', 'words', 'dtype', 'size', 'korean')]
        assert rows == 60 and len(cell_diffs) == 20
        assert not any(c.data_type == 'f' for s in after for row in s for c in row)
        with zipfile.ZipFile(path) as z:
            assert z.testzip() is None
            assert not any(n.lower().endswith(('.js', '.jsx', '.mjs', '.cjs')) for n in z.namelist())
        results.append({'file': path.name, 'sha256': sha(path), 'bytes': path.stat().st_size,
                        'tables': 13, 'columns': 60, 'sheets': 15, 'pk_definitions': 13,
                        'regular_indexes': 11, 'column_cell_changes': cell_diffs})
    a, b = [load_workbook(p, data_only=True) for _, p in pairs]
    normalize = lambda x: x.replace('B03', 'BXX').replace('B05', 'BXX') if isinstance(x, str) else x
    for sa, sb in zip(a, b, strict=True):
        for ra, rb in zip(sa.iter_rows(values_only=True), sb.iter_rows(values_only=True), strict=True):
            assert list(map(normalize, ra)) == list(map(normalize, rb))
    invbook = load_workbook(inv, data_only=True)
    assert [s.max_row - 1 for s in invbook.worksheets[:3]] == [12, 38, 16]
    assert sum(r[6] for r in invbook.worksheets[0].iter_rows(min_row=2, values_only=True)) == 60
    for agent in ('B03', 'B05'):
        sql = (OUT / f'GOLD_{agent}_DDL_REVIEW.sql').read_text()
        assert sql.count('CREATE TABLE ') == 13 and sql.count('CREATE INDEX ') == 11
        assert sql.count('PRIMARY KEY (') == 13
        assert 'VARCHAR2(1000 BYTE)' not in sql
        assert sql.count('VARCHAR2(50 BYTE)') == 12 and sql.count('VARCHAR2(3000 BYTE)') == 3
        assert not re.search(r'\b(FOREIGN KEY|CHECK\s*\(|CREATE UNIQUE INDEX|DROP TABLE)\b', sql)
        for t in m['tables']:
            for c in t['columns']:
                assert re.search(r'^  ' + re.escape(c['name'] + ' ' + c['type']) + r'(?:[,\s]|$)', sql, re.M)
    return {'status': 'PASS_DOCUMENT_AND_LOCAL_LENGTH_CHECK', 'workbooks': results,
            'unique_columns': 38, 'domain_type_combinations': 12, 'id_1000_remaining': 0,
            'id_shortened_rows': 12, 'korean_multiplied_rows': 3, 'domain_corrected_rows': 1,
            'korean_flag_corrected_rows': 3,
            'definitions_pk_null_defaults_indexes_preserved': True,
            'database_changed': False, 'product_changed': False, 'mail_sent': False,
            'onsite_oracle_tested': False, 'native_excel_render': False,
            'original_photo_reopened': False,
            'document_name_2250_retained_from_photo_transcription': True}


def main():
    inputs = [R12 / 'MODEL.json', AUDIT / 'build_review.py', AUDIT / '사진10장_49컬럼_검토.xlsx',
              BASE / 'DATAIKU_GOLD_REGISTER_20261028_R8/SOURCE_PHOTOS.json']
    inputs += [R13 / f'법률에이전트_{a}_골드신청용_R13.xlsx' for a in ('B03', 'B05')]
    sources = [{'path': str(p.relative_to(ROOT)), 'sha256': sha(p)} for p in inputs]
    measured = measure()
    original, current, changes = model()
    pairs = [workbook(current, a) for a in ('B03', 'B05')]
    for agent in ('B03', 'B05'):
        ddl(current, agent)
    inv = inventory(current, changes, measured)
    validation = verify(original, current, pairs, inv)
    for p, s in zip(inputs, sources, strict=True):
        assert sha(p) == s['sha256']
    dump('MODEL.json', current)
    dump('CHANGES.json', changes)
    dump('LOCAL_MEASUREMENTS.json', measured)
    dump('SOURCES.json', {'files': sources, 'original_photos_available': False,
                         'photo_evidence_used': 'preserved contemporaneous transcription and user correction'})
    dump('VALIDATION.json', validation)
    with (OUT / 'COLUMNS.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['table', 'column', 'logical', 'domain', 'type', 'pk_order', 'required', 'source', 'basis'])
        for t in current['tables']:
            for c in t['columns']:
                writer.writerow([t['suffix'], c['name'], c['logical'], c['domain'], c['type'], c['pk'], c['required'], c['source'], c['metadata_basis']['basis']])
    print(json.dumps({k: v for k, v in validation.items() if k != 'workbooks'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
