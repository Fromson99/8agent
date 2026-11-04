"""Assemble a separate ZIP-input Flow; preserve all prior handoffs byte-for-byte."""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PACKAGE = HERE / 'package'
PARENT = HERE.parent / 'gold_vector_structure_20261104_r4/package'


def main():
    engine = PACKAGE / 'engine'
    engine.mkdir(parents=True, exist_ok=True)
    for src in PARENT.rglob('*'):
        if not src.is_file() or '__pycache__' in src.parts:
            continue
        if src.suffix not in {'.py', '.json', '.csv', '.txt'}:
            continue
        dst = engine / src.relative_to(PARENT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    for src in (HERE / 'engine_overrides').glob('*.py'):
        shutil.copyfile(src, engine / src.name)
    # These readers never execute code or restore runtime files from the data ZIP.
    for name in ('oracle_existing_zip.py', 'oracle_legacy_parts.py', 'oracle_transfer_progress.py'):
        src = REPO / '02_BACKEND/lawrag/pipeline' / name
        shutil.copyfile(src, engine / 'vendor/02_BACKEND/lawrag/pipeline' / name)
    registration = json.loads((PACKAGE / 'registration_current.json').read_text())
    development = json.loads((engine / 'contract.json').read_text())
    rows = []
    for key, table in registration['tables'].items():
        dev = development['tables'][key]
        for order, (logical, col) in enumerate(table['columns'].items(), 1):
            rows.append([key, table['name'], dev['owner']+'.'+dev['name'], order,
                         logical, col['name'], col['type'], 'Y' if col['required'] else 'N',
                         table['primary_key'].index(logical)+1 if logical in table['primary_key'] else '',
                         col['default'] or ''])
    headers = ['구분', 'Gold 등록 테이블', '기존 개발계 테이블', '컬럼 순서', '코드 내부 이름',
               '실제 컬럼명', 'Oracle 타입', 'NOT NULL', 'PK 순서', '기본값']
    with (HERE / 'GOLD_R19_MAPPING.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f); writer.writerow(headers); writer.writerows(rows)
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = Workbook(); ws = wb.active; ws.title = '13테이블_60컬럼'
    ws.append(headers)
    for row in rows: ws.append(row)
    ws.freeze_panes = 'A2'; ws.auto_filter.ref = ws.dimensions
    for cell in ws[1]:
        cell.font = Font(color='FFFFFF', bold=True)
        cell.fill = PatternFill('solid', fgColor='244B65')
    for col, width in zip('ABCDEFGHIJ', [18, 30, 36, 12, 29, 31, 31, 12, 12, 20]):
        ws.column_dimensions[col].width = width
    notes = wb.create_sheet('읽기안내')
    for text in [
        'Gold 최신 등록 정의 / registration_current.json 매핑 기준: B003, 문서ID100, RGSN_ASTM, RFRN_DATA_HASH_VALU/CTNT, CHAN_NO',
        '현장 DB 실조회 결과가 아닙니다. 실제 owner는 실행 파라미터로 지정합니다.',
        '등록 정의의 owner는 미지정이며 GOLD_OWNER 실행 파라미터를 사용합니다.',
        '13개 테이블, 컬럼 항목 총60개. Agent 기록4테이블은 이 Flow의 적재 대상이 아닙니다.',
        '온톨로지3테이블은 구조 확인만 합니다. VCTR_HEAD는 이번 검색 게시본에만 신규 연결하며 기존 서비스 채널을 교체하지 않습니다.',
        'VECTOR(*,FLOAT32)는 실제 DB의 native VECTOR 지원을 사전 확인합니다.',
    ]: notes.append([text])
    notes.column_dimensions['A'].width = 120
    wb.save(HERE / 'GOLD_R19_MAPPING.xlsx')
    shutil.copyfile(HERE/'GOLD_R19_MAPPING.csv', PACKAGE/'GOLD_R19_MAPPING.csv')
    hashes = {p.relative_to(PACKAGE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(PACKAGE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts
              and p.name != 'FLOW_MANIFEST.json' and p.suffix != '.pyc'}
    (PACKAGE/'FLOW_MANIFEST.json').write_text(json.dumps({'version':'gold-zip-flow-20261104-r1',
        'files':hashes}, indent=2)+'\n')
    archive = HERE/'DATAIKU_GOLD_ZIP_FLOW_20261104_R1.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in sorted([*hashes, 'FLOW_MANIFEST.json']): z.write(PACKAGE/name, name)
    bootstrap = (HERE/'bootstrap_template.py').read_text().replace('@@ZIP_SHA@@', hashlib.sha256(archive.read_bytes()).hexdigest())
    cell = (HERE/'params_template.py').read_text() + '\n' + bootstrap
    cell += '\nfrom zip_install import install\nFLOW_CONFIG = install(PARAMS, '+repr(bootstrap)+')\n'
    (HERE/'DATAIKU_GOLD_ZIP_FLOW_RUN_R1.txt').write_text(cell)
    print(json.dumps({'zip_bytes':archive.stat().st_size,'members':len(hashes)+1,'tables':len(registration['tables']),
                      'columns':len(rows),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}))


if __name__ == '__main__': main()
