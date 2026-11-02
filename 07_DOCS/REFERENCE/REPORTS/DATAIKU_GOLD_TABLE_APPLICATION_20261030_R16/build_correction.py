"""Apply the user's MNFST -> DTLS registration correction; preserve active DB mappings."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import zipfile

from openpyxl import load_workbook
from openpyxl.worksheet.table import TableColumn

ROOT = Path('/home/jin/8-AGENT')
OUT = Path(__file__).resolve().parent
OLD_DIR = OUT.parent / 'DATAIKU_GOLD_TABLE_APPLICATION_20261030_R15'
ENGINE = ROOT / '08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
SOURCE = OLD_DIR / '법률에이전트_B03_테이블신청_사진확정컬럼_R15.xlsx'
TARGET = OUT / '법률에이전트_B03_테이블신청_등록확정컬럼_R16.xlsx'
MAPPING = ENGINE / 'mapping_r16_registration.json'
BEFORE, AFTER = 'MNFST_HASH_VALU', 'DTLS_HASH_VALU'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    protected = [SOURCE, ENGINE/'ACTIVE_MAPPING.json', ENGINE/'mapping_local_current.json', ENGINE/'mapping_r14_photos.json']
    unchanged = {str(p.relative_to(ROOT)): sha(p) for p in protected}
    original_mapping = json.loads((ENGINE/'mapping_r14_photos.json').read_text())
    corrected = copy.deepcopy(original_mapping)
    corrected['revision'] = '20261030-r16-registration-dtls-r1'
    affected = []
    for key, table in corrected['tables'].items():
        for column in table['columns'].values():
            if column['name'] == BEFORE:
                column['name'] = AFTER
                affected.append(key)
    assert affected == ['DOC_VER','DOC_UNIT','DOC_BLK','SRC_POST']
    MAPPING.write_text(json.dumps(corrected,ensure_ascii=False,indent=2)+'\n')
    module_spec = importlib.util.spec_from_file_location('registration_map',ENGINE/'physical_mapping.py')
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    mapped = module.GoldMapping.load(MAPPING)
    assert all(mapped.column(t,BEFORE) == AFTER for t in affected)
    ddl = '\n'.join(mapped.ddl())
    assert BEFORE not in ddl
    assert ddl.count('CREATE TABLE ') == 13 and ddl.count('CREATE INDEX ') == 11
    for key in affected:
        assert AFTER + ' AS ' + BEFORE in mapped.projection(key)

    wb = load_workbook(SOURCE)
    replacements = []
    for ws in wb:
        for row in ws:
            for c in row:
                if isinstance(c.value,str):
                    old = c.value
                    c.value = old.replace(BEFORE,AFTER).replace('R15','R16')
                    if BEFORE in old:
                        replacements.append({'sheet':ws.title,'cell':c.coordinate,'before':old,'after':c.value})
        for part in [ws.oddFooter.left,ws.oddFooter.center,ws.oddFooter.right]:
            if part.text: part.text = part.text.replace('R15','R16').replace('사진 기준 컬럼','등록 확정 컬럼')
    guide = wb['00_사용안내']
    guide['B1'] = 'B03 · 등록 확정 컬럼 · R16 · 2026-10-30'
    guide['B3'] = '테이블 신청에는 R15 대신 이 R16 파일을 사용한다. 사용자 정정에 따라 명세해시값의 물리명을 DTLS_HASH_VALU로 변경했다.'
    guide['B6'] = '사진 6장의 최종 명칭·타입에 사용자 후속 정정(명세=MNFST → DTLS)을 반영했다. 현재 신청 물리명은 DTLS_HASH_VALU이다.'
    guide['B7'] = '테이블·정의·타입·필수·기본값은 기존 R15와 동일하다. 명세해시값을 쓰는 4개 테이블 및 PK 3개·일반 인덱스 3개의 컬럼 참조를 정정했다.'
    guide['B31'] = '사진 6장 + 2026-10-30 사용자 명세=DTLS 정정 / mapping_r16_registration.json / R14 MODEL·DDL'
    guide['B32'] = sha(MAPPING)
    guide['B33'] = '사진 원본은 과거 근거로 보존한다. 이번 명세해시값 명칭은 사진 이후의 사용자 정정이 우선한다.'
    # This field is about the correction record; retain the old name only in the explicit comparison sheet.
    guide['B6'] = guide['B6'].value.replace('명세=MNFST → DTLS','명세 약어=DTLS')
    compare = wb['08_사진명칭대조']
    compare.title = '08_명칭대조'
    compare['B1'] = '확정물리명'; compare['D1'] = '확정논리명'
    new_row = compare.max_row+1
    for column,value in enumerate([BEFORE,AFTER,'명세해시값','명세해시값',4,'2026-10-30 사용자 후속 정정'],1):
        cell = compare.cell(new_row,column,value)
        cell._style = copy.copy(compare.cell(new_row-1,column)._style)
    compare.row_dimensions[new_row].height = 44
    for table in compare.tables.values():
        table.ref = f'A1:F{new_row}'
        table.autoFilter.ref = table.ref
        table.tableColumns[1].name = '확정물리명'
        table.tableColumns[3].name = '확정논리명'
    wb.properties.title = '법률에이전트 B03 테이블 신청 R16 — 명세해시값 DTLS 정정'
    wb.save(TARGET)

    check = load_workbook(TARGET,data_only=False)
    baseline = load_workbook(SOURCE,data_only=False)
    # Every copy grid, including the 13 table tabs, must equal the original with exactly the registered rename.
    for ws in baseline:
        if ws.title in ['00_사용안내','08_사진명칭대조']: continue
        new = check[ws.title]
        assert (ws.max_row,ws.max_column) == (new.max_row,new.max_column)
        for row in ws:
            for c in row:
                expected = c.value.replace(BEFORE,AFTER).replace('R15','R16') if isinstance(c.value,str) else c.value
                assert new[c.coordinate].value == expected,(ws.title,c.coordinate)
    columns = list(check['02_컬럼'].values)[1:]
    pk = list(check['05_PK'].values)[1:]
    indexes = list(check['03_인덱스'].values)[1:]
    assert len(columns)==60 and len({r[3] for r in columns})==38
    assert sum(r[3]==AFTER for r in columns)==4
    assert sum(r[4]==AFTER for r in pk)==3
    assert sum(AFTER in r[7] and r[6]=='N' for r in indexes)==3
    assert len({r[2] for r in pk})==13 and len(indexes)==24
    for ws in check:
        for row in ws:
            for c in row:
                assert c.data_type!='f'
                if isinstance(c.value,str) and ws.title!='08_명칭대조': assert BEFORE not in c.value
    with zipfile.ZipFile(TARGET) as archive:
        assert archive.testzip() is None
        assert not any(p.lower().endswith(('.js','.jsx','.mjs','.cjs')) for p in archive.namelist())
    assert unchanged == {str(p.relative_to(ROOT)):sha(p) for p in protected}
    receipt = {'status':'PASS', 'correction':{'old':BEFORE,'new':AFTER,'basis':'User correction 2026-10-30; supersedes photograph name'},
               'xlsx':str(TARGET.relative_to(ROOT)), 'sha256':sha(TARGET),'bytes':TARGET.stat().st_size,
               'mapping':str(MAPPING.relative_to(ROOT)),'mapping_sha256':sha(MAPPING),
               'affected_tables':affected,'columns_changed':4,'pk_definitions_affected':3,'regular_indexes_affected':3,
               'tables':13,'column_rows':60,'unique_columns':38,'pk_constraints':13,'regular_indexes':11,
               'cells_renamed':len(replacements),'cell_changes':replacements,'protected_files_unchanged':unchanged,
               'checks':['serialized workbook exact rename comparison','mapping parser and DDL/projection name checks','PK/index reference checks','ZIP integrity'],
               'database_changes':0,'active_mapping_changes':0,'native_excel_rendered':False}
    (OUT/'VALIDATION.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    (OUT/'정정내역.txt').write_text('명세 약어 정정 — 2026-10-30\n\n사용자 후속 정정: MNFST_HASH_VALU → DTLS_HASH_VALU. 논리명 명세해시값·정의·타입은 동일.\nB03 신청 엑셀 R16은 R15를 대체한다.\n적용: DOC_VER / DOC_UNIT / DOC_BLK / SRC_POST의 4개 컬럼. PK3개·일반 인덱스3개의 구성컬럼도 정정.\n신청 대상 매핑: 08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/mapping_r16_registration.json\n기존 사진·R15 발송본·mapping_r14_photos.json은 과거 근거로 보존.\n매핑 내부의 MNFST_HASH_VALU 키는 기존 엔진 논리키이며 실제 SQL 컬럼은 DTLS_HASH_VALU로 변환한다.\n현재 로컬 DB 및 ACTIVE_MAPPING.json→mapping_local_current.json은 이번에 변경하지 않았다.\n신청용 R14 크기와 실제 로컬 보존 크기는 다르므로 새 신청용 매핑을 현재 DB에 활성화하지 않는다.\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ['cell_changes','protected_files_unchanged']},ensure_ascii=False))


if __name__=='__main__': main()
