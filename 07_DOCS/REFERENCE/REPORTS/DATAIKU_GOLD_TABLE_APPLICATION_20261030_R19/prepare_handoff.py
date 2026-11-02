"""Build a current, validated informational workbook from the prior integrated handoff."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import zipfile
from openpyxl import load_workbook

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
PREV = OUT.parent / 'DATAIKU_GOLD_TABLE_APPLICATION_20261030_R18'
SOURCE = PREV / '법률에이전트_B03_컬럼_PK_인덱스_통합_R18.xlsx'
CANONICAL = PREV / '법률에이전트_B03_테이블별_컬럼정의_R18.xlsx'
TARGET = OUT / '법률에이전트_B03_골드테이블_최종통합_R19.xlsx'
GUIDE = OUT / '골드테이블_R19_반영사항과_사용안내.txt'
MAPDIR = ROOT / '08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    source_hash = sha(SOURCE)
    canonical_hash = sha(CANONICAL)
    wb = load_workbook(SOURCE)
    changes = []
    for ws in wb:
        for row in ws:
            for cell in row:
                if isinstance(cell.value, str) and 'VCTR_SEG_ID' in cell.value:
                    old = cell.value
                    cell.value = old.replace('VCTR_SEG_ID', 'VCTR_SCTN_ID')
                    changes.append({'sheet': ws.title, 'cell': cell.coordinate, 'before': old, 'after': cell.value})
        for footer in (ws.oddFooter, ws.evenFooter, ws.firstFooter):
            for part in (footer.left, footer.center, footer.right):
                if part.text:
                    part.text = part.text.replace('R18', 'R19').replace('VCTR_SEG_ID', 'VCTR_SCTN_ID')
    assert len(changes) == 6, changes
    main_sheet = wb.worksheets[0]
    main_sheet['A1'] = 'B03 골드 신청 R19 · 컬럼 / PK / 인덱스 최종 통합'
    main_sheet['A2'] = '13개 테이블·60개 컬럼. 전체 보기와 테이블별 시트에 같은 정보를 담았습니다. 이전 R18 통합본 대신 이 파일을 사용하세요.'
    main_sheet['A3'] = '명세해시값=DTLS_HASH_VALU / 벡터구간ID=VCTR_SCTN_ID / 신청용 타입·길이 유지 / X0: PK 자동 생성 / X1 이후: 추가 인덱스'
    wb.properties.title = '법률에이전트 B03 골드테이블 최종 통합 R19'
    wb.properties.subject = '13개 테이블·60개 컬럼·PK·인덱스·파티션 신청 정의'
    wb.save(TARGET)

    check = load_workbook(TARGET)
    original = load_workbook(SOURCE)
    canonical = load_workbook(CANONICAL)
    mapping = json.loads((MAPDIR / 'mapping_r18_registration.json').read_text())
    by_name = {t['name']: t for t in mapping['tables'].values()}
    pointer = json.loads((MAPDIR / 'ACTIVE_MAPPING.json').read_text())
    active_path = MAPDIR / pointer['mapping_file']
    assert sha(active_path) == pointer['sha256']
    active = json.loads(active_path.read_text())
    assert {k: (t['name'], [c['name'] for c in t['columns'].values()]) for k,t in mapping['tables'].items()} == {k: (t['name'], [c['name'] for c in t['columns'].values()]) for k,t in active['tables'].items()}
    assert check.sheetnames == original.sheetnames and len(check.worksheets) == 14
    columns = pk_count = index_count = 0
    for ws in check.worksheets[1:]:
        table = by_name[ws['B2'].value]
        cols = list(table['columns'].items())
        assert ws['B3'].value == next(r[4] for r in canonical.worksheets[0].iter_rows(min_row=2,values_only=True) if r[2] == table['name'])
        assert tuple(ws.cell(7,c).value for c in range(1,9)) == tuple(canonical[ws.title].cell(5,c).value for c in range(1,9))
        for i,(key, col) in enumerate(cols,8):
            values = tuple(ws.cell(i,c).value for c in range(1,9))
            assert values == tuple(canonical[ws.title].cell(i-2,c).value for c in range(1,9)), (ws.title,i)
            expected_pk = table['primary_key'].index(key)+1 if key in table['primary_key'] else None
            assert values[1:7] == (col['name'], 'Y' if expected_pk else 'N', 'N' if col['required'] else 'Y', expected_pk, col['type'], col['default'])
            columns += 1
        sections = []
        for i in range(1,ws.max_row+1):
            if ws.cell(i,1).value == '컬럼 논리명':
                rows = []
                j = i+1
                while j <= ws.max_row and ws.cell(j,2).value:
                    rows.append(tuple(ws.cell(j,c).value for c in range(1,9)))
                    j += 1
                sections.append(rows)
        expected_indexes = [table['primary_key']] + table['indexes']
        assert len(sections) == len(expected_indexes)
        for idx,(rows,keys) in enumerate(zip(sections,expected_indexes)):
            assert [r[1] for r in rows] == [table['columns'][k]['name'] for k in keys]
            assert [r[2] for r in rows] == list(range(1,len(keys)+1))
            assert all(r[3:7] == ('ASC','Y' if idx==0 else 'N','Y' if idx==0 else 'N','B-TREE') for r in rows)
        pk_count += 1
        index_count += len(sections)-1
        assert next(ws.cell(i,2).value for i in range(1,ws.max_row+1) if ws.cell(i,1).value=='파티션 여부') == 'N'
        starts = [i-1 for i in range(21,check.worksheets[0].max_row+1) if check.worksheets[0].cell(i,1).value=='테이블 물리명' and check.worksheets[0].cell(i,2).value==table['name']]
        assert len(starts)==1
        for i in range(1,ws.max_row+1):
            assert tuple(ws.cell(i,c).value for c in range(1,9)) == tuple(check.worksheets[0].cell(starts[0]+i-1,c).value for c in range(1,9))
    assert columns == 60 and pk_count == 13 and index_count == 11
    for before,after in zip(original,check):
        assert str(before.merged_cells) == str(after.merged_cells)
        assert before.freeze_panes == after.freeze_panes
        assert before.max_row == after.max_row and before.max_column == after.max_column
        for row in before:
            for c in row:
                a = after[c.coordinate]
                assert a.style_id == c.style_id
                if not (before == original.worksheets[0] and c.coordinate in ('A1','A2','A3')):
                    expected = c.value.replace('VCTR_SEG_ID','VCTR_SCTN_ID') if isinstance(c.value,str) else c.value
                    assert a.value == expected
                if isinstance(a.value,str):
                    assert 'VCTR_SEG_ID' not in a.value and 'MNFST_HASH_VALU' not in a.value
    with zipfile.ZipFile(TARGET) as z:
        assert z.testzip() is None
        assert not any(Path(n).suffix.lower() in ('.js','.jsx','.mjs','.cjs') for n in z.namelist())
    assert sha(SOURCE)==source_hash and sha(CANONICAL)==canonical_hash
    GUIDE.write_text('''골드 레이어 테이블 최종 통합 R19 — 2026-10-30

사용 파일: 법률에이전트_B03_골드테이블_최종통합_R19.xlsx
이전에 보낸 법률에이전트_B03_컬럼_PK_인덱스_통합_R18.xlsx 대신 이번 R19를 사용합니다.
같은 R18 번호의 테이블별 컬럼 정의서에는 최종 벡터 이름이 반영되어 있었지만,
이전 발송 통합본에는 옛 이름이 남아 있어 R19에서 일치시켰습니다.

포함 범위
- B03 골드 13개 테이블, 총60개 컬럼.
- 첫 시트 00_전체_한시트: 전체 테이블의 컬럼·PK·인덱스·파티션을 이어서 표시.
- 이어지는 13개 시트: 같은 내용을 테이블별로 표시.
- 테이블 논리명·물리명·정의, 컬럼 논리명·영문 물리명·PK·NULL 허용·PK 순서·타입/길이·기본값·정의.
- PK 인덱스13개, 추가 일반 인덱스11개: 이름·구성컬럼·순서·정렬·UNIQUE 여부·등록 방법.
- 13개 테이블 모두 파티션 미사용. 테이블스페이스는 현장에서 확인한 값으로 입력.

최종 반영사항
1. 명세해시값은 DTLS_HASH_VALU. DOC_VER/DOC_UNIT/DOC_BLK/SRC_POST와 관련 PK·인덱스에 적용.
2. 벡터구간ID는 VCTR_SCTN_ID. 전체 보기 및 개별 시트의 컬럼·PK·추가 인덱스 총6곳을 정정.
3. 컬럼 표의 첫4열은 논리명 / 물리명 / PK / NULL 허용.
4. 사용자 사진·정정에 따른 기존 B03 테이블명·나머지 컬럼명·신청용 타입/길이·기본값을 유지.
5. PK=Y 지정 시 X0 자동 생성. 일반 인덱스는 추가 항목에 순서대로 입력하며 UNIQUE를 해제.

적용 범위와 상태
- 이 파일은 골드 메타 등록·생성 신청용 정의서입니다. 실행할 코드나 SQL은 없습니다.
- 현장 등록 승인·DBA 생성·배포 완료를 의미하지 않습니다.
- 로컬 Oracle에서는 DTLS_HASH_VALU와 VCTR_SCTN_ID 이름 변경을 완료했으며,
  활성 매핑은 mapping_local_vctr_current.json입니다.
- 신청용 이름/타입 기준은 mapping_r18_registration.json과 같습니다.
  R19는 전달 문서 버전이며 새로운 DB 스키마 버전이나 새 매핑을 뜻하지 않습니다.
- 신청용 타입·길이와 로컬 DB에 보존된 기존 타입·길이는 구분합니다.
- 승인 전 온톨로지 작업 JSON, 사용자 로그·LLM 판단·감사 기록은 이번 골드13개 테이블 범위에 추가하지 않습니다.

발송 전 확인
13테이블60컬럼의 이름·타입·NULL·기본값·PK 순서가 최종 신청 매핑 및 최신 테이블별 정의서와 일치합니다.
PK13개·일반 인덱스11개의 컬럼과 순서를 확인했으며, 전체 보기와 개별 시트의 내용이 일치합니다.
로컬 활성 매핑과 물리 테이블·컬럼 이름도 일치합니다. 이번 발송 작업에서 DB 변경은 없습니다.
''', encoding='utf-8')
    result = {'status':'PASS','created_at':datetime.now(timezone.utc).isoformat(),'table_count':13,'column_count':columns,'primary_key_indexes':pk_count,'additional_indexes':index_count,'all_table_columns_match_latest_canonical':True,'registration_mapping_matches':True,'active_mapping_physical_names_match':True,'index_columns_and_order_match':True,'combined_and_individual_sheets_match':True,'source_files_unchanged':True,'layout_and_styles_preserved':True,'native_excel_rendered':False,'changes':changes,'sources':[{'path':str(SOURCE.relative_to(ROOT)),'sha256':source_hash},{'path':str(CANONICAL.relative_to(ROOT)),'sha256':canonical_hash}],'attachments':[{'path':str(p),'filename':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in (TARGET,GUIDE)]}
    (OUT/'VALIDATION.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    main()
